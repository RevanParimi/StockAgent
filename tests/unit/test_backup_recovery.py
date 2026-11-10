"""SA-007: every nightly archive is consistent, self-describing and proven
restorable before it leaves the volume.

Expected values come from the fixture itself (rows inserted, bytes written),
never from the code under test. Each test names the defect it would catch.
"""
import hashlib
import json
import logging
import shutil
import sqlite3
import zipfile
from pathlib import Path

import pytest

from services.data import backup, restore

SENTINEL = "SENTINEL-DO-NOT-ARCHIVE-7f3a"
TXNS = [{"txn_id": f"t{i}", "cash_before": 100.0 - i, "cash_after": 99.0 - i} for i in range(3)]


def _jsonl(rows) -> str:
    return "".join(json.dumps(r) + "\n" for r in rows)


@pytest.fixture()
def data_dir(tmp_path):
    """A small volume: ledgers, a WAL database whose committed rows exist ONLY
    in its -wal file (the live connection stays open), a rollback-journal
    database, a cache that must be excluded and two credential-shaped files."""
    d = tmp_path / "data"
    user = d / "portfolio" / "primary"
    user.mkdir(parents=True)
    (user / "portfolio.json").write_text('{"cash_deployable": 97.0}')
    (user / "transactions.jsonl").write_text(_jsonl(TXNS))
    (user / "advice_ledger.jsonl").write_text(_jsonl([{"a": 1}, {"a": 2}]))
    (d / "predictions" / "SUZLON").mkdir(parents=True)
    (d / "predictions" / "SUZLON" / "feedback_log.jsonl").write_text("{}\n")
    (d / "market_cache").mkdir()
    (d / "market_cache" / "big.json").write_text("x" * 1000)
    (d / ".env").write_text(f"OPENROUTER_API_KEY={SENTINEL}\n")
    (user / "signing.pem").write_text(SENTINEL)

    tele = sqlite3.connect(d / "telemetry.db")
    tele.execute("CREATE TABLE t (x)")
    tele.execute("INSERT INTO t VALUES (1)")
    tele.commit()
    tele.close()

    live = sqlite3.connect(d / "users.db")
    live.execute("PRAGMA journal_mode=WAL")
    live.execute("PRAGMA wal_autocheckpoint=0")
    live.execute("CREATE TABLE users (user_id TEXT PRIMARY KEY, email TEXT)")
    live.execute("CREATE TABLE sessions (token_hash TEXT PRIMARY KEY)")
    live.executemany("INSERT INTO users VALUES (?, ?)",
                     [("primary", "a@example.com"), ("u2", "b@example.com")])
    live.commit()
    yield d
    live.close()


def _manifest(archive: Path) -> dict:
    with zipfile.ZipFile(archive) as z:
        return json.loads(z.read(backup.MANIFEST_NAME))


def _rezip(src: Path, dst: Path, replace: dict[str, bytes]) -> None:
    """Copy an archive, swapping member contents, and give it a VALID sidecar,
    so only the per-member checks can catch the change."""
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for name in zin.namelist():
            zout.writestr(name, replace.get(name, zin.read(name)))
        for name, data in replace.items():
            if name not in zin.namelist():
                zout.writestr(name, data)
    side = json.loads(backup.sidecar_path(src).read_text())
    side.update(archive=dst.name, **backup.file_digest(dst))
    backup.sidecar_path(dst).write_text(json.dumps(side))


# --------------------------------------------------------------------------
# Snapshot consistency
# --------------------------------------------------------------------------

