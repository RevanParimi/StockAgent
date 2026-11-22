"""PR-037 — enough analysed ideas to hold 25 to 30 stocks: invariant tests.

The shipped values are read from config.yaml with a YAML parser (not through
the settings module) and every expected call list is worked out by hand from
the fixture: who is due, who is held, what the screen offers. The property
test checks statements the card makes, against eligibility the fixture
decides when it builds each symbol, never against the code's own split:

- the week's analyst calls never pass the budget, and no symbol is called twice;
- new companies get the floor whenever the screen offers that many;
- re-dives get their room (calls less IPO candidates less the floor);
- no call is left unused while an eligible candidate waits;
- every due re-dive is reported once: offered first, late, or deferred;
- no sector key holds more than its cap, the shelf no more than its size;
- an idea reaches the shelf only from its own dive, a BUY at or above 0.55;
- a re-dive that turns a stock down removes it.

The analyst is a stub, transports are faked or blocked by tests/hermetic.py,
and each run has its own sandbox directory.
"""
from __future__ import annotations

import json
import random
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

import pytest
import yaml

import core.discovery as disc
import core.discovery.deep_dive as dd
import core.discovery.shelf as shelf_mod
import tests.unit.test_idea_supply_pr004 as pr004
from backend.shared.schemas.discovery import Shelf
from core.config import settings
from tests.unit.test_idea_supply_pr004 import dive_env  # noqa: F401 — fixture

ON = date(2026, 7, 4)                     # a Saturday; the window ends Fri 3 Jul
CONFIG = Path(__file__).resolve().parents[2] / "config.yaml"


def shipped() -> dict:
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8"))["discovery"]


def use_shipped(monkeypatch):
    """The shipped discovery values, read from config.yaml, over whatever a
    fixture set (pr004._cycle_env turns the floor off for PR-004's tests)."""
    d = shipped()
    for name, key in [("DISCOVERY_DEEP_DIVE_COUNT", "deep_dive_count"),
                      ("DISCOVERY_NEW_DIVE_FLOOR", "new_dive_floor"),
                      ("DISCOVERY_SHELF_SIZE", "shelf_size"),
                      ("DISCOVERY_MAX_IDEAS_PER_SECTOR", "max_ideas_per_sector"),
                      ("DISCOVERY_IPO_MAX_DEEP_DIVES", "ipo_max_deep_dives"),
                      ("DISCOVERY_REDIVE_AFTER_DAYS", "redive_after_days"),
                      ("DISCOVERY_STALE_DAYS", "stale_days"),
                      ("DISCOVERY_MIN_CONVICTION", "min_conviction")]:
        monkeypatch.setattr(settings, name, d[key])


def days_ago(n: int) -> str:
    return (ON - timedelta(days=n)).isoformat()


def ideas(prefix: str, ages, start: int = 0, **kw):
    """One idea per age (days since its dive), sectors in turn over eight."""
    return [pr004._idea(f"{prefix}{k:02d}", days_ago(age),
                        sector=pr004.SECTORS8[(start + k) % 8], **kw)
            for k, age in enumerate(ages)]


def screen(n: int, prefix: str = "S"):
    return [pr004.cand(f"{prefix}{k:02d}") for k in range(n)]


IPO = [pr004.cand("IPO0", close=300.0, flags=["ipo"]),
       pr004.cand("IPO1", close=300.0, flags=["ipo"])]


def cycle_env(tmp_path, monkeypatch, *, shelf_ideas, scr, ipo=IPO, sold=None, held=(),
              **kw):
    env = pr004._cycle_env(tmp_path, monkeypatch, screen=scr, ipo=ipo,
                           window_symbols=[i.symbol for i in shelf_ideas], **kw)
    use_shipped(monkeypatch)
    monkeypatch.setattr(disc, "autopilot_sales", lambda: dict(sold or {}))
    monkeypatch.setattr(disc, "no_longer_held", lambda s: set())
    monkeypatch.setattr(dd, "load_managed_tickers",
                        lambda: [{"sym": s, "enabled": True} for s in held])
    shelf_mod.ShelfStore().save(Shelf(ideas=list(shelf_ideas)))
    return env


