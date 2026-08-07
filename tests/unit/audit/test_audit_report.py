from backend.shared.schemas.audit import AuditOutcome
from core.audit.metrics import Rate
from core.audit.report import build_report, classify, render_section
from core.audit.store import AuditOutcomeStore


def _row(correct=True, horizon=60, excess=2.0, i=0):
    return AuditOutcome(
        ref=f"r{i}", lane="advice", user_id="primary", symbol="MARUTI",
        verdict="HOLD", triggers=["thesis_break"], issued_on="2026-07-01",
        horizon_td=horizon, graded_on="2026-08-14", entry_close=100.0,
        exit_close=110.0, return_pct=10.0, bench_entry=100.0,
        bench_exit=101.0, bench_pct=1.0, excess_pct=excess, correct=correct,
        graded_at="2026-08-14T00:00:00Z",
    )


def test_classify_insufficient_below_min_n():
    assert classify(Rate(5, 0.9, 0.6, 1.0), 0.01, 3.0, min_n=30) == "INSUFFICIENT_DATA"


def test_classify_below_coin_flip():
    assert classify(Rate(40, 0.30, 0.2, 0.45), 0.004, -2.0, min_n=30) == "BELOW_COIN_FLIP"


def test_classify_beats_benchmark():
    assert classify(Rate(40, 0.72, 0.6, 0.85), 0.004, 3.0, min_n=30) == "BEATS_BENCHMARK"


def test_classify_unproven_when_not_significant():
    assert classify(Rate(40, 0.55, 0.4, 0.7), 0.42, 0.4, min_n=30) == "UNPROVEN"


def test_classify_empty_is_insufficient():
    assert classify(Rate(0, None, None, None), None, None, min_n=30) == "INSUFFICIENT_DATA"


def test_build_report_on_empty_store_says_insufficient(tmp_path):
    store = AuditOutcomeStore(user_id="primary", base_dir=str(tmp_path))
    report = build_report("primary", store=store)
    assert report["verdict"] == "INSUFFICIENT_DATA"
    assert report["total_rows"] == 0
    assert report["hit_rate"]["60"]["n"] == 0


def test_build_report_populates_horizons_and_triggers(tmp_path):
    store = AuditOutcomeStore(user_id="primary", base_dir=str(tmp_path))
    for i in range(40):
        store.append(_row(correct=(i % 4 != 0), i=i))
    report = build_report("primary", store=store, min_n=30)
    assert report["total_rows"] == 40
    assert report["hit_rate"]["60"]["n"] == 40
    assert report["per_trigger"]["thesis_break"]["n"] == 40
    assert report["verdict"] in ("BEATS_BENCHMARK", "UNPROVEN")


def test_render_section_is_plain_text_with_the_verdict(tmp_path):
    store = AuditOutcomeStore(user_id="primary", base_dir=str(tmp_path))
    text = render_section(build_report("primary", store=store))
    assert "INSUFFICIENT_DATA" in text
    assert "Advice outcomes" in text
