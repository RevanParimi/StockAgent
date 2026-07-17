# Audit Wave F — Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the Wave F polish docket from docs/audit/LEDGER.md — AUD-057 (atomic writes), AUD-013 (sent-log rotation), AUD-015 (alert audience), AUD-090d (last-run-outcome surface), AUD-091 (close_on retry), AUD-089 (equity-curve labeling), AUD-008 (/performance as_of), AUD-073 (factor_regime staleness + verify=True), AUD-072 (ablation-delta caveat), AUD-104 (one chat memory model), AUD-036 (stale docs).

**Architecture:** One shared atomic-write util (`core/utils/atomic_io.py`) consumed by every previously-non-atomic JSON writer plus two new consumers (sent-log rotation, job-outcome store). Alert emission gains a broadcast helper that fans system alerts to every push-subscribed user. Everything else is a small, local, honest-labeling fix. No behavior change to the money path except one retry in `close_on`.

**Tech Stack:** Python 3.11, pytest, FastAPI. No new dependencies.

## Global Constraints

- Branch: `audit-wave-f-polish` (in-repo branch, NOT a git worktree — OneDrive locks broke worktree cleanup in Waves C/D).
- TDD: every code task = failing test first, then minimal implementation.
- Known-failing baseline (do not fix, do not worsen): AUD-022 stale-mock failures in `test_phase0_llm_migration` / `test_orchestrator` / `test_phase2_api`, the `event_ingestor` unparseable-date test, and `test_harness` real-data tests when gitignored `data/` is absent.
- Alert-emitting tests rely on the autouse `_no_real_deliveries` conftest fixture (AUD-106) — never disable it.
- House error style: helpers that run inside jobs/pipelines never raise; log `warning`/`debug` and degrade.
- Public-repo rule: no prod host/cash/auth specifics in committed docs.
- Commit messages end with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

---

### Task 1: `core/utils/atomic_io.py` — shared temp+rename writer (AUD-057)

**Files:**
- Create: `core/utils/__init__.py` (empty)
- Create: `core/utils/atomic_io.py`
- Test: `tests/unit/test_atomic_io.py`

**Interfaces:**
- Produces: `atomic_write_text(path: str | Path, text: str, encoding: str = "utf-8") -> None` and `atomic_write_json(path: str | Path, obj, *, indent: int | None = 2, sort_keys: bool = False, ensure_ascii: bool = True) -> None`. Both create the parent dir, write to a `tempfile.mkstemp` file in the SAME directory, then `os.replace` onto the target. They RAISE on failure (callers keep their own try/except per house style).

- [ ] **Step 1: Write the failing test**

```python
"""tests/unit/test_atomic_io.py — AUD-057 shared atomic writer."""
import json
import os

import pytest

from core.utils.atomic_io import atomic_write_json, atomic_write_text


def test_atomic_write_text_roundtrip(tmp_path):
    p = tmp_path / "sub" / "out.txt"          # parent does not exist yet
    atomic_write_text(p, "hello\n")
    assert p.read_text(encoding="utf-8") == "hello\n"


def test_atomic_write_text_overwrites(tmp_path):
    p = tmp_path / "out.txt"
    atomic_write_text(p, "one")
    atomic_write_text(p, "two")
    assert p.read_text(encoding="utf-8") == "two"


def test_atomic_write_leaves_no_temp_files(tmp_path):
    p = tmp_path / "out.json"
    atomic_write_json(p, {"a": 1})
    assert [f.name for f in tmp_path.iterdir()] == ["out.json"]


def test_atomic_write_json_kwargs(tmp_path):
    p = tmp_path / "out.json"
    atomic_write_json(p, {"b": 2, "a": 1}, indent=None, sort_keys=True)
    assert p.read_text(encoding="utf-8") == '{"a": 1, "b": 2}'
    assert json.loads(p.read_text(encoding="utf-8")) == {"a": 1, "b": 2}


def test_atomic_write_failure_cleans_tmp(tmp_path, monkeypatch):
    p = tmp_path / "out.txt"
    def boom(src, dst):
        raise OSError("simulated replace failure")
    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        atomic_write_text(p, "x")
    assert list(tmp_path.iterdir()) == []     # tmp file removed, target absent
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_atomic_io.py -v`
Expected: FAIL / ERROR with `ModuleNotFoundError: No module named 'core.utils'`

- [ ] **Step 3: Write minimal implementation**

`core/utils/__init__.py`: empty file.

`core/utils/atomic_io.py`:

```python
"""
core/utils/atomic_io.py
=======================
Shared temp+rename JSON/text writer (AUD-057).

A bare `Path.write_text` can be observed half-written by the other uvicorn
worker or the scheduler thread (torn JSON -> counters silently reset). Writing
to a uniquely-named temp file in the SAME directory and `os.replace`-ing it
onto the target makes the swap atomic on both POSIX and Windows/NTFS.

Both helpers RAISE on failure — call sites keep their own try/except-degrade
per the house style.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


def atomic_write_text(path: str | Path, text: str, encoding: str = "utf-8") -> None:
    """Write `text` to `path` atomically (mkstemp in target dir + os.replace)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=path.parent, prefix=path.name + ".", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline="") as fh:
            fh.write(text)
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def atomic_write_json(
    path: str | Path,
    obj,
    *,
    indent: int | None = 2,
    sort_keys: bool = False,
    ensure_ascii: bool = True,
) -> None:
    """`json.dumps` + `atomic_write_text`."""
    atomic_write_text(
        path,
        json.dumps(obj, indent=indent, sort_keys=sort_keys, ensure_ascii=ensure_ascii),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_atomic_io.py -v`
Expected: 5 PASS

- [ ] **Step 5: Commit**

```bash
git add core/utils/__init__.py core/utils/atomic_io.py tests/unit/test_atomic_io.py
git commit -m "feat(wave-f): core/utils/atomic_io shared temp+rename writer (AUD-057)"
```

---

### Task 2: Swap the 6 non-atomic writers onto atomic_io (AUD-057)

**Files:**
- Modify: `services/data/stores/api_usage.py:70-75` (`_save`)
- Modify: `services/data/fetchers/nse_key_registry.py:117-122` (`_save_registry`)
- Modify: `core/delivery/ops_alerts.py:43-48` (`_save_state`)
- Modify: `src/backend/shared/data/fetchers/symbol_resolver.py` (3 sites: prune-write ~:165, `_persist` ~:187, `learn_company_name` ~:237)
- Modify: `core/intelligence/rl/calendar_updater.py:241`
- Test: `tests/unit/test_atomic_io_adoption.py`

**Interfaces:**
- Consumes: `core.utils.atomic_io.atomic_write_json` from Task 1.
- Produces: identical public behavior (same file contents, same JSON formatting) — only the write mechanics change.

- [ ] **Step 1: Write the failing test**

