"""FIX-025 — deployment follows the money and the ideas; a top-up checks NSE's
report too.

Every expected figure is worked by hand in the test's docstring or comments
from the fixture's own numbers, never asked of the code under test. Settings
come from SA-049's autouse fixture: no trading costs; 80% in calm regimes, 50%
in RISK_OFF, none in MACRO_CRISIS; a soft minimum of 10 holdings, 12 to size a
position by, at most 15; caps 10% and 30%; cash floor ₹10,000. A position asks
for 80% of equity ÷ 12.

Independent invariants:
- the card's table, each row by hand-derived quantities, through the real
  executor, and one row through the real pipeline;
- `stop_reason` over a brute-force grid against the definition written here:
  the soft minimum never changes whether a position opens;
- any amount of money: no cap breached, cash at or above its floor, the target
  never passed by more than one position (SA-049's property test now holds the
  same with no below-floor exception);
- D3: every kind of refusal stops a top-up in either switch position, keeps the
  shares and the cash, leaves the cooldown alone and reads NSE once;
- D4: a stock the autopilot sold since its latest dive is due the next Saturday
  ahead of routine re-dives, inside the budget; bought back only after that
  dive, by the first run that may use it, so at most one round trip a week;
- a stock sold with no idea left takes its rank in the screen like any other
  stock, once no portfolio holds it, and spends nothing a rank would not.
"""
from __future__ import annotations

import logging
import random
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

import core.discovery as disc
import core.discovery.shelf as shelf_mod
import core.portfolio.pipeline as pipeline
import tests.unit.test_deploy_idle_cash_sa049 as story
import tests.unit.test_idea_supply_pr004 as pr004
from backend.shared.schemas.discovery import Shelf
from backend.shared.schemas.portfolio import AdviceRecord, TransactionRecord
from core.config import settings
from core.discovery.candidates import buy_candidates
from core.portfolio import autopilot as ap
from core.portfolio import deployment, sizing
from core.portfolio.digest import build_digest
from core.portfolio.digest_text import render_digest_text
from tests.unit.test_deploy_idle_cash_sa049 import _pinned  # noqa: F401  (autouse)
from tests.unit.test_idea_supply_pr004 import shelf  # noqa: F401  (a fixture)

D = story.D                                  # Monday 13 Jul 2026
FLOOR = 10_000.0


def _unlimited(monkeypatch):
    monkeypatch.setattr(settings, "AUTOPILOT_DEPLOY_MAX_NEW_PER_DAY", 30)


def _bought(txns):
    return [(t.symbol, t.qty) for t in txns if t.side == "BUY"]


# ---------------------------------------------------------------------------
# The card's table
# ---------------------------------------------------------------------------

def test_row1_twelve_lakh_asks_for_a_share_of_equity_and_stops_at_the_target(tmp_path,
                                                                            monkeypatch):
    """₹12 L, calm, 2 holdings (₹1,90,000), ₹10,10,000 cash, 12 ideas at ₹1,000.
    Target 80% = ₹9,60,000. A position asks for 9,60,000 ÷ 12 = ₹80,000, 80
    shares. After 9 buys ₹9,10,000 is invested, below; the 10th makes ₹9,90,000
    (82.5%). Two ideas wait. Cash 10,10,000 − 8,00,000 = ₹2,10,000."""
    _unlimited(monkeypatch)
    s = story._store(tmp_path, [story._h("AAA", 1000, 100.0, "it_sector"),
                                story._h("BBB", 900, 100.0, "fmcg")], cash=1_010_000.0)
    ideas = story._ideas_at_1000(12)
    story._prices(monkeypatch, {i.symbol: 1000.0 for i in ideas})
    txns, rec = story._run(s, ideas, {"AAA": 100.0, "BBB": 100.0})
    assert _bought(txns) == [(f"I{k:02d}", 80.0) for k in range(10)]
    assert (rec["target_inr"], rec["target_pct"], rec["position_inr"]) == (960_000.0, 80.0, 80_000.0)
    assert rec["reasons"][0] == ("regime NORMAL, target reached: 82.5% invested against a target "
                                 "of 80.0% (₹9,60,000)")
    assert story._outcomes(rec)["I10"][0] == story._outcomes(rec)["I11"][0] == "waiting"
    assert s.load().cash_deployable == 210_000.0


def test_no_deposit_the_ten_lakh_book_buys_to_the_target(tmp_path, monkeypatch):
    """The book as it stands; no deposit is planned (owner, 6 Nov 2026). ₹10 L,
    calm, 2 holdings (₹1,90,000), ₹8,10,000 cash, 12 ideas at ₹1,000. Target 80% =
    ₹8,00,000. A position asks for 8,00,000 ÷ 12 = ₹66,666.67, 66 shares =
    ₹66,000. Two a day make 4, 6, 8, 10, 12 holdings. After 9 buys ₹7,84,000 is
    invested, below; the 10th makes ₹8,50,000 (85.0%). Two ideas wait, and day six
    buys nothing. Cash 8,10,000 − 6,60,000 = ₹1,50,000."""
    s = story._store(tmp_path, [story._h("AAA", 1000, 100.0, "it_sector"),
                                story._h("BBB", 900, 100.0, "fmcg")], cash=810_000.0)
    ideas = story._ideas_at_1000(12)
    story._prices(monkeypatch, {i.symbol: 1000.0 for i in ideas})
    bought, counts, rec = [], [], None
    for day in (13, 14, 15, 16, 17, 20):
        txns, rec = story._one_day(s, ideas, date(2026, 7, day), {"AAA": 100.0, "BBB": 100.0})
        bought += _bought(txns)
        counts.append(rec["holdings_after"])
    assert bought == [(f"I{k:02d}", 66.0) for k in range(10)]
    assert counts == [4, 6, 8, 10, 12, 12]
    assert rec["reasons"][0] == ("regime NORMAL, target reached: 85.0% invested against a target "
                                 "of 80.0% (₹8,00,000)")
    assert s.load().cash_deployable == 150_000.0


def test_no_deposit_the_ten_lakh_book_in_risk_off(tmp_path, monkeypatch):
    """₹10 L, all cash, RISK_OFF: the target is ₹5,00,000 and a position the same
    66 shares. Seven buys come to ₹4,62,000, below; the eighth makes ₹5,28,000
    (52.8%), past the target by less than one position."""
    _unlimited(monkeypatch)
    monkeypatch.setattr(deployment, "recorded_regime", lambda on: "RISK_OFF")
    s = story._store(tmp_path, [], cash=1_000_000.0)
    ideas = story._ideas_at_1000(12)
    story._prices(monkeypatch, {i.symbol: 1000.0 for i in ideas})
    txns, rec = story._run(s, ideas, {})
    assert _bought(txns) == [(f"I{k:02d}", 66.0) for k in range(8)]
    assert rec["reasons"][0] == ("regime RISK_OFF, target reached: 52.8% invested against a target "
                                 "of 50.0% (₹5,00,000)")


def test_row2_fifty_lakh_grows_each_position_and_stops_at_the_target(tmp_path, monkeypatch):
    """₹50 L, calm, all cash, 15 ideas at ₹1,000. A position asks for
    50 L × 80% ÷ 12 = ₹3,33,333.33, 333 shares = ₹3,33,000 (6.66%, inside the
    10% cap). Twelve come to ₹39,96,000, ₹4,000 short of the ₹40 L target, so a
    thirteenth opens: ₹43,29,000 (86.58%), past the target by less than one
    position. Two ideas wait. SA-049's fixed ₹83,333 stopped at 15 holdings with
    about ₹12.5 L (25%) invested. Cash 50,00,000 − 43,29,000 = ₹6,71,000."""
    _unlimited(monkeypatch)
    s = story._store(tmp_path, [], cash=5_000_000.0)
    ideas = story._ideas_at_1000(15)
    story._prices(monkeypatch, {i.symbol: 1000.0 for i in ideas})
    txns, rec = story._run(s, ideas, {})
    assert _bought(txns) == [(f"I{k:02d}", 333.0) for k in range(13)]
    assert rec["position_inr"] == 333_333.33
    assert rec["reasons"][0] == ("regime NORMAL, target reached: 86.6% invested against a target "
                                 "of 80.0% (₹40,00,000)")
    assert [o["outcome"] for o in rec["ideas"]][-2:] == ["waiting", "waiting"]
    assert s.load().cash_deployable == 671_000.0
    assert 4_329_000.0 - 4_000_000.0 < 333_333.33


def test_row2_through_the_real_pipeline(tmp_path, monkeypatch):
    """The same ₹50 L through the pipeline: the advisor has nothing to review,
    the candidates are the real list, the digest carries the record, and the
    day's value point keeps equity at ₹50 L."""
    _unlimited(monkeypatch)
    monkeypatch.setattr(ap, "_today_ist", lambda: D)
    ideas = story._ideas_at_1000(15)
    store, _ = story._pipeline_world(tmp_path, monkeypatch, [], 5_000_000.0, ideas,
                                     {i.symbol: 1000.0 for i in ideas})
    pipeline.run_post_review_pipeline(D)
    assert _bought(store.load_transactions()) == [(f"I{k:02d}", 333.0) for k in range(13)]
    digest = store.load_latest_digest()
    assert digest["deployment"]["position_inr"] == 333_333.33
    assert "Idle cash: bought I00" in render_digest_text(digest)
    point = store.load_value_history()[-1]
    assert (point["total_equity"], point["market_value"]) == (5_000_000.0, 4_329_000.0)


