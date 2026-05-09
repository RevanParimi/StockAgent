"""
prompts/oilgas/management.py
==========================
Prompt templates for the Oil & Gas Management agent.
Framework source: sector_analysis_v4_final.html — Oil & Gas > Management pillar
"""

SYSTEM_PROMPT = """You are a governance analyst for Indian oil & gas companies."""

ANALYSIS_PROMPT = """Analyse the Management outlook for Indian oil & gas company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **PSU vs Private Management** — Assess and score this dimension for {ticker} ({company_name}).

2. **Capital Allocation & Capex** — Assess and score this dimension for {ticker} ({company_name}).

3. **RPT & Subsidiary** — Assess and score this dimension for {ticker} ({company_name}).

4. **ESG & Carbon Goals** — Assess and score this dimension for {ticker} ({company_name}).

5. **Succession** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "management",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "psu_private": <float>,
    "capital_allocation": <float>,
    "rpt": <float>,
    "esg_carbon": <float>,
    "succession": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} management capital allocation ESG {year}",
    "{company_name} RPT subsidiary {year}",
]
