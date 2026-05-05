# Team Training Plan — Banking & Financial Services Stock Agent
> Based on the 17-agent architecture for NSE/BSE Indian Financial Services universe
> Date: April 2026

---

## What Is Already Built (Automobile Sector — Reuse Everything)

The repo already has a **complete, production-grade Automobile sector agent** that every team member must understand before building the Banking sector. All infrastructure is reusable.

| Component | Location | Status | Reuse for Banking |
|---|---|---|---|
| BaseAgent (abstract class) | `core/pipeline/base_agent.py` | ✅ Complete | Yes — extend this |
| Orchestrator | `core/pipeline/orchestrator.py` | ✅ Complete | Copy + adapt for BFSI |
| SignalAggregator | `core/pipeline/signal_aggregator.py` | ✅ Complete | Yes — plug in BFSI weights |
| RAG pipeline | `intelligence/rag/` | ✅ Complete | Yes — new collections per sector |
| RL workflows | `intelligence/rl/` | ✅ Complete | Yes — same feedback loop |
| FastAPI server | `services/api/` | ✅ Complete | Yes — add BFSI route |
| TypeScript gateway | `services/gateway/` | ✅ Scaffolded | Yes — add BFSI endpoints |
| C# scheduler | `services/csharp/` | ✅ Scaffolded | Yes — add BFSI tickers |
| Data fetchers | `services/data/fetchers/` | ✅ Complete | Extend for BFSI-specific data |
| Pydantic schemas | `core/schemas/` | ✅ Complete | Extend AgentOutput subtypes |
| Banking sector stub | `core/sectors/banking/` | 🔲 Empty stub | Build here |
| Banking graph stub | `graphs/banking_bfsi/` | 🔲 Stub | Wire here |

---

## Module 0 — Repo Orientation (Day 1, 2 hours)

**Goal:** Every team member can run the Automobile agent end-to-end before touching Banking.

### Step 1: Install and run

```bash
pip install -r requirements.txt
cp .env.example .env   # add OPENROUTER_API_KEY
python main.py MARUTI
```

### Step 2: Understand the data flow

```
main.py / FastAPI route
        ↓
AutomobileAgentOrchestrator.analyse("MARUTI")
        ↓ (resolves ticker via LLM)
_run_agents_parallel() — 9 agents via ThreadPoolExecutor
        ↓ (each agent: _gather_context → _build_prompt → LLM call → _parse_output)
SignalAggregator.run() — weighted fusion + conflict resolution
        ↓
FinalReport (score 0–1, verdict, thesis, per-agent breakdown)
```

### Step 3: Read these files in order

1. `core/schemas/pipeline.py` — understand `StockQuery`, `AgentOutput`, `FinalReport`
2. `core/pipeline/base_agent.py` — the template every agent follows
3. `core/sectors/automobile/sales_demand.py` — a real agent implementation
4. `core/pipeline/signal_aggregator.py` — how scores are fused
5. `docs/CODEBASE.md` — authoritative module map

---

## Module 1 — Architecture Deep Dive (Week 1)

### The 17-Agent Banking Architecture

The Banking/BFSI system is **17 specialist agents** (vs 9 for Automobile). All follow the same BaseAgent pattern.

#### 8 Signal Layers

| Layer | Agents | Key metrics |
|---|---|---|
| Universe & data | 01 | 726 stocks, index weights, peer grouping, AMFI holdings |
| Macro & regulatory | 02, 15 | Repo rate, CRR, SEBI rules, IRDA norms, RBI/SEBI events |
| Fundamental / CAMELS | 03, 04, 09, 10 | NPA, NIM, CRAR, ROE, CASA, CD ratio, ALM mismatch |
| Qualitative & governance | 11, 12 | Promoter pledge, CEO exits, competitive positioning |
| News & sentiment | 06, 08 | NLP sentiment, G-Sec yields, real estate health, global contagion |
| Technical & market | 05, 07, 13, 14 | TA indicators, MF/FII flows, P/B vs ROE, F&O microstructure |
| Insurance-specific | 16 | EV, VNB, VNB margin, persistency, claims ratio, solvency |
| AMC & wealth | 17 | AUM growth, SIP flows, fee compression, market share |

