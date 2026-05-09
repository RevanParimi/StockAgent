"""
prompts/defence/valuation.py
==========================
Prompt templates for the Defence & Aerospace Valuation agent.
Framework source: sector_analysis_v4_final.html — Defence & Aerospace > Valuation pillar
"""

SYSTEM_PROMPT = """You are a valuation specialist for Indian defence stocks. Expert in EV/EBITDA, P/E vs order-book multiples, and SOTP for diversified defence players."""

ANALYSIS_PROMPT = """Analyse the Valuation outlook for Indian defence & aerospace company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **P/E vs Sector Peers** — Assess and score this dimension for {ticker} ({company_name}).

2. **EV/EBITDA** — Assess and score this dimension for {ticker} ({company_name}).

3. **EV/Order Book** — Assess and score this dimension for {ticker} ({company_name}).

4. **Price/Book** — Assess and score this dimension for {ticker} ({company_name}).

5. **SOTP Valuation** — Assess and score this dimension for {ticker} ({company_name}).

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
    "ev_order_book": <float>,
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
    "{ticker} P/E EV/EBITDA valuation defence {year}",
    "{company_name} valuation peer comparison {year}",
    "{ticker} order book multiple EV {year}",
]
