"""Linux process-tree helpers for the test guard (scripts/ci/guarded_suite.py).

Processes are found by lineage, never by name: everything that descends from a
root process. A root that calls ``become_subreaper`` keeps its orphans: a
browser whose parent was killed moves under the root instead of under init, so
it is still found, and nothing outside the root's own tree ever is.

Standard library only. The functions work on Linux alone; importing is safe
anywhere.
"""
from __future__ import annotations

import ctypes
import os
import signal
import time
from functools import lru_cache
from typing import Callable, Iterable, NamedTuple

_PR_SET_PDEATHSIG = 1
_PR_SET_CHILD_SUBREAPER = 36


class Proc(NamedTuple):
    pid: int
    ppid: int
    start: int      # clock ticks since boot: (pid, start) names one process, even if a pid is reused
    state: str      # "Z" has exited and only waits to be collected
    name: str


@lru_cache(maxsize=None)
def _libc():
    return ctypes.CDLL(None, use_errno=True)


def _prctl(option: int, value: int) -> None:
    if _libc().prctl(option, value, 0, 0, 0) != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))


def become_subreaper() -> None:
    """Orphans of this process's descendants become its own children."""
    _prctl(_PR_SET_CHILD_SUBREAPER, 1)


def die_with_parent() -> None:
    """The kernel kills this process when its parent dies, however that happens."""
    _prctl(_PR_SET_PDEATHSIG, signal.SIGKILL)


def read_proc(pid: int) -> Proc | None:
    try:
        with open(f"/proc/{pid}/stat", "rb") as fh:
            data = fh.read()
    except OSError:
        return None
    # "pid (name) state ppid ...": the name may hold spaces and brackets, so split at the last ")".
    head, _, tail = data.rpartition(b")")
    fields = tail.split()
    if len(fields) < 20:
        return None
    return Proc(pid, int(fields[1]), int(fields[19]), fields[0].decode("ascii"),
                head.partition(b"(")[2].decode("utf-8", "replace"))


def all_processes() -> list[Proc]:
    found = (read_proc(int(name)) for name in os.listdir("/proc") if name.isdigit())
    return [proc for proc in found if proc is not None]


def descendants(root: int) -> list[Proc]:
    """Every process under ``root`` that is still running; ``root`` itself and zombies excluded."""
    children: dict[int, list[Proc]] = {}
    for proc in all_processes():
        children.setdefault(proc.ppid, []).append(proc)
    found, queue, seen = [], [root], {root}
    while queue:
        for child in children.get(queue.pop(), []):
            if child.pid in seen:
                continue
            seen.add(child.pid)
            queue.append(child.pid)
            if child.state != "Z":
                found.append(child)
    return found


def describe(proc: Proc) -> dict:
    """What a log needs to say which process this was. Read before it is ended."""
    anon_mb, command = 0, ""
    try:
        with open(f"/proc/{proc.pid}/status", "rb") as fh:
            for line in fh:
                if line.startswith(b"RssAnon:"):
                    anon_mb = int(line.split()[1]) // 1024
        with open(f"/proc/{proc.pid}/cmdline", "rb") as fh:
            command = fh.read().replace(b"\0", b" ").decode("utf-8", "replace").strip()
    except OSError:
        pass                                  # it ended while being read: the name is enough
    return {"pid": proc.pid, "name": proc.name, "anon_mb": anon_mb, "cmd": command[:160]}


def end_processes(find: Callable[[], list[Proc]], wait_s: float = 10.0) -> tuple[list[dict], list[dict]]:
    """SIGKILL whatever ``find`` returns until it returns nothing twice running.

    Twice, because a process that changes parent while /proc is being listed
    can be missed once. Returns (ended, still running after ``wait_s``).
    """
    seen: dict[tuple[int, int], dict] = {}
    deadline = time.monotonic() + wait_s
    empty = 0
    while True:
        running = find()
        empty = 0 if running else empty + 1
        if empty >= 2:
            return list(seen.values()), []
        for proc in running:
            if (proc.pid, proc.start) not in seen:
                seen[(proc.pid, proc.start)] = describe(proc)
            try:
                os.kill(proc.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass                          # gone already, or listed below as still running
        if time.monotonic() >= deadline:
            left = find()
            gone = {(proc.pid, proc.start) for proc in left}
            return ([entry for key, entry in seen.items() if key not in gone],
                    [describe(proc) for proc in left])
        time.sleep(0.05)


def reap(pids: Iterable[int]) -> None:
    """Collect those of ``pids`` that are this process's exited children."""
    for pid in pids:
        try:
            os.waitpid(pid, os.WNOHANG)
        except ChildProcessError:
            pass                              # not a child of this process, or already collected


def reap_orphans(keep: frozenset[int] = frozenset()) -> None:
    """Collect every exited child except ``keep``, whose exit status someone else reads.

    For a subreaper that starts only ``keep`` itself: every other child is an
    orphan it adopted.
    """
    me = os.getpid()
    reap(proc.pid for proc in all_processes()
         if proc.ppid == me and proc.state == "Z" and proc.pid not in keep)
