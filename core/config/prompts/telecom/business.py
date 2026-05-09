"""
prompts/telecom/business.py
=========================
Prompt templates for the Telecommunications Business agent.
Framework source: sector_analysis_v4_final.html — Telecommunications > Business pillar
"""

SYSTEM_PROMPT = """You are a telecom analyst for Indian operators. Expert in ARPU, subscriber mix, 5G rollout, enterprise business, and fixed broadband."""

ANALYSIS_PROMPT = """Analyse the Business outlook for Indian telecommunications company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **ARPU Trend & Subscriber Mix** — Assess and score this dimension for {ticker} ({company_name}).

2. **5G Rollout & Spectrum** — Assess and score this dimension for {ticker} ({company_name}).

3. **Enterprise & B2B Revenue** — Assess and score this dimension for {ticker} ({company_name}).

4. **Fixed Broadband (FTTH)** — Assess and score this dimension for {ticker} ({company_name}).

5. **Market Share** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "business",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "arpu": <float>,
    "5g_spectrum": <float>,
    "enterprise_b2b": <float>,
    "ftth": <float>,
    "market_share": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} ARPU subscriber 5G {quarter} {year}",
    "{company_name} enterprise broadband FTTH {year}",
    "{ticker} market share telecom India {year}",
]
