# Is StockAgent Actually Learning? — A Scientific Review of the Adaptive Layer

**Date:** 2026-07-19 · **Author:** AI/ML architecture review (Claude) · **Status:** findings verified against prod backup data in `analysis_data/`

**Companion instrument:** `core/intelligence/rl/eval/learning_evidence.py` — the Learning Evidence Report that measures, monthly and on demand, whether the claims below are still true. See `docs/superpowers/specs/2026-07-19-learning-evidence-design.md`.

---

## 0. The question being asked

Not "does the system adjust numbers after outcomes" — it visibly does. The question is the scientific one:

> Does the adaptive layer **acquire information from outcomes and convert it into measurably better decisions** than the same system with the learning switched off?

That is the operational definition of adaptive learning used throughout this review. Everything else — weight nudges, lesson journals, regime tables — is mechanism, not evidence. Mechanism without measured lift is indistinguishable from noise-following.

**Verdict up front:** the system today is best described as *a bounded heuristic re-weighter plus an LLM-narrated post-mortem journal*. The journal (ledger/dossier text fed back into prompts) is genuine in-context adaptation and is the strongest part. The **numeric** learning loop is currently inert-to-harmful on the evidence below, and — decisively — nothing in the system measures whether it helps. The scaffolding for real learning exists (shadow lane, scorecard, baselines, regime stratification); the controlled experiment that would prove or disprove learning was missing. That experiment is what the Learning Evidence Report now runs.

---

## 1. Census: what the "adaptive" layer actually consists of

| # | Component | Mechanism | Nature |
|---|-----------|-----------|--------|
| 1 | `WeightAdapter` | ±0.02/−0.03 hit-rate nudges, bias penalty, drift clamp ±0.15, renormalise | deterministic hill-climbing heuristic |
| 2 | `FeedbackAgent` | LLM post-mortem → `miss_type`, `primary_miss_agent`, text lessons | LLM-attributed credit assignment |
| 3 | `LearningLedger` + `lesson_emphasis` | text lessons, self-assigned confidence, calendar decay, fixed ±delta nudge on trigger-tag days | episodic memory, never outcome-validated |
| 4 | Regime detector + `REGIME_MULTIPLIERS` | 6 labels from VIX/FII-proxy/RSI → static per-agent multiplier table | hand-tuned constants, not learned |
| 5 | Seasonal thresholds, miss-type multipliers, factor-regime penalty scale | fixed constants from settings | hand-tuned constants |
| 6 | Conviction streak → reversion prior; ThesisReviewer; Living Envelope re-forecast | LLM-mediated forecast revision | in-context adaptation |
| 7 | Monthly scorecard + baseline duel; shadow lane | Brier, direction accuracy vs persistence / always-up / control LLM | measurement (good), but no self-ablation |

---

## 2. The gaps, in order of scientific severity

### G1. The reward channel was broken for most of the training history

`is_direction_correct` treated NEUTRAL as an automatic hit until the AUD-060 fix (2026-07-17). A learner optimising a loss that rewards silence learns silence.

**Empirical confirmation (MARUTI, June 2026):** all 21 verdicts NEUTRAL; realized moves 13 UP / 6 DOWN / 2 FLAT; log records **21/21 direction_correct**. The month scored "perfect" while the system made zero correct directional claims. Every weight update, accuracy snapshot, and lesson confidence accumulated before 07-17 was trained against this degenerate objective, and the fix was fix-forward — the contaminated state (weight memories at v60+, ledger confidences) still drives today's decisions. No reset, no discounting, no re-scoring.

### G2. Credit assignment carries ~0 bits on most days

`agent_hit_credit`: on a correct day, **every** agent gets a hit; on a no-fault miss, every agent gets a hit; otherwise everyone except the single LLM-blamed agent. So the per-agent hit-rate vector is nearly identical across agents almost always — and identical relative boosts cancel exactly under renormalisation. The **only** differentiating signal in the entire weight loop is one LLM-guessed blame bit on penalisable-miss days.

That blame is never validated. There is no counterfactual check (leave-one-out or Shapley over the stored `predicted_agent_scores`) that the blamed agent's signal actually caused the miss. Credit assignment is the central problem reinforcement learning exists to solve; here it is delegated to an ungrounded generative guess. This is the deepest structural gap.

