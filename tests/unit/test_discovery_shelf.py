"""Compass Phase B — Discovery Shelf: cap, displacement, stale rotation, promote."""
import json
from datetime import date

import pytest

import core.discovery.shelf as shelf_mod
from backend.shared.schemas.discovery import DeepDiveResult, ShelfIdea


def _dive(symbol, conviction, on="2026-07-04"):
    return DeepDiveResult(symbol=symbol, sector="pharma", graph="generic",
                          conviction=conviction, verdict="BUY", thesis="t",
                          entry_low=97.0, entry_high=102.0, invalidation_level=88.0,
                          close=100.0, composite=0.8, dive_date=on)


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(shelf_mod.settings, "DISCOVERY_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(shelf_mod.settings, "DISCOVERY_SHELF_SIZE", 2)
    monkeypatch.setattr(shelf_mod.settings, "DISCOVERY_STALE_DAYS", 60)
    monkeypatch.setattr(shelf_mod.settings, "DISCOVERY_MIN_CONVICTION", 0.55)
    return shelf_mod.ShelfStore()


def test_apply_adds_above_conviction_floor(store):
    summary = store.apply_deep_dives([_dive("AAA", 0.72), _dive("BBB", 0.40)],
                                     on=date(2026, 7, 4))
    assert summary["added"] == ["AAA"]
    assert summary["skipped"] == ["BBB"]          # below 0.55 floor
    shelf = store.load()
    idea = shelf.ideas[0]
    assert idea.symbol == "AAA" and idea.status == "active"
    assert idea.added == "2026-07-04" and idea.invalidation_level == 88.0


def test_apply_respects_cap_and_displaces_weakest(store):
    store.apply_deep_dives([_dive("AAA", 0.60), _dive("BBB", 0.65)], on=date(2026, 7, 4))
    summary = store.apply_deep_dives([_dive("CCC", 0.90), _dive("DDD", 0.58)],
                                     on=date(2026, 7, 11))
    assert "CCC" in summary["added"]
    assert "AAA" in summary["displaced"]          # weakest active displaced
    assert "DDD" in summary["skipped"]            # cap reached, not stronger than remaining
    active = [i.symbol for i in store.load().ideas if i.status == "active"]
    assert sorted(active) == ["BBB", "CCC"]


def test_rotate_stale(store):
    store.apply_deep_dives([_dive("AAA", 0.7, on="2026-05-01")], on=date(2026, 5, 1))
    rotated = store.rotate_stale(on=date(2026, 7, 4))     # 64 days later
    assert rotated == ["AAA"]
    assert store.load().ideas[0].status == "dropped"


def test_promote_to_watchlist(store, monkeypatch):
    added_items, promoted = [], []

    class _FakePortfolio:
        def __init__(self, user_id=None): pass
        def add_watchlist(self, item): added_items.append(item)
    monkeypatch.setattr(shelf_mod, "PortfolioStore", _FakePortfolio)
    monkeypatch.setattr(shelf_mod, "promote_symbol",
                        lambda symbol, sector, origin: promoted.append(
                            (symbol, sector, origin)) or {"status": "promoted",
                                                          "graph": "generic"})

    store.apply_deep_dives([_dive("AAA", 0.7)], on=date(2026, 7, 4))
    result = store.promote("AAA")
    assert result["status"] == "promoted"
    assert added_items[0].symbol == "AAA" and added_items[0].source == "discovery"
    assert promoted == [("AAA", "pharma", "watchlist")]
    assert store.load().ideas[0].status == "promoted"


def test_promote_unknown_symbol(store):
    result = store.promote("NOPE")
    assert result["status"] == "not_on_shelf"


def test_events_jsonl_written(store, tmp_path):
    store.apply_deep_dives([_dive("AAA", 0.7)], on=date(2026, 7, 4))
    lines = (tmp_path / "shelf_events.jsonl").read_text().strip().splitlines()
    events = [json.loads(l) for l in lines]
    assert events[0]["event"] == "added" and events[0]["symbol"] == "AAA"
