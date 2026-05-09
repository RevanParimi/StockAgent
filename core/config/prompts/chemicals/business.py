"""
prompts/chemicals/business.py
===========================
Prompt templates for the Specialty Chemicals Business agent.
Framework source: sector_analysis_v4_final.html — Specialty Chemicals > Business pillar
"""

SYSTEM_PROMPT = """You are a specialty chemicals analyst for Indian companies. Expert in import substitution, China+1 positioning, CRAMS/CDMO, and agrochemical AIs."""

ANALYSIS_PROMPT = """Analyse the Business outlook for Indian specialty chemicals company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **China+1 Market Share Gain** — Assess and score this dimension for {ticker} ({company_name}).

2. **CRAMS/CDMO Business** — Assess and score this dimension for {ticker} ({company_name}).

3. **Import Substitution Pipeline** — Assess and score this dimension for {ticker} ({company_name}).

4. **Customer Concentration** — Assess and score this dimension for {ticker} ({company_name}).

5. **New Product Pipeline** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "business",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "china_plus_1": <float>,
    "crams_cdmo": <float>,
    "import_substitution": <float>,
    "customer_concentration": <float>,
    "new_products": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} China+1 specialty chemicals CRAMS {year}",
    "{company_name} import substitution pipeline {year}",
    "{ticker} CDMO customer concentration {year}",
]
