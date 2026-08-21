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
    # per_trigger now reads audit.per_trigger_horizon_td (default 10td) rather
    # than the hardcoded 60td that made this block render empty on real data,
    # so the trigger rows have to be at the horizon it reads.
    for i in range(40, 80):
        store.append(_row(correct=(i % 4 != 0), horizon=10, i=i))
    report = build_report("primary", store=store, min_n=30)
    assert report["total_rows"] == 80
    assert report["hit_rate"]["60"]["n"] == 40
    assert report["per_trigger"]["thesis_break"]["n"] == 40
    assert report["verdict"] in ("BEATS_BENCHMARK", "UNPROVEN")


def test_render_section_is_plain_text_with_the_verdict(tmp_path):
    store = AuditOutcomeStore(user_id="primary", base_dir=str(tmp_path))
    text = render_section(build_report("primary", store=store))
    assert "INSUFFICIENT_DATA" in text
    assert "Advice outcomes" in text


# -- switch blocks + the horizon fix (2026-08-20) --------------------------

def _sw(issued, horizon=10, origin_excess=-2.0, dest_excess=3.0,
        decision="rejected", reason="not_best"):
    return AuditOutcome(
        ref=f"switch:{issued}|OLD|NEW", lane="switch", user_id="u", symbol="OLD",
        candidate="NEW", triggers=[decision, reason], issued_on=issued,
        horizon_td=horizon, graded_on=issued, entry_close=100.0,
        exit_close=98.0, return_pct=-2.0, bench_entry=1.0, bench_exit=1.0,
        bench_pct=0.0, excess_pct=origin_excess, switch_excess_pct=dest_excess,
        correct=dest_excess > origin_excess,
        graded_at="2026-09-01T00:00:00+00:00")


class _Store:
    user_id = "u"

    def __init__(self, rows):
        self._rows = rows

    def load_all(self):
        return self._rows


def test_switch_rule_block_reports_raw_n_and_effective_n_separately():
    rows = [_sw(f"2026-08-{d:02d}") for d in range(3, 13)]   # one pair, 10 days
    block = build_report(store=_Store(rows))["switch_rule"]
    assert block["n"] == 10
    assert block["n_effective"] == 1


def test_a_large_raw_n_of_overlapping_rows_still_reads_insufficient_data():
    """The specific dishonesty this design exists to prevent: 100+ overlapping
    observations of one pair are not 100+ observations."""
    rows = [_sw(f"2026-{m:02d}-{d:02d}")
            for m in (3, 4, 5, 6) for d in range(1, 29)]
    block = build_report(store=_Store(rows))["switch_rule"]
    assert block["n"] > 100
    assert block["verdict"] == "INSUFFICIENT_DATA"


def test_taken_and_rejected_pairs_are_reported_separately():
    rows = [_sw("2026-03-02", decision="taken", reason=""),
            _sw("2026-04-02", decision="rejected")]
    report = build_report(store=_Store(rows))
    assert report["switch_taken"]["n"] == 1
    assert report["switch_rule"]["n"] == 2


def test_per_reason_uses_only_switch_lane_rows():
    """per_trigger_precision filters on `correct is not None` and nothing else,
    so handing it the whole store blends advisor trigger codes with switch
    reason codes and reports a meaningless mixture."""
    block = build_report(store=_Store([_sw("2026-03-02"), _row(i=1)]))["switch_rule"]
    assert "thesis_break" not in block["per_reason"]
    assert "not_best" in block["per_reason"]


def test_per_trigger_horizon_is_configurable_and_no_longer_hardcoded_to_60():
    """The existing defect: per_trigger read at 60td and conviction at 30td, so
    both blocks rendered empty on real data."""
    report = build_report(store=_Store([_row(horizon=10, i=2)]))
    assert "thesis_break" in report["per_trigger"]


def test_attribution_block_is_present():
    report = build_report(store=_Store([_sw("2026-03-02", dest_excess=-9.0)]))
    assert "attribution" in report and "n_classified" in report["attribution"]
