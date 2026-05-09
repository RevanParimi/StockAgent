"""
prompts/chemicals/risk.py
=======================
Prompt templates for the Specialty Chemicals Risk agent.
Framework source: sector_analysis_v4_final.html — Specialty Chemicals > Risk pillar
"""

SYSTEM_PROMPT = """You are a risk analyst for Indian specialty chemical companies."""

ANALYSIS_PROMPT = """Analyse the Risk outlook for Indian specialty chemicals company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **Raw Material Cost Volatility** — Assess and score this dimension for {ticker} ({company_name}).

2. **Customer Concentration Risk** — Assess and score this dimension for {ticker} ({company_name}).

3. **China Competition Return** — Assess and score this dimension for {ticker} ({company_name}).

4. **Regulatory (REACH, BIS)** — Assess and score this dimension for {ticker} ({company_name}).

5. **Capex Execution** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "risk",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "rm_volatility": <float>,
    "customer_concentration": <float>,
    "china_competition": <float>,
    "regulatory": <float>,
    "capex_execution": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} raw material cost risk {year}",
    "{company_name} China competition regulatory chemicals {year}",
]
