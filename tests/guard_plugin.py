"""The test guard's pytest plugin. scripts/ci/guarded_suite.py loads it (``-p``).

It does two things, and nothing unless the guard started this pytest process:

* writes which test is running, for the guard's time limits and its log;
* ends the processes tests leave behind: after each test when the guard asks
  for it (the browser step), and always at session end. "Left behind" means
  started by the test itself (found by lineage, tests/proc_tree.py) and still
  running after it.

Standard library and pytest only: it loads before tests/conftest.py, so it must
not import application code (tests/hermetic.py).
"""
from __future__ import annotations

import json
import os

import pytest

from tests import proc_tree

# Popped, so a child process (a test's own pytest run, say) never reports as this one.
_DIR = os.environ.pop("SA_TEST_GUARD_DIR", "")
_EACH = os.environ.pop("SA_TEST_GUARD_CLEANUP", "end") == "each"
_PID = os.getpid()
_open, _replace = open, os.replace      # a test's patch of either must not reach the guard
_seq = 0
_before: set[tuple[int, int]] | None = None     # what was running when the test's body began


def active() -> bool:
    """True in the pytest process the guard started, not in a process forked from it."""
    return bool(_DIR) and os.getpid() == _PID


def _mark(state: str, test: str) -> None:
    global _seq
    _seq += 1
    part = os.path.join(_DIR, "marker.part")
    with _open(part, "w", encoding="utf-8") as fh:
        json.dump({"seq": _seq, "state": state, "test": test}, fh)
    _replace(part, os.path.join(_DIR, "marker.json"))


def _end_left_behind(when: str, test: str, keep: set[tuple[int, int]]) -> None:
    ended, running = proc_tree.end_processes(
        lambda: [p for p in proc_tree.descendants(_PID) if (p.pid, p.start) not in keep])
    proc_tree.reap(entry["pid"] for entry in ended)
    if ended or running:
        with _open(os.path.join(_DIR, "leftovers.jsonl"), "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"when": when, "test": test, "ended": ended,
                                 "still_running": running}) + "\n")


def pytest_configure(config):
    if active():
        proc_tree.become_subreaper()
        _mark("collecting", "")


def pytest_runtest_logstart(nodeid, location):
    global _before
    if active():
        _before = None
        _mark("running", nodeid)


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_call(item):
    global _before
    if active() and _EACH:
        # Taken after set-up: a longer-lived fixture's process is not this test's leftover.
        _before = {(p.pid, p.start) for p in proc_tree.descendants(_PID)}
    yield


def pytest_runtest_logfinish(nodeid, location):
    if active():
        if _before is not None:
            _end_left_behind("after the test", nodeid, _before)
        _mark("between", nodeid)


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session, exitstatus):
    if active():
        _mark("finishing", "")
        _end_left_behind("at session end", "", set())
