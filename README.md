# StockAgent — Automobile Stock Analyser

> AI-powered Indian automobile stock analyser using a **multi-language, multi-agent** architecture.
> Built with OpenRouter/Qwen LLM, C++ native indicators, TypeScript dashboard, and C# scheduler.

---

## What this project does

**StockAgent** analyses any NSE/BSE-listed Indian automobile stock and produces a structured
**investment score + verdict** by running eight specialist AI sub-agents in parallel,
fusing their outputs in a Signal Aggregator, and persisting results for trend tracking.

```
User Input (ticker / company name)
          │
          ▼
  AutomobileAgentOrchestrator
  (resolves ticker, dispatches 8 agents in parallel)
          │
   ┌──────┼──────┬──────────┬──────────┬──────────┬──────────┬──────────┐
   ▼      ▼      ▼          ▼          ▼          ▼          ▼          ▼
Sales  Raw    Funda-   Pattern   Sentiment  Policy   Compet.  Risk &
Demand Mats   mentals  Analysis             Reg.    Intel    Macro
   └──────┴──────┴──────────┴──────────┴──────────┴──────────┴──────────┘
                                   │
                                   ▼
                           Signal Aggregator
                       (weighted fusion + conflict resolution)
                                   │
                                   ▼
                       Automobile Stock Score Output
                       (0.0–1.0 score + verdict + thesis)
```

---

## Agent Overview

| Agent | Weight | Dimensions analysed |
|---|---|---|
| Sales & Demand | 18% | FADA/SIAM dispatch, EV Vahan data, dealer inventory, DGFT exports, used car price index |
| Raw Materials | 10% | Steel/aluminium, platinum/palladium, crude/polymer, power tariff, commodities trend |
| Fundamentals | 20% | Revenue/EBITDA delta, margin vs peers, order book, headcount, FII/DII flow |
| Pattern Analysis | 13% | 10-yr price cycle, seasonal patterns, RSI/MACD/BB, support/resistance, Nifty Auto correlation |
| Sentiment | 4% | News NLP, earnings call tone, Twitter/Reddit, YouTube spikes, dealer feedback |
| Policy & Regulatory | 10% | FAME EV subsidy, emission norms, Union Budget duties, PLI scheme, state EV incentives |
| Competitive Intel | 10% | EV market share, new model pipeline, JV/acquisitions, ADAS/safety ratings |
| Risk & Macro | 15% | INR/USD/crude exposure, commodities, RBI repo rate, emission policy risk, China supply |

**Signal Aggregator** applies weights, detects conflicts (score delta ≥ 0.30 between any two agents),
asks the LLM to resolve them, and emits a final verdict: `STRONG BUY / BUY / NEUTRAL / SELL / STRONG SELL`.

---

## Multi-Language Architecture

| Language | Module | Port | Status |
|---|---|---|---|
| **Python** | 8 LLM agents, orchestrator, RAG, FastAPI bridge | 8000 | ✅ Complete |
| **C++** | RSI / MACD / Bollinger Bands via pybind11 | — (in-process .pyd) | ✅ Live |
| **TypeScript** | Express REST proxy + WebSocket hub | 3000 (REST), 3001 (WS) | ✅ Scaffolded |
| **C#** | Quartz.NET cron scheduler + EF Core persistence | 5000 | ✅ Scaffolded |

Every language boundary uses **JSON over HTTP** — no shared memory, no cross-language FFI
(except C++ which runs in-process via pybind11).

---

## Project Structure