```python
"""tests/unit/test_atomic_io_adoption.py — the AUD-057 sites write via atomic_io."""
import inspect


def _uses_atomic(func) -> bool:
    src = inspect.getsource(func)
    return "atomic_write_json" in src and ".write_text(" not in src


def test_api_usage_save_is_atomic():
    from services.data.stores import api_usage
    assert _uses_atomic(api_usage._save)


def test_nse_key_registry_save_is_atomic():
    from services.data.fetchers import nse_key_registry
    assert _uses_atomic(nse_key_registry._save_registry)


def test_ops_alerts_state_save_is_atomic():
    from core.delivery import ops_alerts
    assert _uses_atomic(ops_alerts._save_state)


def test_symbol_resolver_writers_are_atomic():
    from backend.shared.data.fetchers import symbol_resolver
    assert _uses_atomic(symbol_resolver._persist)
    assert _uses_atomic(symbol_resolver.forget_symbol)
    assert _uses_atomic(symbol_resolver.learn_company_name)


def test_calendar_updater_write_is_atomic():
    import inspect
    from core.intelligence.rl import calendar_updater
    src = inspect.getsource(calendar_updater)
    assert "_HOLIDAY_FILE.write_text(" not in src
    assert "atomic_write_json" in src


def test_api_usage_roundtrip_still_works(tmp_path, monkeypatch):
    from services.data.stores import api_usage
    monkeypatch.setattr(api_usage, "_USAGE_FILE", tmp_path / "api_usage.json")
    api_usage.record_call("serper")
    usage = api_usage.get_usage()
    assert usage["serper"]["calls"] == 1
```

