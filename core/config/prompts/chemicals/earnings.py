"""
prompts/chemicals/earnings.py
===========================
Prompt templates for the Specialty Chemicals Earnings agent.
Framework source: sector_analysis_v4_final.html — Specialty Chemicals > Earnings pillar
"""

SYSTEM_PROMPT = """You are an earnings analyst for Indian specialty chemicals."""

ANALYSIS_PROMPT = """Analyse the Earnings outlook for Indian specialty chemicals company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **Volume vs Realization** — Assess and score this dimension for {ticker} ({company_name}).

2. **EBITDA Margin Trend** — Assess and score this dimension for {ticker} ({company_name}).

3. **Utilisation Rate** — Assess and score this dimension for {ticker} ({company_name}).

4. **New Product Revenue** — Assess and score this dimension for {ticker} ({company_name}).

5. **Guidance vs Actual** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "earnings",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "volume_realization": <float>,
    "ebitda_margin": <float>,
    "utilisation": <float>,
    "new_product": <float>,
    "guidance": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} volume realization EBITDA {quarter} {year}",
    "{company_name} utilisation guidance {year}",
]
