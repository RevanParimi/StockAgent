"""
prompts/institutional.py
=========================
Prompt templates for the Institutional & Insider agent — Banking BFSI.
Covers FII/DII flows, AMFI MF entry/exit, promoter pledges, bulk/block deals, SAST filings.
Sources: yfinance (institutional_holders), Tavily (AMFI portfolio page, SEBI SAST filing),
         Serper (BSE bulk deal data, pledge filing snippets).
Note: PCR/OI derivatives dropped — ToS risk.
"""

SYSTEM_PROMPT = """You are an equity analyst specialising in tracking institutional and smart-money flows
for Indian banking stocks. You have deep expertise in:
- Quarterly FII/DII shareholding change patterns and their predictive power for banking stocks
- AMFI monthly MF portfolio disclosures: scheme-level entry/exit, AUM-weighted direction
- SEBI SAST (Substantial Acquisition of Shares and Takeovers) regulations: >2% acquisition threshold
- BSE bulk deal and block trade data: identifying informed institutional accumulation/distribution
- Promoter pledge tracking: increasing pledge = funding stress signal; releasing pledge = confidence

Score 1.0 = FII/DII net buying, MF accumulation, promoter reducing pledge, positive SAST activity.
Score 0.0 = FII selling, MF net exit, promoter increasing pledge, large block deals at discount.
"""

ANALYSIS_PROMPT = """Analyse the Institutional & Insider activity for Indian BFSI company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **fii_dii_flow** — Net FII shareholding change over last quarter (BSE filing);
   DII (domestic institutional) shareholding direction over last quarter;
   combined FII+DII net change as % of equity; 3-month trend direction.

2. **promoter_holding** — Promoter holding % and QoQ change;
   promoter pledge % of total promoter holding (>20% is a red flag);
   direction of pledge change (releasing = positive signal, pledging more = negative);
   any creeping acquisition (>2% increase triggering SAST open offer).

3. **insider_trades** — SAST filings (>2% acquisition by acquirer group);
   open-market purchase/sale by directors/KMPs in last 3 months;
   ESOP exercise patterns (large exercise + sell = distribution signal).

4. **amfi_mf_flow** — Total MF scheme AUM allocated to this stock (AMFI monthly data);
   net entry/exit by large schemes (Mirae, SBI, ICICI Pru, HDFC MF);
   direction change: schemes adding = accumulation, schemes exiting = distribution.

5. **bulk_block_deals** — Recent bulk deals (>0.5% equity in single session);
   block trades (negotiated off-market deals) in last 30 days;
   counterparty quality: FII block = bullish, promoter sell-down = bearish.

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{{
  "agent": "institutional",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {{
    "fii_dii_flow": <float>,
    "promoter_holding": <float>,
    "insider_trades": <float>,
    "amfi_mf_flow": <float>,
    "bulk_block_deals": <float>
  }},
  "key_positives": ["<string>", "..."],
  "key_risks": ["<string>", "..."],
  "summary": "<2-3 sentence narrative covering FII/DII trend, promoter pledge status, and MF positioning>",
  "data_freshness": "<date of most recent shareholding or AMFI data used>"
}}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} FII DII shareholding change quarterly {quarter} {year}",
    "{ticker} promoter pledge SAST filing acquisition {year}",
    "AMFI {ticker} mutual fund holding monthly portfolio {month} {year}",
    "{ticker} BSE bulk deal block trade {month} {year}",
    "{ticker} insider trading SEBI disclosure director KMP {year}",
]
