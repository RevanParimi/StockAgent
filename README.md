# Automobile Agent

> AI-powered Indian automobile stock analyser using a multi-agent architecture.
> Built with Groq LLM, Pydantic v2, and asyncio parallel execution.

---

## What this project does

The **Automobile Agent** analyses any NSE/BSE-listed Indian automobile stock
and produces a structured **investment score + verdict** by running five
specialist AI sub-agents in parallel, then fusing their outputs in a
Signal Aggregator.

```
User Input (ticker / company name)
          │
          ▼
  AutomobileAgentOrchestrator
  (resolves ticker, dispatches agents in parallel)
          │
   ┌──────┼──────┬───────────────┬────────────┐
   ▼      ▼      ▼               ▼            ▼
Sales &  Fund-  Pattern      Sentiment   Risk &
Demand  amentals Analysis               Macro
   └──────┴──────┴───────────────┴────────────┘
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
| Sales & Demand | 20% | FADA/SIAM dispatch, EV Vahan data, dealer inventory, DGFT exports, used car price index |
| Fundamentals | 25% | Revenue/EBITDA delta, margin vs peers, order book, headcount, FII/DII flow |
| Pattern Analysis | 20% | 10-yr price cycle, seasonal patterns, RSI/MACD/BB, support/resistance, Nifty Auto correlation |
| Sentiment | 15% | News NLP, earnings call tone, Twitter/Reddit, YouTube spikes, dealer feedback |
| Risk & Macro | 20% | INR/USD/crude exposure, commodities, RBI repo rate, emission norms, China supply risk |

**Signal Aggregator** (0% own score) applies weights, detects conflicts
(score delta ≥ 0.30 between any two agents), asks the LLM to resolve them,
and emits a final verdict: `STRONG BUY / BUY / NEUTRAL / SELL / STRONG SELL`.

---

## Project Structure

```
automobile_agent/
├── config/
│   ├── settings.py          ← ALL static config: API keys, LLM, weights, scheduler, alerts
│   └── rag_config.py        ← RAG pipeline config (disabled by default)
├── prompts/
│   ├── sales_demand.py      ← System + analysis prompts for Sales & Demand agent
│   ├── fundamentals.py      ← Prompts for Fundamentals agent
│   ├── pattern_analysis.py  ← Prompts for Pattern Analysis agent
│   ├── sentiment.py         ← Prompts for Sentiment agent
│   ├── risk_macro.py        ← Prompts for Risk & Macro agent
│   ├── signal_aggregator.py ← Prompts for Signal Aggregator
│   └── orchestrator.py      ← Prompts for ticker resolution + error handling
├── agents/
│   ├── base_agent.py        ← Abstract base: Groq LLM caller, retry, context routing
│   ├── sales_demand.py      ← Sales & Demand sub-agent
│   ├── fundamentals.py      ← Fundamentals sub-agent
│   ├── pattern_analysis.py  ← Pattern Analysis sub-agent
│   ├── sentiment.py         ← Sentiment sub-agent
│   ├── risk_macro.py        ← Risk & Macro sub-agent
│   ├── signal_aggregator.py ← Weighted fusion + conflict resolution
│   └── orchestrator.py      ← Top-level dispatcher (parallel via ThreadPoolExecutor)
├── models/
│   └── schemas.py           ← All Pydantic v2 models (StockQuery, AgentOutput, FinalReport)
├── tools/
│   ├── yfinance_fetcher.py  ← OHLCV, RSI/MACD/BB, peer correlation (Phase 2)
│   ├── fundamentals_fetcher.py ← Quarterly P&L, margins, shareholding (Phase 2)
│   ├── news_fetcher.py      ← Serper + NewsAPI search (Phase 2)
│   ├── macro_fetcher.py     ← INR/USD, crude, commodities via yfinance (Phase 2)
│   ├── context_builder.py   ← Routes each agent to the right fetchers (Phase 2)
│   ├── score_store.py       ← SQLite historical score persistence (Phase 4)
│   ├── scheduler.py         ← APScheduler cron trigger + run dispatch (Phase 4)
│   ├── alerting.py          ← Score/verdict change alerts: console/file/webhook (Phase 4)
│   └── rag/
│       ├── embedder.py      ← sentence-transformers local embeddings (Phase 3)
│       ├── vector_store.py  ← ChromaDB CRUD wrapper (Phase 3)
│       ├── ingestion.py     ← PDF/TXT chunking + indexing (Phase 3)
│       └── retriever.py     ← Semantic search + optional reranking (Phase 3)
├── scripts/
│   ├── ingest_documents.py  ← CLI: index documents into ChromaDB (Phase 3)
│   └── run_schedule.py      ← CLI: start/run/status/history for scheduler (Phase 4)
├── tests/
│   ├── conftest.py
│   ├── test_config.py
│   ├── test_schemas.py
│   ├── test_agents_unit.py
│   ├── test_signal_aggregator.py
│   ├── test_orchestrator.py
│   ├── test_prompts.py
│   ├── test_data_fetchers.py ← Phase 2 fetcher tests
│   ├── test_rag.py           ← Phase 3 RAG tests
│   ├── test_scheduler.py     ← Phase 4 ScoreStore + AlertManager + Scheduler tests
│   └── TEST_DOCUMENTATION.md
├── data/                    ← SQLite DB + ChromaDB store + document dirs (git-ignored)
├── outputs/                 ← Saved reports + alert logs (git-ignored)
├── logs/                    ← Runtime logs (git-ignored)
├── main.py                  ← One-off CLI entry point
├── requirements.txt
├── .env.example
└── README.md
```

---

## Quick Start

### 1. Install dependencies

```bash
cd automobile_agent
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env and add your GROQ_API_KEY
```

### 3. Run analysis

```bash
# Analyse Maruti Suzuki (JSON output)
python main.py MARUTI