# ---------------------------------------------------------------------------
# The shipped values and the split
# ---------------------------------------------------------------------------

def test_the_shipped_values():
    d = shipped()
    assert (d["shortlist_size"], d["max_candidates"], d["deep_dive_count"],
            d["new_dive_floor"], d["shelf_size"], d["max_ideas_per_sector"]) == \
        (120, 60, 45, 15, 45, 6)
    assert d["min_conviction"] == 0.55               # the bar does not move
    assert d["ipo_max_deep_dives"] == 2
    assert d["redive_after_days"] == 30


def test_the_split_of_45_calls(monkeypatch):
    use_shipped(monkeypatch)
    # 45 - 2 IPO candidates - 15 for new companies = 28 re-dives ahead of them.
    assert disc.budget_split(2) == {"calls": 45, "ipo": 2, "new_floor": 15, "redive_room": 28}
    assert disc.budget_split(0)["redive_room"] == 30
    monkeypatch.setattr(settings, "DISCOVERY_DEEP_DIVE_COUNT", 10)
    assert disc.budget_split(2)["redive_room"] == 0  # never below 0


# ---------------------------------------------------------------------------
# The card's Saturdays, end to end
# ---------------------------------------------------------------------------

def test_the_cards_saturday(tmp_path, monkeypatch):
    """45 ideas, 12 older than 30 days, 1 sold since its dive: 13 re-dives,
    the 2 IPO slots, 30 new companies from the screen's ranks: 45 calls."""
    fresh = ideas("F", [2 + k % 26 for k in range(32)])
    stale = ideas("T", [31 + k for k in range(12)], start=32)          # 31..42 days
    sold = pr004._idea("SOLD", days_ago(10), sector="Energy")
    env = cycle_env(tmp_path, monkeypatch, shelf_ideas=fresh + stale + [sold], scr=screen(50),
                    sold={"SOLD": ON - timedelta(days=2)})
    result = disc.run_discovery_cycle(on=ON)
    oldest_first = [i.symbol for i in reversed(stale)]                   # 42 days first
    assert env["analyst"].calls == (["SOLD"] + oldest_first + ["IPO0", "IPO1"]
                                    + [f"S{k:02d}" for k in range(30)])
    assert result["hygiene"]["redive"] == ["SOLD"] + oldest_first
    assert (result["hygiene"]["redive_late"], result["hygiene"]["redive_deferred"]) == ([], [])
    assert result["budget"] == {"calls": 45, "ipo": 2, "new_floor": 15, "redive_room": 28,
                                "made": 45, "redive_calls": 13}


def _heavy_shelf():
    """35 ideas due: 5 never gated (5-9 days), 30 older than 30 days (31-60),
    and 10 fresh ones: 45 ideas."""
    unverified = ideas("U", [5 + k for k in range(5)], gate="")
    stale = ideas("T", [31 + k for k in range(30)], start=5)
    fresh = ideas("F", [1 + k for k in range(10)], start=3)
    due = [i.symbol for i in reversed(unverified)] + [i.symbol for i in reversed(stale)]
    return unverified + stale + fresh, due


def test_a_heavy_week_defers_seven_and_they_go_first_the_next(tmp_path, monkeypatch):
    """35 due, 2 IPO candidates, 50 new companies: 28 re-dives, the IPOs and
    the 15 the floor keeps. The 7 least overdue (31-37 days) are deferred and
    named; a week later they are the first re-dives, oldest first."""
    shelf_ideas, due = _heavy_shelf()
    env = cycle_env(tmp_path, monkeypatch, shelf_ideas=shelf_ideas, scr=screen(50))
    first = disc.run_discovery_cycle(on=ON)
    assert env["analyst"].calls == due[:28] + ["IPO0", "IPO1"] + [f"S{k:02d}" for k in range(15)]
    assert first["hygiene"]["redive"] == due[:28]
    assert first["hygiene"]["redive_deferred"] == due[28:] == [f"T{k:02d}" for k in range(6, -1, -1)]
    assert first["budget"]["made"] == 45
    # Deferred ideas keep their old dive, so nothing buys them until re-dived.
    by = {i.symbol: i for i in shelf_mod.ShelfStore().load().ideas}
    assert all(by[s].status == "active" and not by[s].dived for s in due[28:])

    env["analyst"].calls.clear()
    second = disc.run_discovery_cycle(on=ON + timedelta(days=7))
    assert second["hygiene"]["redive"][:7] == due[28:]
    assert env["analyst"].calls[:7] == due[28:]
    assert second["hygiene"]["redive_deferred"] == []


