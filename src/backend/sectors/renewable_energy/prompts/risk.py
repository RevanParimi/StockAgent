"""prompts/risk.py -- Renewable Energy (monitoring-only, weight=0.0)"""

SYSTEM_PROMPT = """Risk specialist for Indian renewable energy (weight=0.0, monitoring-only).
DISCOM health (PFC report), curtailment (CERC), PPA tariff protection, execution delay, promoter pledge.
Note: SLDC feeds, satellite irradiance, smart meter feeds all dropped.
"""

ANALYSIS_PROMPT = """Analyse Risk Profile for: **{ticker}** ({company_name}).

1. **discom_credit** -- PFC DISCOM health score; state payment track record; >180-day receivables %.
2. **curtailment_risk** -- State-wise curtailment % from CERC/MNRE; must-run enforcement.
3. **ppa_protection** -- Fixed vs variable tariff; renegotiation history (AP precedent); force majeure.
4. **execution_risk** -- Commissioning delay vs target; LDs activation; EPC contractor quality.
5. **promoter_pledge** -- Pledge % of promoter holding; direction; group leverage contagion.

Context:
{context}

Return ONLY valid JSON:
{{
  "agent": "risk",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {{
    "discom_credit": <float>,
    "curtailment_risk": <float>,
    "ppa_protection": <float>,
    "execution_risk": <float>,
    "promoter_pledge": <float>
  }},
  "key_positives": ["<string>"],
  "key_risks": ["<string>"],
  "summary": "<2-3 sentences on DISCOM health, curtailment, promoter pledge>",
  "data_freshness": "<date>"
}}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} DISCOM payment delay PFC RDSS {year}",
    "{ticker} curtailment risk CERC MNRE state grid {year}",
    "{company_name} PPA tariff protection force majeure {year}",
    "{company_name} commissioning delay execution risk {year}",
    "{ticker} promoter pledge BSE NSE {year}",
]
