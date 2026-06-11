# RL Intelligence Phase — Measure → Sharpen → Forget

**Date:** 2026-06-10
**Status:** Design — awaiting user review before plan
**Author:** Architect (Claude) on behalf of beta tester
**Scope:** Three tightly-coupled RL improvements that turn the existing RL stack from
faith-based to evidence-based, fix the highest-leverage learning signal, and stop
unbounded memory accumulation. No new agents. No LLM mechanisms added.

---

## 1. Why this phase

The RL stack is broad (8-step daily loop, 4 JSON schemas, regime detector, conviction
tracker, seasonal validator, thesis reviewer, 54 hand-set regime multipliers) but
**cannot currently be proven to improve accuracy** — `RL_DESIGN.md` G6 defers backtesting
to "Month 6". Until that exists, every constant is unfalsifiable.

Two concrete defects compound this:

- **Thin/blunt reward.** When `direction_correct=True`, *every* agent is credited a hit
  ([weight_adapter.py:253](../../../core/intelligence/rl/agents/weight_adapter.py)),
  so weights track ensemble luck, not individual skill.
- **Unbounded memory.** `miss_counter` only increments and drives PromptEnhancer ranking
  ([enhancer.py:304](../../../core/intelligence/prompt_enhancer/enhancer.py)); lessons are
  never archived (`grep prune|archive|forget` → 0 functions). Stale signal accumulates.

This phase delivers, in dependency order: **(1)** a measuring instrument, **(2)** a sharper
reward, validated by (1), **(3)** active forgetting, validated by (1).

**Guiding principle (inherited from the May redesign reviewer):** bias toward deletions and
one constant over new abstractions. Nothing ships unless the harness shows it moved a real
number.

---

## 2. Component 1 — Evaluation Harness

### 2.1 Purpose
A read-only module that replays prediction + feedback history forward in time and emits hard
metrics. It is also the **test instrument** for Components 2 and 3.

### 2.2 Metrics

| Metric | Definition | Why |
|---|---|---|
| `direction_accuracy` | hits / total over UP/DOWN/FLAT (reuse `classify_direction`, `RL_FLAT_THRESHOLD_PCT`) | Core skill measure |
| `brier_score` | mean( (confidence − outcome)² ), outcome ∈ {0,1} | Is stated confidence honest? |
| `reliability_table` | bucket predictions by confidence decile → realized hit rate per bucket | Calibration curve (over/under-confident) |
| `band_coverage` | % of actual closes within [P10, P90] | Should be ≈0.80; tests MC honesty |
| `mae_pct` | mean abs `price_error_pct` | Magnitude error |

All metrics computable per ticker, per sector, and aggregate.

### 2.3 Ablation
`run_eval(..., ablate=["regime_multipliers"|"calibration_reward"|"forgetting"|...])`
re-runs the same replay with a named subsystem disabled and reports the **delta** in
`direction_accuracy` and `brier_score`. This is the mechanism that justifies keeping or
deleting each constant.

For this phase, ablation is wired for exactly the two flags introduced here
(`calibration_reward`, `forgetting`). The framework accepts arbitrary ablation keys so future
subsystems (regime multipliers, RSI amplifier) can be added without harness changes.

### 2.4 Data sources (user-confirmed: synthetic + real)
- **Real:** auto-discover `data/predictions/{sector}/{ticker}/*_daily_feedback_log.json` +
  `*_prediction_envelope.json`. Use when present.
- **Synthetic:** `SyntheticLogGenerator(seed=42)` fabricates deterministic, realistic
  envelope+feedback cycles (configurable n_tickers, n_cycles, accuracy_rate, vol) so the
  harness yields physical numbers today. Real and synthetic share one code path — the harness
  never special-cases them after load.

### 2.5 Structure & isolation
```
core/intelligence/rl/eval/
  __init__.py
  metrics.py          # pure functions: direction_accuracy, brier, reliability, band_coverage
  synthetic.py        # SyntheticLogGenerator — seeded, deterministic
  harness.py          # EvalHarness: load → replay → aggregate → EvalReport
  run_eval.py         # CLI entry: python -m core.intelligence.rl.eval.run_eval
```
- `metrics.py` is pure (list[FeedbackEntry] → float/dict). Independently testable, no I/O.
- `harness.py` depends on `PredictionStore` (read-only) + `metrics` + optionally `synthetic`.
- **Touches no live RL write path.** Zero risk to the running loop.

### 2.6 Output
`outputs/eval/{YYYY-MM-DD}_report.json` (machine) + a printed summary table (human).
`EvalReport` is a Pydantic model: per-scope metric dicts + metadata (n_entries, source,
ablations run).

---

## 3. Component 2 — Per-Agent Calibration Reward

