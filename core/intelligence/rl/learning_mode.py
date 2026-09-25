"""
SA-039 learning containment — one switch, two modes.

adapt   The behaviour before SA-039. Decisions aggregate with each ticker's
        learned weights, the daily review writes adapted weights, and lessons
        nudge agent scores.
observe Decisions aggregate with the sector's configured default weights
        (get_sector_weights — what a ticker with no learning state gets). The
        review never writes adapted weights: the adapter still runs, on a copy,
        and its proposal is recorded as a diagnostic. Lessons are still recorded
        but no longer move agent scores.

The mode is read at call time from settings.RL_LEARNING_MODE (config
rl.learning_mode, env RL_LEARNING_MODE). An unrecognised value fails closed to
observe. Observe mode leaves the stored WeightMemory untouched, so switching
back to adapt resumes exactly the stored weights.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

ADAPT = "adapt"
OBSERVE = "observe"
_MODES = (ADAPT, OBSERVE)

# Unrecognised values already warned about in this process — one warning per
# value, not one per ticker per call site.
_warned: set[str] = set()


def learning_mode_state() -> tuple[str, str]:
    """Return (mode, reason). Reads settings at call time; never raises."""
    from core.config import settings

    raw = getattr(settings, "RL_LEARNING_MODE", ADAPT)
    value = str(raw).strip().lower() if raw is not None else ""
    if value in _MODES:
        return value, f"rl.learning_mode={value}"
    if value not in _warned:
        _warned.add(value)
        logger.warning(
            "[learning_mode] Unrecognised rl.learning_mode %r — failing closed to %s",
            raw, OBSERVE,
        )
    return OBSERVE, f"unrecognised rl.learning_mode {raw!r}; failed closed to {OBSERVE}"


def learning_mode() -> str:
    """The effective mode: 'adapt' or 'observe'."""
    return learning_mode_state()[0]


def is_observing() -> bool:
    return learning_mode() == OBSERVE


def decision_weights(weight_memory, sector: str) -> dict[str, float] | None:
    """Weights a decision should aggregate with.

    observe: the sector's configured default table, whatever is stored.
    adapt:   the stored effective weights, or None when nothing is stored
             (callers keep their existing fallback).
    """
    if is_observing():
        from core.intelligence.rl.workflows.sector_router import get_sector_weights
        return get_sector_weights(sector)
    return weight_memory.effective_weights() if weight_memory is not None else None


def weight_observation(
    *,
    review_date: str,
    mode: str,
    mode_reason: str,
    stored,
    proposal,
    decision: dict[str, float] | None,
) -> dict:
    """Diagnostic record of what the adapter would have written.

    `stored` is the WeightMemory as loaded; `proposal` is the adapter's output
    computed on a copy of it. Weights are the raw current_weights a save would
    have written; deltas are proposal minus stored, per agent.
    """
    adapted = proposal.weight_version != stored.weight_version
    stored_w = dict(stored.current_weights)
    would_be = dict(proposal.current_weights)
    deltas = {
        a: round(would_be.get(a, 0.0) - stored_w.get(a, 0.0), 6)
        for a in sorted(set(stored_w) | set(would_be))
    }
    if adapted and proposal.weight_history:
        adapter_reason = proposal.weight_history[-1].reason
    else:
        adapter_reason = "no proposal (fewer observations than rl.weight_min_observations)"
    return {
        "review_date": review_date,
        "mode": mode,
        "mode_reason": mode_reason,
        "applied": False,
        "stored_version": stored.weight_version,
        "stored_weights": stored_w,
        "would_be_version": proposal.weight_version,
        "would_be_weights": would_be,
        "deltas": {a: d for a, d in deltas.items() if d != 0.0},
        "adapter_reason": adapter_reason,
        "decision_weights": dict(decision or {}),
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
