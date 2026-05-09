"""
prompts/media/business.py
=======================
Prompt templates for the Media & Entertainment Business agent.
Framework source: sector_analysis_v4_final.html — Media & Entertainment > Business pillar
"""

SYSTEM_PROMPT = """You are a media analyst for Indian companies. Expert in advertising revenue, subscription, OTT streaming, box office, and live events."""

ANALYSIS_PROMPT = """Analyse the Business outlook for Indian media & entertainment company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **Ad Revenue Market Share** — Assess and score this dimension for {ticker} ({company_name}).

2. **Subscription & OTT Growth** — Assess and score this dimension for {ticker} ({company_name}).

3. **Box Office Performance** — Assess and score this dimension for {ticker} ({company_name}).

4. **Live Events & IP** — Assess and score this dimension for {ticker} ({company_name}).

5. **Digital vs Traditional Mix** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "business",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "ad_revenue": <float>,
    "subscription_ott": <float>,
    "box_office": <float>,
    "live_events": <float>,
    "digital_mix": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} ad revenue subscription OTT {quarter} {year}",
    "{company_name} box office live events {year}",
    "{ticker} digital traditional media mix {year}",
]
