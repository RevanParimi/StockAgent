"""FIX-032 — a home-page watchlist save changes only what the user changed,
and a stock leaves the daily review only when nobody holds or watches it.

Real routes through FastAPI's TestClient (the signed-in user is a header),
real portfolio files, and the real promotion over a real
managed_tickers.json in the test's own folder. Atlas is on, as in
config.yaml. Only prices, the clock and NSE's surveillance report (conftest:
all clear) are fixed. What each test expects is worked from its own fixture:

- the card's example: a watchlist of MARUTI, BACK (added through the API),
  NEWCO (a promoted shelf idea) and OLD (the autopilot's note of an exit);
  adding HEROMOTOCO on the home page keeps all four as they were, and
  removing MARUTI keeps the other four;
- random watchlists and random changes: a stock the request does not name is
  never dropped or rewritten; the older whole-list form (a page loaded before
  FIX-032) never removes, so a stock that page never saw is never dropped;
- a removal disables the stock's held or watchlist entry only when no
  portfolio holds it and no user's own watchlist lists it (the autopilot's
  note does not count), from the home page and from the API's two deletes
  alike; an original entry never changes;
- a quarantined account not yet restored stops every release and every
  demotion, and the log says why; once restored, both work again.
"""
from __future__ import annotations

import json
import logging
import random
from datetime import date

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

import services.api.log_buffer as lb
from backend.shared.schemas.portfolio import AdviceRecord, Holding, Portfolio, WatchlistItem
from core.config import settings
from core.portfolio import autopilot as ap
from core.portfolio import promotion
from core.portfolio.pricing import SessionClose
from core.portfolio.store import PortfolioStore
from services.api.auth import get_current_user
from services.api.routes import portfolio_api, ui_data

MON = date(2026, 7, 13)            # the session u's exit is booked at
TUE = date(2026, 7, 14)            # u's next run
TODAY = date(2026, 7, 31)          # the executor refuses a review day after today
UNIVERSE = [t["sym"] for t in ui_data._ALL_TICKERS]
OUTSIDE = ["BACK", "NEWCO", "OLD", "ZEDCO"]     # stocks the home page's own list lacks
SOURCES = ["user", "discovery", "autopilot"]


@pytest.fixture(autouse=True)
def world(tmp_path, monkeypatch):
    """A managed file and the portfolios in this test's own folder; Atlas on
    (the per-user watchlist); the autopilot on, deployment off."""
    monkeypatch.setenv("ATLAS_ENABLED", "false")
    monkeypatch.setattr(ui_data.atlas_store, "enabled", lambda: True)
    # The atlas mirror never runs here, whatever atlas_store.enabled answers.
    monkeypatch.setattr(PortfolioStore, "_sync_instrument", lambda self, *a, **k: None)
    monkeypatch.setattr(ui_data, "_WATCHLIST_PATH", tmp_path / "watchlist.json")
    monkeypatch.setattr(lb, "_MANAGED_TICKERS_PATH", tmp_path / "data" / "managed_tickers.json")
    for name, value in {
        "PORTFOLIO_DATA_DIR": str(tmp_path / "pf"), "AUTOPILOT_ENABLED": True,
        "AUTOPILOT_DEPLOY_IDLE_CASH": False, "AUTOPILOT_TRIM_PCT": 25.0,
        "DECISION_GATE_MODE": "record", "ADVISOR_MAX_POSITION_PCT": 100.0,
        "ADVISOR_MAX_SECTOR_PCT": 100.0, "AUTOPILOT_MIN_CASH_FLOOR": 0.0,
        "PORTFOLIO_MAX_MANAGED_TICKERS": 40, "PORTFOLIO_OVERRIDES": {},
    }.items():
        monkeypatch.setattr(settings, name, value)
    monkeypatch.setattr(ap, "_today_ist", lambda: TODAY)
    monkeypatch.setattr(ap, "_now_iso", lambda: "2026-07-14T11:30:00+00:00")
    monkeypatch.setattr(promotion, "resolve_company_name", lambda sym: f"{sym} Ltd")
    monkeypatch.setattr(ap, "session_close",
                        lambda sym, d: (SessionClose(100.0, d, "agree"), d))
    return tmp_path


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(ui_data.router)
    app.include_router(portfolio_api.router)

    def _user(request: Request) -> dict:
        uid = request.headers["x-user"]
        return {"user_id": uid, "role": "owner" if uid == "primary" else "member"}

    app.dependency_overrides[get_current_user] = _user
    return TestClient(app)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _put(client, user: str, **body):
    return client.put("/ui/watchlist", json=body, headers={"x-user": user})


