"""The test guard (OPS-002): scripts/ci/guarded_suite.py, run as the autopilot runs it,
on throwaway pytest files, with a made-up cgroup folder for the memory it reads.

What must hold: the run is stopped over the anon limit (and never for the page cache
that fills ``memory.current``), at the time limits and on a signal; the log names the
running test; whatever a test leaves behind is ended, by lineage only; a failure in
either step of the full suite fails the whole run.
"""
from __future__ import annotations

import os
import re
import shutil
import signal
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(not sys.platform.startswith("linux"),
                                reason="the guard reads Linux's /proc and cgroup v2")

REPO = Path(__file__).resolve().parents[3]
GUARD = REPO / "scripts" / "ci" / "guarded_suite.py"
FORCED = REPO / "scripts" / "ci" / "guard_forced_memory.py"
MB = 1024 * 1024
NODE = shutil.which("node")

# Shared by the stand-in test files. A launcher starts a child in a session of its own
# and exits, so the child is an orphan, as a browser is when its node process is killed.
HELPERS = '''
import os, signal, subprocess, sys, time
from pathlib import Path
import pytest

SLEEP = "import time; time.sleep(600)"
LAUNCH = ("import subprocess, sys; "
          "p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(600)'], "
          "start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); "
          "print(p.pid)")

def leave_a_child_behind(pid_file):
    done = subprocess.run([sys.executable, "-c", LAUNCH], capture_output=True, text=True,
                          timeout=60, check=True)
    Path(pid_file).write_text(done.stdout.strip())

def running(pid_file):
    pid = int(Path(pid_file).read_text())
    try:
        return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0] != "Z"
    except OSError:
        return False
'''


def _running(pid: int) -> bool:
    try:
        return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0] != "Z"
    except OSError:
        return False


def _pid_in(path: Path) -> int:
    return int(path.read_text())


def _wait_for(condition, seconds: float = 90.0):
    deadline = time.monotonic() + seconds
    while not condition():
        assert time.monotonic() < deadline, "waited too long"
        time.sleep(0.1)


def _cgroup(tmp_path: Path, anon_mb: int = 500, current_mb: int = 900, cap_mb: int = 3815,
            **stat_mb: int) -> Path:
    folder = tmp_path / "cgroup"
    folder.mkdir(exist_ok=True)
    stat = {"anon": anon_mb, "file": current_mb - anon_mb, **stat_mb}
    (folder / "memory.stat").write_text("".join(f"{key} {mb * MB}\n" for key, mb in stat.items()))
    (folder / "memory.current").write_text(f"{current_mb * MB}\n")
    (folder / "memory.max").write_text(f"{cap_mb * MB}\n")
    (folder / "memory.events").write_text("max 0\noom_kill 0\n")
    return folder


def _stand_in(tmp_path: Path, body: str, name: str = "test_stand_in.py") -> Path:
    project = tmp_path / "project"
    project.mkdir(exist_ok=True)
    (project / "pytest.ini").write_text("[pytest]\n")
    path = project / name
    path.write_text(HELPERS + textwrap.dedent(body))
    return path


def _pytest_args(path: Path) -> list[str]:
    return ["-c", str(path.parent / "pytest.ini"), "--rootdir", str(path.parent),
            "-p", "no:cacheprovider", str(path)]


def _command(tmp_path: Path, cgroup: Path, test: Path, *options: str) -> list[str]:
    return [sys.executable, str(GUARD), "--log", str(tmp_path / "guard.log"),
            "--cgroup-dir", str(cgroup), *options, "--", *_pytest_args(test)]


def _guard(tmp_path: Path, cgroup: Path, test: Path, *options: str):
    """Runs the guard to its end: (finished process, its log)."""
    done = subprocess.run(_command(tmp_path, cgroup, test, *options), cwd=REPO,
                          capture_output=True, text=True, timeout=180)
    log = tmp_path / "guard.log"
    return done, log.read_text() if log.exists() else ""


# --------------------------------------------------------------------------- memory

