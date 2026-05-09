"""
prompts/tech/risk.py
==================
Prompt templates for the Information Technology Risk agent.
Framework source: sector_analysis_v4_final.html — Information Technology > Risk pillar
"""

SYSTEM_PROMPT = """You are a risk analyst for Indian IT companies. Expert in pricing pressure, automation risk, deal ramp-down, and client industry exposure."""

ANALYSIS_PROMPT = """Analyse the Risk outlook for Indian information technology company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **Pricing Pressure & Commoditisation** — Assess and score this dimension for {ticker} ({company_name}).

2. **Automation & AI Displacement** — Assess and score this dimension for {ticker} ({company_name}).

3. **Large Deal Ramp Risk** — Assess and score this dimension for {ticker} ({company_name}).

4. **BFSI/Retail Client Exposure** — Assess and score this dimension for {ticker} ({company_name}).

5. **Regulatory & Data Privacy** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "risk",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "pricing_pressure": <float>,
    "automation_risk": <float>,
    "deal_ramp": <float>,
    "sector_exposure": <float>,
    "regulatory": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} pricing pressure deal ramp {year}",
    "{company_name} BFSI retail exposure risk {year}",
]
