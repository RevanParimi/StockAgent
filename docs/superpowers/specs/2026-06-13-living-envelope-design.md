# Living Envelope — Shock-Robust Forecasting (RL Phase 2.5)

**Date:** 2026-06-13
**Status:** IMPLEMENTED 2026-06-13 (live-verified: forced MARUTI re-forecast — archive v1, 23 days re-pathed, past days untouched; real pre-open check caught severity-0.75 risk_on Iran-oil news, zero false flags)
**Depends on:** Phase 0/1 (envelope, daily review, regime detector, thesis reviewer) — all live.

---

## 1. Problem

The 30-day envelope is **frozen at month-start**. Audit findings (file:line evidence in
the 2026-06-13 robustness audit):

1. Monte Carlo price paths are built once on the 1st (`generate_forecast.py:161-175`);
   no mid-month regeneration trigger exists.
2. Step-7 revision adjusts **confidence only** — never the price path or direction. A
   thesis broken by a macro shock (war, crude spike) limps to month-end as "NEUTRAL at
   0.45" while the stock does −6%.
3. Regime detection is **ephemeral**: MACRO_CRISIS detected today is discarded by
   tomorrow's review (`regime/detector.py` consumers apply multipliers for that day only).
4. Nothing inspects overnight news pre-open; the loop is entirely post-close.
5. Zero tests cover the shock path (external_shock classification, 20% rate-cap
   override at `daily_review.py:799-823`, revision under stress).

The weight layer is already shock-safe (±0.05 step / ±0.15 drift caps, external_shock
zero-penalty, calibration shock exclusion, 20% rate-cap) — **out of scope, unchanged**.

## 2. Goal

Make the envelope a living document: an experienced analyst abandons a broken monthly
thesis and re-underwrites. Bounded, evidence-gated, fully flag-gated; scoring honesty
preserved (every prediction is scored against the envelope that was active when made).

## 3. Component 1 — Sticky regime (market-level, hysteresis)

New `core/intelligence/regime/state.py`:

```python
@dataclass
class RegimeState:
    label: str           # NORMAL / RISK_OFF / MACRO_CRISIS / ...
    since: str           # ISO date the label was entered
    calm_streak: int     # consecutive detections milder than the sticky label

def update_sticky_regime(detected_label: str, today: str) -> RegimeState
```

- Persisted market-wide (one file, not per ticker): `data/predictions/_regime_state.json`.
- Enter a severe regime (RISK_OFF / MACRO_CRISIS) **immediately** on detection.
- Exit only after `RL_REGIME_CALM_DAYS` (default 3) consecutive milder detections
  (hysteresis); `calm_streak` resets on any severe re-detection.
- Severity order: NORMAL < RISK_OFF < MACRO_CRISIS (use/extend the detector's existing
  labels — implementer must read `detector.py` for the canonical set).
- Consumers: daily_review Step 0 uses the STICKY label (not the raw daily one) for its
  regime weight multipliers; re-forecast (Component 2) passes it to the Monte Carlo
  `regime_label` so bands widen for the whole regenerated path. Never raises; missing/
  corrupt state file → behaves exactly as today (raw label pass-through).

## 4. Component 2 — Shock-triggered re-forecast

### 4.1 Engine

Factor `generate_forecast.py` so the envelope build is callable mid-month:

```python
def regenerate_envelope(ticker: str, sector: str, reason: str,
                        review_date: date) -> PredictionEnvelope | None:
    """Fresh full-pipeline run -> new Monte Carlo paths for the REMAINING days of the
    current cycle only. Archives the superseded envelope. NEVER raises (None on failure)."""
```

- Runs the (unified) orchestrator fresh → new dimension scores/verdict → new forecast
  profile → new MC paths from today's actual close, for remaining trading days only.
- Past days' forecasts and already-logged feedback entries are **untouched**.
- Archive: superseded envelope copied to
  `data/predictions/{sector}/{ticker}/archived_envelopes/{month}_v{n}.json` before
  overwrite (PredictionStore gains `archive_envelope()`); new envelope carries
  `reforecast_count`, `reforecast_history: [{date, reason, trigger, archived_file}]`.
- Hard cap: `RL_REFORECAST_MAX_PER_MONTH` (default 2) per ticker; at cap → log + skip.

### 4.2 Triggers (daily_review, after Step 6, before Step 7)

Re-forecast fires when ANY of (checked in this order, first match is the recorded reason):

| Trigger | Condition |
|---|---|
| `external_shock` | FeedbackAgent miss_type == external_shock AND direction wrong (post rate-cap — i.e. the classification SURVIVED the 20% cap) |
| `thesis_break` | ThesisReviewer ran and `horizon_confidence_multiplier` ≤ `RL_REFORECAST_THESIS_MULT_THRESHOLD` (default 0.5) |
| `regime_flip` | Sticky regime ENTERED MACRO_CRISIS today (transition, not steady state) |

- When re-forecast fires, Step 7 confidence-revision is **skipped** for that day (the
  fresh envelope supersedes nudging the dead one). Cycle log records the event.
