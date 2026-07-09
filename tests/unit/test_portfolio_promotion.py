"""Compass Phase A — auto-promotion: 4 supported sectors, cap, cadence."""
from datetime import date

import pytest

import core.portfolio.promotion as promo


@pytest.fixture
def managed(monkeypatch):
    """In-memory managed_tickers list, patched over log_buffer load/save."""
    state = {"tickers": [
        {"sym": "MARUTI", "name": "Maruti Suzuki India Ltd", "sector": "automobile", "enabled": True},
    ]}
    monkeypatch.setattr(promo, "load_managed_tickers", lambda: state["tickers"])

    def fake_save(tickers):
        state["tickers"] = tickers
    monkeypatch.setattr(promo, "save_managed_tickers", fake_save)
    monkeypatch.setattr(promo, "resolve_company_name", lambda t: f"{t} Ltd")
    return state


def test_promote_new_held_symbol(managed):
    result = promo.promote_symbol("TCS", "it_sector", origin="held")
    assert result["status"] == "promoted"
    entry = next(t for t in managed["tickers"] if t["sym"] == "TCS")
    assert entry["origin"] == "held" and entry["cadence"] == "daily"
    assert entry["enabled"] is True


def test_promote_watchlist_gets_weekly_cadence(managed):
    promo.promote_symbol("INFY", "it_sector", origin="watchlist")
    entry = next(t for t in managed["tickers"] if t["sym"] == "INFY")
    assert entry["cadence"] == "weekly"


def test_promote_generic_sector_accepted(managed):
    """Phase B: generic sector graph lifts the 4-sector restriction."""
    result = promo.promote_symbol("SUNPHARMA", "pharma", origin="held")
    assert result["status"] == "promoted"
    assert result["graph"] == "generic"
    entry = next(t for t in managed["tickers"] if t["sym"] == "SUNPHARMA")
    assert entry["sector"] == "pharma" and entry["cadence"] == "daily"


def test_promote_native_sector_flagged_native(managed):
    result = promo.promote_symbol("TCS2", "it_sector", origin="held")
    assert result["status"] == "promoted"
    assert result["graph"] == "native"


def test_promote_invalid_sector_key_rejected(managed):
    result = promo.promote_symbol("XYZ", "Pharma & Health!!", origin="held")
    assert result["status"] == "invalid_sector"
    assert all(t["sym"] != "XYZ" for t in managed["tickers"])


def test_is_valid_sector():
    assert promo.is_valid_sector("pharma")
    assert promo.is_valid_sector("banking_bfsi")
    assert not promo.is_valid_sector("Pharma!!")
    assert not promo.is_valid_sector("")
    assert not promo.is_valid_sector("x" * 40)


def test_promote_existing_symbol_noop(managed):
    result = promo.promote_symbol("MARUTI", "automobile", origin="held")
    assert result["status"] == "already_managed"


def test_cap_evicts_watchlist_first(managed, monkeypatch):
    monkeypatch.setattr(promo.settings, "PORTFOLIO_MAX_MANAGED_TICKERS", 2)
    managed["tickers"].append({
        "sym": "WIPRO", "name": "Wipro Ltd", "sector": "it_sector", "enabled": True,
        "origin": "watchlist", "cadence": "weekly", "promoted_at": "2026-06-01",
    })
    result = promo.promote_symbol("TCS", "it_sector", origin="held")
    assert result["status"] == "promoted"
    syms = [t["sym"] for t in managed["tickers"] if t.get("enabled", True)]
    assert "WIPRO" not in syms          # watchlist-origin evicted
    assert "MARUTI" in syms             # manual entry never evicted
    assert "TCS" in syms


def test_cap_full_when_nothing_evictable(managed, monkeypatch):
    monkeypatch.setattr(promo.settings, "PORTFOLIO_MAX_MANAGED_TICKERS", 1)
    result = promo.promote_symbol("TCS", "it_sector", origin="watchlist")
    assert result["status"] == "cap_full"
    assert all(t["sym"] != "TCS" for t in managed["tickers"])


def test_demote_only_touches_portfolio_origin(managed):
    promo.promote_symbol("TCS", "it_sector", origin="held")
    assert promo.demote_symbol("TCS") is True
    entry = next(t for t in managed["tickers"] if t["sym"] == "TCS")
    assert entry["enabled"] is False
    assert promo.demote_symbol("MARUTI") is False    # manual entry untouched
    assert next(t for t in managed["tickers"] if t["sym"] == "MARUTI")["enabled"] is True


def test_due_for_review_cadence():
    daily = {"sym": "TCS", "cadence": "daily"}
    weekly = {"sym": "INFY", "cadence": "weekly"}
    legacy = {"sym": "MARUTI"}                        # no cadence field = daily
    friday, monday = date(2026, 7, 10), date(2026, 7, 6)
    assert promo.due_for_review(daily, monday) is True
    assert promo.due_for_review(legacy, monday) is True
    assert promo.due_for_review(weekly, monday) is False
    assert promo.due_for_review(weekly, friday) is True


def test_reenable_respects_cap(managed, monkeypatch):
    monkeypatch.setattr(promo.settings, "PORTFOLIO_MAX_MANAGED_TICKERS", 1)
    managed["tickers"].append({
        "sym": "TCS", "name": "TCS Ltd", "sector": "it_sector", "enabled": False,
        "origin": "watchlist", "cadence": "weekly", "promoted_at": "2026-06-01",
    })
    result = promo.promote_symbol("TCS", "it_sector", origin="watchlist")
    assert result["status"] == "cap_full"
    entry = next(t for t in managed["tickers"] if t["sym"] == "TCS")
    assert entry["enabled"] is False


def test_watchlist_promotion_rotates_oldest_watchlist(managed, monkeypatch):
    monkeypatch.setattr(promo.settings, "PORTFOLIO_MAX_MANAGED_TICKERS", 3)
    managed["tickers"] += [
        {"sym": "WIPRO", "name": "Wipro Ltd", "sector": "it_sector", "enabled": True,
         "origin": "watchlist", "cadence": "weekly", "promoted_at": "2026-05-01"},
        {"sym": "COFORGE", "name": "Coforge Ltd", "sector": "it_sector", "enabled": True,
         "origin": "watchlist", "cadence": "weekly", "promoted_at": "2026-06-01"},
    ]
    result = promo.promote_symbol("INFY", "it_sector", origin="watchlist")
    assert result["status"] == "promoted"
    active = [t["sym"] for t in managed["tickers"] if t.get("enabled", True)]
    assert "WIPRO" not in active        # oldest watchlist entry rotated out
    assert "COFORGE" in active and "INFY" in active and "MARUTI" in active
