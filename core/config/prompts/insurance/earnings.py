"""
prompts/insurance/earnings.py
===========================
Prompt templates for the Insurance Earnings agent.
Framework source: sector_analysis_v4_final.html — Insurance > Earnings pillar
"""

SYSTEM_PROMPT = """You are an earnings analyst for Indian insurance."""

ANALYSIS_PROMPT = """Analyse the Earnings outlook for Indian insurance company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **VNB vs Guidance** — Assess and score this dimension for {ticker} ({company_name}).

2. **APE Growth Trend** — Assess and score this dimension for {ticker} ({company_name}).

3. **Opex Ratio** — Assess and score this dimension for {ticker} ({company_name}).

4. **Claims Ratio Trend** — Assess and score this dimension for {ticker} ({company_name}).

5. **Operating Leverage** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "earnings",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "vnb_guidance": <float>,
    "ape_growth": <float>,
    "opex_ratio": <float>,
    "claims_ratio": <float>,
    "operating_leverage": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} VNB APE earnings {quarter} {year}",
    "{company_name} claims ratio guidance {year}",
]
