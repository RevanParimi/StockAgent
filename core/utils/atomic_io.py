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

`replace_with_retry` is the rename step on its own, for stores that manage
their own temp file (SA-005).
"""
from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path

# Windows refuses to replace a file that another handle holds open without
# FILE_SHARE_DELETE — a concurrent reader, or an antivirus or indexer scan of
# the file just written — with PermissionError (WinError 5 or 32). That clears
# within milliseconds, so retry briefly there. POSIX renames do not fail this
# way, so everywhere else (production and CI run Linux) this is one os.replace.
def _retry_delays(os_name: str) -> tuple[float, ...]:
    return (0.01, 0.02, 0.05, 0.1, 0.2) if os_name == "nt" else ()


_REPLACE_RETRY_DELAYS = _retry_delays(os.name)


def replace_with_retry(src: str | Path, dst: str | Path) -> None:
    """`os.replace(src, dst)`, retried on Windows' transient sharing violation.
    Raises the last error once the retries are spent."""
    for delay in _REPLACE_RETRY_DELAYS:
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            time.sleep(delay)
    os.replace(src, dst)


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
        replace_with_retry(tmp_name, path)
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
