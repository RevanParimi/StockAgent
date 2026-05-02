# StockAgent

> AI-powered Indian stock analyser with a **self-learning RL feedback loop**.
> Multi-sector · Multi-agent · Multi-language · Compounds knowledge with every trading day it runs.

---

## What This System Does

**StockAgent** analyses NSE/BSE-listed Indian stocks across four sectors, runs up to **9 specialist AI sub-agents in parallel**, fuses their outputs through a weighted Signal Aggregator, and — crucially — **reviews its own predictions every trading day** to get smarter over time.

Unlike tools that browse and output a one-shot answer, StockAgent maintains **per-ticker persistent memory** across months: earned agent credibility weights, accumulated pattern lessons, and a 30-day prediction envelope that self-revises as reality unfolds.

```
Browser :5173 (Vite)
    │  /api/* + /ws/*
    ▼
TypeScript Gateway  :3000  (Bun + Hono)
    │  REST proxy + WebSocket proxy + 8:30am IST analysis cron
    ▼
Python FastAPI  :8001  (internal)
    │  POST /analyse  →  AutomobileAgentOrchestrator
    │  WS   /ws/stream (live agent progress)
    │  GET  /history/* (SQLite score store)
    ▼
9 Specialist Agents  (parallel via LangGraph worker pool)
    │
    ▼
Signal Aggregator  (weighted fusion + LLM conflict resolution)
    │
    ▼
FinalReport  (score 0–1 · verdict · thesis · conviction drivers)
    │
    ▼
RL Feedback Loop  (daily, post-market close, 4:30pm IST)
    predict → compare → diagnose → adapt weights → accumulate lessons
```

---

## Sectors

| Sector | Agent Count | Status |
|---|---|---|
| **Automobile** | 9 agents | Full — all agents + RL loop live |
| **Banking / BFSI** | 6 agents | Stub — graph wired, agents pending |
| **IT** | 8 agents | Stub — graph wired, agents pending |
| **Renewable Energy** | 6 agents | Stub — graph wired, agents pending |

Each sector maintains **completely independent** per-ticker memory. Weights learned for HDFCBANK never affect TCS.

---

## Automobile Agents

| Agent | Weight | What It Analyses |
|---|---|---|
| Sales & Demand | 16% | FADA/SIAM dispatch, EV Vahan registrations, dealer inventory, DGFT exports, used car price index |
| Fundamentals | 18% | Revenue/EBITDA delta, margin vs peers, order book, FII/DII flow, balance sheet |
| Risk & Macro | 13% | INR/crude/commodity exposure, RBI repo rate, FII flows, India VIX, China supply risk |
| Pattern Analysis | 12% | 10-yr price cycle, RSI/MACD/Bollinger, support/resistance, Nifty Auto correlation |
| Valuation & Catalyst | 10% | P/E vs peers, upcoming catalysts, re-rating triggers |
| Policy & Regulatory | 9% | FAME EV subsidy, emission norms, Budget duties, PLI scheme, state EV incentives |
| Raw Materials | 9% | Steel/aluminium/platinum/palladium/crude/polymer/rubber trends |
| Competitive Intel | 9% | EV market share, new model pipeline, JV/acquisitions, ADAS safety ratings |
| Sentiment | 4% | News NLP, earnings call tone, social media signals, dealer feedback |

**Signal Aggregator** detects conflicts (score delta ≥ 0.30 between any two agents), sends them to the LLM for resolution, then emits: `STRONG BUY / BUY / NEUTRAL / SELL / STRONG SELL`.

---

## Architecture

### Multi-Language Stack

| Language | Module | Port | Role |
|---|---|---|---|
| **Python** | 9 LLM agents, orchestrator, RAG, FastAPI | 8001 (internal) | Core intelligence |
| **TypeScript** | Bun + Hono gateway, WS proxy, analysis cron | 3000 (public) | API gateway |
| **C++** | RSI / MACD / Bollinger Bands via pybind11 | in-process .pyd | Fast indicators |
| **React + Vite** | Frontend dashboard | 5173 (dev) | UI |
| **C#** | Quartz.NET scheduler + EF Core | 5000 (optional) | Alt persistence |

