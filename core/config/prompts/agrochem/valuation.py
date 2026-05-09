"""
prompts/agrochem/valuation.py
===========================
Prompt templates for the Agrochemicals & Fertilizers Valuation agent.
Framework source: sector_analysis_v4_final.html — Agrochemicals & Fertilizers > Valuation pillar
"""

SYSTEM_PROMPT = """You are a valuation specialist for Indian agrochem stocks."""

ANALYSIS_PROMPT = """Analyse the Valuation outlook for Indian agrochemicals & fertilizers company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **P/E vs Peers** — Assess and score this dimension for {ticker} ({company_name}).

2. **EV/EBITDA** — Assess and score this dimension for {ticker} ({company_name}).

3. **EV/Sales** — Assess and score this dimension for {ticker} ({company_name}).

4. **Price/Book** — Assess and score this dimension for {ticker} ({company_name}).

5. **Pipeline DCF** — Assess and score this dimension for {ticker} ({company_name}).

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
    "ev_sales": <float>,
    "price_book": <float>,
    "pipeline_dcf": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} P/E EV/EBITDA agrochem valuation {year}",
    "{company_name} pipeline valuation {year}",
]
