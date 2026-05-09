"""
prompts/capgoods/management.py
============================
Prompt templates for the Capital Goods Management agent.
Framework source: sector_analysis_v4_final.html — Capital Goods > Management pillar
"""

SYSTEM_PROMPT = """You are a governance analyst for Indian capital goods companies."""

ANALYSIS_PROMPT = """Analyse the Management outlook for Indian capital goods company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **Promoter Quality** — Assess and score this dimension for {ticker} ({company_name}).

2. **Capital Allocation** — Assess and score this dimension for {ticker} ({company_name}).

3. **RPT** — Assess and score this dimension for {ticker} ({company_name}).

4. **Technology Partnerships** — Assess and score this dimension for {ticker} ({company_name}).

5. **ESG** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "management",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "promoter_quality": <float>,
    "capital_allocation": <float>,
    "rpt": <float>,
    "tech_partnerships": <float>,
    "esg": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} management promoter capital {year}",
    "{company_name} technology partnership RPT {year}",
]
