"""Run the tests under a memory guard: a runaway run ends the tests, not the machine.

Usage (repository root, Linux):

    python scripts/ci/guarded_suite.py                    # the full suite
    python scripts/ci/guarded_suite.py --only browser     # one of its two steps
    python scripts/ci/guarded_suite.py -- PYTEST_ARGS     # any pytest run, guarded

The full suite is two steps, and both must pass: every test except the browser
files, then the browser files. While a step runs, the guard:

* stops it when the container's anonymous memory (``anon`` in cgroup v2's
  ``memory.stat``; page cache is never judged) is over 2,400 MB;
* stops it when one test, or a stretch with no test running, passes its time
  limit;
* ends every process the step leaves behind, found by lineage and never by name
  (tests/proc_tree.py), and logs what it ended (tests/guard_plugin.py does so
  after each browser test and at session end; the guard sweeps once more).

A stopped step ends the whole run. The pytest process is also the kernel's
first choice if memory runs out between two looks, and it dies if the guard
does. The log, analysis_data/test-guard/guard.log (ignored by git), keeps its
last 400 lines. Where the memory cannot be read, as on Windows, the guard does
not run: use ``python -m pytest`` there.

Exit codes: 0 passed, 1 a test or step failed, 2 the guard could not run,
3 stopped for memory, 4 stopped for time, 5 stopped by a signal. A fault in the
guard itself ends the run's processes and exits 2.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import traceback
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import partial
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from tests import proc_tree  # noqa: E402

LIMIT_ANON_MB = 2400         # the owner's figure (26 Nov 2026)
TEST_TIMEOUT_S = 300         # one test; the slowest outside the browser files took 16 s
BROWSER_TIMEOUT_S = 960      # above the 600 and 900 s the browser tests give their own node runs
IDLE_TIMEOUT_S = 600         # no test running: start-up, collection, session end
MAX_RUN_S = 5400
POLL_S = 0.25
BLIND_S = 5.0                # memory unreadable for this long: stop
MAX_LOG_LINES = 400
MAX_LINE_CHARS = 400
MAX_PROCESS_LINES = 20       # per event; the count is always given
DEFAULT_LOG = REPO / "analysis_data" / "test-guard" / "guard.log"
CGROUP_DIR = "/sys/fs/cgroup"
MB = 1024 * 1024
IST = timezone(timedelta(hours=5, minutes=30))

# The test files that start a real browser. They run as their own step.
BROWSER_FILES = (
    "tests/unit/test_chat_markdown_boundary.py",
    "tests/unit/test_member_screens_pr040.py",
    "tests/unit/test_ui_no_invented_figures_pr001.py",
    "tests/unit/architecture_map/test_viewer_browser_map002.py",
)

PASSED, FAILED, CANNOT_RUN, STOPPED_MEMORY, STOPPED_TIME, STOPPED_SIGNAL = range(6)


@dataclass(frozen=True)
class Step:
    name: str
    pytest_args: tuple[str, ...]
    cleanup: str             # "each": end leftovers after every test too; "end": at session end
    test_timeout_s: float


def suite_steps(test_timeout_s: float = TEST_TIMEOUT_S,
                browser_timeout_s: float = BROWSER_TIMEOUT_S) -> list[Step]:
    """The full suite: everything but the browser files, then the browser files."""
    options = ("-q", "-rfEs")
    # Absolute: pytest resolves --ignore against the folder in use while it collects, and
    # tests/hermetic.py has moved into an empty one by then.
    ignored = tuple(f"--ignore={REPO / path}" for path in BROWSER_FILES)
    return [
        Step("main", options + ignored, "end", test_timeout_s),
        Step("browser", options + BROWSER_FILES, "each", browser_timeout_s),
    ]


class GuardLog:
    """Prints each line and keeps the last ``max_lines`` of them in a file."""

    def __init__(self, path: Path, max_lines: int = MAX_LOG_LINES):
        self.path = Path(path)
        self.max_lines = max_lines

    def write(self, text: str) -> None:
        text = text.replace("\r", " ").replace("\n", " ")
        line = f"{datetime.now(IST):%Y-%m-%d %H:%M:%S} IST  {text}"[:MAX_LINE_CHARS]
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            old = (self.path.read_text(encoding="utf-8", errors="replace").splitlines()
                   if self.path.exists() else [])
            part = self.path.with_name(f"{self.path.name}.{os.getpid()}.part")
            part.write_text("\n".join((old + [line])[-self.max_lines:]) + "\n", encoding="utf-8")
            os.replace(part, self.path)
        except OSError as exc:
            text += f"  (could not write {self.path}: {exc})"
        try:
            print(f"[guard] {text}", flush=True)
        except OSError:
            pass                             # whoever read the output has gone; the file has it

    def processes(self, heading: str, entries: list[dict]) -> None:
        self.write(f"{heading}: {len(entries)} process(es)")
        for entry in sorted(entries, key=lambda e: -e["anon_mb"])[:MAX_PROCESS_LINES]:
            self.write(f"  pid {entry['pid']} {entry['name']} {entry['anon_mb']} MB: {entry['cmd']}")


def _read_counter(path: str, key: str) -> int | None:
    try:
        with open(path, encoding="ascii") as fh:
            for line in fh:
                name, _, value = line.partition(" ")
                if name == key:
                    return int(value)
    except (OSError, ValueError):
        return None
    return None


def read_anon_mb(cgroup_dir: str) -> float | None:
    """Anonymous memory of the whole container, or None when it cannot be read."""
    value = _read_counter(os.path.join(cgroup_dir, "memory.stat"), "anon")
    return None if value is None else value / MB


def read_cap_mb(cgroup_dir: str) -> float | None:
    try:
        with open(os.path.join(cgroup_dir, "memory.max"), encoding="ascii") as fh:
            return int(fh.read()) / MB
    except (OSError, ValueError):            # "max": no cap
        return None


def read_pinned_mb(cgroup_dir: str) -> float:
    """What the cap also holds that is neither anon nor free to take back: shared memory,
    and the kernel's own less its reclaimable caches."""
    stat = os.path.join(cgroup_dir, "memory.stat")
    kernel, reclaimable, shared = ((_read_counter(stat, key) or 0)
                                   for key in ("kernel", "slab_reclaimable", "shmem"))
    return (max(kernel - reclaimable, 0) + shared) / MB


