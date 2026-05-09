"""
prompts/defence/earnings.py
=========================
Prompt templates for the Defence & Aerospace Earnings agent.
Framework source: sector_analysis_v4_final.html — Defence & Aerospace > Earnings pillar
"""

SYSTEM_PROMPT = """You are an earnings quality analyst for Indian defence companies."""

ANALYSIS_PROMPT = """Analyse the Earnings outlook for Indian defence & aerospace company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **Revenue Recognition Policy** — Assess and score this dimension for {ticker} ({company_name}).

2. **Order-to-Revenue Conversion** — Assess and score this dimension for {ticker} ({company_name}).

3. **Margin Trajectory** — Assess and score this dimension for {ticker} ({company_name}).

4. **Exceptional Items** — Assess and score this dimension for {ticker} ({company_name}).

5. **Guidance vs Actual** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "earnings",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "revenue_recognition": <float>,
    "order_conversion": <float>,
    "margin_trajectory": <float>,
    "exceptional_items": <float>,
    "guidance_accuracy": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} quarterly results earnings {quarter} {year}",
    "{company_name} revenue recognition policy defence {year}",
    "{ticker} margin guidance actual {year}",
]
