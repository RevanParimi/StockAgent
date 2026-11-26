"""Write docs/architecture-map/model.json and TREES.md from the code and curated/.

    python tools/architecture_map/model/generate.py

Run it after any change to the code, to `config.yaml` or to the curated files,
and commit what it writes. It writes nothing when the curated part names
something the code does not have.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if __package__ in (None, ""):
    sys.path[0] = str(ROOT)          # run as a script: import from the repository root

from tools.architecture_map.model import build, trees_md          # noqa: E402


def write(root: Path, curated_dir: Path | None = None) -> list[str]:
    """Write both files; return the problems that stopped it (empty when written)."""
    model, problems = build.build_model(root, curated_dir)
    if model is None or problems:
        return problems
    out = root / build.OUT_DIR
    out.mkdir(parents=True, exist_ok=True)
    for name, text in ((build.MODEL_FILE, build.dumps(model)),
                       (build.TREES_FILE, trees_md.render(model))):
        (root / name).write_bytes(text.encode("utf-8"))
    return []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    try:
        problems = write(args.root.resolve())
    except Exception as exc:          # a line and a fix, never a traceback
        problems = [f"architecture map: cannot generate ({type(exc).__name__}: {exc}); fix: "
                    "correct what it names, or report a bug in tools/architecture_map"]
    for problem in problems:
        print(" ".join(problem.split()))
    if problems:
        print(f"nothing written: {len(problems)} problem(s)")
        return 1
    print(f"wrote {build.MODEL_FILE} and {build.TREES_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
