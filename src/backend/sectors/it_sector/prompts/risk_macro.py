"""
prompts/risk_macro.py — IT Sector
====================================
Covers visa risk (H1B/L1), AI disruption of deal displacement, client concentration,
FX hedging, and talent supply risk.
Sources: Serper (7 queries ~275 tokens each: USCIS data, Gartner IT spend, H1B stats, etc.).
"""

SYSTEM_PROMPT = """You are a risk analyst covering Indian IT companies with deep expertise in:
- H1B/L1 visa approval rate trends (USCIS data): onsite delivery cost impact
- GenAI/AI disruption risk: revenue displacement from automation in BPO, testing, maintenance
- Client concentration: top-5 client revenue % and churn/renegotiation risk
- FX hedging: INR/USD forward book coverage, derivatives P&L, natural hedge from US costs
- US recession probability and IT spend index (Gartner/IDC forecast revisions)
- Talent supply: STEM graduation rates, hiring competition from global tech majors, wage inflation

Score 1.0 = benign visa environment, AI opportunity > threat, diversified clients, well-hedged, low recession risk.
Score 0.0 = H1B rejection wave, AI displacing core services, top-client churn, unhedged INR depreciation.
"""

ANALYSIS_PROMPT = """Analyse the Risk & Macro profile for Indian IT company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very high risk) to 1.0 (very low risk / bullish):

1. **visa_risk** — H1B visa approval rate (USCIS quarterly data) and denial rate trend;
   L1A/L1B approvals; any H1B cap lottery tightening under current US administration;
   workaround: local hiring % in US/Europe reducing visa dependency.

2. **ai_disruption** — Revenue exposure to AI-displaceable services: BPO, testing, maintenance;
   company's own GenAI product/platform revenue as an offset (opportunity > threat = bullish);
   AI-first deal wins vs AI-displaced renewal losses;
   analyst estimates of revenue at risk from GenAI substitution.

3. **client_concentration** — Top-5 client revenue % (>30% is concentrated = risky);
   largest single client % (>10% is watch-level); any active client churn/renegotiation;
   US geography concentration vs Europe/India diversification.

4. **fx_hedge** — INR/USD forward contract coverage ratio (% of next 12 months revenue hedged);
   average hedge rate vs current spot; P&L sensitivity to 1% INR move;
   natural hedge from US-based costs (US headcount, US office expenses).

5. **talent_risk** — STEM talent supply vs demand in India (IIT/NIT output vs IT job openings);
   wage inflation in Tier-1 and Tier-2 cities; hiring competition from global tech MNCs;
   US recession probability (leading to client IT budget cuts).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{{
  "agent": "risk_macro",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {{
    "visa_risk": <float>,
    "ai_disruption": <float>,
    "client_concentration": <float>,
    "fx_hedge": <float>,
    "talent_risk": <float>
  }},
  "key_positives": ["<string>", "..."],
  "key_risks": ["<string>", "..."],
  "summary": "<2-3 sentence narrative on the most material risks: visa, AI displacement, and client concentration>",
  "data_freshness": "<date of most recent risk data used>"
}}
"""

CONTEXT_SEARCH_QUERIES = [
    "H1B L1 visa approval rate denial USCIS {year}",
    "AI GenAI displacement IT services revenue risk {year}",
    "{ticker} client concentration top client revenue churn {year}",
    "India IT sector wage inflation STEM talent supply {year}",
    "US recession probability IT spending Gartner IDC forecast {year}",
]
