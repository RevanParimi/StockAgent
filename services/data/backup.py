"""
Nightly data/ backup (AUD-088, SA-007).

The Railway volume is the ONLY home of the trade ledgers (portfolio.json,
transactions.jsonl, value_history), the RL predictions tree and the SQLite
stores (users, atlas, chat, telemetry, scores). This module zips the
non-rebuildable state and keeps a small local rotation under data/backups/
(guards against app-level corruption / fat-fingered writes). Caches are
excluded — they rebuild themselves.

SA-007 made each archive independently recoverable:
  * every SQLite file (found by its header, not by name) is copied through the
    sqlite3 backup API, so committed WAL pages are included; -wal/-shm/-journal
    side files are never copied raw;
  * MANIFEST.json inside the zip records each file's size and SHA-256, each
    database's integrity_check, schema digest and per-table row counts, and
    each portfolio ledger's row count; a sidecar <archive>.manifest.json
    beside it records the archive's own size and SHA-256;
  * the nightly job restores every archive into a temporary directory and
    checks it (services/data/restore.py) before anything leaves the volume;
  * an archive that passes goes off-site, encrypted (services/data/offsite.py);
  * data/backups/backup_status.json records the drill and the off-site
    result, and the watchdog's backup_recoverable check reads it.
Secret-shaped files (.env, keys, certificates) are never archived.
"""
from __future__ import annotations

import fnmatch
import hashlib
import json
import logging
import os
import re
import sqlite3
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

DATA_DIR = Path("data")
BACKUP_SUBDIR = "backups"
BACKUP_KEEP = 7
EMAIL_MAX_BYTES = 20 * 1024 * 1024   # Gmail cap is 25MB; leave headroom for base64

FORMAT = "stockagent-backup/1"
ARCHIVE_PREFIX = "stockagent-backup-"
ARCHIVE_RE = re.compile(r"stockagent-backup-[0-9]{8}-[0-9]{4,6}\.zip")
MANIFEST_NAME = "MANIFEST.json"             # inside the zip
SIDECAR_SUFFIX = ".manifest.json"           # beside the zip
STATUS_NAME = "backup_status.json"          # under data/backups/, read by the watchdog

# Rebuildable caches — never backed up. Everything else under data/ goes in.
EXCLUDE_DIRS = {BACKUP_SUBDIR, "market_cache", "tavily_cache", "nse", "macro_news", "eval"}
_SQLITE_MAGIC = b"SQLite format 3\x00"
_SQLITE_SIDE_FILES = ("-wal", "-shm", "-journal")
# Append-only per-user ledgers (core/portfolio/store.py opens them only with "a").
LEDGER_NAMES = {"transactions.jsonl", "advice_ledger.jsonl", "value_history.jsonl",
                "switch_evaluations.jsonl"}
# Credentials belong in the environment, never on the volume. If one lands
# there anyway it stays out of every archive and off-site copy.
SECRET_PATTERNS = (".env", ".env.*", "*.env", "*.pem", "*.key", "*.p12", "*.pfx",
                   "id_rsa*", "id_ed25519*", "*secret*", "*credential*")


class BackupError(RuntimeError):
    """The archive could not be built, or failed its restore drill."""


def file_digest(path: Path) -> dict:
    digest, size = hashlib.sha256(), 0
    with open(path, "rb") as fh:
        while chunk := fh.read(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
    return {"bytes": size, "sha256": digest.hexdigest()}


def sidecar_path(archive: Path) -> Path:
    return archive.with_name(archive.name + SIDECAR_SUFFIX)


def _write_json_atomic(path: Path, data: dict) -> None:
    part = path.with_name(path.name + ".part")
    part.write_bytes(json.dumps(data, indent=2, sort_keys=True).encode("utf-8"))
    os.replace(part, path)


def _is_sqlite(path: Path) -> bool:
    with open(path, "rb") as fh:
        return fh.read(len(_SQLITE_MAGIC)) == _SQLITE_MAGIC


def _secret_shaped(name: str) -> bool:
    lowered = name.lower()
    return any(fnmatch.fnmatchcase(lowered, pattern) for pattern in SECRET_PATTERNS)


def _snapshot_sqlite(src: Path, dst: Path) -> None:
    """Consistent point-in-time copy of a possibly-live SQLite db.
    NB: sqlite3 connections must be close()d explicitly — the context manager
    only commits, and an open handle keeps the file locked on Windows."""
    conn = sqlite3.connect(src)
    try:
        out = sqlite3.connect(dst)
        try:
            conn.backup(out)
        finally:
            out.close()
    finally:
        conn.close()


def sqlite_facts(path: Path) -> dict:
    """integrity_check, a digest of the schema and every table's row count."""
    conn = sqlite3.connect(path)
    try:
        integrity = "; ".join(r[0] for r in conn.execute("PRAGMA integrity_check").fetchall())
        schema = conn.execute("SELECT type, name, tbl_name, sql FROM sqlite_master "
                              "ORDER BY type, name").fetchall()
        tables: dict[str, int | None] = {}
        for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' "
                                    "ORDER BY name").fetchall():
            try:
                quoted = '"' + name.replace('"', '""') + '"'
                tables[name] = conn.execute(f"SELECT COUNT(*) FROM {quoted}").fetchone()[0]
            except sqlite3.Error:
                tables[name] = None         # e.g. a virtual table whose module is absent
    finally:
        conn.close()
    return {"integrity": integrity,
            "schema_sha256": hashlib.sha256(json.dumps(schema).encode("utf-8")).hexdigest(),
            "tables": tables}


