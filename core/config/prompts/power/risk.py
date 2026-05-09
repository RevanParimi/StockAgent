"""
prompts/power/risk.py
===================
Prompt templates for the Power & Utilities Risk agent.
Framework source: sector_analysis_v4_final.html — Power & Utilities > Risk pillar
"""

SYSTEM_PROMPT = """You are a risk analyst for Indian power companies."""

ANALYSIS_PROMPT = """Analyse the Risk outlook for Indian power & utilities company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **Fuel Supply & Linkage Risk** — Assess and score this dimension for {ticker} ({company_name}).

2. **DISCOM Payment Delays** — Assess and score this dimension for {ticker} ({company_name}).

3. **Regulatory Tariff Risk** — Assess and score this dimension for {ticker} ({company_name}).

4. **Plant Breakdown & Availability** — Assess and score this dimension for {ticker} ({company_name}).

5. **Debt & Refinancing** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "risk",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "fuel_linkage": <float>,
    "discom_payment": <float>,
    "tariff_risk": <float>,
    "plant_availability": <float>,
    "debt": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} fuel linkage DISCOM payment risk {year}",
    "{company_name} plant availability tariff risk {year}",
]
