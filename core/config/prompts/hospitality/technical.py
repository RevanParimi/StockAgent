"""
prompts/hospitality/technical.py
==============================
Prompt templates for the Hospitality & Travel Technical agent.
Framework source: sector_analysis_v4_final.html — Hospitality & Travel > Technical pillar
"""

SYSTEM_PROMPT = """You are a technical analyst for Indian hospitality stocks."""

ANALYSIS_PROMPT = """Analyse the Technical outlook for Indian hospitality & travel company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **Trend (50/200 DMA)** — Assess and score this dimension for {ticker} ({company_name}).

2. **RSI** — Assess and score this dimension for {ticker} ({company_name}).

3. **MACD** — Assess and score this dimension for {ticker} ({company_name}).

4. **Volume** — Assess and score this dimension for {ticker} ({company_name}).

5. **Support/Resistance** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "technical",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "trend": <float>,
    "rsi": <float>,
    "macd": <float>,
    "volume": <float>,
    "support_resistance": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} hospitality hotel stock technical {year}",
]
