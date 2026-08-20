# Switch Validation and Miss Attribution — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the advisor's switch rule measurable by grading the candidate pairs it *evaluates and rejects*, not only the ~4% it acts on, and classify its misses into unpredictable / technical / knowledge / research.

**Architecture:** A fourth lane in the existing verification layer. The advisor emits an evaluation row per (holding, candidate) considered; a new grading lane prices both legs at 10/30/60 trading days and asks whether the destination beat the origin; a classifier attributes the misses; the report gates every claim behind a non-overlapping strided subsample. Read-only throughout — nothing here feeds RL, autopilot, or verdicts.

**Tech Stack:** Python 3.13, pydantic v2, pytest, append-only JSONL, `cfg()` config.

**Spec:** `docs/superpowers/specs/2026-08-20-switch-validation-design.md` — read it before Task 1. The plan argues from the spec; where they disagree, the spec wins.

**Branch:** `feat/switch-validation`, off `main` @ `0b5a8e6`.

## Global Constraints

- **Never raise on the hot path.** Every function added here logs and degrades. The advisor, the pipeline, and the scheduler must not be takeable down by telemetry. Follow the existing `logger.warning("[x] ... (non-fatal): %s", exc)` idiom.
- **Append-only.** Source ledgers are never rewritten. Grading is derived data and derived data must not corrupt the record of what the user was told.
- **`is_correct` in `core/audit/rules.py` is NOT modified.** Its docstring states that changing it invalidates accumulated history. Add beside it.
- **All tunables via `cfg()` with NO `env=`.** Non-secret toggles live in `config.yaml` only. Every new key must also be added to the config table in `CODEBASE.md`.
- **TDD, strictly.** Write the test, run it, watch it fail for the right reason, then implement. A test that passes on first run is testing existing behaviour — fix the test.
- **Commit after every task.** Run the full suite (`python -m pytest -q`, ~6 min) before the final commit of the last task; per-task commits may run only the touched test files.
- **Baseline:** `main` @ `0b5a8e6` is **2884 passed, 12 skipped, 0 failed.** Any deviation other than tests you added is a regression — stop and investigate.

---

### Task 1: `is_switch_correct` and the switch lane on the outcome schema

**Files:**
- Modify: `core/audit/rules.py` (append after `is_correct`)
- Modify: `src/backend/shared/schemas/audit.py:14` (Lane), `:43` (new fields)
- Test: `tests/unit/audit/test_audit_rules.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `is_switch_correct(origin_excess_pct: float, dest_excess_pct: float) -> bool`; `Lane` literal gains `"switch"`; `AuditOutcome.candidate: str = ""` and `AuditOutcome.miss_class: str = ""`.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/audit/test_audit_rules.py`:

```python
# -- switch pairs (2026-08-20) ----------------------------------------------

import pytest
from core.audit.rules import is_switch_correct


@pytest.mark.parametrize("origin,dest,expected", [
    (-2.0, -20.0, False),   # the case the old grade got WRONG: origin fell, so
                            # is_correct() scored this SWITCH correct — but the
                            # destination fell ten times harder.
    (-20.0, -2.0, True),    # rotating genuinely helped
    (5.0, 9.0, True),       # both up, destination further
    (9.0, 5.0, False),      # both up, staying was better
    (3.0, 3.0, False),      # a dead heat is not a win; rotation has costs
])
def test_is_switch_correct_compares_the_pair(origin, dest, expected):
    assert is_switch_correct(origin, dest) is expected


def test_switch_lane_and_pair_fields_exist_on_the_outcome_row():
    from backend.shared.schemas.audit import AuditOutcome
    row = AuditOutcome(
        ref="switch:2026-08-20|OLD|NEW", lane="switch", user_id="u",
        symbol="OLD", issued_on="2026-08-20", horizon_td=10,
        graded_on="2026-09-03", entry_close=100.0, exit_close=98.0,
        return_pct=-2.0, bench_entry=1000.0, bench_exit=1000.0,
        bench_pct=0.0, excess_pct=-2.0, correct=False,
        graded_at="2026-09-03T00:00:00+00:00",
        switch_excess_pct=-20.0, candidate="NEW", miss_class="knowledge")
    assert row.lane == "switch" and row.candidate == "NEW"
    assert row.miss_class == "knowledge"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/audit/test_audit_rules.py -q`
Expected: FAIL — `ImportError: cannot import name 'is_switch_correct'`, and a pydantic `ValidationError` on `lane="switch"`.

- [ ] **Step 3: Write minimal implementation**

Append to `core/audit/rules.py`:

```python
def is_switch_correct(origin_excess_pct: float, dest_excess_pct: float) -> bool:
    """Did rotating beat staying, over the same window?

    Deliberately NOT part of is_correct(). That function defines what every
    accumulated advice row already means, and its docstring says so; a switch
    is a different question and gets its own answer here.

    Both legs are excess over the same benchmark, so the benchmark cancels and
    this is a pure relative-strength comparison. A dead heat is False:
    rotating has real costs (brokerage, spread, tax) that this layer does not
    model, so a tie is not evidence that moving was right.
    """
    return dest_excess_pct > origin_excess_pct
```

In `src/backend/shared/schemas/audit.py`, line 14:

```python
Lane = Literal["advice", "alert", "shelf", "switch"]
```

and after the `conviction` field:

```python
    # Switch lane only (2026-08-20). Both written by grade_switch_lane — no
    # declared-but-unwritten fields, which is the outcome_*td failure this
    # whole layer exists to correct.
    candidate: str = ""            # the destination symbol
    miss_class: str = ""           # attribution bucket; "" when not a miss
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/audit/ -q`
Expected: PASS, no other audit test disturbed.

- [ ] **Step 5: Commit**

```bash
git add core/audit/rules.py src/backend/shared/schemas/audit.py tests/unit/audit/test_audit_rules.py
git commit -m "feat(audit): grade a switch on the pair, not on the origin alone"
```

---

### Task 2: The evaluation ledger

**Files:**
- Modify: `src/backend/shared/schemas/portfolio.py` (new model, append near `AdviceRecord`)
- Modify: `core/portfolio/store.py` (new path + append/load, beside `append_advice` at `:242`)
- Test: `tests/unit/test_portfolio_store_switch_evals.py` (create)

**Interfaces:**
- Consumes: Task 1's schema module (no code dependency).
- Produces: `SwitchEvaluation` pydantic model; `PortfolioStore.append_switch_evaluations(rows: list[SwitchEvaluation]) -> None`; `PortfolioStore.load_switch_evaluations(limit: int = 5000) -> list[SwitchEvaluation]`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_portfolio_store_switch_evals.py`:

```python
"""Switch-evaluation ledger — append-only, one row per considered pair."""
from backend.shared.schemas.portfolio import SwitchEvaluation
from core.portfolio.store import PortfolioStore


def _row(candidate="NEWCO", decision="rejected", reason="not_best"):
    return SwitchEvaluation(
        date="2026-08-20", user_id="u1", origin="OLDCO", origin_close=100.0,
        origin_sector="automobile", origin_confidence=0.42,
        origin_verdict="EXIT", candidate=candidate, candidate_close=250.0,
        candidate_sector="pharma", candidate_conviction=0.81,
        decision=decision, reason=reason, rationale_hash="abc123")


def test_append_then_load_round_trips(tmp_path):
    store = PortfolioStore(user_id="u1", base_dir=str(tmp_path))
    store.append_switch_evaluations([_row(), _row(candidate="OTHERCO")])
    rows = store.load_switch_evaluations()
    assert [r.candidate for r in rows] == ["NEWCO", "OTHERCO"]
    assert rows[0].reason == "not_best"


def test_append_is_additive_never_rewrites(tmp_path):
    store = PortfolioStore(user_id="u1", base_dir=str(tmp_path))
    store.append_switch_evaluations([_row()])
    store.append_switch_evaluations([_row(candidate="THIRDCO")])
    assert len(store.load_switch_evaluations()) == 2


def test_a_corrupt_line_is_skipped_not_fatal(tmp_path):
    store = PortfolioStore(user_id="u1", base_dir=str(tmp_path))
    store.append_switch_evaluations([_row()])
    with open(store._switch_eval_path(), "a", encoding="utf-8") as fh:
        fh.write("{not json\n")
    assert len(store.load_switch_evaluations()) == 1


