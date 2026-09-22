"""IPO-3d — the verdict store. Offline, one tmp_path JSONL per test.

The rules that matter here are the ones that protect the rows the IPO-5b gate
will be measured on: an extended close date is a NEW row and never an
overwrite, an unchanged re-run does not double-count the issue, the raw
features survive so a later anchor change can be replayed, and no rewrite can
delete a line it could not parse.
"""
import json
from datetime import datetime, timedelta, timezone

import pytest

from core.ipo.hype import HypeReading
from core.ipo.ledger import LedgerIntegrityError
from core.ipo.substance import SubstanceReading
from core.ipo.verdict import IpoVerdict, LongView, ShortView
from core.ipo.verdicts import IpoVerdictRecord, IpoVerdictStore


def _verdict(symbol="VARMORA", close_date="2026-09-24", lean="strong", demand=80.0,
             **kw):
    return IpoVerdict(symbol=symbol, close_date=close_date, as_of="2026-09-23T13:30:00+00:00",
                      state="closed", demand=demand, hype=20.0, substance=60.0,
                      quadrant="quiet_compounder",
                      short=ShortView(lean=lean, band=(15.1, 51.5), evidenced=True,
                                      basis="because the spine says so"),
                      long=LongView(basis="dark", h_minus_s=-40.0), **kw)


def _hype(**kw):
    return HypeReading(symbol="VARMORA", as_of="2026-09-23T13:30:00+00:00", state="closed",
                       features={"qib_x": 40.35, "total_x": 30.0, "ofs_share": 0.8},
                       components={"qib_x": 0.5}, demand=80.0, froth=20.0, **kw)


def _sub(features=None, **kw):
    return SubstanceReading(symbol="VARMORA", index=60.0,
                            features=features or {"pat_growth": 1.107,
                                                  "revenue_growth": 1.003},
                            components={"pat_growth": 0.42}, **kw)


def _ts(days_ago, now):
    return (now - timedelta(days=days_ago)).isoformat()


# ─────────────────────────── round trip ───────────────────────────────────

def test_append_then_load_round_trips(tmp_path):
    store = IpoVerdictStore(base_dir=str(tmp_path))
    assert store.append(_verdict(), _hype(), _sub()) is True
    rows = store.load_all()
    assert len(rows) == 1 and rows[0].key == ("VARMORA", "2026-09-24")
    assert rows[0].verdict.short.lean == "strong"
    assert rows[0].verdict.short.band == (15.1, 51.5)
    assert rows[0].written_at


def test_the_row_keeps_the_raw_features_so_a_new_anchor_can_be_replayed(tmp_path):
    """The indices are a function of anchors that WILL move. Without the
    features behind them a stored verdict cannot be re-asked under new ones."""
    store = IpoVerdictStore(base_dir=str(tmp_path))
    store.append(_verdict(), _hype(), _sub())
    row = store.load_all()[0]
    assert row.hype.features["qib_x"] == 40.35
    assert row.substance.features["pat_growth"] == 1.107
    assert row.hype.components["qib_x"] == 0.5


def test_a_verdict_stores_without_its_readings(tmp_path):
    store = IpoVerdictStore(base_dir=str(tmp_path))
    assert store.append(_verdict()) is True
    row = store.load_all()[0]
    assert row.verdict.symbol == "VARMORA" and row.hype.features == {}


def test_a_verdict_with_no_symbol_is_refused(tmp_path):
    """An unkeyed row cannot be found again, so the gate would count it
    against nothing."""
    store = IpoVerdictStore(base_dir=str(tmp_path))
    assert store.append(IpoVerdict(close_date="2026-09-24")) is False
    assert store.load_all() == []


# ─────────────────── the key, and what counts as a new row ────────────────

def test_an_extended_close_date_is_a_new_row_not_an_overwrite(tmp_path):
    """The extension is not a correction — it is a second book with its own
    final demand. Keying on the symbol alone would discard the first read."""
    store = IpoVerdictStore(base_dir=str(tmp_path))
    assert store.append(_verdict(close_date="2026-09-24", lean="strong")) is True
    assert store.append(_verdict(close_date="2026-09-26", lean="mixed")) is True
    rows = store.load_all()
    assert len(rows) == 2
    assert {r.verdict.close_date for r in rows} == {"2026-09-24", "2026-09-26"}
    assert store.latest("VARMORA", "2026-09-24").verdict.short.lean == "strong"
    assert store.latest("VARMORA", "2026-09-26").verdict.short.lean == "mixed"


