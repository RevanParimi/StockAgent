"""
prompts/tech/macro.py
===================
Prompt templates for the Information Technology Macro agent.
Framework source: sector_analysis_v4_final.html — Information Technology > Macro pillar
"""

SYSTEM_PROMPT = """You are a macro analyst for Indian IT sector. Expert in US tech spending, Fed rates, USDINR, H1B visa policy, and GenAI disruption."""

ANALYSIS_PROMPT = """Analyse the Macro outlook for Indian information technology company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **US IT Spending Outlook** — Assess and score this dimension for {ticker} ({company_name}).

2. **Fed Rate & USD/INR** — Assess and score this dimension for {ticker} ({company_name}).

3. **H1B Visa Policy** — Assess and score this dimension for {ticker} ({company_name}).

4. **GenAI Disruption Risk** — Assess and score this dimension for {ticker} ({company_name}).

5. **European Demand** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "macro",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "us_spending": <float>,
    "usd_inr": <float>,
    "h1b": <float>,
    "genai_disruption": <float>,
    "europe_demand": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "US enterprise IT spending {year}",
    "Fed rate USD INR impact Indian IT {year}",
    "H1B visa policy India IT {year}",
    "GenAI disruption IT services {year}",
]
