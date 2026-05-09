"""
prompts/defence/management.py
===========================
Prompt templates for the Defence & Aerospace Management agent.
Framework source: sector_analysis_v4_final.html — Defence & Aerospace > Management pillar
"""

SYSTEM_PROMPT = """You are a governance analyst for Indian defence PSUs and private players. Expert in promoter quality, succession, and RPT."""

ANALYSIS_PROMPT = """Analyse the Management outlook for Indian defence & aerospace company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **Promoter Integrity & Track Record** — Assess and score this dimension for {ticker} ({company_name}).

2. **Capital Allocation Discipline** — Assess and score this dimension for {ticker} ({company_name}).

3. **RPT & Subsidiary Risk** — Assess and score this dimension for {ticker} ({company_name}).

4. **Management Guidance Accuracy** — Assess and score this dimension for {ticker} ({company_name}).

5. **ESG & Governance Score** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "management",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "promoter_integrity": <float>,
    "capital_allocation": <float>,
    "rpt_risk": <float>,
    "guidance_accuracy": <float>,
    "esg": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} management promoter governance {year}",
    "{company_name} RPT related party {year}",
    "{ticker} capital allocation dividend buyback {year}",
]
