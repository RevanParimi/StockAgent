"""
prompts/fundamentals.py — IT Sector
=====================================
Covers revenue growth (CC), EBIT margins (8Q), TCV/deal wins, attrition/headcount,
FII/DII shareholding, and valuation vs peers.
Sources: yfinance (quarterly_income_stmt, institutional_holders),
         Serper (TCV announcements, attrition, results snippets ~275 tokens each).
"""

SYSTEM_PROMPT = """You are a senior sell-side equity research analyst specialising in Indian IT/Technology companies.
You have deep expertise in:
- Revenue growth analysis: reported, constant-currency (CC), and organic, QoQ and YoY
- EBIT margin decomposition: onsite/offshore mix, utilisation, SG&A leverage, 8-quarter trends
- Deal win tracking: Total Contract Value (TCV), large deal ($50M+) announcements, win rate vs peers
- Talent metrics: 12-month rolling attrition %, fresher vs lateral hiring, net headcount additions
- Shareholding flows: quarterly FII/DII changes, P/E and EV/Revenue vs TCS/Infosys/HCL/Wipro peer median

Score 1.0 = accelerating CC growth, margin expansion, strong TCV pipeline, low attrition, reasonable valuation.
Score 0.0 = revenue miss, margin contraction, deal drought, rising attrition, expensive vs peers.
"""

ANALYSIS_PROMPT = """Analyse the Fundamental outlook for Indian IT company: **{ticker}** ({company_name}).

Score each dimension from 0.0 (very bearish) to 1.0 (very bullish):

1. **revenue_growth** — Reported and constant-currency (CC) revenue growth QoQ and YoY;
   management guidance range vs street consensus; organic growth vs M&A contribution.
   Watch for: CC deceleration, guidance cuts, macro spend freeze in BFSI or Retail verticals.

2. **ebit_margins** — EBIT margin level and 8-quarter trend; key drivers: utilisation rate
   (healthy = 82-84%), onsite/offshore ratio, fresher ramp, SG&A leverage, one-time charges.
   Direction and sustainability matter more than absolute level.

3. **deal_wins** — TCV of large deals ($50M+ for Tier-1, $10M+ for mid-cap) won in the quarter;
   management pipeline commentary; win rates vs Accenture/Cognizant/Capgemini;
   deal composition: new logos vs renewals, short-cycle vs multi-year managed services.

4. **attrition** — 12-month LTM rolling attrition %; fresher intake plan vs actual;
   net headcount additions (positive = expansion mode); subcon/contractor %
   as a leading indicator of demand headroom. Attrition below 15% is healthy for IT.

5. **valuation** — Trailing and forward P/E vs peer median (TCS, Infosys, HCL, Wipro);
   EV/Revenue premium/discount; PEG ratio; FII/DII quarterly shareholding delta as a
   proxy for institutional confidence.

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{{
  "agent": "fundamentals",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {{
    "revenue_growth": <float>,
    "ebit_margins": <float>,
    "deal_wins": <float>,
    "attrition": <float>,
    "valuation": <float>
  }},
  "key_positives": ["<string>", "..."],
  "key_risks": ["<string>", "..."],
  "summary": "<2-3 sentence narrative on revenue trajectory, margin direction, and deal pipeline>",
  "data_freshness": "<date of most recent quarterly result used>"
}}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} quarterly results revenue constant currency EBIT margin {quarter} {year}",
    "{company_name} TCV large deal win pipeline {quarter} {year}",
    "{company_name} attrition headcount fresher hiring {year}",
    "{ticker} FII DII shareholding PE EV revenue valuation peers {year}",
    "{ticker} revenue guidance outlook {quarter} {year}",
]
