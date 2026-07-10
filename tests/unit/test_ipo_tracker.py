"""Compass Phase C — IPO tracker scoring, guards, lock-in calendar (spec §6.2)."""
from datetime import date

import pandas as pd

import core.discovery.ipo_tracker as it
from backend.shared.schemas.discovery import DiscoveryCandidate
from core.discovery.ipo_tracker import (
    build_ipo_candidates,
    lockin_events,
    upcoming_lockin_alerts,
)


def _no_bulk(monkeypatch):
    """Isolate from the real data/market_cache/bulk_block.json."""
    monkeypatch.setattr(it, "load_bulk_block", lambda: {"deals": []})


def _window(symbol="NEWCO", sessions=10, close=350.0, traded_cr=8.0,
            deliv_last5=55.0, deliv_prior=35.0, series="EQ"):
    rows = []
    days = pd.bdate_range(end="2026-07-03", periods=sessions)
    for i, d in enumerate(days):
        deliv = deliv_last5 if i >= sessions - 5 else deliv_prior
        rows.append({
            "symbol": symbol, "series": series, "date": d.date().isoformat(),
            "prev_close": close, "open": close, "high": close, "low": close,
            "close": close, "volume": 1_000_000,
            "traded_value_cr": traded_cr, "delivery_qty": 500_000,
            "delivery_pct": deliv,
        })
    return pd.DataFrame(rows)


def _cache(listing="2026-06-20", issue=315.0, qib=45.0, retail=8.0):
    return {"fetched_at": "x", "degraded": False, "current": [], "upcoming": [],
            "past": [{"symbol": "NEWCO", "company": "NewCo Ltd", "series": "EQ",
                      "listing_date": listing, "issue_price": issue,
                      "qib_x": qib, "retail_x": retail, "total_x": 22.0,
                      "status": "past"}]}


def test_candidate_built_with_ipo_flag_and_subscores(monkeypatch):
    _no_bulk(monkeypatch)
    cands = build_ipo_candidates(date(2026, 7, 4), window=_window(), cache=_cache())
    assert len(cands) == 1
    c = cands[0]
    assert isinstance(c, DiscoveryCandidate)
    assert c.symbol == "NEWCO" and "ipo" in c.flags
    assert 0.0 <= c.composite <= 1.0
    # +11% over issue, delivery surging, strong QIB -> healthy composite
    assert c.composite > 0.5
    assert set(c.signal_ranks) >= {"listing_evidence", "delivery_trend", "subscription"}


def test_missing_subscription_renormalizes_not_zeroes(monkeypatch):
    _no_bulk(monkeypatch)
    cache = _cache(qib=None, retail=None)
    c = build_ipo_candidates(date(2026, 7, 4), window=_window(), cache=cache)[0]
    assert "subscription_dark" in c.flags
    assert c.composite > 0.4          # evidence-only score, not dragged to 0


def test_guards_price_liquidity_sessions(monkeypatch):
    _no_bulk(monkeypatch)
    # penny price rejected
    assert build_ipo_candidates(
        date(2026, 7, 4), window=_window(close=15.0), cache=_cache(issue=14.0)) == []
    # illiquid rejected
    assert build_ipo_candidates(
        date(2026, 7, 4), window=_window(traded_cr=1.0), cache=_cache()) == []
    # too few sessions rejected
    assert build_ipo_candidates(
        date(2026, 7, 4), window=_window(sessions=3), cache=_cache()) == []


def test_old_listing_outside_window_excluded(monkeypatch):
    _no_bulk(monkeypatch)
    cands = build_ipo_candidates(
        date(2026, 7, 4), window=_window(), cache=_cache(listing="2026-01-05"))
    assert cands == []


def test_lockin_calendar_and_warn_window():
    evs = lockin_events("NEWCO", date(2026, 6, 20))
    assert [(e.kind, e.expiry) for e in evs] == [
        ("anchor_50pct", "2026-07-20"),
        ("anchor_remaining", "2026-09-18"),
        ("pre_ipo_6mo", "2026-12-17"),
    ]
    # 2026-07-14 -> anchor_50pct on 07-20 is 6 days out (warn window 7)
    alerts = upcoming_lockin_alerts(date(2026, 7, 14), cache=_cache())
    assert [a.kind for a in alerts] == ["anchor_50pct"]
    # symbol filter
    assert upcoming_lockin_alerts(date(2026, 7, 14), symbols={"OTHER"}, cache=_cache()) == []