def test_empty_batch_writes_nothing(tmp_path):
    store = PortfolioStore(user_id="u1", base_dir=str(tmp_path))
    store.append_switch_evaluations([])
    assert store.load_switch_evaluations() == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_portfolio_store_switch_evals.py -q`
Expected: FAIL — `ImportError: cannot import name 'SwitchEvaluation'`.

- [ ] **Step 3: Write minimal implementation**

Append to `src/backend/shared/schemas/portfolio.py`:

```python
class SwitchEvaluation(BaseModel):
    """One (holding, shelf-candidate) pair the advisor considered on one day.

    Written for EVERY holding on every advisor run, not only when a SWITCH
    fires — the rule acts on ~4% of its calls, so grading only the taken pairs
    never accumulates a sample. `decision` records what the rule did and
    `reason` why it declined; a rejected pair that would have won is exactly as
    informative as a taken pair that lost.
    """
    date: str                      # ISO date the evaluation was made
    user_id: str
    origin: str                    # the held symbol
    origin_close: float
    origin_sector: str = ""
    origin_confidence: float = 0.5
    origin_verdict: str = ""       # the advisor's verdict for the origin that day
    candidate: str                 # the shelf idea considered
    candidate_close: float
    candidate_sector: str = ""
    candidate_conviction: float = 0.0
    decision: Literal["taken", "rejected"]
    reason: str = ""               # "" when taken; else the declining branch
    rationale_hash: str = ""       # joins back to the origin's AdviceRecord
```

`Literal` is already imported in that module; confirm before adding an import.

In `core/portfolio/store.py`, after `_ledger_path` (`:91`):

```python
    def _switch_eval_path(self) -> Path:
        return self._dir / "switch_evaluations.jsonl"
```

and after `load_advice` (`:246`):

```python
    def append_switch_evaluations(self, rows: list) -> None:
        """Append switch-evaluation rows. No-op on an empty batch."""
        if not rows:
            return
        with open(self._switch_eval_path(), "a", encoding="utf-8") as fh:
            for rec in rows:
                fh.write(json.dumps(rec.model_dump(), ensure_ascii=False) + "\n")

    def load_switch_evaluations(self, limit: int = 5000) -> list:
        """The newest `limit` evaluation rows, oldest-first. A corrupt line is
        skipped and logged, never fatal — same contract as load_advice."""
        from backend.shared.schemas.portfolio import SwitchEvaluation
        path = self._switch_eval_path()
        if not path.exists():
            return []
        out: list = []
        for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(SwitchEvaluation(**json.loads(line)))
            except Exception as exc:
                logger.warning("[PortfolioStore] skipping bad switch-eval line: %s", exc)
        return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_portfolio_store_switch_evals.py tests/unit/test_portfolio_store.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/backend/shared/schemas/portfolio.py core/portfolio/store.py tests/unit/test_portfolio_store_switch_evals.py
git commit -m "feat(portfolio): add the append-only switch-evaluation ledger"
```

---

### Task 3: The advisor returns the evaluation, not just the winner

**Files:**
- Modify: `core/portfolio/advisor.py:245` (`_best_switch_candidate`)
- Test: `tests/unit/test_portfolio_advisor_switch.py`

**Interfaces:**
- Consumes: nothing from Tasks 1–2 (returns plain dicts; the pipeline builds `SwitchEvaluation` in Task 4).
- Produces: `evaluate_switch_candidates(signals, shelf_ideas, sector_weights, held_symbols=None, max_candidates=5) -> tuple[object | None, list[dict]]`. Each dict has keys `candidate`, `candidate_sector`, `candidate_conviction`, `decision`, `reason`. `_best_switch_candidate(...)` keeps its current signature and returns `evaluate_switch_candidates(...)[0]`, so `decide()` is untouched.

**Reason vocabulary** — exactly the four existing `continue` branches, same order:
`already_held`, `sector_not_underweight`, `conviction_gap_too_small`, `not_best`.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_portfolio_advisor_switch.py`:

```python
# -- the evaluation, not just the winner (2026-08-20) -----------------------

from core.portfolio.advisor import evaluate_switch_candidates


def _evals(ideas, weights, held=None, max_candidates=5):
    _best, rows = evaluate_switch_candidates(
        _exit_signals(confidence=0.5), ideas, weights,
        held_symbols=held, max_candidates=max_candidates)
    return {r["candidate"]: r for r in rows}


def test_every_considered_idea_yields_a_row_with_its_reason():
    rows = _evals(
        [_idea("HELD", "pharma", 0.95),      # already held
         _idea("HEAVY", "automobile", 0.95), # sector not underweight
         _idea("WEAK", "fmcg", 0.55),        # conviction gap too small
         _idea("GOOD", "metals", 0.90),      # wins
         _idea("ALSO", "textiles", 0.80)],   # qualifies but loses
        {"automobile": 60.0, "pharma": 5.0, "fmcg": 5.0,
         "metals": 5.0, "textiles": 5.0},
        held={"OLDCO", "HELD"})
    assert rows["HELD"]["reason"] == "already_held"
    assert rows["HEAVY"]["reason"] == "sector_not_underweight"
    assert rows["WEAK"]["reason"] == "conviction_gap_too_small"
    assert rows["ALSO"]["reason"] == "not_best"
    assert rows["GOOD"]["decision"] == "taken" and rows["GOOD"]["reason"] == ""
    assert all(r["decision"] == "rejected" for k, r in rows.items() if k != "GOOD")


def test_the_winner_is_unchanged_by_capture():
    best, _rows = evaluate_switch_candidates(
        _exit_signals(confidence=0.5),
        [_idea("A", "pharma", 0.70), _idea("B", "fmcg", 0.85)],
        {"automobile": 60.0, "pharma": 5.0, "fmcg": 5.0})
    assert best.symbol == "B"


def test_capture_is_bounded_by_max_candidates_highest_conviction_first():
    rows = _evals([_idea(f"C{i}", "pharma", 0.60 + i / 100) for i in range(10)],
                  {"automobile": 60.0, "pharma": 5.0}, max_candidates=3)
    assert len(rows) == 3
    assert set(rows) == {"C9", "C8", "C7"}


def test_dropped_ideas_are_not_evaluated_at_all():
    """A dropped idea was never a candidate; recording it as "rejected" would
    put a shelf-lifecycle event into a decision-rule ledger."""
    from backend.shared.schemas.discovery import ShelfIdea
    rows = _evals([ShelfIdea(symbol="GONE", sector="pharma", added="2026-07-01",
                             conviction=0.99, status="dropped")],
                  {"automobile": 60.0, "pharma": 5.0})
    assert rows == {}


def test_evaluations_are_produced_even_when_nothing_qualifies():
    """The whole point: an EXIT that found no candidate is still evidence."""
    rows = _evals([_idea("HEAVY", "automobile", 0.95)], {"automobile": 60.0})
    assert rows["HEAVY"]["reason"] == "sector_not_underweight"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_portfolio_advisor_switch.py -q`
Expected: FAIL — `ImportError: cannot import name 'evaluate_switch_candidates'`.

- [ ] **Step 3: Write minimal implementation**

Replace `_best_switch_candidate` in `core/portfolio/advisor.py` with:

```python
def evaluate_switch_candidates(signals: AdvisorSignals, shelf_ideas,
                               sector_weights: dict,
                               held_symbols: set[str] | None = None,
                               max_candidates: int = 5):
    """Return (winner_or_None, evaluation_rows).

    The rows are the point. The advisor acts on ~4% of its calls, so grading
    only the pairs it took never accumulates a sample; every pair it CONSIDERED
    and declined is evidence about the same rule. Each row records which branch
    declined it, named exactly after that branch.

    Pure: no I/O, no clock. Candidates are the top `max_candidates` ACTIVE
    ideas by conviction — a dropped or promoted idea was never a candidate and
    yields no row.
    """
    own_weight = sector_weights.get(signals.sector, 0.0)
    excluded = set(held_symbols or ()) | {signals.symbol}
    active = sorted((i for i in (shelf_ideas or [])
                     if getattr(i, "status", "active") == "active"),
                    key=lambda i: -i.conviction)[:max_candidates]

    rows: list[dict] = []
    qualified: list = []
    for idea in active:
        reason = ""
        if idea.symbol in excluded:
            reason = "already_held"
        elif sector_weights.get(idea.sector, 0.0) >= own_weight:
            reason = "sector_not_underweight"
        elif idea.conviction - signals.confidence < settings.ADVISOR_SWITCH_CONVICTION_GAP:
            reason = "conviction_gap_too_small"
        else:
            qualified.append(idea)
        rows.append({"candidate": idea.symbol,
                     "candidate_sector": getattr(idea, "sector", ""),
                     "candidate_conviction": getattr(idea, "conviction", 0.0),
                     "decision": "rejected", "reason": reason})

    best = max(qualified, key=lambda i: i.conviction, default=None)
    for row in rows:
        if not row["reason"]:
            if best is not None and row["candidate"] == best.symbol:
                row["decision"], row["reason"] = "taken", ""
            else:
                row["reason"] = "not_best"
    return best, rows


def _best_switch_candidate(signals: AdvisorSignals, shelf_ideas, sector_weights: dict,
                           held_symbols: set[str] | None = None):
    """SWITCH (spec §5.2) — the winner only. See evaluate_switch_candidates."""
    return evaluate_switch_candidates(signals, shelf_ideas, sector_weights,
                                      held_symbols)[0]
```

