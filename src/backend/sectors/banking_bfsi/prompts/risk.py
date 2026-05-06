"""Prompt templates for banking_bfsi/risk."""

SYSTEM_PROMPT = """Credit risk specialist covering Indian banks and NBFCs. Return ONLY valid JSON."""

ANALYSIS_PROMPT = """
{ticker} ({company_name}) as of {analysis_date}.

Context:
{context}

Evaluate:
1. asset_quality_trend — SMA slippage, restructured book
2. concentration_risk — Top-5 borrower exposure
3. deposit_stability — Wholesale deposit %, CASA trend
4. regulatory_risk — RBI/SEBI penalties
5. macro_sensitivity — Rate sensitivity, FX exposure

Return ONLY valid JSON:
{{
  "overall_score": <0.0-1.0>,
  "sub_scores": {{
    "asset_quality_trend": <float>,
    "concentration_risk": <float>,
    "deposit_stability": <float>,
    "regulatory_risk": <float>,
    "macro_sensitivity": <float>,
  }},
  "key_positives": ["..."],
  "key_risks": ["..."],
  "summary": "<2-3 sentence summary>",
  "data_freshness": "<date/quarter>"
}}
"""