All language boundaries use **JSON over HTTP**. The C++ extension is the only in-process FFI (pybind11 — falls back to pure Python silently if `.pyd` is absent).

### Request Flow

```
Browser → GET /api/analyse?ticker=MARUTI
    │
    ▼  :3000 TypeScript Gateway (Bun + Hono)
    │   validates request, proxies to Python
    │
    ▼  :8001 Python FastAPI  POST /analyse
    │
    ▼  AutomobileAgentOrchestrator
    │   resolves ticker via LLM → dispatches LangGraph worker pool
    │
    ├──► SalesDemand     ──┐
    ├──► RawMaterials    ──┤
    ├──► Fundamentals    ──┤
    ├──► PatternAnalysis ──┤  (parallel, LangGraph Send fan-out)
    ├──► Sentiment       ──┤
    ├──► PolicyRegulatory──┤
    ├──► CompetitiveIntel──┤
    ├──► RiskMacro       ──┤
    └──► ValuationCatalyst┘
              │
              ▼
        SignalAggregator
        (applies learned weights from agent_weight_memory.json
         if available; defaults to base weights on first run)
              │
              ▼
        FinalReport  →  saved to SQLite  →  returned to browser
```

### RL Daily Feedback Loop (4:30pm IST, weekdays)

```
daily_review.py  (per tracked ticker, per sector)
    │
    ├─ Step 1  load prediction_envelope.json → today's forecast
    ├─ Step 2  fetch actual closing price (yfinance)
    ├─ Step 3  compute price_error_pct + direction_correct
    ├─ Step 4  FeedbackAgent (LLM) → miss_type + root cause + new lessons
    ├─ Step 5  WeightAdapter (deterministic) → adjust agent weights
    ├─ Step 6  LearningLedger → deduplicate + store lessons
    ├─ Step 7  revise remaining 30-day forecasts with updated weights
    └─ Step 8  append to daily_feedback_log.json
```

**4 persistent JSON files per ticker (never deleted — survive month rollovers):**

| File | Purpose |
|---|---|
| `{TICKER}_{CYCLE}_prediction_envelope.json` | 30-day living forecast, revised daily |
| `{TICKER}_{CYCLE}_daily_feedback_log.json` | Miss history with root cause per day |
| `{TICKER}_agent_weight_memory.json` | Earned credibility per agent — persists across all cycles |
| `{TICKER}_learning_ledger.json` | Accumulated stock-specific pattern rules |

---

## Project Structure