> **Behaviour note for the implementer:** the original picked the winner with a
> running `if best is None or idea.conviction > best.conviction`, which keeps
> the FIRST idea on a conviction tie. `max(..., key=...)` also keeps the first
> maximum, so tie-breaking is unchanged. The pre-sort by conviction changes
> which idea is "first" on a tie only when `max_candidates` truncates — that is
> the intended new bound, not a regression.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_portfolio_advisor_switch.py tests/unit/test_portfolio_pipeline.py tests/unit/test_autopilot_executor_switch.py -q`
Expected: PASS — all pre-existing switch tests included, since `decide()` must be behaviourally unchanged.

- [ ] **Step 5: Commit**

```bash
git add core/portfolio/advisor.py tests/unit/test_portfolio_advisor_switch.py
git commit -m "feat(advisor): return the whole switch evaluation, not just the winner"
```

---

### Task 4: Capture every holding's evaluation in the pipeline

**Files:**
- Modify: `core/portfolio/pipeline.py` (Step 3 loop, around `:120`)
- Modify: `config.yaml` (`advisor:` block)
- Modify: `CODEBASE.md` (config table)
- Test: `tests/unit/test_portfolio_pipeline.py`

**Interfaces:**
- Consumes: `evaluate_switch_candidates` (Task 3), `SwitchEvaluation` + `append_switch_evaluations` (Task 2).
- Produces: `capture_switch_evaluations(rec, signals, shelf_ideas, sector_weights, held_symbols, candidate_closes, user_id, on) -> list[SwitchEvaluation]` in `core/portfolio/pipeline.py` — pure, takes prices in, does no fetching.

**Config added here:**

| Key | Default |
|---|---|
| `advisor.switch_eval_enabled` | `true` |
| `advisor.switch_eval_max_candidates` | `5` |

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_portfolio_pipeline.py`:

```python
# -- switch-evaluation capture (2026-08-20) --------------------------------

def _sig(symbol="OLDCO", sector="automobile", confidence=0.5):
    from core.portfolio.advisor import AdvisorSignals
    return AdvisorSignals(symbol=symbol, sector=sector, close=100.0,
                          atr_stop_pct=12.0, unrealised_pnl_pct=-15.0,
                          holding_age_days=100, confidence=confidence)


def _shelf(symbol, sector, conviction):
    from backend.shared.schemas.discovery import ShelfIdea
    return ShelfIdea(symbol=symbol, sector=sector, added="2026-07-01",
                     conviction=conviction)


def _rec(symbol="OLDCO", verdict="HOLD"):
    from backend.shared.schemas.portfolio import AdviceRecord
    return AdviceRecord(date="2026-08-20", user_id="u1", symbol=symbol,
                        verdict=verdict, close=100.0, unrealised_pnl_pct=-15.0,
                        stop_pct=12.0, rationale_hash="hash1")


def test_capture_produces_one_row_per_candidate_with_both_prices():
    from datetime import date
    from core.portfolio.pipeline import capture_switch_evaluations
    rows = capture_switch_evaluations(
        _rec(), _sig(), [_shelf("NEWCO", "pharma", 0.9)],
        {"automobile": 60.0, "pharma": 5.0}, {"OLDCO"},
        {"NEWCO": 250.0}, "u1", date(2026, 8, 20))
    assert len(rows) == 1
    r = rows[0]
    assert r.origin == "OLDCO" and r.candidate == "NEWCO"
    assert r.origin_close == 100.0 and r.candidate_close == 250.0
    assert r.decision == "taken"
    assert r.rationale_hash == "hash1"
    assert r.origin_verdict == "HOLD"


def test_capture_happens_for_a_HOLD_not_only_an_EXIT():
    """The whole reframe: evidence must accrue at the rate the rule EVALUATES,
    and it evaluates on every holding every run."""
    from datetime import date
    from core.portfolio.pipeline import capture_switch_evaluations
    rows = capture_switch_evaluations(
        _rec(verdict="HOLD"), _sig(), [_shelf("NEWCO", "pharma", 0.9)],
        {"automobile": 60.0, "pharma": 5.0}, {"OLDCO"},
        {"NEWCO": 250.0}, "u1", date(2026, 8, 20))
    assert rows and rows[0].origin_verdict == "HOLD"


def test_an_unpriceable_candidate_is_dropped_not_guessed():
    from datetime import date
    from core.portfolio.pipeline import capture_switch_evaluations
    rows = capture_switch_evaluations(
        _rec(), _sig(), [_shelf("NEWCO", "pharma", 0.9),
                         _shelf("NOPRICE", "metals", 0.9)],
        {"automobile": 60.0, "pharma": 5.0, "metals": 5.0}, {"OLDCO"},
        {"NEWCO": 250.0}, "u1", date(2026, 8, 20))
    assert [r.candidate for r in rows] == ["NEWCO"]


def test_capture_is_a_no_op_when_the_flag_is_off(monkeypatch):
    from datetime import date
    import core.portfolio.pipeline as pl
    monkeypatch.setattr(pl, "_switch_eval_enabled", lambda: False)
    rows = pl.capture_switch_evaluations(
        _rec(), _sig(), [_shelf("NEWCO", "pharma", 0.9)],
        {"automobile": 60.0, "pharma": 5.0}, {"OLDCO"},
        {"NEWCO": 250.0}, "u1", date(2026, 8, 20))
    assert rows == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_portfolio_pipeline.py -q`
Expected: FAIL — `ImportError: cannot import name 'capture_switch_evaluations'`.

- [ ] **Step 3: Write minimal implementation**

Add to `core/portfolio/pipeline.py` beside `advice_alert_fields`:

```python
def _switch_eval_enabled() -> bool:
    from backend.shared.config.settings.loader import cfg
    return bool(cfg("advisor.switch_eval_enabled", fallback=True))


def _switch_eval_max_candidates() -> int:
    from backend.shared.config.settings.loader import cfg
    return int(cfg("advisor.switch_eval_max_candidates", fallback=5))


def capture_switch_evaluations(rec, signals, shelf_ideas, sector_weights,
                               held_symbols, candidate_closes, user_id, on):
    """Evaluation rows for one holding against the shelf. Pure — prices come
    in via `candidate_closes`, nothing is fetched here.

    A candidate with no price is dropped rather than guessed: a fabricated
    entry price would silently corrupt every excess computed from it.
    """
    if not _switch_eval_enabled():
        return []
    from backend.shared.schemas.portfolio import SwitchEvaluation
    from core.portfolio.advisor import evaluate_switch_candidates
    _best, rows = evaluate_switch_candidates(
        signals, shelf_ideas, sector_weights, held_symbols,
        _switch_eval_max_candidates())
    out = []
    for r in rows:
        close = candidate_closes.get(r["candidate"])
        if close is None:
            continue
        out.append(SwitchEvaluation(
            date=on.isoformat(), user_id=user_id,
            origin=signals.symbol, origin_close=signals.close,
            origin_sector=signals.sector, origin_confidence=signals.confidence,
            origin_verdict=rec.verdict, candidate=r["candidate"],
            candidate_close=float(close),
            candidate_sector=r["candidate_sector"],
            candidate_conviction=r["candidate_conviction"],
            decision=r["decision"], reason=r["reason"],
            rationale_hash=rec.rationale_hash))
    return out
```

Then wire it into the Step 3 loop. Immediately **before** `for holding in ...`, build the price map once:

