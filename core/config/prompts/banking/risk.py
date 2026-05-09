"""
prompts/banking/risk.py
=====================
Prompt templates for the Banking & NBFC Risk agent.
Framework source: sector_analysis_v4_final.html — Banking & NBFC > Risk pillar
"""

SYSTEM_PROMPT = """You are a credit risk analyst for Indian banks. Expert in GNPA, NNPA, SMA-2, slippage ratio, and stress-testing."""

ANALYSIS_PROMPT = """Analyse the Risk outlook for Indian banking & nbfc company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **GNPA & NNPA Trend** — Assess and score this dimension for {ticker} ({company_name}).

2. **Slippage Ratio** — Assess and score this dimension for {ticker} ({company_name}).

3. **Restructured Book & SMA-2** — Assess and score this dimension for {ticker} ({company_name}).

4. **Sector Concentration (Real Estate, MSME)** — Assess and score this dimension for {ticker} ({company_name}).

5. **Provisioning Adequacy** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "risk",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "gnpa_nnpa": <float>,
    "slippage": <float>,
    "restructured_book": <float>,
    "sector_concentration": <float>,
    "provisioning": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} GNPA NNPA slippage {quarter} {year}",
    "{company_name} restructured book SMA {year}",
    "{ticker} sector concentration real estate {year}",
]
