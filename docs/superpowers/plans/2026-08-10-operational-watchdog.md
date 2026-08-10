# Operational Watchdog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make prod detect, unprompted, that a milestone is due/lapsed or a standing invariant has broken, and tell the user by push+email — instead of it being discovered only when a human happens to ask.

**Architecture:** A committed `config/milestones.yaml` becomes the authoritative registry. `core/ops/watchdog/` loads it, runs named check functions, feeds results into a **pure** escalation engine, and emits through the existing `ops_alerts` → `emit_alerts_broadcast` channel. A new daily 06:30 IST scheduler job drives it.

**Tech Stack:** Python 3.11+, APScheduler (already wired), PyYAML (already in `requirements.txt`), pytest.

**Spec:** `docs/superpowers/specs/2026-08-10-operational-watchdog-design.md`

**DEADLINE:** Tasks 1–5 must be merged and deployed before **Sat 2026-08-15** or the Atlas C11 window is missed again. Task 5 is the minimum shippable point — after it, the watchdog notifies about Atlas. Tasks 6–9 add prep, remaining checks, heartbeat, and the memory migration.

## Global Constraints

- **Never raise into the scheduler.** The job wrapper catches everything. A check that raises becomes `CheckResult(state="unknown")` and *notifies*; it is never silently treated as satisfied.
- **New non-secret toggles use `cfg()` with NO `env=`** — `config.yaml` is the sole source. Import exactly: `from backend.shared.config.settings.loader import cfg`.
- **All dates/times are IST.** Use `zoneinfo.ZoneInfo("Asia/Kolkata")`. Never use naive `date.today()` inside the engine — the engine takes `now` as a parameter.
- **`AlertEvent.severity` only accepts `"info" | "warning" | "critical"`.** The ladder's `resolved` level maps to severity `"info"`.
- **`AlertEvent.key()` is `f"{date}|{kind}|{symbol}"`** — the alerts layer dedups on it. Encode the milestone id and level into `kind` so per-day dedup works.
- **Test suite must stay green.** Baseline at plan time: **2525 passed / 12 skipped / 0 failed**.
- Commit after every task.

---

### Task 1: Registry — schema, loader, validation

**Files:**
- Create: `config/milestones.yaml`
- Create: `core/ops/__init__.py`
- Create: `core/ops/watchdog/__init__.py`
- Create: `core/ops/watchdog/registry.py`
- Test: `tests/unit/ops/test_watchdog_registry.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `Milestone` dataclass and `load_registry(path: str | Path = "config/milestones.yaml") -> list[Milestone]`; raises `RegistryError` on any validation failure.

```python
@dataclass(frozen=True)
class Window:
    weekdays: tuple[int, ...]          # 0=Mon .. 6=Sun; empty = always open

@dataclass(frozen=True)
class Milestone:
    id: str
    kind: Literal["milestone", "invariant"]
    title: str
    check: str
    prep: str | None = None
    window: Window | None = None
    deadline: date | None = None
    lead_days: int = 3
    schedule: Literal["daily", "monthly"] = "daily"
    action: str = ""
    docs: str = ""
```

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/ops/test_watchdog_registry.py
import pytest
from datetime import date
from core.ops.watchdog.registry import load_registry, RegistryError, Milestone


def _write(tmp_path, text):
    p = tmp_path / "milestones.yaml"
    p.write_text(text, encoding="utf-8")
    return p


def test_loads_milestone_and_invariant(tmp_path):
    p = _write(tmp_path, """
milestones:
  - id: atlas_c11_cutover
    kind: milestone
    title: "Atlas C11 live cutover"
    check: atlas_cutover_pending
    prep: atlas_cutover_prep
    window: {weekdays: [sat, sun]}
    deadline: 2026-08-15
    lead_days: 3
    action: "Set ATLAS_ENABLED=true and redeploy."
    docs: docs/plan.md
invariants:
  - id: serper_month_rollover
    kind: invariant
    title: "Serper counter rolled over"
    check: serper_counter_current_month
    schedule: monthly
""")
    entries = load_registry(p)
    assert [e.id for e in entries] == ["atlas_c11_cutover", "serper_month_rollover"]
    m = entries[0]
    assert m.window.weekdays == (5, 6)          # sat, sun
    assert m.deadline == date(2026, 8, 15)
    assert m.lead_days == 3
    assert entries[1].schedule == "monthly"
    assert entries[1].window is None


def test_defaults_applied(tmp_path):
    p = _write(tmp_path, """
milestones:
  - id: m1
    kind: milestone
    title: T
    check: c
""")
    m = load_registry(p)[0]
    assert m.lead_days == 3 and m.schedule == "daily"
    assert m.prep is None and m.deadline is None and m.window is None


def test_duplicate_id_rejected(tmp_path):
    p = _write(tmp_path, """
milestones:
  - {id: dup, kind: milestone, title: A, check: c}
  - {id: dup, kind: milestone, title: B, check: c}
""")
    with pytest.raises(RegistryError, match="duplicate"):
        load_registry(p)


def test_unknown_field_rejected(tmp_path):
    p = _write(tmp_path, """
milestones:
  - {id: m1, kind: milestone, title: T, check: c, wat: 1}
""")
    with pytest.raises(RegistryError, match="unknown field"):
        load_registry(p)


def test_bad_weekday_rejected(tmp_path):
    p = _write(tmp_path, """
milestones:
  - {id: m1, kind: milestone, title: T, check: c, window: {weekdays: [funday]}}
""")
    with pytest.raises(RegistryError, match="weekday"):
        load_registry(p)


def test_missing_required_field_rejected(tmp_path):
    p = _write(tmp_path, "milestones:\n  - {id: m1, kind: milestone, title: T}\n")
    with pytest.raises(RegistryError, match="check"):
        load_registry(p)


def test_missing_file_is_registry_error(tmp_path):
    with pytest.raises(RegistryError, match="not found"):
        load_registry(tmp_path / "nope.yaml")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/ops/test_watchdog_registry.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.ops'`

- [ ] **Step 3: Implement the registry**

Create `core/ops/__init__.py` and `core/ops/watchdog/__init__.py` as empty files. Then `core/ops/watchdog/registry.py`:

```python
"""Watchdog registry — loads and validates config/milestones.yaml.

A registry that cannot be parsed is a loud failure, never a silent skip:
the caller turns RegistryError into an `unknown`-state alert.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal

import yaml

_WEEKDAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}

_ALLOWED = {"id", "kind", "title", "check", "prep", "window", "deadline",
            "lead_days", "schedule", "action", "docs"}
_REQUIRED = {"id", "kind", "title", "check"}


class RegistryError(Exception):
    """config/milestones.yaml is malformed."""


@dataclass(frozen=True)
class Window:
    weekdays: tuple[int, ...]

    def is_open(self, on: date) -> bool:
        return not self.weekdays or on.weekday() in self.weekdays


@dataclass(frozen=True)
class Milestone:
    id: str
    kind: Literal["milestone", "invariant"]
    title: str
    check: str
    prep: str | None = None
    window: Window | None = None
    deadline: date | None = None
    lead_days: int = 3
    schedule: Literal["daily", "monthly"] = "daily"
    action: str = ""
    docs: str = ""


def _parse_window(raw, mid: str) -> Window | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise RegistryError(f"{mid}: window must be a mapping")
    days = raw.get("weekdays") or []
    out = []
    for d in days:
        key = str(d).strip().lower()[:3]
        if key not in _WEEKDAYS:
            raise RegistryError(f"{mid}: unknown weekday {d!r}")
        out.append(_WEEKDAYS[key])
    return Window(weekdays=tuple(sorted(set(out))))


def _parse_entry(raw: dict, kind: str) -> Milestone:
    if not isinstance(raw, dict):
        raise RegistryError(f"{kind} entry must be a mapping, got {type(raw).__name__}")
    mid = str(raw.get("id") or "").strip()
    if not mid:
        raise RegistryError(f"{kind} entry missing 'id'")
    extra = set(raw) - _ALLOWED
    if extra:
        raise RegistryError(f"{mid}: unknown field(s) {sorted(extra)}")
    missing = _REQUIRED - set(raw)
    if missing:
        raise RegistryError(f"{mid}: missing required field(s) {sorted(missing)}")

    deadline = raw.get("deadline")
    if deadline is not None and not isinstance(deadline, date):
        raise RegistryError(f"{mid}: deadline must be an ISO date (YYYY-MM-DD)")
    schedule = str(raw.get("schedule", "daily"))
    if schedule not in ("daily", "monthly"):
        raise RegistryError(f"{mid}: schedule must be 'daily' or 'monthly'")

    return Milestone(
        id=mid,
        kind=raw["kind"],
        title=str(raw["title"]),
        check=str(raw["check"]),
        prep=(str(raw["prep"]) if raw.get("prep") else None),
        window=_parse_window(raw.get("window"), mid),
        deadline=deadline,
        lead_days=int(raw.get("lead_days", 3)),
        schedule=schedule,
        action=str(raw.get("action", "")).strip(),
        docs=str(raw.get("docs", "")),
    )


def load_registry(path: str | Path = "config/milestones.yaml") -> list[Milestone]:
    p = Path(path)
    if not p.exists():
        raise RegistryError(f"registry not found: {p}")
    try:
        doc = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise RegistryError(f"registry is not valid YAML: {exc}") from exc
    if not isinstance(doc, dict):
        raise RegistryError("registry root must be a mapping")

    entries: list[Milestone] = []
    for key in ("milestones", "invariants"):
        for raw in (doc.get(key) or []):
            entries.append(_parse_entry(raw, key))

    seen: set[str] = set()
    for e in entries:
        if e.id in seen:
            raise RegistryError(f"duplicate id: {e.id}")
        seen.add(e.id)
    return entries
```

