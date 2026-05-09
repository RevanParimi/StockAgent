"""
prompts/logistics/earnings.py
===========================
Prompt templates for the Logistics & Supply Chain Earnings agent.
Framework source: sector_analysis_v4_final.html — Logistics & Supply Chain > Earnings pillar
"""

SYSTEM_PROMPT = """You are an earnings analyst for Indian logistics."""

ANALYSIS_PROMPT = """Analyse the Earnings outlook for Indian logistics & supply chain company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **Volume vs Realization** — Assess and score this dimension for {ticker} ({company_name}).

2. **EBITDA Margin Trend** — Assess and score this dimension for {ticker} ({company_name}).

3. **Fuel Cost Impact** — Assess and score this dimension for {ticker} ({company_name}).

4. **New Network Ramp-up** — Assess and score this dimension for {ticker} ({company_name}).

5. **Guidance vs Actual** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "earnings",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "volume_realization": <float>,
    "ebitda_margin": <float>,
    "fuel_impact": <float>,
    "network_ramp": <float>,
    "guidance": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} volume realization EBITDA {quarter} {year}",
    "{company_name} fuel margin guidance {year}",
]
