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
