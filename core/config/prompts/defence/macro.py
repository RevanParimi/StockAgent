"""
prompts/defence/macro.py
======================
Prompt templates for the Defence & Aerospace Macro agent.
Framework source: sector_analysis_v4_final.html — Defence & Aerospace > Macro pillar
"""

SYSTEM_PROMPT = """You are a macro analyst for Indian defence sector. Expert in defence budget, FDI policy, geopolitical triggers, and SIPRI data."""

ANALYSIS_PROMPT = """Analyse the Macro outlook for Indian defence & aerospace company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **Defence Budget Allocation** — Assess and score this dimension for {ticker} ({company_name}).

2. **FDI & Private Sector Policy** — Assess and score this dimension for {ticker} ({company_name}).

3. **Geopolitical Risk Premium** — Assess and score this dimension for {ticker} ({company_name}).

4. **HAL/BEL/DRDO Order Pipeline** — Assess and score this dimension for {ticker} ({company_name}).

5. **Offset & Make-in-India Policy** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "macro",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "defence_budget": <float>,
    "fdi_policy": <float>,
    "geopolitical": <float>,
    "order_pipeline": <float>,
    "make_in_india": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "India defence budget allocation {year}",
    "Make in India defence policy {year}",
    "India geopolitical risk defence spending {year}",
    "{ticker} government order pipeline {year}",
]
