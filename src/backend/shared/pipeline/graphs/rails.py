"""
graphs/_shared/rails.py
=======================
NeMo Guardrails-inspired validators inserted as lightweight checks
at three points in every sector graph.

  InputRail    — after resolve_ticker:  is this a real, tradeable ticker?
  OutputRail   — after each agent node: is the score valid and summary present?
  ConflictRail — in aggregate node:     do agents disagree beyond threshold?

Rails never hard-stop the graph — they clamp bad values and append to
rail_errors so the audit trail is always complete.
"""

from __future__ import annotations

import logging

import yfinance as yf

from backend.shared.schemas.pipeline import AgentOutput

logger = logging.getLogger(__name__)

# ── Thresholds ─────────────────────────────────────────────────────────────
CONFLICT_THRESHOLD = 0.30   # must match agents/signal_aggregator.CONFLICT_THRESHOLD
SCORE_MIN, SCORE_MAX = 0.0, 1.0
NEUTRAL_FALLBACK = 0.5


# ──────────────────────────────────────────────────────────────────────────
# Input Rail
# ──────────────────────────────────────────────────────────────────────────

def input_rail(ticker: str, exchange: str = "NSE") -> tuple[bool, list[str]]:
    """
    Verify the ticker resolves to a real instrument via yfinance.

    Returns
    -------
    (is_valid, errors)
        is_valid  — True if yfinance found a price; False if completely unknown.
        errors    — list of human-readable warning strings (may be non-empty
                    even when is_valid=True, e.g. stale data warnings).
    """
    errors: list[str] = []

    if not ticker or not ticker.strip():
        errors.append("INPUT_RAIL: ticker is empty — cannot proceed with analysis")
        return False, errors

    # Append .NS for NSE tickers yfinance convention
    yf_symbol = f"{ticker}.NS" if exchange == "NSE" else ticker
    try:
        info = yf.Ticker(yf_symbol).fast_info
        price = getattr(info, "last_price", None)
        if price is None or price == 0:
            errors.append(
                f"INPUT_RAIL: {yf_symbol} returned no price — "
                "LLM will use training knowledge only"
            )
            return True, errors   # not a hard block; analysis can still run
        logger.debug("INPUT_RAIL: %s price=%.2f — OK", yf_symbol, price)
    except Exception as exc:
        errors.append(
            f"INPUT_RAIL: yfinance lookup failed for {yf_symbol}: {exc} — "
            "proceeding with LLM knowledge only"
        )

    return True, errors


# ──────────────────────────────────────────────────────────────────────────
# Output Rail
# ──────────────────────────────────────────────────────────────────────────

def output_rail(output: AgentOutput) -> tuple[AgentOutput, list[str]]:
    """
    Validate and sanitize a single AgentOutput.

    Rules (from Mirascope response_model pattern + NeMo output guardrails):
      1. score must be in [0.0, 1.0] — clamp if not
      2. summary must not be empty — inject placeholder if missing
      3. agent name must be non-empty — warn if missing

    Returns sanitized output and a list of errors (empty = clean).
    """
    errors: list[str] = []
    agent = output.agent or "unknown"

    # Rule 1: score range
    raw_score = output.overall_score
    if not (SCORE_MIN <= raw_score <= SCORE_MAX):
        clamped = max(SCORE_MIN, min(SCORE_MAX, raw_score))
        errors.append(
            f"OUTPUT_RAIL [{agent}]: score {raw_score:.3f} out of range — "
            f"clamped to {clamped:.3f}"
        )
        output = output.model_copy(update={"overall_score": clamped})

    # Rule 2: summary
    if not output.summary or not output.summary.strip():
        errors.append(
            f"OUTPUT_RAIL [{agent}]: empty summary — injecting placeholder"
        )
        output = output.model_copy(
            update={"summary": f"{agent} analysis completed with score {output.overall_score:.3f}."}
        )

    # Rule 3: agent name
    if not output.agent:
        errors.append("OUTPUT_RAIL: agent name missing in output")

    if errors:
        logger.warning("OutputRail violations for %s: %s", agent, errors)

    return output, errors


# ──────────────────────────────────────────────────────────────────────────
# Conflict Rail
# ──────────────────────────────────────────────────────────────────────────

def conflict_rail(
    agent_outputs: dict[str, AgentOutput],
) -> tuple[bool, list[tuple[str, str, float]]]:
    """
    Detect scoring conflicts across agents.

    A conflict is any pair where |score_a - score_b| > CONFLICT_THRESHOLD.

    Returns
    -------
    (has_conflict, conflicting_pairs)
        has_conflict       — True if any pair exceeds the threshold.
        conflicting_pairs  — list of (agent_a, agent_b, delta) tuples.
    """
    scores = {
        name: out.overall_score
        for name, out in agent_outputs.items()
        if out.error is None
    }
    if len(scores) < 2:
        return False, []

    pairs: list[tuple[str, str, float]] = []
    names = list(scores.keys())
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = names[i], names[j]
            delta = abs(scores[a] - scores[b])
            if delta > CONFLICT_THRESHOLD:
                pairs.append((a, b, round(delta, 3)))
                logger.info(
                    "CONFLICT_RAIL: %s=%.3f vs %s=%.3f delta=%.3f",
                    a, scores[a], b, scores[b], delta,
                )

    return bool(pairs), pairs
