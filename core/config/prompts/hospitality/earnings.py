"""
prompts/hospitality/earnings.py
=============================
Prompt templates for the Hospitality & Travel Earnings agent.
Framework source: sector_analysis_v4_final.html — Hospitality & Travel > Earnings pillar
"""

SYSTEM_PROMPT = """You are an earnings analyst for Indian hospitality."""

ANALYSIS_PROMPT = """Analyse the Earnings outlook for Indian hospitality & travel company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **RevPAR vs Guidance** — Assess and score this dimension for {ticker} ({company_name}).

2. **EBITDA vs Consensus** — Assess and score this dimension for {ticker} ({company_name}).

3. **Seasonality Adjustment** — Assess and score this dimension for {ticker} ({company_name}).

4. **New Hotel Ramp-up** — Assess and score this dimension for {ticker} ({company_name}).

5. **One-time Items** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "earnings",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "revpar_guidance": <float>,
    "ebitda_consensus": <float>,
    "seasonality": <float>,
    "new_hotel_ramp": <float>,
    "one_time": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} RevPAR EBITDA earnings {quarter} {year}",
    "{company_name} guidance hospitality {year}",
]
