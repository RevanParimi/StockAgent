"""
prompts/realestate/macro.py
=========================
Prompt templates for the Real Estate & REITs Macro agent.
Framework source: sector_analysis_v4_final.html — Real Estate & REITs > Macro pillar
"""

SYSTEM_PROMPT = """You are a macro analyst for Indian real estate. Expert in RBI repo rate, home loan rates, housing affordability, and government schemes."""

ANALYSIS_PROMPT = """Analyse the Macro outlook for Indian real estate & reits company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **RBI Repo Rate & Home Loan Rates** — Assess and score this dimension for {ticker} ({company_name}).

2. **Housing Affordability Index** — Assess and score this dimension for {ticker} ({company_name}).

3. **PMAY & Government Schemes** — Assess and score this dimension for {ticker} ({company_name}).

4. **Commercial Real Estate Demand** — Assess and score this dimension for {ticker} ({company_name}).

5. **NRI Demand** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "macro",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "rbi_home_loan": <float>,
    "affordability": <float>,
    "pmay": <float>,
    "commercial_demand": <float>,
    "nri": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "India home loan rates RBI real estate {year}",
    "India housing affordability PMAY {year}",
    "Commercial real estate demand {year}",
]
