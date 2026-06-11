"""
prompts/feedback_agent.py
=========================
LLM prompt templates for the FeedbackAgent — the daily learning agent that
analyses prediction misses and generates stock-specific lessons.

Applies to all sectors: automobile · banking_bfsi · it_sector · renewable_energy
The system prompt is built dynamically per sector and agent list.
"""

from __future__ import annotations

from backend.shared.schemas.feedback import EVENT_TAGS

# Human-readable names for each sector (used in the system prompt)
SECTOR_DISPLAY_NAMES: dict[str, str] = {
    "automobile":      "Indian Automobile",
    "banking_bfsi":    "Indian Banking & Financial Services (BFSI)",
    "it_sector":       "Indian IT Sector",
    "renewable_energy":"Indian Renewable Energy",
}


def build_system_prompt(sector: str, agent_names: list[str]) -> str:
    """
    Build a sector-aware system prompt for the FeedbackAgent.

    Parameters
    ----------
    sector : str
        One of: automobile, banking_bfsi, it_sector, renewable_energy
    agent_names : list[str]
        The sub-agent names active for this sector (e.g. ["sales_demand", "fundamentals", ...])
    """
    sector_label = SECTOR_DISPLAY_NAMES.get(sector, sector.replace("_", " ").title())
    agents_str   = ", ".join(agent_names)
    event_tags_str = ", ".join(sorted(EVENT_TAGS))

    return f"""You are the Feedback & Learning Agent for a {sector_label} stock prediction system.

Your job every trading day is:
1. Compare what the system predicted vs what actually happened in the market.
2. Classify the TYPE of miss using the miss_type taxonomy below.
3. Identify the ROOT CAUSE — which signals were over-trusted or ignored.
4. Identify which sub-agent ({agents_str}) was the primary contributor to the error.
5. Extract REUSABLE LESSONS — specific patterns that this stock consistently reacts to.
6. Provide a structured forward outlook for the remaining forecast horizon.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MISS TYPE TAXONOMY (classify every miss into exactly one):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  data_gap       — required input data was not yet published at forecast time
                   (e.g. FADA dispatch releases on the 10th, forecast was on the 5th)
                   → agent is NOT at fault; zero weight penalty
  data_stale     — data used was outdated (e.g. RBI repo rate was hardcoded and stale)
                   → agent is NOT at fault; zero weight penalty
  external_shock — unpredictable black-swan event (sudden war, exchange circuit breaker,
                   surprise regulatory ban); no model could have foreseen it
                   → zero weight penalty
                   ⚠ STRICT CAP: external_shock must not exceed 20% of all days analysed
                   for this stock in the current cycle. If that cap is already reached,
                   you MUST assign a different miss_type (typically model_bias or direction_flip).
  timing         — direction was CORRECT but the stock moved earlier or later than predicted
                   → half weight penalty
  magnitude      — direction was CORRECT but the size of the move was much larger/smaller
                   → quarter weight penalty
  model_bias     — agent consistently over/under-estimates a specific signal across multiple days
                   → full weight penalty
  direction_flip — stock moved in the OPPOSITE direction with no valid external excuse
                   → full weight penalty

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ANALYST DISTRUST RULE (non-negotiable):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  NEVER cite analyst upgrades, broker price targets, consensus ratings, EPS estimate
  revisions, or institutional buy/sell recommendations as missed_factors or
  over_weighted_factors. This system intentionally excludes analyst opinion from all
  input data. Referencing them implies we should add them — we must not.
  Valid missed factors: price action, macro events, sector data, technical signals,
  company fundamentals, government policy, global commodity moves, regulatory actions.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
LESSON CATEGORIES AND SCOPE:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  macro            — domestic macro: RBI decisions, FII flows, INR movement
  global_macro     — cross-border macro: Fed rate decision, China PMI, crude oil spike >5%,
                     USD/INR move >1% in a single day, EM capital flight
                     → ALWAYS use scope="market_wide" and prefix pattern with "global_"
  technical        — price patterns, RSI, MACD, support/resistance, volume spikes
  sentiment        — news tone, social media, management commentary, analyst day reactions
  fundamental      — earnings surprises, margin compression, order book changes
  seasonal         — recurring calendar patterns (quarter-end flush, festive demand, budget week)
  data_availability— patterns about when specific data is or is not yet published
                     → use when miss_type is data_gap; helps system anticipate future gaps

  Lesson scope:
    stock_specific — only applies to this ticker
    sector_wide    — applies to all {sector_label} stocks (e.g. sector-wide RBI impact)
    market_wide    — applies regardless of sector (global macro events)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CATALYST REVIEW (when predicted_catalysts are provided):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  When predicted_catalysts are provided, compare them to what actually happened
  and name the specific catalyst that failed or succeeded.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
GENERAL GUIDELINES:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  - Be precise and concise. Do not repeat the input data back.
  - Lessons must be ACTIONABLE rules, not vague observations.
  - Even when direction_correct=true, check if agent score drift >0.12 — that signals
    future risk even on correct days.
  - Lessons should capture STOCK-SPECIFIC reactions where possible.
    What is true for MARUTI may not be true for TATAMOTORS.
  - Do NOT invent factors. Only reference signals present in market_context_today
    or derivable from the agent score snapshot.
  - If an existing lesson already covers the pattern, do NOT create a new lesson.
    The caller will increment occurrences and update confidence automatically.
  - If miss_type is data_gap or data_stale, still identify the pattern so a
    data_availability lesson can be created to prevent the same gap next cycle.
  - Every new lesson MUST include trigger_tags so the system can apply it
    automatically on matching days.

You must return a valid JSON object with EXACTLY this structure (no markdown, no extra keys):

{{
  "primary_miss_agent": "<agent_name from: {agents_str}>",
  "miss_type": "<one of: data_gap|data_stale|external_shock|timing|magnitude|model_bias|direction_flip>",
  "missed_factors": ["<factor1>", "<factor2>"],
  "over_weighted_factors": ["<factor1>"],
  "agent_score_drift": {{
    "<agent_name>": <float: positive=underestimated, negative=overestimated>
  }},
  "new_lessons": [
    {{
      "category": "<macro|global_macro|technical|sentiment|fundamental|seasonal|data_availability>",
      "pattern": "<short_snake_case_key>",
      "observation": "<one sentence: what was observed>",
      "rule": "<one sentence: what to do differently next time>",
      "confidence": <0.0 to 1.0>,
      "scope": "<stock_specific|sector_wide|market_wide>",
      "trigger_tags": ["central_bank_event"],   // REQUIRED — 1-3 tags, ONLY from: {event_tags_str}
      "prioritise_agents": ["risk_macro"],      // agents to trust MORE when this fires (from: {agents_str})
      "discount_agents": ["sales_demand"]       // agents to trust LESS when this fires (from: {agents_str})
    }}
  ],
  "revised_context": {{
    "headline": "<one sentence: key takeaway for remaining forecast horizon>",
    "risks_next_7_days": ["<risk1>", "<risk2>"],
    "catalysts_next_7_days": ["<catalyst1>", "<catalyst2>"],
    "watch_signals": ["<what to monitor, e.g. INR past 84>"],
    "horizon_confidence_adjustment": <float between -0.15 and +0.05>
  }}
}}

If direction was correct and no new lessons arise, return empty lists for
missed_factors, over_weighted_factors, and new_lessons.
revised_context must always be populated — even on correct days.
"""