```
StockAgent-main/
│
├── core/                              ← All Python intelligence
│   ├── config/
│   │   ├── settings/base.py          ← All constants: LLM, weights, ports, RL settings
│   │   ├── prompts/automobile/       ← 9 prompt files (one per agent)
│   │   └── prompts/shared/           ← orchestrator, signal_aggregator, feedback_agent
│   ├── graphs/                       ← LangGraph: nodes, rails, state
│   ├── pipeline/
│   │   ├── base_agent.py             ← Abstract base: LLM caller, retry, context routing
│   │   ├── orchestrator.py           ← Dispatch 9 agents in parallel
│   │   └── signal_aggregator.py      ← Weighted fusion + conflict resolution → FinalReport
│   ├── schemas/
│   │   ├── pipeline.py               ← StockQuery, AgentOutput subtypes, FinalReport
│   │   └── feedback.py               ← RL schemas: MissType, LessonScope, TimingAccuracy, etc.
│   ├── sectors/
│   │   ├── automobile/               ← 9 agent classes + LangGraph graph
│   │   ├── banking/                  ← graph + agent stubs
│   │   ├── it/                       ← graph + agent stubs
│   │   └── renewable/                ← graph + agent stubs
│   ├── intelligence/
│   │   ├── algorithms/indicators/fetcher.py   ← RSI/MACD/BB (C++ or pure-Python)
│   │   ├── rag/                               ← ChromaDB + sentence-transformers
│   │   └── rl/
│   │       ├── agents/feedback_agent.py       ← 6th agent: daily LLM root-cause analysis
│   │       ├── agents/weight_adapter.py       ← Deterministic miss-type-aware weight update
│   │       ├── stores/prediction_store.py     ← Reads/writes all 4 JSON memory files
│   │       └── workflows/
│   │           ├── daily_review.py            ← Cron entry point (8-step feedback loop)
│   │           └── generate_forecast.py       ← Month-start: 30-day prediction envelope
│   └── scripts/
│       ├── make_ppt.py                        ← PowerPoint from final report
│       └── sanity_rl.py                       ← RL smoke tests
│
├── services/
│   ├── api/server.py                 ← FastAPI :8001 (internal, CORS → :3000 only)
│   ├── gateway/src/index.ts          ← Bun + Hono :3000 (public REST + WS proxy + cron)
│   ├── clients/
│   │   ├── llm_client.py             ← OpenRouter/Qwen client (sync + async)
│   │   └── tavily_fetcher.py         ← Full-page extraction (Policy agent only)
│   ├── data/
│   │   ├── cache/macro_cache.py      ← In-memory macro cache (TTL-based)
│   │   ├── context/builder.py        ← Routes each agent to the right fetchers
│   │   ├── fetchers/                 ← fundamentals.py, macro.py, news.py (Serper + yfinance)
│   │   └── stores/
│   │       ├── analysis_logger.py    ← Append to logs/analysis_history.jsonl
│   │       ├── score_store.py        ← SQLite score persistence
│   │       └── run_logger.py         ← LLM call + run summary logging
│   └── scheduler/
│       ├── python/scheduler.py       ← APScheduler: RL daily review at 4:30pm IST
│       └── run_schedule.py           ← CLI: forecast / daily-review / feedback-status / start
│
├── frontend/                         ← React 19 + Vite :5173
│   └── src/
│       ├── panda/                    ← Panda character / loading animation components
│       └── sphere/                   ← Oracle Orb 3D effect components
│
├── tests/
│   ├── unit/                         ← Pure logic (no network, no LLM)
│   ├── integration/                  ← RAG, data fetchers, local services
│   └── contract/                     ← Cross-layer wiring (import paths, schema compat)
│       ├── test_phase0_llm_migration.py   ← Zero Groq references; OpenRouter wiring
│       ├── test_phase1_indicators.py      ← C++ parity + fallback (25 tests)
│       ├── test_phase3_typescript.py      ← Python-side JSON shape contracts
│       ├── test_phase4_csharp.py          ← C# proxy + cron contracts
│       └── test_scheduler.py             ← Scheduler contracts
│
├── data/                             ← Runtime only — gitignored
│   └── predictions/
│       ├── _market_ledger.json       ← scope=market_wide lessons (all sectors)
│       ├── automobile/
│       │   ├── _shared_ledger.json   ← scope=sector_wide lessons (all auto tickers)
│       │   └── MARUTI/               ← 4 JSON memory files per ticker
│       └── banking_bfsi/
│           └── ...
│
├── main.py                           ← CLI entry point
├── langgraph.json                    ← LangGraph graph registry
├── requirements.txt
├── .env.example
│
├── CODEBASE.md                       ← Authoritative module map + API reference
├── AGENT_DESIGN.md                   ← Agent architecture deep dive
├── SOLUTION_DESIGN.md                ← Service + runtime architecture
├── API_SOURCES.md                    ← Data sources, API limits, yfinance tickers
├── RL_FEEDBACK_DESIGN.md             ← Phase 5+6 RL system: schemas, daily flow, config
└── RL_EVOLUTION_DESIGN.md            ← Gap analysis + P1–P5 implementation roadmap
```

> `data/`, `logs/`, `outputs/` are created at runtime and gitignored.
> Full module detail and public API signatures: see [CODEBASE.md](CODEBASE.md).

---

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
cd services/gateway && bun install
cd frontend && npm install
```

### 2. Configure environment

```bash
cp .env.example .env
# Required:  OPENROUTER_API_KEY
# Optional:  SERPER_API_KEY, TAVILY_API_KEY, NEWSAPI_KEY
```

### 3. One-off CLI analysis

```bash
python main.py MARUTI
python main.py TATAMOTORS --output markdown --save
python main.py --list-tickers
```

### 4. Start the full stack

```bash
# Terminal 1 — Python FastAPI (internal)
uvicorn services.api.server:app --port 8001

# Terminal 2 — TypeScript gateway (public, REST + WS + analysis cron)
bun run services/gateway/src/index.ts

