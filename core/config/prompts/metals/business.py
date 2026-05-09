"""
prompts/metals/business.py
========================
Prompt templates for the Metals & Mining Business agent.
Framework source: sector_analysis_v4_final.html — Metals & Mining > Business pillar
"""

SYSTEM_PROMPT = """You are a metals & mining analyst for Indian companies. Expert in mining integration, product mix, capacity utilisation, and exports."""

ANALYSIS_PROMPT = """Analyse the Business outlook for Indian metals & mining company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **Captive Mining Integration** — Assess and score this dimension for {ticker} ({company_name}).

2. **Capacity & Utilisation Rate** — Assess and score this dimension for {ticker} ({company_name}).

3. **Product Mix (Flat/Long/Special)** — Assess and score this dimension for {ticker} ({company_name}).

4. **Export Revenue Share** — Assess and score this dimension for {ticker} ({company_name}).

5. **Downstream Value Addition** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "business",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "mining_integration": <float>,
    "capacity_utilisation": <float>,
    "product_mix": <float>,
    "export_share": <float>,
    "downstream": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} mining integration capacity {year}",
    "{company_name} product mix flat long steel {year}",
    "{ticker} export revenue {year}",
]
