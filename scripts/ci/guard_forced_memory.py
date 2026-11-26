"""The guard's proof on a real machine: grow to 3.5 GB and be stopped on the way.

    python scripts/ci/guarded_suite.py -- scripts/ci/guard_forced_memory.py -s

Expected: exit 3, the log naming this test and the memory it was stopped at, and
the detached child below ended too. It grows in 50 MB steps, two a second.
Outside the guard it skips. It has a brake of its own: if the container's anon
passes 2,700 MB, the guard has failed and the test gives up (exit 1). Not part of
the suite (pytest collects ``tests/`` only).
"""
from __future__ import annotations

import subprocess
import sys
import time

import pytest

from tests import guard_plugin

STEP_MB = 50
TARGET_MB = 3584            # 3.5 GB
BRAKE_ANON_MB = 2700        # past the guard's 2,400 with room for a late look, under the cap
PAUSE_S = 0.5


def _anon_mb() -> float:
    """The real container's, whatever the guard was told to read."""
    with open("/sys/fs/cgroup/memory.stat", encoding="ascii") as fh:
        return next(int(line.split()[1]) for line in fh if line.startswith("anon ")) / 1048576


def test_allocates_3_5_gb():
    if not guard_plugin.active():
        pytest.skip("run only through scripts/ci/guarded_suite.py")
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(600)"],
                             start_new_session=True)
    print(f"\ndetached child: pid {child.pid}", flush=True)
    held = []
    while len(held) * STEP_MB < TARGET_MB:
        anon = _anon_mb()
        if anon > BRAKE_ANON_MB:
            held.clear()
            pytest.fail(f"anon reached {anon:.0f} MB and nothing stopped the run")
        held.append(bytearray(b"x") * (STEP_MB * 1024 * 1024))   # written, so it is resident
        print(f"holding {len(held) * STEP_MB} MB", flush=True)
        time.sleep(PAUSE_S)
    pytest.fail(f"held {TARGET_MB} MB and nothing stopped the run")
