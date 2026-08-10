"""Watchdog prep — safe, idempotent preparation run automatically.

Prep NEVER performs the irreversible step. For Atlas C11 it runs the ETL
dry-run, then the real ETL, and stops: flipping ATLAS_ENABLED stays human,
because prod holds no Railway token (see the design doc, section 9).

The point is the transcript. It rides in the notification so the alert reads
"prep done and verified, one step left" rather than "go and check".
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PrepResult:
    ok: bool
    transcript: list[str]


PREPS: dict[str, Callable[[], PrepResult]] = {}


def prep(name: str):
    """Register a prep under `name` for reference from milestones.yaml."""
    def _wrap(fn: Callable[[], PrepResult]) -> Callable[[], PrepResult]:
        if name in PREPS:
            raise ValueError(f"prep {name!r} already registered")
        PREPS[name] = fn
        return fn
    return _wrap


def run_prep(name: str) -> PrepResult:
    """Run a prep by name. Never raises."""
    fn = PREPS.get(name)
    if fn is None:
        return PrepResult(False, [f"prep {name!r} is not registered"])
    try:
        return fn()
    except Exception as exc:
        logger.warning("[watchdog] prep %s raised: %s", name, exc, exc_info=True)
        return PrepResult(False, [f"prep {name!r} raised: {exc}"])


def _run_etl(**kwargs):
    """Indirection so tests patch one function instead of the script."""
    from scripts.atlas_etl import run_etl
    return run_etl(**kwargs)


@prep("atlas_cutover_prep")
def atlas_cutover_prep() -> PrepResult:
    """Dry-run the ETL, then run it for real. Never sets ATLAS_ENABLED.

    The dry run is the gate: if the sources cannot even be read, we stop
    before writing anything.
    """
    lines: list[str] = []
    try:
        dry = _run_etl(dry_run=True)
        lines.append(f"ETL dry-run OK: {dry}")
    except Exception as exc:
        lines.append(f"ETL dry-run FAILED: {exc}")
        lines.append("Aborted before the real ETL — nothing was written.")
        return PrepResult(False, lines)

    try:
        real = _run_etl(dry_run=False)
        lines.append(f"ETL complete: {real}")
    except Exception as exc:
        lines.append(f"ETL FAILED: {exc}")
        return PrepResult(False, lines)

    lines.append("Prep done. ATLAS_ENABLED deliberately NOT set — that step "
                 "is yours.")
    return PrepResult(True, lines)