def test_memory_over_the_limit_stops_the_run_names_the_test_and_ends_its_processes(tmp_path):
    cgroup = _cgroup(tmp_path)
    left, later = tmp_path / "left.pid", tmp_path / "later"
    test = _stand_in(tmp_path, f"""
        def test_grows():
            leave_a_child_behind({str(left)!r})
            stat = Path({str(cgroup / 'memory.stat')!r})
            part = stat.with_suffix(".part")
            part.write_text("anon {2401 * MB}\\n")
            os.replace(part, stat)
            time.sleep(600)

        def test_after():
            Path({str(later)!r}).write_text("ran")
    """)
    done, log = _guard(tmp_path, cgroup, test)      # the default limit: the owner's 2,400 MB
    assert done.returncode == 3, done.stdout + done.stderr
    assert "STOPPED while running test_stand_in.py::test_grows" in log
    assert "anon 2401 MB is over the 2400 MB limit" in log
    assert "verdict: FAIL (exit 3)" in log
    assert f"pid {_pid_in(left)} " in log
    assert not _running(_pid_in(left))
    assert not later.exists(), "a stopped run must not go on to the next test"


def test_a_full_cache_and_anon_at_the_limit_do_not_stop_the_run(tmp_path):
    # The total is at the cap, as it was in a healthy run (OPS-001); anon is exactly 2,400.
    cgroup = _cgroup(tmp_path, anon_mb=2400, current_mb=3815)
    test = _stand_in(tmp_path, """
        def test_long_enough_to_be_looked_at():
            time.sleep(2)

        def test_the_kernel_takes_the_tests_first():
            assert Path("/proc/self/oom_score_adj").read_text().strip() == "900"
    """)
    done, log = _guard(tmp_path, cgroup, test)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "2 passed" in done.stdout
    assert "STOPPED" not in log and "verdict: PASS (exit 0)" in log
    assert "peak anon 2400 MB" in log


def test_a_box_already_over_the_limit_is_not_given_a_run(tmp_path):
    ran = tmp_path / "ran"
    test = _stand_in(tmp_path, f"""
        def test_never():
            Path({str(ran)!r}).write_text("ran")
    """)
    done, log = _guard(tmp_path, _cgroup(tmp_path, anon_mb=2600), test)
    assert done.returncode == 3
    assert "STOPPED before it started" in log and "2600 MB" in log
    assert not ran.exists()


def test_unreadable_memory_refuses_to_run(tmp_path):
    ran = tmp_path / "ran"
    test = _stand_in(tmp_path, f"""
        def test_never():
            Path({str(ran)!r}).write_text("ran")
    """)
    empty = tmp_path / "no-cgroup"
    empty.mkdir()
    done, log = _guard(tmp_path, empty, test)
    assert done.returncode == 2
    assert "cannot run" in log and not ran.exists()


def test_memory_that_stops_being_readable_stops_the_run(tmp_path):
    cgroup = _cgroup(tmp_path)
    test = _stand_in(tmp_path, f"""
        def test_blinds_the_guard():
            os.remove({str(cgroup / 'memory.stat')!r})
            time.sleep(600)
    """)
    done, log = _guard(tmp_path, cgroup, test)
    assert done.returncode == 2
    assert "could not be read" in log and "test_blinds_the_guard" in log


# --------------------------------------------------------------------------- time

def test_the_time_limit_is_per_test_and_names_the_one_that_passed_it(tmp_path):
    left = tmp_path / "left.pid"
    test = _stand_in(tmp_path, f"""
        def test_first():
            time.sleep(4)

        def test_second():
            time.sleep(4)

        def test_hangs():
            leave_a_child_behind({str(left)!r})
            time.sleep(600)
    """)
    done, log = _guard(tmp_path, _cgroup(tmp_path), test, "--test-timeout", "7")
    assert done.returncode == 4, done.stdout + done.stderr
    # The two four-second tests, eight seconds together, were each inside the limit.
    assert "STOPPED while running test_stand_in.py::test_hangs" in log
    assert "one test ran longer than 7 s" in log
    assert not _running(_pid_in(left))


def test_a_hang_outside_any_test_is_stopped(tmp_path):
    test = _stand_in(tmp_path, """
        time.sleep(600)          # while pytest collects this file

        def test_never():
            pass
    """)
    done, log = _guard(tmp_path, _cgroup(tmp_path), test, "--idle-timeout", "5")
    assert done.returncode == 4
    assert "STOPPED with no test running" in log and "no test ran for 5 s" in log


def test_the_whole_run_has_a_limit(tmp_path):
    test = _stand_in(tmp_path, """
        def test_slow():
            time.sleep(600)
    """)
    done, log = _guard(tmp_path, _cgroup(tmp_path), test, "--max-seconds", "5")
    assert done.returncode == 4
    assert "the run is longer than 5 s" in log


# --------------------------------------------------------------------------- left behind