def test_max_holdings_still_binds_when_money_arrives_on_a_full_book(tmp_path, monkeypatch):
    """Recorded as it stands: the owner agreed "up to max_holdings (15)" on 4 Nov,
    and on 6 Nov was asked whether it stays. The ₹10 L book once deployed: AAA, BBB
    and ten positions of 66 shares at ₹1,000, ₹8,50,000 in 12 holdings. ₹40 L
    arrives: equity ₹50 L, cash ₹41,50,000. A position asks for ₹3,33,333.33, 333
    shares. Three open and the maximum stops the fourth: ₹18,49,000 (37.0%) invested
    against a ₹40 L target, ₹31,51,000 idle. Two ideas wait."""
    _unlimited(monkeypatch)
    held = [story._h("AAA", 1000, 100.0, "it_sector"), story._h("BBB", 900, 100.0, "fmcg")]
    held += [story._h(f"H{k:02d}", 66, 1000.0, f"held{k:02d}") for k in range(10)]
    s = story._store(tmp_path, held, cash=4_150_000.0)
    ideas = story._ideas_at_1000(5)
    story._prices(monkeypatch, {i.symbol: 1000.0 for i in ideas})
    txns, rec = story._run(s, ideas, {h.symbol: h.avg_buy_price for h in held})
    assert _bought(txns) == [(f"I{k:02d}", 333.0) for k in range(3)]
    assert rec["reasons"][0] == "15 holdings, the maximum of 15"
    assert (rec["equity"], rec["invested_after_pct"], rec["target_inr"]) == (5_000_000.0, 37.0, 4_000_000.0)
    assert s.load().cash_deployable == 3_151_000.0
    assert [o["outcome"] for o in rec["ideas"]][-2:] == ["waiting", "waiting"]


def test_row3_a_fall_never_buys_toward_the_old_floor(tmp_path, monkeypatch):
    """₹12 L fell to ₹10,20,000: 9 holdings worth ₹8,77,200 (86.0%), ₹1,42,800
    cash. Target 80% = ₹8,16,000, already met. SA-049's ₹10 L floor bought 83
    shares, then 58 more, to about 99%. Now nothing is bought, and the 9
    holdings are only reported."""
    held = [story._h(f"H{k}", 975, 100.0, ("banking", "power", "metals", "fmcg")[k % 4])
            for k in range(8)] + [story._h("H8", 972, 100.0, "pharma")]
    s = story._store(tmp_path, held, cash=142_800.0)
    ideas = story._ideas_at_1000(3)
    story._prices(monkeypatch, {i.symbol: 1000.0 for i in ideas})
    txns, rec = story._run(s, ideas, {h.symbol: 100.0 for h in held})
    assert txns == [] and s.load().cash_deployable == 142_800.0
    assert rec["reasons"] == [
        "regime NORMAL, target reached: 86.0% invested against a target of 80.0% (₹8,16,000)",
        "9 holdings, below the 10 aimed for: target reached"]


def test_row4_only_six_ideas_are_all_bought_and_the_record_says_so(tmp_path, monkeypatch):
    """₹12 L, 6 qualifying ideas at ₹1,000: 6 × 80 shares. The ideas decide how
    many, so no other buy is forced; the sentence replaces SA-049's "holdings
    floor unreachable"."""
    _unlimited(monkeypatch)
    s = story._store(tmp_path, [], cash=1_200_000.0)
    ideas = story._ideas_at_1000(6)
    story._prices(monkeypatch, {i.symbol: 1000.0 for i in ideas})
    txns, rec = story._run(s, ideas, {})
    assert _bought(txns) == [(f"I{k:02d}", 80.0) for k in range(6)]
    assert rec["reasons"] == ["no further qualifying idea",
                              "6 holdings, below the 10 aimed for: only 6 qualifying ideas"]
    assert not any("floor" in r for r in rec["reasons"])


def test_row6_a_stock_sold_since_its_dive_is_due_the_next_saturday(shelf):
    """Analysed 24 Oct, sold 27 Oct. Today its routine re-dive comes once the
    dive is over 30 days old: not on Sat 21 Nov (28 days), on Sat 28 Nov (35).
    With the sale it is due on Sat 31 Oct."""
    shelf.save(Shelf(ideas=[pr004._idea("SOLD", "2026-10-24")]))
    due = lambda on, sold=None: [i.symbol for i in shelf.redive_due(on, sold)]  # noqa: E731
    sat_31_oct, sat_21_nov, sat_28_nov = date(2026, 10, 31), date(2026, 11, 21), date(2026, 11, 28)
    sale = {"SOLD": date(2026, 10, 27)}
    assert due(sat_31_oct, sale) == ["SOLD"]
    assert (due(sat_31_oct), due(sat_21_nov), due(sat_28_nov)) == ([], [], ["SOLD"])


# ---------------------------------------------------------------------------
# The target and the soft minimum
# ---------------------------------------------------------------------------

def _breadth(min_h=10, target_h=12, max_h=15, shares=None):
    return deployment.Breadth(True, min_h, target_h, max_h, shares or dict(story.TARGETS))


def test_the_target_is_the_regimes_share_and_nothing_else():
    """₹12 L: 80% and 50%. Near the cash floor the room governs: 80% of ₹12,000
    is ₹9,600, but ₹2,000 sits above the ₹10,000 floor. Below the floor, no room."""
    b = _breadth()
    assert deployment.target("NORMAL", 1_200_000.0, b, FLOOR).invested_inr == 960_000.0
    assert deployment.target("RISK_OFF", 1_200_000.0, b, FLOOR).invested_inr == 600_000.0
    assert deployment.target("NORMAL", 12_000.0, b, FLOOR).invested_inr == 2_000.0
    assert deployment.target("NORMAL", 9_000.0, b, FLOOR).invested_inr == 0.0
    assert deployment.target("NORMAL", 1_200_000.0, b, FLOOR).min_holdings == 10
    assert deployment.target("RISK_OFF", 1_200_000.0, b, FLOOR).min_holdings == 0


def test_a_position_is_the_calm_share_of_equity_in_every_regime():
    """80% × equity ÷ 12, by hand: ₹12 L → ₹80,000; ₹50 L → ₹3,33,333.33; twice
    the money asks for twice the position. No NORMAL share asks for nothing."""
    b = _breadth()
    assert b.position_inr(1_200_000.0) == pytest.approx(80_000.0)
    assert b.position_inr(5_000_000.0) == pytest.approx(333_333.33, abs=0.01)
    assert b.position_inr(2_400_000.0) == pytest.approx(2 * b.position_inr(1_200_000.0))
    assert _breadth(shares={"RISK_OFF": 50.0}).position_inr(1_200_000.0) == 0.0
    # The holdings it is sized by: 80% × 12 L ÷ 10 = ₹96,000.
    assert _breadth(target_h=10).position_inr(1_200_000.0) == pytest.approx(96_000.0)


def test_with_costs_a_position_follows_the_day_s_equity(tmp_path, monkeypatch):
    """₹12 L all cash at the configured rates, two buys a day at ₹1,000. Day one:
    ₹80,000 asks for 80 shares. The charges on ₹80,000 are about ₹95: STT ₹80,
    stamp duty ₹12, exchange ₹2.46, SEBI ₹0.08, GST 18% of the last two ₹0.46.
    So day two's equity is about ₹11,99,810, a position ₹79,987, and 79 shares."""
    monkeypatch.setattr(settings, "PORTFOLIO_COSTS", story.CONFIGURED_COSTS)
    s = story._store(tmp_path, [], cash=1_200_000.0)
    ideas = story._ideas_at_1000(4)
    story._prices(monkeypatch, {i.symbol: 1000.0 for i in ideas})
    first, _ = story._run(s, ideas, {})
    assert _bought(first) == [("I00", 80.0), ("I01", 80.0)]
    assert first[0].costs.total == pytest.approx(94.99, abs=0.05)
    second, _ = story._run(s, ideas, {"I00": 1000.0, "I01": 1000.0}, on=D + timedelta(days=1))
    assert _bought(second) == [("I02", 79.0), ("I03", 79.0)]


def test_the_soft_minimum_never_changes_whether_a_position_opens():
    """Brute force against the definition written here: at ₹10 L in NORMAL, a
    position opens iff holdings are below the maximum, the day's limit is not
    reached and invested is below ₹8,00,000. Neither the soft minimum nor the
    holdings a position is sized by moves that answer."""
    checked = 0
    for min_h in (0, 1, 10, 16):
        for target_h in (4, 12, 20):
            b = _breadth(min_h=min_h, target_h=target_h)
            t = deployment.target("NORMAL", 1_000_000.0, b, FLOOR)
            for holdings in range(0, 18):
                for invested in (0.0, 500_000.0, 799_999.99, 800_000.0, 900_000.0):
                    for opened in range(0, 4):
                        why = deployment.stop_reason(t, b, equity=1_000_000.0, invested=invested,
                                                     holdings=holdings, opened=opened, max_new=2)
                        opens = holdings < 15 and opened < 2 and invested < 800_000.0
                        assert (why == "") is opens, (min_h, target_h, holdings, invested, opened)
                        checked += 1
    assert checked == 4 * 3 * 18 * 5 * 4


