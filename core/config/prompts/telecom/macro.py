"""
prompts/telecom/macro.py
======================
Prompt templates for the Telecommunications Macro agent.
Framework source: sector_analysis_v4_final.html — Telecommunications > Macro pillar
"""

SYSTEM_PROMPT = """You are a macro analyst for Indian telecom sector. Expert in spectrum auctions, TRAI regulations, government levies, and 5G policy."""

ANALYSIS_PROMPT = """Analyse the Macro outlook for Indian telecommunications company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **Spectrum Auction & 5G Policy** — Assess and score this dimension for {ticker} ({company_name}).

2. **TRAI Tariff Regulation** — Assess and score this dimension for {ticker} ({company_name}).

3. **AGR & Govt Dues** — Assess and score this dimension for {ticker} ({company_name}).

4. **Tower Infrastructure Policy** — Assess and score this dimension for {ticker} ({company_name}).

5. **Digital India Demand** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "macro",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "spectrum_5g": <float>,
    "trai_tariff": <float>,
    "agr_dues": <float>,
    "tower_policy": <float>,
    "digital_india": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "India 5G spectrum auction TRAI telecom {year}",
    "AGR dues Supreme Court telecom India {year}",
    "India Digital India telecom policy {year}",
]
