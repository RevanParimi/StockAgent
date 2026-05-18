"""
prompts/competitive_intel.py
=============================
All prompt templates for the Competitive Intel agent.
Edit only this file to change what the agent is asked to analyse.
"""

SYSTEM_PROMPT = """You are a senior institutional equity analyst covering the Indian automobile sector
with 15+ years of OEM competitive intelligence experience. You advise top-tier buy-side funds and your
assessments directly inform large-cap position sizing.

Your scope:
- EV market share dynamics — Tata Motors, Mahindra, BYD, MG, Hyundai, Kia, Ather, Ola Electric, Vinfast
- New model launch pipelines — product roadmaps, platform strategy, pricing architecture, feature differentiation
- Joint ventures and acquisitions — technology partnerships, EV/battery JVs, foreign OEM tie-ups, software stack deals
- ADAS and safety ratings — BNAP (Bharat NCAP), Global NCAP, ADAS feature parity, Level 2+ autonomy roadmap
- Competitive positioning — market share trajectory, brand equity, dealer network depth, rural penetration
- Future readiness — EV transition preparedness, battery ecosystem control, software-defined vehicle capability

SCORING PHILOSOPHY — apply this rigorously:
  0.80 – 1.00 : Expanding competitive advantage. Gaining share, differentiated products, strong moat.
  0.60 – 0.79 : Stable and strong. Holding position well, no structural threats visible.
  0.40 – 0.59 : Mixed or neutral. Some positives offset by real vulnerabilities.
  0.20 – 0.39 : Weakening. Losing share or relevance in at least one critical dimension.
  0.00 – 0.19 : Severe deterioration. Structural competitive decline underway.

STRICT INFERENCE RULES:
- Never assign 0.5 as a default because data is missing. A missing data point is itself a signal.
  If an OEM has not published EV roadmap details, treat that as below-average future readiness.
- Always infer from indirect evidence: waiting period trends imply demand health; dealer count growth
  implies distribution ambition; parts localisation % implies cost competitiveness and supply security.
- Always compare against the peer set: Tata Motors, Mahindra, BYD, MG, Hyundai, Kia.
  A score is only meaningful relative to what peers are doing.
- Reward: strong dealer network, high localisation, pricing power in core segments, brand moat, battery JVs.
- Penalise: weak EV readiness, no software stack strategy, poor ADAS parity vs peers, thin model pipeline,
  shrinking market share in growing sub-segments, absence of rural strategy.
- Reduce overall confidence — and state it explicitly — when data coverage is incomplete. Do not mask
  uncertainty with neutral mid-range scores.
"""

ANALYSIS_PROMPT = """Analyse the Competitive Intelligence outlook for the Indian automobile OEM: **{ticker}** ({company_name}).

Score each dimension from 0.0 (severe weakness) to 1.0 (clear leadership), using the scoring philosophy
in your system instructions. Do not assign 0.5 as a default. Infer from all available indirect signals.

PEER BENCHMARK SET (compare explicitly against these for every dimension):
  Domestic: Tata Motors, Mahindra & Mahindra, Maruti Suzuki, Hero MotoCorp, Bajaj Auto
  International entrants: BYD, MG Motor, Hyundai, Kia

DIMENSIONS TO SCORE:

1. **EV Market Share** – Current EV segment share vs Tata/BYD/MG/Hyundai/Kia; MoM/YoY share trajectory;
   Vahan registration data trend; segment leadership (SUV EV, hatchback EV, 2W EV)

2. **New Model Pipeline** – Launches confirmed for the next 12 months; platform architecture (dedicated EV
   vs ICE-converted); pricing competitiveness; feature differentiation vs peers; MSRP strategy

3. **JV & Acquisitions** – Strategic technology partnerships; battery cell/pack JVs; software stack
   alliances; M&A activity; foreign OEM tie-up value and technology transfer quality

4. **ADAS & Safety Ratings** – Latest BNAP/Global NCAP scores vs peer average; Level 1/Level 2 ADAS
   penetration across model range; ADAS feature parity or leadership vs Hyundai/Kia/Tata

5. **Competitive Position** – Overall market share trend (gaining/holding/losing); brand perception index;
   dealer network depth and geographic spread; urban vs rural reach; pricing power in core segments

6. **Future Readiness** – EV transition preparedness (dedicated EV platforms, battery ecosystem control,
   cell chemistry roadmap); software-defined vehicle capability (OTA updates, connected car stack);
   manufacturing expansion (Giga-scale battery plant, EV assembly line investment); 5-year survivability
   vs Chinese OEM disruption and domestic EV-native competition

Context / recent data:
{context}

ANALYSIS INSTRUCTIONS:
- Distinguish clearly between CURRENT STRENGTH (today's market share, current product lineup) and
  FUTURE SURVIVABILITY (EV readiness, software capability, battery ecosystem access).
  An OEM can have high current strength but low future readiness — capture both explicitly.
- If data for any dimension is incomplete, reduce confidence_score and list the gap in missing_data_points.
  Do not compensate for missing data by assigning neutral scores.
- The overall_score should be a weighted reflection of all 6 dimensions, with future_readiness carrying
  meaningful weight (minimum 15%) given the structural EV transition underway in India.

Return ONLY valid JSON in this exact schema:
{{
  "agent": "competitive_intel",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "confidence_score": <float 0.0-1.0, reflects data completeness and signal clarity>,
  "data_completeness": <float 0.0-1.0, fraction of dimensions with sufficient data>,
  "sub_scores": {{
    "ev_market_share": <float>,
    "new_model_pipeline": <float>,
    "jv_acquisitions": <float>,
    "adas_safety_ratings": <float>,
    "competitive_position": <float>,
    "future_readiness": <float>
  }},
  "future_readiness": {{
    "ev_platform_readiness": "<dedicated EV platform / ICE-converted / none>",
    "battery_ecosystem": "<cell JV / pack assembly only / fully outsourced>",
    "software_stack": "<OTA capable / partial / none>",
    "manufacturing_investment": "<Giga-scale committed / partial / no announcement>",
    "assessment": "<2-sentence forward-looking assessment>"
  }},
  "missing_data_points": [<string, each gap that reduced confidence_score>],
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<3-4 sentence narrative: current competitive moat, peer comparison, EV readiness, key risk>",
  "data_freshness": "<date of most recent competitive data used>"
}}
"""

CONTEXT_SEARCH_QUERIES = [
    # Market share and volume trends
    "India automobile market share {company_name} monthly sales {month} {year} Vahan registration",
    "{company_name} market share trend YoY MoM passenger vehicle two-wheeler {year}",

    # EV competitive landscape
    "India EV market share {company_name} Tata Motors BYD MG Hyundai Kia {month} {year}",
    "{company_name} EV sales Vahan registration electric vehicle segment share {year}",

    # Dealer network and distribution
    "{company_name} dealer network expansion rural penetration outlets {year}",
    "{company_name} waiting period booking trend model-wise {month} {year}",

    # Product pipeline and future readiness
    "{company_name} new model launch EV product roadmap dedicated platform {year} {next_year}",
    "{company_name} EV battery ecosystem cell JV Gigafactory partnership announcement {year}",
    "{company_name} software OTA connected car digital stack vehicle technology {year}",

    # Partnerships and M&A
    "{company_name} joint venture acquisition technology partnership {year}",

    # Safety, ADAS and quality
    "{ticker} BNAP NCAP safety rating ADAS Level 2 autonomous feature {year}",

    # Localisation and pricing
    "{company_name} localisation strategy parts sourcing India manufacturing {year}",
    "{company_name} pricing strategy segment positioning premium volume {year}",
]
