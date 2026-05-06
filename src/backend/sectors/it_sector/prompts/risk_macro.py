"""Prompt templates for it_sector/risk_macro."""

SYSTEM_PROMPT = """Risk analyst covering Indian IT companies. Return ONLY valid JSON."""

ANALYSIS_PROMPT = """
{ticker} ({company_name}) as of {analysis_date}.

Context:
{context}

Evaluate:
1. visa_risk — H1B/L1 approval rates, visa reform
2. ai_disruption — Revenue at risk from GenAI/automation
3. client_concentration — Top-5 client revenue %, churn
4. fx_hedge — INR/USD hedge coverage, derivatives
5. talent_risk — Skilled talent supply, campus hiring

Return ONLY valid JSON:
{{
  "overall_score": <0.0-1.0>,
  "sub_scores": {{
    "visa_risk": <float>,
    "ai_disruption": <float>,
    "client_concentration": <float>,
    "fx_hedge": <float>,
    "talent_risk": <float>,
  }},
  "key_positives": ["..."],
  "key_risks": ["..."],
  "summary": "<2-3 sentence summary>",
  "data_freshness": "<date/quarter>"
}}
"""
