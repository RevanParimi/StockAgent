"""
Audit Wave 1 (AUD-039) — self-monitoring alerts through the existing push channel.

The 2026-07-11 incident: the OpenRouter key died, 887 calls returned 401 over
~3 hours, every scheduled job logged "complete" with zero output, and no human
was told. Two tiny helpers close that gap:

    record_llm_result(success)             — call after every LLM call
                                             (wired into llm_client.record_llm_call);
                                             >= _FAIL_STREAK consecutive failures
                                             emits ONE critical alert, throttled.
    alert_job_zero_output(job, produced, expected)
                                           — call from a job's summary point;
                                             "completed with 0/N output" alerts
                                             (same-day repeats deduped by the
                                             alerts layer's date|kind key).

Both persist minimal state in data/ops_alerts_state.json and NEVER raise —
telemetry must not take down the pipeline it watches.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import date
from pathlib import Path

logger = logging.getLogger(__name__)

_STATE_PATH = Path("data") / "ops_alerts_state.json"
_FAIL_STREAK = 10            # consecutive LLM failures before alerting
_THROTTLE_S = 6 * 3600       # at most one streak alert per 6 h


def _load_state() -> dict:
    try:
        return json.loads(_STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(state: dict) -> None:
    try:
        from core.utils.atomic_io import atomic_write_json
        atomic_write_json(_STATE_PATH, state, indent=None)   # AUD-057
    except Exception as exc:
        logger.debug("[ops_alerts] state write failed (non-fatal): %s", exc)


def _emit(kind: str, message: str) -> None:
    """One critical alert through the existing delivery layer. Never raises
    from callers' perspective (they wrap us anyway)."""
    from core.delivery.alerts import AlertEvent, emit_alerts
    emit_alerts([AlertEvent(date=date.today().isoformat(), kind=kind, symbol="",
                            message=message, severity="critical")],
                title="StockAgent ops alert")


def record_llm_result(success: bool) -> None:
    """Track consecutive LLM failures; alert once per streak (AUD-039)."""
    try:
        state = _load_state()
        if success:
            if state.get("llm_consecutive_failures"):
                state["llm_consecutive_failures"] = 0
                _save_state(state)
            return
        streak = int(state.get("llm_consecutive_failures", 0)) + 1
        state["llm_consecutive_failures"] = streak
        now = time.time()
        if streak >= _FAIL_STREAK and \
                now - float(state.get("last_llm_alert_ts", 0)) > _THROTTLE_S:
            state["last_llm_alert_ts"] = now
            try:
                _emit("llm_failure_streak",
                      f"LLM provider failing: {streak} consecutive call failures — "
                      "check OPENROUTER_API_KEY validity, key limit, and balance.")
            except Exception as exc:
                logger.warning("[ops_alerts] llm alert emit failed: %s", exc)
        _save_state(state)
    except Exception as exc:
        logger.debug("[ops_alerts] record_llm_result failed (non-fatal): %s", exc)


def alert_job_zero_output(job: str, produced: int, expected: int) -> None:
    """A job that 'completed' with zero output against nonzero expected input
    is the silent-failure signature (AUD-039). Same-day repeats are deduped by
    the alerts layer (date|kind key)."""
    try:
        if expected <= 0 or produced > 0:
            return
        try:
            _emit(f"job_zero_output_{job}",
                  f"Job '{job}' completed with 0/{expected} output — likely a "
                  "provider/key failure being swallowed. Check logs.")
        except Exception as exc:
            logger.warning("[ops_alerts] zero-output alert emit failed: %s", exc)
    except Exception as exc:
        logger.debug("[ops_alerts] alert_job_zero_output failed (non-fatal): %s", exc)


def alert_job_partial_output(job: str, produced: int, expected: int) -> None:
    """A job that completed only PART of its input (e.g. 13/16 reviews after a
    harvest timeout, AUD-084/090b) is invisible to the zero-output alert.
    Warning severity — the day still ran; same-day repeats deduped by the
    alerts layer (date|kind key)."""
    try:
        if expected <= 0 or produced <= 0 or produced >= expected:
            return
        from core.delivery.alerts import AlertEvent, emit_alerts
        emit_alerts([AlertEvent(
            date=date.today().isoformat(),
            kind=f"job_partial_output_{job}", symbol="",
            message=(f"Job '{job}' completed {produced}/{expected} — the rest "
                     "timed out or failed. Check logs."),
            severity="warning")],
            title="StockAgent ops alert")
    except Exception as exc:
        logger.debug("[ops_alerts] alert_job_partial_output failed (non-fatal): %s", exc)


def alert_job_crashed(job: str, error: str) -> None:
    """An exception escaped a scheduled job entirely (AUD-084 listener class):
    everything after the crash point — alerts, portfolio pipeline — did not
    run. Same-day repeats deduped by the alerts layer (date|kind key)."""
    try:
        _emit(f"job_crashed_{job}",
              f"Scheduled job '{job}' CRASHED: {error[:300]} — steps after the "
              "crash (alerts / portfolio pipeline) did not run. Check logs.")
    except Exception as exc:
        logger.debug("[ops_alerts] alert_job_crashed failed (non-fatal): %s", exc)
