"""
prompts/insurance/fundamentals.py
===============================
Prompt templates for the Insurance Fundamentals agent.
Framework source: sector_analysis_v4_final.html — Insurance > Fundamentals pillar
"""

SYSTEM_PROMPT = """You are a financial analyst for Indian insurance companies."""

ANALYSIS_PROMPT = """Analyse the Fundamentals outlook for Indian insurance company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **Embedded Value (EV) Growth** — Assess and score this dimension for {ticker} ({company_name}).

2. **Operating RoEV** — Assess and score this dimension for {ticker} ({company_name}).

3. **Solvency Ratio** — Assess and score this dimension for {ticker} ({company_name}).

4. **Investment Yield** — Assess and score this dimension for {ticker} ({company_name}).

5. **Cost Ratio** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "fundamentals",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "ev_growth": <float>,
    "roev": <float>,
    "solvency_ratio": <float>,
    "investment_yield": <float>,
    "cost_ratio": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} embedded value EV RoEV {year}",
    "{company_name} solvency ratio investment yield {year}",
]
