"""
prompts/hospitality/management.py
===============================
Prompt templates for the Hospitality & Travel Management agent.
Framework source: sector_analysis_v4_final.html — Hospitality & Travel > Management pillar
"""

SYSTEM_PROMPT = """You are a governance analyst for Indian hospitality companies."""

ANALYSIS_PROMPT = """Analyse the Management outlook for Indian hospitality & travel company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **Brand Strategy & Expansion** — Assess and score this dimension for {ticker} ({company_name}).

2. **Capital Allocation (Owned vs Managed)** — Assess and score this dimension for {ticker} ({company_name}).

3. **RPT** — Assess and score this dimension for {ticker} ({company_name}).

4. **Management Quality** — Assess and score this dimension for {ticker} ({company_name}).

5. **ESG** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "management",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "brand_strategy": <float>,
    "capital_allocation": <float>,
    "rpt": <float>,
    "management_quality": <float>,
    "esg": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} management brand expansion {year}",
    "{company_name} capital allocation RPT {year}",
]
