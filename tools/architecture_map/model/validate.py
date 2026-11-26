"""Does the curated part describe the code that exists?

Every function returns problems as one-line strings: the reason, then
`fix: ...`. Nothing here raises on a curation mistake.
"""
from __future__ import annotations

import ast
import re
from datetime import date
from pathlib import Path

from tools.architecture_map.model import sources

PRODUCTION_SOURCE = "KT section 1"
_WILDCARD = re.compile(r"[*?]")


def glob_regex(pattern: str) -> re.Pattern:
    """`*` is one path segment's text, `**` any depth, `**/` zero or more folders."""
    out, position = [], 0
    while position < len(pattern):
        if pattern.startswith("**/", position):
            out.append("(?:.*/)?")
            position += 3
        elif pattern.startswith("**", position):
            out.append(".*")
            position += 2
        elif pattern[position] == "*":
            out.append("[^/]*")
            position += 1
        elif pattern[position] == "?":
            out.append("[^/]")
            position += 1
        else:
            out.append(re.escape(pattern[position]))
            position += 1
    return re.compile("^" + "".join(out) + "$")


def is_text(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


# value kind -> (check, what a message asks for)
KINDS = {
    "text": (is_text, "text"),
    "texts": (lambda v: isinstance(v, list) and all(is_text(x) for x in v), "a list of texts"),
    "list": (lambda v: isinstance(v, list), "a list"),
    "flag": (lambda v: isinstance(v, bool), "true or false"),
    "any": (lambda v: True, "a value"),
}


def as_list(value, label: str, problems: list[str]) -> list:
    """The value when it is a list ([] for nothing); report anything else."""
    if value is None or isinstance(value, list):
        return value or []
    problems.append(f"{label} must be a list; fix: correct the YAML")
    return []


def shaped(entries: list, keys: dict[str, str], label: str, problems: list[str],
           optional: dict[str, str] | None = None) -> list[dict]:
    """The entries that are mappings with these keys, each value of its kind
    (`KINDS`); report the others."""
    optional = optional or {}
    good = []
    for number, entry in enumerate(entries, start=1):
        if (not isinstance(entry, dict) or set(keys) - set(entry)
                or set(entry) - set(keys) - set(optional)):
            problems.append(f"{label} entry {number} must have the keys {sorted(keys)}"
                            f"{' and may have ' + str(sorted(optional)) if optional else ''}; "
                            "fix: correct the YAML")
            continue
        bad = [f"{name} must be {KINDS[kind][1]}"
               for name, kind in {**keys, **optional}.items()
               if name in entry and not KINDS[kind][0](entry[name])]
        if bad:
            problems.append(f"{label} entry {number}: {', '.join(bad)}; fix: correct the YAML")
        else:
            good.append(entry)
    return good


def in_repository(path: str) -> bool:
    """A forward-slash path below the repository root."""
    return (bool(path) and not path.startswith("/") and "\\" not in path
            and ".." not in path.split("/") and ":" not in path)


# -- files and functions ------------------------------------------------------

def check_paths(root: Path, python: list[str], owners: list[tuple[str, list[str]]],
                problems: list[str]) -> None:
    """Every curated file entry names something that exists."""
    for owner, patterns in owners:
        for pattern in patterns:
            if not in_repository(pattern):
                problems.append(f"{owner}: {pattern} is not a path inside the repository; "
                                "fix: write it from the repository root")
            elif _WILDCARD.search(pattern):
                regex = glob_regex(pattern)
                found = any(regex.match(p) for p in python) or (
                    not pattern.endswith(".py") and any(root.glob(pattern)))
                if not found:
                    problems.append(f"{owner}: the file pattern {pattern} matches nothing; "
                                    "fix: correct or remove it")
            elif not (root / pattern).exists():
                problems.append(f"{owner}: the path {pattern} does not exist; "
                                "fix: correct or remove it")


def own_files(python: list[str], owners: list[tuple[str, list[str]]],
              problems: list[str]) -> dict[str, str]:
    """{python file: owner}. An exact path beats a pattern; a sub-module beats
    its own module; two other owners is an error, and so is none."""
    compiled = [(owner, pattern, glob_regex(pattern), not _WILDCARD.search(pattern))
                for owner, patterns in owners for pattern in patterns]
    result: dict[str, str] = {}
    for path in python:
        matches = [(owner, exact) for owner, _, regex, exact in compiled if regex.match(path)]
        if any(exact for _, exact in matches):
            matches = [m for m in matches if m[1]]
        claimed = {owner for owner, _ in matches}
        claimed -= {owner.split(".")[0] for owner in claimed if "." in owner}
        if not claimed:
            problems.append(f"{path} belongs to no module; fix: add it to a module's or "
                            "shared.yaml's files in curated/")
        elif len(claimed) > 1:
            problems.append(f"{path} is claimed by {' and '.join(sorted(claimed))}; "
                            "fix: name it in one of them only")
        else:
            result[path] = claimed.pop()
    return result


def defined_names(tree: ast.Module) -> set[str]:
    """Functions, classes and assigned names, with `Class.method` for members."""
    names: set[str] = set()

    def visit(body: list[ast.stmt], prefix: str) -> None:
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.add(prefix + node.name)
                if isinstance(node, ast.ClassDef):
                    visit(node.body, prefix + node.name + ".")
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                names.update(prefix + t.id for t in targets if isinstance(t, ast.Name))
            elif isinstance(node, (ast.If, ast.Try)):
                visit(node.body, prefix)
                visit(getattr(node, "orelse", []), prefix)
                for handler in getattr(node, "handlers", []):
                    visit(handler.body, prefix)

    visit(tree.body, "")
    return names


def check_code(root: Path, python: set[str], refs: list[tuple[str, str]],
               problems: list[str]) -> None:
    """Every `path::name` reference names a definition in that file."""
    cache: dict[str, set[str]] = {}
    for owner, ref in refs:
        path, separator, name = ref.partition("::")
        if not separator or not name:
            problems.append(f"{owner}: code reference {ref} is not path::name; fix: correct it")
        elif not in_repository(path) or path not in python:
            problems.append(f"{owner}: the file {path} does not exist; fix: correct or remove it")
        else:
            if path not in cache:
                cache[path] = defined_names(sources.parse(root, path))
            if name not in cache[path]:
                problems.append(f"{owner}: {path} defines no {name}; "
                                "fix: name the current function or remove it")


# -- jobs, routes, references -------------------------------------------------

def check_jobs(jobs: list[dict], curated: dict, module_ids: set[str],
               problems: list[str]) -> None:
    known = {job["id"] for job in jobs}
    for job_id in sorted(known - set(curated)):
        problems.append(f"job {job_id} belongs to no module; fix: add it to curated/jobs.yaml")
    for job_id, entry in curated.items():
        if job_id not in known:
            problems.append(f"curated/jobs.yaml names the job {job_id} that scheduler.py does "
                            "not register; fix: remove or rename it")
        if (not isinstance(entry, dict) or set(entry) != {"module", "does"}
                or not all(is_text(v) for v in entry.values())):
            problems.append(f"curated/jobs.yaml {job_id} must have module and does, both text; "
                            "fix: correct the entry")
        elif entry["module"] not in module_ids:
            problems.append(f"curated/jobs.yaml {job_id}: module {entry['module']} is not in "
                            "the model; fix: name an existing module")


def route_rule(path: str, rules: list[dict]) -> dict | None:
    """The rule with the longest prefix that holds this route path."""
    best = None
    for rule in rules:
        prefix = str(rule["prefix"])
        if path == prefix or path.startswith(prefix.rstrip("/") + "/"):
            if best is None or len(prefix) > len(str(best["prefix"])):
                best = rule
    return best


def check_routes(routes: list[dict], rules: list[dict], module_ids: set[str],
                 problems: list[str]) -> None:
    used: set[str] = set()
    for rule in rules:
        if str(rule["prefix"]) in ("", "/"):
            problems.append("curated/routes.yaml has a catch-all prefix, which would hide a new "
                            "router; fix: name each router's prefix")
        if rule["module"] not in module_ids:
            problems.append(f"curated/routes.yaml {rule['prefix']}: module {rule['module']} is "
                            "not in the model; fix: name an existing module")
    for route in routes:
        rule = route_rule(route["path"], rules)
        if rule is None:
            problems.append(f"route {route['method']} {route['path']} ({route['file']}) belongs "
                            "to no module; fix: add its prefix to curated/routes.yaml")
        else:
            used.add(str(rule["prefix"]))
    for rule in rules:
        if str(rule["prefix"]) not in used:
            problems.append(f"curated/routes.yaml prefix {rule['prefix']} matches no route; "
                            "fix: remove or correct it")


def check_refs(refs: list[tuple[str, str]], known: set[str], problems: list[str]) -> None:
    for where, name in refs:
        if name not in known:
            problems.append(f"{where} names {name}, which the model lacks; "
                            "fix: name an existing id")


def check_production(entries: list[dict], problems: list[str]) -> None:
    seen: set[str] = set()
    for entry in entries:
        name = str(entry.get("key") or entry.get("name") or "")
        label = f"curated/production.yaml {name or 'entry'}"
        if not name:
            problems.append(f"{label} needs a key or a name; fix: add one")
        elif name in seen:
            problems.append(f"{label} is given twice; fix: keep one")
        seen.add(name)
        if entry.get("source") != PRODUCTION_SOURCE:
            problems.append(f"{label} cites no source ({entry.get('source')!r}); fix: set "
                            f"source: {PRODUCTION_SOURCE} and take the value from it")
        try:
            date.fromisoformat(str(entry.get("as_of")))
        except ValueError:
            problems.append(f"{label}: as_of {entry.get('as_of')!r} is not a date; "
                            "fix: write YYYY-MM-DD")
        if entry.get("value") in (None, ""):
            problems.append(f"{label} has no value; fix: add it or remove the entry")
