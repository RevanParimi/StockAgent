"""
Nightly data/ backup (AUD-088).

The Railway volume is the ONLY home of the trade ledgers (portfolio.json,
transactions.jsonl, value_history), the RL predictions tree and telemetry.db.
This module zips the non-rebuildable state, keeps a small local rotation under
data/backups/ (guards against app-level corruption / fat-fingered writes), and
emails the archive through the existing SMTP transport (the off-site copy that
guards against volume loss). Caches are excluded — they rebuild themselves.
"""
from __future__ import annotations

import logging
import sqlite3
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

DATA_DIR = Path("data")
BACKUP_SUBDIR = "backups"
BACKUP_KEEP = 7
EMAIL_MAX_BYTES = 20 * 1024 * 1024   # Gmail cap is 25MB; leave headroom for base64

# Rebuildable caches — never backed up. Everything else under data/ goes in.
EXCLUDE_DIRS = {BACKUP_SUBDIR, "market_cache", "tavily_cache", "nse", "macro_news", "eval"}
# Live SQLite files — copied via the sqlite3 backup API, not a raw file read.
SQLITE_NAMES = {"telemetry.db", "scores.db"}


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


def create_backup_archive(data_dir: Path = DATA_DIR, dest_dir: Path | None = None) -> Path:
    """Zip the non-rebuildable state under `data_dir`. Returns the archive path."""
    data_dir = Path(data_dir)
    dest_dir = Path(dest_dir) if dest_dir else data_dir / BACKUP_SUBDIR
    dest_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    archive = dest_dir / f"stockagent-backup-{stamp}.zip"

    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
        for path in sorted(data_dir.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(data_dir)
            if rel.parts[0] in EXCLUDE_DIRS:
                continue
            if path.name in SQLITE_NAMES:
                with tempfile.TemporaryDirectory() as td:
                    snap = Path(td) / path.name
                    _snapshot_sqlite(path, snap)
                    z.write(snap, rel.as_posix())
            else:
                z.write(path, rel.as_posix())
    return archive


def prune_backups(dest_dir: Path, keep: int = BACKUP_KEEP) -> int:
    """Delete all but the newest `keep` archives (by name — names carry the stamp)."""
    archives = sorted(Path(dest_dir).glob("stockagent-backup-*.zip"))
    stale = archives[:-keep] if keep else archives
    for p in stale:
        try:
            p.unlink()
        except OSError as exc:
            logger.warning("[backup] could not prune %s: %s", p.name, exc)
    return len(stale)


def run_backup_job(data_dir: Path = DATA_DIR) -> dict:
    """Create the nightly archive, rotate local copies, email the off-site copy.
    Delivery problems only WARN — but archive-creation errors DO raise (the
    scheduler's job-error alerting must hear about a failed backup)."""
    from core.delivery import channels

    archive = create_backup_archive(data_dir=data_dir)
    size = archive.stat().st_size
    pruned = prune_backups(archive.parent)

    emailed = False
    if size <= EMAIL_MAX_BYTES:
        emailed = channels.send_email(
            f"StockAgent nightly backup — {archive.name}",
            f"Nightly data/ backup attached ({size / 1024:.0f} KB). "
            "Ledgers + predictions + telemetry; caches excluded.",
            attachments=[archive],
        )
    else:
        logger.warning("[backup] archive %s is %.1f MB — over the email cap, "
                       "NOT sent off-site", archive.name, size / 1e6)
    if not emailed:
        logger.warning("[backup] no off-site copy landed for %s (email disabled, "
                       "oversize, or send failed) — local rotation only", archive.name)
    summary = {"archive": str(archive), "bytes": size, "emailed": emailed, "pruned": pruned}
    logger.info("[backup] %s", summary)
    return summary
