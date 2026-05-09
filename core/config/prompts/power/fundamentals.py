"""
prompts/power/fundamentals.py
===========================
Prompt templates for the Power & Utilities Fundamentals agent.
Framework source: sector_analysis_v4_final.html — Power & Utilities > Fundamentals pillar
"""

SYSTEM_PROMPT = """You are a financial analyst for Indian power companies."""

ANALYSIS_PROMPT = """Analyse the Fundamentals outlook for Indian power & utilities company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **Revenue Growth & PLF** — Assess and score this dimension for {ticker} ({company_name}).

2. **EBITDA Margin** — Assess and score this dimension for {ticker} ({company_name}).

3. **Net Debt/EBITDA** — Assess and score this dimension for {ticker} ({company_name}).

4. **DSCR** — Assess and score this dimension for {ticker} ({company_name}).

5. **RoE on Regulated Equity** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "fundamentals",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "revenue_plf": <float>,
    "ebitda_margin": <float>,
    "net_debt": <float>,
    "dscr": <float>,
    "regulated_roe": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} PLF EBITDA DSCR {quarter} {year}",
    "{company_name} net debt RoE power {year}",
]