# Terminal 3 — RL daily review scheduler (post-market)
python services/scheduler/python/scheduler.py

# Terminal 4 — Frontend
cd frontend && npm run dev
# → http://localhost:5173
```

### 5. RL Feedback Loop commands

```bash
# Generate 30-day forecast (month-start)
python -m services.scheduler.run_schedule forecast --ticker MARUTI
python -m services.scheduler.run_schedule forecast --sector banking_bfsi --ticker HDFCBANK SBIN

# Run daily review (normally automated; run manually for backfill)
python -m services.scheduler.run_schedule daily-review --ticker MARUTI
python -m services.scheduler.run_schedule daily-review --sector it_sector --ticker TCS --date 2026-04-15

# Check learning status for a ticker
python -m services.scheduler.run_schedule feedback-status --ticker MARUTI
```

`feedback-status` output:
```
=== RL Feedback Status: MARUTI | Cycle: MARUTI_2026-04 ===

  Forecast horizon : 30 days          Days reviewed    : 12
  Direction accuracy: 9/12 (75.0%)    Weight version   : v7

  Current weights (v7):
    sales_demand         0.1850  (-0.0150 from base)
    fundamentals         0.2000  (+0.0200 from base)
    risk_macro           0.1500  (+0.0200 from base)
    pattern_analysis     0.1100  (-0.0100 from base)
    sentiment            0.0380  (-0.0020 from base)
    ...

  Learning ledger: 4 lessons
    [L001] RBI_policy_day        (conf=0.80, seen=4×, scope=sector_wide)
    [L002] month_end_inventory   (conf=0.65, seen=2×, scope=stock_specific)
    [L003] crude_oil_spike       (conf=0.72, seen=3×, scope=market_wide)
    [L004] shravan_demand_dip    (conf=0.68, seen=1×, scope=sector_wide)

  Top missed factors: [('FII_outflow_spike', 5), ('crude_oil_spot_price', 4)]
