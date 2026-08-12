"""PI Prospect P1 — the measurement report."""
from core.ipo.history import IpoRecord
from core.ipo.report import render_report, summarise


def _rec(symbol, total_x, listing_pct):
    return IpoRecord(symbol=symbol, issue_price=100.0, total_x=total_x,
                     outcomes={"1": listing_pct}, excess={"1": listing_pct},
                     sessions_available=260)


def test_buckets_by_subscription_and_reports_n():
    rows = [_rec("A", 50.0, 30.0), _rec("B", 40.0, 20.0),
            _rec("C", 1.5, -10.0), _rec("D", 1.0, -5.0)]
    out = summarise(rows)
    hot = out["by_subscription"]["hot (>=10x)"]
    cold = out["by_subscription"]["cold (<2x)"]
    assert hot["n"] == 2 and cold["n"] == 2
    assert hot["mean_listing_pct"] == 25.0
    assert cold["mean_listing_pct"] == -7.5


def test_rows_without_the_feature_are_excluded_not_zeroed():
    rows = [_rec("A", 50.0, 30.0), _rec("B", None, 20.0)]
    out = summarise(rows)
    assert sum(b["n"] for b in out["by_subscription"].values()) == 1
    assert out["missing_subscription"] == 1


def test_report_states_sample_size_and_the_gmp_caveat():
    text = render_report(summarise([_rec("A", 50.0, 30.0)]))
    assert "n=" in text
    assert "GMP" in text          # the forward-validation caveat must survive


def test_empty_history_does_not_crash():
    out = summarise([])
    assert out["total"] == 0
    assert "no rows" in render_report(out).lower()
