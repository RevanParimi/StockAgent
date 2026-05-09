"""
prompts/tech/earnings.py
======================
Prompt templates for the Information Technology Earnings agent.
Framework source: sector_analysis_v4_final.html — Information Technology > Earnings pillar
"""

SYSTEM_PROMPT = """You are an earnings analyst for Indian IT companies."""

ANALYSIS_PROMPT = """Analyse the Earnings outlook for Indian information technology company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **Revenue Guidance Adherence** — Assess and score this dimension for {ticker} ({company_name}).

2. **Margin Guidance vs Actual** — Assess and score this dimension for {ticker} ({company_name}).

3. **Deal Conversion to Revenue** — Assess and score this dimension for {ticker} ({company_name}).

4. **Forex Impact** — Assess and score this dimension for {ticker} ({company_name}).

5. **One-time Items** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "earnings",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "revenue_guidance": <float>,
    "margin_guidance": <float>,
    "deal_conversion": <float>,
    "forex_impact": <float>,
    "one_time": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} earnings guidance actual {quarter} {year}",
    "{company_name} margin forex impact {year}",
]
