import json
from datetime import date

from core.audit.outcomes import grade_alert_lane, grade_due, grade_shelf_lane
from core.audit.store import AuditOutcomeStore


class _FakeBench:
    """+1% over any window starting on the 2026-07-01 issue date. The boundary
    must fall between issue and the 2026-07-15 maturity, or the benchmark never
    moves and excess collapses to the raw return."""
    def close_on(self, d):
        return 100.0 if d < date(2026, 7, 2) else 101.0

    def pct_change(self, start, end):
        return round((self.close_on(end) / self.close_on(start) - 1.0) * 100.0, 4)


def _write(tmp_path, name, rows, sub="primary"):
    d = tmp_path / sub
    d.mkdir(parents=True, exist_ok=True)
    with open(d / name, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    return d / name


def test_alert_lane_grades_only_alerts_with_advice_ref(tmp_path):
    log = _write(tmp_path, "alerts_sent.jsonl", [
        {"date": "2026-07-01", "kind": "advisor_exit", "symbol": "MARUTI",
         "message": "m", "severity": "critical", "user_id": "primary",
         "delivered": True, "advice_ref": "2026-07-01|MARUTI|abc123"},
        {"date": "2026-07-01", "kind": "job_crashed_x", "symbol": "",
         "message": "m", "severity": "critical", "user_id": "primary",
         "delivered": True},
    ])
    store = AuditOutcomeStore(user_id="primary", base_dir=str(tmp_path))
    result = grade_alert_lane(
        date(2026, 7, 15), "primary", store=store, bench=_FakeBench(),
        price_fn=lambda s, d: 110.0, base_dir=str(tmp_path), sent_log=str(log),
    )
    assert result["graded"] == 1          # the ops alert is not a prediction
    assert store.load_all()[0].lane == "alert"


def test_shelf_lane_records_conviction_and_never_scores_correct(tmp_path):
    shelf = tmp_path / "shelf.json"
    shelf.write_text(json.dumps({"ideas": [{
        "symbol": "APOLLOTYRE", "sector": "automobile", "graph": "generic",
        "added": "2026-07-01", "conviction": 0.71, "verdict": "", "thesis": "",
        "entry_low": 0.0, "entry_high": 0.0, "invalidation_level": 0.0,
        "close_at_add": 100.0, "status": "active", "paper_cycle_id": "",
        "last_paper_review": "", "source_screen_date": "",
    }], "updated_at": ""}), encoding="utf-8")
    store = AuditOutcomeStore(user_id="primary", base_dir=str(tmp_path))
    result = grade_shelf_lane(
        date(2026, 7, 15), "primary", store=store, bench=_FakeBench(),
        price_fn=lambda s, d: 110.0, base_dir=str(tmp_path),
        shelf_path=str(shelf),
    )
    assert result["graded"] == 1
    row = store.load_all()[0]
    assert row.lane == "shelf" and row.conviction == 0.71
    assert row.correct is None            # a shelf add is not a call
    assert row.excess_pct == 9.0          # but the return is still recorded


def test_grade_due_sums_all_lanes(tmp_path):
    _write(tmp_path, "advice_ledger.jsonl", [{
        "date": "2026-07-01", "user_id": "primary", "symbol": "MARUTI",
        "verdict": "HOLD", "close": 100.0, "unrealised_pnl_pct": 0.0,
        "stop_pct": 8.0, "triggers": [], "notes": [], "confidence": 0.6,
        "narrative": "", "switch_candidate": "", "rationale_hash": "abc123",
    }])
    store = AuditOutcomeStore(user_id="primary", base_dir=str(tmp_path))
    result = grade_due(
        date(2026, 7, 15), "primary", store=store, bench=_FakeBench(),
        price_fn=lambda s, d: 110.0, base_dir=str(tmp_path),
        sent_log=str(tmp_path / "missing.jsonl"),
        shelf_path=str(tmp_path / "missing.json"),
    )
    assert result["graded"] == 1
    assert set(result["lanes"]) == {"advice", "alert", "shelf", "switch"}


def test_grade_due_never_raises_on_broken_lane(tmp_path):
    """A dead benchmark must degrade the run, not crash the nightly job.

    The ledger row matters: without a gradeable row the lanes return early and
    never reach the benchmark, so the test would pass without proving anything.
    sent_log/shelf_path are pinned at absent paths to keep the test off the
    real data/delivery and data/discovery files.
    """
    _write(tmp_path, "advice_ledger.jsonl", [{
        "date": "2026-07-01", "user_id": "primary", "symbol": "MARUTI",
        "verdict": "HOLD", "close": 100.0, "unrealised_pnl_pct": 0.0,
        "stop_pct": 8.0, "triggers": [], "notes": [], "confidence": 0.6,
        "narrative": "", "switch_candidate": "", "rationale_hash": "abc123",
    }])
    store = AuditOutcomeStore(user_id="primary", base_dir=str(tmp_path))

    class _Boom:
        def close_on(self, d):
            raise RuntimeError("benchmark down")

        def pct_change(self, start, end):
            raise RuntimeError("benchmark down")

    result = grade_due(
        date(2026, 7, 15), "primary", store=store, bench=_Boom(),
        price_fn=lambda s, d: 110.0, base_dir=str(tmp_path),
        sent_log=str(tmp_path / "missing.jsonl"),
        shelf_path=str(tmp_path / "missing.json"),
    )
    assert result["graded"] == 0     # degraded, not crashed
    assert result["skipped_unpriceable"] == 1
    assert store.load_all() == []
