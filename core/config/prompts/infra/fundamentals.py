"""
prompts/infra/fundamentals.py
===========================
Prompt templates for the Infrastructure & Construction Fundamentals agent.
Framework source: sector_analysis_v4_final.html — Infrastructure & Construction > Fundamentals pillar
"""

SYSTEM_PROMPT = """You are a financial analyst for Indian infra/construction companies. Expert in EBITDA margins, working capital, D/E ratio, and cash conversion."""

ANALYSIS_PROMPT = """Analyse the Fundamentals outlook for Indian infrastructure & construction company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **Revenue Growth & Order Conversion** — Assess and score this dimension for {ticker} ({company_name}).

2. **EBITDA Margin** — Assess and score this dimension for {ticker} ({company_name}).

3. **Debt/Equity & Interest Cover** — Assess and score this dimension for {ticker} ({company_name}).

4. **Working Capital Cycle** — Assess and score this dimension for {ticker} ({company_name}).

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
    "debt_equity": <float>,
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
    "{ticker} EBITDA margin debt equity {quarter} {year}",
    "{company_name} working capital cash flow {year}",
]