```python
        # One price per candidate per run — candidates repeat across holdings,
        # so this must not be inside the holding loop.
        candidate_closes: dict[str, float] = {}
        if _switch_eval_enabled():
            for idea in shelf_ideas:
                try:
                    candidate_closes[idea.symbol] = close_on(idea.symbol, review_date)
                except Exception as exc:
                    logger.debug("[portfolio_pipeline] no close for candidate %s "
                                 "(non-fatal): %s", idea.symbol, exc)
        switch_evals: list = []
```

and immediately **after** `rec.narrative = narrate(rec, signals)`:

```python
                try:
                    switch_evals.extend(capture_switch_evaluations(
                        rec, signals, shelf_ideas, sector_weights,
                        {h.symbol for h in portfolio.holdings},
                        candidate_closes, user_id, review_date))
                except Exception as exc:
                    logger.warning("[portfolio_pipeline] switch capture failed "
                                   "for %s (non-fatal): %s", holding.symbol, exc)
```

and after the holding loop closes, before Step 3.5:

```python
        try:
            store.append_switch_evaluations(switch_evals)
        except Exception as exc:
            logger.warning("[portfolio_pipeline] switch-eval write failed "
                           "(non-fatal): %s", exc)
```

Add to `config.yaml` under `advisor:`:

```yaml
  # Switch-validation capture (design 2026-08-20). Records every (holding,
  # shelf-candidate) pair the rule evaluates, taken or not, so the auditor has
  # a sample. Read-only telemetry — never changes a verdict.
  switch_eval_enabled: true
  switch_eval_max_candidates: 5     # top-N active ideas by conviction, per holding
```

Add both rows to the config table in `CODEBASE.md`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_portfolio_pipeline.py tests/unit/test_autopilot_pipeline.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add core/portfolio/pipeline.py config.yaml CODEBASE.md tests/unit/test_portfolio_pipeline.py
git commit -m "feat(pipeline): capture every switch pair the advisor evaluates"
```

---

### Task 5: `grade_switch_lane`

**Files:**
- Modify: `core/audit/outcomes.py` (new lane + `grade_due` registration at `:330`, `_LANE_KWARGS` at the file end)
- Modify: `config.yaml` (`audit:` block)
- Modify: `CODEBASE.md` (config table)
- Test: `tests/unit/audit/test_audit_switch_lane.py` (create)

**Interfaces:**
- Consumes: `is_switch_correct` (Task 1), `SwitchEvaluation` + `load_switch_evaluations` (Task 2).
- Produces: `grade_switch_lane(on, user_id, *, store=None, bench=None, price_fn=None, base_dir=None) -> dict` with keys `graded`, `skipped_unpriceable`, `already_present`. Row `ref` format: `f"switch:{date}|{origin}|{candidate}"`.

**Config added here:**

| Key | Default |
|---|---|
| `audit.switch_lane_enabled` | `true` |
| `audit.switch_grade_max_rows_per_run` | `2000` |

- [ ] **Step 1: Write the failing test**

Create `tests/unit/audit/test_audit_switch_lane.py`:

```python
"""Switch lane — grade the pair, idempotently, never fatally."""
from datetime import date

from backend.shared.schemas.portfolio import SwitchEvaluation
from core.audit.outcomes import grade_switch_lane
from core.audit.store import AuditOutcomeStore
from core.portfolio.store import PortfolioStore


class _Bench:
    def pct_change(self, a, b):
        return 0.0

    def close_on(self, d):
        return 1000.0


def _prices(mapping):
    def _fn(symbol, on):
        if symbol not in mapping:
            raise ValueError(f"no price for {symbol}")
        return mapping[symbol][0] if on <= date(2026, 8, 20) else mapping[symbol][1]
    return _fn


def _seed(tmp_path, **kw):
    store = PortfolioStore(user_id="u1", base_dir=str(tmp_path))
    fields = dict(date="2026-08-20", user_id="u1", origin="OLD",
                  origin_close=100.0, candidate="NEW", candidate_close=200.0,
                  decision="rejected", reason="not_best")
    fields.update(kw)
    store.append_switch_evaluations([SwitchEvaluation(**fields)])
    return store


def test_a_rejected_pair_whose_candidate_won_grades_correct(tmp_path):
    _seed(tmp_path)
    out = grade_switch_lane(
        date(2027, 1, 1), "u1", bench=_Bench(), base_dir=str(tmp_path),
        price_fn=_prices({"OLD": (100.0, 98.0), "NEW": (200.0, 260.0)}))
    assert out["graded"] == 3          # one row per horizon
    rows = [r for r in AuditOutcomeStore(user_id="u1", base_dir=str(tmp_path)).load_all()
            if r.lane == "switch"]
    r = rows[0]
    assert r.symbol == "OLD" and r.candidate == "NEW"
    assert r.excess_pct == -2.0 and r.switch_excess_pct == 30.0
    assert r.correct is True           # declining to rotate was WRONG
    assert r.verdict == ""
    assert r.triggers == ["rejected", "not_best"]


def test_a_taken_pair_whose_destination_lost_grades_incorrect(tmp_path):
    _seed(tmp_path, decision="taken", reason="")
    grade_switch_lane(
        date(2027, 1, 1), "u1", bench=_Bench(), base_dir=str(tmp_path),
        price_fn=_prices({"OLD": (100.0, 98.0), "NEW": (200.0, 160.0)}))
    rows = [r for r in AuditOutcomeStore(user_id="u1", base_dir=str(tmp_path)).load_all()
            if r.lane == "switch"]
    assert rows[0].correct is False
    assert rows[0].triggers == ["taken", ""]


def test_regrading_is_idempotent(tmp_path):
    _seed(tmp_path)
    kw = dict(bench=_Bench(), base_dir=str(tmp_path),
              price_fn=_prices({"OLD": (100.0, 98.0), "NEW": (200.0, 260.0)}))
    first = grade_switch_lane(date(2027, 1, 1), "u1", **kw)
    second = grade_switch_lane(date(2027, 1, 1), "u1", **kw)
    assert first["graded"] == 3 and second["graded"] == 0
    assert second["already_present"] == 3


def test_an_unpriceable_leg_is_skipped_never_guessed(tmp_path):
    _seed(tmp_path)
    out = grade_switch_lane(
        date(2027, 1, 1), "u1", bench=_Bench(), base_dir=str(tmp_path),
        price_fn=_prices({"OLD": (100.0, 98.0)}))     # NEW has no price
    assert out["graded"] == 0 and out["skipped_unpriceable"] == 3


def test_immature_rows_are_left_alone(tmp_path):
    _seed(tmp_path)
    out = grade_switch_lane(
        date(2026, 8, 21), "u1", bench=_Bench(), base_dir=str(tmp_path),
        price_fn=_prices({"OLD": (100.0, 98.0), "NEW": (200.0, 260.0)}))
    assert out["graded"] == 0


def test_the_lane_is_registered_with_grade_due():
    from core.audit.outcomes import _LANE_KWARGS
    assert "switch" in _LANE_KWARGS
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/audit/test_audit_switch_lane.py -q`
Expected: FAIL — `ImportError: cannot import name 'grade_switch_lane'`.

- [ ] **Step 3: Write minimal implementation**

Add to `core/audit/outcomes.py`, after `grade_shelf_lane`:

```python
def _switch_lane_enabled() -> bool:
    return bool(cfg("audit.switch_lane_enabled", fallback=True))