def _watch(user: str, sym: str, source: str = "user", reason: str = "") -> None:
    PortfolioStore(user_id=user).add_watchlist(WatchlistItem(
        symbol=sym, sector="pharma", added="2026-07-01", reason=reason, source=source))


def _items(user: str) -> dict[str, dict]:
    """The stored watchlist, in order, each item as stored."""
    return {w.symbol: w.model_dump() for w in PortfolioStore(user_id=user).load().watchlist}


def _h(sym: str, qty: float = 5.0) -> Holding:
    return Holding(symbol=sym, sector="pharma", qty=qty, avg_buy_price=100.0,
                   adj_avg_price=100.0, adj_qty=qty, buy_date="2026-06-01")


def _hold(user: str, *syms: str, autopilot: bool = False) -> PortfolioStore:
    s = PortfolioStore(user_id=user)
    p = s.load()
    p.holdings = [_h(x) for x in syms]
    p.cash_deployable, p.capital_in, p.autopilot = 100_000.0, 200_000.0, autopilot
    s.save(p)
    return s


def _write_managed(*entries: dict) -> None:
    lb._MANAGED_TICKERS_PATH.parent.mkdir(parents=True, exist_ok=True)
    lb._MANAGED_TICKERS_PATH.write_text(json.dumps(list(entries), indent=2), encoding="utf-8")


def _managed() -> dict[str, dict]:
    return {t["sym"]: t for t in json.loads(lb._MANAGED_TICKERS_PATH.read_text(encoding="utf-8"))}


def _manual(sym: str) -> dict:
    return {"sym": sym, "name": sym, "sector": "automobile", "enabled": True}


def _entry(sym: str, origin: str, enabled: bool = True) -> dict:
    return {"sym": sym, "name": sym, "sector": "pharma", "enabled": enabled, "origin": origin,
            "cadence": "daily" if origin == "held" else "weekly", "promoted_at": "2026-07-01"}


def _exit(store: PortfolioStore, sym: str, on: date = MON) -> None:
    rec = AdviceRecord(date=on.isoformat(), user_id=store.user_id, symbol=sym, verdict="EXIT",
                       close=100.0, unrealised_pnl_pct=0.0, stop_pct=12.0,
                       rationale_hash=f"{sym}-EXIT")
    ap.execute_advice(store, store.load(), [rec], {}, on)


def test_the_fixture_universe():
    assert {"MARUTI", "HEROMOTOCO"} <= set(UNIVERSE)
    assert not set(OUTSIDE) & set(UNIVERSE)


# ---------------------------------------------------------------------------
# 1. A save changes only what the user changed
# ---------------------------------------------------------------------------

def _card_watchlist(user: str = "primary") -> dict[str, dict]:
    _watch(user, "MARUTI")
    _watch(user, "BACK")
    _watch(user, "NEWCO", source="discovery", reason="discovery shelf (conviction 0.70)")
    _watch(user, "OLD", source="autopilot", reason="autopilot_exit")
    return _items(user)


def test_the_cards_example_add_then_remove(client):
    _write_managed(_manual("MARUTI"), _entry("BACK", "watchlist"), _entry("NEWCO", "watchlist"))
    before = _card_watchlist()
    managed_before = _managed()

    r = _put(client, "primary", add=["HEROMOTOCO"])
    assert r.status_code == 200
    after = _items("primary")
    assert list(after) == ["MARUTI", "BACK", "NEWCO", "OLD", "HEROMOTOCO"]
    assert {s: after[s] for s in before} == before          # the four, exactly as they were
    assert r.json()["watchlist"] == list(after)

    r = _put(client, "primary", remove=["MARUTI"])
    assert r.status_code == 200
    after = _items("primary")
    assert list(after) == ["BACK", "NEWCO", "OLD", "HEROMOTOCO"]
    assert {s: after[s] for s in ("BACK", "NEWCO", "OLD")} == \
        {s: before[s] for s in ("BACK", "NEWCO", "OLD")}
    assert r.json()["watchlist"] == list(after)
    # MARUTI's entry is an original one: it never changes, and nothing else did.
    assert _managed() == managed_before


