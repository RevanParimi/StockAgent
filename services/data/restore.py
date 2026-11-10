"""
Restore drill for nightly backups (SA-007).

An archive existing proves nothing; this restores one into an ISOLATED
directory and checks it against the manifest written when it was made:

  errors   (ok=False: the archive is not a faithful, restorable copy)
           missing or unreadable manifest, archive checksum mismatch, bad zip,
           unsafe or unexpected member, missing file, per-file checksum
           mismatch, SQLite integrity_check failure, schema digest or table
           row-count mismatch, ledger row-count mismatch.
  warnings (ok=True, clean=False: the copy is faithful, the data is suspect)
           a portfolio ledger that shrank, disappeared or was rewritten since
           the previous archive (ledgers are append-only, so its earlier bytes
           must survive unchanged); unparseable or torn ledger rows; a file
           that kept changing while it was archived.

A destination that is, contains or sits inside a protected directory (the
live data/ by default) is refused, and so is one that is not empty. Nothing
here ever writes to production state.

CLI (run it from the repository root):
  python -m services.data.restore drill ARCHIVE [--dest DIR] [--previous ARCHIVE]
  python -m services.data.restore fetch [NAME] --dest DIR
fetch downloads the newest (or the named) off-site copy, decrypts it and
drills it into DIR/restored. Exit code 0 = clean, 2 = ok with warnings,
1 = failed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from services.data.backup import (DATA_DIR, FORMAT, MANIFEST_NAME, file_digest,
                                  ledger_facts, sidecar_path, sqlite_facts)


class RestoreRefused(RuntimeError):
    """The destination is not an isolated, empty directory."""


@dataclass
class DrillResult:
    archive: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    checked: dict = field(default_factory=dict)
    restored_to: str | None = None

    @property
    def ok(self) -> bool:
        return not self.errors

    @property
    def clean(self) -> bool:
        return self.ok and not self.warnings

    def as_dict(self) -> dict:
        return {"archive": self.archive, "ok": self.ok, "clean": self.clean,
                "errors": self.errors, "warnings": self.warnings, "checked": self.checked,
                "restored_to": self.restored_to}


def check_isolated(dest: Path, protected: Iterable[Path]) -> None:
    dest = Path(dest).resolve()
    for p in protected:
        p = Path(p).resolve()
        if dest == p or p in dest.parents or dest in p.parents:
            raise RestoreRefused(f"refusing to restore into {dest}: it overlaps {p}")
    if dest.exists() and (not dest.is_dir() or any(dest.iterdir())):
        raise RestoreRefused(f"refusing to restore into {dest}: it is not an empty directory")


def _member_target(dest: Path, name: str) -> Path:
    """Where a member lands, or ValueError when it could land outside dest.
    The drill writes only regular files into an empty directory, so no
    symlink can redirect a path that passes this lexical check."""
    parts = name.split("/")
    if (not name or name.startswith("/") or any(p in ("", ".", "..") for p in parts)
            or (os.name == "nt" and (":" in name or "\\" in name))):
        raise ValueError(f"unsafe archive member {name!r}")
    return dest.joinpath(*parts)


def _read_manifest(archive: Path) -> dict | None:
    """The MANIFEST.json inside an archive, or None."""
    try:
        with zipfile.ZipFile(archive) as z:
            return json.loads(z.read(MANIFEST_NAME))
    except (OSError, KeyError, ValueError, zipfile.BadZipFile):
        return None


def _drill(archive: Path, dest: Path, previous: Path | None, result: DrillResult) -> None:
    side = sidecar_path(archive)
    if not side.exists():
        result.errors.append(f"missing manifest: {side.name} not found")
        return
    try:
        sidecar = json.loads(side.read_text(encoding="utf-8"))
    except ValueError:
        result.errors.append(f"manifest unreadable: {side.name}")
        return
    if sidecar.get("format") != FORMAT:
        result.errors.append(f"unknown manifest format {sidecar.get('format')!r}")
        return
    if not archive.is_file():
        result.errors.append(f"archive {archive.name} not found")
        return
    got = file_digest(archive)
    if (got["bytes"], got["sha256"]) != (sidecar.get("bytes"), sidecar.get("sha256")):
        result.errors.append(f"archive checksum mismatch: {got['bytes']} bytes, sha256 "
                             f"{got['sha256'][:12]} vs manifest {sidecar.get('bytes')} bytes, "
                             f"{str(sidecar.get('sha256'))[:12]} — corrupt or truncated")
        return
    try:
        z = zipfile.ZipFile(archive)
    except zipfile.BadZipFile as exc:
        result.errors.append(f"not a readable zip: {exc}")
        return

    with z:
        names = z.namelist()
        if MANIFEST_NAME not in names:
            result.errors.append(f"missing manifest: {MANIFEST_NAME} not in the archive")
            return
        manifest = json.loads(z.read(MANIFEST_NAME))
        entries = {e["path"]: e for e in manifest.get("files", [])}
        if len(entries) != sidecar.get("files"):
            result.errors.append(f"manifest lists {len(entries)} files, sidecar says "
                                 f"{sidecar.get('files')}")
        members = [n for n in names if n != MANIFEST_NAME]
        if len(members) != len(set(members)):
            result.errors.append("archive has duplicate members")
        for name in sorted(set(members) - set(entries)):
            result.errors.append(f"unexpected member {name!r} (not in the manifest)")
        for name in sorted(set(entries) - set(members)):
            result.errors.append(f"{name}: in the manifest but missing from the archive")
        dest.mkdir(parents=True, exist_ok=True)
        for name in sorted(set(members) & set(entries)):
            try:
                target = _member_target(dest, name)
            except ValueError as exc:
                result.errors.append(str(exc))
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(name) as src, open(target, "wb") as out:
                while chunk := src.read(1024 * 1024):
                    out.write(chunk)

    rows, dbs, ledgers = 0, 0, 0
    for path, entry in sorted(entries.items()):
        try:
            restored = _member_target(dest, path)
        except ValueError:
            continue                                  # already reported
        if not restored.is_file():
            continue
        got = file_digest(restored)
        if (got["bytes"], got["sha256"]) != (entry.get("bytes"), entry.get("sha256")):
            result.errors.append(f"{path}: checksum mismatch after restore")
            continue
        if entry.get("unstable"):
            result.warnings.append(f"{path}: kept changing while it was archived")
        if entry.get("kind") == "sqlite":
            dbs += 1
            facts = sqlite_facts(restored)
            if facts["integrity"] != "ok":
                result.errors.append(f"{path}: integrity_check {facts['integrity'][:200]}")
            if facts["schema_sha256"] != entry.get("schema_sha256"):
                result.errors.append(f"{path}: schema differs from the manifest")
            want = entry.get("tables") or {}
            for table in sorted(set(want) | set(facts["tables"])):
                if facts["tables"].get(table) != want.get(table):
                    result.errors.append(f"{path}: table {table} has "
                                         f"{facts['tables'].get(table)} rows, manifest says "
                                         f"{want.get(table)}")
            rows += sum(n for n in facts["tables"].values() if n)
        elif entry.get("kind") == "ledger":
            ledgers += 1
            facts = ledger_facts(restored.read_bytes())
            if facts["rows"] != entry.get("rows"):
                result.errors.append(f"{path}: {facts['rows']} rows, manifest says "
                                     f"{entry.get('rows')}")
            if facts["bad_rows"]:
                result.warnings.append(f"{path}: {facts['bad_rows']} row(s) are not JSON "
                                       f"objects (first at line {facts['first_bad_line']})")
            if facts["torn_tail"]:
                result.warnings.append(f"{path}: the last row has no newline (torn write)")
    result.checked.update({"files": len(entries), "sqlite_dbs": dbs, "sqlite_rows": rows,
                           "ledgers": ledgers})
    if previous is not None:
        _continuity(previous, entries, dest, result)


def _continuity(previous: Path, entries: dict, dest: Path, result: DrillResult) -> None:
    """Every ledger in the previous archive must still start with the same
    bytes: append-only means history is only ever extended."""
    prior = _read_manifest(previous)
    if prior is None:
        result.checked["continuity"] = f"not checked: {previous.name} has no readable manifest"
        return
    prior_ledgers = [e for e in prior.get("files", []) if e.get("kind") == "ledger"]
    for old in prior_ledgers:
        path = old["path"]
        cur = entries.get(path)
        if cur is None:
            result.warnings.append(f"ledger {path} disappeared since {previous.name}")
            continue
        if cur["bytes"] < old["bytes"]:
            result.warnings.append(f"ledger {path} shrank from {old['bytes']} to "
                                   f"{cur['bytes']} bytes since {previous.name}")
            continue
        try:
            with open(_member_target(dest, path), "rb") as fh:
                head = fh.read(old["bytes"])
        except (OSError, ValueError):
            continue                                  # not restored: already an error
        if hashlib.sha256(head).hexdigest() != old["sha256"]:
            result.warnings.append(f"ledger {path} was rewritten since {previous.name}: "
                                   f"its first {old['bytes']} bytes changed")
    result.checked["continuity"] = f"{len(prior_ledgers)} ledger(s) checked against {previous.name}"


def verify_archive(archive: Path, dest: Path | None = None, *, previous: Path | None = None,
                   protected: Iterable[Path] = (DATA_DIR,)) -> DrillResult:
    """Restore `archive` into `dest` (a fresh temporary directory when None)
    and check it. Never raises; a refused destination or an unexpected
    failure is an error in the result."""
    archive = Path(archive)
    result = DrillResult(archive.name)
    try:
        if dest is None:
            with tempfile.TemporaryDirectory(prefix="stockagent-drill-") as td:
                target = Path(td) / "restored"
                check_isolated(target, protected)
                _drill(archive, target, previous, result)
        else:
            dest = Path(dest)
            check_isolated(dest, protected)
            _drill(archive, dest, previous, result)
            result.restored_to = str(dest)
    except Exception as exc:
        result.errors.append(f"drill aborted: {type(exc).__name__}: {exc}")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m services.data.restore",
                                     description="Restore a StockAgent backup into an "
                                                 "isolated directory and verify it.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    drill = sub.add_parser("drill", help="verify a local archive")
    drill.add_argument("archive")
    drill.add_argument("--dest", help="empty directory to restore into (default: a "
                                      "temporary one, deleted afterwards)")
    drill.add_argument("--previous", help="the archive before it, for ledger continuity")
    fetch = sub.add_parser("fetch", help="download, decrypt and verify an off-site copy")
    fetch.add_argument("name", nargs="?", help="archive name (default: the newest)")
    fetch.add_argument("--dest", required=True, help="empty directory for the download "
                                                     "and the restored tree")
    args = parser.parse_args(argv)

    if args.cmd == "drill":
        result = verify_archive(Path(args.archive), Path(args.dest) if args.dest else None,
                                previous=Path(args.previous) if args.previous else None)
    else:
        from services.data import offsite
        dest = Path(args.dest)
        try:
            check_isolated(dest, (DATA_DIR,))
            archive = offsite.fetch(args.name, dest / "download", offsite.config_from_settings(),
                                    data_dir=DATA_DIR)
        except (RestoreRefused, offsite.OffsiteError) as exc:
            print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
            return 1
        result = verify_archive(archive, dest / "restored")
    print(json.dumps(result.as_dict(), indent=2))
    return 0 if result.clean else (2 if result.ok else 1)


if __name__ == "__main__":
    sys.exit(main())
