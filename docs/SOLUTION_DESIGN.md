# Automobile Agent — Solution Design

> ⚠️ **PATH NOTE:** All `agents/`, `models/`, `prompts/`, `tools/` paths in this document are
> compatibility shims. Real implementations live under `core/`, `services/`, `config/`.
> See `docs/CODEBASE.md` for the authoritative module map.
> Agent count is now **9** (valuation_catalyst added). Orchestrator = `core/pipeline/orchestrator.py`.

> Internal reference document.

---

## 8. Target Architecture vs Implementation — Full Mapping

Based on `automobile_agent_tree.txt`.

Legend: `✓` built  ·  `~` partial  ·  `○` not yet wired

```
AUTOMOBILE AGENT
│   Orchestrator: AutomobileAgentOrchestrator in agents/orchestrator.py      ✓ built
│   Trigger: SCHEDULER_ENABLED / CLI (main.py)                               ✓ built
│   Parallel dispatch: ThreadPoolExecutor (5 workers)                         ✓ built
│   Micro search loop: micro_search_loop() in main.py                        ✓ built
│
├── Sales & Demand Agent  (agents/sales_demand.py)                           ✓ built
│   │   Context: fetch_news_context() via ContextBuilder._build_sales_demand()
│   │   Serper calls per run: up to SERPER_MAX_QUERIES (default 3)
│   │
│   ├── FADA monthly retail dispatch            ~ Serper search proxy
│   │     Built: "{ticker} FADA monthly retail sales {month} {year}"
│   │     Gap: no direct FADA API — Serper fetches news about FADA data
│   │     Discuss: scrape fada.in/news/monthly-reports for structured dispatch numbers
│   │
│   ├── SIAM dispatch data                      ~ Serper search proxy
│   │     Built: "{ticker} SIAM dispatch data {year}"
│   │     Gap: SIAM API is private — search proxy only
│   │
│   ├── EV segment — Vahan registration data    ~ Serper search proxy
│   │     Built: "{ticker} EV registration Vahan {year}"
│   │     Gap: Vahan dashboard (vahan.parivahan.gov.in) has structured data but
│   │     no official API. Scraping is the only path.
│   │     Discuss: add as a direct fetcher (vahan_fetcher.py) — 2-day effort.
│   │
│   ├── Dealer inventory channel check          ~ Serper search proxy
│   │     Built: "{company_name} dealer inventory channel check"
│   │     Gap: no structured source — analyst reports only
│   │
│   ├── Export/Import — DGFT data               ~ Serper search proxy
│   │     Built: "India automobile export {ticker} DGFT {year}"
│   │     Gap: DGFT (dgft.gov.in) has downloadable data but no API
│   │
│   └── Used car price index — Cars24/CarDekho  ~ Serper search proxy
│         Built: "used car price index Cars24 CarDekho {year}"
│         URLs configured: CARS24_PRICE_URL, CARDEKHO_PRICE_URL in settings.py
│         Gap: no structured API — search proxy only
│         Discuss: CarDekho has unofficial endpoints — evaluate scraping legality
│
├── Fundamentals Agent  (agents/fundamentals.py)                             ✓ built
│   │   Context: fundamentals_fetcher.py (yfinance) + news_fetcher (Serper)
│   │   Serper calls per run: up to SERPER_MAX_QUERIES (default 3)
│   │
│   ├── Revenue & EBITDA — QoQ / YoY delta      ~ yfinance snapshot only
│   │     Built: get_fundamentals_context() → P/E, revenue, EBITDA via yfinance
│   │     Gap: yfinance financials endpoint unreliable for NSE — returns annual
│   │     snapshots, not delta metrics. No QoQ comparison.
│   │     Discuss: screener.in has structured quarterly data — scraping is the
│   │     only free path. Evaluate Tickertape API as a paid alternative.
│   │
│   ├── Margin vs sector peers                  ~ Serper search proxy
│   │     Built: "{ticker} margin EBITDA comparison peers {year}"
│   │     Gap: peer margin data needs multi-ticker fetch + normalisation
│   │     Discuss: build peer basket (MARUTI, TATAMOTORS, M&M, BAJAJ-AUTO),
│   │     fetch via yfinance, compute margin delta. ~1 day effort, zero cost.
│   │
│   ├── Deal wins & order book pipeline         ~ Serper search proxy
│   │     Built: "{company_name} order book pipeline deal wins {year}"
│   │     Gap: deal data is in press releases — unstructured
│   │
│   ├── Attrition & headcount at OEMs           ~ Serper search proxy
│   │     Built: "{company_name} headcount attrition employees {year}"
│   │     Gap: LinkedIn blocks scraping; official data in annual reports only
│   │
│   └── Promoter holding & FII/DII flow         ~ Serper search proxy
│         Built: "{ticker} promoter shareholding FII DII {quarter} {year}"
│         Gap: NSE publishes shareholding quarterly — changes slowly
│         Discuss: pull once per quarter, store as slow signal in score DB.
│         This is a free yfinance field: ticker.institutional_holders
│
├── Pattern Analysis Agent  (agents/pattern_analysis.py)                     ✓ built
│   │   Context: yfinance_fetcher.py only — ZERO Serper calls
│   │   This agent is the most API-efficient in the system.
│   │
│   ├── 10-yr price history cycle detection     ✓ yfinance period="10y"
│   │     Built: get_technical_context() fetches 10yr OHLCV via yfinance
│   │
│   ├── RSI / MACD / BB periodic refresh        ✓ computed from yfinance data
│   │     Built: RSI, MACD, Bollinger Bands in yfinance_fetcher.py
│   │     Config: RSI_PERIOD, MACD_FAST/SLOW/SIGNAL, BB_PERIOD/STD in settings.py
│   │
│   ├── Breakout / support zone mapping         ✓ computed from yfinance data
│   │     Built: support/resistance levels derived from 52w high/low + recent closes
│   │
│   ├── Seasonal sales pattern — quarterly      ~ Serper queries defined, not fetched
│   │     Built: CONTEXT_SEARCH_QUERIES defined but ContextBuilder uses yfinance only
│   │     Gap: seasonal pattern needs historical quarterly sales data, not news
│   │     Discuss: FADA dispatch history → CSV storage → seasonal index computation
│   │
│   └── Peer correlation — Nifty Auto vs stock  ~ Nifty Auto ticker configured
│         Built: NIFTY_AUTO_TICKER = "^CNXAUTO" in settings.py
│         Gap: correlation not computed in yfinance_fetcher.py yet
│         Discuss: ~10 lines with yfinance multi-ticker fetch + df.corr(). Free.
│
├── Sentiment Agent  (agents/sentiment.py)                                   ✓ built
│   │   Context: fetch_news_context() via ContextBuilder._build_sentiment()
│   │   Serper calls per run: up to SERPER_MAX_QUERIES (default 3)
│   │
│   │   OVERLAP NOTE: sentiment query 1 "{company_name} news sentiment {month} {year}"
│   │   has topical overlap with fundamentals query 1 "{ticker} quarterly results...".
│   │   These are stock-specific (different per ticker) so cannot be deduplicated via cache.
│   │   The overlap is at the topic level only — both consume recent news about the same company.
│   │
│   ├── News NLP — Reuters / ET / Bloomberg     ~ Serper search proxy
│   │     Built: fetch_news_context() with news source filter (NEWS_SOURCES in settings)
│   │     Gap: no direct Reuters/Bloomberg API — Serper fetches their published articles
│   │
│   ├── Management tone — earnings call NLP     ~ Serper search proxy
│   │     Built: "{ticker} earnings call transcript management tone {quarter} {year}"
│   │     Gap: no transcript source — Serper fetches summaries only, not full transcripts
│   │     Discuss: Tickertape / Screener have earnings call summaries. Tavily/Serper
│   │     search is a reasonable proxy for POC signal validation.
│   │
│   ├── Twitter / Reddit consumer sentiment     ~ Serper search proxy
│   │     Built: "{company_name} Twitter Reddit investor sentiment {year}"
│   │     Gap: Twitter API v2 free tier + Reddit PRAW available — not wired
│   │     Discuss: r/IndianStockMarket + r/Nifty are high-signal for retail mood.
│   │     Twitter Bearer Token already configured in settings.py (TWITTER_BEARER_TOKEN)
│   │
│   ├── YouTube review view spikes              ~ Serper search proxy
│   │     Built: "{company_name} new model launch YouTube reviews views {year}"
│   │     Gap: YouTube Data API v3 (free) can return view counts — not wired
│   │     Discuss: model launch view spike = early demand signal. ~1 day effort.
│   │
│   └── Dealer / consumer feedback signals      ~ Serper search proxy
│         Built: "{company_name} dealer consumer feedback complaints {year}"
│         Gap: no structured source — Serper fetches news articles about complaints
│
├── Risk & Macro Agent  (agents/risk_macro.py)                               ✓ built
│   │   Context: macro_fetcher.py (yfinance, free) + news_fetcher (Serper, cached)
│   │   Serper calls: 3 on cache MISS → 0 on cache HIT (saved by micro_search_loop)
│   │
│   │   CACHE NOTE: All 3 Serper queries for risk_macro are sector-level, not
│   │   per-stock. The micro search loop pre-fetches this context with a 2h TTL.
│   │   When the cache is fresh, risk_macro uses cached text and makes 0 Serper calls.
│   │
│   ├── INR/USD & crude oil revenue exposure    ✓ yfinance (free, always fresh)
│   │     Built: get_inr_usd_rate(), get_crude_oil_price() via macro_fetcher.py
│   │     Tickers: INR=X (INR/USD), CL=F (WTI crude)
│   │
│   ├── Steel / Aluminium / Rubber prices       ✓ yfinance (free, always fresh)
│   │     Built: get_commodity_prices() → SLX (steel ETF), AA (Alcoa/aluminium proxy)
│   │     Gap: rubber (TOCOM) unreliable on yfinance — graceful skip implemented
│   │
│   ├── RBI repo rate & EMI impact              ~ static value (manually updated)
│   │     Built: get_rbi_repo_rate() returns hardcoded value with a "static" note
│   │     Gap: no RBI API. Static value needs manual update after each MPC decision.
│   │     Discuss: scrape rbi.org.in press releases — low-frequency, justified effort.
│   │     Alternatively: add as micro search query 3 (RBI MPC decision updates).
│   │
│   ├── Emission norms & BS6 CAFE policy risk   ~ Serper search proxy (cached)
│   │     Built: "India emission norms BS6 CAFE {company_name} compliance {year}"
│   │     This is query 4 in CONTEXT_SEARCH_QUERIES — company-specific (not cached).
│   │     SERPER_MAX_QUERIES=3 means only queries 1-3 run; this is currently skipped.
│   │     Discuss: raise SERPER_MAX_QUERIES to 4, or move company-specific emission
│   │     query to a dedicated fetcher (emissions_fetcher.py).
│   │
│   └── Geopolitical — China parts import risk  ~ Serper search proxy (cached)
│         Built: "China semiconductor supply chain India automobile {year}"
│         Included in micro search queries → cached at sector level.
│         (Covered by micro query 1: "Nifty Auto ... crude oil steel aluminium commodity")
│
└── Signal Aggregator  (agents/signal_aggregator.py)                         ✓ built
    │   Weighted fusion with conflict resolution
    │   RL adaptive weight learning (Phase 5)
    │
    ├── Base weights                            ✓ AGENT_WEIGHTS in settings.py
    │     sales_demand 0.20 · fundamentals 0.25 · pattern 0.20
    │     sentiment 0.15 · risk_macro 0.20
    │
    ├── Conflict resolution                     ✓ built in signal_aggregator.py
    │     Detects bull/bear conflicts across agent scores, logs resolution
    │
    ├── RL weight adaptation                    ✓ built (Phase 5)
    │     WEIGHT_MAX_STEP, WEIGHT_MAX_DRIFT, WEIGHT_MIN_OBSERVATIONS in settings.py
    │     Adapts weights based on rolling direction accuracy per agent
    │
    └── Output: FinalReport                     ✓ BUY/ACCUMULATE/HOLD/WATCH/AVOID
          Verdict, final_score, weighted_agent_scores, conviction_drivers, top_risks
```

