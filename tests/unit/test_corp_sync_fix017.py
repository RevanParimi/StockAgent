"""FIX-017: the holding sync reads every NSE corporate-action row it is given, under NSE's code.

The live sync (`corp_actions.sync_corp_actions`) adjusts each holding's quantity and average
price before the stops and targets run. It applies only the bonus and split ratios the exit
rule's grading record reads in full (`action_record`), so the two read every row alike, and it
asks NSE for the code the close is read under (`symbol_resolver.nse_symbol`).

Each expected effect below is worked by hand from what the row says for a holding of 100
shares bought at ₹1,000 on 5 Jan 2026, with the row ex 10 Jun 2026 and the sync on 6 Jul 2026.
"""
from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

import pytest

from backend.shared.data.fetchers import symbol_resolver
from backend.shared.schemas.portfolio import Holding, Portfolio
from core.portfolio import corp_actions as ca
from core.portfolio.store import PortfolioStore
from services.data.fetchers import corporate_events as ce

TODAY = date(2026, 7, 6)
EX = "10-Jun-2026"
REGISTRY = Path(__file__).resolve().parents[2] / "config" / "instruments.yaml"

BONUS_AND_SPLIT = ("Bonus 1:1/Face Value Split (Sub-Division) - From Rs 10/- Per Share To Rs 2/- "
                   "Per Share")
SPLIT_10_TO_2 = "Face Value Split (Sub-Division) - From Rs 10/- Per Share To Rs 2/- Per Share"


@pytest.fixture(autouse=True)
def _no_learned_symbols(monkeypatch):
    monkeypatch.setattr(symbol_resolver, "_load_cache", lambda: {})


def _holding(symbol: str, buy_date: str = "2026-01-05", qty: float = 100,
             price: float = 1000.0) -> Holding:
    return Holding(symbol=symbol, sector="banks", qty=qty, avg_buy_price=price,
                   adj_avg_price=price, adj_qty=qty, buy_date=buy_date)


def _store(tmp_path, holdings, name="u1") -> PortfolioStore:
    store = PortfolioStore(user_id=name, base_dir=str(tmp_path / name))
    store.save(Portfolio(user_id=name, holdings=list(holdings)))
    return store


# (NSE's subject, where it is from, quantity after, average price after, dividends after, a
# named gap). A ratio r: 100 x r shares at ₹1,000 / r, so the holding's worth and its P&L at
# the ex-day's fair close (₹1,000 / r) are unchanged. A row the sync cannot read: unchanged, and
# named.
ROWS = [
    # the plain rows
    ("Bonus 1:1", "plain bonus", 200, 500.0, 0.0, False),                    # 1 new for 1 held
    (SPLIT_10_TO_2, "plain split", 500, 200.0, 0.0, False),                  # 10 / 2 = 5
    ("Dividend - Rs 8 Per Share", "plain dividend", 100, 1000.0, 800.0, False),  # 100 x ₹8
    ("Annual General Meeting", "a meeting", 100, 1000.0, 0.0, False),
    # 1. a bonus and a split in one row: x2 and x5, a tenth of the price (was x2: -80%)
    (BONUS_AND_SPLIT, "BAJFINANCE 2016", 1000, 100.0, 0.0, False),
    # 2. a bonus of other securities: the number of equity shares does not change (was x22,
    #    x5 and x7)
    ("Bonus Preference Shares 21:1", "ZEEL 2014", 100, 1000.0, 0.0, True),
    ("Scheme Of Arrangement - Bonus Ncrps 4:1", "TVSMOTOR 2025", 100, 1000.0, 0.0, True),
    ("Scheme Of Arrangement - Bonus Debentures 6:1", "DRREDDY 2011", 100, 1000.0, 0.0, True),
    # 3. NSE's short split words: a split, old / new face value (was not seen: -90%, -80%)
    ("Fv Splt Frm Rs 10 To Re 1", "JSWSTEEL 2017", 1000, 100.0, 0.0, False),
    ("Fv Splt Frm Rs 10 To Rs 2", "KNRCON 2016", 500, 200.0, 0.0, False),
    # a split worded with no two face values the reader finds: unchanged, named
    ("Agm/Div-Rs.2/Fv Rs10tors5", "BHARTIARTL 2009", 100, 1000.0, 0.0, True),
]


@pytest.mark.parametrize("subject, source, qty, avg, dividends, gap", ROWS,
                         ids=[r[1] for r in ROWS])
