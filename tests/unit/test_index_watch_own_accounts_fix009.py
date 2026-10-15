"""FIX-009: an index-change notice names only the account's own stocks.

Invariants, stated from the outside:

- the owner watches one stock and holds another, the member holds a third,
  the shelf lists a fourth, and a fifth is a dropped shelf idea nobody holds.
  One index check that moves all five: the owner's devices and mailbox get
  the owner's two stocks in one notice and the shelf idea in another; the
  member's get the member's stock and the shelf idea; nobody hears about the
  fifth. The member never learns the owner's stocks and the owner never
  learns the member's;
- each account's Inbox lists only those same index events;
- a shelf idea that an account also holds or watches reaches it once, even
  when the account has no push subscription and so is outside the market
  audience, and is recorded once when delivery fails;
- with no account (AUTH off), the default user gets its own and the shelf's
  events, and an orphan push subscription gets the shelf's alone;
- an account whose portfolio cannot be read (a corrupt file, a read error, or
  a failed account lookup) misses its own events, and nothing is sent to
  anyone in their place; the other accounts still get theirs;
- the first snapshot sends nothing, a failed index keeps its stale snapshot,
  and a re-run, or a run after the old broadcast already delivered the same
  events on the deploy day, sends nothing twice;
- with Atlas on, the accounts come from atlas.db and each queues outbox rows
  holding only its own and the shelf's events.

Real portfolio stores, a real shelf file, the real sent-log and Inbox; a fake
NSE client; transports recorded at pywebpush's `webpush` and `smtplib.SMTP`
(FIX-008's `wire` fixture). Nothing leaves the process.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import date

import pytest

import core.delivery.index_watch as iw
from backend.shared.schemas.discovery import Shelf, ShelfIdea
from backend.shared.schemas.portfolio import Holding, Portfolio, WatchlistItem
from core.config import settings
from core.delivery import alerts
from core.discovery.shelf import ShelfStore
from core.portfolio import store as portfolio_store
from core.portfolio.store import PortfolioStore
from services.data.stores import user_store
from tests.unit.test_operator_notices_owner_only_fix008 import (  # noqa: F401 — fixtures
    MEMBER_EMAIL,
    MEMBER_ENDPOINT,
    OWNER_EMAIL,
    OWNER_ENDPOINTS,
    _inbox,
    _subscribe,
    accounts,
    wire,
)

DAY = date(2026, 10, 12)
INDEX = "NIFTY 50"
OWN_WATCH = "OWNWATCH"       # the owner watches it
OWN_HOLD = "OWNHOLD"         # the owner holds it
MEM_HOLD = "MEMHOLD"         # the member holds it
SHELF_IDEA = "SHELFIDEA"     # an active shelf idea
NOBODY = "NOBODYCO"          # a dropped shelf idea that nobody holds or watches
QUIET_EMAIL = "quiet@example.invalid"   # an account with no push subscription
SYMBOLS = (OWN_WATCH, OWN_HOLD, MEM_HOLD, SHELF_IDEA, NOBODY)
BEFORE = ["AAA", OWN_WATCH, MEM_HOLD, NOBODY]
AFTER = ["AAA", OWN_HOLD, SHELF_IDEA]          # every one of the five moves


class _NSE:
    """Constituents by index; an index named in `down` fails to fetch."""

    def __init__(self, by_index: dict[str, list[str]], down: tuple[str, ...] = ()):
        self._by_index, self._down = by_index, down

    def listEquityStocksByIndex(self, index="NIFTY 50"):
        if index in self._down:
            raise ConnectionError(f"{index} unavailable")
        return {"data": [{"symbol": index}] + [{"symbol": s} for s in self._by_index[index]]}

    def exit(self):
        pass


def _holding(symbol: str) -> Holding:
    return Holding(symbol=symbol, sector="Test", qty=1, avg_buy_price=100.0,
                   adj_avg_price=100.0, adj_qty=1, buy_date="2026-09-01")


def _portfolio(user_id: str, *, holds=(), watches=()) -> None:
    PortfolioStore(user_id=user_id).save(Portfolio(
        user_id=user_id, holdings=[_holding(s) for s in holds],
        watchlist=[WatchlistItem(symbol=s, added="2026-10-01") for s in watches]))


def _shelf(*active: str, dropped: tuple[str, ...] = (NOBODY,)) -> None:
    ShelfStore().save(Shelf(ideas=[
        ShelfIdea(symbol=s, sector="Test", added="2026-10-01", conviction=0.7,
                  status=status)
        for status, symbols in (("active", active), ("dropped", dropped))
        for s in symbols]))


@pytest.fixture()
def world(wire, tmp_path, monkeypatch):
    """Data directories of this test's own, a shelf with one active idea and
    one dropped, and NIFTY 50's previous snapshot."""
    monkeypatch.setattr(settings, "PORTFOLIO_DATA_DIR", str(tmp_path / "portfolios"))
    monkeypatch.setattr(settings, "DISCOVERY_DATA_DIR", str(tmp_path / "discovery"))
    monkeypatch.setattr(settings, "DELIVERY_INDEX_WATCH", [INDEX])
    _shelf(SHELF_IDEA)
    cache = tmp_path / "index_constituents.json"
    cache.write_text(json.dumps({INDEX: {"fetched_at": "old", "symbols": BEFORE}}),
                     encoding="utf-8")
    monkeypatch.setattr(iw, "_make_nse_client", lambda: _NSE({INDEX: AFTER}))
    return cache


