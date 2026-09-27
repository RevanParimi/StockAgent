"""
src/backend/shared/pipeline/decision_gate.py
============================================
SA-003 (audit F08): recommendations and learning act only on essential data.

Before this module, `data_health` was write-only. A run whose price source
answered 404 could still ship BUY, and production recorded BUY on 1 of 6
scored dimensions and STRONG BUY on 3 of 9: the aggregator renormalises over
whatever was scored, so one surviving dimension becomes the whole verdict.

The gate, for one analysis run:

  abstain     an essential section (observability.data_health_essential_sections:
              fundamentals, technicals, peers_valuation) is not ok/cache_hit;
              or fewer than decision_gate.min_dimensions_fraction of the
              sector's dimensions were scored; or the run has no structured
              provenance (the legacy worker-pool fallback builds no bundle).
  degraded    actionable, but an ordinary enrichment (news, macro, flows, ...)
              or a dimension above the minimum share is missing.
  actionable  complete.

It is derived from the same pure `build_record` the data-health row uses, so
the gate and the row cannot disagree, and it is computed whether or not the
row is recorded (`observability.data_health_enabled` only switches the row).

One switch, `decision_gate.mode` (env DECISION_GATE_MODE):

  record   every consumer computes the gate and records what enforcement
           would stop; nothing changes. The checked-in default.
  enforce  consumers stop: see config.yaml `decision_gate`.

An unrecognised value fails closed to enforce. Artifacts made before this
module (forecast rows, shelf ideas) carry no gate; their status is UNKNOWN,
which `is_actionable` treats as not verified.

Skip records go to data/logs/decision_gate.jsonl, one row per skipped (or,
in record mode, would-be-skipped) action, with its reason and source run id.
Rows are ticker-level only: no user id is ever written here. Per-user
decisions are recorded on the user's own AdviceRecord.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.shared.schemas.pipeline import DecisionGate

logger = logging.getLogger(__name__)

RECORD = "record"
ENFORCE = "enforce"
_MODES = (RECORD, ENFORCE)

ACTIONABLE = "actionable"
DEGRADED = "degraded"
ABSTAIN = "abstain"
UNKNOWN = ""          # an artifact made before the gate existed

ABSTAIN_VERDICT = "INSUFFICIENT DATA"

DEFAULT_MIN_DIMENSIONS_FRACTION = 0.5

# Same volume rule as data_health: data/logs is the Railway mount.
LOGS_DIR = Path(os.getenv("LOGS_DIR", "data/logs"))

# Unrecognised mode values already warned about in this process.
_warned: set[str] = set()


# ---------------------------------------------------------------------------
# The switch
# ---------------------------------------------------------------------------

def gate_mode_state() -> tuple[str, str]:
    """Return (mode, reason). Reads settings at call time; never raises."""
    from core.config import settings

    raw = getattr(settings, "DECISION_GATE_MODE", RECORD)
    value = str(raw).strip().lower() if raw is not None else ""
    if value in _MODES:
        return value, f"decision_gate.mode={value}"
    if value not in _warned:
        _warned.add(value)
        logger.warning(
            "[decision_gate] Unrecognised decision_gate.mode %r — failing closed to %s",
            raw, ENFORCE,
        )
    return ENFORCE, f"unrecognised decision_gate.mode {raw!r}; failed closed to {ENFORCE}"


def gate_mode() -> str:
    return gate_mode_state()[0]


def enforcing() -> bool:
    return gate_mode() == ENFORCE


def min_dimensions_fraction() -> float:
    """`decision_gate.min_dimensions_fraction`, clamped to [0, 1]."""
    from backend.shared.config.settings.loader import cfg
    try:
        value = float(cfg("decision_gate.min_dimensions_fraction",
                          fallback=DEFAULT_MIN_DIMENSIONS_FRACTION))
    except (TypeError, ValueError):
        value = DEFAULT_MIN_DIMENSIONS_FRACTION
    return min(max(value, 0.0), 1.0)


def is_actionable(status: str | None) -> bool:
    """actionable and degraded may act; abstain and UNKNOWN may not."""
    return status in (ACTIONABLE, DEGRADED)


# ---------------------------------------------------------------------------
# The analysis gate
# ---------------------------------------------------------------------------

def gate_from_health_row(row: dict[str, Any], *, run_id: str = "") -> DecisionGate:
    """
    The gate implied by one data-health row (build_record's shape, or a
    normalized telemetry row). A v1 row, or one without essential_unusable,
    abstains: its `ok` never meant the data arrived.
    """
    run_id = run_id or str(row.get("run_id") or "")
    try:
        version = int(row.get("contract_version")) if row.get("contract_version") is not None else None
    except (TypeError, ValueError):
        version = None
    essential = row.get("essential_unusable")
    if version is None or version < 2 or not isinstance(essential, dict):
        return DecisionGate(
            status=ABSTAIN, run_id=run_id,
            reasons=["health record without contract v2 provenance: essential data unverified"],
        )

    scored = int(row.get("dimensions_scored") or 0)
    expected = int(row.get("dimensions_expected") or 0)
    reasons: list[str] = []
    if row.get("health") == "hollow":
        reasons.append("hollow run")
    reasons += [f"essential {name}={status}" for name, status in essential.items()]
    floor = min_dimensions_fraction()
    if expected <= 0:
        reasons.append("no dimensions expected for this sector")
    elif scored / expected < floor:
        reasons.append(f"dimensions scored {scored}/{expected} < {floor:.0%}")

    if reasons:
        status = ABSTAIN
    elif row.get("health") == "ok":
        status = ACTIONABLE
    else:
        status = DEGRADED
        reasons = list(row.get("health_reasons") or [])
    return DecisionGate(
        status=status, run_id=run_id, reasons=reasons,
        essential_unusable={str(k): str(v) for k, v in essential.items()},
        dimensions_scored=scored, dimensions_expected=expected,
    )


def assess_analysis(
    *,
    run_id: str,
    section_status: dict[str, str] | None,
    dimensions_expected: list[str] | None,
    dimensions_missing: list[str] | None,
    section_provenance: dict[str, dict] | None = None,
) -> DecisionGate:
    """The gate for one unified-path run. Pure apart from config reads."""
    from services.data.stores.data_health import build_record
    row = build_record(
        run_id=run_id, ticker="", sector="",
        section_status=section_status, api_calls=None,
        dimensions_expected=dimensions_expected,
        dimensions_missing=dimensions_missing,
        section_provenance=section_provenance,
    )
    return gate_from_health_row(row, run_id=run_id)


def no_provenance_gate(run_id: str, reason: str) -> DecisionGate:
    """Abstain for a run that built no bundle (legacy worker-pool path)."""
    return DecisionGate(status=ABSTAIN, run_id=run_id, reasons=[reason])


def apply_gate(report, gate: DecisionGate) -> DecisionGate:
    """Attach the gate to a FinalReport. In enforce mode an abstaining gate
    withholds the verdict: it moves to `withheld_verdict` and the report reads
    INSUFFICIENT DATA. final_score and the agent scores are left as computed,
    for diagnosis; every consumer that acts on them checks the gate first."""
    mode, _ = gate_mode_state()
    gate.mode = mode
    if gate.status == ABSTAIN and mode == ENFORCE:
        gate.enforced = True
        gate.withheld_verdict = report.verdict
        report.verdict = ABSTAIN_VERDICT
    report.decision_gate = gate
    return gate


def report_gate(report) -> tuple[str, str, list[str]]:
    """(status, run_id, reasons) of a report's gate; UNKNOWN when it has none."""
    gate = getattr(report, "decision_gate", None)
    if gate is None:
        return UNKNOWN, "", ["analysis carries no decision gate"]
    return gate.status, gate.run_id, list(gate.reasons)


