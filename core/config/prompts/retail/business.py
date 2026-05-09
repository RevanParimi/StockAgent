"""
prompts/retail/business.py
========================
Prompt templates for the Retail & Consumer Discretionary Business agent.
Framework source: sector_analysis_v4_final.html — Retail & Consumer Discretionary > Business pillar
"""

SYSTEM_PROMPT = """You are a retail analyst for Indian consumer discretionary and retail companies. Expert in SSSG, store expansion, omnichannel, and category mix."""

ANALYSIS_PROMPT = """Analyse the Business outlook for Indian retail & consumer discretionary company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **SSSG (Same Store Sales Growth)** — Assess and score this dimension for {ticker} ({company_name}).

2. **Store Expansion & Productivity** — Assess and score this dimension for {ticker} ({company_name}).

3. **Omnichannel & D2C** — Assess and score this dimension for {ticker} ({company_name}).

4. **Category Mix & Premiumisation** — Assess and score this dimension for {ticker} ({company_name}).

5. **Customer Loyalty Program** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "business",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "sssg": <float>,
    "store_expansion": <float>,
    "omnichannel": <float>,
    "category_mix": <float>,
    "loyalty": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} SSSG same store sales growth retail {quarter} {year}",
    "{company_name} store expansion omnichannel {year}",
    "{ticker} category mix premium {year}",
]
