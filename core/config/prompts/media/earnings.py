"""
prompts/media/earnings.py
=======================
Prompt templates for the Media & Entertainment Earnings agent.
Framework source: sector_analysis_v4_final.html — Media & Entertainment > Earnings pillar
"""

SYSTEM_PROMPT = """You are an earnings analyst for Indian media."""

ANALYSIS_PROMPT = """Analyse the Earnings outlook for Indian media & entertainment company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **Ad Revenue vs Guidance** — Assess and score this dimension for {ticker} ({company_name}).

2. **Subscription Growth** — Assess and score this dimension for {ticker} ({company_name}).

3. **Content Cost vs Budget** — Assess and score this dimension for {ticker} ({company_name}).

4. **Operating Leverage** — Assess and score this dimension for {ticker} ({company_name}).

5. **One-time Impairments** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "earnings",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "ad_guidance": <float>,
    "subscription_growth": <float>,
    "content_cost": <float>,
    "operating_leverage": <float>,
    "impairments": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} ad subscription earnings {quarter} {year}",
    "{company_name} content cost guidance media {year}",
]
