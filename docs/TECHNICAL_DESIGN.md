---
title: "StockAgent — Technical Design Document"
version: "2026-05-19"
date: "2026-05-19"
author: "StockAgent Engineering Team"
confidentiality: "Internal — Engineering Reference"
---

# StockAgent — Technical Design Document

| | |
|---|---|
| **Version** | 2026-05-19 |
| **Date** | 2026-05-19 |
| **Author** | StockAgent Engineering Team |
| **Confidentiality** | Internal — Engineering Reference |
| **Scope** | All sectors: automobile, banking_bfsi, it_sector, renewable_energy |

---

## Table of Contents

- [0. Abbreviations & Glossary](#0-abbreviations--glossary)
- [1. System Overview](#1-system-overview)
- [2. Sector Analysis Engine](#2-sector-analysis-engine)
- [3. Sector-by-Sector Agent Reference](#3-sector-by-sector-agent-reference)
- [4. Business Model Context Injection](#4-business-model-context-injection)
- [5. Data Fetchers — Serper, Tavily, yfinance](#5-data-fetchers--serper-tavily-yfinance)
- [6. Chat Pipeline (Agentic Tool-Loop)](#6-chat-pipeline-agentic-tool-loop)
- [7. Reinforcement Learning Pipeline](#7-reinforcement-learning-pipeline)
- [8. Scheduler & Cron Architecture](#8-scheduler--cron-architecture)
- [9. Dynamic Stock Management](#9-dynamic-stock-management)
- [10. Settings Reference](#10-settings-reference)
- [11. Logging & Observability](#11-logging--observability)
- [12. Known Gaps & Open Items](#12-known-gaps--open-items)
- [13. Quick Reference Cards](#13-quick-reference-cards)
- [Appendix A: File Structure Tree](#appendix-a-file-structure-tree)
- [Appendix B: Sector-to-Orchestrator Mapping](#appendix-b-sector-to-orchestrator-mapping)
- [Appendix C: managed_tickers.json Schema](#appendix-c-managed_tickersjson-schema)

---

## 0. Abbreviations & Glossary

| Abbreviation | Expands To | Plain-English Description |
|---|---|---|
| **2W** | Two-Wheeler | Motorcycles and scooters (Hero MotoCorp, Bajaj, TVS segment) |
| **4W** | Four-Wheeler | Passenger cars and utility vehicles (Maruti, Tata, M&M segment) |
| **ADAS** | Advanced Driver-Assistance Systems | Safety technology (automatic braking, lane-keep, parking assist) in new vehicles |
| **ATR** | Average True Range | A 14-day rolling volatility measure for a stock; used to set ThesisReviewer trigger thresholds |
| **BB** | Bollinger Bands | A technical indicator using a 20-day SMA ± 2 standard deviations as price envelope |
| **BFSI** | Banking, Financial Services & Insurance | Sector group including banks, NBFCs, AMCs, insurance companies |
| **BS6** | Bharat Stage 6 | India's current tailpipe emission standard (equivalent to Euro 6) |
| **CAFE** | Corporate Average Fuel Economy | Fleet-average fuel efficiency standard mandated by MoRTH for OEMs |
| **CASA** | Current Account Savings Account | Ratio of low-cost deposits to total deposits; higher CASA = lower cost of funds for banks |
| **CESL** | Convergence Energy Services Limited | Govt-owned EV procurement aggregator under Ministry of Power |
| **CRAR** | Capital-to-Risk-Weighted-Assets Ratio | Regulatory capital adequacy ratio; RBI minimum 11.5% for commercial banks |
| **CUF** | Capacity Utilisation Factor | Renewable energy term; actual generation ÷ installed capacity × time; ~19–22% for solar in India |
| **CV** | Commercial Vehicle | Trucks, buses; used here as Tata Motors' CV segment vs passenger vehicles |
| **DD** | Design Document | This document |
| **DII** | Domestic Institutional Investor | Mutual funds, insurance, pension funds buying Indian equities |
| **DISCOM** | Distribution Company | State electricity distribution companies; DISCOM payment delays are a key risk for RE companies |
| **DSCR** | Debt Service Coverage Ratio | (EBITDA or operating cashflow) ÷ (annual debt repayments); <1.25 is distress territory for RE |
| **EBITDA** | Earnings Before Interest, Taxes, Depreciation & Amortisation | Operating profitability margin; automobile sector benchmark ~10–20% |
| **EMA** | Exponential Moving Average | A weighted moving average giving more weight to recent prices |
| **EV** | Electric Vehicle | Battery-powered automobile; context-dependent (also Enterprise Value in finance) |
| **EV/MW** | Enterprise Value per Megawatt | Renewable energy valuation metric; compares capital intensity across RE companies |
| **FADA** | Federation of Automobile Dealers Associations | Reports monthly retail dispatch (dealer sales) data for the Indian auto sector |
| **FAME** | Faster Adoption and Manufacturing of Hybrid & Electric Vehicles | Govt subsidy scheme to promote EV adoption; FAME-II closed March 2024, FAME-III pending |
| **FeedbackEntry** | — | One day's entry in the RL daily feedback log; contains actual close, miss analysis, lessons generated |
| **FeedbackLog** | — | The full monthly collection of FeedbackEntry records for one ticker |
| **FII** | Foreign Institutional Investor | Overseas portfolio investors buying/selling Indian equities; tracked as proxy for sentiment |
| **FinalReport** | — | Top-level Pydantic output of a complete sector pipeline run; contains verdict, score, thesis |
| **JLR** | Jaguar Land Rover | Tata Motors' UK luxury automotive subsidiary; significant revenue contributor |
| **LLM** | Large Language Model | AI text generation model (in StockAgent: Qwen via OpenRouter) |
| **MACD** | Moving Average Convergence Divergence | Momentum indicator using the difference between 12-day EMA and 26-day EMA |
| **MNRE** | Ministry of New and Renewable Energy | India's central ministry overseeing renewable energy policy, targets, and MNRE auctions |
| **MPC** | Monetary Policy Committee | RBI's rate-setting body; meets every ~45 days (bimonthly schedule) |
| **NIM** | Net Interest Margin | (Interest income − Interest expense) ÷ Earning assets; key bank profitability metric |
| **NPA** | Non-Performing Asset | A loan overdue >90 days; Gross NPA (GNPA) and Net NPA (after provisions) are key ratios |
| **NSE** | National Stock Exchange of India | Primary exchange for Indian equities; all tickers in StockAgent use the `.NS` suffix |
| **OHLCV** | Open, High, Low, Close, Volume | Five columns of daily price data fetched via yfinance |
| **OEM** | Original Equipment Manufacturer | Automobile assembler (Maruti, Tata, M&M etc.); not components suppliers |
| **P/E** | Price-to-Earnings Ratio | Market cap ÷ annual earnings; used in valuation_catalyst agent |
| **PLI** | Production Linked Incentive | Govt scheme offering cash incentives for domestic manufacturing (auto, RE, IT hardware) |
| **PPA** | Power Purchase Agreement | Long-term contract between a RE generator and a buyer (DISCOM, C&I customer) |
| **PredictionEnvelope** | — | Full 30-day forward forecast for a ticker; stored per monthly cycle as a JSON file |
| **PV** | Passenger Vehicle | Cars and SUVs; Maruti's primary segment |
| **RAG** | Retrieval-Augmented Generation | Technique of fetching relevant documents and injecting them into an LLM prompt |
| **RE** | Renewable Energy | Wind, solar, hydro energy; also shorthand for the `renewable_energy` sector key |
| **RL** | Reinforcement Learning | Here: adaptive weight adjustment via feedback loops (not traditional RL algorithms) |
| **RBI** | Reserve Bank of India | India's central bank; sets the repo rate and supervises banks |
| **RSI** | Relative Strength Index | Momentum oscillator: values >70 = overbought, <30 = oversold |
| **ScoreDB** | Score Database | SQLite database (`data/scores.db`) storing historical analysis verdicts and agent scores |
| **Serper** | — | Google Search-as-API service (serper.dev); returns structured JSON snippets |
| **SIAM** | Society of Indian Automobile Manufacturers | Industry body reporting wholesale dispatch (factory → dealer) statistics |
| **SMA** | Simple Moving Average | Arithmetic mean of closing prices over N days |
| **SSE** | Server-Sent Events | HTTP streaming protocol used by the chat API (`/ui/chat/stream`) |
| **Tavily** | — | Full-page content extraction API (tavily.com); returns full document text, not just snippets |
| **TCV** | Total Contract Value | Total deal value for IT service contracts (multi-year); used in IT sector fundamentals |
| **ThesisReviewer** | — | Conditional LLM agent that fires only after large prediction misses to validate the underlying thesis |
| **VIX** | Volatility Index | India VIX (`^INDIAVIX`): NSE's 30-day implied volatility index; >22 = volatile macro regime |
| **WeightAdapter** | — | STATIC component that deterministically adjusts agent weights based on rolling accuracy |
| **yfinance** | — | Open-source Python library wrapping the Yahoo Finance API; used for OHLCV, fundamentals, macro tickers |
| **DISCOM** | Distribution Company | State electricity boards responsible for last-mile power distribution |

---

## 1. System Overview

### 1.1 What is StockAgent?

StockAgent is an Artificial Intelligence (AI)-powered Indian stock market prediction and analysis platform designed to deliver institutional-grade research on National Stock Exchange (NSE)-listed equities. It operates across four active sectors — automobile, Banking, Financial Services & Insurance (BFSI), Information Technology (IT), and renewable energy (RE) — with a registry of 27 sectors ready for progressive activation.

The platform's core insight is that stock analysis quality degrades without memory. A one-shot analysis tool forgets that it was wrong last month, cannot learn that a specific stock consistently mis-reacts to crude oil shocks, and cannot recognize that December wholesale push data is systematically deceptive for auto OEMs. StockAgent addresses this with a persistent Reinforcement Learning (RL) feedback loop: every prediction is recorded, every miss is root-caused by a Large Language Model (LLM), and the weights of the analysis agents are updated accordingly. After six months, the system holds a proprietary per-ticker rulebook that no general-purpose AI tool can replicate.

The architecture is deliberately heterogeneous. Static, deterministic computations (weight arithmetic, regime classification, confidence decay) are never delegated to an LLM. LLMs are used exclusively where human-like synthesis is needed: interpreting conflicting signals, classifying miss root causes, writing investment theses, and adapting response depth to user sophistication. This separation keeps the system auditable, cost-controlled, and debuggable. The total Serper Application Programming Interface (API) cost at three active tickers is approximately 74% of the free tier, and Tavily usage is under 1% of the free tier due to a monthly disk cache.

### 1.2 High-Level Architecture Diagram

<details><summary>📊 System Architecture Diagram</summary>

<div style="font-family: monospace; font-size: 13px; background: #0d1117; color: #e6edf3; padding: 24px; border-radius: 8px; overflow-x: auto;">

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              StockAgent Platform                                 │
│                                                                                  │
│   ┌─────────────┐      ┌──────────────────────────────────────────────────┐      │
│   │  User       │      │              FastAPI Backend                      │      │
│   │  Browser /  │─────▶│   POST /ui/chat/stream   (SSE)                   │      │
│   │  Chat UI    │◀─────│   GET/PUT /ui/tickers/managed                    │      │
│   └─────────────┘      │   POST /scheduler/forecast                       │      │
│                        │   GET /scheduler/status                          │      │
│                        └────────────────┬─────────────────────────────────┘      │
│                                         │                                         │
│             ┌───────────────────────────┼───────────────────────────┐            │
│             │                           │                           │            │
│             ▼                           ▼                           ▼            │
│   ┌──────────────────┐     ┌────────────────────────┐   ┌──────────────────┐    │
│   │  Chat Pipeline   │     │   Analysis Pipeline     │   │  RL Pipeline     │    │
│   │  (agentic        │     │   (LangGraph sector     │   │  daily_review    │    │
│   │  tool-loop:      │     │    graphs)              │   │  generate_       │    │
│   │  pre-router →    │     │                         │   │  forecast        │    │
│   │  tool loop →     │     │  automobile (9 agents)  │   │  FeedbackAgent   │    │
│   │  sanitize)       │     │  banking_bfsi (6)       │   │  WeightAdapter   │    │
│   └────────┬─────────┘     │  it_sector (8)          │   │  ThesisReviewer  │    │
│            │               │  renewable_energy (6)   │   └────────┬─────────┘    │
│            │               └────────────┬────────────┘            │             │
│            │                            │                         │             │
│            └──────────────┬─────────────┘                         │             │
│                           │                                       │             │
│                           ▼                                       ▼             │
│   ┌───────────────────────────────────────────────────────────────────────────┐  │
│   │                        Data Sources & Storage                             │  │
│   │                                                                           │  │
│   │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌───────────┐  ┌──────────┐  │  │
│   │  │ yfinance  │  │  Serper  │  │  Tavily  │  │  ScoreDB  │  │ JSON     │  │  │
│   │  │ (NSE      │  │ (Google  │  │ (full-   │  │  SQLite   │  │ Memory   │  │  │
│   │  │  OHLCV,   │  │  search  │  │  page    │  │  scores   │  │ Files:   │  │  │
│   │  │  indices, │  │  API)    │  │  extract)│  │  verdicts)│  │ envelope │  │  │
│   │  │  macros)  │  │          │  │          │  │           │  │ feedback │  │  │
│   │  └──────────┘  └──────────┘  └──────────┘  └───────────┘  │ weights  │  │  │
│   │                                                             │ ledger   │  │  │
│   │                                                             └──────────┘  │  │
│   └───────────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

**APScheduler Jobs (background, inside FastAPI process):**
```
04:30 PM IST (Mon–Fri) → rl_daily_review
09:00 AM IST (1st/month) → rl_monthly_forecast
09:00/12:00/15:00 IST (Mon–Fri) → macro_market_news
07:30 AM IST (Mon–Fri) → macro_daily_news
03:30 AM IST (Mondays) → ledger_cleanup_weekly
Dec 31 11:00 PM IST → rl_calendar_update
Midnight IST (daily) → prompt_daily_deploy
```

The `RL Pipeline` box runs `daily_review` and `generate_forecast`, which call `FeedbackAgent`,
`WeightAdapter`, and `ThesisReviewer` as shown — plus `DossierCurator`, which runs every day
(Step 8.5) to maintain the per-ticker dossier in JSON Memory. See §7.1 below, AGENTIC_DESIGN.md
§9.4, and RL_DESIGN.md §23 for the knowledge layer.

</div>
</details>

### 1.3 Technology Stack

| Component | Technology | Version / Notes |
|---|---|---|
| Backend language | Python | 3.13 |
| Web framework | FastAPI | With APScheduler running inside the same process |
| Agent orchestration | LangGraph | `StateGraph` with `Send` fan-out; async and sync paths |
| Schema validation | Pydantic | v2; strict typing throughout |
| LLM inference | OpenRouter | Hybrid tiers — FAST `qwen3.6-flash` (chat), REASONING `qwen3.7-max` (verdict synthesis + RL + the automobile Unified Sector Analyst), BULK `qwen-2.5-72b` (per-dimension sector agents for sectors not yet on the unified path); set via `LLM_MODEL_FAST/REASONING/BULK` |
| Price data | yfinance | Free; NSE tickers require `.NS` suffix (e.g. `MARUTI.NS`) |
| News search | Serper (serper.dev) | Google Search-as-API; 2,500 free queries/month per key |
| Full-page extraction | Tavily | Monthly disk cache reduces actual API calls to <1% of free tier |
| RL scheduling | APScheduler | `BackgroundScheduler` (`CronTrigger`, IST timezone) |
| Score storage | SQLite | `data/scores.db`; accessed via `ScoreStore` |
| Technical indicators | C++ via pybind11 | `stockindicators.pyd`; pure-Python fallback when absent |
| User profile storage | JSON files | `data/user_profiles/{session_id}.json` |
| RL memory storage | JSON files | `data/predictions/{sector}/{ticker}/…` (5 permanent/cyclical files per ticker, incl. `{TICKER}_dossier.json` — see §7.1, §11.4) |

### 1.4 Supported Sectors

| Sector | Key | Key Tickers | Agents | Context Builder | RL Live? |
|---|---|---|---|---|---|
| Automobile & Auto Ancillaries | `automobile` | MARUTI, TATAMOTORS, M&M, HEROMOTOCO, BAJAJ-AUTO, EICHERMOT, TVSMOTORS, ASHOKLEY | 9 | `_build_{agent}` (9 methods) ✅ | ✅ |
| Banking & BFSI | `banking_bfsi` | HDFCBANK, ICICIBANK, SBIN, KOTAKBANK, AXISBANK, BAJFINANCE, MUTHOOTFIN | 6 | `_build_bfsi_{agent}` (6 methods) ✅ | ✅ |
| IT & Technology | `it_sector` | TCS, INFY, WIPRO, HCLTECH, TECHM, LTIM, COFORGE, MPHASIS, PERSISTENT | 8 | `_build_it_{agent}` (8 methods) ✅ | ✅ |
| Renewable Energy | `renewable_energy` | ADANIGREEN, TATAPOWER, NTPC, POWERGRID, SJVN, NHPC, JSWENERGY, WAAREEENER | 6 | `_build_re_{agent}` (6 methods) ✅ | ✅ |

> ⚠️ WARNING: 23 additional sectors (pharma, fmcg, metals, etc.) are mapped in `SectorRegistry.TICKER_SECTOR` but are **disabled by default**. They degrade silently to `AutomobileAgentOrchestrator` with a WARNING log when called. Enable via `config/sector_toggles.json`.

---

## 2. Sector Analysis Engine

### 2.1 BaseAgent Architecture

**File:** `src/backend/shared/pipeline/base_agent.py`

All sector analysis agents inherit from `BaseAgent`. Every subclass must implement exactly three abstract methods:

| Method | Signature | Purpose |
|---|---|---|
| `agent_name` | `@property → str` | Snake-case identifier matching the key in `AGENT_WEIGHTS` |
| `_build_prompt` | `(query, context) → (system_prompt, user_prompt)` | Assembles the LLM prompt from template + injected context |
| `_parse_output` | `(data: dict, ticker: str) → AgentOutput` | Parses the LLM JSON response into a typed `AgentOutput` |

**Context Priority Chain (all STATIC — no LLM):**

```python
BaseAgent._gather_context(query):
  Check 1: RAG_ENABLED=true?
    YES → RAGRetriever.retrieve(search_query) → ChromaDB top-K + optional reranker
  Check 2: ContextBuilder.build(agent_name, query) → live data from fetchers
  FALLBACK: "Stock: MARUTI | Date: 2026-05-17 | Note: Live data unavailable."
```

**Retry Logic (STATIC):** 3 attempts with exponential backoff on `APIError`, `RateLimitError`, `APITimeoutError`. Backoff delay set by `settings.RETRY_DELAY_SECONDS` (default: 2.0 s). Max retries set by `settings.MAX_RETRIES` (default: 3).

**Failure Fallback (STATIC):** If all retries fail, `BaseAgent` returns `AgentOutput(overall_score=0.5, error=str(exc))`. The pipeline never crashes; a neutral score is used rather than propagating an exception.

**PromptEnhancer Integration:**

```python
BaseAgent.run(query):
    base_queries   = CONTEXT_SEARCH_QUERIES          # static, per-agent
    agent_extra    = PredictionStore.load_enhancements(ticker, cycle_id).get(agent_name, [])
    all_queries    = base_queries + agent_extra[:2]  # RL-informed extras (max 2)
    # → passed to ContextBuilder fetchers
```

This is Phase 4 (P4) functionality. The `PromptEnhancer` generates additional Serper queries from the `miss_counter` in `LearningLedger`, giving agents a self-improving search vocabulary for known blind spots.

### 2.2 Orchestrator Execution Model

**File:** `src/backend/shared/pipeline/base_orchestrator.py` (`BaseSectorOrchestrator`, shared by all sectors)
plus `src/backend/sectors/{sector}/pipeline/graph.py` (legacy LangGraph worker pool, one per sector)

```
BaseSectorOrchestrator.analyse_async(ticker)
  │
  ▼
_resolve_ticker()  [LLM: temp=0.0, deterministic]
  "Tata Motors" → StockQuery(ticker="TATAMOTORS", company_name="Tata Motors Ltd", exchange="NSE")
  Fallback: raw input used as ticker if LLM fails
  │
  ▼
_load_learned_weights(ticker)  [STATIC: reads agent_weight_memory.json]
  Returns None if no RL data yet (uses settings.AGENT_WEIGHTS defaults)
  Weights are scoped per ticker: _resolve_weights_for(ticker) reloads
  whenever the query ticker differs from the cached _aggregator_weights_ticker
  │
  ▼
_prefetch_nse_data(query)  [STATIC: NseIndiaApi announcements/boardMeetings/actions, once]
  │
  ▼
_run_agents(query, run_id, progress_callback)
  │
  ├── _unified_enabled()? → SECTOR_NAME in settings.UNIFIED_ANALYST_SECTORS (default: "automobile")
  │
  ├── YES → _run_unified()  ─── UNIFIED PATH (2026-06-12 redesign) ──────────────┐
  │           │                                                                   │
  │           ▼                                                                   │
  │      build_sector_bundle(query, SECTOR_NAME)  [services/data/context/        │
  │        bundle_builder.py]                                                     │
  │        → SectorDataBundle: 10 labeled sections (company_news,                 │
  │          sector_policy_news, macro_context, policy_deep_dive,                 │
  │          fundamentals, technicals, commodities, flows_sentiment,              │
  │          peers_valuation, dossier), each capped at                            │
  │          UNIFIED_SECTION_MAX_CHARS, total capped at                           │
  │          UNIFIED_BUNDLE_MAX_CHARS; ≤3 Serper + ≤1 Tavily, rest free            │
  │           │                                                                    │
  │           ▼                                                                    │
  │      UnifiedAnalyst().run(query, bundle, SECTOR_NAME)                         │
  │        [shared/pipeline/unified_analyst.py]                                   │
  │        ONE call, REASONING tier (qwen3.7-max), temp=0.2,                      │
  │        response_format=json_object, max_tokens=UNIFIED_ANALYST_MAX_TOKENS     │
  │        → dict[str, AgentOutput] — all 9 dimensions, same schemas as legacy    │
  │        Never raises; returns {} on total failure (truncation salvage first)   │
  │           │                                                                    │
  │           ▼                                                                    │
  │      progress_callback(name, score) fired per dimension (batch, after return) │
  │           │                                                                    │
  │           ├── non-empty outputs → proceed to SignalAggregator ────────────────┤
  │           └── empty AND UNIFIED_ANALYST_FALLBACK_LEGACY=true → fall through ───┤
  │                 to legacy LangGraph worker pool                               │
  │                                                                                 │
  └── NO (or fallback) → _run_via_graph()/_run_via_graph_async()  ── LEGACY PATH ─┘
              │
              ▼
        LangGraph StateGraph:
          ┌── resolve_ticker ──────────────────────────────────────────────────┐
          │                                                                     │
          │   input_rail  [STATIC: yfinance fast_info check, non-blocking]     │
          │                                                                     │
          │   make_dispatch_fn → list[Send]  (conditional_edges, fan-out)      │
          │   ┌──────┬──────┬──────┬──────────────────────────────────────────┐ │
          │   ↓      ↓      ↓      ↓                                          │ │
          │   run_agent × N  [parallel, RetryPolicy(max_attempts=2)]          │ │
          │   │  output_rail inside each: clamp score [0,1], inject summary   │ │
          │   │  writes {agent_name: AgentOutput} via _merge_dicts reducer    │ │
          │   └────────────────────────────────────────── fan-in ─────────────┘ │
          └─────────────────────────────────────────────────────────────────────┘
  │
  ▼
SignalAggregator.run(agent_outputs, learned_weights)  [conflict_rail: spread > 0.30 → LLM re-resolution]
  → FinalReport
```

Both paths produce the **same** `dict[str, AgentOutput]` shape and feed the **same**
`SignalAggregator`, so `FinalReport`, `weighted_agent_scores`, and `agent_outputs` are
byte-compatible regardless of which path ran — the UI, chat tool, WebSocket stream, and
RL calibration/lessons/weight-adaptation jobs require zero changes.

**Three-Rail Safety Layer (all STATIC, all non-blocking — legacy worker-pool path:
banking_bfsi, it_sector, renewable_energy, and the automobile fallback):**

| Rail | Where | Trigger | Action |
|---|---|---|---|
| `input_rail` | Before fan-out | Bad ticker / yfinance not found | Append to `rail_errors`; continue pipeline |
| `output_rail` | Inside `run_agent` | `overall_score` out of `[0,1]` or empty summary | Clamp score; inject placeholder summary |
| `conflict_rail` | Inside `aggregate` | Pairwise score spread > 0.30 | Fire LLM re-resolution call |

**Sync vs Async Paths:**

| Path | When Used | Mechanism | LLM Client |
|---|---|---|---|
| Sync | CLI (`main.py`), APScheduler jobs | `analyse()` — unified call or LangGraph with threading | `openai.OpenAI` (synchronous) |
| Async | FastAPI request handlers | `analyse_async()` — unified call or `graph.astream_events()` | `AsyncOpenAI` coroutine |

**Multi-Sector Comparison:**

| Graph | Agents/Dimensions | Path | Key Weight | Unique Signal |
|---|---|---|---|---|
| `automobile` | 9 | **Unified** (one bundle + one analyst call; legacy pool as fallback) | `fundamentals` 0.18 | `sales_demand` (FADA/Vahan dispatch), `competitive_intel` (EV share) |
| `banking_bfsi` | 6 | Legacy (9-agent-style worker pool, 6 agents) | `fundamentals` 0.25 | NPA/NIM/CASA, RBI MPC rate cycle |
| `it_sector` | 8 | Legacy worker pool | `fundamentals` 0.25 | US tech spend, H1B visa risk, TCV deal wins |
| `renewable_energy` | 6 | Legacy worker pool | `fundamentals` 0.30 | CUF/DSCR/EV-MW, MNRE auctions, DISCOM payment risk |

Migrating banking_bfsi, it_sector, or renewable_energy to the unified path requires only
a `prompts/unified.py` module for that sector (mirroring
`src/backend/sectors/automobile/prompts/unified.py`) plus adding the sector name to the
`UNIFIED_ANALYST_SECTORS` CSV setting — `BaseSectorOrchestrator` and `UnifiedAnalyst`
already dispatch generically via `_SECTOR_CLASS_MAPS`.

### 2.3 AgentOutput Schema — Full Field Reference

**File:** `src/backend/shared/schemas/pipeline.py`

| Field | Type | Default | Purpose | 🆕 2026-05? |
|---|---|---|---|---|
| `agent` | `str` | — | Snake-case agent name (e.g. `"sales_demand"`) | — |
| `ticker` | `str` | — | NSE ticker symbol (uppercase) | — |
| `overall_score` | `float [0,1]` | — | Composite score for this agent's dimension of analysis | — |
| `sub_scores` | `{SubScores} \| None` | `None` | Five named dimension scores within the agent's domain | — |
| `key_positives` | `list[str]` | `[]` | Bullish evidence points found by the LLM | — |
| `key_risks` | `list[str]` | `[]` | Risk factors found by the LLM | — |
| `summary` | `str` | `""` | One-paragraph agent analysis in plain English | — |
| `data_freshness` | `str` | `""` | Free-text note on how recent the underlying data is | — |
| `raw_llm_response` | `str` | `""` | Full LLM response (excluded from serialised reports, `exclude=True`) | — |
| `error` | `str \| None` | `None` | Exception message if the agent failed; non-null triggers neutral score | — |
| `ticker_vs_peers` | `str` | `""` | Direct numeric comparison string | 🆕 2026-05 |
| `bull_case_if` | `str` | `""` | Specific catalyst that would push score +0.15 | 🆕 2026-05 |
| `bear_case_if` | `str` | `""` | Specific risk that would push score −0.15 | 🆕 2026-05 |
| `what_changed` | `str` | `""` | What is materially different this cycle vs prior | 🆕 2026-05 |
| `data_confidence` | `float [0,1]` | `0.5` | Data quality signal: 0.3=sparse; 0.7=multi-point; 1.0=direct verified | 🆕 2026-05 |

**Real examples for the five new fields (MARUTI, May 2026 run):**

| Field | Example Value |
|---|---|
| `ticker_vs_peers` | `"MARUTI EBITDA 8.6% vs TATA 10.5% vs M&M 11.2% — MARUTI margin compressed by rubber +18% YoY"` |
| `bull_case_if` | `"Alto K10 EV captures 8% EV share by FY27 — unlocks premium valuation re-rating"` |
| `bear_case_if` | `"Crude >$90/bbl compresses EBITDA margin 100–150 bps; FII outflow >₹5,000 Cr triggers de-rating"` |
| `what_changed` | `"FII holding +120 bps QoQ; dealer inventory days fell from 28 to 22; rubber 3m +18%"` |
| `data_confidence` | `0.72` (multiple FADA + yfinance data points available) |

**Why the five new fields matter for RL:** These fields are captured in `PredictionEnvelope.agent_predictions` at forecast time and later surfaced to `FeedbackAgent` as `predicted_catalysts_by_agent`. This enables **catalyst-level miss attribution** instead of only score-level: "We predicted `FADA dispatch +12% YoY` as the bull case — actual came in at +8%. Magnitude miss, not direction. Lesson: weight `sales_demand` lower for magnitude-sensitive stocks." [→ Section 7.5]

### 2.4 SignalAggregator

**File:** `src/backend/shared/pipeline/signal_aggregator.py`

**Five-step execution (Steps 1, 2, 4, 5 are STATIC; Step 3 is LLM):**

```
Step 1 [STATIC]:  composite = Σ(agent.overall_score × weight) / Σ(weights)
                  Uses learned_weights if available, else settings.AGENT_WEIGHTS

Step 2 [STATIC]:  Conflict detection
                  For every pair: if |score_A - score_B| ≥ 0.30 → add to conflict_flags
                  Threshold 0.30: meaningful analytical disagreement (e.g. BUY vs NEUTRAL)

Step 3 [LLM]:     Full aggregation via AGGREGATION_PROMPT
                  Inputs: all agent scores, weights, composite, conflict list,
                          agent_narratives block (from _build_narrative_block())
                  Outputs: {verdict, final_score, conviction_drivers, top_risks,
                            investment_thesis, conflicts_resolved}
                  Model: REASONING tier — qwen/qwen3.7-max via OpenRouter

Step 4 [STATIC]:  extract_valuation_fields(agent_outputs) — single extraction point
                  shared by the unified and legacy paths (2026-06-12 redesign), pulls
                  from agent_outputs["valuation_catalyst"]
                  → populate FinalReport: price_target, recovery_timeline_quarters,
                    undervalued_by_pct, discount_reason, recovery_catalysts

Step 5 [STATIC]:  Map final_score → verdict label if LLM did not return an explicit one
```

**`_build_narrative_block()` (STATIC):** Collects `bull_case_if`, `bear_case_if`, and `what_changed` from each agent's `AgentOutput` and assembles them into a structured `{agent_narratives}` block injected into the Step 3 LLM prompt. This gives the aggregation LLM specific catalyst language instead of bare score numbers.

**Verdict Thresholds (STATIC — from `settings.SCORE_THRESHOLDS` in `src/backend/shared/config/settings/base.py`):**

| Verdict | Score Range |
|---|---|
| `STRONG BUY` | 0.75 – 1.00 |
| `BUY` | 0.55 – 0.75 |
| `NEUTRAL` | 0.40 – 0.55 |
| `SELL` | 0.20 – 0.40 |
| `STRONG SELL` | 0.00 – 0.20 |

**Scoring example (automobile, warm macro cache):**

```
Agent             Score    Weight    Weighted
sales_demand      0.72  ×  0.16  =  0.1152
fundamentals      0.68  ×  0.18  =  0.1224
risk_macro        0.58  ×  0.13  =  0.0754
pattern_analysis  0.63  ×  0.12  =  0.0756
valuation_catal.  0.71  ×  0.10  =  0.0710
policy_regul.     0.65  ×  0.09  =  0.0585
raw_materials     0.60  ×  0.09  =  0.0540
competitive_intel 0.62  ×  0.09  =  0.0558
sentiment         0.70  ×  0.04  =  0.0280
                            ─────────────
composite = 0.6559 / 1.00  =  0.656  →  BUY
```

This weighted-sum step is identical regardless of how the 9 dimension scores were
produced. On automobile's default unified path, all 9 come from one `UnifiedAnalyst`
call over the shared `SectorDataBundle`; on the legacy path (other sectors, or
automobile's fallback), each score comes from its own per-dimension agent call.

**Weight Priority Chain:**

```
1. Explicitly injected by generate_forecast.py / daily_review.py (highest priority)
   via set_aggregator_weights(weights, ticker) — pins weights to that ticker
2. RL WeightMemory.effective_weights() — auto-loaded by _load_learned_weights(ticker)
   via _resolve_weights_for(ticker), which reloads when the ticker changes
3. settings.AGENT_WEIGHTS config defaults (lowest priority)
```

---

## 3. Sector-by-Sector Agent Reference

### 3.1 Automobile Sector — 9 Dimensions ✅

As of the 2026-06-12 Unified Sector Analyst redesign, automobile runs on the **unified
path** by default (`UNIFIED_ANALYST_SECTORS` includes "automobile"): `build_sector_bundle()`
fetches data once into a `SectorDataBundle`, and `UnifiedAnalyst.run()` makes ONE
REASONING-tier LLM call that returns all 9 dimension scores below as the same
`AgentOutput` subclasses the legacy agents produced. The weights, score-dimension keys,
and output schemas in this section are unchanged — they describe the **scoring contract**,
which both the unified analyst and the legacy per-agent pool must satisfy. The
"Serper Calls"/"Tavily Calls"/"yfinance Used" columns below describe the **legacy
per-agent fetch pattern** (`src/backend/sectors/automobile/pipeline/orchestrator.py`),
which now runs only as the fallback path (`UNIFIED_ANALYST_FALLBACK_LEGACY=true`, engaged
if the unified analyst call fails outright) and remains the live path for banking_bfsi,
it_sector, and renewable_energy.

On the unified path, the equivalent fetches happen once via `bundle_builder.py`'s 10
sections (`company_news`, `sector_policy_news`, `macro_context`, `policy_deep_dive`,
`fundamentals`, `technicals`, `commodities`, `flows_sentiment`, `peers_valuation`,
`dossier`) — e.g. `company_news` (1 Serper) feeds `sales_demand`/`fundamentals`/`sentiment`,
`sector_policy_news` (1 Serper) feeds `policy_regulatory`/`competitive_intel`, and
`macro_context` (yfinance + macro cache, ≤1 Serper on cache miss) feeds `risk_macro`.

#### 3.1.1 Agent List

**Base weights defined in `src/backend/sectors/automobile/config/settings.py`.**

| Agent Key | Weight | Score Dimensions (5) | Serper Calls | Tavily Calls | yfinance Used | Key Gap |
|---|---|---|---|---|---|---|
| `fundamentals` | **0.18** | revenue_ebitda_delta, margin_vs_peers, order_book_pipeline, attrition_headcount, promoter_fii_dii_flow | ≤3 | 0 | quarterly P&L, balance sheet, institutional_holders | yfinance returns annual snapshot, not QoQ |
| `sales_demand` | **0.16** | fada_siam_dispatch, ev_segment_vahan, dealer_inventory, export_import, used_car_price_index | ≤3 | 0 | ✗ | No direct FADA/SIAM/Vahan API; Serper proxy only |
| `risk_macro` | **0.13** | inr_usd_crude_exposure, commodity_prices, rbi_repo_emi_impact, emission_policy_risk, global_geopolitical_risk | 0 (cache HIT) / 3 (MISS) | 0 | INR=X, CL=F, BZ=F, SLX, AA, ^INDIAVIX | RBI rate now live-fetched (✅ FIXED) |
| `pattern_analysis` | **0.12** | price_cycle_position, seasonal_pattern, rsi_macd_bb, breakout_support_zone, peer_correlation | **0** | 0 | 10yr OHLCV, ^CNXAUTO | No live Nifty Auto peer correlation |
| `valuation_catalyst` | **0.10** | pe_discount_vs_peers, earnings_yield_premium, mean_reversion_potential, catalyst_timing, recovery_signal_confidence | 0 | 0 | financials via ContextBuilder | — |
| `policy_regulatory` | **0.09** | fame_ev_subsidy, emission_norms, union_budget_duties, pli_scheme, state_ev_incentives | ≤3 | **≤2** | ✗ | Only agent that uses Tavily |
| `raw_materials` | **0.09** | steel_aluminium, platinum_palladium, crude_oil_polymer, power_tariff, commodities_trend | **1** | 0 | SLX, AA, PPLT, PALL, CL=F, BZ=F | Rubber via Serper news (✅ FIXED) |
| `competitive_intel` | **0.09** | ev_market_share, new_model_pipeline, jv_acquisitions, adas_safety_ratings, competitive_position | ≤3 | 0 | ✗ | No ADAS/NCAP structured data |
| `sentiment` | **0.04** | news_nlp, management_tone, twitter_reddit_sentiment, youtube_view_spikes, dealer_consumer_feedback | ≤3 | 0 | ✗ | No Twitter/Reddit/YouTube API; Serper proxy only |

#### 3.1.2 Context Builder Methods (legacy path)

**File:** `services/data/context/builder.py` — used by the legacy per-agent pool
(other sectors, and automobile's fallback). The unified path uses
`services/data/context/bundle_builder.py` instead (see 2.2).

| Method | Fetchers Called | Serper Calls |
|---|---|---|
| `_build_fundamentals` | `get_fundamentals_context(ticker)` + `fetch_news_context()` | ≤3 |
| `_build_sales_demand` | `fetch_news_context(queries)` | ≤3 |
| `_build_pattern_analysis` | `get_technical_context(ticker)` → RSI(14), MACD(12,26,9), BB(20,2σ), S/R levels | **0** |
| `_build_sentiment` | `fetch_news_context(queries)` | ≤3 |
| `_build_risk_macro` | `get_macro_context()` + `get_macro_cache("automobile")` | 3 on miss; 0 on hit |
| `_build_raw_materials` | `get_raw_materials_context()` + `fetch_news_context(max_queries=1)` | 1 |
| `_build_policy_regulatory` | `fetch_tavily_context()` + `fetch_news_context()` | 3 Serper + 2 Tavily |
| `_build_competitive_intel` | `fetch_news_context(queries)` | ≤3 |
| `_build_valuation_catalyst` | yfinance financials + `fetch_news_context()` | ≤3 |

**Lookup precedence:** `_build_{sector}_{agent_name}` → `_build_{agent_name}` → `_build_generic`

#### 3.1.3 Sector-Specific Signals

The automobile sector is unique in combining **retail dispatch data** (what consumers actually buy) with **wholesale dispatch data** (what OEMs ship to dealers). The critical distinction:

- **FADA dispatch** = retail sales (dealer-to-consumer). Reflects true demand. Reported on ~10th of next month.
- **SIAM dispatch** = wholesale (OEM-to-dealer). Can be inflated by channel stuffing at quarter-end.
- **`SEA_AUTO_004`** seasonal seed: March wholesale push data from SIAM is systematically misleading; the `sales_demand` agent discounts it by −0.06.

**Key automobile-specific signals not present in other sectors:**

| Signal | Source | Agent | What It Means |
|---|---|---|---|
| FADA monthly retail dispatch (by OEM) | Serper news proxy | `sales_demand` | Primary demand indicator; +12% YoY = bullish |
| EV registration via VAHAN portal | Serper news proxy | `sales_demand` | EV penetration; MARUTI lagged; TATA leads |
| Dealer inventory days | Serper channel checks | `sales_demand` | <25 days = demand healthy; >35 days = channel stress |
| Natural rubber MCX price | `_fetch_rubber_price_via_news()` | `raw_materials` | ~15% of BOM cost for tyres; Serper MCX proxy (4h cache) |
| FAME/PLI subsidies | Tavily policy docs | `policy_regulatory` | FAME-II closed; FAME-III pending; PLI disbursement timeline |
| EV market share by OEM | Serper news | `competitive_intel` | TATA leads ~60% share; MARUTI catching up with e-Vitara |
| BS6 Phase 2/CAFE norms | Tavily circulars | `policy_regulatory` | Non-compliance = production stop + recall risk |

#### 3.1.4 Supported Tickers

From `SectorRegistry.TICKER_SECTOR` (`src/backend/sectors/registry.py`):

`MARUTI`, `TATAMOTORS`, `M&M`, `HEROMOTOCO`, `BAJAJ-AUTO`, `EICHERMOT`, `TVSMOTORS`, `ASHOKLEY`, `ESCORTS`, `APOLLOTYRE`, `MRF`, `BALKRISIND`, `MOTHERSON`, `BOSCHLTD`, `SUNDRMFAST`, `ENDURANCE`

---

### 3.2 Banking/BFSI Sector — 6 Agents ✅

#### 3.2.1 Agent List

| Agent Key | Weight | Score Dimensions (5) | Serper Calls | Key Gap |
|---|---|---|---|---|
| `fundamentals` | **0.25** | earnings_quality, net_interest (NIM/CASA), capital_adequacy (CRAR), profitability (RoA/RoE), loan_mix | ≤3 | `rbi_data.py` stub; NPA structured data not wired |
| `risk` | **0.20** | asset_quality_trend, concentration_risk, deposit_stability, regulatory_risk, cyber_fraud_risk | ≤3 | RBI stress-test data unavailable |
| `macro_policy` | **0.20** | rbi_rate_cycle, system_credit, liquidity_conditions, regulatory_actions, fiscal_policy | ≤3 | RBI press releases not scraped directly |
| `institutional` | **0.15** | fii_dii_flow, promoter_activity, mf_holding_change, bulk_block_deals, insider_activity | ≤3 | NSE shareholding API (quarterly) |
| `pattern_analysis` | **0.12** | price_cycle, momentum, breakout_zones, peer_relative_strength, volume_confirmation | **0** | — (yfinance works; zero new wiring needed) |
| `universe_setup` | **0.08** | index_weight, peer_positioning, market_cap_tier, corporate_actions, rebalancing_risk | ≤3 | General LLM knowledge sufficient |

> ⚠️ WARNING: `rbi_data.py` and `npa_metrics.py` raise `NotImplementedError`. All NPA/NIM/CASA signals are currently inferred from Serper news snippets, not structured RBI DBIE data. Fix target: Phase 7.

#### 3.2.2 Context Builder Methods

| Method | Purpose |
|---|---|
| `_build_bfsi_fundamentals` | NIM/CASA/CRAR context via yfinance + Serper |
| `_build_bfsi_risk` | Credit/liquidity risk context; asset quality focus |
| `_build_bfsi_pattern_analysis` | yfinance OHLCV technical context (shared technical prompt) |
| `_build_bfsi_institutional` | Shareholding + FII/DII flows context |
| `_build_bfsi_universe_setup` | Sector peer overview and positioning |
| `_build_macro_policy` | RBI policy and credit growth news via Serper |

#### 3.2.3 Sector-Specific Signals

| Signal | What It Means | Key Metric |
|---|---|---|
| RBI Monetary Policy Committee (MPC) cycle | Rate cuts → NIM compression for banks (they earn less on loans); rate hikes → NIM expansion | Repo rate 5.25% as of Feb 2026 |
| Gross NPA (GNPA) ratio | Asset quality; >4% = distress; PSU banks typically higher than private | System GNPA ~2.7% (FY26 target) |
| Credit cost | Provisions as % of loans; falling credit cost = less bad loan reserve needed | <1% = healthy |
| CASA ratio | Low-cost deposit mix; >40% CASA gives competitive funding advantage | HDFCBANK ~45%, YES Bank ~30% |
| CRAR | Regulatory capital buffer; RBI minimum 11.5% for scheduled commercial banks | HDFCBANK ~18%, SBIN ~14% |
| DISCOM bond guarantees | PSU bank exposure to state DISCOMs | Material for SBIN, PNB, CANARABANK |
| Seasonal: `SEA_BFSI_002` RBI MPC meeting week | Cautious bias (0.80 confidence); market waits for rate decision; macro uncertainty peaks | Bimonthly |

#### 3.2.4 Supported Tickers

`HDFCBANK`, `ICICIBANK`, `SBIN`, `KOTAKBANK`, `AXISBANK`, `INDUSINDBK`, `BANKBARODA`, `PNB`, `CANARABANK`, `FEDERALBNK`, `IDFCFIRSTB`, `BANDHANBNK`, `RBLBANK`, `YESBANK`, `HDFCAMC`, `BAJAJFINSV`, `BAJFINANCE`, `MUTHOOTFIN`, `CHOLAFIN`, `MANAPPURAM`

---

### 3.3 IT Sector — 8 Agents ✅

#### 3.3.1 Agent List

| Agent Key | Weight | Score Dimensions (5) | Tavily? | Key Gap |
|---|---|---|---|---|
| `fundamentals` | **0.25** | revenue_growth (constant currency), ebit_margins (8Q trend), deal_wins (TCV), attrition, valuation | — | `deal_wins.py` stub; TCV data via Serper news only |
| `global_macro` | **0.20** | us_tech_spending, client_sector_mix, currency_headwinds, global_it_demand, macro_sensitivity | — | No structured US tech spend index |
| `risk_macro` | **0.15** | visa_risk, ai_disruption, client_concentration, fx_hedge, talent_risk | — | H1B petition data not wired |
| `peer_benchmark` | **0.12** | revenue_growth_rank, margin_rank, deal_win_rate, attrition_rank, valuation_gap | — | — |
| `pattern_analysis` | **0.10** | price_cycle, momentum, breakout_zones, peer_relative_strength, volume_confirmation | — | (shared technical prompt) |
| `sentiment` | **0.08** | ai_narrative, layoff_signals, management_tone, sector_narrative, news_volume | — | — |
| `transcript_nlp` | **0.06** | guidance_delta, vertical_mix, geography_colour, ai_deal_count, analyst_pushback | **Tavily** | `transcript.py` stub; Tavily for NSE IR pages |
| `insider_smart_money` | **0.04** | fii_dii_flow, promoter_activity, mf_holding_change, bulk_block_deals, insider_activity | — | (shared institutional flow prompt) |

> ⚠️ WARNING: `deal_wins.py` and `transcript.py` raise `NotImplementedError`. Earnings call transcript NLP currently uses Tavily to fetch NSE IR pages rather than structured transcript data. Fix target: Phase 7.

#### 3.3.2 Context Builder Methods

| Method | Purpose |
|---|---|
| `_build_it_fundamentals` | Revenue/deal wins/attrition context via yfinance + Serper |
| `_build_global_macro` | US tech spend + USD/INR context |
| `_build_it_risk_macro` | Visa/pricing/concentration risk context; uses `get_macro_cache("it")` |
| `_build_peer_benchmark` | Peer comparison via Serper (TCS vs INFY vs WIPRO revenue growth) |
| `_build_it_pattern_analysis` | yfinance OHLCV + ^CNXIT index correlation |
| `_build_it_sentiment` | News/analyst coverage/AI narrative context |
| `_build_transcript_nlp` | Management tone + earnings guidance via Tavily IR pages |
| `_build_insider_smart_money` | Insider buys/block deals + FII F&O futures positioning |

#### 3.3.3 Sector-Specific Signals

| Signal | What It Means | Key Metric |
|---|---|---|
| Total Contract Value (TCV) of deal wins | Forward revenue visibility; mega-deals (>$500M) are market-moving | TCS Q4 FY26 TCV $10.2B |
| US enterprise IT spending index | Primary revenue driver; 60–80% of revenue from North America for large-caps | IDC/Gartner quarterly data |
| H1B visa approvals | US immigration policy directly affects offshore headcount capacity | Denial rate <10% = benign |
| Constant-currency (CC) revenue growth | Strips out USD/INR tailwind/headwind; true volume measure | TCS +4.5% CC YoY |
| EBIT margin 8-quarter trend | Sustained margin improvement signals pricing power; contraction signals wage/AI pressure | TCS target 26–28% band |
| GenAI deal count in earnings call | Management tone on AI adoption; deal count rising = structural tailwind | Analyst pushback sub-score |
| Seasonal: `SEA_IT_001` US tech earnings spillover | Correlated positive/negative spillover during US tech earnings season (Jan/Apr/Jul/Oct) | Quarterly |

#### 3.3.4 Supported Tickers

`TCS`, `INFY`, `WIPRO`, `HCLTECH`, `TECHM`, `LTIM`, `COFORGE`, `MPHASIS`, `PERSISTENT`, `LTTS`, `KPITTECH`, `TATAELXSI`, `NIIT`, `MASTEK`, `HEXAWARE`, `HAPPSTMNDS`

---

### 3.4 Renewable Energy Sector — 6 Agents ✅

#### 3.4.1 Agent List

| Agent Key | Weight | Score Dimensions (5) | Tavily? | Key Gap |
|---|---|---|---|---|
| `fundamentals` | **0.30** | capacity_utilisation (CUF), ebitda_quality, debt_serviceability (DSCR), receivables, leverage | — | `mnre_data.py` stub; MNRE auction data not wired |
| `business` | **0.25** | subsector_mix, ppa_quality, pipeline_cred, customer_divers, geography_spread | — | Order book structured data |
| `valuation` | **0.20** | ev_per_mw, ev_ebitda, tariff_vs_auction, pipeline_dcf, implied_irr | — | — |
| `sentiment_policy` | **0.10** | mnre_auction_health, budget_allocation, policy_tailwinds, rbi_rate_impact, module_price | **Tavily** | MNRE portal docs via Tavily |
| `technical` | **0.10** | price_cycle, momentum, breakout_zones, peer_relative_strength, volume_confirmation | — | (shared technical prompt) |
| `risk` | **0.05** | discom_credit, curtailment_risk, ppa_protection, execution_risk, promoter_pledge | — | PRAAPTI DISCOM payment data not wired |

> ⚠️ WARNING: `mnre_data.py` raises `NotImplementedError`. MNRE auction details and DISCOM payment status currently arrive via Serper/Tavily news proxies. Fix target: Phase 7.

#### 3.4.2 Context Builder Methods

| Method | Purpose |
|---|---|
| `_build_re_fundamentals` | DSCR/CUF/revenue context via yfinance + Serper |
| `_build_business` | Order book + MNRE auction context |
| `_build_valuation` | EV/MW + peer valuation context |
| `_build_sentiment_policy` | MNRE policy + state offtake + module price context; Tavily for mnre.gov.in docs |
| `_build_technical` | yfinance OHLCV + ^CNXENERGY index correlation |
| `_build_re_risk` | DISCOM payment delay + regulatory + curtailment risk context |

#### 3.4.3 Sector-Specific Signals

| Signal | What It Means | Key Metric |
|---|---|---|
| CUF (Capacity Utilisation Factor) | Solar: ~19–22%; wind: ~25–35%. Below threshold = underperformance or curtailment | ADANIGREEN FY26 solar CUF ~22% |
| DSCR | Annual cashflow ÷ annual debt service; <1.25 = distress; >1.5 = healthy | TATAPOWER project DSCR ~1.4× |
| EV/MW | Enterprise Value ÷ installed capacity (MW); sector valuation benchmark | ADANIGREEN ~₹8.5 Cr/MW |
| PPA tenure and tariff | Fixed-price 25-year PPAs with DISCOMs or C&I customers lock in revenue | Tariff ₹2.5–3.2/kWh (2026 auctions) |
| DISCOM payment delay (PRAAPTI data) | Outstanding DISCOM receivables; >180 days overdue = credit risk | System-wide overdue ~₹85,000 Cr |
| MNRE auction pipeline | Forward capacity allocation; GW auctioned → GW awarded → GW connected | MNRE FY27 target: 50 GW new |
| Solar module price | Global polysilicon/module prices directly affect RE project capex and IRR | Chinese module ~$0.11/W (2026) |
| Seasonal: `SEA_RE_001` Monsoon solar dip | Jun–Sep generation 15–25% below peak; grid offtake falls with rainfall | Highest confidence (0.80) |

#### 3.4.4 Supported Tickers

`ADANIGREEN`, `TATAPOWER`, `TORNTPOWER`, `CESC`, `SJVN`, `NHPC`, `NTPC`, `POWERGRID`, `ADANIPOWER`, `JSWENERGY`, `INOXGREEN`, `INOXWIND`, `WAAREEENER`, `SUZLON`, `PREMIERENE`, `RPOWER`

---

## 4. Business Model Context Injection

### 4.1 Purpose

Every prompt sent to a sector analysis agent includes a `{business_model_context}` block via `get_business_model_context(ticker)` from `src/backend/sectors/automobile/config/settings.py`. This injection is critical because two tickers in the same sector can require completely different analytical lenses:

- **MARUTI**: ~50% market share in passenger vehicles (PVs); rural-first demand with entry/mid segment; nearly zero EV exposure until e-Vitara; margins anchored by scale and localised supply chain; Suzuki parent relationship.
- **TATAMOTORS**: Conglomerate exposure — CVs + JLR (Jaguar Land Rover) premium luxury in UK/EU + domestic EV leader (~60% India EV share via Tiago/Nexon); JLR profitability drives the stock more than domestic volumes.

Without this context, a `risk_macro` agent evaluating crude oil exposure would apply the same analytical weight to both, missing that TATAMOTORS exports are JLR-denominated (partially offsetting INR weakness) while MARUTI's Indian costs dominate.

### 4.2 Three-Tier Resolution

| Tier | Source | Cache Location | TTL | Quality | When Triggered |
|---|---|---|---|---|---|
| **1 — Curated** | `BUSINESS_MODEL_SNAPSHOTS` dict in automobile `settings.py` | In-memory (Python dict at import time) | N/A (indefinite) | Highest — manually maintained, specific to OEM strategy | 8 known OEMs (MARUTI, TATAMOTORS, M&M, BAJAJ-AUTO, HEROMOTOCO, EICHERMOT, ASHOKLEY, TVSMOTORS) |
| **2 — Dynamic** | Serper news search: `"{ticker} business model revenue portfolio India automobile 2026"` | `data/oem_profiles/{TICKER}.json` | **30 days** | Good — news-based, specific to ticker | Any ticker not in the curated 8 |
| **3 — Fallback** | `BUSINESS_MODEL_SNAPSHOT_DEFAULT` constant | None (in-memory) | N/A | Generic — applies to any automobile OEM | Serper call fails or returns empty |

### 4.3 Source Tags in Prompt

Each injected context block includes a source tag so the LLM can calibrate trust:

| Tag | Meaning | LLM Behaviour |
|---|---|---|
| `[source: curated]` | Manually maintained OEM profile | Treat as authoritative; minimal hedging |
| `[source: news-cache 2026-05-19]` | Date-stamped Serper result | Cross-check headline claims; apply news-freshness scepticism |
| `[source: generic-default]` | No OEM-specific data found | Flag low confidence; avoid specific numerical claims |

### 4.4 Curated OEM List (8 Tickers)

| OEM | Portfolio | EV Status | Revenue Mix | Margin Anchor | Key Watch |
|---|---|---|---|---|---|
| **MARUTI** | Alto K10, Baleno, Swift, Ertiga, Jimny, Brezza | e-Vitara launch FY26; late entrant to EV | ~100% domestic PV | Scale + localised supply chain; rubber/steel are primary levers | Rural demand, dealer inventory days |
| **TATAMOTORS** | Tiago, Nexon, Safari (domestic); Defender, Discovery, F-PACE (JLR) | Domestic EV leader ~60% share; JLR transitioning | Domestic + JLR ~50:50 | JLR pricing power; CV margin cyclical | JLR order book, GBP/INR |
| **M&M** | XUV700, Thar, Scorpio, BE6e (EV), XEV9e (EV) | Aggressive EV push; BE series targeting premium | PV + Tractor + EV | SUV premium positioning | EV launch execution, tractor monsoon |
| **BAJAJ-AUTO** | Pulsar, Dominar, CT100 (2W); Chetak (EV); Qute (3W) | Chetak EV growing; 3W export | Domestic 2W + exports + EV | High 2W margin, export diversification | Export markets (Africa, ASEAN), Chetak share |
| **HEROMOTOCO** | Splendor, HF Deluxe, Passion, Vida (EV) | Vida V2 EV; modest share | ~100% domestic 2W | Volume-driven; entry segment dominance | Rural income, rural 2W demand |
| **EICHERMOT** | Royal Enfield (premium 2W); VE Commercial Vehicles | RE EV concept; not yet commercial | Royal Enfield + VECV | Premium 2W pricing power | RE exports, VECV CV cycle |
| **ASHOKLEY** | M&HCV trucks, buses, defence | eMobility subsidiary; electric buses | CV-dominant | Government/fleet business | Infrastructure capex, fleet replacement |
| **TVSMOTORS** | Apache, Jupiter, iQube (EV), Ronin | iQube growing; export EV focus | Domestic + exports | 3W + scooter + export margin | iQube volume, Indonesia market |

### 4.5 Why Margin Anchors Are Relative, Not Hardcoded

**The problem with absolute percentages:** A snapshot saying "MARUTI EBITDA ~19%" is accurate for one quarter. After one earnings release — a commodity price spike, a new model amortisation — the number is stale and the LLM will cite a wrong figure.

**The solution:** All curated profiles describe margins **relatively**: "Industry-leading EBITDA vs peers; rubber, steel, and crude are the primary levers." This statement is accurate in any market environment. It tells the LLM:
1. MARUTI's margin is structurally *higher* than peers (true in good times and bad)
2. The variables to watch are rubber, steel, crude (not absolute %)
3. The LLM compares against fresh `ticker_vs_peers` data from `AgentOutput` at runtime

**Example of the contrast:**

| Approach | Prompt Injection | Problem |
|---|---|---|
| ❌ Hardcoded % | `"MARUTI EBITDA margin ~19%"` | Stale after 1 earnings quarter; LLM cites wrong number |
| ✅ Relative | `"Industry-leading margins vs peers; rubber/steel/crude are primary levers"` | Timeless; LLM compares dynamically using ticker_vs_peers field |

---

## 5. Data Fetchers — Serper, Tavily, yfinance

### 5.1 Serper (Google Search API)

#### 5.1.1 How It Works

Serper provides a JSON wrapper around Google Search. StockAgent uses two functions:

```python
# services/data/fetchers/news.py
search_serper(query: str, n: int = 5, api_key: str = "") → list[dict]
    # Returns up to n result dicts: {title, snippet, url, date}
    # Endpoint: POST https://google.serper.dev/news
    # No date strings in query — Serper /news is inherently recent

fetch_news_context(queries: list[str], max_queries: int = 3, api_key: str = "") → str
    # Calls search_serper for each query (up to max_queries)
    # Concatenates snippets into a formatted text block for prompt injection
    # Returns formatted string ready for ContextBuilder injection
```

**Critical note from live testing:** Appending date strings like `"2026-05-12"` to Serper queries returns zero results. Serper's `/news` endpoint naturally returns recent articles — no date string needed. All queries in `CONTEXT_SEARCH_QUERIES` use `{month}` and `{year}` template substitution, not ISO dates.

#### 5.1.2 Dual-Key Routing

To stay within the 2,500 queries/month free tier per key, sectors are distributed across two Serper API keys:

```python
# src/backend/shared/config/settings/base.py
def get_serper_key(sector: str) -> str:
    if sector in {"bfsi", "it"} and SERPER_API_KEY_2:
        return SERPER_API_KEY_2
    return SERPER_API_KEY
```

| Key | Env Variable | Sectors | Estimated Monthly Usage |
|---|---|---|---|
| Key 1 | `SERPER_API_KEY` | `automobile`, `renewable_energy` | ~2,450 calls/month (at 5 tickers) |
| Key 2 | `SERPER_API_KEY_2` | `banking_bfsi`, `it_sector` | ~1,490 calls/month (at 5 tickers) |

> ⚠️ WARNING: The `macro_news_fetcher.py` (background macro feed) uses `SERPER_API_KEY_2` first (bfsi/it key), falling back to Key 1. The macro feed runs during market hours (9am–3pm IST) while the RL sector agents run post-market (4:30pm IST), so the keys do not compete for the same time window.

#### 5.1.3 Complete Serper Call Map

| Caller | Agent / Task | Sector | Queries/Call | Cached? | Cache TTL |
|---|---|---|---|---|---|
| `_build_fundamentals` | `fundamentals` | All | ≤3 | No | — (per-run) |
| `_build_sales_demand` | `sales_demand` | automobile | ≤3 | No | — (per-run) |
| `_build_risk_macro` | `risk_macro` | automobile | 3 (miss) / 0 (hit) | Yes | 4h (`get_macro_cache("automobile")`) |
| `_build_raw_materials` | `raw_materials` | automobile | 1 | No | — |
| `_build_policy_regulatory` | `policy_regulatory` | automobile | ≤3 | No | — |
| `_build_competitive_intel` | `competitive_intel` | automobile | ≤3 | No | — |
| `_build_sentiment` | `sentiment` | automobile | ≤3 | No | — |
| `_build_valuation_catalyst` | `valuation_catalyst` | automobile | ≤3 | No | — |
| `_build_bfsi_fundamentals` | `fundamentals` | banking_bfsi | ≤3 | No | — |
| `_build_bfsi_risk` | `risk` | banking_bfsi | ≤3 | No | — |
| `_build_macro_policy` | `macro_policy` | banking_bfsi | 3 (miss) / 0 (hit) | Yes | 4h (`get_macro_cache("bfsi")`) |
| `_build_bfsi_institutional` | `institutional` | banking_bfsi | ≤3 | No | — |
| `_build_bfsi_universe_setup` | `universe_setup` | banking_bfsi | ≤3 | No | — |
| `_build_it_fundamentals` | `fundamentals` | it_sector | ≤3 | No | — |
| `_build_global_macro` | `global_macro` | it_sector | ≤3 | No | — |
| `_build_it_risk_macro` | `risk_macro` | it_sector | 3 (miss) / 0 (hit) | Yes | 4h (`get_macro_cache("it")`) |
| `_build_peer_benchmark` | `peer_benchmark` | it_sector | ≤3 | No | — |
| `_build_it_sentiment` | `sentiment` | it_sector | ≤3 | No | — |
| `_build_insider_smart_money` | `insider_smart_money` | it_sector | ≤3 | No | — |
| `_build_re_fundamentals` | `fundamentals` | renewable_energy | ≤3 | No | — |
| `_build_business` | `business` | renewable_energy | ≤3 | No | — |
| `_build_valuation` | `valuation` | renewable_energy | ≤3 | No | — |
| `_build_sentiment_policy` | `sentiment_policy` | renewable_energy | ≤3 | No | — |
| `_build_re_risk` | `risk` | renewable_energy | ≤3 | No | — |
| `_fetch_rubber_price_via_news` | `raw_materials` | automobile | **1** | Yes | **4h** (`_RUBBER_CACHE`) |
| `get_rbi_repo_rate` | `risk_macro` | automobile / bfsi | **1** | Yes | **60 days** (`_RBI_CACHE`) |
| `get_business_model_context` | All automobile agents | automobile | **1** | Yes | **30 days** (`data/oem_profiles/{TICKER}.json`) |
| `micro_search_loop` | Sector macro pre-fetch | automobile, bfsi, it | 2 per sector per cycle | Yes | 4h (`set_macro_cache`) |
| `search_market_news` (chat) | Chat executor | All | 1–2 | No | — (on-demand) |
| `MacroNewsFetcher` | Background macro feed | All | 2 per run | Yes | Daily (`data/macro_news/`) |

#### 5.1.4 Micro Search Loop

**File:** `main.py` → `_micro_search_loop()` (daemon thread)

The micro search loop pre-fetches sector-level macro news on a configurable schedule so that per-ticker agent runs find a warm cache.

**Sectors covered:** `automobile`, `bfsi`, `it`. Renewable energy is excluded — its primary signals (MNRE auctions, DISCOM payments) are per-company, not sector-wide, so a shared cache provides no benefit.

**Budget calculation (weekdays only — skips Saturday/Sunday via `date.today().weekday() >= 5` guard):**

```
3 sectors × 2 queries/run × 6 cycles/day × 22 trading days/month = 792 Serper calls/month
```

**Cache consumption (ContextBuilder):**

```python
# ContextBuilder._build_risk_macro():
text = get_macro_cache("automobile")
if text:
    # CACHE HIT: skip all 3 Serper calls for risk_macro
    return text
else:
    # CACHE MISS: run 3 Serper calls, populate cache
    text = fetch_news_context(RISK_MACRO_QUERIES, max_queries=3)
    set_macro_cache("automobile", text)
    return text
```

Cache Hit saves **3 Serper calls per ticker per day** for `risk_macro`. At 5 tickers, this is 15 calls/day = 330 calls/month saved on the risk_macro agent alone.

**Configuration constants (all in `settings/base.py`):**

| Variable | Default | Purpose |
|---|---|---|
| `MICRO_CYCLES_PER_DAY` | 6 | Runs every ~4 hours |
| `MICRO_QUERIES_PER_RUN` | 2 | Combined Serper calls per sector per cycle |
| `MACRO_CACHE_TTL_HOURS` | `int(24 // MICRO_CYCLES_PER_DAY)` = 4 | Cache TTL; **derived** from loop interval (Static Audit fix #13) |

#### 5.1.5 Monthly Budget by Scenario

| Scenario | Pre-market Orchestrator | RL Daily Review (30% rerun) | Micro Loop | Serper Total | % of 2,500 Free Tier |
|---|---|---|---|---|---|
| 1 ticker, 21 trading days | 16 × 1 × 21 = 336 | 0.3 × 336 = 101 | 792 | **~1,229** | **49%** ✅ |
| 3 tickers, 21 trading days | 16 × 3 × 21 = 1,008 | 0.3 × 1,008 = 302 | 792 | **~1,848** | **74%** ✅ |
| 5 tickers, 21 trading days | 16 × 5 × 21 = 1,680 | 0.3 × 1,680 = 504 | 792 | **~2,976** | **119%** ⚠️ OVER |

> ⚠️ WARNING: At 5 tickers, monthly Serper usage is approximately 2,976 — 19% over the 2,500 free tier. Safe operating point: **3 tickers** (~1,848/month, 74%). Upgrade to a paid plan or split keys further before adding a 4th or 5th ticker.

**Tavily usage:** 2 calls × 0.04 (monthly cache hit rate) × 5 tickers × 21 days ≈ **8 actual API calls/month** (< 1% of the 1,000/month free tier). [→ Section 5.2.3]

<details><summary>📊 Serper Budget Pie Chart (5 tickers, typical month)</summary>

<div style="padding: 20px; background: #0d1117; border-radius: 8px;">

```svg
<svg viewBox="0 0 400 280" xmlns="http://www.w3.org/2000/svg" style="background:#0d1117; font-family: monospace;">
  <text x="200" y="20" text-anchor="middle" fill="#e6edf3" font-size="13" font-weight="bold">Serper Budget: ~2,976 calls/month (5 tickers)</text>

  <!-- Pie chart: Pre-market 56%, RL daily 17%, Micro loop 27% -->
  <!-- Pre-market 1,680/2,976 = 56.4% → 203° sweep -->
  <circle cx="140" cy="155" r="90" fill="#1a1a2e"/>
  <!-- Pre-market slice (56.4%) - starts at top, 203° -->
  <path d="M140,155 L140,65 A90,90 0 1,1 62.5,205 Z" fill="#2d8cf0"/>
  <!-- RL daily slice (16.9%) - 60.9° -->
  <path d="M140,155 L62.5,205 A90,90 0 0,1 85.5,237 Z" fill="#19be6b"/>
  <!-- Micro loop slice (26.6%) - 95.8° -->
  <path d="M140,155 L85.5,237 A90,90 0 0,1 140,65 Z" fill="#ff9900"/>

  <!-- Legend -->
  <rect x="260" y="80" width="14" height="14" fill="#2d8cf0"/>
  <text x="280" y="92" fill="#e6edf3" font-size="11">Pre-market agents</text>
  <text x="280" y="106" fill="#8b949e" font-size="10">1,680 calls (56%)</text>

  <rect x="260" y="120" width="14" height="14" fill="#19be6b"/>
  <text x="280" y="132" fill="#e6edf3" font-size="11">RL daily review</text>
  <text x="280" y="146" fill="#8b949e" font-size="10">504 calls (17%)</text>

  <rect x="260" y="160" width="14" height="14" fill="#ff9900"/>
  <text x="280" y="172" fill="#e6edf3" font-size="11">Micro search loop</text>
  <text x="280" y="186" fill="#8b949e" font-size="10">792 calls (27%)</text>

  <text x="260" y="220" fill="#ff4d4f" font-size="11" font-weight="bold">Total: 2,976 / 2,500</text>
  <text x="260" y="234" fill="#ff4d4f" font-size="10">⚠ 19% over free tier</text>
  <text x="260" y="248" fill="#8b949e" font-size="10">3 tickers: ~1,848 (74%) ✅</text>
</svg>
```

</div>
</details>

---

### 5.2 Tavily (Full-Page Content Extraction API)

#### 5.2.1 How Tavily Differs from Serper

| Dimension | Serper | Tavily |
|---|---|---|
| Returns | Title + snippet (100–300 chars) | Full document text (up to several KB) |
| Best for | News headlines, price mentions, brief facts | Government circulars, PDFs, earnings call transcripts, policy documents |
| Cost | Per search query | Per URL extraction |
| Latency | ~1–2s | ~3–6s |
| StockAgent usage | High volume (most agents) | Selective (3 specific agents only) |

#### 5.2.2 Which Agents Use Tavily and Why

Only three agents use Tavily, chosen because they need document depth that snippets cannot provide:

| Agent | Sector | Why Tavily | What It Fetches |
|---|---|---|---|
| `policy_regulatory` | automobile | Government FAME/BS6/CAFE circulars are PDFs on mygov.in; snippets miss the fine print on subsidy eligibility dates | FAME scheme notification PDFs, MoRTH emission standard circulars |
| `transcript_nlp` | it_sector | Earnings call transcripts are long; snippets only surface headlines, missing management guidance nuance | NSE IR pages with transcript links; analyst Q&A sections |
| `sentiment_policy` | renewable_energy | MNRE auction tender documents are PDFs; subsidy/tariff details only in full text | MNRE bid document pages, CERC tariff orders |

#### 5.2.3 Monthly Disk Cache

Tavily results are cached on disk to stay within the free tier. The cache key is `MD5(sorted_queries + YYYY-MM)` so the same queries within a calendar month always hit the cache.

**File:** `services/data/fetchers/tavily_fetcher.py`

```
Cache path: data/tavily_cache/{YYYY-MM}/{md5hash}.txt
Cache key:  MD5(sorted(queries) + current YYYY-MM string)
TTL:        Calendar month (cache expires when month changes)
Hit rate:   ~96% after first run of the month
```

#### 5.2.4 Monthly Budget

| Scenario | Without Cache | With Cache (~96% hit rate) |
|---|---|---|
| `policy_regulatory` per ticker per day | 2 Tavily calls | 0.04 calls expected |
| All 3 Tavily agents × 5 tickers × 21 days | 630 calls | **~25 calls/month** |
| % of 1,000/month free tier | 63% | **~2.5%** |

---

### 5.3 yfinance (Free NSE/BSE Price Data)

#### 5.3.1 Module-Level Commodity Cache

**File:** `services/data/fetchers/macro.py`

```python
_COMMODITY_CACHE: dict = {}  # {ticker: {"data": {...}, "date": "YYYY-MM-DD"}}

def _fetch_latest_cached(yf_ticker: str) -> dict[str, float]:
    today = str(date.today())
    cached = _COMMODITY_CACHE.get(yf_ticker)
    if cached and cached.get("date") == today:
        return cached["data"]
    result = _fetch_latest(yf_ticker)
    _COMMODITY_CACHE[yf_ticker] = {"data": result, "date": today}
    return result
```

**Why this matters:** Both `risk_macro` and `raw_materials` agents need crude oil prices (`CL=F`, `BZ=F`). Without this cache, running 5 automobile tickers in a batch would trigger 10 identical yfinance network calls for `CL=F` alone. The daily TTL means the cache is valid for the entire pre-market analysis batch, then resets for the RL daily review run.

Similarly, `_RBI_CACHE` (60-day TTL) prevents concurrent orchestrator threads from firing parallel Serper calls for the same RBI rate. `_RBI_CACHE_LOCK` (a `threading.Lock`) ensures only one thread fires the Serper call; all others block and use the result.

#### 5.3.2 Complete yfinance Ticker Reference

| yfinance Symbol | What It Represents | Used By Agent(s) | Cache Type |
|---|---|---|---|
| `INR=X` | INR per 1 USD exchange rate | `risk_macro` (automobile), `global_macro` (IT) | `_COMMODITY_CACHE` (daily) |
| `CL=F` | WTI Crude Oil Futures (USD/bbl) | `risk_macro`, `raw_materials` | `_COMMODITY_CACHE` (daily) |
| `BZ=F` | Brent Crude Futures (USD/bbl) | `risk_macro`, `raw_materials` | `_COMMODITY_CACHE` (daily) |
| `SLX` | VanEck Steel ETF (USD) | `risk_macro`, `raw_materials` | `_COMMODITY_CACHE` (daily) |
| `AA` | Alcoa Corp (aluminium price proxy) | `risk_macro`, `raw_materials` | `_COMMODITY_CACHE` (daily) |
| `PPLT` | Aberdeen Platinum ETF | `raw_materials` | `_COMMODITY_CACHE` (daily) |
| `PALL` | Aberdeen Palladium ETF | `raw_materials` | `_COMMODITY_CACHE` (daily) |
| `^INDIAVIX` | India Volatility Index (VIX) | `RegimeDetector` | Per-run (no cache) |
| `^CNXAUTO` | Nifty Auto Index | `PatternAnalysis` (automobile), `RegimeDetector` | Per-run |
| `^NSEBANK` | Nifty Bank Index | `PatternAnalysis` (BFSI), `RegimeDetector` | Per-run |
| `^CNXIT` | Nifty IT Index | `PatternAnalysis` (IT), `RegimeDetector` | Per-run |
| `^CNXENERGY` | Nifty Energy Index | `PatternAnalysis` (RE), `RegimeDetector` | Per-run |
| `^NSEI` | Nifty 50 | `RegimeDetector` (FII proxy via 5-day return) | Per-run |
| `{TICKER}.NS` | NSE-listed stock | All agents (OHLCV, fundamentals, fast_info) | Per-run |

**OHLCV period used for technical analysis:** `period="10y"` (10 years), controlled by `settings.PRICE_HISTORY_YEARS = 10`. Shorter history is used for RSI/MACD calculations (14/26 period lookback).

**C++ acceleration:** The `stockindicators.pyd` module (compiled via pybind11) provides faster RSI, MACD, and Bollinger Band calculations. If the module is absent (e.g. fresh clone), `_USE_CPP = False` and pure-Python fallbacks are used automatically.

#### 5.3.3 RBI Repo Rate — Live Fetch vs Settings Fallback

The Reserve Bank of India (RBI) repo rate was previously hardcoded as `6.50%` in `macro.py`, which was 16+ months stale by May 2026 (see STATIC_AUDIT.md gap #1).

**Current implementation** (`services/data/fetchers/macro.py` → `get_rbi_repo_rate()`):

```
Fallback chain:
  1. Check _RBI_CACHE — 60-day TTL (MPC meets every ~45 days)
  2. Live Serper fetch: "RBI Monetary Policy Committee repo rate India latest decision 2026"
     Regex: r"repo rate[^\d]*(\d+\.?\d*)\s*%"
     Stance detection: "cut/lower/dovish" → accommodative; "hike/raise/hawkish" → withdrawal
  3. settings.RBI_REPO_RATE_PCT = "5.25" (fallback if Serper fails)
     → logs WARNING if settings value is >90 days stale
```

**Current value:** 5.25% (confirmed via live Serper fetch, 2026-02-07, stance = neutral).

**Thread safety:** `_RBI_CACHE_LOCK` ensures only one concurrent thread fires the Serper call. All others block and receive the cached result once it's populated.

#### 5.3.4 Rubber Price — Delisted Ticker Workaround

`^TOCOM_RUBBER` (Tokyo Commodity Exchange rubber) is delisted from yfinance. The fallback tickers in settings (`RUBBER_TICKER_FALLBACKS = ["RUBR.L", "SGX:SIR1!", "TOCOM:RSS3"]`) are also unavailable.

**Current implementation** (`_fetch_rubber_price_via_news()`):

```
_RUBBER_CACHE (4-hour in-memory TTL)
  → cache HIT: return cached direction
  → cache MISS:
      Serper("natural rubber price India MCX today 2026", n=3)
      Regex: extract pct from snippet
      Direction words: "fall/drop/down/decline/lower" → negative; "rise/gain/up/rally" → positive
      Returns: {"current": 0, "change_3m_pct": ±X.XX, "source": "serper_news"}
```

**Important:** The rubber result is a **direction percentage** derived from news text (not an absolute price). This is sufficient for the `raw_materials` agent's `commodities_trend` sub-score. Absolute rubber price requires a paid data provider.

**Cache scope:** `_RUBBER_CACHE` is module-level and shared across all tickers in a batch. One Serper call per 4-hour window serves all 5 automobile tickers.

---

## 5.4 New Structured Data Sources — Zero-Credential (May 2026)

Three new data sources integrated alongside the existing Serper/Tavily/yfinance stack. All three require no API keys, no accounts, and are cached to avoid repeated external hits.

### 5.4.1 NSE Market Intelligence — `services/data/fetchers/nse_market.py`

**Source:** National Stock Exchange of India via `nsepython` (community library that handles NSE's Cloudflare cookie handshake).

**Data provided:**
- FII/DII daily net flows in Cr (structured numbers, not news snippets)
- Bulk deal net buyers and sellers (>0.5% of listed shares in one transaction)
- Per-ticker bulk deal activity lookup
- Upcoming board meeting / earnings dates

**Caching:** In-process dict keyed by date (`_CACHE["YYYY-MM-DD"]`). Zero overhead for repeated calls within one process; NSE hit exactly once per analysis session.

**ContextBuilder integration:**

| Builder method | Focus mode | Replaces Serper query |
|---|---|---|
| `_build_risk_macro()` | `"fii_dii"` | `"{ticker} FII DII India net buying today"` |
| `_build_sentiment()` | `"bulk_deals"` | `"{ticker} BSE bulk deal block trade {month}"` |
| `_build_bfsi_risk()` | `"fii_dii"` | FII selling pressure in BFSI risk context |
| `_build_it_risk_macro()` | `"fii_dii"` | FII outflow context for IT macro risk |
| `_build_macro_policy()` | `"fii_dii"` | FII/DII in BFSI macro policy context |

**daily_review.py integration (G8):** FII/DII + bulk deal context injected into `market_context_today` before `FeedbackAgent` so it can attribute price moves to institutional flows rather than news inference.

**Limitations:** FII/DII data is T-1 (published after 6 PM IST). nsepython can break if NSE changes internal endpoints — wrapped in try/except, falls back silently to Serper-only.

### 5.4.2 AMFI MF Sector Herding — `services/data/fetchers/mf_herding.py`

**Source:** `mfapi.in` (community wrapper around AMFI official NAV data; ~14,000 schemes; AMFI is SEBI-regulated and publishes NAV by regulatory obligation).

**Data provided:**
- 30-day NAV momentum across sector ETFs (Nifty Auto ETF, Nifty Bank ETF, Nifty IT ETF, New Energy ETF)
- Institutional flow signal: `INFLOW | OUTFLOW | NEUTRAL`

**Caching:** In-process dict keyed by ISO week (`_CACHE["YYYY-WNN:sector"]`). Weekly cadence — MF NAV changes daily but sector trend is stable across 7 days.

**ContextBuilder integration:** `_build_sentiment()` appends MF herding signal for the current sector. Provides a signal type Serper cannot surface: sector-level institutional accumulation vs distribution pressure before it shows in price.

**Limitations:** NAV is end-of-day, not real-time. Wrapper is community-maintained with no SLA. AMFI publishes NAV daily around 10–11 PM IST, so intraday signal is not available.

### 5.4.3 IIMA 4-Factor Regime — `core/intelligence/rl/algorithms/factor_regime.py`

**Source:** Indian Institute of Management Ahmedabad — `www.iimahd.ernet.in/~iffm/Indian-Fama-French-Momentum/`

**Data provided:**
- Monthly WML (Winners Minus Losers) momentum factor: `MOMENTUM | REVERSAL` regime
- SMB (size): `SMALL_CAP | LARGE_CAP` market tilt
- HML (style): `VALUE | GROWTH` market tilt

**Caching:** 30-day CSV file cache + daily in-process dict. The CSV is ~50 KB and downloaded once per month.

**ContextBuilder integration:** `_build_risk_macro()` appends factor regime as a long-run prior so the LLM understands the structural market background.

**WeightAdapter integration:** `update()` now accepts `factor_regime: dict | None`. `get_regime_penalty_scale(agent, regime)` returns:
- `0.80` in REVERSAL regime for `pattern_analysis`, `competitive_intel`, `sales_demand` (momentum agents are structurally disadvantaged)
- `0.85` in MOMENTUM regime for `fundamentals`, `risk_macro` (value/macro agents lag in momentum markets)
- `1.0` in WEAK regime or for non-disadvantaged agents

**Critical limitation:** Data vintage ends **March 2023** (3 years stale). This is the last CSV available on the IIMA server as of May 2026. Use as a long-run structural prior ONLY — NOT as a live signal. `RegimeDetector` (`core/intelligence/regime/detector.py`) remains the authoritative source for live regime state.

**Trust:** Academic data from IIMA faculty (Profs. Agarwalla, Jacob, Varma — peer-reviewed research, underlying data from CMIE Prowess). TLS cert hostname mismatch on `iimahd.ernet.in` is a government university IT issue, not a security concern; `verify=False` is intentional and documented.

---

## 6. Chat Pipeline (Agentic Tool-Loop)

> Canonical reference: [`CHAT_ARCHITECTURE.md`](CHAT_ARCHITECTURE.md). Summary below.

### 6.1 Architecture Overview

**File:** `services/api/routes/ui_data.py` — the old `chat_graph.py` 3-node LangGraph DAG
(`dispatch → executor → synthesize`) was removed 2026-06-03.

The chat assistant is an **agentic streaming tool-loop** served at `POST /ui/chat/stream` (SSE), with a
non-streaming twin at `POST /ui/chat`. Flow:

```
build prompt (strong system prompt + IST market session + session history)
  → deterministic intent pre-router  (_detect_invest_intent → pre-run screen_stocks + news
                                       for buy/sell/momentum queries; plan-and-execute)
  → agentic tool loop  (FAST tier qwen3.6-flash, ≤4 rounds, _CHAT_TOOLS)
  → _sanitize_answer → stream tokens
```

The pre-router is what guarantees buy/sell/momentum queries get the right candidates and real catalysts
regardless of the model's tool-routing reliability. The old DAG could only plan tools once, up front.

**Model:** FAST tier `qwen/qwen3.6-flash`; `_chat_completion` falls back to REASONING `qwen/qwen3.7-max`
on rate-limit/5xx (retry + backoff first).

**Session memory:** in-process `_SESSION_HISTORY[session_id]` (capped 12 msgs) — replaced the LangGraph
`MemorySaver`; client sends only `session_id`.

<details><summary>📊 Flowchart — HISTORICAL (the removed 3-node DAG; kept for reference only)</summary>

<div style="font-family: monospace; font-size: 12px; background: #0d1117; color: #e6edf3; padding: 20px; border-radius: 8px;">

```
POST /ui/chat/stream
{"message": "How is MARUTI trending?", "session_id": "abc-123"}
          │
          ▼
┌─────────────────────────────────────────────────┐
│  dispatch node  [LLM: qwen, temp=0.0, ~400 tok] │
│  Reads: last 8 messages + user_profile.json      │
│  Outputs: tasks[], user_tier, browsing_strategy  │
│  SSE: {"event":"dispatch","tier":"active",...}   │
└──────────────────────┬──────────────────────────┘
                       │ asyncio.gather(all tasks)
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼
  get_live_price  get_historical  search_market_news
  (yfinance)      (yfinance)      (Serper)
        │              │              │
  SSE tool_start  SSE tool_start  SSE tool_start
        │              │              │
  SSE tool_result SSE tool_result SSE tool_result
        │              │              │
        └──────────────┴──────────────┘
                       │ collected results
                       ▼
┌─────────────────────────────────────────────────┐
│  synthesize node  [LLM: qwen, streaming]         │
│  SSE: {"event":"thinking"} (if think phase)      │
│  SSE: {"event":"token","text":"..."} (streaming) │
│  SSE: {"event":"done"}                           │
│  Post-turn: saves/updates user_profile.json      │
└─────────────────────────────────────────────────┘
                       │
                       ▼
               END (response complete)
```

</div>
</details>

### 6.2 Deterministic Intent Pre-Router

Before the loop, `_detect_invest_intent(message)` classifies a screen-type intent from keywords and the
target sector. When both are present it runs the plan itself — `screen_stocks` + `search_market_news` —
and injects the results, so the right candidates and real headlines reach the model deterministically.

| Intent phrase | Action | `screen_stocks` mode |
|---|---|---|
| invest / buy / accumulate / undervalued / oversold | buy | `value` — beaten-down near 1-mo lows (buy-the-dip) |
| book profit / trim / take profit / overbought | sell | `profit` — extended near 1-mo highs |
| momentum / leaders / strongest / breakout | momentum | `momentum` — 1-week leaders |

> The earlier user-tier profiling (casual/active/expert via `user_profile.py`) is **dormant** — it was
> only used by the removed DAG. Retained for a future tier-adaptive verbosity feature.

### 6.3 Tool Catalogue (12 tools, all STATIC except `run_agent_analysis`)

| Tool Name | Data Source | Notes |
|---|---|---|
| `screen_stocks(sector, mode)` | yfinance 1-mo windows | **Insight engine** — value/momentum/profit screen |
| `get_sector_snapshot(sector)` | yfinance + DB | Index + per-stock movers (gainers/losers) + verdicts |
| `get_live_price(symbol)` | yfinance | NSE-first resolution, freshness-labelled |
| `get_historical_prices(symbol, days)` | yfinance OHLCV (close-to-close %) | Trend/comparison |
| `get_stock_analysis(ticker)` | SQLite ScoreDB | Latest verdict |
| `get_analysis_history(days)` | SQLite ScoreDB | Verdict trend |
| `get_rl_prediction(ticker)` | prediction JSON | RL verdict + confidence |
| `get_rl_insights()` | weight memory JSON | Agent weights + accuracy |
| `get_macro_news()` | macro cache → live Serper fallback | Self-heals when cache empty |
| `get_ticker_dossier(ticker)` | `{TICKER}_dossier.json` digest | Accumulated thesis, response signatures, guidance, flow notes |
| `search_market_news(query)` | Serper `/news` + RRF fusion, Tavily fallback | Multi-query (see retry below) |
| `run_agent_analysis(ticker)` **[LLM]** | Full 9-agent sector pipeline (~45s) | Deep mode |

> Every dispatched tool — including `get_rl_prediction`, `get_macro_news`, and
> `get_historical_prices` — now has a matching `_CHAT_TOOLS` schema, enforced by a
> drift-guard test (previously these three were documented but uncallable).

**`search_market_news` geo detection:**

| Query Content | India Terms? | `geo` Used |
|---|---|---|
| "why did Nifty fall" | Yes (Nifty) | `"in"` (India) |
| "OpenAI impact on IT stocks" | No | `None` (global) |
| "why is the market down" | No | `"in"` (default India) |

**Retry strategy for `search_market_news`:**
1. Serper `/news` with detected geo, 5 results
2. Auto-retry if 0 results and no India terms (strip geo + prepend "India Nifty")
3. Conditional second query if <3 results and global entity detected
4. Fallback to Tavily only when all Serper passes return 0 results

### 6.4 Historical Price % Change — Close-to-Close

> ⚠️ WARNING: **Bug fixed 2026-05-19.** `get_historical_prices` was computing intraday percentage change (open-to-close) rather than day-over-day (close-to-close). This produced misleading "daily" percentage figures.

**Current behaviour (post-fix):** Each day's percentage change = `(close[d] − close[d−1]) / close[d−1] × 100`. This is the standard day-over-day return and matches NSE daily gain/loss figures.

**Example:**

```
May 13 Sensex close: 74,609
May 12 Sensex close: 74,559
Day-over-day change: (74,609 − 74,559) / 74,559 × 100 = +0.07%

Intraday (old, wrong): (May 13 close − May 13 open) / May 13 open × 100
  = (74,609 − 74,780) / 74,780 × 100 = −0.23%  ← different number, wrong metric
```

### 6.5 Anti-Fabrication & Grounding

The loop is grounded so the model answers only from fetched data:
- **IST market session** (`_nse_market_context` → `nse_calendar.market_session`) — labels prices `live`
  vs `last close <date>`; the model is told whether the market is pre-open, open, or closed.
- **NSE-first symbol resolution** (`_resolve_yf_symbol`) — name aliases → registry → India-preferred search.
- **Multi-query + RRF** (`_chat_tool_search_news`, `_rrf_fuse`) — fuses several query variants for relevance.
- **Deterministic sanitizer** (`_sanitize_answer`) — strips banned disclaimer labels. (An LLM Reflexion
  self-critique was trialled and rejected — on qwen it hallucinated; grounding at the source is more reliable.)

### 6.6 Session Continuity

In-process `_SESSION_HISTORY: dict[session_id → list[turn]]` (last 12 messages), cleared on restart —
same semantics as the removed LangGraph `MemorySaver`, no graph dependency. The client sends only
`session_id`; when the user says "what about IT?" after discussing MARUTI, the carried history resolves
the referent without resending it.

---

## 7. Reinforcement Learning Pipeline

### 7.1 Overview

The RL pipeline gives StockAgent persistent memory across months. Every prediction is written to a JSON envelope; every miss is root-caused by the `FeedbackAgent` LLM; agent credibility weights are updated by the deterministic `WeightAdapter`. After six months, the system holds a per-ticker behavioural rulebook.

The 5th permanent memory file, `{TICKER}_dossier.json`, adds a **knowledge layer** on top of
this numeric loop: `DossierCurator` runs daily (Step 8.5, hit or miss) to maintain a per-ticker
thesis, response signatures, guidance, recurring catalysts, flow notes, and an episodic
observation buffer, with a weekly LLM distillation pass. Full schema, merge rules, and
consumption surfaces (agent prompts + chat `get_ticker_dossier`) are in
**RL_DESIGN.md §23 (Knowledge Layer)**.

```
Month 1:   Forecasts from config defaults + pre-seeded seasonal patterns
Month 3:   Weights earned from 60 days of real accuracy data
Month 6:   Lessons accumulated, seasonal seeds validated, cross-ticker sector patterns active
Month 12:  Proprietary calendar + ledger; miss rate on known patterns approaches near-zero
```

**Four RL agents:**

| Agent | Type | File | When It Runs |
|---|---|---|---|
| `FeedbackAgent` | **LLM** (Qwen, temp=0.3) | `core/intelligence/rl/agents/feedback_agent.py` | Daily post-market; once per ticker per trading day |
| `WeightAdapter` | **STATIC** (deterministic) + per-agent calibration reward blend (`RL_CALIBRATION_REWARD_ENABLED`) | `core/intelligence/rl/agents/weight_adapter.py` | After FeedbackAgent; no LLM |
| `ThesisReviewer` | **LLM** (Qwen, temp=0.1) | `core/intelligence/rl/agents/thesis_reviewer.py` | Conditional; only on significant misses (~1–3×/month) |
| `DossierCurator` | **LLM** (Qwen, temp=0.2) | `core/intelligence/rl/agents/dossier_curator.py` | Daily, Step 8.5 (every day, never fatal) + weekly distillation |

<details><summary>📊 RL Monthly Cycle Flowchart</summary>

<div style="font-family: monospace; font-size: 12px; background: #0d1117; color: #e6edf3; padding: 20px; border-radius: 8px;">

```
Month Start (1st trading day)
           │
           ▼
┌─────────────────────────────────────────────────┐
│  generate_forecast.py                           │
│  1. Load WeightMemory (bootstrap from base wts) │  STATIC
│  2. SeasonalCalendar → per-day adjustments      │  STATIC
│  3. PromptEnhancer → extra search queries       │  STATIC
│  4. Run N-agent sector pipeline (LLM × N)       │  LLM
│  5. PriceInterpolator → 30-day price path       │  STATIC + LLM
│  6. Confidence decay 0.5%/day                   │  STATIC
│  7. Save PredictionEnvelope JSON                │  STATIC
└─────────────────────────────────────────────────┘
           │
           ▼  (days 1–30, every weekday at 4:30pm IST)
┌─────────────────────────────────────────────────┐
│  daily_review.py                                │
│  Step 0: RegimeDetector (VIX/FII/RSI)           │  STATIC
│  Step 1: Load today's forecast row              │  STATIC
│  Step 2: Fetch actual close (yfinance)          │  STATIC
│  Step 3: Compute error metrics                  │  STATIC
│  Step 4: FeedbackAgent → miss analysis          │  LLM
│  Step 5: WeightAdapter → update weights         │  STATIC
│  Step 5.5: Regime multipliers (ephemeral)       │  STATIC
│  Step 6: LearningLedger → merge lessons         │  STATIC
│  Step 6.5: ConvictionTracker → streak           │  STATIC
│  Step 7: Revise remaining forecasts             │  STATIC
│    + apply_lesson_emphasis (tagged lessons      │  STATIC
│      fire on today's event_tags)                │
│  Step 8: Append FeedbackEntry to log            │  STATIC
│  Step 8.5: DossierCurator → update ticker       │  LLM
│      dossier (every day, never fatal)           │
│  Step 9: SeasonalValidator (month-end only)     │  STATIC
│  Step 10: Control lane — score yesterday's      │  LLM
│      bare-model call + predict next session     │
│      (baseline duel, RL_DESIGN §25)             │
└─────────────────────────────────────────────────┘
           │
           ▼ (end of month)
┌─────────────────────────────────────────────────┐
│  Month rollover                                  │
│  • WeightMemory carries forward (permanent)     │
│  • LearningLedger carries forward (permanent)   │
│  • Old envelope + log archived                  │
│  • Next month: generate_forecast() fires again  │
└─────────────────────────────────────────────────┘
```

</div>
</details>

### 7.2 PredictionEnvelope — Full Schema Reference

**File:** `src/backend/shared/schemas/feedback.py` → `PredictionEnvelope`

**Storage path:** `data/predictions/{sector}/{TICKER}/{TICKER}_{YYYY-MM}_prediction_envelope.json`

| Field | Type | Populated By | Purpose |
|---|---|---|---|
| `ticker` | `str` | `generate_forecast.py` | NSE ticker symbol |
| `sector` | `str` | `generate_forecast.py` | Which sector pipeline generated this envelope |
| `cycle_id` | `str` | `generate_forecast.py` | e.g. `"MARUTI_2026-04"` |
| `generated_at` | `str` (ISO datetime) | `generate_forecast.py` | When the envelope was created |
| `base_close` | `float` | `generate_forecast.py` | Actual closing price on day 0 |
| `weight_version_used` | `int` | `generate_forecast.py` | Which `WeightMemory` version was active |
| `forecast_profile_shape` | `str` | `PriceInterpolator` | `"linear"` / `"front_loaded"` / `"back_loaded"` / `"volatile"` |
| `forecast_profile_monthly_pct` | `float` | `PriceInterpolator` | Expected monthly return % (LLM-calibrated or ATR-scaled static) |
| `forecast_profile_source` | `str` | `PriceInterpolator` | `"llm"` or `"static"` (audit field) |
| `daily_forecasts` | `list[DailyForecast]` | `generate_forecast.py` + daily revision | 30-day forecast rows |
| `conviction_streak` | `ConvictionStreak` | `ConvictionTracker` | Current verdict streak + reversion prior |
| `agent_predictions` | `dict[str, dict]` | `generate_forecast.py` | 🆕 Per-agent catalyst snapshot at forecast time |

**`agent_predictions` example (MARUTI, forecast time):**

```json
"agent_predictions": {
  "sales_demand": {
    "bull_case_if": "FADA dispatch +12% YoY if rural recovery holds",
    "bear_case_if": "Crude >$90 compresses margin 100-150bps",
    "ticker_vs_peers": "MARUTI dispatch +8% vs TATA -2% this month",
    "what_changed": "FII inflow +₹2,000Cr; dealer inventory down 3 days",
    "data_confidence": 0.82
  }
}
```

### 7.3 DailyForecast — Full Field Reference

**File:** `src/backend/shared/schemas/feedback.py` → `DailyForecast`

| Field | Type | Purpose |
|---|---|---|
| `day` | `int` | 1-indexed from cycle start |
| `date` | `str` | ISO date `"YYYY-MM-DD"` |
| `predicted_close` | `float` | Forecast closing price |
| `predicted_change_pct` | `float` | `(predicted_close − base_close) / base_close × 100`; computed on write |
| `predicted_verdict` | `str` | `BUY` / `SELL` / `NEUTRAL` etc. |
| `predicted_agent_scores` | `dict[str, float]` | Per-agent composite scores frozen at forecast time |
| `predicted_agent_subscores` | `dict[str, dict[str, float]]` | Per-agent sub-dimension scores (e.g. `{"fundamentals": {"revenue_ebitda_delta": 0.72}}`) |
| `confidence` | `float [0,1]` | Base confidence decayed at 0.5%/day from `base_confidence` |
| `key_assumptions` | `list[str]` | Human-readable assumptions underlying this day's forecast |
| `revised` | `bool` | `True` after a daily review revises this row |
| `revision_count` | `int` | How many times this row has been revised |
| `predicted_agent_catalysts` | `dict[str, dict]` | 🆕 Per-agent bull/bear catalyst predictions for this day |

**`predicted_agent_catalysts` example (Day 1, MARUTI):**

```json
"predicted_agent_catalysts": {
  "sales_demand": {
    "bull_case_if": "FADA +12%",
    "data_confidence": 0.7
  },
  "risk_macro": {
    "bear_case_if": "Crude >$90",
    "data_confidence": 0.9
  }
}
```

### 7.4 Daily Review — Step-by-Step

**File:** `core/intelligence/rl/workflows/daily_review.py`

| Step | Name | Type | What It Does | Early Exit? |
|---|---|---|---|---|
| **0** | `RegimeDetector.detect()` | **STATIC** | Fetches `^INDIAVIX`, Nifty 5-day return, sector RSI; classifies into 6 regimes | No |
| **1** | Load forecast row | **STATIC** | `PredictionStore.load_envelope(cycle_id)` → today's `DailyForecast` | Exits if no envelope exists |
| **2** | Fetch actual close | **STATIC** | `yfinance.download("{TICKER}.NS", period="5d")["Close"]` → `actual_close` | Exits if price unavailable |
| **3** | Compute error metrics | **STATIC** | `price_error_pct = (actual − predicted) / predicted × 100`; `classify_direction()` → UP/DOWN/FLAT; timing accuracy | No |
| **4** | `FeedbackAgent.run()` | **LLM** | Receives full context including `predicted_catalysts_by_agent` 🆕; returns miss_type, missed_factors, lessons, revised_context | — |
| **5** | `WeightAdapter.update()` | **STATIC** | 3-stage algorithm: accuracy→deltas→apply+normalize | No |
| **5.5** | Regime multipliers | **STATIC** | Apply ephemeral regime multipliers to get `effective_weights`; **NEVER written to weight_memory.json** | No |
| **6** | LearningLedger merge | **STATIC** | `merge_lessons_into_ledger()`: dedup by pattern, blend confidence, propagate to sector/market ledgers | No |
| **6.5** | ConvictionTracker | **STATIC** | Update streak days + `reversion_prior` formula; inject streak warning at `streak ≥ 8` | No |
| **7** | Revise remaining forecasts | **STATIC** | Re-run `SignalAggregator` with `effective_weights`; apply lesson rules + seasonal adjustments | **YES** → early exit if `direction_correct AND \|error\| < 0.5%` |
| **8** | Persist FeedbackEntry | **STATIC** | Atomic write (`.tmp` → rename); idempotent (replaces same-date entry) | No |
| **8.5** | `DossierCurator.run()` | **LLM** | Updates ticker dossier (thesis, signatures, guidance, catalysts, flows, observations); runs **every day, hit or miss**; static merge enforces all bounds; never raises | No |
| **9** | SeasonalValidator | **STATIC** | Runs **only on last trading day of month** (not daily); validates pattern fire/no-fire | No |
| **10** | Control lane (`run_control_lane_step`) | **LLM** | Baseline duel: scores yesterday's bare-model prediction, then a bare LLM (same info, no agents/weights/dossier) predicts the next session; feeds the monthly scorecard (RL_DESIGN §25); never raises | No |

**Step 7 Early Exit (Critical Optimisation — 2026-05-17):**

```python
# daily_review.py
if direction_correct and abs(price_error_pct) < settings.RL_AGENT_RERUN_THRESHOLD_PCT:
    # Skip full 9-agent orchestrator re-run → ~70% reduction in daily LLM calls
    # Still run: WeightAdapter, LedgerMerge, ConvictionTracker, FeedbackEntry write
    return
```

`RL_AGENT_RERUN_THRESHOLD_PCT = 0.5` (in `settings/base.py`). Set to `0.0` to disable early exit entirely.

**Step 7 lesson emphasis:** `apply_lesson_emphasis()` (STATIC) checks today's `event_tags`
(from `tag_events()` + `calendar_day_tags()`) against each `Lesson.trigger_tags`; matches with
`eff_confidence ≥ RL_LESSON_MATCH_MIN_CONF` nudge `prioritise_agents`/`discount_agents` scores by
±`RL_LESSON_EMPHASIS_DELTA` (capped at ±`RL_LESSON_EMPHASIS_CAP`). See RL_DESIGN.md §23.3.

**Step 9 ThesisReviewer:** When `should_review()` returns `True`, the `ThesisReviewer` LLM fires. [→ Section 7.8]

### 7.5 Catalyst Persistence 🆕 2026-05

**The data flow from `AgentOutput` → `PredictionEnvelope` → `FeedbackAgentInput`:**

```
generate_forecast.py:
  Run all N agents → AgentOutput[].{bull_case_if, bear_case_if, data_confidence}
  → Store in PredictionEnvelope.agent_predictions
  → Store per-day in DailyForecast.predicted_agent_catalysts

daily_review.py (Day N):
  Load PredictionEnvelope.agent_predictions
  → Pack as FeedbackAgentInput.predicted_catalysts_by_agent
  → Pass to FeedbackAgent.run()
  → Also stored in FeedbackEntry.predicted_catalysts_snapshot (audit trail)
```

**Before catalyst persistence (what RL saw):**

```
"sales_demand was the primary miss agent (unknown why)"
→ WeightAdapter: penalise sales_demand by −0.03
→ Lesson: "sales_demand often misses" (useless — no causal explanation)
```

**After catalyst persistence (what RL now sees):**

```
[PREDICTED CATALYSTS FROM LAST CYCLE — did they materialise?]
  sales_demand bull_case_if: "FADA dispatch +12% YoY if rural recovery holds"
    → actual FADA came in at +8% — magnitude miss, not direction
  risk_macro bear_case_if: "Crude >$90 compresses margin 100-150bps" (confidence=0.90)
    → crude stayed at $84 — bear case did NOT materialise

→ FeedbackAgent: "sales_demand predicted +12% YoY (direction correct, magnitude wrong).
                  Classification: magnitude miss (0.25× penalty).
                  Lesson: sales_demand tends to be optimistic on rural demand magnitude
                  when crude is stable. Reduce confidence when FADA growth > 10% predicted."
```

**Low-confidence penalty reduction:** If `data_confidence < 0.5`, the `FeedbackAgent` system prompt instructs the LLM to apply a lighter penalty for magnitude misses — the agent signalled its own uncertainty.

### 7.6 FeedbackAgent

**File:** `core/intelligence/rl/agents/feedback_agent.py`

| Parameter | Value |
|---|---|
| Model | REASONING tier — `qwen/qwen3.7-max` via OpenRouter |
| Temperature | 0.3 (surfaces non-obvious cross-signal patterns) |
| `max_tokens` | 1500 (structured `RevisedContext` requires extra space) |
| `response_format` | `{"type": "json_object"}` (guarantees parseable JSON) |
| System prompt | `build_system_prompt(sector, agent_names)` — dynamically built, no hardcoded agent names |

**`FeedbackAgentInput` fields (key):**

```python
class FeedbackAgentInput(BaseModel):
    ticker: str
    sector: str                          # drives sector-aware system prompt
    predicted_close: float
    actual_close: float
    price_error_pct: float
    direction_correct: bool
    predicted_agent_scores: dict[str, float]
    todays_agent_scores: dict[str, float]
    market_context_today: str
    key_assumptions_made: list[str]
    active_lessons_summary: str
    significant_subscore_drift: dict     # sub-dimension drift for large drifters
    weight_drift_summary: str            # "risk_macro +0.06 (base 0.13→0.19)"
    recent_accuracy_trend: str          # "risk_macro: 5/7 this week, 4/7 last week"
    previous_watch_signals: list[str]   # from yesterday's revised_context
    predicted_catalysts_by_agent: dict  # 🆕 bull/bear/confidence per agent
```

**`FeedbackAgentOutput` schema:**

```python
{
  "primary_miss_agent": "risk_macro",
  "miss_type": "model_bias",            # one of 7 types
  "missed_factors": ["RBI rate hold surprise", "FII outflow ₹2200Cr"],
  "over_weighted_factors": ["FADA dispatch optimism — market ignored it on policy day"],
  "agent_score_drift": {"risk_macro": -0.18, "sales_demand": 0.04},
  "new_lessons": [{
    "category": "macro",
    "scope": "sector_wide",
    "pattern": "RBI_policy_day",
    "observation": "When RBI makes surprise decision, market ignores fundamental signals",
    "rule": "On RBI event days, prioritise risk_macro over fundamentals",
    "confidence": 0.75
  }],
  "revised_context": {
    "headline": "RBI policy surprise suppressed demand signals",
    "risks_next_7_days": ["RBI follow-through commentary", "FII positioning"],
    "catalysts_next_7_days": ["FADA data release in 5 days"],
    "watch_signals": ["INR past 84"],
    "horizon_confidence_adjustment": -0.05
  }
}
```

**LLM rules (from system prompt):** Do NOT cite analyst ratings, broker targets, or EPS estimates as missed factors. Valid missed factors: price action, macro events, sector data, technical signals, fundamentals, policy, commodities, regulatory actions.

### 7.7 Miss Taxonomy — 7 Types

| Miss Type | When to Use | Penalty Multiplier | Agent Absolved? |
|---|---|---|---|
| `data_gap` | Data not yet published at forecast time (e.g. FADA releases on 10th, forecast made on 5th) | **0.0×** | ✅ Yes |
| `data_stale` | Hardcoded/outdated data used (e.g. RBI repo rate not updated after MPC) | **0.0×** | ✅ Yes |
| `external_shock` | Unpredictable black-swan event (circuit breaker, sudden tariff, geopolitical) | **0.0×** | ✅ Yes |
| `timing` | Direction correct but move happened earlier/later than predicted | See tier below | Partial |
| `magnitude` | Direction correct but size of move wrong | **0.25×** | Partial |
| `model_bias` | Agent consistently over/under-estimates a specific signal | **1.0×** | ❌ No |
| `direction_flip` | Completely wrong direction, no valid external cause | **1.0×** | ❌ No |

**Timing penalty tiers (Mechanism C):**

| `\|lag_days\|` | Multiplier | Meaning |
|---|---|---|
| ≤ 3 trading days | **0.00×** | Within-week noise; no penalty |
| ≤ 7 trading days | **0.20×** | Light signal — move was close |
| > 7 trading days | **0.50×** | Real timing failure |

**Source:** `MISS_TYPE_PENALTY_MULTIPLIER` dict in `src/backend/shared/schemas/feedback.py` — single source of truth imported by `WeightAdapter`.

### 7.8 WeightAdapter — 3-Stage Algorithm (STATIC)

**File:** `core/intelligence/rl/agents/weight_adapter.py`

All three stages are fully deterministic. No LLM.

**Stage 1 — Accuracy Computation (`_compute_accuracy`):**

- Rolling window: last `WEIGHT_ACCURACY_WINDOW = 7` **trading days** (calendar-aware; weekends excluded)
- Hit-credit rules:
  - `direction_correct = True` → **all agents** credited
  - `direction_correct = False` AND `miss_type ∈ NO_PENALTY_MISS_TYPES` → **all agents** credited (model not at fault)
  - `direction_correct = False` AND miss is penalisable → **non-primary agents** credited; **primary miss agent** not credited

**Stage 2 — Delta Computation (`_compute_deltas`):** Three independent mechanisms:

*Mechanism A — Hit-rate boost/penalty (every agent):*

```
effective_boost_threshold   = WEIGHT_BOOST_HIT_RATE   + seasonal_delta  (default 0.70)
effective_penalty_threshold = WEIGHT_PENALTY_HIT_RATE + seasonal_delta  (default 0.40)

if hit_rate ≥ effective_boost_threshold:    delta += RL_BOOST    (+0.02)
elif hit_rate ≤ effective_penalty_threshold: delta += RL_PENALTY  (−0.03)
else:                                        delta  = 0.0
```

`seasonal_delta` shifts thresholds during structurally easy/hard periods. Example: during Navratri/Diwali festive season, `sales_demand` threshold raised +0.08 (harder to earn boost when demand is structurally elevated).

*Mechanism B — Bias penalty (primary miss agent only, penalisable miss types):*

```
bias_score = Σ(window_weight × agent_miss_rate_in_window) / Σ(window_weight)

Windows: 5 td → weight 0.50  (recent dominates)
         10 td → weight 0.30
         21 td → weight 0.20

if bias_score < RL_BIAS_TRIGGER (0.55):     bias_penalty = 0.0
if RL_BIAS_TRIGGER ≤ bias_score < RL_BIAS_FULL (0.70):
    scale = (bias_score − 0.55) / (0.70 − 0.55)
    bias_penalty = RL_MISS_STREAK_PENALTY × scale × miss_type_multiplier
if bias_score ≥ RL_BIAS_FULL (0.70):
    bias_penalty = RL_MISS_STREAK_PENALTY × 1.0 × miss_type_multiplier  (full penalty)
```

| bias_score | scale | bias_penalty | Meaning |
|---|---|---|---|
| 0.40 | — | 0.000 | Occasional miss; ignore |
| 0.55 | 0.00 | 0.000 | Just at trigger; no penalty yet |
| 0.625 | 0.50 | −0.025 | Consistent underperformer |
| 0.70 | 1.00 | −0.050 | Full penalty — badly miscalibrated |

*Mechanism C — Timing penalty:* Described in Section 7.7.

**Stage 3 — Bound Application + Normalization (`_apply_deltas`):**

```
For each agent:
  1. Clamp delta to ±WEIGHT_MAX_STEP (0.05)        ← max one-day move
  2. proposed = current_weight + clamped_delta
  3. lo = max(0.0, base_weight − WEIGHT_MAX_DRIFT)  ← floor: base − 0.15
     hi = base_weight + WEIGHT_MAX_DRIFT             ← ceiling: base + 0.15
  4. proposed = clamp(proposed, lo, hi)
  5. Renormalize: weight /= Σ(all weights)          ← always sums to 1.0
```

### 7.9 Regime Multipliers (Step 5.5 — STATIC, EPHEMERAL)

**Key invariant:** Regime multipliers are computed daily, applied to `effective_weights`, and **never written to `weight_memory.json`**. Learned weights drift slowly; regime multipliers are daily overlays only. This prevents a single `MACRO_CRISIS` day from permanently depressing `fundamentals` agent weight.

```
effective_weight[agent] = learned_weight[agent] × regime_multiplier[agent]
                          ─────────────────────────────────────────────────
                            Σ(learned_weight[i] × regime_multiplier[i])
```

**Full Regime Multiplier Table (from `settings.REGIME_MULTIPLIERS` in `settings/base.py`):**

| Agent | MACRO_CRISIS | RISK_OFF | NORMAL | RISK_ON | MOMENTUM_EXT | OVERSOLD |
|---|---|---|---|---|---|---|
| `risk_macro` | **1.40** | 1.20 | 1.00 | 0.90 | 0.85 | 1.10 |
| `fundamentals` | 0.80 | 0.90 | 1.00 | **1.10** | 1.05 | 1.00 |
| `sales_demand` | 0.70 | 0.85 | 1.00 | **1.10** | 0.95 | 1.00 |
| `sentiment` | 0.80 | 0.90 | 1.00 | **1.15** | 0.80 | 0.90 |
| `pattern_analysis` | 0.90 | 0.95 | 1.00 | 0.95 | **1.20** | **1.30** |
| `competitive_intel` | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| `valuation_catalyst` | 0.90 | 0.95 | 1.00 | 1.10 | 1.10 | 1.05 |
| `raw_materials` | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| `policy_regulatory` | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

Values >1.0 = boost agent influence; <1.0 = discount. NORMAL = passthrough (all 1.00).

**Regime classification (RegimeDetector, STATIC — first match wins):**

| Priority | Regime | Condition |
|---|---|---|
| 1 | `MACRO_CRISIS` | VIX > 22 AND Nifty-5d < −1.0% |
| 2 | `RISK_OFF` | VIX > 22 OR (14≤VIX≤22 AND Nifty-5d < −1.0%) |
| 3 | `MOMENTUM_EXTENDED` | VIX < 14 AND Nifty-5d > +1.0% AND Sector RSI > 70 |
| 4 | `RISK_ON` | VIX < 22 AND Nifty-5d > +1.0% AND Sector RSI < 70 |
| 5 | `OVERSOLD` | Sector RSI < 30 (macro-independent) |
| 6 | `NORMAL` | Everything else — base learned weights, no adjustment |

### 7.10 ThesisReviewer

**File:** `core/intelligence/rl/agents/thesis_reviewer.py`

The ThesisReviewer fires after large prediction misses to validate whether the original 30-day thesis is still valid. It prevents re-weighted BUY forecasts from inheriting a structurally broken premise.

**Trigger conditions (`should_review()`):**

```
ThesisReviewer fires when:
  abs(price_error_pct) > max(1.5%, 1.5 × atr_pct)     ← size trigger
  OR
  direction_correct = False
  AND miss_type ∈ {direction_flip, model_bias}          ← structural trigger
```

**ATR-relative threshold examples:**

| Ticker | 14-day ATR % | Threshold Calculation | Effective Threshold |
|---|---|---|---|
| HDFCBANK | 0.8% | max(1.5%, 1.5 × 0.8%) = max(1.5%, 1.2%) | **1.5%** |
| MARUTI | 1.4% | max(1.5%, 1.5 × 1.4%) = max(1.5%, 2.1%) | **2.1%** |
| ADANIGREEN | 3.5% | max(1.5%, 1.5 × 3.5%) = max(1.5%, 5.25%) | **5.25%** |

This ensures the ThesisReviewer does not over-fire on high-volatility stocks (ADANIGREEN has natural ±5% swings) while remaining sensitive for low-volatility stocks (HDFCBANK ±0.8% swings).

**ThesisReview output schema:**

```json
{
  "assumptions_invalidated": ["crude stable ~$82"],
  "assumptions_still_valid": ["FADA dispatch +6% MoM"],
  "thesis_intact": false,
  "revised_narrative": "RBI surprise + crude spike invalidated the low-cost thesis.",
  "horizon_confidence_multiplier": 0.70
}
```

**`horizon_confidence_multiplier` interpretation:**

| Multiplier | Meaning |
|---|---|
| 1.00 | Thesis intact — minor re-weighting only |
| 0.85 | One assumption broken; recovery plausible |
| 0.70 | Core assumption invalidated; high uncertainty |
| 0.50 | Thesis fundamentally wrong |
| **0.30 (floor)** | Deep uncertainty — forecasts are unreliable |

**Safety contract:** `ThesisReviewer.review()` catches all exceptions and returns `ThesisReview(thesis_intact=True, multiplier=1.0)` on any failure. The daily review cycle is **never blocked** by a thesis review failure.

**Telemetry:** Appends to `data/predictions/{sector}/{ticker}/thesis_calls.jsonl` for calibration audit.

**Firing frequency:** ~1–3×/month per ticker (only on significant misses).

### 7.11 LearningLedger

**File:** `src/backend/shared/schemas/feedback.py` → `LearningLedger`

**Storage path:** `data/predictions/{sector}/{TICKER}/{TICKER}_learning_ledger.json`

**Lesson scope propagation (write path):**

```
FeedbackAgent outputs lesson → merge_lessons_into_ledger()
  lesson.scope == "stock_specific"
      └── write to TICKER_learning_ledger.json
  lesson.scope == "sector_wide"
      ├── write to TICKER_learning_ledger.json  (source record)
      └── propagate → data/predictions/{sector}/_shared_ledger.json
  lesson.scope == "market_wide"
      ├── write to TICKER_learning_ledger.json
      ├── propagate → data/predictions/{sector}/_shared_ledger.json
      └── propagate → data/predictions/_market_ledger.json
```

**Deduplication formula (STATIC):**

```
If same pattern (or ≥2 shared semantic_tags) already in shared_ledger:
  new_confidence = 0.70 × existing + 0.30 × incoming
  occurrences += 1
  last_seen = today
  contributing_tickers.append(source_ticker)
Else:
  add as new lesson
```

**Cross-ticker confidence boost:** Each new ticker independently confirming a `sector_wide` lesson: `confidence += 0.05`. After 3 independent tickers confirm: lesson marked `validated_by_rl = True`.

**Tiered read for FeedbackAgent context:**

| Tier | Source | Max Lessons in Prompt |
|---|---|---|
| T1 (most specific) | `ticker_learning_ledger.json` (stock_specific) | Top 6 by `eff_confidence` |
| T2 (sector) | `_shared_ledger.json` (sector_wide) | Top 3 by `eff_confidence` |
| T3 (market) | `_market_ledger.json` (market_wide) | Top 2 by `eff_confidence` |

**Confidence Decay (STATIC):** Category-specific rates with occurrence damping.

```
effective_rate = LESSON_DECAY_RATES[category] / sqrt(occurrences)
decayed_confidence = stored_confidence × (1 - effective_rate) ^ months_inactive
result = max(0.10, decayed_confidence)
```

| Category | Base Rate/Month | Rationale |
|---|---|---|
| `seasonal` | **0.000** | Decay-exempt — calendar patterns repeat annually |
| `data_availability` | 0.005 | Data release calendars rarely change |
| `fundamental` | 0.008 | Earnings/business cycle patterns — semi-structural |
| `technical` | 0.015 | Chart patterns shift with volatility regime |
| `sentiment` | 0.020 | Sentiment half-life ~50 days |
| `macro` | 0.030 | Domestic macro regimes are transitional |
| `global_macro` | 0.040 | Global macro moves fastest, least persistent |

**Floor = 0.10:** Lessons are never fully discarded automatically.

**Weekly stale lesson downgrade:** The `ledger_cleanup_weekly` APScheduler job (Mondays 3:30am IST) calls `downgrade_stale_lessons()` from `ledger_propagator.py` to reverse `market_wide` lessons that have been inactive for >30 days back to `sector_wide`. This prevents stale single-ticker findings from polluting the Tier 3 FeedbackAgent context.

---

## 8. Scheduler & Cron Architecture

### 8.1 Cron Jobs Master Table

**File:** `services/scheduler/python/scheduler.py` → `AutomobileScheduler`

All jobs run inside the FastAPI process as an APScheduler `BackgroundScheduler` with `timezone="Asia/Kolkata"`.

| Job ID | Trigger (IST) | Market Aware? | What It Does | Tickers | Serper Calls | LLM Calls |
|---|---|---|---|---|---|---|
| `rl_daily_review` | 4:30 PM Mon–Fri (`FEEDBACK_CRON`) | Post-close weekdays ✅ | 8-step RL feedback loop; FeedbackAgent + WeightAdapter | Active managed tickers | 0–16 (warm vs cold) | 0–1 (early-exit) |
| `rl_monthly_forecast` | 1st of month 9:00 AM | Any | Generate 30-day prediction envelopes; full agent pipeline | All managed tickers | ~16 per ticker | N agents per ticker (~9) |
| `rl_calendar_update` | Dec 31 11:00 PM | N/A | Fetch NSE holidays for next year; hot-reload calendar | N/A | 0 | 0 |
| `prompt_daily_deploy` | Midnight IST | N/A | Deploy pending prompt file changes to GitHub | N/A | 0 | 0 |
| `macro_market_news` | 9:00/12:00/15:00 IST Mon–Fri | During NSE session ✅ | Fetch real-time Nifty/market news; populate macro cache | Sector-wide | 2 per run | 1 ReviewAgent call |
| `macro_daily_news` | 7:30 AM Mon–Fri | Pre-market ✅ | Fetch overnight policy/RBI news; populate macro cache | Sector-wide | 2 per run | 1 ReviewAgent call |
| `ledger_cleanup_weekly` | 3:30 AM Mondays | N/A | Downgrade stale market_wide lessons in ledger | All managed tickers | 0 | 0 |

**Job configuration parameters (all jobs):**
- `coalesce=True` — if a run was missed (server restart), fire once, not catch-up
- `replace_existing=True` — safe to restart server without duplicate job registration
- `misfire_grace_time` — varies per job (30min for market-hours news; 2h for monthly forecast)

### 8.2 Multi-Sector Routing — Critical Fix (2026-05) ✅

**File:** `services/scheduler/python/scheduler.py` + `services/api/log_buffer.py`

> ⚠️ WARNING: Before the 2026-05 fix, all tickers defaulted to the `"automobile"` sector regardless of their `sector` field in `managed_tickers.json`. HDFCBANK was being analysed by `AutomobileAgentOrchestrator` using FADA dispatch data — producing meaningless results.

**The fix:** `get_active_tickers_with_sector()` returns `[{"sym": str, "sector": str}]` from `data/managed_tickers.json`. Both `_daily_review_job()` and `_monthly_forecast_job()` now pass `sector=` to `run_daily_review()` and `generate_forecast()`.

```python
# services/api/log_buffer.py
def get_active_tickers_with_sector() -> list[dict]:
    return [
        {"sym": t["sym"], "sector": t.get("sector", "automobile")}
        for t in load_managed_tickers()
        if t.get("enabled", True)
    ]

# services/scheduler/python/scheduler.py
ticker_entries = get_active_tickers_with_sector()
for entry in ticker_entries:
    ticker = entry["sym"]
    sector = entry.get("sector", "automobile")
    run_daily_review(ticker, review_date, sector=sector)  # correctly routes to BFSI orchestrator
```

**Before fix:** `HDFCBANK` → `AutomobileAgentOrchestrator` (9 auto agents, FADA data — meaningless)
**After fix:** `HDFCBANK` → `BankingAgentOrchestrator` (6 BFSI agents, NIM/CASA data — correct)

### 8.3 Per-Ticker Timeout

The daily review loop runs each ticker sequentially but wraps each run in a `ThreadPoolExecutor(max_workers=1)` with a 180-second timeout:

```python
with _cf.ThreadPoolExecutor(max_workers=1) as executor:
    future = executor.submit(run_daily_review, ticker, review_date, sector=sector)
    summary = future.result(timeout=180)  # 3-minute per-ticker timeout
```

**Why this matters:** The `ThesisReviewer` LLM call can occasionally hang (network timeout, rate limit). Without the 180s cap, a single stuck ticker would block the entire daily review loop, causing all remaining tickers' reviews to be skipped for the day.

### 8.4 Scheduler Self-Heal (Server Startup)

**File:** `services/api/server.py` lifespan handler

On every server start (including Railway deployments):

```
1. NSE Calendar first-run:
   if data/nse_holidays.json doesn't exist → calendar_updater.update_calendar()

2. RL self-heal (background daemon thread — server accepts requests immediately):
   For each managed ticker:
     a. If no envelope for current cycle → run generate_forecast() (background, ~2 min/ticker)
     b. Find missing trading-day reviews this month → run_daily_review() for each

3. BackgroundScheduler.start():
   All 7 jobs registered with their CronTriggers
```

The self-heal runs as a background thread so the server is immediately available to handle API requests while catch-up runs happen in the background.

<details><summary>📊 Typical Trading Day Timeline</summary>

<div style="font-family: monospace; font-size: 12px; background: #0d1117; color: #e6edf3; padding: 20px; border-radius: 8px;">

```
Time (IST)  Event
──────────────────────────────────────────────────────────
07:30 AM    macro_daily_news job fires
            → Serper: RBI/policy news (2 queries)
            → ReviewAgent (LLM): severity tag HIGH/MEDIUM/LOW
            → Write data/macro_news/YYYY-MM-DD_macro_feed.json

08:30 AM    [Pre-market window begins]
            APScheduler rl_daily_review will read yesterday's close
            (actual review fires at 4:30pm, but forecasts are pre-loaded)

09:00 AM    macro_market_news job fires (1st of 3 market-hours runs)
            → Serper: "India Nifty Sensex stock market news"
            → Update macro_news cache

09:15 AM    NSE OPENS
            → Stock prices start moving
            → Chat tools (get_live_price) now return live data

12:00 PM    macro_market_news job fires (2nd run)
            → Refresh market context mid-day

15:00 PM    macro_market_news job fires (3rd run)
            → Capture any late-session news

15:30 PM    NSE CLOSES
            → Final closing prices available

16:00 PM    [~30 minute pre-review window]
            Closing prices propagate to yfinance

16:30 PM    rl_daily_review job fires
            → Fetch actual close via yfinance
            → Run FeedbackAgent + WeightAdapter for all tickers
            → Update prediction envelopes with revised forecasts

Every 4h    micro_search_loop (daemon thread, if running)
            → 3 sectors × 2 Serper queries → populate macro cache
            → Cache TTL = 4h; consumed by ContextBuilder._build_risk_macro()
```

</div>
</details>

---

## 9. Dynamic Stock Management

### 9.1 Runtime Ticker Management (No Redeploy)

**File:** `services/api/log_buffer.py`

`data/managed_tickers.json` is the single source of truth for which tickers the system analyses. The APScheduler reads this file on every job firing — changes take effect immediately without a server restart.

If `data/managed_tickers.json` does not exist, `load_managed_tickers()` seeds it from `settings.SCHEDULER_TICKERS` (default: 5 automobile tickers) and writes the file.

### 9.2 API Endpoint Reference

| Endpoint | Method | Auth | Behaviour | Side Effects |
|---|---|---|---|---|
| `/ui/tickers/managed` | GET | None | List all managed tickers | None |
| `/ui/tickers/managed` | PUT | None | Replace entire managed ticker list | Validates sectors |
| `/ui/tickers/managed/{sym}` | POST | None | Add ticker | Auto-detect sector; NSE validate; envelope async |
| `/ui/tickers/managed/{sym}` | DELETE | None | Remove ticker | `shutil.rmtree(data/predictions/{sector}/{sym}/)` — **permanent** |
| `/ui/tickers/managed/{sym}/toggle` | PATCH | None | Enable/disable | Preserves all RL data |
| `/ui/tickers/managed/{sym}/generate-envelope` | POST | None | Force envelope generation | Background async task |

### 9.3 Sector Auto-Detection

`SectorRegistry.resolve(ticker)` is the authoritative source of truth:

```
POST /ui/tickers/managed/HDFCBANK  Body: {"sector": "automobile"}
  → SectorRegistry.resolve("HDFCBANK") = "banking_bfsi"
  → Registry wins → Response: {"sector": "banking_bfsi", "sector_auto_detected": true}
```

### 9.4 RL Data Lifecycle

| Action | Scheduling Effect | RL Data Effect |
|---|---|---|
| **Add** | Starts in next scheduler cycle | Envelope generated async; RL learning starts that night |
| **Disable** | Stops scheduling | All data **preserved** |
| **Delete** | Removed immediately | `shutil.rmtree` — **permanent, unrecoverable** |

> ⚠️ WARNING: Deleting a ticker permanently removes all accumulated RL learning. Use `toggle` to pause instead.

### 9.5 Valid Sectors

```python
def _get_valid_sectors() -> list[str]:
    return SectorRegistry.enabled_sectors()
    # → ["automobile", "banking_bfsi", "it_sector", "renewable_energy"]
```

Never hardcoded. Updated automatically when `sector_toggles.json` enables a new sector.

---

## 10. Settings Reference

### 10.1 Settings Architecture

```
API keys / URLs / secrets           → .env (os.getenv)
Algorithm thresholds / constants    → settings/base.py (plain Python values)
Never: os.getenv() for algorithm constants
```

### 10.2 Master Settings Table — RL & Algorithm Constants

| Setting | Value | Purpose |
|---|---|---|
| `FORECAST_HORIZON_DAYS` | 30 | Trading days to forecast on month-start |
| `WEIGHT_MAX_STEP` | 0.05 | Max weight change per daily step |
| `WEIGHT_MAX_DRIFT` | 0.15 | Max total drift from base weight |
| `WEIGHT_MIN_OBSERVATIONS` | 3 | Days before weight adaptation activates |
| `WEIGHT_ACCURACY_WINDOW` | 7 | Rolling window (trading days) for hit-rate |
| `WEIGHT_BOOST_HIT_RATE` | 0.70 | Hit rate ≥ this → weight boost |
| `WEIGHT_PENALTY_HIT_RATE` | 0.40 | Hit rate ≤ this → weight penalty |
| `RL_BOOST` | +0.02 | Delta for hit-rate boost |
| `RL_PENALTY` | −0.03 | Delta for hit-rate penalty |
| `RL_MISS_STREAK_PENALTY` | −0.05 | Full bias penalty magnitude |
| `RL_BIAS_TRIGGER` | 0.55 | Bias score at which penalty starts |
| `RL_BIAS_FULL` | 0.70 | Bias score at which full penalty applies |
| `RL_TIMING_FREE_WINDOW` | 3 | Lag ≤ N trading days → 0× timing penalty |
| `RL_TIMING_PARTIAL_WINDOW` | 7 | Lag ≤ N → 0.20×; > N → 0.50× |
| `RL_FLAT_THRESHOLD_PCT` | 0.3 | ±% within which direction = FLAT |
| `RL_AGENT_RERUN_THRESHOLD_PCT` | 0.5 | Skip orchestrator if direction correct + error < 0.5% |
| `RL_STREAK_WARNING_THRESHOLD` | 8 | Streak ≥ this → FeedbackAgent gets streak warning |
| `RL_RSI_AMPLIFIER` | 1.50 | RSI divergence multiplier on reversion_prior |
| `RL_MAX_REVERSION_PRIOR` | 0.30 | Cap on reversion_prior |
| `RL_ATR_THRESHOLD_FLOOR` | 1.5 | Minimum ThesisReviewer trigger % |
| `RL_ATR_THRESHOLD_MULTIPLIER` | 1.5 | Multiplier × ATR% for ThesisReviewer |
| `RL_LESSON_BLEND_EXISTING` | 0.70 | Weight for existing lesson on merge |
| `RL_LESSON_BLEND_INCOMING` | 0.30 | Weight for new confirmation on merge |
| `RL_CROSS_TICKER_BOOST` | 0.05 | Confidence boost per confirming ticker |
| `VIX_VOLATILE_THRESHOLD` | 22.0 | India VIX → volatile macro regime |
| `VIX_LOW_VOL_THRESHOLD` | 14.0 | India VIX → calm/trending regime |
| `FII_PROXY_THRESHOLD_PCT` | 1.0 | Nifty 5-day % threshold for FII proxy |
| `RSI_OVERBOUGHT` | 70.0 | Sector RSI → overbought |
| `RSI_OVERSOLD` | 30.0 | Sector RSI → oversold |
| `RBI_REPO_RATE_PCT` | `"5.25"` | Fallback repo rate (live Serper fetch preferred) |
| `RBI_REPO_RATE_DATE` | `"2026-02-07"` | Date of last known rate change |
| `SERPER_MAX_QUERIES` | 3 | Max Serper queries per agent run |
| `SERPER_TIMEOUT_SECONDS` | 10 | Serper HTTP timeout |
| `TAVILY_MAX_CONTENT_CHARS` | 600 | Tavily content truncation |
| `MACRO_CACHE_TTL_HOURS` | 4 | Derived: `int(24 // MICRO_CYCLES_PER_DAY)` |
| `MICRO_CYCLES_PER_DAY` | 6 | Micro search loop runs per day |
| `MICRO_QUERIES_PER_RUN` | 2 | Serper queries per sector per cycle |
| `MACRO_NEWS_RETAIN_DAYS` | 90 | Days before macro news JSON files deleted |
| `RSI_PERIOD` | 14 | RSI calculation period |
| `MACD_FAST` / `SLOW` / `SIGNAL` | 12 / 26 / 9 | MACD parameters |
| `BB_PERIOD` / `BB_STD` | 20 / 2.0 | Bollinger Band parameters |

**Automobile base weights (sector settings file):** fundamentals 0.18, sales_demand 0.16, risk_macro 0.13, pattern_analysis 0.12, valuation_catalyst 0.10, policy_regulatory 0.09, raw_materials 0.09, competitive_intel 0.09, sentiment 0.04 (sum = 1.00).

### 10.3 Environment Variables (.env)

| Variable | Purpose | Sector Routing |
|---|---|---|
| `SERPER_API_KEY` | Automobile + renewable_energy Serper calls | `get_serper_key("automobile")` |
| `SERPER_API_KEY_2` | Banking_bfsi + it_sector Serper calls | `get_serper_key("bfsi")` |
| `TAVILY_API_KEY` | Full-page extraction (all sectors) | All sectors |
| `OPENROUTER_API_KEY` | All LLM calls | All agents |
| `LLM_MODEL_FAST` / `LLM_MODEL_REASONING` / `LLM_MODEL_BULK` | Hybrid model tiers — REASONING also powers the automobile Unified Sector Analyst; BULK runs the per-dimension agents for sectors not yet on the unified path | `qwen3.6-flash` / `qwen3.7-max` / `qwen-2.5-72b` (235b retired) |
| `SCHEDULER_ENABLED` | Activate APScheduler | `true` in production |
| `FEEDBACK_CRON` | Daily review trigger | `0 11 * * 1-5` (4:30pm IST) |
| `MACRO_NEWS_ENABLED` | Toggle macro news feed | `true` / `false` |

---

## 11. Logging & Observability

### 11.1 LLM Cost Telemetry

**Path:** `outputs/llm_log/{YYYY-MM-DD}.jsonl`

```json
{"ts": "2026-05-17T09:45:12Z", "caller": "FeedbackAgent", "model": "qwen/qwen3.7-max",
 "input_tokens": 1240, "output_tokens": 480, "latency_ms": 2340, "success": true}
```

One JSON line per LLM call. Daily file roll-up gives monthly spend per caller.

### 11.2 Thesis Calibration Log

**Path:** `data/predictions/{sector}/{ticker}/thesis_calls.jsonl`

```json
{"date": "2026-05-12", "ticker": "MARUTI", "price_error_pct": -2.34,
 "atr_pct": 1.4, "threshold_used": 2.1, "multiplier": 0.70, "thesis_intact": false}
```

Use to calibrate `RL_ATR_THRESHOLD_MULTIPLIER` per ticker over time.

### 11.3 Live Log Ring Buffer

**File:** `services/api/log_buffer.py` → `RingBufferHandler`

- Holds last 1,000 log records in `deque(maxlen=1000)`
- Thread-safe: `threading.Lock` on the buffer; `threading.Queue` per SSE subscriber
- API: `GET /ui/logs` (snapshot) and `GET /ui/logs/stream` (SSE live tail)

### 11.4 RL Logs Hierarchy

```
data/predictions/
  _market_ledger.json
  {sector}/_shared_ledger.json
  {sector}/{TICKER}/
    {TICKER}_{YYYY-MM}_prediction_envelope.json   ← monthly, archived
    {TICKER}_{YYYY-MM}_daily_feedback_log.json    ← monthly, archived
    {TICKER}_{YYYY-MM}_prompt_enhancements.json   ← monthly, per-cycle
    {TICKER}_agent_weight_memory.json             ← PERMANENT
    {TICKER}_learning_ledger.json                 ← PERMANENT
    {TICKER}_dossier.json                         ← PERMANENT (5th memory file, RL_DESIGN.md §23)
    thesis_calls.jsonl                            ← append-only audit
```

All JSON files use atomic writes (`.tmp` → `os.replace()`).

### 11.5 OEM Profile Cache

**Path:** `data/oem_profiles/{TICKER}.json` — 30-day TTL, fetched from Serper for unknown tickers.

---

## 12. Known Gaps & Open Items

### 12.1 Automobile

| Gap | Agent | Status | Workaround |
|---|---|---|---|
| RBI repo rate | `risk_macro` | ✅ FIXED 2026-05-10 | Live Serper fetch |
| `^TOCOM_RUBBER` delisted | `raw_materials` | ✅ FIXED 2026-05-10 | Serper MCX news proxy |
| `_build_valuation_catalyst` | `valuation_catalyst` | ✅ FIXED | — |
| FADA/SIAM/Vahan structured API | `sales_demand` | ❌ OPEN (P7) | Serper proxy |
| Nifty Auto peer correlation | `pattern_analysis` | ❌ OPEN (P6) | ~10 lines of yfinance |

### 12.2 Banking/BFSI

| Gap | Agent | Status |
|---|---|---|
| `rbi_data.py` stub | `fundamentals`, `macro_policy` | ❌ OPEN (P7) |
| `npa_metrics.py` stub | `fundamentals` | ❌ OPEN (P7) |
| ContextBuilder methods | All 6 | ✅ FIXED |

### 12.3 IT Sector

| Gap | Agent | Status |
|---|---|---|
| `deal_wins.py` stub | `fundamentals`, `transcript_nlp` | ❌ OPEN (P7) |
| `transcript.py` stub | `transcript_nlp` | ❌ OPEN (P7) |
| ContextBuilder methods | All 8 | ✅ FIXED |

### 12.4 Renewable Energy

| Gap | Agent | Status |
|---|---|---|
| `mnre_data.py` stub | `business`, `sentiment_policy` | ❌ OPEN (P7) |
| DISCOM PRAAPTI data | `risk` | ❌ OPEN (P7) |
| ContextBuilder methods | All 6 | ✅ FIXED |

### 12.5 LangGraph Design Weaknesses (Backlog)

| Issue | Severity | Status |
|---|---|---|
| `run_agent` calls sync `agent.run()` — threading not asyncio | Medium | ❌ OPEN |
| `input_rail` makes blocking yfinance call before fan-out | Medium | ❌ OPEN |
| No CLI / FastAPI entry point for non-automobile sectors | Medium | ❌ OPEN |
| `BaseAgent._rag_retrieve` defaults to "automobile India" for unknown agents | High | ❌ OPEN |

### 12.6 RL Open Items

| Gap | Status |
|---|---|
| Forecast path is linear interpolation (no Monte Carlo bands) | ❌ Phase 8 |
| `WEIGHT_MAX_DRIFT = 0.15` too tight after 6+ months | ❌ Revisit Month 6 |
| Score verdict thresholds identical across all sectors | ❌ Add per-sector thresholds |
| NSE holiday calendar hardcoded fallback ends 2026; `calendar_updater.py` auto-fetches next year on Dec 31 via NSE API → yfinance → fixed-holidays chain | ⚠️ Monitor Dec 31 job; if job fails, 2027 moveable feasts will be missing from `_HARDCODED_HOLIDAYS` |

### 12.7 Serper Budget Warning

> ⚠️ WARNING: At 5 tickers: ~2,976 Serper calls/month (119% of 2,500 free tier). Safe operating point: **3 tickers ≈ 1,848/month (74%)**. Options: upgrade Serper plan, add SERPER_API_KEY_3, or reduce MICRO_CYCLES_PER_DAY from 6 to 4.

---

## 13. Quick Reference Cards

### 13.1 Chat Pipeline

| Step | What Fires | SSE Event |
|---|---|---|
| User sends message | `dispatch` node (LLM) | `{"event":"dispatch","tier":"active"}` |
| Per tool (parallel) | `executor` (STATIC) | `{"event":"tool_start","tool":"..."}` |
| Per result | `executor` (STATIC) | `{"event":"tool_result","summary":"..."}` |
| Reasoning | `synthesize` (LLM) | `{"event":"thinking"}` |
| Streaming text | `synthesize` (LLM) | `{"event":"token","text":"..."}` |
| Done | `synthesize` (LLM) | `{"event":"done"}` |

**Tier response formats:** `casual` → 3–4 plain sentences (~80 words) · `active` → price + direction + headlines (~150 words) · `expert` → regime + RL + metrics (no cap)

---

### 13.2 RL Pipeline

| Trigger | Function | Output |
|---|---|---|
| 1st of month 9am IST | `generate_forecast(ticker, sector)` | `PredictionEnvelope` JSON |
| Daily 4:30pm IST | `run_daily_review(ticker, date, sector)` | `FeedbackEntry` appended |
| Large miss (auto) | `ThesisReviewer.review()` | `horizon_confidence_multiplier` |
| Month-end | `SeasonalValidator.validate_pattern()` | Seed: SEEDED → VALIDATED |
| Monday 3:30am IST | `downgrade_stale_lessons()` | market_wide → sector_wide |
| Dec 31 11pm IST | `run_dec31_update()` | NSE holidays refreshed |

---

### 13.3 AgentOutput → Used By

| Field | Populated By | Consumed By |
|---|---|---|
| `overall_score` | LLM | `SignalAggregator` weighted sum |
| `sub_scores` | LLM | RL `predicted_agent_subscores` drill-down |
| `ticker_vs_peers` 🆕 | LLM | `_build_narrative_block()` → aggregation prompt |
| `bull_case_if` 🆕 | LLM | `PredictionEnvelope.agent_predictions`; `FeedbackAgentInput` |
| `bear_case_if` 🆕 | LLM | Same as `bull_case_if` |
| `what_changed` 🆕 | LLM | `_build_narrative_block()` → aggregation prompt |
| `data_confidence` 🆕 | LLM | FeedbackAgent penalty modulation |
| `error` | STATIC failure | `output_rail` clamps; excluded from aggregation |

---

### 13.4 Scheduler Job Quick Reference

| Job | IST Time | Serper | LLM |
|---|---|---|---|
| `rl_daily_review` | 4:30pm Mon–Fri | 0–16/ticker | 0–1 FeedbackAgent |
| `rl_monthly_forecast` | 1st of month 9am | ~16/ticker | N agents |
| `macro_market_news` | 9/12/15am Mon–Fri | 2/run | 1 ReviewAgent |
| `macro_daily_news` | 7:30am Mon–Fri | 2/run | 1 ReviewAgent |
| `ledger_cleanup_weekly` | 3:30am Mondays | 0 | 0 |
| `rl_calendar_update` | Dec 31 11pm | 0 | 0 |
| `prompt_daily_deploy` | Midnight IST | 0 | 0 |

---

## Appendix A: File Structure Tree

```
StockAgent-main/
├── main.py                         ← CLI + micro search loop daemon
├── config/sector_toggles.json      ← 27-sector enable/disable flags
├── src/backend/
│   ├── sectors/
│   │   ├── registry.py             ← SectorRegistry, TICKER_SECTOR
│   │   ├── automobile/             ← 9 agents, sector settings
│   │   ├── banking_bfsi/           ← 6 agents
│   │   ├── it_sector/              ← 8 agents
│   │   └── renewable_energy/       ← 6 agents
│   └── shared/
│       ├── agents/prompts/
│       │   ├── technical.py        ← shared technical prompt (4 → 1)
│       │   └── institutional_flow.py
│       ├── config/settings/base.py ← ALL algorithm constants
│       ├── pipeline/
│       │   ├── base_agent.py       ← BaseAgent (3 abstract methods)
│       │   └── signal_aggregator.py
│       └── schemas/
│           ├── pipeline.py         ← AgentOutput, FinalReport
│           └── feedback.py         ← PredictionEnvelope, LearningLedger
├── core/intelligence/
│   ├── regime/detector.py          ← RegimeDetector (STATIC)
│   └── rl/
│       ├── agents/
│       │   ├── feedback_agent.py   ← FeedbackAgent (LLM)
│       │   ├── weight_adapter.py   ← WeightAdapter (STATIC)
│       │   └── thesis_reviewer.py  ← ThesisReviewer (conditional LLM)
│       ├── stores/
│       │   ├── prediction_store.py ← JSON R/W
│       │   └── ledger_propagator.py
│       └── workflows/
│           ├── daily_review.py     ← 9-step daily loop
│           └── generate_forecast.py
├── services/
│   ├── api/
│   │   ├── log_buffer.py           ← ring buffer + managed_tickers
│   │   └── routes/ui_data.py       ← all API endpoints + agentic chat loop + 11 tools
│   ├── background/
│   │   └── macro_news_fetcher.py   ← FetchAgent + ReviewAgent
│   ├── data/
│   │   ├── context/builder.py      ← ContextBuilder (29 methods)
│   │   ├── fetchers/
│   │   │   ├── macro.py            ← yfinance + RBI + rubber
│   │   │   ├── news.py             ← Serper
│   │   │   └── tavily_fetcher.py   ← Tavily + disk cache
│   │   └── stores/score_store.py   ← SQLite ScoreDB
│   └── scheduler/python/scheduler.py ← 7 APScheduler jobs
├── data/
│   ├── managed_tickers.json        ← runtime ticker list
│   ├── scores.db                   ← SQLite historical verdicts
│   ├── macro_news/                 ← daily JSON feed (90-day retention)
│   ├── oem_profiles/               ← 30-day Serper cache
│   ├── tavily_cache/               ← monthly Tavily cache
│   ├── user_profiles/              ← session tier profiles
│   └── predictions/
│       ├── _market_ledger.json
│       ├── {sector}/_shared_ledger.json
│       └── {sector}/{TICKER}/
│           ├── {TICKER}_{YYYY-MM}_prediction_envelope.json
│           ├── {TICKER}_{YYYY-MM}_daily_feedback_log.json
│           ├── {TICKER}_agent_weight_memory.json  ← PERMANENT
│           ├── {TICKER}_learning_ledger.json       ← PERMANENT
│           ├── {TICKER}_dossier.json               ← PERMANENT (5th memory file, RL_DESIGN.md §23)
│           └── thesis_calls.jsonl
├── outputs/llm_log/{YYYY-MM-DD}.jsonl  ← LLM cost telemetry
└── docs/
    ├── AGENTIC_DESIGN.md
    ├── RL_DESIGN.md
    ├── CHAT_ARCHITECTURE.md
    ├── MACRO_NEWS.md
    ├── SECTOR_DESIGN.md
    ├── STATIC_AUDIT.md
    └── TECHNICAL_DESIGN.md         ← This document
```

---

## Appendix B: Sector-to-Orchestrator Mapping

| Sector Key | Tier | Enabled | Orchestrator |
|---|---|---|---|
| `automobile` | backend | ✅ | `AutomobileAgentOrchestrator` |
| `banking_bfsi` | backend | ✅ | `BankingAgentOrchestrator` |
| `it_sector` | backend | ✅ | `ITAgentOrchestrator` |
| `renewable_energy` | backend | ✅ | `RenewableAgentOrchestrator` |
| All others (21 sectors) | core | ❌ | `AutomobileAgentOrchestrator` (degraded + WARNING) |

**To enable a disabled sector:** Set `"enabled": true` in `config/sector_toggles.json` and restart server.

**Promotion path:** disabled → `tier=core` (CoreSectorAdapter, 8-pillar generic) → `tier=backend` (custom orchestrator + domain agents).

---

## Appendix C: managed_tickers.json Schema

**Path:** `data/managed_tickers.json`

```python
list[{
    "sym":     str,   # NSE ticker, UPPERCASE (e.g. "MARUTI")
    "name":    str,   # Display name
    "sector":  str,   # Must be in SectorRegistry.enabled_sectors()
    "enabled": bool   # false = pause (data preserved); delete = permanent
}]
```

**Example:**

```json
[
  {"sym": "MARUTI",    "name": "Maruti Suzuki India Ltd",       "sector": "automobile",      "enabled": true},
  {"sym": "HDFCBANK",  "name": "HDFC Bank Ltd",                 "sector": "banking_bfsi",    "enabled": true},
  {"sym": "TCS",       "name": "Tata Consultancy Services Ltd", "sector": "it_sector",       "enabled": true},
  {"sym": "ADANIGREEN","name": "Adani Green Energy Ltd",        "sector": "renewable_energy","enabled": true},
  {"sym": "TATAMOTORS","name": "Tata Motors Ltd",               "sector": "automobile",      "enabled": false}
]
```

**Validation rules on POST `/ui/tickers/managed/{sym}`:**
- `sym` must exist on NSE (checked via `yfinance.Ticker("{sym}.NS").fast_info`)
- `sector` must be in `SectorRegistry.enabled_sectors()` — never hardcoded
- Sector conflict (user vs registry): registry always wins; response includes `sector_auto_detected: true`
- Duplicate `sym`: returns 409 Conflict

**Bootstrap:** If file absent, seeds from `settings.SCHEDULER_TICKERS` (5 automobile tickers) and writes file. The file persists across restarts; `settings.SCHEDULER_TICKERS` is only the fallback seed, not the runtime source of truth.

---

*End of StockAgent Technical Design Document — Version 2026-05-19*
