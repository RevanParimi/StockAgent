"""
prompts/banking/fundamentals.py
=============================
Prompt templates for the Banking & NBFC Fundamentals agent.
Framework source: sector_analysis_v4_final.html — Banking & NBFC > Fundamentals pillar
"""

SYSTEM_PROMPT = """You are a financial analyst for Indian banks. Expert in NIM, RoA, RoE, CET1, cost-to-income ratio."""

ANALYSIS_PROMPT = """Analyse the Fundamentals outlook for Indian banking & nbfc company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **NIM (Net Interest Margin)** — Assess and score this dimension for {ticker} ({company_name}).

2. **RoA & RoE** — Assess and score this dimension for {ticker} ({company_name}).

3. **CET1 Capital Adequacy** — Assess and score this dimension for {ticker} ({company_name}).

4. **Cost-to-Income Ratio** — Assess and score this dimension for {ticker} ({company_name}).

5. **Provision Coverage Ratio** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "fundamentals",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "nim": <float>,
    "roa_roe": <float>,
    "cet1": <float>,
    "cost_income": <float>,
    "pcr": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} NIM RoA RoE {quarter} {year}",
    "{company_name} CET1 capital adequacy {year}",
    "{ticker} cost income ratio provisions {year}",
]