---

## 9. Search API Efficiency

### 9.1 Call Count per Full Analysis

`SERPER_MAX_QUERIES = 3` (default). Each agent calls `fetch_news_context()` which
runs up to this many Serper searches.

| Agent | Serper calls | Query type | Cacheable? |
|-------|-------------|-----------|-----------|
| sales_demand | 3 | Stock-specific (FADA, SIAM, EV reg) | No — per ticker |
| fundamentals | 3 | Stock-specific (earnings, margins) | No — per ticker |
| pattern_analysis | **0** | yfinance only | n/a |
| sentiment | 3 | Stock-specific (news NLP, social) | No — per ticker |
| risk_macro | **3 → 0** | **Sector-level** (INR/USD, commodities, RBI) | **Yes — shared** |
| **Total** | **12 (cold) / 9 (warm)** | | |

**Key insight:** `risk_macro`'s 3 queries (INR/USD, steel/aluminium/rubber, RBI repo rate)
return the same answer for every automobile stock on any given day. They are sector-level
signals, not per-stock signals. All three are captured by the micro search loop.

### 9.2 Overlap Analysis

| Overlap | Agents | Type | Resolution |
|---------|--------|------|-----------|
| INR/USD news | risk_macro | Sector-level | **Cached** via micro_search_loop |
| Commodity prices news | risk_macro | Sector-level | **Cached** via micro_search_loop |
| RBI repo rate news | risk_macro | Sector-level | **Cached** via micro_search_loop |
| General company news | sentiment + fundamentals | Per-stock, different angle | Not merged — sentiment focuses on tone, fundamentals on numbers |

