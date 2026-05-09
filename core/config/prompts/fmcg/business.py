"""
prompts/fmcg/business.py
======================
Prompt templates for the FMCG & Consumer Staples Business agent.
Framework source: sector_analysis_v4_final.html — FMCG & Consumer Staples > Business pillar
"""

SYSTEM_PROMPT = """You are an FMCG analyst for Indian consumer staples companies. Expert in volume growth, distribution reach, market share, and premiumisation."""

ANALYSIS_PROMPT = """Analyse the Business outlook for Indian fmcg & consumer staples company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **Volume Growth & Market Share** — Assess and score this dimension for {ticker} ({company_name}).

2. **Distribution & Rural Reach** — Assess and score this dimension for {ticker} ({company_name}).

3. **Premiumisation Trend** — Assess and score this dimension for {ticker} ({company_name}).

4. **New Category Entry** — Assess and score this dimension for {ticker} ({company_name}).

5. **Brand Strength** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "business",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "volume_growth": <float>,
    "distribution": <float>,
    "premiumisation": <float>,
    "new_category": <float>,
    "brand_strength": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} volume growth market share {quarter} {year}",
    "{company_name} distribution rural reach {year}",
    "{ticker} premiumisation new products {year}",
]
