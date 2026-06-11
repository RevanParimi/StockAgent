# Ticker Dossier — RL Knowledge Layer

**Date:** 2026-06-11
**Status:** Design — approved direction (Option A), plan follows
**Scope:** Adds the missing *knowledge accumulation* layer on top of the existing RL
calibration loop, and connects it to the product (forecast agents + chatbot).
Companion to `2026-06-10-rl-intelligence-phase-design.md` (harness/calibration/forgetting),
which remains valid and ships independently.

---

## 1. Problem (evidence-verified)

The RL loop tunes numbers well but accumulates almost no usable domain knowledge:

1. **Lessons are platitudes and write-only.** Live `MARUTI_learning_ledger.json` after a
   month: 7 lessons like "Monitor sales volume more closely". The `rule` text is injected
   into one prompt (FeedbackAgent) and never applied; the only programmatic use of lessons
   is a flat category→agent +0.01 nudge (`generate_forecast.py:79-120`).
2. **Nothing is learned on hit days.** FeedbackAgent runs daily
   (`daily_review.py:769`) but extracts knowledge only from misses. 20 consecutive
   correct calls teach the system nothing about *why* it was right.
3. **No entity-level memory.** Nothing accumulates "MARUTI's story": guidance, recurring
   catalysts, response signatures ("drops ~2% within 2 days of crude > $90"), flow trends.
4. **Chat sees almost none of it.** Chat has `get_rl_prediction` (envelope row) and
   `get_rl_insights` (accuracy + top weights) — but no lessons, no knowledge, and two
   bugs: sector hardcoded to `"automobile"` (`ui_data.py:1271, 1393`) and
   `wm.learned_weights` (`ui_data.py:1409-1410`) — `WeightMemory` has no such attribute
   (silently skips via broad except).
5. **Learned weights** *are* auto-loaded in `/analyse`
   (`base_orchestrator.py:112-114`) — but cached in `self._aggregator_weights` per
   orchestrator instance, so instance reuse across tickers would serve stale weights.

## 2. Goal

A per-ticker **living dossier** — updated every trading day from the context the loop
already fetches, consolidated weekly, consumed by both the forecast agents and the chat
pipeline — plus **executable claims** so learned patterns actually fire on matching days.
The artifact should read like the notes of an analyst who has followed the stock daily.

---

## 3. Component A — `TickerDossier` schema + store

New `src/backend/shared/schemas/dossier.py` (Pydantic, same style as `feedback.py`):

```python
class DossierObservation(BaseModel):      # episodic buffer entry
    date: str
    observation: str                       # one factual sentence, grounded in that day's context
    tags: list[str] = []                   # controlled vocabulary (see §6)
    materiality: float = 0.5               # 0–1, curator-assigned
    outcome_link: str = ""                 # "hit" | "miss" | "" (what the day's review said)

class ResponseSignature(BaseModel):        # quantified behavioral pattern
    signature_id: str                      # "RS001"
    trigger_tags: list[str]                # e.g. ["crude_price"]
    response: str                          # "closes -1.5% to -2.5% within 2 sessions"
    occurrences: int = 1
    contradictions: int = 0
    first_seen: str
    last_seen: str
    confidence: float = 0.5
    evidence_dates: list[str] = []         # capped at last 10

class GuidanceItem(BaseModel):
    date: str; source: str                 # "Q4 earnings call", "NSE filing"
    guidance: str
    status: str = "open"                   # open | met | missed | withdrawn

class RecurringCatalyst(BaseModel):
    name: str                              # "FADA monthly dispatch data"
    typical_timing: str                    # "~10th of each month"
    expected_effect: str
    hit_rate: str = ""                     # filled by distillation, e.g. "3/4 moved price"

class OpenQuestion(BaseModel):
    question: str; raised_on: str
    resolved_on: str = ""; answer: str = ""

class TickerDossier(BaseModel):
    ticker: str; sector: str
    created_at: str; last_updated: str
    version: int = 1                       # bumped by weekly distillation
    business_summary: str = ""             # 2–4 sentences, distillation-maintained
    current_thesis: str = ""               # stance + why, curator-maintained
    thesis_since: str = ""
    response_signatures: list[ResponseSignature] = []
    guidance: list[GuidanceItem] = []
    recurring_catalysts: list[RecurringCatalyst] = []
    flow_notes: str = ""                   # FII/DII/bulk-deal trend, 1–3 sentences
    open_questions: list[OpenQuestion] = []
    observations: list[DossierObservation] = []   # rolling, max DOSSIER_MAX_OBSERVATIONS

    def to_digest(self, max_chars: int) -> str: ...  # markdown digest for prompt injection
```