- [ ] **Step 4: Create the seed registry**

Create `config/milestones.yaml`. Only the Atlas entry is populated now; Task 7 adds the rest.

```yaml
# Authoritative registry of date-bound milestones and standing invariants.
# Read by the ops_watchdog scheduler job (06:30 IST daily).
#
# THIS FILE IS THE SOURCE OF TRUTH. Claude's memory files must point here
# rather than carry their own dates. A new milestone lands in the SAME commit
# as the work that creates it.
#
# Reaches prod only on deploy — the deploy_matches_origin invariant guards that.

milestones:
  - id: atlas_c11_cutover
    kind: milestone
    title: "Atlas C11 live cutover"
    check: atlas_cutover_pending
    prep: atlas_cutover_prep
    window: {weekdays: [sat, sun]}
    deadline: 2026-08-15
    lead_days: 3
    action: >
      Set ATLAS_ENABLED=true in Railway and redeploy.
      Rollback at any time: set ATLAS_ENABLED=false.
    docs: docs/superpowers/plans/2026-07-26-atlas-user-data-program.md

invariants: []
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/unit/ops/test_watchdog_registry.py -q`
Expected: 7 passed

- [ ] **Step 6: Verify the real registry parses**

Run: `python -c "from core.ops.watchdog.registry import load_registry; print([m.id for m in load_registry()])"`
Expected: `['atlas_c11_cutover']`

- [ ] **Step 7: Commit**

```bash
git add core/ops config/milestones.yaml tests/unit/ops/test_watchdog_registry.py
git commit -m "feat(watchdog): committed milestone registry + strict loader"
```

---

### Task 2: Checks — result type, name registry, Atlas check

**Files:**
- Create: `core/ops/watchdog/checks.py`
- Test: `tests/unit/ops/test_watchdog_checks.py`

**Interfaces:**
- Consumes: nothing from Task 1 (deliberately independent).
- Produces: `CheckResult`, the `@check(name)` decorator, `run_check(name) -> CheckResult` (never raises; unknown name or exception → `state="unknown"`), and `CHECKS: dict[str, Callable[[], CheckResult]]`.

```python
CheckState = Literal["satisfied", "pending", "blocked", "unknown"]

@dataclass(frozen=True)
class CheckResult:
    state: CheckState
    detail: str
    evidence: dict = field(default_factory=dict)
```

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/ops/test_watchdog_checks.py
import pytest
from core.ops.watchdog import checks as C


def test_run_check_unknown_name_is_unknown_state():
    r = C.run_check("no_such_check")
    assert r.state == "unknown" and "not registered" in r.detail


def test_run_check_swallows_exception_as_unknown(monkeypatch):
    @C.check("boom_for_test")
    def _boom():
        raise RuntimeError("kaboom")
    try:
        r = C.run_check("boom_for_test")
        assert r.state == "unknown"
        assert "kaboom" in r.detail
    finally:
        C.CHECKS.pop("boom_for_test", None)


def test_duplicate_check_name_rejected():
    @C.check("dupe_for_test")
    def _a():
        return C.CheckResult("satisfied", "ok")
    try:
        with pytest.raises(ValueError, match="already registered"):
            @C.check("dupe_for_test")
            def _b():
                return C.CheckResult("satisfied", "ok")
    finally:
        C.CHECKS.pop("dupe_for_test", None)


class TestAtlasCutoverPending:
    def test_satisfied_when_flag_set(self, monkeypatch):
        monkeypatch.setenv("ATLAS_ENABLED", "true")
        r = C.run_check("atlas_cutover_pending")
        assert r.state == "satisfied"

    def test_pending_when_flag_unset_and_preflight_clean(self, monkeypatch, tmp_path):
        monkeypatch.delenv("ATLAS_ENABLED", raising=False)
        monkeypatch.setattr(C, "_DATA_DIR", tmp_path)
        (tmp_path / "portfolio").mkdir()
        (tmp_path / "portfolio" / "primary").mkdir()
        r = C.run_check("atlas_cutover_pending")
        assert r.state == "pending"
        assert r.evidence["atlas_db_present"] is False

    def test_blocked_when_atlas_db_already_exists(self, monkeypatch, tmp_path):
        monkeypatch.delenv("ATLAS_ENABLED", raising=False)
        monkeypatch.setattr(C, "_DATA_DIR", tmp_path)
        (tmp_path / "portfolio").mkdir()
        (tmp_path / "portfolio" / "primary").mkdir()
        (tmp_path / "atlas.db").write_text("x")
        r = C.run_check("atlas_cutover_pending")
        assert r.state == "blocked"
        assert "atlas.db" in r.detail

    def test_blocked_when_extra_portfolio_dirs(self, monkeypatch, tmp_path):
        monkeypatch.delenv("ATLAS_ENABLED", raising=False)
        monkeypatch.setattr(C, "_DATA_DIR", tmp_path)
        (tmp_path / "portfolio").mkdir()
        (tmp_path / "portfolio" / "primary").mkdir()
        (tmp_path / "portfolio" / "u_other").mkdir()
        r = C.run_check("atlas_cutover_pending")
        assert r.state == "blocked"
        assert "u_other" in r.detail
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/ops/test_watchdog_checks.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.ops.watchdog.checks'`

- [ ] **Step 3: Implement checks.py**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/ops/test_watchdog_checks.py -q`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add core/ops/watchdog/checks.py tests/unit/ops/test_watchdog_checks.py
git commit -m "feat(watchdog): check registry + Atlas cutover pre-flight check"
```

---

### Task 3: The engine — pure escalation ladder

**Files:**
- Create: `core/ops/watchdog/engine.py`
- Test: `tests/unit/ops/test_watchdog_engine.py`

**Interfaces:**
- Consumes: `Milestone`, `Window` (Task 1); `CheckResult` (Task 2).
- Produces:

```python
Level = Literal["info", "warning", "critical", "resolved"]

@dataclass(frozen=True)
class Notification:
    milestone_id: str
    level: Level
    title: str
    body: str
    @property
    def severity(self) -> str: ...      # "resolved" -> "info"

def evaluate(entries: list[Milestone],
             results: dict[str, CheckResult],
             now: datetime,                       # IST-aware
             prior_state: dict) -> tuple[list[Notification], dict]
```

State file shape (`data/watchdog_state.json`):

```json
{"last_run_ts": 1754800000.0,
 "entries": {"atlas_c11_cutover": {"last_level": "warning",
                                    "last_notified_date": "2026-08-15",
                                    "last_state": "pending"}}}
```

Ladder, evaluated per entry (spec §7). `lead_days` counts back from the **next window occurrence** when a window exists, else from the deadline:

| Condition | Level | Repeat |
|---|---|---|
| state `satisfied`, previously not satisfied | `resolved` | once |
| state `satisfied`, already was | — | silent |
| state `unknown` | `warning` | once per day |
| past `deadline`, not satisfied | `critical` | every 7 days |
| window open (or no window) and within lead of deadline | `warning` | once per day |
| within `lead_days` of next window occurrence | `info` | once per occurrence |
| otherwise | — | silent |

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/ops/test_watchdog_engine.py
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from core.ops.watchdog.checks import CheckResult
from core.ops.watchdog.engine import Notification, evaluate
from core.ops.watchdog.registry import Milestone, Window

IST = ZoneInfo("Asia/Kolkata")