### G3. The dynamics destroy information: convergence to uniformity plus a poverty trap

**Empirical (MARUTI weight memory, v63):** engineered base weights ranged 0.04–0.18 per agent. After 63 updates, 8 of 9 agents sit at ≈0.1215 — the uniform value — and `sales_demand` is trapped at 0.027.

Two mechanisms produce this:

1. **Uniform collapse.** With G2's identical hit rates, all agents cross the boost threshold together; equal deltas + renormalisation ratchet every weight toward 1/n. The learned state converges to the **maximum-entropy** distribution — it ends with *less* information than the hand-engineered prior it started from. By any information-theoretic measure this is anti-learning.
2. **Poverty trap.** `prop_scale` multiplies an agent's delta by (current weight / uniform), floored at 0.25×. An agent crushed to low weight receives quarter-sized boosts forever: MARUTI's `sales_demand` shows hits 6/6 (perfect) yet receives Δ+0.005 while every other agent gets Δ+0.022 — so it can never climb back. Weight ≈ 0.027 is an absorbing state reached largely during the G1 era, now unrecoverable.

### G4. The learned state barely reaches the decision (actuation gap)

The final verdict is emitted **free-form by the aggregation LLM**. The learned composite enters as one line of prompt text. `verdict_shadow.py`'s own docstring concedes: *"the weight loop's causal effect on verdicts is unmeasured (live evidence: SUZLON 0/10 direction accuracy on an 11-day BUY streak)."*

Learning without a guaranteed actuation path is memory, not adaptation. Even a perfectly learned weight vector changes nothing unless the LLM happens to attend to that number. The shadow lane (observe-only since 07-17) is the right first instrument; the hard-bind decision scheduled for ~07-31 is where actuation gets decided.

### G5. No self-ablation — the one controlled experiment that matters was never run

The scorecard duels the agent against persistence, always-up, and a control LLM. It never duels the system **against itself with learning switched off** (frozen base weights, uniform weights, empty ledger). Without that ablation, "the system learns" is unfalsifiable. This is precisely the experiment the Learning Evidence Report implements: replay every logged day's stored `predicted_agent_scores` through the deterministic verdict map under adapted vs frozen vs uniform weights, and report divergence rate + paired accuracy lift with confidence intervals.

### G6. Update thresholds fire on statistical noise

~21 trading days per ticker-month. A 95% binomial CI at n=21 is roughly ±21 percentage points. Boost/penalty rules trigger on hit-rate differences over 5–10-day windows — differences that are essentially never significant. MARUTI reached weight_version 63 in ~3 months: roughly one update per trading day, each exploiting noise. Nowhere in the adaptation path is there a significance gate, an uncertainty estimate, or an exploration mechanism (contrast: any bandit formulation would carry posterior uncertainty per agent).

### G7. Lessons are never validated against outcomes

Lesson confidence is self-assigned by the LLM at creation, blended by arithmetic mean on recurrence, and decayed by *calendar time* — never updated by whether applying the lesson **helped**. `claims_fired` is logged per day and the scorecard reports pooled claim-day vs other-day accuracy, but there is no per-lesson lift, no retirement of lessons with negative lift, and no test of whether self-assigned confidence predicts usefulness. An episodic memory whose entries are never tested against outcomes is an archive, not knowledge. (Actuation is also weak: a fired lesson moves agent scores by a fixed capped ±delta — the same G4 problem one level down.)

### G8. Static constants posing as adaptivity

`REGIME_MULTIPLIERS`, seasonal threshold deltas, miss-type multipliers, decay rates, bias windows — all hand-tuned constants. The Wave-I regime-stratified hit rates are explicitly report-only. So the adaptive weights (dynamic range ±0.15) operate inside a shell of fixed multipliers with equal or larger dynamic range. Most of what shapes a day's effective weights was written by hand, not learned.

### G9. Calibration is measured, not learned