@pytest.mark.parametrize("regime, holdings, invested, stop, outcomes, sentence", [
    ("NORMAL", 8, 500_000.0, "", ["bought"] * 8,
     "8 holdings, below the 10 aimed for: only 8 qualifying ideas"),
    ("NORMAL", 1, 100_000.0, "", ["bought"],
     "1 holding, below the 10 aimed for: only 1 qualifying idea"),
    ("NORMAL", 2, 200_000.0, "", ["band"],
     "2 holdings, below the 10 aimed for: no qualifying idea"),
    ("NORMAL", 9, 860_000.0, "target stop", [],
     "9 holdings, below the 10 aimed for: target reached"),
    ("NORMAL", 4, 300_000.0, "the daily limit", ["bought"] * 2 + ["waiting"] * 6,
     "4 holdings, below the 10 aimed for: the daily limit"),
    ("NORMAL", 4, 300_000.0, "the daily limit", ["bought"] * 2 + ["waiting"],
     "4 holdings, below the 10 aimed for: only 3 qualifying ideas"),
    ("NORMAL", 3, 0.0, "nothing looked at", [],
     "3 holdings, below the 10 aimed for: nothing looked at"),
    ("NORMAL", 10, 500_000.0, "", [], ""),
    ("NORMAL", 12, 900_000.0, "target stop", [], ""),
    ("RISK_OFF", 4, 600_000.0, "target stop", [], ""),
    ("MACRO_CRISIS", 2, 0.0, "closed", [], ""),
    (None, 2, 0.0, "closed", [], ""),
])
def test_the_soft_minimums_sentence(regime, holdings, invested, stop, outcomes, sentence):
    """₹10 L: the target is ₹8 L in NORMAL. The aim is in force only in calm
    regimes, and its reason is the first that applies: the target, ideas waiting
    behind the limit, too few ideas."""
    t = deployment.target(regime, 1_000_000.0, _breadth(), FLOOR)
    assert deployment.below_aim(t, holdings=holdings, invested=invested, stop=stop,
                                outcomes=[{"outcome": o} for o in outcomes]) == sentence


def test_a_portfolio_below_the_cash_floor_says_so_not_target_reached(tmp_path):
    """₹9,000 and no holdings: no room above the ₹10,000 floor; the aim's reason
    is the stop, not "target reached"."""
    s = story._store(tmp_path, [], cash=9_000.0)
    txns, rec = story._run(s, [], {})
    assert txns == []
    assert rec["reasons"] == ["no equity above the cash floor to invest",
                              "0 holdings, below the 10 aimed for: no equity above the cash "
                              "floor to invest"]


def test_property_any_amount_of_money_keeps_every_cap(tmp_path, monkeypatch):
    """300 seeded portfolios from ₹50,000 to ₹5 crore, no daily limit in the way,
    at the configured trading costs. By this test's own arithmetic at the run's
    marks: each buy asks for at most 80% of the run's equity ÷ 12; each position
    at most 10% of equity after the buys, each sector at most 30%; cash at or
    above the floor; at most 15 holdings; invested past the regime's share by
    at most one position. The counters prove the cases were exercised."""
    monkeypatch.setattr(settings, "PORTFOLIO_COSTS", story.CONFIGURED_COSTS)
    _unlimited(monkeypatch)
    seen = {"buys": 0, "large": 0, "capped": 0, "target": 0, "maximum": 0, "below_aim": 0}
    for seed in range(300):
        rng = random.Random(10_000 + seed)
        regime = rng.choice(["NORMAL", "RISK_ON", "OVERSOLD", "RISK_OFF"])
        story._regime(monkeypatch, regime)
        cash = round(rng.choice([50_000, 300_000, 1_200_000, 5_000_000, 50_000_000])
                     * rng.uniform(0.6, 1.4), 2)
        holdings, marks = [], {}
        for i in range(rng.choice([0, 0, 2, 5, 9])):
            cost = round(rng.uniform(50, 3000), 2)
            h = story._h(f"H{i}", float(rng.randint(1, 300)), cost, rng.choice(story.SECTORS))
            holdings.append(h)
            marks[h.symbol] = round(cost * rng.uniform(0.7, 1.4), 2)
        prices, ideas = {}, []
        for k in range(rng.randint(0, 25)):
            sym = f"C{k}"
            prices[sym] = round(rng.choice([rng.uniform(20, 2_000), rng.uniform(2_000, 150_000)]), 2)
            ideas.append(story._idea(sym, prices[sym], round(rng.random(), 2),
                                     rng.choice(story.SECTORS)))
        story._prices(monkeypatch, prices)
        s = story._store(tmp_path, holdings, cash, name=f"p{seed}")
        before = s.load()
        equity = sizing.total_equity(before, marks)
        invested0 = sizing.holdings_value(before, marks)
        asked = equity * 0.80 / 12
        share = 0.50 if regime == "RISK_OFF" else 0.80
        target = min(share * equity, max(0.0, equity - FLOOR))
        txns, rec = story._run(s, ideas, dict(marks))
        after = s.load()
        run_marks = {**marks, **prices}
        buys = [t for t in txns if t.side == "BUY"]
        seen["buys"] += len(buys)
        seen["large"] += equity > 2_000_000 and len(buys) > 0
        seen["capped"] += any("capped by" in t.note for t in buys)
        seen["target"] += "target reached" in rec["reasons"][0]
        seen["maximum"] += "the maximum of" in rec["reasons"][0]
        seen["below_aim"] += any("aimed for" in r for r in rec["reasons"])
        assert len(after.holdings) <= 15, seed
        if buys:
            assert after.cash_deployable >= FLOOR - 0.005, seed
            assert sizing.holdings_value(after, run_marks) <= \
                max(target, invested0) + asked + 1e-6, seed
        # The caps hold on the equity at each buy: a later buy's charges then
        # shrink equity by a few rupees. So replay the ledger in order.
        sector_of = {h.symbol: h.sector for h in after.holdings}
        in_sector: dict = {}
        for h in before.holdings:
            in_sector[h.sector] = in_sector.get(h.sector, 0.0) + h.adj_qty * marks[h.symbol]
        equity_now = equity
        for t in buys:
            equity_now -= t.costs.total
            value = t.qty * t.price
            in_sector[sector_of[t.symbol]] = in_sector.get(sector_of[t.symbol], 0.0) + value
            assert value <= asked + 1e-6, seed
            assert value <= 0.10 * equity_now + 1e-6, (seed, t.symbol)
            assert in_sector[sector_of[t.symbol]] <= 0.30 * equity_now + 1e-6, (seed, t.symbol)
    assert seen["buys"] > 300 and seen["large"] > 30, seen
    assert seen["target"] > 20 and seen["capped"] > 5 and seen["below_aim"] > 50, seen


# ---------------------------------------------------------------------------
# Settings change the behaviour with no code change
# ---------------------------------------------------------------------------

def test_the_removed_setting_is_gone_and_an_old_override_of_it_does_nothing(tmp_path, monkeypatch):
    """₹12 L with a leftover override asking for ₹90 L: the position stays 80
    shares and the target ₹9,60,000."""
    assert not hasattr(settings, "PORTFOLIO_MIN_INVESTED_INR")
    monkeypatch.setattr(settings, "PORTFOLIO_OVERRIDES", {"u": {"min_invested_inr": 9_000_000}})
    s = story._store(tmp_path, [], cash=1_200_000.0)
    ideas = story._ideas_at_1000(1)
    story._prices(monkeypatch, {"I00": 1000.0})
    txns, rec = story._run(s, ideas, {})
    assert _bought(txns) == [("I00", 80.0)] and rec["target_inr"] == 960_000.0


def test_regime_shares_from_config_set_the_target_and_the_position(tmp_path, monkeypatch):
    """NORMAL at 60%: target ₹7,20,000; a position 60% × 12 L ÷ 12 = ₹60,000, 60
    shares; 12 of them are exactly the target."""
    _unlimited(monkeypatch)
    monkeypatch.setattr(settings, "AUTOPILOT_DEPLOY_TARGET_PCT", {**story.TARGETS, "NORMAL": 60.0})
    s = story._store(tmp_path, [], cash=1_200_000.0)
    ideas = story._ideas_at_1000(14)
    story._prices(monkeypatch, {i.symbol: 1000.0 for i in ideas})
    txns, rec = story._run(s, ideas, {})
    assert _bought(txns) == [(f"I{k:02d}", 60.0) for k in range(12)]
    assert rec["target_inr"] == 720_000.0


def test_one_portfolio_can_have_its_own_shares_and_its_own_aim(tmp_path, monkeypatch):
    """Portfolio u, RISK_OFF, its override naming only RISK_OFF at 30% and an
    aim of 3: target 30% × 12 L = ₹3,60,000. The position still comes from the
    configured NORMAL 80%: ₹80,000, so 5 buys make ₹4,00,000 past the target.
    Portfolio v, the same day, keeps 50%: 8 buys. In NORMAL, u's override
    leaves 80% alone, and with an aim of 3 its 4 holdings need no sentence."""
    _unlimited(monkeypatch)
    monkeypatch.setattr(settings, "PORTFOLIO_OVERRIDES", {
        "u": {"deploy_target_invested_pct": {"risk_off": 30}, "min_holdings": 3}})
    ideas = story._ideas_at_1000(10)
    story._prices(monkeypatch, {i.symbol: 1000.0 for i in ideas})
    story._regime(monkeypatch, "RISK_OFF")
    u = story._store(tmp_path, [], cash=1_200_000.0, name="u")
    assert len(story._run(u, ideas, {})[0]) == 5
    v = story._store(tmp_path, [], cash=1_200_000.0, name="v")
    assert len(story._run(v, ideas, {})[0]) == 8
    assert deployment.breadth("u").shares["NORMAL"] == 80.0
    story._regime(monkeypatch, "NORMAL")
    monkeypatch.setattr(settings, "AUTOPILOT_DEPLOY_MAX_NEW_PER_DAY", 4)
    w = story._store(tmp_path, [], cash=1_200_000.0, name="u2")
    monkeypatch.setattr(settings, "PORTFOLIO_OVERRIDES", {"u2": {"min_holdings": 3}})
    txns, rec = story._run(w, ideas, {})
    assert len(txns) == 4 and not any("aimed for" in r for r in rec["reasons"])


