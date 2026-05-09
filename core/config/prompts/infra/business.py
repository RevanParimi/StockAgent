"""
prompts/infra/business.py
=======================
Prompt templates for the Infrastructure & Construction Business agent.
Framework source: sector_analysis_v4_final.html — Infrastructure & Construction > Business pillar
"""

SYSTEM_PROMPT = """You are an infrastructure analyst for Indian construction and infra companies. Expert in order books, L1 bid pipeline, HAM/EPC mix, and government capex."""

ANALYSIS_PROMPT = """Analyse the Business outlook for Indian infrastructure & construction company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **Order Book & L1 Pipeline** — Assess and score this dimension for {ticker} ({company_name}).

2. **EPC vs HAM Mix** — Assess and score this dimension for {ticker} ({company_name}).

3. **Sector Diversification** — Assess and score this dimension for {ticker} ({company_name}).

4. **Geographic Mix** — Assess and score this dimension for {ticker} ({company_name}).

5. **Execution Track Record** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "business",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "order_book": <float>,
    "epc_ham_mix": <float>,
    "sector_diversification": <float>,
    "geo_mix": <float>,
    "execution": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} order book L1 pipeline {year}",
    "{company_name} EPC HAM roads infra {year}",
    "{ticker} execution capex {year}",
]