### 9.3 Macro Cache Architecture

```
micro_search_loop()  ─────────────────────────►  tools/macro_cache.py
(main.py, background thread)                       set_macro_cache("automobile", text)
runs every  24h / MICRO_CYCLES_PER_DAY                      │
                                                             │ TTL = MACRO_CACHE_TTL_HOURS (2h)
                                                             ▼
ContextBuilder._build_risk_macro()  ─────────►  get_macro_cache("automobile")
(called per stock analysis)                        HIT  → skip 3 Serper calls
                                                   MISS → fetch fresh, 3 Serper calls
```

Pattern is identical to `StockAI/backend/agents/graph.py` `_macro_cache`.

### 9.4 Micro Search Loop

**Automobile-relevant queries (2 per run):**

```
Query 1: "Nifty Auto index India automobile sector outlook crude oil steel aluminium commodity prices"
Query 2: "India EV policy electric vehicle incentives FADA retail dispatch RBI repo rate auto loan EMI"
```

These cover the domain of all 3 risk_macro Serper queries in a single combined call each,
matching the StockAI pattern of merging overlapping queries into 1 combined call.

**Configuration:**

| Variable | Default | Purpose |
|----------|---------|---------|
| `MICRO_CYCLES_PER_DAY` | `6` | Runs every 4 hours |
| `MICRO_QUERIES_PER_RUN` | `2` | Serper calls per micro run |
| `MACRO_CACHE_TTL_HOURS` | `2` | Cache TTL (matches run interval) |