def test_every_row_has_the_effect_worked_by_hand(tmp_path, subject, source, qty, avg,
                                                 dividends, gap):
    store = _store(tmp_path, [_holding("ACME")])
    result = ca.sync_corp_actions(store, TODAY,
                                  fetch=lambda s: [{"subject": subject, "exDate": EX}])
    held = store.load().holdings[0]
    assert (held.adj_qty, held.adj_avg_price, held.dividends_received) == (
        pytest.approx(qty), pytest.approx(avg), pytest.approx(dividends)), source
    assert (held.qty, held.avg_buy_price) == (100, 1000.0)          # raw fields untouched
    # the holding's worth at the ex-day's fair close is unchanged by a ratio it applied
    assert held.adj_qty * held.adj_avg_price == pytest.approx(100_000.0)
    lines = result["gaps"].get("ACME", [])
    assert bool(lines) is gap, (source, lines)
    if gap:
        assert lines == [f"NSE lists a split or bonus on 2026-06-10 that could not be read "
                         f"({subject!r}); the quantity and average price are unchanged"]


@pytest.mark.parametrize("subject", [r[0] for r in ROWS])
def test_the_sync_and_the_exit_rules_grading_read_every_row_alike(tmp_path, subject):
    """The ratio the sync applies is the product of the grading record's ratios for the row,
    and the sync names a gap exactly where the record holds the row unread."""
    row = {"subject": subject, "exDate": EX}
    record = ca.action_record([row], "ACME")
    store = _store(tmp_path, [_holding("ACME")])
    result = ca.sync_corp_actions(store, TODAY, fetch=lambda s: [row])
    graded = 1.0
    for a in record.actions:
        graded *= a.ratio
    assert store.load().holdings[0].adj_qty == pytest.approx(100 * graded)
    assert bool(result["gaps"]) is bool(record.unparsed)
    assert result["records"]["ACME"] == record


class _NseOnlyItsOwnCodes:
    """NSE's actions(): rows only under NSE's own codes, nothing under an app alias, as it
    answered on 29 Oct 2026 (CANARABANK: 0 rows; CANBK: 20)."""
    asked: list[str] = []

    def __init__(self, lists):
        self.lists = lists

    def actions(self, symbol):
        self.asked.append(symbol)
        return {"data": list(self.lists.get(symbol, []))}

    def exit(self):
        pass


def test_a_canara_bank_holding_is_split_through_the_real_sync(monkeypatch, tmp_path):
    """The card's example: bought before May 2024 at ₹500, 100 shares; Canara Bank split its
    face value from Rs 10 to Rs 2 ex 15 May 2024, and closes near ₹100. By hand: 500 shares at
    ₹100, a P&L of 0 at ₹100. With the defect the sync asked NSE for CANARABANK, got nothing,
    and the holding read ₹500 against ₹100: -80%, and the stop sold it."""
    monkeypatch.setenv("INSTRUMENT_REGISTRY_PATH", str(REGISTRY))
    _NseOnlyItsOwnCodes.asked = []
    lists = {"CANBK": [{"subject": SPLIT_10_TO_2, "exDate": "15-May-2024"},
                       {"subject": "Dividend - Rs 16.10 Per Share", "exDate": "13-Jun-2024"}]}
    monkeypatch.setattr(ce, "_make_nse_client", lambda: _NseOnlyItsOwnCodes(lists))
    store = _store(tmp_path, [_holding("CANARABANK", "2024-01-10", 100, 500.0)])
    result = ca.sync_corp_actions(store, date(2024, 6, 20))           # the real fetch
    held = store.load().holdings[0]
    assert _NseOnlyItsOwnCodes.asked == ["CANBK"]
    assert (held.adj_qty, held.adj_avg_price) == (pytest.approx(500), pytest.approx(100.0))
    assert held.dividends_received == pytest.approx(500 * 16.10)   # on the split shares
    # at ₹100 the shares are worth their cost; the P&L is the dividend alone, ₹8,050 on ₹50,000
    assert held.unrealised_pnl_pct(100.0) == pytest.approx(16.1)
    assert result["applied"] == 2 and result["gaps"] == {}
    assert [(a.kind, a.ratio) for a in result["records"]["CANARABANK"].actions] == [
        ("split", 5.0)]
    assert ce.fetch_corp_actions("CANARABANK") == []     # NSE lists nothing under the alias


def test_the_investment_case_asks_nse_under_its_own_code_too(monkeypatch):
    """PR-005's purchase record of an alias read NSE's empty list, so its level was unused."""
    monkeypatch.setenv("INSTRUMENT_REGISTRY_PATH", str(REGISTRY))
    from core.portfolio import cases
    asked = []
    monkeypatch.setattr(ce, "fetch_corp_actions",
                        lambda s: asked.append(s) or [{"subject": SPLIT_10_TO_2,
                                                        "exDate": "15-May-2024"}])
    record = cases._corp_record("CANARABANK")
    assert asked == ["CANBK"] and [(a.kind, a.ratio) for a in record.actions] == [("split", 5.0)]


# == Idempotency: a row already applied is never applied twice ==================================

def _applied_under_the_old_reading(subject: str):
    """What the sync before FIX-017 applied for `subject`: parse_action's one reading."""
    return ca.parse_action({"subject": subject, "exDate": EX, "symbol": "ACME"})


