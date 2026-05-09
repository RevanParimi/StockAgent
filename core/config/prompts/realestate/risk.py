"""
prompts/realestate/risk.py
========================
Prompt templates for the Real Estate & REITs Risk agent.
Framework source: sector_analysis_v4_final.html — Real Estate & REITs > Risk pillar
"""

SYSTEM_PROMPT = """You are a risk analyst for Indian real estate companies."""

ANALYSIS_PROMPT = """Analyse the Risk outlook for Indian real estate & reits company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **Project Delivery Delays** — Assess and score this dimension for {ticker} ({company_name}).

2. **RERA Compliance** — Assess and score this dimension for {ticker} ({company_name}).

3. **Working Capital & Debt** — Assess and score this dimension for {ticker} ({company_name}).

4. **Unsold Inventory** — Assess and score this dimension for {ticker} ({company_name}).

5. **Regulatory Changes (RERA, GST)** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "risk",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "delivery_delay": <float>,
    "rera_compliance": <float>,
    "debt_risk": <float>,
    "unsold_inventory": <float>,
    "regulatory": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} RERA project delay delivery risk {year}",
    "{company_name} unsold inventory debt {year}",
]