**Activation:**

```bash
# Single analysis with micro loop pre-warm
python main.py MARUTI --micro-loop

# Scheduler mode (micro loop always runs alongside scheduler)
# SCHEDULER_ENABLED=true in .env — wire start_micro_loop() into scheduler startup
```

### 9.5 Serper Budget Math

Serper free tier: **2,500 queries/month**

Baseline (5 scheduled tickers, no micro loop, no cache):

| Usage | Formula | Calls/month |
|-------|---------|------------|
| Per-stock analysis | 12 calls × 5 tickers × 30 days | 1,800 |
| **Total** | | **1,800** |
| **Buffer** | | **700 (28%)** |

With micro search loop + cache (steady-state):

| Usage | Formula | Calls/month |
|-------|---------|------------|
| Per-stock analysis | 9 calls × 5 tickers × 30 days | 1,350 |
| Micro search | 6 cycles × 2 queries × 30 days | 360 |
| **Total** | | **1,710** |
| **Saved by cache** | 3 × 5 × 30 | **450 calls/month** |
| **Buffer** | | **790 (32%)** |

The micro loop costs 360 calls/month but saves 450 — net saving of 90 calls/month
plus consistent, pre-warmed context quality for every risk_macro analysis.

Max micro cycles before hitting 2,500 free limit:
```
(2500 - 1350) / (2 queries × 30 days) = 19.1 → max 19 cycles/day
```