def test_a_bonus_and_split_row_applied_as_its_bonus_alone_gets_its_split_once(tmp_path):
    """Before FIX-017 the row was applied as x2 under its key. The new reading keeps that key for
    the bonus, already applied, and gives the split its own key: x5 more, x10 in all, the tenth
    the price fell to. A second sync applies nothing."""
    held = _holding("ACME")
    old = _applied_under_the_old_reading(BONUS_AND_SPLIT)
    assert (old.kind, old.ratio) == ("bonus", 2.0)
    ca.apply_actions_to_holding(held, [old], TODAY)
    assert (held.adj_qty, held.adj_avg_price) == (200, 500.0)
    store = _store(tmp_path, [held])
    fetch = lambda s: [{"subject": BONUS_AND_SPLIT, "exDate": EX}]          # noqa: E731
    assert ca.sync_corp_actions(store, TODAY, fetch=fetch)["applied"] == 1
    assert ca.sync_corp_actions(store, TODAY, fetch=fetch)["applied"] == 0
    after = store.load().holdings[0]
    assert (after.adj_qty, after.adj_avg_price) == (pytest.approx(1000), pytest.approx(100.0))
    assert [(a.kind, a.ratio) for a in after.applied_actions] == [("bonus", 2.0), ("split", 5.0)]


def test_a_bonus_of_other_securities_applied_before_is_named_never_reversed(tmp_path, caplog):
    """Before FIX-017 ZEEL's row was applied as 22 equity shares for one. The sync applies
    nothing more and does not reverse it: a ledger correction is the operator's. It names it
    each day, as a data-health warning, until corrected by hand. On 29 Oct 2026 no production
    holding had any bonus or split applied."""
    held = _holding("ACME")
    ca.apply_actions_to_holding(held, [_applied_under_the_old_reading(
        "Bonus Preference Shares 21:1")], TODAY)
    assert held.adj_qty == pytest.approx(2200)
    store = _store(tmp_path, [held])
    caplog.set_level(logging.WARNING, logger="core.portfolio.corp_actions")
    result = ca.sync_corp_actions(store, TODAY, fetch=lambda s: [
        {"subject": "Bonus Preference Shares 21:1", "exDate": EX}])
    assert result["applied"] == 0 and store.load().holdings[0].adj_qty == pytest.approx(2200)
    assert result["gaps"]["ACME"] == [
        "NSE lists a split or bonus on 2026-06-10 that could not be read ('Bonus Preference "
        "Shares 21:1'); the quantity and average price are unchanged",
        "the bonus ex 2026-06-10 (×22) was applied under an earlier reading, and NSE's row no "
        "longer reads as one; the quantity and average price keep it until corrected by hand"]
    assert sum("data health: ACME" in r.getMessage() for r in caplog.records) == 2


def test_a_reworded_row_for_a_bonus_already_applied_is_not_applied_again(tmp_path):
    """NSE rewords a row ("(Revised)"): a new key, the same bonus. By hand x2 once, not x4."""
    store = _store(tmp_path, [_holding("ACME")])
    first = [{"subject": "Bonus 1:1", "exDate": EX}]
    assert ca.sync_corp_actions(store, TODAY, fetch=lambda s: first)["applied"] == 1
    again = [{"subject": "Bonus 1:1 (Revised)", "exDate": EX}]
    assert ca.sync_corp_actions(store, TODAY, fetch=lambda s: again)["applied"] == 0
    assert store.load().holdings[0].adj_qty == 200


def test_two_ratios_of_one_kind_on_one_day_apply_neither(tmp_path):
    """NSE lists a 1:1 and a 1:2 bonus ex the same day. The grading has no result across that
    day; the sync applies neither and names it, so the quantity is never x2 or x1.5 by guess."""
    store = _store(tmp_path, [_holding("ACME")])
    result = ca.sync_corp_actions(store, TODAY, fetch=lambda s: [
        {"subject": "Bonus 1:1", "exDate": EX}, {"subject": "Bonus 1:2", "exDate": EX}])
    assert result["applied"] == 0 and store.load().holdings[0].adj_qty == 100
    assert result["gaps"]["ACME"] == ["NSE lists two bonus ratios ex 2026-06-10 (1.5 and 2); "
                                      "neither is applied"]


def test_a_row_before_the_buy_or_after_today_is_neither_applied_nor_named(tmp_path):
    store = _store(tmp_path, [_holding("ACME")])
    rows = [{"subject": "Bonus Preference Shares 21:1", "exDate": "03-Mar-2014"},
            {"subject": "Bonus 1:1", "exDate": "03-Mar-2014"},
            {"subject": "Bonus Preference Shares 21:1", "exDate": "10-Aug-2026"},
            {"subject": "Bonus 1:1", "exDate": "10-Aug-2026"}]
    result = ca.sync_corp_actions(store, TODAY, fetch=lambda s: rows)
    assert result["applied"] == 0 and result["gaps"] == {}
    assert store.load().holdings[0].adj_qty == 100
