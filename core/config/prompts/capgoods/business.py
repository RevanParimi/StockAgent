"""
prompts/capgoods/business.py
==========================
Prompt templates for the Capital Goods Business agent.
Framework source: sector_analysis_v4_final.html — Capital Goods > Business pillar
"""

SYSTEM_PROMPT = """You are a capital goods analyst for Indian engineering & industrial companies. Expert in order books, product complexity, T&D equipment, railways, and industrial automation."""

ANALYSIS_PROMPT = """Analyse the Business outlook for Indian capital goods company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **Order Book & L1 Pipeline** — Assess and score this dimension for {ticker} ({company_name}).

2. **Revenue Visibility (OB/Revenue)** — Assess and score this dimension for {ticker} ({company_name}).

3. **Product Complexity & Technology** — Assess and score this dimension for {ticker} ({company_name}).

4. **Sector Diversification (Power/Infra/Railways)** — Assess and score this dimension for {ticker} ({company_name}).

5. **Export Revenue** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "business",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "order_book": <float>,
    "revenue_visibility": <float>,
    "product_complexity": <float>,
    "sector_diversification": <float>,
    "export_revenue": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} order book L1 pipeline capgoods {year}",
    "{company_name} product complexity technology {year}",
    "{ticker} export revenue industrial {year}",
]
