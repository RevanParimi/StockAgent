"""
prompts/pharma/valuation.py
=========================
Prompt templates for the Pharmaceuticals Valuation agent.
Framework source: sector_analysis_v4_final.html — Pharmaceuticals > Valuation pillar
"""

SYSTEM_PROMPT = """You are a valuation specialist for Indian pharma stocks."""

ANALYSIS_PROMPT = """Analyse the Valuation outlook for Indian pharmaceuticals company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **P/E vs Pharma Peers** — Assess and score this dimension for {ticker} ({company_name}).

2. **EV/EBITDA** — Assess and score this dimension for {ticker} ({company_name}).

3. **EV/R&D Adjusted** — Assess and score this dimension for {ticker} ({company_name}).

4. **Price/FCF** — Assess and score this dimension for {ticker} ({company_name}).

5. **Pipeline NPV** — Assess and score this dimension for {ticker} ({company_name}).

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
    "ev_rd": <float>,
    "price_fcf": <float>,
    "pipeline_npv": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} P/E EV/EBITDA pharma valuation {year}",
    "{company_name} pipeline NPV valuation {year}",
]
