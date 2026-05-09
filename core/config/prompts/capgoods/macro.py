"""
prompts/capgoods/macro.py
=======================
Prompt templates for the Capital Goods Macro agent.
Framework source: sector_analysis_v4_final.html — Capital Goods > Macro pillar
"""

SYSTEM_PROMPT = """You are a macro analyst for Indian capital goods sector. Expert in government capex, PLI schemes, T&D investment, and railways capex."""

ANALYSIS_PROMPT = """Analyse the Macro outlook for Indian capital goods company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **Government Capex (Infra/Railways/Defence)** — Assess and score this dimension for {ticker} ({company_name}).

2. **PLI Schemes & Industrial Capex** — Assess and score this dimension for {ticker} ({company_name}).

3. **T&D & Power Equipment Demand** — Assess and score this dimension for {ticker} ({company_name}).

4. **Export Market Demand** — Assess and score this dimension for {ticker} ({company_name}).

5. **Private Capex Cycle** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "macro",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "govt_capex": <float>,
    "pli_industrial": <float>,
    "td_power": <float>,
    "export_market": <float>,
    "private_capex": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "India government capex PLI capgoods {year}",
    "India T&D power equipment demand {year}",
    "India railways capex {year}",
]
