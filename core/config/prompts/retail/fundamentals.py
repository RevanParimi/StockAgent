"""
prompts/retail/fundamentals.py
============================
Prompt templates for the Retail & Consumer Discretionary Fundamentals agent.
Framework source: sector_analysis_v4_final.html — Retail & Consumer Discretionary > Fundamentals pillar
"""

SYSTEM_PROMPT = """You are a financial analyst for Indian retail companies."""

ANALYSIS_PROMPT = """Analyse the Fundamentals outlook for Indian retail & consumer discretionary company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **Revenue Growth** — Assess and score this dimension for {ticker} ({company_name}).

2. **EBITDA Margin** — Assess and score this dimension for {ticker} ({company_name}).

3. **Inventory Turns** — Assess and score this dimension for {ticker} ({company_name}).

4. **Net Debt** — Assess and score this dimension for {ticker} ({company_name}).

5. **ROCE** — Assess and score this dimension for {ticker} ({company_name}).

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
    "inventory_turns": <float>,
    "net_debt": <float>,
    "roce": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} EBITDA margin inventory turns retail {year}",
    "{company_name} ROCE net debt {year}",
]