def test_the_shipped_config_names_the_owners_values():
    from backend.shared.config.settings.loader import cfg
    assert cfg("portfolio.min_invested_inr", fallback=None) is None
    assert (cfg("portfolio.min_holdings"), cfg("portfolio.target_holdings"),
            cfg("portfolio.max_holdings")) == (10, 12, 15)


# ---------------------------------------------------------------------------
# D3: a top-up checks NSE's report
# ---------------------------------------------------------------------------

def _add(symbol="RAILCO", day=D, close=800.0, confidence=0.8):
    return AdviceRecord(date=day.isoformat(), user_id="u", symbol=symbol, verdict="ADD",
                        close=close, unrealised_pnl_pct=100.0, stop_pct=12.0,
                        confidence=confidence, rationale_hash=f"a{symbol}{day}")


def _railco(tmp_path, monkeypatch, name="u"):
    """100 RAILCO at a ₹400 cost, now ₹800: ₹80,000; ₹9,20,000 cash; equity ₹10 L.
    The tranche is 25% of ₹80,000 = ₹20,000, 25 shares; the position then is
    ₹1,00,000, exactly the 10% cap. No other idea on offer."""
    monkeypatch.setattr(settings, "AUTOPILOT_ADD_TRANCHE_PCT", 25.0)
    monkeypatch.setattr(settings, "AUTOPILOT_ADD_COOLDOWN_TD", 5)
    return story._store(tmp_path, [story._h("RAILCO", 100, 400.0, "infra")], cash=920_000.0,
                        name=name)


REFUSALS = [
    ({"measures": {"RAILCO": ["LT-ASM"]}},
     "top-up skipped: under LT-ASM in NSE's surveillance report of 2026-07-10"),
    ({"measures": {"RAILCO": ["ST-ASM"]}},
     "top-up skipped: under ST-ASM in NSE's surveillance report of 2026-07-10"),
    ({"measures": {"RAILCO": ["GSM"]}},
     "top-up skipped: under GSM in NSE's surveillance report of 2026-07-10"),
    ({"status": {"RAILCO": "S"}},
     "top-up skipped: status S, not active, in NSE's surveillance report of 2026-07-10"),
    ({"unlisted": ("RAILCO",)},
     "top-up skipped: not listed in NSE's surveillance report of 2026-07-10"),
    ({"dark": True},
     "top-up skipped: NSE's surveillance report is unavailable (none from the last 7 days)"),
]


@pytest.mark.parametrize("deploying", [False, True], ids=["switch_off", "switch_on"])
@pytest.mark.parametrize("report, why", REFUSALS)
def test_d3_a_top_up_nse_refuses_keeps_the_shares_and_says_why(tmp_path, monkeypatch, caplog,
                                                                report, why, deploying):
    """SA-049's executor bought 25 at ₹800 here. Now no BUY, 100 shares and
    ₹9,20,000 stay, and the skip reaches the run's report and the log, whether
    or not deployment is on."""
    monkeypatch.setattr(settings, "AUTOPILOT_DEPLOY_IDLE_CASH", deploying)
    s = _railco(tmp_path, monkeypatch)
    story._report(monkeypatch, **report)
    caplog.set_level(logging.INFO, logger="core.portfolio.autopilot")
    out: dict = {}
    txns, _ = story._run(s, [], {"RAILCO": 800.0}, advice=[_add()], report=out)
    assert txns == []
    p = s.load()
    assert ([(h.symbol, h.adj_qty) for h in p.holdings], p.cash_deployable) == \
        ([("RAILCO", 100.0)], 920_000.0)
    assert out["top_ups_skipped"] == [{"symbol": "RAILCO", "why": why}]
    assert f"ADD RAILCO skipped: {why.removeprefix('top-up skipped: ')}" in caplog.text
    assert p.last_autopilot_run == D.isoformat()


@pytest.mark.parametrize("deploying", [False, True], ids=["switch_off", "switch_on"])
def test_d3_a_top_up_of_a_cleared_stock_is_unchanged(tmp_path, monkeypatch, deploying):
    """BUY 25 at ₹800 = ₹20,000; cash ₹9,00,000; 125 shares; nothing skipped."""
    monkeypatch.setattr(settings, "AUTOPILOT_DEPLOY_IDLE_CASH", deploying)
    s = _railco(tmp_path, monkeypatch)
    out: dict = {}
    txns, _ = story._run(s, [], {"RAILCO": 800.0}, advice=[_add()], report=out)
    assert [(t.side, t.symbol, t.qty, t.price, t.note) for t in txns] == \
        [("BUY", "RAILCO", 25.0, 800.0, "add_tranche")]
    assert s.load().holdings[0].adj_qty == 125.0 and s.load().cash_deployable == 900_000.0
    assert "top_ups_skipped" not in out


def test_d3_a_skip_does_not_start_the_cooldown(tmp_path, monkeypatch):
    """Monday RAILCO is under LT-ASM: skipped, no BUY on the ledger. Tuesday it
    is clear: the ADD buys 25 at once, as no cooldown began."""
    monkeypatch.setattr(settings, "AUTOPILOT_DEPLOY_IDLE_CASH", False)
    s = _railco(tmp_path, monkeypatch)
    story._report(monkeypatch, measures={"RAILCO": ["LT-ASM"]})
    assert story._run(s, [], {"RAILCO": 800.0}, advice=[_add()])[0] == []
    story._report(monkeypatch)
    tue = D + timedelta(days=1)
    txns, _ = story._run(s, [], {"RAILCO": 800.0}, on=tue, advice=[_add(day=tue)])
    assert [(t.symbol, t.qty) for t in txns] == [("RAILCO", 25.0)]


def _past_buy(day: str) -> TransactionRecord:
    return TransactionRecord(
        txn_id=f"b{day}", date=day, ts=f"{day}T11:00:00+00:00", user_id="u", symbol="RAILCO",
        side="BUY", qty=1, price=800.0, value=800.0, cash_before=920_800.0, cash_after=920_000.0,
        holding_qty_after=100.0, verdict="ADD")


def test_d3_the_cooldown_comes_first_and_is_untouched(tmp_path, monkeypatch):
    """A buy on Thu 9 Jul is 2 sessions before Mon 13 Jul, inside the 5-session
    cooldown: no BUY, no skip recorded and NSE not read, whatever the report
    says. Mon 20 Jul is 7 sessions on: the cooldown is over, so the report
    decides, and refuses. Fri 24 Jul it clears, and the ADD buys."""
    monkeypatch.setattr(settings, "AUTOPILOT_DEPLOY_IDLE_CASH", False)
    s = _railco(tmp_path, monkeypatch)
    s.append_transaction(_past_buy("2026-07-09"))
    reads = story._report(monkeypatch, measures={"RAILCO": ["LT-ASM"]})
    out: dict = {}
    assert story._run(s, [], {"RAILCO": 800.0}, advice=[_add()], report=out)[0] == []
    assert out == {} and reads == []

    monday = date(2026, 7, 20)
    assert story._run(s, [], {"RAILCO": 800.0}, on=monday, advice=[_add(day=monday)],
                      report=out)[0] == []
    assert out["top_ups_skipped"][0]["symbol"] == "RAILCO" and reads == [monday]
    story._report(monkeypatch)
    friday = date(2026, 7, 24)
    txns, _ = story._run(s, [], {"RAILCO": 800.0}, on=friday, advice=[_add(day=friday)])
    assert [(t.symbol, t.qty) for t in txns] == [("RAILCO", 25.0)]


def test_d3_one_refused_top_up_leaves_the_next_and_reads_nse_once(tmp_path, monkeypatch):
    """RAILCO under ST-ASM and CLEAR clean, both ADD (RAILCO first, more
    confident), and a SWITCH of AAA into WATCHED under LT-ASM: every buy is
    checked against one read of the report. CLEAR: 25% of 100 × ₹800 = 25
    shares. AAA's sale stays in cash."""
    monkeypatch.setattr(settings, "AUTOPILOT_DEPLOY_IDLE_CASH", False)
    monkeypatch.setattr(settings, "AUTOPILOT_ADD_TRANCHE_PCT", 25.0)
    s = story._store(tmp_path, [story._h("RAILCO", 100, 400.0, "infra"),
                                story._h("CLEAR", 100, 400.0, "power"),
                                story._h("AAA", 100, 100.0, "fmcg")], cash=830_000.0)
    reads = story._report(monkeypatch, measures={"RAILCO": ["ST-ASM"], "WATCHED": ["LT-ASM"]})
    story._prices(monkeypatch, {"WATCHED": 500.0})
    switch = AdviceRecord(date=D.isoformat(), user_id="u", symbol="AAA", verdict="SWITCH",
                          close=100.0, unrealised_pnl_pct=0.0, stop_pct=12.0,
                          switch_candidate="WATCHED", rationale_hash="s1")
    out: dict = {}
    txns, _ = story._run(s, [story._idea("WATCHED", 500.0)], {"RAILCO": 800.0, "CLEAR": 800.0,
                                                              "AAA": 100.0},
                         advice=[_add("RAILCO", confidence=0.9), _add("CLEAR", confidence=0.7),
                                 switch], report=out)
    assert [(t.side, t.symbol, t.qty) for t in txns] == [("SELL", "AAA", 100.0),
                                                         ("BUY", "CLEAR", 25.0)]
    assert [x["symbol"] for x in out["top_ups_skipped"]] == ["RAILCO"]
    assert reads == [D]


