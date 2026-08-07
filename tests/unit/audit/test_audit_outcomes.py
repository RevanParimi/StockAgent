import json
from datetime import date

from core.audit.outcomes import grade_advice_lane
from core.audit.store import AuditOutcomeStore


class _FakeBench:
    """Deterministic benchmark: +1% over any window that starts on the issue
    date. The 2026-07-02 boundary matches the price_fn fixtures below — it has
    to fall between issue (2026-07-01) and maturity (2026-07-15), or the
    benchmark never moves and every excess collapses to the raw return."""
    def close_on(self, d):
        return 100.0 if d < date(2026, 7, 2) else 101.0

    def pct_change(self, start, end):
        return round((self.close_on(end) / self.close_on(start) - 1.0) * 100.0, 4)


def _write_ledger(tmp_path, rows):
    d = tmp_path / "primary"
    d.mkdir(parents=True, exist_ok=True)
    with open(d / "advice_ledger.jsonl", "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def _advice(date_str="2026-07-01", verdict="HOLD", close=100.0):
    return {
        "date": date_str, "user_id": "primary", "symbol": "MARUTI",
        "verdict": verdict, "close": close, "unrealised_pnl_pct": 0.0,
        "stop_pct": 8.0, "triggers": ["thesis_break"], "notes": [],
        "confidence": 0.6, "narrative": "", "switch_candidate": "",
        "rationale_hash": "abc123",
    }


def test_grades_matured_horizon_only(tmp_path):
    _write_ledger(tmp_path, [_advice()])
    store = AuditOutcomeStore(user_id="primary", base_dir=str(tmp_path))
    # 2026-07-15 is ~10 trading days after 2026-07-01, not yet 30 or 60.
    result = grade_advice_lane(
        date(2026, 7, 15), "primary", store=store, bench=_FakeBench(),
        price_fn=lambda sym, d: 110.0, base_dir=str(tmp_path),
    )
    assert result["graded"] == 1
    rows = store.load_all()
    assert [r.horizon_td for r in rows] == [10]


def test_grading_is_idempotent(tmp_path):
    _write_ledger(tmp_path, [_advice()])
    store = AuditOutcomeStore(user_id="primary", base_dir=str(tmp_path))
    kwargs = dict(store=store, bench=_FakeBench(),
                  price_fn=lambda sym, d: 110.0, base_dir=str(tmp_path))
    first = grade_advice_lane(date(2026, 7, 15), "primary", **kwargs)
    second = grade_advice_lane(date(2026, 7, 15), "primary", **kwargs)
    assert first["graded"] == 1
    assert second["graded"] == 0 and second["already_present"] == 1
    assert len(store.load_all()) == 1


def test_hold_beating_benchmark_is_correct(tmp_path):
    _write_ledger(tmp_path, [_advice(verdict="HOLD", close=100.0)])
    store = AuditOutcomeStore(user_id="primary", base_dir=str(tmp_path))
    grade_advice_lane(
        date(2026, 7, 15), "primary", store=store, bench=_FakeBench(),
        price_fn=lambda sym, d: 110.0, base_dir=str(tmp_path),
    )
    row = store.load_all()[0]
    assert row.return_pct == 10.0 and row.bench_pct == 1.0
    assert row.excess_pct == 9.0 and row.correct is True


def test_exit_beating_benchmark_is_incorrect(tmp_path):
    _write_ledger(tmp_path, [_advice(verdict="EXIT", close=100.0)])
    store = AuditOutcomeStore(user_id="primary", base_dir=str(tmp_path))
    grade_advice_lane(
        date(2026, 7, 15), "primary", store=store, bench=_FakeBench(),
        price_fn=lambda sym, d: 110.0, base_dir=str(tmp_path),
    )
    assert store.load_all()[0].correct is False


def test_unpriceable_symbol_is_counted_not_fatal(tmp_path):
    def _boom(sym, d):
        raise RuntimeError("delisted")

    _write_ledger(tmp_path, [_advice()])
    store = AuditOutcomeStore(user_id="primary", base_dir=str(tmp_path))
    result = grade_advice_lane(
        date(2026, 7, 15), "primary", store=store, bench=_FakeBench(),
        price_fn=_boom, base_dir=str(tmp_path),
    )
    assert result["graded"] == 0 and result["skipped_unpriceable"] == 1
    assert store.load_all() == []


def test_missing_ledger_returns_zeros(tmp_path):
    store = AuditOutcomeStore(user_id="primary", base_dir=str(tmp_path))
    result = grade_advice_lane(
        date(2026, 7, 15), "primary", store=store, bench=_FakeBench(),
        price_fn=lambda sym, d: 110.0, base_dir=str(tmp_path),
    )
    assert result == {"graded": 0, "skipped_unpriceable": 0, "already_present": 0}


def test_switch_records_the_candidate_excess(tmp_path):
    """A SWITCH is graded on whether the DESTINATION beat the ORIGIN, not
    merely on whether the origin fell (design section 5)."""
    row = _advice(verdict="SWITCH", close=100.0)
    row["switch_candidate"] = "M&M"
    _write_ledger(tmp_path, [row])
    store = AuditOutcomeStore(user_id="primary", base_dir=str(tmp_path))
    prices = {"MARUTI": 110.0, "M&M": 130.0}
    grade_advice_lane(
        date(2026, 7, 15), "primary", store=store, bench=_FakeBench(),
        price_fn=lambda sym, d: prices[sym] if d > date(2026, 7, 2) else 100.0,
        base_dir=str(tmp_path),
    )
    out = store.load_all()[0]
    assert out.excess_pct == 9.0            # MARUTI: +10% vs +1% bench
    assert out.switch_excess_pct == 29.0    # M&M:    +30% vs +1% bench


def test_switch_with_unpriceable_candidate_still_grades_the_origin(tmp_path):
    row = _advice(verdict="SWITCH", close=100.0)
    row["switch_candidate"] = "DELISTED"
    _write_ledger(tmp_path, [row])
    store = AuditOutcomeStore(user_id="primary", base_dir=str(tmp_path))

    def _price(sym, d):
        if sym == "DELISTED":
            raise RuntimeError("no such symbol")
        return 110.0 if d > date(2026, 7, 2) else 100.0

    result = grade_advice_lane(
        date(2026, 7, 15), "primary", store=store, bench=_FakeBench(),
        price_fn=_price, base_dir=str(tmp_path),
    )
    assert result["graded"] == 1
    out = store.load_all()[0]
    assert out.switch_excess_pct is None    # absent, not fatal
    assert out.correct is False             # origin rose: leaving was wrong
