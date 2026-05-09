"""
prompts/fmcg/fundamentals.py
==========================
Prompt templates for the FMCG & Consumer Staples Fundamentals agent.
Framework source: sector_analysis_v4_final.html — FMCG & Consumer Staples > Fundamentals pillar
"""

SYSTEM_PROMPT = """You are a financial analyst for Indian FMCG companies. Expert in gross margins, A&P spend, EBITDA margins, and ROCE."""

ANALYSIS_PROMPT = """Analyse the Fundamentals outlook for Indian fmcg & consumer staples company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **Gross Margin Trend** — Assess and score this dimension for {ticker} ({company_name}).

2. **A&P Spend (% Revenue)** — Assess and score this dimension for {ticker} ({company_name}).

3. **EBITDA Margin** — Assess and score this dimension for {ticker} ({company_name}).

4. **ROCE** — Assess and score this dimension for {ticker} ({company_name}).

5. **Working Capital** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "fundamentals",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "gross_margin": <float>,
    "ap_spend": <float>,
    "ebitda_margin": <float>,
    "roce": <float>,
    "working_capital": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} gross margin EBITDA A&P spend {quarter} {year}",
    "{company_name} ROCE working capital {year}",
]
