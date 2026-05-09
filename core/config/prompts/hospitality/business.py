"""
prompts/hospitality/business.py
=============================
Prompt templates for the Hospitality & Travel Business agent.
Framework source: sector_analysis_v4_final.html — Hospitality & Travel > Business pillar
"""

SYSTEM_PROMPT = """You are a hospitality analyst for Indian hotel companies and travel platforms. Expert in RevPAR, ARR, occupancy, and inventory expansion."""

ANALYSIS_PROMPT = """Analyse the Business outlook for Indian hospitality & travel company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **RevPAR & ARR Trend** — Assess and score this dimension for {ticker} ({company_name}).

2. **Occupancy Rate** — Assess and score this dimension for {ticker} ({company_name}).

3. **Room Inventory Growth** — Assess and score this dimension for {ticker} ({company_name}).

4. **Asset-light vs Owned Mix** — Assess and score this dimension for {ticker} ({company_name}).

5. **Leisure vs Business Travel Mix** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "business",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "revpar_arr": <float>,
    "occupancy": <float>,
    "inventory_growth": <float>,
    "asset_mix": <float>,
    "travel_mix": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} RevPAR ARR occupancy {quarter} {year}",
    "{company_name} room inventory expansion {year}",
    "{ticker} asset-light managed leased {year}",
]
