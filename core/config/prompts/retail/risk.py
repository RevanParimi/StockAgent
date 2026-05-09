"""
prompts/retail/risk.py
====================
Prompt templates for the Retail & Consumer Discretionary Risk agent.
Framework source: sector_analysis_v4_final.html — Retail & Consumer Discretionary > Risk pillar
"""

SYSTEM_PROMPT = """You are a risk analyst for Indian retail companies."""

ANALYSIS_PROMPT = """Analyse the Risk outlook for Indian retail & consumer discretionary company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **E-commerce Disruption** — Assess and score this dimension for {ticker} ({company_name}).

2. **High Rentals & Real Estate Cost** — Assess and score this dimension for {ticker} ({company_name}).

3. **Inventory Risk** — Assess and score this dimension for {ticker} ({company_name}).

4. **Seasonality** — Assess and score this dimension for {ticker} ({company_name}).

5. **Competition** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "risk",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "ecommerce_disruption": <float>,
    "rental_cost": <float>,
    "inventory_risk": <float>,
    "seasonality": <float>,
    "competition": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} e-commerce disruption rental risk {year}",
    "{company_name} inventory competition retail {year}",
]
