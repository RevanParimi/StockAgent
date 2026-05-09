"""
prompts/pharma/fundamentals.py
============================
Prompt templates for the Pharmaceuticals Fundamentals agent.
Framework source: sector_analysis_v4_final.html — Pharmaceuticals > Fundamentals pillar
"""

SYSTEM_PROMPT = """You are a financial analyst for Indian pharma companies. Expert in EBITDA margins, R&D spend, working capital, and free cash flow."""

ANALYSIS_PROMPT = """Analyse the Fundamentals outlook for Indian pharmaceuticals company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **Revenue Growth & Mix** — Assess and score this dimension for {ticker} ({company_name}).

2. **EBITDA Margin** — Assess and score this dimension for {ticker} ({company_name}).

3. **R&D Spend (% Revenue)** — Assess and score this dimension for {ticker} ({company_name}).

4. **Working Capital** — Assess and score this dimension for {ticker} ({company_name}).

5. **FCF Generation** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "fundamentals",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "revenue_growth": <float>,
    "ebitda_margin": <float>,
    "rd_spend": <float>,
    "working_capital": <float>,
    "fcf": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} EBITDA margin R&D spend {quarter} {year}",
    "{company_name} revenue growth working capital {year}",
]
