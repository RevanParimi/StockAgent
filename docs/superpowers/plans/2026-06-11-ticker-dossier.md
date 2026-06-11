# Ticker Dossier — RL Knowledge Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the per-ticker living dossier (daily curator + weekly distillation), make lessons executable via trigger tags, and surface the accumulated knowledge to both the forecast agents and the chatbot.

**Architecture:** New `TickerDossier` Pydantic schema persisted by `PredictionStore`; a `DossierCurator` LLM step (Step 8.5) in the daily review that runs every day (hits AND misses); a static keyword event tagger + `trigger_tags` on lessons so claims fire deterministically on matching days; digest injection into `BaseAgent` prompts and a new chat tool. Everything flag-gated, non-fatal, atomic-write.

**Tech Stack:** Python 3.13, Pydantic v2, OpenRouter/Qwen via `services/clients/llm_client.py`, pytest, APScheduler.

**Spec:** `docs/superpowers/specs/2026-06-11-ticker-dossier-knowledge-layer-design.md`

**Critical path facts (pre-verified):**
- Real schemas/settings live in `src/backend/shared/...`; `core/schemas/feedback.py` and `core/config/settings/base.py` are re-export shims. `core/config/prompts/` and `core/intelligence/rl/` are REAL files.
- Settings style: module-level `NAME: type = os.getenv("NAME", "default")` constants.
- Imports: `from core.config import settings`, `from backend.shared.schemas.feedback import ...` both work.
- `PredictionStore` (`core/intelligence/rl/stores/prediction_store.py`): atomic `_write_json` (line 153), `_read_json` (168), path helpers e.g. `_learning_ledger_path()` (146).
- `daily_review.py`: market_context fully assembled by ~line 629; `fb_output = fb_agent.run(...)` line 769; `_revise_remaining_forecasts(...)` def line 238, called line 977; `final_entry` built ~line 1004 and persisted line 1011 (`store.append_feedback_entry`).
- `generate_forecast.py`: `_apply_ledger_micro_adjustments` lines 79–120; `_build_daily_forecasts` from line 122.
- `base_agent.py`: system prompt assembled lines 102–103 (sync) and 139–140 (async); lazy `_extra_queries` pattern lines 428–436 + 479–485; agents have `self.sector` and `self.agent_name`.
- `base_orchestrator.py`: weights auto-load lines 112–114 (async) and 174–176 (sync); explicit injection from `generate_forecast.py:267` and `daily_review.py:176`.
- Chat: `services/api/routes/ui_data.py` — `_ctx_rl_learning` line 1386 (bugs: `sector="automobile"` line 1393; nonexistent `wm.learned_weights` line 1409); second hardcode line 1271; tool dispatch `_dispatch_chat_tool` line 2483; envelope tool `_chat_tool_rl_prediction` line 2405 (directory-scan pattern to copy); `_CHAT_SYSTEM_PROMPT` line 2514.
- Scheduler weekly job: `services/scheduler/python/scheduler.py` — `ledger_cleanup_weekly` registered ~line 225–234; job body `_ledger_cleanup_job` ~line 412.
- Test conventions: `tests/unit/intelligence/rl/`, run via `python -m pytest <path> -v`.

---

## File Structure

| File | Status | Responsibility |
|---|---|---|
| `src/backend/shared/schemas/dossier.py` | NEW | All dossier models + `to_digest()` |
| `src/backend/shared/schemas/feedback.py` | MODIFY | `EVENT_TAGS`, `tag_events()`, `Lesson` claim fields, `FeedbackEntry.event_tags` |
| `src/backend/shared/config/settings/base.py` | MODIFY | 9 new settings |
| `core/intelligence/rl/stores/prediction_store.py` | MODIFY | dossier load/save |
| `core/intelligence/rl/algorithms/lesson_emphasis.py` | NEW | `apply_lesson_emphasis()`, `calendar_day_tags()` |
| `core/config/prompts/shared/dossier_curator.py` | NEW | curator + distillation prompts |
| `core/intelligence/rl/agents/dossier_curator.py` | NEW | `DossierCurator.run()`, `_merge()`, `distill_dossier()` |
| `core/config/prompts/shared/feedback_agent.py` | MODIFY | lesson contract: trigger_tags + agent lists |
| `core/intelligence/rl/agents/feedback_agent.py` | MODIFY | parse + merge passthrough of claim fields |
| `core/intelligence/rl/workflows/daily_review.py` | MODIFY | today_tags, Step-7 emphasis, `event_tags` persist, Step 8.5 curator |
| `core/intelligence/rl/workflows/generate_forecast.py` | MODIFY | per-day calendar-tag emphasis; narrow legacy micro-adjust |
| `src/backend/shared/pipeline/base_agent.py` | MODIFY | dossier digest injection |
| `src/backend/shared/pipeline/base_orchestrator.py` | MODIFY | per-ticker weight scoping |
| `services/scheduler/python/scheduler.py` | MODIFY | weekly distillation |
| `services/api/routes/ui_data.py` | MODIFY | `get_ticker_dossier` tool; sector + weights bug fixes |
| `services/scheduler/run_schedule.py` (or package CLI entry) | MODIFY | `dossier-status` subcommand |
| `docs/RL_DESIGN.md` | MODIFY | document the knowledge layer |

Tests: `tests/unit/intelligence/rl/test_event_tags.py`, `test_dossier_schema.py`, `test_dossier_store.py`, `test_lesson_emphasis.py`, `test_dossier_curator.py`, `test_dossier_distill.py`, `test_feedback_claim_fields.py`, `test_forecast_emphasis.py`, `tests/unit/pipeline/test_agent_dossier_injection.py`, `tests/unit/api/test_chat_dossier_tool.py`.

---

### Task 1: Settings

