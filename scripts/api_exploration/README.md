# API Exploration Scripts

Scripts to validate and test data sources before integrating into StockAgent.
Each script is self-contained — run individually after filling in credentials.

## Scripts

| File | API | Cost | What it tests |
|---|---|---|---|
| `fyers_explorer.py` | Fyers API v3 | Free | Live quotes, OHLCV history, options chain with IV/PCR |
| `angel_one_explorer.py` | Angel One SmartAPI v2 | Free | Live quotes, history, options Greeks, Depth-20 WebSocket |
| `dhan_explorer.py` | Dhan DhanHQ v2 | Free | **Best options chain** — full Greeks (Δ,Θ,Γ,ν,IV) per strike |
| `amfi_mf_explorer.py` | mfapi.in (AMFI) | Free, no auth | MF NAV history, herding signal detection |
| `iima_ff_factors.py` | IIMA Fama-French | Free CSV | 4-factor model: Market/SMB/HML/WML for India |
| `earnings_api_explorer.py` | EarningsAPI.com + AlphaStreet | Free tier / Enterprise | Earnings call transcripts + guidance extraction |
| `nse_insider_scraper.py` | NSE public endpoints | Free, no auth | Bulk/block deals, insider transactions, shareholding |

## Quick Start

```bash
pip install requests pandas fyers-apiv3 smartapi-python pyotp dhanhq
```

Run any script directly — if credentials are not set, it prints setup instructions:

```bash
python scripts/api_exploration/fyers_explorer.py
python scripts/api_exploration/amfi_mf_explorer.py      # no setup needed
python scripts/api_exploration/iima_ff_factors.py       # no setup needed
python scripts/api_exploration/nse_insider_scraper.py   # no setup needed
```

## Zerodha Kite — Why It's Excluded

Community research (May 2026) found:
- WebSocket "silent-dead" bug (Issue #229): ticks stop without firing `on_close`
- `market_protection` missing from PyPI for 22 days after SEBI made it mandatory
- `autobahn` dependency pinned to 2020 (v19.11.2)
- 25-month gap between SDK releases (Feb 2024 → Mar 2026)
- 0 of 28 open GitHub issues have Zerodha responses
- SEBI static IP mandate: all cloud-hosted bots need dedicated static IP
- ₹500/month for data while Fyers, Angel One, Dhan are free

**Better free alternatives: Fyers (documentation praised) or Dhan (best options data).**

## SEBI Static IP Note (Dhan / All Brokers)

SEBI mandated static IP whitelisting for all API *order placement* from April 2026.
**Read-only data access (what StockAgent needs) does NOT require a static IP.**
Static IP enforcement is at the trading/order API level only.

If you later add order execution features on Railway, use QuotaGuard Shield (~₹1,500/year).

## Paid APIs Worth Evaluating

| API | Cost | Why Paid Might Be Worth It |
|---|---|---|
| **AlphaStreet** | Enterprise | Real Indian earnings call transcripts, speaker-level Q&A |
| **Sensibull** | Freemium | IV surface, Max Pain, PCR charting for NSE options |
| **EarningsAPI.com** | ~$20/month | Programmatic transcript access if free tier is too limited |