def test_wal_database_rows_survive_the_archive(data_dir, tmp_path):
    """Before SA-007 only telemetry.db and scores.db used the backup API;
    users.db was copied raw, which loses rows still in its -wal file."""
    raw = tmp_path / "raw-copy.db"
    shutil.copyfile(data_dir / "users.db", raw)
    with pytest.raises(sqlite3.OperationalError):          # the premise: raw loses them
        sqlite3.connect(raw).execute("SELECT COUNT(*) FROM users").fetchone()

    archive = backup.create_backup_archive(data_dir=data_dir)
    out = tmp_path / "restored-users.db"
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        out.write_bytes(z.read("users.db"))
    conn = sqlite3.connect(out)
    try:
        assert conn.execute("SELECT user_id FROM users ORDER BY 1").fetchall() == \
            [("primary",), ("u2",)]
    finally:
        conn.close()
    assert not any(n.endswith(("-wal", "-shm", "-journal")) for n in names)


def test_manifest_records_counts_derived_from_the_fixture(data_dir):
    archive = backup.create_backup_archive(data_dir=data_dir)
    files = {e["path"]: e for e in _manifest(archive)["files"]}
    users = files["users.db"]
    assert users["kind"] == "sqlite" and users["integrity"] == "ok"
    assert users["tables"] == {"users": 2, "sessions": 0}
    assert files["telemetry.db"]["tables"] == {"t": 1}
    txns = files["portfolio/primary/transactions.jsonl"]
    assert txns["kind"] == "ledger" and txns["rows"] == 3 and txns["bad_rows"] == 0
    raw = (data_dir / "portfolio/primary/transactions.jsonl").read_bytes()
    assert txns["sha256"] == hashlib.sha256(raw).hexdigest() and txns["bytes"] == len(raw)
    assert files["portfolio/primary/advice_ledger.jsonl"]["rows"] == 2
    side = json.loads(backup.sidecar_path(archive).read_text())
    assert side["sha256"] == hashlib.sha256(archive.read_bytes()).hexdigest()
    assert side["files"] == len(files)


def test_credential_files_are_never_archived(data_dir):
    archive = backup.create_backup_archive(data_dir=data_dir)
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        blobs = b"".join(z.read(n) for n in names)
    assert ".env" not in names and "portfolio/primary/signing.pem" not in names
    assert SENTINEL.encode() not in blobs
    assert SENTINEL not in backup.sidecar_path(archive).read_text()


def test_interrupted_build_leaves_no_archive(data_dir, monkeypatch):
    def boom(path):
        raise OSError("disk full")
    monkeypatch.setattr(backup, "sqlite_facts", boom)
    with pytest.raises(OSError):
        backup.create_backup_archive(data_dir=data_dir)
    assert list((data_dir / "backups").iterdir()) == []


def test_a_file_changing_during_the_read_is_reread(data_dir, monkeypatch):
    ledger = data_dir / "portfolio/primary/transactions.jsonl"
    real = Path.read_bytes
    calls = {"n": 0}

    def appending_read(self):
        data = real(self)
        if self == ledger and calls["n"] == 0:
            calls["n"] += 1
            with open(ledger, "a") as fh:                  # a writer appends mid-read
                fh.write(json.dumps({"txn_id": "t3"}) + "\n")
        return data
    monkeypatch.setattr(Path, "read_bytes", appending_read)
    archive = backup.create_backup_archive(data_dir=data_dir)
    entry = next(e for e in _manifest(archive)["files"] if e["path"].endswith("transactions.jsonl"))
    assert entry["rows"] == 4 and "unstable" not in entry


# --------------------------------------------------------------------------
# Restore drill
# --------------------------------------------------------------------------

def test_drill_restores_and_reads_back_the_records(data_dir, tmp_path):
    archive = backup.create_backup_archive(data_dir=data_dir)
    dest = tmp_path / "drill"
    result = restore.verify_archive(archive, dest, protected=(data_dir,))
    assert result.ok and result.clean, result.as_dict()
    assert result.checked["sqlite_rows"] == 3 and result.checked["ledgers"] == 2
    conn = sqlite3.connect(dest / "users.db")
    try:
        assert conn.execute("SELECT COUNT(*) FROM users").fetchone() == (2,)
    finally:
        conn.close()
    assert (dest / "portfolio/primary/transactions.jsonl").read_text() == _jsonl(TXNS)


