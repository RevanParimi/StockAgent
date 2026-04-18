# API Sources & Feature Reference — All Sector Agents

> Last updated: 2026-04-18
> Covers all four sector graphs: Automobile · Banking/BFSI · IT · Renewable Energy
> Free-tier only. No paid APIs. 0 spend.

---

## 1. Source Summary

| Source | What it returns | Free limit | Key needed | Status |
|---|---|---|---|---|
| **yfinance** | OHLCV, financials, macro tickers, peer data | Unlimited (unofficial scrape) | None | Active |
| **Serper** | Google search → title + 2-line snippet + URL | 2,500 calls/month | `SERPER_API_KEY` | Active |
| **Tavily** | Google search → full extracted page text | 1,000 calls/month | `TAVILY_API_KEY` | Active (Policy agent only) |
| **NewsAPI** | News articles from curated sources | 100 calls/day (free) | `NEWSAPI_KEY` | Fallback only |
| **OpenRouter (Qwen)** | LLM inference (qwen/qwen3-235b-a22b via OpenAI SDK) | Free tier available | `OPENROUTER_API_KEY` | Active |

### Why OpenRouter not Groq?
- OpenRouter is a gateway to multiple model providers — Qwen 3.5 / qwen3-235b-a22b selected for accuracy
- Uses standard OpenAI SDK (`openai>=1.30.0`) pointed at `https://openrouter.ai/api/v1`
- Groq was removed entirely; `GROQ_API_KEY` is no longer used

### Why Serper not Tavily for most agents?
- Serper free tier is **2.5× larger** (2,500 vs 1,000)
- For news/headlines, a 2-line snippet is sufficient for LLM context
- Tavily's full-page extraction adds value only where document depth matters (policy circulars, regulatory PDFs)
- Tavily is reserved for agents that require full document text (Automobile Policy & Regulatory, BFSI macro circulars)

---

## 2. Master Feature Table

### 2.1 Automobile (8 agents)

