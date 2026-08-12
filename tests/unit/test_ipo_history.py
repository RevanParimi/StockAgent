"""PI Prospect P1 — the historical spine store."""
from core.ipo.history import IpoHistoryStore, IpoRecord

_REC = dict(symbol="NEWCO", company="NewCo Ltd", listing_date="2026-06-15",
            issue_price=315.0, total_x=22.7, qib_x=45.2, retail_x=8.1,
            issue_size_shares=1_000_000.0)


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
