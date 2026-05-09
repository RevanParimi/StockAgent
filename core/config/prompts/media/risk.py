"""
prompts/media/risk.py
===================
Prompt templates for the Media & Entertainment Risk agent.
Framework source: sector_analysis_v4_final.html — Media & Entertainment > Risk pillar
"""

SYSTEM_PROMPT = """You are a risk analyst for Indian media companies."""

ANALYSIS_PROMPT = """Analyse the Risk outlook for Indian media & entertainment company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **Ad Revenue Cyclicality** — Assess and score this dimension for {ticker} ({company_name}).

2. **OTT Competition & Content Costs** — Assess and score this dimension for {ticker} ({company_name}).

3. **Piracy** — Assess and score this dimension for {ticker} ({company_name}).

4. **Regulatory (MIB)** — Assess and score this dimension for {ticker} ({company_name}).

5. **Single Platform Dependence** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "risk",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "ad_cyclicality": <float>,
    "ott_competition": <float>,
    "piracy": <float>,
    "regulatory": <float>,
    "platform_dependence": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} ad revenue risk OTT competition {year}",
    "{company_name} piracy regulatory media {year}",
]
