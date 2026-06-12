"""
core/intelligence/regime/state.py
==================================
Living Envelope (RL Phase 2.5) — Component 1: Sticky regime (hysteresis).

RegimeDetector.detect() classifies the market into one of six labels every
day (see detector.py docstring): MACRO_CRISIS, RISK_OFF, MOMENTUM_EXTENDED,
RISK_ON, OVERSOLD, NORMAL. That raw label is ephemeral — a single calm day
can flip MACRO_CRISIS straight back to NORMAL, which is too jumpy for
regime-weight multipliers and re-forecast triggers.

This module adds a market-wide sticky layer on top of the raw label:

  - Severity order (only RISK_OFF / MACRO_CRISIS are "severe"; every other
    label — NORMAL, RISK_ON, MOMENTUM_EXTENDED, OVERSOLD — is "calm" for
    hysteresis purposes):
        NORMAL/RISK_ON/MOMENTUM_EXTENDED/OVERSOLD (0) < RISK_OFF (1) < MACRO_CRISIS (2)
  - A severe label is entered IMMEDIATELY on first detection.
  - A milder detection while a severe label is sticky increments calm_streak.
  - After RL_REGIME_CALM_DAYS consecutive milder detections, the sticky label
    exits to the milder detected label (calm_streak resets to 0).
  - Any severe re-detection resets calm_streak to 0 (does not necessarily
    change the label if it's already at/above that severity).
  - Same-day repeat calls are idempotent — calling update_sticky_regime twice
    for the same `today` does not double-count calm_streak.

Persisted market-wide (NOT per ticker): data/predictions/_regime_state.json
(path follows PredictionStore's PREDICTION_DATA_DIR convention).

Flag: RL_REGIME_STICKY_ENABLED (default true). When disabled, this module
never touches disk and simply echoes the detected label back with calm_streak=0
— i.e. raw label pass-through (today's behavior).

NEVER raises. Corrupt/missing state file -> start fresh from detected label.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, asdict
from pathlib import Path

from core.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Severity ordering
# ---------------------------------------------------------------------------
# Only RISK_OFF and MACRO_CRISIS are treated as "severe" regimes for sticky
# hysteresis. All other detector labels (NORMAL, RISK_ON, MOMENTUM_EXTENDED,
# OVERSOLD) are equally "calm" — severity 0 — matching the spec's
# NORMAL < RISK_OFF < MACRO_CRISIS ordering while accommodating the detector's
# full six-label set.
_SEVERITY = {
    "MACRO_CRISIS": 2,
    "RISK_OFF": 1,
}
_DEFAULT_SEVERITY = 0  # NORMAL, RISK_ON, MOMENTUM_EXTENDED, OVERSOLD, and unknowns


def _severity(label: str) -> int:
    return _SEVERITY.get(label, _DEFAULT_SEVERITY)


@dataclass
class RegimeState:
    label: str          # NORMAL / RISK_OFF / MACRO_CRISIS / ... (sticky label)
    since: str          # ISO date the sticky label was entered
    calm_streak: int     # consecutive detections milder than the sticky label


def _state_path() -> Path:
    return Path(settings.PREDICTION_DATA_DIR) / "_regime_state.json"


def _read_state(path: Path) -> RegimeState | None:
    """Read and parse the persisted state file. None on missing/corrupt."""
    try:
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return RegimeState(
            label=str(data["label"]),
            since=str(data["since"]),
            calm_streak=int(data["calm_streak"]),
        )
    except Exception as exc:
        logger.warning("[RegimeState] Corrupt/unreadable state file %s: %s", path, exc)
        return None


def _write_state(path: Path, state: RegimeState) -> None:
    """Atomically persist state. Logs and swallows any error (never raises)."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(state), indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
    except Exception as exc:
        logger.error("[RegimeState] Failed to persist state to %s: %s", path, exc)