@pytest.mark.skipif(NODE is None, reason="node is not on PATH")
def test_a_browser_test_s_leftover_is_ended_after_it_and_an_outside_node_is_left_alone(tmp_path):
    left = tmp_path / "left.pid"
    # As Playwright starts a browser: detached, from a node process that then goes away.
    launch = ("const {spawn} = require('child_process');"
              "const c = spawn(process.execPath, ['-e', 'setTimeout(() => {}, 600000)'],"
              " {detached: true, stdio: 'ignore'});"
              "c.unref(); console.log(c.pid);")
    test = _stand_in(tmp_path, f"""
        def test_leaves_a_node():
            done = subprocess.run([{NODE!r}, "-e", {launch!r}], capture_output=True,
                                  text=True, timeout=120, check=True)
            Path({str(left)!r}).write_text(done.stdout.strip())
            assert running({str(left)!r})

        def test_next():
            assert not running({str(left)!r}), "the leftover outlived its test"
    """)
    outsider = subprocess.Popen([NODE, "-e", "setTimeout(() => {}, 600000)"])
    try:
        done, log = _guard(tmp_path, _cgroup(tmp_path), test, "--cleanup", "each")
        assert done.returncode == 0, done.stdout + done.stderr
        assert outsider.poll() is None, "a node process outside the run was ended"
    finally:
        outsider.kill()
        outsider.wait()
    assert "after the test test_stand_in.py::test_leaves_a_node: ended what was left running" in log
    assert f"pid {_pid_in(left)} " in log
    assert str(outsider.pid) not in re.findall(r"pid (\d+) ", log)
    assert "left-behind processes ended: 1; still running: 0" in log
    assert not _running(_pid_in(left))


def test_a_test_whose_own_child_times_out_has_the_grandchild_ended(tmp_path):
    # The browser wrappers' case: subprocess.run(timeout=) ends the top process only.
    left = tmp_path / "left.pid"
    parent = ("import subprocess, sys, time; "
              "p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(600)'], "
              "start_new_session=True); "
              f"open({str(left)!r}, 'w').write(str(p.pid)); time.sleep(600)")
    test = _stand_in(tmp_path, f"""
        def test_times_out():
            subprocess.run([sys.executable, "-c", {parent!r}], timeout=20)

        def test_next():
            assert not running({str(left)!r}), "the grandchild outlived its test"
    """)
    done, log = _guard(tmp_path, _cgroup(tmp_path), test, "--cleanup", "each")
    assert done.returncode == 1, done.stdout + done.stderr
    assert "1 failed, 1 passed" in done.stdout and "TimeoutExpired" in done.stdout
    assert "after the test test_stand_in.py::test_times_out" in log
    assert not _running(_pid_in(left))


def test_without_per_test_cleanup_a_leftover_is_ended_at_session_end(tmp_path):
    left = tmp_path / "left.pid"
    test = _stand_in(tmp_path, f"""
        def test_leaves_a_child():
            leave_a_child_behind({str(left)!r})

        def test_next():
            assert running({str(left)!r}), "ended before the session did"
    """)
    done, log = _guard(tmp_path, _cgroup(tmp_path), test, "--cleanup", "end")
    assert done.returncode == 0, done.stdout + done.stderr
    assert "at session end: ended what was left running" in log
    assert f"pid {_pid_in(left)} " in log
    assert not _running(_pid_in(left))


def test_a_fixture_s_longer_lived_process_is_not_ended_between_tests(tmp_path):
    held = tmp_path / "server.pid"
    test = _stand_in(tmp_path, f"""
        @pytest.fixture(scope="module")
        def server():
            process = subprocess.Popen([sys.executable, "-c", SLEEP])
            Path({str(held)!r}).write_text(str(process.pid))
            return process

        def test_one(server):
            assert server.poll() is None

        def test_two(server):
            assert server.poll() is None, "ended after the first test"
    """)
    done, log = _guard(tmp_path, _cgroup(tmp_path), test, "--cleanup", "each")
    assert done.returncode == 0, done.stdout + done.stderr
    assert "after the test" not in log
    assert "at session end: ended what was left running" in log
    assert not _running(_pid_in(held))


def test_when_pytest_itself_dies_the_guard_ends_what_it_left(tmp_path):
    left = tmp_path / "left.pid"
    test = _stand_in(tmp_path, f"""
        def test_takes_pytest_down():
            leave_a_child_behind({str(left)!r})
            os.kill(os.getpid(), signal.SIGKILL)
    """)
    done, log = _guard(tmp_path, _cgroup(tmp_path), test)
    assert done.returncode == 1, done.stdout + done.stderr
    assert "pytest was killed by signal 9 while running test_stand_in.py::test_takes_pytest_down" in log
    assert "after pytest ended: ended what was left running" in log
    assert not _running(_pid_in(left))