**Persistence:** `PredictionStore` gains `_dossier_path()` →
`data/predictions/{sector}/{TICKER}/{TICKER}_dossier.json` (PERMANENT, like the ledger),
plus `load_dossier()` / `save_dossier()` using the existing atomic `_write_json` +
per-path lock machinery (`prediction_store.py:68, 153-179`).

`to_digest()` renders sections in priority order (thesis → signatures → guidance →
catalysts → flows → open questions → last 5 observations) and truncates whole sections —
never mid-sentence — to fit `max_chars`.

## 4. Component B — `DossierCurator` (daily, every day)

New `core/intelligence/rl/agents/dossier_curator.py`, LLM pattern copied from
`FeedbackAgent` (json_object, temp 0.2, ~900 max_tokens, never raises — on any failure
the dossier is left untouched and the review continues).

**Hook:** `daily_review.py` new **Step 8.5**, immediately after
`store.append_feedback_entry` (`daily_review.py:1011`) — every trading day, hit or miss.

**Input (all already in scope at that point):** today's `market_context` (news + NSE +
FII/DII + off-market + F&O when present), predicted vs actual + `direction_correct`,
`fb_output` (miss analysis or hit-day output), the day's agent catalysts, current dossier
digest (≤ `DOSSIER_DIGEST_MAX_CHARS`).

**Output (strict JSON):**
```json
{
  "event_tags_today": ["crude_price", "fii_flow"],
  "new_observations": [{"observation": "...", "tags": [...], "materiality": 0.7}],
  "signature_updates": [{"action": "confirm|create|contradict", "signature_id": "RS001",
                          "trigger_tags": [...], "response": "..."}],
  "guidance_updates": [{"action": "add|met|missed", "guidance": "...", "source": "..."}],
  "catalyst_updates": [{"action": "add", "name": "...", "typical_timing": "...", "expected_effect": "..."}],
  "thesis_update": null,
  "flow_note": "",
  "open_question_updates": [{"action": "raise|resolve", "question": "...", "answer": ""}]
}
```

**Static merge (deterministic, bounded):** max 3 new observations/day (top materiality);
observations list capped at `DOSSIER_MAX_OBSERVATIONS` (evict oldest); signature
`confirm` → occurrences+1, confidence +0.05 (cap 0.95), `contradict` → contradictions+1,
confidence −0.10; a signature with contradictions ≥ occurrences is dropped at
distillation. Hit days explicitly produce confirmations — the prompt instructs: "on
correct days, record WHAT WORKED and which predicted catalysts materialised."

The day's `event_tags` persisted on `FeedbackEntry.event_tags: list[str]` (new optional
field, default `[]`) come from the **static keyword tagger only** (§6), computed right
after market-context assembly so Step-7 claim matching can use them the same day —
deterministic and LLM-independent. Curator-emitted tags additionally enrich dossier
observations but are not written back to the already-persisted entry.

## 5. Component C — Weekly distillation

`distill_dossier(ticker, sector)` in `dossier_curator.py`, invoked from the existing
weekly scheduler job (`scheduler.py:225-234`, `ledger_cleanup_weekly` —
extend the job rather than adding a new trigger). LLM pass over the full dossier:

- Compress observations older than 7 days into durable sections (signatures, business
  summary, flow notes) — episodic → semantic.
- Update `RecurringCatalyst.hit_rate` from evidence.
- Drop signatures with contradictions ≥ occurrences; mark stale guidance.
- Enforce `to_digest(DOSSIER_DIGEST_MAX_CHARS)` renders within budget; bump `version`.

**Static fallback** when LLM unavailable: evict observations beyond cap, no semantic
merge, version unchanged. Distillation also never raises.

## 6. Component D — Executable claims (Lesson upgrade)

Make lessons fire on matching days instead of being prompt furniture.

