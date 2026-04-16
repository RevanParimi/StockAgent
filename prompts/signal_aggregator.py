"""
prompts/signal_aggregator.py
=============================
Prompt templates for the Signal Aggregator (weighted fusion + conflict resolution).
"""

SYSTEM_PROMPT = """You are a senior portfolio manager synthesising multi-dimensional research signals
for Indian automobile stocks. You receive scored outputs from five specialist agents:
  1. Sales & Demand
  2. Fundamentals
  3. Pattern Analysis
  4. Sentiment
  5. Risk & Macro

Your job is to:
  - Apply the configured weight to each agent score
  - Detect and resolve conflicts (e.g., bullish fundamentals vs bearish macro)
  - Produce a final composite score and a clear investment verdict
  - Highlight the top 3 conviction drivers and top 3 risk factors

Be decisive. Investors rely on your synthesis to act.
"""

AGGREGATION_PROMPT = """Synthesise the following agent outputs for stock **{ticker}** ({company_name}).

Agent scores and weights:
{agent_scores_block}

Weighted composite score (pre-calculated): {weighted_score:.3f}

Conflict flags detected: {conflict_flags}

Instructions:
1. Confirm or adjust the weighted score if conflicts materially alter the outlook.
2. Map the final score to a verdict: STRONG BUY / BUY / NEUTRAL / SELL / STRONG SELL.
3. Write a 3-5 sentence investment thesis.
4. List top 3 conviction drivers and top 3 risks.

Return ONLY valid JSON:
{{
  "ticker": "{ticker}",
  "company_name": "{company_name}",
  "final_score": <float 0.0-1.0>,
  "verdict": "<STRONG BUY | BUY | NEUTRAL | SELL | STRONG SELL>",
  "weighted_agent_scores": {{
    "sales_demand":     {{"raw": <float>, "weight": <float>, "weighted": <float>}},
    "fundamentals":     {{"raw": <float>, "weight": <float>, "weighted": <float>}},
    "pattern_analysis": {{"raw": <float>, "weight": <float>, "weighted": <float>}},
    "sentiment":        {{"raw": <float>, "weight": <float>, "weighted": <float>}},
    "risk_macro":       {{"raw": <float>, "weight": <float>, "weighted": <float>}}
  }},
  "conflicts_resolved": [<string>, ...],
  "conviction_drivers": [<string>, <string>, <string>],
  "top_risks": [<string>, <string>, <string>],
  "investment_thesis": "<paragraph>",
  "report_date": "{report_date}"
}}
"""

CONFLICT_DETECTION_PROMPT = """Given these agent scores for {ticker}:
{scores_json}

Identify any significant conflicts (score difference > 0.3 between agents) that could
materially change the investment thesis. Return a JSON list of conflict descriptions,
or an empty list if none.
"""
