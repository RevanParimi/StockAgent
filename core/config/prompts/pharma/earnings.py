"""
prompts/pharma/earnings.py
========================
Prompt templates for the Pharmaceuticals Earnings agent.
Framework source: sector_analysis_v4_final.html — Pharmaceuticals > Earnings pillar
"""

SYSTEM_PROMPT = """You are an earnings analyst for Indian pharma."""

ANALYSIS_PROMPT = """Analyse the Earnings outlook for Indian pharmaceuticals company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **US Revenue Guidance vs Actual** — Assess and score this dimension for {ticker} ({company_name}).

2. **Domestic Growth** — Assess and score this dimension for {ticker} ({company_name}).

3. **R&D Capitalisation Policy** — Assess and score this dimension for {ticker} ({company_name}).

4. **One-time Charges** — Assess and score this dimension for {ticker} ({company_name}).

5. **EBITDA Guidance** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "earnings",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "us_guidance": <float>,
    "domestic_growth": <float>,
    "rd_policy": <float>,
    "one_time": <float>,
    "ebitda_guidance": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} earnings guidance US domestic {quarter} {year}",
    "{company_name} EBITDA one-time items {year}",
]
