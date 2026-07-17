"""
graphs/_shared/rails.py
=======================
NeMo Guardrails-inspired validator for the legacy worker pool.

  OutputRail — after each agent node: is the score valid and summary present?

Rails never hard-stop the graph — they clamp bad values and append to
rail_errors so the audit trail is always complete.

Wave E (AUD-095): input_rail and conflict_rail were deleted with the
standalone sector graphs; the live path validates input in
BaseOrchestrator._resolve_ticker and resolves conflicts in
SignalAggregator.
"""

from __future__ import annotations

import logging

from backend.shared.schemas.pipeline import AgentOutput

logger = logging.getLogger(__name__)

# ── Thresholds ─────────────────────────────────────────────────────────────
SCORE_MIN, SCORE_MAX = 0.0, 1.0
NEUTRAL_FALLBACK = 0.5


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
