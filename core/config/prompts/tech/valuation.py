"""
prompts/tech/valuation.py
=======================
Prompt templates for the Information Technology Valuation agent.
Framework source: sector_analysis_v4_final.html — Information Technology > Valuation pillar
"""

SYSTEM_PROMPT = """You are a valuation specialist for Indian IT stocks. Expert in P/E, EV/EBITDA, PEG ratio, and premium/discount to TCS."""

ANALYSIS_PROMPT = """Analyse the Valuation outlook for Indian information technology company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **P/E vs Sector Peers** — Assess and score this dimension for {ticker} ({company_name}).

2. **EV/EBITDA** — Assess and score this dimension for {ticker} ({company_name}).

3. **PEG Ratio** — Assess and score this dimension for {ticker} ({company_name}).

4. **Price/FCF** — Assess and score this dimension for {ticker} ({company_name}).

5. **Premium to TCS** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "valuation",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "pe_ratio": <float>,
    "ev_ebitda": <float>,
    "peg_ratio": <float>,
    "price_fcf": <float>,
    "tcs_premium": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} P/E EV/EBITDA IT sector valuation {year}",
    "{company_name} vs TCS Infosys multiple {year}",
]
