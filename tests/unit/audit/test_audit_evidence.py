"""Gap D — whether a call was made blind must be recoverable afterwards."""
from datetime import date

from core.audit.evidence import news_availability_index, record_news_availability


def test_recorded_availability_is_readable_by_symbol_and_date(tmp_path):
    p = str(tmp_path / "news.jsonl")
    record_news_availability("MARUTI", date(2026, 8, 20), True, False, path=p)
    record_news_availability("SUZLON", date(2026, 8, 20), False, True, path=p)
    idx = news_availability_index(path=p)
    assert idx[("MARUTI", "2026-08-20")] is True
    assert idx[("SUZLON", "2026-08-20")] is False


def test_a_later_record_wins_for_the_same_symbol_and_day(tmp_path):
    """Append-only storage plus a re-run must not leave the index ambiguous."""
    p = str(tmp_path / "news.jsonl")
    record_news_availability("MARUTI", date(2026, 8, 20), False, False, path=p)
    record_news_availability("MARUTI", date(2026, 8, 20), True, False, path=p)
    assert news_availability_index(path=p)[("MARUTI", "2026-08-20")] is True


def test_a_missing_file_is_an_empty_index_not_an_error(tmp_path):
    assert news_availability_index(path=str(tmp_path / "absent.jsonl")) == {}


def test_recording_never_raises_on_an_unwritable_path(tmp_path):
    """Telemetry about telemetry must not be able to fail a daily review."""
    bad = str(tmp_path / "file.txt")
    with open(bad, "w", encoding="utf-8") as fh:
        fh.write("x")
    record_news_availability("X", date(2026, 8, 20), True, False,
                             path=str(tmp_path / "file.txt" / "nested.jsonl"))


def test_a_corrupt_line_does_not_break_the_index(tmp_path):
    p = tmp_path / "news.jsonl"
    record_news_availability("MARUTI", date(2026, 8, 20), True, False, path=str(p))
    with open(p, "a", encoding="utf-8") as fh:
        fh.write("{broken\n")
    assert len(news_availability_index(path=str(p))) == 1
