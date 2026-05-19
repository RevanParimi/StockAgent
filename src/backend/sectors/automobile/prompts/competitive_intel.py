"""
prompts/competitive_intel.py
=============================
All prompt templates for the Competitive Intel agent.
Edit only this file to change what the agent is asked to analyse.
"""

SYSTEM_PROMPT = """You are a specialist analyst for Indian automobile sector competitive intelligence.
You have deep expertise in:
- EV market share dynamics — Tata Motors, MG, BYD, Ather, Ola, Vinfast, Hero Electric
- New model launch pipelines — OEM product roadmaps, pricing strategy, feature differentiation
- Joint ventures and acquisitions — technology partnerships, EV battery JVs, foreign OEM tie-ups
- ADAS and safety ratings — BNAP (Bharat New Car Assessment Programme), Global NCAP, ADAS milestones
- Competitive positioning — market share trends, brand strength, dealer network reach

Your job is to assess the competitive intelligence outlook for a specific automobile OEM and return a
structured JSON score. A HIGH score (near 1.0) means the OEM has STRONG competitive positioning
(gaining share, rich pipeline, strong safety ratings, strategic partnerships).
A LOW score means the OEM is LOSING ground (shrinking share, thin pipeline, poor ratings).
Be concise, data-driven, and India-specific.
"""

ANALYSIS_PROMPT = """Analyse the Competitive Intelligence outlook for the Indian automobile company: **{ticker}** ({company_name}).

{business_model_context}

Focus on the following dimensions and score each from 0.0 (very weak competitive position)
to 1.0 (very strong competitive position):

1. **EV Market Share** – Current EV segment share vs Tata/BYD/Ather/Ola/MG; share trajectory
2. **New Model Pipeline** – Upcoming launches in next 12 months; pricing competitiveness; EV models
3. **JV & Acquisitions** – Strategic partnerships, technology JVs, M&A activity and value
4. **ADAS & Safety Ratings** – BNAP/NCAP scores vs peers; ADAS feature parity or leadership
5. **Competitive Position** – Overall market share trend, brand perception, dealer network strength

Context / recent data:
{context}

Return ONLY valid JSON. IMPORTANT: Be ticker-specific. Cite actual market share figures and competitive data.
For key_positives/key_risks: quote specific figures (e.g. "TATAMOTORS EV share 65% in PV-EV segment; Tiago EV sold 8,000 units/month").
For ticker_vs_peers: cite specific market share % vs named competitors (e.g. "TATAMOTORS EV 65% vs MG 12% vs BYD 8% of PV-EV market").
For bull_case_if: name the specific competitive event + share gain (e.g. "If e-Vitara launch captures 8% EV share by FY27, MARUTI re-rated").
For bear_case_if: name the competitive threat + share loss (e.g. "If BYD/Hyundai takes 15% EV share, TATAMOTORS drops to 50% EV share").
For what_changed: cite what shifted in competitive landscape this cycle (e.g. "Ola S1 recalls impacted 2W EV share; TVS iQube gained 200bps").

{{
  "agent": "competitive_intel",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {{
    "ev_market_share": <float>,
    "new_model_pipeline": <float>,
    "jv_acquisitions": <float>,
    "adas_safety_ratings": <float>,
    "competitive_position": <float>
  }},
  "key_positives": [<string>, ...],
  "key_risks": [<string>, ...],
  "summary": "<2-3 sentence narrative on competitive positioning and moat strength>",
  "data_freshness": "<date of most recent competitive data used>",
  "ticker_vs_peers": "<specific market share % vs named competitors in relevant segments>",
  "bull_case_if": "<specific competitive event + share gain threshold that would add ~0.15 to score>",
  "bear_case_if": "<specific competitive threat + share loss that would cut ~0.15 from score>",
  "what_changed": "<what shifted in competitive landscape this cycle vs last, with specific share/model data>",
  "data_confidence": <float 0.3-1.0>
}}
"""

CONTEXT_SEARCH_QUERIES = [
    "India EV market share {company_name} Tata Motors BYD Ather Ola {month} {year}",
    "{company_name} new model launch pipeline EV product roadmap {year}",
    "{company_name} joint venture acquisition partnership {year}",
    "{ticker} BNAP NCAP safety rating ADAS autonomous feature {year}",
]
