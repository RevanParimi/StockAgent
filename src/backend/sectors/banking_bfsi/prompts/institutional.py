"""Prompt templates for banking_bfsi/institutional."""

SYSTEM_PROMPT = """Equity analyst tracking smart money flow for Indian banking stocks. Return ONLY valid JSON."""

ANALYSIS_PROMPT = """
{ticker} ({company_name}) as of {analysis_date}.

Context:
{context}

Evaluate:
1. fii_dii_flow — Net FII/DII buying over 1M and 3M
2. promoter_holding — Promoter stake change, pledge %
3. insider_trades — ESOP exercises, open-market purchases/sales
4. analyst_changes — Rating upgrades/downgrades, target revisions
5. institutional_conc — Mutual fund holding %, top-10 institutional

Return ONLY valid JSON:
{{
  "overall_score": <0.0-1.0>,
  "sub_scores": {{
    "fii_dii_flow": <float>,
    "promoter_holding": <float>,
    "insider_trades": <float>,
    "analyst_changes": <float>,
    "institutional_conc": <float>,
  }},
  "key_positives": ["..."],
  "key_risks": ["..."],
  "summary": "<2-3 sentence summary>",
  "data_freshness": "<date/quarter>"
}}
"""
