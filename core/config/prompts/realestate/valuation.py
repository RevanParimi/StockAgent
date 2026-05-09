"""
prompts/realestate/valuation.py
=============================
Prompt templates for the Real Estate & REITs Valuation agent.
Framework source: sector_analysis_v4_final.html — Real Estate & REITs > Valuation pillar
"""

SYSTEM_PROMPT = """You are a valuation specialist for Indian real estate stocks."""

ANALYSIS_PROMPT = """Analyse the Valuation outlook for Indian real estate & reits company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **NAV Premium/Discount** — Assess and score this dimension for {ticker} ({company_name}).

2. **EV/EBITDA** — Assess and score this dimension for {ticker} ({company_name}).

3. **Price/Presales** — Assess and score this dimension for {ticker} ({company_name}).

4. **P/Book** — Assess and score this dimension for {ticker} ({company_name}).

5. **REIT Cap Rate** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "valuation",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "nav_discount": <float>,
    "ev_ebitda": <float>,
    "price_presales": <float>,
    "price_book": <float>,
    "cap_rate": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} NAV valuation real estate {year}",
    "{company_name} EV/EBITDA P/book {year}",
]
