"""
prompts/metals/earnings.py
========================
Prompt templates for the Metals & Mining Earnings agent.
Framework source: sector_analysis_v4_final.html — Metals & Mining > Earnings pillar
"""

SYSTEM_PROMPT = """You are an earnings analyst for Indian metals."""

ANALYSIS_PROMPT = """Analyse the Earnings outlook for Indian metals & mining company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **Volume Growth** — Assess and score this dimension for {ticker} ({company_name}).

2. **Realization Trend** — Assess and score this dimension for {ticker} ({company_name}).

3. **EBITDA/Tonne vs LME** — Assess and score this dimension for {ticker} ({company_name}).

4. **Input Cost Pass-through** — Assess and score this dimension for {ticker} ({company_name}).

5. **One-time Items** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "earnings",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "volume_growth": <float>,
    "realization": <float>,
    "ebitda_vs_lme": <float>,
    "pass_through": <float>,
    "one_time": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} volume realization EBITDA {quarter} {year}",
    "{company_name} earnings LME {year}",
]