```
StockAgent-main/
│
├── config/
│   ├── settings.py            ← ALL static config: API keys, LLM, weights, ports, scheduler
│   └── rag_config.py          ← RAG pipeline config (RAG_ENABLED=false by default)
│
├── agents/
│   ├── base_agent.py          ← Abstract base: sync+async LLM caller, retry, context routing
│   ├── orchestrator.py        ← Top-level dispatcher — sync (ThreadPoolExecutor) + async (asyncio.gather)
│   ├── signal_aggregator.py   ← Weighted fusion + LLM conflict resolution → FinalReport
│   ├── sales_demand.py
│   ├── raw_materials.py
│   ├── fundamentals.py
│   ├── pattern_analysis.py
│   ├── sentiment.py
│   ├── policy_regulatory.py
│   ├── competitive_intel.py
│   └── risk_macro.py
│
├── models/
│   └── schemas.py             ← All Pydantic v2 models (StockQuery, AgentOutput, FinalReport)
│
├── prompts/
│   ├── sales_demand.py        ← System + analysis prompts per agent
│   ├── raw_materials.py
│   ├── fundamentals.py
│   ├── pattern_analysis.py
│   ├── sentiment.py
│   ├── policy_regulatory.py
│   ├── competitive_intel.py
│   ├── risk_macro.py
│   ├── signal_aggregator.py
│   └── orchestrator.py        ← Ticker resolution prompt
│
├── tools/
│   ├── yfinance_fetcher.py    ← OHLCV, RSI/MACD/BB (C++ dispatch when _USE_CPP=True, pure-Python fallback)
│   ├── yfinance_fetcher_pure.py ← Frozen pure-Python reference (parity tests for C++ extension)
│   ├── fundamentals_fetcher.py  ← Quarterly P&L, margins, shareholding via yfinance
│   ├── news_fetcher.py          ← Serper + NewsAPI search
│   ├── macro_fetcher.py         ← INR/USD, crude, commodities via yfinance
│   ├── context_builder.py       ← Routes each agent to the right fetchers
│   ├── macro_cache.py           ← In-memory macro news cache (TTL-based, avoids repeat Serper calls)
│   ├── score_store.py           ← SQLite persistence; proxies to C# when CSHARP_SCHEDULER_ENABLED=true
│   ├── scheduler.py             ← APScheduler cron daemon (Python-side; replaced by C# Quartz when flag set)
│   ├── alerting.py              ← Score/verdict change alerts: console / file / webhook
│   ├── prediction_store.py      ← RL feedback loop — prediction tracking
│   ├── tavily_fetcher.py        ← Full-page extraction for Policy/Regulatory agent
│   └── rag/
│       ├── embedder.py          ← sentence-transformers local embeddings
│       ├── vector_store.py      ← ChromaDB CRUD wrapper
│       ├── ingestion.py         ← PDF/TXT chunking + indexing
│       └── retriever.py         ← Semantic search + optional cross-encoder reranking
│
├── api/                         ← FastAPI bridge (port 8000)
│   ├── server.py                ← FastAPI app, CORS for ports 3000/3001/5000
│   └── routes/
│       ├── analyse.py           ← POST /analyse → orchestrator.analyse_async(ticker)
│       ├── history.py           ← GET /history/{ticker}[/latest] → ScoreStore
│       └── stream.py            ← WS /ws/stream?ticker=MARUTI → async progress events
│
├── cpp/                         ← C++ pybind11 extension (Phase 1)
│   ├── CMakeLists.txt           ← FetchContent pybind11 v2.13.6; installs .pyd to project root
│   ├── build_ext.ps1            ← PowerShell build helper (VS 2022 + CMake)
│   └── src/
│       └── indicators.cpp       ← RSI (EWM adjust=True), MACD (EWM adjust=False), Bollinger Bands (ddof=1)
│
├── typescript/                  ← TypeScript dashboard (ports 3000 + 3001)
│   ├── package.json
│   ├── tsconfig.json
│   └── src/
│       ├── index.ts             ← Express :3000 + HTTP server for WS hub :3001
│       ├── wsHub.ts             ← WS hub: one upstream per ticker → rebroadcasts to all subscribers
│       ├── clients/
│       │   └── pythonClient.ts  ← axios wrappers: postAnalyse, getHistory, getSchedulerStatus
│       ├── routes/
│       │   ├── analyse.ts       ← POST /api/analyse  → POST :8000/analyse
│       │   ├── history.ts       ← GET  /api/history  → GET  :8000/history
│       │   └── schedule.ts      ← GET  /api/schedule → GET  :5000/scheduler/status
│       └── types/
│           └── stockAgent.ts    ← FinalReport, StreamEvent, SchedulerStatus interfaces
│
├── csharp/                      ← C# Quartz.NET scheduler + EF Core persistence (port 5000)
│   └── StockAgent.Scheduler/
│       ├── StockAgent.Scheduler.csproj  ← Quartz 3.13, EF Core 8, Polly, ASP.NET 8
│       ├── Program.cs                   ← DI wiring, EF migrations on startup, port 5000
│       ├── appsettings.json             ← PythonApiUrl, cron, tickers, alert threshold
│       ├── Jobs/
│       │   └── AnalyseJob.cs            ← [DisallowConcurrentExecution] Quartz job
│       ├── Data/
│       │   └── SchedulerDbContext.cs    ← EF Core DbContext → ScoreRecords table (SQL Server)
│       ├── Models/
│       │   ├── FinalReportDto.cs        ← Mirrors Python FinalReport (snake_case JsonPropertyName)
│       │   ├── ScoreRecord.cs           ← EF entity; ScoreRecord.FromDto(dto)
│       │   └── SchedulerStatus.cs       ← Response shape for GET /scheduler/status
│       └── Controllers/
│           ├── HealthController.cs      ← GET /health → {status, service, next_fire_utc}
│           ├── SchedulerController.cs   ← GET /scheduler/status
│           └── ScoresController.cs      ← POST /scores, GET /scores/{ticker}[/latest]
│
├── scripts/
│   ├── ingest_documents.py     ← CLI: index documents into ChromaDB
│   └── run_schedule.py         ← CLI: start | run-now | status | history | latest
│
├── tests/
│   ├── conftest.py
│   ├── test_config.py
│   ├── test_schemas.py
│   ├── test_agents_unit.py
│   ├── test_signal_aggregator.py
│   ├── test_orchestrator.py
│   ├── test_prompts.py
│   ├── test_data_fetchers.py
│   ├── test_rag.py
│   ├── test_scheduler.py
│   ├── test_phase0_llm_migration.py  ← Zero Groq references; OpenRouter/Qwen wiring
│   ├── test_phase1_indicators.py     ← 25 tests: pure-Python parity + C++ bridge + fallback
│   ├── test_phase2_api.py            ← FastAPI /analyse /history /ws/stream contracts
│   ├── test_phase3_typescript.py     ← Python-side JSON shape contracts for TypeScript client
│   └── test_phase4_csharp.py         ← Python-side C# proxy + JSON + cron contracts
│
├── data/                       ← SQLite DB + ChromaDB store (git-ignored)
├── outputs/                    ← Saved reports + alert logs (git-ignored)
├── logs/                       ← Runtime logs (git-ignored)
├── stockindicators.cp313-win_amd64.pyd  ← Compiled C++ extension (built from cpp/)
├── main.py                     ← One-off CLI entry point (never modified by other phases)
└── requirements.txt
```