Note: if the prune-write site (~:165) is not inside a function named `forget_symbol`, adjust the test to the actual enclosing function name found in the file.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_atomic_io_adoption.py -v`
Expected: the `_uses_atomic` assertions FAIL (writers still use `.write_text(`)

- [ ] **Step 3: Swap the writers**

Each site keeps its existing try/except and logging; only the write line changes. Add `from core.utils.atomic_io import atomic_write_json` at each module top (symbol_resolver already imports from `core.config`, so `core` is importable there).

`services/data/stores/api_usage.py` `_save`:

```python
def _save(data: dict) -> None:
    try:
        atomic_write_json(_USAGE_FILE, data, indent=2)   # AUD-057
    except Exception as exc:
        logger.warning("[api_usage] Failed to save usage file: %s", exc)
```

(The explicit `mkdir` line can go — `atomic_write_json` creates the parent.)

`services/data/fetchers/nse_key_registry.py` `_save_registry`:

```python
def _save_registry(registry: dict) -> None:
    try:
        atomic_write_json(_REGISTRY_PATH, registry, indent=2)   # AUD-057
    except OSError as exc:
        logger.warning("[NseKeyRegistry] Could not save registry: %s", exc)
```

`core/delivery/ops_alerts.py` `_save_state`:

```python
def _save_state(state: dict) -> None:
    try:
        from core.utils.atomic_io import atomic_write_json
        atomic_write_json(_STATE_PATH, state, indent=None)   # AUD-057
    except Exception as exc:
        logger.debug("[ops_alerts] state write failed (non-fatal): %s", exc)
```

`src/backend/shared/data/fetchers/symbol_resolver.py` — all 3 write sites become (keeping each site's surrounding try/except/log lines):

```python
            atomic_write_json(_CACHE_FILE, cache, indent=2, sort_keys=True)   # AUD-057
```

```python
            atomic_write_json(
                _COMPANY_NAME_CACHE_FILE, cache, indent=2, sort_keys=True
            )   # AUD-057
```

`core/intelligence/rl/calendar_updater.py:241`:

```python
    atomic_write_json(_HOLIDAY_FILE, existing, indent=2, sort_keys=True)   # AUD-057
```

- [ ] **Step 4: Run the new test + the existing suites that cover these files**

Run: `python -m pytest tests/unit/test_atomic_io_adoption.py tests/unit/test_company_name_cache.py tests/unit/test_symbol_cache_guard.py tests/unit/intelligence/rl/test_calendar_updater.py -v` (adjust the calendar test path if it lives elsewhere; discover with `python -m pytest --collect-only -q -k calendar`).
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor(wave-f): swap 6 non-atomic JSON writers onto atomic_io (AUD-057)"
```

---

### Task 3: Sent-log rotation (AUD-013) + broadcast audience (AUD-015) in the alerts layer

**Files:**
- Modify: `core/delivery/alerts.py`
- Modify: `core/delivery/channels.py` (add `PushStore.user_ids()`)
- Test: `tests/unit/test_alerts_wave_f.py`

**Interfaces:**
- Consumes: `atomic_write_text` from Task 1.
- Produces: `PushStore.user_ids() -> list[str]`; `alert_audience() -> list[str]`; `emit_alerts_broadcast(events: list[AlertEvent], title: str = "StockAgent alerts", sent_log: str | None = None) -> dict` (returns `{"users": {uid: emit_result}, "emitted": total}`). Task 4 switches call sites onto `emit_alerts_broadcast`.

- [ ] **Step 1: Write the failing test**

```python
"""tests/unit/test_alerts_wave_f.py — AUD-013 rotation + AUD-015 broadcast."""
import json

from core.delivery.alerts import (
    AlertEvent, alert_audience, emit_alerts, emit_alerts_broadcast,
)
from core.delivery.channels import PushStore


def _event(kind="test_kind", symbol="SYM"):
    return AlertEvent(date="2026-07-17", kind=kind, symbol=symbol,
                      message="msg", severity="info")


# ---- AUD-013: rotation ----

def test_sent_log_rotates_past_threshold(tmp_path):
    log = tmp_path / "alerts_sent.jsonl"
    rec = json.dumps({"date": "2026-01-01", "kind": "old", "symbol": "",
                      "user_id": "", "delivered": True})
    log.write_text("\n".join([rec] * 4001) + "\n", encoding="utf-8")
    emit_alerts([_event()], sent_log=str(log))
    lines = log.read_text(encoding="utf-8").splitlines()
    # rotated down to the keep-window plus the freshly appended record
    assert len(lines) == 2001


def test_sent_log_untouched_under_threshold(tmp_path):
    log = tmp_path / "alerts_sent.jsonl"
    rec = json.dumps({"date": "2026-01-01", "kind": "old", "symbol": "",
                      "user_id": "", "delivered": True})
    log.write_text("\n".join([rec] * 10) + "\n", encoding="utf-8")
    emit_alerts([_event()], sent_log=str(log))
    assert len(log.read_text(encoding="utf-8").splitlines()) == 11


# ---- AUD-015: audience + broadcast ----

def test_push_store_user_ids(tmp_path):
    store = PushStore(path=str(tmp_path / "subs.json"))
    store.add({"endpoint": "https://e/1"}, user_id="alice")
    store.add({"endpoint": "https://e/2"}, user_id="bob")
    assert store.user_ids() == ["alice", "bob"]


def test_alert_audience_includes_default_and_sub_users(tmp_path, monkeypatch):
    from core.config import settings
    import core.delivery.alerts as alerts_mod
    store = PushStore(path=str(tmp_path / "subs.json"))
    store.add({"endpoint": "https://e/1"}, user_id="alice")
    monkeypatch.setattr(alerts_mod, "_audience_push_store", lambda: store)
    audience = alert_audience()
    assert "alice" in audience
    assert settings.PORTFOLIO_DEFAULT_USER_ID in audience


def test_broadcast_emits_once_per_user(tmp_path, monkeypatch):
    import core.delivery.alerts as alerts_mod
    store = PushStore(path=str(tmp_path / "subs.json"))
    store.add({"endpoint": "https://e/1"}, user_id="alice")
    store.add({"endpoint": "https://e/2"}, user_id="bob")
    monkeypatch.setattr(alerts_mod, "_audience_push_store", lambda: store)
    log = tmp_path / "alerts_sent.jsonl"
    result = emit_alerts_broadcast([_event()], sent_log=str(log))
    recs = [json.loads(l) for l in log.read_text(encoding="utf-8").splitlines()]
    users = {r["user_id"] for r in recs}
    assert "alice" in users and "bob" in users
    assert result["emitted"] == len(users)   # one record per audience user
    # re-broadcast same day dedupes per user (delivered flag False in tests
    # would retry, so mark them delivered first)
```

Note: the autouse `_no_real_deliveries` fixture forces transports off, so `deliver` returns delivered=False and records are retryable — the dedupe re-broadcast assertion is intentionally left out; assert only the per-user fan-out above.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_alerts_wave_f.py -v`
Expected: FAIL with `ImportError: cannot import name 'alert_audience'`

- [ ] **Step 3: Implement**

`core/delivery/channels.py` — add inside `PushStore`:

```python
    def user_ids(self) -> list[str]:
        """All user_ids with at least one stored subscription (AUD-015)."""
        return sorted(uid for uid, subs in self._load().items() if subs)
```

`core/delivery/alerts.py` — add after `_sent_log_path`:

```python
_ROTATE_AT_LINES = 4000   # rotate when the sent-log grows past this
_ROTATE_KEEP = 2000       # keep-window; matches the _seen_keys tail


def _rotate_sent_log(path: Path) -> None:
    """AUD-013: cap unbounded sent-log growth (~10 lines/day on the volume).
    Rewrites the newest _ROTATE_KEEP lines atomically; dedupe already only
    looks at that same tail window, so rotation never changes behavior."""
    try:
        if not path.exists():
            return
        lines = path.read_text(encoding="utf-8").splitlines()
        if len(lines) <= _ROTATE_AT_LINES:
            return
        from core.utils.atomic_io import atomic_write_text
        atomic_write_text(path, "\n".join(lines[-_ROTATE_KEEP:]) + "\n")
        logger.info("[alerts] sent-log rotated: %d -> %d lines",
                    len(lines), _ROTATE_KEEP)
    except Exception as exc:
        logger.warning("[alerts] sent-log rotation failed (non-fatal): %s", exc)
```

Call it in `emit_alerts` right after `path = _sent_log_path(sent_log)`:

```python
        path = _sent_log_path(sent_log)
        _rotate_sent_log(path)   # AUD-013
```

Add at module bottom (after `emit_alerts`):

```python
def _audience_push_store():
    """Seam for tests — the default PushStore."""
    from core.delivery.channels import PushStore
    return PushStore()


def alert_audience() -> list[str]:
    """Every user who should receive SYSTEM-level alerts (AUD-015): all users
    with a push subscription, plus the default portfolio user (the email
    transport is a single global mailbox and rides the default user's emit)."""
    uids: set[str] = set()
    try:
        uids.update(_audience_push_store().user_ids())
    except Exception as exc:
        logger.warning("[alerts] audience lookup failed (non-fatal): %s", exc)
    uids.add(settings.PORTFOLIO_DEFAULT_USER_ID)
    return sorted(uids)


def emit_alerts_broadcast(
    events: list[AlertEvent],
    title: str = "StockAgent alerts",
    sent_log: str | None = None,
) -> dict:
    """emit_alerts to every alert_audience() user (AUD-015). Never raises.

    Note: with >1 audience user the single global mailbox receives one email
    per user (deliver() sends email unconditionally); acceptable at the
    current single-real-user scale, and per-user push still lands correctly.
    """
    results: dict[str, dict] = {}
    for uid in alert_audience():
        results[uid] = emit_alerts(events, user_id=uid, title=title,
                                   sent_log=sent_log)
    return {"users": results,
            "emitted": sum(r.get("emitted", 0) for r in results.values())}
```

`settings` is already imported at the top of alerts.py.

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/unit/test_alerts_wave_f.py tests/unit/test_delivery_settings.py tests/unit/test_delivery_api.py -v` (plus any existing alerts tests: discover with `-k alert`)
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/delivery/alerts.py core/delivery/channels.py tests/unit/test_alerts_wave_f.py
git commit -m "feat(wave-f): sent-log rotation (AUD-013) + broadcast alert audience (AUD-015)"
```

---

### Task 4: Switch system-alert call sites to emit_alerts_broadcast (AUD-015)

**Files:**
- Modify: `core/delivery/ops_alerts.py` (`_emit` :51-57, `alert_job_partial_output` :111-118)
- Modify: `core/delivery/index_watch.py:106`
- Modify: `core/discovery/__init__.py:87`
- Modify: `core/portfolio/store.py:126`
- Modify: `core/portfolio/reconcile.py:38`
- Test: `tests/unit/test_alerts_wave_f.py` (extend)

Leave per-user emits alone: `core/portfolio/pipeline.py:201` and `core/delivery/brief.py:277` already target the owning user correctly.

- [ ] **Step 1: Write the failing test (append to tests/unit/test_alerts_wave_f.py)**

```python
def test_system_alert_sites_broadcast():
    """The 6 system-level alert sites fan out to the whole audience (AUD-015)."""
    import inspect
    from core.delivery import ops_alerts, index_watch
    import core.discovery as discovery
    from core.portfolio import store as pstore, reconcile

    assert "emit_alerts_broadcast" in inspect.getsource(ops_alerts._emit)
    assert "emit_alerts_broadcast" in inspect.getsource(
        ops_alerts.alert_job_partial_output)
    assert "emit_alerts_broadcast" in inspect.getsource(index_watch)
    assert "emit_alerts_broadcast" in inspect.getsource(discovery)
    assert "emit_alerts_broadcast" in inspect.getsource(pstore._alert_quarantine := pstore.PortfolioStore._alert_quarantine)
    assert "emit_alerts_broadcast" in inspect.getsource(reconcile._alert)
```

(If the walrus line is awkward, split it: `src = inspect.getsource(pstore.PortfolioStore._alert_quarantine)`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_alerts_wave_f.py::test_system_alert_sites_broadcast -v`
Expected: FAIL (sites still call `emit_alerts`)

- [ ] **Step 3: Switch the call sites**

Pattern at each site — import `emit_alerts_broadcast` instead of `emit_alerts`, drop any `user_id` argument (none of these six pass one today), keep the events/title unchanged. Example, `core/delivery/ops_alerts.py` `_emit`:

```python
def _emit(kind: str, message: str) -> None:
    """One critical alert through the existing delivery layer, fanned to the
    whole alert audience (AUD-015). Never raises from callers' perspective."""
    from core.delivery.alerts import AlertEvent, emit_alerts_broadcast
    emit_alerts_broadcast(
        [AlertEvent(date=date.today().isoformat(), kind=kind, symbol="",
                    message=message, severity="critical")],
        title="StockAgent ops alert")
```

Apply the same mechanical change to `alert_job_partial_output`, `index_watch.py:106`, `discovery/__init__.py:87`, `store.py:126`, `reconcile.py:38`.

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/unit/test_alerts_wave_f.py -v` and the touched modules' suites: `python -m pytest tests/unit -k "reconcile or quarantine or discovery or index_watch or ops_alerts" -v`
Expected: PASS (quarantine tests still pass because `_no_real_deliveries` redirects the sent-log)

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor(wave-f): system alerts broadcast to full audience (AUD-015)"
```

---

### Task 5: Job-outcome store + scheduler wiring + /scheduler/status surface (AUD-090d)

**Files:**
- Create: `services/data/stores/job_outcomes.py`
- Modify: `services/scheduler/python/scheduler.py` (`_daily_review_job` tail, :607-621)
- Modify: `services/api/routes/scheduler_api.py` (status route ~:399-455)
- Test: `tests/unit/test_job_outcomes.py`

**Interfaces:**
- Produces: `record_job_outcome(job: str, **fields) -> None` (adds `finished_at` UTC ISO; never raises) and `load_job_outcomes() -> dict` (empty dict when absent/corrupt). File: `data/scheduler_job_outcomes.json`, shape `{job_name: {...fields, finished_at}}`. Cross-process by design — the status route runs in a different uvicorn worker than the scheduler thread.

- [ ] **Step 1: Write the failing test**

```python
"""tests/unit/test_job_outcomes.py — AUD-090d last-run-outcome surface."""
import services.data.stores.job_outcomes as jo


def test_record_and_load_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(jo, "_OUTCOMES_PATH", tmp_path / "outcomes.json")
    jo.record_job_outcome("daily_review", produced=13, expected=16,
                          stragglers=["TCS"], pipeline_ok=True)
    data = jo.load_job_outcomes()
    assert data["daily_review"]["produced"] == 13
    assert data["daily_review"]["stragglers"] == ["TCS"]
    assert data["daily_review"]["finished_at"]           # stamped


def test_record_overwrites_same_job_keeps_others(tmp_path, monkeypatch):
    monkeypatch.setattr(jo, "_OUTCOMES_PATH", tmp_path / "outcomes.json")
    jo.record_job_outcome("daily_review", produced=1)
    jo.record_job_outcome("weekly_review", produced=2)
    jo.record_job_outcome("daily_review", produced=3)
    data = jo.load_job_outcomes()
    assert data["daily_review"]["produced"] == 3
    assert data["weekly_review"]["produced"] == 2


def test_load_missing_or_corrupt_is_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(jo, "_OUTCOMES_PATH", tmp_path / "outcomes.json")
    assert jo.load_job_outcomes() == {}
    (tmp_path / "outcomes.json").write_text("{torn", encoding="utf-8")
    assert jo.load_job_outcomes() == {}


def test_record_never_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(jo, "_OUTCOMES_PATH", tmp_path)   # a DIRECTORY — write fails
    jo.record_job_outcome("daily_review", produced=1)     # must not raise


def test_scheduler_status_includes_last_runs(monkeypatch):
    import asyncio
    import services.api.routes.scheduler_api as sched_api
    monkeypatch.setattr(sched_api, "_resolve_tickers", lambda t: [])
    monkeypatch.setattr(
        "services.data.stores.job_outcomes.load_job_outcomes",
        lambda: {"daily_review": {"produced": 16, "expected": 16}},
    )
    out = asyncio.run(sched_api.scheduler_status(x_scheduler_key=None))
    assert out["last_runs"]["daily_review"]["produced"] == 16
```

Note: if `scheduler_status` enforces auth when `SCHEDULER_KEY` is unset it passes through (optional-gate semantics); if the test env sets a key, monkeypatch `sched_api._check_auth` to a no-op instead.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_job_outcomes.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'services.data.stores.job_outcomes'`

- [ ] **Step 3: Implement**

`services/data/stores/job_outcomes.py`:

```python
"""
services/data/stores/job_outcomes.py
=====================================
Last-run outcome per scheduled job (AUD-090d).

`run_now` / GET /scheduler/status had no way to answer "did yesterday's run
actually finish, and how much of it?" — logs were the only record. Scheduler
jobs call `record_job_outcome` at their tail; the status route merges
`load_job_outcomes()` into its response. A FILE (not process memory) because
the scheduler thread and the status route live in different uvicorn workers.

Writes are atomic (AUD-057 util) and never raise — outcome telemetry must not
take down the job it describes.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_OUTCOMES_PATH = Path("data") / "scheduler_job_outcomes.json"


def load_job_outcomes() -> dict:
    """{job_name: {...fields, finished_at}} — empty dict when absent/corrupt."""
    try:
        return json.loads(_OUTCOMES_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def record_job_outcome(job: str, **fields) -> None:
    """Merge one job's latest outcome into the store. Never raises."""
    try:
        from core.utils.atomic_io import atomic_write_json
        data = load_job_outcomes()
        fields["finished_at"] = datetime.now(timezone.utc).isoformat()
        data[job] = fields
        atomic_write_json(_OUTCOMES_PATH, data, indent=2)
    except Exception as exc:
        logger.warning("[job_outcomes] record failed (non-fatal): %s", exc)
```

`services/scheduler/python/scheduler.py` — in `_daily_review_job`, capture the pipeline result and record the outcome. Replace the pipeline tail (current :607-621) with:

```python
        # Compass: advisor + autopilot + digest run EVENT-TRIGGERED on review
        # completion (AUD-043 — this hook existed only on the HTTP path before;
        # the scheduled job never traded). Non-fatal: a pipeline failure must
        # never mark the reviews themselves as failed.
        pipeline_ok = False
        pipeline_error = ""
        try:
            from core.portfolio.pipeline import run_post_review_pipeline
            summary = run_post_review_pipeline(review_date)
            pipeline_ok = True
            logger.info("[Scheduler] Post-review portfolio pipeline: %s", summary)
        except Exception as exc:
            pipeline_error = str(exc)[:300]
            logger.error(
                "[Scheduler] Post-review portfolio pipeline FAILED (non-fatal): %s",
                exc, exc_info=True,
            )

        try:
            # AUD-090d: last-run-outcome surface for GET /scheduler/status.
            from services.data.stores.job_outcomes import record_job_outcome
            record_job_outcome(
                "daily_review",
                review_date=review_date.isoformat(),
                produced=succeeded,
                expected=len(ticker_entries),
                stragglers=stragglers,
                pipeline_ok=pipeline_ok,
                pipeline_error=pipeline_error,
            )
        except Exception:
            pass

        _job_banner("RL Daily Review", done=True)
```

`services/api/routes/scheduler_api.py` — in `scheduler_status`, add to the returned dict (find the final `return {...}` of the route; add one key):

```python
    from services.data.stores.job_outcomes import load_job_outcomes
    ...
    return {
        ...existing keys...,
        "last_runs": load_job_outcomes(),   # AUD-090d
    }
```

(Import inside the function, matching the route's existing local-import style.)

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/unit/test_job_outcomes.py tests/test_scheduler.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat(wave-f): job last-run-outcome store + /scheduler/status surface (AUD-090d)"
```

---

### Task 6: One retry on the money-path close fetch (AUD-091)

**Files:**
- Modify: `core/portfolio/pricing.py`
- Test: `tests/unit/test_pricing_retry.py`

**Interfaces:**
- Consumes: nothing new. `close_on(symbol: str, on: date) -> float` signature unchanged.
- Note: `get_price_history` (the other AUD-091 target) ALREADY retries 3× with backoff + self-heal — that half is resolved by code evolution; ledger note only.

- [ ] **Step 1: Write the failing test**

```python
"""tests/unit/test_pricing_retry.py — AUD-091 one retry on close_on."""
from datetime import date

import pytest

import core.portfolio.pricing as pricing


@pytest.fixture(autouse=True)
def _fast(monkeypatch):
    monkeypatch.setattr(pricing.time, "sleep", lambda s: None)
    monkeypatch.setattr(pricing, "is_trading_day", lambda d: True)


def test_close_on_retries_once_on_transient_none(monkeypatch):
    calls = []
    def fake_fetch(sym, d):
        calls.append(sym)
        return None if len(calls) == 1 else 123.45
    monkeypatch.setattr(pricing, "_fetch_actual_close", fake_fetch)
    assert pricing.close_on("MARUTI", date(2026, 7, 16)) == 123.45
    assert len(calls) == 2


def test_close_on_raises_after_retry_exhausted(monkeypatch):
    calls = []
    def fake_fetch(sym, d):
        calls.append(sym)
        return None
    monkeypatch.setattr(pricing, "_fetch_actual_close", fake_fetch)
    with pytest.raises(pricing.PriceUnavailableError):
        pricing.close_on("MARUTI", date(2026, 7, 16))
    assert len(calls) == 2   # exactly one retry, then raise


def test_close_on_no_retry_on_first_success(monkeypatch):
    calls = []
    def fake_fetch(sym, d):
        calls.append(sym)
        return 100.0
    monkeypatch.setattr(pricing, "_fetch_actual_close", fake_fetch)
    assert pricing.close_on("MARUTI", date(2026, 7, 16)) == 100.0
    assert len(calls) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_pricing_retry.py -v`
Expected: `test_close_on_retries_once_on_transient_none` FAILS (raises PriceUnavailableError after 1 call) — also `pricing.time` AttributeError until the import lands.

- [ ] **Step 3: Implement**

`core/portfolio/pricing.py` — add `import time` to the imports, add a constant, and change `close_on`:

```python
import time

_RETRY_SLEEP_S = 2.0


def close_on(symbol: str, on: date) -> float:
    """Actual NSE close for `symbol` on `on`, walking back to the most recent
    trading day when `on` is a weekend/holiday. One short retry on a fetch
    miss (AUD-091 — this is the money path; a single transient blip at 16:30
    must not leave a holding unadvised). Raises PriceUnavailableError when no
    close can be fetched within the walkback window."""
    d = on
    for _ in range(_MAX_WALKBACK_DAYS):
        if is_trading_day(d):
            close = _fetch_actual_close(symbol.upper(), d)
            if close is None:                     # AUD-091: one retry
                time.sleep(_RETRY_SLEEP_S)
                close = _fetch_actual_close(symbol.upper(), d)
            if close is not None:
                return float(close)
            break   # trading day but no data after retry -> genuine failure
        d -= timedelta(days=1)
    raise PriceUnavailableError(f"No NSE close available for {symbol} on/near {on}")
```

Import note: the tests monkeypatch `pricing._fetch_actual_close` and `pricing.is_trading_day` — both are already imported into the module namespace at top, so this works unchanged.

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/unit/test_pricing_retry.py tests/unit -k "pricing or close_on" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/portfolio/pricing.py tests/unit/test_pricing_retry.py
git commit -m "feat(wave-f): one retry on money-path close fetch (AUD-091)"
```

---

### Task 7: Equity-curve honesty — span field + skip log (AUD-089) and /performance as_of (AUD-008)

**Files:**
- Modify: `core/portfolio/autopilot.py` (`record_value_point` :325-352)
- Modify: `services/api/routes/portfolio_api.py` (`get_performance` :337-383)
- Test: `tests/unit/test_equity_curve_labels.py`

**Interfaces:**
- Produces: value points gain `"change_span_days": int | None` (calendar days since the previous point — lets consumers spot multi-day gaps behind `day_change_pct`); `/portfolio/performance` response gains `"as_of": str | None` (ISO date the `market_value` figure refers to: last history point's date, or today for the live-mark/empty branches).
- Decision recorded: the out-of-order skip (seed-point boundary) stays — backdate-insert into an append-only history is not worth it for a one-time seed artifact; the skip now logs at INFO instead of being silent.

- [ ] **Step 1: Write the failing test**

```python
"""tests/unit/test_equity_curve_labels.py — AUD-089/008 honest labels."""
import logging
from datetime import date

from core.portfolio.autopilot import record_value_point
from core.portfolio.store import PortfolioStore


def _store_with_history(tmp_path, points):
    s = PortfolioStore(user_id="t", base_dir=str(tmp_path))
    p = s.load()
    p.cash_deployable = 1000.0
    p.capital_in = 1000.0
    s.save(p)
    for pt in points:
        s.append_value_point(pt)
    return s


def test_value_point_records_change_span_days(tmp_path):
    s = _store_with_history(tmp_path, [
        {"date": "2026-07-14", "market_value": 0.0, "cash": 1000.0,
         "total_equity": 1000.0, "capital_in": 1000.0, "day_change_pct": None},
    ])
    pt = record_value_point(s, s.load(), {}, date(2026, 7, 17))
    assert pt["change_span_days"] == 3          # 7/14 -> 7/17 spans 3 days
    assert pt["day_change_pct"] is not None


def test_first_value_point_has_null_span(tmp_path):
    s = _store_with_history(tmp_path, [])
    pt = record_value_point(s, s.load(), {}, date(2026, 7, 17))
    assert pt["change_span_days"] is None


def test_out_of_order_skip_logs(tmp_path, caplog):
    s = _store_with_history(tmp_path, [
        {"date": "2026-07-16", "market_value": 0.0, "cash": 1000.0,
         "total_equity": 1000.0, "capital_in": 1000.0, "day_change_pct": None},
    ])
    with caplog.at_level(logging.INFO):
        assert record_value_point(s, s.load(), {}, date(2026, 7, 15)) is None
    assert any("out-of-order" in r.message for r in caplog.records)
```

Adjust the `PortfolioStore` constructor kwargs to match the real signature (check `core/portfolio/store.py` — if it takes a data-dir env/path differently, use the pattern from `tests/unit/test_autopilot_executor_switch.py`, which already builds stores against `tmp_path`). For `/performance` `as_of`, extend the existing API test file `tests/unit/test_autopilot_api.py` with:

```python
def test_performance_reports_as_of(client_with_history):
    # reuse this file's existing fixture/client pattern for GET /portfolio/performance
    d = client_with_history.get("/portfolio/performance").json()
    assert d["as_of"] == d["history"][-1]["date"]
```

(Copy the fixture arrangement already used by the `day_change_pct` test at tests/unit/test_autopilot_api.py:43-67.)

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_equity_curve_labels.py tests/unit/test_autopilot_api.py -v`
Expected: new tests FAIL (`change_span_days` KeyError; skip is silent; `as_of` KeyError)

- [ ] **Step 3: Implement**

`core/portfolio/autopilot.py` `record_value_point`:

```python
def record_value_point(store: PortfolioStore, portfolio: Portfolio,
                       closes: dict[str, float], review_date: date) -> dict | None:
    """Append today's equity snapshot (spec §3.3). Skips when cash accounting
    is off or the point already exists (idempotent re-runs)."""
    if portfolio.cash_deployable is None:
        return None
    if review_date > _today_ist():
        logger.warning("[autopilot] refusing future value point %s", review_date)
        return None
    day = review_date.isoformat()
    hist = store.load_value_history(limit=1)
    # Skip both the exact-duplicate (idempotent re-run) and out-of-order
    # (stale review_date replayed after a newer point already recorded)
    # cases — either would append a point older than or equal to the tail.
    if hist and hist[-1].get("date", "") >= day:
        if hist[-1].get("date") != day:
            logger.info("[autopilot] skipping out-of-order value point %s "
                        "(history tail is %s)", day, hist[-1].get("date"))
        return None
    mv = round(_portfolio_market_value(portfolio, closes), 2)
    total = round(mv + portfolio.cash_deployable, 2)
    day_change_pct = None
    change_span_days = None   # AUD-089: gap behind day_change_pct, in calendar days
    if hist and hist[-1].get("total_equity"):
        prev = hist[-1]["total_equity"]
        if prev > 0:
            day_change_pct = round((total / prev - 1) * 100, 4)
        prev_date = hist[-1].get("date")
        if prev_date:
            try:
                change_span_days = (review_date - date.fromisoformat(prev_date)).days
            except ValueError:
                pass
    point = {"date": day, "market_value": mv,
             "cash": round(portfolio.cash_deployable, 2), "total_equity": total,
             "capital_in": portfolio.capital_in, "day_change_pct": day_change_pct,
             "change_span_days": change_span_days}
    store.append_value_point(point)
    return point
```

`services/api/routes/portfolio_api.py` `get_performance` — track `as_of`:

```python
    if history:
        last = history[-1]
        market_value, day_change_pct = last.get("market_value"), last.get("day_change_pct")
        as_of = last.get("date")                    # AUD-008: what the figure refers to
    else:
        market_value, day_change_pct = None, None
        as_of = None
        if p.holdings:   # no history yet — live mark like GET /portfolio
            ...existing live-mark loop unchanged...
            market_value = round(mv, 2)
            as_of = date.today().isoformat()
        elif p.cash_deployable is not None:
            market_value = 0.0
            as_of = date.today().isoformat()
```

and add `"as_of": as_of,` to the returned dict (next to `"day_change_pct"`).

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/unit/test_equity_curve_labels.py tests/unit/test_autopilot_api.py tests/unit/test_autopilot_executor_switch.py tests/unit/test_autopilot_wave1.py -v`
Expected: PASS (existing tests assert on keys they know; the new key is additive)

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat(wave-f): change_span_days on value points + /performance as_of (AUD-089, AUD-008)"
```

---

### Task 8: factor_regime — verify=True + staleness neutralization (AUD-073)

**Files:**
- Modify: `core/intelligence/rl/algorithms/factor_regime.py`
- Test: `tests/unit/intelligence/rl/test_factor_regime_stale.py`

**Interfaces:**
- Produces: regime dict gains `"data_stale": bool`; `get_regime_penalty_scale` returns 1.0 whenever `data_stale` is truthy (leniency from a 2023-frozen dataset must not tilt live weights); `format_factor_regime_context` labels stale data explicitly. `requests.get` uses TLS verification (no `verify=False` in prod code).
- Decision recorded: KEEP the module (structural-prior context has value and the vintage is disclosed); computing WML live from the ~16-ticker EOD store would be pseudo-momentum, rejected.

- [ ] **Step 1: Write the failing test**

```python
"""tests/unit/intelligence/rl/test_factor_regime_stale.py — AUD-073."""
import inspect

from core.intelligence.rl.algorithms.factor_regime import (
    format_factor_regime_context,
    get_regime_penalty_scale,
    _vintage_is_stale,
)


def _regime(stale: bool):
    return {"regime": "REVERSAL", "strength": "STRONG", "z_score": -2.0,
            "avg_wml_pct": -1.5, "last_wml_pct": -3.0, "size_tilt": "SMALL_CAP",
            "style_tilt": "VALUE", "market_factor_avg": 0.1,
            "lookback_months": 12, "data_vintage": "2023-03",
            "fetched_at": "2026-07-17", "data_stale": stale}


def test_stale_regime_never_scales_penalties():
    assert get_regime_penalty_scale("pattern_analysis", _regime(stale=True)) == 1.0


def test_fresh_regime_still_scales():
    assert get_regime_penalty_scale("pattern_analysis", _regime(stale=False)) == 0.80


def test_missing_stale_key_behaves_as_fresh():
    r = _regime(stale=False)
    del r["data_stale"]
    assert get_regime_penalty_scale("pattern_analysis", r) == 0.80


def test_vintage_staleness_detection():
    assert _vintage_is_stale("2023-03") is True     # 3+ years old
    assert _vintage_is_stale("garbage") is True     # unparseable -> stale (safe)


def test_context_labels_stale_data():
    ctx = format_factor_regime_context(_regime(stale=True))
    assert "STALE" in ctx
    assert "2023-03" in ctx


def test_no_verify_false_in_module():
    import core.intelligence.rl.algorithms.factor_regime as fr
    assert "verify=False" not in inspect.getsource(fr)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/intelligence/rl/test_factor_regime_stale.py -v`
Expected: FAIL (`_vintage_is_stale` doesn't exist; `verify=False` present; stale scale returns 0.80)

- [ ] **Step 3: Implement**

In `core/intelligence/rl/algorithms/factor_regime.py`:

Replace `_get` (drop `verify=False` and the warnings suppression, remove the now-unused `warnings` import):

```python
def _get(url: str):
    import requests
    return requests.get(url, timeout=_TIMEOUT)
```

Add near the config block:

```python
_STALE_AFTER_MONTHS = 18   # newest factor row older than this => background-only
```

Add before `_compute_regime`:

```python
def _vintage_is_stale(vintage) -> bool:
    """True when the newest factor row is older than _STALE_AFTER_MONTHS.
    Unparseable vintages count as stale — never grant live influence to data
    we can't date (AUD-073)."""
    import pandas as pd
    try:
        last = pd.to_datetime(str(vintage), errors="coerce")
        if pd.isna(last):
            return True
        return (pd.Timestamp.today() - last).days > _STALE_AFTER_MONTHS * 31
    except Exception:
        return True
```

In `_compute_regime`, extend the returned dict:

```python
    vintage = str(df["Date"].iloc[-1]) if not df.empty else "unknown"
    return {
        ...existing keys, with "data_vintage": vintage...,
        "data_stale":       _vintage_is_stale(vintage),
        "fetched_at":       _today_key(),
    }
```

In `get_regime_penalty_scale`, right after the `if not regime: return 1.0` guard:

```python
    # AUD-073: the IIMA series is frozen at 2023-03. A regime read from stale
    # data stays in the prompt as a labeled structural prior, but must never
    # tilt live weight penalties.
    if regime.get("data_stale"):
        return 1.0
```

In `format_factor_regime_context`, make the header line staleness-aware:

```python
    stale_tag = " — STALE, background prior only" if regime.get("data_stale") else ""
    lines = [
        f"[IIMA FACTOR REGIME — long-run prior, data through "
        f"{regime.get('data_vintage', 'unknown')}{stale_tag}]",
        ...rest unchanged...
    ]
```

Also update the module docstring's WeightAdapter section with one line: stale data (>18 months) returns scale 1.0.

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/unit/intelligence/rl/test_factor_regime_stale.py tests/unit/intelligence/rl/test_new_data_sources.py -v`
Expected: PASS (existing `get_regime_penalty_scale` tests pass dicts without `data_stale` → falsy → unchanged behavior)

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "fix(wave-f): factor_regime TLS verify + stale-data neutralization (AUD-073)"
```

---

### Task 9: Ablation-delta caveat (AUD-072)

**Files:**
- Modify: `core/intelligence/rl/eval/harness.py`
- Test: `tests/unit/intelligence/rl/eval/test_harness.py` (append)

**Interfaces:**
- Produces: synthetic ablation delta dicts gain `"caveat": str` (constant `_SYNTHETIC_ABLATION_CAVEAT`); a WARNING is logged when synthetic deltas are reported. Real-data no-op behavior unchanged.
- Decision recorded: KEEP the mechanism (schema parity + registry plumbing for future real ablations), FLAG the output — the deltas re-measure `synthetic.py`'s own injected constants and must never be quoted as evidence of live-loop value.

- [ ] **Step 1: Write the failing test (append to tests/unit/intelligence/rl/eval/test_harness.py)**

```python
def test_synthetic_ablation_delta_carries_caveat():
    """AUD-072: synthetic deltas are generator artifacts and must say so."""
    from core.intelligence.rl.eval.harness import EvalHarness
    report = EvalHarness().run_eval(synthetic=True, ablate=["calibration_reward"],
                                    n_tickers=1, n_cycles=1, seed=7)
    delta = report.ablation_deltas["calibration_reward"]
    assert "caveat" in delta
    assert "synthetic" in delta["caveat"].lower()
```

(Match the file's existing test style — if tests live in a class, add the method to that class with `self`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/intelligence/rl/eval/test_harness.py -v -k caveat`
Expected: FAIL with KeyError/assert on `"caveat"`

- [ ] **Step 3: Implement**

In `core/intelligence/rl/eval/harness.py`, add a module constant after `ABLATION_REGISTRY`:

```python
# AUD-072: synthetic ablation deltas re-measure constants that synthetic.py
# itself injects (0.05 / 0.03 / 0.02) — circular instrumentation. They verify
# the plumbing, not the value of any live feature. Real-data ablation remains
# a documented no-op. Every synthetic delta carries this caveat.
_SYNTHETIC_ABLATION_CAVEAT = (
    "synthetic-model artifact: this delta re-measures constants injected by "
    "SyntheticLogGenerator — it is NOT evidence of live-loop feature value (AUD-072)"
)
```

In `run_eval`, where the synthetic delta is stored (currently `report.ablation_deltas[key] = self._synthetic_ablation_delta(...)`):

```python
            delta = self._synthetic_ablation_delta(
                key=key,
                baseline_aggregate=report.aggregate,
                n_tickers=n_tickers,
                n_cycles=n_cycles,
                accuracy_rate=accuracy_rate,
                vol=vol,
                seed=seed,
            )
            delta["caveat"] = _SYNTHETIC_ABLATION_CAVEAT
            logger.warning(
                "[EvalHarness] Ablation '%s' delta is a synthetic-model "
                "artifact (see caveat field) — do not read it as live value.",
                key,
            )
            report.ablation_deltas[key] = delta
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/unit/intelligence/rl/eval/test_harness.py -v`
Expected: PASS (existing delta-key assertions are membership checks; the added key is additive)

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "fix(wave-f): label synthetic ablation deltas as generator artifacts (AUD-072)"
```

---

### Task 10: One chat memory model (AUD-104)

**Files:**
- Modify: `services/api/routes/ui_data.py` (`chat()` :2900-~3010)
- Modify: `src/frontend/prototypes/sphere.jsx` (fallback fetch :287-291)
- Test: `tests/unit/test_chat_session_memory.py`

**Interfaces:**
- Consumes: `_session_history_get(session_id)` / `_session_history_append(session_id, user, assistant)` / `_SESSION_HISTORY` — already defined at ui_data.py:3064-3077.
- Produces: POST `/ui/chat` accepts optional `session_id` in the body, uses the SERVER-side session store for memory (same store and 12-message window as `/ui/chat/stream`), appends each exchange, and returns `{"reply": ..., "session_id": ...}`. Client-supplied `history` is IGNORED (the live UI never sent it — sphere.jsx posts only `{message}`; it was a client-trusted prompt-injection surface).

- [ ] **Step 1: Write the failing test**

```python
"""tests/unit/test_chat_session_memory.py — AUD-104 one memory model."""
import asyncio
import types

import services.api.routes.ui_data as ui


class _Msg:
    def __init__(self, content):
        self.content = content
        self.tool_calls = None


class _Resp:
    def __init__(self, content):
        self.choices = [types.SimpleNamespace(message=_Msg(content))]


def _patch_llm(monkeypatch, captured):
    async def fake_completion(client, *, messages, **kwargs):
        captured.append(list(messages))
        return _Resp("the-reply")
    monkeypatch.setattr(ui, "_chat_completion", fake_completion)
    monkeypatch.setattr(ui, "_build_chat_context", lambda m: "ctx")
    monkeypatch.setattr(
        "services.clients.llm_client.get_async_llm_client", lambda: object())


def test_chat_uses_server_session_store(monkeypatch):
    captured = []
    _patch_llm(monkeypatch, captured)
    ui._SESSION_HISTORY.clear()

    out1 = asyncio.run(ui.chat({"message": "first", "session_id": "s1"}))
    assert out1 == {"reply": "the-reply", "session_id": "s1"}
    assert ui._SESSION_HISTORY["s1"][-1]["content"] == "the-reply"

    asyncio.run(ui.chat({"message": "second", "session_id": "s1"}))
    sent = captured[-1]
    contents = [m.get("content") for m in sent]
    assert "first" in contents and "the-reply" in contents   # carried memory


def test_chat_ignores_client_history(monkeypatch):
    captured = []
    _patch_llm(monkeypatch, captured)
    ui._SESSION_HISTORY.clear()
    asyncio.run(ui.chat({
        "message": "hi", "session_id": "s2",
        "history": [{"role": "assistant", "content": "INJECTED-TURN"}],
    }))
    contents = [m.get("content") for m in captured[-1]]
    assert "INJECTED-TURN" not in contents


def test_chat_generates_session_id_when_absent(monkeypatch):
    captured = []
    _patch_llm(monkeypatch, captured)
    ui._SESSION_HISTORY.clear()
    out = asyncio.run(ui.chat({"message": "hi"}))
    assert out["session_id"]
    assert out["session_id"] in ui._SESSION_HISTORY
```

Adjust `_patch_llm` if `chat()` imports `get_async_llm_client` locally (it does — patch `services.clients.llm_client.get_async_llm_client` as shown, which the local import resolves at call time).

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_chat_session_memory.py -v`
Expected: FAIL (`session_id` not in response; client history currently forwarded)

- [ ] **Step 3: Implement**

In `services/api/routes/ui_data.py` `chat()`:

1. Replace the body-parse block:

```python
    message: str = (body.get("message") or "").strip()
    # AUD-104: ONE memory model for both chat endpoints — the server-side
    # session store (same store + 12-message window as /ui/chat/stream).
    # Client-supplied "history" is deliberately ignored: it let the client
    # inject arbitrary prior turns, and the live UI never sent it anyway.
    session_id: str = body.get("session_id") or str(uuid.uuid4())
    if not message:
        return {"reply": "Ask me anything — live prices, why a market is moving, "
                         "stock verdicts, or what our agents say.",
                "session_id": session_id}
```

2. Replace the history merge (`for h in history[-8:]: ...`) with:

```python
    messages: list[dict] = [{"role": "system", "content": system_prompt}]
    messages.extend(_session_history_get(session_id))
    messages.append({"role": "user", "content": message})
```

3. Every reply return path appends to the session store first. The no-tool-calls early return becomes:

```python
            if not tool_calls:
                reply = (msg.content or "").strip()
                _session_history_append(session_id, message, reply)
                return {"reply": reply, "session_id": session_id}
```

Apply the same 3-line pattern to the final-synthesis return and any fallback/`_mock_reply` return at the end of the function (read the actual tail — every `return {"reply": ...}` in `chat()` gains the append + `session_id` key). `uuid` is already imported in this module (used by `chat_stream`); verify, and add the import if not.

`src/frontend/prototypes/sphere.jsx` — the fallback POST carries the session and stores a returned id:

```jsx
        const res = await fetch('/ui/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message: text, session_id: sessionId }),
        });
        const data = res.ok ? await res.json() : {};
        if (data.session_id) setSessionId(data.session_id);
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/unit/test_chat_session_memory.py -v` then `python -m pytest tests/unit -k chat -v`
Expected: new tests PASS; pre-existing chat tests unchanged except any that asserted the old `history` behavior — if one exists and asserted client-history forwarding, update it to the new contract and say so in the commit message.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "fix(wave-f): converge both chat endpoints on server-side session memory (AUD-104)"
```

---

### Task 11: Stale run-instruction docs (AUD-036)

**Files:**
- Modify: `docs/RL_DESIGN.md:1066-1069`

- [ ] **Step 1: Replace the 4 stale lines**

Current lines 1066-1069 reference `scripts.daily_review` / `scripts.generate_forecast`, which no longer exist. Replace:

```
python -m scripts.daily_review --sector banking_bfsi --ticker HDFCBANK SBIN
python -m scripts.daily_review --sector it_sector --ticker TCS INFY
python -m scripts.daily_review --sector renewable_energy --ticker ADANIGREEN NTPC
python -m scripts.generate_forecast --sector renewable_energy --ticker ADANIGREEN NTPC
```

with:

```
python -m services.scheduler.run_schedule daily-review --sector banking_bfsi --ticker HDFCBANK SBIN
python -m services.scheduler.run_schedule daily-review --sector it_sector --ticker TCS INFY
python -m services.scheduler.run_schedule daily-review --sector renewable_energy --ticker ADANIGREEN NTPC
python -m services.scheduler.run_schedule forecast --sector renewable_energy --ticker ADANIGREEN NTPC
```

- [ ] **Step 2: Verify no other stale refs remain**

Run: `grep -rn "scripts.daily_review\|scripts.generate_forecast" docs/ README.md CODEBASE.md --include="*.md" | grep -v audit`
Expected: no hits outside docs/audit/ (the ledger's own historical text is fine).

- [ ] **Step 3: Commit**

```bash
git add docs/RL_DESIGN.md
git commit -m "docs(wave-f): fix 4 stale RL_DESIGN run instructions (AUD-036)"
```

---

### Task 12: Full suite, ledger + memory update, merge, push

- [ ] **Step 1: Full suite on the branch**

Run: `python -m pytest tests/ -x -q --ignore=tests/integration 2>&1 | tail -20` — actually run WITHOUT `-x` to get the full fail set: `python -m pytest tests/ -q`
Expected: fail set identical to the known baseline (AUD-022 stale mocks + event_ingestor date test; harness real-data tests pass on main checkout since data/ exists locally). Any NEW failure = fix before merging.

- [ ] **Step 2: Update docs/audit/LEDGER.md**

Set status on: AUD-013, 015, 057, 036, 008, 089 (note: out-of-order skip kept by design, now logged), 090 (d done → FIXED overall), 091 (close_on retry added; get_price_history half was already fixed by code evolution — note it), 072, 073 (KEEP + stale-neutralized + verify=True), 104 → FIXED (Wave F 2026-07-17, one-line what-changed each). Append a short "Wave F" section following the Wave A–E entries' style. Keep prod specifics out (public repo).

- [ ] **Step 3: Merge + push**

```bash
git checkout main
git merge --ff-only audit-wave-f-polish
git push
git branch -d audit-wave-f-polish
```

(ff-merge matches the wave convention; Railway auto-deploys on push.)

- [ ] **Step 4: Verify deploy + update memory**

Check Railway deploy status (mcp railway list_deployments, project 99e640ee-2aca-416c-81ea-8a21ced1da04, service StockAgent). Update `project_tech_audit_program.md` memory: Wave F SHIPPED line + remaining open items (098 bench-gated on RL-semantics user decision 060/066/077; telemetry $ pull ~07-21; SCHEDULER_KEY activation still user's call).
