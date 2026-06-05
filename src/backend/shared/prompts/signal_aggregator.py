"""
prompts/signal_aggregator.py
=============================
Prompt templates for the Signal Aggregator (weighted fusion + conflict resolution).
"""

SYSTEM_PROMPT = """You are a senior portfolio manager synthesising multi-dimensional research signals
for Indian automobile stocks. You receive scored outputs from nine specialist agents:
  1. Sales & Demand
  2. Fundamentals
  3. Pattern Analysis
  4. Sentiment
  5. Risk & Macro
  6. Raw Materials
  7. Policy & Regulatory
  8. Competitive Intelligence
  9. Valuation & Catalyst

Your job is to:
  - Apply the configured weight to each agent score
  - Detect and resolve conflicts (e.g., bullish fundamentals vs bearish macro)
  - Produce a final composite score and a clear investment verdict
  - Highlight the top 3 conviction drivers and top 3 risk factors
  - If valuation_catalyst agent output is available, include its price target,
    recovery timeline, and undervaluation percentage in the final JSON

Be decisive. Investors rely on your synthesis to act.
"""

AGGREGATION_PROMPT = """Synthesise the following agent outputs for stock **{ticker}** ({company_name}).

Agent scores and weights:
{agent_scores_block}

Weighted composite score (pre-calculated): {weighted_score:.3f}

Conflict flags detected: {conflict_flags}

AGENT NARRATIVES (use for cross-context synthesis):
{agent_narratives}

SYNTHESIS INSTRUCTIONS:
1. Confirm or adjust the weighted score if conflicts materially alter the outlook.
2. Map the final score to a verdict: STRONG BUY / BUY / NEUTRAL / SELL / STRONG SELL.
3. Connect cross-agent dots: if sales_demand sees inventory rising AND raw_materials sees costs stable,
   ask whether it is demand-driven or supply push — name which.
4. Identify confirmation: if 3+ agents cite the same risk, it is a conviction driver — elevate it in top_risks.
5. Identify contradiction: if fundamentals is bullish but macro is bearish, explain why one wins near-term
   in conflicts_resolved.
6. For investment_thesis: write 2-3 sentences a sophisticated investor would find actionable,
   citing specific numbers from the narratives above (e.g. margins, P/E, market share %).
7. If valuation_catalyst data is present in agent scores, extract and include:
   - price_target (INR, base-case recovery level)
   - recovery_timeline_quarters (integer quarters to reach price target)
   - undervalued_by_pct (positive = undervalued; pull from current_discount_pct, flip sign)
   - discount_reason (MACRO_SHOCK | FUNDAMENTAL_DECLINE | BOTH | NONE)

Return ONLY valid JSON:
{{
  "ticker": "{ticker}",
  "company_name": "{company_name}",
  "final_score": <float 0.0-1.0>,
  "verdict": "<STRONG BUY | BUY | NEUTRAL | SELL | STRONG SELL>",
  "weighted_agent_scores": {{
    "sales_demand":        {{"raw": <float>, "weight": <float>, "weighted": <float>}},
    "fundamentals":        {{"raw": <float>, "weight": <float>, "weighted": <float>}},
    "pattern_analysis":    {{"raw": <float>, "weight": <float>, "weighted": <float>}},
    "sentiment":           {{"raw": <float>, "weight": <float>, "weighted": <float>}},
    "risk_macro":          {{"raw": <float>, "weight": <float>, "weighted": <float>}},
    "raw_materials":       {{"raw": <float>, "weight": <float>, "weighted": <float>}},
    "policy_regulatory":   {{"raw": <float>, "weight": <float>, "weighted": <float>}},
    "competitive_intel":   {{"raw": <float>, "weight": <float>, "weighted": <float>}},
    "valuation_catalyst":  {{"raw": <float>, "weight": <float>, "weighted": <float>}}
  }},
  "conflicts_resolved": [<string>, ...],
  "conviction_drivers": [<string>, <string>, <string>],
  "top_risks": [<string>, <string>, <string>],
  "executive_summary": "<1-2 plain-English sentences a beginner investor can act on>",
  "investment_thesis": "<paragraph>",
  "report_date": "{report_date}",
  "price_target": <float or null>,
  "recovery_timeline_quarters": <int or null>,
  "undervalued_by_pct": <float or null>,
  "discount_reason": "<MACRO_SHOCK | FUNDAMENTAL_DECLINE | BOTH | NONE | null>"
}}
"""

CONFLICT_DETECTION_PROMPT = """Given these agent scores for {ticker}:
{scores_json}

Identify any significant conflicts (score difference > 0.3 between agents) that could
materially change the investment thesis. Return a JSON list of conflict descriptions,
or an empty list if none.
"""