#### 4 Output Streams

| Stream | Time horizon | Key output fields |
|---|---|---|
| Intraday | Same-day | Entry, stop, target, lot size, valid-till, max loss |
| Swing | 2–10 days | Direction + conviction, T1/T2, strike & expiry, overnight risk |
| Positional | Weeks–months | Buy/Accumulate/Exit, conviction H/M/L, portfolio % |
| MF rotation | Monthly | Increase/reduce SIP, fund switch, PSU vs private rotation |

#### Conflict Resolution Rules (built into SignalAggregator)

| Condition | Action |
|---|---|
| Fundamentals ↑ + Technicals ↓ | Mixed — reduce position size |
| News very negative + Fundamentals strong | Hold — wait for clarity |
| F&O OI bearish + Price bullish | Caution — smaller position |
| All agents aligned | High conviction — full size |

---

## Module 2 — Building a Banking Agent (Week 2)

### How to create a new BFSI agent (follow the automobile pattern)

**File location:** `core/sectors/banking/<agent_name>.py`

Every agent must:
1. Inherit from `BaseAgent`
2. Implement `agent_name` property
3. Implement `sector` property → return `"banking_bfsi"`
4. Implement `_build_prompt(query, context)` → `(system_prompt, user_prompt)`
5. Implement `_parse_output(data, ticker)` → `AgentOutput`

### Skeleton

```python
# core/sectors/banking/credit_quality.py
from core.pipeline.base_agent import BaseAgent
from core.schemas.pipeline import AgentOutput, StockQuery

class CreditQualityAgent(BaseAgent):

    @property
    def agent_name(self) -> str:
        return "credit_quality"

    @property
    def sector(self) -> str:
        return "banking_bfsi"

    def _build_prompt(self, query: StockQuery, context: str) -> tuple[str, str]:
        system = """You are a CAMELS framework analyst specialising in Indian banks and NBFCs.
        Analyse GNPA, NNPA, PCR, slippage ratio, SMA buckets, restructured book, and net credit cost.
        Score from 0.0 (severe stress) to 1.0 (pristine quality). Return JSON only."""
        user = f"Stock: {query.ticker}\nContext:\n{context}"
        return system, user

    def _parse_output(self, data: dict, ticker: str) -> AgentOutput:
        return AgentOutput(
            agent=self.agent_name,
            ticker=ticker,
            overall_score=self._clamp(data.get("score", 0.5)),
            key_positives=data.get("positives", []),
            key_risks=data.get("risks", []),
            summary=data.get("summary", ""),
        )
```

### Build order for Banking agents (priority sequence)

| Priority | Agent | File | Why first |
|---|---|---|---|
| 1 | Universe tracker | `universe_tracker.py` | All others depend on the stock list |
| 2 | Technical analysis | `technical_analysis.py` | yfinance data available immediately |
| 3 | News & sentiment | `news_sentiment.py` | Demonstrates NLP pipeline |
| 4 | Credit quality | `credit_quality.py` | Core bank signal, CAMELS layer |
| 5 | Macro & regulatory | `macro_regulatory.py` | Affects entire sector |
| 6 | Profitability | `profitability.py` | NIM, ROE, CASA — quarterly data |
| 7 | Capital adequacy | `capital_adequacy.py` | CRAR, Tier 1/2 |
| 8 | Liquidity & funding | `liquidity_funding.py` | CD ratio, LCR, ALM |
| 9 | F&O microstructure | `fo_microstructure.py` | BankNifty/FinNifty OI, PCR |
| 10 | Valuation & strength | `valuation_strength.py` | P/B vs ROE, sector relative perf |
| 11 | MF & institutional | `mf_institutional.py` | FII/DII/MF holding changes |
| 12 | Event & catalyst | `event_catalyst.py` | Earnings calendar, M&A, ratings |
| 13 | Management & governance | `management_governance.py` | Pledging, CEO exits, penalties |
| 14 | Competitive positioning | `competitive_intel.py` | Market share, fintech disruption |
| 15 | Cross-market impact | `cross_market.py` | G-Sec yields, real estate, MSME |
| 16 | Insurance signals | `insurance_signals.py` | EV, VNB, persistency |
| 17 | AMC & wealth signals | `amc_wealth.py` | AUM, SIP flows, fee compression |

