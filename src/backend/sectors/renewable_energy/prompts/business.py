"""Prompt templates for renewable_energy/business."""

SYSTEM_PROMPT = """Energy sector analyst evaluating business quality of Indian renewable companies. Return ONLY valid JSON."""

ANALYSIS_PROMPT = """
{ticker} ({company_name}) as of {analysis_date}.

Context:
{context}

Evaluate:
1. subsector_mix — Solar/Wind/Hydro/Hybrid %, diversification
2. ppa_quality — PPA tariff level, tenor, counterparty quality
3. pipeline_cred — Under-construction %, commissioning track record
4. customer_divers — DISCOM diversification, C&I customer %
5. geography_spread — MW by state, resource quality

Return ONLY valid JSON:
{{
  "overall_score": <0.0-1.0>,
  "sub_scores": {{
    "subsector_mix": <float>,
    "ppa_quality": <float>,
    "pipeline_cred": <float>,
    "customer_divers": <float>,
    "geography_spread": <float>,
  }},
  "key_positives": ["..."],
  "key_risks": ["..."],
  "summary": "<2-3 sentence summary>",
  "data_freshness": "<date/quarter>"
}}
"""
