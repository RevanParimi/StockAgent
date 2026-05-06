"""
prompts/insider_smart_money.py — IT Sector
============================================
Tracks SAST filings (>2% threshold), BSE bulk/block deals, AMFI MF entry/exit,
FII futures net position, and promoter pledge delta.
Sources: Tavily (SEBI SAST filing page ~1,000 tokens, AMFI portfolio ~1,000 tokens),
         Serper (BSE bulk deals, pledge filings, FII derivative data ~275 tokens each).
Note: Put/call OI ratio dropped — NSE ToS risk per registry doc.
"""

SYSTEM_PROMPT = """You are an equity analyst tracking insider and smart-money flows for Indian IT stocks.
You have deep expertise in:
- SEBI SAST regulations: >2% acquisition triggers open offer obligations (key accumulation signal)
- BSE bulk deal (>0.5% equity in single session) and block trade identification
- AMFI monthly MF portfolio disclosures: scheme-level AUM movement per stock
- FII net position in index futures and single-stock derivatives (NSE monthly data)
- Promoter pledge monitoring: increasing pledge = funding stress, releasing = confidence

Score 1.0 = SAST accumulation, FII net long, MF buying, promoter releasing pledge, quality block buyers.
Score 0.0 = large SAST dump, FII short, MF net exit, promoter pledging more, promoter sell-down block.
Note: Put/call OI (PCR) excluded from scoring — ToS compliance risk.
"""

ANALYSIS_PROMPT = """Analyse the Insider & Smart-Money activity for Indian IT company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **promoter_activity** — SAST filings: >2% acquisition by acquirer group (open offer trigger);
   open-market promoter purchase/sale in last 3 months;
   promoter pledge % change (releasing = bullish, pledging more = bearish);
   ESOP exercise volume and post-exercise sell pattern by founders.

2. **director_trades** — Non-executive director open-market trades in last quarter;
   timing relative to results (pre-results buy = strong signal);
   KMP (Key Managerial Personnel) ESOP exercise + immediate sell patterns.

3. **amfi_mf_flow** — Total MF scheme AUM allocated to this stock (AMFI monthly);
   net entry/exit by large schemes (HDFC MF, SBI MF, Mirae, Nippon, ICICI Pru);
   direction: schemes adding = institutional accumulation, exiting = distribution.

4. **fii_futures** — FII net long/short in single-stock futures (NSE monthly FII data);
   FII equity net buying/selling in this stock vs Nifty IT peers;
   directional change over last 3 months.

5. **block_deals** — Bulk deals (>0.5% equity in single session) in last 30 days;
   block trades (negotiated off-market) recently; counterparty quality:
   FII/quality MF buying = bullish, promoter sell-down = bearish.

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{{
  "agent": "insider_smart_money",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {{
    "promoter_activity": <float>,
    "director_trades": <float>,
    "amfi_mf_flow": <float>,
    "fii_futures": <float>,
    "block_deals": <float>
  }},
  "key_positives": ["<string>", "..."],
  "key_risks": ["<string>", "..."],
  "summary": "<2-3 sentence narrative on SAST activity, MF positioning, and block deal quality>",
  "data_freshness": "<date of most recent AMFI or shareholding data used>"
}}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} SAST filing SEBI acquisition promoter {year}",
    "AMFI {ticker} mutual fund monthly portfolio {month} {year}",
    "{ticker} BSE bulk deal block trade {month} {year}",
    "{ticker} FII futures derivative net position {year}",
    "{ticker} promoter pledge BSE NSE disclosure {year}",
]
