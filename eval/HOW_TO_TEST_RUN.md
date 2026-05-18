# How to Do a Test Run for Evaluation

This guide explains how to generate test data and run the evaluation
so you can measure whether a code change made the model better or worse.

---

## What the evaluator needs

The evaluator reads three types of JSON files that the pipeline writes
automatically during normal operation:

| File pattern | Written by | Contains |
|---|---|---|
| `*_daily_feedback_log.json` | `scripts/daily_review.py` | direction correct/wrong, price error, miss analysis |
| `*_agent_weight_memory.json` | `scripts/daily_review.py` | per-agent hit rates, weight drift |
| `*_prediction_envelope.json` | `scripts/generate_forecast.py` | 30-day forecasts with sub-scores |

All files live under `data/predictions/{sector}/{TICKER}/`.

If you have not run the pipeline yet, follow **Step A** to generate
synthetic test data. If you already have real data, skip to **Step B**.

---

## Step A — Generate synthetic test data (first-time / no real data)

Run the built-in data generator. It creates realistic fake feedback logs
and weight memories for all four sectors so the evaluator has something
to measure.

```bash
python eval/gen_test_data.py --seed 42
```

What it creates (30 trading days per ticker, all four sectors):

```
data/predictions/
  automobile/
    MARUTI/
      MARUTI_2026-05_daily_feedback_log.json
      MARUTI_2026-05_prediction_envelope.json
      MARUTI_2026-05_agent_weight_memory.json
    TATAMOTORS/  ...
  banking_bfsi/
    HDFCBANK/    ...
  it_sector/
    TCS/         ...
  renewable_energy/
    ADANIGREEN/  ...
```

The synthetic data is realistic: ~62% direction hit rate, natural spread
in scores, a few conflict events and RL weight drifts already present.

---

## Step B — Save a BEFORE baseline

Always save a baseline snapshot before touching any code.

```bash
python eval/evaluate.py --output eval/reports/before.json
```

This runs in under 1 second (reads JSON files, no LLM calls).

---

## Step C — Make your code change

Edit whatever you need: a prompt, a scoring weight, an agent's logic,
a sub-score definition, etc.

---

## Step D — Re-generate test data for the changed code (optional)

If your change affects how the pipeline scores stocks, regenerate
the synthetic data so it reflects the new logic.

```bash
python eval/gen_test_data.py --seed 42   # same random seed for fair comparison
```

If your change only affects non-scoring logic (data fetching, config,
infrastructure), skip this step and reuse the same data files.

---

## Step E — Save an AFTER snapshot

```bash
python eval/evaluate.py --output eval/reports/after.json
```

---

## Step F — Compare

```bash
python eval/evaluate.py --compare eval/reports/before.json eval/reports/after.json
```

Sample output:

```
COMPARISON: 2026-05-15  ->  2026-05-16
==========================================

  Overall hit rate:   62.0% -> 64.3%  ^ 2.3%
  Avg price error:    1.83 -> 1.71  ^0.12%

  Sector                Before HR   After HR      Delta  Change
  ---------------------------------------------------------------
  automobile              63.2%       65.8%       +2.6%  ^ BETTER
  banking_bfsi            60.1%       59.7%       -0.4%  ~ same
  it_sector               61.8%       63.9%       +2.1%  ^ BETTER
  renewable_energy        58.9%       59.2%       +0.3%  ~ same

  Agent (sector)                       Before HR   After HR    Delta
  -------------------------------------------------------------------
  fundamentals (automobile)             68.2%       71.0%      +2.8%  ^
  risk_macro (automobile)               55.3%       58.6%      +3.3%  ^
  sentiment (automobile)                52.1%       49.4%      -2.7%  v
```

**A change is an improvement when:**
- `direction_hit_rate` goes up (even +1-2% matters at scale)
- `avg_price_error_pct` goes down
- No previously-passing sector drops more than 1%

**A change is a regression when:**
- Any sector drops more than 2% while another gains
- The grade for a previously A/B agent drops to C or below
- `score_std` drops below 0.08 on multiple agents (bunching)

---

## Quick reference — all commands

```bash
# Full evaluation (all sectors, verbose with sub-scores)
python eval/evaluate.py

# Single sector only
python eval/evaluate.py --sector automobile
python eval/evaluate.py --sector banking_bfsi
python eval/evaluate.py --sector it_sector
python eval/evaluate.py --sector renewable_energy

# Save to named file
python eval/evaluate.py --output eval/reports/my_snapshot.json

# Compare two snapshots
python eval/evaluate.py --compare eval/reports/before.json eval/reports/after.json

# Hide sub-score detail (shorter output)
python eval/evaluate.py --no-sub-scores

# JSON only (for piping / scripting)
python eval/evaluate.py --json-only

# Generate synthetic test data
python eval/gen_test_data.py
python eval/gen_test_data.py --seed 42    # reproducible
python eval/gen_test_data.py --days 60    # more history
python eval/gen_test_data.py --sector automobile   # one sector only
```

---

## What each metric means

| Metric | Good value | Red flag |
|---|---|---|
| `direction_hit_rate` | > 60% | < 52% (barely better than random) |
| `avg_price_error_pct` | < 2% | > 4% |
| `conflict_rate` | 10–30% | > 50% (agents constantly disagree) |
| `score_std` per agent | > 0.10 | < 0.08 (LLM bunching scores) |
| `weight_drift` | ±0.02–0.06 | > 0.10 (RL has wildly re-weighted) |
| Sub-score correlation | > 0.25 | < 0.0 (negative = counter-productive signal) |
| Calibration error | < 0.10 | > 0.20 (score 0.8 but only 50% accurate) |

### Grade scale

| Grade | Direction hit rate |
|---|---|
| A | >= 65% |
| B | 58–65% |
| C | 52–58% |
| D | 46–52% |
| F | < 46% |

---

## File locations

```
eval/
  evaluate.py         Main evaluator CLI
  engine.py           Metric computation
  schemas.py          Pydantic output models
  gen_test_data.py    Synthetic data generator
  HOW_TO_TEST_RUN.md  This file
  reports/            Saved JSON snapshots go here
    eval_2026-05-15.json
    before.json
    after.json
```
