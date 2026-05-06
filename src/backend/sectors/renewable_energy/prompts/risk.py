"""Prompt templates for renewable_energy/risk."""

SYSTEM_PROMPT = """Risk specialist for Indian renewable energy projects. Return ONLY valid JSON."""

ANALYSIS_PROMPT = """
{ticker} ({company_name}) as of {analysis_date}.

Context:
{context}

Evaluate (1.0=low risk, 0.0=high risk — inverse scoring):
1. discom_credit — DISCOM payment delays, UDAY/RDSS compliance
2. regulatory_change — Retroactive tariff renegotiation, curtailment
3. weather_resource — Monsoon variability, generation impact
4. grid_integration — Transmission bottlenecks, curtailment %
5. commodity_input — Steel/copper capex impact, module prices

Return ONLY valid JSON:
{{
  "overall_score": <0.0-1.0>,
  "sub_scores": {{
    "discom_credit": <float>,
    "regulatory_change": <float>,
    "weather_resource": <float>,
    "grid_integration": <float>,
    "commodity_input": <float>,
  }},
  "key_positives": ["..."],
  "key_risks": ["..."],
  "summary": "<2-3 sentence summary>",
  "data_freshness": "<date/quarter>"
}}
"""
