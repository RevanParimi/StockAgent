"""Watchdog checks — named, individually testable state probes.

Every check answers one question: is this thing done / broken / blocked?
A check must never raise to its caller; run_check converts any exception into
state="unknown", which NOTIFIES. That inverts the codebase's usual
"swallow and stay quiet" default on purpose: a watchdog that fails silently
is worse than no watchdog.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Literal

logger = logging.getLogger(__name__)

CheckState = Literal["satisfied", "pending", "blocked", "unknown"]

# Patched in tests; prod cwd is /app so data/ is the mounted volume.
_DATA_DIR = Path("data")


@dataclass(frozen=True)
class CheckResult:
    state: CheckState
    detail: str
    evidence: dict = field(default_factory=dict)


CHECKS: dict[str, Callable[[], CheckResult]] = {}


def check(name: str):
    """Register a check under `name` for reference from milestones.yaml."""
    def _wrap(fn: Callable[[], CheckResult]) -> Callable[[], CheckResult]:
        if name in CHECKS:
            raise ValueError(f"check {name!r} already registered")
        CHECKS[name] = fn
        return fn
    return _wrap


def run_check(name: str) -> CheckResult:
    """Run a check by name. Never raises."""
    fn = CHECKS.get(name)
    if fn is None:
        return CheckResult("unknown", f"check {name!r} is not registered")
    try:
        return fn()
    except Exception as exc:
        logger.warning("[watchdog] check %s raised: %s", name, exc, exc_info=True)
        return CheckResult("unknown", f"check {name!r} raised: {exc}")


# ---------------------------------------------------------------------------
# Atlas C11
# ---------------------------------------------------------------------------

@check("atlas_cutover_pending")
def atlas_cutover_pending() -> CheckResult:
    """Satisfied once ATLAS_ENABLED is set. Until then, report whether the
    documented pre-flight is still clean (atlas.db absent, portfolio/ holding
    only the primary user) — a dirty pre-flight means the human's next step
    is investigation, not the cutover."""
    if (os.getenv("ATLAS_ENABLED") or "").strip():
        return CheckResult("satisfied", "ATLAS_ENABLED is set — cutover done.",
                           {"atlas_enabled": True})

    atlas_db = _DATA_DIR / "atlas.db"
    portfolio = _DATA_DIR / "portfolio"
    dirs = sorted(p.name for p in portfolio.iterdir() if p.is_dir()) \
        if portfolio.is_dir() else []
    unexpected = [d for d in dirs if d != "primary"]
    evidence = {"atlas_enabled": False,
                "atlas_db_present": atlas_db.exists(),
                "portfolio_dirs": dirs}

    if atlas_db.exists():
        return CheckResult(
            "blocked",
            "Pre-flight DIRTY: data/atlas.db already exists — investigate "
            "before cutting over.", evidence)
    if unexpected:
        return CheckResult(
            "blocked",
            f"Pre-flight DIRTY: unexpected portfolio dirs {unexpected} "
            "(expected only 'primary').", evidence)
    return CheckResult(
        "pending",
        "Pre-flight clean (atlas.db absent, portfolio/ = only 'primary'). "
        "ATLAS_ENABLED is not set.", evidence)
