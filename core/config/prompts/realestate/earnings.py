"""
prompts/realestate/earnings.py
============================
Prompt templates for the Real Estate & REITs Earnings agent.
Framework source: sector_analysis_v4_final.html — Real Estate & REITs > Earnings pillar
"""

SYSTEM_PROMPT = """You are an earnings analyst for Indian real estate."""

ANALYSIS_PROMPT = """Analyse the Earnings outlook for Indian real estate & reits company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **Presales vs Revenue Recognition Lag** — Assess and score this dimension for {ticker} ({company_name}).

2. **Collections Efficiency** — Assess and score this dimension for {ticker} ({company_name}).

3. **Margin on Completed Projects** — Assess and score this dimension for {ticker} ({company_name}).

4. **New Launch Performance** — Assess and score this dimension for {ticker} ({company_name}).

5. **Guidance vs Actual** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "earnings",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "presales_recognition": <float>,
    "collections": <float>,
    "project_margin": <float>,
    "launch_performance": <float>,
    "guidance": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} presales collections earnings {quarter} {year}",
    "{company_name} margin guidance real estate {year}",
]
