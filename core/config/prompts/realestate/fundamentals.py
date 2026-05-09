"""
prompts/realestate/fundamentals.py
================================
Prompt templates for the Real Estate & REITs Fundamentals agent.
Framework source: sector_analysis_v4_final.html — Real Estate & REITs > Fundamentals pillar
"""

SYSTEM_PROMPT = """You are a financial analyst for Indian real estate companies."""

ANALYSIS_PROMPT = """Analyse the Fundamentals outlook for Indian real estate & reits company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **Revenue Recognition (Completion Method)** — Assess and score this dimension for {ticker} ({company_name}).

2. **EBITDA Margin** — Assess and score this dimension for {ticker} ({company_name}).

3. **Net Debt & Leverage** — Assess and score this dimension for {ticker} ({company_name}).

4. **Operating Cash Flow** — Assess and score this dimension for {ticker} ({company_name}).

5. **Land Bank Value** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "fundamentals",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "revenue_recognition": <float>,
    "ebitda_margin": <float>,
    "net_debt": <float>,
    "operating_cf": <float>,
    "land_bank": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} revenue EBITDA net debt real estate {year}",
    "{company_name} land bank cash flow {year}",
]
