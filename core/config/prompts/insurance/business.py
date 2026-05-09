"""
prompts/insurance/business.py
===========================
Prompt templates for the Insurance Business agent.
Framework source: sector_analysis_v4_final.html — Insurance > Business pillar
"""

SYSTEM_PROMPT = """You are an insurance analyst for Indian life and non-life insurance companies. Expert in VNB, APE, persistency, combined ratio, and distribution."""

ANALYSIS_PROMPT = """Analyse the Business outlook for Indian insurance company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **VNB Growth & VNB Margin (Life)** — Assess and score this dimension for {ticker} ({company_name}).

2. **APE & Product Mix** — Assess and score this dimension for {ticker} ({company_name}).

3. **Persistency Ratio** — Assess and score this dimension for {ticker} ({company_name}).

4. **Combined Ratio (Non-life)** — Assess and score this dimension for {ticker} ({company_name}).

5. **Distribution Channel Mix** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "business",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "vnb_growth": <float>,
    "ape_mix": <float>,
    "persistency": <float>,
    "combined_ratio": <float>,
    "distribution_mix": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} VNB APE persistency insurance {quarter} {year}",
    "{company_name} combined ratio non-life {year}",
    "{ticker} distribution bancassurance agency {year}",
]
