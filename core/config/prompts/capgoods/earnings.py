"""
prompts/capgoods/earnings.py
==========================
Prompt templates for the Capital Goods Earnings agent.
Framework source: sector_analysis_v4_final.html — Capital Goods > Earnings pillar
"""

SYSTEM_PROMPT = """You are an earnings analyst for Indian capital goods."""

ANALYSIS_PROMPT = """Analyse the Earnings outlook for Indian capital goods company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **Order Book Conversion to Revenue** — Assess and score this dimension for {ticker} ({company_name}).

2. **EBITDA Margin Trend** — Assess and score this dimension for {ticker} ({company_name}).

3. **Working Capital Improvement** — Assess and score this dimension for {ticker} ({company_name}).

4. **Guidance vs Actual** — Assess and score this dimension for {ticker} ({company_name}).

5. **Exceptional Items** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "earnings",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "ob_conversion": <float>,
    "ebitda_margin": <float>,
    "working_capital": <float>,
    "guidance": <float>,
    "exceptional": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} earnings order conversion EBITDA {quarter} {year}",
    "{company_name} margin guidance {year}",
]
