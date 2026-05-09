"""
prompts/media/fundamentals.py
===========================
Prompt templates for the Media & Entertainment Fundamentals agent.
Framework source: sector_analysis_v4_final.html — Media & Entertainment > Fundamentals pillar
"""

SYSTEM_PROMPT = """You are a financial analyst for Indian media companies."""

ANALYSIS_PROMPT = """Analyse the Fundamentals outlook for Indian media & entertainment company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **Revenue Growth** — Assess and score this dimension for {ticker} ({company_name}).

2. **EBITDA Margin** — Assess and score this dimension for {ticker} ({company_name}).

3. **Content Amortisation Policy** — Assess and score this dimension for {ticker} ({company_name}).

4. **Net Debt** — Assess and score this dimension for {ticker} ({company_name}).

5. **FCF Generation** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "fundamentals",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "revenue_growth": <float>,
    "ebitda_margin": <float>,
    "content_amortisation": <float>,
    "net_debt": <float>,
    "fcf": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} EBITDA margin content media {year}",
    "{company_name} net debt FCF {year}",
]
