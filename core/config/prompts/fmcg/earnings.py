"""
prompts/fmcg/earnings.py
======================
Prompt templates for the FMCG & Consumer Staples Earnings agent.
Framework source: sector_analysis_v4_final.html — FMCG & Consumer Staples > Earnings pillar
"""

SYSTEM_PROMPT = """You are an earnings analyst for Indian FMCG."""

ANALYSIS_PROMPT = """Analyse the Earnings outlook for Indian fmcg & consumer staples company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **Volume vs Price Growth** — Assess and score this dimension for {ticker} ({company_name}).

2. **Gross Margin Trajectory** — Assess and score this dimension for {ticker} ({company_name}).

3. **A&P Cuts vs Brand Health** — Assess and score this dimension for {ticker} ({company_name}).

4. **Guidance vs Actual** — Assess and score this dimension for {ticker} ({company_name}).

5. **Premiumisation Revenue Share** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "earnings",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "volume_price": <float>,
    "gross_margin": <float>,
    "ap_cuts": <float>,
    "guidance": <float>,
    "premium_share": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} volume price growth earnings {quarter} {year}",
    "{company_name} margin guidance {year}",
]