@pytest.fixture()
def two_accounts(accounts, world):
    """The card's example: the owner watches one stock and holds another; the
    member holds a third."""
    owner, member = accounts["owner"]["user_id"], accounts["member"]["user_id"]
    _portfolio(owner, holds=[OWN_HOLD], watches=[OWN_WATCH])
    _portfolio(member, holds=[MEM_HOLD])
    return owner, member


def _run(cache, on: date = DAY) -> dict:
    return iw.run_index_watch(on=on, cache_path=str(cache))


def _named(texts: list[str]) -> set[str]:
    return {s for s in SYMBOLS if any(s in t for t in texts)}


def _pushes(wire, endpoint: str) -> list[str]:
    return [json.dumps(p) for ep, p in wire.pushes if ep == endpoint]


def _log_rows(user_id: str) -> set[tuple[str, str]]:
    """The account's index-change records in the sent-log."""
    return {(r["kind"], r["symbol"])
            for r in alerts.load_recent_alerts(limit=500, user_id=user_id)
            if r["kind"].startswith("index_")}


OWNER_ROWS = {("index_inclusion", OWN_HOLD), ("index_exclusion", OWN_WATCH),
              ("index_inclusion", SHELF_IDEA)}
MEMBER_ROWS = {("index_exclusion", MEM_HOLD), ("index_inclusion", SHELF_IDEA)}


# ---------------------------------------------------------------------------
# each account hears about its own stocks and the shelf's
# ---------------------------------------------------------------------------

def test_each_account_hears_only_its_own_stocks_and_the_shelf(two_accounts, wire, world):
    owner, member = two_accounts
    assert _run(world)["events"] == 4                     # NOBODYCO is watched by no one

    for ep in OWNER_ENDPOINTS:
        assert _named(_pushes(wire, ep)) == {OWN_HOLD, OWN_WATCH, SHELF_IDEA}
        assert len(_pushes(wire, ep)) == 2                # its own bundle + the shelf's
    assert _named(wire.emails_to(OWNER_EMAIL)) == {OWN_HOLD, OWN_WATCH, SHELF_IDEA}
    assert len(wire.emails_to(OWNER_EMAIL)) == 2

    assert _named(_pushes(wire, MEMBER_ENDPOINT)) == {MEM_HOLD, SHELF_IDEA}
    assert len(_pushes(wire, MEMBER_ENDPOINT)) == 2
    assert _named(wire.emails_to(MEMBER_EMAIL)) == {MEM_HOLD, SHELF_IDEA}
    assert len(wire.emails_to(MEMBER_EMAIL)) == 2

    # the account's own stocks arrive together, apart from the shelf's
    own = [t for t in _pushes(wire, OWNER_ENDPOINTS[0]) if OWN_HOLD in t]
    assert len(own) == 1 and OWN_WATCH in own[0] and SHELF_IDEA not in own[0]
    assert NOBODY not in json.dumps(wire.pushes) + json.dumps(wire.emails)

    assert _log_rows(owner) == OWNER_ROWS
    assert _log_rows(member) == MEMBER_ROWS


