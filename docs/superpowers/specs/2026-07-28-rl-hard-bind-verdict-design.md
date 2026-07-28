# RL Hard-Bind Verdict — Design Spec

**Date:** 2026-07-28
**Status:** SHIPPED (flag OFF, byte-identical no-op) — pending prod-enable on user go
**Findings/IDs:** AUD-077 (resolve: decision made), AUD-117 (new — frozen-verdict reward poisoning), unblocks AUD-098
**Related memory:** project-learning-evidence, project-tech-audit-program (Lighthouse)

## 1. Motivation

The RL knowledge layer learns per-agent weights, regime multipliers, lesson
emphasis and seasonal deltas. AUD-077 established that none of this **binds the
decision**: `SignalAggregator` emits the final verdict free-form from the
aggregation LLM, and the learned weighted composite reaches it only as one prompt
line. The AUD-077 shadow lane (`verdict_shadow.py`, observe-only since 2026-07-17)
was built to measure the gap and drive a hard-bind-vs-keep decision.

### 1.1 The analysis (fresh prod data, 2026-07-28)

Pulled fresh prod data via `railway ssh` (shadow jsonl 133 rows 7/18→7/27 + 26
feedback logs) and graded each verdict channel against realized `actual_direction`
(read-only script `shadow_actuation_analysis.py`). n = 81 gradeable daily-review
rows. **The decisive discovery: there are three verdict channels, not two.**

| Channel | What it is | Direction accuracy (n=81) |
|---|---|---|
| `threshold_verdict` | today's composite → `SCORE_THRESHOLDS` bands (hard-bind candidate) | **33.3%** |
| `llm_verdict` | today's aggregator `report.verdict` (what the shadow logs) | 25.9% |
| `predicted_verdict` | **frozen month-start envelope verdict** — the value the system grades + acts on | **14.8%** |

`predicted_verdict` is stamped once at month-start
([generate_forecast.py:245](../../../core/intelligence/rl/workflows/generate_forecast.py))
onto **every** day of the 30-day envelope, then graded daily at
([daily_review.py:547](../../../core/intelligence/rl/workflows/daily_review.py)).
Confirmed constant-per-ticker-per-month in the data (SUZLON=BUY all July and fell
16/16; TVSMOTOR=SELL all week and rose; TATAELXSI=NEUTRAL all week). That frozen
verdict feeds `direction_correct` → WeightAdapter credit + the advisor ADD gate.
**This staleness is a new finding, AUD-117 (P1).**

Threshold (daily) vs the **actual production verdict** (frozen `predicted_verdict`):
32 divergent rows, **threshold wins 16, production wins 1, sign-test p = 0.0003.**
The originally-scoped AUD-077 comparison (threshold vs aggregator-raw `llm_verdict`)
was 11–5, p = 0.21 — inconclusive, because it measured against a baseline the
system does not use.

### 1.2 Honest caveats (not overclaimed)

- Single month, one mild-down regime (DOWN 40 / UP 34 / FLAT 7). Generalization to
  trending/rising regimes is unproven.
- All three lanes are weak predictors — even 33% is below a naive "always-modal-
  direction" call (49%) in this sample. Hard-bind fixes the **ranking**, the
  **reward-signal integrity**, and **determinism** — it is not a good predictor.
  The weak base agent signal (bullish bias, composite resolution ≈ 0) is a
  separate, larger problem for the RL "real brain" backlog.

## 2. Decision

**BIND**, scope = "graded channel + aggregator" (user-ratified 2026-07-28), flag-
gated, TDD, prod-enable still gated on user go. **Per-sector `SCORE_THRESHOLDS`:
DEFER** (thin per-sector n, no config schema, the failure is the NEUTRAL dead-zone
+ staleness — uniform, not sector-specific band boundaries).

## 3. Design

### 3.1 Flag

```
RL_HARD_BIND_VERDICT_ENABLED: bool = cfg(
    "rl.hard_bind_verdict_enabled", env="RL_HARD_BIND_VERDICT_ENABLED", fallback=False)
```

One flag governs both bindings (conceptually one decision). Merged OFF ⇒ deploy is
a byte-identical no-op. `config.yaml` gets `rl.hard_bind_verdict_enabled: false`
([[feedback-config-over-hardcode]] — no hardcoded magic).

### 3.2 Binding 1 — Aggregator (`SignalAggregator.run`)

After `report = self._parse(...)` and **before** the shadow-log call:

1. `raw_llm_verdict = report.verdict` (capture first).
2. Shadow lane logs `llm_verdict=raw_llm_verdict` (unchanged) so it keeps
   comparing **raw-LLM vs threshold** even after the bind — monitoring survives.
