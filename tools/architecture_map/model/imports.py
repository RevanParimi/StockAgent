"""Imports between the repository's Python files, and each file's line count.

Every `import` and `from ... import` is read, those inside functions too, and
resolved to a repository file. `src/backend/` is imported as `backend`.
`from package import name` points at `package/name.py` when that file exists,
else at the package. Imports of other libraries are left out; so are imports a
string names at run time (`importlib`).
"""
from __future__ import annotations

import ast
from pathlib import Path

from tools.architecture_map.model import sources

SRC_PREFIX = "src/"


def module_name(rel: str) -> str:
    """"src/backend/a/b.py" -> "backend.a.b"; a package's __init__ is the package."""
    path = rel[len(SRC_PREFIX):] if rel.startswith(SRC_PREFIX) else rel
    parts = path[:-len(".py")].split("/")
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _resolve(name: str, index: dict[str, str]) -> str | None:
    """The file of a dotted module name: itself, else its nearest package file.

    `src.backend.x` is the same file as `backend.x`.
    """
    if name.startswith("src.backend"):
        name = name[len("src."):]
    parts = name.split(".")
    while parts:
        found = index.get(".".join(parts))
        if found is not None:
            return found
        parts.pop()
    return None


def _targets(tree: ast.Module, rel: str, index: dict[str, str]) -> set[str]:
    own = module_name(rel)
    package = own.split(".") if rel.endswith("__init__.py") else own.split(".")[:-1]
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                target = _resolve(alias.name, index)
                if target:
                    found.add(target)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package[:len(package) - (node.level - 1)]
                base_name = ".".join(base + ([node.module] if node.module else []))
            else:
                base_name = node.module or ""
            if base_name.startswith("src.backend"):
                base_name = base_name[len("src."):]
            for alias in node.names:
                submodule = f"{base_name}.{alias.name}" if base_name else alias.name
                target = index.get(submodule) or (
                    _resolve(base_name, index) if base_name else None)
                if target:
                    found.add(target)
    found.discard(rel)
    return found


def import_graph(root: Path) -> list[dict]:
    """[{path, lines, imports}] for every Python file, sorted by path."""
    files = sources.python_files(root)
    index = {module_name(rel): rel for rel in files}
    return [{"path": rel, "lines": sources.line_count(root, rel),
             "imports": sorted(_targets(sources.parse(root, rel), rel, index))}
            for rel in files]
