"""
prompts/pharma/risk.py
====================
Prompt templates for the Pharmaceuticals Risk agent.
Framework source: sector_analysis_v4_final.html — Pharmaceuticals > Risk pillar
"""

SYSTEM_PROMPT = """You are a risk analyst for Indian pharma companies. Expert in FDA 483s, USFDA import alerts, patent cliffs, and pricing pressure."""

ANALYSIS_PROMPT = """Analyse the Risk outlook for Indian pharmaceuticals company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **USFDA 483 & Warning Letter Risk** — Assess and score this dimension for {ticker} ({company_name}).

2. **Patent Cliff Exposure** — Assess and score this dimension for {ticker} ({company_name}).

3. **Pricing Pressure in US Generics** — Assess and score this dimension for {ticker} ({company_name}).

4. **Regulatory Compliance Cost** — Assess and score this dimension for {ticker} ({company_name}).

5. **Single-Product Concentration** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "risk",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "fda_risk": <float>,
    "patent_cliff": <float>,
    "pricing_pressure": <float>,
    "compliance_cost": <float>,
    "concentration": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} USFDA 483 warning letter {year}",
    "{company_name} patent cliff risk {year}",
    "{ticker} US generics pricing {year}",
]