---

## Quick Start

### 1. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Add your OPENROUTER_API_KEY (required)
# Optional: SERPER_API_KEY, NEWSAPI_KEY
```

### 3. Run a one-off analysis (CLI)

```bash
# Analyse Maruti Suzuki
python main.py MARUTI

# Markdown output, save to outputs/
python main.py TATAMOTORS --output markdown --save

# List all supported tickers
python main.py --list-tickers
```

### 4. Start the FastAPI bridge (port 8000)

```bash
uvicorn api.server:app --reload --port 8000
# POST http://localhost:8000/analyse        {"ticker": "MARUTI"}
# GET  http://localhost:8000/history/MARUTI
# WS   ws://localhost:8000/ws/stream?ticker=MARUTI
```

### 5. Start the TypeScript dashboard (ports 3000 + 3001)

```bash
cd typescript
npm install
npm run dev          # ts-node src/index.ts
# REST:  http://localhost:3000/api/analyse
# WS:    ws://localhost:3001?ticker=MARUTI
# Sched: http://localhost:3000/api/schedule  (proxies to C# :5000)
```

### 6. Build and activate the C++ indicators

```bash
# Requires: Visual Studio 2022 + CMake (Windows)
#           or GCC/Clang + CMake (Linux/macOS)
powershell -ExecutionPolicy Bypass -File cpp/build_ext.ps1

