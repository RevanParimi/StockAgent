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

Contract v2 (SA-002, audit F07). v1 rows took a section's status from its
text, so "Technical data unavailable for TATAMOTORS" read `ok`, and derived
`health` from the dimension count alone: a 9/9 run with one live section was
`ok`. In v2 each section's status is its producer's FetchResult verdict
(ok / cache_hit / stale / fallback / empty / n/a / unverified / failed:<Type>),
and `health` is `ok` only when every dimension scored AND every section that
applies came back verified and fresh. Essential price/fundamental sections
are listed separately in `essential_unusable` because SA-003 gates on them.
Every non-`ok` verdict names its causes in `health_reasons`.

v1 rows stay on disk untouched. `normalize_health_row` reads both and labels
a v1 row's provenance unknown rather than pretending its `ok` meant v2's.
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
    LIVE_STATUSES,
    SECTION_ORDER,
    STATUS_EMPTY,
    STATUS_FAILED_PREFIX,
    STATUS_FALLBACK,
    STATUS_NOT_APPLICABLE,
    STATUS_STALE,
    STATUS_UNVERIFIED,
)

logger = logging.getLogger(__name__)

# The telemetry contract. Rows without the field are v1 (B2, 2026-08-26).
CONTRACT_VERSION = 2
LEGACY_CONTRACT_VERSION = 1

# Sections whose absence leaves no price or fundamental evidence (SA-002/003).
DEFAULT_ESSENTIAL_SECTIONS = ("fundamentals", "technicals", "peers_valuation")

_LEGACY_SECTION_PROVENANCE = {
    "source": "unknown", "as_of": None,
    "reason": "recorded under contract v1: the status meant only that the fetcher did not raise",
}

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


def essential_sections() -> list[str]:
    """`observability.data_health_essential_sections`, limited to real section names."""
    configured = cfg("observability.data_health_essential_sections",
                     fallback=list(DEFAULT_ESSENTIAL_SECTIONS))
    names = [str(n) for n in (configured or []) if str(n) in SECTION_ORDER]
    return names or list(DEFAULT_ESSENTIAL_SECTIONS)


def _bucket(status: str) -> str:
    """The counter a section status adds to. Unknown statuses are `unverified`:
    a value outside the vocabulary is not evidence that data arrived."""
    if status in LIVE_STATUSES:
        return "live"
    if status.startswith(STATUS_FAILED_PREFIX):
        return "degraded"
    return {
        STATUS_EMPTY: "empty",
        STATUS_NOT_APPLICABLE: "not_applicable",
        STATUS_STALE: "stale",
        STATUS_FALLBACK: "fallback",
    }.get(status, "unverified")


def assess_health(
    *, sections: dict[str, str], dimensions_scored: int, dimensions_expected: int,
) -> dict[str, Any]:
    """
    The verdict, its reasons, and the essential sections that were unusable.

    `hollow` means the run should not train the RL loop (B5). The thresholds
    are deliberately the weakest ones that are still true — no dimension
    scored, or no section came back verified (`ok`/`cache_hit`). Raising them
    is a judgement about how much data the RL loop needs, which belongs to
    B5/SA-003 with rows in hand, not to the task that makes the rows honest.

    `degraded` is anything short of a full run: a missing dimension, or any
    section that applies (not `n/a`) and did not come back verified and
    fresh. `ok` therefore requires every dimension and every applicable
    section — a 9/9 run with one live section is not `ok` (F07).
    """
    essential = essential_sections()
    live = sum(1 for s in sections.values() if s in LIVE_STATUSES)

    hollow: list[str] = []
    if dimensions_scored < _hollow_min_dimensions():
        hollow.append(f"dimensions scored {dimensions_scored} < {_hollow_min_dimensions()}")
    if live < _hollow_min_live_sections():
        hollow.append(f"live sections {live} < {_hollow_min_live_sections()}")

    short: list[str] = []
    if dimensions_expected and dimensions_scored < dimensions_expected:
        short.append(f"dimensions missing {dimensions_expected - dimensions_scored}"
                     f"/{dimensions_expected}")
    essential_unusable = {
        name: sections.get(name, f"{STATUS_FAILED_PREFIX}NotReached")
        for name in essential
        if sections.get(name) not in LIVE_STATUSES
        and sections.get(name) != STATUS_NOT_APPLICABLE
    }
    short += [f"essential {n}={s}" for n, s in essential_unusable.items()]
    short += [f"section {n}={s}" for n, s in sections.items()
              if n not in essential and s not in LIVE_STATUSES and s != STATUS_NOT_APPLICABLE]

    health = HEALTH_HOLLOW if hollow else (HEALTH_DEGRADED if short else HEALTH_OK)
    return {
        "health": health,
        "health_reasons": hollow + short,
        "essential_sections": essential,
        "essential_unusable": essential_unusable,
    }


def derive_health(
    *, sections: dict[str, str], dimensions_scored: int, dimensions_expected: int,
) -> str:
    """`ok` | `degraded` | `hollow` — see `assess_health`."""
    return assess_health(sections=sections, dimensions_scored=dimensions_scored,
                         dimensions_expected=dimensions_expected)["health"]