### 3.1 Defect
`_compute_accuracy` ([weight_adapter.py:242-279](../../../core/intelligence/rl/agents/weight_adapter.py))
credits a hit to **every** agent whenever `direction_correct` — and to every non-blamed agent
on miss days. An agent's weight therefore reflects whether the *ensemble* was right, not
whether *its own score* predicted the move.

### 3.2 Fix
Introduce a per-agent **calibration hit**: an agent earns credit when its own
`predicted_agent_scores[agent]` is directionally consistent with the realized outcome.

The realized direction is read directly from `FeedbackEntry.actual_direction` — no inference,
no new data:
```
realized_up   = (actual_direction == "UP")  # only when actual_direction in {"UP", "DOWN"}
                                             # and predicted_verdict is directional
agent_bullish = predicted_agent_scores[agent] >= AGENT_BULLISH_THRESHOLD   # 0.5
calibrated    = (agent_bullish == realized_up)        # this agent's lean matched reality
```
FLAT realized days carry no directional information and are excluded from the calibration
denominator, exactly like NEUTRAL-verdict days. This reuses the system's own
realized-direction definition (`actual_direction` is the `classify_direction` output,
already populated by `daily_review` every day), so calibration can never disagree with the
direction metric about which way the stock actually moved.

`AgentAccuracy` gains an optional `calibration_hits: int` (default 0, backward-compatible).
When `RL_CALIBRATION_REWARD_ENABLED` is true, the hit-rate that drives boost/penalty deltas
blends ensemble-direction and own-calibration:

```
hit_rate = (1 - w) * direction_hit_rate + w * calibration_hit_rate
w = RL_CALIBRATION_WEIGHT   (default 0.5)
```