3. If `settings.RL_HARD_BIND_VERDICT_ENABLED`: `report.verdict =
   verdict_from_composite(composite)`.

`report.final_score` is **left as the LLM's** — it feeds `base_confidence` →
Monte-Carlo path width; binding only the categorical verdict avoids disturbing the
price path. `verdict_from_composite` is imported from `verdict_shadow` (single
source of the composite→band map). Effect: the aggregator verdict becomes
deterministic → unblocks AUD-098 (aggregator/thesis-reviewer down-tier).

### 3.3 Binding 2 — Graded channel (`daily_review`)

`daily_review` already re-runs the full analysis daily via
`orchestrator.analyse(ticker)` (line ~224, for agent-score drift). With Binding 1
active, **that fresh `report.verdict` is the daily threshold verdict**. So:

- When the flag is on **and** a fresh daily report exists: grade
  `direction_correct = is_direction_correct(fresh_report.verdict, actual_direction)`
  instead of the frozen `today_forecast.predicted_verdict`.
- On `_can_skip_rerun` early-exit days (no fresh report): fall back to
  `today_forecast.predicted_verdict` (which, under Binding 1, is the month-start
  threshold verdict). Documented fallback.
- Record the actually-graded verdict on the `FeedbackEntry` (new optional field,
  e.g. `graded_verdict`) for transparency and future analysis.

**Scope decision (user: "whichever is recommended"): grade-against-daily-rerun
only.** The stored envelope per-day `predicted_verdict` is left as the month
thesis — NOT rewritten. Smallest surface, smallest blast radius; the reward-signal
+ ADD-gate win is fully realized through `direction_correct`.

### 3.4 Blast radius (verified in code)

The advisor ([advisor.py](../../../core/portfolio/advisor.py)) drives EXIT/TRIM
from `envelope_direction` (MC price-path drift), `thesis_intact`, and profit —
**none touched** by the verdict bind. The verdict reaches the money path only via
`direction_accuracy_7d` → the **ADD gate** (threshold 0.60; both 14.8% and 33.3%
sit well below it, so ADD behavior barely moves). `report.verdict` feeds the price
path only in the `_static_fallback` case (normally superseded by the LLM
forecast-profile). Net: bounded to the **RL reward signal + ADD gate**; EXIT/TRIM
and the normal price path are unaffected.

### 3.5 History and monitoring

- `direction_correct` semantics change **forward** from the enable-date — a
  deliberate accuracy-series break, exactly like AUD-060 (2026-07-17). Stored
  values are never rewritten.
- The shadow lane keeps running post-bind (logs raw-LLM vs threshold), so
  divergence remains observable and the decision stays auditable.

## 4. Non-goals

- Per-sector `SCORE_THRESHOLDS` (deferred — needs a config schema + more data).
- Changing `report.final_score`, the MC price path, or `envelope_direction`.
- Rewriting stored envelope `predicted_verdict` rows.
- Touching EXIT/TRIM logic or rewriting historical `direction_correct`.
- Fixing the weak base agent signal (separate RL "real brain" backlog item).

## 5. Testing (TDD)

- `verdict_from_composite` band mapping (already covered; assert boundaries).
- Aggregator: flag OFF → `report.verdict` unchanged (byte-identical); flag ON →
  `report.verdict == verdict_from_composite(composite)`; shadow row's `llm_verdict`
  is the **raw** LLM verdict in both cases; `final_score` never overridden.
- daily_review grading: flag ON + fresh report → `direction_correct` uses the bound
  verdict; skip-rerun day → falls back to frozen envelope verdict; flag OFF →
  grading unchanged. `graded_verdict` persisted on the entry.
- Full-suite fail-set A/B == known-red baseline (10F/10E: AUD-022 stale mocks +
  event_ingestor date test) — flag-off path proven inert.

## 6. Rollout

Merge with flag OFF (no-op deploy). Enable via `config.yaml`
`rl.hard_bind_verdict_enabled: true` (or Railway env) when the user gives the go —
ideally after the optional 2026-07-31 reconfirmation re-run (`p=0.0003` is already
decisive, so this is confirmation, not a gate). Watch the first post-enable
daily_review: `direction_correct` should track the daily threshold verdict; shadow
lane continues logging. Rollback = set the flag false (instant, no redeploy needed
if env-driven).

## 7. Ledger updates (on ship)

- AUD-077: status → decision made (bind, graded+aggregator); shipped when merged.
- AUD-117 (new, P1): frozen month-start `predicted_verdict` poisons the RL reward
  signal + ADD gate; FIXED by Binding 2.
- AUD-098: unblocked (aggregator now deterministic → down-tier candidate).
- Keep cash/endpoint/auth specifics out of committed docs (public repo).