```

### 6. Build C++ indicators (optional, Windows)

```bash
# Requires Visual Studio 2022 + CMake
powershell -ExecutionPolicy Bypass -File core/intelligence/algorithms/cpp/build_ext.ps1
# → stockindicators.cp313-win_amd64.pyd  (auto-detected; pure-Python fallback if absent)
```

---

## Port Map

| Service | Port | Protocol | Visible to |
|---|---|---|---|
| Vite dev server | 5173 | HTTP | Browser |
| TypeScript Gateway (Bun + Hono) | 3000 | HTTP + WebSocket | Browser → gateway |
| Python FastAPI | 8001 | HTTP + WebSocket | Gateway only (CORS locked) |
| APScheduler (RL daily review) | — | No HTTP | Internal process |
| C# Quartz.NET (optional) | 5000 | HTTP | Python (when `CSHARP_SCHEDULER_ENABLED=true`) |

---

## Configuration

All settings in `core/config/settings/base.py` — override with environment variables or `.env`.

### LLM

| Variable | Default | Purpose |
|---|---|---|
| `OPENROUTER_API_KEY` | env var | OpenRouter API key |
| `LLM_MODEL` | `qwen/qwen3-235b-a22b` | Model slug |
| `LLM_TEMPERATURE` | `0.2` | General agent creativity |
| `LLM_MAX_TOKENS` | `2048` | Per-call token limit |
| `LLM_TIMEOUT_SECONDS` | `60` | Per-call timeout |

### Agent execution

| Variable | Default | Purpose |
|---|---|---|
| `AGENT_TIMEOUT_SECONDS` | `120` | Per-agent wall-clock timeout |
| `MAX_RETRIES` | `3` | LLM retry attempts (exponential back-off) |
| `AGENT_WEIGHTS` | see base.py | Per-agent score weights (must sum to 1.0) |
| `SCORE_THRESHOLDS` | see base.py | Score → verdict mapping |
| `SERPER_MAX_QUERIES` | `3` | Serper calls per agent per run |

### RL Feedback Loop

| Variable | Default | Purpose |
|---|---|---|
| `PREDICTION_DATA_DIR` | `data/predictions` | Root for all 4 JSON memory files |
| `FORECAST_HORIZON_DAYS` | `30` | Trading days in each prediction envelope |
| `WEIGHT_MIN_OBSERVATIONS` | `3` | Days of feedback before weight adaptation activates |
| `WEIGHT_ACCURACY_WINDOW` | `7` | Rolling window for direction hit-rate calculation |
| `WEIGHT_MAX_STEP` | `0.05` | Max weight change in a single daily update |
| `WEIGHT_MAX_DRIFT` | `0.15` | Max total drift any agent weight can move from its base |
| `WEIGHT_BOOST_HIT_RATE` | `0.70` | Hit rate to earn +0.02 weight boost |
| `WEIGHT_PENALTY_HIT_RATE` | `0.40` | Hit rate to receive −0.03 weight penalty |
| `FEEDBACK_CRON` | `0 11 * * 1-5` | Daily review cron (11:00 UTC = 4:30pm IST, weekdays) |

### Technical indicators

| Variable | Default | Purpose |
|---|---|---|
| `RSI_PERIOD` | `14` | RSI lookback |
| `MACD_FAST / SLOW / SIGNAL` | `12 / 26 / 9` | MACD parameters |
| `BB_PERIOD / BB_STD` | `20 / 2.0` | Bollinger Bands |
| `PRICE_HISTORY_YEARS` | `10` | Years of OHLCV history fetched |

---

## Data Sources

| Source | What It Returns | Free Limit | Key |
|---|---|---|---|
| **yfinance** | OHLCV, financials, macro prices, index data | Unlimited (unofficial) | None |
| **Serper** | Google search → title + snippet + URL | 2,500 calls/month | `SERPER_API_KEY` |
| **Tavily** | Google search → full extracted page text | 1,000 calls/month | `TAVILY_API_KEY` |
| **NewsAPI** | News articles from curated sources | 100 calls/day | `NEWSAPI_KEY` |
| **OpenRouter** | LLM inference (OpenAI-compatible) | Pay-per-token | `OPENROUTER_API_KEY` |

Serper is the primary search layer (larger quota). Tavily reserved for Policy/Regulatory agent where full government document depth matters. See [API_SOURCES.md](API_SOURCES.md) for per-agent source routing and all yfinance tickers used.

---

## Running Tests

```bash
# Full suite (LLM and network calls are mocked — no API key needed)
pytest tests/ -v

# By layer
pytest tests/unit/ -v
pytest tests/integration/ -v
pytest tests/contract/ -v

# Phase-specific contracts
pytest tests/contract/test_phase0_llm_migration.py -v   # zero Groq references
pytest tests/contract/test_phase1_indicators.py -v      # C++ parity (25 tests)
pytest tests/contract/test_phase3_typescript.py -v      # JSON shape contracts
pytest tests/contract/test_phase4_csharp.py -v          # C# proxy contracts