def _now(y, m, d, hh=6, mm=30):
    return datetime(y, m, d, hh, mm, tzinfo=IST)


def _atlas(**kw):
    base = dict(id="atlas", kind="milestone", title="Atlas C11",
                check="atlas_cutover_pending", prep="atlas_cutover_prep",
                window=Window(weekdays=(5, 6)), deadline=date(2026, 8, 15),
                lead_days=3, action="Set ATLAS_ENABLED=true.")
    base.update(kw)
    return Milestone(**base)


PENDING = {"atlas": CheckResult("pending", "pre-flight clean")}
SATISFIED = {"atlas": CheckResult("satisfied", "flag set")}


def test_silent_outside_lead_window():
    # Mon 2026-08-10; next window Sat 8/15 is 5 days away, lead is 3.
    notes, state = evaluate([_atlas()], PENDING, _now(2026, 8, 10), {})
    assert notes == []
    assert state["entries"]["atlas"]["last_state"] == "pending"


def test_info_when_lead_window_opens():
    # Wed 2026-08-12 is exactly 3 days before Sat 8/15.
    notes, _ = evaluate([_atlas()], PENDING, _now(2026, 8, 12), {})
    assert [n.level for n in notes] == ["info"]
    assert "Atlas C11" in notes[0].title


def test_warning_while_window_open():
    notes, _ = evaluate([_atlas()], PENDING, _now(2026, 8, 15), {})   # Sat
    assert [n.level for n in notes] == ["warning"]


def test_no_duplicate_on_same_day():
    now = _now(2026, 8, 15)
    notes1, state = evaluate([_atlas()], PENDING, now, {})
    notes2, _ = evaluate([_atlas()], PENDING, now, state)
    assert len(notes1) == 1 and notes2 == []


def test_repeats_next_day_while_window_open():
    n1, s = evaluate([_atlas()], PENDING, _now(2026, 8, 15), {})
    n2, _ = evaluate([_atlas()], PENDING, _now(2026, 8, 16), s)      # Sun
    assert len(n1) == 1 and len(n2) == 1


def test_critical_after_deadline_lapses():
    notes, _ = evaluate([_atlas()], PENDING, _now(2026, 8, 17), {})   # past 8/15
    assert [n.level for n in notes] == ["critical"]
    assert "lapsed" in notes[0].body.lower()


def test_lapsed_repeats_weekly_not_daily():
    n1, s = evaluate([_atlas()], PENDING, _now(2026, 8, 17), {})
    n2, s2 = evaluate([_atlas()], PENDING, _now(2026, 8, 20), s)     # +3d
    n3, _ = evaluate([_atlas()], PENDING, _now(2026, 8, 24), s2)     # +7d
    assert len(n1) == 1 and n2 == [] and len(n3) == 1


def test_satisfied_emits_resolved_once_then_silent():
    _, s = evaluate([_atlas()], PENDING, _now(2026, 8, 15), {})
    n2, s2 = evaluate([_atlas()], SATISFIED, _now(2026, 8, 16), s)
    n3, _ = evaluate([_atlas()], SATISFIED, _now(2026, 8, 17), s2)
    assert [n.level for n in n2] == ["resolved"]
    assert n3 == []


def test_satisfied_from_the_start_is_silent():
    notes, _ = evaluate([_atlas()], SATISFIED, _now(2026, 8, 15), {})
    assert notes == []


def test_unknown_notifies_as_warning_once_per_day():
    res = {"atlas": CheckResult("unknown", "check raised: boom")}
    n1, s = evaluate([_atlas()], res, _now(2026, 8, 10), {})
    n2, _ = evaluate([_atlas()], res, _now(2026, 8, 10, 7), s)
    assert [n.level for n in n1] == ["warning"]
    assert "boom" in n1[0].body
    assert n2 == []


def test_blocked_warns_with_different_copy():
    res = {"atlas": CheckResult("blocked", "atlas.db already exists")}
    notes, _ = evaluate([_atlas()], res, _now(2026, 8, 15), {})
    assert [n.level for n in notes] == ["warning"]
    assert "blocked" in notes[0].body.lower()


def test_invariant_with_no_window_warns_when_pending():
    inv = Milestone(id="serper", kind="invariant", title="Serper rollover",
                    check="serper_counter_current_month")
    res = {"serper": CheckResult("pending", "counter stuck on 2026-07")}
    notes, _ = evaluate([inv], res, _now(2026, 9, 2), {})
    assert [n.level for n in notes] == ["warning"]


def test_monthly_invariant_silent_when_already_notified_this_month():
    inv = Milestone(id="sc", kind="invariant", title="Scorecard",
                    check="monthly_scorecard_written", schedule="monthly")
    res = {"sc": CheckResult("pending", "missing")}
    n1, s = evaluate([inv], res, _now(2026, 9, 1), {})
    n2, _ = evaluate([inv], res, _now(2026, 9, 14), s)
    assert len(n1) == 1 and n2 == []


def test_action_text_included_in_body():
    notes, _ = evaluate([_atlas()], PENDING, _now(2026, 8, 15), {})
    assert "ATLAS_ENABLED=true" in notes[0].body


def test_missing_check_result_is_unknown():
    notes, _ = evaluate([_atlas()], {}, _now(2026, 8, 15), {})
    assert [n.level for n in notes] == ["warning"]


def test_severity_maps_resolved_to_info():
    n = Notification("x", "resolved", "t", "b")
    assert n.severity == "info"
    assert Notification("x", "critical", "t", "b").severity == "critical"


def test_last_run_ts_recorded():
    _, state = evaluate([_atlas()], PENDING, _now(2026, 8, 10), {})
    assert state["last_run_ts"] > 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/ops/test_watchdog_engine.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.ops.watchdog.engine'`

- [ ] **Step 3: Implement engine.py**

```python
"""Watchdog engine — the escalation ladder, as a pure function.

evaluate() performs no I/O and reads no clock: `now` and `prior_state` are
parameters. That is what makes the whole ladder table-testable without prod.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Literal

from core.ops.watchdog.checks import CheckResult
from core.ops.watchdog.registry import Milestone

Level = Literal["info", "warning", "critical", "resolved"]

_LAPSED_REPEAT_DAYS = 7


@dataclass(frozen=True)
class Notification:
    milestone_id: str
    level: Level
    title: str
    body: str

    @property
    def severity(self) -> str:
        return "info" if self.level == "resolved" else self.level


def _next_window_start(entry: Milestone, today: date) -> date | None:
    """First day on/after `today` on which the window is open."""
    if entry.window is None or not entry.window.weekdays:
        return today
    for offset in range(0, 14):
        cand = today + timedelta(days=offset)
        if cand.weekday() in entry.window.weekdays:
            return cand
    return None


def _compose(entry: Milestone, result: CheckResult, level: Level,
             headline: str) -> Notification:
    lines = [headline, "", f"Status: {result.detail}"]
    if entry.action:
        lines += ["", "Next step:", entry.action.strip()]
    if entry.docs:
        lines += ["", f"Docs: {entry.docs}"]
    return Notification(entry.id, level, f"[watchdog] {entry.title}",
                        "\n".join(lines))


def evaluate(entries: list[Milestone],
             results: dict[str, CheckResult],
             now: datetime,
             prior_state: dict) -> tuple[list[Notification], dict]:
    """Return (notifications to send, new state). Pure."""
    today = now.date()
    prior_entries = (prior_state or {}).get("entries", {})
    new_entries: dict[str, dict] = {}
    notes: list[Notification] = []

    for entry in entries:
        result = results.get(entry.id) or CheckResult(
            "unknown", f"no result produced for {entry.id}")
        prior = prior_entries.get(entry.id, {})
        last_level = prior.get("last_level")
        last_state = prior.get("last_state")
        last_notified = prior.get("last_notified_date")
        record = {"last_level": last_level,
                  "last_notified_date": last_notified,
                  "last_state": result.state}

        def fire(level: Level, headline: str) -> None:
            notes.append(_compose(entry, result, level, headline))
            record["last_level"] = level
            record["last_notified_date"] = today.isoformat()

        notified_today = last_notified == today.isoformat()

        if result.state == "satisfied":
            if last_state is not None and last_state != "satisfied":
                fire("resolved", f"{entry.title} is now satisfied — closing.")
            new_entries[entry.id] = record
            continue

        if result.state == "unknown":
            if not notified_today:
                fire("warning",
                     f"{entry.title}: the check could not answer. "
                     "Treating as UNRESOLVED rather than passing it.")
            new_entries[entry.id] = record
            continue

        # pending / blocked from here on.
        lapsed = entry.deadline is not None and today > entry.deadline
        if lapsed:
            due = (last_notified is None or
                   (today - date.fromisoformat(last_notified)).days
                   >= _LAPSED_REPEAT_DAYS)
            if due:
                fire("critical",
                     f"{entry.title} has LAPSED — deadline {entry.deadline} "
                     "passed and it is still not done.")
            new_entries[entry.id] = record
            continue

        window_open = entry.window is None or entry.window.is_open(today)
        if window_open:
            if entry.schedule == "monthly":
                same_month = (last_notified is not None and
                              last_notified[:7] == today.isoformat()[:7])
                if not same_month:
                    fire("warning", f"{entry.title} needs attention.")
            elif not notified_today:
                if result.state == "blocked":
                    fire("warning",
                         f"{entry.title} is BLOCKED — a precondition failed, "
                         "so investigate before acting.")
                else:
                    fire("warning", f"{entry.title} is due now.")
            new_entries[entry.id] = record
            continue

        nxt = _next_window_start(entry, today)
        if nxt is not None and (nxt - today).days <= entry.lead_days:
            already = (last_level == "info" and last_notified is not None and
                       date.fromisoformat(last_notified) >= today
                       - timedelta(days=entry.lead_days))
            if not already:
                fire("info",
                     f"{entry.title} comes due on {nxt.isoformat()} "
                     f"({(nxt - today).days} day(s) away).")
        new_entries[entry.id] = record

    return notes, {"last_run_ts": now.timestamp(), "entries": new_entries}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/ops/test_watchdog_engine.py -q`
