"""
prompts/insurance/macro.py
========================
Prompt templates for the Insurance Macro agent.
Framework source: sector_analysis_v4_final.html — Insurance > Macro pillar
"""

SYSTEM_PROMPT = """You are a macro analyst for Indian insurance sector. Expert in IRDAI regulations, interest rates, mortality/morbidity trends, and insurance penetration."""

ANALYSIS_PROMPT = """Analyse the Macro outlook for Indian insurance company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **IRDAI Regulatory Changes** — Assess and score this dimension for {ticker} ({company_name}).

2. **Interest Rate Cycle (Investment Yield)** — Assess and score this dimension for {ticker} ({company_name}).

3. **Insurance Penetration Expansion** — Assess and score this dimension for {ticker} ({company_name}).

4. **Health Inflation** — Assess and score this dimension for {ticker} ({company_name}).

5. **Reinsurance Costs** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "macro",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "irdai_regulation": <float>,
    "interest_rate": <float>,
    "penetration": <float>,
    "health_inflation": <float>,
    "reinsurance": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "IRDAI regulation India insurance {year}",
    "India insurance penetration growth {year}",
    "India health inflation reinsurance {year}",
]