1. **Schema** (`feedback.py`): `Lesson` gains `trigger_tags: list[str] = []`,
   `prioritise_agents: list[str] = []`, `discount_agents: list[str] = []` (all optional —
   legacy lessons keep working). No numeric deltas stored on lessons (the schema comment
   at `feedback.py:414-416` is right: stored deltas go stale).
2. **FeedbackAgent prompt** (`core/config/prompts/shared/feedback_agent.py`): new_lessons
   must include `trigger_tags` from the controlled vocabulary and may name
   `prioritise_agents`/`discount_agents` from the live agent list.
3. **Controlled vocabulary:** one module-level frozenset `EVENT_TAGS` in `feedback.py`,
   superset of the existing `semantic_tags` vocabulary (`feedback.py:424-429`):
   `central_bank_event, fii_flow, crude_price, currency, earnings_event, guidance_change,
   sector_policy, technical_pattern, seasonal, credit_event, supply_chain, regulatory,
   global_macro, expiry_week, block_deal, monsoon, budget_event`. Unknown tags from the
   LLM are dropped at merge time.
4. **Static keyword tagger:** `tag_events(market_context: str) -> list[str]` (pure
   function, keyword → tag map) so claims still fire when the curator LLM fails. Day
   tags = curator tags ∪ static tags.
5. **Application:** new `apply_lesson_emphasis(day_agent_scores, lessons, today_tags)`:
   for each still-valid lesson with `eff_confidence ≥ 0.45` whose `trigger_tags`
   intersect `today_tags` → `prioritise_agents` get `+RL_LESSON_EMPHASIS_DELTA` (0.03),
   `discount_agents` get `−RL_LESSON_EMPHASIS_DELTA`; total per agent capped at ±0.06.
   Called from **both** Step-7 revision (`daily_review.py`) and
   `_build_daily_forecasts` (`generate_forecast.py`) — tagged lessons use this path;
   untagged legacy lessons keep the category-based micro-adjustment (which is narrowed
   to lessons without `trigger_tags`, avoiding double-counting).
6. **Ablation:** behind `RL_CLAIMS_ENABLED` (default True); registered as ablation key
   `executable_claims` in the June-10 eval harness so the accuracy delta is measurable.

## 7. Component E — Consumption (one brain)

1. **Forecast agents:** mirror the `_extra_queries` lazy-load pattern
   (`base_agent.py:428-436, 479-485`) — `BaseAgent` lazily loads the dossier digest once
   per (ticker, run) and appends to the system prompt as
   `[ACCUMULATED TICKER KNOWLEDGE — learned from daily tracking]\n{digest}`
   (≤ `DOSSIER_AGENT_DIGEST_CHARS`, 1500). Empty/missing dossier → no injection,
   byte-identical prompts. Applies to `/analyse`, chat's `run_agent_analysis`,
   forecast and review paths automatically (same BaseAgent).
2. **Chat tool:** new `get_ticker_dossier(ticker)` in `ui_data.py` chat tools (sector
   resolved by directory scan like `_chat_tool_rl_prediction`, `ui_data.py:2415`),
   returning `to_digest(2000)`. Register in `_CHAT_TOOLS`, `_dispatch_chat_tool`, and
   the system-prompt tool table (deep-dive row: `get_live_price + get_stock_analysis +
   get_rl_prediction + get_ticker_dossier + search_market_news`).
3. **Chat bug fixes:** `_ctx_rl_learning` — resolve sector per ticker from
   `managed_tickers.json` (fall back to directory scan) instead of `"automobile"`;
   use `wm.effective_weights()`/`wm.current_weights` instead of nonexistent
   `wm.learned_weights`. Same sector fix at `ui_data.py:1271`.
4. **Weight scoping check:** confirm orchestrator instances are not reused across
   tickers in API routes; if they are, key `_aggregator_weights` by ticker.

## 8. New settings (real file: `src/backend/shared/config/settings/base.py`; `core/config/settings/base.py` is a re-export shim)

