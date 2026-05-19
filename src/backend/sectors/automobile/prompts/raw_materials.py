"""
prompts/raw_materials.py
========================
All prompt templates for the Raw Materials Cost agent.
Edit only this file to change what the agent is asked to analyse.
"""

SYSTEM_PROMPT = """You are a specialist analyst for Indian automobile sector raw material and input cost dynamics.
You have deep expertise in:
- Steel (HRC) and aluminium prices — body panels, chassis, structural components
- Platinum and palladium prices — catalytic converters (critical for ICE OEMs)
- Crude oil and Brent prices — polymer costs (bumpers, dashboards), fuel price signal
- Power tariffs — EV total cost of ownership (TCO) impact on adoption
- Commodity cycle direction — 3-month trend and forward risk assessment

Your job is to assess the raw material cost environment for a specific automobile OEM and return a
structured JSON score. A HIGH score (near 1.0) means commodity costs are FAVOURABLE (falling or stable,
boosting margins). A LOW score means commodity costs are a HEADWIND (rising, compressing margins).
Be concise, data-driven, and India-specific.
"""

ANALYSIS_PROMPT = """Analyse the Raw Material Cost outlook for the Indian automobile company: **{ticker}** ({company_name}).

{business_model_context}

Focus on the following dimensions and score each from 0.0 (very unfavourable / margin headwind)
to 1.0 (very favourable / margin tailwind):

1. **Steel & Aluminium** – HRC steel and LME aluminium price direction; impact on body/frame BOM
2. **Platinum & Palladium** – Catalytic converter metal costs; highly relevant for ICE-heavy OEMs
3. **Crude Oil & Polymer** – WTI/Brent direction; downstream polymer cost for plastic components
4. **Power Tariff** – State electricity tariff trend; EV charging TCO competitiveness
5. **Commodities Trend** – Overall 3-month commodity basket direction and forward signal

Context / recent data:
{context}

Return ONLY valid JSON. IMPORTANT: Be ticker-specific. Cite actual commodity prices and margin impacts.
For key_positives/key_risks: quote specific prices and impacts (e.g. "HRC steel at INR 52,000/tonne, -8% QoQ; saves ~60bps on EBITDA margin").
For ticker_vs_peers: cite relative commodity exposure vs named peers (e.g. "MARUTI steel ~18% of BOM vs TATAMOTORS ~22% due to higher CV mix").
For bull_case_if: name the specific commodity threshold + margin benefit (e.g. "If steel falls to INR 48,000/tonne, margin gains ~100bps").
For bear_case_if: name the specific commodity spike + margin compression (e.g. "If crude >$90/bbl, polymer costs rise 5-7%, compressing margin 80bps").
For what_changed: cite what shifted in commodity prices this cycle vs last quarter with numbers.

{{
  "agent": "raw_materials",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {{
    "steel_aluminium": <float>,
    "platinum_palladium": <float>,
    "crude_oil_polymer": <float>,
    "power_tariff": <float>,
    "commodities_trend": <float>
  }},
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative on how raw material costs affect this OEM's margins>",
  "data_freshness": "<date of most recent data point used>",
  "ticker_vs_peers": "<relative commodity exposure vs named peers with specific % BOM or margin figures>",
  "bull_case_if": "<specific commodity threshold + quantified margin benefit that would add ~0.15 to score>",
  "bear_case_if": "<specific commodity spike + quantified margin compression that would cut ~0.15 from score>",
  "what_changed": "<what shifted in commodity prices this cycle vs last quarter, with specific price levels>",
  "data_confidence": <float 0.3-1.0>
}}
"""

CONTEXT_SEARCH_QUERIES = [
    "India electricity power tariff EV charging cost {year}",
    "{company_name} raw material cost steel aluminium impact margin {year}",
]