| Agent | Feature / Signal | Keep | Source | How Extracted | Est. Tokens |
|---|---|:---:|---|---|:---:|
| **Sales & Demand** | FADA / SIAM monthly dispatch | ✓ | Serper | Google search → title + snippet | ~275 |
| | Vahan registration data | ✓ | Serper | Google search → title + snippet | ~275 |
| | Segment split 2W/3W/4W/PV/CV/EV | ✓ | Serper | Google search → title + snippet | ~275 |
| | Dealer inventory days | ✓ | Serper | Google search → title + snippet | ~275 |
| | Used car price index Cars24/CarDekho | ✓ | Serper | Google search → title + snippet | ~275 |
| | Export / Import DGFT data | ✓ | Serper | Google search → title + snippet | ~275 |
| **Raw Materials** | Steel HRC & Aluminium LME/MCX | ✓ | yfinance (SLX, AA ETFs) | `yf.download()` → price + 3m change | ~80 |
| | Platinum & Palladium — catalytic converters | ✓ | yfinance (PPLT, PALL ETFs) | `yf.download()` → price + 3m change | ~80 |
| | Crude oil / Brent — polymer costs | ✓ | yfinance (CL=F, BZ=F) | `yf.download()` → price + 3m change | ~60 |
| | Power tariff — EV TCO impact | ✓ | Serper | Google search → headline snippet | ~275 |
| | ~~Lithium carbonate spot price~~ | ✗ | BloombergNEF | **Paid — dropped** | — |
| | ~~Battery pack $/kWh~~ | ✗ | BloombergNEF | **Paid — dropped** | — |
| | ~~Rubber RSS4~~ | ✗ | Tokyo Commodity Exchange | Not on yfinance — dropped | — |
| | ~~Cobalt / Nickel / Manganese NMC~~ | ✗ | No reliable free ETF | Too noisy — dropped | — |
| **Fundamentals** | Indian OEM financials Maruti/Tata/M&M | ✓ | yfinance | `quarterly_income_stmt` | ~200 |
| | Intl OEM Toyota/BYD/Tesla/Stellantis | ✓ | yfinance | `quarterly_income_stmt` | ~200 |
| | Revenue/EBITDA segment QoQ/YoY | ✓ | yfinance | Computed from quarterly statements | ~150 |
| | Volume growth / Market Share % | ✓ | Serper | Google search → snippet | ~275 |
| | EV Sales %, P/E, ROE | ✓ | yfinance + Serper | `info` dict + search snippet | ~200 |
| | EPS vs analyst estimates beat/miss | ✓ | yfinance | `quarterly_earnings` | ~100 |
| | Promoter / FII shareholding changes | ✓ | yfinance | `major_holders` | ~120 |
| | ~~Derivatives PCR / OI build-up~~ | ✗ | NSE (ToS risk) | **Legal risk — dropped** | — |
| **Pattern Analysis** | 10-yr price history cycle detection | ✓ | yfinance | `yf.download()` 10yr OHLCV | ~100 |
| | Seasonal sales window patterns | ✓ | yfinance | Monthly return avg over history | ~80 |
| | RSI / MACD / BB periodic refresh | ✓ | yfinance + C++ extension | Computed on Close price series | ~120 |
| | Breakout / support zone mapping | ✓ | yfinance | Rolling min/max pivot on 1yr close | ~80 |
| | Peer correl. Nifty Auto vs stock | ✓ | yfinance | Pearson corr + Beta vs `^CNXAUTO` | ~60 |
| **Policy & Regulatory** | FAME / EV subsidy disbursements | ✓ | **Tavily** | Full MoHI/PIB page text extracted | ~1,000 |
| | Emission norms BS7 / CAFE standards | ✓ | **Tavily** | Full regulatory document text | ~1,000 |
| | Union Budget — auto component duties | ✓ | Serper | Budget speech snippets | ~275 |
| | PLI scheme utilization by OEMs | ✓ | Serper | Ministry press release snippets | ~275 |
| | State EV incentives (varies) | ✓ | Serper | State govt announcement snippets | ~275 |
| **Competitive Intel** | EV market share Tata/BYD/Ather/Ola | ✓ | Serper | Google search → snippet | ~275 |
| | New model launch pipeline & pricing | ✓ | Serper | Google search → snippet | ~275 |
| | JV / acquisition announcements | ✓ | Serper | Google search → snippet | ~275 |
| | ADAS milestones BNAP/NCAP ratings | ✓ | Serper | Google search → snippet | ~275 |
| **Risk & Macro** | India GDP & IIP — consumer spending | ✓ | yfinance + Serper | Macro tickers + snippet | ~350 |
| | RBI repo rate — auto loan EMI | ✓ | yfinance + Serper | Proxy tickers + snippet | ~200 |
| | Fuel price trajectory ICE vs EV | ✓ | Serper | Google search → snippet | ~275 |
| | India-China tensions component risk | ✓ | Serper | Google search → snippet | ~275 |
| | Global import/export duty changes | ✓ | Serper | Google search → snippet | ~275 |
| ~~Alternate Signals~~ | ~~Parking lot satellite data~~ | ✗ | Planet Labs | **Paid — team lead dropped** | — |
| | ~~Test drive booking scraping~~ | ✗ | OEM websites | ToS risk — dropped | — |
| | ~~Job postings capex intent~~ | ✗ | LinkedIn/Indeed | ToS risk — dropped | — |
| | ~~Earnings call NLP~~ | ✗ | Custom NLP pipeline | Complexity — dropped for auto; active in IT sector | — |

---

### 2.2 Banking & BFSI (6 agents)

> Context status: **wired** — `ContextBuilder` sector routing active (`sector="bfsi"`). All 6 agents receive live Serper + yfinance data. `pattern_analysis` falls through to the shared yfinance technical method. Priority column reflects data depth already fetched (P0 = active in current build).

| Agent | Feature / Signal | Source | Priority | Est. Tokens |
|---|---|---|:---:|:---:|
| **Fundamentals** | NPA %, PCR, NIM, CASA ratio | yfinance `quarterly_financials` | P0 | ~200 |
| | CRAR/CET1 capital ratios | yfinance `balance_sheet` | P0 | ~150 |
| | RoA, RoE, credit cost trend | yfinance computed | P0 | ~100 |
| | Loan mix (retail/corporate/MSME) | Serper (company filings snippets) | P1 | ~275 |
| **Risk** | SMA / NPA slippage watchlist | Serper | P1 | ~275 |
| | Top-5 borrower concentration | Serper (annual report snippets) | P1 | ~275 |
| | Deposit stability / CASA trend | yfinance + Serper | P1 | ~200 |
| **Macro & Policy** | RBI MPC repo rate decisions | Serper / RBI press releases | P0 | ~275 |
| | System credit / deposit growth | RBI DBIE (scrape) | P1 | ~200 |
| | SEBI/RBI circulars & penalties | **Tavily** (full circular text) | P1 | ~800 |
| | LAF / CRR / SLR liquidity ops | Serper | P2 | ~275 |
| **Institutional** | FII/DII net flow 1M/3M | yfinance `institutional_holders` | P0 | ~120 |
| | Promoter stake change, pledge % | yfinance `major_holders` | P0 | ~100 |
| | Analyst rating changes | Serper | P1 | ~275 |
| **Pattern Analysis** | RSI / MACD / BB | yfinance + C++ extension | P0 | ~120 |
| | Rate-cut rally seasonality | yfinance 10yr OHLCV | P0 | ~80 |
| | Nifty Bank / PSU Bank correlation | yfinance `^NSEBANK`, `^CNXPSUBANK` | P0 | ~60 |
| **Universe Setup** | Nifty Bank index weights | NSE website / Serper | P2 | ~150 |
| | Corporate actions (splits/bonuses) | yfinance `actions` | P1 | ~80 |

