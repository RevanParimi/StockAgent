# Monthly Scorecard + Baseline Duel — RL Phase 1

**Date:** 2026-06-12
**Status:** Design — approved direction (roadmap Phase 1)
**Depends on:** June-10 measurement phase (eval harness, metrics) + June-11 knowledge layer
(event_tags, lesson claims) — both IMPLEMENTED and merged.

---

## 1. Problem

The harness measures a point in time; nothing tracks month-over-month. And nothing runs a
control, so "the architecture beats the plain model" is an assertion. After this phase:

- **Improvement is a number**: every month gets a persisted scorecard with deltas vs the
  previous month.
- **The duel is a number**: a frontier-LLM control lane (same model, same information,
  none of the architecture) and naive baselines are scored on the same days, so
  StockAgent's edge = `agent_accuracy − control_accuracy` is measured, not claimed.
- **Claims are audited**: each day records which lessons fired, so the scorecard reports
  accuracy on claim-fired days vs other days.

## 2. Component 1 — Control lane (the duel)

### 2.1 What it is
A bare-LLM predictor that gets exactly the information StockAgent has at the same moment
— yesterday's close + the day's already-fetched `market_context` — but none of the
machinery (no 9 agents, no learned weights, no lessons, no dossier). Same model tier as
the system's verdict reasoning.

### 2.2 Schema (`src/backend/shared/schemas/scorecard.py`)
```python
class ControlPrediction(BaseModel):
    date: str                       # trading day being predicted
    made_on: str                    # review date when prediction was made (prev session)
    predicted_direction: str        # "UP" | "DOWN" | "FLAT"
    confidence: float = 0.5         # 0..1
    predicted_close: float | None = None
    rationale: str = ""             # capped 200 chars
    model: str = ""
    # Filled when scored (next review):
    actual_direction: str = ""
    correct: bool | None = None

class ControlLog(BaseModel):
    ticker: str
    sector: str
    cycle_id: str                   # e.g. "MARUTI_2026-06" — monthly, like feedback log
    entries: list[ControlPrediction] = []
```
Persistence: `PredictionStore._control_log_path(cycle_id)` →
`data/predictions/{sector}/{TICKER}/{cycle_id}_control_log.json`, `load_control_log` /
`save_control_log` via the existing atomic `_write_json` pattern.

### 2.3 Hook — daily_review Step 10 (new, flag-gated, never fatal)
At the END of `run_daily_review` (after Step 9), gated on `RL_CONTROL_LANE_ENABLED`:
1. **Score yesterday's call**: load this cycle's ControlLog; find the entry with
   `date == review_date` and `correct is None`; fill `actual_direction` from
   `final_entry.actual_direction` and `correct = (predicted_direction == actual_direction)`.
2. **Predict the next session**: one LLM call (model = `CONTROL_LANE_MODEL` or
   `settings.LLM_MODEL_REASONING` when empty; temp 0.2; json_object; ≤300 tokens).
   Prompt (new `core/config/prompts/shared/control_lane.py`): "You are a standalone
   market analyst with NO tools and NO memory. {ticker} ({sector}, NSE) closed at
   {actual_close} on {date}. Market context: {market_context[:3000]}. Predict the NEXT
   trading session: JSON {{"direction": "UP|DOWN|FLAT", "confidence": 0..1,
   "predicted_close": number|null, "rationale": "<one sentence>"}}." Next trading day from
   `nse_calendar`. Append entry; save log.
3. Any failure (LLM, parse, I/O): log warning, skip — review result unaffected.

Fairness invariant: the control predicts day D+1 during day D's review; StockAgent's
envelope row for D+1 was revised in the same review (Step 7) with the same context.
Same information, same timing — the delta isolates the architecture.

Cost: +1 LLM call/ticker/day. No new Serper/yfinance calls (context is already in scope).

## 3. Component 2 — Naive baselines (`core/intelligence/rl/eval/baselines.py`)

Pure functions over a month's ordered `FeedbackEntry` list (no I/O, no LLM, computed at
scorecard time — backfillable for any past month):
```python
def persistence_accuracy(entries) -> float | None
    # predict day D direction = day D-1 actual_direction; first day skipped; None if <2
def always_up_accuracy(entries) -> float | None      # predict UP every day
def always_down_accuracy(entries) -> float | None
```
Directions compared against `entry.actual_direction` (3-way, same classifier as
everything else).

## 4. Component 3 — Claim audit trail

`FeedbackEntry` gains `claims_fired: list[str] = []` (lesson_ids whose claims fired in
Step-7 revision that day). To avoid duplicating gating logic:
`lesson_emphasis.py` gains `matching_lessons(ledger, today_tags) -> list[Lesson]`
(extracted from `apply_lesson_emphasis`'s loop — same still_valid / trigger_tags /
eff-confidence ≥ `RL_LESSON_MATCH_MIN_CONF` gates; `apply_lesson_emphasis` is refactored
to use it internally; behavior identical, existing tests must stay green).
`daily_review` populates `claims_fired=[l.lesson_id for l in matching_lessons(...)]` on
the final entry (empty when `RL_CLAIMS_ENABLED` off or no ledger/tags).

## 5. Component 4 — Scorecard (`core/intelligence/rl/eval/scorecard.py`)