def test_each_inbox_lists_only_its_own_index_events(two_accounts, wire, world):
    owner, member = two_accounts
    _run(world)

    def index_rows(user_id):
        token = user_store.create_session(user_id, True)
        return {(a["kind"], a["symbol"]) for a in json.loads(_inbox(token))["alerts"]
                if a["kind"].startswith("index_")}

    assert index_rows(owner) == OWNER_ROWS
    assert index_rows(member) == MEMBER_ROWS


def test_a_shelf_idea_an_account_also_holds_reaches_it_once(accounts, wire, world):
    owner, member = accounts["owner"]["user_id"], accounts["member"]["user_id"]
    _portfolio(owner, watches=[SHELF_IDEA, OWN_WATCH])
    _portfolio(member, holds=[SHELF_IDEA])
    _run(world)

    for ep in (*OWNER_ENDPOINTS, MEMBER_ENDPOINT):
        assert sum(t.count(SHELF_IDEA) for t in _pushes(wire, ep)) == 1, ep
    assert len(_pushes(wire, MEMBER_ENDPOINT)) == 1        # the shelf bundle only
    for address in (OWNER_EMAIL, MEMBER_EMAIL):
        assert sum(SHELF_IDEA in t for t in wire.emails_to(address)) == 1
    for uid in (owner, member):
        rows = alerts.load_recent_alerts(limit=500, user_id=uid)
        assert [r["symbol"] for r in rows].count(SHELF_IDEA) == 1
    assert OWN_WATCH not in json.dumps(_pushes(wire, MEMBER_ENDPOINT))


def test_an_account_without_push_still_hears_about_a_shelf_idea_it_holds(
        two_accounts, wire, world):
    """The market audience is the push-subscribed accounts and the default
    user. An account outside it is not told about the shelf in general, but a
    shelf idea it holds is its own news: one email, one Inbox row."""
    owner, member = two_accounts
    quiet = user_store.create_user(QUIET_EMAIL, "pw-for-tests-1", "Quiet")["user_id"]
    _portfolio(quiet, holds=[SHELF_IDEA])
    _run(world)

    assert len(wire.emails_to(QUIET_EMAIL)) == 1
    assert _named(wire.emails_to(QUIET_EMAIL)) == {SHELF_IDEA}
    assert _log_rows(quiet) == {("index_inclusion", SHELF_IDEA)}
    assert _log_rows(owner) == OWNER_ROWS and _log_rows(member) == MEMBER_ROWS
    assert sum(SHELF_IDEA in t for t in wire.emails_to(MEMBER_EMAIL)) == 1


def test_a_held_shelf_idea_is_recorded_once_when_delivery_fails(accounts, wire, world,
                                                                monkeypatch):
    """An undelivered record does not dedupe: it retries on the next emit
    (AUD-085). The account's own notice must not retry the shelf's within the
    same run, or the account's Inbox would list the idea twice."""
    owner, member = accounts["owner"]["user_id"], accounts["member"]["user_id"]
    _portfolio(owner, holds=[SHELF_IDEA, OWN_HOLD])
    _portfolio(member, holds=[SHELF_IDEA])
    monkeypatch.setattr(settings, "DELIVERY_ENABLED", False)
    _run(world)

    for uid in (owner, member):
        rows = alerts.load_recent_alerts(limit=500, user_id=uid)
        assert [r["symbol"] for r in rows].count(SHELF_IDEA) == 1, uid
        assert rows and all(r["delivered"] is False for r in rows)
    assert _log_rows(owner) == {("index_inclusion", SHELF_IDEA),
                                ("index_inclusion", OWN_HOLD)}
    assert wire.pushes == [] and wire.emails == []


