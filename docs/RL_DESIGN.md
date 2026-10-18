# RL Design — Adaptive Prediction Loop

**Edition:** 2026-10-10 · **Code inspected:** `e85da94`, the code production runs

**Scope:** the learning loop in depth: forecast envelopes, the daily review,
weights, lessons, company knowledge, measurement and the Living Envelope.

The [technical design](TECHNICAL_DESIGN.md) (the KT) summarises this loop in
[section 5](TECHNICAL_DESIGN.md#5-learning-forecast-review-and-memory). It is
also the reference for the decision gate, instrument identity and store
ownership, which this document uses without repeating. Measured production
state, including which learning mode production runs, lives only in
[KT section 1](TECHNICAL_DESIGN.md#production-state-at-this-edition). Work
planned in PI-2026-09 is labelled **Planned** with its story.

Section numbers are stable: other documents cite sections 23 to 27.

| Part | Sections |
|---|---|
| The loop and its records | 1 Purpose and limits · 2 Architecture · 3 Persistent memory and store ownership |
| Forecast and review | 4 Month-start forecast · 5 Daily review · 6 Review input checks · 7 Learning mode · 8 Per-ticker outcomes |
| Learning mechanics | 9 Weight adapter · 10 Miss taxonomy · 11 Lessons · 12 Conviction streak · 13 Regime · 14 Seasonal calendar · 15 Prompt enhancer · 16 Thesis review · 17 Market-structure signals |
| Reference | 18 Schemas · 19 Configuration · 20 Jobs, CLI and API · 21 Static versus LLM · 22 Limits and planned work |
| Components | 23 Knowledge layer · 24 Measurement harness · 25 Scorecard and learning evidence · 26 Event ingestion · 27 Living Envelope |

---

## 1. Purpose and limits

Each managed ticker gets a monthly **envelope**: a forecast row for each of
the next 30 exchange sessions. Every weekday the loop grades the previous
session's row against the actual close and asks an LLM why it missed. It
then adjusts how much each analysis dimension counts (its weight), records
reusable lessons, and keeps a per-ticker dossier of company knowledge. All of
it is persistent JSON under `data/predictions/`.

This is an adaptive feedback system. It is not shown to predict better than a
fixed policy, and three defects limit what its records mean:

- **The graded label is error direction.** `classify_direction` compares the
  actual close with the *predicted* close, not with the previous close. A
  stock that rose 5% but undershot a 10% forecast is graded DOWN. The KT's
  [worked example](TECHNICAL_DESIGN.md#grading-defect-an-example-everyone-can-follow)
  shows the effect.
- **The graded verdict can be chosen after the outcome.** With hard-bind on,
  a review that re-runs the analysis grades the session against that fresh
  verdict, not the frozen one the row was issued with (section 5, step 4).
- **Final weights can leave their bounds.** The adapter clamps each weight
  and then renormalises, which can push a weight past its ceiling (section 9).

**Why the switch exists.** Unconstrained, the adapter drove chart weights
toward zero. The learning mode (section 7) lets production record what
learning would do without letting it move decisions. **Planned:** a corrected
target (SA-012), frozen issue-time grading (SA-013, SA-014), idempotent and
bounded updates (SA-015), and a shadow learner with explicit conditions for
returning to `adapt` (SA-043; KT
[section 11](TECHNICAL_DESIGN.md#11-planned-redesign)).

## 2. Architecture overview

```text
MONTH START (calendar 1st, 09:00 IST: rl_monthly_forecast)
  generate_forecast(ticker, managed sector)
    weights      decision_weights(): stored weights (adapt) or sector defaults (observe)
    analysis     sector orchestrator -> report + decision gate        [LLM]
    gate         enforce + abstain -> InsufficientDataError, no envelope
    base close   verified close (yfinance x NSE cross-check)
    enhancer     miss counter -> extra search queries, saved per cycle [STATIC, LLM fallback]
    profile      ForecastProfile: monthly return %, band, shape        [LLM, static fallback]
    paths        GBM Monte Carlo, 500 paths, P10/P50/P90 per session  [STATIC]
    per day      seasonal deltas, lesson adjustments (adapt only)     [STATIC]
    rows         each row stamped: data_gate, source_run_id, instrument
    save         envelope with learning_mode, decision_gate, instrument

PRE-OPEN (Mon-Fri 08:45 IST: preopen_shock_check)        section 27.3
  1 news search + 1 fast-tier rating -> on a shock, re-forecast contradicted envelopes

DAILY (Mon-Fri 16:30 IST: rl_daily_review, previous trading session)
  run_daily_review(ticker, session, managed sector)       section 5
    0    regime: raw detection + market-wide sticky label (written every run)
    1    envelope row for the session (own month, else previous month)
    gate row provenance and identity                      section 6
    2    session close; stale-close check
    3    error and direction
    4    optional analysis re-run (gated), feedback agent  [LLM]
    5    weight adapter: adapt writes, observe proposes   sections 7, 9
    5.5  regime multipliers (ephemeral)
    6    lessons merge + shared-ledger propagation         section 11
    6.5  conviction streak                                 section 12
    7a   thesis review on significant misses               [LLM] section 16
    --   re-forecast trigger (external_shock / thesis_break / regime_flip)  section 27.2
    7b   confidence-only revision of remaining rows (skipped after a re-forecast)
    8    feedback entry (upsert by date)
    8.5  dossier curator                                   [LLM] section 23.2
    --   off-market signals saved for tomorrow
    9    seasonal validation (last trading day of the month)
    10   control lane: score yesterday's call, make tomorrow's  [LLM] section 25
  scheduler: one outcome per ticker, then the portfolio pipeline   section 8

WEEKLY
  Sat 10:00 event_ingest_weekly   NSE events -> dossier            [LLM] section 26
  Sat 11:00 research_loop_weekly  open questions -> searches       [LLM] section 23.2
  Mon 03:30 ledger_cleanup_weekly stale-lesson cleanup + dossier distillation

MONTHLY
  1st 02:00 scorecard_monthly     scorecard + learning evidence report   section 25
```

Three switches decide what this flow may change:

- `rl.learning_mode` (section 7): whether learned weights and lesson emphasis
  move decisions, or are only recorded;
- `decision_gate.mode` (KT
  [section 4](TECHNICAL_DESIGN.md#decision-gate)): whether forecasts and
  reviews built on unverified data or an unresolved identity are withheld, or
  only recorded;
- per-component flags (section 19): each component can be switched off on its
  own, and every off path skips that component's reads and writes.

**Invariants that hold in every mode:**

- regime multipliers are applied per day and never written to weight memory;
- a review writes at most one feedback entry per ticker and date: a re-run
  replaces it;
- every JSON write goes to a `.tmp` file first and is then renamed, so a crash
  never leaves a half-written file;
- the paper lane (discovery ideas) never trains or writes weights, never
  propagates lessons to shared ledgers, never writes the sticky regime, never
  re-forecasts and never runs the control lane.

## 3. Persistent memory and store ownership

### 3.1 Layout

```text
data/predictions/
  _market_ledger.json                 market-wide lessons (all sectors)
  _regime_state.json                  sticky regime label (market-wide)
  <sector>/
    _shared_ledger.json               sector-wide lessons
    _seasonal_validation.json         seed validation state (section 14)
    <TICKER>/
      <TICKER>_<YYYY-MM>_prediction_envelope.json   monthly forecast rows
      <TICKER>_<YYYY-MM>_daily_feedback_log.json    one entry per graded session
      <TICKER>_<YYYY-MM>_control_log.json           control-lane calls (section 25)
      <TICKER>_<YYYY-MM>_prompt_enhancements.json   extra queries (section 15)
      <TICKER>_agent_weight_memory.json             weights, permanent
      <TICKER>_weight_observations.json             observe-mode proposals (section 7)
      <TICKER>_learning_ledger.json                 lessons and miss counters, permanent
      <TICKER>_archived_lessons.json                cold store (section 11)
      <TICKER>_dossier.json                         company knowledge (section 23)
      <TICKER>_<YYYY-MM-DD>_offmarket.json          deals and pre-open data (section 17)
      archived_envelopes/<YYYY-MM>_v<n>.json        superseded envelopes (section 27.2)
      thesis_calls.jsonl                            thesis-review telemetry (section 16)
data/rl/paper/predictions/            paper-lane root, same layout (discovery ideas)
data/prediction_quarantine/           stores moved out by the ownership quarantine
```

A cycle id is `<TICKER>_<YYYY-MM>`, the calendar month the row's date falls
in. Envelope rows run 30 trading days from the 1st, about six weeks, so early
sessions of a month are also covered by the previous month's envelope.

### 3.2 Ownership

A ticker's forecasts, reviews and learned state belong to one store,
`<managed sector>/<TICKER>`: the sector of its entry in
`data/managed_tickers.json`, whether or not the ticker is enabled. The
monthly forecast, the daily review, the startup self-heal and the weekly jobs
all use that sector. The KT's
[ownership section](TECHNICAL_DESIGN.md#prediction-store-ownership) gives the
rule's history, the read-only inventory, the quarantine and the readers that
still pick another store.

Three behaviours of `PredictionStore` matter to every reader:

- **Constructing a store creates its directory.** A read through
  `PredictionStore` for a ticker that has no store leaves an empty directory
  behind.
- **New files carry the store's sector.** A feedback log, weight memory or
  ledger created by a sectored store records that sector; files already on
  disk keep what they say.
- **Disabling keeps history; removing deletes it.** Toggling a managed ticker
  off stops scheduling and keeps every file. Removing it from the list deletes
  `data/predictions/<sector>/<TICKER>/` (section 20). Only the nightly backup
  archives keep a copy.

### 3.3 Envelope

```json
{
  "ticker": "MARUTI",
  "sector": "automobile",
  "cycle_id": "MARUTI_2026-10",
  "generated_at": "2026-10-01",
  "base_close": 12850.0,
  "weight_version_used": 41,
  "learning_mode": "observe",
  "decision_gate": {"status": "actionable", "run_id": "…", "identity": {"…": "…"}},
  "instrument": {"ticker": "MARUTI", "symbol": "MARUTI.NS", "basis": "…", "status": "active"},
  "forecast_profile_shape": "front_loaded",
  "forecast_profile_monthly_pct": 3.2,
  "forecast_profile_source": "llm",
  "conviction_streak": {"current_verdict": "BUY", "streak_days": 6, "reversion_prior": 0.05},
  "agent_predictions": {"sales_demand": {"bull_case_if": "…", "data_confidence": 0.8}},
  "fno_snapshot": {"pcr": 1.1, "max_pain_price": 12700.0, "oi_buildup_direction": "NEUTRAL"},
  "reforecast_count": 0,
  "reforecast_history": [],
  "daily_forecasts": [{
    "day": 1,
    "date": "2026-10-03",
    "predicted_close": 12880.4,
    "price_lower": 12610.2,
    "price_upper": 13150.9,
    "predicted_verdict": "BUY",
    "predicted_agent_scores": {"sales_demand": 0.72, "fundamentals": 0.68},
    "confidence": 0.71,
    "key_assumptions": ["…"],
    "revised": false,
    "revision_count": 0,
    "data_gate": "actionable",
    "source_run_id": "…",
    "instrument": {"ticker": "MARUTI", "symbol": "MARUTI.NS", "basis": "…", "status": "active"}
  }]
}
```

Each row records where it came from. `data_gate` and `source_run_id` name
the analysis run that issued the row and that run's gate status; `instrument`
names the security its analysis priced. A later registry change never
rewrites them. A row issued before these stamps existed has an empty
`data_gate`, meaning provenance unknown, and `instrument: {}`. In `observe`
mode, `weight_version_used` is only the stored version at that time: the
forecast used the sector defaults.

### 3.4 Feedback entry

```json
{
  "day": 5, "date": "2026-10-09",
  "predicted_close": 12920.0, "actual_close": 12790.0, "price_error_pct": -1.0062,
  "predicted_verdict": "BUY", "graded_verdict": "BUY",
  "actual_direction": "DOWN", "direction_correct": false,
  "predicted_agent_scores": {"sales_demand": 0.72, "fundamentals": 0.68},
  "regime_label": "NORMAL",
  "event_tags": ["earnings_event", "fii_flow"],
  "claims_fired": [],
  "volume_vs_20d_avg": 1.4,
  "miss_analysis": {"primary_miss_agent": "sales_demand", "miss_type": "magnitude",
                    "missed_factors": ["…"], "agent_score_drift": {"sales_demand": -0.08}},
  "timing": {"predicted_peak_day": 22, "actual_move_start_day": 5, "lag_days": -17,
             "assessment": "no_move"},
  "revised_context": {"headline": "…", "watch_signals": ["…"], "horizon_confidence_adjustment": -0.02},
  "thesis_review": null,
  "lessons_generated": ["L014"],
  "weight_adjustment_applied": "v41",
  "predicted_catalysts_snapshot": {"sales_demand": {"bull_case_if": "…"}},
  "offmarket_context": ""
}
```

`miss_analysis` is written when the direction is wrong or the absolute error
exceeds 1%. `weight_adjustment_applied` is the stored version after the
review; in `observe` mode it never changes.

### 3.5 Weight memory and observations

```json
{
  "ticker": "MARUTI", "sector": "automobile", "weight_version": 41,
  "current_weights": {"sales_demand": 0.22, "fundamentals": 0.24, "pattern_analysis": 0.0},
  "base_weights":    {"sales_demand": 0.20, "fundamentals": 0.18, "pattern_analysis": 0.10},
  "agent_accuracy": {"sales_demand": {"direction_hits": 5, "total": 7, "calibration_hits": 4, "calibration_total": 6}},
  "weight_history": [{"version": 41, "date": "2026-09-25", "weights": {"…": 0.0},
                      "reason": "sales_demand: Δ+0.02 (hits=6/7)", "deltas": {"sales_demand": 0.02},
                      "accuracy_snapshot": {"sales_demand": 0.857}}]
}
```

`base_weights` is the graph's default table when the file was created, and
the drift bounds are measured from it. A missing or unreadable weight file is
recreated from the sector's graph at version 0, by the forecast and by the
review, in either learning mode.

`<TICKER>_weight_observations.json` holds one record per review date, the
newest 260 (about a year):

```json
{"review_date": "2026-10-09", "mode": "observe", "mode_reason": "rl.learning_mode=observe",
 "applied": false, "stored_version": 41, "stored_weights": {"…": 0.0},
 "would_be_version": 42, "would_be_weights": {"…": 0.0}, "deltas": {"sales_demand": 0.02},
 "adapter_reason": "sales_demand: Δ+0.02 (hits=6/7)",
 "decision_weights": {"…": 0.0}, "recorded_at": "2026-10-09T11:12:30+00:00"}
```

### 3.6 Learning ledger

```json
{
  "ticker": "MARUTI", "sector": "automobile",
  "lessons": [{
    "lesson_id": "L014", "date_learned": "2026-09-12", "last_seen": "2026-10-09",
    "category": "macro", "scope": "sector_wide", "pattern": "RBI_policy_day",
    "observation": "…", "rule": "Prioritise risk_macro over demand signals on RBI days",
    "confidence": 0.71, "occurrences": 3, "still_valid": true,
    "contributing_tickers": ["MARUTI"],
    "trigger_tags": ["central_bank_event"],
    "prioritise_agents": ["risk_macro"], "discount_agents": ["sales_demand"],
    "evidence": ["2026-10-08 — RBI holds repo rate at …"]
  }],
  "miss_counter": {"fii_outflow_spike": 5},
  "miss_events": {"fii_outflow_spike": [{"date": "2026-10-09", "miss_type": "model_bias", "cycle_id": "MARUTI_2026-10"}]}
}
```

A lesson's `rule` states intent, not a number: a stored delta would go stale
as weights move. `evidence` keeps up to three dated headlines that were in
the agent's context when the lesson was written or confirmed; a lesson
learned on a day with no dated news has none, and none is invented.

## 4. Month-start forecast generation

**Trigger.** `rl_monthly_forecast` runs on the **calendar first at 09:00
IST**, not the first trading day, for each enabled managed ticker in its
managed sector. Rows cover the 30 NSE trading days after the run date
(`rl.forecast_horizon_days`). A restart's self-heal also generates a missing
envelope (section 20).

**Steps** ([generate_forecast.py](../core/intelligence/rl/workflows/generate_forecast.py)):

1. **Weights.** `decision_weights()` returns the stored effective weights in
   `adapt` mode and the sector's default table in `observe` mode.
2. **Analysis.** The sector orchestrator runs with those weights injected
   into its aggregator. Its report carries the decision gate.
3. **Gate.** A non-actionable report is recorded in the gate log. In
   `enforce` mode it stops here with `InsufficientDataError`, and no envelope
   is written.
4. **Base close.** The latest verified close (yfinance cross-checked with
   NSE). One retry after 15 seconds; then the ticker fails for this run.
5. **Prompt enhancements** from the ledger's miss counter (section 15).
6. **Forecast profile.** One bulk-tier LLM call returns the expected monthly
   return (bounded to ±20%), a daily uncertainty band (0.1% to 5%) and a path
   shape. Its inputs are the verdict, the 14-day ATR as a percentage of
   price, the regime label detected for the run date, the report's
   conviction drivers and the median past return for the same verdict (same
   regime first; recent cycles weighted more when forgetting is on). Any
   failure uses the static fallback below.
7. **Paths and rows** (below), the F&O snapshot (section 17) and each
   dimension's catalyst predictions (`agent_predictions`).
8. **Save** the envelope with its `learning_mode`, the report's
   `decision_gate` and its `instrument`.

**Price paths.** `build_monte_carlo_paths` simulates 500 geometric Brownian
motion paths with a fixed seed of 42:

```text
mu_daily    = monthly_return_pct / 100 / n_days
sigma_daily = confidence_band_daily_pct / 100 × REGIME_SIGMA_SCALE[regime]
log return  = (mu − sigma²/2) + sigma × Z,  Z ~ N(0, 1)
row i       : predicted_close = P50, price_lower = P10, price_upper = P90

REGIME_SIGMA_SCALE: MACRO_CRISIS 1.50 · RISK_OFF 1.20 · OVERSOLD 1.10 · NORMAL 1.00
                    MOMENTUM_EXTENDED 0.90 · RISK_ON 0.80
```

The drift is uniform. The profile's `path_shape` (`front_loaded`,
`back_loaded`, `volatile`, `linear`) is stored on the envelope and described
to the feedback agent, but the Monte Carlo path does not use it. The regime
label here is the raw detection for the run date, not the sticky label.

**Confidence per row:**

```text
base       = clamp(report.final_score, 0.10, 1.00)
band_width = (P90 − P10) / P50 × 100
confidence = clamp(base × (1 − 0.004 × i) − max(0, (band_width / 2 − 1) × 0.015), 0.05, 0.99)
             i = 0 for the first row
```

**Per-day adjustments**, in order:

- **Seasonal.** Active seasonal patterns add their agent deltas to that
  row's agent scores and their confidence modifier to its confidence
  (section 14). This applies in both learning modes.
- **Lesson micro-adjustment.** Untagged lessons seen at least twice and
  confirmed within 90 days add up to 0.01 each to the dimensions their
  category maps to, capped at ±0.05 per dimension. A no-op in `observe`.
- **Tagged-lesson emphasis.** Lessons whose trigger tags match the row's
  calendar tags nudge scores (section 23.3). A no-op in `observe`.

Every row carries the same verdict, the report's. Agent scores differ by row
only through these adjustments.

**Static fallback.** When the profile call fails, the monthly return comes
from the verdict, scaled by volatility:

```text
STRONG BUY 8.0 · BUY 4.0 · NEUTRAL 0.5 · SELL −3.0 · STRONG SELL −7.0  (percent per month)
scaled = base × clamp(ATR% / 1.5, 0.5, 2.5),  band = max(0.1, ATR% × 0.5)
```

For example, a BUY on a stock with a 0.8% ATR gets 4.0 × 0.53 = 2.1%, and on
a stock with a 3.5% ATR gets 4.0 × 2.33 = 9.3%.

**In `enforce` mode** an abstained analysis builds no envelope and logs
`InsufficientDataError`. Nothing scheduled retries it before the next
month's run; only a restart's self-heal does. Until then that ticker's
reviews return `no_envelope`. **Planned:** a same-month retry (SA-036).

## 5. Daily review step by step

[daily_review.py](../core/intelligence/rl/workflows/daily_review.py),
`run_daily_review(ticker, session, sector, paper=False)`. The scheduler
passes the previous NSE trading session, so the day after a weekday holiday
reviews the session before the holiday again. The mode is read once, so a
whole review runs under one learning mode.

**Step 0 — regime.** `RegimeDetector` classifies the market (section 13).
The market-wide sticky label is updated from it (section 27.1); outside the
paper lane this write happens on every run, before anything can stop the
review. The sticky label chooses the regime multipliers and is stored on the
feedback entry.

**Step 1 — the row.** The review loads the session's row from its own
month's envelope, else from the previous month's. No envelope returns
`no_envelope`; no row (a holiday) returns `no_forecast_row`.

**Input checks.** The row's provenance and the ticker's identity are checked
next (section 6).

**Step 2 — the close.** `_fetch_session_close` asks yfinance for the
resolved instrument's symbol over a 7-day window, then its BSE listing, then
the one-year price history, and cross-checks the result with NSE's official
close (more than 1% apart, NSE wins). The result names the date of the bar
it came from. No close returns `no_actual_data`; a close from an earlier bar
fails the stale-close check (section 6). The ratio of the session's volume
to its 20-day average is computed for context.

**Step 3 — error and direction.**

```text
price_error_pct   = (actual − predicted) / predicted × 100
actual_direction  = UP if price_error_pct > 0.3, DOWN if < −0.3, else FLAT
direction_correct = BUY/STRONG BUY → UP · SELL/STRONG SELL → DOWN · NEUTRAL → FLAT
```

`actual_direction` is measured against the predicted close (section 1). A
NEUTRAL row is correct only on a FLAT session. The timing assessment
compares the session's day number with the envelope's predicted peak (the
highest predicted close for a bullish verdict, the lowest for a bearish one).

**Step 4 — re-run and feedback agent.**

- When the direction is correct and the absolute error is below 0.5%
  (`rl.agent_rerun_threshold_pct`), the analysis is not re-run: the day's
  scores are the row's own, and the agent is told so.
- Otherwise the orchestrator re-runs with the decision weights. The re-run's
  gate is checked (section 6). With `rl.hard_bind_verdict_enabled` on, the
  session is graded against the re-run's verdict (`graded_verdict`) instead
  of the row's.
- The context for the feedback agent is assembled: company news from the
  last 3 calendar days (dated headlines only); the market-wide macro feed,
  labelled as such, when company news is missing (HIGH and MEDIUM items
  published on the reviewed day or the day before, from files fetched by the
  reviewed day); active seasonal patterns;
  a streak warning at 8 or more days; the regime narrative when not NORMAL;
  the three-tier lesson summary (section 11); recurring blind spots from the
  cycle's prompt enhancements; the F&O snapshot during expiry week;
  yesterday's off-market signals; and NSE institutional flows.
- Event tags for the day come from a keyword map over that context plus
  calendar tags (section 23.3).
- `FeedbackAgent` (reasoning tier, temperature 0.3, JSON output) returns the
  miss type, the blamed dimension, missed factors, score drifts, new lessons
  and a forward outlook. If the call fails, the output is marked degraded
  (`data_gap`, no lessons).
- **External-shock cap.** When the agent says `external_shock` on a wrong
  day, and more than 20% of at least 5 earlier entries this cycle were
  already `external_shock`, the miss is reclassified `direction_flip`.
- **Absurd-error guard.** An absolute error above 50%
  (`rl.absurd_price_error_pct`) is a broken input, such as a stale envelope
  across a split, not a model miss. The miss becomes `data_stale` and no
  weight update runs.

**Step 5 — weights.** The adapter (section 9) sees the cycle's log with
today's provisional entry. In `adapt` mode it writes a new weight version.
In `observe` mode it runs on a copy and records the proposal (section 7).
The paper lane and the absurd-error guard skip it.

**Step 5.5 — regime multipliers.** The decision weights are multiplied by
the sticky regime's multipliers and renormalised (section 13). These
effective weights are used for today's revision only.

**Step 6 — lessons.** New lessons merge into the ticker's ledger, and
sector-wide and market-wide ones propagate to the shared ledgers
(section 11). The paper lane does not propagate.

**Step 6.5 — conviction streak** (section 12).

**Step 7a — thesis review** on significant misses (section 16).

**Re-forecast check** (section 27.2). In the live cycle only, the first
match of `external_shock` on a wrong day, `thesis_break` or `regime_flip`
regenerates the remaining rows. On success, step 7b is skipped and the
updated streak is saved onto the new envelope.

**Step 7b — revision.** Each remaining row is marked revised and its
confidence recomputed; its price and verdict are not changed:

```text
scores     = tagged-lesson emphasis on today's tags (adapt only)
composite  = Σ score[a] × effective_weight[a] / Σ effective_weight
confidence = 0.7 × confidence + 0.3 × composite + horizon_confidence_adjustment
confidence = confidence × (1 − reversion_prior × 0.5)
confidence = confidence × thesis multiplier      (only when below 1.0)
confidence = clamp(confidence, 0.05, 0.99)
```

The feedback agent's headline becomes each row's leading assumption.

**Step 8 — feedback entry.** One entry per date, replacing any earlier
entry for that date. `claims_fired` lists the tagged lessons that matched
today; it stays empty in `observe` mode, where no lesson acts.

**Step 8.5 — dossier curator** (section 23.2), on hit days as well as misses.
After it, today's block deals, bulk deals and pre-open price are saved for
tomorrow's review (section 17).

**Step 9 — seasonal validation**, on the last trading day of the month only
(section 14).

**Step 10 — control lane** (section 25), not in the paper lane.

Finally the review records whether company news was available, and returns a
summary with `status: completed`, the learning mode, the decision weights,
the regime, the streak, any thesis or re-forecast result, and a `data_gate`
list of what enforcement would have stopped.

## 6. Review input checks

The review checks four inputs, in this order, before it writes anything that
depends on them. Each failure is one row in `data/logs/decision_gate.jsonl`
(consumer `daily_review`, or `paper_review`), with its stage, reason and the
row's source run id:

| Stage | Passes when | Example of a failure |
|---|---|---|
| `forecast_row` | The row's `data_gate` is actionable or degraded. | A row issued before stamps existed (`data_gate` empty): provenance unknown. |
| `identity` | The ticker's identity on the session is resolved, and the row's price basis is the session's. | A row stamped on one basis, graded after a demerger started another. |
| `actual_close` | The close comes from the bar dated the session. | A suspended symbol: both providers return the previous day's close. |
| `rerun` | The fresh re-run, when one happens, is actionable. | The re-run's technicals came back empty. |

For an unstamped row, the identity check asks the instrument registry
whether a demerger or relisting lies between the envelope's issue date and
the session. A rename keeps the basis, so it passes. The KT's
[review input checks](TECHNICAL_DESIGN.md#review-input-checks) give the
identity and stale-close examples.

- **In `enforce` mode** the first failure ends the review with
  `status: data_gated`: no grading, feedback agent, weight update or
  proposal, lesson, revision, streak, feedback entry, dossier or control-lane
  step. The sticky regime, written in step 0, is the one write that has
  already happened.
- **In `record` mode** the review runs and lists every failure in its
  summary's `data_gate`. The scheduler then counts it as `degraded`
  (section 8).

**Why.** Learning from a row issued on missing data, or graded on another
company's close, teaches the weights noise: a carried-forward close grades a
day as flat, a zero return that never happened.

## 7. Learning mode

[learning_mode.py](../core/intelligence/rl/learning_mode.py) reads
`rl.learning_mode` (env `RL_LEARNING_MODE`) at call time. The repository
default is `adapt`; an unrecognised value fails closed to `observe` with one
warning per process.

| | `adapt` | `observe` |
|---|---|---|
| Weights decisions aggregate with | The ticker's stored weights | The sector's default table, whatever is stored |
| Daily review's weight step | Writes a new weight version | Runs the adapter on a copy; records the proposal |
| Tagged-lesson emphasis and lesson micro-adjustment | Move agent scores | No-ops |
| `claims_fired` on the feedback entry | Matching tagged lessons | Empty |
| Lessons, dossier, streak, revision, re-forecast | Run | Run |

"Decisions" means every place the decision weights are read: the monthly
forecast, re-forecasts, the review's re-run, its regime-weighted revision,
and public analysis that reads learned weights.

**Example.** A ticker stores `technical = 0.0` at v41, and its sector default
is 0.12. In `observe` mode its forecast aggregates with 0.12. After the
review the file still says 0.0 at v41, and the observation record shows the
v42 the adapter would have written. Switching back to `adapt` resumes v41
unchanged.

**Where the mode shows:** the review's start and completion log lines and
its summary; each envelope's `learning_mode`; `/ui/rl/weights/{ticker}`,
which returns the mode, the live `decision_weights` and the latest
observation; and `/ui/rl/summary/{ticker}`.

**What it does not contain:** regime multipliers, thesis multipliers, the
conviction streak, the prompt enhancements and the dossier text all still
act in `observe` mode.

**Limit.** In `observe` mode each night proposes one step from the same
frozen stored file, so the observation records do not accumulate into a
learner. Rollback of `observe` is removing the environment variable.
**Planned:** a shadow learner that does accumulate, and the conditions for
returning to `adapt` (SA-043; KT section 11).

## 8. Per-ticker review outcomes

The scheduler gives every enabled managed ticker exactly one outcome per run
([review_outcomes.py](../core/intelligence/rl/workflows/review_outcomes.py)),
from what `run_daily_review` returned:

| Review result | Outcome | Counts as output |
|---|---|---|
| `completed`, empty `data_gate` | `completed` | Yes |
| `completed`, non-empty `data_gate` (`record` mode) | `degraded` | Yes |
| `data_gated` (`enforce` mode) | `data_gated` | No |
| `no_envelope`, `no_forecast_row`, `no_actual_data` | `skipped` | No |
| Raised, malformed, or unfinished when the harvest budget ran out | `failed` | No |

The harvest budget is 300 seconds per ticker, in aggregate; finished reviews
stand and the portfolio pipeline still runs. A skip, a gate stop or a failure
fires the partial-output alert, which names the ticker and the reason. A
graded row with unknown provenance therefore reads `degraded` in `record`
mode. The record in `data/scheduler_job_outcomes.json` keeps each ticker's
outcome, reason and attempts; the KT's
[daily-review outcomes](TECHNICAL_DESIGN.md#daily-review-outcomes) give the
holiday merge rule and the limits.

## 9. Weight adapter

[weight_adapter.py](../core/intelligence/rl/agents/weight_adapter.py) is
deterministic. It needs at least 3 entries in the cycle's log
(`rl.weight_min_observations`), counting today's.

**Stage 1 — accuracy.** The window is the last 7 NSE trading days
(`rl.weight_accuracy_window`), counted back from the date the review runs.
For each entry in it, every dimension gets a hit, except the blamed dimension
on a wrong day whose miss type is penalisable:

- correct day: every dimension gets a hit;
- wrong day, miss type `data_gap`, `data_stale` or `external_shock`: every
  dimension gets a hit;
- otherwise: every dimension except the primary miss agent gets a hit.

With the calibration reward on (`rl.calibration_reward_enabled`), each
dimension also earns a calibration hit when its own score's lean (0.5 or more
is bullish) matched the realised direction, on directional verdicts and UP or
DOWN sessions only. The hit rate that drives stage 2 is then
`0.5 × direction rate + 0.5 × calibration rate` (`rl.calibration_weight`).

**Stage 2 — deltas.** Every delta is scaled by the dimension's weight
relative to an equal share, `prop_scale = clamp(w / (1/n), 0.25, 2.0)`, so a
heavy dimension gains and loses weight faster.

- **Hit rate.** At or above 0.70, `+0.02 × prop_scale`; at or below 0.40,
  `−0.03 × prop_scale`. Active seasonal patterns shift both thresholds per
  dimension (section 14).
- **Zero-weight recovery.** A dimension already at exactly 0.0, whose blended
  rate sits between the thresholds but whose plain direction rate reaches
  the boost threshold, gets the boost. Without it, a dimension at 0.0 has
  nothing left to lose and no way back.
- **Bias penalty**, for the blamed dimension on a penalisable miss only. A
  weighted miss rate over 5, 10 and 21 trading days (weights 0.50, 0.30,
  0.20) counts the share of penalisable misses blamed on it:

```text
bias_score < 0.55         no penalty
0.55 ≤ bias_score < 0.70  scale = (bias_score − 0.55) / 0.15
bias_score ≥ 0.70         scale = 1.0
penalty = −0.05 × scale × miss multiplier × prop_scale × factor-regime scale
```

The miss multiplier comes from the taxonomy (section 10); for `timing` it is
0 within 3 trading days of lag, 0.20 within 7, and 0.50 beyond. The
factor-regime scale lightens the penalty for a dimension that the long-run
IIMA factor regime disadvantages: 0.80 for `pattern_analysis` and
`competitive_intel` in a reversal regime, 0.85 for `fundamentals` and
`risk_macro` in a momentum regime, otherwise 1.0. That factor data ends in
March 2023, so it is a static prior, not a live signal.

**Stage 3 — bounds and normalisation:**

```text
delta     = clamp(delta, −0.05, +0.05)                 single step
drift     = 0.15, or min(0.15 × 1.5, 0.35) after 14 consecutive correct entries
weight    = clamp(weight + delta, max(0, base − drift), base + drift)
weights   = weights / Σ weights                        renormalise
```

The renormalisation runs after the clamp, so the final weights can leave
their bounds. **Example:** a dimension with base 0.40 has a ceiling of 0.55
and already sits there. Its boost is clamped to 0.55, and two other
dimensions each lose 0.03, so the weights sum to 0.94. Renormalising lifts it
to 0.55 / 0.94 = 0.585, above its ceiling. The floor is `max(0, base −
0.15)`, so any dimension whose default is 0.15 or less can reach exactly 0.0.
**Planned:** bounds that hold on the final weights (SA-015).

Each update appends a history entry with the new weights, the structured
deltas, the hit rates behind them and a readable reason.

## 10. Miss taxonomy

The feedback agent classifies each miss; the adapter applies the penalty.

| Miss type | Meaning | Bias multiplier | Blamed dimension still gets a hit? |
|---|---|---|---|
| `data_gap` | Data not yet published when the forecast was made | 0.0 | Yes |
| `data_stale` | Outdated data used; also set by the absurd-error guard | 0.0 | Yes |
| `external_shock` | Unforeseeable event; capped at 20% of a cycle's days | 0.0 | Yes |
| `timing` | Right direction, wrong day | 0, 0.20 or 0.50 by lag | No |
| `magnitude` | Right direction, wrong size | 0.25 | No |
| `model_bias` | Systematic over- or under-estimate | 1.0 | No |
| `direction_flip` | Wrong direction with no external cause | 1.0 | No |

A degraded agent output, when the LLM call failed, is `data_gap` and writes
no lessons and no miss counts, so an outage is never learned as a market
pattern.

## 11. Lessons

**Merge into the ticker's ledger.** A lesson whose pattern is already live
gains an occurrence; its confidence becomes the running mean of all its
confirmations; its scope widens if the new one is broader; and it adopts
trigger tags or agent lists it lacks. A new pattern first looks in the cold
store, `<TICKER>_archived_lessons.json`; an archived lesson with that pattern
is resurrected with its history instead of being duplicated. Missed factors
increment the miss counter only when they look like a factor name
(lower-case letters, digits and underscores, 3 to 40 characters), so an
error message never becomes a factor.

**Propagation.** A `sector_wide` lesson is also merged into
`<sector>/_shared_ledger.json`, and a `market_wide` one into both shared
ledgers. A shared lesson blends confidence as `0.7 × existing + 0.3 ×
incoming`, and gains +0.05 the first time each new ticker confirms it, so a
single active ticker cannot make a pattern look like sector truth.

**What the feedback agent sees.** Three tiers, each sorted by effective
confidence and excluding anything below 0.20: up to 6 stock-specific lessons,
3 sector-wide and 2 market-wide.

**Decay.** A lesson's effective confidence decays with months since it was
last seen:

```text
rate       = max(0.002, category rate / sqrt(occurrences))
confidence = max(0.10, stored × (1 − rate) ^ months_inactive)

category rate per month: seasonal 0 (exempt) · data_availability 0.005 · fundamental 0.008
                         technical 0.015 · sentiment 0.020 · macro 0.030 · global_macro 0.040
```

**Example:** a macro lesson at 0.75, unseen for 3 months, confirmed once
(rate 0.030) reads 0.75 × 0.97³ = 0.68; confirmed 9 times (rate 0.010) it
reads 0.73. Repeated confirmation makes a pattern behave as structural.

**Weekly cleanup** (Mon 03:30, `ledger_cleanup_weekly`), for each enabled
ticker:

- a lesson confirmed by only one ticker is downgraded from market-wide to
  sector-wide after 30 days unseen, and invalidated as sector-wide after 60;
  lessons with several contributing tickers are never downgraded;
- the ticker's own copies follow the shared ledgers' downgrades;
- invalidated lessons that are also stale (60 days unseen) and weak
  (effective confidence at or below 0.12) move to the cold store. The rule
  also asks for effectiveness below 0.25, read from a correction counter
  that nothing writes, so that test always passes;
- the dossier is distilled (section 23.2).

**How lessons act.** Free-text rules are context for the LLM only and are
never parsed. Lessons move numbers in two places, both no-ops in `observe`
mode: tagged lessons through emphasis (section 23.3), and untagged lessons
through the month-start micro-adjustment (section 4).

## 12. Conviction streak and reversion prior

[tracker.py](../core/intelligence/rl/conviction/tracker.py). The streak
counts consecutive reviewed sessions whose row verdict points the same way.
NEUTRAL resets it to 0; a flip starts it again at 1. Because every row of an
envelope carries the same verdict, the streak mostly measures how long the
current envelope has been reviewed.

```text
base prior  = min(0.25, max(0, (streak_days − 4) × 0.025))
amplifier   = 1.5 when streak_days ≥ 8 and the sector RSI contradicts the streak
              (bullish streak with RSI > 70, bearish streak with RSI < 30), else 1.0
final prior = min(0.30, base prior × amplifier)
```

| Streak days | 0–4 | 5 | 6 | 8 | 12 | 14+ |
|---|---|---|---|---|---|---|
| Base prior | 0 | 0.025 | 0.05 | 0.10 | 0.20 | 0.25 |

The final prior dampens remaining confidence by `× (1 − prior × 0.5)` in
step 7b: a prior of 0.25 cuts it by 12.5%. From 8 days, a warning block asks
the feedback agent to check for momentum exhaustion.

## 13. Regime detection and multipliers

[detector.py](../core/intelligence/regime/detector.py) uses three signals,
each with a neutral fallback when the fetch fails:

- India VIX (`^INDIAVIX`, fallback 17.0);
- the Nifty 50's 5-session move as a proxy for foreign flows (`^NSEI`,
  fallback 0.0);
- the sector index's 14-day RSI (fallback 50.0): automobile `^CNXAUTO`,
  banking/BFSI `^NSEBANK`, IT `^CNXIT`, renewable energy `^CNXENERGY`, any
  other sector `^NSEI`. An index with no data falls back to `^NSEI`.

The first matching rule wins:

| Order | Label | Condition |
|---|---|---|
| 1 | `MACRO_CRISIS` | VIX > 22 and Nifty 5-session < −1.0% |
| 2 | `RISK_OFF` | VIX > 22, or VIX 14–22 and Nifty 5-session < −1.0% |
| 3 | `MOMENTUM_EXTENDED` | VIX < 14, Nifty 5-session > +1.0% and RSI > 70 |
| 4 | `RISK_ON` | VIX < 22, Nifty 5-session > +1.0% and RSI < 70 |
| 5 | `OVERSOLD` | RSI < 30 |
| 6 | `NORMAL` | Anything else |

**Global stress escalation.** Three more signals are checked: Brent's
5-session move at or above +8%, USD/INR's at or above +1.5%, and the S&P 500's
last session at or below −2%. When two or more fire, the label moves one
notch toward crisis: `RISK_OFF` becomes `MACRO_CRISIS`, and any calm label
becomes `RISK_OFF`. A single signal never escalates, and a failed fetch never
counts.

**Multipliers** (`regime_multipliers` in config.yaml) use the automobile
dimension names. Other sectors map their dimensions to those names through
`sector_agent_regime_role`; an unmapped dimension stays at 1.0.

| Dimension | MACRO_CRISIS | RISK_OFF | NORMAL | RISK_ON | MOMENTUM_EXT | OVERSOLD |
|---|---|---|---|---|---|---|
| risk_macro | 1.40 | 1.20 | 1.00 | 0.90 | 0.85 | 1.10 |
| fundamentals | 0.80 | 0.90 | 1.00 | 1.10 | 1.05 | 1.00 |
| sales_demand | 0.70 | 0.85 | 1.00 | 1.10 | 0.95 | 1.00 |
| sentiment | 0.80 | 0.90 | 1.00 | 1.15 | 0.80 | 0.90 |
| pattern_analysis | 0.90 | 0.95 | 1.00 | 0.95 | 1.20 | 1.30 |
| valuation_catalyst | 0.90 | 0.95 | 1.00 | 1.10 | 1.10 | 1.05 |
| competitive_intel, raw_materials, policy_regulatory | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

```text
effective[a] = weight[a] × multiplier[role(a)] / Σ (weight × multiplier)
```

**Why ephemeral.** Weight memory tracks long-run accuracy; the regime can
flip within days. Writing multipliers into the stored weights would mix the
two, so they are applied to each day's revision and discarded.

**Limit.** The detector reads the latest values, not values as of the
reviewed session, so a backfill of an old session uses today's regime.

## 14. Seasonal calendar

[calendar.py](../core/intelligence/seasonal/calendar.py) merges two layers:
patterns seeded by hand in `core/intelligence/seasonal/seeds/<sector>.yaml`,
and lessons in the ticker's ledger with category `seasonal`. Only the four
native sectors have seed files.

| Sector | Seeded patterns (months) |
|---|---|
| Automobile | December model clearance (12); Navratri–Diwali festive peak (10–11, lunar); Shravan demand dip (7–8, lunar); March wholesale push (3); Union Budget week (1); September pre-festive wait (9) |
| Banking/BFSI | March year-end credit surge (3); RBI MPC meeting week (even months); Budget PSU-bank risk (2); Q1 NPA recognition and results (4–5) |
| IT | US tech earnings spillover (1, 4, 7, 10); Q1 salary-hike margin pressure (4–5); Q1 client budget softness (4–6); H-1B result season (4) |
| Renewable energy | Monsoon solar generation dip (6–9); peak irradiation season (4–5); year-end government project push (10–12); Q1 tariff orders (1–2) |

Each sector also has an F&O expiry-week pattern, which applies during the 5
trading days up to the monthly expiry instead of by month.

**Rules:**

- deltas of all active patterns are summed and capped at ±0.20 per dimension;
  a lunar pattern counts at half weight, because its Gregorian dates move;
- the confidence modifier is capped at ±0.10; expiry week adds −0.05, or
  −0.08 on expiry day itself, within the same cap;
- the same patterns shift the adapter's hit-rate thresholds per dimension
  (section 9), and their narrative is given to the feedback agent with an
  instruction not to rediscover them as lessons.

**Validation.** On the last trading day of a month, each pattern active that
day is compared with the month's feedback log. Two confirming cycles mark it
validated; three contradicting cycles mark it invalidated. The state is
written to `<sector>/_seasonal_validation.json`. A matching seasonal lesson in
the ticker's ledger is then invalidated, or gains +0.05 confidence when
validated. **Limit:** the calendar does not read the validation state, so an
invalidated seed keeps applying its deltas.

## 15. Prompt enhancer

[enhancer.py](../core/intelligence/prompt_enhancer/enhancer.py) runs once
at month start. It takes the three most frequent factors in the ledger's
miss counter. A recency-weighted ranking exists for structured miss events,
but no writer records those events, so the raw counter decides. For each
factor and
dimension it looks up a query template: the sector's own map first (banking,
IT and renewable energy each have about 10 factors), then the cross-sector
map, then one bulk-tier LLM call. The queries are saved as the cycle's
`prompt_enhancements.json`.

Two consumers read them: the feedback agent's context, as "recurring blind
spots", and the legacy per-dimension agents, which add up to 2 queries to
their searches. The unified analyst, the preferred research path, does not
read them. The loop is self-regulating: a factor that stops being missed
falls out of the top three.

## 16. Thesis review

[thesis_reviewer.py](../core/intelligence/rl/agents/thesis_reviewer.py)
asks whether the envelope's key assumptions still hold after a significant
miss. It fires when:

- the direction was wrong and the miss is `direction_flip` or `model_bias`; or
- the absolute error exceeds `max(1.5, 1.5 × ATR%)`, so a volatile stock
  needs a larger miss.

One reasoning-tier call (temperature 0.1) returns the invalidated and intact
assumptions, whether the thesis is intact, and a
`horizon_confidence_multiplier` between 0.3 and 1.0. Below 1.0, the multiplier
cuts every remaining row's confidence (step 7b); at or below 0.5 it also
triggers a re-forecast (section 27.2). Any failure returns an intact thesis
with multiplier 1.0. Each review is stored on the feedback entry and appended
to the store's `thesis_calls.jsonl`.

**Example:** a remaining row at confidence 0.60, after a review that finds
the low-input-cost assumption broken (multiplier 0.70), drops to 0.42.

## 17. Market-structure signals

| Signal | Source and rule | Where it is used |
|---|---|---|
| F&O expiry | The last Thursday of the month, moved back over NSE holidays; expiry week is the 5 trading days up to it | Seasonal overlay (section 14); calendar event tag |
| Options snapshot | Near-month chain at month start: put-call ratio (below 0.7 reads bullish, above 1.5 bearish), max pain, and open-interest build-up (ATM calls or puts above 1.3× the other: LONG or SHORT) | Stored on the envelope; given to the feedback agent during expiry week |
| Block and bulk deals, pre-open price | Fetched after each review and saved per date; the net institutional direction is BUY or SELL when one side's value exceeds 1.5× the other, else MIXED | Next day's feedback-agent context |
| Institutional flows | NSE FII/DII net figures and bulk deals for the day | Feedback-agent context |
| Volume ratio | The session's volume over its 20-day average | Feedback-agent context and the feedback entry |

## 18. Schemas

Pydantic models in
[schemas/feedback.py](../src/backend/shared/schemas/feedback.py);
`core/schemas/feedback.py` re-exports them.

| Schema | Holds | Lifetime |
|---|---|---|
| `DailyForecast` | One row: closes and band, verdict, agent scores, confidence, assumptions, catalysts, `data_gate`, `source_run_id`, `instrument` | Per cycle |
| `PredictionEnvelope` | The rows plus streak, `learning_mode`, `decision_gate`, `instrument`, profile, F&O snapshot, re-forecast history | Per cycle |
| `ReforecastEvent` | Date, reason, trigger and archived file of one re-forecast | In envelope |
| `ConvictionStreak` | Verdict, streak days and start, maximum seen, reversion prior | In envelope |
| `FeedbackEntry` | One graded session (section 3.4) | Per cycle |
| `MissAnalysis`, `TimingAccuracy`, `RevisedContext`, `ThesisReview` | Parts of a feedback entry | Per entry |
| `WeightMemory`, `AgentAccuracy`, `WeightHistoryEntry` | Weights, accuracy, history (section 3.5) | Permanent |
| `LearningLedger`, `Lesson`, `MissEvent` | Lessons, miss counters and structured miss events | Permanent |
| `TickerDossier` and its parts | Company knowledge (section 23.1); in `schemas/dossier.py` | Permanent |
| `ControlLog` | Control-lane calls (section 25); in `schemas/scorecard.py` | Per cycle |
| `FeedbackAgentInput`, `FeedbackAgentOutput`, `RawLesson` | The feedback agent's contract | Per call |
| `RegimeSnapshot`, `SeasonalPattern`, `SeasonalContext` | Regime and seasonal context | Per call |
| `OffMarketSignals`, `FnOSnapshot` | Market-structure data (section 17) | Per date or cycle |

## 19. Configuration reference

The `rl:` and `regime:` sections of [config.yaml](../config.yaml), read by
[settings](../src/backend/shared/config/settings/base.py). Most values are
read at import, so a change needs a restart. The KT
[section 3](TECHNICAL_DESIGN.md#configuration) explains precedence.

| Key (env override) | Default | Controls |
|---|---|---|
| `rl.learning_mode` (`RL_LEARNING_MODE`) | `adapt` | Section 7 |
| `rl.forecast_horizon_days` | 30 | Rows per envelope |
| `rl.weight_max_step`, `rl.weight_max_drift` | 0.05, 0.15 | Stage 3 bounds |
| `rl.weight_min_observations`, `rl.weight_accuracy_window` | 3, 7 | Stage 1 |
| `rl.weight_boost_hit_rate`, `rl.weight_penalty_hit_rate` | 0.70, 0.40 | Stage 2 thresholds |
| `rl.boost`, `rl.penalty`, `rl.miss_streak_penalty` | +0.02, −0.03, −0.05 | Stage 2 magnitudes |
| `rl.bias_trigger`, `rl.bias_full`; `rl.bias_windows` / `rl.bias_window_weights` | 0.55, 0.70; [5, 10, 21] / [0.50, 0.30, 0.20] | Bias penalty |
| `rl.timing_free_window`, `rl.timing_partial_window` | 3, 7 | Timing multiplier |
| `rl.weight_drift_escape_days`, `rl.weight_drift_escape_multiplier` | 14, 1.5 | Drift escape |
| `rl.calibration_reward_enabled`, `rl.calibration_weight` | true, 0.5 | Calibration blend |
| `rl.zero_weight_recovery_enabled` | true | Zero-weight recovery |
| `rl.hard_bind_verdict_enabled` | true | Grading against the re-run verdict |
| `rl.flat_threshold_pct` | 0.3 | UP/DOWN/FLAT band |
| `rl.agent_rerun_threshold_pct` | 0.5 | Skip the re-run below this error on a correct day (0 disables) |
| `rl.absurd_price_error_pct` | 50.0 | Absurd-error guard |
| `rl.macro_fallback_context_enabled`, `rl.macro_fallback_max_items` | true, 5 | Macro feed for news-blind reviews |
| `rl.provenance_enabled`, `rl.lesson_evidence_max_items`, `rl.lesson_evidence_max_chars` | true, 3, 160 | Lesson and observation evidence |
| `rl.streak_warning_threshold`, `rl.rsi_amplifier`, `rl.max_reversion_prior` | 8, 1.5, 0.30 | Section 12 |
| `rl.atr_threshold_floor`, `rl.atr_threshold_multiplier` | 1.5, 1.5 | Thesis-review size trigger |
| `rl.lesson_blend_existing`, `rl.lesson_blend_incoming`, `rl.cross_ticker_boost` | 0.70, 0.30, 0.05 | Shared-ledger merge |
| `rl.forgetting_enabled`, `rl.miss_recency_halflife_days`, `rl.miss_penalizable_discount` | true, 21, 0.3 | Recency-weighted misses |
| `rl.archive_conf_floor`, `rl.archive_effectiveness_floor`, `rl.archive_stale_days` | 0.12, 0.25, 60 | Lesson archiving |
| `rl.feedback_halflife_months` | 3.0 | Weighting of past cycles' returns |
| `rl.dossier_enabled`, `rl.claims_enabled` | true, true | Sections 23.2 and 23.3 |
| `rl.dossier_max_observations`, `rl.dossier_max_new_obs_per_day` | 30, 3 | Observation buffer |
| `rl.dossier_digest_max_chars`, `rl.dossier_agent_digest_chars`, `rl.dossier_distill_input_max_chars` | 2500, 1500, 20000 | Digest budgets |
| `rl.lesson_emphasis_delta`, `rl.lesson_emphasis_cap`, `rl.lesson_match_min_conf` | 0.03, 0.06, 0.45 | Section 23.3 |
| `rl.event_ingest_enabled`, `…_lookback_days`, `…_max_events_per_scan`, `…_text_max_chars` | true, 8, 3, 6000 | Section 26 |
| `rl.research_loop_enabled`, `rl.research_max_questions_per_run`, `rl.research_max_attempts` | true, 2, 3 | Research loop |
| `rl.control_lane_enabled`, `rl.control_lane_model`; `rl.scorecard_enabled` | true, "" (reasoning tier); true | Section 25 |
| `rl.reforecast_enabled`, `rl.reforecast_max_per_month`, `rl.reforecast_thesis_mult_threshold` | true, 2, 0.5 | Section 27.2 |
| `rl.regime_sticky_enabled`; `regime.calm_days` (`RL_REGIME_CALM_DAYS`) | true; 3 | Section 27.1 |
| `rl.preopen_check_enabled`, `rl.preopen_shock_severity` | true, 0.7 | Section 27.3 |
| `rl.close_verify_enabled`, `rl.close_verify_tolerance_pct` | true, 1.0 | NSE close cross-check |
| `rl.scheduler_max_workers` (`RL_SCHEDULER_MAX_WORKERS`) | 1 | Parallel reviews |
| `regime.vix_volatile_threshold`, `regime.vix_low_vol_threshold` | 22.0, 14.0 | Section 13 |
| `regime.fii_proxy_threshold_pct`, `regime.rsi_overbought`, `regime.rsi_oversold` | 1.0, 70, 30 | Section 13 |
| `scheduler.feedback_cron` (`FEEDBACK_CRON`) | `30 16 * * mon-fri` | Daily review time, IST |

Storage roots: `PREDICTION_DATA_DIR` (`data/predictions`), the paper root
`discovery.paper_data_dir` (`data/rl/paper/predictions`), `SCORECARD_DIR`
(`data/eval/scorecards`) and `LEARNING_EVIDENCE_DIR`
(`data/eval/learning_evidence`).

## 20. Jobs, CLI and API

**Scheduled jobs.** The RL jobs are `rl_monthly_forecast`, `rl_daily_review`,
`preopen_shock_check`, `event_ingest_weekly`, `research_loop_weekly`,
`ledger_cleanup_weekly`, `scorecard_monthly` and `rl_calendar_update`
(31 December, 23:00). The KT's
[job table](TECHNICAL_DESIGN.md#9-scheduled-jobs-and-event-hooks) has every
job and time. The daily review runs reviews one at a time by default.

**Startup self-heal** ([server.py](../services/api/server.py)), in the
background owner worker. For each enabled managed ticker, in its managed
sector, once per month (a checkpoint file per month records progress):

1. if the month's envelope is missing, generate it;
2. review every trading day from the 1st to yesterday that has no feedback
   entry.

A ticker that fails is retried on the next restart. A missing NSE holiday
file is fetched at startup.

**CLI** (`python -m services.scheduler.run_schedule <command>`):
`start`, `run-now`, `status`, `history`, `latest`, `forecast`,
`daily-review`, `feedback-status`, `reforecast`, `preopen-check`,
`dossier-status`, `ingest-events`, `research` and `scorecard`. `forecast`
and `daily-review` take no sector: they use the automobile graph and store
(KT store class `automobile_default`), and default to `SCHEDULER_TICKERS`.
For any other ticker, use the scheduler API, which takes each ticker's
managed sector.

**Scheduler API** (`/scheduler`), owner session or the `X-Scheduler-Key`
header matching `SCHEDULER_KEY`:

| Method and path | Effect |
|---|---|
| `POST /scheduler/forecast` | Generate envelopes, optionally for one ticker. Accepted for background work (202). |
| `POST /scheduler/daily-review` | Review one date, optionally one ticker, then run the portfolio pipeline. |
| `POST /scheduler/backfill` | Review every past trading day of the current or a named month; `skip_existing` leaves reviewed dates alone. |

Both review routes skip a watchlist-cadence ticker except on Fridays
(`portfolio.weekly_review_weekday`); the scheduled 16:30 job reviews every
enabled ticker every weekday.
| `GET /scheduler/status` | Per-ticker RL state: envelope, entry count, weight version, accuracy, drift. |

**Managed tickers** (`/ui/tickers/managed`, owner only):

| Method and path | Effect |
|---|---|
| `GET` | The list, with sector and enabled flag. |
| `PUT` | Replace the whole list; each sector must be an enabled sector. |
| `POST /{sym}` | Add a ticker and generate its envelope in the background. The sector registry's answer wins over the requested sector, except when the registry only defaulted to automobile. |
| `POST /{sym}/generate-envelope` | Generate an envelope now, for a mid-month addition. |
| `PATCH /{sym}/toggle` | Enable or disable; history is kept. |
| `DELETE /{sym}` | Remove and **delete** `data/predictions/<sector>/<sym>/`. |

The scheduler reads the list on every run, so changes need no redeploy. A
retired ticker is disabled, never removed, so its history survives.

**RL monitor** (`/ui/rl`): `tickers`, `summary/{ticker}`,
`predictions/{ticker}`, `weights/{ticker}` and `misses/{ticker}`. The
summary and weights views show the learning mode; the weights view also
shows the live decision weights and the latest observation.

## 21. Static versus LLM boundary

Model tiers come from `llm:` in config.yaml, each overridable by environment:
fast `qwen/qwen3.6-flash`, reasoning `z-ai/glm-5.2`, bulk
`deepseek/deepseek-v4-flash`. Production's values are not recorded here.

| Component | File | Kind | Notes |
|---|---|---|---|
| `RegimeDetector.detect` | `core/intelligence/regime/detector.py` | Static | Section 13 |
| `update_sticky_regime` | `core/intelligence/regime/state.py` | Static | Section 27.1 |
| `WeightAdapter.update` | `core/intelligence/rl/agents/weight_adapter.py` | Static | Section 9 |
| `classify_direction`, `is_direction_correct` | `core/intelligence/rl/agents/feedback_agent.py` | Static | Section 5, step 3 |
| `merge_lessons_into_ledger`, propagation, decay, cleanup | `feedback_agent.py`, `stores/ledger_propagator.py` | Static | Section 11 |
| Conviction streak | `core/intelligence/rl/conviction/tracker.py` | Static | Section 12 |
| Seasonal calendar and validator | `core/intelligence/seasonal/` | Static | Section 14 |
| Monte Carlo paths, confidence decay | `rl/algorithms/price_interpolator.py` | Static | Section 4 |
| `tag_events`, `apply_lesson_emphasis` | `schemas/feedback.py`, `rl/algorithms/lesson_emphasis.py` | Static | Section 23.3 |
| `to_digest`, `open_guidance` | `src/backend/shared/schemas/dossier.py` | Static | Section 23.1 |
| `FeedbackAgent.run` | `rl/agents/feedback_agent.py` | LLM, reasoning tier, temperature 0.3 | Degraded output on failure |
| `ThesisReviewer.review` | `rl/agents/thesis_reviewer.py` | LLM, reasoning tier, temperature 0.1 | Intact thesis on failure |
| `PriceInterpolator.get_profile` | `rl/algorithms/price_interpolator.py` | LLM, bulk tier | Static fallback |
| `PromptEnhancer` fallback queries | `core/intelligence/prompt_enhancer/enhancer.py` | LLM, bulk tier | Only when no template matches |
| `DossierCurator.run`, `distill_dossier` | `rl/agents/dossier_curator.py` | LLM, bulk tier, temperature 0.2 | Static merge enforces every bound |
| `EventIngestor` | `rl/agents/event_ingestor.py` | LLM, bulk tier | Same merge as the curator |
| `QuestionResearcher` | `rl/agents/question_researcher.py` | LLM, bulk tier | Section 23.2 |
| `run_control_lane_step` | `rl/agents/control_lane.py` | LLM, `rl.control_lane_model` or reasoning tier | Section 25 |
| `run_preopen_check` | `rl/workflows/preopen_check.py` | LLM, fast tier | Section 27.3 |

## 22. Limits and planned work

- **Label and timing.** The graded direction is error direction; hard-bind
  can grade against a verdict computed after the outcome; and a revised or
  re-forecast row replaces the evidence behind the earlier decision.
  **Planned:** SA-012, SA-013 and SA-014.
- **Weight bounds and idempotency.** Final weights can leave their bounds,
  and a second review of the same session updates learning state again.
  **Planned:** SA-015.
- **Credit assignment.** Blame goes to one dimension per miss, and shared
  lessons inherit that attribution. **Planned:** SA-016, SA-017.
- **Reference dates.** The adapter's windows count back from the run date,
  and the regime and company news are current values, so a backfill of an
  old session is graded with today's context.
- **Coverage.** The pre-open check scans the four native sectors' built-in
  ticker lists, not the managed list (section 27.3). The calendar ignores
  seed validation (section 14). The unified analyst does not read prompt
  enhancements, and no writer records the miss events that the
  recency-weighted ranking reads (section 15).
- **Control lane.** It is scored on the same error-direction label, so its
  edge measures the same defect (section 25).
- **Evidence of benefit.** No measurement here shows that adaptation beats
  the defaults. **Planned:** matched cohorts, effective samples and
  calibration checks (SA-018 to SA-021), prospective experiments (SA-022),
  lessons on probation (SA-023) and a shadow learner (SA-043).

---

## 23. Knowledge Layer — Ticker Dossier and Executable Claims

The numeric loop calibrates weights. The knowledge layer keeps what the
system learns about each company: its story, its guidance, how its price
responds to recurring triggers, and open questions. It also gives lessons a
way to act on matching days.

### 23.1 TickerDossier

`data/predictions/<sector>/<TICKER>/<TICKER>_dossier.json`, schema in
[dossier.py](../src/backend/shared/schemas/dossier.py):

| Section | Content | Maintained by |
|---|---|---|
| `business_summary` | 2–4 sentences | Event ingestion, distillation |
| `current_thesis`, `thesis_since` | Stance and reason | Curator |
| `response_signatures[]` | Trigger tags → typical price response, with occurrences, contradictions, confidence and evidence dates | Curator (confirm, create, contradict), distillation |
| `guidance[]` | Management guidance with date, source and status (open, met, missed, withdrawn); the newest 20 | Curator, event ingestion, distillation (withdraws) |
| `recurring_catalysts[]` | Name, timing, effect and hit rate; up to 10 | Curator adds, distillation rates |
| `flow_notes` | Institutional flow trend | Curator, distillation |
| `open_questions[]` | Questions with research attempts and answers; the newest 12 | Curator raises, research loop answers |
| `observations[]` | Dated facts with tags, materiality, hit/miss link and source; the newest 30 | Curator, event ingestion, research loop |
| `ingested_event_keys[]` | Watermark of digested NSE events; the newest 40 | Event ingestion |

A signature is dead once its contradictions reach its occurrences: it leaves
the digest and is dropped at distillation.

**Dates.** No writer dates a row after the run that wrote it. The curator
dates rows with the reviewed session; event ingestion with the event's own
day, and only for events on or before the scan (section 26). Older rows
written before that rule can still carry a future board-meeting date, and
stored rows are not rewritten. So every reader filters by date instead:

- `open_guidance(as_of)` returns open items dated on or before `as_of`, in
  stored order, the latest learned last;
- `to_digest(max_chars, as_of)` renders, in priority order and whole sections
  only: business, thesis, the 8 most confident live signatures, the last 5 of
  `open_guidance(as_of)`, up to 6 catalysts, flows, up to 4 open questions,
  and the last 5 observations dated on or before `as_of`. `as_of` defaults to
  today.

**The morning brief.** Its earnings-watch line for a holding with results in
the next 3 trading days is the last item of `open_guidance` as of the day
**before** the brief's date. The brief goes out at 08:50, before any weekday
dossier writer runs (the curator runs inside the 16:30 review; event
ingestion and research run on Saturdays). So a row dated the brief's own day
can only be an old future-dated one, and the earnings window includes the
meeting day.

**Example:** a held stock has results on Tue 27 Oct. Its dossier holds open
guidance dated 15 Sep and an old item dated 27 Oct. The briefs of Mon 26 and
Tue 27 Oct both show the 15 Sep item. The cost of the rule: a brief triggered
by hand after the 16:30 review leaves out that day's new guidance until the
next day.

### 23.2 Curator, distillation and research

**Daily curator** (step 8.5, [dossier_curator.py](../core/intelligence/rl/agents/dossier_curator.py)).
One bulk-tier call (temperature 0.2, at most 900 tokens) reads the session's
outcome, the miss analysis, the day's context and the current digest. It runs
on hit days too, and records what worked. The LLM proposes; a static merge
enforces every bound:

- at most 3 new observations a day, chosen by materiality, with tags from
  `EVENT_TAGS` only; the buffer keeps the newest 30;
- confirming a signature adds an occurrence and +0.05 confidence (cap 0.95);
  contradicting it subtracts 0.10;
- guidance, catalyst and question lists keep their caps (section 23.1);
- any failure leaves the dossier unchanged.

**Weekly distillation**, inside `ledger_cleanup_weekly` (Mon 03:30). One
bulk-tier pass folds old observations into durable sections, refreshes the
business summary and flows, rates catalysts, creates or drops signatures,
withdraws stale guidance, marks resolved questions and bumps the version.
Without the LLM, only dead signatures are dropped and the buffer is capped.

**Research loop** (`research_loop_weekly`, Sat 11:00,
[question_researcher.py](../core/intelligence/rl/agents/question_researcher.py)).
Up to 2 open questions per ticker, fewest attempts first: one news search
each, and one Tavily page per run as a fallback. One batched bulk-tier call
judges them. An answered question is resolved and adds an observation whose
source is the search result behind it; a partial finding adds an
observation; anything else records an attempt. A question unanswered after
3 attempts is closed as expired. The research loop writes no guidance.

### 23.3 Executable claims

`EVENT_TAGS` is a controlled vocabulary of 17 tags: `central_bank_event`,
`fii_flow`, `crude_price`, `currency`, `earnings_event`, `guidance_change`,
`sector_policy`, `technical_pattern`, `seasonal`, `credit_event`,
`supply_chain`, `regulatory`, `global_macro`, `expiry_week`, `block_deal`,
`monsoon` and `budget_event`.

```text
day tags = tag_events(context)        keyword map; short keywords match whole words only
         ∪ calendar_day_tags(date)    monsoon (Jun–Sep), budget (25 Jan–7 Feb),
                                      festive (Oct–Nov), expiry week

a lesson fires when: still valid, trigger_tags ∩ day tags ≠ ∅,
                     effective confidence ≥ 0.45
each firing lesson:  +0.03 to its prioritise_agents, −0.03 to its discount_agents
per dimension cap:   ±0.06 per day; scores stay within [0, 1]
```

Emphasis applies to a row's agent scores in step 7b (today's tags) and at
month start (each row's calendar tags). Tagged lessons skip the older
category micro-adjustment, so nothing counts twice. Both are no-ops in
`observe` mode. The feedback entry's `claims_fired` lists the firing lessons
in `adapt` mode; the scorecard splits accuracy by it.

**Why tags, not text.** A lesson's free-text rule was never executed. A tag
is deterministic and independent of the LLM, so the same day always fires the
same lessons, and a stored number would go stale as weights move.

### 23.4 Consumption

| Reader | What it gets |
|---|---|
| Unified analyst | The bundle's `dossier` section: the 1,500-character digest, once per analysis, read from the analysis graph's store |
| Legacy per-dimension agents | The same digest appended to each agent's system prompt |
| Curator | The 2,500-character digest |
| Chat | The `get_ticker_dossier(ticker)` tool: a 2,000-character digest from the first sector directory holding that ticker's dossier |
| Morning brief | The earnings-watch line (section 23.1) |
| Operators | `run_schedule dossier-status`: size, version and staleness per ticker |

### 23.5 Cost and safety

The curator adds one LLM call per ticker per review, distillation one per
ticker per week, and the research loop one per ticker per week. Every
step is non-fatal and behind its flag; with `rl.dossier_enabled` and
`rl.claims_enabled` off, the loop runs without the knowledge layer. All
writes go through the store's atomic write.

### 23.6 Out of scope

No embeddings or vector retrieval (tag matching comes first), no
fine-tuning, and no dossier screen: the dossier is read through the chat
tool, the digest and the brief.

## 24. Measurement harness

[core/intelligence/rl/eval/](../core/intelligence/rl/eval/) holds a
read-only replay harness and two adapter extensions.

- **Eval harness:** `python -m core.intelligence.rl.eval.run_eval
  [--synthetic]`. It replays recorded envelopes and feedback, or a synthetic
  history, into direction accuracy, Brier score, a reliability table, band
  coverage and mean absolute error, per ticker and per sector. It never
  writes under `data/predictions`. Its ablation keys (`calibration_reward`,
  `forgetting`, `executable_claims`) produce a before/after delta on
  synthetic data only; recorded history cannot be re-run.
- **Calibration reward** (section 9, stage 1): a dimension also earns credit
  when its own lean was right, independent of the ensemble verdict.
- **Forgetting:** lesson archiving with resurrection (section 11),
  recency-weighted past returns for the forecast profile (half-life 3
  months), and a recency-weighted miss ranking (half-life 21 days). The
  ranking reads structured miss events, which no writer records, so it has
  no effect (section 15).

Each extension has a flag (section 19); switching one off restores the plain
counters.

## 25. Monthly Scorecard, Baseline Duel and Learning Evidence

**Control lane** (step 10, [control_lane.py](../core/intelligence/rl/agents/control_lane.py)).
A bare model gets the session's close and the same context string the review
assembled: no dimensions, weights, lessons or dossier. It predicts the next
session's direction (UP, DOWN or FLAT, with confidence). The next review
scores yesterday's call. Calls are stored in the month they predict for, in
`<TICKER>_<YYYY-MM>_control_log.json`. The control is scored against the
feedback entry's `actual_direction`, which measures the actual close against
StockAgent's *predicted* close. Its edge therefore inherits the grading
defect: it is not a comparison of market-direction calls.

**Naive baselines** ([baselines.py](../core/intelligence/rl/eval/baselines.py)):
persistence (repeat the previous session's direction) and always-up, on the
same label.

**Monthly scorecard** ([scorecard.py](../core/intelligence/rl/eval/scorecard.py)),
`scorecard_monthly` on the calendar first at 02:00 for the previous month,
or `run_schedule scorecard [--month YYYY-MM] [--ticker …]`. Per ticker and
pooled: agent, control, persistence and always-up lanes; edges over the
control and persistence; band coverage; error; the claim-day split; dossier
health; and deltas from the previous month. Saved to
`data/eval/scorecards/<YYYY-MM>_scorecard.json`.

**Learning evidence report** ([learning_evidence.py](../core/intelligence/rl/eval/learning_evidence.py)),
run inside the same job, emailed, and saved under
`data/eval/learning_evidence/`; on demand with
`python -m core.intelligence.rl.eval.learning_evidence --month YYYY-MM
[--months-back N] [--email]`. It replays each logged day's frozen agent
scores under three weightings: the adapted weights in force before that day,
the base weights and uniform weights. Each goes through the same
composite-to-verdict map. It reports how often the verdicts diverge and the
paired lift with an exact sign test, plus credit degeneracy, weight entropy,
per-lesson lift and a Brier decomposition. The verdict is one of
`LEARNING_INERT`, `LEARNING_ACTIVE_BENEFICIAL`, `LEARNING_ACTIVE_HARMFUL`,
`LEARNING_ACTIVE_UNPROVEN` or `INSUFFICIENT_DATA`. This is a retrospective
replay on the existing label, not a prospective experiment.

## 26. Event-Driven Dossier Ingestion

[event_ingestor.py](../core/intelligence/rl/agents/event_ingestor.py),
`event_ingest_weekly` (Sat 10:00) or `run_schedule ingest-events [--ticker …]
[--days N]`.

- **Scan (static).** NSE announcements and board meetings within the last 8
  days whose subject names results, a con-call, a transcript, guidance, an
  investor presentation, a dividend or similar. Only events dated on or
  before the scan qualify. An event announced for a later date is skipped,
  left out of the watermark and the 3-event cap, and digested by the first
  scan on or after its date. The watermark key is the event's date and the
  first 60 characters of its description.
- **Enrich.** The announcement text plus one Tavily page (skipped without a
  key), at most 6,000 characters. No news-search spend.
- **Digest.** One bulk-tier call per event returns the same contract as the
  curator, applied through the same merge, dated with the event's day. An
  optional `business_summary_update` refreshes the business summary. A
  failed event is skipped; nothing raises.

At most 3 LLM calls and 3 Tavily pages per ticker per week, usually none.

## 27. Living Envelope

A monthly envelope built once on the 1st cannot react to a broken thesis or
a market shock: step 7b changes confidence only, never prices or direction.
The Living Envelope lets the loop re-underwrite the rest of the month,
bounded and evidence-gated, while every graded session is still graded
against the row that was active when it was predicted.

### 27.1 Sticky regime

[state.py](../core/intelligence/regime/state.py) keeps one market-wide
label in `data/predictions/_regime_state.json`:

- only `RISK_OFF` (severity 1) and `MACRO_CRISIS` (2) are severe; every other
  label is calm (0);
- a severe label is entered immediately on its first detection;
- while a severe label is sticky, each milder detection adds to a calm
  streak, and 3 in a row (`regime.calm_days`) exit to the milder label; a
  severe detection resets the streak;
- a second call on the same day changes nothing;
- with `rl.regime_sticky_enabled` off, the raw label passes through and
  nothing is written. A missing or corrupt file starts fresh. Nothing raises.

The daily review uses the sticky label for multipliers, the feedback entry
and the `regime_flip` trigger. The paper lane reads the raw label and writes
nothing. Forecast generation and re-forecasts use the raw detection for
their Monte Carlo bands (section 4).

### 27.2 Shock-triggered re-forecast

`regenerate_envelope(ticker, sector, reason, trigger, review_date)` in
[generate_forecast.py](../core/intelligence/rl/workflows/generate_forecast.py):

- returns `None`, changing nothing, when the flag is off, the cycle has no
  envelope, the month's cap (`rl.reforecast_max_per_month`, 2) is reached,
  no rows remain after `review_date`, or any step fails;
- copies the current envelope to `archived_envelopes/<YYYY-MM>_v<n>.json`
  first;
- runs a fresh analysis with the decision weights. An abstaining analysis is
  recorded, and in `enforce` mode the re-forecast stops with the envelope
  unchanged;
- anchors new Monte Carlo paths on the latest close for the rows after
  `review_date` only, keeping their dates and continuing the day numbers.
  Rows on or before `review_date` are kept byte for byte;
- updates the envelope's count, history, profile, learning mode, gate and
  instrument. New rows carry their own stamps.

**Triggers** in the daily review, after step 7a, live cycle only, first
match wins:

| Trigger | Condition |
|---|---|
| `external_shock` | The miss is `external_shock` on a wrong day, after the 20% cap |
| `thesis_break` | The thesis review's multiplier is at or below 0.5 |
| `regime_flip` | The sticky label entered `MACRO_CRISIS` today |

The pre-open check adds `preopen_shock` (section 27.3).

**Scoring stays honest.** A review grades the row stored for its session,
and a re-forecast replaces only later rows, so each graded row is the one
that was active when it was predicted.

### 27.3 Pre-open sanity check

`preopen_shock_check` (Mon–Fri 08:45 IST) or `run_schedule preopen-check`,
[preopen_check.py](../core/intelligence/rl/workflows/preopen_check.py):

1. one news search for overnight India-market, GIFT Nifty and global macro
   headlines;
2. one fast-tier call rating severity (0 to 1), direction (`risk_off`,
   `risk_on` or `neutral`) and a headline. Any failure reads as severity 0;
3. below `rl.preopen_shock_severity` (0.7): one log line and nothing else;
4. at or above it: each scanned ticker whose row for today contradicts the
   direction (UP in `risk_off`, DOWN in `risk_on`) is re-forecast with
   `trigger="preopen_shock"`, under the same monthly cap. One ticker's
   failure does not stop the others.

**Coverage limit.** The scheduled job passes no ticker list, so on a shock
morning the check scans the four native sectors' built-in ticker lists (29
symbols in each sector's `config/settings.py`), not the managed list. A
managed ticker outside those lists, such as a bank or energy stock added
later, is never checked. A listed ticker with no store has an empty store
directory created and is skipped.

### 27.4 Settings

| Setting | Default | Controls |
|---|---|---|
| `rl.reforecast_enabled` | true | Section 27.2 |
| `rl.reforecast_max_per_month` | 2 | Re-forecasts per ticker per calendar month |
| `rl.reforecast_thesis_mult_threshold` | 0.5 | `thesis_break` trigger |
| `rl.regime_sticky_enabled` | true | Section 27.1 |
| `regime.calm_days` | 3 | Milder detections needed to leave a severe label |
| `rl.preopen_check_enabled` | true | Section 27.3 |
| `rl.preopen_shock_severity` | 0.7 | Severity that starts the per-ticker scan |

### 27.5 Safety

With the three flags off, none of these components reads or writes anything.
`regenerate_envelope`, `update_sticky_regime` and `run_preopen_check` never
raise. The cost ceilings are 2 full analyses per ticker per month for
re-forecasts, and one search plus one fast-tier call per morning for the
pre-open check. Weight memory, lessons and the dossier are not touched by any
of them.
