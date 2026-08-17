"""Watchdog checks — named, individually testable state probes.

Every check answers one question: is this thing done / broken / blocked?
A check must never raise to its caller; run_check converts any exception into
state="unknown", which NOTIFIES. That inverts the codebase's usual
"swallow and stay quiet" default on purpose: a watchdog that fails silently
is worse than no watchdog.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Literal
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

_GITHUB_REPO = "RevanParimi/StockAgent"     # verified via `git remote get-url origin`
_IST = ZoneInfo("Asia/Kolkata")

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

def _data_dir() -> Path:
    """Resolved at call time so tests patching _DATA_DIR affect prep too."""
    return _DATA_DIR


def _atlas_prep_marker() -> Path:
    """Written by atlas_cutover_prep once the ETL has run successfully."""
    return _data_dir() / "atlas_prep_done.json"


def _atlas_prep_record() -> dict | None:
    try:
        return json.loads(_atlas_prep_marker().read_text(encoding="utf-8"))
    except Exception:
        return None


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
    prepared = _atlas_prep_record()
    evidence = {"atlas_enabled": False,
                "atlas_db_present": atlas_db.exists(),
                "portfolio_dirs": dirs,
                "prepared_at": (prepared or {}).get("at")}

    if atlas_db.exists():
        # Our OWN prep creates atlas.db. Without distinguishing that from an
        # unexplained one, Saturday's prep would make Sunday — the last day of
        # the window — report "pre-flight DIRTY, investigate", talking the user
        # out of the very cutover this milestone exists to land.
        if prepared and prepared.get("validated"):
            return CheckResult(
                "pending",
                f"ETL already run and VALIDATED by the watchdog at "
                f"{prepared.get('at')} ({prepared.get('result')}). "
                "Ready to flip — the flag is still off.", evidence)
        if prepared:
            fails = "; ".join(prepared.get("failures") or []) or "see logs"
            return CheckResult(
                "blocked",
                f"ETL ran at {prepared.get('at')} but its validation FAILED "
                f"({fails[:180]}). Do NOT flip the flag until this is "
                "resolved.", evidence)
        return CheckResult(
            "blocked",
            "Pre-flight DIRTY: data/atlas.db already exists and the watchdog "
            "did not create it — investigate before cutting over.", evidence)
    if unexpected:
        return CheckResult(
            "blocked",
            f"Pre-flight DIRTY: unexpected portfolio dirs {unexpected} "
            "(expected only 'primary').", evidence)
    return CheckResult(
        "pending",
        "Pre-flight clean (atlas.db absent, portfolio/ = only 'primary'). "
        "ATLAS_ENABLED is not set.", evidence)


# ---------------------------------------------------------------------------
# Standing invariants
# ---------------------------------------------------------------------------

def _today() -> date:
    return datetime.now(_IST).date()


_REGISTRY_RELPATH = "config/milestones.yaml"


def _github_registry_text() -> str | None:
    """config/milestones.yaml as it stands on origin/main. None if unavailable."""
    import base64
    token = os.getenv("GITHUB_TOKEN") or ""
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(
        f"https://api.github.com/repos/{_GITHUB_REPO}/contents/"
        f"{_REGISTRY_RELPATH}?ref=main", headers=headers)
    with urllib.request.urlopen(req, timeout=15) as resp:
        payload = json.loads(resp.read())
    raw = payload.get("content")
    if not raw:
        return None
    return base64.b64decode(raw).decode("utf-8")


def _local_registry_text() -> str | None:
    try:
        return Path(_REGISTRY_RELPATH).read_text(encoding="utf-8")
    except Exception:
        return None


def _normalise(text: str) -> str:
    """Compare content, not line endings or trailing whitespace."""
    return "\n".join(line.rstrip() for line in text.strip().splitlines())


@check("registry_is_current")
def registry_is_current() -> CheckResult:
    """Is the DEPLOYED registry the same as the one on origin/main?

    This deliberately compares the registry file rather than the commit SHA.
    Holding unrelated commits back is normal working practice here, so a
    SHA comparison would warn every day and get ignored. What actually
    matters is narrower: a milestone added but never deployed leaves the
    watchdog blind to it — the one way this design silently goes stale.
    """
    local = _local_registry_text()
    if local is None:
        return CheckResult("unknown",
                           f"Could not read the deployed {_REGISTRY_RELPATH}.")
    remote = _github_registry_text()
    if remote is None:
        return CheckResult("unknown",
                           "Could not read the registry from origin/main.")
    if _normalise(local) == _normalise(remote):
        return CheckResult("satisfied",
                           "Deployed registry matches origin/main.")
    return CheckResult(
        "pending",
        "The registry on origin/main differs from the deployed one — a "
        "milestone has been added or changed but not deployed, so the "
        "watchdog is blind to it. Redeploy.")


def _api_usage() -> dict:
    from services.data.stores.api_usage import get_usage
    return get_usage()


@check("serper_counter_current_month")
def serper_counter_current_month() -> CheckResult:
    usage = _api_usage()
    month = str(usage.get("month") or "")
    expected = _today().strftime("%Y-%m")
    if month == expected:
        return CheckResult("satisfied", f"Counter is on {month}.",
                           {"month": month})
    return CheckResult(
        "pending",
        f"API usage counter still reads {month!r}, expected {expected!r} — "
        "the monthly rollover did not happen.", {"month": month})


def _scorecard_dir() -> Path:
    from core.config import settings
    return Path(settings.SCORECARD_DIR)


@check("monthly_scorecard_written")
def monthly_scorecard_written() -> CheckResult:
    """The scorecard file is named for the COMPLETED month, so on any day in
    September the file to look for is 2026-08_scorecard.json."""
    today = _today()
    prev = (today.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    path = _scorecard_dir() / f"{prev}_scorecard.json"
    if path.exists():
        return CheckResult("satisfied", f"{prev} scorecard present.",
                           {"path": str(path)})
    return CheckResult("pending", f"{prev} scorecard is missing at {path}.",
                       {"path": str(path)})


_AUDIT_RUN_PATH = _DATA_DIR / "audit_last_run.json"


def _audit_counts() -> dict:
    """Last nightly grading summary, persisted by the audit job."""
    return json.loads(_AUDIT_RUN_PATH.read_text(encoding="utf-8"))


@check("audit_graded_when_due")
def audit_graded_when_due() -> CheckResult:
    """Closes the hole in alert_job_partial_output, which returns early when
    expected <= 0. On 2026-08-07 graded=0 AND skipped_unpriceable=0, so
    expected was 0 and NO alert fired for a 0/119 grading run.

    Two failure modes, both invisible before this: the nightly stopped running
    at all, and the nightly ran but produced nothing while having work to do.
    """
    try:
        run = _audit_counts()
    except FileNotFoundError:
        return CheckResult("pending",
                           "No audit run summary yet — the nightly has not "
                           "completed since the watchdog was deployed.")

    last = date.fromisoformat(str(run["date"]))
    age = (_today() - last).days
    if age > 2:
        return CheckResult(
            "pending",
            f"Last audit run was {last} ({age} days ago) — the nightly has "
            "stopped running.", run)

    graded = int(run.get("graded") or 0)
    present = int(run.get("already_present") or 0)
    pending_rows = int(run.get("pending_rows") or 0)
    if graded == 0 and present == 0 and pending_rows > 0:
        return CheckResult(
            "pending",
            f"The auditor graded 0 and carried 0 forward while {pending_rows} "
            "advice row(s) exist — the 0/119 signature. Check the ^NSEI "
            "benchmark fetch.", run)
    return CheckResult(
        "satisfied",
        f"Last run {last}: graded={graded}, already_present={present}.", run)


def _atlas_enabled() -> bool:
    from services.data.stores import atlas_store
    return atlas_store.enabled()


def _identity_counts() -> tuple[int, int]:
    """(accounts in users.db, mirrored rows in atlas.db). Called only once the
    flag is on — `user_ids()` opens atlas.db, which CREATES it, and a
    pre-cutover atlas.db reads as a dirty pre-flight."""
    from services.data.stores import atlas_store, user_store
    return user_store.count_users(), len(atlas_store.user_ids())


@check("users_mirrored")
def users_mirrored() -> CheckResult:
    """Does every users.db account have its atlas.db mirror row?

    Signup writes users.db; `atlas_store.user_ids()` — the set the brief and
    autopilot fan out over — reads atlas.db. The mirror between them is written
    non-fatally, and unlike the user_instruments index there is no nightly
    rebuild to quietly repair it. A dropped mirror is therefore a person who
    authenticates fine and receives nothing: exactly the class of silent
    failure this watchdog exists to end.
    """
    if not _atlas_enabled():
        return CheckResult(
            "satisfied",
            "Atlas plane is off — users.db is the sole identity store.",
            {"atlas_enabled": False})
    n_users, n_mirrored = _identity_counts()
    evidence = {"atlas_enabled": True, "users_db": n_users,
                "atlas_db": n_mirrored}
    if n_users == n_mirrored:
        return CheckResult("satisfied",
                           f"{n_users} user(s), all mirrored into atlas.db.",
                           evidence)
    if n_mirrored < n_users:
        return CheckResult(
            "pending",
            f"{n_users - n_mirrored} of {n_users} account(s) are missing from "
            "atlas.db — they can log in but receive no brief and no autopilot. "
            "Re-run scripts/atlas_etl.py (idempotent).", evidence)
    return CheckResult(
        "pending",
        f"atlas.db holds {n_mirrored - n_users} user row(s) that users.db does "
        "not — a delete cascade half-failed. Reconcile before trusting the "
        "fan-out set.", evidence)


@check("manual_confirmation")
def manual_confirmation() -> CheckResult:
    """No programmatic signal exists; stays pending until the entry is removed
    from the registry. Deliberately dumb — a date-only reminder."""
    return CheckResult("pending", "Awaiting manual confirmation.")


# ---------------------------------------------------------------------------
# PI Prospect — IPO feed liveness
# ---------------------------------------------------------------------------

@check("ipo_cache_fresh")
def ipo_cache_fresh() -> CheckResult:
    """The IPO cache is refreshed twice daily by the ipo_refresh jobs. If it
    goes stale the jobs are dead, and the failure is otherwise SILENT — the
    brief keeps rendering yesterday's issues with no error anywhere."""
    from core.config import settings

    max_age = float(getattr(settings, "IPO_CACHE_MAX_AGE_HOURS", 48))
    path = _data_dir() / "market_cache" / "ipo.json"
    if not path.exists():
        return CheckResult("pending", f"IPO cache absent at {path}",
                           {"path": str(path)})
    try:
        stamp = json.loads(path.read_text(encoding="utf-8")).get("fetched_at") or ""
        fetched = datetime.fromisoformat(stamp)
    except Exception as exc:
        return CheckResult("pending", f"IPO cache timestamp unreadable: {exc}",
                           {"path": str(path)})
    if fetched.tzinfo is None:
        fetched = fetched.replace(tzinfo=timezone.utc)
    age_h = (datetime.now(timezone.utc) - fetched).total_seconds() / 3600.0
    evidence = {"fetched_at": stamp, "age_hours": round(age_h, 1),
                "max_age_hours": max_age}
    if age_h > max_age:
        return CheckResult(
            "pending",
            f"IPO cache is stale — {age_h:.1f}h old (limit {max_age:.0f}h). "
            f"The twice-daily ipo_refresh job is not running.",
            evidence)
    return CheckResult("satisfied", f"IPO cache {age_h:.1f}h old.", evidence)