def build_record(
    *,
    run_id: str,
    ticker: str,
    sector: str,
    section_status: dict[str, str] | None,
    api_calls: dict[str, int] | None,
    dimensions_expected: list[str] | None,
    dimensions_missing: list[str] | None,
    section_provenance: dict[str, dict] | None = None,
) -> dict[str, Any]:
    """
    Shape one health row. Pure — no I/O, no config reads beyond `assess_health`.

    `dimensions_expected` is the sector's full dimension list and
    `dimensions_missing` those that carry an `error` (missing from the
    unified response, or a parse failure). A run whose analyst returned {}
    is missing all of them, which is the case that must still produce a row.

    Every section lands in exactly one counter, so
    live + degraded + empty + not_applicable + stale + fallback + unverified
    equals the number of sections.
    """
    sections = dict(section_status or {})
    # A section the builder never reached is not silently dropped — it is
    # named and marked, or the row would under-report the damage.
    for name in SECTION_ORDER:
        sections.setdefault(name, f"{STATUS_FAILED_PREFIX}NotReached")

    given = dict(section_provenance or {})
    provenance = {
        name: given.get(name) or {"source": None, "as_of": None,
                                  "reason": "no provenance reported"}
        for name in sections
    }

    counts = {k: 0 for k in ("live", "degraded", "empty", "not_applicable",
                             "stale", "fallback", "unverified")}
    for s in sections.values():
        counts[_bucket(s)] += 1

    expected = list(dimensions_expected or [])
    missing = list(dimensions_missing or [])
    scored = max(len(expected) - len(missing), 0)
    verdict = assess_health(sections=sections, dimensions_scored=scored,
                            dimensions_expected=len(expected))

    return {
        "contract_version": CONTRACT_VERSION,
        "ts": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "ticker": ticker,
        "sector": sector,
        "sections": sections,
        "section_provenance": provenance,
        **counts,
        "dimensions_expected": len(expected),
        "dimensions_scored": scored,
        "dimensions_missing": missing,
        "api_calls": dict(api_calls or {}),
        **verdict,
    }


def normalize_health_row(row: dict[str, Any]) -> dict[str, Any]:
    """
    One health row, from the JSONL or the telemetry table, in the v2 shape.

    A row without `contract_version` (or with NULL there) is v1. It is
    returned with every field it had, and labelled rather than upgraded:
    `provenance_known: False`, each section's provenance `unknown`, and
    `essential_unusable` / `health_reasons` None — v1 recorded nothing from
    which to derive them honestly. Its `health` stays what v1 wrote, with
    `health_basis` saying what that meant. Never raises on a malformed field.
    """
    out = dict(row)
    for key in ("sections", "section_provenance", "dimensions_missing", "api_calls",
                "essential_sections", "essential_unusable", "health_reasons"):
        if isinstance(out.get(key), str):
            try:
                out[key] = json.loads(out[key])
            except ValueError:
                pass
    try:
        version = int(out["contract_version"]) if out.get("contract_version") is not None else None
    except (TypeError, ValueError):
        version = None
    if version is None or version < CONTRACT_VERSION:
        sections = out.get("sections") if isinstance(out.get("sections"), dict) else {}
        out.update({
            "contract_version": LEGACY_CONTRACT_VERSION,
            "provenance_known": False,
            "health_basis": ("v1: dimension count and live-section count only; a section "
                             "status meant the fetcher did not raise, not that data arrived"),
            "section_provenance": {n: dict(_LEGACY_SECTION_PROVENANCE) for n in sections},
            "essential_unusable": None,
            "health_reasons": None,
        })
        return out
    out["contract_version"] = version
    out["provenance_known"] = True
    out["health_basis"] = ("v2: every dimension scored and every applicable section "
                           "verified and fresh")
    return out


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
    section_provenance: dict[str, dict] | None = None,
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
            section_provenance=section_provenance,
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
            contract_version=record["contract_version"],
            section_provenance=json.dumps(record["section_provenance"], default=str),
            stale=record["stale"],
            fallback=record["fallback"],
            unverified=record["unverified"],
            essential_unusable=json.dumps(record["essential_unusable"], default=str),
            health_reasons=json.dumps(record["health_reasons"], default=str),
        )
    except Exception as exc:
        logger.warning("[data_health] telemetry DB mirror failed (non-fatal): %s", exc)

    missing_note = ""
    if record["dimensions_missing"]:
        missing_note = ", missing=" + ",".join(record["dimensions_missing"])
    essential_note = ""
    if record["essential_unusable"]:
        essential_note = ", essential unusable=" + ",".join(
            f"{n}:{s}" for n, s in record["essential_unusable"].items())
    log = logger.warning if record["health"] != HEALTH_OK else logger.info
    log(
        "[data_health] %s/%s %s — sections live=%d failed=%d empty=%d stale=%d "
        "fallback=%d unverified=%d n/a=%d, dimensions %d/%d%s%s",
        sector, ticker, record["health"], record["live"], record["degraded"],
        record["empty"], record["stale"], record["fallback"], record["unverified"],
        record["not_applicable"], record["dimensions_scored"],
        record["dimensions_expected"], missing_note, essential_note,
    )
    return record


def recent_health_rows(limit: int = 100) -> list[dict[str, Any]]:
    """The newest `limit` rows from telemetry.db, normalized (v1 rows labelled).
    [] when the store is unavailable; never raises."""
    try:
        from services.data.stores import log_store
        return [normalize_health_row(r) for r in log_store.data_health_rows(limit)]
    except Exception as exc:
        logger.warning("[data_health] read failed (non-fatal): %s", exc)
        return []
