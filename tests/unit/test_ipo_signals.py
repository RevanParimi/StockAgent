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


def test_prune_keeps_a_row_whose_timestamp_cannot_be_parsed(tmp_path):
    """prune() is the one path that can delete captured data, and it promises
    to keep rows it cannot date. Deleting data we cannot date is the worse error."""
    store = IpoSignalStore(base_dir=str(tmp_path))
    now = datetime(2026, 8, 13, tzinfo=timezone.utc)
    store.append(_snap(captured_at=(now - timedelta(days=500)).isoformat(), total=2.05))
    store.append(_snap(captured_at="not-a-real-timestamp", total=9.80))
    assert store.prune(older_than_days=400, now=now) == 1      # only the datable-old row
    survivors = store.load_all()
    assert len(survivors) == 1
    assert survivors[0].captured_at == "not-a-real-timestamp"


def test_prune_with_zero_retention_is_a_no_op_not_a_wipe(tmp_path):
    """0 is the near-universal 'disabled' convention. cutoff = now - 0 would
    empty `keep` and delete every row — the one path that can destroy the
    whole ledger. Must be a no-op instead.

    Both rows here are captured CLEARLY before `now` (30d and 500d back), not
    at `now` itself: a row captured at exactly `now` would survive the old,
    unguarded `cutoff = now - 0d == now` by coincidence (the `>=` comparison
    keeps anything not strictly older than cutoff), passing this test for the
    wrong reason even with the guard removed. Old rows discriminate for real.
    """
    store = IpoSignalStore(base_dir=str(tmp_path))
    now = datetime(2026, 8, 13, tzinfo=timezone.utc)
    store.append(_snap(captured_at=(now - timedelta(days=30)).isoformat(), total=2.05))
    store.append(_snap(captured_at=(now - timedelta(days=500)).isoformat(), total=3.40))
    before = store.path.read_bytes()
    assert store.prune(older_than_days=0, now=now) == 0
    assert store.path.read_bytes() == before
    assert len(store.load_all()) == 2


def test_prune_with_negative_retention_is_a_no_op_not_a_wipe(tmp_path):
    store = IpoSignalStore(base_dir=str(tmp_path))
    now = datetime(2026, 8, 13, tzinfo=timezone.utc)
    store.append(_snap(captured_at=now.isoformat()))
    before = store.path.read_bytes()
    assert store.prune(older_than_days=-5, now=now) == 0
    assert store.path.read_bytes() == before
    assert len(store.load_all()) == 1


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


# ---------------------------------------------------------------------------
# prune() is the ledger's only rewrite path, and load_all()'s corrupt-line
# tolerance turned it into permanent deletion: it wrote back only the rows that
# parsed. It runs twice daily in production, immediately after capture.
# ---------------------------------------------------------------------------

def test_prune_refuses_to_rewrite_a_file_it_cannot_fully_parse(tmp_path):
    from core.ipo.ledger import LedgerIntegrityError
    store = IpoSignalStore(base_dir=str(tmp_path))
    now = datetime(2026, 8, 18, 6, 0, tzinfo=timezone.utc)
    store.append(IpoSignalSnapshot(symbol="AAA", captured_at="2024-01-01T06:00:00+00:00",
                                   combined={"total": 1.0}))
    with open(store.path, "a", encoding="utf-8") as fh:
        fh.write("{not json\n")
    before = store.path.read_text(encoding="utf-8")

    try:
        store.prune(older_than_days=400, now=now)
        raise AssertionError("prune rewrote a file it could not fully parse")
    except LedgerIntegrityError:
        pass

    assert store.path.read_text(encoding="utf-8") == before


def test_append_still_lands_alongside_a_corrupt_line(tmp_path):
    """Capture is append-only and cannot lose data, so one bad line must never
    stop the twice-daily snapshot from landing."""
    store = IpoSignalStore(base_dir=str(tmp_path))
    store.append(IpoSignalSnapshot(symbol="AAA", captured_at="2026-08-18T06:00:00+00:00",
                                   combined={"total": 1.0}))
    with open(store.path, "a", encoding="utf-8") as fh:
        fh.write("{not json\n")
    assert store.append(IpoSignalSnapshot(symbol="BBB",
                                          captured_at="2026-08-18T06:00:00+00:00",
                                          combined={"total": 2.0})) is True
    assert {r.symbol for r in store.load_all()} == {"AAA", "BBB"}


def test_content_dedup_compares_against_the_chronologically_newest_row(tmp_path):
    """append() picked the newest row for a symbol by FILE ORDER
    (symbol_rows[-1]) while load_symbol() sorts by captured_at. The two agree
    only under strictly append-only, in-order writes; they diverge the moment
    any out-of-order or backfill-style writer touches the ledger, and then the
    content-dedup rule silently vetoes a genuinely new reading.

    Here the file's last line is the OLDER row. The incoming snapshot repeats
    that older row's ladder but differs from the chronologically newest one, so
    it is a real change and must be written.
    """
    store = IpoSignalStore(base_dir=str(tmp_path))
    newer = IpoSignalSnapshot(symbol="AAA", captured_at="2026-08-18T08:00:00+00:00",
                              combined={"total": 2.0})
    older = IpoSignalSnapshot(symbol="AAA", captured_at="2026-08-18T06:00:00+00:00",
                              combined={"total": 1.0})
    assert store.append(newer) is True
    assert store.append(older) is True          # lands AFTER newer in the file
    assert [r.captured_at for r in store.load_all()][-1] == older.captured_at

    incoming = IpoSignalSnapshot(symbol="AAA", captured_at="2026-08-18T10:00:00+00:00",
                                 combined={"total": 1.0})
    assert store.append(incoming) is True
    assert len(store.load_symbol("AAA")) == 3


def test_content_dedup_still_vetoes_an_unchanged_reading_in_file_order(tmp_path):
    """The ordinary append-only case must keep deduping: NSE serves a closed
    issue's unchanged ladder for days, and appending byte-identical rows would
    make a later delta read a meaningless 0.0 forever."""
    store = IpoSignalStore(base_dir=str(tmp_path))
    assert store.append(IpoSignalSnapshot(
        symbol="BBB", captured_at="2026-08-18T06:00:00+00:00",
        combined={"total": 3.0})) is True
    assert store.append(IpoSignalSnapshot(
        symbol="BBB", captured_at="2026-08-18T18:00:00+00:00",
        combined={"total": 3.0})) is False