---

## Module 3 — Data Architecture (Week 3)

The existing data fetchers (`services/data/fetchers/`) handle fundamentals, news, and macro. For Banking/BFSI these need to be extended.

### 5 Data Categories

#### 1. Market Data
- **Real-time**: Fyers API (free with account) or TrueData (Rs. 2,500/mo)
- **Historical**: Fyers gives 5yr daily + 1yr intraday free
- **Options chain**: NSE via Fyers/Angel One API (for Agent 14)
- **What exists**: `tools/yfinance_fetcher.py` — extend for NSE-specific data

#### 2. Fundamental Data (BFSI-specific)
| Signal | Source | Agent |
|---|---|---|
| GNPA, NNPA, NIM, CRAR, CASA | Screener.in API + NSE EDGAR | 03, 04, 09, 10 |
| Embedded Value, VNB margin | Company BSE filings | 16 |
| AUM, SIP flows | AMFI (free monthly) | 17 |
| RBI sector aggregates | RBI website scraper | 02 |
| FII/DII daily flows | NSE data | 07 |

#### 3. News & Sentiment Data
- NewsAPI (existing `tools/news_fetcher.py`) + Serper (existing `tools/tavily_fetcher.py`)
- Add: RBI/SEBI circular scrapers, Moneycontrol scraper for BFSI news

#### 4. F&O Data (new — not in Automobile)
| Data | Source | Agent |
|---|---|---|
| Options chain (OI, IV, strikes) | NSE via broker API | 14 |
| PCR, max pain, FII derivatives | NSE India website | 14 |
| BankNifty/FinNifty basis | NSE | 14 |

#### 5. RAG Knowledge Base
Extend `intelligence/rag/` with BFSI-specific collections:

| Collection | Content | Refresh |
|---|---|---|
| `bfsi_earnings_calls` | Quarterly earnings transcripts | Quarterly |
| `bfsi_rbi_circulars` | RBI policy circulars | As published |
| `bfsi_sebi_irda_filings` | Regulatory filings | As published |
| `bfsi_past_analyses` | Every signal the system generates | Continuous |
| `bfsi_analyst_reports` | Broker research | Weekly |

---

## Module 4 — RAG Integration (Week 4)

The RAG pipeline is already built at `intelligence/rag/`. Banking agents need BFSI-specific retrieval queries.

### How BaseAgent uses RAG (already wired)

```python
# base_agent.py — _gather_context() already does this:
if rag_config.RAG_ENABLED:
    return self._rag_retrieve(query), True
# Falls back to live data if RAG fails
```

### Adding BFSI retrieval queries

Each banking agent needs a `CONTEXT_SEARCH_QUERIES` list in its prompt module:

```python
# prompts/banking/credit_quality.py
CONTEXT_SEARCH_QUERIES = [
    "{ticker} GNPA NNPA slippage ratio {quarter}",
    "{ticker} credit quality NPA trend {year}",
    "{company_name} provisioning coverage ratio restructured book",
]
```

The `BaseAgent._rag_retrieve()` method already reads these — just add the prompt module.

### Chunking strategy for BFSI documents

