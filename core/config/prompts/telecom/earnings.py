"""
prompts/telecom/earnings.py
=========================
Prompt templates for the Telecommunications Earnings agent.
Framework source: sector_analysis_v4_final.html — Telecommunications > Earnings pillar
"""

SYSTEM_PROMPT = """You are an earnings analyst for Indian telecom."""

ANALYSIS_PROMPT = """Analyse the Earnings outlook for Indian telecommunications company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **ARPU Improvement vs Guidance** — Assess and score this dimension for {ticker} ({company_name}).

2. **EBITDA vs Consensus** — Assess and score this dimension for {ticker} ({company_name}).

3. **Subscriber Additions** — Assess and score this dimension for {ticker} ({company_name}).

4. **Capex vs Budget** — Assess and score this dimension for {ticker} ({company_name}).

5. **Debt Reduction Progress** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "earnings",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "arpu_guidance": <float>,
    "ebitda_consensus": <float>,
    "subscriber_adds": <float>,
    "capex_budget": <float>,
    "debt_reduction": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} ARPU EBITDA subscriber {quarter} {year}",
    "{company_name} earnings guidance {year}",
]