Expected: 17 passed

- [ ] **Step 5: Commit**

```bash
git add core/ops/watchdog/engine.py tests/unit/ops/test_watchdog_engine.py
git commit -m "feat(watchdog): pure escalation-ladder engine"
```

---

### Task 4: Runner — state persistence + delivery

**Files:**
- Create: `core/ops/watchdog/runner.py`
- Test: `tests/unit/ops/test_watchdog_runner.py`

**Interfaces:**
- Consumes: `load_registry`/`RegistryError` (T1), `run_check` (T2), `evaluate`/`Notification` (T3).
- Produces: `run_watchdog(now: datetime | None = None) -> dict` returning `{"evaluated": int, "notified": int, "levels": list[str]}`. Never raises.

Delivery goes through the existing broadcast channel. `AlertEvent.kind` embeds the id and level so the layer's `date|kind|symbol` dedup is per-entry-per-level-per-day.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/ops/test_watchdog_runner.py
import json
from datetime import datetime
from zoneinfo import ZoneInfo

from core.ops.watchdog import runner as R

IST = ZoneInfo("Asia/Kolkata")


def _reg(tmp_path, body):
    p = tmp_path / "milestones.yaml"
    p.write_text(body, encoding="utf-8")
    return p


ATLAS_YAML = """
milestones:
  - id: atlas_c11_cutover
    kind: milestone
    title: "Atlas C11 live cutover"
    check: atlas_cutover_pending
    window: {weekdays: [sat, sun]}
    deadline: 2026-08-15
    action: "Set ATLAS_ENABLED=true."
"""


def test_emits_and_persists_state(tmp_path, monkeypatch):
    sent = []
    monkeypatch.setattr(R, "_REGISTRY_PATH", _reg(tmp_path, ATLAS_YAML))
    monkeypatch.setattr(R, "_STATE_PATH", tmp_path / "watchdog_state.json")
    monkeypatch.setattr(R, "_broadcast", lambda events, title: sent.append((events, title)))
    monkeypatch.delenv("ATLAS_ENABLED", raising=False)
    monkeypatch.setattr(R, "_data_dir", lambda: tmp_path)
    (tmp_path / "portfolio").mkdir()
    (tmp_path / "portfolio" / "primary").mkdir()

    out = R.run_watchdog(now=datetime(2026, 8, 15, 6, 30, tzinfo=IST))
    assert out["evaluated"] == 1 and out["notified"] == 1
    assert sent and sent[0][0][0].severity == "warning"
    assert "atlas_c11_cutover" in sent[0][0][0].kind
    state = json.loads((tmp_path / "watchdog_state.json").read_text())
    assert state["entries"]["atlas_c11_cutover"]["last_level"] == "warning"


def test_second_run_same_day_is_silent(tmp_path, monkeypatch):
    sent = []
    monkeypatch.setattr(R, "_REGISTRY_PATH", _reg(tmp_path, ATLAS_YAML))
    monkeypatch.setattr(R, "_STATE_PATH", tmp_path / "watchdog_state.json")
    monkeypatch.setattr(R, "_broadcast", lambda events, title: sent.append(events))
    monkeypatch.delenv("ATLAS_ENABLED", raising=False)
    monkeypatch.setattr(R, "_data_dir", lambda: tmp_path)
    (tmp_path / "portfolio").mkdir()
    (tmp_path / "portfolio" / "primary").mkdir()

    now = datetime(2026, 8, 15, 6, 30, tzinfo=IST)
    R.run_watchdog(now=now)
    out2 = R.run_watchdog(now=now)
    assert out2["notified"] == 0 and len(sent) == 1


def test_broken_registry_alerts_instead_of_raising(tmp_path, monkeypatch):
    sent = []
    monkeypatch.setattr(R, "_REGISTRY_PATH", _reg(tmp_path, "milestones: [{id: x}]"))
    monkeypatch.setattr(R, "_STATE_PATH", tmp_path / "watchdog_state.json")
    monkeypatch.setattr(R, "_broadcast", lambda events, title: sent.append(events))
    out = R.run_watchdog(now=datetime(2026, 8, 15, 6, 30, tzinfo=IST))
    assert out["evaluated"] == 0
    assert sent and sent[0][0].severity == "critical"
    assert "registry" in sent[0][0].message.lower()


def test_delivery_failure_does_not_raise(tmp_path, monkeypatch):
    monkeypatch.setattr(R, "_REGISTRY_PATH", _reg(tmp_path, ATLAS_YAML))
    monkeypatch.setattr(R, "_STATE_PATH", tmp_path / "watchdog_state.json")
    monkeypatch.setattr(R, "_broadcast",
                        lambda events, title: (_ for _ in ()).throw(RuntimeError("smtp down")))
    monkeypatch.delenv("ATLAS_ENABLED", raising=False)
    monkeypatch.setattr(R, "_data_dir", lambda: tmp_path)
    (tmp_path / "portfolio").mkdir()
    (tmp_path / "portfolio" / "primary").mkdir()
    out = R.run_watchdog(now=datetime(2026, 8, 15, 6, 30, tzinfo=IST))
    assert out["notified"] == 0            # send failed, but no exception


def test_state_not_advanced_when_send_fails(tmp_path, monkeypatch):
    """A dropped notification must be retried tomorrow, not marked as sent."""
    monkeypatch.setattr(R, "_REGISTRY_PATH", _reg(tmp_path, ATLAS_YAML))
    monkeypatch.setattr(R, "_STATE_PATH", tmp_path / "watchdog_state.json")
    monkeypatch.setattr(R, "_broadcast",
                        lambda events, title: (_ for _ in ()).throw(RuntimeError("down")))
    monkeypatch.delenv("ATLAS_ENABLED", raising=False)
    monkeypatch.setattr(R, "_data_dir", lambda: tmp_path)
    (tmp_path / "portfolio").mkdir()
    (tmp_path / "portfolio" / "primary").mkdir()
    now = datetime(2026, 8, 15, 6, 30, tzinfo=IST)
    R.run_watchdog(now=now)
    sent = []
    monkeypatch.setattr(R, "_broadcast", lambda events, title: sent.append(events))
    out = R.run_watchdog(now=now)
    assert out["notified"] == 1 and sent
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/ops/test_watchdog_runner.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.ops.watchdog.runner'`

- [ ] **Step 3: Implement runner.py**