def test_an_unchanged_re_run_does_not_double_count_the_issue(tmp_path):
    store = IpoVerdictStore(base_dir=str(tmp_path))
    assert store.append(_verdict(), _hype(), _sub()) is True
    assert store.append(_verdict(), _hype(), _sub()) is False
    assert len(store.load_all()) == 1


def test_a_changed_verdict_for_the_same_key_is_appended(tmp_path):
    """Research that finally corroborated, or a book that moved, is a new
    reading of the same issue — both are kept, newest wins on read."""
    store = IpoVerdictStore(base_dir=str(tmp_path))
    store.append(_verdict(lean="mixed", demand=50.0))
    assert store.append(_verdict(lean="strong", demand=80.0)) is True
    rows = store.load_key("VARMORA", "2026-09-24")
    assert [r.verdict.short.lean for r in rows] == ["mixed", "strong"]
    assert store.latest("VARMORA", "2026-09-24").verdict.demand == 80.0


def test_better_evidence_behind_the_same_verdict_is_still_a_new_row(tmp_path):
    """The features are the half of the row that makes a replay possible, so a
    run that learned more must not be vetoed by a verdict that did not move."""
    store = IpoVerdictStore(base_dir=str(tmp_path))
    thin = _sub(features={"pat_growth": None}, dark=["pat_growth"])
    assert store.append(_verdict(), _hype(), thin) is True
    assert store.append(_verdict(), _hype(), _sub()) is True
    rows = store.load_key("VARMORA", "2026-09-24")
    assert [r.substance.features.get("pat_growth") for r in rows] == [None, 1.107]
    assert rows[0].verdict.model_dump() == rows[1].verdict.model_dump()


def test_crossing_from_open_to_closed_is_a_new_row_even_at_identical_numbers(tmp_path):
    """The numbers did not move but the evidence did: the lean is now
    admissible. That change is exactly what the gate needs to see."""
    store = IpoVerdictStore(base_dir=str(tmp_path))
    interim = _verdict()
    interim.state = "open"
    interim.short.evidenced = False
    assert store.append(interim) is True
    assert store.append(_verdict()) is True          # state closed, evidenced True
    assert len(store.load_all()) == 2


def test_two_issues_do_not_dedup_against_each_other(tmp_path):
    store = IpoVerdictStore(base_dir=str(tmp_path))
    assert store.append(_verdict(symbol="VARMORA")) is True
    assert store.append(_verdict(symbol="NSE")) is True
    assert len(store.load_all()) == 2


def test_load_key_returns_oldest_first(tmp_path):
    store = IpoVerdictStore(base_dir=str(tmp_path))
    store.append(_verdict(lean="weak"), written_at="2026-09-23T10:00:00+00:00")
    store.append(_verdict(lean="strong"), written_at="2026-09-23T19:00:00+00:00")
    rows = store.load_key("VARMORA", "2026-09-24")
    assert [r.written_at for r in rows] == ["2026-09-23T10:00:00+00:00",
                                            "2026-09-23T19:00:00+00:00"]


def test_latest_on_an_unknown_key_is_none(tmp_path):
    store = IpoVerdictStore(base_dir=str(tmp_path))
    assert store.latest("NOBODY", "2026-09-24") is None
    assert store.load_key("NOBODY", "2026-09-24") == []


# ─────────────────────────── read tolerance ───────────────────────────────

def test_a_corrupt_line_never_breaks_a_read(tmp_path):
    store = IpoVerdictStore(base_dir=str(tmp_path))
    store.append(_verdict())
    with open(store.path, "a", encoding="utf-8") as fh:
        fh.write("{not json at all\n")
    store.append(_verdict(close_date="2026-09-26"))
    assert len(store.load_all()) == 2


def test_reading_a_store_that_was_never_written_is_empty_not_an_error(tmp_path):
    assert IpoVerdictStore(base_dir=str(tmp_path / "fresh")).load_all() == []


# ─────────────────────────── prune ────────────────────────────────────────