def _read_marker(run_dir: str) -> dict | None:
    try:
        with open(os.path.join(run_dir, "marker.json"), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):            # not written yet
        return None


class _Leftovers:
    """Logs what the plugin reports ending, as it reports it."""

    def __init__(self, run_dir: str, step: str, log: GuardLog):
        self.path = os.path.join(run_dir, "leftovers.jsonl")
        self.step, self.log = step, log
        self.offset = 0
        self.ended = 0
        self.still_running = 0

    def drain(self) -> None:
        try:
            with open(self.path, "rb") as fh:
                fh.seek(self.offset)
                data = fh.read()
        except OSError:
            return
        complete = data[:data.rfind(b"\n") + 1]
        self.offset += len(complete)
        for line in complete.splitlines():
            record = json.loads(line)
            where = f"step {self.step}, {record['when']} {record['test']}".rstrip()
            if record["ended"]:
                self.ended += len(record["ended"])
                self.log.processes(f"{where}: ended what was left running", record["ended"])
            if record["still_running"]:
                self.still_running += len(record["still_running"])
                self.log.processes(f"{where}: COULD NOT END", record["still_running"])


def _first_to_die(guard_pid: int) -> None:
    """Runs in the pytest process before it starts."""
    try:
        with open("/proc/self/oom_score_adj", "w", encoding="ascii") as fh:
            fh.write("900")                  # the kernel's first choice if memory runs out
    except OSError:
        os.write(2, b"[guard] could not raise oom_score_adj\n")
    proc_tree.die_with_parent()              # never left running without the guard
    if os.getppid() != guard_pid:            # it died before that took effect
        os._exit(STOPPED_SIGNAL)


def _watch(child: subprocess.Popen, step: Step, options, run_dir: str, leftovers: _Leftovers,
           stop: list[int], run_started: float, seen: dict) -> tuple[int, str] | None:
    """Looks until the step ends (None) or a rule stops it: (exit code, reason)."""
    marker = {"seq": 0, "state": "starting", "test": ""}
    since = time.monotonic()
    blind_since = None
    while child.poll() is None:
        now = time.monotonic()
        newer = _read_marker(run_dir)
        if newer and newer["seq"] != marker["seq"]:
            marker, since = newer, now
        seen["marker"] = marker
        anon = read_anon_mb(options.cgroup_dir)
        if anon is None:
            blind_since = blind_since or now
            if now - blind_since >= BLIND_S:
                return CANNOT_RUN, f"the memory could not be read for {BLIND_S:g} s"
        else:
            blind_since = None
            if anon > seen["peak_mb"]:
                seen["peak_mb"], seen["peak_test"] = anon, marker["test"]
            if anon > options.limit_anon_mb:
                return STOPPED_MEMORY, (f"anon {anon:.0f} MB is over the "
                                        f"{options.limit_anon_mb} MB limit")
        if stop:
            return STOPPED_SIGNAL, f"stopped by signal {stop[0]}"
        if marker["state"] == "running" and now - since > step.test_timeout_s:
            return STOPPED_TIME, f"one test ran longer than {step.test_timeout_s:g} s"
        if marker["state"] != "running" and now - since > options.idle_timeout:
            return STOPPED_TIME, (f"no test ran for {options.idle_timeout:g} s "
                                  f"({marker['state']})")
        if now - run_started > options.max_seconds:
            return STOPPED_TIME, f"the run is longer than {options.max_seconds:g} s"
        leftovers.drain()
        proc_tree.reap_orphans(keep=frozenset({child.pid}))
        time.sleep(options.poll_seconds)
    # pytest has ended. A test may have begun since the last look, and taken pytest with it.
    seen["marker"] = _read_marker(run_dir) or seen["marker"]
    return None


