# API Sources & Feature Reference — Automobile Agent

> Last updated: 2026-04-11  
> Free-tier only. No paid APIs. 0 spend.

---

## 1. Source Summary

| Source | What it returns | Free limit | Key needed | Status |
|---|---|---|---|---|
| **yfinance** | OHLCV, financials, macro tickers, peer data | Unlimited (unofficial scrape) | None | Active |
| **Serper** | Google search → title + 2-line snippet + URL | 2,500 calls/month | `SERPER_API_KEY` | Active |
| **Tavily** | Google search → full extracted page text | 1,000 calls/month | `TAVILY_API_KEY` | Active (Policy agent only) |
| **NewsAPI** | News articles from curated sources | 100 calls/day (free) | `NEWSAPI_KEY` | Fallback only |
| **Groq LLM** | LLM inference (llama-3.3-70b-versatile) | ~6,000 TPM free | `GROQ_API_KEY` | Active |

### Why Serper not Tavily for most agents?
- Serper free tier is **2.5× larger** (2,500 vs 1,000)
- For news/headlines, a 2-line snippet is sufficient for LLM context
- Tavily's full-page extraction adds value only where document depth matters (policy circulars, regulatory PDFs)
- Tavily is reserved for Policy & Regulatory agent only (2 calls/analysis)

---

## 2. Master Feature Table

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
| **Financial & Market** | Indian OEM financials Maruti/Tata/M&M | ✓ | yfinance | `quarterly_income_stmt` | ~200 |
| | Intl OEM Toyota/BYD/Tesla/Stellantis | ✓ | yfinance | `quarterly_income_stmt` | ~200 |
| | Revenue/EBITDA segment QoQ/YoY | ✓ | yfinance | Computed from quarterly statements | ~150 |
| | Volume growth / Market Share % | ✓ | Serper | Google search → snippet | ~275 |
| | EV Sales %, P/E, ROE | ✓ | yfinance + Serper | `info` dict + search snippet | ~200 |
| | EPS vs analyst estimates beat/miss | ✓ | yfinance | `quarterly_earnings` | ~100 |
| | Promoter / FII shareholding changes | ✓ | yfinance | `major_holders` | ~120 |
| | ~~Derivatives PCR / OI build-up~~ | ✗ | NSE (ToS risk) | **Legal risk — dropped** | — |
| **Pattern Analysis** | 10-yr price history cycle detection | ✓ | yfinance | `yf.download()` 10yr OHLCV | ~100 |
| | Seasonal sales window patterns | ✓ | yfinance | Monthly return avg over history | ~80 |
| | RSI / MACD / BB periodic refresh | ✓ | yfinance + `ta` lib | Computed on Close price series | ~120 |
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
| | ~~Earnings call NLP~~ | ✗ | Custom NLP pipeline | Complexity — dropped | — |

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

> Assumption: 5 tickers/day × 22 working days = **110 analyses/month**

| Source | Calls/Analysis | Monthly (analyses) | Micro loop | **Total** | Limit | Headroom |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| Serper | 9 (warm cache) | 990 | 360 | **1,350** | 2,500 | ✅ 46% used |
| Tavily | 2 (Policy only) | 220 | 0 | **220** | 1,000 | ✅ 22% used |
| yfinance | ~8 fetches | unlimited | unlimited | **unlimited** | Free | ✅ |
| Groq LLM | 8 calls | ~880 calls / ~1.2M tokens | 0 | ~1.2M tokens/month | ~500K TPD | ✅ |

**Both Serper and Tavily stay within free tier with 54% and 78% headroom respectively.**
