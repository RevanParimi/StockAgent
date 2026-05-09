"""
prompts/pharma/macro.py
=====================
Prompt templates for the Pharmaceuticals Macro agent.
Framework source: sector_analysis_v4_final.html — Pharmaceuticals > Macro pillar
"""

SYSTEM_PROMPT = """You are a macro analyst for Indian pharma. Expert in US drug pricing policy, FDA import alerts, generic competition, and Indian domestic pricing."""

ANALYSIS_PROMPT = """Analyse the Macro outlook for Indian pharmaceuticals company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **US Drug Pricing Policy** — Assess and score this dimension for {ticker} ({company_name}).

2. **FDA Import Alerts** — Assess and score this dimension for {ticker} ({company_name}).

3. **Generic Price Erosion** — Assess and score this dimension for {ticker} ({company_name}).

4. **NPPA Pricing Regulation** — Assess and score this dimension for {ticker} ({company_name}).

5. **China API Competition** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "macro",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "us_pricing": <float>,
    "fda_alerts": <float>,
    "generic_erosion": <float>,
    "nppa": <float>,
    "china_api": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "US drug pricing policy FDA {year}",
    "India NPPA pharma pricing regulation {year}",
    "China API competition India pharma {year}",
]
