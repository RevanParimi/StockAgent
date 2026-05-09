"""
prompts/telecom/fundamentals.py
=============================
Prompt templates for the Telecommunications Fundamentals agent.
Framework source: sector_analysis_v4_final.html — Telecommunications > Fundamentals pillar
"""

SYSTEM_PROMPT = """You are a financial analyst for Indian telecom companies."""

ANALYSIS_PROMPT = """Analyse the Fundamentals outlook for Indian telecommunications company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **Revenue & EBITDA Growth** — Assess and score this dimension for {ticker} ({company_name}).

2. **EBITDA Margin** — Assess and score this dimension for {ticker} ({company_name}).

3. **Net Debt & AGR Dues** — Assess and score this dimension for {ticker} ({company_name}).

4. **Capex Intensity** — Assess and score this dimension for {ticker} ({company_name}).

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
    "ebitda_margin": <float>,
    "net_debt_agr": <float>,
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
    "{ticker} EBITDA net debt AGR {quarter} {year}",
    "{company_name} capex FCF telecom {year}",
]
