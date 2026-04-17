# Automobile Agent — Solution Design

> Internal reference document.
> Cross-reference: `E:\AI projects\StockAI\docs\SOLUTION_DESIGN.md` (IT sector reference).
> This document uses the same section numbering as the StockAI doc for easy cross-referencing.
> Sections 1–7 are the IT sector reference; Sections 8–9 are automobile-specific.

---

## 8. Target Architecture vs Implementation — Full Mapping

Based on `automobile_agent_tree.txt`.

Legend: `✓` built  ·  `~` partial  ·  `○` not yet wired

```
AUTOMOBILE AGENT
│   Orchestrator: AutomobileAgentOrchestrator in agents/orchestrator.py      ✓ built
│   LLM: OpenRouter → Qwen 2.5 72B via tools/llm_client.py (Helicone proxy)  ✓ built
│   Observability: JSONL token/cost logging via tools/run_logger.py           ✓ built
│   Trigger: SCHEDULER_ENABLED / CLI (main.py)                               ✓ built
│   Parallel dispatch: ThreadPoolExecutor (8 workers)                         ✓ built
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
├── Raw Materials Agent  (agents/raw_materials.py)                           ✓ built
│   │   Context: macro_fetcher.get_raw_materials_context() (yfinance) + news_fetcher (Serper, 1 call)
│   │   Serper calls per run: 1 (power tariff — sector-level news)
│   │   yfinance tickers: SLX (steel), AA (aluminium), PPLT (platinum), PALL (palladium),
│   │                      CL=F (WTI crude), BZ=F (Brent crude)
│   │
│   ├── Steel HRC & Aluminium LME/MCX          ✓ yfinance (SLX ETF, Alcoa AA proxy)
│   │     Built: get_raw_material_prices() → SLX, AA in macro_fetcher.py
│   │     Limitation: SLX/AA are US-listed ETFs; proxy for directional cost signal only
│   │
│   ├── Platinum & Palladium — catalytic        ✓ yfinance (PPLT, PALL ETFs)
│   │     Built: PPLT (Aberdeen Platinum ETF), PALL (Aberdeen Palladium ETF)
│   │     Relevant for ICE-heavy OEMs (Maruti, Bajaj Auto, Hero MotoCorp)
│   │
│   ├── Crude oil / Brent — polymer costs       ✓ yfinance (CL=F, BZ=F)
│   │     Built: WTI + Brent futures via yfinance in _RAW_MATERIAL_TICKERS
│   │
│   ├── Power tariff — EV TCO impact            ~ Serper search proxy (1 call)
│   │     Built: "India electricity power tariff EV charging cost {year}"
│   │     Gap: state-wise tariff data varies; Serper fetches news-level summaries
│   │
│   └── ~~Lithium / Battery $/kWh~~             ✗ dropped — BloombergNEF paid only
│         ~~Rubber RSS4~~                        ✗ dropped — TOCOM not on yfinance
│         ~~Cobalt / Nickel / Manganese~~        ✗ dropped — no reliable free ETF proxy
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
├── Policy & Regulatory Agent  (agents/policy_regulatory.py)                 ✓ built
│   │   Context: tavily_fetcher (2 calls, full doc) + news_fetcher (Serper, 3 calls)
│   │   Tavily calls: 2 (FAME circulars, BS7/CAFE standards — full text extraction)
│   │   Serper calls: 3 (Union Budget duties, PLI scheme, state EV incentives)
│   │   WHY Tavily here: MoHI policy PDFs and regulatory standards need full content,
│   │   not just 2-line snippets. Tavily's page extraction materially improves LLM accuracy.
│   │
│   ├── FAME / EV subsidy disbursements         ✓ Tavily (full MoHI circular text)
│   │     Built: fetch_tavily_context() in context_builder._build_policy_regulatory()
│   │     Query: "FAME II III EV subsidy disbursement India automobile {year} MoHI notification"
│   │
│   ├── Emission norms BS7 / CAFE standards     ✓ Tavily (full regulatory doc)
│   │     Built: Tavily query 2 in TAVILY_SEARCH_QUERIES (prompts/policy_regulatory.py)
│   │
│   ├── Union Budget — auto component duties    ~ Serper search proxy
│   │     Built: "India Union Budget automobile component import duty {ticker} {year}"
│   │
│   ├── PLI scheme utilization by OEMs          ~ Serper search proxy
│   │     Built: "PLI scheme automobile OEM {company_name} utilization incentive {year}"
│   │
│   └── State EV incentives (varies)            ~ Serper search proxy
│         Built: "India state EV incentive electric vehicle subsidy registration waiver {year}"
│         Gap: state-level data is fragmented — Serper captures news about incentive changes
│
├── Competitive Intel Agent  (agents/competitive_intel.py)                   ✓ built
│   │   Context: news_fetcher (Serper, 4 calls — all company-specific)
│   │   Serper calls per run: 4 (EV share, model launches, JV/M&A, ADAS/NCAP)
│   │   Note: all 4 queries are company-specific — cannot be cached like risk_macro
│   │
│   ├── EV market share — Tata/BYD/Ather/Ola    ~ Serper search proxy
│   │     Built: "India EV market share {company_name} Tata Motors BYD Ather Ola {month} {year}"
│   │
│   ├── New model launch pipeline & pricing     ~ Serper search proxy
│   │     Built: "{company_name} new model launch pipeline EV product roadmap {year}"
│   │
│   ├── JV / acquisition announcements          ~ Serper search proxy
│   │     Built: "{company_name} joint venture acquisition partnership {year}"
│   │
│   ├── ADAS milestones BNAP/NCAP ratings       ~ Serper search proxy
│   │     Built: "{ticker} BNAP NCAP safety rating ADAS autonomous feature {year}"
│   │
│   └── ~~Alternate signals~~                   ✗ dropped per team lead decision
│         (parking lot satellite, test drive scraping, job postings, earnings call NLP)
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
    │     sales_demand 0.18 · raw_materials 0.10 · fundamentals 0.20
    │     pattern_analysis 0.13 · sentiment 0.04 (legacy)
    │     policy_regulatory 0.10 · competitive_intel 0.10 · risk_macro 0.15
    │     sum = 1.00
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

`SERPER_MAX_QUERIES = 3` (default). Each Serper-using agent calls `fetch_news_context()`
which runs up to this many searches. Tavily is called directly in `_build_policy_regulatory()`.

| Agent | Serper calls | Tavily calls | Query type | Cacheable? |
|-------|-------------|-------------|-----------|-----------|
| sales_demand | 3 | 0 | Stock-specific (FADA, SIAM, EV reg) | No — per ticker |
| raw_materials | 1 | 0 | Sector-level (power tariff) | Partly |
| fundamentals | 2 | 0 | Stock-specific (earnings, margins) | No — per ticker |
| pattern_analysis | **0** | 0 | yfinance only | n/a |
| sentiment | 3 | 0 | Stock-specific (news NLP, social) | No — per ticker |
| policy_regulatory | 3 | **2** | Sector + company mix | Partly |
| competitive_intel | 4 | 0 | Stock-specific (EV share, launches) | No — per ticker |
| risk_macro | **3 → 0** | 0 | **Sector-level** (INR/USD, commodities, RBI) | **Yes — shared** |
| **Total** | **19 (cold) / 16 (warm)** | **2** | | |

**Key insight:** `risk_macro`'s 3 Serper queries are sector-level — same answer for
every automobile stock on any given day. Captured by micro search loop (cache HIT = 0 calls).
`policy_regulatory`'s Tavily calls (2/analysis) are the only Tavily usage in the system,
reserved for full document extraction of FAME circulars and BS7/CAFE regulatory texts.

### 9.2 Overlap Analysis

| Overlap | Agents | Type | Resolution |
|---------|--------|------|-----------|
| INR/USD news | risk_macro | Sector-level | **Cached** via micro_search_loop |
| Commodity prices news | risk_macro | Sector-level | **Cached** via micro_search_loop |
| RBI repo rate news | risk_macro | Sector-level | **Cached** via micro_search_loop |
| General company news | sentiment + fundamentals | Per-stock, different angle | Not merged — sentiment = tone, fundamentals = numbers |
| Steel/aluminium prices | risk_macro + raw_materials | Both use yfinance (free) | No dedup needed — yfinance is free and fast |
| Policy/emission norms | risk_macro + policy_regulatory | Overlapping angle | risk_macro uses Serper snippet; policy_regulatory uses Tavily full text — different depth |

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
| Search API | Tavily (1,000 credits/month) | Serper (2,500/month) + Tavily (1,000/month) |
| Calls per stock (cold) | 1 Tavily | 19 Serper + 2 Tavily |
| Calls per stock (warm) | 0 Tavily (cache hit) | 16 Serper + 2 Tavily |
| Tavily usage | All agents | Policy & Regulatory agent only |
| Micro loop queries | 2 per run (IT + RBI/Fed) | 2 per run (Nifty Auto + EV/FADA) |
| Macro cache | sector key in graph.py | sector key in tools/macro_cache.py |
| Cache TTL | 2h | 2h (MACRO_CACHE_TTL_HOURS) |
| Agent architecture | 3-stage async (POC) | 8 dedicated classes + orchestrator |
| Monthly budget (Serper) | n/a | ~1,350 / 2,500 (54% used) |
| Monthly budget (Tavily) | 660 credits | ~220 / 1,000 (22% used) |

Automobile repo uses Serper as primary (larger free tier) and adds Tavily selectively
for the Policy & Regulatory agent where full document content matters (FAME circulars,
BS7/CAFE regulatory texts). Both APIs stay well within free tiers.

---

*Generated: 2026-04-09. Updated: 2026-04-12 — added Raw Materials, Policy & Regulatory,
Competitive Intel agents; added Tavily fetcher; updated weights and call count tables.*
