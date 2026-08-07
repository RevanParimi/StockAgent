import json

import pytest

from backend.shared.schemas.audit import AuditOutcome
from core.audit.store import AuditOutcomeStore


def _row(ref: str = "2026-07-03|MARUTI|abc123", horizon: int = 30) -> AuditOutcome:
    return AuditOutcome(
        ref=ref, lane="advice", user_id="primary", symbol="MARUTI",
        verdict="HOLD", triggers=["thesis_break"], issued_on="2026-07-03",
        horizon_td=horizon, graded_on="2026-08-14",
        entry_close=12450.0, exit_close=12890.5, return_pct=3.54,
        bench_entry=24810.2, bench_exit=25102.7, bench_pct=1.18,
        excess_pct=2.36, correct=True, graded_at="2026-08-14T02:11:04Z",
    )


def test_append_and_load_roundtrip(tmp_path):
    store = AuditOutcomeStore(user_id="primary", base_dir=str(tmp_path))
    store.append(_row())
    rows = store.load_all()
    assert len(rows) == 1
    assert rows[0].symbol == "MARUTI" and rows[0].excess_pct == 2.36


def test_append_is_append_only(tmp_path):
    """Mirrors test_advice_ledger_append_only: a second write never rewrites
    the first line."""
    store = AuditOutcomeStore(user_id="primary", base_dir=str(tmp_path))
    store.append(_row(horizon=10))
    store.append(_row(horizon=30))
    lines = store.path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["horizon_td"] == 10


def test_corrupt_line_is_skipped_not_fatal(tmp_path):
    store = AuditOutcomeStore(user_id="primary", base_dir=str(tmp_path))
    store.append(_row())
    with open(store.path, "a", encoding="utf-8") as fh:
        fh.write("{not json\n")
    assert len(store.load_all()) == 1


def test_existing_keys_reports_ref_and_horizon(tmp_path):
    store = AuditOutcomeStore(user_id="primary", base_dir=str(tmp_path))
    store.append(_row(horizon=10))
    store.append(_row(horizon=30))
    assert store.existing_keys() == {
        ("2026-07-03|MARUTI|abc123", 10),
        ("2026-07-03|MARUTI|abc123", 30),
    }


def test_load_all_on_missing_file_returns_empty(tmp_path):
    store = AuditOutcomeStore(user_id="primary", base_dir=str(tmp_path))
    assert store.load_all() == []


def test_rejects_invalid_user_id(tmp_path):
    with pytest.raises(ValueError):
        AuditOutcomeStore(user_id="../escape", base_dir=str(tmp_path))
