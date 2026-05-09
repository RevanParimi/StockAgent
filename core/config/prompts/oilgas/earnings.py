"""
prompts/oilgas/earnings.py
========================
Prompt templates for the Oil & Gas Earnings agent.
Framework source: sector_analysis_v4_final.html — Oil & Gas > Earnings pillar
"""

SYSTEM_PROMPT = """You are an earnings analyst for Indian oil & gas."""

ANALYSIS_PROMPT = """Analyse the Earnings outlook for Indian oil & gas company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **GRM vs Benchmark** — Assess and score this dimension for {ticker} ({company_name}).

2. **Production Volume vs Guidance** — Assess and score this dimension for {ticker} ({company_name}).

3. **Inventory Gains/Losses** — Assess and score this dimension for {ticker} ({company_name}).

4. **Under-recovery Impact** — Assess and score this dimension for {ticker} ({company_name}).

5. **Forex Impact** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "earnings",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "grm_vs_benchmark": <float>,
    "production_volume": <float>,
    "inventory": <float>,
    "under_recovery": <float>,
    "forex": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} GRM earnings production {quarter} {year}",
    "{company_name} under-recovery inventory gains {year}",
]
