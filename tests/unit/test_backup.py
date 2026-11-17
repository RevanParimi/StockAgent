"""AUD-088: nightly data/ backup — zip ledgers, snapshot sqlite, rotate; never emailed (CLEAN-007)."""
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


@pytest.mark.parametrize("transport", ["smtp", "resend"])
def test_nightly_job_sends_no_email_on_either_transport(data_dir, monkeypatch, transport):
    """CLEAN-007: the archive stays on the volume. With email fully configured
    and working, the nightly job opens no SMTP connection and posts nothing to
    Resend, and neither its summary nor the status file speaks of an email."""
    import json

    import requests

    import core.delivery.channels as ch

    opened = []

    class _SMTP:
        def __init__(self, *a, **k):
            opened.append(("smtp", a))

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def starttls(self):
            pass

        def login(self, *a):
            pass

        def sendmail(self, *a):
            opened.append(("sendmail", a[1]))

    class _Accepted:
        status_code = 200

        def json(self):
            return {"id": "msg_1"}

    def _post(url, **kwargs):
        opened.append(("post", url))
        return _Accepted()

    for name, value in (("DELIVERY_EMAIL_ENABLED", True), ("EMAIL_TRANSPORT", transport),
                        ("SMTP_HOST", "smtp.example.com"), ("SMTP_USER", "u@example.com"),
                        ("SMTP_PASSWORD", "pw"), ("RESEND_API_KEY", "re_test"),
                        ("RESEND_FROM", "StockAgent <reports@example.com>"),
                        ("DELIVERY_EMAIL_TO", "me@example.com")):
        monkeypatch.setattr(ch.settings, name, value, raising=False)
    monkeypatch.setattr(ch.smtplib, "SMTP", _SMTP)
    monkeypatch.setattr(requests, "post", _post)

    # The fakes do record a send: the channel is live for this test.
    assert ch.send_email("probe", "body") is True and opened
    opened.clear()

    summary = backup.run_backup_job(data_dir=data_dir)

    assert opened == []
    assert Path(summary["archive"]).exists() and summary["drill_ok"] is True
    status = json.loads((data_dir / "backups" / backup.STATUS_NAME).read_text())
    assert "emailed" not in summary and "emailed" not in status
    assert not hasattr(backup, "EMAIL_MAX_BYTES")
