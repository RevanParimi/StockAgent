---
name: market-domain
description: Use when work touches Indian market structure, instrument types, market microstructure, SEBI compliance, disclaimers, or any logic that depends on understanding how NSE/BSE/MCX actually work. Triggers: equities, F&O, options chain, OI, futures, commodities, currency, ETFs, mutual funds, debt instruments, market hours, settlement, corporate actions, SEBI, RBI, RA/IA, disclaimer, regime, FII/DII, expiry. Not for general LLM or signal-combination logic — those have their own skills.
---

# Market Domain (India)

Indian market structure, instrument taxonomy, regulatory context. The skill that ensures the tool doesn't generate output that's nonsensical or non-compliant for Indian markets.

Read `PROJECT.md` for asset scope (which classes are active), output mode (recommendation vs research vs execution), and SEBI registration status.

## Exchanges and segments

NSE and BSE for equities and equity derivatives. NSE dominates volume in equity F&O and is the default unless `PROJECT.md` says otherwise. MCX for commodities. NSE currency derivatives for FX. CBLO/G-Sec markets for debt. Mutual funds transact through AMCs and platforms (BSE StAR MF, NSE NMF II), not exchange order books.

## Market hours (IST)

Pre-open: 09:00–09:15 (equities). Continuous: 09:15–15:30 (equities and equity F&O). Closing session: 15:40–16:00 (equities). Currency: 09:00–17:00. Commodities: 09:00–23:30 (varies by contract; agri commodities close earlier). Mutual funds use NAV cutoffs, not real-time pricing — 15:00 cutoff for equity schemes for same-day NAV.

## Instrument taxonomy

**Equities** — cash market shares. T+1 settlement. Series EQ (rolling), BE (trade-to-trade), BZ (suspended/illiquid).

**Equity F&O** — index futures and options (Nifty, Bank Nifty, FinNifty, Midcap Nifty, Sensex), single-stock futures and options on the F&O list (~180 stocks). Lot sizes vary per contract. Weekly expiry on indices (different days for different indices), monthly expiry on stocks. Last Thursday of the month is the historical monthly expiry day; weekly schedules have shifted multiple times — confirm current schedule from exchange before relying on memory.

**Commodities** — bullion (gold, silver), energy (crude, natgas), base metals, agri. Different contract sizes and tick values. Some agri contracts have delivery logistics that retail can't handle.

**Currency** — USDINR, EURINR, GBPINR, JPYINR. Tight spreads, regulated lot sizes.

**ETFs** — trade like equities. Liquidity varies wildly; many have wide spreads. Index ETFs (Nifty BeES, BankBeES) liquid; thematic ETFs often not.

**Mutual funds** — lump sum / SIP / STP / SWP. Direct vs Regular plans. Exit loads. ELSS lock-in. Categorization per SEBI (large-cap, flexi-cap, mid-cap, small-cap, etc. — defined categories with prescribed allocation rules).

**Debt** — G-Secs, T-Bills, SDLs, corporate bonds, debt MFs. Yield curve, duration, credit risk all matter. Retail access mostly through debt MFs and the RBI Retail Direct platform for G-Secs.

## Microstructure facts that matter

Circuit limits exist on stocks (5/10/20%) and on indices (10/15/20% with trading halts). Upper/lower circuits stop trading in a stock; building this into signal logic is mandatory. Auction sessions handle settlement shortfalls. T+1 settlement means today's buy is delivered tomorrow's morning; affects strategy P&L calculations. STT, exchange charges, GST, SEBI charges, stamp duty all eat into returns — tax treatment differs for equity (LTCG/STCG with 1-year boundary) vs F&O (business income) vs debt (slab rate or indexation).

## Signals specific to Indian markets

OI buildup and unwinding, PCR (put-call ratio), IV percentile, max pain — for index and stock options. FII/DII daily activity. Block deals and bulk deals. Promoter holding changes, pledged shares. MF holdings changes (reported monthly). Corporate actions: dividends, splits, bonuses, rights, buybacks, mergers. RBI policy (repo, CRR, SLR), inflation prints, GDP, IIP, PMI for macro. Sector-specific: GST collections, auto sales monthly, banking credit growth, IT export numbers.

## SEBI compliance baseline

The single most important compliance fork is whether the tool gives **personalized recommendations** ("buy 100 shares of HDFC Bank") or **non-personalized research / education** ("HDFC Bank's loan book is growing at X%").

Personalized recommendations to clients require SEBI Investment Advisor (IA) registration with strict requirements (qualifications, fees structure, fiduciary duty, audit). Non-personalized research output to a general audience requires SEBI Research Analyst (RA) registration. Distributing/executing through a broker is yet another framework.

