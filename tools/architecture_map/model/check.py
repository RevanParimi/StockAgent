"""The guard: fail when the code and the map's model disagree.

    python tools/architecture_map/model/check.py

Exit 0 when the committed model.json and TREES.md match a fresh run and the
curated part names only what exists. Else exit 1 with one line per problem: the
reason, then `fix: ...`. The stamp (the commit a run was made at) is not
compared: it records what was inspected, and every commit moves it.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if __package__ in (None, ""):
    sys.path[0] = str(ROOT)          # run as a script: import from the repository root

from tools.architecture_map.model import build, trees_md          # noqa: E402

REGENERATE = ("fix: run `python tools/architecture_map/model/generate.py` and commit "
              "what it writes")


def _describe(old, new, where: str) -> str:
    """The first difference between two models, in a few words."""
    if isinstance(old, dict) and isinstance(new, dict):
        for key in sorted(set(old) | set(new)):
            if old.get(key) != new.get(key):
                return _describe(old.get(key), new.get(key), f"{where}.{key}" if where else key)
    if isinstance(old, list) and isinstance(new, list):
        before = {_label(o): o for o in old}
        after = {_label(n) for n in new}
        for item in new:
            name = _label(item)
            if name not in before:
                return f"{where}: {name} is new"
            if before[name] != item:
                return _describe(before[name], item, f"{where}[{name}]")
        for name in before:
            if name not in after:
                return f"{where}: {name} is gone"
        return f"{where}: the order or the count differs"
    short = lambda v: json.dumps(v, ensure_ascii=False)[:60]          # noqa: E731
    return f"{where}: recorded {short(old)}, found {short(new)}"


def _label(item) -> str:
    """A list entry's name in a message: a route's method and path, else its id."""
    if isinstance(item, dict):
        for key in ("path", "id", "key", "name", "from", "prefix", "text"):
            if key in item:
                return one_line(f"{item.get('method', '')} {item[key]}")[:80]
    return json.dumps(item, ensure_ascii=False)[:60]


def one_line(text: str) -> str:
    return " ".join(str(text).split())


def run(root: Path, curated_dir: Path | None = None) -> list[str]:
    """Every problem, one line each; empty when the map is true."""
    model, problems = build.build_model(root, curated_dir)
    if model is None or problems:
        return problems
    try:
        recorded_text = (root / build.MODEL_FILE).read_bytes().decode("utf-8")
        recorded = json.loads(recorded_text)
        model["stamp"] = recorded["stamp"]
        if not isinstance(model["stamp"], dict) or not isinstance(model["stamp"]["commit"], str):
            return [f"{build.MODEL_FILE} cannot be read (its stamp names no commit); "
                    f"{REGENERATE}"]
    except FileNotFoundError:
        return [f"{build.MODEL_FILE} is missing; {REGENERATE}"]
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        return [f"{build.MODEL_FILE} cannot be read ({type(exc).__name__}); {REGENERATE}"]
    if recorded_text != build.dumps(model):
        fresh = json.loads(build.dumps(model))
        detail = _describe(recorded, fresh, "") if recorded != fresh else "its bytes differ"
        return [f"{build.MODEL_FILE} is stale: {detail}; {REGENERATE}"]
    try:
        trees = (root / build.TREES_FILE).read_bytes().decode("utf-8")
    except FileNotFoundError:
        return [f"{build.TREES_FILE} is missing; {REGENERATE}"]
    except (OSError, UnicodeDecodeError) as exc:
        return [f"{build.TREES_FILE} cannot be read ({type(exc).__name__}); {REGENERATE}"]
    if trees != trees_md.render(model):
        return [f"{build.TREES_FILE} differs from the model (stale or edited by hand); "
                f"{REGENERATE}"]
    return []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    try:
        problems = run(args.root.resolve())
    except Exception as exc:          # the guard owes a line and a fix, never a traceback
        problems = [f"architecture map: cannot check ({type(exc).__name__}: {exc}); fix: "
                    "correct what it names, or report a bug in tools/architecture_map"]
    for problem in problems:
        print(one_line(problem))
    if problems:
        return 1
    print("architecture map: model.json and TREES.md match the code")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
