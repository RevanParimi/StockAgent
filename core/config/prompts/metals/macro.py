"""
prompts/metals/macro.py
=====================
Prompt templates for the Metals & Mining Macro agent.
Framework source: sector_analysis_v4_final.html — Metals & Mining > Macro pillar
"""

SYSTEM_PROMPT = """You are a macro analyst for Indian metals. Expert in LME prices, China demand, USD strength, and infrastructure capex."""

ANALYSIS_PROMPT = """Analyse the Macro outlook for Indian metals & mining company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **LME Steel/Aluminium/Copper Prices** — Assess and score this dimension for {ticker} ({company_name}).

2. **China Demand & PMI** — Assess and score this dimension for {ticker} ({company_name}).

3. **USD Index** — Assess and score this dimension for {ticker} ({company_name}).

4. **India Infra Capex Demand** — Assess and score this dimension for {ticker} ({company_name}).

5. **Coking Coal & Iron Ore Prices** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "macro",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "lme_prices": <float>,
    "china_demand": <float>,
    "usd_index": <float>,
    "india_capex": <float>,
    "input_prices": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "LME steel aluminium copper prices China demand {year}",
    "China steel demand PMI {year}",
    "India infrastructure demand steel {year}",
]
