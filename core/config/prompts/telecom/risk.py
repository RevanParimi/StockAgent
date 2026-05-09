"""
prompts/telecom/risk.py
=====================
Prompt templates for the Telecommunications Risk agent.
Framework source: sector_analysis_v4_final.html — Telecommunications > Risk pillar
"""

SYSTEM_PROMPT = """You are a risk analyst for Indian telecom companies."""

ANALYSIS_PROMPT = """Analyse the Risk outlook for Indian telecommunications company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **AGR & Regulatory Liability** — Assess and score this dimension for {ticker} ({company_name}).

2. **High Debt & Refinancing** — Assess and score this dimension for {ticker} ({company_name}).

3. **Competitive Pricing Risk (Jio)** — Assess and score this dimension for {ticker} ({company_name}).

4. **Spectrum Renewal Cost** — Assess and score this dimension for {ticker} ({company_name}).

5. **Capex Overrun** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "risk",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "agr_liability": <float>,
    "debt_refinancing": <float>,
    "jio_competition": <float>,
    "spectrum_renewal": <float>,
    "capex_overrun": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} AGR debt risk Jio competition {year}",
    "{company_name} spectrum renewal capex {year}",
]
