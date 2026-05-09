"""
prompts/power/business.py
=======================
Prompt templates for the Power & Utilities Business agent.
Framework source: sector_analysis_v4_final.html — Power & Utilities > Business pillar
"""

SYSTEM_PROMPT = """You are a power sector analyst for Indian utilities. Expert in generation mix, PPA quality, T&D business, and DISCOM relationships."""

ANALYSIS_PROMPT = """Analyse the Business outlook for Indian power & utilities company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **Generation Mix (Thermal/Hydro/RE)** — Assess and score this dimension for {ticker} ({company_name}).

2. **PPA Coverage & Tenure** — Assess and score this dimension for {ticker} ({company_name}).

3. **T&D Business** — Assess and score this dimension for {ticker} ({company_name}).

4. **DISCOM Payment Health** — Assess and score this dimension for {ticker} ({company_name}).

5. **Merchant vs Regulated Revenue** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "business",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "generation_mix": <float>,
    "ppa_coverage": <float>,
    "td_business": <float>,
    "discom_health": <float>,
    "merchant_regulated": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} generation mix PPA DISCOM {year}",
    "{company_name} T&D power business {year}",
    "{ticker} merchant regulated revenue {year}",
]
