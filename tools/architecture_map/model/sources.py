"""Reading the repository's source files, without importing any of them."""
from __future__ import annotations

import ast
import subprocess
from pathlib import Path

# The code the map describes. `src/backend` is imported as `backend`.
CODE_ROOTS = ("core", "services", "src/backend", "scripts")
SKIP_DIRS = {"__pycache__"}


class SourceError(Exception):
    """A source file the generators cannot read; the message names it."""


def _git_files(root: Path) -> list[str] | None:
    """Tracked and new (not ignored) files, or None where git cannot answer.

    Used so an ignored scratch file cannot make this machine's model differ from
    CI's. Without `.git` (a test fixture) the caller walks the folder instead.
    """
    if not (root / ".git").exists():
        return None
    try:
        done = subprocess.run(
            ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard",
             "--", *CODE_ROOTS],
            cwd=root, capture_output=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return None
    return [p for p in done.stdout.decode("utf-8").split("\0") if p]


def _walk_files(root: Path) -> list[str]:
    found: list[str] = []
    for code_root in CODE_ROOTS:
        for path in (root / code_root).rglob("*"):
            parts = path.relative_to(root).parts
            if any(p in SKIP_DIRS or p.startswith(".") for p in parts):
                continue
            found.append("/".join(parts))
    return found


def python_files(root: Path) -> list[str]:
    """Repository paths (forward slashes) of the Python files, sorted."""
    names = _git_files(root)
    if names is None:
        names = _walk_files(root)
    return sorted({n for n in names if n.endswith(".py") and (root / n).is_file()})


def read_text(root: Path, rel: str) -> str:
    """A file's text: UTF-8, a byte-order mark removed, line ends as LF."""
    try:
        raw = (root / rel).read_bytes()
        text = raw.decode("utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        raise SourceError(f"{rel}: cannot be read ({exc})") from exc
    return text.replace("\r\n", "\n")


def parse(root: Path, rel: str) -> ast.Module:
    try:
        return ast.parse(read_text(root, rel), filename=rel)
    except SyntaxError as exc:
        raise SourceError(f"{rel}: does not parse ({exc.msg}, line {exc.lineno})") from exc


def line_count(root: Path, rel: str) -> int:
    return len(read_text(root, rel).splitlines())