def test_the_older_whole_list_form_adds_and_never_removes(client):
    """A page loaded before FIX-032 sends its whole list. It adds what is
    new; it removes nothing, since a stock it omits may be one it never saw."""
    before = _card_watchlist()
    r = _put(client, "primary", watchlist=["MARUTI", "HEROMOTOCO"])    # the page saw MARUTI only
    assert r.status_code == 200
    assert list(_items("primary")) == ["MARUTI", "BACK", "NEWCO", "OLD", "HEROMOTOCO"]
    r = _put(client, "primary", watchlist=[])
    assert r.status_code == 200
    after = _items("primary")
    assert list(after) == ["MARUTI", "BACK", "NEWCO", "OLD", "HEROMOTOCO"]
    assert {s: after[s] for s in before} == before


def test_a_page_whose_list_is_out_of_date_drops_nothing_it_did_not_name(client):
    """The page read MARUTI and BACK; NEWCO was promoted from the shelf after
    that. Adding HEROMOTOCO and removing BACK leave NEWCO alone."""
    _watch("v", "MARUTI")
    _watch("v", "BACK")
    _watch("v", "NEWCO", source="discovery")
    assert _put(client, "v", add=["HEROMOTOCO"]).status_code == 200
    assert _put(client, "v", remove=["BACK"]).status_code == 200
    assert list(_items("v")) == ["MARUTI", "NEWCO", "HEROMOTOCO"]


def test_what_a_save_may_name(client):
    """An add outside the home page's list, an add already there, a removal
    not on the list: nothing changes, the managed list included (nobody
    holds or watches NEWCO, so a demotion would disable it). Symbols are read
    upper-case, trimmed."""
    _write_managed(_entry("NEWCO", "watchlist"))
    managed_before = _managed()
    _watch("v", "BACK")
    before = _items("v")
    for body in ({"add": ["ZEDCO"]}, {"add": ["back"]}, {"remove": ["NEWCO"]},
                 {"add": [], "remove": []}, {"add": ["  "]}):
        r = _put(client, "v", **body)
        assert r.status_code == 200 and _items("v") == before, body
    assert _managed() == managed_before
    assert _put(client, "v", add=[" heromotoco "], remove=[" back"]).status_code == 200
    assert list(_items("v")) == ["HEROMOTOCO"]


def test_a_body_with_nothing_to_do_is_refused(client):
    r = _put(client, "v")
    assert r.status_code == 422
    assert _items("v") == {}


def test_each_user_changes_only_their_own_list(client):
    _watch("u", "BACK")
    _watch("v", "BACK")
    assert _put(client, "v", remove=["BACK"], add=["MARUTI"]).status_code == 200
    assert list(_items("u")) == ["BACK"]
    assert list(_items("v")) == ["MARUTI"]


@pytest.mark.parametrize("seed", range(80))
def test_a_change_never_touches_a_stock_it_does_not_name(client, seed):
    """Random lists of in- and out-of-universe stocks with random sources, and
    a random add and remove, in random spellings. Every stock the request
    does not name is kept exactly as stored; a named removal is gone; a named
    addition from the home page's list is there."""
    rng = random.Random(seed)
    pool = rng.sample(UNIVERSE, 5) + OUTSIDE
    current = rng.sample(pool, rng.randint(0, len(pool)))
    for s in current:
        _watch("v", s, source=rng.choice(SOURCES))
    before = _items("v")
    add = rng.sample(pool, rng.randint(0, 3))
    remove = rng.sample(pool, rng.randint(0, 3))

    def spell(s):
        return rng.choice([s, s.lower(), f" {s} "])

    r = _put(client, "v", add=[spell(s) for s in add], remove=[spell(s) for s in remove])
    assert r.status_code == 200
    after = _items("v")
    named = set(add) | set(remove)
    for s in set(before) - named:
        assert after.get(s) == before[s], s
    for s in set(remove) & set(before):
        assert s not in after
    for s in set(add) - set(before):
        assert (s in after) == (s in UNIVERSE), s
    assert set(after) <= set(before) | set(add)
    assert r.json()["watchlist"] == list(after)


