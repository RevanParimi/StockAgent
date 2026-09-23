"""Write or verify a review-input manifest in committed-blob terms.

    python scripts/docs/kt_manifest.py write  MANIFEST PATH... [--meta JSON]
    python scripts/docs/kt_manifest.py verify MANIFEST [--rev REV]

Each file is recorded twice over the SAME bytes -- the blob git stores after
`.gitattributes` normalization (CRLF -> LF for text; binary unchanged):

- `git_blob`: `git hash-object PATH`. Compare directly with
  `git rev-parse REV:PATH` at any commit; no line-ending convention involved.
- `sha256`: SHA-256 of those blob bytes, i.e. `git cat-file blob REV:PATH | sha256sum`.

`write` refuses to record a file unless the bytes it hashed reproduce git's
blob id, so the SHA-256 provably covers what git stores. `verify` without
`--rev` recomputes both values from the working tree. With `--rev` it compares
`git_blob` with `git rev-parse REV:PATH`. That is git's own content identity,
and it avoids reading blob bodies: on this OneDrive checkout,
`git cat-file blob` hangs on the PDF. The manifest's own digest (the
review-input digest) is SHA-256 of its LF bytes; the file is always written
with LF.

Read-only apart from writing MANIFEST: `git hash-object` is run without `-w`.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, check=True,
                          timeout=60).stdout.decode("utf-8").strip()


def _blob_oid(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def worktree_entry(path: str) -> dict:
    oid = _git("hash-object", "--", path)
    raw = (ROOT / path).read_bytes()
    for candidate in (raw, raw.replace(b"\r\n", b"\n")):
        if _blob_oid(candidate) == oid:
            return {"path": path, "git_blob": oid, "sha256": hashlib.sha256(candidate).hexdigest()}
    raise SystemExit(f"{path}: cannot reproduce git's blob id from its bytes; refusing to record it")


def revision_blob(path: str, rev: str) -> str:
    return _git("rev-parse", "--verify", "--quiet", f"{rev}:{path}")


def write(manifest: Path, paths: list[str], meta: dict) -> None:
    body = dict(meta)
    body["hash_convention"] = ("git blob bytes after .gitattributes normalization (CRLF->LF for text, "
                               "binary unchanged); verify with scripts/docs/kt_manifest.py verify")
    body["files"] = [worktree_entry(p) for p in sorted(set(paths))]
    text = json.dumps(body, indent=2, ensure_ascii=False) + "\n"
    manifest.write_bytes(text.encode("utf-8"))
    print(json.dumps({"manifest": str(manifest), "files": len(body["files"]),
                      "review_input_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}, indent=2))


def verify(manifest: Path, rev: str | None) -> None:
    raw = manifest.read_bytes()
    recorded = json.loads(raw)
    mismatches = []
    for entry in recorded["files"]:
        try:
            if rev:
                same = revision_blob(entry["path"], rev) == entry["git_blob"]
            else:
                actual = worktree_entry(entry["path"])
                same = (actual["git_blob"], actual["sha256"]) == (entry["git_blob"], entry["sha256"])
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
            mismatches.append({"path": entry["path"], "problem": "missing"})
            continue
        if not same:
            mismatches.append({"path": entry["path"], "problem": "changed"})
    print(json.dumps({"manifest": str(manifest), "against": rev or "working tree",
                      "files": len(recorded["files"]), "mismatches": mismatches,
                      "review_input_sha256": hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()},
                     indent=2))
    if mismatches:
        raise SystemExit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    w = sub.add_parser("write")
    w.add_argument("manifest", type=Path)
    w.add_argument("paths", nargs="+")
    w.add_argument("--meta", default="{}", help="JSON object of fields recorded before 'files'")
    v = sub.add_parser("verify")
    v.add_argument("manifest", type=Path)
    v.add_argument("--rev")
    args = parser.parse_args()
    if args.command == "write":
        write(args.manifest, args.paths, json.loads(args.meta))
    else:
        verify(args.manifest, args.rev)


if __name__ == "__main__":
    sys.exit(main())