```python
"""Watchdog runner — wires registry + checks + engine to state and delivery.

Never raises: this is called from a scheduled job.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from core.ops.watchdog import checks as checks_mod
from core.ops.watchdog.engine import Notification, evaluate
from core.ops.watchdog.registry import RegistryError, load_registry

logger = logging.getLogger(__name__)

IST = ZoneInfo("Asia/Kolkata")
_REGISTRY_PATH = Path("config/milestones.yaml")
_STATE_PATH = Path("data") / "watchdog_state.json"


def _data_dir() -> Path:
    return checks_mod._DATA_DIR


def _broadcast(events, title: str) -> None:
    from core.delivery.alerts import emit_alerts_broadcast
    emit_alerts_broadcast(events, title=title)


def _load_state() -> dict:
    try:
        return json.loads(_STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(state: dict) -> None:
    try:
        from core.utils.atomic_io import atomic_write_json
        atomic_write_json(_STATE_PATH, state, indent=None)
    except Exception as exc:
        logger.warning("[watchdog] state write failed (non-fatal): %s", exc)


def _as_events(notes: list[Notification], today: date):
    from core.delivery.alerts import AlertEvent
    return [AlertEvent(date=today.isoformat(),
                       kind=f"watchdog_{n.milestone_id}_{n.level}",
                       symbol="", message=f"{n.title}\n\n{n.body}",
                       severity=n.severity)
            for n in notes]


def _alert_registry_broken(detail: str, today: date) -> None:
    from core.delivery.alerts import AlertEvent
    try:
        _broadcast([AlertEvent(
            date=today.isoformat(), kind="watchdog_registry_broken", symbol="",
            message=("The watchdog registry could not be loaded, so NOTHING is "
                     f"being watched: {detail}"),
            severity="critical")], "StockAgent ops alert")
    except Exception as exc:
        logger.warning("[watchdog] registry alert failed: %s", exc)


def run_watchdog(now: datetime | None = None) -> dict:
    """Evaluate every entry and notify on transitions. Never raises."""
    now = now or datetime.now(IST)
    today = now.date()
    try:
        entries = load_registry(_REGISTRY_PATH)
    except RegistryError as exc:
        logger.error("[watchdog] registry load failed: %s", exc)
        _alert_registry_broken(str(exc), today)
        return {"evaluated": 0, "notified": 0, "levels": []}

    results = {e.id: checks_mod.run_check(e.check) for e in entries}
    notes, new_state = evaluate(entries, results, now, _load_state())

    if not notes:
        _save_state(new_state)
        return {"evaluated": len(entries), "notified": 0, "levels": []}

    try:
        _broadcast(_as_events(notes, today), "StockAgent ops alert")
    except Exception as exc:
        # Do NOT advance state: an undelivered notification must be retried
        # tomorrow, not silently marked as sent.
        logger.warning("[watchdog] delivery failed, state not advanced: %s", exc)
        return {"evaluated": len(entries), "notified": 0, "levels": []}

    _save_state(new_state)
    return {"evaluated": len(entries), "notified": len(notes),
            "levels": [n.level for n in notes]}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/ops/test_watchdog_runner.py -q`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add core/ops/watchdog/runner.py tests/unit/ops/test_watchdog_runner.py
git commit -m "feat(watchdog): runner with state persistence and alert delivery"
```

---

### Task 5: Scheduler job — 06:30 IST daily  ← **MINIMUM SHIPPABLE FOR 8/15**

**Files:**
- Modify: `services/scheduler/python/scheduler.py` (add job registration after the `audit_nightly` block ending ~line 480; add `_watchdog_job` method near `_audit_nightly_job` ~line 966)
- Modify: `config.yaml` (add the `watchdog:` section)
- Test: `tests/unit/ops/test_watchdog_job.py`

**Interfaces:**
- Consumes: `run_watchdog` (T4).
- Produces: scheduler job id `ops_watchdog`; method `StockAgentScheduler._watchdog_job()`.

- [ ] **Step 1: Add config**

In `config.yaml`, immediately after the `analyse:` block:

```yaml
watchdog:
  enabled: true                  # master gate for the ops_watchdog job
  prep_enabled: true             # auto-run safe, idempotent prep (Task 6)
  hour: 6                        # IST. Deliberately NOT the 23:xx cluster:
  minute: 30                     #   "your window is open today" at 23:45 is useless
```

- [ ] **Step 2: Write the failing test**

```python
# tests/unit/ops/test_watchdog_job.py
from unittest.mock import patch

from services.scheduler.python.scheduler import AutomobileScheduler


def test_job_registered_at_0630_ist():
    sched = AutomobileScheduler()._build_scheduler()
    job = sched.get_job("ops_watchdog")
    assert job is not None
    fields = {f.name: str(f) for f in job.trigger.fields}
    assert fields["hour"] == "6" and fields["minute"] == "30"


def test_job_never_raises_even_if_runner_explodes():
    with patch("core.ops.watchdog.runner.run_watchdog",
               side_effect=RuntimeError("boom")):
        AutomobileScheduler()._watchdog_job()      # must not raise
```

**Verified:** the class is `AutomobileScheduler` (a legacy name — it drives all
sectors) and the builder is `_build_scheduler()`, at
`services/scheduler/python/scheduler.py:115` and `:128`. If
`AutomobileScheduler()` requires constructor arguments, mirror how
`tests/contract/test_scheduler.py` builds it.

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/unit/ops/test_watchdog_job.py -q`
Expected: FAIL — `get_job("ops_watchdog")` returns `None`

- [ ] **Step 4: Register the job**

In `services/scheduler/python/scheduler.py`, after the `audit_nightly`
registration block (the `else: logger.info("[Scheduler] Audit job disabled...")`
around line 480) and before `return scheduler`:

```python
        # ── Operational watchdog (06:30 IST daily) ──────────────────────────
        # Deliberately early and NOT in the 23:xx cluster: a "your window is
        # open today" notice delivered at 23:45 has already wasted the day.
        if cfg("watchdog.enabled", fallback=True):
            scheduler.add_job(
                func=self._watchdog_job,
                trigger=CronTrigger(hour=int(cfg("watchdog.hour", fallback=6)),
                                    minute=int(cfg("watchdog.minute", fallback=30)),
                                    timezone="Asia/Kolkata"),
                id="ops_watchdog",
                name="Operational watchdog (milestones + invariants)",
                misfire_grace_time=6 * 3600,
                coalesce=True,
                replace_existing=True,
            )
            logger.info("[Scheduler] Watchdog job: daily at 6:30 am IST")
        else:
            logger.info("[Scheduler] Watchdog job disabled (watchdog.enabled=false)")
```

Add the method next to `_audit_nightly_job`:

```python
    def _watchdog_job(self) -> None:
        """Evaluate milestones + invariants and notify on transitions.

        Never raises: the watchdog must not take down the scheduler it shares
        a process with.
        """
        _job_banner("Operational watchdog")
        try:
            from core.ops.watchdog.runner import run_watchdog
            out = run_watchdog()
            logger.info("[Scheduler] watchdog evaluated=%s notified=%s levels=%s",
                        out["evaluated"], out["notified"], out["levels"])
        except Exception as exc:
            logger.error("[Scheduler] watchdog FAILED: %s", exc, exc_info=True)
        _job_banner("Operational watchdog", done=True)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/unit/ops/test_watchdog_job.py -q`
Expected: 2 passed

- [ ] **Step 6: Run the whole suite**

Run: `python -m pytest tests/ -q -p no:randomly`
Expected: no new failures vs the 2525/12 baseline

- [ ] **Step 7: Commit**

```bash
git add services/scheduler/python/scheduler.py config.yaml tests/unit/ops/test_watchdog_job.py
git commit -m "feat(watchdog): daily 06:30 IST scheduler job"
```

**STOP AND DEPLOY.** This is the deadline-critical point: from here the
watchdog will warn about Atlas C11 on Wed 8/12 and Sat 8/15. Push to main,
confirm the deploy, then continue with Task 6.

---

### Task 6: Prep — auto-run the safe Atlas preparation

**Files:**
- Create: `core/ops/watchdog/prep.py`
- Modify: `core/ops/watchdog/runner.py` (call prep before composing notifications)
- Test: `tests/unit/ops/test_watchdog_prep.py`

**Interfaces:**
- Consumes: `CheckResult` (T2), `Milestone` (T1).
- Produces: `PrepResult`, `@prep(name)` decorator, `run_prep(name) -> PrepResult`, `PREPS: dict`. Registered prep `atlas_cutover_prep`.

```python
@dataclass(frozen=True)
class PrepResult:
    ok: bool
    transcript: list[str]
```

Prep runs **only** when: `cfg("watchdog.prep_enabled")` is true, the entry names a prep, the check state is `pending` (never `blocked`), and the window is open. Its transcript is appended to the notification body.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/ops/test_watchdog_prep.py
import pytest
from core.ops.watchdog import prep as P


def test_run_prep_unknown_name_is_not_ok():
    r = P.run_prep("nope")
    assert r.ok is False and "not registered" in r.transcript[0]