**Single manual analysis (1 stock):**

| Scenario | Serper calls |
|----------|-------------|
| Cold start (no cache) | 12 |
| Cache warm (micro loop ran ≤ 2h ago) | 9 |
| pattern_analysis only | 0 |

### 9.6 Comparison with StockAI

| Dimension | StockAI (IT sector) | Automobile Agent |
|-----------|--------------------|--------------------|
| Search API | Tavily (1,000 credits/month) | Serper (2,500 calls/month) |
| Calls per stock (cold) | 1 Tavily | 12 Serper |
| Calls per stock (warm) | 0 Tavily (cache hit) | 9 Serper |
| Micro loop queries | 2 per run (IT + RBI/Fed) | 2 per run (Nifty Auto + EV/FADA) |
| Macro cache | sector key in graph.py | sector key in tools/macro_cache.py |
| Cache TTL | 2h | 2h (MACRO_CACHE_TTL_HOURS) |
| Agent architecture | 3-stage async (POC) | 5 dedicated classes + orchestrator (v2) |
| Monthly budget target | 660 Tavily credits | 1,710 Serper calls |

The automobile repo uses Serper (not Tavily) and has a more generous free tier,
so the per-stock call count (12 cold, 9 warm) is acceptable. The same macro cache
pattern from StockAI is applied to deduplicate the sector-level risk_macro queries.

---

*Last updated: 2026-04-17. Update when adding new agents, changing SERPER_MAX_QUERIES, or wiring new search API fetchers.*

---

## 10. LangGraph Multi-Sector Graphs

Four independent LangGraph `StateGraph` flows defined in `langgraph.json`.
Each graph is fully isolated — a failure in one sector's graph never affects another.

### 10.1 Registry (`langgraph.json`)

```json
{
  "dependencies": ["."],
  "graphs": {
    "automobile":       "./graphs/automobile/graph.py:graph",
    "banking_bfsi":     "./graphs/banking_bfsi/graph.py:graph",
    "it_sector":        "./graphs/it_sector/graph.py:graph",
    "renewable_energy": "./graphs/renewable_energy/graph.py:graph"
  },
  "env": ".env"
}
```

### 10.2 Shared Infrastructure (`graphs/_shared/`)

| File | Purpose |
|---|---|
| `state.py` | `GraphState` TypedDict (`total=False`) with merge reducers for `agent_outputs` and `rail_errors` |
| `rails.py` | Three NeMo Guardrails-style validators: `input_rail`, `output_rail`, `conflict_rail` |
| `nodes.py` | Factory functions producing node callables parameterised by sector, agent registry, and weights |

**Why factory functions, not classes?**
LangGraph nodes must be plain callables. Factories let the same node logic serve all 4 sectors without sub-classing or global state.

### 10.3 Node Topology (identical for all 4 graphs)

```
graph.invoke({"ticker": "MARUTI"})
      │
      ▼
resolve_ticker          LLM call → StockQuery (ticker, company_name, exchange)
      │
      ▼
input_rail              NeMo input guard — yfinance fast_info check,
                        errors appended to rail_errors (non-blocking)
      │
      ▼ add_conditional_edges → make_dispatch_fn returns list[Send]
      │
  ┌───┴────────────────────────────────────┐
  ▼           ▼          ▼         ▼  (Send fan-out, parallel)
run_agent  run_agent  run_agent  run_agent  ...
  │  (each writes {"agent_name": AgentOutput} to agent_outputs via merge reducer)
  └───┬────────────────────────────────────┘
      │ fan-in: LangGraph waits for all Send branches
      ▼
aggregate               NeMo conflict_rail + weighted fusion + LLM synthesis
      │
      ▼
END                     FinalReport in state["final_report"]
```

### 10.4 Three-Rail Safety Layer

