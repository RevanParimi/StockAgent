"""
prompts/telecom/management.py
===========================
Prompt templates for the Telecommunications Management agent.
Framework source: sector_analysis_v4_final.html — Telecommunications > Management pillar
"""

SYSTEM_PROMPT = """You are a governance analyst for Indian telecom companies."""

ANALYSIS_PROMPT = """Analyse the Management outlook for Indian telecommunications company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **Promoter Quality & Commitment** — Assess and score this dimension for {ticker} ({company_name}).

2. **Capital Allocation & FPO** — Assess and score this dimension for {ticker} ({company_name}).

3. **AGR Strategy** — Assess and score this dimension for {ticker} ({company_name}).

4. **RPT** — Assess and score this dimension for {ticker} ({company_name}).

5. **ESG** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "management",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "promoter_commitment": <float>,
    "capital_allocation": <float>,
    "agr_strategy": <float>,
    "rpt": <float>,
    "esg": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} promoter management capital {year}",
    "{company_name} AGR strategy {year}",
]