This is intentionally a **blend, not a replacement**: ensemble direction still matters
(an agent shouldn't be punished for the basket being right), but individual calibration now
breaks the "everyone wins" tie. The blend weight is the single tunable the harness optimizes.

### 3.3 Safety (user-confirmed: flag default ON)
- `RL_CALIBRATION_REWARD_ENABLED: bool = True` and `RL_CALIBRATION_WEIGHT: float = 0.5` in
  `core/config/settings/base.py` (env-overridable).
- When false → byte-identical to today's behavior (old path preserved).
- Harness ablation `calibration_reward` flips the flag and reports the accuracy/Brier delta.
  We keep the default ON only if the number is non-negative on synthetic + any real data.

### 3.4 Scope guard
Only `_compute_accuracy` changes. The 3-stage delta/bounds/normalize math
(`_compute_deltas`, `_apply_deltas`) is untouched — calibration feeds the existing hit_rate
input, nothing downstream moves.

---

## 4. Component 3 — Forgetting & Recency

### 4.1 Defects (all code-confirmed)
1. `miss_counter` only `+1`s; PromptEnhancer.enhance ranks off it → stale factors dominate
   queries forever. The recency-aware `miss_events` (rolling 12 w/ dates) already exists but
   is unused for ranking.
2. No lesson archival anywhere → live ledger grows unbounded; `active_lessons_summary` /
   `find_by_semantic_overlap` iterate all lessons every daily call.
3. `load_recent_feedback_entries(6)` flat-weights cycles.

### 4.2 Fixes

**(a) Recency-weighted miss ranking.** New `LearningLedger.recency_weighted_miss_scores()`:
```
score(factor) = Σ over events in miss_events[factor]:
                  exp(-Δdays / MISS_RECENCY_HALFLIFE_DAYS)   # default 21
                  × (1.0 if event.miss_type in PENALIZABLE else PENALIZABLE_DISCOUNT)
```
PromptEnhancer.enhance ranks top-N by this score instead of raw `miss_counter`. Falls back to
`miss_counter` only when `miss_events` is empty (legacy ledgers). Behind
`RL_FORGETTING_ENABLED` (default ON) for ablation symmetry.

**(b) Lesson archival.** New `archive_stale_lessons(ledger, cold_store_path, ...)` in
`ledger_propagator.py`:
```
for lesson in ledger.lessons:
  if lesson.still_valid: continue              # only archive already-invalidated
  eff = ledger.effective_confidence(lesson)
  effectiveness = correction/(correction+miss) from correction_counter  # measured usefulness
  if eff <= ARCHIVE_CONF_FLOOR (0.12) and effectiveness < ARCHIVE_EFFECTIVENESS_FLOOR (0.25)
     and days_inactive > ARCHIVE_STALE_DAYS (60):
        move lesson → cold_store JSON (append), remove from ledger.lessons
```
Cold store: `data/predictions/{sector}/{ticker}/{ticker}_archived_lessons.json`. Resurrection:
when a new lesson with the same `pattern`/semantic tags arrives, propagator checks cold store
first and restores it (occurrences + history intact) rather than creating a duplicate.
Invoked weekly from the scheduler (alongside existing `downgrade_stale_lessons`).

**(c) Recency-weighted feedback aggregation.** `load_recent_feedback_entries` gains optional
`recency_weighted=True` returning `list[(entry, weight)]` where
`weight = exp(-cycle_age_months / FEEDBACK_HALFLIFE_MONTHS)` (default 3). PriceInterpolator's
`compute_historical_avg_return` uses the weighted median. Default path (no weights) unchanged
for all other callers.

### 4.3 Validated by harness
Report live-ledger lesson count and per-day iteration cost before/after archival on a seeded
multi-cycle synthetic run; confirm `direction_accuracy` is unchanged (forgetting must not cost
accuracy) and enhanced-query factors shifted toward recent misses.

---

## 5. New settings (all env-overridable, in `core/config/settings/base.py`)

| Setting | Default | Controls |
|---|---|---|
| `RL_CALIBRATION_REWARD_ENABLED` | `True` | Component 2 on/off (ablation) |
| `RL_CALIBRATION_WEIGHT` | `0.5` | Blend of own-calibration vs ensemble-direction |
| `RL_FORGETTING_ENABLED` | `True` | Component 3 recency ranking on/off (ablation) |
| `MISS_RECENCY_HALFLIFE_DAYS` | `21` | Miss-event recency decay half-life |
| `MISS_PENALIZABLE_DISCOUNT` | `0.3` | Weight of non-penalizable misses in ranking |
| `ARCHIVE_CONF_FLOOR` | `0.12` | Eff-confidence at/below which a dead lesson is archivable |
| `ARCHIVE_EFFECTIVENESS_FLOOR` | `0.25` | Measured-usefulness floor for archival |
| `ARCHIVE_STALE_DAYS` | `60` | Days inactive before archival eligible |
| `FEEDBACK_HALFLIFE_MONTHS` | `3` | Recency half-life for feedback-log aggregation |

---

## 6. Sequencing & validation

1. **Harness** (read-only; synthetic + real). Deliverable: `run_eval` prints metrics on a
   seeded synthetic dataset. *Physical result: a baseline metrics table.*
2. **Calibration reward** (flagged ON). Deliverable: harness ablation `calibration_reward`
   on vs off. *Physical result: accuracy/Brier delta; keep only if ≥ 0.*
3. **Forgetting** (flagged ON). Deliverable: harness shows ledger shrinks, accuracy flat,
   query factors recency-shifted. *Physical result: before/after ledger size + accuracy.*

Each component: TDD (failing test first), implement, run locally, paste real output. After
all three, self-review against this spec; redesign any gap.

---

## 7. What is explicitly NOT in scope

- No deletion of the 54 regime multipliers / RSI amplifier yet — the harness *enables* that
  decision; this phase only wires the ablation hook, it doesn't pull the trigger.
- No change to the daily-loop step order, schemas' persisted field meaning, or agent prompts.
- No true parametric RL (policy/value networks). Out of scope by design.
- No real-time/intraday loop change. Horizon stays end-of-day.

---

## 8. File map

| File | Component | Change |
|---|---|---|
| `core/intelligence/rl/eval/metrics.py` | 1 | New — pure metric functions |
| `core/intelligence/rl/eval/synthetic.py` | 1 | New — seeded log generator |
| `core/intelligence/rl/eval/harness.py` | 1 | New — EvalHarness + EvalReport |
| `core/intelligence/rl/eval/run_eval.py` | 1 | New — CLI |
| `core/intelligence/rl/agents/weight_adapter.py` | 2 | `_compute_accuracy` calibration blend (flagged) |
| `src/backend/shared/schemas/feedback.py` | 2,3 | `AgentAccuracy.calibration_hits`; `LearningLedger.recency_weighted_miss_scores()` |
| `core/intelligence/prompt_enhancer/enhancer.py` | 3 | Rank off recency-weighted miss scores |
| `core/intelligence/rl/stores/ledger_propagator.py` | 3 | `archive_stale_lessons()` + resurrection |
| `core/intelligence/rl/stores/prediction_store.py` | 3 | `load_recent_feedback_entries(recency_weighted=)` + cold-store I/O |
| `core/intelligence/rl/algorithms/price_interpolator.py` | 3 | weighted median in `compute_historical_avg_return` |
| `services/scheduler/python/scheduler.py` | 3 | weekly `archive_stale_lessons` hook |
| `core/config/settings/base.py` | 2,3 | 9 new settings |
| `tests/unit/intelligence/rl/eval/` | 1 | New test dir |
| `tests/unit/intelligence/rl/test_calibration_reward.py` | 2 | New |
| `tests/unit/intelligence/rl/test_forgetting.py` | 3 | New |
