"""The model: the generated facts and the curated meaning, in one mapping."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from tools.architecture_map.model import (curated, imports, jobs, routes, sources, switches,
                                          validate)

SCHEMA = 1
OUT_DIR = "docs/architecture-map"
MODEL_FILE = f"{OUT_DIR}/model.json"
TREES_FILE = f"{OUT_DIR}/TREES.md"
# What the generated part reads: changes here make the stamp "dirty".
INPUTS = (*sources.CODE_ROOTS, switches.CONFIG_FILE)


def commit_stamp(root: Path) -> dict:
    """The commit the code was read at, and whether the code differed from it."""
    unknown = {"commit": "unknown", "uncommitted_code": None}
    if not (root / ".git").exists():
        return unknown
    try:
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True,
                              text=True, check=True).stdout.strip()
        status = subprocess.run(["git", "status", "--porcelain", "--", *INPUTS], cwd=root,
                                capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return unknown
    return {"commit": head, "uncommitted_code": bool(status)}


def _curated_owners(modules: list[dict], shared: dict) -> list[tuple[str, list[str]]]:
    owners = [(m["id"], m["files"]) for m in modules]
    owners += [(s["id"], s["files"]) for m in modules for s in m["submodules"]]
    return owners + [("shared", shared.get("files") or [])]


def _config_keys(data: dict, generated_jobs: list[dict]) -> list[str]:
    keys = [k for m in data["modules"] for s in m["submodules"] for k in s["config"]]
    keys += [p["key"] for p in data["production"] if isinstance(p, dict) and p.get("key")]
    keys += [g.removeprefix("not ") for j in generated_jobs for g in j["gates"]]
    return keys


def _reference_lists(data: dict, problems: list[str]) -> dict[str, list[dict]]:
    """The list files with their entries' shapes checked."""
    trace = data["trace"]
    groups = {}
    for kind, keys, optional in (
            ("traces", {"when": "text", "text": "text", "refs": "texts"}, {"flows": "texts"}),
            ("tours", {"preset": "text", "caption": "text"}, {"ref": "text"})):
        where = f"curated/trace.yaml {kind}"
        groups[kind] = validate.shaped(
            validate.as_list(trace.get(kind), where, problems),
            {"id": "text", "title": "text", "steps": "list"}, where, problems)
        if len(groups[kind]) > 1:
            problems.append(f"{where} has {len(groups[kind])} entries and the map plays one; "
                            "fix: keep one")
        for entry in groups[kind]:
            if not entry["steps"]:
                problems.append(f"{where} {entry['id']} has no steps; fix: write them")
            entry["steps"] = validate.shaped(entry["steps"], keys,
                                             f"{where} {entry['id']} steps", problems, optional)
    return {
        "externals": validate.shaped(
            validate.as_list(data["overview"].get("externals"), "curated/overview.yaml externals",
                             problems),
            {"id": "text", "name": "text"}, "curated/overview.yaml externals", problems),
        "stores": validate.shaped(
            data["stores"], {"id": "text", "name": "text", "path": "text", "holds": "text",
                             "writers": "texts", "readers": "texts"},
            "curated/stores.yaml", problems, {"code": "texts"}),
        "flows": validate.shaped(data["flows"], {"from": "text", "to": "text", "what": "text"},
                                 "curated/flows.yaml", problems),
        "routes": validate.shaped(data["routes"], {"prefix": "text", "module": "text"},
                                  "curated/routes.yaml", problems),
        # check_production says what is wrong with a value, a source or a date
        "production": validate.shaped(
            data["production"], {"value": "any", "source": "any", "as_of": "any"},
            "curated/production.yaml", problems,
            {"key": "text", "name": "text", "note": "text"}),
        **groups,
    }


def _code_map(entries, problems: list[str], where: str) -> list[tuple[str, str]]:
    """(label, path) pairs of the code map, for the existence check."""
    found: list[tuple[str, str]] = []
    checked = validate.shaped(
        validate.as_list(entries, f"{where} code_map", problems), {"path": "text", "note": "text"},
        f"{where} code_map", problems, {"children": "list", "runtime": "flag"})
    for entry in checked:
        if not entry.get("runtime"):
            found.append((where, entry["path"]))
        found += _code_map(entry.get("children"), problems, where)
    return found


def build_model(root: Path, curated_dir: Path | None = None,
                stamp: dict | None = None) -> tuple[dict | None, list[str]]:
    """(model, problems). The model is None when it cannot be built; with
    problems it must not be written."""
    data, problems = curated.load(root, curated_dir)
    if data is None:
        return None, problems
    try:
        return _assemble(root, data, problems, stamp)
    except sources.SourceError as exc:
        problems.append(f"{exc}; fix: correct the source or teach "
                        "tools/architecture_map/model to read it")
        return None, problems


