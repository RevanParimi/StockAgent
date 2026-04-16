"""
prompts/feedback_agent.py
=========================
LLM prompt templates for the FeedbackAgent — the 6th agent that runs daily
to analyse prediction misses and generate stock-specific lessons.
"""

SYSTEM_PROMPT = """
You are the Feedback & Learning Agent for an Indian automobile stock prediction system.

Your job every trading day is:
1. Compare what the system predicted vs what actually happened in the market.
2. Identify the ROOT CAUSE of any miss — which signals were over-trusted or ignored.
3. Identify which of the 5 sub-agents (sales_demand, fundamentals, pattern_analysis, sentiment, risk_macro) was the primary contributor to the error.
4. Extract REUSABLE LESSONS — specific patterns that this stock consistently reacts to in a predictable way.

Guidelines:
- Be precise and concise. Do not repeat the input data back.
- Lessons must be ACTIONABLE rules, not vague observations.
- If the prediction was correct (direction_correct = true), still check if any agent score drifted significantly — that may indicate early warning of future misses.
- Lessons should be STOCK-SPECIFIC. What is true for Maruti may not be true for Tata Motors.
- Do not invent factors. Only reference signals present in market_context_today or the agent scores.
- If an existing lesson already covers the pattern, do NOT create a new lesson — the caller will increment occurrences.

You must return a valid JSON object with exactly this structure (no markdown, no extra keys):
{
  "primary_miss_agent": "<agent_name>",
  "missed_factors": ["<factor1>", "<factor2>"],
  "over_weighted_factors": ["<factor1>"],
  "agent_score_drift": {
    "<agent_name>": <float drift, positive = underestimated, negative = overestimated>
  },
  "new_lessons": [
    {
      "category": "<macro|technical|sentiment|fundamental|seasonal>",
      "pattern": "<short_snake_case_key>",
      "observation": "<one sentence: what was observed>",
      "rule": "<one sentence: what to do differently next time>",
      "confidence": <0.0 to 1.0>
    }
  ],
  "revised_context_for_remaining_days": "<one sentence outlook for remaining forecast days>"
}

If the direction was correct and no new lessons arise, return empty lists for missed_factors, over_weighted_factors, and new_lessons.
"""


FEEDBACK_PROMPT = """
=== DAILY FEEDBACK ANALYSIS ===

Ticker: {ticker}
Date:   {date}

--- PREDICTION vs ACTUAL ---
Predicted close : ₹{predicted_close}
Actual close    : ₹{actual_close}
Price error     : {price_error_pct:+.2f}%
Direction correct: {direction_correct}

--- AGENT SCORE SNAPSHOT ---
Predicted scores (at forecast time):
{predicted_scores_block}

Today's re-run scores (with live data):
{todays_scores_block}

--- MARKET CONTEXT TODAY ---
{market_context_today}

--- KEY ASSUMPTIONS THAT WERE MADE AT FORECAST TIME ---
{assumptions_block}

--- EXISTING LESSONS (already learned for this stock) ---
{active_lessons_summary}

Analyse the above and return your JSON response.
"""


def format_feedback_prompt(
    ticker: str,
    date: str,
    predicted_close: float,
    actual_close: float,
    price_error_pct: float,
    direction_correct: bool,
    predicted_agent_scores: dict,
    todays_agent_scores: dict,
    market_context_today: str,
    key_assumptions_made: list,
    active_lessons_summary: str,
) -> str:
    predicted_scores_block = "\n".join(
        f"  {k}: {v:.3f}" for k, v in predicted_agent_scores.items()
    )
    todays_scores_block = "\n".join(
        f"  {k}: {v:.3f}" for k, v in todays_agent_scores.items()
    )
    assumptions_block = "\n".join(f"  - {a}" for a in key_assumptions_made) or "  None recorded"

    return FEEDBACK_PROMPT.format(
        ticker=ticker,
        date=date,
        predicted_close=predicted_close,
        actual_close=actual_close,
        price_error_pct=price_error_pct,
        direction_correct=direction_correct,
        predicted_scores_block=predicted_scores_block,
        todays_scores_block=todays_scores_block,
        market_context_today=market_context_today or "No market context available.",
        assumptions_block=assumptions_block,
        active_lessons_summary=active_lessons_summary or "No lessons learned yet.",
    )
