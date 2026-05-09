"""
prompts/pharma/business.py
========================
Prompt templates for the Pharmaceuticals Business agent.
Framework source: sector_analysis_v4_final.html — Pharmaceuticals > Business pillar
"""

SYSTEM_PROMPT = """You are a pharma sector analyst for Indian pharmaceutical companies. Expert in US FDA pipeline, domestic formulations, API backward integration, and CDMO business."""

ANALYSIS_PROMPT = """Analyse the Business outlook for Indian pharmaceuticals company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **US FDA Pipeline & ANDA Filings** — Assess and score this dimension for {ticker} ({company_name}).

2. **Domestic Formulations Market Share** — Assess and score this dimension for {ticker} ({company_name}).

3. **API/CDMO Business** — Assess and score this dimension for {ticker} ({company_name}).

4. **Specialty/Branded Mix** — Assess and score this dimension for {ticker} ({company_name}).

5. **New Therapy Area Entry** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "business",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "us_pipeline": <float>,
    "domestic_share": <float>,
    "api_cdmo": <float>,
    "specialty_mix": <float>,
    "new_therapy": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} US FDA ANDA pipeline {year}",
    "{company_name} domestic formulations market share {year}",
    "{ticker} API CDMO business {year}",
]
