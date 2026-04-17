# Automobile Agent — Complete System Flow

> This document explains the full logical flow of every component:
> what runs, in what order, why each step exists, and how data moves
> through the system from user input to investment verdict.

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Entry Points](#2-entry-points)
3. [Phase 1 — Core Agent Pipeline](#3-phase-1--core-agent-pipeline)
   - 3.1 Ticker Resolution
   - 3.2 Context Assembly
   - 3.3 Parallel Agent Execution
   - 3.4 Per-Agent Internal Flow
   - 3.5 Signal Aggregation
   - 3.6 Output
4. [Phase 2 — Live Data Feeds](#4-phase-2--live-data-feeds)
   - 4.1 ContextBuilder Routing
   - 4.2 Per-Agent Data Sources
5. [Phase 3 — RAG Pipeline](#5-phase-3--rag-pipeline)
   - 5.1 Document Ingestion
   - 5.2 Retrieval at Runtime
6. [Phase 4 — Scheduler & Alerting](#6-phase-4--scheduler--alerting)
   - 6.1 Scheduled Run Flow
   - 6.2 Score Persistence
   - 6.3 Alert Logic
7. [Configuration Hierarchy](#7-configuration-hierarchy)
8. [Error Handling & Fallbacks](#8-error-handling--fallbacks)
9. [Data Flow Diagram (Full System)](#9-data-flow-diagram-full-system)
10. [Decision Logic — Scoring & Verdicts](#10-decision-logic--scoring--verdicts)
11. [File Responsibility Map](#11-file-responsibility-map)

---

## 1. System Overview

The Automobile Agent is a **multi-agent LLM pipeline** that analyses
Indian NSE/BSE automobile stocks by breaking the problem into five
specialist viewpoints, running them in parallel, then fusing the
results into a single investment score and verdict.

**Why multi-agent?**
A single LLM prompt asking "should I buy MARUTI?" produces shallow,
generic output. Splitting the problem into specialist agents forces
depth in each dimension: a fundamentals agent cannot take shortcuts
on technicals, and vice versa. The Signal Aggregator then synthesises
all five views — including resolving conflicts between them.

**Core principle:**
```
Specialisation → Parallelism → Conflict-Aware Fusion → Verdict
```

---

## 2. Entry Points

There are three ways to trigger the pipeline:

```
┌─────────────────────────────────────────────────────────────┐
│                       ENTRY POINTS                          │
├─────────────────┬──────────────────┬────────────────────────┤
│  One-off CLI    │ Scheduled Daemon │  Direct Python Call    │
│                 │                  │                        │
│  python main.py │  python scripts/ │  from agents.orchestr- │
│  MARUTI         │  run_schedule.py │  ator import Automob-  │
│  --output json  │  start           │  ileAgentOrchestrator  │
│                 │                  │  report = orch.analyse │
│  ↓              │  ↓               │  ("MARUTI")            │
│  main.py        │  scheduler.py    │  ↓                     │
│  parses args    │  triggers job    │  orchestrator.py       │
│  ↓              │  ↓               │                        │
│         AutomobileAgentOrchestrator.analyse(input)          │
└─────────────────────────────────────────────────────────────┘
```

All three paths converge at `AutomobileAgentOrchestrator.analyse()`.

---

## 3. Phase 1 — Core Agent Pipeline

### 3.1 Ticker Resolution

**File:** `agents/orchestrator.py` → `_resolve_ticker()`

**Why it exists:**
Users may type "Maruti", "maruti suzuki", or "MARUTI". The system must
normalise this to a canonical NSE ticker before any analysis can start.

```
User input: "Maruti Suzuki"
      │
      ▼
LLM call (OpenRouter/Qwen, temperature=0.0 for determinism)
  Prompt: TICKER_RESOLUTION_PROMPT (from prompts/orchestrator.py)
  Known ticker table embedded in prompt
      │
      ▼
JSON response: { "ticker": "MARUTI", "company_name": "Maruti Suzuki India Ltd",
                 "exchange": "NSE", "confidence": 0.99 }
      │
      ▼
StockQuery object created (Pydantic, ticker auto-uppercased)
      │
  ┌───┴────────────────────────────────────┐
  │  Fallback: if LLM call fails,          │
  │  treat raw input as ticker directly    │
  │  e.g. "MARUTI" → StockQuery(ticker=   │
  │  "MARUTI", company_name="MARUTI")      │
  └────────────────────────────────────────┘
```

**Logical reasoning:** Using temperature=0.0 for resolution (not analysis)
ensures the ticker mapping is deterministic. Confidence score allows
future code to reject low-confidence resolutions.

---

### 3.2 Context Assembly

**File:** `agents/base_agent.py` → `_gather_context()`

Before calling the LLM with an analysis prompt, each agent needs
*context* — real-world data about the stock. The context system has
a priority chain:

```
_gather_context(query) called by each agent
      │
      ▼ Check 1: Is RAG_ENABLED=true?
      ├── YES → _rag_retrieve(query)
      │         ↓
      │         RAGRetriever.retrieve(search_query)
      │         → top-K chunks from ChromaDB
      │         → concatenated text string
      │
      ├── NO  → ContextBuilder().build(agent_name, query)
      │         ↓ (Phase 2 live data)
      │         Routes to agent-specific fetcher
      │         → formatted data string
      │
      └── FALLBACK (both fail) → minimal stub string
          "Stock: MARUTI | Date: 2026-04-03
           Note: Live data unavailable."
```

**Why this layered approach?**
- RAG provides *your own documents* (earnings transcripts, etc.) — highest quality
- Phase 2 provides real-time market data — always fresh
- Stub ensures the pipeline never crashes — agents still reason from LLM training knowledge

---

### 3.3 Parallel Agent Execution

**File:** `agents/orchestrator.py` → `_run_agents_parallel()`

```
StockQuery
      │
      ▼
ThreadPoolExecutor(max_workers=8)
      │
      ├──► SalesDemandAgent.run(query)       ──┐
      ├──► RawMaterialsAgent.run(query)      ──┤
      ├──► FundamentalsAgent.run(query)      ──┤
      ├──► PatternAnalysisAgent.run(query)   ──┤──► as_completed()
      ├──► SentimentAgent.run(query)         ──┤    collects results
      ├──► PolicyRegulatoryAgent.run(query)  ──┤
      ├──► CompetitiveIntelAgent.run(query)  ──┤
      └──► RiskMacroAgent.run(query)         ──┘
                                                │
                                                ▼
                               dict[agent_name → AgentOutput]
```

**Why parallel?**
Each agent makes one LLM API call (~1-3 seconds). Sequential execution
would take 8-24 seconds. Parallel execution takes ~max(all agents)
≈ 3-5 seconds. This matters for user experience and scheduled runs.

**Why ThreadPoolExecutor and not asyncio?**
The OpenAI SDK is synchronous. ThreadPoolExecutor lets us parallelise
blocking I/O calls without rewriting the SDK. For future async support,
swap to `asyncio.gather()` with an async OpenAI client.

**Timeout handling:**
`as_completed()` has a `timeout=AGENT_TIMEOUT_SECONDS` (default 120s).
If an agent exceeds this, it raises `TimeoutError` which is caught and
converted to a neutral fallback score (0.5). The pipeline always completes.

---

### 3.4 Per-Agent Internal Flow

Every sub-agent follows the same pattern (defined in `BaseAgent`):

```
agent.run(query)
      │
      ▼
1. _gather_context(query)
   → returns context string (RAG / live data / stub)
      │
      ▼
2. _build_prompt(query, context)
   → returns (system_prompt, user_prompt)
   → prompts read from prompts/<agent_name>.py
   → {ticker}, {company_name}, {context} placeholders filled
      │
      ▼
3. _call_llm_with_retry(system_prompt, user_prompt)
   → OpenRouter API call (via tools/llm_client.py)
   → response_format={"type": "json_object"} (forces valid JSON)
   → captures response.usage → logs tokens + cost to logs/agent_calls.jsonl
   → retry up to MAX_RETRIES=3 times on RateLimit/Timeout
   → exponential backoff between retries
      │
      ▼
4. _safe_parse(raw_json, ticker)
   → json.loads(raw)
   → _parse_output(data, ticker)  ← agent-specific, returns typed model
   → scores clamped to [0.0, 1.0] via _clamp()
      │
   ┌──┴────────────────────────────────────────┐
   │  On parse failure:                        │
   │  → _error_output() returns AgentOutput   │
   │    with overall_score=0.5 (neutral)       │
   │    and error message in key_risks         │
   └───────────────────────────────────────────┘
      │
      ▼
5. Returns AgentOutput (Pydantic model)
   Fields: overall_score, sub_scores (5 dimensions),
           key_positives, key_risks, summary, data_freshness
```

**Why JSON mode?**
LLMs sometimes produce markdown-wrapped JSON or trailing text.
`response_format={"type": "json_object"}` guarantees the response
is parseable JSON, eliminating the most common failure mode.

**Why clamp scores?**
LLMs occasionally return values like 0.85000000001 or -0.01 due to
floating point representation. Clamping is defensive, not restrictive.

---

### 3.5 Signal Aggregation

**File:** `agents/signal_aggregator.py`

```
dict[agent_name → AgentOutput]
      │
      ▼
Step 1: Weighted Score Computation
  For each agent:
    weighted = agent.overall_score × AGENT_WEIGHTS[agent]
  composite = sum(weighted) / sum(weights)   # normalised

  Weights (config/settings.py):
    sales_demand:     0.20  (demand is leading indicator)
    fundamentals:     0.25  (highest weight — P&L is ground truth)
    pattern_analysis: 0.20  (technical posture)
    sentiment:        0.15  (softer signal, more noise)
    risk_macro:       0.20  (macro headwinds can override all else)
      │
      ▼
Step 2: Conflict Detection
  For every pair of agents:
    if |score_A - score_B| >= 0.30:
      add to conflict_flags list
  Example: fundamentals=0.80, risk_macro=0.45 → conflict

  WHY 0.30 threshold?
  A 0.30 gap represents a meaningful disagreement (e.g., BUY vs NEUTRAL
  range). Smaller gaps are normal noise. Larger gaps need LLM resolution.
      │
      ▼
Step 3: LLM Resolution (AGGREGATION_PROMPT)
  Input to LLM:
    - All 5 agent scores with weights
    - Pre-computed composite score
    - List of detected conflicts
  LLM task:
    - Confirm or adjust the composite score
    - Resolve conflicts with a narrative explanation
    - Map score to verdict
    - Generate investment thesis
    - List top 3 conviction drivers + top 3 risks
      │
      ▼
Step 4: FinalReport construction (Pydantic)
  Fields:
    final_score          → 0.0–1.0
    verdict              → STRONG BUY / BUY / NEUTRAL / SELL / STRONG SELL
    weighted_agent_scores → breakdown per agent
    conflicts_resolved   → list of resolution narratives
    conviction_drivers   → top 3 reasons to invest
    top_risks            → top 3 risks
    investment_thesis    → 3-5 sentence paragraph
    agent_outputs        → full raw output from all 5 agents
```

**Why have the LLM resolve conflicts instead of a formula?**
A formula (e.g., discard outliers) loses information. When fundamentals
are bullish but macro is bearish, the right answer depends on *which*
one is more reliable *right now* — that requires reasoning, not arithmetic.
The LLM has the narrative context to make that judgement.

---

### 3.6 Output

**File:** `main.py` → `_format_json()` / `_format_markdown()`

```
FinalReport
      │
      ├── --output json     → report.model_dump_json(indent=2)
      │                        Pydantic serialises all fields to JSON
      │
      └── --output markdown → formatted table + thesis + bullets
                               verdict_emoji() maps score → emoji

      │
      ├── --save flag       → writes to outputs/{TICKER}_{DATE}.{ext}
      │
      └── printed to stdout
```

---

## 4. Phase 2 — Live Data Feeds

### 4.1 ContextBuilder Routing

**File:** `tools/context_builder.py`

The ContextBuilder is the single dispatcher that knows which data
each agent needs. It reads the agent name and calls the right fetchers.

```
ContextBuilder().build(agent_name, query)
      │
      ├── "sales_demand"        → news_fetcher (Serper × 3)
      │                           queries: FADA/SIAM, Vahan, dealer inventory...
      │
      ├── "raw_materials"       → macro_fetcher.get_raw_materials_context() (yfinance)
      │                           tickers: SLX, AA, PPLT, PALL, CL=F, BZ=F
      │                         + news_fetcher (Serper × 1: power tariff)
      │
      ├── "fundamentals"        → fundamentals_fetcher (yfinance quarterly P&L)
      │                         + news_fetcher (Serper × 2: earnings, market share)
      │
      ├── "pattern_analysis"    → yfinance_fetcher (OHLCV, RSI, MACD, BB,
      │                           support/resistance, seasonal, correlation)
      │                           [ZERO Serper calls — most API-efficient agent]
      │
      ├── "sentiment"           → news_fetcher (Serper × 3)
      │                           queries: news NLP, earnings call, Reddit...
      │
      ├── "policy_regulatory"   → tavily_fetcher (Tavily × 2, full page text)
      │                           queries: FAME III circular, BS7/CAFE standards
      │                         + news_fetcher (Serper × 3: budget, PLI, state EV)
      │
      ├── "competitive_intel"   → news_fetcher (Serper × 4)
      │                           queries: EV share, model launches, JV/M&A, ADAS
      │
      └── "risk_macro"          → macro_fetcher (INR/USD, crude, steel — yfinance)
                                + macro_cache check:
                                    HIT  → skip Serper × 3 (sector cached)
                                    MISS → news_fetcher (Serper × 3)
```

**Why not give every agent all data?**
Token limits. Each agent gets ~2048 tokens for its response. Stuffing
irrelevant data (e.g., RSI data into the Fundamentals agent) wastes
tokens and dilutes the signal. Specialisation applies to data too.

**Why Tavily only for Policy & Regulatory?**
FAME circulars and BS7/CAFE regulatory standards are published as dense
government documents. A 2-line Serper snippet misses the critical numbers
(disbursement amounts, compliance thresholds). Tavily's full-page extraction
costs 2 calls (22% of 1,000/month free tier) and materially improves
LLM scoring accuracy for this agent.

---

### 4.2 Per-Agent Data Sources

#### yfinance_fetcher (Pattern Analysis + Fundamentals)

```
get_price_history(ticker, years=10)
  → yf.download("MARUTI.NS", start, end)
  → pd.DataFrame [Open, High, Low, Close, Volume]

compute_technicals(df)
  → RSI(14):       momentum oscillator, >70=overbought, <30=oversold
  → MACD(12,26,9): trend direction + crossover signal
  → Bollinger(20): volatility bands + %B position
  → Support/Resistance: rolling min/max over 252 days
  → 52W High/Low distances

get_seasonal_pattern(df)
  → group monthly returns over full history
  → identify historically strong/weak months
  → WHY: festive season (Sep-Nov) is structurally bullish for Indian autos

get_peer_correlation(ticker, "^CNXAUTO")
  → Pearson correlation vs Nifty Auto index
  → Beta calculation (cov / var_index)
  → WHY: high-beta stocks amplify index moves; low-beta = defensive
```

#### fundamentals_fetcher (Fundamentals Agent)

```
get_financials(ticker)
  → yf.Ticker("MARUTI.NS").quarterly_income_stmt
  → Revenue + EBITDA (Operating Income proxy) for last 4 quarters
  → QoQ growth = (Q_now - Q_prev) / Q_prev × 100
  → YoY growth = (Q_now - Q_4ago) / Q_4ago × 100
  → EBITDA margin = EBITDA / Revenue × 100

get_shareholding(ticker)
  → yf.Ticker.info["heldPercentInstitutions"]
  → WHY: rising institutional holding = smart money accumulating
  → Limitation: yfinance combines FII+DII; no split available

get_company_info(ticker)
  → Market cap, P/E, P/B, employees, sector description
```

#### macro_fetcher (Risk & Macro Agent + Raw Materials Agent)

```
get_inr_usd_rate()          → yf.download("INR=X")
get_crude_oil_price()       → yf.download("CL=F")   [WTI futures]
get_commodity_prices()      → SLX (steel ETF), AA (aluminium proxy),
                               RBc1 (rubber futures if available)
get_raw_material_prices()   → SLX, AA, PPLT (platinum ETF), PALL (palladium ETF),
                               CL=F (WTI), BZ=F (Brent)
get_raw_materials_context() → formatted string for Raw Materials agent prompt
get_rbi_repo_rate()         → static dict (no yfinance feed for RBI)
                               → update manually or automate via RBI website scrape

WHY these commodities?
  Steel       → 60-70% of vehicle body weight; input cost driver
  Aluminium   → engine components, wheels; rising trend = margin pressure
  Platinum    → catalytic converters (ICE OEMs: Maruti, Bajaj, Hero)
  Palladium   → catalytic converters; supply concentrated in Russia/S.Africa
  Crude/Brent → polymer costs (bumpers, dashboards) + fuel price signal
  INR/USD     → export revenue (Bajaj, Hero export heavily) vs import cost
```

#### tavily_fetcher (Policy & Regulatory Agent)

```
search_tavily(query, max_results=2, search_depth="advanced")
  → POST https://api.tavily.com/search
  → Tavily visits each result URL, strips HTML, extracts readable text
  → Returns: title, content (~600 chars), url per result
  → WHY not Serper here: FAME circulars and BS7 standards are dense
    government documents — a 2-line snippet is insufficient

fetch_tavily_context(queries, max_queries=2)
  → Budget guard: max 2 calls (220/month for 110 analyses = 22% of 1,000 free)
  → Content truncated to 600 chars each to control token usage
  → Falls back gracefully if TAVILY_API_KEY not set (returns empty)
```

#### news_fetcher (Sales & Demand + Sentiment Agents)

```
search_serper(query, n=5)
  → POST https://google.serper.dev/search
  → Returns: title, snippet, link, date
  → WHY Serper over direct Google: structured JSON, no scraping

search_newsapi(query, n=5)
  → GET https://newsapi.org/v2/everything
  → Filters to NEWS_SOURCES: Reuters, ET, Bloomberg, Moneycontrol, LiveMint
  → WHY restrict sources: reduces noise from low-quality blogs

Fallback chain:
  Serper (if key set) → NewsAPI (if key set) → "[No results]" stub
  → Pipeline never crashes on missing API keys
```

---

## 5. Phase 3 — RAG Pipeline

### 5.1 Document Ingestion

**Triggered by:** `python scripts/ingest_documents.py`

```
User runs: python scripts/ingest_documents.py
           --dir data/earnings_transcripts
           --ticker MARUTI
           --doc-type earnings
      │
      ▼
DocumentIngester.ingest_directory(path, metadata)
      │
      ▼
For each .pdf / .txt / .md file:
      │
      ├── PDF → pypdf.PdfReader → extract text from all pages
      └── TXT → pathlib.Path.read_text()
      │
      ▼
_chunk_text(text, chunk_size=512, overlap=64)
  → split into word-approximate token chunks
  → overlapping windows preserve context at boundaries
  → WHY overlap: a sentence split across chunk boundaries
    should appear in both so retrieval doesn't miss it
      │
      ▼
_doc_id(text, source, chunk_index)
  → deterministic MD5-based ID
  → WHY deterministic: re-ingesting the same file is idempotent
    (ChromaDB upsert replaces existing ID)
      │
      ▼
Embedder.embed_batch(chunks)
  → sentence-transformers model (nomic-embed-text-v1.5)
  → runs locally, no API key
  → WHY local: speed, privacy, no per-token cost
  → model cached after first load (~90MB download once)
      │
      ▼
VectorStore.upsert(ids, documents, embeddings, metadatas)
  → ChromaDB PersistentClient → stores to data/chroma_db/
  → metadata includes: source, ticker, doc_type, chunk_index
  → WHY metadata: enables filtered retrieval (e.g., only MARUTI docs)
```

---

### 5.2 Retrieval at Runtime

**Triggered by:** `_rag_retrieve()` in `base_agent.py` when RAG_ENABLED=true

```
Agent needs context for MARUTI → fundamentals agent
      │
      ▼
Build search query from CONTEXT_SEARCH_QUERIES[:2] joined together
Example: "MARUTI quarterly results revenue EBITDA MARUTI margin EBITDA peers"
      │
      ▼
Embedder.embed(search_query)
  → single vector [0.12, -0.05, 0.88, ...]  (768 dimensions)
      │
      ▼
VectorStore.query(query_embedding, n_results=5, where={"ticker": "MARUTI"})
  → ChromaDB cosine similarity search
  → returns top-K chunks sorted by similarity
  → filters out chunks below SIMILARITY_THRESHOLD (0.75)
      │
      ▼ Optional: RERANKER_ENABLED=true
CrossEncoder.predict([(query, chunk1), (query, chunk2), ...])
  → re-scores with a cross-attention model (slower but more accurate)
  → re-orders results by reranker score
      │
      ▼
List of text chunks joined with "---" separator
  → returned as context string to the agent's prompt
      │
      ▼ If store is empty:
"No RAG documents found for MARUTI."
  → agent falls back to Phase 2 live data
```

**Why two-stage retrieval (embedding + reranker)?**
Embeddings are fast but approximate — they compare meaning in vector
space which misses fine-grained lexical matches. Cross-encoders read
query and document together, giving much higher precision. The two-stage
approach (embed for recall, rerank for precision) is the industry
standard for production RAG.

---

## 6. Phase 4 — Scheduler & Alerting

### 6.1 Scheduled Run Flow

**File:** `tools/scheduler.py`

```
python scripts/run_schedule.py start
      │
      ▼
AutomobileScheduler.__init__()
  → ScoreStore()  (opens/creates SQLite DB)
  → AlertManager()
  → BlockingScheduler(timezone="Asia/Kolkata")
  → CronTrigger parsed from SCHEDULER_CRON="30 8 * * 1-5"
      │
      ▼
scheduler.start()  → BLOCKS here
      │
      │  (every weekday at 8:30am IST)
      │
      ▼
_scheduled_job() fires
      │
      ▼
For each ticker in SCHEDULER_TICKERS:
  _run_single_ticker(ticker, store, alerter)
      │
      ├──► AutomobileAgentOrchestrator().analyse(ticker)
      │    → full pipeline (Phases 1+2+3 depending on config)
      │    → returns FinalReport
      │
      ├──► ScoreStore.save(report)
      │    → persists to SQLite
      │    → auto-prunes to SCORE_HISTORY_MAX_ROWS
      │
      └──► AlertManager.check_and_alert(report, store)
           → checks for score/verdict changes
           → dispatches to configured channels
```

**Why IST timezone?**
Indian markets open at 9:15am IST. Running at 8:30am gives time to
complete the analysis before market open — useful for pre-market decisions.

**Why APScheduler?**
Lightweight, pure Python, supports cron expressions with timezone
awareness. No message broker (Celery/Redis) needed. Sufficient for
a single-machine deployment running 5-10 tickers per day.

---

### 6.2 Score Persistence

**File:** `tools/score_store.py`

```
FinalReport (Pydantic)
      │
      ▼
ScoreStore.save(report)
      │
      ├── Inserts into score_history table:
      │     id, ticker, company_name, run_at (UTC ISO),
      │     final_score, verdict,
      │     agent_scores (JSON blob of all 5 weighted scores),
      │     investment_thesis, conviction_drivers, top_risks,
      │     report_json (full serialised FinalReport)
      │
      └── prune_old_records(ticker)
          → DELETE oldest rows where count > SCORE_HISTORY_MAX_ROWS
          → keeps DB from growing unbounded

Key queries:
  get_latest(ticker)   → most recent row (for delta comparison)
  get_previous(ticker) → second most recent row
  get_score_delta()    → latest.final_score - previous.final_score
  get_verdict_changed()→ latest.verdict != previous.verdict
  get_all_latest()     → most recent row per distinct ticker
  get_history(n)       → last N runs for trend analysis
```

**Why SQLite?**
Zero infrastructure. No PostgreSQL/MySQL server needed. SQLite handles
the write load (5-10 inserts per day easily). The full JSON of each
report is stored so you can reconstruct any historical FinalReport.

---

### 6.3 Alert Logic

**File:** `tools/alerting.py`

```
AlertManager.check_and_alert(report, store)
      │
      ▼
previous = store.get_previous(ticker)
      │
      ├── previous is None?
      │     → Alert type: "new_ticker", severity: "info"
      │     → "First run recorded. Score=0.70 Verdict=BUY"
      │
      ├── |score_delta| >= ALERT_SCORE_CHANGE_THRESHOLD (0.10)?
      │     → Alert type: "score_change"
      │     → severity: "warning" if delta < 0.20
      │                 "critical" if delta >= 0.20
      │     → Message: "Score ▲0.15 (0.60 → 0.75)"
      │
      └── verdict_changed AND ALERT_ON_VERDICT_CHANGE=true?
            → Alert type: "verdict_change"
            → severity: "warning"  for BUY↔NEUTRAL
                         "critical" for STRONG BUY/SELL involved
            → Message: "Verdict changed: BUY → NEUTRAL"

For each alert:
      │
      ▼
dispatch to ALERT_CHANNELS (console, file, webhook)

  console → print to stdout immediately
  file    → append line to ALERT_LOG_FILE (outputs/alerts.log)
  webhook → HTTP POST to ALERT_WEBHOOK_URL
            payload: Slack-compatible Block Kit JSON
            → works with Slack, Discord (set to Slack mode), or any webhook
```

**Why 0.10 as default threshold?**
A 10% score move represents a meaningful shift — roughly equivalent
to moving half a verdict tier (e.g., mid-BUY to low-BUY). Smaller
moves are noise from LLM variability. The threshold is configurable.

---

## 7. Configuration Hierarchy

```
.env file (highest priority)
      │  overrides
      ▼
config/settings.py (defaults + type annotations)
      │  imported by
      ▼
All agents, tools, scripts
      │
config/rag_config.py (separate namespace for RAG)
      │  read by
      ▼
tools/rag/*, agents/base_agent.py

prompts/<agent>.py  ← NOT config — but editable without code changes
      │  templates used by
      ▼
Each agent's _build_prompt()
```

**Rule:** Never hardcode values in agent or tool files. All tunable
values live in `config/settings.py` or `config/rag_config.py`.
Environment variables always win so CI/CD can override without
touching files.

---

## 8. Error Handling & Fallbacks

The system is designed so that **no single failure can kill the pipeline**.

```
Failure Point              │ What happens
───────────────────────────┼────────────────────────────────────────────────
Ticker resolution LLM fail │ Raw input used as ticker directly
Context: RAG fails          │ Falls back to Phase 2 live data
Context: live data fails    │ Falls back to minimal stub string
Agent LLM call: rate limit  │ Retry with exponential backoff (3 attempts)
Agent LLM call: timeout     │ Retry with same delay
Agent LLM call: total fail  │ AgentOutput with score=0.5, error in key_risks
Agent JSON parse fail       │ Same — neutral fallback score
Any agent: exception        │ Caught in orchestrator, neutral AgentOutput inserted
Signal Aggregator JSON fail │ FinalReport with score=0.5, verdict=NEUTRAL
Scheduler: one ticker fails │ Logged as error, next ticker proceeds
Alert: webhook fails        │ Logged as error, other channels still fire
ScoreStore: DB locked       │ SQLite retry (default 5s timeout)
```

**Why neutral (0.5) as fallback?**
0.5 is the most conservative position — neither buy nor sell. It
minimises the risk of a crashed agent producing a false signal.
The `error` field on `AgentOutput` makes failures visible in the report.

---

## 9. Data Flow Diagram (Full System)

```
                         ┌─────────────────────────────────┐
                         │       USER / SCHEDULER           │
                         │  "python main.py MARUTI"        │
                         │  or cron trigger at 8:30am IST  │
                         └──────────────┬──────────────────┘
                                        │
                                        ▼
                         ┌─────────────────────────────────┐
                         │    AutomobileAgentOrchestrator  │
                         │    1. Resolve ticker via LLM    │
                         │    2. Create StockQuery object  │
                         └──────────────┬──────────────────┘
                                        │
              ┌─────────────────────────┼─────────────────────────────┐
              │                         │                             │
              ▼                         ▼                             ▼
   ┌──────────────────┐    ┌──────────────────────┐    ┌─────────────────────┐
   │ Phase 2 Fetchers │    │  OpenRouter LLM API  │    │  Phase 3 ChromaDB   │
   │                  │    │  (Qwen 2.5 72B)      │    │  (if RAG_ENABLED)   │
   │ yfinance:        │    │                      │    │                     │
   │  OHLCV, P&L,     │    │  Routed via          │    │  Embedder queries   │
   │  shareholding,   │    │  llm_client.py       │    │  vector store for   │
   │  macro/FX        │    │  (OpenRouter only)   │    │  relevant chunks    │
   │                  │    │                      │    │                     │
   │ Serper/NewsAPI:  │    │  Tokens+cost logged  │    │                     │
   │  news articles   │    │  → agent_calls.jsonl │    │                     │
   └────────┬─────────┘    └──────────────────────┘    └──────────┬──────────┘
            │                         ▲                           │
            │                         │ prompts                   │
            └───────────context────────┴───────────context────────┘
                                      │
                    ┌─────────────────┼─────────────────┐
                    │                 │                  │
     ┌──────────────▼──┐  ┌──────────▼──────┐  ┌───────▼─────────────┐
     │ Sales & Demand  │  │  Fundamentals   │  │  Pattern Analysis   │
     │ Agent           │  │  Agent          │  │  Agent              │
     │ score: 0.0–1.0  │  │  score: 0.0–1.0 │  │  score: 0.0–1.0     │
     └────────┬────────┘  └───────┬─────────┘  └──────────┬──────────┘
              │                   │                        │
     ┌────────▼────────┐  ┌───────▼─────────┐
     │   Sentiment     │  │  Risk & Macro   │
     │   Agent         │  │  Agent          │
     │   score: 0.0–1.0│  │  score: 0.0–1.0 │
     └────────┬────────┘  └───────┬─────────┘
              │                   │
              └─────────┬─────────┘
                        │ all 5 AgentOutput objects
                        ▼
           ┌─────────────────────────────┐
           │      Signal Aggregator      │
           │  1. Apply weights           │
           │  2. Detect conflicts        │
           │  3. LLM resolution          │
           │  4. Map score → verdict     │
           └──────────────┬──────────────┘
                          │ FinalReport
                          ▼
           ┌─────────────────────────────┐
           │         Phase 4             │
           │  ScoreStore.save(report)    │  ← SQLite DB
           │  AlertManager.check(report) │  ← console/file/webhook
           └──────────────┬──────────────┘
                          │
                          ▼
                    Final Output
             JSON / Markdown report
             printed to stdout or saved
```

---

## 10. Decision Logic — Scoring & Verdicts

### How each agent scores

Each agent asks the LLM to score 5 specific dimensions on a 0.0–1.0 scale,
then provide an `overall_score`. The LLM is not constrained to average the
sub-scores — it can weight dimensions contextually.

```
Example — Pattern Analysis Agent scoring MARUTI:

  Dimension               LLM reasoning                    Score
  ──────────────────────────────────────────────────────────────
  price_cycle_position   Mid-cycle, not extended            0.62
  seasonal_pattern       Q2/Q3 festive tailwind upcoming    0.72
  rsi_macd_bb            RSI=58, MACD bullish crossover     0.65
  breakout_support_zone  8% from resistance, 3% above sup   0.55
  peer_correlation       Beta=1.2, Nifty Auto trending up   0.60

  overall_score = 0.63   (LLM-assessed, not a simple average)
```

### Weighted fusion

```
Final composite = Σ (agent_score × agent_weight) / Σ(weights)

Example (MARUTI):
  sales_demand       0.72 × 0.18 = 0.1296
  raw_materials      0.65 × 0.10 = 0.0650
  fundamentals       0.76 × 0.20 = 0.1520
  pattern_analysis   0.63 × 0.13 = 0.0819
  sentiment          0.58 × 0.04 = 0.0232
  policy_regulatory  0.71 × 0.10 = 0.0710
  competitive_intel  0.55 × 0.10 = 0.0550
  risk_macro         0.60 × 0.15 = 0.0900
                                 ──────────
  composite = 0.6677 / 1.00 = 0.668  → BUY
```

### Verdict mapping

```
Score Range    Verdict          Meaning
──────────────────────────────────────────────────────
0.75 – 1.00    STRONG BUY    Strong across all dimensions
0.55 – 0.75    BUY           Majority positive signals
0.40 – 0.55    NEUTRAL       Mixed or uncertain signals
0.20 – 0.40    SELL          Majority negative signals
0.00 – 0.20    STRONG SELL   Weakness across all dimensions
```

**Note:** The Signal Aggregator LLM may adjust the final score slightly
upward or downward after conflict resolution. The final verdict is
derived from the LLM-confirmed score, not the raw composite.

### Why fundamentals gets the highest weight (0.20)?

Fundamentals (revenue growth, EBITDA margins, FII flows) are the most
reliable predictor of medium-term stock performance in Indian markets.
Sales data is a leading indicator but can be noisy month-to-month.
Technical patterns are short-term. Sentiment is low-weight (0.04) — kept
for legacy compatibility but de-emphasised as social signal is noisy.
Raw materials, policy, and competitive intel are new dimensions each at
0.10 — meaningful but secondary to financial reality. Macro risk at 0.15
acknowledges that sector-level headwinds can override all company signals.

---

## 11. File Responsibility Map

```
WHAT YOU WANT TO CHANGE              WHERE TO CHANGE IT
──────────────────────────────────── ────────────────────────────
LLM model / provider                config/settings.py → LLM_MODEL (OpenRouter model ID)
View token/cost logs                logs/agent_calls.jsonl (plain Python, no external service)
Update cost rates for new model     config/settings.py → LLM_INPUT_COST_PER_M / LLM_OUTPUT_COST_PER_M
Add OpenRouter API key              .env → OPENROUTER_API_KEY
Add Serper API key                  .env → SERPER_API_KEY
Add Tavily API key                  .env → TAVILY_API_KEY
Change agent weights                config/settings.py → AGENT_WEIGHTS (8 keys, sum=1.0)
Change score → verdict thresholds  config/settings.py → SCORE_THRESHOLDS
Change cron schedule                .env → SCHEDULER_CRON
Add a new ticker to schedule        .env → SCHEDULER_TICKERS
Change what Sales agent analyses    prompts/sales_demand.py → ANALYSIS_PROMPT
Change Policy agent Tavily queries  prompts/policy_regulatory.py → TAVILY_SEARCH_QUERIES
Change Policy agent Serper queries  prompts/policy_regulatory.py → CONTEXT_SEARCH_QUERIES
Change news sources                 config/settings.py → NEWS_SOURCES
Change RSI period                   config/settings.py → RSI_PERIOD
Change macro cache TTL              .env → MACRO_CACHE_TTL_HOURS
Change micro loop frequency         .env → MICRO_CYCLES_PER_DAY
Add platinum/palladium tickers      config/settings.py → PLATINUM_TICKER, PALLADIUM_TICKER
Enable RAG                          .env → RAG_ENABLED=true
Change ChromaDB location            .env → CHROMA_PERSIST_DIR
Change embedding model              config/rag_config.py → EMBEDDING_MODEL
Add Slack alerts                    .env → ALERT_CHANNELS=console,file,webhook
                                          ALERT_WEBHOOK_URL=https://hooks.slack.com/...
Change alert sensitivity            .env → ALERT_SCORE_CHANGE_THRESHOLD
Add a new sub-agent dimension       prompts/<agent>.py + agents/<agent>.py
                                    + models/schemas.py (new SubScores field)
Add a new sub-agent entirely        New files in prompts/, agents/, models/schemas.py
                                    + context_builder.py (_build_<agent_name>)
                                    + orchestrator.py _SUB_AGENTS dict
Index new documents into RAG        python scripts/ingest_documents.py --dir ...
Run pipeline immediately            python scripts/run_schedule.py run-now
View score trends                   python scripts/run_schedule.py history --ticker MARUTI
```

---

*Last updated: 2026-04-12 | Phases 1–4 complete | 8 agents | LLM: OpenRouter (Qwen 2.5 72B) | Helicone observability + JSONL logging added | Phase 5 (Web UI) planned*
