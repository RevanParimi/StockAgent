"""
prompts/metals/management.py
==========================
Prompt templates for the Metals & Mining Management agent.
Framework source: sector_analysis_v4_final.html — Metals & Mining > Management pillar
"""

SYSTEM_PROMPT = """You are a governance analyst for Indian metals companies."""

ANALYSIS_PROMPT = """Analyse the Management outlook for Indian metals & mining company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **Promoter Quality** — Assess and score this dimension for {ticker} ({company_name}).

2. **Capex Discipline** — Assess and score this dimension for {ticker} ({company_name}).

3. **RPT & Group Risk** — Assess and score this dimension for {ticker} ({company_name}).

4. **ESG & Environment Compliance** — Assess and score this dimension for {ticker} ({company_name}).

5. **Capital Allocation** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "management",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "promoter_quality": <float>,
    "capex_discipline": <float>,
    "rpt": <float>,
    "esg": <float>,
    "capital_allocation": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} management capex ESG {year}",
    "{company_name} RPT group risk {year}",
]
