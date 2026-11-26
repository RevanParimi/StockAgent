"""API routes, read from the routers' source (never by importing the app).

`services/api/routes/*.py` each build one `APIRouter(prefix=...)`; the server
mounts them with `include_router` and defines a few routes of its own. A route
is its method, its full path, the file and the handler. A registration style
this reader does not know (`add_api_route` and friends) stops it, so a route is
never silently left out.
"""
from __future__ import annotations

import ast
from pathlib import Path

from tools.architecture_map.model import sources

ROUTES_DIR = "services/api/routes"
SERVER_FILE = "services/api/server.py"
METHODS = ("get", "post", "put", "patch", "delete", "head", "options", "trace")
UNREAD = ("add_api_route", "add_api_websocket_route", "add_route", "add_websocket_route")


def _text(node: ast.AST | None, where: str) -> str:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    raise sources.SourceError(f"{where}: a route path or prefix that is not a plain string")


def _keyword(call: ast.Call, name: str) -> ast.AST | None:
    return next((k.value for k in call.keywords if k.arg == name), None)


def _is_router_call(node: ast.AST) -> bool:
    return isinstance(node, ast.Call) and (
        getattr(node.func, "id", "") == "APIRouter"
        or getattr(node.func, "attr", "") == "APIRouter")


def _router_prefixes(tree: ast.Module, rel: str) -> dict[str, str]:
    """{variable: prefix} for each `x = APIRouter(...)` in a file, annotated or
    not. A router built any other way is refused: its routes would be missed."""
    prefixes: dict[str, str] = {}
    read: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            targets, built = node.targets, node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets, built = [node.target], node.value
        else:
            continue
        if not _is_router_call(built) or not all(isinstance(t, ast.Name) for t in targets):
            continue
        value = _keyword(built, "prefix")
        prefix = "" if value is None else _text(value, rel)
        prefixes.update({t.id: prefix for t in targets})
        read.add(id(built))
    for node in ast.walk(tree):
        if _is_router_call(node) and id(node) not in read:
            raise sources.SourceError(f"{rel} line {node.lineno}: an APIRouter(...) that is not "
                                      "assigned to a plain name, which tools/architecture_map "
                                      "does not read")
    return prefixes


def _mounts(root: Path) -> dict[str, str]:
    """{router file: include prefix} for every router the server mounts."""
    tree = sources.parse(root, SERVER_FILE)
    imported: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith(
                "services.api.routes"):
            for alias in node.names:
                module = node.module if alias.name == "router" else f"{node.module}.{alias.name}"
                imported[alias.asname or alias.name] = module.replace(".", "/") + ".py"
    mounted: dict[str, str] = {}
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "include_router" and node.args):
            arg = node.args[0]
            name = arg.id if isinstance(arg, ast.Name) else (
                arg.value.id if isinstance(arg, ast.Attribute)
                and isinstance(arg.value, ast.Name) else "")
            if name not in imported:
                raise sources.SourceError(
                    f"{SERVER_FILE} line {node.lineno}: include_router of {name or 'something'} "
                    f"that is not imported from {ROUTES_DIR}")
            prefix = _keyword(node, "prefix")
            mounted[imported[name]] = "" if prefix is None else _text(prefix, SERVER_FILE)
    return mounted


def _file_routes(root: Path, rel: str, owners: dict[str, str]) -> list[dict]:
    tree = sources.parse(root, rel)
    prefixes = _router_prefixes(tree, rel)
    owned = {**{name: "" for name in owners}, **prefixes}
    found: list[dict] = []
    unread = UNREAD if rel == SERVER_FILE else (*UNREAD, "include_router")
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr in unread):
            raise sources.SourceError(f"{rel} line {node.lineno}: {node.func.attr}() is a route "
                                      "registration tools/architecture_map does not read")
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not (isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute)):
                continue
            verb = decorator.func.attr
            if verb not in (*METHODS, "websocket", "api_route"):
                continue
            if not (isinstance(decorator.func.value, ast.Name)
                    and decorator.func.value.id in owned):
                raise sources.SourceError(
                    f"{rel} line {decorator.lineno}: @...{verb}() on something that is not a "
                    "router tools/architecture_map read here")
            if verb in METHODS:
                methods = [verb.upper()]
            elif verb == "websocket":
                methods = ["WS"]
            else:
                listed = _keyword(decorator, "methods")
                if listed is not None and not isinstance(listed, (ast.List, ast.Tuple, ast.Set)):
                    raise sources.SourceError(f"{rel} line {decorator.lineno}: api_route methods "
                                              "that are not written out")
                methods = ["GET"] if listed is None else sorted(
                    _text(e, rel).upper() for e in listed.elts)
            first = decorator.args[0] if decorator.args else _keyword(decorator, "path")
            path = owned[decorator.func.value.id] + _text(first, f"{rel} line {decorator.lineno}")
            found += [{"method": m, "path": path, "file": rel, "handler": node.name}
                      for m in methods]
    return found


def api_routes(root: Path) -> list[dict]:
    """Every route of the routers and the server, sorted by path and method."""
    mounts = _mounts(root)
    found = _file_routes(root, SERVER_FILE, {"app": ""})
    files = sorted(p.relative_to(root).as_posix() for p in (root / ROUTES_DIR).glob("*.py"))
    for rel in files:
        for route in _file_routes(root, rel, {}):
            route["mounted"] = rel in mounts
            route["path"] = mounts.get(rel, "") + route["path"]
            found.append(route)
    for route in found:
        route.setdefault("mounted", True)
    return sorted(found, key=lambda r: (r["path"], r["method"], r["file"], r["handler"]))