| Document type | Chunk size | Overlap |
|---|---|---|
| Earnings call transcripts | 500 tokens | 50 tokens |
| RBI/SEBI circulars | 300 tokens | 30 tokens |
| AMFI monthly portfolio | 200 tokens | 20 tokens |
| Past agent analyses | Full (< 500 tokens) | None |

---

## Module 5 — RL Feedback Loop (Week 5)

The RL pipeline is already built at `intelligence/rl/`. The concept: track signal direction vs actual outcome, feed back as reward to improve aggregator weights.

### What exists
- `intelligence/rl/workflows/daily_review.py` — runs every day at 11am IST
- `intelligence/rl/workflows/generate_forecast.py` — generates predictions with learned weights
- `services/data/stores/score_store.py` — persists scores for trend tracking

### Reward function for BFSI signals

| Outcome | Reward |
|---|---|
| Signal direction correct + target hit | +1.0 |
| Signal direction correct + partial target | +0.5 |
| Signal neutral, no movement | 0.0 |
| Signal direction wrong, small loss | −0.5 |
| Signal direction wrong, stop hit | −1.0 |

### RL phases (don't skip phase 1)

| Phase | When | What |
|---|---|---|
| Phase 1 | First 3 months | Just log every signal + outcome. No RL yet. |
| Phase 2 | Months 4–6 | Contextual Bandit — per stock+timeframe weight vector |
| Phase 3 | 6+ months | PPO/A3C — full sequential decision making |

**Key rule:** RL is useless without outcome data. Start logging signals immediately, even before the BFSI agents are fully built.

---

## Module 6 — Wiring the Banking Orchestrator (Week 6)

### What to build in `core/sectors/banking/`

```
core/sectors/banking/
├── agents.py          ← Import all 17 agents + define AGENTS dict + WEIGHTS dict
├── graph.py           ← LangGraph wiring (mirrors automobile/graph.py)
├── credit_quality.py
├── profitability.py
├── technical_analysis.py
├── news_sentiment.py
├── macro_regulatory.py
├── capital_adequacy.py
├── liquidity_funding.py
├── fo_microstructure.py
├── valuation_strength.py
├── mf_institutional.py
├── event_catalyst.py
├── management_governance.py
├── competitive_intel.py
├── cross_market.py
├── insurance_signals.py
├── amc_wealth.py
└── universe_tracker.py
```

### BFSI-specific orchestrator

The orchestrator in `core/pipeline/orchestrator.py` currently imports only Automobile agents. Add a BFSI orchestrator (follow exact same pattern):

```python
# core/pipeline/bfsi_orchestrator.py
from core.sectors.banking.agents import AGENTS as BFSI_AGENTS

class BFSIAgentOrchestrator:
    # Same structure as AutomobileAgentOrchestrator
    # Just swap _SUB_AGENTS to BFSI_AGENTS
    # Add institution_type detection (bank / nbfc / insurance / amc / hfc / mfi / exchange)
    # Apply institution-type-aware weights before aggregation
```

### Institution-type weight routing

This is BFSI-specific. The same stock (e.g., SBI Life) needs different agent weights than a bank:

```python
INSTITUTION_WEIGHTS = {
    "bank":      {"credit_quality": 0.20, "profitability": 0.18, "capital_adequacy": 0.15, ...},
    "nbfc":      {"credit_quality": 0.18, "profitability": 0.15, "liquidity_funding": 0.18, ...},
    "insurance": {"insurance_signals": 0.30, "capital_adequacy": 0.15, ...},
    "amc":       {"amc_wealth": 0.35, "competitive_intel": 0.20, ...},
    "hfc":       {"credit_quality": 0.20, "liquidity_funding": 0.20, ...},
}
```

---

## Module 7 — Infrastructure & Cost (Week 7)

### Tech stack (already decided by the repo)