def ledger_facts(data: bytes) -> dict:
    """Rows in a JSONL ledger, and whether any row is not a JSON object.
    `torn_tail` is a final line without its newline (a write in progress)."""
    lines = data.split(b"\n")
    tail = lines.pop()
    if tail:
        lines.append(tail)
    rows, bad = 0, []
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        rows += 1
        try:
            ok = isinstance(json.loads(line), dict)
        except ValueError:
            ok = False
        if not ok:
            bad.append(number)
    return {"rows": rows, "bad_rows": len(bad), "first_bad_line": bad[0] if bad else None,
            "torn_tail": bool(tail)}


def _stable_read(path: Path, attempts: int = 3) -> tuple[bytes, bool]:
    """Read a file no writer changed while it was read (size and mtime equal
    before and after). After `attempts` tries the last read is returned
    with stable=False, which the manifest and the drill report."""
    data = b""
    for _ in range(attempts):
        before = path.stat()
        data = path.read_bytes()
        after = path.stat()
        if (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns) \
                and len(data) == after.st_size:
            return data, True
    return data, False


def _kind(rel: Path) -> str:
    if rel.parts[0] == "portfolio" and rel.name in LEDGER_NAMES:
        return "ledger"
    return "file"


def create_backup_archive(data_dir: Path = DATA_DIR, dest_dir: Path | None = None) -> Path:
    """Zip the non-rebuildable state under `data_dir` with its manifest, and
    write the sidecar. Returns the archive path. The zip is built under a
    .part name, so an interrupted run never leaves a finished-looking archive."""
    data_dir = Path(data_dir)
    dest_dir = Path(dest_dir) if dest_dir else data_dir / BACKUP_SUBDIR
    dest_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    created_at = now.isoformat(timespec="seconds")
    archive = dest_dir / f"{ARCHIVE_PREFIX}{now:%Y%m%d-%H%M%S}.zip"
    part = archive.with_name(archive.name + ".part")
    entries: list[dict] = []
    excluded: list[str] = []

    try:
        with zipfile.ZipFile(part, "w", zipfile.ZIP_DEFLATED) as z:
            for path in sorted(data_dir.rglob("*")):
                if not path.is_file():
                    continue
                rel = path.relative_to(data_dir)
                if rel.parts[0] in EXCLUDE_DIRS or path.name.endswith(_SQLITE_SIDE_FILES):
                    continue
                arc = rel.as_posix()
                if _secret_shaped(path.name):
                    excluded.append(arc)
                    logger.warning("[backup] %s looks like a credential file — excluded", arc)
                    continue
                if arc == MANIFEST_NAME:
                    raise BackupError(f"data/{MANIFEST_NAME} collides with the archive manifest")
                if _is_sqlite(path):
                    with tempfile.TemporaryDirectory() as td:
                        snap = Path(td) / path.name
                        _snapshot_sqlite(path, snap)
                        facts = sqlite_facts(snap)
                        if facts["integrity"] != "ok":
                            raise BackupError(f"{arc}: snapshot failed integrity_check: "
                                              f"{facts['integrity'][:200]}")
                        entry = {"path": arc, "kind": "sqlite", **file_digest(snap), **facts}
                        z.write(snap, arc)
                else:
                    data, stable = _stable_read(path)
                    entry = {"path": arc, "kind": _kind(rel), "bytes": len(data),
                             "sha256": hashlib.sha256(data).hexdigest()}
                    if entry["kind"] == "ledger":
                        entry.update(ledger_facts(data))
                    if not stable:
                        entry["unstable"] = True
                        logger.warning("[backup] %s kept changing while it was read", arc)
                    info = zipfile.ZipInfo.from_file(path, arc)
                    z.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED)
                entries.append(entry)
            manifest = {"format": FORMAT, "created_at": created_at, "files": entries,
                        "excluded_secret_shaped": excluded}
            z.writestr(MANIFEST_NAME, json.dumps(manifest, indent=2, sort_keys=True))
        digest = file_digest(part)
        os.replace(part, archive)
    except BaseException:
        part.unlink(missing_ok=True)
        raise
    _write_json_atomic(sidecar_path(archive), {
        "format": FORMAT, "archive": archive.name, "created_at": created_at,
        "files": len(entries), **digest})
    return archive


