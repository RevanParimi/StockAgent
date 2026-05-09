"""
prompts/defence/fundamentals.py
=============================
Prompt templates for the Defence & Aerospace Fundamentals agent.
Framework source: sector_analysis_v4_final.html — Defence & Aerospace > Fundamentals pillar
"""

SYSTEM_PROMPT = """You are a financial analyst for Indian defence companies. Expert in EBITDA margins, working capital cycles (long defence procurement), RoCE, and debt management."""

ANALYSIS_PROMPT = """Analyse the Fundamentals outlook for Indian defence & aerospace company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **Revenue Growth & Order Conversion** — Assess and score this dimension for {ticker} ({company_name}).

2. **EBITDA Margin Trend** — Assess and score this dimension for {ticker} ({company_name}).

3. **RoCE & Capital Efficiency** — Assess and score this dimension for {ticker} ({company_name}).

4. **Working Capital & Cash Conversion** — Assess and score this dimension for {ticker} ({company_name}).

5. **Net Debt / EBITDA** — Assess and score this dimension for {ticker} ({company_name}).

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
    "roce": <float>,
    "working_capital": <float>,
    "net_debt_ebitda": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} revenue EBITDA margin {quarter} {year}",
    "{company_name} RoCE capital efficiency {year}",
    "{ticker} working capital cash flow defence {year}",
    "{ticker} net debt balance sheet {year}",
]