def row_gate_reason(status: str, run_id: str) -> str:
    """Why a forecast row made by run `run_id` cannot be acted or learned on."""
    if status == UNKNOWN:
        return "forecast issued before the data gate existed: provenance unknown"
    return f"forecast issued by run {run_id or '?'} with data gate {status}"


# ---------------------------------------------------------------------------
# Skip records
# ---------------------------------------------------------------------------

def _path(path: str | None = None) -> Path:
    return Path(path) if path else LOGS_DIR / "decision_gate.jsonl"


def record_gate_decision(
    *,
    consumer: str,
    ticker: str,
    skipped: str,
    status: str,
    reasons: list[str],
    run_id: str,
    enforced: bool,
    on_date: str | None = None,
    extra: dict | None = None,
    path: str | None = None,
) -> dict:
    """
    One row per action the gate stopped (enforced=True) or, in record mode,
    would have stopped (enforced=False). Never raises; never takes a user id.
    """
    mode, mode_reason = gate_mode_state()
    row = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "consumer": consumer,
        "ticker": ticker,
        "date": on_date,
        "skipped": skipped,
        "status": status or "unknown",
        "reasons": list(reasons or []),
        "source_run_id": run_id or "",
        "mode": mode,
        "mode_reason": mode_reason,
        "enforced": bool(enforced),
        **(extra or {}),
    }
    try:
        target = _path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, default=str) + "\n")
    except Exception as exc:
        logger.warning("[decision_gate] skip record write failed (non-fatal): %s", exc)
    # A real skip is a WARNING; a record-mode "would skip" is routine telemetry.
    log = logger.warning if enforced else logger.info
    log(
        "[decision_gate] %s %s %s: %s — %s (status=%s, run=%s)",
        consumer, ticker, "SKIPPED" if enforced else "would skip (record mode)",
        skipped, "; ".join(row["reasons"]) or "no reason given", row["status"],
        row["source_run_id"] or "-",
    )
    return row
