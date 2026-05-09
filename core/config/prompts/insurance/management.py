"""
prompts/insurance/management.py
=============================
Prompt templates for the Insurance Management agent.
Framework source: sector_analysis_v4_final.html — Insurance > Management pillar
"""

SYSTEM_PROMPT = """You are a governance analyst for Indian insurance companies."""

ANALYSIS_PROMPT = """Analyse the Management outlook for Indian insurance company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **MD Track Record** — Assess and score this dimension for {ticker} ({company_name}).

2. **Capital Allocation** — Assess and score this dimension for {ticker} ({company_name}).

3. **RPT with Promoter** — Assess and score this dimension for {ticker} ({company_name}).

4. **IRDAI Compliance** — Assess and score this dimension for {ticker} ({company_name}).

5. **ESG** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "management",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "md_track_record": <float>,
    "capital_allocation": <float>,
    "rpt": <float>,
    "irdai_compliance": <float>,
    "esg": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} management capital allocation insurance {year}",
    "{company_name} IRDAI compliance {year}",
]
