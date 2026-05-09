"""
prompts/defence/risk.py
=====================
Prompt templates for the Defence & Aerospace Risk agent.
Framework source: sector_analysis_v4_final.html — Defence & Aerospace > Risk pillar
"""

SYSTEM_PROMPT = """You are a risk analyst for Indian defence companies. Expert in programme delays, payment cycles, competition risks, and regulatory risks."""

ANALYSIS_PROMPT = """Analyse the Risk outlook for Indian defence & aerospace company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **Programme Delay Risk** — Assess and score this dimension for {ticker} ({company_name}).

2. **Payment & Receivable Risk** — Assess and score this dimension for {ticker} ({company_name}).

3. **Competition from Imports** — Assess and score this dimension for {ticker} ({company_name}).

4. **Regulatory & Export Control** — Assess and score this dimension for {ticker} ({company_name}).

5. **Concentration Risk** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "risk",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "programme_delay": <float>,
    "payment_risk": <float>,
    "import_competition": <float>,
    "regulatory": <float>,
    "concentration": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} programme delay risk {year}",
    "{company_name} receivables government payment {year}",
    "{ticker} competition imports defence {year}",
]
