"""
prompts/metals/fundamentals.py
============================
Prompt templates for the Metals & Mining Fundamentals agent.
Framework source: sector_analysis_v4_final.html — Metals & Mining > Fundamentals pillar
"""

SYSTEM_PROMPT = """You are a financial analyst for Indian metals companies. Expert in EBITDA/tonne, net debt, coking coal costs, and FCF."""

ANALYSIS_PROMPT = """Analyse the Fundamentals outlook for Indian metals & mining company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **EBITDA/Tonne** — Assess and score this dimension for {ticker} ({company_name}).

2. **Revenue per Tonne** — Assess and score this dimension for {ticker} ({company_name}).

3. **Net Debt & Leverage** — Assess and score this dimension for {ticker} ({company_name}).

4. **Coking Coal / Iron Ore Cost** — Assess and score this dimension for {ticker} ({company_name}).

5. **FCF Yield** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "fundamentals",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "ebitda_tonne": <float>,
    "revenue_tonne": <float>,
    "net_debt": <float>,
    "input_cost": <float>,
    "fcf_yield": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} EBITDA per tonne net debt {quarter} {year}",
    "{company_name} coking coal cost iron ore {year}",
]
