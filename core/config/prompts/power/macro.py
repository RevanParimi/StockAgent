"""
prompts/power/macro.py
====================
Prompt templates for the Power & Utilities Macro agent.
Framework source: sector_analysis_v4_final.html — Power & Utilities > Macro pillar
"""

SYSTEM_PROMPT = """You are a macro analyst for Indian power sector. Expert in coal prices, fuel linkage, electricity demand, and CERC tariff orders."""

ANALYSIS_PROMPT = """Analyse the Macro outlook for Indian power & utilities company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **Coal Price & Fuel Linkage** — Assess and score this dimension for {ticker} ({company_name}).

2. **Electricity Demand Growth** — Assess and score this dimension for {ticker} ({company_name}).

3. **CERC/SERC Tariff Orders** — Assess and score this dimension for {ticker} ({company_name}).

4. **Renewable Integration** — Assess and score this dimension for {ticker} ({company_name}).

5. **DISCOM Finances** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "macro",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "coal_price": <float>,
    "electricity_demand": <float>,
    "cerc_tariff": <float>,
    "re_integration": <float>,
    "discom_finances": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "India coal price fuel linkage power {year}",
    "India electricity demand growth {year}",
    "CERC tariff order power {year}",
    "DISCOM finances health India {year}",
]