@pytest.mark.parametrize("seed", range(40))
def test_an_older_page_never_drops_anything(client, seed):
    """The whole-list form from a page that saw a random part of the list,
    with one stock added or one removed on it: every stock stored before is
    still stored, unchanged."""
    rng = random.Random(500 + seed)
    pool = rng.sample(UNIVERSE, 5) + OUTSIDE
    server = rng.sample(pool, rng.randint(0, len(pool)))
    for s in server:
        _watch("v", s, source=rng.choice(SOURCES))
    before = _items("v")
    seen = [s for s in server if rng.random() < 0.7]
    if seen and rng.random() < 0.5:
        posted = [s for s in seen if s != rng.choice(seen)]
        new = None
    else:
        new = rng.choice(UNIVERSE)
        posted = seen + [new]
    assert _put(client, "v", watchlist=posted).status_code == 200
    after = _items("v")
    assert {s: after.get(s) for s in before} == before
    assert set(after) - set(before) == ({new} - set(before) if new else set())


def test_with_atlas_off_the_global_list_takes_the_change_too(client, monkeypatch):
    """The dormant path (owner only, the global watchlist file) reads the same
    change; a member is still refused."""
    monkeypatch.setattr(ui_data.atlas_store, "enabled", lambda: False)
    assert _put(client, "primary", watchlist=["MARUTI", "TATAMOTORS"]).json()["watchlist"] == \
        ["MARUTI", "TATAMOTORS"]
    r = _put(client, "primary", add=["HEROMOTOCO", "ZEDCO"], remove=["MARUTI"])
    assert r.status_code == 200 and r.json()["watchlist"] == ["TATAMOTORS", "HEROMOTOCO"]
    assert json.loads(ui_data._WATCHLIST_PATH.read_text(encoding="utf-8")) == \
        ["TATAMOTORS", "HEROMOTOCO"]
    # Named in both: removed when on the list, added when not (as with Atlas on).
    assert _put(client, "primary", add=["TATAMOTORS", "MARUTI"],
                remove=["TATAMOTORS", "MARUTI"]).json()["watchlist"] == ["HEROMOTOCO", "MARUTI"]
    assert _put(client, "v", add=["MARUTI"]).status_code == 403


# ---------------------------------------------------------------------------
# 2. A removal leaves the daily review only when nobody holds or watches it
# ---------------------------------------------------------------------------

def _watched_sale() -> PortfolioStore:
    """u (autopilot) holds BACK and KEEP and exits BACK on Monday; v watches
    BACK (added through the API). FIX-028 keeps BACK as a weekly watchlist
    entry for v's watch."""
    _write_managed(_manual("MARUTI"), _entry("BACK", "held"))
    u = _hold("u", "BACK", "KEEP", autopilot=True)
    _watch("v", "BACK")
    _exit(u, "BACK")
    back = _managed()["BACK"]
    assert (back["enabled"], back["origin"], back["cadence"]) == (True, "watchlist", "weekly")
    assert list(_items("u")) == ["BACK"]                 # the autopilot's note
    return u


def test_a_home_page_removal_takes_the_stock_out_of_the_review(client):
    u = _watched_sale()
    assert _put(client, "v", remove=["BACK"]).status_code == 200
    assert list(_items("v")) == []
    assert _managed()["BACK"]["enabled"] is False
    ap.execute_advice(u, u.load(), [], {}, TUE)          # u's next run follows its holdings
    assert _managed()["BACK"]["enabled"] is False
    assert _managed()["BACK"]["sector"] == "pharma"     # kept for a later re-buy


@pytest.mark.parametrize("keeper", ["another user watches it", "another portfolio holds it",
                                    "the remover still holds it"])
def test_a_removal_keeps_a_stock_someone_still_watches_or_holds(client, keeper):
    _watched_sale()
    if keeper == "another user watches it":
        _watch("w", "BACK", source="discovery")
    elif keeper == "another portfolio holds it":
        _hold("w", "BACK")
    else:
        _hold("v", "BACK")
    before = _managed()["BACK"]
    assert _put(client, "v", remove=["BACK"]).status_code == 200
    assert list(_items("v")) == []
    assert _managed()["BACK"] == before


def test_the_autopilots_own_note_does_not_keep_a_stock_in_the_review(client):
    """w's watchlist names BACK only as the autopilot's note of w's own exit:
    not a user's own watch, so v's removal still takes BACK out."""
    _watched_sale()
    _watch("w", "BACK", source="autopilot", reason="autopilot_exit")
    assert _put(client, "v", remove=["BACK"]).status_code == 200
    assert _managed()["BACK"]["enabled"] is False


