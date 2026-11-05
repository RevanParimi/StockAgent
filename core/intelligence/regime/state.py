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

**A day whose label the live inputs do not establish** (FIX-023:
RegimeSnapshot.unavailable, e.g. India VIX did not answer, or the detector
failed) goes through `record_unavailable_day` instead. It moves nothing, except
that it enters a severer label the inputs that answered establish on their
own (`floor_label`); it never counts as a calm day, nor breaks a calm streak.
The day is marked unavailable, so `label_recorded_for` gives no label for it
and idle-cash deployment opens nothing. The first established detection of the
same day replaces the mark. Example: sticky NORMAL; on 30 Oct Yahoo's India
VIX is empty and the Nifty fell 3% in 5 sessions, so the label could be
anything from NORMAL to MACRO_CRISIS: the state stays NORMAL, marked "India VIX
did not answer", and deployment reads "market regime unavailable for
2026-10-30: India VIX did not answer".

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


def severity(label: str) -> int:
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
      incrementing calm_streak again or re-writing the file. A day
      `record_unavailable_day` marked is not yet updated: the first call for
      it applies the transition and clears the mark.
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
        if last_update == today and not _read_unavailable(path):
            return current

        detected_sev = severity(detected_label)
        current_sev = severity(current.label)

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


def record_unavailable_day(today: str, why: str, floor_label: str = "") -> RegimeState | None:
    """Record `today` (ISO date) as a day whose label the live inputs do not
    establish (FIX-023): `why` says which inputs did not answer, or that the
    detector failed; `floor_label` is the label the inputs that answered
    establish on their own ("" when none).

    Returns the sticky state, or None when there is none to carry (the sticky
    layer off, or no readable state: nothing is written, and the caller keeps
    the raw label). Never raises.

    - The day is already established (updated for `today`, not marked): no-op.
    - Otherwise the state is kept, except that a `floor_label` severer than
      the sticky label is entered (since=today, calm_streak=0). calm_streak is
      neither incremented nor reset. The day is marked unavailable with `why`.
    """
    try:
        if not getattr(settings, "RL_REGIME_STICKY_ENABLED", True):
            return None
        path = _state_path()
        current = _read_state(path)
        if current is None:
            return None
        if _read_last_update(path) == today and not _read_unavailable(path):
            return current
        new_state = current
        if floor_label and severity(floor_label) > severity(current.label):
            new_state = RegimeState(label=floor_label, since=today, calm_streak=0)
        _write_state_with_marker(path, new_state, today, unavailable=why or "unavailable")
        return new_state
    except Exception as exc:
        logger.error("[RegimeState] record_unavailable_day failed: %s", exc)
        return None


def label_recorded_for(today: str) -> str | None:
    """The sticky label as updated for `today` (ISO date) by the daily review,
    or None when the state was not updated for that day (missing, corrupt,
    stale, or written for a later day) or the day was recorded unavailable
    (`record_unavailable_day`). Read-only. Idle-cash deployment
    (core/portfolio/deployment.py) buys only on a label of its own review day.

    A state written fresh (no `_last_update` marker yet) counts for the day it
    was entered (`since`)."""
    path = _state_path()
    state = _read_state(path)
    if state is None:
        return None
    last = _read_last_update(path)
    if (last or state.since) != today or _read_unavailable(path):
        return None
    return state.label


def unrecorded_reason(today: str) -> str:
    """Why `label_recorded_for(today)` is None, as the deployment record
    says it: "market regime unavailable for 2026-10-30: India VIX did not
    answer" for a day recorded unavailable, else "no market regime recorded
    for 2026-10-30"."""
    path = _state_path()
    why = _read_unavailable(path) if _read_last_update(path) == today else ""
    if why:
        return f"market regime unavailable for {today}: {why}"
    return f"no market regime recorded for {today}"


# ---------------------------------------------------------------------------
# Internal: same-day idempotence marker
# ---------------------------------------------------------------------------
# RegimeState (per spec) only has {label, since, calm_streak}. To make
# same-day repeat calls idempotent without changing the public dataclass, we
# persist one extra "_last_update" field in the JSON file and ignore it when
# constructing RegimeState from disk. A day recorded unavailable also carries
# "_unavailable" (why); it always describes the `_last_update` day.

def _read_marker(path: Path, key: str) -> str | None:
    try:
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        val = data.get(key)
        return str(val) if val is not None else None
    except Exception:  # swallow-ok: an unreadable marker reads as none; _read_state logs the corrupt file
        return None


def _read_last_update(path: Path) -> str | None:
    return _read_marker(path, "_last_update")


def _read_unavailable(path: Path) -> str:
    return _read_marker(path, "_unavailable") or ""


def _write_state_with_marker(path: Path, state: RegimeState, today: str,
                             unavailable: str = "") -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(state)
        payload["_last_update"] = today
        if unavailable:
            payload["_unavailable"] = unavailable
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
    except Exception as exc:
        logger.error("[RegimeState] Failed to persist state to %s: %s", path, exc)
