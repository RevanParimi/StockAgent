"""
prompts/hospitality/macro.py
==========================
Prompt templates for the Hospitality & Travel Macro agent.
Framework source: sector_analysis_v4_final.html — Hospitality & Travel > Macro pillar
"""

SYSTEM_PROMPT = """You are a macro analyst for Indian hospitality sector. Expert in domestic tourism, inbound FTAs, corporate travel, and event calendar."""

ANALYSIS_PROMPT = """Analyse the Macro outlook for Indian hospitality & travel company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **Domestic Tourism Growth** — Assess and score this dimension for {ticker} ({company_name}).

2. **Foreign Tourist Arrivals (FTA)** — Assess and score this dimension for {ticker} ({company_name}).

3. **Corporate Travel & MICE** — Assess and score this dimension for {ticker} ({company_name}).

4. **Event & Wedding Season** — Assess and score this dimension for {ticker} ({company_name}).

5. **Aviation Connectivity** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "macro",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "domestic_tourism": <float>,
    "fta": <float>,
    "corporate_travel": <float>,
    "events": <float>,
    "aviation": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "India domestic tourism hospitality {year}",
    "India foreign tourist arrivals FTA {year}",
    "India corporate travel MICE {year}",
]