def test_a_removal_never_changes_an_original_entry(client):
    _write_managed(_manual("MARUTI"), _manual("BACK"))
    _watch("v", "MARUTI")
    _watch("v", "BACK")
    before = _managed()
    assert _put(client, "v", remove=["MARUTI", "BACK"]).status_code == 200
    assert list(_items("v")) == []
    assert _managed() == before


def test_the_api_delete_asks_the_same_question(client):
    """DELETE /portfolio/watchlist/BACK by v while w holds BACK: before
    FIX-032 the route looked only at v's own holdings and disabled it."""
    _write_managed(_entry("BACK", "watchlist"))
    _watch("v", "BACK")
    _hold("w", "BACK")
    r = client.delete("/portfolio/watchlist/BACK", headers={"x-user": "v"})
    assert r.status_code == 200 and r.json()["demoted"] is False
    assert _managed()["BACK"]["enabled"] is True
    _hold("w")                                           # w sells
    _watch("v", "BACK")
    r = client.delete("/portfolio/watchlist/BACK", headers={"x-user": "v"})
    assert r.json()["demoted"] is True and _managed()["BACK"]["enabled"] is False


def test_a_holding_deleted_while_another_user_watches_becomes_weekly(client):
    """DELETE /portfolio/holdings/BACK (no cash ledger): u's own watchlist
    does not list BACK, v's does, so the daily entry turns weekly, as
    FIX-028's release does, instead of leaving the review."""
    _write_managed(_entry("BACK", "held"))
    _hold("u", "BACK")
    p = PortfolioStore(user_id="u").load()
    p.cash_deployable = None
    PortfolioStore(user_id="u").save(p)
    _watch("v", "BACK")
    r = client.delete("/portfolio/holdings/BACK", headers={"x-user": "u"})
    assert r.status_code == 200 and r.json()["demoted"] is False
    back = _managed()["BACK"]
    assert (back["enabled"], back["origin"], back["cadence"]) == (True, "watchlist", "weekly")


@pytest.mark.parametrize("own_item, expected", [
    ("user", (True, "watchlist", "weekly")),       # u's own watch keeps it, weekly
    ("autopilot", (False, "held", "daily")),       # the autopilot's note is no watch
    (None, (False, "held", "daily")),
])
def test_a_holding_deleted_asks_about_the_removers_own_watchlist_too(client, own_item, expected):
    """Before FIX-032 the route skipped the demotion whenever u's own
    watchlist named the stock, the autopilot's note included, and left a
    daily entry for a stock nobody holds."""
    _write_managed(_entry("BACK", "held"))
    _hold("u", "BACK")
    p = PortfolioStore(user_id="u").load()
    p.cash_deployable = None
    PortfolioStore(user_id="u").save(p)
    if own_item:
        _watch("u", "BACK", source=own_item)
    r = client.delete("/portfolio/holdings/BACK", headers={"x-user": "u"})
    assert r.status_code == 200 and r.json()["demoted"] is (expected[0] is False)
    back = _managed()["BACK"]
    assert (back["enabled"], back["origin"], back["cadence"]) == expected


def test_a_watch_deleted_while_the_remover_still_holds_keeps_the_entry(client):
    _write_managed(_entry("BACK", "held"))
    _hold("v", "BACK")
    _watch("v", "BACK")
    r = client.delete("/portfolio/watchlist/BACK", headers={"x-user": "v"})
    assert r.status_code == 200 and r.json()["demoted"] is False
    assert _managed()["BACK"] == _entry("BACK", "held")


ORIGINS = [None, "manual", "held", "watchlist"]