FEEDBACK_PROMPT = """
=== DAILY FEEDBACK ANALYSIS ===

Ticker  : {ticker}
Sector  : {sector}
Date    : {date}

--- PREDICTION vs ACTUAL ---
Predicted close  : {currency}{predicted_close}
Actual close     : {currency}{actual_close}
Price error      : {price_error_pct:+.2f}%
Direction correct: {direction_correct}
{volume_context_block}
--- AGENT SCORE SNAPSHOT ---
Predicted composite scores (frozen at forecast time):
{predicted_scores_block}

Today's re-run composite scores (with live data):
{todays_scores_block}
{subscore_drift_block}
--- MARKET CONTEXT TODAY ---
{market_context_today}

--- FORECAST PROFILE ---
{forecast_profile_block}

--- KEY ASSUMPTIONS MADE AT FORECAST TIME ---
{assumptions_block}
{previous_watch_block}
--- AGENT WEIGHT CONTEXT ---
{weight_drift_summary}
{accuracy_trend_block}
{catalyst_block}
--- EXISTING LESSONS FOR THIS STOCK ---
{active_lessons_summary}

Classify the miss type first, then identify root cause, then extract lessons.
Return your JSON response.
"""

# Currency symbol per sector (cosmetic, helps LLM anchor to the right market)
_SECTOR_CURRENCY: dict[str, str] = {
    "automobile":      "₹",
    "banking_bfsi":    "₹",
    "it_sector":       "₹",
    "renewable_energy":"₹",
}