@pytest.mark.parametrize("lookup", ["directory scan", "no account listed"])
def test_without_accounts_the_default_user_gets_its_own_and_the_shelf(
        lookup, wire, world, monkeypatch):
    """AUTH off, before the first signup: no users.db row. The default user's
    portfolio is read either way; an orphan push subscription is not an
    account, so it hears about the shelf alone."""
    monkeypatch.setattr(settings, "AUTH_REQUIRED", False)
    default = settings.PORTFOLIO_DEFAULT_USER_ID
    _portfolio(default, watches=[OWN_WATCH])
    _subscribe(default, OWNER_ENDPOINTS[0])
    _subscribe("u_orphan01", MEMBER_ENDPOINT)
    if lookup == "no account listed":
        monkeypatch.setattr(portfolio_store, "active_user_ids", lambda base_dir=None: [])
    _run(world)

    assert _named(_pushes(wire, OWNER_ENDPOINTS[0])) == {OWN_WATCH, SHELF_IDEA}
    assert _named(wire.emails_to(OWNER_EMAIL)) == {OWN_WATCH, SHELF_IDEA}
    assert _named(_pushes(wire, MEMBER_ENDPOINT)) == {SHELF_IDEA}
    assert {to for to, _ in wire.emails} == {OWNER_EMAIL}  # DELIVERY_EMAIL_TO only
    assert _log_rows(default) == {("index_exclusion", OWN_WATCH),
                                  ("index_inclusion", SHELF_IDEA)}


# ---------------------------------------------------------------------------
# an unreadable account: its own events are skipped, never sent elsewhere
# ---------------------------------------------------------------------------

def _assert_member_stock_reached_nobody(wire, owner, member):
    assert MEM_HOLD not in json.dumps(wire.pushes) + json.dumps(wire.emails)
    assert _named(_pushes(wire, MEMBER_ENDPOINT)) == {SHELF_IDEA}
    assert _named(wire.emails_to(MEMBER_EMAIL)) == {SHELF_IDEA}
    assert {OWN_HOLD, OWN_WATCH, SHELF_IDEA} <= _named(_pushes(wire, OWNER_ENDPOINTS[0]))
    assert _log_rows(owner) == OWNER_ROWS
    assert _log_rows(member) == {("index_inclusion", SHELF_IDEA)}


def test_a_corrupt_member_portfolio_skips_only_the_members_own_events(
        two_accounts, wire, world, tmp_path):
    """The real failure in production: the store quarantines the file, reads
    it as empty and tells the owner. The member's stock is not announced to
    anyone; the owner's and the shelf's still are."""
    owner, member = two_accounts
    (tmp_path / "portfolios" / member / "portfolio.json").write_text("{not json",
                                                                     encoding="utf-8")
    _run(world)
    _assert_member_stock_reached_nobody(wire, owner, member)
    owner_texts = _pushes(wire, OWNER_ENDPOINTS[0])
    assert any("quarantined" in t for t in owner_texts)       # the owner-only notice
    assert not any("quarantined" in t for t in _pushes(wire, MEMBER_ENDPOINT))


def test_a_portfolio_read_error_skips_that_account_with_a_warning(
        two_accounts, wire, world, monkeypatch, caplog):
    owner, member = two_accounts
    real_load = PortfolioStore.load

    def load(self):
        if self.user_id == member:
            raise PermissionError(13, "Permission denied")
        return real_load(self)

    monkeypatch.setattr(PortfolioStore, "load", load)
    with caplog.at_level(logging.WARNING, logger="core.delivery.index_watch"):
        assert _run(world)["events"] == 3                    # the member's stock is unknown
    assert f"portfolio read failed for {member}" in caplog.text
    _assert_member_stock_reached_nobody(wire, owner, member)


def test_a_failed_account_lookup_sends_the_shelf_alone(two_accounts, wire, world,
                                                       monkeypatch, caplog):
    owner, member = two_accounts

    def boom(base_dir=None):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(portfolio_store, "active_user_ids", boom)
    with caplog.at_level(logging.WARNING, logger="core.delivery.index_watch"):
        assert _run(world)["events"] == 1
    assert "account lookup failed" in caplog.text
    for ep in (*OWNER_ENDPOINTS, MEMBER_ENDPOINT):
        assert _named(_pushes(wire, ep)) == {SHELF_IDEA}
    assert _log_rows(owner) == _log_rows(member) == {("index_inclusion", SHELF_IDEA)}


# ---------------------------------------------------------------------------
# snapshots and repeats
# ---------------------------------------------------------------------------

def test_the_first_snapshot_sends_nothing(two_accounts, wire, world):
    world.unlink()
    assert _run(world)["events"] == 0
    assert wire.pushes == [] and wire.emails == []
    assert json.loads(world.read_text(encoding="utf-8"))[INDEX]["symbols"] == sorted(AFTER)


