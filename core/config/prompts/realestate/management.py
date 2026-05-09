"""
prompts/realestate/management.py
==============================
Prompt templates for the Real Estate & REITs Management agent.
Framework source: sector_analysis_v4_final.html — Real Estate & REITs > Management pillar
"""

SYSTEM_PROMPT = """You are a governance analyst for Indian real estate developers."""

ANALYSIS_PROMPT = """Analyse the Management outlook for Indian real estate & reits company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **Promoter Track Record & Delivery** — Assess and score this dimension for {ticker} ({company_name}).

2. **Capital Allocation** — Assess and score this dimension for {ticker} ({company_name}).

3. **RPT & Land Deals** — Assess and score this dimension for {ticker} ({company_name}).

4. **Corporate Governance** — Assess and score this dimension for {ticker} ({company_name}).

5. **ESG** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "management",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "promoter_delivery": <float>,
    "capital_allocation": <float>,
    "rpt": <float>,
    "governance": <float>,
    "esg": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} promoter track record delivery {year}",
    "{company_name} RPT land deals {year}",
]
