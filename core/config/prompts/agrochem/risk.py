"""
prompts/agrochem/risk.py
======================
Prompt templates for the Agrochemicals & Fertilizers Risk agent.
Framework source: sector_analysis_v4_final.html — Agrochemicals & Fertilizers > Risk pillar
"""

SYSTEM_PROMPT = """You are a risk analyst for Indian agrochem companies."""

ANALYSIS_PROMPT = """Analyse the Risk outlook for Indian agrochemicals & fertilizers company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **Monsoon Failure Risk** — Assess and score this dimension for {ticker} ({company_name}).

2. **China Dumping & Price Erosion** — Assess and score this dimension for {ticker} ({company_name}).

3. **Patent Cliff on In-licensed AIs** — Assess and score this dimension for {ticker} ({company_name}).

4. **Regulatory Bans (CIB)** — Assess and score this dimension for {ticker} ({company_name}).

5. **Inventory Build-up Risk** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "risk",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "monsoon_risk": <float>,
    "china_dumping": <float>,
    "patent_cliff": <float>,
    "regulatory_ban": <float>,
    "inventory_risk": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} monsoon risk China dumping agrochem {year}",
    "{company_name} patent cliff CIB ban {year}",
]