If `PROJECT.md` does not specify registration status, default to **research/educational framing** — describe, don't prescribe. Avoid "buy now" / "target X" / "stop loss Y" phrasings unless RA registration is confirmed and the report includes the mandated disclosures.

Mandatory disclaimers for any registered output: registration number, conflict-of-interest disclosure, "investments are subject to market risks" language, past-performance disclaimer. Exact text comes from the RA/IA registration paperwork — do not invent disclaimer text; reference the canonical version stored in the repo (location in `PROJECT.md`).

## Market regimes

Bull / bear / sideways is the crude version. More useful: trending vs mean-reverting (different signals work in each), low-vol vs high-vol (option strategies flip), rising-rate vs falling-rate (sector rotation flips), risk-on vs risk-off (FII flow direction). Regime detection isn't optional for a multi-asset, multi-sector tool — signals that work in one regime fail in another.

## When you don't know

Indian market rules change. Lot sizes get revised. Expiry days shift. Tax rules change in every Union Budget. New asset classes get added (REITs, InvITs, sovereign gold bonds). If a fact is time-sensitive and you don't have current data, say so — don't quote yesterday's rule as today's. The exchange websites (nseindia.com, bseindia.com) and SEBI circulars are the source of truth.

## Hand-off triggers

- Task is about combining or weighting market signals → also load `signal-engineering`
- Task is about how the tool actually computes or stores this data → also load `system-design-engineer`
- Task involves LLM-generated content that references regulated areas → also load `ai-engineer` for prompt-level disclaimer enforcement

---

## This project

### Supported tickers (automobile, currently active)

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

BFSI/IT/Renewable tickers are not yet registered anywhere in the codebase — must be added when Phase 2b wires those sectors.

### yfinance conventions

- All NSE tickers need `.NS` suffix: `MARUTI` → `MARUTI.NS`
- Setting: `YFINANCE_SUFFIX = ".NS"` in `config/settings/base.py`
- Helper: `_nse_ticker(ticker)` in both `fetchers/fundamentals.py` and `indicators/fetcher.py`
- Data is ~15 min delayed — **not real-time**; suitable for positional/long-term analysis only

### Macro tickers used (yfinance, no API key needed)

| What | Ticker | Used for |
|---|---|---|
| WTI Crude | `CL=F` | Raw materials, risk/macro agents |
| Brent Crude | `BZ=F` | Polymer cost proxy |
| INR/USD | `INR=X` | Macro exposure |
| Steel ETF | `SLX` | Steel price proxy |
| Aluminium | `AA` | Alcoa as aluminium proxy |
| Platinum ETF | `PPLT` | Catalytic converters |
| Palladium ETF | `PALL` | Catalytic converters |
| Nifty Auto Index | `^CNXAUTO` | Peer correlation / beta |

### RBI repo rate — hardcoded

`data/macro.py → get_rbi_repo_rate()` returns a static dict. **There is no live RBI API.** This must be manually updated when RBI changes rates. It's the only hardcoded fundamental fact in the pipeline.

### Primary Indian auto data sources (not APIs — Serper searches)

- **FADA** (Federation of Automobile Dealers Associations) — monthly retail dispatch: `fada.in/news/monthly-reports`
- **SIAM** (Society of Indian Automobile Manufacturers) — wholesale dispatch: `siam.in/statistics.aspx`
- **Vahan** — EV registration data: `vahan.parivahan.gov.in`
- **DGFT** — export data: `dgft.gov.in`

These are fetched via Serper search queries, not direct scraping. The `CONTEXT_SEARCH_QUERIES` in each prompt module defines what to search.

### Sector-specific KPIs the agents score

**BFSI:** NPA (gross/net), PCR, NIM, CASA ratio, CRAR/CET1, RoA, RoE, credit cost, DSCR
**IT:** TCV deal wins, attrition %, constant-currency revenue growth, EBIT margin, bench utilisation
**Renewable:** CUF (capacity utilisation factor), EBITDA/MW, DSCR ≥1.2x, DISCOM receivables aging, EV/MW

### Compliance — current posture

No SEBI registration. All output must be framed as research/educational. Avoid: "buy X," "target price Y," "stop loss Z." Safe framing: "scores suggest," "analysis indicates," "research output."

The `FinalReport.verdict` field (STRONG BUY etc.) is an **analytical label**, not an investment recommendation. If the tool ever goes multi-user or public, this needs RA registration + mandatory disclaimers before the verdict field can be user-facing.
