"""
prompts/fmcg/macro.py
===================
Prompt templates for the FMCG & Consumer Staples Macro agent.
Framework source: sector_analysis_v4_final.html — FMCG & Consumer Staples > Macro pillar
"""

SYSTEM_PROMPT = """You are a macro analyst for Indian FMCG sector. Expert in rural demand, commodity input costs, inflation, and GST."""

ANALYSIS_PROMPT = """Analyse the Macro outlook for Indian fmcg & consumer staples company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **Rural Demand & Monsoon** — Assess and score this dimension for {ticker} ({company_name}).

2. **Commodity Input Costs (Palm Oil, Wheat)** — Assess and score this dimension for {ticker} ({company_name}).

3. **CPI Inflation & Pricing Power** — Assess and score this dimension for {ticker} ({company_name}).

4. **GST & Regulatory** — Assess and score this dimension for {ticker} ({company_name}).

5. **Urban Consumption** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "macro",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "rural_demand": <float>,
    "commodity_costs": <float>,
    "inflation_pricing": <float>,
    "gst": <float>,
    "urban_consumption": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "India rural demand FMCG consumption {year}",
    "Palm oil wheat commodity prices India {year}",
    "India CPI inflation FMCG pricing {year}",
]
