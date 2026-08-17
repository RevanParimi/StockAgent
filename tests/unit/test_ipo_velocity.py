from core.ipo.signals import IpoSignalSnapshot
from core.ipo.velocity import demand_delta, final_demand_snapshot, latest_demand


def _s(captured_at, total, state="open"):
    return IpoSignalSnapshot(symbol="MOLBIO", captured_at=captured_at,
                             state=state, combined={"total": total})


def test_latest_demand_reads_the_newest_snapshot():
    snaps = [_s("2026-08-11T08:00:00+00:00", 2.0),
             _s("2026-08-13T18:00:00+00:00", 12.4)]
    assert latest_demand(snaps) == 12.4


def test_latest_demand_ignores_input_order():
    snaps = [_s("2026-08-13T18:00:00+00:00", 12.4),
             _s("2026-08-11T08:00:00+00:00", 2.0)]
    assert latest_demand(snaps) == 12.4


def test_demand_delta_is_the_change_since_the_previous_reading():
    snaps = [_s("2026-08-13T08:00:00+00:00", 9.3),
             _s("2026-08-13T18:00:00+00:00", 12.4)]
    assert round(demand_delta(snaps), 4) == 3.1


def test_a_single_snapshot_has_no_delta():
    """None, never 0.0 — zero would assert demand did not move."""
    assert demand_delta([_s("2026-08-13T08:00:00+00:00", 9.3)]) is None


def test_no_snapshots_is_none_everywhere():
    assert latest_demand([]) is None
    assert demand_delta([]) is None
    assert final_demand_snapshot([]) is None


def test_snapshots_without_a_total_are_not_readings():
    snaps = [IpoSignalSnapshot(symbol="X", captured_at="2026-08-13T08:00:00+00:00",
                               combined={"total": None}),
             _s("2026-08-13T18:00:00+00:00", 12.4)]
    assert latest_demand(snaps) == 12.4
    assert demand_delta(snaps) is None


def test_final_demand_snapshot_is_the_last_one_carrying_a_total():
    last = _s("2026-08-14T08:00:00+00:00", 12.4, state="closed")
    snaps = [_s("2026-08-13T08:00:00+00:00", 9.3), last,
             IpoSignalSnapshot(symbol="MOLBIO",
                               captured_at="2026-08-15T08:00:00+00:00",
                               state="closed", combined={"total": None})]
    assert final_demand_snapshot(snaps).captured_at == last.captured_at


def test_a_genuine_zero_total_is_a_real_reading_not_absence():
    """NSE can report a real 0.00 total. It must survive _readings — a
    truthiness filter here would silently drop a real reading."""
    snaps = [_s("2026-08-13T08:00:00+00:00", 0.0)]
    assert latest_demand(snaps) == 0.0
    assert final_demand_snapshot(snaps).combined["total"] == 0.0


def test_demand_delta_skips_a_non_reading_row_between_two_real_readings():
    """Three raw snapshots, the middle one carrying no total. The delta must be
    computed between the two REAL readings, not merely the last two rows."""
    snaps = [
        _s("2026-08-13T08:00:00+00:00", 9.3),
        IpoSignalSnapshot(symbol="MOLBIO",
                          captured_at="2026-08-13T12:00:00+00:00",
                          combined={"total": None}),
        _s("2026-08-13T18:00:00+00:00", 12.4),
    ]
    assert round(demand_delta(snaps), 4) == 3.1


def test_a_combined_dict_with_no_total_key_at_all_is_not_a_reading():
    """Absent key must behave exactly like an explicit None."""
    snaps = [IpoSignalSnapshot(symbol="MOLBIO",
                               captured_at="2026-08-13T08:00:00+00:00",
                               combined={"qib": 1.4}),
             _s("2026-08-13T18:00:00+00:00", 12.4)]
    assert latest_demand(snaps) == 12.4
    assert demand_delta(snaps) is None


def test_demand_delta_is_order_invariant():
    """Only latest_demand had an ordering test; delta shares _readings but was
    never proven to sort."""
    snaps = [_s("2026-08-13T18:00:00+00:00", 12.4),
             _s("2026-08-13T08:00:00+00:00", 9.3)]
    assert round(demand_delta(snaps), 4) == 3.1
