"""Loading the curated part: meaning the code cannot state itself.

`curated/` holds one file per module under `modules/`, and one file each for the
overview, stores, flows, jobs, routes, production values, traces and the files
no module owns. This reader checks each file's shape; validate.py checks that
what it names exists.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

from tools.architecture_map.model import tree

CURATED_DIR = "tools/architecture_map/model/curated"
PLANES = ("top", "middle", "bottom", "ring", "base")
MODULE_ID = re.compile(r"^M\d+$")
# file name -> the type its content must have
FILES = {
    "overview.yaml": dict, "stores.yaml": list, "flows.yaml": list, "jobs.yaml": dict,
    "routes.yaml": list, "production.yaml": list, "trace.yaml": dict, "shared.yaml": dict,
}
MODULE_KEYS = {"id", "name", "short", "plane", "column", "summary", "files", "submodules"}
SUBMODULE_KEYS = {"id", "name", "summary", "files", "code", "config", "logic"}
# the mapping files: keys that must be text, and every key allowed
MAPPINGS = {
    "overview": (("title", "product", "reading", "clock_note"),
                 {"title", "product", "reading", "clock_note", "externals", "code_map"}),
    "trace": ((), {"traces", "tours"}),
    "shared": ((), {"files"}),
}


def _is_text(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _mappings(found: dict, label_root: str, problems: list[str]) -> None:
    for name, (texts, allowed) in MAPPINGS.items():
        data = found.get(name)
        if data is None:
            continue
        label = f"{label_root}/{name}.yaml"
        unknown = [str(k) for k in data if k not in allowed]
        if unknown:
            problems.append(f"{label} has unknown keys {sorted(unknown)}; fix: correct the YAML")
        for key in texts:
            if not _is_text(data.get(key)):
                problems.append(f"{label}: {key} must be text; fix: write it")
    if found.get("shared") is not None:
        found["shared"] = {"files": _strings(found["shared"].get("files"),
                                             f"{label_root}/shared.yaml: files", problems)}
    for job_id in found.get("jobs") or {}:
        if not _is_text(job_id):
            problems.append(f"{label_root}/jobs.yaml: the job name {job_id!r} is not text; "
                            "fix: correct the YAML")


def _read(path: Path, kind: type, label: str, problems: list[str]):
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        problems.append(f"{label} is missing; fix: add the curated file")
        return None
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        first = str(exc).split("\n")[0]
        problems.append(f"{label} cannot be read ({first}); fix: correct the YAML")
        return None
    if not isinstance(data, kind):
        problems.append(f"{label} holds a {type(data).__name__}, not a {kind.__name__}; "
                        "fix: correct the YAML")
        return None
    return data


def _strings(value, label: str, problems: list[str]) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(_is_text(v) for v in value):
        problems.append(f"{label} must be a list of strings; fix: correct the YAML")
        return []
    return value


def _module(data: dict, label: str, problems: list[str]) -> dict | None:
    unknown = set(data) - MODULE_KEYS
    missing = {"id", "name", "short", "plane", "column", "summary", "submodules"} - set(data)
    if unknown or missing:
        problems.append(f"{label} has unknown keys {sorted(unknown)} or lacks {sorted(missing)}; "
                        "fix: correct the YAML")
        return None
    if not MODULE_ID.match(str(data["id"])):
        problems.append(f"{label}: id {data['id']!r} is not M<number>; fix: correct the id")
        return None
    for key in ("name", "short", "summary"):
        if not _is_text(data[key]):
            problems.append(f"{label}: {key} must be text; fix: write it")
            return None
    if data["plane"] not in PLANES:
        problems.append(f"{label}: plane {data['plane']!r} is not one of {', '.join(PLANES)}; "
                        "fix: correct the plane")
    if not isinstance(data["column"], int) or isinstance(data["column"], bool):
        problems.append(f"{label}: column must be a whole number; fix: correct it")
    if not isinstance(data["submodules"], list) or not data["submodules"]:
        problems.append(f"{label}: needs at least one sub-module; fix: add one")
        return None
    module = {**data, "files": _strings(data.get("files"), f"{label}: files", problems),
              "submodules": []}
    for sub in data["submodules"]:
        if not isinstance(sub, dict):
            problems.append(f"{label}: a sub-module is not a mapping; fix: correct the YAML")
            continue
        unknown = set(sub) - SUBMODULE_KEYS
        missing = {"id", "name", "summary", "logic"} - set(sub)
        where = f"{label}: sub-module {sub.get('id', '?')}"
        if unknown or missing:
            problems.append(f"{where} has unknown keys {sorted(unknown)} or lacks "
                            f"{sorted(missing)}; fix: correct the YAML")
            continue
        if not re.match(rf"^{data['id']}\.\d+$", str(sub["id"])):
            problems.append(f"{where}: id is not {data['id']}.<number>; fix: correct the id")
            continue
        wrong = [key for key in ("name", "summary", "logic") if not _is_text(sub[key])]
        if wrong:
            problems.append(f"{where}: {', '.join(wrong)} must be text; fix: write it")
            continue
        try:
            logic = tree.parse_tree(sub["logic"])
        except tree.TreeError as exc:
            problems.append(f"{where}: logic tree {exc}; fix: correct the tree")
            continue
        if not logic:
            problems.append(f"{where}: the logic tree is empty; fix: write it")
            continue
        module["submodules"].append({
            **sub, "logic": logic,
            "files": _strings(sub.get("files"), f"{where}: files", problems),
            "code": _strings(sub.get("code"), f"{where}: code", problems),
            "config": _strings(sub.get("config"), f"{where}: config", problems),
        })
    return module


def load(root: Path, curated_dir: Path | None = None) -> tuple[dict | None, list[str]]:
    """(curated data, problems). The data is None when any file cannot be used."""
    folder = curated_dir or root / CURATED_DIR
    label_root = CURATED_DIR if curated_dir is None else str(folder)
    problems: list[str] = []
    found: dict = {}
    for name, kind in FILES.items():
        found[name[:-len(".yaml")]] = _read(folder / name, kind, f"{label_root}/{name}", problems)
    modules = []
    paths = sorted((folder / "modules").glob("*.yaml"))
    if not paths:
        problems.append(f"{label_root}/modules/ holds no module file; fix: add them")
    for path in paths:
        label = f"{label_root}/modules/{path.name}"
        data = _read(path, dict, label, problems)
        module = _module(data, label, problems) if data is not None else None
        if module is not None:
            modules.append(module)
    modules.sort(key=lambda m: int(m["id"][1:]))
    ids = [m["id"] for m in modules] + [s["id"] for m in modules for s in m["submodules"]]
    for identifier in sorted({i for i in ids if ids.count(i) > 1}):
        problems.append(f"id {identifier} is used twice; fix: give each module its own id")
    _mappings(found, label_root, problems)
    if any(value is None for value in found.values()):
        return None, problems
    found["modules"] = modules
    return (None if problems else found), problems
