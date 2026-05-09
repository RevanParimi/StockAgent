"""
prompts/infra/macro.py
====================
Prompt templates for the Infrastructure & Construction Macro agent.
Framework source: sector_analysis_v4_final.html — Infrastructure & Construction > Macro pillar
"""

SYSTEM_PROMPT = """You are a macro analyst for Indian infrastructure sector. Expert in government capex budgets, NIP, NHAI pipeline, and RBI rate impact on project viability."""

ANALYSIS_PROMPT = """Analyse the Macro outlook for Indian infrastructure & construction company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **Government Capex Budget** — Assess and score this dimension for {ticker} ({company_name}).

2. **NHAI/Railways/Airport Pipeline** — Assess and score this dimension for {ticker} ({company_name}).

3. **RBI Rate & Project IRR** — Assess and score this dimension for {ticker} ({company_name}).

4. **State Capex Spend** — Assess and score this dimension for {ticker} ({company_name}).

5. **PLI & Industrial Capex** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "macro",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "govt_capex": <float>,
    "nhai_pipeline": <float>,
    "rbi_rate": <float>,
    "state_capex": <float>,
    "pli": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "India government capex budget infrastructure {year}",
    "NHAI roads railways airport pipeline {year}",
    "India infrastructure NIP {year}",
]