def test_corrupt_archive_fails(data_dir):
    archive = backup.create_backup_archive(data_dir=data_dir)
    blob = bytearray(archive.read_bytes())
    blob[len(blob) // 2] ^= 0xFF
    archive.write_bytes(bytes(blob))
    result = restore.verify_archive(archive, protected=(data_dir,))
    assert not result.ok and "checksum mismatch" in result.errors[0]


def test_truncated_archive_fails(data_dir):
    archive = backup.create_backup_archive(data_dir=data_dir)
    archive.write_bytes(archive.read_bytes()[:-100])
    assert not restore.verify_archive(archive, protected=(data_dir,)).ok


def test_missing_sidecar_fails(data_dir):
    archive = backup.create_backup_archive(data_dir=data_dir)
    backup.sidecar_path(archive).unlink()
    result = restore.verify_archive(archive, protected=(data_dir,))
    assert not result.ok and "missing manifest" in result.errors[0]


def test_archive_without_inner_manifest_fails(data_dir, tmp_path):
    """A pre-SA-007 archive has no MANIFEST.json and cannot be verified."""
    archive = backup.create_backup_archive(data_dir=data_dir)
    old = tmp_path / "stockagent-backup-20260901-1800.zip"
    with zipfile.ZipFile(archive) as zin, zipfile.ZipFile(old, "w") as zout:
        for name in zin.namelist():
            if name != backup.MANIFEST_NAME:
                zout.writestr(name, zin.read(name))
    side = json.loads(backup.sidecar_path(archive).read_text())
    side.update(**backup.file_digest(old))
    backup.sidecar_path(old).write_text(json.dumps(side))
    result = restore.verify_archive(old, protected=(data_dir,))
    assert not result.ok and "missing manifest" in result.errors[0]


def test_member_swapped_under_a_valid_sidecar_fails(data_dir, tmp_path):
    archive = backup.create_backup_archive(data_dir=data_dir)
    forged = tmp_path / "stockagent-backup-20260901-180000.zip"
    _rezip(archive, forged, {"portfolio/primary/transactions.jsonl": _jsonl(TXNS[:2]).encode()})
    result = restore.verify_archive(forged, protected=(data_dir,))
    assert not result.ok
    assert any("transactions.jsonl: checksum mismatch" in e for e in result.errors)


def test_row_count_disagreeing_with_manifest_fails(data_dir, tmp_path):
    archive = backup.create_backup_archive(data_dir=data_dir)
    manifest = _manifest(archive)
    for e in manifest["files"]:
        if e["path"] == "users.db":
            e["tables"]["users"] = 3                        # the manifest claims a row we lack
    forged = tmp_path / "stockagent-backup-20260901-180000.zip"
    _rezip(archive, forged, {backup.MANIFEST_NAME: json.dumps(manifest).encode()})
    result = restore.verify_archive(forged, protected=(data_dir,))
    assert any("table users has 2 rows, manifest says 3" in e for e in result.errors)


def test_unlisted_and_traversal_members_fail_and_nothing_escapes(data_dir, tmp_path):
    archive = backup.create_backup_archive(data_dir=data_dir)
    manifest = _manifest(archive)
    evil = {"path": "../escaped.txt", "kind": "file", "bytes": 4,
            "sha256": hashlib.sha256(b"evil").hexdigest()}
    manifest["files"].append(evil)
    forged = tmp_path / "stockagent-backup-20260901-180000.zip"
    _rezip(archive, forged, {backup.MANIFEST_NAME: json.dumps(manifest).encode(),
                             "../escaped.txt": b"evil", "extra.txt": b"x"})
    side = json.loads(backup.sidecar_path(forged).read_text())
    side["files"] += 1
    backup.sidecar_path(forged).write_text(json.dumps(side))
    dest = tmp_path / "drill" / "inner"
    result = restore.verify_archive(forged, dest, protected=(data_dir,))
    assert not result.ok
    assert any("unsafe archive member '../escaped.txt'" in e for e in result.errors)
    assert any("unexpected member 'extra.txt'" in e for e in result.errors)
    assert not (tmp_path / "drill" / "escaped.txt").exists()


@pytest.mark.parametrize("where", ["data", "inside", "parent"])
def test_drill_never_writes_into_production(data_dir, where):
    archive = backup.create_backup_archive(data_dir=data_dir)
    before = sorted(p.relative_to(data_dir.parent).as_posix() for p in data_dir.parent.rglob("*"))
    dest = {"data": data_dir, "inside": data_dir / "restore-here",
            "parent": data_dir.parent}[where]
    result = restore.verify_archive(archive, dest, protected=(data_dir,))
    assert not result.ok and "refusing to restore" in result.errors[0]
    after = sorted(p.relative_to(data_dir.parent).as_posix() for p in data_dir.parent.rglob("*"))
    assert after == before


def test_drill_refuses_a_non_empty_destination(data_dir, tmp_path):
    archive = backup.create_backup_archive(data_dir=data_dir)
    dest = tmp_path / "busy"
    dest.mkdir()
    (dest / "keep.txt").write_text("mine")
    result = restore.verify_archive(archive, dest, protected=(data_dir,))
    assert not result.ok and (dest / "keep.txt").read_text() == "mine"


# --------------------------------------------------------------------------
# Ledger continuity across nightly archives
# --------------------------------------------------------------------------

def _two_nights(data_dir, change) -> restore.DrillResult:
    first = backup.create_backup_archive(data_dir=data_dir)
    change(data_dir / "portfolio/primary/transactions.jsonl")
    second = backup.create_backup_archive(data_dir=data_dir)
    assert second.name > first.name
    return restore.verify_archive(second, previous=first, protected=(data_dir,))


def _later(data_dir, monkeypatch):
    """Two archives in one test need distinct stamps."""
    import itertools
    from datetime import datetime, timezone
    ticks = itertools.count()

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 9, 29, 18, 0, next(ticks), tzinfo=timezone.utc)
    monkeypatch.setattr(backup, "datetime", Clock)