# Analyse Tata Motors with Markdown output
python main.py TATAMOTORS --output markdown

# Save report to outputs/ directory
python main.py BAJAJ-AUTO --output json --save

# List all supported tickers
python main.py --list-tickers
```

---

## Configuration Guide

All customisation lives in two files — **no code changes needed** for most adjustments.

### `config/settings.py`

| Variable | Default | Purpose |
|---|---|---|
| `GROQ_API_KEY` | env var | Groq API key |
| `LLM_MODEL` | `llama-3.3-70b-versatile` | Groq model ID |
| `LLM_TEMPERATURE` | `0.2` | LLM creativity (0 = deterministic) |
| `LLM_MAX_TOKENS` | `2048` | Max tokens per LLM response |
| `AGENT_WEIGHTS` | see file | Per-agent score weights (must sum to 1.0) |
| `SCORE_THRESHOLDS` | see file | Score → verdict mapping |
| `PRICE_HISTORY_YEARS` | `10` | Years of OHLCV for pattern analysis |
| `NEWS_SOURCES` | Reuters, ET, Bloomberg, ... | News sources for sentiment NLP |
| `MAX_RETRIES` | `3` | LLM call retry attempts |

### `config/rag_config.py`

Set `RAG_ENABLED=true` in `.env` to activate the RAG pipeline.
When disabled (default), agents use LLM training knowledge only.

| Variable | Default | Purpose |
|---|---|---|
| `RAG_ENABLED` | `false` | Master switch for RAG |
| `VECTOR_STORE_PROVIDER` | `chromadb` | chromadb / pinecone / qdrant |
| `TOP_K_RESULTS` | `5` | Chunks retrieved per query |
| `CHUNK_SIZE` | `512` | Token chunk size for indexing |

### Adding / changing prompts

Edit any file in `prompts/` — for example to change what the Sentiment agent
analyses, edit [prompts/sentiment.py](prompts/sentiment.py).
The `SYSTEM_PROMPT`, `ANALYSIS_PROMPT`, and `CONTEXT_SEARCH_QUERIES` are the
three things you'll want to customise.

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

The orchestrator also accepts free-form company names (e.g. "Tata Motors") —
it uses the LLM to resolve them to the correct ticker.

---

## Running Tests

```bash
# All tests (no API key needed — LLM is mocked)
pytest tests/ -v

