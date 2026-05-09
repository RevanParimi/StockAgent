"""
prompts/metals/risk.py
====================
Prompt templates for the Metals & Mining Risk agent.
Framework source: sector_analysis_v4_final.html — Metals & Mining > Risk pillar
"""

SYSTEM_PROMPT = """You are a risk analyst for Indian metals companies."""

ANALYSIS_PROMPT = """Analyse the Risk outlook for Indian metals & mining company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **Commodity Price Cycle Risk** — Assess and score this dimension for {ticker} ({company_name}).

2. **China Dumping & Anti-dumping** — Assess and score this dimension for {ticker} ({company_name}).

3. **Input Cost Volatility** — Assess and score this dimension for {ticker} ({company_name}).

4. **Regulatory & Mining Lease Risk** — Assess and score this dimension for {ticker} ({company_name}).

5. **Debt & Refinancing** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "risk",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "price_cycle": <float>,
    "china_dumping": <float>,
    "input_volatility": <float>,
    "regulatory": <float>,
    "debt_risk": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} China dumping anti-dumping metals {year}",
    "{company_name} mining lease regulatory risk {year}",
]
