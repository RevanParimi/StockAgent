"""
prompts/fmcg/risk.py
==================
Prompt templates for the FMCG & Consumer Staples Risk agent.
Framework source: sector_analysis_v4_final.html — FMCG & Consumer Staples > Risk pillar
"""

SYSTEM_PROMPT = """You are a risk analyst for Indian FMCG companies."""

ANALYSIS_PROMPT = """Analyse the Risk outlook for Indian fmcg & consumer staples company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **Raw Material Cost Volatility** — Assess and score this dimension for {ticker} ({company_name}).

2. **D2C & Private Label Competition** — Assess and score this dimension for {ticker} ({company_name}).

3. **Rural Slowdown Risk** — Assess and score this dimension for {ticker} ({company_name}).

4. **Regulatory (FSSAI, GST)** — Assess and score this dimension for {ticker} ({company_name}).

5. **Concentration in Key SKUs** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "risk",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "rm_volatility": <float>,
    "competition": <float>,
    "rural_risk": <float>,
    "regulatory": <float>,
    "sku_concentration": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} raw material risk commodity {year}",
    "{company_name} competition D2C private label {year}",
]
