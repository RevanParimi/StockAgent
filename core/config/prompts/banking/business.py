"""
prompts/banking/business.py
=========================
Prompt templates for the Banking & NBFC Business agent.
Framework source: sector_analysis_v4_final.html — Banking & NBFC > Business pillar
"""

SYSTEM_PROMPT = """You are a banking sector analyst for Indian banks and NBFCs. Expert in loan mix, CASA ratio, fee income, and retail vs corporate franchise."""

ANALYSIS_PROMPT = """Analyse the Business outlook for Indian banking & nbfc company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **Loan Book Growth & Mix** — Assess and score this dimension for {ticker} ({company_name}).

2. **CASA Ratio & Deposit Franchise** — Assess and score this dimension for {ticker} ({company_name}).

3. **Fee Income & Cross-sell** — Assess and score this dimension for {ticker} ({company_name}).

4. **Retail vs Corporate Mix** — Assess and score this dimension for {ticker} ({company_name}).

5. **Market Share** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "business",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "loan_growth": <float>,
    "casa_ratio": <float>,
    "fee_income": <float>,
    "retail_corporate_mix": <float>,
    "market_share": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} loan growth CASA ratio {quarter} {year}",
    "{company_name} retail corporate loan mix {year}",
    "{ticker} fee income {year}",
]