def _assemble(root: Path, data: dict, problems: list[str],
              stamp: dict | None) -> tuple[dict | None, list[str]]:
    lists = _reference_lists(data, problems)
    map_paths = _code_map(data["overview"].get("code_map"), problems, "curated/overview.yaml")
    if problems:
        return None, problems
    modules, shared = data["modules"], data["shared"]
    module_ids = {m["id"] for m in modules} | {s["id"] for m in modules for s in m["submodules"]}

    job_list = jobs.scheduled_jobs(root)
    route_list = routes.api_routes(root)
    graph = imports.import_graph(root)
    python = [f["path"] for f in graph]
    records, missing_keys = switches.switch_records(root, _config_keys(
        {"modules": modules, "production": lists["production"]}, job_list))

    owners = _curated_owners(modules, shared)
    validate.check_paths(root, python,
                         owners + [(where, [path]) for where, path in map_paths], problems)
    ownership = validate.own_files(python, owners, problems)
    refs = [(s["id"], r) for m in modules for s in m["submodules"] for r in s["code"]]
    refs += [(s["id"], r) for s in lists["stores"] for r in s.get("code", [])]
    validate.check_code(root, set(python), refs, problems)
    config = switches.load_config(root)
    for key in missing_keys:
        reason = ("is a whole section of config.yaml, not one setting"
                  if switches.dig(config, key)[0] else
                  "does not exist in config.yaml or the settings")
        problems.append(f"the curated config key {key} {reason}; fix: correct or remove it")
    store_ids = {s["id"] for s in lists["stores"]}
    external_ids = {e["id"] for e in lists["externals"]}
    job_ids = {j["id"] for j in job_list}
    all_ids = module_ids | store_ids | external_ids
    flow_keys = {f"{f['from']}>{f['to']}" for f in lists["flows"]}
    validate.check_jobs(job_list, data["jobs"], module_ids, all_ids, flow_keys, problems)
    validate.check_routes(route_list, lists["routes"], module_ids, problems)

    validate.check_refs([(f"curated/stores.yaml {s['id']} {side}", name)
                         for s in lists["stores"] for side in ("writers", "readers")
                         for name in s[side] or []], module_ids | external_ids, problems)
    validate.check_refs([(f"curated/flows.yaml {f['from']} -> {f['to']}", f[end])
                         for f in lists["flows"] for end in ("from", "to")], all_ids, problems)
    validate.check_traces(lists["traces"], {j: data["jobs"].get(j) for j in job_ids}, all_ids,
                          flow_keys, problems)
    validate.check_tours(lists["tours"], job_ids, module_ids, all_ids, problems)
    validate.check_production(lists["production"], problems)
    if problems:
        return None, problems

    owned_by: dict[str, list[str]] = {}
    for path, owner in ownership.items():
        owned_by.setdefault(owner, []).append(path)
    model_modules = []
    for module in modules:
        subs = [{**s, "python_files": sorted(owned_by.get(s["id"], []))}
                for s in module["submodules"]]
        model_modules.append({**module, "submodules": subs,
                              "python_files": sorted(owned_by.get(module["id"], []))})
    model = {
        "schema": SCHEMA,
        "stamp": stamp if stamp is not None else commit_stamp(root),
        "title": data["overview"]["title"],
        "product": data["overview"]["product"],
        "reading": data["overview"]["reading"],
        "clock_note": data["overview"]["clock_note"],
        "code_map": data["overview"].get("code_map") or [],
        "modules": model_modules,
        "shared": {"files": shared.get("files") or [],
                   "python_files": sorted(owned_by.get("shared", []))},
        "externals": lists["externals"],
        "stores": lists["stores"],
        "flows": lists["flows"],
        "traces": lists["traces"],
        "tours": lists["tours"],
        "production": [{**p, "as_of": str(p["as_of"])} for p in lists["production"]],
        "jobs": [{**job, **data["jobs"][job["id"]],
                  "schedule": jobs.describe_schedule(job["cron"])} for job in job_list],
        "routes": [{**r, "module": validate.route_rule(r["path"], lists["routes"])["module"]}
                   for r in route_list],
        "files": [{**f, "owner": ownership[f["path"]]} for f in graph],
        "switches": records,
    }
    return model, problems


def dumps(model: dict) -> str:
    """The model's bytes: stable key order, so two runs write the same file."""
    return json.dumps(model, indent=1, sort_keys=True, ensure_ascii=False) + "\n"
