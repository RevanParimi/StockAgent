"""
prompts/hospitality/valuation.py
==============================
Prompt templates for the Hospitality & Travel Valuation agent.
Framework source: sector_analysis_v4_final.html — Hospitality & Travel > Valuation pillar
"""

SYSTEM_PROMPT = """You are a valuation specialist for Indian hospitality stocks."""

ANALYSIS_PROMPT = """Analyse the Valuation outlook for Indian hospitality & travel company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **EV/EBITDA vs Peers** — Assess and score this dimension for {ticker} ({company_name}).

2. **EV/Room** — Assess and score this dimension for {ticker} ({company_name}).

3. **P/E Normalised** — Assess and score this dimension for {ticker} ({company_name}).

4. **Price/Book** — Assess and score this dimension for {ticker} ({company_name}).

5. **Replacement Cost** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "valuation",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "ev_ebitda": <float>,
    "ev_room": <float>,
    "pe_normalised": <float>,
    "price_book": <float>,
    "replacement_cost": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} EV/EBITDA hospitality valuation {year}",
    "{company_name} EV per room {year}",
]