def test_prune_drops_only_rows_older_than_the_window(tmp_path):
    now = datetime.now(timezone.utc)
    store = IpoVerdictStore(base_dir=str(tmp_path))
    store.append(_verdict(close_date="2024-01-10"), written_at=_ts(1300, now))
    store.append(_verdict(close_date="2026-09-24"), written_at=_ts(10, now))
    assert store.prune(1200, now=now) == 1
    assert [r.verdict.close_date for r in store.load_all()] == ["2026-09-24"]


def test_prune_with_a_wide_window_is_a_no_op(tmp_path):
    now = datetime.now(timezone.utc)
    store = IpoVerdictStore(base_dir=str(tmp_path))
    store.append(_verdict(), written_at=_ts(30, now))
    assert store.prune(1200, now=now) == 0
    assert len(store.load_all()) == 1


@pytest.mark.parametrize("retention", [0, -1])
def test_prune_with_no_retention_is_a_no_op_not_a_wipe(tmp_path, retention):
    """0 is this codebase's convention for disabled. A caller meaning that
    must not have the store emptied out from under them."""
    now = datetime.now(timezone.utc)
    store = IpoVerdictStore(base_dir=str(tmp_path))
    store.append(_verdict(), written_at=_ts(5000, now))
    assert store.prune(retention, now=now) == 0
    assert len(store.load_all()) == 1


def test_prune_keeps_a_row_whose_timestamp_cannot_be_parsed(tmp_path):
    """Deleting data we cannot date is the worse error."""
    now = datetime.now(timezone.utc)
    store = IpoVerdictStore(base_dir=str(tmp_path))
    store.append(_verdict(close_date="2024-01-10"), written_at="not a timestamp")
    store.append(_verdict(close_date="2020-01-10"), written_at=_ts(1300, now))
    assert store.prune(1200, now=now) == 1
    assert [r.written_at for r in store.load_all()] == ["not a timestamp"]


def test_prune_refuses_to_rewrite_a_file_it_cannot_fully_parse(tmp_path):
    """The read tolerance above plus a rewrite equals silent deletion. The
    guard turns that into a loud, recoverable refusal."""
    now = datetime.now(timezone.utc)
    store = IpoVerdictStore(base_dir=str(tmp_path))
    store.append(_verdict(close_date="2024-01-10"), written_at=_ts(1300, now))
    store.append(_verdict(close_date="2026-09-24"), written_at=_ts(10, now))
    with open(store.path, "a", encoding="utf-8") as fh:
        fh.write("{half a row\n")
    before = store.path.read_text(encoding="utf-8")
    with pytest.raises(LedgerIntegrityError):
        store.prune(1200, now=now)
    assert store.path.read_text(encoding="utf-8") == before   # nothing written


def test_append_still_lands_alongside_a_corrupt_line(tmp_path):
    """An append cannot drop a line, so a corrupt store must not stop capture."""
    store = IpoVerdictStore(base_dir=str(tmp_path))
    with open(store.path, "w", encoding="utf-8") as fh:
        fh.write("{broken\n")
    assert store.append(_verdict()) is True
    assert len(store.load_all()) == 1


def test_a_naive_timestamp_is_treated_as_utc_not_crashed_on(tmp_path):
    now = datetime.now(timezone.utc)
    store = IpoVerdictStore(base_dir=str(tmp_path))
    store.append(_verdict(), written_at=(now - timedelta(days=1300))
                 .replace(tzinfo=None).isoformat())
    assert store.prune(1200, now=now) == 1


# ─────────────────────────── the file on disk ─────────────────────────────

def test_the_file_is_jsonl_at_the_documented_path(tmp_path):
    store = IpoVerdictStore(base_dir=str(tmp_path))
    store.append(_verdict(), _hype(), _sub())
    assert store.path.name == "ipo_verdicts.jsonl"
    payload = json.loads(store.path.read_text(encoding="utf-8").splitlines()[0])
    # `narration` joined the row at IPO-4b: prose about the reading, outside
    # the dedup rule, never an input to it.
    assert set(payload) == {"written_at", "verdict", "hype", "substance", "narration"}
    assert payload["verdict"]["long"]["lean"] is None
    assert IpoVerdictRecord(**payload).verdict.symbol == "VARMORA"