def test_a_pytest_that_leaves_without_finishing_its_session_is_not_a_pass(tmp_path):
    test = _stand_in(tmp_path, """
        def test_fails():
            assert False

        def test_leaves_with_a_zero():
            os._exit(0)
    """)
    done, log = _guard(tmp_path, _cgroup(tmp_path), test)
    assert done.returncode == 1, done.stdout + done.stderr
    assert "ended without finishing its session" in log and "test_leaves_with_a_zero" in log
    assert "verdict: FAIL (exit 1)" in log


# --------------------------------------------------------------------------- the guard itself

# Runs the guard with one of its parts replaced, for what cannot be arranged for real.
PATCHED = '''
import os, sys
sys.path.insert(0, {ci!r})
import guarded_suite as guard
{patch}
sys.exit(guard.main({argv!r}))
'''


def _patched_guard(tmp_path: Path, patch: str, test: Path):
    log = tmp_path / "guard.log"
    argv = ["--log", str(log), "--cgroup-dir", str(_cgroup(tmp_path)), "--", *_pytest_args(test)]
    driver = tmp_path / "patched.py"
    driver.write_text(PATCHED.format(ci=str(GUARD.parent), patch=patch, argv=argv))
    done = subprocess.run([sys.executable, str(driver)], cwd=REPO, capture_output=True,
                          text=True, timeout=180)
    return done, log.read_text()


def test_a_process_that_cannot_be_ended_fails_a_run_whose_tests_passed(tmp_path):
    test = _stand_in(tmp_path, """
        def test_passes():
            pass
    """)
    done, log = _patched_guard(tmp_path, textwrap.dedent("""
        real = guard.proc_tree.end_processes
        def stuck(find, wait_s=10.0):
            ended, _ = real(find, wait_s)
            return ended, [{"pid": 4242, "name": "stuck", "anon_mb": 1, "cmd": "in disk wait"}]
        guard.proc_tree.end_processes = stuck
    """), test)
    assert "1 passed" in done.stdout
    assert done.returncode == 1, done.stdout + done.stderr
    assert "COULD NOT END" in log and "pid 4242 stuck" in log and "still running: 1" in log


def test_a_fault_in_the_guard_ends_the_run_s_processes_and_is_logged(tmp_path):
    left = tmp_path / "left.pid"
    test = _stand_in(tmp_path, f"""
        def test_waits():
            leave_a_child_behind({str(left)!r})
            time.sleep(600)
    """)
    done, log = _patched_guard(tmp_path, textwrap.dedent(f"""
        def broken(self):
            if os.path.exists({str(left)!r}) and os.path.getsize({str(left)!r}):
                raise RuntimeError("a fault of the guard's own")
        guard._Leftovers.drain = broken
    """), test)
    assert done.returncode == 2, done.stdout + done.stderr
    assert "guard error" in log and "a fault of the guard's own" in log
    assert not _running(_pid_in(left))


@pytest.mark.parametrize("kernel, reclaimable, warned", [(500, 478, False), (600, 100, True)])
def test_the_log_warns_when_the_cap_leaves_little_room_above_the_limit(
        tmp_path, kernel, reclaimable, warned):
    # A 3 GB limit reads as 2,861 MB. Reclaimable caches leave room; held memory does not.
    cgroup = _cgroup(tmp_path, cap_mb=2861, kernel=kernel, slab_reclaimable=reclaimable)
    test = _stand_in(tmp_path, """
        def test_passes():
            pass
    """)
    done, log = _guard(tmp_path, cgroup, test)
    assert done.returncode == 0, done.stdout + done.stderr
    assert ("WARNING" in log) is warned, log


# --------------------------------------------------------------------------- signals