def grade_switch_lane(
    on: date, user_id: str, *, store=None, bench=None,
    price_fn: Callable[[str, date], float] | None = None,
    base_dir: str | None = None,
) -> dict:
    """Grade every matured (origin, candidate) pair the advisor evaluated.

    `correct` here answers a different question from every other lane — did
    rotating beat staying — so it comes from is_switch_correct, not is_correct.
    Both legs must price or the row is skipped: a pair graded on one leg is not
    a pair.
    """
    from core.audit.benchmark import BenchmarkSeries
    from core.audit.rules import is_switch_correct
    from core.audit.store import AuditOutcomeStore
    from core.portfolio.store import PortfolioStore

    summary = {"graded": 0, "skipped_unpriceable": 0, "already_present": 0}
    if not _switch_lane_enabled():
        return summary

    store = store or AuditOutcomeStore(user_id=user_id, base_dir=base_dir)
    bench = bench or BenchmarkSeries()
    price_fn = price_fn or _default_price_fn
    max_rows = int(cfg("audit.switch_grade_max_rows_per_run", fallback=2000))

    evals = PortfolioStore(user_id=user_id, base_dir=base_dir).load_switch_evaluations()
    seen = store.existing_keys()

    for row in evals:
        if summary["graded"] >= max_rows:
            logger.info("[audit] switch lane hit the per-run cap (%d)", max_rows)
            break
        try:
            issued = date.fromisoformat(row.date)
        except Exception:
            summary["skipped_unpriceable"] += 1
            continue
        ref = f"switch:{row.date}|{row.origin}|{row.candidate}"
        for horizon in _horizons():
            if (ref, horizon) in seen:
                summary["already_present"] += 1
                continue
            matured = trading_days_after(issued, horizon)
            if matured > on:
                continue
            try:
                bench_pct = bench.pct_change(issued, matured)
                origin_exit = float(price_fn(row.origin, matured))
                dest_exit = float(price_fn(row.candidate, matured))
                origin_excess = excess(pct_change(row.origin_close, origin_exit), bench_pct)
                dest_excess = excess(pct_change(row.candidate_close, dest_exit), bench_pct)
                outcome = AuditOutcome(
                    ref=ref, lane="switch", user_id=user_id, symbol=row.origin,
                    verdict="", triggers=[row.decision, row.reason],
                    issued_on=row.date, horizon_td=horizon,
                    graded_on=matured.isoformat(),
                    entry_close=row.origin_close, exit_close=origin_exit,
                    return_pct=pct_change(row.origin_close, origin_exit),
                    bench_entry=bench.close_on(issued),
                    bench_exit=bench.close_on(matured),
                    bench_pct=bench_pct, excess_pct=origin_excess,
                    correct=is_switch_correct(origin_excess, dest_excess),
                    graded_at=datetime.now(timezone.utc).isoformat(),
                    switch_excess_pct=dest_excess, candidate=row.candidate)
            except Exception as exc:
                logger.debug("[audit] switch %s->%s @%dtd ungradeable (non-fatal): %s",
                             row.origin, row.candidate, horizon, exc)
                summary["skipped_unpriceable"] += 1
                continue
            store.append(outcome)
            seen.add((ref, horizon))
            summary["graded"] += 1
    return summary
```

Register it in `grade_due` — add `("switch", grade_switch_lane)` to the tuple — and extend `_LANE_KWARGS`:

```python
_LANE_KWARGS = {"advice": set(), "alert": {"sent_log"}, "shelf": {"shelf_path"},
                "switch": set()}
```

Add to `config.yaml` under `audit:`:

```yaml
  switch_lane_enabled: true          # grade the evaluated switch pairs
  switch_grade_max_rows_per_run: 2000  # bounds the first backfill after deploy
```

Add both rows to the `CODEBASE.md` config table.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/audit/ -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add core/audit/outcomes.py config.yaml CODEBASE.md tests/unit/audit/test_audit_switch_lane.py
git commit -m "feat(audit): add the switch lane — grade the pair over the same window"
```

---

### Task 6: Pair metrics and the non-overlap stride

**Files:**
- Modify: `core/audit/metrics.py`
- Test: `tests/unit/audit/test_audit_metrics.py`

**Interfaces:**
- Consumes: `AuditOutcome` rows with `lane="switch"`.
- Produces: `stride_subsample(rows: Iterable[AuditOutcome], horizon: int) -> list[AuditOutcome]`; `mean_edge(rows: Iterable[AuditOutcome], horizon: int | None = None) -> float | None`.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/audit/test_audit_metrics.py`:

```python
# -- switch pair metrics + overlap control (2026-08-20) --------------------

from core.audit.metrics import mean_edge, stride_subsample


def _switch_row(issued, origin="OLD", candidate="NEW", horizon=10,
                origin_excess=-2.0, dest_excess=3.0):
    from backend.shared.schemas.audit import AuditOutcome
    return AuditOutcome(
        ref=f"switch:{issued}|{origin}|{candidate}", lane="switch", user_id="u",
        symbol=origin, candidate=candidate, issued_on=issued,
        horizon_td=horizon, graded_on=issued, entry_close=100.0,
        exit_close=98.0, return_pct=-2.0, bench_entry=1.0, bench_exit=1.0,
        bench_pct=0.0, excess_pct=origin_excess,
        switch_excess_pct=dest_excess, correct=dest_excess > origin_excess,
        graded_at="2026-09-01T00:00:00+00:00")


def test_mean_edge_is_destination_minus_origin():
    rows = [_switch_row("2026-08-03", origin_excess=-2.0, dest_excess=3.0),
            _switch_row("2026-08-04", origin_excess=1.0, dest_excess=2.0)]
    assert mean_edge(rows, horizon=10) == 3.0   # (5.0 + 1.0) / 2


def test_mean_edge_ignores_rows_with_no_destination():
    rows = [_switch_row("2026-08-03", origin_excess=-2.0, dest_excess=3.0)]
    rows.append(rows[0].model_copy(update={"switch_excess_pct": None}))
    assert mean_edge(rows, horizon=10) == 5.0


def test_stride_keeps_one_row_per_pair_per_horizon_window():
    """Ten consecutive daily evaluations of ONE pair share almost the whole
    10td window. Counting them as ten independent observations is the specific
    dishonesty this function exists to prevent."""
    rows = [_switch_row(f"2026-08-{d:02d}") for d in range(3, 13)]
    kept = stride_subsample(rows, horizon=10)
    assert len(kept) == 1
    assert kept[0].issued_on == "2026-08-03"     # earliest wins


def test_stride_keeps_distinct_pairs_separately():
    rows = [_switch_row("2026-08-03", candidate="A"),
            _switch_row("2026-08-03", candidate="B")]
    assert len(stride_subsample(rows, horizon=10)) == 2


def test_stride_admits_the_next_row_once_the_window_has_passed():
    rows = [_switch_row("2026-08-03"), _switch_row("2026-08-28")]
    assert len(stride_subsample(rows, horizon=10)) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/audit/test_audit_metrics.py -q`
Expected: FAIL — `ImportError: cannot import name 'mean_edge'`.

- [ ] **Step 3: Write minimal implementation**

Append to `core/audit/metrics.py`:

```python
def mean_edge(
    rows: Iterable[AuditOutcome], horizon: int | None = None
) -> float | None:
    """Mean (destination excess − origin excess) in percentage points.

    Rows without a destination excess are excluded, not treated as zero: an
    unpriceable candidate is an absent measurement, and calling it "no edge"
    would drag the mean toward zero with data that does not exist.
    """
    vals = [r.switch_excess_pct - r.excess_pct for r in rows
            if r.switch_excess_pct is not None
            and (horizon is None or r.horizon_td == horizon)]
    if not vals:
        return None
    return round(sum(vals) / len(vals), 4)


def stride_subsample(
    rows: Iterable[AuditOutcome], horizon: int
) -> list[AuditOutcome]:
    """One row per (origin, candidate) per non-overlapping `horizon` window.

    Daily capture means the same pair recurs with windows that share nearly
    every trading day. Those are not independent observations, and a Wilson
    interval over them would claim a precision the data does not have. Keeps
    the EARLIEST row in each window — the first time the rule reached that
    judgement, before any subsequent day could revise it.

    The stride is measured in CALENDAR days (horizon trading days span more
    calendar days, so this is deliberately conservative — it discards more
    than strictly necessary rather than admitting overlapping pairs).
    """
    from datetime import date as _date
    picked: list[AuditOutcome] = []
    last_kept: dict[tuple[str, str], _date] = {}
    for r in sorted((x for x in rows if x.horizon_td == horizon),
                    key=lambda x: x.issued_on):
        key = (r.symbol, r.candidate)
        try:
            issued = _date.fromisoformat(r.issued_on)
        except Exception:
            continue
        prev = last_kept.get(key)
        if prev is None or (issued - prev).days >= horizon:
            picked.append(r)
            last_kept[key] = issued
    return picked
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/audit/ -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add core/audit/metrics.py tests/unit/audit/test_audit_metrics.py
git commit -m "feat(audit): pair edge + a non-overlapping stride for switch rows"
```

---

### Task 7: Persist per-symbol news availability

**Files:**
- Create: `core/audit/evidence.py`
- Modify: `core/intelligence/rl/workflows/daily_review.py` (near the summary assembly at `:1464`)
- Test: `tests/unit/audit/test_audit_evidence.py` (create)

**Interfaces:**
- Consumes: nothing.
- Produces: `record_news_availability(symbol: str, on: date, news_available: bool, macro_fallback_used: bool, path: str | None = None) -> None`; `news_availability_index(path: str | None = None) -> dict[tuple[str, str], bool]` keyed `(symbol, iso_date)`.

Storage: `data/rl/news_availability.jsonl`, append-only.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/audit/test_audit_evidence.py`:

```python
"""Gap D — whether a call was made blind must be recoverable afterwards."""
from datetime import date

from core.audit.evidence import news_availability_index, record_news_availability


def test_recorded_availability_is_readable_by_symbol_and_date(tmp_path):
    p = str(tmp_path / "news.jsonl")
    record_news_availability("MARUTI", date(2026, 8, 20), True, False, path=p)
    record_news_availability("SUZLON", date(2026, 8, 20), False, True, path=p)
    idx = news_availability_index(path=p)
    assert idx[("MARUTI", "2026-08-20")] is True
    assert idx[("SUZLON", "2026-08-20")] is False


def test_a_later_record_wins_for_the_same_symbol_and_day(tmp_path):
    """Append-only storage plus a re-run must not leave the index ambiguous."""
    p = str(tmp_path / "news.jsonl")
    record_news_availability("MARUTI", date(2026, 8, 20), False, False, path=p)
    record_news_availability("MARUTI", date(2026, 8, 20), True, False, path=p)
    assert news_availability_index(path=p)[("MARUTI", "2026-08-20")] is True


def test_a_missing_file_is_an_empty_index_not_an_error(tmp_path):
    assert news_availability_index(path=str(tmp_path / "absent.jsonl")) == {}


def test_recording_never_raises_on_an_unwritable_path(tmp_path):
    bad = str(tmp_path / "no_such_dir" / "x" / "news.jsonl")
    record_news_availability("X", date(2026, 8, 20), True, False, path=bad)


def test_a_corrupt_line_does_not_break_the_index(tmp_path):
    p = tmp_path / "news.jsonl"
    record_news_availability("MARUTI", date(2026, 8, 20), True, False, path=str(p))
    with open(p, "a", encoding="utf-8") as fh:
        fh.write("{broken\n")
    assert len(news_availability_index(path=str(p))) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/audit/test_audit_evidence.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.audit.evidence'`.

- [ ] **Step 3: Write minimal implementation**

Create `core/audit/evidence.py`:

```python
"""Per-call evidence the miss taxonomy needs, captured when it is knowable.

`news_available` is computed on every daily review and was only ever
aggregated into one scheduler log line, so "was this call made blind?" could
not be answered afterwards — which made every miss attributable to the model's
reasoning by default, including the ones where it simply had no news.

Append-only; the index takes the LAST record for a (symbol, date), so a
re-run corrects rather than duplicates. Never raises: this is telemetry about
telemetry and must not be able to fail a review.
"""
from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_PATH = Path("data") / "rl" / "news_availability.jsonl"


def _path(path: str | None) -> Path:
    return Path(path) if path else _DEFAULT_PATH


def record_news_availability(symbol: str, on: date, news_available: bool,
                             macro_fallback_used: bool = False,
                             path: str | None = None) -> None:
    """Append one availability record. Never raises."""
    try:
        p = _path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "date": on.isoformat(), "symbol": symbol,
                "news_available": bool(news_available),
                "macro_fallback_used": bool(macro_fallback_used),
            }) + "\n")
    except Exception as exc:
        logger.warning("[audit] news-availability write failed (non-fatal): %s", exc)


def news_availability_index(path: str | None = None) -> dict:
    """{(symbol, iso_date): news_available}. {} when absent. Never raises."""
    out: dict = {}
    try:
        p = _path(path)
        if not p.exists():
            return out
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                out[(rec["symbol"], rec["date"])] = bool(rec["news_available"])
            except Exception:
                continue
    except Exception as exc:
        logger.warning("[audit] news-availability read failed (non-fatal): %s", exc)
    return out
```

In `core/intelligence/rl/workflows/daily_review.py`, immediately before the
`return` that builds the summary containing `"news_available": news_available`
(`:1464`), add:

```python
    try:
        from core.audit.evidence import record_news_availability
        record_news_availability(ticker, review_date, news_available,
                                 bool(locals().get("macro_fallback_used", False)))
    except Exception as exc:
        logger.debug("[daily_review] news-availability record failed "
                     "(non-fatal): %s", exc)
```

> **Implementer:** confirm the actual local variable names for the ticker and
> the review date in that scope before pasting — this function is long and the
> names differ from the parameter names in places. Do not guess; read it.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/audit/test_audit_evidence.py tests/unit/intelligence/rl/ -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add core/audit/evidence.py core/intelligence/rl/workflows/daily_review.py tests/unit/audit/test_audit_evidence.py
git commit -m "feat(audit): persist per-symbol news availability so misses can be attributed"
```

---

### Task 8: The miss taxonomy

**Files:**
- Create: `core/audit/attribution.py`
- Modify: `config.yaml` (`audit:` block), `CODEBASE.md`
- Test: `tests/unit/audit/test_audit_attribution.py` (create)

**Interfaces:**
- Consumes: `news_availability_index` (Task 7), switch rows (Task 5).
- Produces: `classify_miss(row: AuditOutcome, *, news_index: dict, shock_reasons: set[str], had_shock: bool = False, atr_breach: bool = False) -> str` returning one of `unpredictable`, `technical`, `knowledge`, `research`, `unknown_evidence`; `attribution_distribution(rows, news_index, ...) -> dict[str, int]`.

**Config added here:** `audit.shock_atr_mult` (default `3.0`).

- [ ] **Step 1: Write the failing test**

Create `tests/unit/audit/test_audit_attribution.py`:

```python
"""Miss taxonomy — ordering is the whole design, so it is tested first."""
from core.audit.attribution import attribution_distribution, classify_miss


def _miss(symbol="OLD", issued="2026-08-20", origin_excess=-2.0, dest_excess=-9.0):
    from backend.shared.schemas.audit import AuditOutcome
    return AuditOutcome(
        ref="switch:x", lane="switch", user_id="u", symbol=symbol,
        candidate="NEW", issued_on=issued, horizon_td=10, graded_on=issued,
        entry_close=100.0, exit_close=98.0, return_pct=-2.0, bench_entry=1.0,
        bench_exit=1.0, bench_pct=0.0, excess_pct=origin_excess,
        switch_excess_pct=dest_excess, correct=False,
        graded_at="2026-09-01T00:00:00+00:00")


NEWS_SEEN = {("OLD", "2026-08-20"): True}
NEWS_BLIND = {("OLD", "2026-08-20"): False}


def test_a_shock_classifies_unpredictable():
    assert classify_miss(_miss(), news_index=NEWS_SEEN, had_shock=True) == "unpredictable"


def test_a_shock_on_a_blind_day_is_still_unpredictable():
    """Ordering: a genuine shock must never be recorded as a plumbing failure,
    or the fix list fills with work that would not have helped."""
    assert classify_miss(_miss(), news_index=NEWS_BLIND, had_shock=True) == "unpredictable"


def test_an_atr_breach_alone_classifies_unpredictable():
    assert classify_miss(_miss(), news_index=NEWS_SEEN, atr_breach=True) == "unpredictable"


def test_news_blind_without_a_shock_classifies_technical():
    assert classify_miss(_miss(), news_index=NEWS_BLIND) == "technical"


def test_news_seen_and_still_wrong_classifies_knowledge():
    assert classify_miss(_miss(), news_index=NEWS_SEEN) == "knowledge"


def test_no_news_record_classifies_unknown_evidence():
    """Rows issued before Task 7 shipped must not be silently blamed on the
    model — they are outside the denominator, not inside it as a knowledge gap."""
    assert classify_miss(_miss(), news_index={}) == "unknown_evidence"


def test_a_correct_row_is_never_classified():
    row = _miss(dest_excess=9.0).model_copy(update={"correct": True})
    assert classify_miss(row, news_index=NEWS_SEEN) == ""


def test_distribution_excludes_unknown_evidence_from_the_denominator():
    rows = [_miss(), _miss(), _miss(symbol="NOREC")]
    dist = attribution_distribution(rows, news_index=NEWS_SEEN)
    assert dist["knowledge"] == 2
    assert dist["unknown_evidence"] == 1
    assert dist["n_classified"] == 2      # the denominator for any percentage
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/audit/test_audit_attribution.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.audit.attribution'`.