def test_d3_through_the_pipeline_nse_is_read_before_the_lock_and_the_digest_says_why(tmp_path,
                                                                                     monkeypatch):
    """Deployment off (production today), the advisor's verdict forced to ADD at
    its one seam. The report is read before the executor takes the user's lock,
    the ADD buys nothing, and the digest's row and text name the measure while
    the row keeps its ADD verdict."""
    monkeypatch.setattr(settings, "AUTOPILOT_DEPLOY_IDLE_CASH", False)
    monkeypatch.setattr(settings, "AUTOPILOT_ADD_TRANCHE_PCT", 25.0)
    monkeypatch.setattr(ap, "_today_ist", lambda: D)
    store, _ = story._pipeline_world(tmp_path, monkeypatch,
                                     [story._h("RAILCO", 100, 400.0, "infra")], 920_000.0, [],
                                     {"RAILCO": 800.0})
    reads = story._report(monkeypatch, measures={"RAILCO": ["LT-ASM"]})
    real_decide, real_execute = pipeline.gated_decide, ap.execute_advice

    def to_add(*a, **k):
        rec, rest = real_decide(*a, **k)
        return rec.model_copy(update={"verdict": "ADD"}), rest
    read_at_entry = []

    def execute(*a, **k):
        read_at_entry.append(len(reads))
        return real_execute(*a, **k)
    monkeypatch.setattr(pipeline, "gated_decide", to_add)
    monkeypatch.setattr(ap, "execute_advice", execute)
    pipeline.run_post_review_pipeline(D)
    assert read_at_entry == [1] and reads == [D]
    assert [t for t in store.load_transactions() if t.side == "BUY"] == []
    assert store.load().holdings[0].adj_qty == 100.0
    digest = store.load_latest_digest()
    why = "top-up skipped: under LT-ASM in NSE's surveillance report of 2026-07-10"
    assert digest["holdings"][0]["verdict"] == "ADD"
    assert digest["holdings"][0]["top_up_skipped"] == why
    assert f"ADD: RAILCO — n ({why})" in render_digest_text(digest)


def test_d3_a_digest_with_no_skipped_top_up_has_no_such_field():
    """A row stays as it was, so nothing reading older digests changes."""
    p = SimpleNamespace(holdings=[story._h("AAA", 10, 100.0, "fmcg")])
    rec = _add("AAA", close=100.0).model_copy(update={"narrative": "why"})
    digest = build_digest("u", D, [rec], p, {"AAA": 100.0})
    assert "top_up_skipped" not in digest["holdings"][0]
    assert render_digest_text(digest).endswith("ADD: AAA — why")


# ---------------------------------------------------------------------------
# D4: a sold stock is re-analysed the next Saturday
# ---------------------------------------------------------------------------

def _sale(symbol, day, *, ts=None, source="autopilot", left=0.0) -> TransactionRecord:
    return TransactionRecord(
        txn_id=f"s{symbol}{day}{source}{left}", date=day, ts=ts or f"{day}T11:00:00+00:00",
        user_id="u", symbol=symbol, side="SELL", qty=10, price=100.0, value=1000.0,
        cash_before=0.0, cash_after=1000.0, holding_qty_after=left, verdict="EXIT", source=source)


def test_d4_order_sold_first_then_the_routine_ones(shelf):
    """On Sat 4 Jul, with the 30-day rule and the 60-day stale age:
    SOLD_OLD (dived 40 days ago, sold 1 Jul), SOLD_NEW (dived 26 Jun, sold on its
    dive day), then the routine order PRE (no gate), STALE. KEPT was sold before
    its latest dive; FRESH was never sold; ROTATING is 65 days old and rotates
    even though it was sold."""
    on = date(2026, 7, 4)
    shelf.save(Shelf(ideas=[
        pr004._idea("STALE", "2026-05-25"), pr004._idea("PRE", "2026-06-20", gate=""),
        pr004._idea("SOLD_NEW", "2026-06-26"), pr004._idea("SOLD_OLD", "2026-05-25"),
        pr004._idea("KEPT", "2026-06-30"), pr004._idea("FRESH", "2026-06-29"),
        pr004._idea("ROTATING", "2026-04-30")]))
    sold = {"SOLD_OLD": date(2026, 7, 1), "SOLD_NEW": date(2026, 6, 26),
            "KEPT": date(2026, 6, 29), "ROTATING": date(2026, 7, 1)}
    assert [i.symbol for i in shelf.redive_due(on, sold)] == \
        ["SOLD_OLD", "SOLD_NEW", "PRE", "STALE"]
    assert [i.symbol for i in shelf.redive_due(on)] == ["PRE", "STALE", "SOLD_OLD"]


def test_d4_an_undated_dive_counts_as_before_the_sale():
    """The re-buy rule's reading: a dive with no date cannot be shown to be after
    the sale, so the stock waits, and its idea goes first. No sale, no rule."""
    undated = SimpleNamespace(dived="", source_screen_date="", added="")
    assert shelf_mod.sold_since_dive(undated, date(2026, 7, 1)) is True
    assert shelf_mod.sold_since_dive(undated, None) is False


def test_d4_a_sold_stock_is_dived_though_managed_and_no_other_managed_one_is(tmp_path, monkeypatch):
    """A stock the autopilot bought stays in the managed list after its sale, and
    run_deep_dives skips a managed symbol. Budget 5, on Sat 4 Jul. SOLD is managed
    and sold: dived. HELD is managed, not sold, its dive 40 days old: due, but the
    skip holds, as for a stock still held. FREE is not managed: dived. Without the
    "sold" flag SOLD's re-dive was a silent no-op: the record named it and no
    analyst was called."""
    monkeypatch.setattr(settings, "DISCOVERY_DEEP_DIVE_COUNT", 5)
    monkeypatch.setattr(settings, "DISCOVERY_REDIVE_AFTER_DAYS", 30)
    monkeypatch.setattr(settings, "DISCOVERY_MIN_CONVICTION", 0.55)
    env = pr004._cycle_env(tmp_path, monkeypatch, screen=[],
                           window_symbols=["SOLD", "HELD", "FREE"], conviction={"SOLD": 0.7})
    monkeypatch.setattr(pr004.dd, "load_managed_tickers",
                        lambda: [{"sym": "SOLD", "enabled": True}, {"sym": "HELD", "enabled": True}])
    shelf_mod.ShelfStore().save(Shelf(ideas=[
        pr004._idea("SOLD", "2026-06-26"), pr004._idea("HELD", "2026-05-25"),
        pr004._idea("FREE", "2026-05-20")]))
    monkeypatch.setattr(disc, "autopilot_sales", lambda: {"SOLD": date(2026, 7, 1)})
    result = disc.run_discovery_cycle(on=date(2026, 7, 4))
    assert env["analyst"].calls == ["SOLD", "FREE"]
    assert result["hygiene"]["redive"] == ["SOLD", "FREE", "HELD"]
    assert result["hygiene"]["redive_sold"] == ["SOLD"]
    by = {i.symbol: i for i in shelf_mod.ShelfStore().load().ideas}
    assert (by["SOLD"].dived, by["SOLD"].conviction) == ("2026-07-04", 0.7)
    assert by["HELD"].dived == ""


@pytest.mark.parametrize("symbol, flags, called", [
    ("M", [], False),                   # managed: skipped
    ("M", ["redive"], False),           # "redive" does not pass the managed skip
    ("M", ["sold"], True),              # "sold" does
    ("S", [], False),                   # on the shelf: skipped
    ("S", ["sold"], False),             # "sold" does not pass the shelf's skip
    ("S", ["redive"], True),            # "redive" does
    ("B", ["sold"], False),             # managed and on the shelf: each flag alone falls short
    ("B", ["redive"], False),
    ("B", ["redive", "sold"], True),    # both pass both
])
def test_each_flag_passes_only_its_own_skip(tmp_path, monkeypatch, symbol, flags, called):
    monkeypatch.setattr(settings, "DISCOVERY_MIN_CONVICTION", 0.55)
    env = pr004._cycle_env(tmp_path, monkeypatch, screen=[], window_symbols=["M", "S", "B"])
    monkeypatch.setattr(pr004.dd, "load_managed_tickers", lambda: [
        {"sym": "M", "enabled": True}, {"sym": "B", "enabled": True}])
    shelf_mod.ShelfStore().save(Shelf(ideas=[pr004._idea("S", "2026-06-26"),
                                             pr004._idea("B", "2026-06-26")]))
    pr004.dd.run_deep_dives([pr004.cand(symbol, flags=flags)], on=date(2026, 7, 4),
                            listing=pr004.companies("M", "S", "B"))
    assert env["analyst"].calls == ([symbol] if called else [])