def test_a_signal_to_the_guard_stops_the_run_and_ends_its_processes(tmp_path):
    left = tmp_path / "left.pid"
    ready = tmp_path / "ready"
    test = _stand_in(tmp_path, f"""
        def test_waits():
            leave_a_child_behind({str(left)!r})
            Path({str(ready)!r}).write_text("ready")
            time.sleep(600)
    """)
    guard = subprocess.Popen(_command(tmp_path, _cgroup(tmp_path), test), cwd=REPO,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        _wait_for(ready.exists)
        guard.send_signal(signal.SIGTERM)       # what `timeout` sends before a push
        assert guard.wait(timeout=60) == 5
    finally:
        guard.kill()
        guard.wait()
    log = (tmp_path / "guard.log").read_text()
    assert f"stopped by signal {int(signal.SIGTERM)}" in log and "test_waits" in log
    assert not _running(_pid_in(left))


def test_pytest_dies_with_a_guard_that_is_killed_outright(tmp_path):
    own = tmp_path / "pytest.pid"
    test = _stand_in(tmp_path, f"""
        def test_waits():
            part = Path({str(own)!r} + ".part")
            part.write_text(str(os.getpid()))
            os.replace(part, {str(own)!r})
            time.sleep(600)
    """)
    guard = subprocess.Popen(_command(tmp_path, _cgroup(tmp_path), test), cwd=REPO,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        _wait_for(own.exists)
        pid = _pid_in(own)
        assert _running(pid)
    finally:
        guard.kill()
        guard.wait()
    try:
        _wait_for(lambda: not _running(pid), 30)
    finally:
        if _running(pid):
            os.kill(pid, signal.SIGKILL)


def test_a_signal_to_the_whole_group_reads_as_a_signal_though_pytest_dies_first(tmp_path):
    # GNU `timeout` signals the group: pytest is gone before the guard, slow to look, sees it.
    left = tmp_path / "left.pid"
    ready = tmp_path / "ready"
    test = _stand_in(tmp_path, f"""
        def test_waits():
            leave_a_child_behind({str(left)!r})
            Path({str(ready)!r}).write_text("ready")
            time.sleep(600)
    """)
    command = _command(tmp_path, _cgroup(tmp_path), test, "--poll-seconds", "20")
    guard = subprocess.Popen(command, cwd=REPO, start_new_session=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        _wait_for(ready.exists)
        os.killpg(guard.pid, signal.SIGTERM)
        assert guard.wait(timeout=90) == 5
    finally:
        guard.kill()
        guard.wait()
    log = (tmp_path / "guard.log").read_text()
    assert "STOPPED while running test_stand_in.py::test_waits: stopped by signal 15" in log
    assert not _running(_pid_in(left))


# --------------------------------------------------------------------------- the two steps

DRIVER = '''
import sys
sys.path.insert(0, {ci!r})
import guarded_suite as guard
steps = [guard.Step(name, tuple(args), "end", 60) for name, args in {steps!r}]
sys.exit(guard.main(["--log", {log!r}, "--cgroup-dir", {cgroup!r}], steps=steps))
'''


def _two_steps(tmp_path: Path, first: str, second: str):
    steps, ran = [], []
    for name, body in (("first", first), ("second", second)):
        marker = tmp_path / f"{name}.ran"
        ran.append(marker)
        test = _stand_in(tmp_path, f"""
            def test_{name}():
                Path({str(marker)!r}).write_text("ran")
                {body}
        """, name=f"test_{name}.py")
        steps.append((name, _pytest_args(test)))
    driver = tmp_path / "driver.py"
    log = tmp_path / "guard.log"
    driver.write_text(DRIVER.format(ci=str(GUARD.parent), steps=steps, log=str(log),
                                    cgroup=str(tmp_path / "cgroup")))
    done = subprocess.run([sys.executable, str(driver)], cwd=REPO, capture_output=True,
                          text=True, timeout=180)
    return done.returncode, [path.exists() for path in ran], log.read_text()


@pytest.mark.parametrize("first, second, code", [
    ("assert True", "assert True", 0),
    ("assert False", "assert True", 1),
    ("assert True", "assert False", 1),
])
def test_both_steps_run_and_a_failure_in_either_fails_the_run(tmp_path, first, second, code):
    _cgroup(tmp_path)
    returned, ran, log = _two_steps(tmp_path, first, second)
    assert returned == code, log
    assert ran == [True, True]
    assert f"(exit {code})" in log


def test_a_stopped_first_step_ends_the_run(tmp_path):
    cgroup = _cgroup(tmp_path)
    grow = (f"Path({str(cgroup / 'memory.stat')!r}).write_text('anon {3000 * MB}\\n'); "
            "time.sleep(600)")
    returned, ran, log = _two_steps(tmp_path, grow, "assert True")
    assert returned == 3, log
    assert ran == [True, False]
    assert "step second: not run" in log


def _load_guard():
    sys.path.insert(0, str(GUARD.parent))
    try:
        import guarded_suite
    finally:
        sys.path.remove(str(GUARD.parent))
    return guarded_suite


def test_the_full_suite_is_the_browser_files_apart_and_nothing_dropped():
    steps = {step.name: step for step in _load_guard().suite_steps()}
    assert list(steps) == ["main", "browser"]
    # Independently of the guard's own list: every test file that runs a node browser suite.
    launches = re.compile(r'"--test",\s*"tests/frontend/')
    found = sorted(path.relative_to(REPO).as_posix() for path in (REPO / "tests").rglob("test_*.py")
                   if launches.search(path.read_text(encoding="utf-8-sig")))
    assert len(found) == 4, found
    ignored = sorted(Path(a.removeprefix("--ignore=")).relative_to(REPO).as_posix()
                     for a in steps["main"].pytest_args if a.startswith("--ignore="))
    assert ignored == found
    assert sorted(a for a in steps["browser"].pytest_args if a.startswith("tests/")) == found
    # No path in "main": it collects the configured testpaths, so a new test file is in it.
    assert not [a for a in steps["main"].pytest_args if not a.startswith("-")]
    assert (steps["main"].cleanup, steps["browser"].cleanup) == ("end", "each")
    # A browser test's own timeout must come first, so that it fails with its report.
    own = [int(n) for path in found
           for n in re.findall(r"timeout=(\d+)", (REPO / path).read_text(encoding="utf-8-sig"))]
    assert own and steps["browser"].test_timeout_s > max(own)


def test_the_main_step_really_leaves_the_browser_files_out():
    """pytest itself, with the repository's own conftest, which changes folder first."""
    guard = _load_guard()
    main_step = guard.suite_steps()[0]
    # Narrowed to the files named test_ch*, test_me* and test_ui*, to keep it quick.
    unit = REPO / "tests" / "unit"
    narrow = [f"--ignore-glob={unit}/{pattern}" for pattern in
              ("*/*", "test_[!cmu]*.py", "test_c[!h]*.py", "test_m[!e]*.py", "test_u[!i]*.py")]
    done = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-p", "no:cacheprovider",
         *main_step.pytest_args, *narrow, "tests/unit"],
        cwd=REPO, capture_output=True, text=True, timeout=180)
    assert done.returncode == 0, done.stdout[-3000:] + done.stderr[-3000:]
    collected = {line.partition("::")[0] for line in done.stdout.splitlines() if "::" in line}
    assert "tests/unit/test_chat_brief_tool.py" in collected, "the narrowing kept nothing"
    assert not collected & set(guard.BROWSER_FILES), collected & set(guard.BROWSER_FILES)


@pytest.mark.parametrize("argv, expected", [
    (["--test-timeout", "7", "--browser-timeout", "9"], [("main", "end", 7), ("browser", "each", 9)]),
    (["--only", "browser", "--browser-timeout", "9"], [("browser", "each", 9)]),
    (["--only", "main"], [("main", "end", 300)]),
    (["--", "tests/unit/test_member_screens_pr040.py::test_member_browser_suite"],
     [("custom", "each", 960)]),
    (["--", "tests/unit/test_atomic_io.py"], [("custom", "end", 300)]),
    (["--cleanup", "each", "--", "tests/unit/test_atomic_io.py"], [("custom", "each", 300)]),
])
def test_each_way_of_calling_the_guard_gets_its_steps_and_limits(argv, expected):
    guard = _load_guard()
    options, pytest_args = guard._parse(argv)
    assert [(s.name, s.cleanup, s.test_timeout_s)
            for s in guard.steps_for(options, pytest_args)] == expected


# --------------------------------------------------------------------------- log, proof

def test_the_log_keeps_only_its_newest_lines_and_cuts_long_ones(tmp_path):
    log = _load_guard().GuardLog(tmp_path / "deep" / "guard.log", max_lines=5)
    for number in range(23):
        log.write(f"line {number}\nstill line {number}")
    log.write("x" * 5000)
    lines = (tmp_path / "deep" / "guard.log").read_text().splitlines()
    assert len(lines) == 5
    assert [line.split(" IST  ")[1] for line in lines[:4]] == [
        f"line {n} still line {n}" for n in range(19, 23)]
    assert len(lines[4]) == 400


def test_the_forced_memory_proof_allocates_nothing_without_the_guard(tmp_path):
    done = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                           str(FORCED)], cwd=REPO, capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "1 skipped" in done.stdout and "holding" not in done.stdout