def format_feedback_prompt(
    ticker: str,
    sector: str,
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
    # New context fields assembled by daily_review.py
    significant_subscore_drift: dict | None = None,
    weight_drift_summary: str = "",
    recent_accuracy_trend: str = "",
    previous_watch_signals: list | None = None,
    volume_context: str = "",
    forecast_profile_context: str = "",
    predicted_catalysts_by_agent: dict | None = None,
) -> str:
    predicted_scores_block = "\n".join(
        f"  {k}: {v:.3f}" for k, v in predicted_agent_scores.items()
    )
    todays_scores_block = "\n".join(
        f"  {k}: {v:.3f}" for k, v in todays_agent_scores.items()
    )
    assumptions_block = (
        "\n".join(f"  - {a}" for a in key_assumptions_made) or "  None recorded"
    )
    currency = _SECTOR_CURRENCY.get(sector, "")

    # Sub-score drift block — only for agents with significant drift
    subscore_drift_block = ""
    if significant_subscore_drift:
        lines = ["\n--- SUB-SCORE DETAIL (agents with significant drift) ---"]
        for agent, dims in significant_subscore_drift.items():
            for dim, vals in dims.items():
                pred = vals.get("predicted", "?")
                actual = vals.get("actual", "?")
                delta = vals.get("actual", 0) - vals.get("predicted", 0)
                lines.append(
                    f"  {agent}.{dim}: predicted={pred:.3f}  actual={actual:.3f}  Δ={delta:+.3f}"
                )
        subscore_drift_block = "\n".join(lines)

    # Volume context
    volume_context_block = f"Volume today      : {volume_context}\n" if volume_context else ""

    # Forecast profile
    forecast_profile_block = (
        forecast_profile_context
        if forecast_profile_context
        else "Linear forecast (uniform drift expected)."
    )

    # Previous watch signals — close the monitoring loop
    previous_watch_block = ""
    if previous_watch_signals:
        lines = ["\n--- PREVIOUSLY FLAGGED WATCH SIGNALS (from yesterday's review) ---"]
        lines += [f"  - {s}" for s in previous_watch_signals]
        lines.append("  Did any of these materialise today?")
        previous_watch_block = "\n".join(lines) + "\n"

    # Accuracy trend block
    accuracy_trend_block = (
        f"\nRecent agent accuracy trend: {recent_accuracy_trend}"
        if recent_accuracy_trend else ""
    )

    # Catalyst context block — shows predicted bull/bear triggers for this cycle
    if predicted_catalysts_by_agent:
        cat_lines = ["\n--- PREDICTED CATALYSTS FROM LAST CYCLE — did they materialise? ---"]
        for _ag, _cats in predicted_catalysts_by_agent.items():
            if _cats.get("bull_case_if"):
                cat_lines.append(f"  {_ag} bull case: {_cats['bull_case_if']}")
            if _cats.get("bear_case_if"):
                cat_lines.append(f"  {_ag} bear case: {_cats['bear_case_if']}")
            _dc = _cats.get("data_confidence", 0.5)
            try:
                if float(_dc) < 0.5:
                    cat_lines.append(
                        f"    ^ low confidence prediction (data_confidence={float(_dc):.2f}) "
                        f"— penalize miss less"
                    )
            except (TypeError, ValueError):
                pass
        catalyst_block = "\n".join(cat_lines)
    else:
        catalyst_block = ""

    return FEEDBACK_PROMPT.format(
        ticker=ticker,
        sector=SECTOR_DISPLAY_NAMES.get(sector, sector),
        date=date,
        currency=currency,
        predicted_close=predicted_close,
        actual_close=actual_close,
        price_error_pct=price_error_pct,
        direction_correct=direction_correct,
        volume_context_block=volume_context_block,
        predicted_scores_block=predicted_scores_block,
        todays_scores_block=todays_scores_block,
        subscore_drift_block=subscore_drift_block,
        market_context_today=market_context_today or "No market context available.",
        forecast_profile_block=forecast_profile_block,
        assumptions_block=assumptions_block,
        previous_watch_block=previous_watch_block,
        weight_drift_summary=weight_drift_summary or "No significant weight drift from base.",
        accuracy_trend_block=accuracy_trend_block,
        catalyst_block=catalyst_block,
        active_lessons_summary=active_lessons_summary or "No lessons learned yet.",
    )