# After build, stockindicators.cp313-win_amd64.pyd lands in project root
# Python automatically uses C++ for RSI/MACD/BB (_USE_CPP=True)
# Falls back to pure Python silently if .pyd is absent
```

### 7. Start the C# scheduler (port 5000)

```bash
# Requires: .NET 8 SDK + SQL Server (or localdb)
cd csharp/StockAgent.Scheduler
dotnet run
# GET  http://localhost:5000/health
# GET  http://localhost:5000/scheduler/status
# POST http://localhost:5000/scores          (called by Python when CSHARP_SCHEDULER_ENABLED=true)
```

---

## Port Map

| Service | Port | Protocol |
|---|---|---|
| Python FastAPI | 8000 | HTTP + WebSocket |
| C# Quartz Scheduler | 5000 | HTTP |
| TypeScript REST | 3000 | HTTP |
| TypeScript WebSocket hub | 3001 | WebSocket |

---

## Configuration Guide

All configuration lives in `config/settings.py` — override any value with environment variables or `.env`.

### LLM

| Variable | Default | Purpose |
|---|---|---|
| `OPENROUTER_API_KEY` | env var | OpenRouter API key |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | OpenRouter endpoint |
| `LLM_MODEL` | `qwen/qwen3-235b-a22b` | Model slug (accuracy-first) |
| `LLM_TEMPERATURE` | `0.2` | LLM creativity |
| `LLM_MAX_TOKENS` | `2048` | Max tokens per response |
| `LLM_TIMEOUT_SECONDS` | `60` | Per-call timeout |

### Agent execution

| Variable | Default | Purpose |
|---|---|---|
| `AGENT_TIMEOUT_SECONDS` | `120` | Per-agent wall-clock timeout |
| `MAX_RETRIES` | `3` | LLM retry attempts (exponential back-off) |
| `AGENT_WEIGHTS` | see settings.py | Per-agent score weights (must sum to 1.0) |
| `SCORE_THRESHOLDS` | see settings.py | Score → verdict mapping |

### Technical indicators (C++ / pure-Python)

| Variable | Default | Purpose |
|---|---|---|
| `RSI_PERIOD` | `14` | RSI lookback period |
| `MACD_FAST` / `SLOW` / `SIGNAL` | `12 / 26 / 9` | MACD parameters |
| `BB_PERIOD` / `BB_STD` | `20 / 2.0` | Bollinger Bands parameters |
| `PRICE_HISTORY_YEARS` | `10` | Years of OHLCV history |

### Python scheduler (APScheduler)

| Variable | Default | Purpose |
|---|---|---|
| `SCHEDULER_ENABLED` | `false` | Master switch for the APScheduler daemon |
| `SCHEDULER_CRON` | `30 8 * * 1-5` | Cron expression (IST, weekdays 8:30am) |
| `SCHEDULER_TICKERS` | 5 major OEMs | Tickers to run each cycle |
| `SCORE_DB_PATH` | `data/scores.db` | SQLite database path |
| `ALERT_SCORE_CHANGE_THRESHOLD` | `0.10` | Min score delta to fire alert |
| `ALERT_ON_VERDICT_CHANGE` | `true` | Alert when verdict changes |
| `ALERT_CHANNELS` | `console,file` | `console` / `file` / `webhook` |
| `ALERT_WEBHOOK_URL` | `` | Slack/Discord/custom webhook |
| `SCORE_HISTORY_MAX_ROWS` | `90` | Records retained per ticker |

### C# scheduler integration

| Variable | Default | Purpose |
|---|---|---|
| `CSHARP_SCHEDULER_ENABLED` | `false` | Routes score_store.save() to C# POST /scores |
| `CSHARP_API_URL` | `http://localhost:5000` | C# service base URL |

