"""
prompts/realestate/business.py
============================
Prompt templates for the Real Estate & REITs Business agent.
Framework source: sector_analysis_v4_final.html — Real Estate & REITs > Business pillar
"""

SYSTEM_PROMPT = """You are a real estate analyst for Indian developers and REITs. Expert in presales, GDV, launch pipeline, and REIT distributions."""

ANALYSIS_PROMPT = """Analyse the Business outlook for Indian real estate & reits company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **Presales & Collections** — Assess and score this dimension for {ticker} ({company_name}).

2. **Launch Pipeline & GDV** — Assess and score this dimension for {ticker} ({company_name}).

3. **Geographical Diversification** — Assess and score this dimension for {ticker} ({company_name}).

4. **Affordable vs Luxury Mix** — Assess and score this dimension for {ticker} ({company_name}).

5. **REIT Distribution Yield** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "business",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "presales": <float>,
    "launch_pipeline": <float>,
    "geo_diversification": <float>,
    "product_mix": <float>,
    "reit_yield": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} presales collections launch pipeline {year}",
    "{company_name} GDV residential commercial {year}",
    "{ticker} REIT distribution {year}",
]
