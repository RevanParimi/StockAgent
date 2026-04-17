# StockAgent — Complete System Flow

> This document explains the full logical flow of every component:
> what runs, in what order, why each step exists, and how data moves
> through the system from user input to investment verdict.

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Entry Points](#2-entry-points)
3. [Core Agent Pipeline](#3-core-agent-pipeline)
   - 3.1 Ticker Resolution
   - 3.2 Context Assembly
   - 3.3 Parallel Agent Execution (sync + async)
   - 3.4 Per-Agent Internal Flow
   - 3.5 Signal Aggregation
   - 3.6 Output
4. [Phase 1 — C++ Technical Indicators](#4-phase-1--c-technical-indicators)
5. [Phase 2 — FastAPI Bridge](#5-phase-2--fastapi-bridge)
6. [Phase 2b — Live Data Feeds](#6-phase-2b--live-data-feeds)
7. [Phase 3 — TypeScript Dashboard](#7-phase-3--typescript-dashboard)
8. [Phase 4 — C# Quartz Scheduler](#8-phase-4--c-quartz-scheduler)
9. [RAG Pipeline](#9-rag-pipeline)
10. [Python Scheduler & Alerting](#10-python-scheduler--alerting)
11. [Configuration Hierarchy](#11-configuration-hierarchy)
12. [Error Handling & Fallbacks](#12-error-handling--fallbacks)
13. [Full System Data Flow Diagram](#13-full-system-data-flow-diagram)
14. [Scoring & Verdict Logic](#14-scoring--verdict-logic)
15. [File Responsibility Map](#15-file-responsibility-map)

---

## 1. System Overview

StockAgent is a **multi-language, multi-agent LLM pipeline** that analyses Indian NSE/BSE
automobile stocks across eight specialist viewpoints, runs them in parallel, then fuses
the results into a single investment score and verdict.

**Why multi-agent?**
A single LLM prompt asking "should I buy MARUTI?" produces shallow, generic output.
Splitting the problem into specialist agents forces depth in each dimension:
a fundamentals agent cannot take shortcuts on technicals, and vice versa.
The Signal Aggregator synthesises all eight views — including resolving conflicts between them.

### Language ownership

```
┌──────────────────────────────────────────────────────────────────────┐
│  Python (port 8000)                                                  │
│    8 LLM agents, orchestrator, RAG pipeline, APScheduler            │
│    FastAPI bridge: POST /analyse, GET /history, WS /ws/stream       │
├──────────────────────────────────────────────────────────────────────┤
│  C++ (in-process .pyd extension)                                     │
│    RSI(14), MACD(12,26,9), Bollinger Bands(20,2σ)                  │
│    Loaded by yfinance_fetcher.py via pybind11                        │
│    Pure-Python fallback if .pyd absent (_USE_CPP=False)             │
├──────────────────────────────────────────────────────────────────────┤
│  TypeScript (ports 3000 + 3001)                                      │
│    Express REST proxy → :8000  (POST /api/analyse, GET /api/history)│
│    WS hub → :8000/ws/stream  (one upstream per ticker, rebroadcast) │
│    GET /api/schedule → :5000/scheduler/status                        │
├──────────────────────────────────────────────────────────────────────┤
│  C# (port 5000)                                                      │
│    Quartz.NET cron "0 30 8 ? * MON-FRI" (8:30am IST weekdays)      │
│    EF Core → SQL Server (ScoreRecords table)                         │
│    ASP.NET controllers: /health, /scheduler/status, /scores         │
└──────────────────────────────────────────────────────────────────────┘
```

**Core principle:** `Specialisation → Parallelism → Conflict-Aware Fusion → Verdict`

Every language boundary uses **JSON over HTTP** — no shared memory, no cross-language FFI
(C++ is the only exception: it runs in-process via pybind11).

---

## 2. Entry Points

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                               ENTRY POINTS                                    │
├──────────────┬─────────────────┬────────────────────┬────────────────────────┤
│  Python CLI  │  FastAPI HTTP   │  TypeScript REST   │  C# Quartz Job         │
│              │  (port 8000)    │  (port 3000)       │  (port 5000)           │
│  python      │                 │                    │                        │
│  main.py     │  POST           │  POST              │  AnalyseJob fires at   │
│  MARUTI      │  /analyse       │  /api/analyse      │  8:30am IST weekdays   │
│              │  ↑              │  → proxies to      │  → POST :8000/analyse  │
│              │  Used by TS     │    :8000/analyse   │  → saves to SQL Server │
│              │  and C# clients │                    │  → fires webhook alert │
│       ↓              ↓                  ↓                       ↓            │
│            AutomobileAgentOrchestrator.analyse(ticker)                        │
│            or  .analyse_async(ticker)  [FastAPI path]                         │
└──────────────────────────────────────────────────────────────────────────────┘
```

- **CLI / APScheduler** → `orchestrator.analyse()` (sync, ThreadPoolExecutor × 8)
- **FastAPI / C# / TypeScript** → `orchestrator.analyse_async()` (async, asyncio.gather)
- Both paths run the same 8 agents and produce an identical `FinalReport`.

---

## 3. Core Agent Pipeline

### 3.1 Ticker Resolution

**File:** `agents/orchestrator.py → _resolve_ticker()`

```
User input: "Maruti Suzuki"
      │
      ▼
LLM call (OpenRouter/Qwen via OpenAI SDK, temperature=0.0 for determinism)
  Prompt: TICKER_RESOLUTION_PROMPT  ← known ticker table embedded
      │
      ▼
JSON: { "ticker": "MARUTI", "company_name": "Maruti Suzuki India Ltd",
        "exchange": "NSE", "confidence": 0.99 }
      │
      ▼
StockQuery object (Pydantic, ticker auto-uppercased)
      │
  ┌───┴──────────────────────────────────────────┐
  │ Fallback: if LLM call fails,                  │
  │ treat raw input as ticker directly            │
  └──────────────────────────────────────────────┘
```

---

### 3.2 Context Assembly

**File:** `agents/base_agent.py → _gather_context()`

Each agent gets context before the LLM call via a priority chain:

```
_gather_context(query)
      │
      ▼ Check 1: RAG_ENABLED=true?
      ├── YES → RAGRetriever.retrieve(search_query)
      │         → top-K chunks from ChromaDB (cosine similarity)
      │         → optional cross-encoder reranking
      │
      ├── NO  → ContextBuilder().build(agent_name, query)
      │         → routes to agent-specific fetcher (yfinance / news / macro)
      │
      └── FALLBACK (both fail) → minimal stub string
          "Stock: MARUTI | Date: 2026-04-17 | Note: Live data unavailable."
```

**Why layered?** RAG provides *your own documents*; live data provides real-time market
data; stub ensures the pipeline never crashes. Agents reason from LLM training knowledge
as the last resort.

---

### 3.3 Parallel Agent Execution

**File:** `agents/orchestrator.py → _run_agents_parallel()` / `_run_agents_parallel_async()`

```
Sync path (CLI / APScheduler / C# AnalyseJob):
────────────────────────────────────────────
ThreadPoolExecutor(max_workers=8)
  ├── agent.run(query) × 8
  └── as_completed(timeout=AGENT_TIMEOUT_SECONDS)
  LLM client: openai.OpenAI (sync)
  Retry back-off: time.sleep()

Async path (FastAPI /analyse, /ws/stream):
────────────────────────────────────────────
asyncio.gather(*[agent.run_async(query) for agent in _SUB_AGENTS])
  each run_async():
    context  = await asyncio.to_thread(_gather_context)   ← yfinance/news I/O offloaded
    raw_json = await AsyncOpenAI.chat.completions.create  ← true coroutine, no thread
  Retry back-off: asyncio.sleep()
```

**Why two paths?** The sync path keeps CLI, APScheduler, and all unit tests unchanged.
The async path gives FastAPI true coroutine-level concurrency — no OS threads for LLM
calls, no GIL concern, lower memory footprint under concurrent requests.

---

### 3.4 Per-Agent Internal Flow

Every sub-agent follows the same pattern (defined in `BaseAgent`):

```
agent.run(query)  [or run_async]
      │
      ▼
1. _gather_context(query)         → context string
      │
      ▼
2. _build_prompt(query, context)  → (system_prompt, user_prompt)
   prompts/<agent_name>.py: {ticker}, {company_name}, {context} filled
      │
      ▼
3. LLM call with retry
   model: qwen/qwen3-235b-a22b via OpenRouter
   response_format={"type": "json_object"}   ← guarantees parseable JSON
   MAX_RETRIES=3, exponential back-off
      │
      ▼
4. _safe_parse(raw_json, ticker)
   json.loads → _parse_output() → scores clamped to [0.0, 1.0]
      │
   ┌──┴──────────────────────────────────────┐
   │ On any failure:                          │
   │ AgentOutput with overall_score=0.5       │
   │ (neutral), error message in key_risks   │
   └─────────────────────────────────────────┘
      │
      ▼
5. Returns AgentOutput (Pydantic)
   Fields: overall_score, sub_scores (5 dimensions),
           key_positives, key_risks, summary, data_freshness
```

---

### 3.5 Signal Aggregation

**File:** `agents/signal_aggregator.py`

```
dict[agent_name → AgentOutput]  (8 agents)
      │
      ▼
Step 1: Weighted Score
  composite = Σ(agent.overall_score × weight) / Σ(weights)
  Weights: sales_demand 0.18, raw_materials 0.10, fundamentals 0.20,
           pattern_analysis 0.13, sentiment 0.04, policy_regulatory 0.10,
           competitive_intel 0.10, risk_macro 0.15
      │
      ▼
Step 2: Conflict Detection
  For every pair: if |score_A - score_B| ≥ 0.30 → conflict_flags
  WHY 0.30: meaningful disagreement (e.g. BUY vs NEUTRAL range)
      │
      ▼
Step 3: LLM Resolution (AGGREGATION_PROMPT, OpenRouter/Qwen)
  Input: all 8 scores + weights + composite + conflict list
  Output: confirmed/adjusted score, conflict narrative,
          conviction drivers, top risks, investment thesis
      │
      ▼
Step 4: FinalReport (Pydantic)
  final_score, verdict, weighted_agent_scores,
  conflicts_resolved, conviction_drivers, top_risks,
  investment_thesis, report_date
```

**Why LLM resolves conflicts instead of a formula?**
A formula (discard outliers) loses information. When fundamentals are bullish but
macro is bearish, the right answer depends on which is more reliable *right now* —
that requires reasoning, not arithmetic.

---

### 3.6 Output

```
FinalReport
      │
      ├── CLI --output json      → report.model_dump_json(indent=2)
      ├── CLI --output markdown  → formatted table + thesis + bullets
      ├── --save flag            → outputs/{TICKER}_{DATE}.{ext}
      │
      ├── FastAPI /analyse       → report.model_dump() as JSON response
      ├── FastAPI /ws/stream     → progress events + complete event (WebSocket)
      │
      └── ScoreStore.save(report)
          → SQLite (default) or C# POST /scores (CSHARP_SCHEDULER_ENABLED=true)
```

---

## 4. Phase 1 — C++ Technical Indicators

**Files:** `cpp/src/indicators.cpp`, `cpp/CMakeLists.txt`, `tools/yfinance_fetcher.py`

The C++ extension (`stockindicators`) implements RSI, MACD, and Bollinger Bands to match
the pandas reference implementation within ±0.01 absolute tolerance.

### Dispatch logic in `yfinance_fetcher.py`

```python
try:
    import stockindicators as _cpp_indicators
    _USE_CPP = True   # C++ path active
except ImportError:
    _cpp_indicators = None
    _USE_CPP = False  # pure-Python fallback

def compute_rsi(close, period=14):
    if _USE_CPP:
        return _cpp_indicators.compute_rsi(close.tolist(), period)
    # ... pandas/numpy fallback ...
```

### Algorithm parity (C++ matches Python exactly)

| Function | Python algorithm | C++ implementation |
|---|---|---|
| `compute_rsi` | `ewm(com=period-1, adjust=True)` | `ewm_adjusted()` — recursive num/den update |
| `compute_macd` | `ewm(span=n, adjust=False)` | `ewm_unadjusted()` — α·x + (1-α)·prev |
| `compute_bollinger_bands` | `rolling(n).std()` (ddof=1) | Variance = (Σx² − n·μ²)/(n−1) |

### Build (Windows — VS 2022 required)

```powershell
powershell -ExecutionPolicy Bypass -File cpp/build_ext.ps1
# Output: stockindicators.cp313-win_amd64.pyd  (project root)
```

```bash
# Linux / macOS
cmake -S cpp -B cpp/build -DCMAKE_BUILD_TYPE=Release
cmake --build cpp/build
cmake --install cpp/build    # copies .so to project root
```

### Test

```bash
pytest tests/test_phase1_indicators.py -v
# 25 passed:
#   TestRSIPurePython (5)           — pure-Python correctness
#   TestMACDPurePython (4)          — pure-Python correctness
#   TestBollingerBandsPurePython (4)— pure-Python correctness
#   TestSupportResistancePurePython (2) — pure-Python correctness
#   TestCppExtensionBridge (7)      — C++ parity within 0.01
#   TestFallbackMechanism (3)       — graceful degradation
```

---

## 5. Phase 2 — FastAPI Bridge

**Files:** `api/server.py`, `api/routes/analyse.py`, `api/routes/history.py`, `api/routes/stream.py`

Thin FastAPI server wrapping the existing orchestrator. Agent logic is never modified —
the bridge only adds HTTP + WebSocket exposure.

### Endpoints

```
POST  /analyse              body: {"ticker": "MARUTI"}
                            → await orchestrator.analyse_async(ticker)
                            → returns FinalReport JSON

GET   /history/{ticker}     → ScoreStore().get_history(ticker)
GET   /history/{ticker}/latest → ScoreStore().get_latest(ticker)

WS    /ws/stream?ticker=MARUTI
                            → asyncio.Queue receives progress events from agents
                            → each event sent to WS client as JSON:
                              {"event": "agent_progress", "agent": "...", "score": 0.72}
                              {"event": "complete", "report": <FinalReport>}
                              {"event": "error", "detail": "..."}

GET   /health               → {"status": "ok"}
```

### Async dispatch detail

```
FastAPI receives POST /analyse
      │
      ▼
await orchestrator.analyse_async(ticker)
      │
      ▼
asyncio.to_thread(_resolve_ticker)      ← one sync LLM call, offloaded to thread
      │
      ▼
asyncio.gather(*[agent.run_async(q) for agent in _SUB_AGENTS])
  each agent:
    context  = await asyncio.to_thread(_gather_context)   ← yfinance/news offloaded
    raw_json = await AsyncOpenAI.chat.completions.create  ← true coroutine
      │
      ▼
dict[name → AgentOutput] → Signal Aggregator → FinalReport
```

### CORS

Allows origins: `localhost:3000` (TypeScript REST), `localhost:3001` (TypeScript WS),
`localhost:5000` (C# scheduler).

---

## 6. Phase 2b — Live Data Feeds

### ContextBuilder routing

**File:** `tools/context_builder.py`

```
ContextBuilder().build(agent_name, query)
      │
      ├── "sales_demand"       → news_fetcher (Serper + NewsAPI)
      │                           queries: FADA/SIAM, Vahan, dealer inventory…
      │
      ├── "raw_materials"      → macro_fetcher (steel, aluminium, rubber, crude)
      │                        + news_fetcher (commodities news)
      │
      ├── "fundamentals"       → fundamentals_fetcher (yfinance quarterly P&L)
      │                        + news_fetcher (earnings, FII flow…)
      │
      ├── "pattern_analysis"   → yfinance_fetcher (OHLCV, RSI/MACD/BB,
      │                          support/resistance, seasonal, Nifty Auto correlation)
      │
      ├── "sentiment"          → news_fetcher (news NLP, earnings call, Reddit…)
      │
      ├── "policy_regulatory"  → tavily_fetcher (full-page policy articles)
      │                        + news_fetcher (FAME, PLI, emission norms…)
      │
      ├── "competitive_intel"  → news_fetcher (EV share, model launches, JVs…)
      │
      └── "risk_macro"         → macro_fetcher (INR/USD, crude, steel/aluminium…)
                               + news_fetcher (RBI, emission norms, China supply…)
```

**Why not give every agent all data?** Token limits. Each agent gets ~2048 tokens for
its response. Stuffing irrelevant data wastes tokens and dilutes the signal.

### yfinance_fetcher — technical indicator dispatch

```
compute_rsi(close_series)
      │
      ├── _USE_CPP=True  → _cpp_indicators.compute_rsi(prices_list, period)
      │                     C++: EWM adjust=True, matches pandas within 0.01
      │
      └── _USE_CPP=False → pandas EWM: gain.ewm(com=period-1).mean() / loss.ewm(...)

compute_macd(close_series)
      ├── _USE_CPP=True  → _cpp_indicators.compute_macd(prices_list, 12, 26, 9)
      └── _USE_CPP=False → close.ewm(span=fast, adjust=False).mean() − slow EMA

compute_bollinger_bands(close_series)
      ├── _USE_CPP=True  → _cpp_indicators.compute_bollinger_bands(prices_list, 20, 2.0)
      └── _USE_CPP=False → rolling(20).mean() ± 2 × rolling(20).std()
```

---

## 7. Phase 3 — TypeScript Dashboard

**Files:** `typescript/src/`

TypeScript never imports Python code. It calls Python FastAPI via HTTP/WS only.

### Architecture

```
Browser / external client
      │
      ├── POST localhost:3000/api/analyse
      │         ↓
      │     routes/analyse.ts
      │         ↓
      │     pythonClient.postAnalyse(ticker)
      │         ↓  axios POST, timeout=180s
      │     POST localhost:8000/analyse
      │         ↓
      │     FinalReport JSON  ←──────────────────
      │
      ├── GET localhost:3000/api/history/:ticker
      │         ↓  proxies to GET :8000/history/:ticker
      │
      ├── GET localhost:3000/api/schedule
      │         ↓  proxies to GET :5000/scheduler/status
      │
      └── WS  localhost:3001?ticker=MARUTI
                ↓
            wsHub.ts — getOrCreateHub(ticker)
                ↓
            Upstream WS: ws://localhost:8000/ws/stream?ticker=MARUTI
                ↓
            Every message rebroadcast to all subscribers for that ticker
            {"event": "agent_progress", "agent": "fundamentals", "score": 0.68}
            {"event": "complete", "report": <FinalReport>}
```

### WS hub detail

```
wsHub.ts — per-ticker upstream management
      │
      ├── Client connects: ws://localhost:3001?ticker=MARUTI
      ├── Hub checks: is there an open upstream WS for MARUTI?
      │     NO  → new WebSocket("ws://localhost:8000/ws/stream?ticker=MARUTI")
      │           hubs.set("MARUTI", { upstream, clients: Set<WebSocket> })
      │     YES → reuse existing upstream
      │
      ├── upstream.on("message") → for each client in hub.clients → client.send(payload)
      │
      ├── upstream.on("close") → send {event:"error", detail:"upstream disconnected"}
      │                           hubs.delete("MARUTI")
      │
      └── client.on("close") → hub.clients.delete(client)
```

### TypeScript types (mirror Python FinalReport)

```typescript
// typescript/src/types/stockAgent.ts
interface FinalReport {
  ticker: string;
  company_name: string;
  final_score: number;          // [0.0, 1.0]
  verdict: Verdict;             // "STRONG BUY" | "BUY" | "NEUTRAL" | "SELL" | "STRONG SELL"
  weighted_agent_scores: Record<string, WeightedAgentScore>;
  conviction_drivers: string[];
  top_risks: string[];
  investment_thesis: string;
  report_date: string;          // ISO date
}

type StreamEvent = ProgressEvent | CompleteEvent | ErrorEvent;
```

---

## 8. Phase 4 — C# Quartz Scheduler

**Files:** `csharp/StockAgent.Scheduler/`

The C# service runs independently on port 5000. It calls Python FastAPI to trigger analyses
and persists results to SQL Server. Python's `score_store.py` proxies writes to C# when
`CSHARP_SCHEDULER_ENABLED=true`.

### AnalyseJob flow (Quartz.NET)

```
Quartz trigger fires: cron "0 30 8 ? * MON-FRI" (8:30am IST weekdays)
      │
      ▼
AnalyseJob.Execute(context)
  For each ticker in appsettings Scheduler:Tickers:
      │
      ├── 1. POST http://localhost:8000/analyse  {"ticker": "MARUTI"}
      │         Polly retry: 3 attempts, exponential back-off (2s, 4s, 8s)
      │         Deserialise response → FinalReportDto
      │
      ├── 2. ScoreRecord.FromDto(dto) → _db.ScoreRecords.Add(record)
      │         await _db.SaveChangesAsync()   [SQL Server via EF Core]
      │
      └── 3. CheckAndFireAlert(ticker, latest, previous)
              if |latest.FinalScore - previous.FinalScore| >= threshold
                  OR latest.Verdict != previous.Verdict:
                  → log warning
                  → POST webhookUrl (if configured)
```

### C# API endpoints

```
GET  /health
     → { "status": "ok", "service": "StockAgent.Scheduler", "next_fire_utc": "..." }

GET  /scheduler/status
     → { "enabled": true, "cron": "0 30 8 ? * MON-FRI",
          "tickers": [...], "next_fire": "..." }

POST /scores          body: FinalReport JSON (snake_case)
     → ScoreRecord.FromDto(dto) → EF Core INSERT → 201 {"id": 42}

GET  /scores/{ticker}
     → last 30 runs for ticker (newest first)

GET  /scores/{ticker}/latest
     → most recent run
```

### Python ↔ C# proxy in `score_store.py`

```python
def save(self, report: FinalReport) -> int:
    if settings.CSHARP_SCHEDULER_ENABLED:
        try:
            requests.post(f"{settings.CSHARP_API_URL}/scores",
                         json=report.model_dump(), timeout=10)
        except Exception as exc:
            logger.warning("[ScoreStore] C# proxy failed (%s) — continuing", exc)
        return -1
    # Default: SQLite path (unchanged)
    ...
```

### Cron equivalence

| Python APScheduler | C# Quartz.NET |
|---|---|
| `30 8 * * 1-5` | `0 30 8 ? * MON-FRI` |
| min hour dom month dow | sec min hour dom month dow |
| Both fire at 8:30am IST weekdays |

### EF Core entity

```
ScoreRecords table (SQL Server)
  Id             INT IDENTITY PK
  Ticker         NVARCHAR(20)
  CompanyName    NVARCHAR(200)
  RunAt          DATETIME2
  FinalScore     DECIMAL(5,4)
  Verdict        NVARCHAR(20)
  InvestmentThesis NVARCHAR(MAX)
  ReportJson     NVARCHAR(MAX)   ← full FinalReport JSON for audit trail
  INDEX: (Ticker, RunAt DESC)
```

### Build & run

```bash
cd csharp/StockAgent.Scheduler
dotnet build
dotnet run
# Applies EF Core migrations on first startup
# Quartz scheduler starts automatically
```

---

## 9. RAG Pipeline

### Document ingestion

**Triggered by:** `python scripts/ingest_documents.py`

```
DocumentIngester.ingest_directory(path, metadata)
      │
      ▼
For each .pdf / .txt / .md:
  PDF → pypdf.PdfReader → text
  TXT → pathlib.Path.read_text()
      │
      ▼
_chunk_text(text, chunk_size=512, overlap=64)
  overlapping windows preserve context at boundaries
      │
      ▼
Embedder.embed_batch(chunks)  ← sentence-transformers, runs locally
      │
      ▼
VectorStore.upsert(ids, documents, embeddings, metadatas)
  → ChromaDB PersistentClient → data/chroma_db/
  → metadata: source, ticker, doc_type, chunk_index
  → deterministic MD5 IDs → re-ingestion is idempotent
```

### Retrieval at runtime

```
_rag_retrieve(query) in base_agent.py  [when RAG_ENABLED=true]
      │
      ▼
Embedder.embed(search_query) → single vector
      │
      ▼
VectorStore.query(embedding, n_results=5, where={"ticker": "MARUTI"})
  → ChromaDB cosine similarity → top-K chunks
  → filters chunks below SIMILARITY_THRESHOLD (0.75)
      │
      ▼ [optional] RERANKER_ENABLED=true
CrossEncoder.predict([(query, chunk) for chunk in chunks])
  → re-orders by reranker score (higher precision)
      │
      ▼
chunks joined with "---" → context string → agent prompt
```

---

## 10. Python Scheduler & Alerting

### Scheduled run flow

**File:** `tools/scheduler.py` (APScheduler — active when `CSHARP_SCHEDULER_ENABLED=false`)

```
python scripts/run_schedule.py start
      │
      ▼
BlockingScheduler(timezone="Asia/Kolkata")
CronTrigger: SCHEDULER_CRON="30 8 * * 1-5"
      │
      │  (every weekday at 8:30am IST)
      ▼
_scheduled_job() → for each ticker in SCHEDULER_TICKERS:
      │
      ├── AutomobileAgentOrchestrator().analyse(ticker) → FinalReport
      ├── ScoreStore.save(report)  → SQLite (or C# proxy if flag set)
      └── AlertManager.check_and_alert(report, store)
```

### Alert logic

```
AlertManager.check_and_alert(report, store)
      │
      ├── previous = None?
      │     → Alert: "new_ticker" (severity: info)
      │
      ├── |score_delta| ≥ ALERT_SCORE_CHANGE_THRESHOLD (0.10)?
      │     → Alert: "score_change"
      │       severity: "warning" if delta < 0.20
      │                 "critical" if delta ≥ 0.20
      │
      └── verdict_changed AND ALERT_ON_VERDICT_CHANGE=true?
            → Alert: "verdict_change" (severity: warning/critical)

For each alert → dispatch to ALERT_CHANNELS:
  console → stdout
  file    → outputs/alerts.log
  webhook → HTTP POST (Slack/Discord compatible)
```

---

## 11. Configuration Hierarchy

```
.env file  (highest priority)
      │ overrides
      ▼
config/settings.py  (typed defaults)
      │ imported by
      ▼
All agents, tools, api/, scripts/

config/rag_config.py  (RAG-specific namespace)
      │ read by
      ▼
tools/rag/*, agents/base_agent.py

prompts/<agent>.py  ← NOT config — editable without code changes
      │ templates used by
      ▼
Each agent's _build_prompt()
```

**Rule:** Never hardcode values in agent or tool files. All tunable values live in
`config/settings.py`. Environment variables always win so CI/CD can override without
touching files.

---

## 12. Error Handling & Fallbacks

The system is designed so **no single failure can kill the pipeline**.

```
Failure Point                     │ What happens
──────────────────────────────────┼──────────────────────────────────────────────
Ticker resolution LLM fail         │ Raw input used as ticker directly
C++ extension absent               │ _USE_CPP=False → pure-Python indicator path
Context: RAG fails                 │ Falls back to Phase 2 live data
Context: live data fails           │ Falls back to minimal stub string
Agent LLM: rate limit / timeout   │ Retry with exponential back-off (3 attempts)
Agent LLM: all retries fail        │ AgentOutput(overall_score=0.5, error in key_risks)
Agent JSON parse fail              │ Same — neutral fallback score
Any agent: uncaught exception     │ Caught in orchestrator → neutral AgentOutput
Signal Aggregator JSON fail       │ FinalReport(score=0.5, verdict=NEUTRAL)
FastAPI /ws/stream upstream close  │ WS hub sends error event to subscribers
C# proxy (score_store.save)        │ Logged as warning → pipeline continues without persistence
APScheduler: one ticker fails      │ Error logged, next ticker proceeds
Alert: webhook fails               │ Logged as error, other channels still fire
ScoreStore: DB locked (SQLite)     │ 5s retry timeout (SQLite default)
```

**Why neutral (0.5) as fallback?**
0.5 is the most conservative position — neither buy nor sell. It minimises the risk of a
crashed agent producing a false signal.

---

## 13. Full System Data Flow Diagram

```
                     ┌───────────────────────────────────────────────┐
                     │              USER / TRIGGER                    │
                     │  CLI: python main.py MARUTI                   │
                     │  TypeScript: POST localhost:3000/api/analyse  │
                     │  C# Quartz: 8:30am IST → POST :8000/analyse  │
                     └────────────────────┬──────────────────────────┘
                                          │
                                          ▼
                     ┌───────────────────────────────────────────────┐
                     │         FastAPI Bridge  (port 8000)           │
                     │  POST /analyse → analyse_async(ticker)        │
                     │  GET  /history/{ticker}                       │
                     │  WS   /ws/stream?ticker=...                   │
                     └────────────────────┬──────────────────────────┘
                                          │
                     ┌────────────────────▼──────────────────────────┐
                     │     AutomobileAgentOrchestrator               │
                     │  1. Resolve ticker (LLM, temp=0.0)           │
                     │  2. Dispatch 8 agents (asyncio.gather)        │
                     └──────────────────────────────────────────────┘
          │                │            │             │             │
          ▼                ▼            ▼             ▼             ▼
  ┌───────────────┐ ┌─────────────┐ ┌──────────┐ ┌────────┐ ┌──────────┐
  │ C++ Extension │ │ yfinance    │ │ Serper / │ │ Tavily │ │ ChromaDB │
  │ stockindic-   │ │ OHLCV, P&L, │ │ NewsAPI  │ │ (policy│ │ (if RAG  │
  │ ators.pyd     │ │ macro/FX    │ │ news     │ │  agent)│ │ enabled) │
  │ RSI/MACD/BB   │ └─────────────┘ └──────────┘ └────────┘ └──────────┘
  └───────────────┘        │              │
         │                 └──────────────┴─── context strings ───────────┐
         │                                                                  │
         └─── via yfinance_fetcher.py (_USE_CPP dispatch) ────────────────┘
                                                                            │
           ┌──────────────────────────────────────────────────────────────┘
           │
           ▼   (context injected into each agent's LLM prompt)
  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
  │ Sales    │ │ Raw      │ │ Funda-   │ │ Pattern  │ │ Sentiment│ │ Policy   │ │ Compet.  │ │ Risk &   │
  │ Demand   │ │ Materials│ │ mentals  │ │ Analysis │ │  (0.04)  │ │ Reg.     │ │ Intel    │ │ Macro    │
  │ (0.18)   │ │ (0.10)   │ │ (0.20)   │ │ (0.13)   │ │          │ │ (0.10)   │ │ (0.10)   │ │ (0.15)   │
  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘
       │             │            │             │            │            │            │            │
       └─────────────┴────────────┴─────────────┴────────────┴────────────┴────────────┴────────────┘
                                                      │
                                                      ▼  (8 AgentOutput objects)
                                         ┌────────────────────────────┐
                                         │      Signal Aggregator     │
                                         │  1. Apply weights          │
                                         │  2. Detect conflicts       │
                                         │  3. LLM resolution (Qwen)  │
                                         │  4. Map score → verdict    │
                                         └──────────────┬─────────────┘
                                                        │  FinalReport
                              ┌─────────────────────────┼───────────────────────────┐
                              │                         │                           │
                              ▼                         ▼                           ▼
                  ┌───────────────────┐    ┌────────────────────────┐  ┌──────────────────────┐
                  │  CLI / stdout     │    │  ScoreStore.save()     │  │  WS /ws/stream       │
                  │  JSON / Markdown  │    │                        │  │  progress events     │
                  │  report           │    │  CSHARP_ENABLED=false: │  │  + complete event    │
                  └───────────────────┘    │    SQLite data/scores.db│  │  → TypeScript hub   │
                                          │  CSHARP_ENABLED=true:  │  │    rebroadcasts     │
                                          │    POST :5000/scores   │  └──────────────────────┘
                                          │    → SQL Server (EF)   │
                                          └───────────┬────────────┘
                                                      │
                                                      ▼
                                          ┌───────────────────────┐
                                          │  AlertManager         │
                                          │  score delta / verdict│
                                          │  → console/file/webhook│
                                          └───────────────────────┘
```

---

## 14. Scoring & Verdict Logic

### Per-agent scoring

Each agent asks the LLM to score 5 specific dimensions on 0.0–1.0, then provide an
`overall_score`. The LLM is not constrained to average the sub-scores — it weights
dimensions contextually.

```
Example — Pattern Analysis scoring MARUTI:

  Dimension               LLM reasoning                    Score
  ──────────────────────────────────────────────────────────────
  price_cycle_position   Mid-cycle, not extended            0.62
  seasonal_pattern       Q2/Q3 festive tailwind upcoming    0.72
  rsi_macd_bb            RSI=58, MACD bullish crossover     0.65
  breakout_support_zone  8% from resistance, 3% above sup   0.55
  peer_correlation       Beta=1.2, Nifty Auto trending up   0.60

  overall_score = 0.63  (LLM-assessed, not a simple average)
```

### Weighted fusion

```
composite = Σ(agent_score × weight) / Σ(weights)

Example:
  sales_demand     0.72 × 0.18 = 0.130
  raw_materials    0.60 × 0.10 = 0.060
  fundamentals     0.68 × 0.20 = 0.136
  pattern_analysis 0.63 × 0.13 = 0.082
  sentiment        0.70 × 0.04 = 0.028
  policy_reg.      0.65 × 0.10 = 0.065
  comp_intel       0.62 × 0.10 = 0.062
  risk_macro       0.58 × 0.15 = 0.087
                               ──────────
  composite = 0.650 / 1.00 = 0.650
```

### Verdict mapping

```
Score Range    Verdict        Meaning
──────────────────────────────────────────────────────
0.75 – 1.00    STRONG BUY    Strong across all dimensions
0.55 – 0.75    BUY           Majority positive signals
0.40 – 0.55    NEUTRAL       Mixed or uncertain signals
0.20 – 0.40    SELL          Majority negative signals
0.00 – 0.20    STRONG SELL   Weakness across all dimensions
```

The Signal Aggregator LLM may adjust the score after conflict resolution. The final verdict
is derived from the confirmed score, not the raw composite.

---

## 15. File Responsibility Map

```
WHAT YOU WANT TO CHANGE                 WHERE TO CHANGE IT
──────────────────────────────────────── ──────────────────────────────────────────
LLM model                               config/settings.py → LLM_MODEL (OpenRouter slug)
LLM provider (OpenRouter endpoint)      config/settings.py → OPENROUTER_BASE_URL
Agent weights                           config/settings.py → AGENT_WEIGHTS
Score → verdict thresholds             config/settings.py → SCORE_THRESHOLDS
RSI / MACD / BB parameters             config/settings.py → RSI_PERIOD, MACD_*, BB_*
Cron schedule (Python)                 .env → SCHEDULER_CRON
Cron schedule (C#)                     csharp/.../appsettings.json → Scheduler:CronExpression
Tickers to schedule                    .env → SCHEDULER_TICKERS
What a specific agent analyses         prompts/<agent>.py → ANALYSIS_PROMPT
News sources                           config/settings.py → NEWS_SOURCES
Enable RAG                             .env → RAG_ENABLED=true
Enable C# scheduler                    .env → CSHARP_SCHEDULER_ENABLED=true
Add Slack alerts                       .env → ALERT_CHANNELS=console,file,webhook
                                              ALERT_WEBHOOK_URL=https://hooks.slack.com/…
Change alert sensitivity               .env → ALERT_SCORE_CHANGE_THRESHOLD
Add new agent sub-score dimension      prompts/<agent>.py + agents/<agent>.py
                                       + models/schemas.py (new SubScores field)
Add a new sub-agent                    New files in all three dirs above
                                       + register in orchestrator.py _SUB_AGENTS
Rebuild C++ indicators                 powershell -File cpp/build_ext.ps1
Index documents into RAG               python scripts/ingest_documents.py --dir …
Run pipeline immediately               python scripts/run_schedule.py run-now
View score trends                      python scripts/run_schedule.py history --ticker MARUTI
Check TypeScript types                 cd typescript && npm run typecheck
Start all services                     See Quick Start in README.md
```

---

## Multi-Language Entry Points (all phases complete)

```
Language        Entry point                              Port    Status
───────────────────────────────────────────────────────────────────────
Python CLI      python main.py MARUTI                   —       ✅ Complete
Python FastAPI  uvicorn api.server:app --port 8000      8000    ✅ Complete
Python Sched.   python scripts/run_schedule.py start    —       ✅ Complete
C++ extension   cpp/build_ext.ps1 → stockindicators.pyd —       ✅ Live (_USE_CPP=True)
TypeScript REST npm run dev (typescript/)               3000    ✅ Scaffolded
TypeScript WS   (same process, separate HTTP server)    3001    ✅ Scaffolded
C# Scheduler    dotnet run (csharp/StockAgent.Scheduler) 5000   ✅ Scaffolded
```

All routes ultimately call `AutomobileAgentOrchestrator` on the Python side.
The FastAPI bridge at port 8000 is the single integration point for TypeScript and C#.

**Test baseline:** 292 Python tests passing (0 failed) | TypeScript: `tsc --noEmit` clean

*Last updated: 2026-04-17 | All 4 integration phases complete*
