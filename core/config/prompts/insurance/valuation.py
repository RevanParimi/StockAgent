"""
prompts/insurance/valuation.py
============================
Prompt templates for the Insurance Valuation agent.
Framework source: sector_analysis_v4_final.html — Insurance > Valuation pillar
"""

SYSTEM_PROMPT = """You are a valuation specialist for Indian insurance stocks."""

ANALYSIS_PROMPT = """Analyse the Valuation outlook for Indian insurance company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **P/EV (Life)** — Assess and score this dimension for {ticker} ({company_name}).

2. **VNB Multiple** — Assess and score this dimension for {ticker} ({company_name}).

3. **P/Book (Non-life)** — Assess and score this dimension for {ticker} ({company_name}).

4. **P/GWP** — Assess and score this dimension for {ticker} ({company_name}).

5. **RoEV-based Fair Value** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "valuation",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "pev": <float>,
    "vnb_multiple": <float>,
    "pbook_nonlife": <float>,
    "p_gwp": <float>,
    "roev_fair_value": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} P/EV VNB multiple insurance valuation {year}",
    "{company_name} P/GWP {year}",
]