@check("ipo_signals_accruing")
def ipo_signals_accruing() -> CheckResult:
    """An OPEN issue with no capture snapshot means the P2 ledger has stopped
    accruing. Silent by nature: a dead ledger and a quiet IPO month look
    identical until P3 needs the data and finds a hole in it.

    Deliberately scoped to currently-open issues so a month with no IPOs
    reports satisfied rather than crying wolf.
    """
    from core.ipo.calendar import issue_state
    from core.ipo.signals import IpoSignalStore

    path = _data_dir() / "market_cache" / "ipo.json"
    if not path.exists():
        return CheckResult("satisfied", "No IPO cache yet — nothing to capture.",
                           {"path": str(path)})
    try:
        cache = json.loads(path.read_text(encoding="utf-8"))
        today = _today()
        rows = (cache.get("current") or []) + (cache.get("upcoming") or [])
        open_symbols = [r.get("symbol", "") for r in rows
                        if isinstance(r, dict) and issue_state(r, today) == "open"]
    except Exception as exc:
        # Covers a bad parse AND a malformed shape (top-level JSON not a dict,
        # or current/upcoming not lists) — either way the cache is corrupt,
        # not quiet, so this is a real "pending", not a crash.
        return CheckResult("pending", f"IPO cache unreadable: {exc}",
                           {"path": str(path)})

    if not open_symbols:
        return CheckResult("satisfied", "No open IPO window — nothing to capture.",
                           {"open_issues": 0})

    try:
        store = IpoSignalStore(base_dir=str(_data_dir() / "ipo"))
        missing = [s for s in open_symbols if not store.load_symbol(s)]
    except Exception as exc:
        # A permission error or unreadable ledger means capture cannot be
        # confirmed for issue(s) that are open right now — that is itself
        # worth surfacing, not something to let bubble up and rely on
        # run_check's outer net to catch.
        return CheckResult(
            "pending",
            f"IPO capture ledger unreadable: {exc}. Cannot confirm capture is "
            f"landing for open issue(s): {', '.join(open_symbols)}.",
            {"open_issues": len(open_symbols), "error": str(exc)})

    evidence = {"open_issues": len(open_symbols), "missing": missing}
    if missing:
        return CheckResult(
            "pending",
            f"IPO capture ledger has no snapshot for open issue(s): "
            f"{', '.join(missing)}. The refresh job is running but capture is "
            f"not landing — check ipo.signals_enabled and the ledger path.",
            evidence)
    return CheckResult(
        "satisfied",
        f"Capture ledger has snapshots for all {len(open_symbols)} open issue(s).",
        evidence)
