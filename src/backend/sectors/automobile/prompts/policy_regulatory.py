"""
prompts/policy_regulatory.py
=============================
All prompt templates for the Policy & Regulatory agent.
Edit only this file to change what the agent is asked to analyse.
"""

SYSTEM_PROMPT = """You are a specialist analyst for Indian automobile sector government policy and regulatory dynamics.
You have deep expertise in:
- FAME (Faster Adoption and Manufacturing of Hybrid and Electric Vehicles) scheme — subsidy disbursements
- Emission regulations — BS7 roadmap, CAFE (Corporate Average Fuel Economy) standards
- Union Budget — import duties on auto components, PLI (Production Linked Incentive) scheme
- State-level EV incentives — registration waivers, road tax exemptions, purchase subsidies
- Regulatory compliance risk and policy tailwinds for OEMs

Your job is to assess the policy and regulatory environment for a specific automobile OEM and return a
structured JSON score. A HIGH score (near 1.0) means policy is SUPPORTIVE (subsidies, low duties, EV incentives).
A LOW score means policy is a HEADWIND (tighter norms, higher duties, subsidy removal).
Be concise, data-driven, and India-specific.
"""

ANALYSIS_PROMPT = """Analyse the Policy & Regulatory outlook for the Indian automobile company: **{ticker}** ({company_name}).

{business_model_context}

Focus on the following dimensions and score each from 0.0 (very unfavourable / regulatory headwind)
to 1.0 (very favourable / policy tailwind):

1. **FAME / EV Subsidy** – FAME II/III disbursement pace; OEM eligibility and localisation compliance
2. **Emission Norms** – BS7 / CAFE compliance readiness; risk of non-compliance penalties
3. **Union Budget Duties** – Import duty changes on components; PLI incentive capture
4. **PLI Scheme** – PLI utilization rate by this OEM; expected incentive realization timeline
5. **State EV Incentives** – Coverage of this OEM's key markets; state-level registration and road tax benefits

Context / recent data (includes full policy document extracts where available):
{context}

Return ONLY valid JSON. IMPORTANT: Be ticker-specific. Cite actual policy details and financial impacts.
For key_positives/key_risks: quote specific amounts (e.g. "FAME III subsidy INR 10,000 per EV; TATAMOTORS captured ~40% of FY25 disbursements").
For ticker_vs_peers: cite relative policy benefit vs named peers (e.g. "TATAMOTORS most FAME III eligible vs MARUTI EV <2% of portfolio").
For bull_case_if: name the specific policy catalyst + financial benefit (e.g. "If PLI disbursement of INR 500Cr realized in H2 FY26").
For bear_case_if: name the specific regulatory risk + cost impact (e.g. "If BS7 timeline accelerated to FY27, compliance capex INR 800Cr").
For what_changed: cite what shifted in policy environment this cycle vs last (e.g. "FAME III announced with INR 2,500Cr allocation; TATAMOTORS eligibility confirmed").

{{
  "agent": "policy_regulatory",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {{
    "fame_ev_subsidy": <float>,
    "emission_norms": <float>,
    "union_budget_duties": <float>,
    "pli_scheme": <float>,
    "state_ev_incentives": <float>
  }},
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative on policy tailwinds and regulatory risks for this OEM>",
  "data_freshness": "<date of most recent policy data used>",
  "ticker_vs_peers": "<relative policy benefit vs named peers with specific amounts or eligibility>",
  "bull_case_if": "<specific policy catalyst + quantified financial benefit that would add ~0.15 to score>",
  "bear_case_if": "<specific regulatory risk + cost/capex impact that would cut ~0.15 from score>",
  "what_changed": "<what shifted in policy environment this cycle vs last, with specific amounts or dates>",
  "data_confidence": <float 0.3-1.0>
}}
"""

# Tavily queries (full document extraction) — 2 calls, high-value regulatory content
TAVILY_SEARCH_QUERIES = [
    "FAME II III EV subsidy disbursement India automobile {year} MoHI notification",
    "India BS7 CAFE emission norms automobile standard regulation {year}",
]

# Serper queries (news snippets) — 3 calls, budget/PLI/state news
CONTEXT_SEARCH_QUERIES = [
    "India Union Budget automobile component import duty {ticker} {year}",
    "PLI scheme automobile OEM {company_name} utilization incentive {year}",
    "India state EV incentive electric vehicle subsidy registration waiver {year}",
]