def test_a_failed_index_keeps_its_stale_snapshot_and_the_others_still_route(
        two_accounts, wire, world, monkeypatch):
    owner, member = two_accounts
    nxt = "NIFTY NEXT 50"
    monkeypatch.setattr(settings, "DELIVERY_INDEX_WATCH", [INDEX, nxt])
    world.write_text(json.dumps({INDEX: {"fetched_at": "old", "symbols": BEFORE},
                                 nxt: {"fetched_at": "old", "symbols": ["ZZZ", MEM_HOLD]}}),
                     encoding="utf-8")
    monkeypatch.setattr(iw, "_make_nse_client",
                        lambda: _NSE({nxt: ["ZZZ"]}, down=(INDEX,)))
    out = _run(world)
    assert out["degraded"] == [INDEX] and out["events"] == 1
    assert json.loads(world.read_text(encoding="utf-8"))[INDEX]["symbols"] == BEFORE
    assert _log_rows(member) == {("index_exclusion", MEM_HOLD)}
    assert _log_rows(owner) == set()
    assert MEM_HOLD not in json.dumps(_pushes(wire, OWNER_ENDPOINTS[0]))
    assert wire.emails_to(OWNER_EMAIL) == []


def test_a_rerun_sends_nothing_twice(two_accounts, wire, world):
    before = world.read_text(encoding="utf-8")
    _run(world)
    sent = len(wire.pushes), len(wire.emails)
    world.write_text(before, encoding="utf-8")       # the same diff again, same day
    _run(world)
    assert (len(wire.pushes), len(wire.emails)) == sent


def test_events_the_old_broadcast_delivered_on_the_deploy_day_are_not_resent(
        two_accounts, wire, world):
    """Before FIX-009 the same run broadcast all four events to every account.
    The sent-log key is the account, date, kind and symbol, unchanged, so a
    run after the deploy on that day re-sends nothing to anyone."""
    old = [alerts.AlertEvent(date=DAY.isoformat(), kind=kind, symbol=sym,
                             message=f"{verb} {INDEX}", severity=sev)
           for kind, sym, verb, sev in (
               ("index_inclusion", OWN_HOLD, "included in", "info"),
               ("index_inclusion", SHELF_IDEA, "included in", "info"),
               ("index_exclusion", OWN_WATCH, "excluded from", "warning"),
               ("index_exclusion", MEM_HOLD, "excluded from", "warning"))]
    alerts.emit_alerts_broadcast(old, title=f"Index reconstitution — {DAY}")
    wire.pushes.clear()
    wire.emails.clear()
    assert _run(world)["events"] == 4
    assert wire.pushes == [] and wire.emails == []


# ---------------------------------------------------------------------------
# Atlas on: accounts from atlas.db, delivery through the outbox
# ---------------------------------------------------------------------------

def test_with_atlas_on_each_account_queues_only_its_own_and_the_shelf(
        two_accounts, wire, world, tmp_path, monkeypatch):
    from services.data.stores import atlas_store
    owner, member = two_accounts
    monkeypatch.setattr(atlas_store, "enabled", lambda: True)
    monkeypatch.setattr(atlas_store, "_DB_PATH", tmp_path / "atlas.db")
    monkeypatch.setattr(atlas_store, "_conn_holder", {"conn": None})
    try:
        for uid in (owner, member):                  # signup mirrors each account
            assert atlas_store.mirror_user(uid, users_db=user_store.db_path())
        assert sorted(portfolio_store.active_user_ids()) == sorted([owner, member])
        _run(world)
        rows = atlas_store._get_conn().execute(
            "SELECT user_id, channel, payload_ref FROM outbox").fetchall()
    finally:
        if atlas_store._conn_holder.get("conn") is not None:
            atlas_store._conn_holder["conn"].close()

    queued: dict[str, list[str]] = {}
    for uid, channel, payload in rows:
        queued.setdefault(uid, []).append(json.loads(payload)["body"])
        assert channel in ("push", "email")
    assert set(queued) == {owner, member}
    assert _named(queued[owner]) == {OWN_HOLD, OWN_WATCH, SHELF_IDEA}
    assert _named(queued[member]) == {MEM_HOLD, SHELF_IDEA}
    assert len(queued[owner]) == len(queued[member]) == 4    # 2 bundles x 2 channels
    assert wire.pushes == [] and wire.emails == []           # queued, not sent inline
