"""
prompts/agrochem/macro.py
=======================
Prompt templates for the Agrochemicals & Fertilizers Macro agent.
Framework source: sector_analysis_v4_final.html — Agrochemicals & Fertilizers > Macro pillar
"""

SYSTEM_PROMPT = """You are a macro analyst for Indian agrochemicals. Expert in kharif/rabi crop cycles, monsoon, China technical grades pricing, and global crop protection."""

ANALYSIS_PROMPT = """Analyse the Macro outlook for Indian agrochemicals & fertilizers company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **Monsoon & Crop Season Outlook** — Assess and score this dimension for {ticker} ({company_name}).

2. **China Technical Grade Pricing** — Assess and score this dimension for {ticker} ({company_name}).

3. **Global Crop Protection Market** — Assess and score this dimension for {ticker} ({company_name}).

4. **India Pesticide Regulation (CIB)** — Assess and score this dimension for {ticker} ({company_name}).

5. **Commodity Crop Prices** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "macro",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "monsoon_crop": <float>,
    "china_pricing": <float>,
    "global_market": <float>,
    "cib_regulation": <float>,
    "commodity_prices": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "India monsoon kharif rabi agrochem {year}",
    "China agrochemical technical grade pricing {year}",
    "Global crop protection market {year}",
    "India CIB pesticide regulation {year}",
]
