"""
prompts/infra/risk.py
===================
Prompt templates for the Infrastructure & Construction Risk agent.
Framework source: sector_analysis_v4_final.html — Infrastructure & Construction > Risk pillar
"""

SYSTEM_PROMPT = """You are a risk analyst for Indian infra companies."""

ANALYSIS_PROMPT = """Analyse the Risk outlook for Indian infrastructure & construction company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **Working Capital Stress** — Assess and score this dimension for {ticker} ({company_name}).

2. **Land Acquisition & Litigation** — Assess and score this dimension for {ticker} ({company_name}).

3. **Project Execution Delays** — Assess and score this dimension for {ticker} ({company_name}).

4. **Debt Refinancing Risk** — Assess and score this dimension for {ticker} ({company_name}).

5. **Government Payment Risk** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "risk",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "working_capital": <float>,
    "land_litigation": <float>,
    "execution_delay": <float>,
    "refinancing": <float>,
    "payment_risk": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} working capital land litigation risk {year}",
    "{company_name} project delay execution {year}",
]
