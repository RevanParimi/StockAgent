"""
services/data/stores/data_health.py
===================================
One row per analysis run describing what that run actually received.

Why this exists (Three Loops PI, task B2 — spec 2026-08-24 §2.3, §6.2):
a prod SUZLON run lost 3 of its 6 dimensions, shipped a BUY, and logged
`real_data=True`. `SectorDataBundle.has_real_data` is `live_count >= 3` of
10 sections, so it reads True with 7 sections dead, and its only consumer is
a log line. Nothing anywhere recorded which sections came back empty, which
raised, and which dimensions the analyst never produced — so a degraded run
and a healthy one left the same trace.

Output (both, per the B1 rule that `LOGS_DIR` means the Railway volume):
  data/logs/data_health.jsonl   — the human/UI copy
  telemetry.db.data_health      — the queryable one that survives a redeploy

WRITE-ONLY BY DESIGN. Nothing branches on `health` yet. B5 adds the
hollow-run gate that keeps a hollow run out of the RL loop; until then this
module observes and never changes an outcome. It also never raises: a run
must not fail because its bookkeeping did.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.shared.config.settings.loader import cfg
from services.data.context.bundle_builder import (
    SECTION_ORDER,
    STATUS_CACHE_HIT,
    STATUS_EMPTY,
    STATUS_FAILED_PREFIX,
    STATUS_NOT_APPLICABLE,
    STATUS_OK,
)

logger = logging.getLogger(__name__)

# B1: data/logs is the Railway volume mount; bare `logs/` is ephemeral
# container storage, wiped by every redeploy. Same default as run_logger.
LOGS_DIR = Path(os.getenv("LOGS_DIR", "data/logs"))
DATA_HEALTH_LOG = LOGS_DIR / "data_health.jsonl"

HEALTH_OK = "ok"
HEALTH_DEGRADED = "degraded"
HEALTH_HOLLOW = "hollow"


def data_health_enabled() -> bool:
    """Rollback line: `observability.data_health_enabled: false` in config.yaml."""
    return bool(cfg("observability.data_health_enabled", fallback=True))


def _hollow_min_dimensions() -> int:
    return int(cfg("observability.data_health_hollow_min_dimensions", fallback=1))


def _hollow_min_live_sections() -> int:
    return int(cfg("observability.data_health_hollow_min_live_sections", fallback=1))


def derive_health(*, live: int, dimensions_scored: int, dimensions_expected: int) -> str:
    """
    `ok` | `degraded` | `hollow`.

    `hollow` means the run should not train the RL loop (B5). The default
    thresholds are deliberately the weakest ones that are still true — a run
    is hollow only when it scored no dimension at all, or fetched no live
    section at all. Raising them is a judgement about how much data the RL
    loop needs, which belongs to B5 with the first weeks of rows in hand, not
    to the task that starts collecting them.

    `degraded` is anything short of a full run: a missing dimension, or a
    section that failed or came back empty. `n/a` sections are not a defect.
    """
    if dimensions_scored < _hollow_min_dimensions() or live < _hollow_min_live_sections():
        return HEALTH_HOLLOW
    if dimensions_expected and dimensions_scored < dimensions_expected:
        return HEALTH_DEGRADED
    return HEALTH_OK


def build_record(
    *,
    run_id: str,
    ticker: str,
    sector: str,
    section_status: dict[str, str] | None,
    api_calls: dict[str, int] | None,
    dimensions_expected: list[str] | None,
    dimensions_missing: list[str] | None,
) -> dict[str, Any]:
    """
    Shape one health row. Pure — no I/O, no config reads beyond `derive_health`.

    `dimensions_expected` is the sector's full dimension list and
    `dimensions_missing` those that carry an `error` (missing from the
    unified response, or a parse failure). A run whose analyst returned {}
    is missing all of them, which is the case that must still produce a row.
    """
    sections = dict(section_status or {})
    # A section the builder never reached is not silently dropped — it is
    # named and marked, or the row would under-report the damage.
    for name in SECTION_ORDER:
        sections.setdefault(name, f"{STATUS_FAILED_PREFIX}NotReached")

    statuses = list(sections.values())
    live = sum(1 for s in statuses if s in (STATUS_OK, STATUS_CACHE_HIT))
    degraded = sum(1 for s in statuses if s.startswith(STATUS_FAILED_PREFIX))
    empty = sum(1 for s in statuses if s == STATUS_EMPTY)
    not_applicable = sum(1 for s in statuses if s == STATUS_NOT_APPLICABLE)

    expected = list(dimensions_expected or [])
    missing = list(dimensions_missing or [])
    scored = max(len(expected) - len(missing), 0)

    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "ticker": ticker,
        "sector": sector,
        "sections": sections,
        "live": live,
        "degraded": degraded,
        "empty": empty,
        "not_applicable": not_applicable,
        "dimensions_expected": len(expected),
        "dimensions_scored": scored,
        "dimensions_missing": missing,
        "api_calls": dict(api_calls or {}),
        "health": derive_health(
            live=live, dimensions_scored=scored, dimensions_expected=len(expected)
        ),
    }


def _append(record: dict[str, Any]) -> None:
    DATA_HEALTH_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(DATA_HEALTH_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str) + "\n")


def record_data_health(
    *,
    run_id: str,
    ticker: str,
    sector: str,
    section_status: dict[str, str] | None,
    api_calls: dict[str, int] | None,
    dimensions_expected: list[str] | None,
    dimensions_missing: list[str] | None,
) -> dict[str, Any] | None:
    """
    Build and persist one health row. Returns it, or None when the flag is
    off or the record could not be built.

    NEVER raises. Each of the three steps — build, JSONL append, telemetry
    mirror — is isolated, so a broken writer costs the row (or half of it),
    never the run. The caller is mid-analysis and has a verdict to deliver.
    """
    try:
        if not data_health_enabled():
            return None
    except Exception as exc:
        logger.warning("[data_health] flag read failed (non-fatal): %s", exc)
        return None

    try:
        record = build_record(
            run_id=run_id,
            ticker=ticker,
            sector=sector,
            section_status=section_status,
            api_calls=api_calls,
            dimensions_expected=dimensions_expected,
            dimensions_missing=dimensions_missing,
        )
    except Exception as exc:
        logger.warning("[data_health] record build failed (non-fatal): %s", exc)
        return None

    try:
        _append(record)
    except Exception as exc:
        logger.warning("[data_health] JSONL write failed (non-fatal): %s", exc)

    try:
        from services.data.stores import log_store
        log_store.log_data_health(
            run_id=record["run_id"],
            ticker=record["ticker"],
            sector=record["sector"],
            sections=json.dumps(record["sections"], default=str),
            live=record["live"],
            degraded=record["degraded"],
            empty=record["empty"],
            not_applicable=record["not_applicable"],
            dimensions_expected=record["dimensions_expected"],
            dimensions_scored=record["dimensions_scored"],
            dimensions_missing=json.dumps(record["dimensions_missing"], default=str),
            api_calls=json.dumps(record["api_calls"], default=str),
            health=record["health"],
        )
    except Exception as exc:
        logger.warning("[data_health] telemetry DB mirror failed (non-fatal): %s", exc)

    missing_note = ""
    if record["dimensions_missing"]:
        missing_note = ", missing=" + ",".join(record["dimensions_missing"])
    log = logger.warning if record["health"] != HEALTH_OK else logger.info
    log(
        "[data_health] %s/%s %s — sections live=%d failed=%d empty=%d n/a=%d, "
        "dimensions %d/%d%s",
        sector, ticker, record["health"], record["live"], record["degraded"],
        record["empty"], record["not_applicable"], record["dimensions_scored"],
        record["dimensions_expected"], missing_note,
    )
    return record