---

### 2.3 IT Sector (8 agents)

> Context status: **wired** — `ContextBuilder` sector routing active (`sector="it"`). All 8 agents receive live data. `pattern_analysis` falls through to shared yfinance method. `transcript_nlp` uses Tavily (2 calls/analysis) for earnings call text. `risk_macro` uses sector-keyed macro cache (`"it"` key) — see budget note on cache population.

| Agent | Feature / Signal | Source | Priority | Est. Tokens |
|---|---|---|:---:|:---:|
| **Fundamentals** | Revenue QoQ/YoY (CC growth) | yfinance `quarterly_income_stmt` | P0 | ~200 |
| | EBIT margin 8-quarter trend | yfinance computed | P0 | ~150 |
| | TCV / deal win announcements | Serper | P0 | ~275 |
| | Attrition %, headcount growth | Serper (company press releases) | P1 | ~275 |
| | P/E, EV/Revenue, PEG | yfinance `info` | P0 | ~100 |
| **Global Macro** | US IT capex / enterprise software spend | Serper (Gartner/IDC snippets) | P1 | ~275 |
| | Fed funds rate trajectory | yfinance `^IRX` (13-week T-bill proxy) | P0 | ~80 |
| | USD/INR rate | yfinance `INR=X` | P0 | ~60 |
| | US-China tech war developments | Serper | P1 | ~275 |
| **Risk & Macro** | H1B/L1 visa approval rates | Serper (USCIS news) | P1 | ~275 |
| | AI disruption / GenAI deal flow | Serper | P0 | ~275 |
| | Client concentration (top-5 revenue %) | Serper (annual report snippets) | P1 | ~275 |
| **Peer Benchmark** | TCS/Infy/HCL/Wipro multi-ticker fetch | yfinance (4 tickers) | P0 | ~400 |
| | Peer margin / deal / valuation deltas | yfinance computed | P0 | ~200 |
| **Pattern Analysis** | RSI / MACD / BB | yfinance + C++ extension | P0 | ~120 |
| | Nifty IT correlation / beta | yfinance `^CNXIT` | P0 | ~60 |
| | Quarter-end rebalancing seasonality | yfinance 10yr OHLCV | P0 | ~80 |
| **Sentiment** | AI narrative in news | Serper | P0 | ~275 |
| | Layoff signals (IT sector) | Serper | P1 | ~275 |
| | Management tone summary | Serper (earnings summaries) | P1 | ~275 |
| **Transcript NLP** | Earnings call transcript text | Screener.in / Tickertape (scrape) | P2 | ~1,500 |
| | Guidance language (CC growth words) | Same transcript source | P2 | ~500 |
| **Insider/Smart Money** | Promoter / director trades | yfinance `insider_transactions` | P0 | ~120 |
| | MF allocation changes | Serper (AMFI snippets) | P1 | ~275 |
| | F&O put-call ratio | NSE website (scrape) | P2 | ~100 |

---

### 2.4 Renewable Energy (6 agents)

> Context status: **wired** — `ContextBuilder` sector routing active (`sector="re"`). All 6 agents receive live data. `technical` uses `_build_technical` (dedicated yfinance OHLCV method, 0 Serper calls). `sentiment_policy` uses Tavily (2 calls/analysis) for MNRE circular text.

