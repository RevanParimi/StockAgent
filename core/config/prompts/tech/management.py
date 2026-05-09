"""
prompts/tech/management.py
========================
Prompt templates for the Information Technology Management agent.
Framework source: sector_analysis_v4_final.html — Information Technology > Management pillar
"""

SYSTEM_PROMPT = """You are a governance analyst for Indian IT companies."""

ANALYSIS_PROMPT = """Analyse the Management outlook for Indian information technology company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **CEO Track Record & Vision** — Assess and score this dimension for {ticker} ({company_name}).

2. **Capital Allocation (Buyback/Dividend)** — Assess and score this dimension for {ticker} ({company_name}).

3. **RPT & Subsidiary Risk** — Assess and score this dimension for {ticker} ({company_name}).

4. **Bench Strength** — Assess and score this dimension for {ticker} ({company_name}).

5. **ESG** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "management",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "ceo_track_record": <float>,
    "capital_allocation": <float>,
    "rpt": <float>,
    "bench_strength": <float>,
    "esg": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} management CEO capital allocation {year}",
    "{company_name} buyback dividend {year}",
]
