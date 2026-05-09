"""
prompts/capgoods/risk.py
======================
Prompt templates for the Capital Goods Risk agent.
Framework source: sector_analysis_v4_final.html — Capital Goods > Risk pillar
"""

SYSTEM_PROMPT = """You are a risk analyst for Indian capital goods companies."""

ANALYSIS_PROMPT = """Analyse the Risk outlook for Indian capital goods company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **Order Cancellation Risk** — Assess and score this dimension for {ticker} ({company_name}).

2. **Execution Delays** — Assess and score this dimension for {ticker} ({company_name}).

3. **Input Cost Volatility** — Assess and score this dimension for {ticker} ({company_name}).

4. **Competition from Imports** — Assess and score this dimension for {ticker} ({company_name}).

5. **Customer Concentration** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "risk",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "cancellation_risk": <float>,
    "execution_delay": <float>,
    "input_cost": <float>,
    "import_competition": <float>,
    "customer_concentration": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} order cancellation risk {year}",
    "{company_name} execution delay competition {year}",
]
