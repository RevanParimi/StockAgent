"""Config switches: the settings the code declares and their repository defaults.

A setting is declared in `settings/base.py` as
`NAME = cfg("section.key", env="ENV_NAME", fallback=X)`, sometimes wrapped in
`bool(...)` or `int(...)`. Its repository default is `config.yaml`'s value for
the key, and the code's fallback where the file has none. Production values are
not here: the curated part cites them to KT section 1.
"""
from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import yaml

from tools.architecture_map.model import sources

SETTINGS_FILE = "src/backend/shared/config/settings/base.py"
CONFIG_FILE = "config.yaml"
_NOT_CONSTANT = object()


def load_config(root: Path) -> dict:
    data = yaml.safe_load(sources.read_text(root, CONFIG_FILE))
    if not isinstance(data, dict):
        raise sources.SourceError(f"{CONFIG_FILE}: is not a mapping")
    return data


def dig(config: dict, key: str) -> tuple[bool, Any]:
    """(found, value) for a dotted key in the config mapping."""
    node: Any = config
    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            return False, None
        node = node[part]
    return True, node


def _constant(node: ast.AST) -> Any:
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError, SyntaxError):
        return _NOT_CONSTANT


def cfg_call(node: ast.AST) -> dict | None:
    """{key, env, fallback} for the first `cfg("...")` call inside `node`."""
    for call in ast.walk(node):
        if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
                and call.func.id == "cfg" and call.args):
            continue
        key = _constant(call.args[0])
        if not isinstance(key, str):
            continue
        # cfg(path, env=None, fallback=None): a missing fallback is None.
        given = dict(zip(("env", "fallback"), call.args[1:]))
        given.update({kw.arg: kw.value for kw in call.keywords if kw.arg})
        env = _constant(given["env"]) if "env" in given else None
        return {"key": key, "env": env if isinstance(env, str) else None,
                "fallback": _constant(given["fallback"]) if "fallback" in given else None}
    return None


def declared_settings(root: Path) -> dict[str, dict]:
    """{NAME: {key, env, fallback}} for every module-level cfg() setting."""
    declared: dict[str, dict] = {}
    for node in sources.parse(root, SETTINGS_FILE).body:
        if isinstance(node, ast.AnnAssign) and node.value is not None:
            targets, value = [node.target], node.value
        elif isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        else:
            continue
        call = cfg_call(value)
        if call is None:
            continue
        for target in targets:
            if isinstance(target, ast.Name):
                declared[target.id] = call
    return declared


def default_of(config: dict, call: dict) -> tuple[bool, Any]:
    """(known, value): the repository default of one cfg() declaration."""
    found, value = dig(config, call["key"])
    if found:
        return True, value
    if call["fallback"] is not _NOT_CONSTANT:
        return True, call["fallback"]
    return False, None


def is_section(value: Any) -> bool:
    """A mapping that holds mappings is a part of config.yaml, not one setting."""
    return isinstance(value, dict) and any(isinstance(v, dict) for v in value.values())


def switch_records(root: Path, keys: list[str]) -> tuple[list[dict], list[str]]:
    """Records for the named keys, sorted, and the keys that are no setting.

    A key is a setting when `config.yaml` holds it (as a value, not as a whole
    section) or the settings module reads it.
    """
    config = load_config(root)
    by_key: dict[str, dict] = {}
    for call in declared_settings(root).values():
        by_key.setdefault(call["key"], call)
    records, missing = [], []
    for key in sorted(set(keys)):
        found, value = dig(config, key)
        call = by_key.get(key)
        if (found and is_section(value)) or (not found and call is None):
            missing.append(key)
            continue
        source = CONFIG_FILE
        if not found:
            known, value = default_of(config, call)
            if not known:
                missing.append(key)
                continue
            source = "code fallback"
        records.append({"key": key, "default": value, "default_source": source,
                        "env": call["env"] if call else None})
    return records, missing
