"""
prompts/logistics/valuation.py
============================
Prompt templates for the Logistics & Supply Chain Valuation agent.
Framework source: sector_analysis_v4_final.html — Logistics & Supply Chain > Valuation pillar
"""

SYSTEM_PROMPT = """You are a valuation specialist for Indian logistics stocks."""

ANALYSIS_PROMPT = """Analyse the Valuation outlook for Indian logistics & supply chain company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **EV/EBITDA vs Peers** — Assess and score this dimension for {ticker} ({company_name}).

2. **P/E** — Assess and score this dimension for {ticker} ({company_name}).

3. **EV/Revenue** — Assess and score this dimension for {ticker} ({company_name}).

4. **Price/Book** — Assess and score this dimension for {ticker} ({company_name}).

5. **DCF** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "valuation",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "ev_ebitda": <float>,
    "pe": <float>,
    "ev_revenue": <float>,
    "price_book": <float>,
    "dcf": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} EV/EBITDA logistics valuation {year}",
    "{company_name} P/E vs peers {year}",
]