def test_run_prep_swallows_exception():
    @P.prep("boom_prep_test")
    def _b():
        raise RuntimeError("kaboom")
    try:
        r = P.run_prep("boom_prep_test")
        assert r.ok is False and any("kaboom" in t for t in r.transcript)
    finally:
        P.PREPS.pop("boom_prep_test", None)


class TestAtlasPrep:
    def test_dry_run_then_real_etl_reported(self, monkeypatch):
        calls = []

        def fake_run_etl(**kw):
            calls.append(kw)
            return {"users": 1, "instruments": 12, "verdicts": 1191}

        monkeypatch.setattr(P, "_run_etl", fake_run_etl)
        r = P.run_prep("atlas_cutover_prep")
        assert r.ok is True
        assert calls[0]["dry_run"] is True and calls[1]["dry_run"] is False
        assert any("1191" in line for line in r.transcript)

    def test_aborts_before_real_etl_when_dry_run_fails(self, monkeypatch):
        def fake_run_etl(**kw):
            if kw.get("dry_run"):
                raise RuntimeError("source db unreadable")
            pytest.fail("must not run the real ETL after a failed dry run")

        monkeypatch.setattr(P, "_run_etl", fake_run_etl)
        r = P.run_prep("atlas_cutover_prep")
        assert r.ok is False
        assert any("unreadable" in line for line in r.transcript)

    def test_never_sets_the_flag(self, monkeypatch):
        monkeypatch.setattr(P, "_run_etl", lambda **kw: {"users": 1})
        monkeypatch.delenv("ATLAS_ENABLED", raising=False)
        P.run_prep("atlas_cutover_prep")
        import os
        assert os.getenv("ATLAS_ENABLED") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/ops/test_watchdog_prep.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.ops.watchdog.prep'`

- [ ] **Step 3: Implement prep.py**

```python
"""Watchdog prep — safe, idempotent preparation run automatically.

Prep NEVER performs the irreversible step. For Atlas C11 it runs the ETL
dry-run, then the real ETL, and stops: flipping ATLAS_ENABLED stays human
(see spec section 9).
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
    def _wrap(fn: Callable[[], PrepResult]) -> Callable[[], PrepResult]:
        if name in PREPS:
            raise ValueError(f"prep {name!r} already registered")
        PREPS[name] = fn
        return fn
    return _wrap


def run_prep(name: str) -> PrepResult:
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
```

- [ ] **Step 4: Wire prep into the runner**

In `core/ops/watchdog/runner.py`, replace the `results = {...}` line with:

```python
    results = {e.id: checks_mod.run_check(e.check) for e in entries}
    prep_notes = _run_preps(entries, results, today)
```

and add, above `run_watchdog`:

```python
def _run_preps(entries, results, today) -> dict[str, list[str]]:
    """Run each due entry's prep. Returns id -> transcript lines."""
    from backend.shared.config.settings.loader import cfg
    if not cfg("watchdog.prep_enabled", fallback=True):
        return {}
    from core.ops.watchdog.prep import run_prep
    out: dict[str, list[str]] = {}
    for entry in entries:
        if not entry.prep:
            continue
        result = results.get(entry.id)
        if result is None or result.state != "pending":
            continue                     # never prep a blocked/unknown entry
        if entry.window is not None and not entry.window.is_open(today):
            continue
        out[entry.id] = run_prep(entry.prep).transcript
    return out
```

Then append transcripts when building events — change `_as_events` to accept
them:

```python
def _as_events(notes, today, preps: dict[str, list[str]] | None = None):
    from core.delivery.alerts import AlertEvent
    preps = preps or {}
    events = []
    for n in notes:
        body = n.body
        lines = preps.get(n.milestone_id)
        if lines:
            body += "\n\nAutomatic prep:\n" + "\n".join(f"  - {l}" for l in lines)
        events.append(AlertEvent(date=today.isoformat(),
                                 kind=f"watchdog_{n.milestone_id}_{n.level}",
                                 symbol="", message=f"{n.title}\n\n{body}",
                                 severity=n.severity))
    return events
```

and pass it at the call site: `_broadcast(_as_events(notes, today, prep_notes), "StockAgent ops alert")`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/unit/ops/ -q`
Expected: all pass (prep 6 + earlier tasks)

- [ ] **Step 6: Commit**

```bash
git add core/ops/watchdog/prep.py core/ops/watchdog/runner.py tests/unit/ops/test_watchdog_prep.py
git commit -m "feat(watchdog): auto-run safe Atlas prep and report it in the alert"
```

---

### Task 7: Remaining checks + registry entries

**Files:**
- Modify: `core/ops/watchdog/checks.py`
- Modify: `config/milestones.yaml`
- Test: `tests/unit/ops/test_watchdog_checks_more.py`

**Interfaces:**
- Consumes: `check`, `CheckResult` (T2).
- Produces registered checks: `deploy_matches_origin`, `serper_counter_current_month`, `monthly_scorecard_written`, `audit_graded_when_due`, `trading_days_elapsed` (parameterised via closures for F2/F3/hard-bind).

**Why `audit_graded_when_due` is not redundant:** the nightly already calls
`alert_job_partial_output("audit_nightly", produced, expected)`, but that
helper returns early when `expected <= 0`. In the 2026-08-07 incident
`graded=0` **and** `skipped_unpriceable=0`, so `expected` was 0 and **no alert
fired** — which is exactly why 0/119 went unnoticed. This check closes that
hole by comparing against rows that have actually matured.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/ops/test_watchdog_checks_more.py
import json
from datetime import date

from core.ops.watchdog import checks as C


class TestDeployMatchesOrigin:
    def test_satisfied_when_sha_matches(self, monkeypatch):
        monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", "abc123def456")
        monkeypatch.setattr(C, "_github_head_sha", lambda: "abc123def456")
        r = C.run_check("deploy_matches_origin")
        assert r.state == "satisfied"

    def test_pending_when_prod_is_behind(self, monkeypatch):
        monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", "aaaaaaa")
        monkeypatch.setattr(C, "_github_head_sha", lambda: "bbbbbbb")
        r = C.run_check("deploy_matches_origin")
        assert r.state == "pending"
        assert "aaaaaaa"[:7] in r.detail

    def test_unknown_when_sha_unavailable(self, monkeypatch):
        monkeypatch.delenv("RAILWAY_GIT_COMMIT_SHA", raising=False)
        monkeypatch.setattr(C, "_github_head_sha", lambda: "bbbbbbb")
        r = C.run_check("deploy_matches_origin")
        assert r.state == "unknown"


class TestSerperRollover:
    def test_satisfied_when_month_current(self, monkeypatch):
        monkeypatch.setattr(C, "_api_usage", lambda: {"month": date.today().strftime("%Y-%m")})
        assert C.run_check("serper_counter_current_month").state == "satisfied"

    def test_pending_when_month_stale(self, monkeypatch):
        monkeypatch.setattr(C, "_api_usage", lambda: {"month": "2020-01"})
        r = C.run_check("serper_counter_current_month")
        assert r.state == "pending" and "2020-01" in r.detail


class TestScorecardWritten:
    def test_satisfied_when_previous_month_file_exists(self, monkeypatch, tmp_path):
        monkeypatch.setattr(C, "_scorecard_dir", lambda: tmp_path)
        monkeypatch.setattr(C, "_today", lambda: date(2026, 9, 3))
        (tmp_path / "2026-08_scorecard.json").write_text("{}")
        assert C.run_check("monthly_scorecard_written").state == "satisfied"

    def test_pending_when_missing(self, monkeypatch, tmp_path):
        monkeypatch.setattr(C, "_scorecard_dir", lambda: tmp_path)
        monkeypatch.setattr(C, "_today", lambda: date(2026, 9, 3))
        r = C.run_check("monthly_scorecard_written")
        assert r.state == "pending" and "2026-08" in r.detail


class TestAuditGradedWhenDue:
    def test_pending_when_rows_matured_but_none_graded(self, monkeypatch):
        monkeypatch.setattr(C, "_audit_counts", lambda: {"matured": 119, "graded": 0})
        r = C.run_check("audit_graded_when_due")
        assert r.state == "pending"
        assert "119" in r.detail

    def test_satisfied_when_nothing_matured(self, monkeypatch):
        monkeypatch.setattr(C, "_audit_counts", lambda: {"matured": 0, "graded": 0})
        assert C.run_check("audit_graded_when_due").state == "satisfied"

    def test_satisfied_when_graded(self, monkeypatch):
        monkeypatch.setattr(C, "_audit_counts", lambda: {"matured": 10, "graded": 10})
        assert C.run_check("audit_graded_when_due").state == "satisfied"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/ops/test_watchdog_checks_more.py -q`