### 5.1 Schema (in `schemas/scorecard.py`)
```python
class LaneScore(BaseModel):
    n: int = 0
    direction_accuracy: float | None = None
    brier_score: float | None = None          # only lanes with confidence (agent, control)

class TickerScorecard(BaseModel):
    ticker: str; sector: str
    agent: LaneScore                          # StockAgent (from feedback log, existing metrics)
    control: LaneScore                        # control lane (scored entries only)
    persistence: LaneScore                    # naive baselines (direction accuracy only)
    always_up: LaneScore
    band_coverage: float | None = None
    mae_pct: float | None = None
    edge_vs_control: float | None = None      # agent − control direction accuracy
    edge_vs_persistence: float | None = None
    claim_days: int = 0                       # days with claims_fired non-empty
    accuracy_on_claim_days: float | None = None
    accuracy_on_other_days: float | None = None
    dossier_version: int | None = None        # health snapshot
    dossier_observations: int | None = None
    live_signatures: int | None = None

class MonthlyScorecard(BaseModel):
    month: str                                # "2026-06"
    generated_at: str
    tickers: dict[str, TickerScorecard] = {}
    aggregate: TickerScorecard | None = None  # ticker-weighted aggregate (ticker="ALL")
    deltas_vs_previous: dict[str, float] = {} # aggregate metric deltas; {} when no prior
```

### 5.2 Builder
`build_scorecard(month: str, tickers: list[str] | None = None) -> MonthlyScorecard` —
READ-ONLY over feedback logs, control logs, ledgers, dossiers (auto-discovers tickers
from `data/predictions/` like the harness). Reuses `eval/metrics.py` functions (no
formula duplication). Loads the previous month's scorecard file (if any) to fill
`deltas_vs_previous`. Saves to `{SCORECARD_DIR}/{YYYY-MM}_scorecard.json` (PERMANENT —
this is the improvement time series) and prints a human table:

```
SCORECARD 2026-06 (vs 2026-05)
lane          accuracy   brier    n
agent           62.5%    0.221   16   (+4.2pp vs prev month)
control LLM     50.0%    0.275   16   → edge +12.5pp
persistence     43.8%      —     16   → edge +18.7pp
always-up       56.3%      —     16
claims: fired on 5 days — 80.0% on claim days vs 54.5% other days
dossier: v3, 18 observations, 2 live signatures
```

## 6. Component 5 — CLI + scheduler

- CLI: `python -m services.scheduler.run_schedule scorecard [--month YYYY-MM] [--ticker ...]`
  — default month = previous calendar month; `--month current` allowed for partial months
  (printed with a "(partial)" marker, still saved).
- Scheduler: monthly job (CronTrigger day 1, 02:00 IST, gated `SCORECARD_ENABLED`) builds
  the previous month's scorecard for all managed tickers. Non-fatal.

## 7. New settings (real file `src/backend/shared/config/settings/base.py`)

| Setting | Default | Controls |
|---|---|---|
| `RL_CONTROL_LANE_ENABLED` | `True` | Daily control-lane prediction + scoring (Step 10) |
| `CONTROL_LANE_MODEL` | `""` | Control model; empty → `LLM_MODEL_REASONING` |
| `SCORECARD_ENABLED` | `True` | Monthly scheduler job |
| `SCORECARD_DIR` | `data/eval/scorecards` | Persisted scorecard time series (volume) |

## 8. Safety

- Everything flag-gated; flags off → byte-identical behavior (claims_fired stays `[]`,
  no Step 10, no monthly job).
- Step 10 and the monthly job never raise (same contract as Step 8.5).
- Scorecard builder is read-only over its inputs; writes only `{SCORECARD_DIR}`.
- `matching_lessons` refactor must keep `apply_lesson_emphasis` behavior identical
  (existing emphasis tests are the regression net).

## 9. Validation

- Unit/TDD per component (schemas round-trip, baselines math, matching_lessons parity
  with emphasis gates, control scoring fills correct entry, scorecard aggregation +
  deltas + claim split, CLI smoke). tmp_path only — never write data/predictions.
- Live: run a real daily review (control lane makes its first real prediction), then
  `scorecard --month current` → table for June's partial data with agent vs baselines.

## 10. Explicitly NOT in scope

- No dashboard/API endpoint for scorecards (CLI + JSON file only; UI later).
- No chat surfacing of the scorecard (later, one tool away).
- No multi-model duel (one control model; configurable).
- No retroactive control backfill (the control lane starts accumulating from deploy;
  naive baselines ARE backfillable and cover history).

## 11. File map

| File | Change |
|---|---|
| `src/backend/shared/schemas/scorecard.py` | NEW — ControlPrediction/ControlLog/LaneScore/TickerScorecard/MonthlyScorecard |
| `src/backend/shared/schemas/feedback.py` | `FeedbackEntry.claims_fired: list[str] = []` |
| `core/intelligence/rl/algorithms/lesson_emphasis.py` | `matching_lessons()` extraction; emphasis refactored onto it |
| `core/intelligence/rl/stores/prediction_store.py` | control-log path + load/save |
| `core/config/prompts/shared/control_lane.py` | NEW — control prompt |
| `core/intelligence/rl/workflows/daily_review.py` | Step 10 control lane; claims_fired population in Step 7/8 |
| `core/intelligence/rl/eval/baselines.py` | NEW — pure naive baselines |
| `core/intelligence/rl/eval/scorecard.py` | NEW — builder + table renderer |
| `services/scheduler/run_schedule.py` | `scorecard` subcommand |
| `services/scheduler/python/scheduler.py` | monthly scorecard job |
| `src/backend/shared/config/settings/base.py` | 4 new settings |
| tests | `test_baselines.py`, `test_control_lane.py`, `test_scorecard.py`, `test_matching_lessons.py` (or folded into emphasis tests) |