- Flag `RL_REFORECAST_ENABLED` (default true); off → today's behavior byte-identical.

### 4.3 Scoring honesty

`daily_review` reads "today's prediction" from the envelope file as of review time —
since regeneration only replaces days > today, every scored day was predicted by the
envelope active when that prediction was made. Scorecard/control-lane comparisons remain
fair. The implementer must verify no code path reads tomorrow's forecast from a stale
in-memory copy after regeneration.

## 5. Component 3 — Pre-open sanity check

New scheduler job `preopen_shock_check` (trading days, 08:45 IST, before 09:15 open),
gated `RL_PREOPEN_CHECK_ENABLED` (default true), plus CLI
`python -m services.scheduler.run_schedule preopen-check [--ticker ...]`.

Cost budget: **1 Serper + 1 FAST-tier LLM call per day TOTAL** (market-level, not per
ticker):

1. One Serper news search: "India stock market overnight global macro crisis news
   {date}" (+ futures/GIFT Nifty wording — implementer picks the query, capped 1 call).
2. One `LLM_MODEL_FAST` call (json_object, never raises): rate
   `{"severity": 0.0-1.0, "direction": "risk_off|risk_on|neutral", "headline": "..."}`.
3. If `severity >= RL_PREOPEN_SHOCK_SEVERITY` (default 0.7): for each managed ticker
   whose TODAY's envelope direction contradicts `direction` (predicted UP in risk_off /
   DOWN in risk_on), write a `preopen_flag` into the ticker's cycle log and trigger
   `regenerate_envelope(reason="preopen_shock")` — same monthly cap applies.
4. Severity < threshold → single log line, nothing else. Failures (Serper dead, LLM
   down) → log + skip, never block the open.

## 6. Settings (`src/backend/shared/config/settings/base.py`)

| Setting | Default |
|---|---|
| `RL_REFORECAST_ENABLED` | `true` |
| `RL_REFORECAST_MAX_PER_MONTH` | `2` |
| `RL_REFORECAST_THESIS_MULT_THRESHOLD` | `0.5` |
| `RL_REGIME_STICKY_ENABLED` | `true` |
| `RL_REGIME_CALM_DAYS` | `3` |
| `RL_PREOPEN_CHECK_ENABLED` | `true` |
| `RL_PREOPEN_SHOCK_SEVERITY` | `0.7` |

## 7. Safety

- All three flags off → byte-identical current behavior (no new file reads on hot paths).
- `regenerate_envelope` / `update_sticky_regime` / pre-open job: never raise.
- Cost ceilings: re-forecast ≤2 full pipeline runs/ticker/month (~$0.08); pre-open check
  1 Serper + 1 fast LLM/day (~$0.01/day).
- Weight layer untouched. Dossier/lessons/calibration flows untouched.

## 8. Validation

- TDD shock suite (NEW — none exists): external_shock rate-cap override (pin existing
  `daily_review.py:799-823` behavior); each of the 3 triggers fires/regenerates exactly
  once; cap enforcement (3rd attempt skipped); archive file written + history metadata;
  past-day forecasts byte-identical after regeneration; Step-7 skip on re-forecast day;
  sticky regime enter-immediately/exit-after-3-calm (+ corrupt state file → passthrough);
  pre-open severity gating, contradiction matrix, cost cap (mock: exactly 1 Serper,
  1 LLM), all flags-off byte-identical.
- Live verification (no real war available): CLI-forced
  `regenerate_envelope(MARUTI, reason="manual_verification")` against real
  pipeline/market data — show archived v1, new envelope with reforecast_history, past
  days untouched, remaining days re-pathed from today's close; then
  `preopen-check` real run showing severity + decision; suite green.

## 9. Not in scope

Weight adapter changes; intraday updates beyond the single pre-open check; shock-lesson
faster decay (minor, separately later); Phase 2 signature validation.

## 10. File map

| File | Change |
|---|---|
| `core/intelligence/regime/state.py` | NEW — sticky RegimeState + update_sticky_regime |
| `core/intelligence/rl/workflows/generate_forecast.py` | factor + `regenerate_envelope()` |
| `core/intelligence/rl/workflows/daily_review.py` | trigger block after Step 6; sticky-label consumption; Step-7 skip |
| `core/intelligence/rl/workflows/preopen_check.py` | NEW — market-level pre-open shock check |
| `core/intelligence/rl/stores/prediction_store.py` | `archive_envelope()` |
| envelope schema (wherever PredictionEnvelope lives) | `reforecast_count`, `reforecast_history` |
| `services/scheduler/python/scheduler.py` | `preopen_shock_check` job (08:45 IST) |
| `services/scheduler/run_schedule.py` | `preopen-check` + `reforecast` subcommands |
| `src/backend/shared/config/settings/base.py` | 7 settings |
| tests | `test_shock_path.py`, `test_sticky_regime.py`, `test_preopen_check.py`, `test_reforecast.py` |