def _where(marker: dict) -> str:
    if marker["state"] == "running":
        return f"while running {marker['test']}"
    after = f", after {marker['test']}" if marker["test"] else ""
    return f"with no test running ({marker['state']}{after})"


def run_step(step: Step, options, log: GuardLog, stop: list[int], run_started: float) -> int:
    if stop:
        log.write(f"step {step.name}: not started, stopped by signal {stop[0]}")
        return STOPPED_SIGNAL
    anon = read_anon_mb(options.cgroup_dir)
    if anon is None:
        log.write(f"step {step.name}: not started, the memory cannot be read")
        return CANNOT_RUN
    if anon > options.limit_anon_mb:
        log.write(f"step {step.name}: STOPPED before it started, anon is already {anon:.0f} MB, "
                  f"over the {options.limit_anon_mb} MB limit")
        return STOPPED_MEMORY
    events = os.path.join(options.cgroup_dir, "memory.events")
    kills_before = _read_counter(events, "oom_kill")
    run_dir = tempfile.mkdtemp(prefix="sa-test-guard-")
    leftovers = _Leftovers(run_dir, step.name, log)
    seen = {"marker": {"seq": 0, "state": "starting", "test": ""}, "peak_mb": anon, "peak_test": ""}
    log.write(f"step {step.name}: started, anon {anon:.0f} MB, "
              f"per-test limit {step.test_timeout_s:g} s")
    started = time.monotonic()
    env = dict(os.environ, SA_TEST_GUARD_DIR=run_dir, SA_TEST_GUARD_CLEANUP=step.cleanup)
    child = subprocess.Popen([sys.executable, "-m", "pytest", "-p", "tests.guard_plugin",
                              *step.pytest_args], cwd=REPO, env=env,
                             preexec_fn=partial(_first_to_die, os.getpid()))
    try:
        stopped = _watch(child, step, options, run_dir, leftovers, stop, run_started, seen)
    finally:
        # Whatever happened, nothing of this step stays running. Everything under this
        # process is the step's: it starts nothing else.
        ended, running = proc_tree.end_processes(lambda: proc_tree.descendants(os.getpid()))
        child.wait()
        proc_tree.reap_orphans()
        leftovers.drain()
        shutil.rmtree(run_dir, ignore_errors=True)
    seconds = time.monotonic() - started
    if stopped is None and stop:
        # A signal to the whole process group can end pytest before the guard looks again.
        stopped = STOPPED_SIGNAL, f"stopped by signal {stop[0]}"
    if stopped:
        code, reason = stopped
        log.write(f"step {step.name}: STOPPED {_where(seen['marker'])}: {reason}")
        log.processes(f"step {step.name}: ended by the stop", ended)
    elif child.returncode == 0 and seen["marker"]["state"] == "finishing":
        code = PASSED
    else:
        code = FAILED
        if child.returncode < 0:
            what = f"was killed by signal {-child.returncode} {_where(seen['marker'])}"
        elif child.returncode == 0:
            what = f"ended without finishing its session, {_where(seen['marker'])}"
        else:
            what = f"exit {child.returncode}"
        log.write(f"step {step.name}: pytest {what}")
    if ended and not stopped:
        leftovers.ended += len(ended)
        log.processes(f"step {step.name}, after pytest ended: ended what was left running", ended)
    left = leftovers.still_running + len(running)
    if running:
        log.processes(f"step {step.name}: COULD NOT END", running)
    if left and code == PASSED:
        code = FAILED
    kills_after = _read_counter(events, "oom_kill")
    if kills_before is not None and kills_after is not None and kills_after > kills_before:
        log.write(f"step {step.name}: the kernel killed {kills_after - kills_before} "
                  f"process(es) for memory during it")
    outcome = {PASSED: "passed", FAILED: "FAILED"}.get(code, "stopped")
    peak_at = f" during {seen['peak_test']}" if seen["peak_test"] else ""
    by_stop = f"; ended by the stop: {len(ended)}" if stopped else ""
    log.write(f"step {step.name}: {outcome} after {seconds:.0f} s; peak anon "
              f"{seen['peak_mb']:.0f} MB{peak_at}; left-behind processes ended: "
              f"{leftovers.ended}{by_stop}; still running: {left}")
    return code


