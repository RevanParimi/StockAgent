"""
prompts/fmcg/valuation.py
=======================
Prompt templates for the FMCG & Consumer Staples Valuation agent.
Framework source: sector_analysis_v4_final.html — FMCG & Consumer Staples > Valuation pillar
"""

SYSTEM_PROMPT = """You are a valuation specialist for Indian FMCG stocks. Expert in premium P/E multiples and DCF for consumer franchises."""

ANALYSIS_PROMPT = """Analyse the Valuation outlook for Indian fmcg & consumer staples company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **P/E vs FMCG Peers** — Assess and score this dimension for {ticker} ({company_name}).

2. **EV/EBITDA** — Assess and score this dimension for {ticker} ({company_name}).

3. **Price/FCF** — Assess and score this dimension for {ticker} ({company_name}).

4. **Dividend Yield** — Assess and score this dimension for {ticker} ({company_name}).

5. **DCF Intrinsic Value** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "valuation",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "pe": <float>,
    "ev_ebitda": <float>,
    "price_fcf": <float>,
    "div_yield": <float>,
    "dcf": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} P/E EV/EBITDA FMCG valuation {year}",
    "{company_name} vs HUL ITC multiple {year}",
]
