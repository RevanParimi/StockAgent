"""
prompts/tech/fundamentals.py
==========================
Prompt templates for the Information Technology Fundamentals agent.
Framework source: sector_analysis_v4_final.html — Information Technology > Fundamentals pillar
"""

SYSTEM_PROMPT = """You are a financial analyst for Indian IT services companies. Expert in EBIT margins, revenue growth, attrition impact, USD/INR hedging, and free cash flow conversion."""

ANALYSIS_PROMPT = """Analyse the Fundamentals outlook for Indian information technology company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **Revenue Growth (CC & INR)** — Assess and score this dimension for {ticker} ({company_name}).

2. **EBIT Margin Trend** — Assess and score this dimension for {ticker} ({company_name}).

3. **Free Cash Flow Conversion** — Assess and score this dimension for {ticker} ({company_name}).

4. **Attrition & Headcount** — Assess and score this dimension for {ticker} ({company_name}).

5. **USD Hedge Book** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "fundamentals",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "revenue_growth": <float>,
    "ebit_margin": <float>,
    "fcf_conversion": <float>,
    "attrition": <float>,
    "usd_hedge": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} revenue growth EBIT margin {quarter} {year}",
    "{company_name} attrition headcount {year}",
    "{ticker} free cash flow USD hedge {year}",
]