# With coverage
pytest tests/ --cov=core --cov=services --cov-report=term-missing
```

**Baseline:** 292 passed, 7 skipped (C++ parity tests — skipped until `.pyd` is compiled), 0 failed.

---

## Supported Tickers

| Ticker | Company |
|---|---|
| `MARUTI` | Maruti Suzuki India Ltd |
| `TATAMOTORS` | Tata Motors Ltd |
| `M&M` | Mahindra & Mahindra Ltd |
| `HEROMOTOCO` | Hero MotoCorp Ltd |
| `BAJAJ-AUTO` | Bajaj Auto Ltd |
| `EICHERMOT` | Eicher Motors Ltd (Royal Enfield) |
| `TVSMOTORS` | TVS Motor Company Ltd |
| `ASHOKLEY` | Ashok Leyland Ltd |
| `ESCORTS` | Escorts Kubota Ltd |
| `FORCEMOT` | Force Motors Ltd |

The orchestrator accepts free-form names ("Tata Motors", "Mahindra") — the LLM resolves them to the correct NSE ticker automatically.

---

## Key Design Decisions

**1. Stateful RL loop — not a one-shot tool**
Most LLM finance tools are stateless: browse → summarize → forget. StockAgent maintains 4 JSON memory files per ticker that persist across monthly cycles. Every miss is logged, root-caused, and used to adjust agent weights. After 6 months, the learning ledger is a proprietary rulebook for how each specific stock responds to specific events.

**2. Miss taxonomy — fair blame attribution**
The `WeightAdapter` uses a 7-type miss taxonomy. Misses classified as `data_gap`, `data_stale`, or `external_shock` carry **zero penalty** — the agent was not at fault. Only `model_bias` and `direction_flip` carry full penalties. This prevents the system from incorrectly penalising agents for unpredictable events.

**3. Bounded weight adaptation — no runaway drift**
Agent weights can move at most `±0.05` per day and at most `±0.15` from their base over all time. This ensures no single bad week silences an agent permanently, and no single good week gives one agent disproportionate influence.

**4. Lesson scope propagation — sector and market learning**
Lessons are tagged `stock_specific`, `sector_wide`, or `market_wide`. Sector-wide lessons (e.g., RBI impact on all banking stocks) propagate to a shared sector ledger that every ticker in that sector reads. Market-wide lessons (e.g., global crude shock) propagate to a root ledger read by all sectors.

**5. Language boundaries via JSON over HTTP**
TypeScript (gateway) and the frontend never import Python modules. All cross-language calls are `POST :8001/analyse` with a FinalReport JSON response. The C++ extension is the only in-process FFI, and it fails silently to pure Python.

**6. LangGraph worker pool for parallelism**
Agents run as LangGraph `Send` nodes with a `RetryPolicy`. Failed agents return a neutral `0.5` score and the pipeline always completes — graceful degradation is guaranteed.

---

## Phase Status

| Phase | Description | Status |
|---|---|---|
| Phase 0 | Groq → OpenRouter / Qwen migration | Complete |
| Phase 1 | C++ RSI / MACD / Bollinger Bands (pybind11) | Live (`_USE_CPP=True`) |
| Phase 2 | FastAPI bridge + WebSocket streaming | Complete |
| Phase 3 | TypeScript gateway (Bun + Hono) | Complete |
| Phase 4 | C# Quartz.NET scheduler (optional, feature-flagged) | Scaffolded |
| Phase 5 | RL feedback loop — prediction envelope + daily review + weight adaptation | Complete |
| Phase 6 | RL improvements — miss taxonomy, lesson scope, timing accuracy, revised context | Complete |
| **Evolution P1** | SeasonalCalendar — pre-seeded sector patterns (Dec clearance, Diwali, etc.) | Complete |
| **Evolution P2** | Shared sector + market ledger cross-ticker propagation | Complete |
| **Evolution P3** | Conviction duration counter + mean-reversion prior | Complete |
| **Evolution P4** | PromptEnhancer — miss_counter auto-updates agent search queries | Complete |
| **Evolution P5** | Context-conditional regime multiplier (VIX + FII + RSI) | Complete |

Evolution P1–P5 design: see [RL_EVOLUTION_DESIGN.md](RL_EVOLUTION_DESIGN.md).
RL system internals (schemas, daily flow, config reference): see [RL_FEEDBACK_DESIGN.md](RL_FEEDBACK_DESIGN.md).

---

## Reference Documents

| Document | Contents |
|---|---|
| [CODEBASE.md](CODEBASE.md) | Authoritative module map, public APIs, runtime architecture, settings reference |
| [AGENT_DESIGN.md](AGENT_DESIGN.md) | Agent design, LangGraph wiring, parallelism model |
| [SOLUTION_DESIGN.md](SOLUTION_DESIGN.md) | Service architecture, target vs implementation mapping |
| [FLOW.md](FLOW.md) | End-to-end system flow: entry points, per-phase internals, error handling, data-flow diagram |
| [API_SOURCES.md](API_SOURCES.md) | Data sources per agent, yfinance tickers, API limits |
| [RL_FEEDBACK_DESIGN.md](RL_FEEDBACK_DESIGN.md) | Phase 5+6 RL system: all schemas, daily cron flow, configuration |
| [RL_EVOLUTION_DESIGN.md](RL_EVOLUTION_DESIGN.md) | Gap analysis + P1–P5 logical design with ASCII trees, schema tables |
| [RL_REFERENCE.md](RL_REFERENCE.md) | Auto-generated quick-reference: daily loop steps, agent roster, weight bounds, config variables |