Brier score and a reliability table exist in `eval/metrics.py` (the table is consumed nowhere). Confidence corrections come from LLM suggestions clamped to [−0.15, +0.05]. There is no closed loop from realized calibration to future stated confidence (no isotonic/Platt-style correction), and no Brier decomposition to check whether **resolution** is even positive — i.e., whether the system's confidence distinguishes outcomes at all.

### G10. No non-stationarity handling

Fixed windows, greedy exploitation, no change-point awareness. The environment itself shifted on 07-17 (reward fix) — a textbook distribution change — with no state reset or down-weighting of pre-fix statistics.

---

## 3. What is genuinely good (and worth building on)

- **Miss-type no-fault rules** (data_gap/external_shock exempt) — correct instinct: don't punish the model for unforecastable inputs.
- **Calendar-aware windows** (NSE trading days, not array indices).
- **The shadow lane** — the team already suspected G4 and built the right instrument before binding the decision.
- **The scorecard's baseline duel** — persistence and always-up are exactly the right nulls; the control-LLM lane is a strong idea.
- **Regime stratification of hit rates** (Wave I) — the correct evidence base for turning G8's constants into learned quantities.
- **The ledger/dossier as prompt context** — feeding structured post-mortems back into next-day prompts is real in-context adaptation, and it is likely where most of the system's actual "learning" happens today. It should be measured as such (claim-day lift), not assumed.

## 4. What "the real brain" would require — the gap between here and there

1. **Grounded credit assignment (replaces G2):** compute leave-one-out / Shapley contribution of each agent's stored score to the composite error each day; use the LLM blame only as a tiebreaker or narrative. All inputs (`predicted_agent_scores`, actuals) are already logged — this is computable retroactively.
2. **Uncertainty-gated updates (replaces G6):** treat each agent's hit rate as a Beta posterior; update weights only on statistically meaningful evidence; keep exploration mass on down-weighted agents (kills the poverty trap).
3. **Outcome-validated memory (replaces G7):** per-lesson lift ledger; retire lessons whose fired-day accuracy underperforms their own non-fired baseline with n≥threshold; let realized lift, not LLM self-confidence, drive emphasis delta.
4. **A closed actuation path (replaces G4):** hard-bind or formally blend the composite into the verdict (the 07-31 shadow-lane decision), so learned state provably moves decisions.
5. **Permanent self-ablation (replaces G5):** the adapted-vs-frozen-vs-uniform replay must run continuously, not once — learning that stops being measured stops being real. This is the Learning Evidence Report.
6. **Calibration loop (replaces G9):** monthly isotonic correction fitted on the reliability table, applied to stated confidence.
7. **Regime multipliers from data (replaces G8):** once regime-stratified samples reach significance, fit the multiplier table from `regime_agent_hit_rates` instead of hand values.

Items 1–3 and 5–7 are deterministic, cheap (no LLM calls), and computable from data already on disk. The order above is the recommended build order; item 5 ships first (2026-07-19) because it is the instrument that makes every other claim testable.

## 5. How to read the monthly Learning Evidence Report

The report (emailed with the monthly scorecard; also `python -m core.intelligence.rl.eval.learning_evidence --month YYYY-MM`) answers four questions, each with sample sizes and intervals, and issues one of four verdicts:

- **LEARNING_INERT** — adapted weights almost never change a decision vs frozen base weights (divergence ≈ 0). The numeric loop is decorative.
- **LEARNING_ACTIVE_BENEFICIAL** — decisions diverge and the adapted lane wins the paired comparison beyond chance.
- **LEARNING_ACTIVE_HARMFUL** — decisions diverge and the adapted lane loses. Freeze or fix the loop.
- **INSUFFICIENT_DATA** — divergent-day count too small for any claim; says so instead of pretending.

Sections: (1) counterfactual weight replay; (2) credit-degeneracy index + weight-entropy trajectory (G2/G3 monitors); (3) per-lesson efficacy table (G7 monitor); (4) calibration: Brier decomposition + reliability trend (G9 monitor); (5) LLM-vs-composite coupling from the shadow lane (G4 monitor).

If, months from now, the report still reads INERT with high credit-degeneracy and flat entropy — the honest conclusion is the one feared: the adaptive layer is bookkeeping, not learning. If it reads ACTIVE_BENEFICIAL with rising resolution and validated lessons — that is the receipts.
