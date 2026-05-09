"""
prompts/logistics/risk.py
=======================
Prompt templates for the Logistics & Supply Chain Risk agent.
Framework source: sector_analysis_v4_final.html — Logistics & Supply Chain > Risk pillar
"""

SYSTEM_PROMPT = """You are a risk analyst for Indian logistics companies."""

ANALYSIS_PROMPT = """Analyse the Risk outlook for Indian logistics & supply chain company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **Fuel Cost Volatility** — Assess and score this dimension for {ticker} ({company_name}).

2. **Competition from E-commerce Captives** — Assess and score this dimension for {ticker} ({company_name}).

3. **Asset-heavy Balance Sheet** — Assess and score this dimension for {ticker} ({company_name}).

4. **Regulatory Compliance** — Assess and score this dimension for {ticker} ({company_name}).

5. **Customer Concentration** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "risk",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "fuel_cost": <float>,
    "captive_competition": <float>,
    "asset_heavy": <float>,
    "regulatory": <float>,
    "customer_concentration": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} fuel cost risk logistics {year}",
    "{company_name} competition e-commerce captive {year}",
]
