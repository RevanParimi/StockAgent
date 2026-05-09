"""
prompts/oilgas/fundamentals.py
============================
Prompt templates for the Oil & Gas Fundamentals agent.
Framework source: sector_analysis_v4_final.html — Oil & Gas > Fundamentals pillar
"""

SYSTEM_PROMPT = """You are a financial analyst for Indian oil & gas companies."""

ANALYSIS_PROMPT = """Analyse the Fundamentals outlook for Indian oil & gas company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **Revenue & EBITDA Growth** — Assess and score this dimension for {ticker} ({company_name}).

2. **GRM / EBITDA/boe** — Assess and score this dimension for {ticker} ({company_name}).

3. **Net Debt & Leverage** — Assess and score this dimension for {ticker} ({company_name}).

4. **Capex Cycle** — Assess and score this dimension for {ticker} ({company_name}).

5. **FCF Generation** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "fundamentals",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "revenue_ebitda": <float>,
    "grm_ebitda": <float>,
    "net_debt": <float>,
    "capex": <float>,
    "fcf": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} EBITDA GRM net debt {quarter} {year}",
    "{company_name} capex FCF oil gas {year}",
]
