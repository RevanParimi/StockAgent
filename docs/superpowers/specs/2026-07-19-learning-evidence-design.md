# Learning Evidence Report — Design (2026-07-19)

**Goal:** a recurring, deterministic report that measures whether the adaptive layer converts outcomes into better decisions — the self-ablation experiment identified as gap G5 in `docs/audit/ADAPTIVE_LEARNING_REVIEW.md`. No LLM calls. Read-only over data already on disk.

## Module

`core/intelligence/rl/eval/learning_evidence.py` — mirrors the scorecard pattern: pure functions + a builder + a renderer + CLI. Output is a plain JSON-serialisable dict (documented schema below), saved to `{SCORECARD_DIR}/../learning_evidence/{month}_evidence.json` plus rendered text.

## Sections and math

### 1. Counterfactual weight replay (the core experiment)
For every `FeedbackEntry` with non-empty `predicted_agent_scores` in the month(s):

- **Lanes:** ADAPTED = weights active *strictly before* the entry date (last `WeightHistoryEntry` with `date < entry.date`, else `base_weights`); BASE = `base_weights`; UNIFORM = 1/n over agents present in the entry.
- Composite = weighted mean of scores (renormalised over agents present). Verdict via `verdict_from_composite` (`SCORE_THRESHOLDS`) — the same deterministic map the shadow lane uses. Correctness via `is_direction_correct(verdict, entry.actual_direction)` — reuse, never reimplement.
- Report per pair (ADAPTED vs BASE, ADAPTED vs UNIFORM): n replayed, divergent-decision days, accuracy per lane, paired lift on divergent days, exact two-sided sign-test p-value on discordant pairs (McNemar exact), Wilson 95% CI on each lane's accuracy.
- Honest caveat embedded in output: production verdicts are LLM-emitted; the replay isolates the weight loop's effect through the deterministic decision channel (the hard-bind candidate).

### 2. Learning-signal health
- **Credit-degeneracy index:** fraction of replayed days where `agent_hit_credit` is identical for all agents (G2 monitor).
- **Weight-entropy trajectory:** normalised entropy of each `WeightHistoryEntry.weights` (and of base), distance from uniform, per ticker; flags convergence-to-uniform and poverty-trapped agents (weight < 0.5 × uniform while rolling hit rate ≥ boost threshold).

### 3. Lesson efficacy (G7 monitor)
Per lesson id appearing in any `claims_fired`: fired-day accuracy vs same-ticker non-fired accuracy, n each, lift; flag `harmful` when lift < 0 with fired-n ≥ 5. Also ledger totals and correlation-free summary (no pretending: below-threshold rows marked insufficient).

### 4. Calibration (G9 monitor)
Brier decomposition (reliability − resolution + uncertainty) over `MatchedRecord`s using the decile bins from `reliability_table`; per month.

### 5. Actuation coupling (G4 monitor)
From `data/rl/verdict_shadow.jsonl` (tolerate absent): divergence rate LLM vs threshold verdict, split by `learned_weights_used`.

### Verdict rule
- n_divergent(ADAPTED vs BASE) < 10 → `INSUFFICIENT_DATA`
- divergence rate < 2% of replayed days → `LEARNING_INERT`
- else sign-test p < 0.10 decides `LEARNING_ACTIVE_BENEFICIAL` / `LEARNING_ACTIVE_HARMFUL`; otherwise `LEARNING_ACTIVE_UNPROVEN`.

## Wiring
- CLI: `python -m core.intelligence.rl.eval.learning_evidence --month 2026-06 [--months-back N] [--data-dir D] [--email]`.
- Scheduler: `_scorecard_monthly_job` additionally builds the evidence report for the same month, saves JSON + text, and emails the rendered text via `core.delivery.channels.send_email` (guarded try/except, never breaks the scorecard job).

## Testing
`tests/unit/intelligence/rl/eval/test_learning_evidence.py`, tmp_path + monkeypatched settings dirs, following `test_scorecard.py` conventions: weights_at selection, replay divergence/lift on constructed cases, degeneracy index, entropy/poverty-trap flags, lesson efficacy, verdict rule branches incl. insufficient data, builder end-to-end over synthetic store files, renderer contains verdict line.

Out of scope (future waves, listed in review doc §4): Shapley credit assignment, Beta-posterior gating, isotonic calibration correction, learned regime multipliers.