def test_d4_end_to_end_bought_sold_and_re_dived(tmp_path, monkeypatch):
    """Nothing faked between the buy and the dive but the analyst. The real
    executor buys BACK (dived Sat 4 Jul) and the real promotion makes it managed;
    the real executor exits it, and the real release takes it off the daily
    review (FIX-028); the real ledger reader finds the sale (stamped 13 Jul); the
    real cycle on Sat 18 Jul dives it, its dive only 14 days old, so only the
    sale makes it due."""
    from core.portfolio import promotion
    monkeypatch.setenv("ATLAS_ENABLED", "false")
    monkeypatch.setattr(settings, "PORTFOLIO_DATA_DIR", str(tmp_path / "pf"))
    monkeypatch.setattr(settings, "DISCOVERY_DEEP_DIVE_COUNT", 5)
    monkeypatch.setattr(settings, "DISCOVERY_REDIVE_AFTER_DAYS", 30)
    monkeypatch.setattr(settings, "DISCOVERY_MIN_CONVICTION", 0.55)
    env = pr004._cycle_env(tmp_path, monkeypatch, screen=[], window_symbols=["BACK"],
                           conviction={"BACK": 0.7})
    managed: list = []
    monkeypatch.setattr(promotion, "load_managed_tickers", lambda: managed)
    monkeypatch.setattr(promotion, "read_managed_tickers", lambda: managed)
    monkeypatch.setattr(promotion, "save_managed_tickers",
                        lambda tickers: managed.__setitem__(slice(None), tickers))
    monkeypatch.setattr(promotion, "resolve_company_name", lambda sym: sym)
    monkeypatch.setattr(ap, "promote_symbol", promotion.promote_symbol)
    monkeypatch.setattr(pr004.dd, "load_managed_tickers", lambda: managed)
    idea = story._idea("BACK", 1000.0, dived="2026-07-04")
    shelf_mod.ShelfStore().save(Shelf(ideas=[idea]))
    s = story._store(tmp_path, [], cash=1_200_000.0)
    story._prices(monkeypatch, {"BACK": 1000.0})
    bought, _ = story._run(s, [idea], {}, on=date(2026, 7, 8))
    assert _bought(bought) == [("BACK", 80.0)] and managed[0]["enabled"] is True
    sell = AdviceRecord(date="2026-07-09", user_id="u", symbol="BACK", verdict="EXIT", close=1000.0,
                        unrealised_pnl_pct=0.0, stop_pct=12.0, rationale_hash="x1")
    sold, _ = story._run(s, [idea], {"BACK": 1000.0}, on=date(2026, 7, 9), advice=[sell])
    assert [t.side for t in sold] == ["SELL"]
    assert (managed[0]["sym"], managed[0]["enabled"]) == ("BACK", False)
    result = disc.run_discovery_cycle(on=date(2026, 7, 18))
    assert env["analyst"].calls == ["BACK"]
    assert result["hygiene"]["redive_sold"] == ["BACK"]
    assert result["redived"]["refreshed"] == ["BACK"]
    assert shelf_mod.ShelfStore().load().ideas[0].dived == "2026-07-18"


# A stock sold after its idea left the shelf (owner, 6 Nov 2026). A dive is all
# that can bring a sold stock back; with no idea left there is no re-dive to wait
# for, so it takes its rank in the screen like any other stock.

def _returning_world(tmp_path, monkeypatch, *, screen, budget=5, conviction=None,
                     window_symbols=(), managed=("BACK",)):
    """The real ledger, portfolios, shelf and cycle; the analyst is faked."""
    monkeypatch.setenv("ATLAS_ENABLED", "false")
    monkeypatch.setattr(settings, "PORTFOLIO_DATA_DIR", str(tmp_path / "pf"))
    monkeypatch.setattr(settings, "DISCOVERY_DEEP_DIVE_COUNT", budget)
    monkeypatch.setattr(settings, "DISCOVERY_REDIVE_AFTER_DAYS", 30)
    monkeypatch.setattr(settings, "DISCOVERY_STALE_DAYS", 60)
    monkeypatch.setattr(settings, "DISCOVERY_MIN_CONVICTION", 0.55)
    env = pr004._cycle_env(tmp_path, monkeypatch, screen=screen, conviction=conviction,
                           window_symbols=window_symbols)
    monkeypatch.setattr(pr004.dd, "load_managed_tickers",
                        lambda: [{"sym": s, "enabled": True} for s in managed])
    return env


def test_returning_a_stock_held_past_its_ideas_60_days_can_come_back(tmp_path, monkeypatch):
    """Nothing faked from the first buy to the second but the analyst. ₹12 L.
    Dived Sat 1 Aug; the real promotion makes it managed when bought at Monday 3
    Aug's close, 80 shares at ₹1,000. On Sat 3 Oct its dive is 63 days old, past
    60, so the idea rotates out while the stock is held, and though the screen
    ranks BACK no analyst is called. The autopilot exits it on Wed 14 Oct and
    it leaves the daily review (FIX-028). On Sat 17 Oct there is no idea to re-dive and the screen
    ranks it: the analyst is called and 0.70 shelves it as a new idea dated 17
    Oct. Monday's run does not offer it (Friday's close is before the dive);
    Tuesday's real candidate list does, at Monday 19 Oct's close, 80 shares."""
    from core.portfolio import promotion
    stamp = {"now": "2026-08-04T11:00:00+00:00"}
    monkeypatch.setattr(ap, "_now_iso", lambda: stamp["now"])
    monkeypatch.setattr(ap, "_today_ist", lambda: date(2026, 10, 20))
    env = _returning_world(tmp_path, monkeypatch, screen=[pr004.cand("BACK", close=1000.0)],
                           conviction={"BACK": 0.70})
    managed: list = []
    monkeypatch.setattr(promotion, "load_managed_tickers", lambda: managed)
    monkeypatch.setattr(promotion, "read_managed_tickers", lambda: managed)
    monkeypatch.setattr(promotion, "save_managed_tickers",
                        lambda tickers: managed.__setitem__(slice(None), tickers))
    monkeypatch.setattr(promotion, "resolve_company_name", lambda sym: sym)
    monkeypatch.setattr(ap, "promote_symbol", promotion.promote_symbol)
    monkeypatch.setattr(pr004.dd, "load_managed_tickers", lambda: managed)
    idea = story._idea("BACK", 1000.0, dived="2026-08-01")
    shelf_mod.ShelfStore().save(Shelf(ideas=[idea]))
    s = story._store(tmp_path, [], cash=1_200_000.0)
    story._prices(monkeypatch, {"BACK": 1000.0})
    bought, _ = story._run(s, [idea], {}, on=date(2026, 8, 3))
    assert _bought(bought) == [("BACK", 80.0)]

    held = disc.run_discovery_cycle(on=date(2026, 10, 3))
    assert held["rotated_stale"] == ["BACK"]
    assert held["hygiene"]["sold_candidates"] == []
    assert env["analyst"].calls == []

    stamp["now"] = "2026-10-14T11:00:00+00:00"
    sell = AdviceRecord(date="2026-10-14", user_id="u", symbol="BACK", verdict="EXIT", close=1000.0,
                        unrealised_pnl_pct=0.0, stop_pct=12.0, rationale_hash="x1")
    sold, _ = story._run(s, [], {"BACK": 1000.0}, on=date(2026, 10, 14), advice=[sell])
    assert [t.side for t in sold] == ["SELL"]
    assert (managed[0]["sym"], managed[0]["enabled"]) == ("BACK", False)

    back = disc.run_discovery_cycle(on=date(2026, 10, 17))
    assert env["analyst"].calls == ["BACK"]
    assert back["hygiene"]["sold_candidates"] == ["BACK"]
    assert back["hygiene"]["redive_sold"] == []
    assert back["shelf"]["added"] == ["BACK"]
    active = [i for i in shelf_mod.ShelfStore().load().ideas if i.status == "active"]
    assert [(i.symbol, i.dived) for i in active] == [("BACK", "2026-10-17")]

    sectors = {m["sym"]: m["sector"] for m in managed}
    assert buy_candidates(s.load(), date(2026, 10, 16), active, managed=sectors)[0] == []
    offered, excluded = buy_candidates(s.load(), date(2026, 10, 19), active, managed=sectors)
    assert [(i.symbol, i.sector) for i in offered] == [("BACK", "pharma")] and excluded == {}
    stamp["now"] = "2026-10-20T11:00:00+00:00"
    again, _ = story._run(s, offered, {}, on=date(2026, 10, 19))
    assert _bought(again) == [("BACK", 80.0)]


def test_returning_no_dive_while_any_portfolio_still_holds_it(tmp_path, monkeypatch):
    """u sold BACK, v holds it, w never did. v's daily review speaks for it, so
    the screen's rank buys no analyst call on Sat 4 Jul. Once v holds nothing
    either, Sat 11 Jul's cycle calls the analyst."""
    env = _returning_world(tmp_path, monkeypatch, screen=[pr004.cand("BACK")])
    story._store(tmp_path, [], cash=100.0, name="u")
    v = story._store(tmp_path, [story._h("BACK", 10, 100.0, "pharma")], cash=100.0, name="v")
    story._store(tmp_path, [], cash=100.0, name="w")
    monkeypatch.setattr(disc, "autopilot_sales", lambda: {"BACK": date(2026, 7, 1)})
    result = disc.run_discovery_cycle(on=date(2026, 7, 4))
    assert (env["analyst"].calls, result["hygiene"]["sold_candidates"]) == ([], [])
    v.save(v.load().model_copy(update={"holdings": []}))
    result = disc.run_discovery_cycle(on=date(2026, 7, 11))
    assert (env["analyst"].calls, result["hygiene"]["sold_candidates"]) == (["BACK"], ["BACK"])


