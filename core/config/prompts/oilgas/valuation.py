"""
prompts/oilgas/valuation.py
=========================
Prompt templates for the Oil & Gas Valuation agent.
Framework source: sector_analysis_v4_final.html — Oil & Gas > Valuation pillar
"""

SYSTEM_PROMPT = """You are a valuation specialist for Indian oil & gas stocks."""

ANALYSIS_PROMPT = """Analyse the Valuation outlook for Indian oil & gas company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **EV/EBITDA vs Brent Cycle** — Assess and score this dimension for {ticker} ({company_name}).

2. **P/E** — Assess and score this dimension for {ticker} ({company_name}).

3. **EV/boe (Reserves)** — Assess and score this dimension for {ticker} ({company_name}).

4. **Price/Book** — Assess and score this dimension for {ticker} ({company_name}).

5. **Dividend Yield** — Assess and score this dimension for {ticker} ({company_name}).

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
    "ev_boe": <float>,
    "price_book": <float>,
    "div_yield": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} EV/EBITDA oil gas valuation Brent {year}",
    "{company_name} P/E reserve valuation {year}",
]