| Agent | Feature / Signal | Source | Priority | Est. Tokens |
|---|---|---|:---:|:---:|
| **Fundamentals** | CUF (%) vs technology benchmark | Company investor presentations (PDF) | P1 | ~150 |
| | EBITDA/MW trend | yfinance `quarterly_income_stmt` | P0 | ~150 |
| | DSCR (≥1.2x target) | yfinance `balance_sheet` computed | P0 | ~100 |
| | Receivables aging (DISCOM delays) | Serper (company updates) | P1 | ~275 |
| | Project-level D/E | yfinance `balance_sheet` | P0 | ~80 |
| **Business** | PPA tariff, tenor, counterparty | Serper (filing summaries) | P1 | ~275 |
| | Pipeline GW (under construction %) | Serper (investor day snippets) | P1 | ~275 |
| | Sub-sector mix Solar/Wind/Hybrid | yfinance `info` + Serper | P1 | ~200 |
| | DISCOM customer state diversification | Serper | P2 | ~275 |
| **Valuation** | EV/MW vs peer range | yfinance + Serper (analyst reports) | P1 | ~200 |
| | Current MNRE L1 auction tariff | SECI/MNRE website (scrape) | P1 | ~200 |
| | P/B ratio, dividend yield | yfinance `info` | P0 | ~80 |
| **Sentiment & Policy** | MNRE auction GW awarded | MNRE website / Serper | P0 | ~275 |
| | Union Budget RE capex allocation | Serper (Budget speech snippets) | P0 | ~275 |
| | Green hydrogen mission funding | Serper | P1 | ~275 |
| | RPO targets, ISTS waiver status | **Tavily** (MNRE circular text) | P1 | ~800 |
| **Technical** | 50/200-DMA golden/death cross | yfinance OHLCV | P0 | ~80 |
| | Weekly RSI, MACD crossover | yfinance + C++ extension | P0 | ~120 |
| | Volume surge on MNRE news | yfinance `yf.download()` | P0 | ~60 |
| | 52-week range / Fibonacci levels | yfinance | P0 | ~60 |
| **Risk** *(monitoring)* | DISCOM payment delays | PFC/REC quarterly reports (Serper) | P1 | ~275 |
| | Grid curtailment % | NLDC/SLDC reports (Serper) | P2 | ~275 |
| | Steel/copper input price trend | yfinance (SLX, CPER ETFs) | P0 | ~80 |
| | Regulatory tariff re-negotiation risk | Serper | P1 | ~275 |

---

## 3. Drop Reasons Reference

| Category | Features Dropped | Reason |
|---|---|---|
| Paid API required | Lithium, Battery $/kWh | BloombergNEF subscription only |
| No free data source | Rubber RSS4 | TOCOM not on yfinance |
| Proxy too noisy | Cobalt/Nickel/Manganese | Individual metal ETFs diverge too much from spot |
| Legal / ToS risk | Derivatives OI, Test drive scraping, Job postings | NSE ToS; OEM/LinkedIn ToS |
| Team lead decision | All 4 Alternate Signals | Complexity vs signal value ratio |

---

## 4. Monthly API Budget

> Assumption: 5 tickers/day × 22 working days = **110 analyses/month per sector**
> All 4 sectors are now fully wired. Numbers reflect actual `ContextBuilder` call counts.
> `SERPER_MAX_QUERIES=3` (configurable) — each agent's `fetch_news_context` runs at most 3 queries.

### 4.1 Automobile (fully wired, production state)

| Source | Calls/Analysis | Monthly | Micro loop | **Total** | Limit | Headroom |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| Serper | 9 (warm cache) | 990 | 360 | **1,350** | 2,500 | ✅ 46% |
| Tavily | 2 (Policy only) | 220 | 0 | **220** | 1,000 | ✅ 78% |
| yfinance | ~8 fetches | unlimited | unlimited | **∞** | Free | ✅ |
| OpenRouter LLM | 9 calls | ~990 calls | 0 | ~990/month | rate-limited | ✅ |

### 4.2 Banking / BFSI (wired)

> Agents calling Serper: `fundamentals`, `risk`, `macro_policy`, `institutional`, `universe_setup` (5 × 3 = 15 max). `pattern_analysis` → yfinance only.  
> `macro_policy` checks `macro_cache("bfsi")` first — cache HIT saves 3 calls. Cache populated only when main.py macro loop is extended to BFSI (pending).

