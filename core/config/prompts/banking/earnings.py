"""
prompts/banking/earnings.py
=========================
Prompt templates for the Banking & NBFC Earnings agent.
Framework source: sector_analysis_v4_final.html — Banking & NBFC > Earnings pillar
"""

SYSTEM_PROMPT = """You are an earnings analyst for Indian banks."""

ANALYSIS_PROMPT = """Analyse the Earnings outlook for Indian banking & nbfc company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **NII Growth vs Guidance** — Assess and score this dimension for {ticker} ({company_name}).

2. **Pre-Provision Operating Profit** — Assess and score this dimension for {ticker} ({company_name}).

3. **Credit Cost Trend** — Assess and score this dimension for {ticker} ({company_name}).

4. **One-time Provisions** — Assess and score this dimension for {ticker} ({company_name}).

5. **Fee Income Growth** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "earnings",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "nii_growth": <float>,
    "ppop": <float>,
    "credit_cost": <float>,
    "one_time": <float>,
    "fee_growth": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} NII PPOP credit cost {quarter} {year}",
    "{company_name} earnings quality provisions {year}",
]
