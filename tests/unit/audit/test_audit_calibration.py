from backend.shared.schemas.audit import AuditOutcome
from core.audit.metrics import (
    calibration_spread, conviction_calibration, portfolio_vs_benchmark,
)


def _shelf(conviction, excess, horizon=30):
    return AuditOutcome(
        ref=f"shelf:{conviction}:{excess}", lane="shelf", user_id="primary",
        symbol="X", verdict="", triggers=[], issued_on="2026-07-01",
        horizon_td=horizon, graded_on="2026-08-14", entry_close=100.0,
        exit_close=110.0, return_pct=10.0, bench_entry=100.0,
        bench_exit=101.0, bench_pct=1.0, excess_pct=excess, correct=None,
        graded_at="2026-08-14T00:00:00Z", conviction=conviction,
    )


def test_calibration_buckets_by_conviction():
    rows = [_shelf(0.1, -5.0), _shelf(0.2, -3.0), _shelf(0.9, 6.0), _shelf(0.8, 4.0)]
    buckets = conviction_calibration(rows, horizon=30, buckets=2)
    assert len(buckets) == 2
    assert buckets[0]["mean_excess"] == -4.0     # low conviction
    assert buckets[-1]["mean_excess"] == 5.0     # high conviction


def test_calibration_ignores_non_shelf_rows():
    advice = _shelf(0.5, 1.0).model_copy(update={"lane": "advice", "conviction": None})
    assert conviction_calibration([advice], horizon=30) == []


def test_calibration_empty_returns_empty_list():
    assert conviction_calibration([], horizon=30) == []


def test_spread_is_top_minus_bottom_populated_bucket():
    rows = [_shelf(0.1, -4.0), _shelf(0.9, 5.0)]
    buckets = conviction_calibration(rows, horizon=30, buckets=2)
    assert calibration_spread(buckets) == 9.0


def test_spread_none_when_fewer_than_two_populated_buckets():
    buckets = conviction_calibration([_shelf(0.9, 5.0)], horizon=30, buckets=2)
    assert calibration_spread(buckets) is None


def test_portfolio_vs_benchmark_reports_excess():
    history = [
        {"date": "2026-06-01", "market_value": 100000.0},
        {"date": "2026-08-01", "market_value": 112000.0},
    ]
    out = portfolio_vs_benchmark(history, bench_pct=5.0)
    assert out["portfolio_pct"] == 12.0
    assert out["bench_pct"] == 5.0
    assert out["excess_pct"] == 7.0


def test_portfolio_vs_benchmark_needs_two_points():
    out = portfolio_vs_benchmark([{"date": "2026-06-01", "market_value": 1.0}], 5.0)
    assert out["portfolio_pct"] is None and out["excess_pct"] is None
