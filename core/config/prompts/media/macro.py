"""
prompts/media/macro.py
====================
Prompt templates for the Media & Entertainment Macro agent.
Framework source: sector_analysis_v4_final.html — Media & Entertainment > Macro pillar
"""

SYSTEM_PROMPT = """You are a macro analyst for Indian media sector. Expert in ad market growth, GDP correlation, OTT disruption, and regulatory environment."""

ANALYSIS_PROMPT = """Analyse the Macro outlook for Indian media & entertainment company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **India Ad Market Growth** — Assess and score this dimension for {ticker} ({company_name}).

2. **GDP & Consumer Sentiment** — Assess and score this dimension for {ticker} ({company_name}).

3. **OTT Disruption of TV** — Assess and score this dimension for {ticker} ({company_name}).

4. **TRAI & MIB Regulation** — Assess and score this dimension for {ticker} ({company_name}).

5. **Broadband Penetration** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "macro",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "ad_market": <float>,
    "gdp_sentiment": <float>,
    "ott_disruption": <float>,
    "trai_mib": <float>,
    "broadband": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "India advertising market growth {year}",
    "OTT disruption traditional TV India {year}",
    "TRAI MIB media regulation {year}",
]