# With coverage
pytest tests/ --cov=. --cov-report=term-missing -v

# Single module
pytest tests/test_config.py -v
```

See [tests/TEST_DOCUMENTATION.md](tests/TEST_DOCUMENTATION.md) for full details.

---

## Data Architecture

### Phase 1 — LLM knowledge only (done)
- No live data feeds
- Agents reason from LLM training knowledge
- Suitable for quick directional analysis

### Phase 2 — Live data feeds (done)

Each agent now receives real data via `tools/context_builder.py`:

| Agent | Data source | Tool file |
|---|---|---|
| Pattern Analysis | yfinance OHLCV, RSI/MACD/BB, peer correlation | [tools/yfinance_fetcher.py](tools/yfinance_fetcher.py) |
| Fundamentals | yfinance quarterly P&L, shareholding | [tools/fundamentals_fetcher.py](tools/fundamentals_fetcher.py) |
| Risk & Macro | yfinance: crude, INR/USD, steel, aluminium | [tools/macro_fetcher.py](tools/macro_fetcher.py) |
| Sales & Demand | Serper + NewsAPI news search | [tools/news_fetcher.py](tools/news_fetcher.py) |
| Sentiment | Serper + NewsAPI news search | [tools/news_fetcher.py](tools/news_fetcher.py) |

**API keys needed for Phase 2:**
- `GROQ_API_KEY` — required
- `SERPER_API_KEY` — optional (news search, get at serper.dev)
- `NEWSAPI_KEY` — optional (news articles, get at newsapi.org)
- yfinance / macro data — **no API key needed**

**Context priority (in `base_agent.py`):**
```
RAG (if enabled) → Live data (Phase 2) → Minimal stub fallback
```

### Phase 4 — Scheduled / Periodic Trigger (done)

Runs the full pipeline automatically on a cron schedule, stores all scores
in SQLite, and fires alerts when scores or verdicts change significantly.

```
tools/
  score_store.py   ← SQLite: save/query historical scores per ticker
  scheduler.py     ← APScheduler cron daemon + manual run-now
  alerting.py      ← Alert on score delta ≥ threshold or verdict change

scripts/
  run_schedule.py  ← CLI: start | run-now | status | history | latest
```

**Usage:**
```bash
# Run all configured tickers right now (no daemon needed)
python scripts/run_schedule.py run-now

# Start the persistent cron daemon (weekdays 8:30am IST by default)
# Requires SCHEDULER_ENABLED=true in .env
python scripts/run_schedule.py start

# Check database and next run time
python scripts/run_schedule.py status

# View score history for a ticker
python scripts/run_schedule.py history --ticker MARUTI --rows 20

# View latest score for every tracked ticker
python scripts/run_schedule.py latest
```

**Configurable in `config/settings.py`:**

| Variable | Default | Purpose |
|---|---|---|
| `SCHEDULER_ENABLED` | `false` | Master switch for the daemon |
| `SCHEDULER_CRON` | `30 8 * * 1-5` | Cron expression (IST timezone) |
| `SCHEDULER_TICKERS` | 5 major OEMs | Tickers to run each cycle |
| `SCORE_DB_PATH` | `data/scores.db` | SQLite database path |
| `ALERT_SCORE_CHANGE_THRESHOLD` | `0.10` | Min delta to fire a score alert |
| `ALERT_ON_VERDICT_CHANGE` | `true` | Alert when verdict changes |
| `ALERT_CHANNELS` | `console,file` | `console` / `file` / `webhook` |
| `ALERT_WEBHOOK_URL` | `` | Slack/Discord/custom webhook URL |
| `SCORE_HISTORY_MAX_ROWS` | `90` | Records retained per ticker |

### Phase 3 — RAG pipeline (done)

Indexes your own documents (earnings transcripts, annual reports, etc.)
into a local ChromaDB vector store for retrieval-augmented generation.

```
tools/rag/
  embedder.py      ← sentence-transformers (local, ~90MB download, no API key)
  vector_store.py  ← ChromaDB CRUD wrapper
  ingestion.py     ← PDF/TXT chunking + indexing pipeline
  retriever.py     ← semantic search + optional cross-encoder reranking

