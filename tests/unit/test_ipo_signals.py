import json
from datetime import datetime, timedelta, timezone

from core.ipo.signals import IpoSignalSnapshot, IpoSignalStore


def _snap(symbol="MOLBIO", captured_at="2026-08-13T08:00:00+00:00", total=2.05):
    return IpoSignalSnapshot(
        symbol=symbol,
        captured_at=captured_at,
        state="open",
        issue_start="2026-08-10",
        issue_end="2026-08-13",
        combined={"qib": 1.39, "fii": 0.9, "dom_fi": 0.2,
                  "mutual_fund": 0.3, "nii": 3.6, "retail": 4.1,
                  "employee": None, "total": total},
        nse_only={"qib": 0.564, "total": 1.2},
        cutoff_share=0.4633,
    )


def test_append_then_load_round_trips(tmp_path):
    store = IpoSignalStore(base_dir=str(tmp_path))
    assert store.append(_snap()) is True
    rows = store.load_all()
    assert len(rows) == 1
    assert rows[0].symbol == "MOLBIO"
    assert rows[0].combined["dom_fi"] == 0.2
    assert rows[0].cutoff_share == 0.4633


def test_same_symbol_and_hour_is_deduped(tmp_path):
    """A manual re-run of the refresh must not double-count demand."""
    store = IpoSignalStore(base_dir=str(tmp_path))
    assert store.append(_snap(captured_at="2026-08-13T08:00:00+00:00")) is True
    assert store.append(_snap(captured_at="2026-08-13T08:41:12+00:00")) is False
    assert len(store.load_all()) == 1


def test_a_different_hour_is_a_new_snapshot(tmp_path):
    """Same symbol, new hour, and a genuinely different reading (total moved)
    — must be appended. (Content is varied here on purpose: an identical
    reading at a new hour is exactly the closed-but-unlisted case the content
    dedup rule exists to catch — see test_identical_content_for_the_same_
    symbol_is_not_re_appended below.)"""
    store = IpoSignalStore(base_dir=str(tmp_path))
    store.append(_snap(captured_at="2026-08-13T08:00:00+00:00", total=2.05))
    assert store.append(_snap(captured_at="2026-08-13T12:15:00+00:00", total=3.40)) is True
    assert len(store.load_all()) == 2


def test_a_corrupt_line_never_breaks_a_read(tmp_path):
    store = IpoSignalStore(base_dir=str(tmp_path))
    store.append(_snap())
    with open(store.path, "a", encoding="utf-8") as fh:
        fh.write("{not json at all\n")
    # total varied vs. the first append: this test is about corrupt-line
    # resilience, not dedup, so the second row must be a genuinely new
    # reading or the content dedup rule would (correctly) swallow it.
    store.append(_snap(captured_at="2026-08-13T18:00:00+00:00", total=5.25))
    assert len(store.load_all()) == 2


def test_load_symbol_filters_and_sorts_oldest_first(tmp_path):
    store = IpoSignalStore(base_dir=str(tmp_path))
    # total varied between the two MOLBIO rows so both are genuinely new
    # readings and neither is swallowed by the content dedup rule.
    store.append(_snap(captured_at="2026-08-13T18:00:00+00:00", total=2.05))
    store.append(_snap(captured_at="2026-08-13T08:00:00+00:00", total=3.40))
    store.append(_snap(symbol="DHOOTTRANS", captured_at="2026-08-13T08:00:00+00:00"))
    rows = store.load_symbol("MOLBIO")
    assert [r.captured_at for r in rows] == [
        "2026-08-13T08:00:00+00:00", "2026-08-13T18:00:00+00:00"]


def test_prune_drops_only_rows_older_than_the_window(tmp_path):
    store = IpoSignalStore(base_dir=str(tmp_path))
    now = datetime(2026, 8, 13, tzinfo=timezone.utc)
    # total varied so the second row is a genuinely new reading rather than
    # being swallowed by the content dedup rule.
    store.append(_snap(captured_at=(now - timedelta(days=500)).isoformat(), total=2.05))
    store.append(_snap(captured_at=(now - timedelta(days=10)).isoformat(), total=3.40))
    assert store.prune(older_than_days=400, now=now) == 1
    assert len(store.load_all()) == 1


def test_prune_with_a_wide_window_is_a_no_op(tmp_path):
    """Guards the one code path that can delete captured data."""
    store = IpoSignalStore(base_dir=str(tmp_path))
    now = datetime(2026, 8, 13, tzinfo=timezone.utc)
    store.append(_snap(captured_at=(now - timedelta(days=10)).isoformat()))
    before = store.path.read_bytes()
    assert store.prune(older_than_days=400, now=now) == 0
    assert store.path.read_bytes() == before


def test_a_naive_timestamp_is_treated_as_utc_not_crashed_on(tmp_path):
    store = IpoSignalStore(base_dir=str(tmp_path))
    store.append(_snap(captured_at="2026-08-13T08:00:00"))
    now = datetime(2026, 8, 13, 12, tzinfo=timezone.utc)
    assert store.prune(older_than_days=400, now=now) == 0
    assert len(store.load_all()) == 1


def test_identical_content_for_the_same_symbol_is_not_re_appended(tmp_path):
    """A closed-but-unlisted issue keeps its ladder and would otherwise append
    a byte-identical row twice a day for days."""
    store = IpoSignalStore(base_dir=str(tmp_path))
    assert store.append(_snap(captured_at="2026-08-13T08:00:00+00:00")) is True
    assert store.append(_snap(captured_at="2026-08-14T08:00:00+00:00")) is False
    assert len(store.load_all()) == 1


def test_a_changed_total_is_appended_even_at_identical_content_otherwise(tmp_path):
    store = IpoSignalStore(base_dir=str(tmp_path))
    store.append(_snap(captured_at="2026-08-13T08:00:00+00:00", total=2.05))
    assert store.append(_snap(captured_at="2026-08-14T08:00:00+00:00", total=9.80)) is True
    assert len(store.load_all()) == 2
