"""
prompts/banking/macro.py
======================
Prompt templates for the Banking & NBFC Macro agent.
Framework source: sector_analysis_v4_final.html — Banking & NBFC > Macro pillar
"""

SYSTEM_PROMPT = """You are a macro analyst for Indian banking sector. Expert in RBI policy, credit growth, liquidity, and MSME/infra credit cycles."""

ANALYSIS_PROMPT = """Analyse the Macro outlook for Indian banking & nbfc company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **RBI Repo Rate & Liquidity** — Assess and score this dimension for {ticker} ({company_name}).

2. **System Credit Growth** — Assess and score this dimension for {ticker} ({company_name}).

3. **Deposit Competition** — Assess and score this dimension for {ticker} ({company_name}).

4. **MSME & Agri Policy** — Assess and score this dimension for {ticker} ({company_name}).

5. **Currency & Inflation** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "macro",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "rbi_rate": <float>,
    "credit_growth": <float>,
    "deposit_competition": <float>,
    "msme_policy": <float>,
    "currency": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "RBI repo rate banking credit growth India {year}",
    "India banking system liquidity deposit {year}",
    "RBI MSME credit policy {year}",
]