**Files:**
- Modify: `src/backend/shared/config/settings/base.py`
- Test: `tests/unit/intelligence/rl/test_event_tags.py` (settings asserts piggyback on Task 2's file; this task uses an import smoke check)

- [ ] **Step 1: Add the 9 settings** — append near the other RL_* constants (keep the file's aligned style):

```python
# ── RL Knowledge Layer — Ticker Dossier + executable claims (2026-06) ──────
RL_DOSSIER_ENABLED: bool = os.getenv("RL_DOSSIER_ENABLED", "true").lower() == "true"
DOSSIER_MAX_OBSERVATIONS: int = int(os.getenv("DOSSIER_MAX_OBSERVATIONS", "30"))
DOSSIER_DIGEST_MAX_CHARS: int = int(os.getenv("DOSSIER_DIGEST_MAX_CHARS", "2500"))
DOSSIER_AGENT_DIGEST_CHARS: int = int(os.getenv("DOSSIER_AGENT_DIGEST_CHARS", "1500"))
DOSSIER_MAX_NEW_OBS_PER_DAY: int = int(os.getenv("DOSSIER_MAX_NEW_OBS_PER_DAY", "3"))
RL_CLAIMS_ENABLED: bool = os.getenv("RL_CLAIMS_ENABLED", "true").lower() == "true"
RL_LESSON_EMPHASIS_DELTA: float = float(os.getenv("RL_LESSON_EMPHASIS_DELTA", "0.03"))
RL_LESSON_EMPHASIS_CAP: float = float(os.getenv("RL_LESSON_EMPHASIS_CAP", "0.06"))
RL_LESSON_MATCH_MIN_CONF: float = float(os.getenv("RL_LESSON_MATCH_MIN_CONF", "0.45"))
```

NOTE: if the file defines settings inside a class/object instead of module level anywhere relevant, match whichever style the existing `RL_BOOST` / `WEIGHT_MAX_STEP` constants use in this same file.

- [ ] **Step 2: Smoke check**

Run: `python -c "from core.config import settings; print(settings.RL_DOSSIER_ENABLED, settings.RL_LESSON_EMPHASIS_DELTA)"`
Expected: `True 0.03`

- [ ] **Step 3: Commit**

```bash
git add src/backend/shared/config/settings/base.py
git commit -m "feat(rl): settings for ticker dossier + executable claims"
```

---

### Task 2: EVENT_TAGS vocabulary + static tagger + schema fields

**Files:**
- Modify: `src/backend/shared/schemas/feedback.py`
- Test: `tests/unit/intelligence/rl/test_event_tags.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for EVENT_TAGS vocabulary, tag_events(), and claim fields on Lesson/FeedbackEntry."""
from backend.shared.schemas.feedback import (
    EVENT_TAGS, tag_events, Lesson, FeedbackEntry,
)


def test_vocabulary_is_frozen_and_complete():
    assert isinstance(EVENT_TAGS, frozenset)
    for tag in ("central_bank_event", "fii_flow", "crude_price", "expiry_week",
                "block_deal", "budget_event", "monsoon", "guidance_change"):
        assert tag in EVENT_TAGS


def test_tag_events_matches_keywords_case_insensitive():
    ctx = "RBI held rates today; FII sold 2200Cr; Brent crude spiked past $90."
    tags = tag_events(ctx)
    assert "central_bank_event" in tags
    assert "fii_flow" in tags
    assert "crude_price" in tags
    assert tags == sorted(set(tags))           # sorted, unique


def test_tag_events_empty_and_no_match():
    assert tag_events("") == []
    assert tag_events("calm uneventful session") == []


def test_lesson_claim_fields_default_empty():
    l = Lesson(lesson_id="L001", date_learned="2026-06-11", category="macro",
               pattern="rbi_day", observation="x", rule="y")
    assert l.trigger_tags == []
    assert l.prioritise_agents == []
    assert l.discount_agents == []


def test_feedback_entry_event_tags_default_empty():
    e = FeedbackEntry(day=1, date="2026-06-11", predicted_close=100.0,
                      actual_close=101.0, price_error_pct=1.0, direction_correct=True)
    assert e.event_tags == []
```

NOTE: if `FeedbackEntry` requires more mandatory fields, copy the minimal-constructor pattern from an existing test in `tests/unit/intelligence/rl/` (e.g. `test_lesson_decay.py`) and adjust.

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/unit/intelligence/rl/test_event_tags.py -v`
Expected: FAIL — `ImportError: cannot import name 'EVENT_TAGS'`

- [ ] **Step 3: Implement in `feedback.py`**

Add near the `semantic_tags` vocabulary comment (~line 424):

```python
# Controlled event-tag vocabulary shared by Lesson.trigger_tags, FeedbackEntry.event_tags
# and the dossier curator. Superset of the semantic_tags vocabulary.
EVENT_TAGS: frozenset = frozenset({
    "central_bank_event", "fii_flow", "crude_price", "currency", "earnings_event",
    "guidance_change", "sector_policy", "technical_pattern", "seasonal", "credit_event",
    "supply_chain", "regulatory", "global_macro", "expiry_week", "block_deal",
    "monsoon", "budget_event",
})

_EVENT_KEYWORD_MAP: dict = {
    "rbi": "central_bank_event", "mpc": "central_bank_event",
    "repo rate": "central_bank_event", "rate cut": "central_bank_event",
    "rate hike": "central_bank_event",
    "fed ": "global_macro", "federal reserve": "global_macro", "fomc": "global_macro",
    "tariff": "global_macro",
    "fii": "fii_flow", "dii": "fii_flow", "foreign institutional": "fii_flow",
    "crude": "crude_price", "brent": "crude_price", "opec": "crude_price",
    "rupee": "currency", "usdinr": "currency", "usd/inr": "currency",
    "earnings": "earnings_event", "quarterly results": "earnings_event",
    "net profit": "earnings_event", "dividend": "earnings_event",
    "guidance": "guidance_change", "outlook revised": "guidance_change",
    "subsidy": "sector_policy", "pli scheme": "sector_policy", "fame": "sector_policy",
    "sebi": "regulatory", "penalty": "regulatory", "investigation": "regulatory",
    "rsi": "technical_pattern", "macd": "technical_pattern",
    "breakout": "technical_pattern", "support level": "technical_pattern",
    "npa": "credit_event", "downgrade": "credit_event", "default": "credit_event",
    "chip shortage": "supply_chain", "semiconductor": "supply_chain",
    "supply chain": "supply_chain",
    "expiry": "expiry_week", "max pain": "expiry_week",
    "block deal": "block_deal", "bulk deal": "block_deal",
    "monsoon": "monsoon",
    "budget": "budget_event",
    "festive": "seasonal", "diwali": "seasonal", "navratri": "seasonal",
}


def tag_events(market_context: str) -> list:
    """Deterministic keyword → event-tag mapping. Pure, never raises."""
    if not market_context:
        return []
    low = market_context.lower()
    return sorted({tag for kw, tag in _EVENT_KEYWORD_MAP.items() if kw in low})
```

On `Lesson` (after `semantic_tags`, ~line 430):

```python
    # Executable-claim fields (2026-06 knowledge layer). All optional — legacy lessons
    # without trigger_tags keep the category-based micro-adjustment path.
    trigger_tags: list[str] = Field(default_factory=list)      # subset of EVENT_TAGS
    prioritise_agents: list[str] = Field(default_factory=list) # agents to boost when fired
    discount_agents: list[str] = Field(default_factory=list)   # agents to dampen when fired
```

On `FeedbackEntry` (next to `regime_label`):

```python
    # Static-tagger event tags for the review day (deterministic; see tag_events()).
    event_tags: list[str] = Field(default_factory=list)
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/unit/intelligence/rl/test_event_tags.py -v`
Expected: 5 PASS

- [ ] **Step 5: Regression check** (schemas are imported everywhere)

Run: `python -m pytest tests/unit/intelligence/rl -q`
Expected: all pass (same baseline as before this task)

- [ ] **Step 6: Commit**

```bash
git add src/backend/shared/schemas/feedback.py tests/unit/intelligence/rl/test_event_tags.py
git commit -m "feat(rl): EVENT_TAGS vocabulary, static tagger, claim fields on Lesson/FeedbackEntry"
```

---

### Task 3: `TickerDossier` schema + `to_digest`

**Files:**
- Create: `src/backend/shared/schemas/dossier.py`
- Test: `tests/unit/intelligence/rl/test_dossier_schema.py`

- [ ] **Step 1: Write failing tests**

```python
from backend.shared.schemas.dossier import (
    TickerDossier, DossierObservation, ResponseSignature, GuidanceItem,
    RecurringCatalyst, OpenQuestion,
)


def _dossier() -> TickerDossier:
    return TickerDossier(
        ticker="MARUTI", sector="automobile",
        created_at="2026-06-01", last_updated="2026-06-11",
        business_summary="India's largest passenger-car maker.",
        current_thesis="BUY — rural recovery + stable crude.", thesis_since="2026-06-01",
        response_signatures=[ResponseSignature(
            signature_id="RS001", trigger_tags=["crude_price"],
            response="closes -1.5% to -2.5% within 2 sessions of crude > $90",
            occurrences=4, first_seen="2026-05-02", last_seen="2026-06-09",
            confidence=0.7, evidence_dates=["2026-05-02", "2026-06-09"])],
        guidance=[GuidanceItem(date="2026-05-21", source="Q4 earnings call",
                               guidance="FY27 dispatch growth 8-10%")],
        recurring_catalysts=[RecurringCatalyst(
            name="FADA dispatch data", typical_timing="~10th monthly",
            expected_effect="±1% same-day move")],
        flow_notes="FII net buyers 3 weeks running.",
        open_questions=[OpenQuestion(question="Will EV capex dent margins?",
                                     raised_on="2026-06-02")],
        observations=[DossierObservation(date="2026-06-10",
                                         observation="Dealer inventory down 3 days MoM.",
                                         tags=["seasonal"], materiality=0.6)],
    )


def test_digest_contains_priority_sections_and_header():
    d = _dossier().to_digest(2500)
    assert d.startswith("# MARUTI dossier")
    for needle in ("Thesis", "Response signatures", "crude", "FADA", "Dealer inventory"):
        assert needle in d


def test_digest_respects_budget_and_drops_whole_sections():
    full = _dossier().to_digest(5000)
    small = _dossier().to_digest(220)
    assert len(small) <= 220
    assert small.startswith("# MARUTI dossier")
    assert len(small) < len(full)
    assert not small.rstrip().endswith(("-", ","))   # no mid-section truncation


def test_dead_signature_excluded_from_digest():
    doss = _dossier()
    doss.response_signatures[0].contradictions = 5   # >= occurrences → dead
    assert "crude > $90" not in doss.to_digest(2500)


def test_resolved_question_excluded():
    doss = _dossier()
    doss.open_questions[0].resolved_on = "2026-06-10"
    assert "EV capex" not in doss.to_digest(2500)


def test_empty_dossier_digest_is_just_header():
    d = TickerDossier(ticker="TCS", sector="it_sector",
                      created_at="2026-06-11", last_updated="2026-06-11")
    out = d.to_digest(2500)
    assert out.startswith("# TCS dossier")
    assert "##" not in out
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/unit/intelligence/rl/test_dossier_schema.py -v`
Expected: FAIL — `ModuleNotFoundError: backend.shared.schemas.dossier`

- [ ] **Step 3: Implement `src/backend/shared/schemas/dossier.py`**

```python
"""
TickerDossier — per-ticker living knowledge document (RL knowledge layer).

Persisted as data/predictions/{sector}/{TICKER}/{TICKER}_dossier.json (PERMANENT).
Updated daily by DossierCurator (Step 8.5 of daily review), consolidated weekly
by distill_dossier(). Consumed as a markdown digest by the forecast agents and
the chat `get_ticker_dossier` tool. See spec 2026-06-11.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class DossierObservation(BaseModel):
    """One day's factual observation — the episodic buffer entry."""
    date: str
    observation: str
    tags: list[str] = Field(default_factory=list)
    materiality: float = Field(ge=0.0, le=1.0, default=0.5)
    outcome_link: str = ""            # "hit" | "miss" | ""


class ResponseSignature(BaseModel):
    """Quantified behavioral pattern: trigger → typical price response."""
    signature_id: str
    trigger_tags: list[str] = Field(default_factory=list)
    response: str
    occurrences: int = 1
    contradictions: int = 0
    first_seen: str = ""
    last_seen: str = ""
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    evidence_dates: list[str] = Field(default_factory=list)   # cap 10 at merge time

    @property
    def is_alive(self) -> bool:
        return self.contradictions < self.occurrences


class GuidanceItem(BaseModel):
    date: str
    source: str
    guidance: str
    status: str = "open"              # open | met | missed | withdrawn


class RecurringCatalyst(BaseModel):
    name: str
    typical_timing: str
    expected_effect: str
    hit_rate: str = ""


class OpenQuestion(BaseModel):
    question: str
    raised_on: str
    resolved_on: str = ""
    answer: str = ""


class TickerDossier(BaseModel):
    ticker: str
    sector: str
    created_at: str
    last_updated: str
    version: int = 1
    business_summary: str = ""
    current_thesis: str = ""
    thesis_since: str = ""
    response_signatures: list[ResponseSignature] = Field(default_factory=list)
    guidance: list[GuidanceItem] = Field(default_factory=list)
    recurring_catalysts: list[RecurringCatalyst] = Field(default_factory=list)
    flow_notes: str = ""
    open_questions: list[OpenQuestion] = Field(default_factory=list)
    observations: list[DossierObservation] = Field(default_factory=list)

    def to_digest(self, max_chars: int = 2500) -> str:
        """Markdown digest for prompt injection. Whole sections only, priority order."""
        sections: list[str] = []
        if self.business_summary:
            sections.append(f"## Business\n{self.business_summary}")
        if self.current_thesis:
            since = self.thesis_since or self.created_at
            sections.append(f"## Thesis (since {since})\n{self.current_thesis}")
        live = sorted((s for s in self.response_signatures if s.is_alive),
                      key=lambda s: s.confidence, reverse=True)[:8]
        if live:
            lines = [f"- [{', '.join(s.trigger_tags)}] {s.response}"
                     f" (seen {s.occurrences}x, conf {s.confidence:.2f})" for s in live]
            sections.append("## Response signatures\n" + "\n".join(lines))
        open_g = [g for g in self.guidance if g.status == "open"][-5:]
        if open_g:
            sections.append("## Open guidance\n" + "\n".join(
                f"- {g.date} ({g.source}): {g.guidance}" for g in open_g))
        if self.recurring_catalysts:
            sections.append("## Recurring catalysts\n" + "\n".join(
                f"- {c.name} ({c.typical_timing}): {c.expected_effect}"
                + (f" [hit rate {c.hit_rate}]" if c.hit_rate else "")
                for c in self.recurring_catalysts[:6]))
        if self.flow_notes:
            sections.append(f"## Institutional flows\n{self.flow_notes}")
        open_q = [q for q in self.open_questions if not q.resolved_on][:4]
        if open_q:
            sections.append("## Open questions\n" + "\n".join(
                f"- {q.question} (since {q.raised_on})" for q in open_q))
        if self.observations:
            recent = sorted(self.observations, key=lambda o: o.date)[-5:]
            sections.append("## Recent observations\n" + "\n".join(
                f"- {o.date}: {o.observation}" for o in recent))

        out = f"# {self.ticker} dossier (updated {self.last_updated}, v{self.version})"
        for sec in sections:
            if len(out) + len(sec) + 2 > max_chars:
                break
            out += "\n\n" + sec
        return out
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/unit/intelligence/rl/test_dossier_schema.py -v`
Expected: 5 PASS

- [ ] **Step 5: Commit**

```bash
git add src/backend/shared/schemas/dossier.py tests/unit/intelligence/rl/test_dossier_schema.py
git commit -m "feat(rl): TickerDossier schema with budgeted markdown digest"
```

---

### Task 4: Dossier persistence in `PredictionStore`

**Files:**
- Modify: `core/intelligence/rl/stores/prediction_store.py`
- Test: `tests/unit/intelligence/rl/test_dossier_store.py`

- [ ] **Step 1: Write failing tests**

```python
from backend.shared.schemas.dossier import TickerDossier
from core.intelligence.rl.stores.prediction_store import PredictionStore


def _store(tmp_path):
    # PredictionStore accepts a base dir override the same way existing store tests
    # construct it — copy the fixture/constructor pattern from
    # tests/integration/test_prediction_store.py and point it at tmp_path.
    return PredictionStore(ticker="TESTX", sector="automobile", base_dir=tmp_path)


def test_load_dossier_returns_none_when_absent(tmp_path):
    assert _store(tmp_path).load_dossier() is None


def test_save_then_load_roundtrip(tmp_path):
    store = _store(tmp_path)
    d = TickerDossier(ticker="TESTX", sector="automobile",
                      created_at="2026-06-11", last_updated="2026-06-11",
                      current_thesis="test thesis")
    store.save_dossier(d)
    loaded = store.load_dossier()
    assert loaded is not None
    assert loaded.current_thesis == "test thesis"
    assert loaded.ticker == "TESTX"


def test_save_stamps_last_updated_today(tmp_path):
    from datetime import date
    store = _store(tmp_path)
    d = TickerDossier(ticker="TESTX", sector="automobile",
                      created_at="2026-01-01", last_updated="2026-01-01")
    store.save_dossier(d)
    assert store.load_dossier().last_updated == date.today().isoformat()
```

NOTE: check `PredictionStore.__init__` (line 105) for the actual base-dir parameter name (`base_dir`, `data_dir`, or settings monkeypatch) and use the same pattern as `tests/integration/test_prediction_store.py`. Adjust `_store()` accordingly — that's environment plumbing, not behavior.

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/unit/intelligence/rl/test_dossier_store.py -v`
Expected: FAIL — `AttributeError: ... has no attribute 'load_dossier'`

- [ ] **Step 3: Implement** — add after `save_learning_ledger`/`load_learning_ledger` (~line 299), mirroring their structure:

```python
    # ------------------------------------------------------------------
    # Ticker dossier (PERMANENT — RL knowledge layer)
    # ------------------------------------------------------------------

    def _dossier_path(self) -> Path:
        return self._learning_ledger_path().parent / f"{self.ticker}_dossier.json"

    def load_dossier(self):
        from backend.shared.schemas.dossier import TickerDossier
        data = self._read_json(self._dossier_path())
        if not data:
            return None
        try:
            return TickerDossier(**data)
        except Exception as exc:
            logger.error("[PredictionStore] Corrupt dossier for %s: %s", self.ticker, exc)
            return None

    def save_dossier(self, dossier) -> None:
        from datetime import date as _date
        dossier.last_updated = _date.today().isoformat()
        self._write_json(self._dossier_path(), dossier.model_dump())
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/unit/intelligence/rl/test_dossier_store.py -v`
Expected: 3 PASS

- [ ] **Step 5: Commit**

```bash
git add core/intelligence/rl/stores/prediction_store.py tests/unit/intelligence/rl/test_dossier_store.py
git commit -m "feat(rl): dossier persistence in PredictionStore (atomic, permanent)"
```

---

### Task 5: `apply_lesson_emphasis` + `calendar_day_tags`

**Files:**
- Create: `core/intelligence/rl/algorithms/lesson_emphasis.py`
- Test: `tests/unit/intelligence/rl/test_lesson_emphasis.py`

- [ ] **Step 1: Write failing tests**

```python
from datetime import date

from backend.shared.schemas.feedback import LearningLedger, Lesson
from core.intelligence.rl.algorithms.lesson_emphasis import (
    apply_lesson_emphasis, calendar_day_tags,
)


def _ledger(**lesson_kwargs) -> LearningLedger:
    defaults = dict(lesson_id="L001", date_learned="2026-06-01", category="macro",
                    pattern="rbi_day", observation="o", rule="r", confidence=0.8,
                    occurrences=3, last_seen=date.today().isoformat(),
                    trigger_tags=["central_bank_event"],
                    prioritise_agents=["risk_macro"], discount_agents=["sales_demand"])
    defaults.update(lesson_kwargs)
    return LearningLedger(ticker="T", sector="automobile",
                          last_updated="2026-06-11", lessons=[Lesson(**defaults)])


SCORES = {"risk_macro": 0.50, "sales_demand": 0.50, "fundamentals": 0.50}


def test_matching_tag_applies_emphasis():
    out = apply_lesson_emphasis(SCORES, _ledger(), ["central_bank_event"])
    assert out["risk_macro"] == 0.53
    assert out["sales_demand"] == 0.47
    assert out["fundamentals"] == 0.50


def test_no_tag_intersection_no_change():
    out = apply_lesson_emphasis(SCORES, _ledger(), ["crude_price"])
    assert out == SCORES


def test_low_confidence_lesson_does_not_fire():
    out = apply_lesson_emphasis(SCORES, _ledger(confidence=0.20), ["central_bank_event"])
    assert out == SCORES


def test_invalid_or_untagged_lesson_skipped():
    assert apply_lesson_emphasis(SCORES, _ledger(still_valid=False), ["central_bank_event"]) == SCORES
    assert apply_lesson_emphasis(SCORES, _ledger(trigger_tags=[]), ["central_bank_event"]) == SCORES


def test_cap_limits_stacked_lessons():
    led = _ledger()
    extra = led.lessons[0].model_copy(update={"lesson_id": "L002"})
    extra2 = led.lessons[0].model_copy(update={"lesson_id": "L003"})
    led.lessons.extend([extra, extra2])         # 3 × 0.03 = 0.09 → capped at 0.06
    out = apply_lesson_emphasis(SCORES, led, ["central_bank_event"])
    assert out["risk_macro"] == 0.56
    assert out["sales_demand"] == 0.44


def test_flag_off_is_identity(monkeypatch):
    from core.config import settings
    monkeypatch.setattr(settings, "RL_CLAIMS_ENABLED", False, raising=False)
    out = apply_lesson_emphasis(SCORES, _ledger(), ["central_bank_event"])
    assert out == SCORES


def test_calendar_day_tags_monsoon_and_budget():
    assert "monsoon" in calendar_day_tags(date(2026, 7, 15))
    assert "budget_event" in calendar_day_tags(date(2026, 2, 1))
    assert "monsoon" not in calendar_day_tags(date(2026, 12, 15))
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/unit/intelligence/rl/test_lesson_emphasis.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement `core/intelligence/rl/algorithms/lesson_emphasis.py`**

```python
"""
Executable-claim application: tagged lessons nudge agent scores on matching days.

apply_lesson_emphasis() is the ONLY place trigger_tags lessons act numerically —
deltas come from settings at call time, never stored on the lesson (they'd go stale).
Untagged legacy lessons remain handled by the category micro-adjustment in
generate_forecast._apply_ledger_micro_adjustments.
"""
from __future__ import annotations

import logging
from datetime import date

logger = logging.getLogger(__name__)


def apply_lesson_emphasis(day_agent_scores: dict, ledger, today_tags: list) -> dict:
    """Boost/dampen agent scores for still-valid tagged lessons firing today.

    Pure with respect to inputs; reads settings at call time; never raises.
    """
    from core.config import settings

    if not getattr(settings, "RL_CLAIMS_ENABLED", True):
        return dict(day_agent_scores)
    if ledger is None or not getattr(ledger, "lessons", None) or not today_tags:
        return dict(day_agent_scores)

    tagset = set(today_tags)
    adj = {a: 0.0 for a in day_agent_scores}
    delta = settings.RL_LESSON_EMPHASIS_DELTA
    min_conf = settings.RL_LESSON_MATCH_MIN_CONF

    for lesson in ledger.lessons:
        try:
            if not lesson.still_valid or not lesson.trigger_tags:
                continue
            if not tagset.intersection(lesson.trigger_tags):
                continue
            eff = (ledger.effective_confidence(lesson)
                   if hasattr(ledger, "effective_confidence") else lesson.confidence)
            if eff < min_conf:
                continue
            for a in lesson.prioritise_agents:
                if a in adj:
                    adj[a] += delta
            for a in lesson.discount_agents:
                if a in adj:
                    adj[a] -= delta
        except Exception as exc:                       # one bad lesson never blocks the rest
            logger.debug("[lesson_emphasis] skipped lesson: %s", exc)

    cap = settings.RL_LESSON_EMPHASIS_CAP
    return {
        a: round(min(1.0, max(0.0, s + max(-cap, min(cap, adj[a])))), 4)
        for a, s in day_agent_scores.items()
    }


def calendar_day_tags(d: date) -> list:
    """Calendar-derivable event tags for a (possibly future) date. Pure, never raises."""
    tags: set = set()
    if 6 <= d.month <= 9:
        tags.add("monsoon")
    if (d.month == 2 and d.day <= 7) or (d.month == 1 and d.day >= 25):
        tags.add("budget_event")
    if d.month in (10, 11):
        tags.add("seasonal")            # festive window (Navratri–Diwali)
    try:
        from core.intelligence.rl.nse_calendar import is_fno_expiry_week
        if is_fno_expiry_week(d):
            tags.add("expiry_week")
    except Exception:
        pass
    return sorted(tags)
```

NOTE: confirm `is_fno_expiry_week`'s exact signature in `core/intelligence/rl/nse_calendar.py` (it exists per `RL_DESIGN.md` §22) — pass `date` or `datetime` accordingly.

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/unit/intelligence/rl/test_lesson_emphasis.py -v`
Expected: 8 PASS

NOTE: if `LearningLedger.effective_confidence(lesson)` doesn't exist under that exact name, grep `feedback.py` for the decay method used by `build_tiered_lessons_summary` (ledger_propagator.py:203-280) and call that; update both the module and the low-confidence test accordingly.

- [ ] **Step 5: Commit**

```bash
git add core/intelligence/rl/algorithms/lesson_emphasis.py tests/unit/intelligence/rl/test_lesson_emphasis.py
git commit -m "feat(rl): executable-claim emphasis application + calendar day tags"
```

---

### Task 6: Curator prompts

**Files:**
- Create: `core/config/prompts/shared/dossier_curator.py`

- [ ] **Step 1: Write the prompt module** (no test of its own — exercised by Task 7 tests):

```python
"""
prompts/dossier_curator.py — LLM prompts for the daily DossierCurator (Step 8.5)
and the weekly distillation pass. Strict JSON contracts; the merge code in
core/intelligence/rl/agents/dossier_curator.py enforces every bound.
"""

CURATOR_SYSTEM_PROMPT = """\
You are the knowledge curator for {ticker} ({sector} sector, NSE India). You maintain a
living dossier — the notes of an analyst who follows this stock every single day.

Your job today: extract FACTS worth remembering from today's market context and review
outcome. You run on BOTH hit days and miss days:
- On CORRECT days: record WHAT WORKED — which predicted catalysts materialised, what
  confirmed the thesis. Confirm response signatures that fired as expected.
- On MISS days: record what actually drove the price and what the dossier was missing.

Rules:
- Observations must be grounded in the provided context — never invent numbers or events.
- Prefer specific, quantified statements ("dispatch +8% YoY") over vague ones.
- event_tags and observation tags MUST come from this vocabulary only: {event_tags}.
- signature_updates: "confirm"/"contradict" must reference an existing signature_id from
  the dossier; "create" needs trigger_tags + a quantified response statement.
- Do NOT cite analyst ratings, broker targets, or EPS estimates.
- Return ONLY valid JSON matching exactly this shape (all keys required, lists may be empty):

{{
  "event_tags_today": ["..."],
  "new_observations": [{{"observation": "...", "tags": ["..."], "materiality": 0.0}}],
  "signature_updates": [{{"action": "confirm|create|contradict", "signature_id": "",
                          "trigger_tags": ["..."], "response": ""}}],
  "guidance_updates": [{{"action": "add|met|missed|withdrawn", "guidance": "", "source": ""}}],
  "catalyst_updates": [{{"action": "add", "name": "", "typical_timing": "", "expected_effect": ""}}],
  "thesis_update": null,
  "flow_note": "",
  "open_question_updates": [{{"action": "raise|resolve", "question": "", "answer": ""}}]
}}

"thesis_update" is null unless today's evidence genuinely changes the stance — then a
1-2 sentence replacement thesis string. "flow_note" is "" unless FII/DII/deal flow
information appeared today.
"""

CURATOR_USER_TEMPLATE = """\
DATE: {date}
PREDICTED CLOSE: {predicted_close}   ACTUAL CLOSE: {actual_close}
PRICE ERROR: {price_error_pct:.2f}%   DIRECTION CORRECT: {direction_correct}
MISS TYPE: {miss_type}

TODAY'S MARKET CONTEXT:
{market_context}

REVIEW FINDINGS (FeedbackAgent):
missed_factors: {missed_factors}
over_weighted_factors: {over_weighted_factors}

CURRENT DOSSIER:
{dossier_digest}
"""

DISTILL_SYSTEM_PROMPT = """\
You are consolidating the dossier for {ticker} ({sector}) — the weekly pass where daily
observations become durable knowledge, like an analyst rewriting scratch notes into a brief.

Given the full dossier JSON, return ONLY valid JSON:
{{
  "business_summary": "2-4 sentences",
  "flow_notes": "1-3 sentences or empty",
  "observations_to_fold": ["<date of each observation now captured in a durable section>"],
  "signature_updates": [{{"action": "create|confirm|drop", "signature_id": "",
                          "trigger_tags": ["..."], "response": ""}}],
  "catalyst_hit_rates": [{{"name": "", "hit_rate": "e.g. 3/4 moved price"}}],
  "stale_guidance": ["<guidance text to mark withdrawn>"],
  "resolved_questions": [{{"question": "", "answer": ""}}]
}}

Rules: fold observations older than 7 days that repeat a pattern into a response
signature ("create"). Never invent data not present in the dossier. Tags from: {event_tags}.
"""
```

- [ ] **Step 2: Syntax check**

Run: `python -c "from core.config.prompts.shared.dossier_curator import CURATOR_SYSTEM_PROMPT; print(len(CURATOR_SYSTEM_PROMPT))"`
Expected: a number > 1000

- [ ] **Step 3: Commit**

```bash
git add core/config/prompts/shared/dossier_curator.py
git commit -m "feat(rl): dossier curator + distillation prompt contracts"
```

---

### Task 7: `DossierCurator.run()` + deterministic merge

**Files:**
- Create: `core/intelligence/rl/agents/dossier_curator.py`
- Test: `tests/unit/intelligence/rl/test_dossier_curator.py`

- [ ] **Step 1: Write failing tests** (fake the LLM; test the merge bounds):

```python
import json

import pytest

from backend.shared.schemas.dossier import TickerDossier, ResponseSignature
from backend.shared.schemas.feedback import FeedbackEntry
from core.intelligence.rl.agents.dossier_curator import DossierCurator


def _entry(direction_correct=False):
    return FeedbackEntry(day=1, date="2026-06-11", predicted_close=100.0,
                         actual_close=98.0, price_error_pct=-2.0,
                         direction_correct=direction_correct)


def _dossier():
    return TickerDossier(ticker="MARUTI", sector="automobile",
                         created_at="2026-06-01", last_updated="2026-06-10",
                         response_signatures=[ResponseSignature(
                             signature_id="RS001", trigger_tags=["crude_price"],
                             response="drops 2% on crude spike", occurrences=2,
                             first_seen="2026-05-01", last_seen="2026-06-01",
                             confidence=0.6)])


def _curator_with(monkeypatch, payload: dict) -> DossierCurator:
    c = DossierCurator()
    monkeypatch.setattr(c, "_call_llm", lambda *a, **k: json.dumps(payload))
    return c


def test_observations_capped_per_day_by_materiality(monkeypatch):
    payload = {
        "event_tags_today": ["crude_price"],
        "new_observations": [
            {"observation": f"obs {i}", "tags": ["crude_price"], "materiality": i / 10}
            for i in range(1, 6)                       # 5 candidates
        ],
        "signature_updates": [], "guidance_updates": [], "catalyst_updates": [],
        "thesis_update": None, "flow_note": "", "open_question_updates": [],
    }
    out = _curator_with(monkeypatch, payload).run(_dossier(), _entry(), "crude up", None)
    todays = [o for o in out.observations if o.date == "2026-06-11"]
    assert len(todays) == 3                            # DOSSIER_MAX_NEW_OBS_PER_DAY
    assert {o.observation for o in todays} == {"obs 5", "obs 4", "obs 3"}  # top materiality


def test_confirm_and_contradict_update_signature(monkeypatch):
    payload = {
        "event_tags_today": [], "new_observations": [],
        "signature_updates": [{"action": "confirm", "signature_id": "RS001",
                               "trigger_tags": [], "response": ""}],
        "guidance_updates": [], "catalyst_updates": [],
        "thesis_update": None, "flow_note": "", "open_question_updates": [],
    }
    out = _curator_with(monkeypatch, payload).run(_dossier(), _entry(True), "ctx", None)
    sig = out.response_signatures[0]
    assert sig.occurrences == 3
    assert sig.confidence == pytest.approx(0.65)
    assert sig.last_seen == "2026-06-11"


def test_create_signature_with_unknown_tags_filtered(monkeypatch):
    payload = {
        "event_tags_today": ["made_up_tag", "fii_flow"],
        "new_observations": [],
        "signature_updates": [{"action": "create", "signature_id": "",
                               "trigger_tags": ["fii_flow", "bogus"],
                               "response": "rises on FII buying streaks"}],
        "guidance_updates": [], "catalyst_updates": [],
        "thesis_update": None, "flow_note": "", "open_question_updates": [],
    }
    out = _curator_with(monkeypatch, payload).run(_dossier(), _entry(), "ctx", None)
    created = [s for s in out.response_signatures if s.signature_id != "RS001"]
    assert len(created) == 1
    assert created[0].trigger_tags == ["fii_flow"]      # bogus dropped


def test_llm_failure_returns_dossier_unchanged(monkeypatch):
    c = DossierCurator()
    monkeypatch.setattr(c, "_call_llm", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down")))
    before = _dossier()
    out = c.run(before, _entry(), "ctx", None)
    assert out.model_dump() == before.model_dump()


def test_hit_day_runs_too(monkeypatch):
    payload = {
        "event_tags_today": [], "new_observations": [
            {"observation": "FADA +8% materialised as predicted", "tags": [], "materiality": 0.8}],
        "signature_updates": [], "guidance_updates": [], "catalyst_updates": [],
        "thesis_update": None, "flow_note": "", "open_question_updates": [],
    }
    out = _curator_with(monkeypatch, payload).run(_dossier(), _entry(True), "ctx", None)
    assert any("materialised" in o.observation for o in out.observations)
    assert [o for o in out.observations if o.date == "2026-06-11"][0].outcome_link == "hit"
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/unit/intelligence/rl/test_dossier_curator.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement `core/intelligence/rl/agents/dossier_curator.py`**

```python
"""
DossierCurator — daily knowledge extraction into the TickerDossier (Step 8.5).

Runs EVERY trading day, hit or miss. LLM proposes updates; this module's merge
code enforces all bounds deterministically. Contract: NEVER raises — any failure
returns the dossier unchanged so the daily review is never blocked.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date as _date

from backend.shared.schemas.dossier import (
    DossierObservation, GuidanceItem, OpenQuestion, RecurringCatalyst,
    ResponseSignature, TickerDossier,
)
from backend.shared.schemas.feedback import EVENT_TAGS
from core.config.prompts.shared.dossier_curator import (
    CURATOR_SYSTEM_PROMPT, CURATOR_USER_TEMPLATE, DISTILL_SYSTEM_PROMPT,
)

logger = logging.getLogger(__name__)


def _strip_think(raw: str) -> str:
    return re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()


class DossierCurator:
    """LLM client pattern mirrors FeedbackAgent (json_object, low temp, retry-free)."""

    def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        from core.config import settings
        from services.clients.llm_client import get_llm_client
        client = get_llm_client()
        resp = client.chat.completions.create(
            model=settings.LLM_MODEL,
            temperature=0.2,
            max_tokens=900,
            response_format={"type": "json_object"},
            messages=[{"role": "system", "content": system_prompt},
                      {"role": "user", "content": user_prompt}],
        )
        return resp.choices[0].message.content or ""

    # ------------------------------------------------------------------

    def run(self, dossier: TickerDossier, entry, market_context: str,
            fb_output) -> TickerDossier:
        """Extract today's knowledge. On ANY failure, returns dossier unchanged."""
        from core.config import settings
        try:
            system = CURATOR_SYSTEM_PROMPT.format(
                ticker=dossier.ticker, sector=dossier.sector,
                event_tags=", ".join(sorted(EVENT_TAGS)))
            user = CURATOR_USER_TEMPLATE.format(
                date=entry.date,
                predicted_close=entry.predicted_close,
                actual_close=entry.actual_close,
                price_error_pct=entry.price_error_pct,
                direction_correct=entry.direction_correct,
                miss_type=(entry.miss_analysis.miss_type
                           if getattr(entry, "miss_analysis", None) else "n/a (hit)"),
                market_context=(market_context or "unavailable")[:4000],
                missed_factors=(fb_output.missed_factors if fb_output else []),
                over_weighted_factors=(fb_output.over_weighted_factors if fb_output else []),
                dossier_digest=dossier.to_digest(settings.DOSSIER_DIGEST_MAX_CHARS),
            )
            raw = self._call_llm(system, user)
            data = json.loads(_strip_think(raw))
            updated = dossier.model_copy(deep=True)
            self._merge(updated, data, entry)
            return updated
        except Exception as exc:
            logger.warning("[DossierCurator] non-fatal failure for %s on %s: %s",
                           dossier.ticker, getattr(entry, "date", "?"), exc)
            return dossier

    # ------------------------------------------------------------------

    def _merge(self, d: TickerDossier, data: dict, entry) -> None:
        """Deterministic, bounded application of curator output. Mutates d."""
        from core.config import settings
        today = entry.date
        outcome = "hit" if entry.direction_correct else "miss"

        # 1. Observations — top-N by materiality, valid tags only, cap total buffer.
        cands = []
        for o in data.get("new_observations", []):
            text = (o.get("observation") or "").strip()
            if not text:
                continue
            cands.append(DossierObservation(
                date=today, observation=text[:300],
                tags=[t for t in o.get("tags", []) if t in EVENT_TAGS],
                materiality=max(0.0, min(1.0, float(o.get("materiality", 0.5)))),
                outcome_link=outcome))
        cands.sort(key=lambda o: o.materiality, reverse=True)
        d.observations.extend(cands[: settings.DOSSIER_MAX_NEW_OBS_PER_DAY])
        if len(d.observations) > settings.DOSSIER_MAX_OBSERVATIONS:
            d.observations = d.observations[-settings.DOSSIER_MAX_OBSERVATIONS:]

        # 2. Signature updates.
        by_id = {s.signature_id: s for s in d.response_signatures}
        for su in data.get("signature_updates", []):
            action = su.get("action")
            if action == "confirm" and su.get("signature_id") in by_id:
                s = by_id[su["signature_id"]]
                s.occurrences += 1
                s.confidence = min(0.95, round(s.confidence + 0.05, 4))
                s.last_seen = today
                s.evidence_dates = (s.evidence_dates + [today])[-10:]
            elif action == "contradict" and su.get("signature_id") in by_id:
                s = by_id[su["signature_id"]]
                s.contradictions += 1
                s.confidence = max(0.0, round(s.confidence - 0.10, 4))
            elif action == "create":
                tags = [t for t in su.get("trigger_tags", []) if t in EVENT_TAGS]
                resp = (su.get("response") or "").strip()
                if tags and resp:
                    next_id = f"RS{len(d.response_signatures) + 1:03d}"
                    d.response_signatures.append(ResponseSignature(
                        signature_id=next_id, trigger_tags=tags, response=resp[:200],
                        occurrences=1, first_seen=today, last_seen=today,
                        confidence=0.5, evidence_dates=[today]))

        # 3. Guidance.
        for gu in data.get("guidance_updates", []):
            action, text = gu.get("action"), (gu.get("guidance") or "").strip()
            if action == "add" and text:
                d.guidance.append(GuidanceItem(
                    date=today, source=(gu.get("source") or "market context")[:80],
                    guidance=text[:200]))
            elif action in ("met", "missed", "withdrawn") and text:
                for g in d.guidance:
                    if g.status == "open" and text.lower() in g.guidance.lower():
                        g.status = action
            d.guidance = d.guidance[-20:]

        # 4. Catalysts (add-only daily; hit_rate is distillation's job).
        known = {c.name.lower() for c in d.recurring_catalysts}
        for cu in data.get("catalyst_updates", []):
            name = (cu.get("name") or "").strip()
            if cu.get("action") == "add" and name and name.lower() not in known:
                d.recurring_catalysts.append(RecurringCatalyst(
                    name=name[:80],
                    typical_timing=(cu.get("typical_timing") or "")[:60],
                    expected_effect=(cu.get("expected_effect") or "")[:120]))
        d.recurring_catalysts = d.recurring_catalysts[:10]

        # 5. Thesis + flows.
        if data.get("thesis_update"):
            d.current_thesis = str(data["thesis_update"])[:400]
            d.thesis_since = today
        if data.get("flow_note"):
            d.flow_notes = str(data["flow_note"])[:300]

        # 6. Open questions.
        for qu in data.get("open_question_updates", []):
            q = (qu.get("question") or "").strip()
            if qu.get("action") == "raise" and q:
                if all(q.lower() != ex.question.lower() for ex in d.open_questions):
                    d.open_questions.append(OpenQuestion(question=q[:200], raised_on=today))
            elif qu.get("action") == "resolve" and q:
                for ex in d.open_questions:
                    if not ex.resolved_on and q.lower() in ex.question.lower():
                        ex.resolved_on = today
                        ex.answer = (qu.get("answer") or "")[:200]
        d.open_questions = d.open_questions[-12:]
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/unit/intelligence/rl/test_dossier_curator.py -v`
Expected: 5 PASS

NOTE: verify `services/clients/llm_client.py` exposes `get_llm_client` (FeedbackAgent's import is the reference — copy its exact import + call pattern if it differs).

- [ ] **Step 5: Commit**

```bash
git add core/intelligence/rl/agents/dossier_curator.py tests/unit/intelligence/rl/test_dossier_curator.py
git commit -m "feat(rl): DossierCurator daily knowledge extraction with bounded merge"
```

---

### Task 8: `distill_dossier` (weekly) + static fallback

**Files:**
- Modify: `core/intelligence/rl/agents/dossier_curator.py`
- Test: `tests/unit/intelligence/rl/test_dossier_distill.py`

- [ ] **Step 1: Write failing tests**

```python
import json

from backend.shared.schemas.dossier import (
    TickerDossier, DossierObservation, ResponseSignature, RecurringCatalyst,
)
from core.intelligence.rl.agents import dossier_curator as dc


def _dossier():
    return TickerDossier(
        ticker="MARUTI", sector="automobile",
        created_at="2026-05-01", last_updated="2026-06-10", version=2,
        observations=[DossierObservation(date=f"2026-06-{i:02d}", observation=f"obs {i}")
                      for i in range(1, 11)],
        response_signatures=[
            ResponseSignature(signature_id="RS001", trigger_tags=["crude_price"],
                              response="drops on crude", occurrences=2, contradictions=3,
                              first_seen="2026-05-01", last_seen="2026-05-20", confidence=0.2),
            ResponseSignature(signature_id="RS002", trigger_tags=["fii_flow"],
                              response="rises on FII buying", occurrences=4,
                              first_seen="2026-05-01", last_seen="2026-06-09", confidence=0.7)],
        recurring_catalysts=[RecurringCatalyst(name="FADA data", typical_timing="~10th",
                                               expected_effect="±1%")])


def test_distill_applies_llm_consolidation(monkeypatch):
    payload = {
        "business_summary": "Largest car maker.",
        "flow_notes": "FII buyers.",
        "observations_to_fold": ["2026-06-01", "2026-06-02"],
        "signature_updates": [],
        "catalyst_hit_rates": [{"name": "FADA data", "hit_rate": "3/4 moved price"}],
        "stale_guidance": [], "resolved_questions": [],
    }
    monkeypatch.setattr(dc.DossierCurator, "_call_llm", lambda *a, **k: json.dumps(payload))
    out = dc.distill_dossier(_dossier())
    assert out.business_summary == "Largest car maker."
    assert out.version == 3
    assert all(o.date not in ("2026-06-01", "2026-06-02") for o in out.observations)
    assert out.recurring_catalysts[0].hit_rate == "3/4 moved price"
    assert all(s.signature_id != "RS001" for s in out.response_signatures)  # dead → dropped


def test_distill_static_fallback_on_llm_failure(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("llm down")
    monkeypatch.setattr(dc.DossierCurator, "_call_llm", _boom)
    before = _dossier()
    out = dc.distill_dossier(before)
    assert out.version == 2                                  # version unchanged
    assert all(s.signature_id != "RS001" for s in out.response_signatures)  # dead still dropped
    assert len(out.observations) <= 10
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/unit/intelligence/rl/test_dossier_distill.py -v`
Expected: FAIL — `distill_dossier` not defined

- [ ] **Step 3: Implement** — append to `dossier_curator.py`:

```python
def distill_dossier(dossier: TickerDossier) -> TickerDossier:
    """Weekly consolidation: episodic observations → durable sections.

    LLM pass when available; static fallback (dead-signature drop + buffer cap)
    when not. Never raises.
    """
    from core.config import settings
    d = dossier.model_copy(deep=True)

    # Static hygiene runs in BOTH paths.
    d.response_signatures = [s for s in d.response_signatures if s.is_alive]
    if len(d.observations) > settings.DOSSIER_MAX_OBSERVATIONS:
        d.observations = d.observations[-settings.DOSSIER_MAX_OBSERVATIONS:]

    try:
        curator = DossierCurator()
        system = DISTILL_SYSTEM_PROMPT.format(
            ticker=d.ticker, sector=d.sector, event_tags=", ".join(sorted(EVENT_TAGS)))
        raw = curator._call_llm(system, json.dumps(d.model_dump(), default=str)[:12000])
        data = json.loads(_strip_think(raw))

        if data.get("business_summary"):
            d.business_summary = str(data["business_summary"])[:500]
        if data.get("flow_notes"):
            d.flow_notes = str(data["flow_notes"])[:300]
        fold = set(data.get("observations_to_fold", []))
        if fold:
            d.observations = [o for o in d.observations if o.date not in fold]
        today = _date.today().isoformat()
        by_id = {s.signature_id: s for s in d.response_signatures}
        for su in data.get("signature_updates", []):
            action = su.get("action")
            if action == "drop" and su.get("signature_id") in by_id:
                d.response_signatures = [s for s in d.response_signatures
                                         if s.signature_id != su["signature_id"]]
            elif action == "create":
                tags = [t for t in su.get("trigger_tags", []) if t in EVENT_TAGS]
                resp = (su.get("response") or "").strip()
                if tags and resp:
                    next_id = f"RS{len(d.response_signatures) + 1:03d}"
                    d.response_signatures.append(ResponseSignature(
                        signature_id=next_id, trigger_tags=tags, response=resp[:200],
                        occurrences=2, first_seen=today, last_seen=today, confidence=0.55))
        rates = {r.get("name", "").lower(): r.get("hit_rate", "")
                 for r in data.get("catalyst_hit_rates", [])}
        for c in d.recurring_catalysts:
            if c.name.lower() in rates and rates[c.name.lower()]:
                c.hit_rate = str(rates[c.name.lower()])[:40]
        for stale in data.get("stale_guidance", []):
            for g in d.guidance:
                if g.status == "open" and str(stale).lower() in g.guidance.lower():
                    g.status = "withdrawn"
        for rq in data.get("resolved_questions", []):
            qtext = (rq.get("question") or "").lower()
            for q in d.open_questions:
                if not q.resolved_on and qtext and qtext in q.question.lower():
                    q.resolved_on = today
                    q.answer = (rq.get("answer") or "")[:200]
        d.version += 1
    except Exception as exc:
        logger.warning("[distill_dossier] LLM pass failed for %s — static fallback only: %s",
                       d.ticker, exc)
    return d
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/unit/intelligence/rl/test_dossier_distill.py tests/unit/intelligence/rl/test_dossier_curator.py -v`
Expected: 7 PASS

- [ ] **Step 5: Commit**

```bash
git add core/intelligence/rl/agents/dossier_curator.py tests/unit/intelligence/rl/test_dossier_distill.py
git commit -m "feat(rl): weekly dossier distillation with static fallback"
```

---

### Task 9: FeedbackAgent emits claim fields

**Files:**
- Modify: `core/config/prompts/shared/feedback_agent.py` (lesson output contract)
- Modify: `core/intelligence/rl/agents/feedback_agent.py` (`RawLesson` ~line 302, `_parse` ~line 298-313, `merge_lessons_into_ledger` ~line 377)
- Test: `tests/unit/intelligence/rl/test_feedback_claim_fields.py`

- [ ] **Step 1: Write failing tests**

```python
import json

from backend.shared.schemas.feedback import EVENT_TAGS
from core.intelligence.rl.agents.feedback_agent import FeedbackAgent


def _fb_input():
    # Copy the minimal FeedbackAgentInput construction from an existing test in
    # tests/integration/test_feedback_agent.py — agent names must include risk_macro
    # and sales_demand in predicted_agent_scores.
    from backend.shared.schemas.feedback import FeedbackAgentInput
    return FeedbackAgentInput(
        ticker="MARUTI", sector="automobile", date="2026-06-11",
        predicted_close=100.0, actual_close=98.0, price_error_pct=-2.0,
        direction_correct=False,
        predicted_agent_scores={"risk_macro": 0.5, "sales_demand": 0.7},
        todays_agent_scores={"risk_macro": 0.4, "sales_demand": 0.6},
        market_context_today="RBI surprise hold",
        key_assumptions_that_were_made=[], existing_lesson_ids=[],
    )


def test_parse_extracts_and_validates_claim_fields():
    agent = FeedbackAgent.__new__(FeedbackAgent)        # no LLM client needed for _parse
    raw = json.dumps({
        "primary_miss_agent": "risk_macro", "miss_type": "model_bias",
        "missed_factors": ["RBI surprise"], "over_weighted_factors": [],
        "agent_score_drift": {},
        "new_lessons": [{
            "category": "macro", "pattern": "rbi_day", "observation": "o", "rule": "r",
            "confidence": 0.7, "scope": "stock_specific",
            "trigger_tags": ["central_bank_event", "not_a_real_tag"],
            "prioritise_agents": ["risk_macro", "ghost_agent"],
            "discount_agents": ["sales_demand"],
        }],
        "revised_context": {"headline": "h"},
    })
    out = agent._parse(raw, _fb_input())
    lesson = out.new_lessons[0]
    assert lesson.trigger_tags == ["central_bank_event"]          # invalid tag dropped
    assert lesson.prioritise_agents == ["risk_macro"]              # unknown agent dropped
    assert lesson.discount_agents == ["sales_demand"]
    assert set(lesson.trigger_tags) <= EVENT_TAGS


def test_parse_defaults_when_fields_absent():
    agent = FeedbackAgent.__new__(FeedbackAgent)
    raw = json.dumps({
        "primary_miss_agent": "", "miss_type": "magnitude",
        "missed_factors": [], "over_weighted_factors": [], "agent_score_drift": {},
        "new_lessons": [{"category": "macro", "pattern": "p", "observation": "o",
                         "rule": "r", "confidence": 0.6}],
        "revised_context": {"headline": "h"},
    })
    lesson = agent._parse(raw, _fb_input()).new_lessons[0]
    assert lesson.trigger_tags == []
    assert lesson.prioritise_agents == []
```

NOTE: if `FeedbackAgentInput` requires different/extra mandatory fields, copy the constructor from `tests/integration/test_feedback_agent.py`. If `_parse`'s signature differs (`self._parse(raw, fb_input)` is from feedback_agent.py:191), match it.

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/unit/intelligence/rl/test_feedback_claim_fields.py -v`
Expected: FAIL — `RawLesson` has no `trigger_tags` / assertion error

- [ ] **Step 3: Implement**

(a) `RawLesson` (wherever it's defined — used at feedback_agent.py:302): add the three fields with empty-list defaults:

```python
    trigger_tags: list[str] = field(default_factory=list)        # dataclass style
    prioritise_agents: list[str] = field(default_factory=list)
    discount_agents: list[str] = field(default_factory=list)
```
(use `Field(default_factory=list)` instead if `RawLesson` is a Pydantic model — match the existing field style.)

(b) `_parse` lesson construction (~feedback_agent.py:301-313) — extend with validated extraction:

```python
            from backend.shared.schemas.feedback import EVENT_TAGS
            valid_agents = set(fb_input.predicted_agent_scores.keys())
            raw_lessons = [
                RawLesson(
                    category=item.get("category", "macro"),
                    pattern=item.get("pattern", "unknown").lower().replace(" ", "_"),
                    observation=item.get("observation", ""),
                    rule=item.get("rule", ""),
                    confidence=float(item.get("confidence", 0.5)),
                    scope=item.get("scope", "stock_specific")
                    if item.get("scope") in self._VALID_SCOPES
                    else "stock_specific",
                    trigger_tags=[t for t in item.get("trigger_tags", []) if t in EVENT_TAGS],
                    prioritise_agents=[a for a in item.get("prioritise_agents", [])
                                       if a in valid_agents],
                    discount_agents=[a for a in item.get("discount_agents", [])
                                     if a in valid_agents],
                )
                for item in data.get("new_lessons", [])
            ]
```
(keep the existing `confidence=` expression if it differs — only ADD the three new kwargs.)

(c) `merge_lessons_into_ledger` (feedback_agent.py:377+): where `Lesson(...)` is constructed from a `RawLesson`, pass through:

```python
                trigger_tags=raw.trigger_tags,
                prioritise_agents=raw.prioritise_agents,
                discount_agents=raw.discount_agents,
```

(d) Prompt contract — in `core/config/prompts/shared/feedback_agent.py`, inside the `new_lessons` JSON contract block, extend the lesson object description with:

```
      "trigger_tags": ["central_bank_event"],   // REQUIRED — 1-3 tags, ONLY from: {event_tags}
      "prioritise_agents": ["risk_macro"],      // agents to trust MORE when this fires (from the agent list above)
      "discount_agents": ["sales_demand"],      // agents to trust LESS when this fires
```

and add to the rules section: `Every new lesson MUST include trigger_tags so the system can apply it automatically on matching days.` Wire `{event_tags}` into whatever `build_system_prompt(sector, agent_names)` formats (pass `", ".join(sorted(EVENT_TAGS))`).

- [ ] **Step 4: Run tests + regression**

Run: `python -m pytest tests/unit/intelligence/rl/test_feedback_claim_fields.py tests/integration/test_feedback_agent.py -v`
Expected: new tests PASS; existing feedback agent tests still PASS

- [ ] **Step 5: Commit**

```bash
git add core/intelligence/rl/agents/feedback_agent.py core/config/prompts/shared/feedback_agent.py tests/unit/intelligence/rl/test_feedback_claim_fields.py
git commit -m "feat(rl): FeedbackAgent emits validated executable-claim fields on lessons"
```

---

### Task 10: Wire daily review — tags, Step-7 emphasis, `event_tags` persist, Step 8.5 curator

**Files:**
- Modify: `core/intelligence/rl/workflows/daily_review.py`
- Test: `tests/unit/intelligence/rl/test_daily_review_dossier.py`

- [ ] **Step 1: Compute today's tags** — right after the final `market_context` assembly (after the G8 FII/DII injection, ~line 629):

```python
    # Static event tags for today — deterministic, LLM-independent. Used by
    # Step-7 claim matching and persisted on the FeedbackEntry.
    from backend.shared.schemas.feedback import tag_events
    from core.intelligence.rl.algorithms.lesson_emphasis import calendar_day_tags
    today_tags = sorted(set(tag_events(market_context or ""))
                        | set(calendar_day_tags(review_date)))
```

NOTE: `review_date` is whatever `date` object the function already uses for "today" (the variable feeding `entry.date`) — reuse it, do not re-derive.

- [ ] **Step 2: Step-7 emphasis** — extend `_revise_remaining_forecasts` (def line 238): add params `ticker_ledger=None, today_tags=None`; inside the per-forecast loop (where `forecast.revised = True` is set, ~line 276), apply to scores:

```python
        if ticker_ledger is not None and today_tags:
            from core.intelligence.rl.algorithms.lesson_emphasis import apply_lesson_emphasis
            forecast.predicted_agent_scores = apply_lesson_emphasis(
                forecast.predicted_agent_scores, ticker_ledger, today_tags)
```

and pass at the call site (line 977): `ticker_ledger=ticker_ledger, today_tags=today_tags,`.

- [ ] **Step 3: Persist tags** — add `event_tags=today_tags,` to the `FeedbackEntry(...)` construction for `final_entry` (~line 1004).

- [ ] **Step 4: Step 8.5 curator hook** — immediately AFTER `store.append_feedback_entry(final_entry, cycle_id)` (line 1011):

```python
    # ── Step 8.5: Dossier curator — runs EVERY day (hit or miss), never fatal ──
    from core.config import settings as _settings
    if getattr(_settings, "RL_DOSSIER_ENABLED", True):
        try:
            from backend.shared.schemas.dossier import TickerDossier
            from core.intelligence.rl.agents.dossier_curator import DossierCurator
            dossier = store.load_dossier() or TickerDossier(
                ticker=ticker, sector=sector,
                created_at=final_entry.date, last_updated=final_entry.date)
            updated = DossierCurator().run(
                dossier, final_entry, market_context or "", fb_output)
            store.save_dossier(updated)
            logger.info("[daily_review] Step 8.5 dossier updated for %s (%d observations)",
                        ticker, len(updated.observations))
        except Exception as exc:
            logger.warning("[daily_review] Step 8.5 dossier curator failed (non-fatal): %s", exc)
```

NOTE: `ticker`/`sector`/`store`/`fb_output` are all in scope at that point (verified: store at line 1011, fb_output at 769). Match the actual local names.

- [ ] **Step 5: Write the integration-style unit test**

```python
"""Step 8.5 wiring: dossier written on review; emphasis applied on tag match."""
import json

from backend.shared.schemas.dossier import TickerDossier
from backend.shared.schemas.feedback import LearningLedger, Lesson, tag_events


def test_tag_events_drives_step7_emphasis_contract():
    # The same context string must produce tags that fire a tagged lesson.
    ctx = "RBI surprise hold pressured autos; FII outflow 2200Cr"
    tags = tag_events(ctx)
    lesson = Lesson(lesson_id="L1", date_learned="2026-06-11", category="macro",
                    pattern="rbi", observation="o", rule="r", confidence=0.8,
                    occurrences=2, last_seen="2026-06-11",
                    trigger_tags=["central_bank_event"], prioritise_agents=["risk_macro"])
    ledger = LearningLedger(ticker="T", sector="automobile",
                            last_updated="2026-06-11", lessons=[lesson])
    from core.intelligence.rl.algorithms.lesson_emphasis import apply_lesson_emphasis
    out = apply_lesson_emphasis({"risk_macro": 0.5}, ledger, tags)
    assert out["risk_macro"] > 0.5


def test_run_daily_review_writes_dossier(monkeypatch, tmp_path):
    # Full-loop smoke: monkeypatch DossierCurator._call_llm with a fixed payload and
    # run run_daily_review() against the existing integration fixture for a ticker
    # with a seeded envelope (copy the fixture setup from
    # tests/integration/test_prediction_store.py / existing daily-review tests).
    # Assert: {ticker}_dossier.json exists afterward and has >=1 observation.
    payload = {"event_tags_today": [], "new_observations": [
                   {"observation": "seeded obs", "tags": [], "materiality": 0.9}],
               "signature_updates": [], "guidance_updates": [], "catalyst_updates": [],
               "thesis_update": None, "flow_note": "", "open_question_updates": []}
    from core.intelligence.rl.agents.dossier_curator import DossierCurator
    monkeypatch.setattr(DossierCurator, "_call_llm", lambda *a, **k: json.dumps(payload))
    # ... fixture-driven run_daily_review(...) call per existing integration tests ...
```

The second test MUST be completed against the repo's existing daily-review test fixtures (there are integration tests that exercise `run_daily_review` with monkeypatched LLM + yfinance — reuse exactly that harness). If no such fixture exists, monkeypatch `FeedbackAgent.run`, yfinance close fetch, and `RegimeDetector.detect` following the pattern in `tests/integration/test_feedback_agent.py`.

- [ ] **Step 6: Run**

Run: `python -m pytest tests/unit/intelligence/rl/test_daily_review_dossier.py -v`
Expected: PASS

- [ ] **Step 7: Full RL test regression**

Run: `python -m pytest tests/unit/intelligence/rl tests/integration -q`
Expected: baseline counts, no new failures

- [ ] **Step 8: Commit**

```bash
git add core/intelligence/rl/workflows/daily_review.py tests/unit/intelligence/rl/test_daily_review_dossier.py
git commit -m "feat(rl): daily review — event tags, Step-7 claim emphasis, Step 8.5 dossier curator"
```

---

### Task 11: Month-start forecast — calendar-tag emphasis, narrow legacy micro-adjust

**Files:**
- Modify: `core/intelligence/rl/workflows/generate_forecast.py`
- Test: `tests/unit/intelligence/rl/test_forecast_emphasis.py`

- [ ] **Step 1: Write failing tests**

```python
from datetime import date

from backend.shared.schemas.feedback import LearningLedger, Lesson
from core.intelligence.rl.workflows.generate_forecast import _apply_ledger_micro_adjustments


def _tagged_lesson():
    return Lesson(lesson_id="L1", date_learned="2026-06-01", category="macro",
                  pattern="p", observation="o", rule="r", confidence=0.9, occurrences=3,
                  last_seen=date.today().isoformat(),
                  trigger_tags=["monsoon"], prioritise_agents=["risk_macro"])


def _untagged_lesson():
    return Lesson(lesson_id="L2", date_learned="2026-06-01", category="macro",
                  pattern="p2", observation="o", rule="r", confidence=0.9, occurrences=3,
                  last_seen=date.today().isoformat())


def test_micro_adjust_skips_tagged_lessons():
    scores = {"risk_macro": 0.5}
    led_tagged = LearningLedger(ticker="T", sector="automobile",
                                last_updated="2026-06-11", lessons=[_tagged_lesson()])
    led_untagged = LearningLedger(ticker="T", sector="automobile",
                                  last_updated="2026-06-11", lessons=[_untagged_lesson()])
    assert _apply_ledger_micro_adjustments(scores, led_tagged) == scores      # skipped
    assert _apply_ledger_micro_adjustments(scores, led_untagged)["risk_macro"] > 0.5
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/unit/intelligence/rl/test_forecast_emphasis.py -v`
Expected: FAIL — tagged lesson currently also adjusts

- [ ] **Step 3: Implement**

(a) In `_apply_ledger_micro_adjustments` (line 98 loop), add right after the `still_valid` check:

```python
        if lesson.trigger_tags:
            continue   # tagged lessons fire via apply_lesson_emphasis on matching days
```

(b) In `_build_daily_forecasts` — at the point where each day's agent scores are finalized (after seasonal adjustments are applied to the per-day scores), add per-day calendar-tag emphasis:

```python
        from core.intelligence.rl.algorithms.lesson_emphasis import (
            apply_lesson_emphasis, calendar_day_tags)
        day_tags = calendar_day_tags(d)        # d = this row's trading date
        if day_tags and learning_ledger is not None:
            day_scores = apply_lesson_emphasis(day_scores, learning_ledger, day_tags)
```

NOTE: locate the local variable holding that day's `predicted_agent_scores` dict inside the day loop of `_build_daily_forecasts` (line 122+; the function receives `learning_ledger` already) and apply just before the `DailyForecast(...)` row is constructed.

- [ ] **Step 4: Run tests + regression**

Run: `python -m pytest tests/unit/intelligence/rl/test_forecast_emphasis.py tests/unit/intelligence/rl/test_price_interpolator.py tests/unit/intelligence/rl/test_monte_carlo.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add core/intelligence/rl/workflows/generate_forecast.py tests/unit/intelligence/rl/test_forecast_emphasis.py
git commit -m "feat(rl): forecast build applies tagged-lesson emphasis; legacy micro-adjust narrowed"
```

---

### Task 12: `BaseAgent` dossier digest injection

**Files:**
- Modify: `src/backend/shared/pipeline/base_agent.py`
- Test: `tests/unit/pipeline/test_agent_dossier_injection.py` (create dir if needed)

- [ ] **Step 1: Write failing tests**

```python
from src.backend.shared.pipeline.base_agent import BaseAgent
# NOTE: match the import path used by existing base_agent tests
# (likely `from backend.shared.pipeline.base_agent import BaseAgent`).


class _Probe(BaseAgent):
    """Minimal concrete agent capturing the final system prompt."""
    agent_name = "probe"
    # implement/stub whatever abstract members BaseAgent requires by copying the
    # smallest concrete agent in the codebase or an existing BaseAgent test double.


def test_digest_appended_when_dossier_exists(monkeypatch):
    agent = _Probe.__new__(_Probe)
    agent.sector = "automobile"
    agent._dossier_digest_cache = {}
    monkeypatch.setattr(agent, "_fetch_dossier_digest",
                        lambda ticker: "# MARUTI dossier\n## Thesis\nBUY")
    out = agent._get_dossier_digest("MARUTI")
    assert "ACCUMULATED TICKER KNOWLEDGE" not in out      # raw digest, no wrapper here
    assert out.startswith("# MARUTI dossier")
    # cached on second call
    monkeypatch.setattr(agent, "_fetch_dossier_digest",
                        lambda ticker: (_ for _ in ()).throw(AssertionError("not cached")))
    assert agent._get_dossier_digest("MARUTI").startswith("# MARUTI dossier")


def test_empty_when_flag_off(monkeypatch):
    from core.config import settings
    monkeypatch.setattr(settings, "RL_DOSSIER_ENABLED", False, raising=False)
    agent = _Probe.__new__(_Probe)
    agent.sector = "automobile"
    agent._dossier_digest_cache = {}
    assert agent._get_dossier_digest("MARUTI") == ""


def test_empty_when_no_dossier(monkeypatch):
    agent = _Probe.__new__(_Probe)
    agent.sector = "automobile"
    agent._dossier_digest_cache = {}
    monkeypatch.setattr(agent, "_fetch_dossier_digest", lambda ticker: "")
    assert agent._get_dossier_digest("NEWTICKER") == ""
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/unit/pipeline/test_agent_dossier_injection.py -v`
Expected: FAIL — `_get_dossier_digest` missing

- [ ] **Step 3: Implement in `base_agent.py`**

(a) In `__init__` next to `self._extra_queries` (line 79):

```python
        self._dossier_digest_cache: dict[str, str] = {}
```

(b) New methods (place near the `_extra_queries` lazy loader, ~line 426):

```python
    # ------------------------------------------------------------------
    # RL knowledge layer: ticker dossier digest (lazy, cached per ticker)
    # ------------------------------------------------------------------

    def _fetch_dossier_digest(self, ticker: str) -> str:
        """Load and render the ticker dossier digest. Never raises."""
        from core.config import settings
        try:
            from core.intelligence.rl.stores.prediction_store import PredictionStore
            ps = PredictionStore(ticker=ticker, sector=self.sector or "automobile")
            dossier = ps.load_dossier()
            if dossier is None:
                return ""
            return dossier.to_digest(settings.DOSSIER_AGENT_DIGEST_CHARS)
        except Exception:
            return ""

    def _get_dossier_digest(self, ticker: str) -> str:
        from core.config import settings
        if not getattr(settings, "RL_DOSSIER_ENABLED", True):
            return ""
        if ticker not in self._dossier_digest_cache:
            self._dossier_digest_cache[ticker] = self._fetch_dossier_digest(ticker)
        return self._dossier_digest_cache[ticker]
```

(c) Injection — in BOTH `run()` (after line 103 `system_prompt += _DATA_ONLY_INSTRUCTION + _date_instruction()`) and `run_async()` (after line 140):

```python
        digest = self._get_dossier_digest(query.ticker)
        if digest:
            system_prompt += ("\n\n[ACCUMULATED TICKER KNOWLEDGE — learned from daily "
                              "tracking of this stock]\n" + digest)
```

- [ ] **Step 4: Run tests + pipeline regression**

Run: `python -m pytest tests/unit/pipeline/test_agent_dossier_injection.py -v && python -m pytest tests/unit -q`
Expected: new PASS; baseline intact

- [ ] **Step 5: Commit**

```bash
git add src/backend/shared/pipeline/base_agent.py tests/unit/pipeline/test_agent_dossier_injection.py
git commit -m "feat(pipeline): inject ticker dossier digest into agent prompts (flag-gated)"
```

---

### Task 13: Orchestrator per-ticker weight scoping

**Files:**
- Modify: `src/backend/shared/pipeline/base_orchestrator.py:112-114, 174-176`
- Modify: `core/intelligence/rl/workflows/generate_forecast.py:267`, `core/intelligence/rl/workflows/daily_review.py:176`
- Test: extend `tests/test_weight_init_fix.py`

- [ ] **Step 1: Write failing test** (append to `tests/test_weight_init_fix.py`, matching its style):

```python
def test_weights_reload_when_ticker_changes(orchestrator_fixture, monkeypatch):
    orch = orchestrator_fixture          # reuse the file's existing construction pattern
    calls = []
    monkeypatch.setattr(orch, "_load_learned_weights",
                        lambda t: calls.append(t) or {"risk_macro": 1.0})
    orch._aggregator_weights = None
    orch._resolve_weights_for("MARUTI")  # helper added in Step 3
    orch._resolve_weights_for("TATAMOTORS")
    assert calls == ["MARUTI", "TATAMOTORS"]   # second ticker NOT served cached weights


def test_externally_injected_weights_not_clobbered(orchestrator_fixture):
    orch = orchestrator_fixture
    orch.set_aggregator_weights({"risk_macro": 0.9}, ticker="MARUTI")
    orch._resolve_weights_for("MARUTI")
    assert orch._aggregator_weights == {"risk_macro": 0.9}
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_weight_init_fix.py -v`
Expected: new tests FAIL — helpers missing

- [ ] **Step 3: Implement in `base_orchestrator.py`**

(a) In `__init__` (line 90 area): `self._aggregator_weights_ticker: str | None = None`

(b) New methods:

```python
    def set_aggregator_weights(self, weights: dict[str, float], ticker: str) -> None:
        """Explicit injection (generate_forecast / daily_review). Pins weights to ticker."""
        self._aggregator_weights = weights
        self._aggregator_weights_ticker = ticker

    def _resolve_weights_for(self, ticker: str) -> None:
        """(Re)load learned weights when unset or when the ticker changed."""
        if self._aggregator_weights is None or self._aggregator_weights_ticker != ticker:
            learned = self._load_learned_weights(ticker)
            self._aggregator_weights = learned or self._get_default_weights()
            self._aggregator_weights_ticker = ticker
```

(c) Replace lines 112–114 (async path) with:

```python
        if self._aggregator_weights is None or self._aggregator_weights_ticker != query.ticker:
            learned = await asyncio.to_thread(self._load_learned_weights, query.ticker)
            self._aggregator_weights = learned or self._get_default_weights()
            self._aggregator_weights_ticker = query.ticker
```

and lines 174–176 (sync path) with a call to `self._resolve_weights_for(query.ticker)`.

(d) Update the two external injectors to use the setter:
- `generate_forecast.py:267`: `orchestrator.set_aggregator_weights(effective_weights, ticker)`
- `daily_review.py:176`: `orchestrator.set_aggregator_weights(learned_weights, ticker)`

- [ ] **Step 4: Run**

Run: `python -m pytest tests/test_weight_init_fix.py -q && python -m pytest tests/unit -q`
Expected: PASS, baseline intact

- [ ] **Step 5: Commit**

```bash
git add src/backend/shared/pipeline/base_orchestrator.py core/intelligence/rl/workflows/generate_forecast.py core/intelligence/rl/workflows/daily_review.py tests/test_weight_init_fix.py
git commit -m "fix(pipeline): scope learned aggregator weights per ticker, explicit injection setter"
```

---

### Task 14: Weekly distillation in scheduler

**Files:**
- Modify: `services/scheduler/python/scheduler.py` (`_ledger_cleanup_job`, ~line 412)
- Test: `tests/unit/intelligence/rl/test_scheduler_distill_hook.py`

- [ ] **Step 1: Write failing test**

```python
def test_cleanup_job_distills_dossiers(monkeypatch, tmp_path):
    import services.scheduler.python.scheduler as sched
    distilled = []

    # Managed tickers: copy the monkeypatch pattern used by existing scheduler tests
    # for get_active_tickers_with_sector / load_managed_tickers.
    monkeypatch.setattr(sched, "_get_tickers_for_jobs",
                        lambda: [{"sym": "MARUTI", "sector": "automobile"}],
                        raising=False)

    import core.intelligence.rl.agents.dossier_curator as dc
    monkeypatch.setattr(dc, "distill_dossier",
                        lambda d: distilled.append(d.ticker) or d)

    # PredictionStore returning a real dossier for MARUTI (point base dir at tmp_path —
    # same plumbing as tests/unit/intelligence/rl/test_dossier_store.py).
    ...
    sched._ledger_cleanup_job()
    assert distilled == ["MARUTI"]
```

NOTE: read `_ledger_cleanup_job` (line ~412) first; reuse exactly its ticker-iteration helper name in the monkeypatch (the placeholder name `_get_tickers_for_jobs` above must be replaced by the real one found in the file — the job already iterates tickers for ledger cleanup).

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/unit/intelligence/rl/test_scheduler_distill_hook.py -v`
Expected: FAIL — no distillation performed

- [ ] **Step 3: Implement** — at the end of `_ledger_cleanup_job`'s per-ticker loop (it already loads ticker ledgers there, ~line 441), add:

```python
            # Weekly dossier distillation (knowledge layer) — same cadence as
            # stale-lesson cleanup; non-fatal per ticker.
            try:
                from core.config import settings as _settings
                if getattr(_settings, "RL_DOSSIER_ENABLED", True):
                    from core.intelligence.rl.agents.dossier_curator import distill_dossier
                    dossier = store.load_dossier()
                    if dossier is not None:
                        store.save_dossier(distill_dossier(dossier))
                        logger.info("[Scheduler] Distilled dossier for %s", ticker)
            except Exception as exc:
                logger.warning("[Scheduler] Dossier distillation failed for %s: %s", ticker, exc)
```

(`store` = the per-ticker `PredictionStore` the job already constructs for ledger cleanup; reuse it.)

- [ ] **Step 4: Run**

Run: `python -m pytest tests/unit/intelligence/rl/test_scheduler_distill_hook.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add services/scheduler/python/scheduler.py tests/unit/intelligence/rl/test_scheduler_distill_hook.py
git commit -m "feat(scheduler): weekly dossier distillation alongside ledger cleanup"
```

---

### Task 15: Chat — `get_ticker_dossier` tool + RL insight bug fixes

**Files:**
- Modify: `services/api/routes/ui_data.py`
- Test: `tests/unit/api/test_chat_dossier_tool.py` (create dir/`__init__` if needed; mirror existing API test setup if `tests/unit/api` doesn't exist — check `tests/` layout first and place beside similar route tests)

- [ ] **Step 1: Write failing tests**

```python
import asyncio
import json


def test_dossier_tool_reads_digest(tmp_path, monkeypatch):
    import services.api.routes.ui_data as ui
    sector_dir = tmp_path / "automobile" / "MARUTI"
    sector_dir.mkdir(parents=True)
    dossier = {"ticker": "MARUTI", "sector": "automobile",
               "created_at": "2026-06-01", "last_updated": "2026-06-11",
               "current_thesis": "BUY on rural recovery"}
    (sector_dir / "MARUTI_dossier.json").write_text(json.dumps(dossier), encoding="utf-8")
    monkeypatch.setattr(ui, "_PREDICTIONS_DIR", tmp_path)
    out = asyncio.run(ui._chat_tool_ticker_dossier("maruti"))
    assert "MARUTI dossier" in out
    assert "rural recovery" in out


def test_dossier_tool_empty_when_missing(tmp_path, monkeypatch):
    import services.api.routes.ui_data as ui
    monkeypatch.setattr(ui, "_PREDICTIONS_DIR", tmp_path)
    assert asyncio.run(ui._chat_tool_ticker_dossier("GHOST")) == ""


def test_dispatch_routes_dossier_tool(monkeypatch):
    import services.api.routes.ui_data as ui
    async def fake(t):
        return f"DOSSIER:{t}"
    monkeypatch.setattr(ui, "_chat_tool_ticker_dossier", fake)
    out = asyncio.run(ui._dispatch_chat_tool("get_ticker_dossier", {"ticker": "TCS"}))
    assert out == "DOSSIER:TCS"


def test_sector_resolution_helper(monkeypatch, tmp_path):
    import services.api.routes.ui_data as ui
    (tmp_path / "banking_bfsi" / "HDFCBANK").mkdir(parents=True)
    monkeypatch.setattr(ui, "_PREDICTIONS_DIR", tmp_path)
    monkeypatch.setattr(ui, "_load_mt", lambda: [])      # force directory-scan fallback
    assert ui._sector_for_ticker("HDFCBANK") == "banking_bfsi"
    assert ui._sector_for_ticker("UNKNOWN") == "automobile"
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/unit/api/test_chat_dossier_tool.py -v`
Expected: FAIL — functions missing

- [ ] **Step 3: Implement in `ui_data.py`**

(a) Sector resolver helper (place near `_ctx_rl_learning`, line ~1386):

```python
def _sector_for_ticker(sym: str) -> str:
    """Resolve a ticker's sector: managed_tickers.json first, then directory scan."""
    s = sym.upper().strip()
    try:
        for t in _load_mt():
            if t.get("sym", "").upper() == s and t.get("sector"):
                return t["sector"]
    except Exception:
        pass
    try:
        for sector_dir in _PREDICTIONS_DIR.iterdir():
            if sector_dir.is_dir() and (sector_dir / s).is_dir():
                return sector_dir.name
    except Exception:
        pass
    return "automobile"
```

(b) Fix `_ctx_rl_learning` (line 1393): `ps = PredictionStore(ticker, sector=_sector_for_ticker(ticker))`; and lines 1409–1411 — replace `wm.learned_weights` with:

```python
                if wm and wm.current_weights:
                    top = sorted(wm.current_weights.items(), key=lambda x: x[1], reverse=True)[:3]
```

(c) Same sector fix at line 1271: `ps = PredictionStore(ticker=sym, sector=_sector_for_ticker(sym))`.

(d) New chat tool (place after `_chat_tool_rl_prediction`, line ~2455):

```python
async def _chat_tool_ticker_dossier(ticker: str) -> str:
    """Accumulated daily-tracking knowledge for a ticker (RL dossier digest)."""
    t = (ticker or "").upper().strip()
    if not t or t in _RL_INDEX_NAMES:
        return ""
    try:
        for sector_dir in _PREDICTIONS_DIR.iterdir():
            if not sector_dir.is_dir():
                continue
            f = sector_dir / t / f"{t}_dossier.json"
            if f.exists():
                from backend.shared.schemas.dossier import TickerDossier
                d = TickerDossier(**json.loads(f.read_text(encoding="utf-8")))
                return d.to_digest(2000)
    except Exception:
        return ""
    return ""
```

(e) Register in `_dispatch_chat_tool` (line 2483 block):

```python
    if name == "get_ticker_dossier":
        return await _chat_tool_ticker_dossier(args.get("ticker", ""))
```

(f) Add the tool schema to `_CHAT_TOOLS` (copy the JSON-schema entry shape of `get_rl_prediction` in the same list):

```python
    {"type": "function", "function": {
        "name": "get_ticker_dossier",
        "description": ("Accumulated knowledge dossier for a tracked NSE ticker — thesis, "
                        "learned price-response signatures, open management guidance, "
                        "recurring catalysts, institutional flow trend. Use for any deep "
                        "dive or 'what do we know about X' question."),
        "parameters": {"type": "object",
                       "properties": {"ticker": {"type": "string",
                                                 "description": "NSE symbol, e.g. MARUTI"}},
                       "required": ["ticker"]}}},
```

(g) `_CHAT_SYSTEM_PROMPT` (line 2514): add a tool bullet
`- **get_ticker_dossier(ticker)** — what we've LEARNED about this stock from daily tracking (thesis, response signatures, guidance, flows).`
and extend the deep-dive routing row to `get_live_price + get_stock_analysis + get_rl_prediction + get_ticker_dossier + search_market_news`.

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/unit/api/test_chat_dossier_tool.py -v`
Expected: 4 PASS

- [ ] **Step 5: Commit**

```bash
git add services/api/routes/ui_data.py tests/unit/api/test_chat_dossier_tool.py
git commit -m "feat(chat): get_ticker_dossier tool; fix RL insight sector hardcode + weights attr"
```

---

### Task 16: `dossier-status` CLI subcommand

**Files:**
- Modify: the `run_schedule` CLI entry (`services/scheduler/run_schedule.py` — confirm exact filename; it's the module behind `python -m services.scheduler.run_schedule`)

- [ ] **Step 1: Add the subcommand** — follow the file's existing argparse subcommand pattern (`feedback-status` is the closest sibling):

```python
def cmd_dossier_status(args) -> None:
    """Print per-ticker dossier health: size, version, staleness, counts."""
    from core.intelligence.rl.stores.prediction_store import PredictionStore
    from services.api.log_buffer import get_active_tickers_with_sector
    rows = get_active_tickers_with_sector()
    if getattr(args, "ticker", None):
        rows = [r for r in rows if r["sym"] in args.ticker]
    for r in rows:
        store = PredictionStore(ticker=r["sym"], sector=r["sector"])
        d = store.load_dossier()
        if d is None:
            print(f"{r['sym']:12s}  — no dossier yet")
            continue
        alive = sum(1 for s in d.response_signatures if s.is_alive)
        open_q = sum(1 for q in d.open_questions if not q.resolved_on)
        print(f"{r['sym']:12s}  v{d.version}  updated={d.last_updated}  "
              f"obs={len(d.observations)}  signatures={alive}  "
              f"guidance_open={sum(1 for g in d.guidance if g.status == 'open')}  "
              f"open_questions={open_q}  digest_chars={len(d.to_digest(99999))}")
```

and register: `p = sub.add_parser("dossier-status", help="RL dossier health per ticker")`, `p.add_argument("--ticker", nargs="*")`, `p.set_defaults(func=cmd_dossier_status)` — matching the file's existing registration style exactly.

- [ ] **Step 2: Manual verification**

Run: `python -m services.scheduler.run_schedule dossier-status`
Expected: one line per managed ticker (`— no dossier yet` is fine pre-rollout)

- [ ] **Step 3: Commit**

```bash
git add services/scheduler/run_schedule.py
git commit -m "feat(cli): dossier-status subcommand for RL dossier health"
```

---

### Task 17: Harness ablation hook (conditional)

**Files:**
- Modify: `core/intelligence/rl/eval/harness.py` — ONLY IF the June-10 eval harness has landed (`core/intelligence/rl/eval/` exists)

- [ ] **Step 1: Check** — `Test-Path core/intelligence/rl/eval/harness.py`.
  - If **absent**: skip this task; leave a line in the plan-completion notes that `executable_claims` ablation must be registered when the harness lands (the flag `RL_CLAIMS_ENABLED` from Task 1 is the toggle it will flip).
  - If **present**: register ablation key `"executable_claims"` mapping to `RL_CLAIMS_ENABLED=False` in the harness's ablation registry, following however `calibration_reward`/`forgetting` are registered, plus one test mirroring the existing ablation tests.

- [ ] **Step 2: Commit (if applied)**

```bash
git add core/intelligence/rl/eval/harness.py
git commit -m "feat(rl-eval): executable_claims ablation key"
```

---

### Task 18: Docs + full regression + live verification

**Files:**
- Modify: `docs/RL_DESIGN.md`

- [ ] **Step 1: Document** — append a new section to `docs/RL_DESIGN.md`:

```markdown
## 23. Knowledge Layer — Ticker Dossier + Executable Claims (2026-06)

Spec: docs/superpowers/specs/2026-06-11-ticker-dossier-knowledge-layer-design.md

- `{TICKER}_dossier.json` (PERMANENT, 5th memory file): business summary, thesis,
  response signatures, guidance, recurring catalysts, flows, open questions, 30-obs
  episodic buffer. Written by DossierCurator (Step 8.5, EVERY day — hits record
  "what worked"). Weekly distillation in ledger_cleanup_weekly consolidates
  observations into durable sections (episodic → semantic).
- Executable claims: Lesson.trigger_tags (EVENT_TAGS vocabulary) + prioritise/
  discount_agents. apply_lesson_emphasis() fires them on tag-matching days
  (±RL_LESSON_EMPHASIS_DELTA, cap ±RL_LESSON_EMPHASIS_CAP) in Step-7 revision and
  month-start forecast build (calendar tags). FeedbackEntry.event_tags persists the
  static tagger output per day.
- Consumption: BaseAgent injects the dossier digest (≤DOSSIER_AGENT_DIGEST_CHARS)
  into every agent system prompt; chat gains get_ticker_dossier; learned weights are
  per-ticker scoped in the orchestrator (set_aggregator_weights / _resolve_weights_for).
- Static/LLM boundary: curator+distillation = LLM (never fatal, dossier untouched on
  failure); tagger, merge bounds, emphasis application, digest rendering = STATIC.
```

Also add the dossier file to the §3 memory-file tree and the new settings to the §11 configuration table.

- [ ] **Step 2: Full suite**

Run: `python -m pytest tests -q`
Expected: baseline (285+ passing pre-change) plus all new tests; zero new failures. Paste the summary line.

- [ ] **Step 3: Live execution check (reviewer evidence — run, don't read)**

```bash
python -m services.scheduler.run_schedule daily-review --ticker MARUTI
python -m services.scheduler.run_schedule dossier-status --ticker MARUTI
```
Expected: review completes; `data/predictions/automobile/MARUTI/MARUTI_dossier.json` exists with ≥1 grounded observation dated today; `dossier-status` prints non-zero `obs=`. Then open one chat turn against a running server (`POST /ui/chat/stream` with "what do we know about MARUTI?") OR call `_chat_tool_ticker_dossier("MARUTI")` directly and paste the digest output.

- [ ] **Step 4: Commit**

```bash
git add docs/RL_DESIGN.md
git commit -m "docs(rl): knowledge layer — dossier, executable claims, consumption map"
```

---

## Self-Review Notes

- **Spec coverage:** §3→Tasks 3–4, §4→Tasks 6–7+10, §5→Tasks 8+14, §6→Tasks 2+5+9+10+11, §7→Tasks 12+13+15, §8→Task 1, §10→Tasks 16–18, §2-fixes→Tasks 13+15. Harness ablation (§6.6)→Task 17 (conditional on June-10 phase).
- **Known judgment points for the executor** (flagged inline as NOTEs, all environment-plumbing not behavior): PredictionStore test base-dir param; `effective_confidence` method name; `RawLesson` dataclass-vs-pydantic field style; daily-review local variable names at the hook points; scheduler ticker-iteration helper name; `tests/unit/api` placement. Resolve each by reading the cited file/lines first — never invent a parallel pattern.
- **Order matters:** Tasks 1–9 are dependency-ordered foundations; 10–11 wire the loop; 12–16 wire consumption; 17–18 close out. Do not reorder 10 before 5/7.
