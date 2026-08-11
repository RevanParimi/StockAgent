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
from datetime import datetime
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

_IST = ZoneInfo("Asia/Kolkata")


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


# ---------------------------------------------------------------------------
# Atlas spec §6 step-5 validations — the gate before the flag is flipped.
#
# The Atlas plan calls the dry-run active_user_ids() check "the runtime gate
# that confirms it before the flip": with AUTH_REQUIRED=true there is no owner
# fallback, so an empty users table post-flip means the morning brief and
# autopilot fan out to NOBODY. Running the ETL and reporting "ready to flip"
# without these checks would be worse than not preparing at all.
# ---------------------------------------------------------------------------

def _atlas_db_path():
    from services.data.stores import atlas_store
    return atlas_store.db_path()


def _atlas_user_ids() -> list[str]:
    """Dry-run `active_user_ids()`. Reads atlas.db directly, so it works while
    the flag is still false — which is the whole point."""
    from services.data.stores import atlas_store
    return atlas_store.user_ids()


def _atlas_integrity() -> tuple[bool, list[str]]:
    """PRAGMA integrity_check + foreign_key_check on atlas.db."""
    import sqlite3
    path = _atlas_db_path()
    if not Path(path).exists():
        return False, [f"atlas.db not found at {path}"]
    problems: list[str] = []
    try:
        conn = sqlite3.connect(str(path))
        try:
            rows = conn.execute("PRAGMA integrity_check").fetchall()
            if not (len(rows) == 1 and str(rows[0][0]).lower() == "ok"):
                problems += [str(r[0]) for r in rows]
            fk = conn.execute("PRAGMA foreign_key_check").fetchall()
            problems += [f"FK violation in {r[0]} (rowid {r[1]})" for r in fk]
        finally:
            conn.close()
    except Exception as exc:
        return False, [f"integrity check raised: {exc}"]
    return (not problems), problems


def _atlas_table_counts() -> dict[str, int]:
    """Row count per table — the 'row counts' half of step 5."""
    import sqlite3
    path = _atlas_db_path()
    counts: dict[str, int] = {}
    conn = sqlite3.connect(str(path))
    try:
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()]
        for t in tables:
            counts[t] = int(conn.execute(
                f'SELECT COUNT(*) FROM "{t}"').fetchone()[0])
    finally:
        conn.close()
    return counts


def _atlas_validations() -> tuple[bool, list[str]]:
    """Run all three step-5 validations. Returns (passed, transcript lines)."""
    from core.config import settings

    lines: list[str] = []
    failures: list[str] = []

    ok, problems = _atlas_integrity()
    if ok:
        lines.append("DDL integrity check: OK (integrity_check + foreign_key_check)")
    else:
        failures.append(f"DDL integrity FAILED: {'; '.join(problems)[:200]}")

    try:
        counts = _atlas_table_counts()
        summary = ", ".join(f"{k}={v}" for k, v in sorted(counts.items()) if v)
        lines.append(f"Row counts: {summary or '(all tables empty)'}")
    except Exception as exc:
        failures.append(f"Row counts FAILED: {exc}")

    owner = settings.PORTFOLIO_DEFAULT_USER_ID
    try:
        ids = _atlas_user_ids()
        if not ids:
            failures.append(
                "Dry-run active_user_ids() returned EMPTY — after the flip the "
                "brief and autopilot would fan out to nobody. DO NOT FLIP.")
        elif owner not in ids:
            failures.append(
                f"Dry-run active_user_ids() = {ids} but the owner "
                f"{owner!r} is missing — the owner would stop receiving "
                "briefs after the flip. DO NOT FLIP.")
        else:
            lines.append(f"Dry-run active_user_ids(): {ids} (owner present)")
    except Exception as exc:
        failures.append(f"Dry-run active_user_ids() raised: {exc}")

    return (not failures), lines + failures


@prep("atlas_cutover_prep")
def atlas_cutover_prep() -> PrepResult:
    """Dry-run the ETL, then run it for real. Never sets ATLAS_ENABLED.

    The dry run is the gate: if the sources cannot even be read, we stop
    before writing anything.

    Records a marker on success. That marker does double duty: it stops the
    ETL being re-run on the window's second day (wasteful, and re-running has
    been observed to raise FOREIGN KEY errors), and it lets
    `atlas_cutover_pending` tell the atlas.db WE created from an unexplained
    one — otherwise Saturday's prep makes Sunday report "pre-flight DIRTY".
    """
    from core.ops.watchdog.checks import _atlas_prep_marker, _atlas_prep_record

    done = _atlas_prep_record()
    if done and done.get("validated"):
        return PrepResult(True, [
            f"Already prepared and validated at {done.get('at')} "
            f"({done.get('result')}). ETL not re-run.",
            "The flag is deliberately NOT set — that step is yours."])

    lines: list[str] = []
    if done:
        # The ETL ran before but validation failed. Re-running the ETL is
        # wasteful and can raise FK errors on a second pass, so re-validate
        # only — that way fixing the cause and waiting for tomorrow works.
        lines.append(f"ETL already ran at {done.get('at')} but validation "
                     "failed last time — re-running validations only.")
        real = done.get("result")
    else:
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

    passed, validation_lines = _atlas_validations()
    lines += validation_lines
    failures = [] if passed else [l for l in validation_lines
                                  if "FAILED" in l or "DO NOT FLIP" in l]

    try:
        from core.utils.atomic_io import atomic_write_json
        atomic_write_json(_atlas_prep_marker(),
                          {"at": datetime.now(_IST).isoformat(timespec="seconds"),
                           "result": real,
                           "validated": passed,
                           "failures": failures}, indent=None)
    except Exception as exc:
        # Non-fatal, but say so: without the marker the next run re-runs the
        # ETL and the check will read atlas.db as unexplained.
        lines.append(f"WARNING: could not record the prep marker ({exc}) — "
                     "tomorrow's check may report a dirty pre-flight.")

    if not passed:
        lines.append("VALIDATION FAILED — do NOT flip the flag. Investigate "
                     "the failures above first.")
        return PrepResult(False, lines)

    lines.append("Prep done and validated. The flag is deliberately NOT set — "
                 "that step is yours.")
    return PrepResult(True, lines)
