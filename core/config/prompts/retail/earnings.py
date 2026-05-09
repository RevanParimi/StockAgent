"""
prompts/retail/earnings.py
========================
Prompt templates for the Retail & Consumer Discretionary Earnings agent.
Framework source: sector_analysis_v4_final.html — Retail & Consumer Discretionary > Earnings pillar
"""

SYSTEM_PROMPT = """You are an earnings analyst for Indian retail."""

ANALYSIS_PROMPT = """Analyse the Earnings outlook for Indian retail & consumer discretionary company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **SSSG vs Guidance** — Assess and score this dimension for {ticker} ({company_name}).

2. **Gross Margin Trend** — Assess and score this dimension for {ticker} ({company_name}).

3. **Opex Leverage** — Assess and score this dimension for {ticker} ({company_name}).

4. **New Store Ramp-up** — Assess and score this dimension for {ticker} ({company_name}).

5. **One-time Items** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "earnings",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "sssg_guidance": <float>,
    "gross_margin": <float>,
    "opex_leverage": <float>,
    "new_store": <float>,
    "one_time": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} SSSG earnings margin {quarter} {year}",
    "{company_name} guidance retail {year}",
]
