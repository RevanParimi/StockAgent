# Adaptive Prediction Loop — RL Feedback Layer Design

> Applies to all four sector graphs: **Automobile · Banking/BFSI · IT · Renewable Energy**
> Each sector and each ticker maintains its own independent memory — weights learned for HDFCBANK do not affect TCS.

> **Plain English first:** Imagine hiring a stock analyst who not only gives you a monthly forecast but also reviews their own calls every single day, writes down *why* they were wrong, and gradually gets better at their job. That's exactly what this system does — automatically.

---

## Table of Contents

1. [The Big Idea](#1-the-big-idea)
2. [Why This Is Different](#2-why-this-is-different)
3. [How It Works — Day by Day](#3-how-it-works--day-by-day)
4. [System Architecture](#4-system-architecture)
5. [The 4 JSON Memory Files](#5-the-4-json-memory-files)
6. [New Components to Build](#6-new-components-to-build)
7. [The Daily Cron Flow](#7-the-daily-cron-flow)
8. [Weight Adaptation Rules](#8-weight-adaptation-rules)
9. [FeedbackAgent Prompt Contract](#9-feedbackagent-prompt-contract)
10. [File Storage Layout](#10-file-storage-layout)
11. [Build Order](#11-build-order)
12. [Implementation — What Was Built](#12-implementation--what-was-built)
13. [Configuration Reference](#13-configuration-reference)
14. [How to Run](#14-how-to-run)
15. [Changes to Existing Files](#15-changes-to-existing-files)

---

## 1. The Big Idea

### Plain English

Most stock analysis tools work like a weather app that gives you a forecast and never tells you how accurate last week's forecast was. You have no idea if you can trust it.

This system works differently. Think of it as having **5 specialist analysts** (agents) plus a **6th analyst whose only job is to review everyone else's work every day**. After each trading day:

- The review analyst checks: *"We predicted the stock would go up — did it?"*
- If wrong: *"Why? Was it something we didn't consider? Which of our 5 analysts led us astray?"*
- The lessons get written down permanently
- Each analyst's **credibility score** (weight) goes up or down based on their track record
- Tomorrow's forecast is updated using what was learned today

Over 30 days, the system has accumulated real experience. After 3 months, it knows things like:

> *"For Maruti Suzuki specifically, whenever the RBI makes a surprise rate decision, our risk analyst's signal is the most reliable one — trust that more than usual."*

That is the **experience factor** — something no static research tool has.

---

## 2. Why This Is Different

| Regular Stock Research Tool | This System |
|---|---|
| One-shot analysis, done | Predicts 30 days ahead, then revises daily |
| Same fixed rules always | Agent weights *earned* by real accuracy over time |
| No memory of past mistakes | Every miss logged with root cause analysis |
| Generic advice for all stocks | Learns **stock-specific** patterns (Maruti behaves differently than Tata Motors) |
| Research without experience | Lessons accumulate — future predictions use learned rules |
| You trust it blindly | You can see its track record, miss history, and why weights changed |

The core insight: **experience = learning from mistakes + updating your mental model**. This system does that automatically, in JSON, every day.

---

## 3. How It Works — Day by Day

### Month Start (Day 0)

The system runs a full analysis and generates a **30-day prediction envelope** — a forecast for every single trading day of the month. Each day's forecast includes:
- Predicted closing price
- Predicted direction (up/down/neutral)
- What assumptions it's making (crude oil price, FADA dispatch data, etc.)
- Confidence level

If the system has **prior learning** from previous months, it uses those learned weights instead of the default ones. A stock with 3 months of history gets smarter forecasts than one being analysed for the first time.

### Every Day (Days 1–30, automated via cron job)

```
Morning: yesterday's actual closing price is fetched automatically
    ↓
Compare: actual vs what we predicted
    ↓
FeedbackAgent runs: "Why did we miss? Which factor did we ignore?"
    ↓
Lessons written to learning ledger
    ↓
Agent weights adjusted (bounded — can't swing wildly)
    ↓
Remaining forecasts revised using new weights
    ↓
Everything saved to JSON files
```

---

## 4. System Architecture

```
                        ┌─────────────────────────────────────────────┐
                        │           MONTH START (Day 0)                │
                        │                                              │
                        │  Sector graph (any of the 4):               │
                        │    automobile  → AutomobileAgentOrchestrator │
                        │    banking_bfsi / it_sector /               │
                        │    renewable_energy → LangGraph graph.invoke │
                        │      ↓  runs N agents in parallel            │
                        │  aggregate node (uses learned weights        │
                        │  from agent_weight_memory.json if exists)    │
                        │      ↓                                       │
                        │  generate_forecast.py --sector <name>        │
                        │  → saves prediction_envelope.json            │
                        └─────────────────────────────────────────────┘

                        ┌─────────────────────────────────────────────┐
                        │        EVERY DAY (cron, 24h interval)        │
                        │                                              │
                        │  daily_review.py --sector <name>             │
                        │  1. load prediction_envelope                 │
                        │  2. fetch actual close (yfinance)            │
                        │  3. compute error                            │
                        │  4. FeedbackAgent → miss analysis + lessons  │
                        │  5. WeightAdapter → adjust agent weights     │
                        │  6. LearningLedger → store/dedupe lessons    │
                        │  7. revise remaining forecasts               │
                        │  8. append daily_feedback_log entry          │
                        └─────────────────────────────────────────────┘

  ┌─────────────────────────────┐     ┌─────────────────────────────┐
  │  Sector Agents (per graph)  │     │  2 Cross-Sector Agents      │
  │  Automobile  (8 agents)     │     │  - feedback_agent           │
  │  Banking/BFSI (6 agents)    │     │  - weight_adapter           │
  │  IT Sector   (8 agents)     │     │  (sector-agnostic —         │
  │  Renewable   (6 agents)     │     │   same code for all 4)      │
  └─────────────────────────────┘     └─────────────────────────────┘
                                      ┌─────────────────────────────┐
                                      │  4 JSON Memory Files        │
                                      │  (one set per ticker,       │
                                      │   sector-tagged in path)    │
                                      │  - prediction_envelope      │
                                      │  - daily_feedback_log       │
                                      │  - agent_weight_memory      │
                                      │  - learning_ledger          │
                                      └─────────────────────────────┘
```

---

## 5. The 4 JSON Memory Files

These files are the system's **brain**. Everything the system learns is stored here. They are designed as JSON so they are easy to filter, query, and inspect without a database.

---

### 5.1 `prediction_envelope.json` — The Living Forecast

**Plain English:** This is the 30-day forecast sheet. Every day, the rows that haven't happened yet get updated based on what was learned so far. Think of it as a spreadsheet that corrects itself.

```json
{
  "ticker": "MARUTI",
  "cycle_id": "MARUTI_2026-04",
  "generated_at": "2026-04-08",
  "base_close": 10500.0,
  "weight_version_used": 3,
  "daily_forecasts": [
    {
      "day": 1,
      "date": "2026-04-09",
      "predicted_close": 10580.0,
      "predicted_change_pct": 0.76,
      "predicted_verdict": "BUY",
      "predicted_agent_scores": {
        "sales_demand": 0.72,
        "fundamentals": 0.68,
        "pattern_analysis": 0.65,
        "sentiment": 0.70,
        "risk_macro": 0.55
      },
      "confidence": 0.71,
      "key_assumptions": [
        "crude stable ~$82",
        "FADA dispatch +6% MoM",
        "no major policy announcement expected"
      ],
      "revised": false,
      "revision_count": 0
    }
  ]
}
```

**Key fields:**
- `weight_version_used` — which generation of learned weights produced this forecast
- `key_assumptions` — what the system was betting on; this is what gets compared when we miss
- `revised` / `revision_count` — tracks how many times this day's forecast was updated before it arrived

---

### 5.2 `daily_feedback_log.json` — What Actually Happened and Why We Missed

**Plain English:** This is the analyst's daily diary. Every day, a new entry is added with the actual price, how wrong we were, and the root cause analysis. Over time, this becomes a goldmine of pattern recognition.

```json
{
  "ticker": "MARUTI",
  "cycle_id": "MARUTI_2026-04",
  "entries": [
    {
      "day": 1,
      "date": "2026-04-09",
      "predicted_close": 10580.0,
      "actual_close": 10430.0,
      "price_error_pct": -1.42,
      "direction_correct": false,
      "miss_analysis": {
        "primary_miss_agent": "risk_macro",
        "missed_factors": [
          "RBI rate hold surprise",
          "FII single-day outflow ₹2200Cr"
        ],
        "over_weighted_factors": [
          "FADA dispatch optimism — data was real but market ignored it"
        ],
        "agent_score_drift": {
          "sales_demand": 0.04,
          "risk_macro": -0.18
        }
      },
      "lessons_generated": ["L003"],
      "weight_adjustment_applied": "v4",
      "remaining_forecasts_revised": true
    }
  ]
}
```

**Key fields:**
- `direction_correct` — the binary scorecard: did we at least get up/down right?
- `primary_miss_agent` — which of the 5 agents led the system astray
- `missed_factors` — real-world events the system didn't account for
- `over_weighted_factors` — signals the system trusted too much
- `lessons_generated` — IDs of lessons written to the learning ledger from this day's miss

---

### 5.3 `agent_weight_memory.json` — Earned Credibility Per Agent

**Plain English:** Imagine 5 analysts. You track how often each one is right. The one who keeps getting the direction correct gets a louder voice in future meetings. The one who keeps being over-optimistic gets their influence reduced. This file tracks that credibility over time — separately for each stock.

```json
{
  "ticker": "MARUTI",
  "last_updated": "2026-04-15",
  "weight_version": 4,
  "current_weights": {
    "sales_demand": 0.22,
    "fundamentals": 0.24,
    "pattern_analysis": 0.18,
    "sentiment": 0.14,
    "risk_macro": 0.22
  },
  "base_weights": {
    "sales_demand": 0.25,
    "fundamentals": 0.20,
    "pattern_analysis": 0.20,
    "sentiment": 0.15,
    "risk_macro": 0.20
  },
  "adjustment_bounds": {
    "max_single_step": 0.05,
    "max_total_drift_from_base": 0.15
  },
  "agent_accuracy": {
    "sales_demand":     {"direction_hits": 3, "total": 7, "avg_error": 0.08},
    "fundamentals":     {"direction_hits": 5, "total": 7, "avg_error": 0.04},
    "pattern_analysis": {"direction_hits": 4, "total": 7, "avg_error": 0.06},
    "sentiment":        {"direction_hits": 3, "total": 7, "avg_error": 0.11},
    "risk_macro":       {"direction_hits": 6, "total": 7, "avg_error": 0.03}
  },
  "weight_history": [
    {
      "version": 4,
      "date": "2026-04-15",
      "weights": {
        "sales_demand": 0.22,
        "fundamentals": 0.24,
        "pattern_analysis": 0.18,
        "sentiment": 0.14,
        "risk_macro": 0.22
      },
      "reason": "risk_macro hit 6/7 directions correctly; bumped +0.02. sales_demand over-optimistic 4/7; trimmed -0.03"
    }
  ]
}
```

**Key design decisions:**
- `base_weights` are always preserved — the system never completely abandons its priors
- `adjustment_bounds.max_total_drift_from_base: 0.15` — an agent can never gain/lose more than 15% weight from its default, preventing runaway drift
- `weight_history` gives full audit trail — you can always see *why* a weight changed
- **Per-ticker** — Maruti's learned weights are completely separate from Tata Motors' weights

---

### 5.4 `learning_ledger.json` — Accumulated Pattern Knowledge

**Plain English:** This is the most powerful file. Over time, the system discovers recurring patterns specific to a stock. Things like: *"Every time there's an RBI announcement, the risk analyst's signal is the most reliable — trust it more."* These patterns persist across monthly cycles. After 6 months, the system has real domain expertise baked in.

```json
{
  "ticker": "MARUTI",
  "last_updated": "2026-04-15",
  "lessons": [
    {
      "lesson_id": "L001",
      "date_learned": "2026-04-10",
      "category": "macro",
      "pattern": "RBI_policy_day",
      "observation": "On RBI policy announcement days, risk_macro agent score delta >0.15 predicts actual direction correctly in 80% of observed cases",
      "rule": "Boost risk_macro weight by +0.05 when RBI event is detected in market context",
      "confidence": 0.80,
      "occurrences": 3,
      "still_valid": true
    },
    {
      "lesson_id": "L002",
      "date_learned": "2026-04-12",
      "category": "seasonal",
      "pattern": "month_end_inventory_flush",
      "observation": "Last 3 trading days of month: sales_demand consistently overestimates demand due to dealer inventory flush; actual price -8% vs predicted on average",
      "rule": "Discount sales_demand score by -0.08 in last 3 trading days of each month",
      "confidence": 0.65,
      "occurrences": 2,
      "still_valid": true
    }
  ],
  "miss_counter": {
    "RBI_policy_surprise": 2,
    "FII_outflow_spike": 3,
    "crude_shock": 1,
    "month_end_inventory_flush": 2
  }
}
```

**Key fields:**
- `category` — groups lessons: `macro` | `technical` | `sentiment` | `fundamental` | `seasonal`
- `occurrences` — if the same pattern fires again, the counter goes up instead of creating a duplicate lesson
- `confidence` — rises with more occurrences, falls if the pattern stops working
- `miss_counter` — top-level frequency map of what this stock is most sensitive to
- `still_valid` — set to `false` when a lesson's rule stops working (the system self-cleans stale rules)

---

## 6. New Components to Build

```
tools/
  prediction_store.py     
      Reads and writes all 4 JSON files.
      Handles file paths keyed by ticker + cycle_id.
      Single source of truth for all persistence.

agents/
  feedback_agent.py       
      The 6th agent. Runs daily.
      Input: predicted values, actual close, today's market context.
      Output: miss_analysis JSON + new lessons to add to ledger.
      Uses LLM to reason about *why* the miss happened.

  weight_adapter.py       
      Reads feedback output and agent_weight_memory.
      Computes new weights using accuracy stats + lesson rules.
      Enforces bounds (max step, max drift from base).
      Writes updated agent_weight_memory.json.

scripts/
  daily_review.py         
      The cron entry point. Runs every 24 hours per tracked ticker.
      Orchestrates the full daily feedback loop (steps 1–8).
      Called by the scheduler, not by the user directly.

  generate_forecast.py    
      Month-start entry point.
      Runs full analysis, then generates the 30-day prediction envelope.
      Reads existing weight_memory if available (uses learned weights).

models/
  feedback_schemas.py     
      Pydantic models for:
        FeedbackEntry, MissAnalysis, Lesson,
        WeightMemory, PredictionEnvelope, DailyForecast
```

---

## 7. The Daily Cron Flow

```
Step 1  load prediction_envelope.json
        → get today's predicted_close, predicted_verdict, key_assumptions

Step 2  fetch actual close price
        → yfinance (existing tool, no new dependency)

Step 3  compute error metrics
        → price_error_pct = (actual - predicted) / predicted * 100
        → direction_correct = True/False
        → agent_score_drift = today's re-run scores vs prediction

Step 4  FeedbackAgent.run()
        → LLM receives: predicted, actual, today's market news, existing lessons
        → LLM outputs: primary_miss_agent, missed_factors, over_weighted_factors, new_lessons[]

Step 5  WeightAdapter.update()
        → score each agent's rolling accuracy (last 7 days)
        → compute weight delta per agent
        → apply adjustment_bounds (clamp if needed)
        → re-normalize so weights sum to 1.0
        → save new version to agent_weight_memory.json

Step 6  LearningLedger.add_lessons()
        → for each new lesson from FeedbackAgent:
            if same pattern already exists → increment occurrences + update confidence
            else → add new lesson with lesson_id
        → update miss_counter
        → save learning_ledger.json

Step 7  Revise remaining forecasts
        → re-run SignalAggregator with updated weights for each remaining day
        → apply any active lesson rules inline (e.g. RBI day discount)
        → update prediction_envelope.json (revised=true, revision_count++)

Step 8  Append to daily_feedback_log.json
        → write complete entry for today (steps 1–7 results)
```

---

## 8. Weight Adaptation Rules

These rules are simple and bounded so the system doesn't make wild swings.

| Condition | Action |
|---|---|
| Agent direction hits ≥ 70% over last 7 days | Weight +0.02 |
| Agent direction hits ≤ 40% over last 7 days | Weight -0.03 |
| Agent was `primary_miss_agent` 2 days in a row | Weight -0.05 (immediate) |
| Lesson rule fires (e.g. RBI event detected) | Apply lesson's inline delta for that day only |
| Any weight drifts > 0.15 from its base value | Clamp to base ± 0.15 |
| Weights no longer sum to 1.0 after adjustments | Re-normalize all weights proportionally |

**Why bounded?** Without bounds, a single bad week could make the system ignore an entire agent forever. The bounds ensure no single agent's voice drops below ~half its original level or exceeds ~1.5x its original level, no matter how bad (or good) its recent track record.

---

## 9. FeedbackAgent Prompt Contract

The FeedbackAgent is the 6th LLM agent. Here is exactly what it receives and what it must return.

### Input (injected as JSON into the LLM prompt)

```json
{
  "ticker": "MARUTI",
  "date": "2026-04-09",
  "predicted_close": 10580.0,
  "actual_close": 10430.0,
  "price_error_pct": -1.42,
  "direction_correct": false,
  "predicted_agent_scores": {
    "sales_demand": 0.72,
    "fundamentals": 0.68,
    "pattern_analysis": 0.65,
    "sentiment": 0.70,
    "risk_macro": 0.55
  },
  "todays_agent_scores": {
    "sales_demand": 0.76,
    "fundamentals": 0.67,
    "pattern_analysis": 0.63,
    "sentiment": 0.68,
    "risk_macro": 0.37
  },
  "market_context_today": "RBI held rates unexpectedly; FII sold ₹2200Cr in auto sector; crude at $84",
  "key_assumptions_that_were_made": [
    "crude stable ~$82",
    "FADA dispatch +6% MoM",
    "no major policy announcement expected"
  ],
  "existing_lesson_ids": ["L001", "L002"],
  "learning_ledger_summary": "L001: RBI days → trust risk_macro more. L002: month-end → discount sales_demand."
}
```

### Output (structured JSON from LLM — stored in feedback_log)

```json
{
  "primary_miss_agent": "risk_macro",
  "missed_factors": [
    "RBI rate hold was a surprise — assumption 'no major policy announcement' was wrong",
    "FII outflow of ₹2200Cr was not captured in sentiment signals"
  ],
  "over_weighted_factors": [
    "FADA dispatch data was real and positive but market completely ignored it on policy day"
  ],
  "agent_score_drift": {
    "risk_macro": -0.18,
    "sales_demand": 0.04
  },
  "new_lessons": [
    {
      "category": "macro",
      "pattern": "RBI_policy_day",
      "observation": "When RBI makes a surprise decision, the market ignores all fundamental signals. risk_macro score drop >0.15 is the leading indicator.",
      "rule": "On days with RBI event in context, boost risk_macro weight by +0.05 and discount sales_demand by -0.04",
      "confidence": 0.75
    }
  ],
  "revised_context_for_remaining_days": "Monitor RBI follow-through commentary over next 3 days; FII positioning likely to continue"
}
```

---

## 10. File Storage Layout

```
data/
  predictions/
    automobile/
      MARUTI/
        MARUTI_2026-04_prediction_envelope.json    ← monthly, one per cycle
        MARUTI_2026-04_daily_feedback_log.json     ← monthly, one per cycle
        MARUTI_agent_weight_memory.json            ← PERSISTS across all cycles
        MARUTI_learning_ledger.json                ← PERSISTS across all cycles
      TATAMOTORS/
        TATAMOTORS_2026-04_prediction_envelope.json
        ...
    banking_bfsi/
      HDFCBANK/
        HDFCBANK_2026-04_prediction_envelope.json
        HDFCBANK_agent_weight_memory.json          ← BFSI weights, separate from auto
        HDFCBANK_learning_ledger.json
      SBIN/
        ...
    it_sector/
      TCS/
        TCS_2026-04_prediction_envelope.json
        TCS_agent_weight_memory.json               ← IT weights, separate from all others
        TCS_learning_ledger.json
      INFY/
        ...
    renewable_energy/
      ADANIGREEN/
        ADANIGREEN_2026-04_prediction_envelope.json
        ADANIGREEN_agent_weight_memory.json
        ADANIGREEN_learning_ledger.json
      NTPC/
        ...
```

**Critical distinction:**
- `*_prediction_envelope.json` and `*_daily_feedback_log.json` are **per cycle** (one per month). They get archived.
- `*_agent_weight_memory.json` and `*_learning_ledger.json` are **permanent**. They are never deleted. They are what make the system smarter over time. Month 6's analysis uses everything learned in months 1–5.

---

## 11. Build Order

Build in this sequence — each step depends on the previous:

```
Step 1  models/feedback_schemas.py
        Define all Pydantic models first so everything else has types to work with.

Step 2  tools/prediction_store.py
        JSON read/write layer. All other components depend on this for persistence.

Step 3  agents/feedback_agent.py
        The 6th agent. Depends on prediction_store for loading context.

Step 4  agents/weight_adapter.py
        Depends on feedback_agent output and prediction_store.

Step 5  scripts/generate_forecast.py
        Month-start script. Wires orchestrator → prediction_store.
        Reads weight_memory if exists, passes learned weights to SignalAggregator.

Step 6  scripts/daily_review.py
        The cron entry point. Wires everything together (steps 1–8 of daily flow).

Step 7  Cron registration
        Register daily_review.py to run every 24 hours per tracked ticker.
```

---

## Summary

The experience factor is the core differentiator. Every stock gets its own memory. Every miss makes the system smarter. Over months, the learning ledger becomes a proprietary knowledge base of how that specific stock responds to specific real-world events — something that cannot be replicated by any tool that only does point-in-time research.

```
Month 1:  forecasts based on defaults
Month 3:  forecasts weighted by 60 days of real accuracy data
Month 6:  forecasts informed by learned stock-specific rules, earned agent credibility,
          and a library of pattern lessons that no research tool has
```

---

## 12. Implementation — What Was Built

This section documents every file created or modified during the implementation, what it does, and the key decisions made.

---

### New Files

#### `models/feedback_schemas.py`

All Pydantic v2 data models for the RL system. Every JSON file has a corresponding model class, so the data is always validated on read and write.

| Model | Maps to |
|---|---|
| `DailyForecast` | One row in the prediction envelope |
| `PredictionEnvelope` | Full 30-day forecast sheet |
| `MissAnalysis` | Root cause breakdown for one day's miss |
| `FeedbackEntry` | One day's entry in the feedback log |
| `DailyFeedbackLog` | All feedback entries for one cycle |
| `AgentAccuracy` | Rolling stats (hits, total, avg error) per agent |
| `WeightHistoryEntry` | One versioned weight snapshot with reason |
| `WeightMemory` | Full earned weight state for a ticker |
| `Lesson` | One accumulated pattern rule |
| `LearningLedger` | All lessons + miss counters for a ticker |
| `FeedbackAgentInput` | What goes into the FeedbackAgent LLM call |
| `FeedbackAgentOutput` | What comes back from the FeedbackAgent LLM |
| `RawLesson` | Lesson as returned by LLM (before deduplication) |

Notable helpers on the model classes:
- `PredictionEnvelope.get_forecast(date)` — look up a specific day's row
- `PredictionEnvelope.remaining_forecasts(from_date)` — all future rows for revision
- `WeightMemory.effective_weights()` — returns weights normalised to exactly 1.0
- `LearningLedger.find_by_pattern(pattern)` — prevents duplicate lessons
- `LearningLedger.next_lesson_id()` — auto-increments L001, L002, L003...
- `LearningLedger.active_lessons_summary()` — compact text injected into LLM prompt

---

#### `tools/prediction_store.py`

The single persistence layer for all 4 JSON files. All reads and writes go through here.

Key design decisions:
- **Atomic writes** — all saves go to a `.tmp` file first, then renamed. A crash mid-write never corrupts the live file.
- **Idempotent appends** — `append_feedback_entry()` replaces any existing entry for the same date before appending. Re-running a daily review for the same date is safe.
- **Per-ticker directory** — each ticker gets its own folder under `data/predictions/`. All file paths are derived from the ticker name and cycle ID automatically.
- **Permanent vs cycle files** — `weight_memory` and `learning_ledger` use the ticker name only in their filename. They survive month rollovers. Envelope and feedback log include the cycle ID and are per-month.

```
Public API:

PredictionStore(ticker)
  .current_cycle_id()                     → "MARUTI_2026-04"
  .save_envelope(env)
  .load_envelope(cycle_id)               → PredictionEnvelope | None
  .save_feedback_log(log)
  .load_feedback_log(cycle_id)           → DailyFeedbackLog
  .append_feedback_entry(entry, cycle_id)
  .save_weight_memory(wm)
  .load_weight_memory()                  → WeightMemory | None
  .init_weight_memory(base_weights)      → WeightMemory  (bootstraps fresh)
  .get_or_init_weight_memory(base)       → WeightMemory  (load or bootstrap)
  .save_learning_ledger(ll)
  .load_learning_ledger()                → LearningLedger
  .list_cycles()                         → list of cycle IDs with envelopes
```

---

#### `prompts/feedback_agent.py`

LLM prompt templates for the FeedbackAgent. Contains:
- `SYSTEM_PROMPT` — instructs the LLM on its role, what to avoid (inventing factors, duplicating lessons), and the exact JSON structure it must return
- `FEEDBACK_PROMPT` — the per-day user prompt template with placeholders
- `format_feedback_prompt(...)` — formats all inputs into the final user prompt string

The system prompt explicitly tells the LLM:
- Do not create a new lesson if the same pattern already exists (caller handles deduplication)
- Only reference signals present in the market context — no invention
- If direction was correct, still check for score drift that could signal future misses

---

#### `agents/feedback_agent.py`

The 6th agent. Unlike the 5 sub-agents it does **not** subclass `BaseAgent` because it takes `FeedbackAgentInput` rather than a `StockQuery`.

Two public methods:

`run(fb_input, ledger) → FeedbackAgentOutput`
- Formats the prompt using `prompts/feedback_agent.py`
- Calls Groq LLM with retry logic (same pattern as BaseAgent)
- Parses JSON response into `FeedbackAgentOutput`
- Falls back to a safe minimal output on parse failure (non-fatal)

`merge_lessons_into_ledger(output, ledger) → (ledger, lesson_ids)`
- For each raw lesson in the output:
  - If pattern already exists in ledger → increment `occurrences`, blend `confidence` using weighted average
  - Otherwise → create new `Lesson` with next ID, add to ledger
- Updates `miss_counter` for each missed factor
- Returns the updated ledger and the list of lesson IDs touched

Direction classification logic (also in this file):
- `classify_direction(actual, predicted)` — UP / DOWN / FLAT based on ±0.3% threshold
- `is_direction_correct(verdict, direction)` — BUY implies UP, SELL implies DOWN, NEUTRAL is always considered not-wrong

---

#### `agents/weight_adapter.py`

Deterministic weight adjustment engine. No LLM call — pure maths.

`update(weight_memory, feedback_log, todays_primary_miss_agent) → WeightMemory`

Three-stage process:

**Stage 1 — Accuracy computation** (`_compute_accuracy`)
- Looks at the last `WEIGHT_ACCURACY_WINDOW` (default 7) feedback entries
- Per agent: counts direction hits (non-primary-miss agents get credit on miss days), totals, and average score drift
- Returns a `dict[str, AgentAccuracy]`

**Stage 2 — Delta computation** (`_compute_deltas`)
- Hit rate ≥ 70% → +0.02
- Hit rate ≤ 40% → -0.03
- Same agent was `primary_miss_agent` 2+ days in a row → extra -0.05 (consecutive streak penalty)

**Stage 3 — Bound application + normalisation** (`_apply_deltas`)
- Clamp each delta to `max_single_step` (default 0.05)
- Clamp each resulting weight to `base ± max_total_drift_from_base` (default 0.15)
- Re-normalise so all weights sum exactly to 1.0

The updated `WeightMemory` gets a new version number and a `WeightHistoryEntry` appended with a human-readable reason string showing exactly what changed and why.

---

#### `scripts/generate_forecast.py`

Month-start script. Run on the first trading day of each month.
Accepts `--sector` flag: `automobile` (default) | `banking_bfsi` | `it_sector` | `renewable_energy`.

Flow:
1. Load `WeightMemory` for the ticker (or bootstrap fresh from sector defaults)
2. Inject learned weights — automobile uses `AutomobileAgentOrchestrator._aggregator_weights`; other sectors pass weights to `graph.invoke()` via state override
3. Run full analysis via the sector graph → `FinalReport`
4. Fetch actual closing price from yfinance as the day-0 baseline
5. Generate `DailyForecast` rows for the next 30 trading weekdays:
   - Linear price path interpolated from verdict's implied monthly return
   - Confidence decays 0.5% per day further out (uncertainty grows with horizon)
   - `key_assumptions` populated from `conviction_drivers` in the FinalReport
6. Save `PredictionEnvelope` to JSON

CLI:
```
python -m scripts.generate_forecast --ticker MARUTI
python -m scripts.generate_forecast --ticker MARUTI TATAMOTORS M&M
```

---

#### `scripts/daily_review.py`

The cron entry point. Runs all 8 steps of the daily feedback loop for one ticker on one date.

Key implementation details:
- `--date` argument allows backfilling missed days (e.g. market holiday the day before)
- Defaults to yesterday (market close is past, price is available)
- Skips weekends automatically when defaulting
- `_fetch_actual_close()` tries exact date match first, falls back to nearest prior date (handles data gaps)
- `_run_todays_agent_scores()` re-runs all 5 agents with today's live data using the current learned weights, so the score drift is comparing apples to apples
- News context is fetched best-effort — if it fails, the prompt still runs with "Market context unavailable"
- A provisional `FeedbackEntry` is appended to the log before calling `WeightAdapter` so the adapter can see today's miss in its rolling window calculation
- The final `FeedbackEntry` replaces the provisional one at Step 8 with the complete record

Returns a summary dict with all key metrics for the caller (scheduler or CLI).

---

### Modified Files

#### `agents/orchestrator.py`

Added `_aggregator_weights: dict[str, float] | None = None` instance attribute.

When set by `generate_forecast.py` or `daily_review.py`, this is passed through to `SignalAggregator.run()` as `learned_weights`. No global `settings.AGENT_WEIGHTS` mutation happens — the learned weights are scoped to the single orchestrator instance.

#### `agents/signal_aggregator.py`

Added optional `learned_weights` parameter to `run()`:

```python
def run(self, ticker, company_name, agent_outputs, learned_weights=None) -> FinalReport:
```

When `learned_weights` is provided, it is used instead of `settings.AGENT_WEIGHTS`. Logged so you can always see which weight set was active. Backwards compatible — existing callers that don't pass `learned_weights` get the config defaults as before.

#### `tools/scheduler.py`

Added `_daily_review_job()` method and registered it as a second APScheduler job on the `FEEDBACK_CRON` schedule (default: weekdays at 4:30pm IST / 11:00 UTC, after market close).

The new job:
- Calculates yesterday's date (skipping weekends)
- Calls `run_daily_review()` for each ticker in `SCHEDULER_TICKERS`
- Logs success/failure per ticker without crashing the whole job if one ticker fails

The existing analysis job (`automobile_agent_run`) is unchanged. New sector jobs register under their own job IDs (`bfsi_agent_run`, `it_agent_run`, `re_agent_run`) when the respective scheduler tickers are configured.

#### `scripts/run_schedule.py`

Added 3 new CLI sub-commands:

| Command | What it does |
|---|---|
| `forecast` | Generate month-start 30-day envelope for all or one ticker |
| `daily-review` | Run feedback review for yesterday (or a specific `--date`) |
| `feedback-status` | Print a full dashboard: envelope summary, weights, accuracy, last 5 log entries, top lessons |

The `feedback-status` command is the most useful for day-to-day monitoring. Example output:

```
=== RL Feedback Status: MARUTI | Cycle: MARUTI_2026-04 ===

  Forecast horizon : 30 days
  Days reviewed    : 7
  Days remaining   : 23
  Base close       : ₹10500.00
  Weight version   : v4

  Current weights (v4):
    sales_demand         0.2200  (-0.0300 from base)
    fundamentals         0.2400  (+0.0400 from base)
    pattern_analysis     0.1800  (-0.0200 from base)
    sentiment            0.1400  (-0.0100 from base)
    risk_macro           0.2200  (+0.0200 from base)

  Direction accuracy: 5/7 (71.4%)

  Last 5 entries:
  Date         Error%  Direction    Miss Agent           Lessons
  -----------------------------------------------------------------------
  2026-04-09   -1.42%  WRONG        risk_macro           ['L001']
  2026-04-10   +0.31%  CORRECT      -                    []
  ...

  Learning ledger: 2 lessons
    [L001] RBI_policy_day (confidence=0.80, seen=3x)
    [L002] month_end_inventory_flush (confidence=0.65, seen=2x)

  Top missed factors: [('FII_outflow_spike', 3), ('RBI_policy_surprise', 2)]
```

---

## 13. Configuration Reference

All new settings live in `config/settings.py` under the `# Phase 5` section.

| Setting | Default | What it controls |
|---|---|---|
| `PREDICTION_DATA_DIR` | `data/predictions` | Root folder for all JSON memory files |
| `FORECAST_HORIZON_DAYS` | `30` | How many trading days to forecast on month-start |
| `WEIGHT_MAX_STEP` | `0.05` | Maximum weight change in a single daily adaptation |
| `WEIGHT_MAX_DRIFT` | `0.15` | Maximum total drift any agent weight can move from its base |
| `WEIGHT_MIN_OBSERVATIONS` | `3` | Days of feedback needed before weight adaptation activates |
| `WEIGHT_ACCURACY_WINDOW` | `7` | Rolling window (days) used to judge agent direction accuracy |
| `WEIGHT_BOOST_HIT_RATE` | `0.70` | Hit rate threshold to earn a weight boost (+0.02) |
| `WEIGHT_PENALTY_HIT_RATE` | `0.40` | Hit rate threshold to receive a weight penalty (-0.03) |
| `FEEDBACK_CRON` | `0 11 * * 1-5` | Cron for the daily review job (11:00 UTC = 4:30pm IST) |

All settings can be overridden via `.env` file without touching the code.

---

## 14. How to Run

All commands accept `--sector` to select the graph. Defaults to `automobile` if omitted.

### Month Start — Generate Forecast

Run once on the first trading day of each month per ticker.

```bash
# Automobile (default)
python -m scripts.run_schedule forecast --ticker MARUTI
python -m scripts.run_schedule forecast --ticker MARUTI TATAMOTORS M&M

# Banking / BFSI
python -m scripts.run_schedule forecast --sector banking_bfsi --ticker HDFCBANK SBIN ICICIBANK

# IT Sector
python -m scripts.run_schedule forecast --sector it_sector --ticker TCS INFY HCLTECH

# Renewable Energy
python -m scripts.run_schedule forecast --sector renewable_energy --ticker ADANIGREEN NTPC TATAPOWER

# All configured tickers for all sectors
python -m scripts.run_schedule forecast --all-sectors
```

Output paths follow the sector-keyed layout:
- `data/predictions/automobile/MARUTI/MARUTI_2026-04_prediction_envelope.json`
- `data/predictions/banking_bfsi/HDFCBANK/HDFCBANK_2026-04_prediction_envelope.json`
- `data/predictions/it_sector/TCS/TCS_2026-04_prediction_envelope.json`
- `data/predictions/renewable_energy/ADANIGREEN/ADANIGREEN_2026-04_prediction_envelope.json`

---

### Every Trading Day — Daily Review

Run after market close (automatically via cron, or manually).

```bash
# Automobile — yesterday (default)
python -m scripts.run_schedule daily-review --ticker MARUTI

# BFSI — specific date (backfill)
python -m scripts.run_schedule daily-review --sector banking_bfsi --ticker HDFCBANK --date 2026-04-09

# IT — all configured tickers
python -m scripts.run_schedule daily-review --sector it_sector

# Renewable — all configured tickers
python -m scripts.run_schedule daily-review --sector renewable_energy
```

---

### Check Status

```bash
# Automobile
python -m scripts.run_schedule feedback-status --ticker MARUTI

# BFSI
python -m scripts.run_schedule feedback-status --sector banking_bfsi --ticker HDFCBANK

# IT
python -m scripts.run_schedule feedback-status --sector it_sector --ticker TCS

# Renewable
python -m scripts.run_schedule feedback-status --sector renewable_energy --ticker ADANIGREEN
```

Shows: forecast progress, current weights vs base, direction accuracy, last 5 log entries, top lessons learned — the same dashboard for all sectors.

---

### Start Full Daemon (Analysis + Daily Review, All Sectors)

```bash
# Requires SCHEDULER_ENABLED=true in .env
# Configure per-sector tickers: AUTOMOBILE_TICKERS, BFSI_TICKERS, IT_TICKERS, RE_TICKERS
python -m scripts.run_schedule start
```

Registers one analysis job + one daily-review job per sector that has configured tickers:
- Automobile: `automobile_agent_run` at `SCHEDULER_CRON` (8:30am IST)
- BFSI: `bfsi_agent_run` at `SCHEDULER_CRON`
- IT: `it_agent_run` at `SCHEDULER_CRON`
- Renewable: `re_agent_run` at `SCHEDULER_CRON`
- All sectors: daily-review at `FEEDBACK_CRON` (4:30pm IST)

---

### Direct Script Usage

```bash
# generate_forecast.py directly
python -m scripts.generate_forecast --sector automobile --ticker MARUTI TATAMOTORS
python -m scripts.generate_forecast --sector banking_bfsi --ticker HDFCBANK AXISBANK
python -m scripts.generate_forecast --sector it_sector --ticker TCS INFY
python -m scripts.generate_forecast --sector renewable_energy --ticker ADANIGREEN NTPC

# daily_review.py directly
python -m scripts.daily_review --sector automobile --ticker MARUTI --date 2026-04-09
python -m scripts.daily_review --sector banking_bfsi --ticker HDFCBANK --date 2026-04-09
```

---

## 15. Changes to Existing Files

These existing files were modified — no breaking changes to their existing callers.

| File | Change | Backward Compatible |
|---|---|---|
| `config/settings.py` | 9 new Phase 5 settings added at the bottom | Yes — all have defaults |
| `agents/orchestrator.py` | Added `_aggregator_weights = None` attribute; passes it to aggregator | Yes — None means use config defaults |
| `agents/signal_aggregator.py` | Added optional `learned_weights` param to `run()` | Yes — defaults to None |
| `tools/scheduler.py` | Added `_daily_review_job()` + second APScheduler job registration | Yes — only fires when daemon is running |
| `scripts/run_schedule.py` | Added 3 sub-commands: `forecast`, `daily-review`, `feedback-status` | Yes — existing commands unchanged |