def test_returning_only_a_stock_the_autopilot_sold_passes_the_managed_skip(tmp_path, monkeypatch):
    """The real ledger reader, four managed stocks the screen ranks. HAND was sold
    by hand, TRIM keeps 5 shares and NEVER was never sold: no analyst call for
    any of them, though BACK, which the autopilot did sell, gets one in the same
    run. Alone, none of the three opens anything either."""
    names = ("HAND", "TRIM", "NEVER", "BACK")
    env = _returning_world(tmp_path, monkeypatch, managed=names,
                           screen=[pr004.cand(n) for n in names])
    s = story._store(tmp_path, [story._h("TRIM", 5, 100.0, "pharma")], cash=100.0)
    s.append_transaction(_sale("HAND", "2026-07-01", source="manual"))
    s.append_transaction(_sale("TRIM", "2026-07-01", left=5.0))
    s.append_transaction(_sale("BACK", "2026-07-01"))
    result = disc.run_discovery_cycle(on=date(2026, 7, 4))
    assert (env["analyst"].calls, result["hygiene"]["sold_candidates"]) == (["BACK"], ["BACK"])


def test_returning_a_hand_sale_or_a_trim_alone_opens_nothing(tmp_path, monkeypatch):
    """With no sale by the autopilot to return, the same stocks make no call."""
    env = _returning_world(tmp_path, monkeypatch, managed=("HAND", "TRIM"),
                           screen=[pr004.cand("HAND"), pr004.cand("TRIM")])
    s = story._store(tmp_path, [story._h("TRIM", 5, 100.0, "pharma")], cash=100.0)
    s.append_transaction(_sale("HAND", "2026-07-01", source="manual"))
    s.append_transaction(_sale("TRIM", "2026-07-01", left=5.0))
    result = disc.run_discovery_cycle(on=date(2026, 7, 4))
    assert (env["analyst"].calls, result["hygiene"]["sold_candidates"]) == ([], [])


def test_returning_a_known_answer_is_not_asked_again_within_the_month(tmp_path, monkeypatch):
    """Sold 1 Jul, no idea left. Sat 4 Jul's analysis says 0.50, below the 0.55
    floor: nothing is shelved. The dive memo keeps the answer for 30 days: Sat 11
    Jul and Sat 1 Aug (28 days on) make no call. Sat 8 Aug (35 days on) may ask
    again, as for any stock the screen still ranks: at most one call a month."""
    env = _returning_world(tmp_path, monkeypatch, screen=[pr004.cand("BACK")],
                           conviction={"BACK": 0.50})
    story._store(tmp_path, [], cash=100.0)
    monkeypatch.setattr(disc, "autopilot_sales", lambda: {"BACK": date(2026, 7, 1)})
    first = disc.run_discovery_cycle(on=date(2026, 7, 4))
    assert env["analyst"].calls == ["BACK"]
    assert first["shelf"]["added"] == []
    assert [i for i in shelf_mod.ShelfStore().load().ideas if i.status == "active"] == []
    second = disc.run_discovery_cycle(on=date(2026, 7, 11))
    assert second["hygiene"]["recently_dived"] == ["BACK"]
    assert second["hygiene"]["sold_candidates"] == []
    disc.run_discovery_cycle(on=date(2026, 8, 1))
    assert env["analyst"].calls == ["BACK"]
    disc.run_discovery_cycle(on=date(2026, 8, 8))
    assert env["analyst"].calls == ["BACK", "BACK"]


@pytest.mark.parametrize("budget, calls", [(3, ["SOLD", "AAA", "BACK"]), (2, ["SOLD", "AAA"])])
def test_returning_it_takes_its_rank_and_a_sold_idea_still_goes_first(tmp_path, monkeypatch, budget,
                                                                      calls):
    """The screen ranks AAA, BACK, CCC. BACK, sold with no idea left, keeps its
    second place and jumps no queue, so it can spend nothing the screen's ranks
    would not. SOLD, sold with its idea on the shelf, goes first, as before."""
    env = _returning_world(tmp_path, monkeypatch, budget=budget, managed=("BACK", "SOLD"),
                           screen=[pr004.cand("AAA"), pr004.cand("BACK"), pr004.cand("CCC")],
                           window_symbols=["SOLD"])
    story._store(tmp_path, [], cash=100.0)
    shelf_mod.ShelfStore().save(Shelf(ideas=[pr004._idea("SOLD", "2026-06-26")]))
    monkeypatch.setattr(disc, "autopilot_sales", lambda: {"BACK": date(2026, 7, 1),
                                                          "SOLD": date(2026, 7, 1)})
    disc.run_discovery_cycle(on=date(2026, 7, 4))
    assert env["analyst"].calls == calls


def test_returning_unread_holdings_keep_it_out_and_cost_nothing_else(tmp_path, monkeypatch):
    """With the holdings unread, whether BACK is held is unknown, so it gets no
    call and the run says why. SOLD's re-dive and the screen's FREE go on."""
    env = _returning_world(tmp_path, monkeypatch, managed=("BACK", "SOLD"),
                           screen=[pr004.cand("BACK"), pr004.cand("FREE")], window_symbols=["SOLD"])
    shelf_mod.ShelfStore().save(Shelf(ideas=[pr004._idea("SOLD", "2026-06-26")]))
    monkeypatch.setattr(disc, "autopilot_sales", lambda: {"BACK": date(2026, 7, 1),
                                                          "SOLD": date(2026, 7, 1)})
    monkeypatch.setattr(disc, "no_longer_held", lambda s: (_ for _ in ()).throw(OSError("disk")))
    result = disc.run_discovery_cycle(on=date(2026, 7, 4))
    assert env["analyst"].calls == ["SOLD", "FREE"]
    assert result["hygiene"]["sold_candidates"] == []
    assert "holdings unread, so no sold stock is dived as a new idea: disk" in result["errors"]


def test_no_longer_held_reads_each_portfolio_and_none_for_no_symbols(tmp_path, monkeypatch):
    monkeypatch.setenv("ATLAS_ENABLED", "false")
    monkeypatch.setattr(settings, "PORTFOLIO_DATA_DIR", str(tmp_path / "pf"))
    story._store(tmp_path, [story._h("AAA", 10, 100.0, "pharma")], cash=100.0, name="u")
    story._store(tmp_path, [story._h("BBB", 10, 100.0, "pharma")], cash=100.0, name="v")
    assert shelf_mod.no_longer_held({"AAA": 1, "BBB": 2, "CCC": 3}) == {"CCC"}
    import core.portfolio.store as store_mod
    monkeypatch.setattr(store_mod, "active_user_ids", lambda: (_ for _ in ()).throw(OSError("read")))
    assert shelf_mod.no_longer_held({}) == set()


def test_d4_an_idea_no_longer_active_and_re_dives_off(shelf, monkeypatch):
    on = date(2026, 7, 4)
    idea = pr004._idea("GONE", "2026-06-26").model_copy(update={"status": "dropped"})
    shelf.save(Shelf(ideas=[idea, pr004._idea("SOLD", "2026-06-26")]))
    sold = {"GONE": date(2026, 7, 1), "SOLD": date(2026, 7, 1)}
    assert [i.symbol for i in shelf.redive_due(on, sold)] == ["SOLD"]
    monkeypatch.setattr(settings, "DISCOVERY_REDIVE_AFTER_DAYS", 0)
    assert shelf.redive_due(on, sold) == []


def test_d4_the_budget_bound_holds_and_the_rest_wait_a_week(tmp_path, monkeypatch):
    """Budget 5, 2 IPO candidates: 3 slots. Due in order: SOLD1, SOLD2, PRE, STALE.
    The analyst gets exactly the three and the IPOs, 5 calls, and no screen
    candidate. STALE is deferred. SOLD2's re-dive falls below the BUY floor, so
    it leaves the shelf; SOLD1 is refreshed. Next week SOLD1's sale is older than
    its new dive, so it is not due again."""
    monkeypatch.setattr(settings, "DISCOVERY_DEEP_DIVE_COUNT", 5)
    monkeypatch.setattr(settings, "DISCOVERY_REDIVE_AFTER_DAYS", 30)
    monkeypatch.setattr(settings, "DISCOVERY_MIN_CONVICTION", 0.55)
    ipo = [pr004.cand("IPO0", close=300.0, flags=["ipo"]),
           pr004.cand("IPO1", close=300.0, flags=["ipo"])]
    env = pr004._cycle_env(tmp_path, monkeypatch, screen=[pr004.cand("SCR0")], ipo=ipo,
                           window_symbols=["SOLD1", "SOLD2", "PRE", "STALE"],
                           conviction={"SOLD1": 0.72, "SOLD2": 0.50})
    shelf_mod.ShelfStore().save(Shelf(ideas=[
        pr004._idea("STALE", "2026-05-20"), pr004._idea("PRE", "2026-06-01", gate=""),
        pr004._idea("SOLD1", "2026-06-26"), pr004._idea("SOLD2", "2026-06-27")]))
    sold = {"SOLD1": date(2026, 7, 1), "SOLD2": date(2026, 7, 1)}
    monkeypatch.setattr(disc, "autopilot_sales", lambda: sold)
    result = disc.run_discovery_cycle(on=date(2026, 7, 4))
    assert env["analyst"].calls == ["SOLD1", "SOLD2", "PRE", "IPO0", "IPO1"]
    assert result["hygiene"]["redive"] == ["SOLD1", "SOLD2", "PRE"]
    assert result["hygiene"]["redive_deferred"] == ["STALE"]
    assert result["hygiene"]["redive_sold"] == ["SOLD1", "SOLD2"]
    assert "SOLD1" in result["redived"]["refreshed"]
    assert result["redived"]["dropped"]["SOLD2"].startswith("re-dive 2026-07-04: conviction 0.50")
    by = {i.symbol: i for i in shelf_mod.ShelfStore().load().ideas}
    assert (by["SOLD1"].status, by["SOLD1"].dived, by["SOLD2"].status) == \
        ("active", "2026-07-04", "dropped")
    assert "SOLD1" not in [i.symbol for i in shelf_mod.ShelfStore().redive_due(date(2026, 7, 11), sold)]