def test_appended_ledger_is_continuous(data_dir, monkeypatch):
    _later(data_dir, monkeypatch)
    def append(path):
        with open(path, "a") as fh:
            fh.write(json.dumps({"txn_id": "t3"}) + "\n")
    result = _two_nights(data_dir, append)
    assert result.clean, result.as_dict()
    assert result.checked["continuity"].startswith("2 ledger(s) checked")


def test_rewritten_ledger_is_flagged(data_dir, monkeypatch):
    _later(data_dir, monkeypatch)
    rewritten = [dict(TXNS[0], cash_after=50.0)] + TXNS[1:]      # same row count, history changed
    result = _two_nights(data_dir, lambda p: p.write_text(_jsonl(rewritten)))
    assert result.ok and not result.clean
    assert any("transactions.jsonl was rewritten" in w for w in result.warnings)


def test_truncated_ledger_is_flagged(data_dir, monkeypatch):
    _later(data_dir, monkeypatch)
    result = _two_nights(data_dir, lambda p: p.write_text(_jsonl(TXNS[:1])))
    assert any("transactions.jsonl shrank" in w for w in result.warnings)


def test_deleted_ledger_is_flagged(data_dir, monkeypatch):
    _later(data_dir, monkeypatch)
    result = _two_nights(data_dir, lambda p: p.unlink())
    assert any("transactions.jsonl disappeared" in w for w in result.warnings)


def test_torn_and_unparseable_ledger_rows_are_flagged(data_dir):
    ledger = data_dir / "portfolio/primary/advice_ledger.jsonl"
    ledger.write_text('{"a": 1}\nnot json\n{"a": 2')
    archive = backup.create_backup_archive(data_dir=data_dir)
    result = restore.verify_archive(archive, protected=(data_dir,))
    assert result.ok and not result.clean
    assert any("not JSON objects (first at line 2)" in w for w in result.warnings)
    assert any("torn write" in w for w in result.warnings)