---

## Running Tests

```bash
# Full suite — no API key needed (LLM is mocked)
pytest tests/ -v

# Phase-specific
pytest tests/test_phase1_indicators.py -v   # 25 tests: C++ parity + fallback
pytest tests/test_phase2_api.py -v          # FastAPI contracts
pytest tests/test_phase3_typescript.py -v   # TS client JSON shape contracts
pytest tests/test_phase4_csharp.py -v       # C# proxy + cron contracts

# With coverage
pytest tests/ --cov=. --cov-report=term-missing
```

**Baseline:** 292 passed, 0 failed, 38 warnings (all LLM and network calls mocked).

---

## Supported Tickers

| Ticker | Company |
|---|---|
| MARUTI | Maruti Suzuki India Ltd |
| TATAMOTORS | Tata Motors Ltd |
| M&M | Mahindra & Mahindra Ltd |
| HEROMOTOCO | Hero MotoCorp Ltd |
| BAJAJ-AUTO | Bajaj Auto Ltd |
| EICHERMOT | Eicher Motors Ltd (Royal Enfield) |
| TVSMOTORS | TVS Motor Company Ltd |
| ASHOKLEY | Ashok Leyland Ltd |
| ESCORTS | Escorts Kubota Ltd |
| FORCEMOT | Force Motors Ltd |

The orchestrator also accepts free-form names ("Tata Motors") — the LLM resolves them to the correct ticker.

---

## Key Design Decisions

1. **Language boundaries via JSON over HTTP** — TypeScript and C# never import Python modules.
   They call `POST :8000/analyse` and receive a FinalReport JSON. The C++ extension is the only
   in-process foreign code (pybind11).

2. **Two execution paths, same output** — `orchestrator.analyse()` (sync, ThreadPoolExecutor × 8)
   for CLI/scheduler; `orchestrator.analyse_async()` (async, asyncio.gather) for FastAPI.
   Both produce an identical `FinalReport`.

3. **C++ fallback** — `_USE_CPP=True` when `stockindicators.pyd` is importable; silently falls
   back to pure Python otherwise. Build failure never breaks the system.

4. **Feature flags** — `CSHARP_SCHEDULER_ENABLED=false` (default) keeps the Python SQLite path
   active. Set to `true` to route persistence through C# EF Core + SQL Server.

5. **Specialisation → Parallelism → Conflict-Aware Fusion** — 8 specialist agents each get only
   the data they need. The Signal Aggregator resolves conflicts with LLM reasoning, not arithmetic.

6. **Graceful degradation** — Every failure has a fallback. Agents return neutral (0.5) on error.
   The pipeline always produces a final report.

---

## Status

| Component | Status |
|---|---|
| 8 LLM agents + Signal Aggregator | ✅ Complete |
| Orchestrator (sync + async parallel) | ✅ Complete |
| CLI (`main.py`) | ✅ Complete |
| Live data feeds (yfinance + Serper + NewsAPI) | ✅ Complete |
| RAG pipeline (ChromaDB + sentence-transformers) | ✅ Complete |
| Python scheduler (APScheduler) + alerting | ✅ Complete |
| **Phase 0** — Groq → OpenRouter/Qwen migration | ✅ Complete |
| **Phase 1** — C++ RSI/MACD/BB extension (pybind11) | ✅ Live (`_USE_CPP=True`) |
| **Phase 2** — FastAPI bridge (port 8000) | ✅ Complete |
| **Phase 3** — TypeScript dashboard scaffold | ✅ Scaffolded (`tsc` clean) |
| **Phase 4** — C# Quartz.NET + EF Core scheduler | ✅ Scaffolded (needs .NET 8 SDK) |
