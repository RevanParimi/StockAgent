from backend.shared.schemas.audit import AuditOutcome
from core.audit.metrics import (
    coin_flip_p, hit_rate, mean_excess, per_trigger_precision,
)


def _row(correct=True, horizon=30, verdict="HOLD", triggers=(), excess=1.0,
         lane="advice"):
    return AuditOutcome(
        ref=f"r{id(triggers)}{correct}{horizon}{excess}", lane=lane,
        user_id="primary", symbol="MARUTI", verdict=verdict,
        triggers=list(triggers), issued_on="2026-07-01", horizon_td=horizon,
        graded_on="2026-08-14", entry_close=100.0, exit_close=110.0,
        return_pct=10.0, bench_entry=100.0, bench_exit=101.0, bench_pct=1.0,
        excess_pct=excess, correct=correct, graded_at="2026-08-14T00:00:00Z",
    )


def test_hit_rate_counts_only_scored_rows():
    rows = [_row(True), _row(False), _row(None, lane="shelf", verdict="")]
    r = hit_rate(rows)
    assert r.n == 2 and r.value == 0.5


def test_hit_rate_empty_returns_none_not_zero():
    r = hit_rate([])
    assert r.n == 0 and r.value is None


def test_hit_rate_filters_by_horizon_and_verdict():
    rows = [_row(True, horizon=10), _row(False, horizon=30),
            _row(True, horizon=30, verdict="EXIT")]
    assert hit_rate(rows, horizon=30).n == 2
    assert hit_rate(rows, horizon=30, verdict="EXIT").value == 1.0


def test_hit_rate_reports_wilson_interval():
    r = hit_rate([_row(True) for _ in range(10)])
    assert r.value == 1.0
    assert r.lo is not None and r.lo < 1.0     # interval is not degenerate
    assert r.hi == 1.0


def test_per_trigger_precision_groups_by_trigger():
    rows = [
        _row(True, triggers=("thesis_break",)),
        _row(False, triggers=("thesis_break",)),
        _row(True, triggers=("stop_breach",)),
    ]
    out = per_trigger_precision(rows)
    assert out["thesis_break"].n == 2 and out["thesis_break"].value == 0.5
    assert out["stop_breach"].n == 1


def test_row_with_two_triggers_counts_under_both():
    out = per_trigger_precision([_row(True, triggers=("thesis_break", "stop_breach"))])
    assert out["thesis_break"].n == 1 and out["stop_breach"].n == 1


def test_coin_flip_p_is_one_for_a_perfect_split():
    rows = [_row(True), _row(False)]
    assert coin_flip_p(rows) == 1.0


def test_coin_flip_p_is_small_for_a_lopsided_result():
    rows = [_row(True) for _ in range(20)]
    p = coin_flip_p(rows)
    assert p is not None and p < 0.001


def test_coin_flip_p_none_without_rows():
    assert coin_flip_p([]) is None


def test_mean_excess_averages_percentage_points():
    assert mean_excess([_row(excess=2.0), _row(excess=4.0)]) == 3.0
    assert mean_excess([]) is None
