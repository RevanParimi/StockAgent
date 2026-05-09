"""
prompts/oilgas/macro.py
=====================
Prompt templates for the Oil & Gas Macro agent.
Framework source: sector_analysis_v4_final.html — Oil & Gas > Macro pillar
"""

SYSTEM_PROMPT = """You are a macro analyst for Indian oil & gas. Expert in Brent crude, OPEC+ decisions, INR/USD, domestic fuel pricing, and gas APM policy."""

ANALYSIS_PROMPT = """Analyse the Macro outlook for Indian oil & gas company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **Brent Crude Price Outlook** — Assess and score this dimension for {ticker} ({company_name}).

2. **OPEC+ Production Policy** — Assess and score this dimension for {ticker} ({company_name}).

3. **USD/INR Impact** — Assess and score this dimension for {ticker} ({company_name}).

4. **India Fuel Subsidy Policy** — Assess and score this dimension for {ticker} ({company_name}).

5. **APM Gas Price** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "macro",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "brent_crude": <float>,
    "opec": <float>,
    "usd_inr": <float>,
    "subsidy_policy": <float>,
    "apm_gas": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "Brent crude OPEC production {year}",
    "India fuel subsidy pricing policy {year}",
    "India APM gas price {year}",
    "USD INR oil import {year}",
]