def test_when_the_screen_runs_short_the_deferred_take_what_is_left(tmp_path, monkeypatch):
    """The same 35 due but only 5 new companies: 28 + 2 + 5 calls, then the 7
    behind the floor take 7 of the 10 calls left."""
    shelf_ideas, due = _heavy_shelf()
    env = cycle_env(tmp_path, monkeypatch, shelf_ideas=shelf_ideas, scr=screen(5))
    result = disc.run_discovery_cycle(on=ON)
    assert env["analyst"].calls == (due[:28] + ["IPO0", "IPO1"]
                                    + [f"S{k:02d}" for k in range(5)] + due[28:])
    assert (result["hygiene"]["redive_late"], result["hygiene"]["redive_deferred"]) == \
        (due[28:], [])
    assert (result["budget"]["made"], result["budget"]["redive_calls"]) == (42, 35)
    assert sorted(result["redived"]["refreshed"]) == sorted(due)


def test_a_held_stocks_idea_takes_no_room(tmp_path, monkeypatch):
    """30 shelf ideas whose stocks are held (managed, not sold: no re-dive,
    FIX-025) are due first, oldest, then 10 more. The held ones make no call,
    so they leave the room to the 10: 10 re-dives, 2 IPOs, 33 new companies.
    Counted by position instead of calls, the 10 would wait behind the screen."""
    held = ideas("H", [31 + k for k in range(30)])
    free = ideas("R", [31 + k for k in range(10)], start=4)
    env = cycle_env(tmp_path, monkeypatch, shelf_ideas=held + free, scr=screen(50),
                    held=[i.symbol for i in held])
    result = disc.run_discovery_cycle(on=ON)
    calls = env["analyst"].calls
    assert sorted(calls[:10]) == sorted(i.symbol for i in free)
    assert calls[10:] == ["IPO0", "IPO1"] + [f"S{k:02d}" for k in range(33)]
    assert not set(calls) & {i.symbol for i in held}
    assert (result["hygiene"]["redive_late"], result["hygiene"]["redive_deferred"]) == ([], [])


# ---------------------------------------------------------------------------
# run_deep_dives' room, directly
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("budget, calls, late, deferred", [
    (4, ["A", "B", "X", "Y"], [], ["C"]),
    (6, ["A", "B", "X", "Y", "C"], ["C"], []),
    (2, ["A", "B"], [], ["C"]),
])
def test_the_room_counts_calls_and_holds_the_rest_back(dive_env, budget, calls, late,  # noqa: F811
                                                       deferred):
    """The docstring's example: room 2, re-dives A, B, C, then screen ranks
    X, Y. H, a held stock's idea, and N, a re-dive without a close, are
    skipped and take no room."""
    dive_env["managed"] = ["H"]
    dive_env["window"] = pr004._eod_window(["A", "B", "C", "H", "X", "Y"], days=3)
    redive = lambda s: pr004.cand(s, close=0.0, flags=["redive"])      # noqa: E731
    tally: dict = {}
    dd.run_deep_dives([redive("H"), redive("N"), redive("A"), redive("B"), redive("C"),
                       pr004.cand("X"), pr004.cand("Y")], on=ON, max_n=budget,
                      listing=pr004.companies("A", "B", "C", "H", "N", "X", "Y"),
                      redive_room=2, tally=tally)
    assert dive_env["analyst"].calls == calls
    assert tally == {"calls": len(calls), "redive_calls": len([c for c in calls if c in "ABC"]),
                     "late": late, "deferred": deferred, "other_company": {}}