| Rail | Where | What it catches |
|---|---|---|
| `input_rail` | Before fan-out | Empty ticker, non-existent yfinance symbol |
| `output_rail` | Inside `run_agent` node | Score out of [0,1], empty summary — clamps and injects placeholder |
| `conflict_rail` | Inside `aggregate` node | Pairwise score spread > 0.35 — triggers LLM re-resolution |

All rails are **non-blocking**: they append to `rail_errors` and continue. No rail terminates the graph.

### 10.5 Resilience Patterns (Agents SDK / Swarm)

```
run_agent node retry=RetryPolicy(max_attempts=2)
      │
      ├── attempt 1: agent.run(query)  ←── normal path
      ├── attempt 2 (on exception): agent.run(query)  ←── LangGraph retry
      └── all attempts fail:
              AgentOutput(overall_score=0.5, error=str(exc))  ←── neutral fallback
              graph continues — no crash
```

### 10.6 Automobile Graph — Zero-Duplication Design

The automobile LangGraph graph (`graphs/automobile/graph.py`) does not copy any agent logic.
It wraps the existing `agents/` sub-agents via `graphs/automobile/agents.py`:

```python
from agents.sales_demand     import SalesDemandAgent    # existing code
from agents.fundamentals     import FundamentalsAgent   # existing code
# ... same for all 8 agents
AGENTS = {"sales_demand": SalesDemandAgent(), ...}      # thin registry only
```

The legacy `AutomobileAgentOrchestrator` in `agents/orchestrator.py` remains fully operational for CLI, FastAPI, and C# scheduler paths. The LangGraph graph is an **additive** path, not a replacement.

### 10.7 New Sector Agents — Context Gap (Known Limitation)

BFSI, IT, and Renewable Energy agents inherit `BaseAgent._gather_context()`, which routes by `agent_name` to `ContextBuilder`. The `ContextBuilder` currently only has automobile-sector routing.

**Impact:** New sector agents fall back to the minimal stub context and rely on LLM training knowledge.

**Mitigation path (priority order):**

| Sector | Agent | Recommended data source | Effort |
|---|---|---|---|
| BFSI | `fundamentals` | yfinance `quarterly_financials` + RBI DBIE | Low |
| BFSI | `macro_policy` | RBI website press releases (scrape) | Medium |
| IT | `fundamentals` | yfinance earnings + Tickertape API | Low |
| IT | `peer_benchmark` | Multi-ticker yfinance fetch | Low (~1 day) |
| RE | `fundamentals` | Company investor PDFs + yfinance | Medium |
| RE | `technical` | yfinance OHLCV only — zero cost | Low |

**Immediate workaround:** Override `_gather_context` in each new sector agent class to call yfinance directly for the fields most relevant to that agent. Pattern Analysis agents across all sectors need only yfinance OHLCV — zero extra wiring.

### 10.8 Known Design Weaknesses & Backlog

| # | Issue | Severity | File | Fix |
|---|---|---|---|---|
| 1 | `ContextBuilder` not sector-aware | High | `tools/context_builder.py` | Add routing branches for BFSI/IT/RE agent names |
| 2 | `BaseAgent._rag_retrieve` falls back to "automobile India" for unknown agents | High | `agents/base_agent.py` | Add `sector` parameter or override per-class |
| 3 | `run_agent` calls sync `agent.run()` — LangGraph parallel via threading, not asyncio | Medium | `graphs/_shared/nodes.py` | Switch to `agent.run_async()` + make nodes `async def` |
| 4 | `input_rail` makes blocking yfinance network call before fan-out | Medium | `graphs/_shared/rails.py` | Wrap in `asyncio.to_thread` or skip on `FAST_MODE=true` |
| 5 | Agent name collisions across sectors (`"fundamentals"` exists in all 4) | Low | All `agents.py` files | No immediate problem (graphs are isolated); prefix names if cross-sector reporting is added |
| 6 | No CLI / FastAPI entry point for new sector graphs | Medium | `main.py`, `api/routes/` | Add `--sector` flag and `/analyse/{sector}` route |
| 7 | `resp` usage logging skipped if JSON parse fails post-LLM call | Low | `graphs/_shared/nodes.py` | Move `log_llm_call` before `json.loads` in aggregate node |
