"""
prompts/logistics/management.py
=============================
Prompt templates for the Logistics & Supply Chain Management agent.
Framework source: sector_analysis_v4_final.html — Logistics & Supply Chain > Management pillar
"""

SYSTEM_PROMPT = """You are a governance analyst for Indian logistics companies."""

ANALYSIS_PROMPT = """Analyse the Management outlook for Indian logistics & supply chain company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **Promoter Track Record** — Assess and score this dimension for {ticker} ({company_name}).

2. **Capital Allocation** — Assess and score this dimension for {ticker} ({company_name}).

3. **RPT** — Assess and score this dimension for {ticker} ({company_name}).

4. **Tech Strategy** — Assess and score this dimension for {ticker} ({company_name}).

5. **ESG** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "management",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "promoter_track_record": <float>,
    "capital_allocation": <float>,
    "rpt": <float>,
    "tech_strategy": <float>,
    "esg": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} management logistics {year}",
    "{company_name} capital allocation tech {year}",
]