| Source | Calls/Analysis | Monthly (110 analyses) | Limit | Status |
|---|:---:|:---:|:---:|:---:|
| Serper | 12–15 (12 w/ cache HIT) | 1,320–1,650 | 2,500 | ✅ Wired |
| Tavily | 0 | 0 | 1,000 | ✅ (RBI full-text is P1, not yet active) |
| yfinance | ~5 (financials + shareholding + technicals) | unlimited | Free | ✅ |
| OpenRouter LLM | 7 (6 agents + 1 aggregator) | ~770/month | rate-limited | ✅ |

### 4.3 IT Sector (wired)

> Agents calling Serper: `fundamentals`, `global_macro`, `risk_macro`, `peer_benchmark`, `sentiment`, `insider_smart_money` (6 × 3 = 18), plus `transcript_nlp` (2 Serper). `pattern_analysis` → yfinance only.  
> `risk_macro` checks `macro_cache("it")` first — HIT saves 3 calls. Cache populated only when main.py macro loop is extended to IT (pending).  
> `transcript_nlp` additionally makes 2 Tavily calls for earnings call document text.

| Source | Calls/Analysis | Monthly (110 analyses) | Limit | Status |
|---|:---:|:---:|:---:|:---:|
| Serper | 17–20 (17 w/ cache HIT) | 1,870–2,200 | 2,500 | ✅ Wired |
| Tavily | 2 (transcript_nlp) | ~220 | 1,000 | ✅ Wired |
| yfinance | ~7 (financials + peer basket + technicals) | unlimited | Free | ✅ |
| OpenRouter LLM | 9 (8 agents + 1 aggregator) | ~990/month | rate-limited | ✅ |

### 4.4 Renewable Energy (wired)

> Agents calling Serper: `fundamentals`, `business`, `valuation`, `risk` (4 × 3 = 12). `sentiment_policy` calls Serper (3) + Tavily (2). `technical` → yfinance only (0 API calls).

| Source | Calls/Analysis | Monthly (110 analyses) | Limit | Status |
|---|:---:|:---:|:---:|:---:|
| Serper | ~15 | ~1,650 | 2,500 | ✅ Wired |
| Tavily | 2 (sentiment_policy MNRE circulars) | ~220 | 1,000 | ✅ Wired |
| yfinance | ~4 (financials + OHLCV) | unlimited | Free | ✅ |
| OpenRouter LLM | 7 (6 agents + 1 aggregator) | ~770/month | rate-limited | ✅ |

### 4.5 Combined budget at full production (all 4 sectors, 110 analyses/sector/month)

> Numbers below use cache-HIT scenario (macro loop running for all sectors).

| Source | Auto | BFSI | IT | RE | **Total** | Limit | Headroom |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| Serper | 1,350 | 1,320 | 1,870 | 1,650 | **6,190** | 2,500 | ⚠️ 148% over |
| Tavily | 220 | 0 | 220 | 220 | **660** | 1,000 | ✅ 34% |
| yfinance | ∞ | ∞ | ∞ | ∞ | **∞** | Free | ✅ |

> ⚠️ **Serper budget concern at full production:** Running all 4 sectors simultaneously at 5 tickers/day will exceed the 2,500/month free tier by ~2.5×. Mitigations:
>
> **1. Sector-level macro cache — extend `main.py` micro loop to BFSI and IT**
> `macro_cache.py` already supports arbitrary sector keys (`set_macro_cache("bfsi", text)`). `_build_macro_policy` and `_build_it_risk_macro` already call `get_macro_cache("bfsi")` / `get_macro_cache("it")`. The missing piece is populating those keys from `main.py`. RBI rate, system credit growth, and US Fed queries are shared across all stocks in a sector — fetch once per 4 hours, serve all. Each cache HIT saves 3 Serper calls per analysis. At 5 tickers/day this saves 450 calls/month per sector.
>
> **2. Stagger sectors — Automobile Mon/Wed/Fri, BFSI/IT/RE Tue/Thu**
> Automobile is the most complete sector and benefits from higher frequency. New sectors run less frequently. With staggering: Auto runs 13 days/month (715 analyses), others run 9 days each (495 analyses). Effective Serper: ~590 + ~580 + ~820 + ~725 = **~2,715** — just over limit but manageable with `SERPER_MAX_QUERIES=2`.
>
> **3. Reduce `SERPER_MAX_QUERIES`** — Setting it to 2 (from 3) cuts all sectors proportionally and brings combined total under 2,500 with staggering active.
>
> **4. Upgrade Serper** — $50/month for 50,000 calls removes this constraint entirely and is the simplest option at scale.