def run(steps: list[Step], options, log: GuardLog, stop: list[int]) -> int:
    run_started = time.monotonic()
    cap = read_cap_mb(options.cgroup_dir)
    capped = "no cap" if cap is None else f"cap {cap:.0f} MB"
    log.write(f"run started: {', '.join(s.name for s in steps)}; limit "
              f"{options.limit_anon_mb} MB anon, {capped}")
    if cap is not None:
        pinned = read_pinned_mb(options.cgroup_dir)
        room = cap - pinned - options.limit_anon_mb
        if room < 300:
            log.write(f"WARNING: {room:.0f} MB of room above the limit under the cap of "
                      f"{cap:.0f} MB ({pinned:.0f} MB held beside anon): the kernel may act "
                      "before the guard")
    codes = []
    for index, step in enumerate(steps):
        codes.append(run_step(step, options, log, stop, run_started))
        if codes[-1] not in (PASSED, FAILED):
            for skipped in steps[index + 1:]:
                log.write(f"step {skipped.name}: not run")
            break
    stopped = [c for c in codes if c not in (PASSED, FAILED)]
    code = stopped[0] if stopped else (FAILED if FAILED in codes else PASSED)
    log.write(f"verdict: {'PASS' if code == PASSED else 'FAIL'} (exit {code})")
    return code


def _parse(argv: list[str]):
    pytest_args = None
    if "--" in argv:
        cut = argv.index("--")
        argv, pytest_args = argv[:cut], tuple(argv[cut + 1:])
    parser = argparse.ArgumentParser(
        prog="guarded_suite.py", description="Run the tests under a memory guard.",
        epilog="Anything after -- is one guarded pytest run with those arguments.")
    parser.add_argument("--only", choices=("main", "browser"), help="one step of the full suite")
    parser.add_argument("--limit-anon-mb", type=int, default=LIMIT_ANON_MB)
    parser.add_argument("--test-timeout", type=float, default=TEST_TIMEOUT_S, help="seconds")
    parser.add_argument("--browser-timeout", type=float, default=BROWSER_TIMEOUT_S, help="seconds")
    parser.add_argument("--idle-timeout", type=float, default=IDLE_TIMEOUT_S, help="seconds")
    parser.add_argument("--max-seconds", type=float, default=MAX_RUN_S)
    parser.add_argument("--poll-seconds", type=float, default=POLL_S)
    parser.add_argument("--cleanup", choices=("each", "end"),
                        help="for a run given after --; default: each if it names a browser "
                             "file, else end")
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--cgroup-dir", default=CGROUP_DIR)
    options = parser.parse_args(argv)
    if pytest_args is not None and (not pytest_args or options.only):
        parser.error("give pytest arguments after --, without --only")
    return options, pytest_args


def steps_for(options, pytest_args: tuple[str, ...] | None) -> list[Step]:
    """The steps asked for: the full suite, one of its steps, or the run given after --."""
    if pytest_args:
        names = {Path(path).name for path in BROWSER_FILES}
        browser = any(Path(arg.partition("::")[0]).name in names for arg in pytest_args)
        return [Step("custom", pytest_args, options.cleanup or ("each" if browser else "end"),
                     options.browser_timeout if browser else options.test_timeout)]
    return [step for step in suite_steps(options.test_timeout, options.browser_timeout)
            if options.only in (None, step.name)]


def main(argv: list[str] | None = None, steps: list[Step] | None = None) -> int:
    options, pytest_args = _parse(sys.argv[1:] if argv is None else argv)
    log = GuardLog(options.log)
    if not sys.platform.startswith("linux") or read_anon_mb(options.cgroup_dir) is None:
        log.write(f"cannot run: no readable anon in {options.cgroup_dir}/memory.stat. "
                  "On this machine run python -m pytest.")
        return CANNOT_RUN
    if steps is None:
        steps = steps_for(options, pytest_args)
    proc_tree.become_subreaper()
    stop: list[int] = []
    for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(signum, lambda received, frame: stop.append(received))
    try:
        return run(steps, options, log, stop)
    except Exception as exc:                 # logged; run_step has already ended its processes
        traceback.print_exc()
        log.write(f"guard error, the run is stopped: {exc!r}")
        return CANNOT_RUN


if __name__ == "__main__":
    sys.exit(main())
