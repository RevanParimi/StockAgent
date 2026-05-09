"""
prompts/infra/valuation.py
========================
Prompt templates for the Infrastructure & Construction Valuation agent.
Framework source: sector_analysis_v4_final.html — Infrastructure & Construction > Valuation pillar
"""

SYSTEM_PROMPT = """You are a valuation specialist for Indian infra stocks. Expert in EV/Order Book and P/E for construction."""

ANALYSIS_PROMPT = """Analyse the Valuation outlook for Indian infrastructure & construction company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **EV/Order Book** — Assess and score this dimension for {ticker} ({company_name}).

2. **P/E vs Peers** — Assess and score this dimension for {ticker} ({company_name}).

3. **EV/EBITDA** — Assess and score this dimension for {ticker} ({company_name}).

4. **Price/Book** — Assess and score this dimension for {ticker} ({company_name}).

5. **SOTP** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "valuation",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "ev_order_book": <float>,
    "pe": <float>,
    "ev_ebitda": <float>,
    "price_book": <float>,
    "sotp": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} EV order book valuation infra {year}",
    "{company_name} P/E peer comparison {year}",
]