| Setting | Default | Controls |
|---|---|---|
| `RL_DOSSIER_ENABLED` | `True` | Curator step + injection on/off |
| `DOSSIER_MAX_OBSERVATIONS` | `30` | Episodic buffer cap |
| `DOSSIER_DIGEST_MAX_CHARS` | `2500` | Full digest budget (chat tool, curator input) |
| `DOSSIER_AGENT_DIGEST_CHARS` | `1500` | Digest budget inside the 8 agents' prompts |
| `DOSSIER_MAX_NEW_OBS_PER_DAY` | `3` | Daily merge bound |
| `RL_CLAIMS_ENABLED` | `True` | Executable-claims application (ablation key) |
| `RL_LESSON_EMPHASIS_DELTA` | `0.03` | Per-lesson emphasis nudge |
| `RL_LESSON_EMPHASIS_CAP` | `0.06` | Per-agent total emphasis cap |
| `RL_LESSON_MATCH_MIN_CONF` | `0.45` | Min eff_confidence for a claim to fire |

## 9. Cost & safety envelope

- +1 LLM call/ticker/day (curator, ~900 tokens out) and +1/ticker/week (distillation) on
  top of the existing FeedbackAgent + conditional ThesisReviewer. Same client, model, and
  retry budget as FeedbackAgent.
- Every new step is non-fatal: curator/distillation failures leave the dossier untouched
  and never block the daily review (same contract as ThesisReviewer,
  `thesis_reviewer.py` safety pattern).
- All writes atomic via existing `_write_json`; dossier is one file per ticker.
- Flag-off behavior (`RL_DOSSIER_ENABLED=False`, `RL_CLAIMS_ENABLED=False`) is
  byte-identical to today.

## 10. Validation

- **Unit/TDD per component** (schemas, merge bounds, tagger, emphasis application,
  digest truncation, store round-trip, chat tool, prompt injection gating).
- **Execution check (reviewer must run, not read):** run `daily_review` for a real ticker
  on a real date → show the dossier JSON grew with grounded observations; run it on a
  HIT day → show a confirmation/`what worked` observation; run chat
  `get_ticker_dossier` → show digest; run an `/analyse` → show
  `[ACCUMULATED TICKER KNOWLEDGE]` in the built prompt (log/debug).
- **Harness:** `executable_claims` ablation wired; accuracy delta reported once the
  June-10 harness lands. Dossier itself is knowledge-layer (not accuracy-gated);
  its health metrics (size, staleness, signature count) printed by a small
  `dossier-status` CLI subcommand on the existing `run_schedule` entry point.

## 11. Explicitly NOT in scope

- No embeddings/vector retrieval yet — tag matching first; revisit only if tag recall
  proves insufficient.
- No fine-tuning, no parametric RL.
- No change to WeightAdapter math, regime multipliers, conviction tracker, or the
  June-10 spec's components (they ship separately).
- No frontend/dossier UI (chat tool only; UI card can come later).

## 12. File map

| File | Change |
|---|---|
| `src/backend/shared/schemas/dossier.py` | NEW — all §3 models + `to_digest` |
| `src/backend/shared/schemas/feedback.py` | `Lesson.trigger_tags/prioritise_agents/discount_agents`; `FeedbackEntry.event_tags`; `EVENT_TAGS` vocabulary; `tag_events()` |
| `core/intelligence/rl/stores/prediction_store.py` | `_dossier_path`, `load_dossier`, `save_dossier` |
| `core/intelligence/rl/agents/dossier_curator.py` | NEW — curator + merge + `distill_dossier` |
| `core/config/prompts/shared/dossier_curator.py` | NEW — curator + distillation prompts |
| `core/intelligence/rl/workflows/daily_review.py` | Step 8.5 curator hook; Step 7 `apply_lesson_emphasis`; persist `event_tags` |
| `core/intelligence/rl/workflows/generate_forecast.py` | `apply_lesson_emphasis` in `_build_daily_forecasts`; narrow legacy micro-adjust to untagged lessons |
| `core/config/prompts/shared/feedback_agent.py` | Lesson output contract: trigger_tags + agent lists |
| `src/backend/shared/pipeline/base_agent.py` | Lazy dossier digest injection |
| `services/scheduler/python/scheduler.py` | Weekly distillation in `ledger_cleanup_weekly` |
| `services/api/routes/ui_data.py` | `get_ticker_dossier` tool; `_ctx_rl_learning` fixes; sector-hardcode fixes |
| `services/scheduler/run_schedule` CLI | `dossier-status` subcommand |
| `src/backend/shared/config/settings/base.py` | 9 new settings (core path is a shim) |
| `tests/unit/intelligence/rl/test_dossier*.py`, `test_lesson_claims.py`, chat tool tests | NEW |
