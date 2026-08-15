"""PI Prospect P1 — the historical spine store."""
from core.ipo.history import IpoHistoryStore, IpoRecord

_REC = dict(symbol="NEWCO", company="NewCo Ltd", listing_date="2026-06-15",
            issue_price=315.0, total_x=22.7, qib_x=45.2, retail_x=8.1)


def test_round_trip(tmp_path):
    store = IpoHistoryStore(base_dir=str(tmp_path))
    store.append(IpoRecord(**_REC))
    rows = store.load_all()
    assert len(rows) == 1 and rows[0].symbol == "NEWCO"
    assert rows[0].outcomes == {}          # not yet graded


def test_upsert_replaces_by_symbol(tmp_path):
    store = IpoHistoryStore(base_dir=str(tmp_path))
    store.append(IpoRecord(**_REC))
    store.upsert(IpoRecord(**{**_REC, "outcomes": {"1": 12.5}}))
    rows = store.load_all()
    assert len(rows) == 1
    assert rows[0].outcomes == {"1": 12.5}


def test_existing_symbols_supports_resumable_backfill(tmp_path):
    store = IpoHistoryStore(base_dir=str(tmp_path))
    store.append(IpoRecord(**_REC))
    assert store.existing_symbols() == {"NEWCO"}


def test_corrupt_line_is_skipped_not_fatal(tmp_path):
    store = IpoHistoryStore(base_dir=str(tmp_path))
    store.append(IpoRecord(**_REC))
    with open(store.path, "a", encoding="utf-8") as fh:
        fh.write("{not json\n")
    assert len(store.load_all()) == 1


def test_missing_file_loads_empty(tmp_path):
    assert IpoHistoryStore(base_dir=str(tmp_path)).load_all() == []


def test_upsert_many_preserves_rows_it_does_not_touch(tmp_path):
    store = IpoHistoryStore(base_dir=str(tmp_path))
    store.append(IpoRecord(symbol="AAA", total_x=40.0, outcomes={"1": 12.3}))
    store.append(IpoRecord(symbol="BBB", total_x=2.0))

    store.upsert_many([IpoRecord(symbol="AAA", total_x=40.0,
                                 outcomes={"1": 12.3}, ofs_share=0.8)])

    rows = {r.symbol: r for r in store.load_all()}
    assert rows["AAA"].ofs_share == 0.8
    assert rows["AAA"].outcomes == {"1": 12.3}   # not wiped by the enrichment
    assert rows["BBB"].total_x == 2.0            # untouched row survives


def test_upsert_many_writes_one_file_replace_not_one_per_record(tmp_path, monkeypatch):
    """The whole point of upsert_many over a loop of upsert() calls: ONE
    rewrite for the batch, not one rewrite per record (O(n) vs O(n^2) IO)."""
    store = IpoHistoryStore(base_dir=str(tmp_path))
    store.append(IpoRecord(symbol="AAA"))

    replace_calls = []
    from pathlib import Path
    original_replace = Path.replace

    def _counting_replace(self, target):
        replace_calls.append(self)
        return original_replace(self, target)

    monkeypatch.setattr(Path, "replace", _counting_replace)
    written = store.upsert_many([
        IpoRecord(symbol="AAA", total_x=1.0),
        IpoRecord(symbol="CCC", total_x=2.0),
        IpoRecord(symbol="DDD", total_x=3.0),
    ])
    assert written == 3
    assert len(replace_calls) == 1
