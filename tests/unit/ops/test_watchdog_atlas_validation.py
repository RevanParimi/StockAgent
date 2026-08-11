"""Atlas cutover validations — the spec §6 step-5 gate before flipping the flag.

The Atlas plan calls the dry-run active_user_ids() check "the runtime gate that
confirms it before the flip", because with AUTH_REQUIRED=true there is no owner
fallback: if the users table is empty after the flip, the morning brief and
autopilot fan out to NOBODY. Running the ETL without these checks and reporting
"ready to flip" would be worse than not preparing at all.
"""
import json

import pytest

from core.ops.watchdog import checks as C
from core.ops.watchdog import prep as P


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "_DATA_DIR", tmp_path)
    monkeypatch.delenv("ATLAS_ENABLED", raising=False)
    (tmp_path / "portfolio").mkdir(exist_ok=True)
    (tmp_path / "portfolio" / "primary").mkdir(exist_ok=True)
    return tmp_path


def _pass_all(monkeypatch, users=("primary",)):
    monkeypatch.setattr(P, "_atlas_user_ids", lambda: list(users))
    monkeypatch.setattr(P, "_atlas_integrity", lambda: (True, []))
    monkeypatch.setattr(P, "_atlas_table_counts",
                        lambda: {"users": 1, "user_instruments": 12})


def _etl_creating_db(tmp_path):
    def _etl(**kw):
        if not kw.get("dry_run"):
            (tmp_path / "atlas.db").write_text("db")
        return {"users": 1, "verdicts": 1191}
    return _etl


class TestValidationsRun:
    def test_all_three_validations_reported(self, monkeypatch, tmp_path):
        monkeypatch.setattr(P, "_run_etl", _etl_creating_db(tmp_path))
        _pass_all(monkeypatch)
        r = P.run_prep("atlas_cutover_prep")
        assert r.ok is True
        joined = " | ".join(r.transcript).lower()
        assert "integrity" in joined
        assert "active_user_ids" in joined or "user ids" in joined
        assert "row counts" in joined or "users=1" in joined

    def test_marker_records_validated_true(self, monkeypatch, tmp_path):
        monkeypatch.setattr(P, "_run_etl", _etl_creating_db(tmp_path))
        _pass_all(monkeypatch)
        P.run_prep("atlas_cutover_prep")
        marker = json.loads(C._atlas_prep_marker().read_text(encoding="utf-8"))
        assert marker["validated"] is True and marker["failures"] == []


class TestValidationFailuresBlockTheFlip:
    """A failed validation must never present as 'ready to flip'."""

    def test_empty_users_table_fails(self, monkeypatch, tmp_path):
        monkeypatch.setattr(P, "_run_etl", _etl_creating_db(tmp_path))
        _pass_all(monkeypatch, users=())
        r = P.run_prep("atlas_cutover_prep")
        assert r.ok is False
        assert any("no users" in l.lower() or "empty" in l.lower()
                   for l in r.transcript)

    def test_owner_missing_from_users_fails(self, monkeypatch, tmp_path):
        """'primary' absent means the owner stops receiving briefs post-flip."""
        monkeypatch.setattr(P, "_run_etl", _etl_creating_db(tmp_path))
        _pass_all(monkeypatch, users=("u_someoneelse",))
        r = P.run_prep("atlas_cutover_prep")
        assert r.ok is False
        assert any("primary" in l for l in r.transcript)

    def test_integrity_failure_fails(self, monkeypatch, tmp_path):
        monkeypatch.setattr(P, "_run_etl", _etl_creating_db(tmp_path))
        _pass_all(monkeypatch)
        monkeypatch.setattr(P, "_atlas_integrity",
                            lambda: (False, ["row not in index users_idx"]))
        r = P.run_prep("atlas_cutover_prep")
        assert r.ok is False
        assert any("integrity" in l.lower() for l in r.transcript)

    def test_check_reports_blocked_not_ready_when_validation_failed(
            self, monkeypatch, tmp_path):
        monkeypatch.setattr(P, "_run_etl", _etl_creating_db(tmp_path))
        _pass_all(monkeypatch, users=())
        P.run_prep("atlas_cutover_prep")
        r = C.run_check("atlas_cutover_pending")
        assert r.state == "blocked"
        assert "validation" in r.detail.lower()
        assert "ready to flip" not in r.detail.lower()

    def test_failed_validation_allows_a_later_retry(self, monkeypatch, tmp_path):
        """A failed run must not wedge: fixing the cause and re-running works."""
        monkeypatch.setattr(P, "_run_etl", _etl_creating_db(tmp_path))
        _pass_all(monkeypatch, users=())
        assert P.run_prep("atlas_cutover_prep").ok is False
        _pass_all(monkeypatch, users=("primary",))
        second = P.run_prep("atlas_cutover_prep")
        assert second.ok is True
        assert C.run_check("atlas_cutover_pending").state == "pending"


class TestRealValidationHelpers:
    """The helpers themselves, against a real sqlite file."""

    def test_integrity_and_counts_on_a_real_db(self, tmp_path, monkeypatch):
        import sqlite3
        db = tmp_path / "atlas.db"
        conn = sqlite3.connect(db)
        conn.execute("CREATE TABLE users (user_id TEXT PRIMARY KEY)")
        conn.execute("INSERT INTO users VALUES ('primary')")
        conn.commit()
        conn.close()
        monkeypatch.setattr(P, "_atlas_db_path", lambda: db)

        ok, problems = P._atlas_integrity()
        assert ok is True and problems == []
        assert P._atlas_table_counts()["users"] == 1

    def test_missing_db_is_a_failure_not_a_crash(self, tmp_path, monkeypatch):
        monkeypatch.setattr(P, "_atlas_db_path", lambda: tmp_path / "absent.db")
        ok, problems = P._atlas_integrity()
        assert ok is False and problems