def test_d4_an_unread_ledger_costs_only_the_priority(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DISCOVERY_DEEP_DIVE_COUNT", 5)
    monkeypatch.setattr(settings, "DISCOVERY_REDIVE_AFTER_DAYS", 30)
    pr004._cycle_env(tmp_path, monkeypatch, screen=[], window_symbols=["STALE"])
    shelf_mod.ShelfStore().save(Shelf(ideas=[pr004._idea("STALE", "2026-05-20")]))
    monkeypatch.setattr(disc, "autopilot_sales",
                        lambda: (_ for _ in ()).throw(OSError("disk")))
    result = disc.run_discovery_cycle(on=date(2026, 7, 4))
    assert result["hygiene"]["redive"] == ["STALE"]
    assert "autopilot sales unread: disk" in result["errors"]


def test_autopilot_sales_counts_only_the_autopilots_exits_in_every_portfolio(tmp_path, monkeypatch):
    """u exits EXITED on 1 Jul and v on 3 Jul: the later counts. MANUAL was sold
    by hand and TRIMMED still has shares: neither says the idea's case failed.
    A BUY is no sale."""
    monkeypatch.setenv("ATLAS_ENABLED", "false")
    monkeypatch.setattr(settings, "PORTFOLIO_DATA_DIR", str(tmp_path / "pf"))
    u = story.PortfolioStore(user_id="u", base_dir=str(tmp_path / "pf"))
    v = story.PortfolioStore(user_id="v", base_dir=str(tmp_path / "pf"))
    for s in (u, v):
        s.save(s.load())
    u.append_transaction(_sale("EXITED", "2026-07-01"))
    v.append_transaction(_sale("EXITED", "2026-07-03"))
    u.append_transaction(_sale("MANUAL", "2026-07-01", source="manual"))
    u.append_transaction(_sale("TRIMMED", "2026-07-01", left=5.0))
    u.append_transaction(_past_buy("2026-07-02"))
    assert shelf_mod.autopilot_sales() == {"EXITED": date(2026, 7, 3)}


THU, FRI, SAT = date(2026, 10, 29), date(2026, 10, 30), date(2026, 10, 31)
MON, TUE = date(2026, 11, 2), date(2026, 11, 3)


def test_a_sale_counts_from_the_day_it_was_decided_not_the_session_it_was_booked_at(tmp_path,
                                                                                    monkeypatch):
    """Monday 2 Nov's 16:30 run reviews Friday and books an exit at Friday's
    close, so the row is dated 30 Oct and stamped 2 Nov. Saturday's dive could
    not have known of it. Read by the date alone, Tuesday's run would buy the
    stock back at Monday's close, a day-old round trip on an analysis older than
    the sale. So it waits for a new dive, and that dive is due the next Saturday."""
    monkeypatch.setattr(ap, "_today_ist", lambda: TUE)
    s = story._store(tmp_path, [], cash=1_200_000.0)
    s.append_transaction(_sale("BACK", FRI.isoformat(), ts="2026-11-02T11:00:00+00:00"))
    idea = story._idea("BACK", 1000.0, dived=SAT.isoformat())
    story._prices(monkeypatch, {"BACK": 1000.0})
    txns, rec = story._run(s, [idea], {}, on=MON)
    assert txns == []
    assert story._outcomes(rec)["BACK"] == (
        "sold", "sold on 2026-11-02, after its deep dive of 2026-10-31; waits for a new deep dive")
    assert shelf_mod.sold_since_dive(idea, shelf_mod.sale_day(s.load_transactions()[0]))


@pytest.mark.parametrize("ts, source, day", [
    ("2026-11-02T11:00:00+00:00", "autopilot", MON),         # 16:30 IST on 2 Nov
    ("2026-11-02T20:00:00+00:00", "autopilot", TUE),         # 01:30 IST on 3 Nov
    ("2026-11-02T11:00:00+00:00", "manual", FRI),            # an import keeps its date
    ("2026-10-30T11:00:00+00:00", "autopilot", FRI),         # booked and decided the same day
    ("not a time", "autopilot", FRI),
    ("2026-11-02T11:00:00", "autopilot", FRI),               # no zone: not trusted
])
def test_sale_day(ts, source, day):
    assert shelf_mod.sale_day(_sale("X", FRI.isoformat(), ts=ts, source=source)) == day


def test_a_sale_the_user_imported_late_does_not_hold_up_a_later_dive(tmp_path, monkeypatch):
    """A SELL of 30 Oct imported on 2 Nov, dive of Sat 31 Oct: the dive came after
    the sale, so the idea may be bought."""
    monkeypatch.setattr(ap, "_today_ist", lambda: TUE)
    s = story._store(tmp_path, [], cash=1_200_000.0)
    s.append_transaction(_sale("BACK", FRI.isoformat(), ts="2026-11-02T11:00:00+00:00",
                               source="manual"))
    story._prices(monkeypatch, {"BACK": 1000.0})
    txns, _ = story._run(s, [story._idea("BACK", 1000.0, dived=SAT.isoformat())], {}, on=MON)
    assert _bought(txns) == [("BACK", 80.0)]


def test_d4_sold_re_analysed_then_bought_by_the_first_run_that_may_use_it(shelf, tmp_path,
                                                                          monkeypatch):
    """Dived 24 Oct, sold 27 Oct (₹12 L cash). Sat 31 Oct's re-dive is still a BUY
    at ₹1,000. Monday's run reviews Friday: not offered, the dive is after that
    close. Tuesday's run reviews Monday: offered and bought at Monday's close,
    80 shares, dated Monday: the sale is older than the new dive."""
    monkeypatch.setattr(ap, "_today_ist", lambda: TUE)
    s = story._store(tmp_path, [], cash=1_200_000.0)
    s.append_transaction(_sale("BACK", "2026-10-27"))
    sold = shelf_mod.ledger_sales(s.load_transactions()).last
    shelf.save(Shelf(ideas=[pr004._idea("BACK", "2026-10-24")]))
    assert [i.symbol for i in shelf.redive_due(SAT, sold)] == ["BACK"]
    out = shelf.apply_redives([pr004.dive("BACK", 0.70, on=SAT.isoformat(), close=1000.0)], on=SAT)
    assert out["refreshed"] == ["BACK"]
    assert shelf.redive_due(date(2026, 11, 7), sold) == []
    ideas = [i for i in shelf.load().ideas if i.status == "active"]
    portfolio = SimpleNamespace(holdings=[], watchlist=[])
    offered, excluded = buy_candidates(portfolio, FRI, ideas, managed={})
    assert offered == [] and excluded["BACK"].startswith("close of 2026-10-30 is before")
    offered, excluded = buy_candidates(portfolio, MON, ideas, managed={})
    assert [i.symbol for i in offered] == ["BACK"] and excluded == {}
    story._prices(monkeypatch, {"BACK": 1000.0})
    txns, _ = story._run(s, offered, {}, on=MON)
    assert [(t.date, t.symbol, t.qty, t.price) for t in txns] == \
        [("2026-11-02", "BACK", 80.0, 1000.0)]


def test_d4_churn_is_at_most_one_round_trip_a_week(tmp_path, monkeypatch):
    """The worst case the card asks about, with the exit forced each time: bought
    on a Tuesday's run, sold on the Wednesday's. Every run until the next dive
    refuses a buy back, whatever the price; the next Saturday's dive frees one
    buy on the next Tuesday's run. Over 3 weeks: 3 buys and 3 sales, each paying
    its charges on its own ledger row."""
    monkeypatch.setattr(settings, "PORTFOLIO_COSTS", story.CONFIGURED_COSTS)
    s = story._store(tmp_path, [], cash=1_200_000.0)
    story._prices(monkeypatch, {"BACK": 1000.0})
    stamp = {"now": ""}
    monkeypatch.setattr(ap, "_now_iso", lambda: stamp["now"])
    dive = date(2026, 10, 31)
    trips = 0
    for week in range(3):
        idea = story._idea("BACK", 1000.0, dived=dive.isoformat())
        monday, tuesday = dive + timedelta(days=2), dive + timedelta(days=3)
        wednesday, friday = dive + timedelta(days=4), dive + timedelta(days=6)
        monkeypatch.setattr(ap, "_today_ist", lambda d=friday: d)
        stamp["now"] = f"{tuesday}T11:00:00+00:00"          # Tuesday's run reviews Monday
        txns, _ = story._run(s, [idea], {}, on=monday)
        assert _bought(txns), week
        sell = AdviceRecord(date=tuesday.isoformat(), user_id="u", symbol="BACK", verdict="EXIT",
                            close=1000.0, unrealised_pnl_pct=0.0, stop_pct=12.0,
                            rationale_hash=f"x{week}")
        stamp["now"] = f"{wednesday}T11:00:00+00:00"        # Wednesday's run reviews Tuesday
        txns, _ = story._run(s, [idea], {"BACK": 1000.0}, on=tuesday, advice=[sell])
        assert [t.side for t in txns] == ["SELL"], week
        trips += 1
        for review in (wednesday, friday):
            stamp["now"] = f"{review + timedelta(days=1)}T11:00:00+00:00"
            txns, rec = story._run(s, [idea], {}, on=review)
            assert txns == [] and story._outcomes(rec)["BACK"][0] == "sold", (week, review)
        dive += timedelta(days=7)
    ledger = s.load_transactions()
    assert trips == 3
    assert [t.side for t in ledger] == ["BUY", "SELL"] * 3
    assert all(t.costs is not None and t.costs.total > 0 for t in ledger)
