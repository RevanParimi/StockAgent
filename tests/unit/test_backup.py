"""AUD-088: nightly data/ backup — zip ledgers, snapshot sqlite, rotate, email offsite."""
import sqlite3
import zipfile
from pathlib import Path

import pytest

from services.data import backup


@pytest.fixture()
def data_dir(tmp_path):
    d = tmp_path / "data"
    (d / "portfolio").mkdir(parents=True)
    (d / "portfolio" / "portfolio.json").write_text('{"ok": true}')
    (d / "portfolio" / "transactions.jsonl").write_text('{"t": 1}\n')
    (d / "predictions" / "SUZLON").mkdir(parents=True)
    (d / "predictions" / "SUZLON" / "feedback_log.jsonl").write_text("{}\n")
    (d / "market_cache").mkdir()                      # rebuildable — excluded
    (d / "market_cache" / "big.json").write_text("x" * 1000)
    (d / "managed_tickers.json").write_text("[]")
    conn = sqlite3.connect(d / "telemetry.db")        # live sqlite — snapshot API
    conn.execute("CREATE TABLE t (x)")
    conn.execute("INSERT INTO t VALUES (1)")
    conn.commit()
    conn.close()
    return d


def test_archive_includes_ledgers_excludes_caches(data_dir):
    path = backup.create_backup_archive(data_dir=data_dir)
    names = zipfile.ZipFile(path).namelist()
    assert "portfolio/portfolio.json" in names
    assert "portfolio/transactions.jsonl" in names
    assert "predictions/SUZLON/feedback_log.jsonl" in names
    assert "managed_tickers.json" in names
    assert "telemetry.db" in names
    assert not any(n.startswith("market_cache") for n in names)
    assert not any(n.startswith("backups") for n in names)


def test_sqlite_snapshot_is_valid_db(data_dir, tmp_path):
    path = backup.create_backup_archive(data_dir=data_dir)
    out = tmp_path / "restored.db"
    with zipfile.ZipFile(path) as z:
        out.write_bytes(z.read("telemetry.db"))
    rows = sqlite3.connect(out).execute("SELECT x FROM t").fetchall()
    assert rows == [(1,)]


def test_prune_keeps_newest(data_dir):
    dest = data_dir / "backups"
    dest.mkdir()
    for i in range(10):
        (dest / f"stockagent-backup-2026071{i}-0000.zip").write_bytes(b"x")
    removed = backup.prune_backups(dest, keep=7)
    assert removed == 3
    left = sorted(p.name for p in dest.glob("*.zip"))
    assert len(left) == 7 and left[0].startswith("stockagent-backup-20260713")


def test_run_backup_job_emails_archive(data_dir, monkeypatch):
    sent = {}

    def _fake_send(subject, body, attachments=None):
        sent["attachments"] = attachments
        return True

    monkeypatch.setattr("core.delivery.channels.send_email", _fake_send)
    summary = backup.run_backup_job(data_dir=data_dir)
    assert summary["emailed"] is True
    assert Path(summary["archive"]).exists()
    assert sent["attachments"] == [Path(summary["archive"])]


def test_run_backup_job_skips_email_when_oversize(data_dir, monkeypatch):
    monkeypatch.setattr(backup, "EMAIL_MAX_BYTES", 1)   # force oversize
    called = []
    monkeypatch.setattr("core.delivery.channels.send_email",
                        lambda *a, **k: called.append(1) or True)
    summary = backup.run_backup_job(data_dir=data_dir)
    assert summary["emailed"] is False and called == []