| Layer | Tech | Where |
|---|---|---|
| Agents + orchestrator | Python 3.11+ | `core/` |
| LLM | OpenRouter / Qwen (swap to Claude Sonnet 4.6 for production) | `config/settings/base.py` |
| Vector store | ChromaDB | `intelligence/rag/` |
| Database | SQLite → PostgreSQL + TimescaleDB | `services/data/stores/` |
| API | FastAPI | `services/api/` |
| Gateway | TypeScript + Bun + Hono | `services/gateway/` |
| Scheduler | TypeScript cron (analysis) + Python APScheduler (RL) | `services/scheduler/` |
| Frontend | React + Vite | `frontend/` |
| Cloud | AWS Mumbai (ap-south-1) | Phase 2+ |

### Phase costs

| Phase | What | Monthly cost |
|---|---|---|
| Phase 1 — Research only | All 17 agents, RAG, manual signal tracking | Rs. 8,000–12,000 |
| Phase 2 — Semi-automated | + Broker API, Telegram alerts, group approval | Rs. 13,000–18,000 |
| Phase 3 — Fully automated | + HA AWS, Claude Sonnet, SEBI algo registration | Rs. 35,000–45,000 |

Per person (10 people): Phase 1 = **Rs. 800–1,200/month**.

### LLM migration (important)

The repo currently uses OpenRouter/Qwen. For BFSI production, switch to Claude Sonnet 4.6:

```python
# config/settings/base.py
LLM_MODEL = "claude-sonnet-4-6"  # was qwen/qwen3-235b-a22b
```

Claude gives better structured JSON output, better domain reasoning for financial text, and prompt caching (saves ~60% on repeated system prompts across 17 agents).

---

## Module 8 — Build Milestones

### Phase 1 — Foundation (Weeks 1–3)
- [ ] All team members run Automobile agent end-to-end
- [ ] Read and understand: `base_agent.py`, `orchestrator.py`, `signal_aggregator.py`
- [ ] Data pipeline: yfinance + Screener.in + NewsAPI for BFSI stocks working
- [ ] Agent 01 (Universe tracker) + Agent 05 (Technical) producing scores
- [ ] RAG: BFSI collections created, earnings transcripts ingested

**Gate:** Two banking agents (technical + credit quality) backtested against 3 months of data.

### Phase 2 — All 17 Agents (Weeks 4–7)
- [ ] All 17 agents implemented and scoring
- [ ] BFSI orchestrator dispatching agents in parallel
- [ ] Institution-type weight routing working
- [ ] SignalAggregator producing all 4 output streams
- [ ] All signals logged to database (critical for RL)
- [ ] Telegram bot delivering signals to group

**Gate:** 30 days of forward-tested signals with manual outcome tracking.

### Phase 3 — RAG + RL (Weeks 8–10)
- [ ] RAG context injection working for all 17 agents
- [ ] RL contextual bandit training on logged outcomes
- [ ] Aggregator weights auto-updating
- [ ] Signal accuracy metrics dashboard

**Gate:** RL model demonstrating measurable improvement over fixed weights.

### Phase 4 — Production (Week 11+)
- [ ] Broker API connected (Fyers or Angel One)
- [ ] Risk management engine (max daily loss, kill switch)
- [ ] HA infrastructure on AWS Mumbai
- [ ] SEBI algo registration via broker

---

## Key Principles

1. **Reuse, don't rewrite** — The Automobile sector built everything you need. Copy `core/sectors/automobile/` as a template for every Banking agent.
2. **Log everything from day 1** — RL needs outcome data. Start logging signals immediately.
3. **Score before you trade** — Run 60 days of forward testing manually before connecting any broker.
4. **Institution-type weighting is the differentiator** — An insurance stock needs Agent 16 weighted 3x more than a bank. This is what makes BFSI analysis better than a generic tool.
5. **RAG quality > agent count** — 10 agents with excellent RAG context beat 17 agents with stale prompts.
6. **Claude Sonnet 4.6 for production** — Swap from Qwen for better JSON fidelity, financial reasoning, and prompt caching.
