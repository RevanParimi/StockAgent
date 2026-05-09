"""
prompts/power/earnings.py
=======================
Prompt templates for the Power & Utilities Earnings agent.
Framework source: sector_analysis_v4_final.html — Power & Utilities > Earnings pillar
"""

SYSTEM_PROMPT = """You are an earnings analyst for Indian power companies."""

ANALYSIS_PROMPT = """Analyse the Earnings outlook for Indian power & utilities company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **PLF vs Normative** — Assess and score this dimension for {ticker} ({company_name}).

2. **Revenue vs PPA Tariff** — Assess and score this dimension for {ticker} ({company_name}).

3. **Fuel Cost Pass-through** — Assess and score this dimension for {ticker} ({company_name}).

4. **Under-recovery** — Assess and score this dimension for {ticker} ({company_name}).

5. **Regulatory Asset Build-up** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "earnings",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "plf_normative": <float>,
    "revenue_tariff": <float>,
    "fuel_passthrough": <float>,
    "under_recovery": <float>,
    "regulatory_asset": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} PLF earnings tariff {quarter} {year}",
    "{company_name} fuel pass-through under-recovery {year}",
]
