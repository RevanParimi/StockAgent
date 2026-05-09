"""
prompts/retail/management.py
==========================
Prompt templates for the Retail & Consumer Discretionary Management agent.
Framework source: sector_analysis_v4_final.html — Retail & Consumer Discretionary > Management pillar
"""

SYSTEM_PROMPT = """You are a governance analyst for Indian retail companies."""

ANALYSIS_PROMPT = """Analyse the Management outlook for Indian retail & consumer discretionary company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **Promoter Quality & Vision** — Assess and score this dimension for {ticker} ({company_name}).

2. **Capital Allocation (Owned vs Leased)** — Assess and score this dimension for {ticker} ({company_name}).

3. **RPT** — Assess and score this dimension for {ticker} ({company_name}).

4. **Store Format Strategy** — Assess and score this dimension for {ticker} ({company_name}).

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
    "store_strategy": <float>,
    "esg": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} management promoter retail {year}",
    "{company_name} capital allocation RPT {year}",
]
