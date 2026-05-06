"""Prompt templates for banking_bfsi/fundamentals."""

SYSTEM_PROMPT = """Senior banking analyst specialising in Indian BFSI. Analyse credit quality, capital adequacy, and profitability. Return ONLY valid JSON."""

ANALYSIS_PROMPT = """
{ticker} ({company_name}) as of {analysis_date}.

Context:
{context}

Evaluate (score 0.0-1.0):
1. asset_quality — Gross NPA, Net NPA, PCR
2. net_interest — NIM trend, CASA ratio
3. capital_adequacy — CRAR/CET1 vs RBI minimum
4. profitability — RoA, RoE, credit cost, cost-to-income
5. loan_mix — Retail vs corporate, secured vs unsecured

Return ONLY valid JSON:
{{
  "overall_score": <0.0-1.0>,
  "sub_scores": {{
    "asset_quality": <float>,
    "net_interest": <float>,
    "capital_adequacy": <float>,
    "profitability": <float>,
    "loan_mix": <float>,
  }},
  "key_positives": ["..."],
  "key_risks": ["..."],
  "summary": "<2-3 sentence summary>",
  "data_freshness": "<date/quarter>"
}}
"""