scripts/
  ingest_documents.py  ← CLI to index documents
```

**To activate RAG:**
```bash
# 1. Set flag
echo "RAG_ENABLED=true" >> .env

# 2. Create data directories
mkdir -p data/earnings_transcripts data/annual_reports data/sector_reports

# 3. Drop your PDFs/TXTs into those folders, then index:
python scripts/ingest_documents.py --ticker MARUTI --doc-type earnings

# 4. Run analysis — agents will now use your documents
python main.py MARUTI
```

**Configurable in `config/rag_config.py`:**

| Variable | Default | Purpose |
|---|---|---|
| `RAG_ENABLED` | `false` | Master switch |
| `EMBEDDING_MODEL` | `nomic-embed-text-v1.5` | sentence-transformer model |
| `CHROMA_PERSIST_DIR` | `data/chroma_db` | Where ChromaDB stores data |
| `TOP_K_RESULTS` | `5` | Chunks retrieved per query |
| `CHUNK_SIZE` | `512` | Tokens per chunk |
| `RERANKER_ENABLED` | `false` | Cross-encoder reranking |

---

## Key Design Decisions

1. **Separation of config, prompts, agents** — Changing what an agent analyses
   only requires editing its prompt file. Changing LLM or API keys only requires
   editing `config/settings.py` or `.env`. No agent code needs to change.

2. **Parallel execution** — All 5 sub-agents run concurrently via
   `ThreadPoolExecutor` in `orchestrator.py`. Total latency ≈ slowest agent,
   not sum of all agents.

3. **Graceful degradation** — If any agent fails (LLM error, parse error),
   it is replaced with a neutral (0.5) score. The pipeline always produces
   a final report.

4. **Pydantic v2 validation** — All LLM outputs are parsed into typed models.
   Score bounds (0.0–1.0) are enforced at the model layer.

5. **LLM JSON mode** — All Groq calls use `response_format={"type": "json_object"}`
   to reduce parse failures.

---

## Development Workflow

```bash
# Make a config change
edit config/settings.py

# Add / modify an agent's analysis logic
edit prompts/sentiment.py      # change what it looks for
# agents/sentiment.py only needs changing if output schema changes

# Run tests to confirm nothing broke
pytest tests/ -v

# Run end-to-end
python main.py MARUTI --output markdown
```

---

## Status

| Component | Status |
|---|---|
| Config & prompts | Done |
| Pydantic schemas | Done |
| BaseAgent + 5 sub-agents | Done |
| Signal Aggregator | Done |
| Orchestrator (parallel) | Done |
| CLI (main.py) | Done |
| Unit + integration tests | Done |
| Live data feeds (yfinance + Serper + NewsAPI) | Done (Phase 2) |
| RAG pipeline (ChromaDB + sentence-transformers) | Done (Phase 3) |
| Scheduled / periodic trigger + alerting | Done (Phase 4) |
| Web UI / dashboard | Planned (Phase 5) |

---

## LLM / Model

- **Provider:** [Groq](https://console.groq.com/)
- **Default model:** `llama-3.3-70b-versatile`
- **Playground:** https://console.groq.com/playground
- Change the model in `config/settings.py → LLM_MODEL` or set `LLM_MODEL=` in `.env`