# --------------------------------------------------------------------------
# Retention
# --------------------------------------------------------------------------

def test_local_retention_boundary_keeps_pairs(tmp_path):
    dest = tmp_path / "backups"
    dest.mkdir()
    names = [f"stockagent-backup-202609{d:02d}-180000.zip" for d in range(1, 10)]
    for n in names:
        (dest / n).write_bytes(b"x")
        (dest / (n + backup.SIDECAR_SUFFIX)).write_text("{}")
    (dest / "stockagent-backup-20260930-180000.zip.part").write_bytes(b"half")
    (dest / "backup_status.json").write_text("{}")
    assert backup.prune_backups(dest, keep=7) == 2
    left = sorted(p.name for p in dest.iterdir())
    assert left == sorted(["backup_status.json"] + names[2:] +
                          [n + backup.SIDECAR_SUFFIX for n in names[2:]])


def test_local_retention_never_deletes_the_newest(tmp_path):
    dest = tmp_path / "backups"
    dest.mkdir()
    for d in (1, 2):
        (dest / f"stockagent-backup-2026090{d}-180000.zip").write_bytes(b"x")
    backup.prune_backups(dest, keep=0)
    assert [p.name for p in dest.iterdir()] == ["stockagent-backup-20260902-180000.zip"]


# --------------------------------------------------------------------------
# The nightly job
# --------------------------------------------------------------------------

@pytest.fixture()
def no_email(monkeypatch):
    sent = []
    monkeypatch.setattr("core.delivery.channels.send_email",
                        lambda *a, **k: sent.append(k.get("attachments")) or False)
    return sent


def test_job_records_the_missing_offsite_copy(data_dir, no_email, caplog):
    caplog.set_level(logging.WARNING)
    summary = backup.run_backup_job(data_dir=data_dir)
    assert summary["drill_ok"] is True and summary["offsite_confirmed"] is False
    status = json.loads((data_dir / "backups" / backup.STATUS_NAME).read_text())
    assert status["offsite"]["confirmed"] is False
    assert "BACKUP_OFFSITE_TARGET is unset" in status["offsite"]["reason"]
    assert status["last_offsite_confirmed_at"] is None
    assert status["archive"] == Path(summary["archive"]).name
    assert "no confirmed off-site copy" in caplog.text


def test_job_checks_continuity_against_last_nights_archive(data_dir, no_email, monkeypatch):
    _later(data_dir, monkeypatch)
    backup.run_backup_job(data_dir=data_dir)
    (data_dir / "portfolio/primary/transactions.jsonl").write_text(_jsonl(TXNS[:1]))
    summary = backup.run_backup_job(data_dir=data_dir)
    status = json.loads((data_dir / "backups" / backup.STATUS_NAME).read_text())
    assert summary["drill_ok"] and summary["drill_warnings"] == 1
    assert "shrank" in status["drill"]["warnings"][0]


def test_failed_drill_raises_and_nothing_goes_offsite(data_dir, no_email, monkeypatch, tmp_path):
    offsite_dir = tmp_path / "offsite"
    monkeypatch.setattr("core.config.settings.BACKUP_OFFSITE_TARGET", "dir", raising=False)
    monkeypatch.setattr("core.config.settings.BACKUP_OFFSITE_DIR", str(offsite_dir), raising=False)
    monkeypatch.setattr("core.config.settings.BACKUP_ENCRYPTION_KEY", "A" * 43 + "=", raising=False)
    monkeypatch.setattr(restore, "verify_archive",
                        lambda *a, **k: restore.DrillResult("x", errors=["users.db: schema differs"]))
    with pytest.raises(backup.BackupError, match="failed its restore drill"):
        backup.run_backup_job(data_dir=data_dir)
    assert not offsite_dir.exists()
    status = json.loads((data_dir / "backups" / backup.STATUS_NAME).read_text())
    assert status["drill"]["ok"] is False
    assert status["offsite"]["reason"].startswith("skipped")