def list_archives(dest_dir: Path) -> list[Path]:
    """Archives oldest first (names carry the stamp)."""
    return sorted(p for p in Path(dest_dir).glob(f"{ARCHIVE_PREFIX}*.zip")
                  if ARCHIVE_RE.fullmatch(p.name))


def prune_backups(dest_dir: Path, keep: int = BACKUP_KEEP) -> int:
    """Delete all but the newest `keep` archives (never the newest one), each
    with its sidecar, plus sidecars and .part files left without an archive."""
    dest_dir = Path(dest_dir)
    archives = list_archives(dest_dir)
    stale = archives[:-max(1, keep)]
    for p in stale:
        for victim in (sidecar_path(p), p):
            try:
                victim.unlink(missing_ok=True)
            except OSError as exc:
                logger.warning("[backup] could not prune %s: %s", victim.name, exc)
    kept = {p.name for p in archives[-max(1, keep):]}
    for orphan in list(dest_dir.glob(f"{ARCHIVE_PREFIX}*{SIDECAR_SUFFIX}")) + \
            list(dest_dir.glob(f"{ARCHIVE_PREFIX}*.part")):
        if orphan.name[:-len(SIDECAR_SUFFIX)] in kept:
            continue
        try:
            orphan.unlink()
        except OSError as exc:
            logger.warning("[backup] could not prune %s: %s", orphan.name, exc)
    return len(stale)


def read_status(dest_dir: Path) -> dict:
    try:
        return json.loads((Path(dest_dir) / STATUS_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write_status(dest_dir: Path, sidecar: dict, drill, off, emailed: bool) -> dict:
    prior = read_status(dest_dir)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    status = {
        "format": 1,
        "last_run_at": now,
        "archive": sidecar["archive"],
        "bytes": sidecar["bytes"],
        "sha256": sidecar["sha256"],
        "files": sidecar["files"],
        "drill": {"ok": drill.ok, "errors": drill.errors[:5], "warnings": drill.warnings[:5],
                  "checked": drill.checked},
        "offsite": {**off.as_dict(), "at": now},
        "last_offsite_confirmed_at": now if off.confirmed else prior.get("last_offsite_confirmed_at"),
        "last_offsite_object": off.object if off.confirmed else prior.get("last_offsite_object"),
        "emailed": emailed,
    }
    _write_json_atomic(Path(dest_dir) / STATUS_NAME, status)
    return status


def run_backup_job(data_dir: Path = DATA_DIR) -> dict:
    """Create the nightly archive, restore-drill it, rotate local copies, push
    an encrypted copy off-site, email it, and record the outcome.
    Archive-creation errors and a failed drill RAISE (the scheduler's
    job-error alerting must hear about them); off-site and email problems
    only WARN, and the watchdog's backup_recoverable check reports them."""
    from core.delivery import channels
    from services.data import offsite, restore

    data_dir = Path(data_dir)
    dest_dir = data_dir / BACKUP_SUBDIR
    earlier = list_archives(dest_dir)
    archive = create_backup_archive(data_dir=data_dir, dest_dir=dest_dir)
    sidecar = json.loads(sidecar_path(archive).read_text(encoding="utf-8"))
    drill = restore.verify_archive(archive, previous=earlier[-1] if earlier else None,
                                   protected=(data_dir,))
    pruned = prune_backups(dest_dir)

    cfg = offsite.config_from_settings()
    if drill.ok:
        off = offsite.push(archive, sidecar, cfg, data_dir=data_dir)
    else:
        off = offsite.OffsiteResult(cfg.target or None, False,
                                    reason="skipped: the archive failed its restore drill")
    if not off.confirmed:
        logger.warning("[backup] no confirmed off-site copy for %s: %s", archive.name, off.reason)

    emailed = False
    size = sidecar["bytes"]
    if size <= EMAIL_MAX_BYTES:
        emailed = channels.send_email(
            f"StockAgent nightly backup — {archive.name}",
            f"Nightly data/ backup attached ({size / 1024:.0f} KB). "
            "Ledgers + predictions + telemetry; caches excluded.",
            attachments=[archive],
        )
    else:
        logger.warning("[backup] archive %s is %.1f MB — over the email cap, "
                       "NOT emailed", archive.name, size / 1e6)

    _write_status(dest_dir, sidecar, drill, off, emailed)
    summary = {"archive": str(archive), "bytes": size, "sha256": sidecar["sha256"],
               "drill_ok": drill.ok, "drill_warnings": len(drill.warnings),
               "offsite_confirmed": off.confirmed, "offsite_reason": off.reason,
               "emailed": emailed, "pruned": pruned}
    logger.info("[backup] %s", summary)
    if not drill.ok:
        raise BackupError(f"{archive.name} failed its restore drill: "
                          + "; ".join(drill.errors[:3]))
    return summary