Expected: FAIL — checks not registered

- [ ] **Step 3: Append the checks to `core/ops/watchdog/checks.py`**

```python
import json
import urllib.request
from datetime import date, timedelta

_GITHUB_REPO = "RevanParimi/StockAgent"       # verified via `git remote get-url origin`


def _today() -> date:
    from zoneinfo import ZoneInfo
    from datetime import datetime
    return datetime.now(ZoneInfo("Asia/Kolkata")).date()


def _github_head_sha() -> str | None:
    """origin/main HEAD via the GitHub API. Returns None when unavailable."""
    token = os.getenv("GITHUB_TOKEN") or ""
    req = urllib.request.Request(
        f"https://api.github.com/repos/{_GITHUB_REPO}/commits/main",
        headers={"Accept": "application/vnd.github+json",
                 **({"Authorization": f"Bearer {token}"} if token else {})})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read()).get("sha")


@check("deploy_matches_origin")
def deploy_matches_origin() -> CheckResult:
    """Prod running behind origin/main means a newly added milestone has not
    reached the watchdog yet — the one way this design silently goes stale."""
    running = (os.getenv("RAILWAY_GIT_COMMIT_SHA") or "").strip()
    if not running:
        return CheckResult("unknown", "RAILWAY_GIT_COMMIT_SHA is not set.")
    head = _github_head_sha()
    if not head:
        return CheckResult("unknown", "Could not read origin/main HEAD.")
    if running.lower().startswith(head.lower()[:7]) or \
            head.lower().startswith(running.lower()[:7]):
        return CheckResult("satisfied", f"Prod is at origin/main ({head[:7]}).",
                           {"running": running[:7], "head": head[:7]})
    return CheckResult(
        "pending",
        f"Prod is running {running[:7]} but origin/main is {head[:7]} — "
        "deploy, or the watchdog is working from a stale registry.",
        {"running": running[:7], "head": head[:7]})


def _api_usage() -> dict:
    from services.data.stores.api_usage import get_usage
    return get_usage()


@check("serper_counter_current_month")
def serper_counter_current_month() -> CheckResult:
    usage = _api_usage()
    month = str(usage.get("month") or "")
    expected = _today().strftime("%Y-%m")
    if month == expected:
        return CheckResult("satisfied", f"Counter is on {month}.", {"month": month})
    return CheckResult(
        "pending",
        f"API usage counter still reads {month!r}, expected {expected!r} — "
        "the monthly rollover did not happen.", {"month": month})


def _scorecard_dir():
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
    return CheckResult("pending",
                       f"{prev} scorecard is missing at {path}.",
                       {"path": str(path)})


_AUDIT_RUN_PATH = _DATA_DIR / "audit_last_run.json"


def _audit_counts() -> dict:
    """Last nightly grading summary, persisted by the audit job (Step 3b)."""
    return json.loads(_AUDIT_RUN_PATH.read_text(encoding="utf-8"))


@check("audit_graded_when_due")
def audit_graded_when_due() -> CheckResult:
    """Closes the hole in alert_job_partial_output, which returns early when
    expected <= 0. On 2026-08-07 graded=0 AND skipped_unpriceable=0, so
    expected was 0 and NO alert fired for a 0/119 grading run.

    Two failure modes, both invisible today:
      1. the nightly stopped running at all (stale summary), and
      2. it ran and produced nothing while having work to do.
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
```

- [ ] **Step 3b: Persist the nightly summary so the check has something to read**

`AuditOutcomeStore` holds only rows that were *already graded*, so "matured but
ungraded" cannot be derived from it. The nightly job already computes the
numbers and then discards them. In `services/scheduler/python/scheduler.py`,
inside `_audit_nightly_job`, immediately after the existing
`alert_job_partial_output("audit_nightly", produced, expected)` call:

```python
            # Persist the run summary so the watchdog can tell "graded nothing
            # because there was nothing to do" from "graded nothing because it
            # is broken" — alert_job_partial_output cannot, since it returns
            # early when expected == 0 (the 2026-08-07 0/119 blind spot).
            try:
                from core.audit.store import AuditOutcomeStore
                from core.utils.atomic_io import atomic_write_json
                atomic_write_json(Path("data") / "audit_last_run.json", {
                    "date": _d.today().isoformat(),
                    "graded": produced,
                    "already_present": int(summary.get("already_present", 0)),
                    "skipped_unpriceable": int(summary.get("skipped_unpriceable", 0)),
                    "pending_rows": len(AuditOutcomeStore().load_all()),
                }, indent=None)
            except Exception as exc:
                logger.warning("[Scheduler] audit summary persist failed: %s", exc)
```

Add a test in `tests/unit/ops/test_watchdog_checks_more.py`:

```python
    def test_pending_when_nightly_has_gone_stale(self, monkeypatch, tmp_path):
        p = tmp_path / "audit_last_run.json"
        p.write_text(json.dumps({"date": "2026-01-01", "graded": 5,
                                 "already_present": 0, "pending_rows": 5}))
        monkeypatch.setattr(C, "_AUDIT_RUN_PATH", p)
        monkeypatch.setattr(C, "_today", lambda: date(2026, 8, 10))
        r = C.run_check("audit_graded_when_due")
        assert r.state == "pending" and "stopped running" in r.detail

    def test_pending_when_no_summary_file_yet(self, monkeypatch, tmp_path):
        monkeypatch.setattr(C, "_AUDIT_RUN_PATH", tmp_path / "absent.json")
        assert C.run_check("audit_graded_when_due").state == "pending"
```

Update the three `_audit_counts` tests above to patch `C._AUDIT_RUN_PATH` with
a written file rather than patching `_audit_counts` directly, so the freshness
branch is genuinely exercised.

- [ ] **Step 4: Add the registry entries**

Replace `invariants: []` in `config/milestones.yaml`:

```yaml
invariants:
  - id: deploy_matches_origin
    kind: invariant
    title: "Prod is running origin/main"
    check: deploy_matches_origin
    action: "Push and/or redeploy — until then the watchdog reads a stale registry."

  - id: serper_month_rollover
    kind: invariant
    title: "Serper quota counter rolled into the current month"
    check: serper_counter_current_month
    schedule: monthly
    action: "Inspect data/logs/api_usage.json on the volume."

  - id: monthly_scorecard_written
    kind: invariant
    title: "Previous month's RL scorecard was written"
    check: monthly_scorecard_written
    schedule: monthly
    action: "Check the 1st-of-month scorecard job ran; rebuild with core.audit.cli if not."

  - id: audit_graded_when_due
    kind: invariant
    title: "Auditor grades rows once they mature"
    check: audit_graded_when_due
    action: >
      Matured rows are not being graded. Check the ^NSEI benchmark fetch
      (the 2026-08-07 failure mode) before trusting any audit verdict.
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/unit/ops/ -q`
Expected: all pass

- [ ] **Step 6: Verify the full registry still parses**

Run: `python -c "from core.ops.watchdog.registry import load_registry; print(len(load_registry()), 'entries')"`
Expected: `5 entries`

- [ ] **Step 7: Commit**

```bash
git add core/ops/watchdog/checks.py config/milestones.yaml tests/unit/ops/test_watchdog_checks_more.py
git commit -m "feat(watchdog): deploy-drift, quota rollover, scorecard and audit-grading invariants"
```

---

### Task 8: Weekly heartbeat

**Files:**
- Modify: `core/ops/watchdog/runner.py`
- Test: `tests/unit/ops/test_watchdog_heartbeat.py`

**Interfaces:**
- Consumes: `run_watchdog` internals (T4).
- Produces: `build_heartbeat(entries, results, now) -> str`; `run_watchdog` sends it on Sundays via `send_email` only.

Email-only on purpose: a push notification that says "all clear" trains the
user to dismiss push. Its job is liveness — **no heartbeat on Sunday means the
watchdog is dead** (spec §7).

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/ops/test_watchdog_heartbeat.py
from datetime import datetime
from zoneinfo import ZoneInfo

from core.ops.watchdog import runner as R
from core.ops.watchdog.checks import CheckResult
from core.ops.watchdog.registry import Milestone

IST = ZoneInfo("Asia/Kolkata")


def _entries():
    return [Milestone(id="a", kind="milestone", title="Atlas", check="c1"),
            Milestone(id="b", kind="invariant", title="Deploy", check="c2")]


def test_heartbeat_lists_every_entry_and_state():
    results = {"a": CheckResult("pending", "not done"),
               "b": CheckResult("satisfied", "in sync")}
    text = R.build_heartbeat(_entries(), results,
                             datetime(2026, 8, 16, 6, 30, tzinfo=IST))
    assert "Atlas" in text and "Deploy" in text
    assert "pending" in text and "satisfied" in text