def test_without_a_room_the_order_is_todays(dive_env):  # noqa: F811
    dive_env["window"] = pr004._eod_window(["A", "B", "X"], days=3)
    dd.run_deep_dives([pr004.cand("A", flags=["redive"]), pr004.cand("B", flags=["redive"]),
                       pr004.cand("X")], on=ON, max_n=2, listing=pr004.companies("A", "B", "X"))
    assert dive_env["analyst"].calls == ["A", "B"]


# ---------------------------------------------------------------------------
# The property
# ---------------------------------------------------------------------------

class VerdictAnalyst(pr004.Analyst):
    """pr004's stub analyst with a verdict per symbol (default BUY)."""

    def __init__(self, *a, verdict=None, **kw):
        super().__init__(*a, **kw)
        self.verdict = dict(verdict or {})

    def orchestrator(self, sector):
        inner, analyst = super().orchestrator(sector), self

        class _O:
            def analyse(self, symbol, sector_question=None, exact_symbol=False):
                out = inner.analyse(symbol, sector_question=sector_question)
                out.verdict = analyst.verdict.get(symbol, "BUY")
                return out
        return _O()


def test_property_the_split_and_the_shelf(tmp_path, monkeypatch):
    rng = random.Random(3037)
    for trial in range(120):
        root = tmp_path / f"t{trial}"
        budget, floor = rng.randint(0, 50), rng.randint(0, 20)
        n_ipo = rng.randint(0, 2)
        # Shelf ideas: fresh, older than 30 days, never gated, sold, held,
        # without a close. Eight sectors in turn keep each key at 6 or fewer.
        shelf_ideas, sold, held, no_close = [], {}, set(), set()
        for k in range(rng.randint(0, 45)):
            kind = rng.choice(["fresh", "fresh", "stale", "stale", "pre", "sold", "held",
                               "noclose"])
            age = rng.randint(31, 60) if kind in ("stale", "held", "noclose") else rng.randint(1, 29)
            sym = f"I{k:02d}"
            shelf_ideas.append(pr004._idea(sym, days_ago(age), sector=pr004.SECTORS8[k % 8],
                                           gate="" if kind == "pre" else "actionable"))
            if kind == "sold":
                sold[sym] = ON - timedelta(days=rng.randint(0, age))
            held |= {sym} if kind == "held" else set()
            no_close |= {sym} if kind == "noclose" else set()
        # The screen: companies and funds, managed ones, ones dived this month.
        scr, funds, recent = [], set(), set()
        for k in range(rng.randint(0, 70)):
            sym = f"S{k:02d}"
            scr.append(pr004.cand(sym))
            funds |= {sym} if rng.random() < 0.1 else set()
            held |= {sym} if rng.random() < 0.1 else set()
            recent |= {sym} if rng.random() < 0.1 else set()
        ipo = IPO[:n_ipo]
        sector_of = {c.symbol: pr004.SECTORS8[k % 8] for k, c in enumerate(scr + ipo)}
        for i in shelf_ideas:
            sector_of[i.symbol] = i.market_sector
        listing = pr004.companies(*[i.symbol for i in shelf_ideas], *[c.symbol for c in scr + ipo])
        for sym in funds:
            listing[sym] = {"series": "EQ", "isin": "INF000000001"}
        env = pr004._cycle_env(root, monkeypatch, screen=scr, ipo=ipo, listing=listing,
                               sector_of=sector_of,
                               window_symbols=[i.symbol for i in shelf_ideas
                                               if i.symbol not in no_close])
        use_shipped(monkeypatch)
        monkeypatch.setattr(settings, "DISCOVERY_DEEP_DIVE_COUNT", budget)
        monkeypatch.setattr(settings, "DISCOVERY_NEW_DIVE_FLOOR", floor)
        monkeypatch.setattr(disc, "autopilot_sales", lambda _s=dict(sold): _s)
        monkeypatch.setattr(disc, "no_longer_held", lambda s: set())
        monkeypatch.setattr(dd, "load_managed_tickers",
                            lambda _h=sorted(held): [{"sym": s, "enabled": True} for s in _h])
        everyone = [i.symbol for i in shelf_ideas] + [c.symbol for c in scr + ipo]
        analyst = VerdictAnalyst(
            conviction={s: round(rng.uniform(0.4, 0.95), 2) for s in everyone},
            verdict={s: rng.choice(["BUY"] * 5 + ["STRONG BUY", "HOLD", "SELL"])
                     for s in everyone},
            fail={s for s in everyone if rng.random() < 0.08},
            key_of={s: pr004.key_for(sec) for s, sec in sector_of.items()})
        monkeypatch.setattr(dd, "get_orchestrator", analyst.orchestrator)
        store = shelf_mod.ShelfStore()
        store.save(Shelf(ideas=shelf_ideas))
        memo = {s: {"date": days_ago(rng.randint(1, 29)), "conviction": 0.5, "verdict": "HOLD",
                    "data_gate": "actionable"} for s in recent}
        (root / "disc" / "dives.json").write_text(json.dumps(memo), encoding="utf-8")
        due = [i.symbol for i in store.redive_due(ON, sold)]
        before = {i.symbol for i in shelf_ideas}

        result = disc.run_discovery_cycle(on=ON)
        calls, hyg = analyst.calls, result["hygiene"]
        msg = (trial, budget, floor, n_ipo)

        # The fixture's own eligibility, decided as each symbol was built.
        due_ok = [s for s in due if s not in no_close and (s not in held or s in sold)]
        ipo_ok = [c.symbol for c in ipo]
        new_ok = [c.symbol for c in scr if c.symbol not in funds | held | recent]
        room = max(0, budget - n_ipo - floor)
        redive_calls = [s for s in calls if s in due]
        new_calls = [s for s in calls if s.startswith("S")]
        ipo_calls = [s for s in calls if s.startswith("IPO")]

        assert len(calls) <= budget and len(calls) == len(set(calls)), msg
        assert set(calls) <= set(due_ok) | set(ipo_ok) | set(new_ok), msg
        assert len(new_calls) >= min(floor, len(new_ok), budget - len(ipo_calls)), msg
        assert len(redive_calls) >= min(len(due_ok), room), msg
        if len(calls) < budget:
            assert set(calls) == set(due_ok) | set(ipo_ok) | set(new_ok), msg
        # Re-dives ahead of a new company never pass the room; one past the
        # room is called only once every eligible new company and IPO was.
        last_new = max((k for k, s in enumerate(calls) if s.startswith("S")), default=0)
        assert len([s for s in calls[:last_new] if s in due]) <= room, msg
        if len(redive_calls) > room:
            assert set(new_ok) | set(ipo_ok) <= set(calls), msg
        # Every due re-dive reported once, in its order; a deferred one had no call.
        reported = hyg["redive"] + hyg["redive_late"] + hyg["redive_deferred"]
        assert sorted(reported) == sorted(due), msg
        for part in (hyg["redive"], hyg["redive_late"], hyg["redive_deferred"]):
            assert part == [s for s in due if s in part], msg
        assert not set(hyg["redive_deferred"]) & set(calls), msg
        assert set(hyg["redive_late"]) <= set(calls), msg
        assert not hyg["redive_deferred"] or len(calls) == budget, msg

        # The shelf at the shipped size and cap.
        on_shelf = [i for i in store.load().ideas if i.status == "active"]
        assert len(on_shelf) <= 45, msg
        keys = Counter(shelf_mod.cap_key(i) for i in on_shelf)
        keys.pop("", None)
        assert max(keys.values(), default=0) <= 6, msg
        answered = {s for s in calls if s not in analyst.fail}
        for i in on_shelf:
            if i.symbol not in before:          # a new idea: its own dive, a BUY >= 0.55
                assert i.symbol in answered and i.added == ON.isoformat(), (msg, i.symbol)
                assert analyst.verdict[i.symbol] in ("BUY", "STRONG BUY"), (msg, i.symbol)
                assert analyst.conviction[i.symbol] >= 0.55, (msg, i.symbol)
        turned_down = {s for s in due if s in answered
                       and (analyst.verdict[s] not in ("BUY", "STRONG BUY")
                            or analyst.conviction[s] < 0.55)}
        assert not turned_down & {i.symbol for i in on_shelf}, msg
