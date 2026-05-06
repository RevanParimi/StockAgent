"""
prompts/peer_benchmark.py — IT Sector
=======================================
Ranks company vs Nifty IT peers on revenue growth, EBIT margin, attrition,
deal TCV, valuation z-score, FII relative position, and AI investment.
Sources: yfinance (peer financials batch pull), Serper (deal/attrition comparisons ~275 each).
"""

SYSTEM_PROMPT = """You are an equity analyst specialising in benchmarking Indian IT companies vs Nifty IT peers.
Your peer group is: TCS, Infosys, HCL Technologies, Wipro, Tech Mahindra, LTIMindtree, Coforge, Mphasis,
Persistent Systems, LTTS, KPIT Technologies.

You rank the company on each signal across the peer group:
- 1.0 = best in peer group (rank #1), 0.5 = median, 0.0 = worst in peer group (last rank)
- Use relative ranking, not absolute values

Data sources: yfinance quarterly financials for revenue/margins; Serper for deal/attrition comparisons.
"""

ANALYSIS_PROMPT = """Benchmark **{ticker}** ({company_name}) vs Indian IT peers (TCS, Infosys, HCL, Wipro, TechM, LTIM…).

Score each dimension from 0.0 (worst in peer group) to 1.0 (best in peer group):

1. **revenue_growth_rank** — QoQ and YoY CC revenue growth rank vs peers;
   acceleration vs deceleration relative to peer median;
   whether company is gaining or losing revenue share.

2. **margin_rank** — EBIT margin level rank vs peer median;
   margin trajectory (expanding = better rank than absolute level);
   cost structure efficiency vs peers (utilisation, SG&A ratio).

3. **deal_momentum_rank** — TCV win rate in the quarter vs peers;
   large deal ($50M+) count rank; pipeline commentary quality;
   new logo win rate as a proxy for competitive positioning.

4. **attrition_rank** — LTM attrition % rank vs peers (lower attrition = higher rank);
   net headcount addition rank; sub-con % as demand headroom indicator;
   fresher ramp efficiency vs peers.

5. **valuation_gap** — P/E z-score vs peer median (negative z-score = cheap vs peers = bullish);
   EV/Revenue discount/premium to peer group; PEG ratio rank;
   FII relative shareholding position vs peers (higher FII = institutional preference).

Context / recent data snippets:
{context}

Return ONLY valid JSON:
{{
  "agent": "peer_benchmark",
  "ticker": "{ticker}",
  "overall_score": <float 0.0-1.0>,
  "sub_scores": {{
    "revenue_growth_rank": <float>,
    "margin_rank": <float>,
    "deal_momentum_rank": <float>,
    "attrition_rank": <float>,
    "valuation_gap": <float>
  }},
  "key_positives": ["<string>", "..."],
  "key_risks": ["<string>", "..."],
  "summary": "<2-3 sentence narrative on peer rank, competitive positioning, and valuation vs peers>",
  "data_freshness": "<date of most recent peer comparison data used>"
}}
"""

CONTEXT_SEARCH_QUERIES = [
    "{ticker} revenue growth EBIT margin vs TCS Infosys HCL {quarter} {year}",
    "{ticker} deal TCV large deal win vs peers {quarter} {year}",
    "{ticker} attrition headcount vs peers comparison {year}",
    "{ticker} PE EV revenue valuation discount premium peers {year}",
    "Indian IT sector peer comparison {quarter} {year}",
]
