# API Sources & Data Reference

> Updated: 2026-04-19 · Automobile sector: 9 agents · All free-tier only

---

## Source Summary

| Source | Returns | Free limit | Key | Status |
|---|---|---|---|---|
| **yfinance** | OHLCV, financials, macro prices | Unlimited (unofficial) | None | Active |
| **Serper** | Google search → title + snippet + URL | 2,500 calls/month | `SERPER_API_KEY` | Active |
| **Tavily** | Google search → full extracted page text | 1,000 calls/month | `TAVILY_API_KEY` | Active (Policy agent only) |
| **NewsAPI** | News articles from curated sources | 100 calls/day | `NEWSAPI_KEY` | Fallback only (when Serper fails) |
| **OpenRouter** | LLM inference via OpenAI-compatible SDK | Pay-per-token | `OPENROUTER_API_KEY` | Active |

**LLM default:** `qwen/qwen3-235b-a22b` via `https://openrouter.ai/api/v1`  
**Why Serper over Tavily for most agents:** Serper is 2.5× larger quota; 2-line snippets are sufficient for news context. Tavily reserved for policy/regulatory where full-page document depth matters.

---

## Per-Agent Data Sources

| Agent | yfinance | Serper | Tavily | Notes |
|---|:---:|:---:|:---:|---|
| sales_demand | | ✓ | | FADA/SIAM dispatch, Vahan EV reg, dealer inventory |
| raw_materials | ✓ | ✓ (1 query) | | SLX, AA, PPLT, PALL, CL=F, BZ=F prices |
| fundamentals | ✓ | ✓ | | Quarterly P&L, balance sheet via yfinance |
| pattern_analysis | ✓ | | | 10yr OHLCV → RSI, MACD, Bollinger, support/resistance |
| sentiment | | ✓ | | News NLP, earnings call sentiment |
| policy_regulatory | | ✓ | ✓ | Tavily for govt circulars/PDFs; Serper for news |
| competitive_intel | | ✓ | | Market share, model pipeline, JV news |
| risk_macro | ✓ | ✓ | | INR=X, CL=F, SLX, AA prices + macro news |
| valuation_catalyst | | | | ContextBuilder method not yet implemented — LLM knowledge only |

---

## yfinance Tickers Used

| Variable | Ticker | Represents |
|---|---|---|
| `CRUDE_OIL_TICKER` | `CL=F` | WTI Crude Futures (USD/bbl) |
| `BRENT_TICKER` | `BZ=F` | Brent Crude Futures |
| `INR_USD_TICKER` | `INR=X` | INR per USD exchange rate |
| `STEEL_TICKER` | `SLX` | VanEck Steel ETF (steel price proxy) |
| `ALUMINIUM_TICKER` | `AA` | Alcoa stock (aluminium price direction proxy) |
| `PLATINUM_TICKER` | `PPLT` | Aberdeen Platinum ETF (catalytic converters) |
| `PALLADIUM_TICKER` | `PALL` | Aberdeen Palladium ETF (catalytic converters) |
| `RUBBER_TICKER` | `^TOCOM_RUBBER` | TOCOM rubber (often unavailable — silently skipped) |
| `NIFTY_AUTO_TICKER` | `^CNXAUTO` | Nifty Auto index (peer correlation) |
| NSE stocks | `{TICKER}.NS` | Individual NSE-listed stocks |

**Known yfinance issues:**
- Newly-listed stocks (e.g. `ATHERENERGY.NS`) return 404 — no historical data available yet
- `INR=X` sometimes returns a multi-column DataFrame in newer yfinance — handled in `_fetch_latest()` with column guard
- `^TOCOM_RUBBER` / `RBc1` delisted — rubber data omitted silently

---

## API Usage Tracking

Monthly counters stored in `logs/api_usage.json`, auto-reset each calendar month.

```python
from services.data.stores.api_usage import get_usage, record_call
get_usage()
# {"month": "2026-04", "serper": {"calls": 24, "limit": 2500, "remaining": 2476, "pct_used": 1.0},
#                      "tavily": {"calls": 6,  "limit": 1000, "remaining": 994,  "pct_used": 0.6}}
```

`record_call("serper")` fires inside `search_serper()` on every successful response.  
`record_call("tavily")` fires inside `search_tavily()` on every successful response.  
Override limits: `SERPER_MONTHLY_LIMIT`, `TAVILY_MONTHLY_LIMIT` env vars.

---

## Serper Budget Per Run

Each run without `--micro-loop` cache: up to `SERPER_MAX_QUERIES=3` calls per agent.

| Agent | Max Serper calls | Notes |
|---|---|---|
| sales_demand | 3 | 5 queries templated, capped at SERPER_MAX_QUERIES |
| raw_materials | 1 | `fetch_news_context(max_queries=1)` |
| fundamentals | 3 | |
| sentiment | 3 | |
| policy_regulatory | 3 | + up to 2 Tavily calls |
| competitive_intel | 3 | |
| risk_macro | 3 (or 0 if cache hit) | macro_cache populated by `--micro-loop` saves all 3 |
| pattern_analysis | 0 | yfinance only |
| valuation_catalyst | 0 | no context builder yet |

**Max per run:** ~19 Serper + 2 Tavily · **With cache:** ~16 Serper + 2 Tavily  
**Monthly budget at 1 run/day:** ~570 Serper (23% of 2500) · ~60 Tavily (6% of 1000)
