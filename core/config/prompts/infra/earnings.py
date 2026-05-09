"""
prompts/infra/earnings.py
=======================
Prompt templates for the Infrastructure & Construction Earnings agent.
Framework source: sector_analysis_v4_final.html — Infrastructure & Construction > Earnings pillar
"""

SYSTEM_PROMPT = """You are an earnings analyst for Indian infra/construction companies."""

ANALYSIS_PROMPT = """Analyse the Earnings outlook for Indian infrastructure & construction company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **Revenue Recognition (POC vs Completion)** — Assess and score this dimension for {ticker} ({company_name}).

2. **Order Book-to-Revenue Conversion** — Assess and score this dimension for {ticker} ({company_name}).

3. **Margin Trajectory** — Assess and score this dimension for {ticker} ({company_name}).

4. **Exceptional Items** — Assess and score this dimension for {ticker} ({company_name}).

5. **Guidance vs Actual** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "earnings",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "revenue_recognition": <float>,
    "ob_conversion": <float>,
    "margin": <float>,
    "exceptional": <float>,
    "guidance": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} earnings revenue recognition {quarter} {year}",
    "{company_name} margin guidance {year}",
]
