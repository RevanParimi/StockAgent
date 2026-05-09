"""
prompts/chemicals/macro.py
========================
Prompt templates for the Specialty Chemicals Macro agent.
Framework source: sector_analysis_v4_final.html — Specialty Chemicals > Macro pillar
"""

SYSTEM_PROMPT = """You are a macro analyst for Indian specialty chemicals. Expert in China environmental regulations, crude derivatives pricing, and export opportunities."""

ANALYSIS_PROMPT = """Analyse the Macro outlook for Indian specialty chemicals company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **China Environmental Crackdown Impact** — Assess and score this dimension for {ticker} ({company_name}).

2. **Crude Oil & Derivatives Pricing** — Assess and score this dimension for {ticker} ({company_name}).

3. **Export Demand (Europe/US)** — Assess and score this dimension for {ticker} ({company_name}).

4. **India Chemical PLI** — Assess and score this dimension for {ticker} ({company_name}).

5. **Currency Impact** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "macro",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "china_regulation": <float>,
    "crude_derivatives": <float>,
    "export_demand": <float>,
    "pli": <float>,
    "currency": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "China chemical regulation environmental {year}",
    "Specialty chemicals export India {year}",
    "India chemical PLI {year}",
]