def update_sticky_regime(detected_label: str, today: str) -> RegimeState:
    """
    Update (and persist) the market-wide sticky regime state given today's
    raw RegimeDetector label.

    Parameters
    ----------
    detected_label : raw label from RegimeDetector.detect() (e.g. "MACRO_CRISIS")
    today : ISO date string "YYYY-MM-DD" for the current detection

    Returns
    -------
    The (possibly updated) RegimeState. Never raises.

    Behavior
    --------
    - RL_REGIME_STICKY_ENABLED == False: returns RegimeState(detected_label,
      today, 0) WITHOUT reading or writing any file (raw pass-through).
    - No/corrupt state file: start fresh — RegimeState(detected_label, today, 0),
      persisted.
    - detected severity > current sticky severity: enter the new (severer)
      label immediately, since=today, calm_streak=0.
    - detected severity >= current sticky severity (re-detection at same or
      higher severity, including equal severe label again): calm_streak
      resets to 0; label/since unchanged (unless strictly severer, handled
      above).
    - detected severity < current sticky severity (milder detection):
      calm_streak increments by 1 (once per distinct `today`); if calm_streak
      reaches RL_REGIME_CALM_DAYS, exit to the milder detected label
      (since=today, calm_streak=0).
    - Same-day repeat calls (same `today` as the persisted state's last
      update) are idempotent: state is returned unchanged without
      incrementing calm_streak again or re-writing the file.
    """
    try:
        if not getattr(settings, "RL_REGIME_STICKY_ENABLED", True):
            return RegimeState(label=detected_label, since=today, calm_streak=0)

        path = _state_path()
        current = _read_state(path)

        if current is None:
            fresh = RegimeState(label=detected_label, since=today, calm_streak=0)
            _write_state(path, fresh)
            return fresh

        # Same-day idempotence: if this state was already updated for `today`,
        # return it unchanged. We track the last-processed date via a
        # sentinel stored alongside calm_streak bookkeeping — but RegimeState
        # itself has no "last_detected_date" field per spec, so we detect
        # same-day repeats by comparing `since` only when the label hasn't
        # moved AND the persisted file was written by THIS function for
        # `today` already. To keep this robust and simple, we persist an
        # internal `_last_update` marker in the JSON (not part of the
        # dataclass contract) so repeat calls for the same date are no-ops.
        last_update = _read_last_update(path)
        if last_update == today:
            return current

        detected_sev = _severity(detected_label)
        current_sev = _severity(current.label)

        if detected_sev > current_sev:
            # Enter the severer regime immediately.
            new_state = RegimeState(label=detected_label, since=today, calm_streak=0)
        elif detected_sev >= current_sev:
            # Same-severity re-detection (incl. severe re-detection at the
            # same level): reset calm streak, keep label/since.
            new_state = RegimeState(label=current.label, since=current.since, calm_streak=0)
        else:
            # Milder detection than the sticky label.
            new_streak = current.calm_streak + 1
            calm_days = int(getattr(settings, "RL_REGIME_CALM_DAYS", 3))
            if new_streak >= calm_days:
                new_state = RegimeState(label=detected_label, since=today, calm_streak=0)
            else:
                new_state = RegimeState(label=current.label, since=current.since, calm_streak=new_streak)

        _write_state_with_marker(path, new_state, today)
        return new_state
    except Exception as exc:
        logger.error("[RegimeState] update_sticky_regime failed, passthrough: %s", exc)
        return RegimeState(label=detected_label, since=today, calm_streak=0)


# ---------------------------------------------------------------------------
# Internal: same-day idempotence marker
# ---------------------------------------------------------------------------
# RegimeState (per spec) only has {label, since, calm_streak}. To make
# same-day repeat calls idempotent without changing the public dataclass, we
# persist one extra "_last_update" field in the JSON file and ignore it when
# constructing RegimeState from disk.

def _read_last_update(path: Path) -> str | None:
    try:
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        val = data.get("_last_update")
        return str(val) if val is not None else None
    except Exception:
        return None


def _write_state_with_marker(path: Path, state: RegimeState, today: str) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(state)
        payload["_last_update"] = today
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
    except Exception as exc:
        logger.error("[RegimeState] Failed to persist state to %s: %s", path, exc)