- [ ] **Step 3: Write minimal implementation**

Create `core/audit/attribution.py`:

```python
"""Why a switch decision was wrong — as a distribution, never as a per-call verdict.

Order is the design. `unpredictable` is tested first so a genuine shock is
never filed as a knowledge gap; `technical` before `knowledge` so a call made
blind is never blamed on the model's reasoning. Getting this order wrong does
not produce an error — it produces a plausible, confident, wrong fix list.

A row with no evidence on file is `unknown_evidence` and sits OUTSIDE the
denominator. Guessing would make the pre-instrumentation backlog look like a
model problem.
"""
from __future__ import annotations

SHOCK_REASONS = frozenset({"external_shock", "preopen_shock"})

BUCKETS = ("unpredictable", "technical", "knowledge", "research", "unknown_evidence")


def classify_miss(row, *, news_index: dict, had_shock: bool = False,
                  atr_breach: bool = False, below_chance: bool = False) -> str:
    """One bucket for one wrong decision; "" when the row was not a miss."""
    if row.correct is not False:
        return ""
    if had_shock or atr_breach:
        return "unpredictable"
    seen = news_index.get((row.symbol, row.issued_on))
    if seen is None:
        return "unknown_evidence"
    if seen is False:
        return "technical"
    if below_chance:
        return "research"
    return "knowledge"


def attribution_distribution(rows, *, news_index: dict,
                             shocked_refs: set | None = None,
                             below_chance_reasons: set | None = None) -> dict:
    """Counts per bucket plus `n_classified` — the denominator any percentage
    must use, which deliberately excludes `unknown_evidence`."""
    shocked_refs = shocked_refs or set()
    below_chance_reasons = below_chance_reasons or set()
    out = {b: 0 for b in BUCKETS}
    for row in rows:
        reason = row.triggers[1] if len(row.triggers) > 1 else ""
        bucket = classify_miss(
            row, news_index=news_index,
            had_shock=row.ref in shocked_refs,
            below_chance=reason in below_chance_reasons)
        if bucket:
            out[bucket] += 1
    out["n_classified"] = sum(out[b] for b in BUCKETS if b != "unknown_evidence")
    return out
```

Add to `config.yaml` under `audit:`:

```yaml
  shock_atr_mult: 3.0        # single-session move counting as an unforeseeable shock
```

Add the row to the `CODEBASE.md` config table.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/audit/ -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add core/audit/attribution.py config.yaml CODEBASE.md tests/unit/audit/test_audit_attribution.py
git commit -m "feat(audit): classify switch misses into shock / technical / knowledge / research"
```

---

### Task 9: The report block, and the horizon bug that empties two existing blocks

**Files:**
- Modify: `core/audit/report.py:59`, `:71`, and `build_report`'s return
- Modify: `config.yaml` (`audit:` block), `CODEBASE.md`
- Test: `tests/unit/audit/test_audit_report.py`

**Interfaces:**
- Consumes: Tasks 1, 5, 6, 8.
- Produces: `build_report(...)["switch_rule"]` and `["switch_taken"]`, each `{n, n_effective, hit_rate, mean_edge, per_reason, verdict}`; `["attribution"]` from `attribution_distribution`.

**Config added here:**

| Key | Default |
|---|---|
| `audit.switch_min_n` | `30` |
| `audit.per_trigger_horizon_td` | `10` |
| `audit.conviction_horizon_td` | `10` |

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/audit/test_audit_report.py`:

```python
# -- switch blocks + the horizon fix (2026-08-20) --------------------------

def _sw(issued, horizon=10, origin_excess=-2.0, dest_excess=3.0, decision="rejected"):
    from backend.shared.schemas.audit import AuditOutcome
    return AuditOutcome(
        ref=f"switch:{issued}|OLD|NEW", lane="switch", user_id="u", symbol="OLD",
        candidate="NEW", triggers=[decision, "not_best"], issued_on=issued,
        horizon_td=horizon, graded_on=issued, entry_close=100.0, exit_close=98.0,
        return_pct=-2.0, bench_entry=1.0, bench_exit=1.0, bench_pct=0.0,
        excess_pct=origin_excess, switch_excess_pct=dest_excess,
        correct=dest_excess > origin_excess,
        graded_at="2026-09-01T00:00:00+00:00")


class _Store:
    user_id = "u"

    def __init__(self, rows):
        self._rows = rows

    def load_all(self):
        return self._rows


def test_switch_rule_block_reports_raw_n_and_effective_n_separately():
    rows = [_sw(f"2026-08-{d:02d}") for d in range(3, 13)]   # one pair, 10 days
    block = build_report(store=_Store(rows))["switch_rule"]
    assert block["n"] == 10
    assert block["n_effective"] == 1


def test_a_large_raw_n_of_overlapping_rows_still_reads_insufficient_data():
    """The specific dishonesty this design exists to prevent: 200 overlapping
    observations of one pair are not 200 observations."""
    rows = [_sw(f"2026-{m:02d}-{d:02d}")
            for m in (3, 4, 5, 6) for d in range(1, 29)]
    block = build_report(store=_Store(rows))["switch_rule"]
    assert block["n"] > 100
    assert block["verdict"] == "INSUFFICIENT_DATA"


def test_taken_and_rejected_pairs_are_reported_separately():
    rows = [_sw("2026-03-02", decision="taken"),
            _sw("2026-04-02", decision="rejected")]
    report = build_report(store=_Store(rows))
    assert report["switch_taken"]["n"] == 1
    assert report["switch_rule"]["n"] == 2


def test_per_trigger_uses_only_switch_lane_rows_in_the_switch_block():
    """per_trigger_precision filters on `correct is not None` and nothing else,
    so handing it the whole store blends advisor trigger codes with switch
    reason codes and reports a meaningless mixture."""
    from backend.shared.schemas.audit import AuditOutcome
    advice = AuditOutcome(
        ref="a", lane="advice", user_id="u", symbol="X", verdict="EXIT",
        triggers=["stop_breach"], issued_on="2026-03-02", horizon_td=10,
        graded_on="2026-03-16", entry_close=1.0, exit_close=1.0,
        return_pct=0.0, bench_entry=1.0, bench_exit=1.0, bench_pct=0.0,
        excess_pct=-1.0, correct=True, graded_at="2026-03-16T00:00:00+00:00")
    block = build_report(store=_Store([_sw("2026-03-02"), advice]))["switch_rule"]
    assert "stop_breach" not in block["per_reason"]


def test_per_trigger_horizon_is_configurable(monkeypatch):
    import core.audit.report as rp
    monkeypatch.setattr(rp, "_cfg_int", lambda key, default: 10)
    from backend.shared.schemas.audit import AuditOutcome
    row = AuditOutcome(
        ref="a", lane="advice", user_id="u", symbol="X", verdict="EXIT",
        triggers=["stop_breach"], issued_on="2026-03-02", horizon_td=10,
        graded_on="2026-03-16", entry_close=1.0, exit_close=1.0,
        return_pct=0.0, bench_entry=1.0, bench_exit=1.0, bench_pct=0.0,
        excess_pct=-1.0, correct=True, graded_at="2026-03-16T00:00:00+00:00")
    assert "stop_breach" in build_report(store=_Store([row]))["per_trigger"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/audit/test_audit_report.py -q`
Expected: FAIL — `KeyError: 'switch_rule'`, and the per-trigger test fails because the horizon is hardcoded to 60.

- [ ] **Step 3: Write minimal implementation**

In `core/audit/report.py`, add near the top:

```python
def _cfg_int(key: str, default: int) -> int:
    """Indirection so tests patch one function, not the loader."""
    try:
        return int(cfg(key, fallback=default))
    except Exception:
        return default


def _switch_block(rows: list, horizon: int, min_n: int,
                  decision: str | None = None) -> dict:
    """One switch block. `decision` filters to taken-only when given."""
    from core.audit.metrics import (hit_rate, mean_edge, per_trigger_precision,
                                    stride_subsample)
    lane = [r for r in rows if r.lane == "switch"
            and (decision is None
                 or (r.triggers and r.triggers[0] == decision))]
    strided = stride_subsample(lane, horizon)
    rate = hit_rate(strided, horizon=horizon)
    p = coin_flip_p(strided, horizon=horizon)
    edge = mean_edge(strided, horizon=horizon)
    return {
        "n": len([r for r in lane if r.horizon_td == horizon]),
        "n_effective": rate.n,
        "hit_rate": _rate_dict(rate),
        "mean_edge_pct": edge,
        "coin_flip_p": p,
        # Switch-lane rows ONLY: per_trigger_precision filters on
        # `correct is not None` and nothing else, so the whole store would
        # blend advisor trigger codes with switch reason codes.
        "per_reason": {t: _rate_dict(r)
                       for t, r in per_trigger_precision(strided, horizon=horizon).items()},
        "verdict": classify(rate, p, edge, min_n),
    }
```

