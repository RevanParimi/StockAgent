"""Prompt templates for renewable_energy/valuation."""

SYSTEM_PROMPT = """Valuation analyst for Indian renewable energy stocks using sector-specific multiples. Return ONLY valid JSON."""

ANALYSIS_PROMPT = """
{ticker} ({company_name}) as of {analysis_date}.

Context:
{context}

Evaluate:
1. ev_per_mw — EV/MW vs peer range (Solar: Rs 4-6Cr/MW, Wind: Rs 5-8Cr/MW)
2. ev_ebitda — EV/EBITDA vs healthy range 15-25x
3. tariff_vs_auction — Existing PPA vs MNRE auction L1 rates
4. pipeline_dcf — Pipeline value with -25% haircut on unbuilt MW
5. implied_irr — Implied equity IRR vs WACC (target spread >= 200bps)

Return ONLY valid JSON:
{{
  "overall_score": <0.0-1.0>,
  "sub_scores": {{
    "ev_per_mw": <float>,
    "ev_ebitda": <float>,
    "tariff_vs_auction": <float>,
    "pipeline_dcf": <float>,
    "implied_irr": <float>,
  }},
  "key_positives": ["..."],
  "key_risks": ["..."],
  "summary": "<2-3 sentence summary>",
  "data_freshness": "<date/quarter>"
}}
"""
