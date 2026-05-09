"""
prompts/infra/management.py
=========================
Prompt templates for the Infrastructure & Construction Management agent.
Framework source: sector_analysis_v4_final.html — Infrastructure & Construction > Management pillar
"""

SYSTEM_PROMPT = """You are a governance analyst for Indian infra companies."""

ANALYSIS_PROMPT = """Analyse the Management outlook for Indian infrastructure & construction company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **Promoter Quality & Track Record** — Assess and score this dimension for {ticker} ({company_name}).

2. **Related Party Transactions** — Assess and score this dimension for {ticker} ({company_name}).

3. **Capital Allocation** — Assess and score this dimension for {ticker} ({company_name}).

4. **Concession Portfolio** — Assess and score this dimension for {ticker} ({company_name}).

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
    "rpt": <float>,
    "capital_allocation": <float>,
    "concession": <float>,
    "esg": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} management promoter {year}",
    "{company_name} RPT capital allocation {year}",
]