Replace the two hardcoded horizons:

```python
    buckets = conviction_calibration(rows, horizon=_cfg_int("audit.conviction_horizon_td", 10))
```

```python
        "per_trigger": {t: _rate_dict(r) for t, r in per_trigger_precision(
            rows, horizon=_cfg_int("audit.per_trigger_horizon_td", 10)).items()},
```

and add to the returned dict:

```python
        "switch_rule": _switch_block(rows, 10, _cfg_int("audit.switch_min_n", 30)),
        "switch_taken": _switch_block(rows, 10, _cfg_int("audit.switch_min_n", 30),
                                      decision="taken"),
        "attribution": attribution_distribution(
            [r for r in rows if r.lane == "switch"],
            news_index=news_availability_index()),
```

with imports at the top of the function body:

```python
    from core.audit.attribution import attribution_distribution
    from core.audit.evidence import news_availability_index
```

Add to `config.yaml` under `audit:`:

```yaml
  switch_min_n: 30                # n_effective floor before any switch verdict
  per_trigger_horizon_td: 10      # was hardcoded to 60 -> the block read empty
  conviction_horizon_td: 10       # was hardcoded to 30 -> the block read empty
```

Add all three rows to the `CODEBASE.md` config table.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/audit/ -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add core/audit/report.py config.yaml CODEBASE.md tests/unit/audit/test_audit_report.py
git commit -m "feat(audit): report the switch rule on a strided sample, and unempty per_trigger"
```

---

### Task 10: The watchdog tells you when it can first speak

**Files:**
- Modify: `core/ops/watchdog/checks.py` (new `@check`)
- Modify: `config/milestones.yaml` (new invariant)
- Modify: `CODEBASE.md`
- Test: `tests/unit/ops/test_watchdog_checks.py`

**Interfaces:**
- Consumes: `build_report` (Task 9).
- Produces: a check registered as `switch_lane_has_sample`.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/ops/test_watchdog_checks.py`:

```python
# -- switch lane sample gate (2026-08-20) ----------------------------------

def test_switch_sample_check_is_pending_below_the_floor(monkeypatch):
    import core.ops.watchdog.checks as C
    monkeypatch.setattr(C, "_switch_report", lambda: {
        "switch_rule": {"n": 400, "n_effective": 4, "verdict": "INSUFFICIENT_DATA"},
        "min_n": 30})
    r = C.run_check("switch_lane_has_sample")
    assert r.state == "pending"
    assert "4" in r.detail


def test_switch_sample_check_is_satisfied_once_it_clears(monkeypatch):
    import core.ops.watchdog.checks as C
    monkeypatch.setattr(C, "_switch_report", lambda: {
        "switch_rule": {"n": 400, "n_effective": 31, "verdict": "UNPROVEN"},
        "min_n": 30})
    assert C.run_check("switch_lane_has_sample").state == "satisfied"


def test_switch_sample_check_is_unknown_when_the_report_fails(monkeypatch):
    """A watchdog that reports "fine" when it cannot see is worse than none."""
    import core.ops.watchdog.checks as C
    monkeypatch.setattr(C, "_switch_report",
                        lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    assert C.run_check("switch_lane_has_sample").state == "unknown"


def test_the_milestone_entry_is_monthly():
    """A windowless pending invariant warns EVERY DAY (engine.py's
    `window_open = True` branch). Over the months this sample takes to accrue
    that trains the reader to ignore watchdog mail."""
    from core.ops.watchdog.registry import load_registry
    entry = next(e for e in load_registry("config/milestones.yaml")
                 if e.id == "switch_lane_has_sample")
    assert entry.schedule == "monthly"
    assert entry.check == "switch_lane_has_sample"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/ops/test_watchdog_checks.py -q`
Expected: FAIL — check not registered; `StopIteration` on the registry lookup.

- [ ] **Step 3: Write minimal implementation**

In `core/ops/watchdog/checks.py`:

```python
def _switch_report() -> dict:
    """Seam for tests — the real graded-outcome report."""
    from core.audit.report import build_report
    return build_report()


@check("switch_lane_has_sample")
def switch_lane_has_sample() -> CheckResult:
    """Satisfied once the switch lane has enough NON-OVERLAPPING rows to say
    anything. Until then the question "do switch ideas work out?" has no
    answer, and this reports how far off it is rather than going quiet.

    Reads n_effective, never raw n: daily capture of the same pair produces
    many rows and almost no additional information.
    """
    report = _switch_report()
    block = report.get("switch_rule") or {}
    floor = int(report.get("min_n") or 30)
    n_eff = int(block.get("n_effective") or 0)
    evidence = {"n_effective": n_eff, "n_raw": block.get("n"), "floor": floor}
    if n_eff >= floor:
        return CheckResult(
            "satisfied",
            f"Switch lane has {n_eff} independent pairs (floor {floor}) — "
            f"verdict {block.get('verdict')}.", evidence)
    return CheckResult(
        "pending",
        f"Switch lane has {n_eff} independent pair(s) of {floor} needed "
        f"({block.get('n')} raw rows). Still accruing.", evidence)
```

Add to `config/milestones.yaml` under `invariants:`:

```yaml
  - id: switch_lane_has_sample
    kind: invariant
    title: "Switch validation has enough evidence to speak"
    check: switch_lane_has_sample
    schedule: monthly
    action: >
      Nothing to do — this is an accrual gate, not a failure. It closes by
      itself once enough non-overlapping switch pairs have matured, and that
      is the day the "do switch ideas work out?" question first has an answer.
      Investigate only if n_effective stops rising: that means capture stopped
      (advisor.switch_eval_enabled) or grading stopped (audit.switch_lane_enabled).
    docs: docs/superpowers/specs/2026-08-20-switch-validation-design.md
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/ops/ -q`
Expected: PASS.

- [ ] **Step 5: Run the FULL suite and commit**

```bash
python -m pytest -q
```

Expected: **2884 + your new tests passed, 12 skipped, 0 failed.** Any other change is a regression — stop and investigate rather than committing.

```bash
git add core/ops/watchdog/checks.py config/milestones.yaml CODEBASE.md tests/unit/ops/test_watchdog_checks.py
git commit -m "feat(watchdog): tell me when the switch lane can first answer the question"
```

---

## Self-review notes (already applied)

- **Spec coverage.** §4.1 → Task 2; §4.2 → Tasks 3–4; §4.3 → Tasks 1, 5; §4.4 → Task 1; §5 → Task 8; §5.1 → Task 7; §6.1 → Task 5; §6.2 → Task 4 (price map hoisted out of the loop) + Task 5 (per-run cap); §6.3 → Task 6; §7 → Task 9 (`switch_rule` / `switch_taken` split); §8 → Tasks 9–10; §9 config → folded into the task that needs each key.
- **Deliberately deferred to first-run observation, not silently dropped:** §5's ATR-breach shock detector and the `research` bucket's below-chance test are wired as *parameters* (`atr_breach`, `below_chance`) with tests, but no caller computes them in Task 9 — it passes neither. Both need the per-leg ATR series and a stable per-reason hit-rate, and neither is meaningful until the lane has rows. Task 9 therefore reports `unpredictable` only for rows a future caller marks, and `research` never fires yet. **This is a known, bounded gap** — the taxonomy will over-report `knowledge` until it is closed, and the report must not be read as final before then.
- **Type consistency.** `evaluate_switch_candidates` returns dicts with `candidate` / `candidate_sector` / `candidate_conviction` / `decision` / `reason` (Task 3) and Task 4 consumes exactly those keys. `AuditOutcome.candidate` (Task 1) is read by `stride_subsample` (Task 6) and `classify_miss` (Task 8). `triggers[0]` is the decision and `triggers[1]` the reason, written in Task 5 and read in Tasks 8 and 9.