def test_heartbeat_sent_on_sunday_only(tmp_path, monkeypatch):
    emails = []
    monkeypatch.setattr(R, "_REGISTRY_PATH", tmp_path / "m.yaml")
    (tmp_path / "m.yaml").write_text(
        "milestones:\n  - {id: a, kind: milestone, title: A, check: atlas_cutover_pending}\n")
    monkeypatch.setattr(R, "_STATE_PATH", tmp_path / "s.json")
    monkeypatch.setattr(R, "_broadcast", lambda e, title: None)
    monkeypatch.setattr(R, "_send_email", lambda subject, body: emails.append(subject))
    monkeypatch.setenv("ATLAS_ENABLED", "true")          # satisfied -> silent

    R.run_watchdog(now=datetime(2026, 8, 15, 6, 30, tzinfo=IST))   # Saturday
    assert emails == []
    R.run_watchdog(now=datetime(2026, 8, 16, 6, 30, tzinfo=IST))   # Sunday
    assert len(emails) == 1 and "heartbeat" in emails[0].lower()


def test_heartbeat_failure_does_not_break_the_run(tmp_path, monkeypatch):
    monkeypatch.setattr(R, "_REGISTRY_PATH", tmp_path / "m.yaml")
    (tmp_path / "m.yaml").write_text(
        "milestones:\n  - {id: a, kind: milestone, title: A, check: atlas_cutover_pending}\n")
    monkeypatch.setattr(R, "_STATE_PATH", tmp_path / "s.json")
    monkeypatch.setattr(R, "_broadcast", lambda e, title: None)
    monkeypatch.setattr(R, "_send_email",
                        lambda s, b: (_ for _ in ()).throw(RuntimeError("smtp")))
    monkeypatch.setenv("ATLAS_ENABLED", "true")
    out = R.run_watchdog(now=datetime(2026, 8, 16, 6, 30, tzinfo=IST))
    assert out["evaluated"] == 1        # no exception
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/ops/test_watchdog_heartbeat.py -q`
Expected: FAIL — `AttributeError: module ... has no attribute 'build_heartbeat'`

- [ ] **Step 3: Implement in runner.py**

```python
def _send_email(subject: str, body: str) -> None:
    from core.delivery.channels import send_email
    send_email(subject, body)


def build_heartbeat(entries, results, now) -> str:
    """Liveness digest: everything tracked and its current state."""
    lines = [f"Watchdog heartbeat — {now.strftime('%Y-%m-%d %H:%M')} IST",
             f"{len(entries)} entr(ies) tracked.", ""]
    for e in entries:
        r = results.get(e.id)
        state = r.state if r else "unknown"
        detail = r.detail if r else "no result"
        lines.append(f"  [{state:<9}] {e.title} — {detail}")
    lines += ["", "Silence on any other day means nothing was due."]
    return "\n".join(lines)
```

Then at the end of `run_watchdog`, before each `return`, send the heartbeat on
Sundays. Simplest correct shape — restructure `run_watchdog` so all exits pass
through one place:

```python
    # ... after notification handling, before returning:
    if now.weekday() == 6:              # Sunday
        try:
            _send_email("StockAgent watchdog heartbeat",
                        build_heartbeat(entries, results, now))
        except Exception as exc:
            logger.warning("[watchdog] heartbeat send failed: %s", exc)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/ops/ -q`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add core/ops/watchdog/runner.py tests/unit/ops/test_watchdog_heartbeat.py
git commit -m "feat(watchdog): weekly Sunday heartbeat as liveness proof"
```

---

### Task 9: Migrate memory + document the registry

**Files:**
- Modify: `CODEBASE.md` (scheduled-jobs table + config table)
- Modify: `C:\Users\RevanParimi\.claude\projects\c--Users-RevanParimi-OneDrive---IBM-Documents-Gen-AI-Projects-StockAgent-main\memory\MEMORY.md`
- Modify: the relevant `project_*.md` memory files
- Test: none (documentation)

Without this the design fails decision D4: two lists that drift, with the
drift invisible until something is missed again.

- [ ] **Step 1: Document the job in CODEBASE.md**

Add to the scheduled-jobs table:

```markdown
| `ops_watchdog` | 06:30 IST daily | Evaluates `config/milestones.yaml` — dated milestones and standing invariants — and notifies on transitions. Auto-runs safe prep. Sunday run also emails a heartbeat; **no Sunday heartbeat means the watchdog is dead**. |
```

Add to the config table:

```markdown
| `watchdog.enabled` | `true` | Master gate for the ops_watchdog job. **`config.yaml` only — no env override.** |
| `watchdog.prep_enabled` | `true` | Auto-run idempotent prep (e.g. the Atlas ETL) when a window is open. Set false for notify-only. |
```

- [ ] **Step 2: Repoint the memory index**

In `MEMORY.md`, change the Roadmap line so it no longer carries dates:

```markdown
- [Roadmap](project_roadmap.md) — cross-program roadmap. **Dated milestones and
  standing invariants now live in `config/milestones.yaml` in the repo, which
  the prod `ops_watchdog` job reads at 06:30 IST daily — that file is
  authoritative, not this one.** Read on "what's next" / "roadmap"
```

- [ ] **Step 3: Strip dates from the project memory files**

In `project_roadmap.md`, `project_user_data_program.md`, and
`project_intelligence_loop_audit.md`, replace each date-bound "due / checkpoint
/ window" claim with a pointer to `config/milestones.yaml`. Keep all narrative
and rationale — only the *dates* move, because those are what prod must act on.

Add a new memory file `project_operational_watchdog.md` describing the
watchdog, and index it in `MEMORY.md`.

- [ ] **Step 4: Add the remaining dated milestones to the registry**

Append to `config/milestones.yaml` under `milestones:` — one entry per
checkpoint currently living only in memory (F2 ≈ 2026-08-28, F3 ≈ 2026-09-04,
hard-bind observation). Each needs a `check`; where no programmatic check
exists yet, use `deadline` with a check that returns `pending` until the
human marks it done by removing the entry. Register that helper explicitly:

```python
@check("manual_confirmation")
def manual_confirmation() -> CheckResult:
    """No programmatic signal exists; stays pending until the entry is removed
    from the registry. Deliberately dumb — a date-only reminder."""
    return CheckResult("pending", "Awaiting manual confirmation.")
```

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest tests/ -q -p no:randomly`
Expected: no new failures vs the 2525/12 baseline

- [ ] **Step 6: Commit**

```bash
git add CODEBASE.md config/milestones.yaml core/ops/watchdog/checks.py
git commit -m "docs(watchdog): registry becomes the source of truth for dated milestones"
```

---

## Self-review notes

**Spec coverage.** §4 architecture → T1–T5. §5 registry → T1. §6 checks and the
four states → T2, T7. §7 ladder and heartbeat → T3, T8. §8 prep → T6. §10
scheduling → T5. §11 testing → every task is TDD. §12 memory migration → T9.
§13 limitation 1 (registry reaches prod only on deploy) → the
`deploy_matches_origin` check in T7.

**API verification (all four resolved against real code, not guessed):**

| Assumption | Outcome |
|---|---|
| `settings.SCORECARD_DIR` | ✅ exists — `base.py:758`, default `data/eval/scorecards` |
| Scheduler constructor | ⚠️ **corrected** — `AutomobileScheduler._build_scheduler()`, not `StockAgentScheduler().build()` |
| GitHub repo slug | ⚠️ **corrected** — `RevanParimi/StockAgent` |
| `build_report()["matured_total"]` | ❌ **does not exist.** `build_report` returns `total_rows`, `min_n`, `verdict`, `hit_rate[h].n`, … and `AuditOutcomeStore` holds only *already-graded* rows, so maturity cannot be derived from it. Redesigned: the nightly persists its own summary (T7 Step 3b) and the check reads that. |

**Deviation from spec §6, recorded deliberately.** The spec listed
`news_blind_rate_ok` as an invariant. It is **dropped**:
`core/audit/thresholds.py` already implements `max_news_blind_rate` and the
nightly already calls `emit_breaches`, so a watchdog copy would be a second
implementation of a live rule. `audit_graded_when_due` is kept because it
covers a genuinely different and currently-unalerted gap (see T7).

**Remaining risk.** T9 Step 3 edits memory files outside the repo, so it is not
covered by the test suite and cannot be reviewed in a diff. Do it last and
verify by re-reading the files.