@pytest.mark.parametrize("seed", range(150))
def test_demote_symbol_against_its_rule(world, seed):
    """Random portfolios (holdings, watchlists of random sources, random
    spellings) and a random entry for X among others. The rule, worked here:
    only an enabled held or watchlist entry can change; a stock some portfolio
    holds keeps it; a stock a user's own watchlist lists keeps it, a held
    entry turning weekly; otherwise it is disabled. No other entry changes."""
    rng = random.Random(9000 + seed)
    root = world / "pf"
    held, watched = set(), set()
    for i in range(rng.randint(0, 3)):
        hs = rng.sample(["X", "Y", "Z"], rng.randint(0, 2))
        ws = [(s, rng.choice(SOURCES)) for s in rng.sample(["X", "Y", "Z"], rng.randint(0, 2))]
        p = Portfolio(user_id=f"p{i}",
                      holdings=[_h(rng.choice([s, s.lower(), f" {s}"])) for s in hs],
                      watchlist=[WatchlistItem(symbol=rng.choice([s, s.lower()]),
                                               added="2026-07-01", source=src)
                                 for s, src in ws])
        (root / p.user_id).mkdir(parents=True, exist_ok=True)
        (root / p.user_id / "portfolio.json").write_text(json.dumps(p.model_dump()),
                                                         encoding="utf-8")
        held |= set(hs)
        watched |= {s for s, src in ws if src != "autopilot"}
    origin = rng.choice(ORIGINS)
    x = {"sym": "X", "name": "X", "sector": "pharma", "promoted_at": "2026-07-01"}
    if origin:
        x["origin"] = origin
        x["cadence"] = "daily" if origin == "held" else "weekly"
    if rng.random() < 0.8:
        x["enabled"] = rng.random() < 0.7
    others = [_entry("Y", rng.choice(["held", "watchlist"])), _manual("Z")]
    _write_managed(*([x] + others))

    expected = dict(x)
    disabled = False
    if origin in ("held", "watchlist") and x.get("enabled", True) and "X" not in held:
        if "X" in watched:
            expected["origin"], expected["cadence"] = "watchlist", "weekly"
        else:
            expected["enabled"] = False
            disabled = True

    assert promotion.demote_symbol(rng.choice(["X", "x", " X "])) is disabled
    after = _managed()
    assert after["X"] == expected
    assert [after["Y"], after["Z"]] == others


# ---------------------------------------------------------------------------
# 3. A quarantined account not yet restored stops every release
# ---------------------------------------------------------------------------

def _quarantine(world, user: str, *syms: str) -> None:
    d = world / "pf" / user
    d.mkdir(parents=True, exist_ok=True)
    (d / "portfolio.json.corrupt-20260713T100000").write_text(
        json.dumps(Portfolio(user_id=user, holdings=[_h(s) for s in syms]).model_dump()),
        encoding="utf-8")


def test_a_quarantined_account_stops_the_release_and_the_log_says_why(world, caplog):
    """v's portfolio.json was corrupt and quarantined; v held BACK. u exits
    BACK: BACK stays enabled (v's holdings are unknown, not empty)."""
    _write_managed(_entry("BACK", "held"))
    _quarantine(world, "v", "BACK")
    u = _hold("u", "BACK", autopilot=True)
    with caplog.at_level(logging.WARNING, logger="core.portfolio.promotion"):
        _exit(u, "BACK")
    assert _managed()["BACK"]["enabled"] is True
    assert "BACK" not in [h.symbol for h in u.load().holdings]       # the sale stands
    assert any("no managed entry released" in r.getMessage()
               and "quarantined and not restored for v" in r.getMessage()
               for r in caplog.records)
    # Restored by hand (the store refuses to write over a quarantine): v's
    # valid file no longer holds BACK, so the next run releases it.
    (world / "pf" / "v" / "portfolio.json").write_text(
        json.dumps(Portfolio(user_id="v").model_dump()), encoding="utf-8")
    ap.execute_advice(u, u.load(), [], {}, TUE)
    assert _managed()["BACK"]["enabled"] is False


def test_a_quarantined_account_stops_a_removals_demotion(client, world, caplog):
    _write_managed(_entry("BACK", "watchlist"))
    _watch("v", "BACK")
    _quarantine(world, "w", "BACK")
    with caplog.at_level(logging.WARNING, logger="core.portfolio.promotion"):
        assert _put(client, "v", remove=["BACK"]).status_code == 200
    assert list(_items("v")) == []
    assert _managed()["BACK"]["enabled"] is True
    assert any("BACK not demoted" in r.getMessage() for r in caplog.records)


def test_an_account_folder_with_no_portfolio_yet_is_not_a_quarantine(world):
    """PortfolioStore makes a user's folder on first use; one with neither a
    portfolio.json nor a quarantined copy stops nothing."""
    _write_managed(_entry("BACK", "watchlist"))
    (world / "pf" / "fresh").mkdir(parents=True)
    (world / "pf" / "fresh" / "portfolio.lock").write_text("")
    assert promotion.demote_symbol("BACK") is True
