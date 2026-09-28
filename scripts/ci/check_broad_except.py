"""Guard against new unlogged broad exception swallowing (SA-005).

A handler is a *silent broad swallow* when it catches everything (a bare
``except:``, ``Exception``, ``BaseException``, or a tuple containing one) and
its body neither re-raises, nor calls a logging method, nor uses the bound
exception. ``contextlib.suppress(Exception)`` counts as one too.

Existing swallows are grandfathered in ``broad_except_baseline.txt`` (next to
this script), keyed by path, enclosing function and ordinal, so moving code
up or down a file does not trip the check. Only code that changed can: a new
swallow, or an edit that shifts the ordinals inside one function. A new,
deliberate boundary is allowlisted inline, with a reason, on the ``except``
line::

    except Exception:  # swallow-ok: best-effort cache warm; a miss is harmless

Usage (repository root)::

    python scripts/ci/check_broad_except.py            # check; exit 1 on drift
    python scripts/ci/check_broad_except.py --update   # rewrite the baseline

The baseline is a burn-down list, not a review: its entries were not judged
individually when it was created. Fixing one makes its entry stale, and the
check then asks for ``--update`` so the list only shrinks through a diff.
"""
from __future__ import annotations

import argparse
import ast
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASELINE = Path(__file__).with_name("broad_except_baseline.txt")
PRAGMA = "swallow-ok:"
_BROAD = {"Exception", "BaseException"}
_LOG_METHODS = {"debug", "info", "warning", "warn", "error", "exception", "critical", "log",
                "print_exc", "print_exception"}
_SKIP_PREFIXES = ("tests/",)
_WALK_DIRS = ("core", "services", "src", "scripts")


def _is_broad(node: ast.expr | None) -> bool:
    if node is None:
        return True
    if isinstance(node, ast.Name):
        return node.id in _BROAD
    if isinstance(node, ast.Attribute):
        return node.attr in _BROAD
    if isinstance(node, ast.Tuple):
        return any(_is_broad(e) for e in node.elts)
    return False


def _handles(handler: ast.ExceptHandler) -> bool:
    """True when the body re-raises, logs, or uses the bound exception."""
    for node in ast.walk(ast.Module(body=handler.body, type_ignores=[])):
        if isinstance(node, ast.Raise):
            return True
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr in _LOG_METHODS):
            return True
        if handler.name and isinstance(node, ast.Name) and node.id == handler.name:
            return True
    return False


def _is_broad_suppress(call: ast.expr) -> bool:
    if not isinstance(call, ast.Call):
        return False
    func = call.func
    name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
    return name == "suppress" and any(_is_broad(a) for a in call.args)


def _has_pragma(lines: list[str], lineno: int) -> bool:
    line = lines[lineno - 1] if 0 < lineno <= len(lines) else ""
    _, found, reason = line.partition(PRAGMA)
    return bool(found) and bool(reason.strip())


class _Finder(ast.NodeVisitor):
    def __init__(self, path: str, lines: list[str]) -> None:
        self.path = path
        self.lines = lines
        self.scope: list[str] = []
        self.ordinals: Counter = Counter()
        self.found: list[tuple[str, int, bool, str]] = []   # key, line, pragma, text

    def _record(self, node: ast.AST, kind: str) -> None:
        qual = ".".join(self.scope) or "<module>"
        n = self.ordinals[qual]
        self.ordinals[qual] += 1
        key = f"{self.path} | {qual} | #{n}"
        text = self.lines[node.lineno - 1].strip() if node.lineno <= len(self.lines) else kind
        self.found.append((key, node.lineno, _has_pragma(self.lines, node.lineno), text))

    def _scoped(self, node) -> None:
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    visit_FunctionDef = visit_AsyncFunctionDef = visit_ClassDef = _scoped

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if _is_broad(node.type) and not _handles(node):
            self._record(node, "except")
        self.generic_visit(node)

    def _visit_with(self, node) -> None:
        if any(_is_broad_suppress(item.context_expr) for item in node.items):
            self._record(node, "suppress")
        self.generic_visit(node)

    visit_With = visit_AsyncWith = _visit_with


def scan_source(path: str, source: str) -> list[tuple[str, int, bool, str]]:
    """Every silent broad swallow in one file: (key, line, has_pragma, text)."""
    finder = _Finder(path, source.splitlines())
    finder.visit(ast.parse(source, filename=path))
    return finder.found


def _python_files(root: Path) -> list[str]:
    try:
        out = subprocess.run(["git", "ls-files", "-z", "--", "*.py"], cwd=root,
                             capture_output=True, check=True).stdout.decode("utf-8")
        files = [f for f in out.split("\0") if f]
    except (OSError, subprocess.CalledProcessError):
        files = [p.relative_to(root).as_posix() for d in _WALK_DIRS for p in (root / d).rglob("*.py")]
        files += [p.name for p in root.glob("*.py")]
    return sorted(f for f in files if not f.startswith(_SKIP_PREFIXES))


def scan(root: Path = ROOT) -> dict[str, tuple[int, bool, str]]:
    found: dict[str, tuple[int, bool, str]] = {}
    for rel in _python_files(root):
        source = (root / rel).read_text(encoding="utf-8-sig")
        for key, line, pragma, text in scan_source(rel, source):
            found[key] = (line, pragma, text)
    return found


def read_baseline(path: Path = BASELINE) -> set[str]:
    if not path.exists():
        return set()
    return {ln.strip() for ln in path.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.startswith("#")}


def write_baseline(keys: set[str], path: Path = BASELINE) -> None:
    header = ("# Grandfathered silent broad exception handlers (SA-005). One per line:\n"
              "# path | enclosing function | ordinal within it. Burn this list down;\n"
              "# regenerate with: python scripts/ci/check_broad_except.py --update\n")
    path.write_text(header + "".join(k + "\n" for k in sorted(keys)), encoding="utf-8", newline="\n")


def check(root: Path = ROOT, baseline: Path = BASELINE) -> tuple[list[str], list[str]]:
    """(new, stale): unallowlisted swallows, and baseline entries that no longer exist."""
    found = scan(root)
    allowed = read_baseline(baseline)
    live = {k for k, (_, pragma, _) in found.items() if not pragma}
    new = [f"{k.split(' | ')[0]}:{found[k][0]}: {found[k][2]}  [{k}]" for k in sorted(live - allowed)]
    stale = sorted(allowed - live)
    return new, stale


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--update", action="store_true", help="rewrite the baseline to the current tree")
    args = parser.parse_args(argv)
    if args.update:
        found = scan()
        keys = {k for k, (_, pragma, _) in found.items() if not pragma}
        write_baseline(keys)
        print(f"baseline rewritten: {len(keys)} grandfathered handler(s)")
        return 0
    new, stale = check()
    for line in new:
        print(f"NEW silent broad except: {line}")
    for key in stale:
        print(f"STALE baseline entry (fixed or moved): {key}")
    if new:
        print(f"\n{len(new)} new silent broad handler(s). Log, re-raise, narrow the exception, "
              f"or add '# {PRAGMA} <reason>' on the except line.")
    if stale:
        print(f"\n{len(stale)} stale baseline entr(y/ies). Run: python scripts/ci/check_broad_except.py --update")
    if not new and not stale:
        print(f"broad-except guard: OK ({len(read_baseline())} grandfathered)")
    return 1 if (new or stale) else 0


if __name__ == "__main__":
    sys.exit(main())
