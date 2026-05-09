"""
prompts/oilgas/business.py
========================
Prompt templates for the Oil & Gas Business agent.
Framework source: sector_analysis_v4_final.html — Oil & Gas > Business pillar
"""

SYSTEM_PROMPT = """You are an oil & gas analyst for Indian E&P and downstream companies. Expert in reserve life, refining margins, petchem, and gas transmission."""

ANALYSIS_PROMPT = """Analyse the Business outlook for Indian oil & gas company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **Reserve Life Index (RLI)** — Assess and score this dimension for {ticker} ({company_name}).

2. **Refining Complexity & GRM** — Assess and score this dimension for {ticker} ({company_name}).

3. **Petchem Integration** — Assess and score this dimension for {ticker} ({company_name}).

4. **Gas Transmission & CGD** — Assess and score this dimension for {ticker} ({company_name}).

5. **Upstream Production Trend** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "business",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "rli": <float>,
    "grm": <float>,
    "petchem": <float>,
    "gas_cgd": <float>,
    "upstream_production": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} reserve life refining margin GRM {year}",
    "{company_name} petchem gas CGD business {year}",
]
