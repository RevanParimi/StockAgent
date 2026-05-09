"""
prompts/banking/valuation.py
==========================
Prompt templates for the Banking & NBFC Valuation agent.
Framework source: sector_analysis_v4_final.html — Banking & NBFC > Valuation pillar
"""

SYSTEM_PROMPT = """You are a valuation specialist for Indian bank stocks. Expert in P/BV, P/ABV, and RoE-based fair value."""

ANALYSIS_PROMPT = """Analyse the Valuation outlook for Indian banking & nbfc company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **P/BV vs Peers** — Assess and score this dimension for {ticker} ({company_name}).

2. **P/ABV** — Assess and score this dimension for {ticker} ({company_name}).

3. **RoE-based Target** — Assess and score this dimension for {ticker} ({company_name}).

4. **Franchise Premium** — Assess and score this dimension for {ticker} ({company_name}).

5. **P/E** — Assess and score this dimension for {ticker} ({company_name}).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{
  "agent": "valuation",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {
    "pbv": <float>,
    "pabv": <float>,
    "roe_based": <float>,
    "franchise_premium": <float>,
    "pe": <float>,
  },
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative>",
  "data_freshness": "<date of most recent data point used>"
}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} P/BV P/ABV banking valuation {year}",
    "{company_name} vs HDFC ICICI multiple {year}",
]
