"""PR-004 — enough researched ideas to fill 10+ positions: invariant tests.

Expected results are worked out by hand in the comments or by an oracle
that does not share code with the implementation:

- the characterization oracle is HEAD 25fae38's `ShelfStore.apply_deep_dives`,
  transcribed below as a pure function;
- the single-batch shelf oracle is "the 20 strongest of the 3 strongest per
  sector", computed by sorting;
- the multi-week end state is checked by its optimality condition: no idea
  left off the shelf could replace one on it without breaking the cap.

The analyst is a stub, every transport is a fake or blocked by
tests/hermetic.py, and each test runs in its own sandbox directory.
"""
from __future__ import annotations

import json
import random
from collections import Counter
from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pandas as pd
import pytest

import core.discovery as disc
import core.discovery.deep_dive as dd
import core.discovery.shelf as shelf_mod
import services.data.fetchers.bhavcopy as bhav
from backend.shared.schemas.audit import AuditOutcome
from backend.shared.schemas.discovery import (
    DeepDiveResult, DiscoveryCandidate, ScreenResult, Shelf, ShelfIdea,
)
from backend.shared.schemas.portfolio import Holding, WatchlistItem
from core.config import settings
from core.discovery import candidates as cands_mod
from core.discovery.universe import (
    COMPANY, FUND, OTHER, TRUST, UNKNOWN, companies_only, instrument_kind,
)
from core.portfolio import results as R
from tests.unit.shared.test_decision_gate_sa003 import gate_mode  # noqa: F401 — fixture

# Listing rows as NSE's UDiFF bhavcopy of 16 Oct 2026 printed them (probe in
# analysis_data/pr004/udiff_probe.py): series and ISIN only.
REAL_ROWS = {
    "AUROPHARMA": {"series": "EQ", "isin": "INE406A01037"},
    "MARKSANS": {"series": "EQ", "isin": "INE750C01026"},
    "LIQUID1": {"series": "EQ", "isin": "INF174KA1LV5"},     # Kotak liquid ETF
    "CASHIETF": {"series": "EQ", "isin": "INF109K1A021"},    # ICICI liquid ETF
    "GOLDBEES": {"series": "EQ", "isin": "INF204KB17I5"},
    "EMBASSY": {"series": "RR", "isin": "INE041025011"},     # REIT
    "INDIGRID": {"series": "IV", "isin": "INE219X23014"},    # InvIT
    "GSEC2030": {"series": "GS", "isin": "IN0020200070"},
}


def companies(*symbols):
    return {s: {"series": "EQ", "isin": f"INE{i:06d}01X"} for i, s in enumerate(symbols)}


def dive(symbol, conviction, sector="", on="2026-07-04", gate="actionable", close=100.0):
    return DeepDiveResult(symbol=symbol, sector="generic", graph="generic",
                          conviction=conviction, verdict="BUY", thesis=f"t {symbol}",
                          entry_low=round(close * 0.97, 2), entry_high=round(close * 1.02, 2),
                          invalidation_level=round(close * 0.88, 2), close=close,
                          composite=0.5, dive_date=on, data_gate=gate,
                          market_sector=sector, industry=f"{sector} industry" if sector else "")


@pytest.fixture
def shelf(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DISCOVERY_DATA_DIR", str(tmp_path / "disc"))
    monkeypatch.setattr(settings, "DISCOVERY_SHELF_SIZE", 20)
    monkeypatch.setattr(settings, "DISCOVERY_MAX_IDEAS_PER_SECTOR", 3)
    monkeypatch.setattr(settings, "DISCOVERY_REDIVE_AFTER_DAYS", 30)
    monkeypatch.setattr(settings, "DISCOVERY_STALE_DAYS", 60)
    monkeypatch.setattr(settings, "DISCOVERY_MIN_CONVICTION", 0.55)
    return shelf_mod.ShelfStore()


def active(store):
    return [i for i in store.load().ideas if i.status == "active"]


def events(tmp_path):
    path = tmp_path / "disc" / "shelf_events.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


# ---------------------------------------------------------------------------
# Only companies: the instrument rule
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("symbol, kind", [
    ("AUROPHARMA", COMPANY), ("MARKSANS", COMPANY),
    ("LIQUID1", FUND), ("CASHIETF", FUND), ("GOLDBEES", FUND),
    ("EMBASSY", TRUST), ("INDIGRID", TRUST),
    ("GSEC2030", OTHER), ("NOTLISTED", UNKNOWN),
])
def test_instrument_kind_from_series_and_isin(symbol, kind):
    assert instrument_kind(symbol, REAL_ROWS) == kind


def test_no_listing_knows_nothing_and_names_never_count():
    assert instrument_kind("AUROPHARMA", None) == UNKNOWN
    # A company whose name sounds like a fund is still a company; a fund whose
    # name sounds like a company is still a fund. Only series and ISIN count.
    listing = {"LIQUIDCO": {"series": "EQ", "isin": "INE999Z01011"},
               "PHARMALTD": {"series": "EQ", "isin": "INF999Z01011"}}
    assert instrument_kind("LIQUIDCO", listing) == COMPANY
    assert instrument_kind("PHARMALTD", listing) == FUND


def test_companies_only_keeps_order_and_names_each_exclusion():
    kept, excluded = companies_only(["LIQUID1", "MARKSANS", "EMBASSY", "AUROPHARMA", "X"],
                                    REAL_ROWS)
    assert kept == ["MARKSANS", "AUROPHARMA"]
    assert excluded == {"LIQUID1": FUND, "EMBASSY": TRUST, "X": UNKNOWN}


# -- the listing fetch and cache ----------------------------------------------

_UDIFF_HEADER = ("TradDt,BizDt,Sgmt,Src,FinInstrmTp,FinInstrmId,ISIN,TckrSymb,SctySrs,"
                 "FinInstrmNm,ClsPric\n")


class _FakeNse:
    """Serves a UDiFF CSV for the days in `files`; any other day raises."""

    def __init__(self, tmp_path, files, calls):
        self.dir, self._files, self._calls = tmp_path, files, calls

    def equityBhavcopy(self, when):
        self._calls.append(when.date())
        if when.date() not in self._files:
            raise RuntimeError("report unavailable")
        path = self.dir / f"udiff_{when:%Y%m%d}.csv"
        path.write_text(self._files[when.date()], encoding="utf-8")
        return path

    def exit(self):
        pass


@pytest.fixture
def fake_archive(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DISCOVERY_DATA_DIR", str(tmp_path / "disc"))
    monkeypatch.setattr(bhav, "_SLEEP_BETWEEN_CALLS", 0.0)
    monkeypatch.setattr(bhav, "is_trading_day", lambda d: d.weekday() < 5)
    files, calls = {}, []
    archive = tmp_path / "archive"
    archive.mkdir()
    monkeypatch.setattr(bhav, "_make_nse_client", lambda: _FakeNse(archive, files, calls))
    return files, calls


def test_listing_prefers_the_equity_row_and_walks_back_over_a_weekend(fake_archive, tmp_path):
    files, calls = fake_archive
    # Friday 16 Oct 2026. An NCD (series N1) shares IIFL's ticker and comes
    # first; the equity row must win. A blank-symbol row is ignored.
    files[date(2026, 10, 16)] = _UDIFF_HEADER + "\n".join([
        "2026-10-16,2026-10-16,CM,NSE,STK,1,INE530B07AB1,IIFL,N1,IIFL NCD,1000",
        "2026-10-16,2026-10-16,CM,NSE,STK,2,INE530B01024,IIFL,EQ,IIFL FINANCE,450",
        "2026-10-16,2026-10-16,CM,NSE,STK,3,INF174KA1LV5,LIQUID1,EQ,KOTAKLIQ,1000",
        "2026-10-16,2026-10-16,CM,NSE,STK,4,INE041025011,EMBASSY,RR,EMBASSY REIT,400",
        "2026-10-16,2026-10-16,CM,NSE,STK,5,INE000000000,,EQ,BLANK,1",
    ]) + "\n"
    info = bhav.refresh_listing(end=date(2026, 10, 18))          # a Sunday
    assert calls == [date(2026, 10, 16)]                         # Sat and Sun are skipped
    assert info == {"as_of": "2026-10-16", "fresh": True, "securities": 3}
    listing = bhav.load_listing()
    assert listing["IIFL"] == {"series": "EQ", "isin": "INE530B01024"}
    assert instrument_kind("IIFL", listing) == COMPANY
    assert instrument_kind("LIQUID1", listing) == FUND
    assert instrument_kind("EMBASSY", listing) == TRUST


def test_a_failed_refresh_keeps_the_last_good_listing(fake_archive, tmp_path):
    files, calls = fake_archive
    files[date(2026, 10, 16)] = (_UDIFF_HEADER +
                                 "2026-10-16,2026-10-16,CM,NSE,STK,1,INE406A01037,AUROPHARMA,"
                                 "EQ,AUROBINDO,1100\n")
    bhav.refresh_listing(end=date(2026, 10, 16))
    files.clear()                                                # the archive is down
    calls.clear()
    info = bhav.refresh_listing(end=date(2026, 10, 23), tries=3)
    assert calls == [date(2026, 10, 23), date(2026, 10, 22), date(2026, 10, 21)]
    assert info == {"as_of": "2026-10-16", "fresh": False, "securities": 1}
    assert bhav.load_listing() == {"AUROPHARMA": {"series": "EQ", "isin": "INE406A01037"}}


def test_no_listing_at_all_reads_as_none(fake_archive):
    info = bhav.refresh_listing(end=date(2026, 10, 16), tries=1)
    assert info == {"as_of": None, "fresh": False, "securities": 0}
    assert bhav.load_listing() is None


# -- the screen ----------------------------------------------------------------

def _eod_window(symbols, days=30, end=date(2026, 7, 3), close=100.0):
    rows = []
    for k in range(days):
        d = end - timedelta(days=days - 1 - k)
        for s in symbols:
            rows.append({"symbol": s, "series": "EQ", "date": d.isoformat(),
                         "prev_close": close, "open": close, "high": close * 1.02,
                         "low": close * 0.98, "close": close, "volume": 1.0,
                         "traded_value_cr": 10.0, "delivery_qty": 1.0, "delivery_pct": 50.0})
    from services.data.stores.eod_store import COLUMNS
    return pd.DataFrame(rows, columns=COLUMNS)


@pytest.fixture
def screen_env(tmp_path, monkeypatch):
    import core.discovery.screen as scr
    monkeypatch.setattr(settings, "DISCOVERY_DATA_DIR", str(tmp_path / "disc"))
    symbols = ["AUROPHARMA", "LIQUID1", "MARKSANS", "CASHIETF"]
    window = _eod_window(symbols)

    class _Store:
        def load_window(self, end, sessions):
            return window

        def latest_day(self):
            return date(2026, 7, 3)
    monkeypatch.setattr(scr, "EodStore", _Store)
    seen = {}

    def _signals(win, universe, bulk, insider=None):
        seen["universe"] = list(universe)
        return {"momentum": pd.Series({s: float(i) for i, s in enumerate(universe)})}
    monkeypatch.setattr(scr, "compute_signals", _signals)
    monkeypatch.setattr(scr, "apply_guards", lambda short, win: (list(short), {}, []))
    monkeypatch.setattr(scr, "load_bulk_block", lambda: {"degraded": True, "deals": []})
    return scr, seen


def test_the_screen_never_ranks_a_fund(screen_env, monkeypatch):
    scr, seen = screen_env
    monkeypatch.setattr(scr, "load_listing", lambda: REAL_ROWS)
    result = scr.run_screen(on=date(2026, 7, 4))
    assert seen["universe"] == ["AUROPHARMA", "MARKSANS"]       # LIQUID1, CASHIETF never ranked
    assert {c.symbol for c in result.candidates} <= {"AUROPHARMA", "MARKSANS"}
    assert result.universe_size == 2
    assert "instrument_listing" not in result.degraded_checks


def test_without_a_listing_the_screen_says_so(screen_env, monkeypatch):
    scr, seen = screen_env
    monkeypatch.setattr(scr, "load_listing", lambda: None)
    result = scr.run_screen(on=date(2026, 7, 4))
    assert "instrument_listing" in result.degraded_checks
    assert len(seen["universe"]) == 4                            # kept, and said so


# ---------------------------------------------------------------------------
# The deep dive: companies only, an honest budget
# ---------------------------------------------------------------------------

class Analyst:
    """Stub analyst: conviction and gate per symbol; records every call."""

    def __init__(self, conviction=None, gate=None, fail=()):
        self.conviction, self.gate, self.fail = conviction or {}, gate or {}, set(fail)
        self.calls: list[str] = []

    def orchestrator(self, sector):
        analyst = self

        class _O:
            def analyse(self, symbol):
                analyst.calls.append(symbol)
                if symbol in analyst.fail:
                    raise RuntimeError("LLM down")
                return SimpleNamespace(
                    final_score=analyst.conviction.get(symbol, 0.7), verdict="BUY",
                    investment_thesis=f"thesis {symbol}",
                    decision_gate=SimpleNamespace(status=analyst.gate.get(symbol, "actionable"),
                                                  run_id=f"r-{symbol}", reasons=[]))
        return _O()


@pytest.fixture
def dive_env(tmp_path, monkeypatch):
    """run_deep_dives with a stub analyst, a fixed EOD window and no network."""
    monkeypatch.setattr(settings, "DISCOVERY_DATA_DIR", str(tmp_path / "disc"))
    state = {"managed": [], "window": pd.DataFrame(), "sector_of": {}}
    monkeypatch.setattr(dd, "load_managed_tickers",
                        lambda: [{"sym": s, "enabled": True} for s in state["managed"]])

    class _Store:
        def load_window(self, end, sessions):
            return state["window"]
    monkeypatch.setattr(dd, "EodStore", _Store)
    monkeypatch.setattr(dd, "infer_sector", lambda s, c=None: "generic")
    monkeypatch.setattr(dd, "market_classification",
                        lambda s: {"sector": state["sector_of"].get(s, ""), "industry": ""})
    analyst = Analyst()
    monkeypatch.setattr(dd, "get_orchestrator", analyst.orchestrator)
    state["analyst"] = analyst
    return state


def cand(symbol, close=100.0, flags=()):
    return DiscoveryCandidate(symbol=symbol, close=close, composite=0.5, flags=list(flags))


def test_no_analyst_call_for_a_fund_a_trust_or_an_unknown_symbol(dive_env):
    listing = {**REAL_ROWS, **companies("NEWCO")}
    cs = [cand(s) for s in ["LIQUID1", "EMBASSY", "INDIGRID", "GSEC2030", "NOTLISTED", "NEWCO"]]
    results = dd.run_deep_dives(cs, on=date(2026, 7, 4), max_n=10, listing=listing)
    assert dive_env["analyst"].calls == ["NEWCO"]
    assert [r.symbol for r in results] == ["NEWCO"]


def test_an_ipo_reit_is_refused_like_a_screen_fund(dive_env):
    """An IPO candidate skips the screen, so the deep dive is where a REIT or
    InvIT listing is stopped."""
    listing = {**REAL_ROWS, **companies("IPOCO")}
    cs = [cand("EMBASSY", flags=["ipo"]), cand("IPOCO", flags=["ipo"])]
    dd.run_deep_dives(cs, on=date(2026, 7, 4), max_n=2, listing=listing)
    assert dive_env["analyst"].calls == ["IPOCO"]


def test_without_any_listing_nothing_is_dived(dive_env, monkeypatch):
    monkeypatch.setattr(dd, "load_listing", lambda: None)
    assert dd.run_deep_dives([cand("NEWCO")], on=date(2026, 7, 4)) == []
    assert dive_env["analyst"].calls == []


def test_a_failed_call_counts_against_the_budget(dive_env):
    """Budget 3; A fails, B and C succeed: 3 calls, D never called."""
    dive_env["analyst"].fail = {"A"}
    out = dd.run_deep_dives([cand(s) for s in "ABCD"], on=date(2026, 7, 4), max_n=3,
                            listing=companies(*"ABCD"))
    assert dive_env["analyst"].calls == ["A", "B", "C"]
    assert [r.symbol for r in out] == ["B", "C"]


def test_a_redive_takes_its_close_from_the_window_and_bypasses_the_shelved_skip(
        dive_env, shelf):
    shelf.apply_deep_dives([dive("OLDIDEA", 0.7, "Healthcare")], on=date(2026, 6, 1))
    dive_env["window"] = _eod_window(["OLDIDEA"], close=250.0)
    listing = companies("OLDIDEA")
    # Shelved and not flagged: skipped before any call.
    assert dd.run_deep_dives([cand("OLDIDEA")], on=date(2026, 7, 4), listing=listing) == []
    out = dd.run_deep_dives([cand("OLDIDEA", close=0.0, flags=["redive"])],
                            on=date(2026, 7, 4), listing=listing)
    assert dive_env["analyst"].calls == ["OLDIDEA"]
    # Band 97-102% and the close of the window's last bar: 242.50 / 255.00.
    assert (out[0].close, out[0].entry_low, out[0].entry_high) == (250.0, 242.5, 255.0)


def test_a_redive_without_a_close_is_not_called(dive_env, shelf):
    out = dd.run_deep_dives([cand("GONE", close=0.0, flags=["redive"])], on=date(2026, 7, 4),
                            listing=companies("GONE"))
    assert out == [] and dive_env["analyst"].calls == []


def test_every_answer_is_returned_even_an_abstain_under_the_enforced_gate(
        dive_env, gate_mode, shelf):
    """Rework 1 (R2): the dive memo must remember a new candidate that
    abstained, so the dive returns it; a re-dive that abstains comes back so
    the shelf can drop the idea with the reason. The shelf, where an idea is
    minted, refuses the new abstain under enforce (SA-003)."""
    gate_mode("enforce")
    dive_env["analyst"].gate = {"NEW": "abstain", "OLD": "abstain"}
    dive_env["window"] = _eod_window(["OLD"])
    out = dd.run_deep_dives([cand("NEW"), cand("OLD", close=0.0, flags=["redive"])],
                            on=date(2026, 7, 4), listing=companies("NEW", "OLD"))
    assert [(r.symbol, r.data_gate) for r in out] == [("NEW", "abstain"), ("OLD", "abstain")]
    summary = shelf.apply_deep_dives([r for r in out if r.symbol == "NEW"], on=date(2026, 7, 4))
    assert (summary["added"], summary["gated"]) == ([], ["NEW"])
    assert active(shelf) == []


@pytest.mark.parametrize("gate, kept", [
    ("abstain", False), ("", False), ("degraded", True), ("actionable", True),
])
def test_under_enforce_the_shelf_mints_only_actionable_ideas(shelf, gate_mode, gate, kept):
    """SA-003's rule at the place an idea is minted: under enforce only an
    actionable or degraded dive becomes a shelf idea; record mode keeps all."""
    gate_mode("enforce")
    shelf.apply_deep_dives([dive("N", 0.8, "Healthcare", gate=gate)], on=date(2026, 7, 4))
    assert [i.symbol for i in active(shelf)] == (["N"] if kept else [])
    gate_mode("record")
    shelf.apply_deep_dives([dive("R", 0.8, "Healthcare", gate=gate)], on=date(2026, 7, 4))
    assert "R" in {i.symbol for i in active(shelf)}


def test_property_the_budget_bounds_every_call(dive_env, gate_mode, monkeypatch):
    """Random candidate lists (re-dives, IPOs, repeats, managed, shelved,
    funds, missing closes) and random analyst failures and gates: the
    analyst is called at most max_n times, never twice for one symbol,
    never for a fund or a managed symbol, never for a shelved one unless it
    is a re-dive; and it is called exactly min(max_n, eligible) times."""
    monkeypatch.setattr(dd, "ShelfStore", dd.ShelfStore)          # so the swaps below undo
    monkeypatch.setattr(dd, "get_orchestrator", dd.get_orchestrator)
    rng = random.Random(4004)
    for trial in range(300):
        gate_mode(rng.choice(["record", "enforce"]))
        names = [f"S{i}" for i in range(rng.randint(1, 30))]
        kinds = {s: rng.choice(["company"] * 6 + ["fund", "trust", "unknown"]) for s in names}
        listing = {s: {"series": "RR" if k == "trust" else "EQ",
                       "isin": "INF0" if k == "fund" else "INE0"}
                   for s, k in kinds.items() if k != "unknown"}
        managed = {s for s in names if rng.random() < 0.15}
        shelved = {s for s in names if rng.random() < 0.15}
        dive_env["managed"] = sorted(managed)
        dive_env["window"] = _eod_window([s for s in names if rng.random() < 0.8], days=3)
        with_close = set(dive_env["window"]["symbol"]) if len(dive_env["window"]) else set()
        on_shelf = Shelf(ideas=[ShelfIdea(symbol=s, sector="generic", added="2026-06-01",
                                          conviction=0.6) for s in sorted(shelved)])
        dd.ShelfStore = lambda: SimpleNamespace(load=lambda: on_shelf)  # restored by monkeypatch
        analyst = Analyst(fail={s for s in names if rng.random() < 0.2},
                          gate={s: rng.choice(["actionable", "degraded", "abstain", ""])
                                for s in names})
        dive_env["analyst"] = analyst
        dd.get_orchestrator = analyst.orchestrator          # restored by monkeypatch
        listed = [DiscoveryCandidate(
            symbol=rng.choice(names), composite=0.5,
            close=rng.choice([0.0, 100.0, 100.0]),
            flags=rng.choice([[], [], ["ipo"], ["redive"]])) for _ in range(rng.randint(0, 40))]
        max_n = rng.randint(1, 12)
        dd.run_deep_dives(listed, on=date(2026, 7, 4), max_n=max_n, listing=listing)

        calls = analyst.calls
        assert len(calls) <= max_n, trial
        assert len(calls) == len(set(calls)), trial
        for s in calls:
            assert kinds[s] == "company" and s not in managed, trial
        eligible: list[str] = []
        for c in listed:
            redive = "redive" in c.flags
            if (c.symbol in managed or (c.symbol in shelved and not redive)
                    or kinds[c.symbol] != "company" or c.symbol in eligible):
                continue
            if c.close <= 0 and c.symbol not in with_close:
                continue
            eligible.append(c.symbol)
        assert calls == eligible[:max_n], trial


# ---------------------------------------------------------------------------
# The shelf: 20 ideas, at most 3 per market sector
# ---------------------------------------------------------------------------

SECTORS8 = ["Healthcare", "Industrials", "Technology", "Financial Services",
            "Consumer Cyclical", "Basic Materials", "Energy", "Utilities"]


def forty_dives(seed=11):
    """40 dives over 8 sectors (5 each), convictions 0.56-0.95, all distinct."""
    rng = random.Random(seed)
    convictions = rng.sample([round(0.56 + k * 0.01, 2) for k in range(40)], 40)
    return [dive(f"C{k:02d}", convictions[k], SECTORS8[k % 8]) for k in range(40)]


def test_forty_dives_in_eight_sectors_fill_twenty_with_three_per_sector(shelf):
    dives = forty_dives()
    summary = shelf.apply_deep_dives(dives, on=date(2026, 7, 4))
    # Oracle: the 3 strongest of each sector (24), then the 20 strongest of those.
    best3 = [d for s in SECTORS8 for d in
             sorted((d for d in dives if d.market_sector == s), key=lambda d: -d.conviction)[:3]]
    expected = {d.symbol for d in sorted(best3, key=lambda d: -d.conviction)[:20]}
    on_shelf = active(shelf)
    assert {i.symbol for i in on_shelf} == expected
    assert max(Counter(i.market_sector for i in on_shelf).values()) == 3
    assert len(on_shelf) == 20
    assert set(summary["added"]) == expected
    # A dive outside its sector's 3 best is turned away by the cap only when
    # those 3 are all on the shelf; otherwise the full shelf turns it away.
    full = [s for s in SECTORS8
            if {d.symbol for d in best3 if d.market_sector == s} <= expected]
    assert set(summary["capped"]) == {d.symbol for d in dives if d.market_sector in full
                                      and d not in best3}
    assert len(summary["skipped"]) == 20 and len(summary["displaced"]) == 0


def test_a_fourth_idea_replaces_its_sectors_weakest_only_if_stronger(shelf, tmp_path):
    shelf.apply_deep_dives([dive("H1", 0.70, "Healthcare"), dive("H2", 0.65, "Healthcare"),
                            dive("H3", 0.60, "Healthcare")], on=date(2026, 7, 4))
    weaker = shelf.apply_deep_dives([dive("H4", 0.59, "Healthcare")], on=date(2026, 7, 11))
    assert weaker["capped"] == ["H4"] and weaker["added"] == []
    stronger = shelf.apply_deep_dives([dive("H5", 0.80, "Healthcare")], on=date(2026, 7, 18))
    assert stronger["added"] == ["H5"] and stronger["displaced"] == ["H3"]
    assert sorted(i.symbol for i in active(shelf)) == ["H1", "H2", "H5"]
    drop = [e for e in events(tmp_path) if e["event"] == "dropped"][-1]
    assert drop["symbol"] == "H3"
    assert drop["detail"] == ("sector cap: 3 ideas in Healthcare; replaced by H5 "
                              "(0.80 > 0.60)")


def test_an_unclassified_idea_is_not_capped_and_generic_never_counts(shelf):
    """Five ideas with no market sector and a `sector` of "generic" all stay:
    the routing label is not a sector, and neither is "unknown"."""
    shelf.apply_deep_dives([dive(f"U{k}", 0.6 + k / 100) for k in range(5)],
                           on=date(2026, 7, 4))
    assert len(active(shelf)) == 5


def test_sector_names_compare_without_case(shelf):
    shelf.apply_deep_dives([dive("A", 0.7, "Healthcare"), dive("B", 0.69, "healthcare"),
                            dive("C", 0.68, "HEALTHCARE ")], on=date(2026, 7, 4))
    out = shelf.apply_deep_dives([dive("D", 0.60, "Healthcare")], on=date(2026, 7, 11))
    assert out["capped"] == ["D"]


class MemoryShelf(shelf_mod.ShelfStore):
    """The real ShelfStore with load/save kept in memory: the property below
    is about the cap logic, and thousands of rapid os.replace calls on one
    Windows file hit transient access-denied errors (antivirus scans)."""

    def __init__(self):
        super().__init__()
        self._mem = Shelf()

    def load(self):
        return self._mem.model_copy(deep=True)

    def save(self, shelf):
        self._mem = shelf.model_copy(deep=True)


def test_property_no_sector_ever_exceeds_the_cap(shelf, monkeypatch):
    """Random sequences of adds, re-dives (which may name a sector for the
    first time), backfills, manual drops and rotations. After every step: no
    market sector holds more than 3 active ideas, the shelf holds at most 20,
    and no symbol is active twice."""
    shelf = MemoryShelf()
    rng = random.Random(9)
    sectors = SECTORS8[:5] + [""]
    classes: dict[str, str] = {}
    for trial in range(60):
        shelf.save(Shelf())
        day = date(2026, 1, 3)
        for step in range(25):
            day += timedelta(days=7)
            op = rng.choice(["add", "add", "add", "redive", "backfill", "drop", "rotate"])
            if op == "add":
                batch = []
                for _ in range(rng.randint(1, 8)):
                    sym = f"X{rng.randint(0, 60)}"
                    batch.append(dive(sym, round(rng.uniform(0.4, 0.95), 3),
                                      rng.choice(sectors), on=day.isoformat()))
                shelf.apply_deep_dives(batch, on=day)
            elif op == "redive":
                ideas = active(shelf)
                if ideas:
                    picked = rng.sample(ideas, min(len(ideas), rng.randint(1, 4)))
                    shelf.apply_redives(
                        [dive(i.symbol, round(rng.uniform(0.4, 0.95), 3), rng.choice(sectors),
                              on=day.isoformat(),
                              gate=rng.choice(["actionable", "actionable", "degraded",
                                               "abstain"])) for i in picked], on=day)
            elif op == "backfill":
                for i in active(shelf):
                    classes.setdefault(i.symbol, rng.choice(sectors))
                shelf.backfill_classification(
                    lambda s: {"sector": classes.get(s, ""), "industry": ""})
            elif op == "drop":
                ideas = active(shelf)
                if ideas:
                    shelf.drop(rng.choice(ideas).symbol, reason="manual")
            else:
                shelf.rotate_stale(on=day)
            on_shelf = active(shelf)
            counts = Counter(shelf_mod.cap_key(i) for i in on_shelf if shelf_mod.cap_key(i))
            assert not counts or max(counts.values()) <= 3, (trial, step, op, counts)
            assert len(on_shelf) <= 20, (trial, step)
            assert len({i.symbol for i in on_shelf}) == len(on_shelf), (trial, step)


# ---------------------------------------------------------------------------
# Characterization: the old values reproduce today's shelf exactly
# ---------------------------------------------------------------------------

def head_apply(ideas, dives, on, *, shelf_size, floor):
    """HEAD 25fae38's ShelfStore.apply_deep_dives, transcribed: ideas are
    dicts {symbol, conviction, status, added}. Returns (summary, events)."""
    added, displaced, skipped, evs = [], [], [], []
    for d in sorted(dives, key=lambda d: d.conviction, reverse=True):
        if d.conviction < floor:
            skipped.append(d.symbol)
            continue
        if any(i["symbol"] == d.symbol and i["status"] == "active" for i in ideas):
            skipped.append(d.symbol)
            continue
        act = [i for i in ideas if i["status"] == "active"]
        if len(act) >= shelf_size:
            weakest = min(act, key=lambda i: i["conviction"])
            if weakest["conviction"] >= d.conviction:
                skipped.append(d.symbol)
                continue
            weakest["status"] = "dropped"
            displaced.append(weakest["symbol"])
            evs.append(("dropped", weakest["symbol"],
                        f"displaced by {d.symbol} ({d.conviction:.2f} > "
                        f"{weakest['conviction']:.2f})"))
        ideas.append({"symbol": d.symbol, "conviction": d.conviction, "status": "active",
                      "added": on.isoformat()})
        added.append(d.symbol)
        evs.append(("added", d.symbol, f"conviction={d.conviction:.2f}"))
    return {"added": added, "displaced": displaced, "skipped": skipped}, evs


def test_old_values_reproduce_todays_shelf_exactly(shelf, monkeypatch, tmp_path):
    shelf = MemoryShelf()
    monkeypatch.setattr(settings, "DISCOVERY_SHELF_SIZE", 10)
    monkeypatch.setattr(settings, "DISCOVERY_DEEP_DIVE_COUNT", 10)
    monkeypatch.setattr(settings, "DISCOVERY_MAX_IDEAS_PER_SECTOR", 0)
    monkeypatch.setattr(settings, "DISCOVERY_REDIVE_AFTER_DAYS", 0)
    rng = random.Random(77)
    for trial in range(40):
        shelf.save(Shelf())
        events_path = tmp_path / "disc" / "shelf_events.jsonl"
        if events_path.exists():
            events_path.unlink()
        oracle: list[dict] = []
        oracle_events: list[tuple] = []
        day = date(2026, 1, 3)
        for week in range(12):
            day += timedelta(days=7)
            batch = [dive(f"S{rng.randint(0, 40)}", round(rng.uniform(0.3, 0.95), 2),
                          rng.choice(SECTORS8 + [""]), on=day.isoformat())
                     for _ in range(rng.randint(0, 10))]
            got = shelf.apply_deep_dives(batch, on=day)
            want, evs = head_apply(oracle, batch, day, shelf_size=10, floor=0.55)
            assert got == want, (trial, week)
            oracle_events += evs
        mine = [{"symbol": i.symbol, "conviction": i.conviction, "status": i.status,
                 "added": i.added} for i in shelf.load().ideas]
        assert mine == oracle, trial
        assert [(e["event"], e["symbol"], e["detail"]) for e in events(tmp_path)] == \
            oracle_events, trial


def test_old_values_offer_every_active_idea_and_no_watchlist(monkeypatch):
    monkeypatch.setattr(settings, "DISCOVERY_REDIVE_AFTER_DAYS", 0)
    monkeypatch.setattr(settings, "DISCOVERY_WATCHLIST_BUYS", False)
    ideas = [ShelfIdea(symbol=s, sector="generic", added=a, conviction=0.7)
             for s, a in [("OLD", "2025-01-01"), ("NEW", "2026-07-10")]]
    portfolio = SimpleNamespace(holdings=[], watchlist=[WatchlistItem(
        symbol="W", added="2026-07-01")])
    out, excluded = cands_mod.buy_candidates(
        portfolio, date(2026, 7, 13), ideas,
        latest_analysis=lambda s: pytest.fail("the score history must not be read"))
    assert out == ideas and excluded == {}


def test_old_values_send_the_cycle_exactly_the_ipo_and_screen_candidates(
        tmp_path, monkeypatch):
    """With re-dives off, the cycle passes ipo + screen to the deep dives as
    before, however stale or unverified the shelf is."""
    monkeypatch.setattr(settings, "DISCOVERY_REDIVE_AFTER_DAYS", 0)
    env = _cycle_env(tmp_path, monkeypatch, screen=[cand("SCR0"), cand("SCR1")],
                     ipo=[cand("IPO0", flags=["ipo"])])
    shelf_mod.ShelfStore().save(Shelf(ideas=[
        ShelfIdea(symbol="PREGATE", sector="generic", added="2026-06-01", conviction=0.7)]))
    passed = []
    monkeypatch.setattr(disc, "run_deep_dives", lambda cs, on: passed.extend(cs) or [])
    disc.run_discovery_cycle(on=date(2026, 7, 4))
    assert [c.symbol for c in passed] == ["IPO0", "SCR0", "SCR1"]
    assert env["listing_refreshed"] == [date(2026, 7, 4)]


# ---------------------------------------------------------------------------
# Re-dives
# ---------------------------------------------------------------------------

def _idea(symbol, added, *, gate="actionable", dived="", conviction=0.7, sector=""):
    return ShelfIdea(symbol=symbol, sector="generic", added=added, conviction=conviction,
                     data_gate=gate, dived=dived, source_screen_date=added,
                     entry_low=97.0, entry_high=102.0, invalidation_level=88.0,
                     close_at_add=100.0, market_sector=sector)


def test_redive_queue_unverified_first_then_oldest_dive(shelf):
    on = date(2026, 7, 4)
    shelf.save(Shelf(ideas=[
        _idea("FRESH", "2026-06-20"),                         # 14 days: not due
        _idea("STALE40", "2026-05-25"),                       # 40 days: due
        _idea("PRE10", "2026-06-24", gate=""),                # no gate: due first
        _idea("STALE31", "2026-06-03"),                       # 31 days: due
        _idea("PRE50", "2026-05-15", gate=""),                # no gate, older
        _idea("REDIVED", "2026-05-10", dived="2026-06-30"),   # dived 4 days ago
        _idea("ROTATING", "2026-04-30"),                      # 65 days: rotates instead
        _idea("BOUNDARY", "2026-06-04"),                      # exactly 30 days: fresh
        _idea("REVIVED", "2026-03-01", dived="2026-05-30"),   # shelved 125 days ago,
    ]))                                                       # last dived 35 days ago: due
    assert [i.symbol for i in shelf.redive_due(on)] ==         ["PRE50", "PRE10", "STALE40", "REVIVED", "STALE31"]


def test_a_redive_refreshes_in_place_and_keeps_the_start(shelf, tmp_path):
    shelf.save(Shelf(ideas=[_idea("KEEP", "2026-05-25", conviction=0.62)]))
    out = shelf.apply_redives([dive("KEEP", 0.71, "Industrials", on="2026-07-04",
                                    close=120.0)], on=date(2026, 7, 4))
    assert out == {"refreshed": ["KEEP"], "dropped": {}, "capped": []}
    idea = shelf.load().ideas[0]
    assert (idea.status, idea.added, idea.close_at_add) == ("active", "2026-05-25", 100.0)
    assert (idea.conviction, idea.dived, idea.data_gate) == (0.71, "2026-07-04", "actionable")
    assert (idea.entry_low, idea.entry_high) == (116.4, 122.4)  # 97% / 102% of 120
    assert idea.market_sector == "Industrials"
    assert events(tmp_path)[-1]["event"] == "redived"


@pytest.mark.parametrize("gate, conviction, reason", [
    ("abstain", 0.80, "re-dive 2026-07-04: data gate abstain"),
    ("", 0.80, "re-dive 2026-07-04: data gate missing"),
    ("actionable", 0.50, "re-dive 2026-07-04: conviction 0.50 below 0.55"),
])
def test_a_redive_that_abstains_or_weakens_drops_the_idea_with_the_reason(
        shelf, tmp_path, gate, conviction, reason):
    shelf.save(Shelf(ideas=[_idea("GO", "2026-05-25", gate="")]))
    out = shelf.apply_redives([dive("GO", conviction, on="2026-07-04", gate=gate)],
                              on=date(2026, 7, 4))
    assert out["dropped"] == {"GO": reason}
    assert shelf.load().ideas[0].status == "dropped"
    assert events(tmp_path)[-1] == {**events(tmp_path)[-1], "event": "dropped",
                                    "symbol": "GO", "detail": reason}


def test_a_redive_that_names_a_full_sector_drops_the_weakest(shelf):
    shelf.save(Shelf(ideas=[_idea(s, "2026-06-20", conviction=c, sector="Energy")
                            for s, c in [("E1", 0.9), ("E2", 0.8), ("E3", 0.7)]]
                     + [_idea("NEWLYNAMED", "2026-05-25", conviction=0.75)]))
    out = shelf.apply_redives([dive("NEWLYNAMED", 0.75, "Energy", on="2026-07-04")],
                              on=date(2026, 7, 4))
    assert out["capped"] == ["E3"]                    # 0.70 is now the 4th of 4 in Energy
    assert sorted(i.symbol for i in active(shelf)) == ["E1", "E2", "NEWLYNAMED"]


def test_rotation_counts_from_the_latest_dive(shelf, tmp_path):
    """REDINGTON's shape: shelved 5 Sep, re-dived 24 Oct. It does not rotate on
    7 Nov (63 days after shelving, 14 after the re-dive); it rotates once its
    latest dive is more than 60 days old (24 Dec is 61 days). An idea never
    re-dived still rotates 61 days after it was shelved."""
    shelf.save(Shelf(ideas=[_idea("REDINGTON", "2026-09-05"), _idea("NEVER", "2026-09-05")]))
    shelf.apply_redives([dive("REDINGTON", 0.70, "Technology", on="2026-10-24")],
                        on=date(2026, 10, 24))
    assert shelf.rotate_stale(on=date(2026, 11, 4)) == []          # 60 days: not yet
    assert shelf.rotate_stale(on=date(2026, 11, 7)) == ["NEVER"]  # 63 days
    assert shelf.rotate_stale(on=date(2026, 12, 23)) == []         # 60 days after the re-dive
    assert shelf.rotate_stale(on=date(2026, 12, 24)) == ["REDINGTON"]
    drops = [e for e in events(tmp_path) if e["event"] == "dropped"]
    assert [(e["symbol"], e["detail"]) for e in drops] == [
        ("NEVER", "stale after 63d"), ("REDINGTON", "stale after 61d")]


def test_without_redives_rotation_is_todays(shelf, monkeypatch):
    """Re-dives off: ideas added over 20 random weeks rotate exactly when an
    oracle counting from `added` says (HEAD's rule)."""
    monkeypatch.setattr(settings, "DISCOVERY_REDIVE_AFTER_DAYS", 0)
    monkeypatch.setattr(settings, "DISCOVERY_MAX_IDEAS_PER_SECTOR", 0)
    rng = random.Random(61)
    store = MemoryShelf()
    day = date(2026, 1, 3)
    for week in range(20):
        day += timedelta(days=7)
        store.apply_deep_dives([dive(f"S{rng.randint(0, 60)}", round(rng.uniform(0.56, 0.95), 2),
                                     on=day.isoformat()) for _ in range(rng.randint(0, 4))],
                               on=day)
        before = [i for i in store.load().ideas if i.status == "active"]
        want = [i.symbol for i in before if (day - date.fromisoformat(i.added)).days > 60]
        assert store.rotate_stale(on=day) == want, week


def test_a_non_company_is_dropped_and_an_unknown_one_kept(shelf, tmp_path):
    shelf.save(Shelf(ideas=[_idea("LIQUID1", "2026-09-27", gate="abstain"),
                            _idea("AUROPHARMA", "2026-10-03"),
                            _idea("DELISTEDCO", "2026-09-27")]))
    out = shelf.drop_non_companies(REAL_ROWS)
    assert out == {"LIQUID1": "not a company: NSE lists it as fund "
                              "(series EQ, ISIN INF174KA1LV5)"}
    assert sorted(i.symbol for i in active(shelf)) == ["AUROPHARMA", "DELISTEDCO"]
    assert shelf.drop_non_companies(None) == {}        # no listing: nothing judged


def test_backfill_names_sectors_and_then_enforces_the_cap(shelf):
    shelf.save(Shelf(ideas=[_idea(f"P{k}", "2026-06-20", conviction=0.6 + k / 100)
                            for k in range(5)]))
    named = shelf.backfill_classification(lambda s: {"sector": "Healthcare",
                                                     "industry": "Drug Manufacturers"})
    assert named == ["P0", "P1", "P2", "P3", "P4"]
    assert sorted(i.symbol for i in active(shelf)) == ["P2", "P3", "P4"]   # the 3 strongest


# ---------------------------------------------------------------------------
# The weekly cycle end to end (analyst stubbed, transports faked or blocked)
# ---------------------------------------------------------------------------

def _cycle_env(tmp_path, monkeypatch, *, screen, ipo=(), listing=None, sector_of=None,
               conviction=None, gate=None, window_symbols=()):
    monkeypatch.setattr(settings, "DISCOVERY_DATA_DIR", str(tmp_path / "disc"))
    monkeypatch.setattr(settings, "DISCOVERY_IPO_ENABLED", bool(ipo))
    monkeypatch.setattr(settings, "DISCOVERY_IPO_MAX_DEEP_DIVES", 2)
    env = {"listing_refreshed": [], "alerts": []}
    symbols = [c.symbol for c in list(screen) + list(ipo)] + list(window_symbols)
    listing = listing if listing is not None else companies(*symbols)
    (tmp_path / "disc").mkdir(parents=True, exist_ok=True)
    (tmp_path / "disc" / "listing.json").write_text(
        json.dumps({"as_of": "2026-07-03", "securities": listing}), encoding="utf-8")

    def _refresh(end=None):
        env["listing_refreshed"].append(end)
        return {"as_of": "2026-07-03", "fresh": True, "securities": len(listing)}
    monkeypatch.setattr(disc, "sync_recent", lambda **kw: {})
    monkeypatch.setattr(disc, "refresh_bulk_block", lambda **kw: {})
    monkeypatch.setattr(disc, "refresh_insider_trades", lambda on=None: {})
    monkeypatch.setattr(disc, "refresh_listing", _refresh)
    monkeypatch.setattr(disc, "refresh_ipo_cache", lambda: {})
    monkeypatch.setattr(disc, "build_ipo_candidates", lambda on: list(ipo))
    monkeypatch.setattr(disc, "run_screen", lambda on=None: ScreenResult(
        screen_date="2026-07-03", universe_size=2000, shortlist_size=80,
        candidates=list(screen)))
    monkeypatch.setattr(disc, "run_paper_reviews",
                        lambda on: {"reviewed": [], "failed": [], "skipped": []})
    sector_of = sector_of or {}
    classify = lambda s: {"sector": sector_of.get(s, ""), "industry": ""}  # noqa: E731
    monkeypatch.setattr(disc, "market_classification", classify)
    monkeypatch.setattr(dd, "market_classification", classify)
    monkeypatch.setattr(dd, "load_managed_tickers", lambda: [])
    monkeypatch.setattr(dd, "infer_sector", lambda s, c=None: "generic")
    window = _eod_window(symbols, days=25, end=date(2026, 7, 3))

    class _Store:
        def load_window(self, end, sessions):
            return window
    monkeypatch.setattr(dd, "EodStore", _Store)
    analyst = Analyst(conviction=conviction, gate=gate)
    monkeypatch.setattr(dd, "get_orchestrator", analyst.orchestrator)
    env["analyst"] = analyst
    import core.delivery.alerts as alerts
    monkeypatch.setattr(alerts, "emit_alerts_broadcast",
                        lambda evs, **kw: env["alerts"].extend(evs) or {})
    return env


def test_cycle_fills_the_shelf_to_twenty_by_conviction_three_per_sector(tmp_path, monkeypatch):
    """The card's acceptance fixture: a screen of 40 candidates over 8
    sectors, ranked so that the 20 best-ranked hold 7 of sector Healthcare.
    Week 1 dives the 20 best-ranked (the budget). Week 2 dives the other 20:
    the dive memo keeps week 1's rejects from being dived again. After it the
    shelf holds the 20 strongest of each sector's 3 strongest, and no idea
    left off could take a place without breaking the cap."""
    monkeypatch.setattr(settings, "DISCOVERY_DEEP_DIVE_COUNT", 20)
    monkeypatch.setattr(settings, "DISCOVERY_SHELF_SIZE", 20)
    monkeypatch.setattr(settings, "DISCOVERY_MAX_IDEAS_PER_SECTOR", 3)
    monkeypatch.setattr(settings, "DISCOVERY_REDIVE_AFTER_DAYS", 30)
    rng = random.Random(404)
    sector_of, conviction = {}, {}
    # Ranks 1-20: Healthcare 7, then 2 each of the next six sectors, Utilities 1.
    # Ranks 21-40: the seven other sectors in turn (Utilities gets 2 more).
    order = (["Healthcare"] * 7 + [s for s in SECTORS8[1:] for _ in range(2)])[:20]
    order += (SECTORS8[1:] * 3)[:20]
    screen = []
    for k, sector in enumerate(order):
        sym = f"R{k:02d}"
        sector_of[sym] = sector
        conviction[sym] = round(rng.uniform(0.53, 0.95), 3)
        screen.append(DiscoveryCandidate(symbol=sym, close=100.0, composite=1 - k / 100))
    env = _cycle_env(tmp_path, monkeypatch, screen=screen, sector_of=sector_of,
                     conviction=conviction)

    first = disc.run_discovery_cycle(on=date(2026, 7, 4))
    assert env["analyst"].calls == [c.symbol for c in screen[:20]]
    assert first["deep_dives"] == 20
    week1 = env["analyst"].calls[:]
    env["analyst"].calls.clear()
    second = disc.run_discovery_cycle(on=date(2026, 7, 11))
    assert env["analyst"].calls == [c.symbol for c in screen[20:]]
    assert second["hygiene"]["recently_dived"] == sorted(week1)

    # Oracle over all 40: the 3 strongest qualifying ideas of each sector,
    # then the 20 strongest of those.
    qualifying = [s for s in conviction if conviction[s] >= 0.55]
    best3 = [s for sec in SECTORS8 for s in sorted(
        (s for s in qualifying if sector_of[s] == sec), key=lambda s: -conviction[s])[:3]]
    expected = set(sorted(best3, key=lambda s: -conviction[s])[:20])
    assert len(expected) == 20                       # the fixture can fill the shelf
    on_shelf = active(shelf_mod.ShelfStore())
    assert {i.symbol for i in on_shelf} == expected
    per_sector = Counter(i.market_sector for i in on_shelf)
    assert max(per_sector.values()) <= 3
    # Optimality: every dived idea at or above the floor that is not on the
    # shelf is weaker than its sector's weakest (sector full) or than the
    # shelf's weakest (sector not full).
    dived = set(week1) | set(env["analyst"].calls)
    held = {i.symbol for i in on_shelf}
    floor_ok = [s for s in dived if conviction[s] >= 0.55 and s not in held]
    weakest_all = min(i.conviction for i in on_shelf)
    for s in floor_ok:
        peers = [i.conviction for i in on_shelf if i.market_sector == sector_of[s]]
        bound = min(peers) if len(peers) >= 3 else weakest_all
        assert conviction[s] <= bound, (s, conviction[s], bound)


def test_cycle_redives_unverified_ideas_first_and_keeps_the_ipo_slots(tmp_path, monkeypatch):
    """Budget 5, 2 IPO candidates: 3 slots for re-dives (of 4 due), the IPOs,
    and no screen candidate. The abstaining re-dive is dropped with the reason,
    the fourth waits for next week."""
    monkeypatch.setattr(settings, "DISCOVERY_DEEP_DIVE_COUNT", 5)
    monkeypatch.setattr(settings, "DISCOVERY_REDIVE_AFTER_DAYS", 30)
    ipo = [cand("IPO0", close=300.0, flags=["ipo"]), cand("IPO1", close=300.0, flags=["ipo"])]
    env = _cycle_env(tmp_path, monkeypatch, screen=[cand("SCR0")], ipo=ipo,
                     window_symbols=["PRE1", "PRE2", "PRE3", "STALE"],
                     gate={"PRE2": "abstain"}, conviction={"PRE1": 0.72, "PRE3": 0.66})
    shelf_mod.ShelfStore().save(Shelf(ideas=[
        _idea("PRE1", "2026-06-01", gate=""), _idea("PRE2", "2026-06-02", gate=""),
        _idea("PRE3", "2026-06-03", gate=""), _idea("STALE", "2026-05-20")]))
    result = disc.run_discovery_cycle(on=date(2026, 7, 4))
    assert env["analyst"].calls == ["PRE1", "PRE2", "PRE3", "IPO0", "IPO1"]
    assert result["hygiene"]["redive"] == ["PRE1", "PRE2", "PRE3"]
    assert result["hygiene"]["redive_deferred"] == ["STALE"]
    assert result["redived"]["refreshed"] == ["PRE1", "PRE3"]
    assert result["redived"]["dropped"] == {"PRE2": "re-dive 2026-07-04: data gate abstain"}
    by = {i.symbol: i for i in shelf_mod.ShelfStore().load().ideas}
    assert (by["PRE1"].status, by["PRE1"].data_gate, by["PRE1"].dived,
            by["PRE1"].conviction) == ("active", "actionable", "2026-07-04", 0.72)
    assert by["PRE2"].status == "dropped"
    assert set(result["shelf"]["added"]) == {"IPO0", "IPO1"}


def test_cycle_drops_liquid1_and_never_dives_a_fund(tmp_path, monkeypatch):
    listing = {**REAL_ROWS, **companies("NEWCO")}
    env = _cycle_env(tmp_path, monkeypatch, screen=[cand("CASHIETF"), cand("NEWCO")],
                     listing=listing)
    shelf_mod.ShelfStore().save(Shelf(ideas=[
        _idea("LIQUID1", "2026-06-27", gate="abstain")]))
    result = disc.run_discovery_cycle(on=date(2026, 7, 4))
    assert result["hygiene"]["not_companies"] == {
        "LIQUID1": "not a company: NSE lists it as fund (series EQ, ISIN INF174KA1LV5)"}
    assert env["analyst"].calls == ["NEWCO"]
    assert [i.symbol for i in active(shelf_mod.ShelfStore())] == ["NEWCO"]


def test_cycle_without_any_listing_dives_nothing_and_says_why(tmp_path, monkeypatch):
    env = _cycle_env(tmp_path, monkeypatch, screen=[cand("NEWCO")])
    (tmp_path / "disc" / "listing.json").unlink()
    result = disc.run_discovery_cycle(on=date(2026, 7, 4))
    assert env["analyst"].calls == []
    assert any("instrument listing unavailable" in e for e in result["errors"])


@pytest.mark.parametrize("mode", ["record", "enforce"])
def test_cycle_remembers_an_abstained_new_dive_for_the_month(tmp_path, monkeypatch,
                                                             gate_mode, mode):
    """Rework 1 (R2). Week 1: X and Y are dived; X abstains, Y is shelved.
    Under enforce X is not shelved, and under record it falls below the
    floor, so either way X is off the shelf with its answer. On 11 Jul (7
    days) and 1 Aug (28 days) neither is dived again; on 8 Aug (35 days)
    X's memo entry has expired and it is dived once more."""
    monkeypatch.setattr(settings, "DISCOVERY_DEEP_DIVE_COUNT", 20)
    monkeypatch.setattr(settings, "DISCOVERY_REDIVE_AFTER_DAYS", 30)
    monkeypatch.setattr(settings, "DISCOVERY_STALE_DAYS", 60)
    gate_mode(mode)
    conv = {"X": 0.50 if mode == "record" else 0.70, "Y": 0.70}
    env = _cycle_env(tmp_path, monkeypatch, screen=[cand("X"), cand("Y")],
                     conviction=conv, gate={"X": "abstain"})
    first = disc.run_discovery_cycle(on=date(2026, 7, 4))
    assert env["analyst"].calls == ["X", "Y"]
    assert {i.symbol for i in active(shelf_mod.ShelfStore())} == {"Y"}
    assert first["shelf"].get("gated", []) == (["X"] if mode == "enforce" else [])
    memo = json.loads((tmp_path / "disc" / "dives.json").read_text(encoding="utf-8"))
    assert memo["X"] == {"date": "2026-07-04", "conviction": conv["X"], "verdict": "BUY",
                         "data_gate": "abstain"}
    for day in (date(2026, 7, 11), date(2026, 8, 1)):
        env["analyst"].calls.clear()
        again = disc.run_discovery_cycle(on=day)
        assert env["analyst"].calls == [], day
        assert again["hygiene"]["recently_dived"] == ["X", "Y"], day
    env["analyst"].calls.clear()
    disc.run_discovery_cycle(on=date(2026, 8, 8))
    # Y (dived 4 Jul, 35 days) is now due for its re-dive; X is a new dive again.
    assert sorted(env["analyst"].calls) == ["X", "Y"]


# ---------------------------------------------------------------------------
# Buy candidates: fresh shelf ideas and the user's own watchlist BUYs
# ---------------------------------------------------------------------------

D = date(2026, 7, 13)                     # a Monday


def record(verdict="BUY", score=0.80, run_at="2026-07-10T11:00:00", gate="actionable",
           thesis="Margins recovering."):
    """A score-history row: run_at is naive UTC (11:00 UTC = 16:30 IST)."""
    report = {"decision_gate": {"status": gate, "run_id": "r1", "reasons": []}} if gate \
        is not None else {}
    return {"ticker": "W", "run_at": run_at, "final_score": score, "verdict": verdict,
            "investment_thesis": thesis, "report_json": json.dumps(report)}


def portfolio(watch=(), holdings=()):
    return SimpleNamespace(
        holdings=[Holding(symbol=s, sector="x", qty=1, avg_buy_price=1, adj_avg_price=1,
                          adj_qty=1, buy_date="2026-06-01") for s in holdings],
        watchlist=[WatchlistItem(symbol=s, sector="pharma", added="2026-07-01", source=src)
                   for s, src in watch])


@pytest.fixture
def fresh_rules(monkeypatch):
    """The window rules, and infer_sector as a recorder: for a symbol outside
    the registry it would ask NSE's meta API, which the hermetic boundary
    refuses."""
    monkeypatch.setattr(settings, "DISCOVERY_REDIVE_AFTER_DAYS", 30)
    monkeypatch.setattr(settings, "DISCOVERY_STALE_DAYS", 60)
    monkeypatch.setattr(settings, "DISCOVERY_WATCHLIST_BUYS", True)
    monkeypatch.setattr(settings, "DISCOVERY_MIN_CONVICTION", 0.55)
    inferred: list[str] = []
    monkeypatch.setattr(cands_mod, "infer_sector",
                        lambda s: inferred.append(s) or "inferred")
    return inferred


def _run_candidates(rec, *, source="user", listing=None, close=500.0, on=D):
    window = _eod_window(["W"], days=60, end=date(2026, 7, 12), close=close)
    return cands_mod.buy_candidates(
        portfolio(watch=[("W", source)]), on, [], latest_analysis=lambda s: rec,
        window=window, listing=companies("W") if listing is None else listing)


def test_a_fresh_actionable_watchlist_buy_is_a_candidate(fresh_rules):
    out, excluded = _run_candidates(record(verdict="STRONG BUY", score=0.81))
    assert excluded == {}
    idea = out[0]
    assert (idea.symbol, idea.source, idea.verdict, idea.conviction) == \
        ("W", "watchlist", "STRONG BUY", 0.81)
    # Analysed 10 Jul (IST): its band is 97-102% of the 10 Jul close, 500.
    assert (idea.dived, idea.close_at_add, idea.entry_low, idea.entry_high) == \
        ("2026-07-10", 500.0, 485.0, 510.0)
    assert idea.invalidation_level < idea.entry_low
    assert (idea.data_gate, idea.sector) == ("actionable", "pharma")


@pytest.mark.parametrize("rec, why", [
    (record(gate="abstain"), "latest analysis data gate abstain"),
    (record(gate=None), "latest analysis data gate missing"),
    (record(verdict="HOLD"), "latest analysis is HOLD"),
    (record(score=0.54), "conviction 0.54 below 0.55"),
    # 12 Jun 11:00 UTC is 12 Jun IST: 31 days before 13 Jul.
    (record(run_at="2026-06-12T11:00:00"), "latest analysis of 2026-06-12 is 31 days old (limit 30)"),
    (None, "no analysis in the score history"),
])
def test_a_watchlist_stock_that_is_not_a_fresh_actionable_buy_is_not(fresh_rules, rec, why):
    out, excluded = _run_candidates(rec)
    assert out == [] and excluded == {"W": why}


def test_thirty_days_is_still_fresh(fresh_rules):
    # 13 Jun 20:00 UTC is 14 Jun 01:30 IST: 29 days. 12 Jun 20:00 UTC = 13 Jun IST: 30.
    out, _ = _run_candidates(record(run_at="2026-06-12T20:00:00"))
    assert [i.dived for i in out] == ["2026-06-13"]


def test_an_autopilot_exit_on_the_watchlist_does_not_qualify(fresh_rules):
    out, excluded = _run_candidates(record(), source="autopilot")
    assert out == [] and excluded == {"W": "sold onto the watchlist by the autopilot"}


def test_beside_a_users_own_pick_an_autopilot_exit_still_does_not_qualify(fresh_rules):
    """Both have a fresh, actionable BUY on record; only the user's own pick
    is offered, so the source check holds when the readers are loaded."""
    window = _eod_window(["A", "U"], days=60, end=date(2026, 7, 12), close=500.0)
    pf = SimpleNamespace(holdings=[], watchlist=[
        WatchlistItem(symbol="A", added="2026-07-01", source="autopilot"),
        WatchlistItem(symbol="U", added="2026-07-01", source="user")])
    out, excluded = cands_mod.buy_candidates(pf, D, [], latest_analysis=lambda s: record(),
                                             window=window, listing=companies("A", "U"))
    assert [i.symbol for i in out] == ["U"]
    assert excluded == {"A": "sold onto the watchlist by the autopilot"}


def test_only_autopilot_exits_left_reads_nothing(fresh_rules, monkeypatch):
    """The default readers (score history, EOD window, listing) are not even
    built when no watchlist item could qualify."""
    def refuse(what):
        return lambda *a, **k: pytest.fail(f"{what} was read")
    monkeypatch.setattr("services.data.stores.score_store.ScoreStore", refuse("score history"))
    monkeypatch.setattr("services.data.stores.eod_store.EodStore", refuse("EOD store"))
    monkeypatch.setattr("services.data.fetchers.bhavcopy.load_listing", refuse("listing"))
    pf = SimpleNamespace(holdings=[], watchlist=[
        WatchlistItem(symbol="A", added="2026-07-01", source="autopilot")])
    out, excluded = cands_mod.buy_candidates(pf, D, [])
    assert out == [] and excluded == {"A": "sold onto the watchlist by the autopilot"}


def test_a_promoted_shelf_idea_on_the_watchlist_does_qualify(fresh_rules):
    out, _ = _run_candidates(record(), source="discovery")
    assert [i.symbol for i in out] == ["W"]


def test_a_watchlist_fund_does_not_qualify(fresh_rules):
    out, excluded = _run_candidates(record(), listing={"W": REAL_ROWS["LIQUID1"]})
    assert out == [] and excluded == {"W": "NSE listing says fund, not a company"}


def test_a_held_or_shelved_watchlist_stock_is_not_offered_twice(fresh_rules):
    shelved = _idea("S", "2026-07-04")
    pf = SimpleNamespace(holdings=portfolio(holdings=["H"]).holdings,
                         watchlist=[WatchlistItem(symbol=s, added="2026-07-01")
                                    for s in ("H", "S")])
    out, excluded = cands_mod.buy_candidates(
        pf, D, [shelved], latest_analysis=lambda s: pytest.fail("not read"),
        window=pd.DataFrame(), listing={})
    assert out == [shelved] and excluded == {}


def test_a_shelf_idea_older_than_thirty_days_waits_for_its_redive(fresh_rules):
    ideas = [_idea("OLD", "2026-06-12"),                  # 31 days
             _idea("EDGE", "2026-06-13"),                 # 30 days
             _idea("REDIVED", "2026-05-01", dived="2026-07-11")]
    out, excluded = cands_mod.buy_candidates(portfolio(), D, ideas)
    assert [i.symbol for i in out] == ["EDGE", "REDIVED"]
    assert excluded == {"OLD": "deep dive of 2026-06-12 is older than 30 days; "
                               "waits for its re-dive"}


# -- the sector a candidate carries (rework 1, R1) -----------------------------
#
# A bought candidate is held under its sector: the advisor then reads
# VerdictStore(symbol, sector=holding.sector), while the daily review and the
# monthly forecast write PredictionStore(symbol, sector=<managed record's
# sector>) (scheduler.py, via get_active_tickers_with_sector), and
# promote_symbol keeps an existing managed record's sector. So the invariant
# is: a candidate's sector equals its managed record's when the stock is
# managed. The home page's PUT /ui/watchlist stores an item with no sector.

def _write_managed(entries):
    from services.api import log_buffer
    log_buffer.save_managed_tickers(entries)


def _sectorless(symbol, source="user"):
    return WatchlistItem(symbol=symbol, added="2026-07-01", source=source)


@pytest.mark.parametrize("managed, own, expected, inferred", [
    ({"W": "automobile"}, "", "automobile", []),        # the home page stores no sector
    ({"W": "automobile"}, "pharma", "automobile", []),  # the managed record's forecasts win
    ({}, " Pharma ", "pharma", []),                     # not managed: its own, as promotion keys it
    ({}, "", "inferred", ["W"]),                        # neither: the deep dive's rule
    ({}, "Auto Parts", "inferred", ["W"]),              # a malformed sector is not a key
    ({"W": ""}, "", "inferred", ["W"]),                 # an empty managed sector is none
])
def test_a_watchlist_candidate_carries_the_sector_its_forecasts_use(
        fresh_rules, managed, own, expected, inferred):
    window = _eod_window(["W"], days=60, end=date(2026, 7, 12), close=500.0)
    item = WatchlistItem(symbol="W", sector=own, added="2026-07-01")
    idea, why = cands_mod.watchlist_idea(item, D, lambda s: record(), window, companies("W"),
                                         managed)
    assert (why, idea.sector) == ("", expected)
    assert fresh_rules == inferred


def test_the_managed_record_is_read_from_the_managed_file_enabled_or_not(fresh_rules):
    """buy_candidates' default reader: a disabled (evicted) record still keys
    the stock, because promote_symbol re-enables it with its own sector; a
    record without a sector reads as the scheduler reads it ("automobile")."""
    _write_managed([{"sym": "W", "sector": "automobile", "enabled": False,
                     "origin": "watchlist", "cadence": "weekly"},
                    {"sym": "V", "enabled": True}])
    window = _eod_window(["W", "V"], days=60, end=date(2026, 7, 12), close=500.0)
    pf = SimpleNamespace(holdings=[], watchlist=[_sectorless("W"), _sectorless("V")])
    out, excluded = cands_mod.buy_candidates(pf, D, [], latest_analysis=lambda s: record(),
                                             window=window, listing=companies("W", "V"))
    assert excluded == {} and fresh_rules == []
    assert [(i.symbol, i.sector) for i in out] == [("W", "automobile"), ("V", "automobile")]


def test_reading_the_managed_sectors_never_writes_the_managed_file():
    """load_managed_tickers seeds a missing file; the candidates' reader must
    not (FIX-002's rule for read paths)."""
    from pathlib import Path
    from services.api import log_buffer
    assert not Path("data/managed_tickers.json").exists()
    assert log_buffer.managed_sectors() == {}
    assert not Path("data/managed_tickers.json").exists()


def test_a_shelf_idea_managed_under_another_sector_is_offered_under_the_managed_one(
        fresh_rules):
    """The same invariant for a shelf idea: the user added S on the portfolio
    screen under "pharma" (promote_symbol made the record) after the deep
    dive shelved it as "generic". Offered as a copy; the shelf is unchanged."""
    idea = _idea("S", "2026-07-04")
    out, _ = cands_mod.buy_candidates(portfolio(), D, [idea], managed={"S": "pharma"})
    assert [(i.symbol, i.sector, i.entry_low, i.conviction) for i in out] == \
        [("S", "pharma", 97.0, 0.7)]
    assert idea.sector == "generic"
    out, _ = cands_mod.buy_candidates(portfolio(), D, [idea], managed={})
    assert out == [idea] and fresh_rules == []


@pytest.mark.parametrize("managed_file", [True, False])
def test_a_home_page_watchlist_buy_counts_in_its_real_sector_for_the_cap(
        monkeypatch, managed_file):
    """Hand-worked. ₹10 L of equity: MARUTI and M&M (automobile) ₹1.4 L each,
    28%; ITCO ₹2.2 L; cash ₹5 L. HEROMOTOCO is on the home-page watchlist (no
    sector stored), a fresh BUY at ₹5,000. Under "automobile" the 30% cap
    leaves ₹20,000: 4 shares, and automobile ends at exactly 30%. As
    "generic" it would take the full 10% position: 20 shares, 38%.
    With the managed file, the record says "automobile"; without it, the real
    infer_sector finds HEROMOTOCO in the registry (no network)."""
    from core.portfolio import sizing
    monkeypatch.setattr(settings, "DISCOVERY_REDIVE_AFTER_DAYS", 30)
    monkeypatch.setattr(settings, "DISCOVERY_MIN_CONVICTION", 0.55)
    monkeypatch.setattr(settings, "ADVISOR_MAX_POSITION_PCT", 10.0)
    monkeypatch.setattr(settings, "ADVISOR_MAX_SECTOR_PCT", 30.0)
    if managed_file:
        _write_managed([{"sym": "HEROMOTOCO", "sector": "automobile", "enabled": True}])
    hold = lambda s, sec, v: Holding(symbol=s, sector=sec, qty=v / 1000.0,  # noqa: E731
                                     avg_buy_price=1000.0, adj_avg_price=1000.0,
                                     adj_qty=v / 1000.0, buy_date="2026-06-01")
    pf = SimpleNamespace(holdings=[hold("MARUTI", "automobile", 140_000),
                                   hold("M&M", "automobile", 140_000),
                                   hold("ITCO", "it_sector", 220_000)],
                         cash_deployable=500_000.0, watchlist=[])
    marks = {"MARUTI": 1000.0, "M&M": 1000.0, "ITCO": 1000.0}
    window = _eod_window(["HEROMOTOCO"], days=25, end=date(2026, 7, 10), close=5000.0)
    idea, why = cands_mod.watchlist_idea(_sectorless("HEROMOTOCO"), D,
                                         lambda s: record(score=0.8), window,
                                         companies("HEROMOTOCO"))
    assert (why, idea.sector) == ("", "automobile")
    size = sizing.size_buy(pf, marks, symbol="HEROMOTOCO", sector=idea.sector,
                           price=5000.0, wanted=100_000.0, floor_cash=10_000.0)
    assert size.qty == 4.0


# -- through the real 16:30 pipeline ----------------------------------------------

class _NoArtifacts:
    def __init__(self, *a, **k):
        pass

    def cycle_id_for(self, d):
        return "X_2026-07"

    def load_envelope(self, cid):
        return None

    def load_feedback_log(self, cid):
        return None


def _review_day(tmp_path, monkeypatch, *, ideas=(), watch=(), rec=None, mode="record",
                listing=None, watch_sector="pharma", managed=None):
    """ACMESOLAR cost 260 closes at 227 (-12.7% against its 12% stop): EXIT,
    or a SWITCH when a buy candidate qualifies (as in SA-050's end-to-end
    test). The candidate trades at 505 today; its band is 485-510.
    `managed` (a managed-tickers list) is written to the sandbox's managed
    file and the real promote_symbol runs; otherwise promotion is stubbed."""
    import core.delivery.alerts as alerts_mod
    import core.delivery.channels as channels_mod
    import core.portfolio.autopilot as ap
    import core.portfolio.pipeline as pipeline
    from core.portfolio.pricing import SessionClose
    from core.portfolio.store import PortfolioStore
    import backend.shared.pipeline.decision_gate as dg

    monkeypatch.setenv("ATLAS_ENABLED", "false")
    dg._warned.clear()
    monkeypatch.setattr(settings, "DECISION_GATE_MODE", mode)
    monkeypatch.setattr(settings, "ADVISOR_MAX_POSITION_PCT", 10.0)
    monkeypatch.setattr(settings, "ADVISOR_MAX_SECTOR_PCT", 30.0)
    monkeypatch.setattr(settings, "AUTOPILOT_MIN_CASH_FLOOR", 10000.0)
    monkeypatch.setattr(settings, "DISCOVERY_REDIVE_AFTER_DAYS", 30)
    monkeypatch.setattr(settings, "DISCOVERY_WATCHLIST_BUYS", True)
    monkeypatch.setattr(ap, "_today_ist", lambda: D)
    if managed is None:
        monkeypatch.setattr(ap, "promote_symbol", lambda *a, **k: {"status": "ok"})
    else:
        _write_managed(managed)
    reg = tmp_path / "instruments.yaml"
    reg.write_text("version: 1\ninstruments: {}\n", encoding="utf-8")
    monkeypatch.setenv("INSTRUMENT_REGISTRY_PATH", str(reg))

    store = PortfolioStore(user_id="u", base_dir=str(tmp_path / "pf"))
    p = store.load()
    p.holdings = [Holding(symbol="ACMESOLAR", sector="power", qty=1000, avg_buy_price=260.0,
                          adj_avg_price=260.0, adj_qty=1000, buy_date="2026-06-01"),
                  Holding(symbol="ITCO", sector="it_sector", qty=500, avg_buy_price=1000.0,
                          adj_avg_price=1000.0, adj_qty=500, buy_date="2026-06-01")]
    p.watchlist = [WatchlistItem(symbol=s, sector=watch_sector, added="2026-07-01", source=src)
                   for s, src in watch]
    p.cash_deployable, p.capital_in, p.autopilot = 273_000.0, 1_000_000.0, True
    store.save(p)

    prices = {"ACMESOLAR": 227.0, "ITCO": 1000.0, "CAND": 505.0, "W": 505.0}
    quote = lambda sym, d: (SessionClose(prices[sym], d, "agree"), d)  # noqa: E731
    monkeypatch.setattr(pipeline, "session_close", quote)
    monkeypatch.setattr(ap, "session_close", quote)
    monkeypatch.setattr(pipeline.settings, "PORTFOLIO_DATA_DIR", str(tmp_path / "pf"))
    monkeypatch.setattr(pipeline, "is_trading_day", lambda d: True)
    monkeypatch.setattr(pipeline, "sync_corp_actions", lambda s, d: {"applied": 0})
    monkeypatch.setattr(pipeline, "refresh_events_calendar", lambda syms: {"events": {}})
    monkeypatch.setattr(pipeline, "get_price_history", lambda t, years=1: None)
    monkeypatch.setattr(pipeline, "narrate", lambda rec, sig: "n")
    monkeypatch.setattr(pipeline, "VerdictStore", _NoArtifacts)
    monkeypatch.setattr("core.discovery.shelf.ShelfStore.load",
                        lambda self: Shelf(ideas=list(ideas)))

    class _Scores:
        def get_latest(self, symbol):
            return rec if symbol == "W" else None
    window = _eod_window(["W"], days=25, end=date(2026, 7, 10), close=500.0)

    class _Eod:
        def load_window(self, end, sessions):
            return window
    monkeypatch.setattr("services.data.stores.score_store.ScoreStore", _Scores)
    monkeypatch.setattr("services.data.stores.eod_store.EodStore", _Eod)
    monkeypatch.setattr("services.data.fetchers.bhavcopy.load_listing",
                        lambda: companies("W", "CAND") if listing is None else listing)
    monkeypatch.setattr(alerts_mod, "emit_alerts", lambda events, **k: {"emitted": 0})
    monkeypatch.setattr(channels_mod, "deliver", lambda *a, **k: {"delivered": False})

    result = pipeline.run_post_review_pipeline(D)
    assert result["status"] == "completed"
    advice = {a.symbol: a for a in store.load_advice()}["ACMESOLAR"]
    buys = [t.symbol for t in store.load_transactions() if t.side == "BUY"]
    return advice, buys


@pytest.mark.parametrize("mode", ["record", "enforce"])
def test_pipeline_buys_a_fresh_watchlist_buy_as_the_switch_destination(
        tmp_path, monkeypatch, mode):
    advice, buys = _review_day(tmp_path, monkeypatch, watch=[("W", "user")],
                               rec=record(score=0.90), mode=mode)
    assert (advice.verdict, advice.switch_candidate) == ("SWITCH", "W")
    assert buys == ["W"]


@pytest.mark.parametrize("rec, source", [
    (record(score=0.90, gate="abstain"), "user"),           # abstained: never offered
    (record(score=0.90, run_at="2026-06-01T11:00:00"), "user"),   # 42 days old
    (record(score=0.90), "autopilot"),                      # the autopilot's own exit
])
def test_pipeline_never_switches_into_an_unqualified_watchlist_stock_even_in_record_mode(
        tmp_path, monkeypatch, rec, source):
    """Record mode keeps the ungated decision for a shelf idea; a watchlist
    stock cannot use that door: it is not offered at all."""
    advice, buys = _review_day(tmp_path, monkeypatch, watch=[("W", source)], rec=rec,
                               mode="record")
    assert advice.verdict == "EXIT" and buys == []


MANAGED = [
    {"sym": "ACMESOLAR", "sector": "power", "enabled": True, "origin": "held", "cadence": "daily"},
    {"sym": "ITCO", "sector": "it_sector", "enabled": True, "origin": "held", "cadence": "daily"},
]


@pytest.mark.parametrize("w_record, watch_sector, held_as", [
    # The home page's watchlist item (no sector) of a managed ticker: rework 1, R1.
    ({"sector": "automobile", "enabled": True, "origin": "watchlist", "cadence": "weekly"},
     "", "automobile"),
    # Evicted from the managed list earlier: promote_symbol re-enables it as is.
    ({"sector": "automobile", "enabled": False, "origin": "watchlist", "cadence": "weekly"},
     "", "automobile"),
    # Not managed yet: the item's own sector, and promote_symbol creates that record.
    (None, "pharma", "pharma"),
])
def test_pipeline_holds_a_watchlist_buy_under_the_key_its_forecasts_use(
        tmp_path, monkeypatch, w_record, watch_sector, held_as):
    """T1, through the real 16:30 pipeline with the real promote_symbol and a
    managed file. After the SWITCH buy, the holding's sector is the sector
    the daily review and the monthly forecast pass for W (scheduler.py reads
    get_active_tickers_with_sector), so the advisor's VerdictStore and the
    daily review's PredictionStore are one directory."""
    import core.portfolio.promotion as promotion
    from core.intelligence.rl.stores.prediction_store import PredictionStore
    from core.portfolio.store import PortfolioStore
    from services.api import log_buffer
    monkeypatch.setattr(promotion, "resolve_company_name", lambda s: f"{s} Ltd")
    managed = MANAGED + ([{"sym": "W", **w_record}] if w_record else [])
    advice, buys = _review_day(tmp_path, monkeypatch, watch=[("W", "user")],
                               rec=record(score=0.90), watch_sector=watch_sector,
                               managed=managed)
    assert (advice.verdict, advice.switch_candidate, buys) == ("SWITCH", "W", ["W"])
    held = {h.symbol: h for h in
            PortfolioStore(user_id="u", base_dir=str(tmp_path / "pf")).load().holdings}
    reviewed = {e["sym"]: e["sector"] for e in log_buffer.get_active_tickers_with_sector()}
    assert (held["W"].sector, reviewed["W"]) == (held_as, held_as)
    assert PredictionStore("W", sector=held["W"].sector)._dir == \
        PredictionStore("W", sector=reviewed["W"])._dir
    origin = {t["sym"]: t.get("origin") for t in log_buffer.load_managed_tickers()}
    assert origin["W"] == "held"


def test_pipeline_does_not_buy_a_stale_shelf_idea_until_it_is_redived(tmp_path, monkeypatch):
    stale = ShelfIdea(symbol="CAND", sector="pharma", added="2026-06-01", conviction=0.9,
                      entry_low=485.0, entry_high=510.0, invalidation_level=450.0,
                      data_gate="actionable")
    advice, buys = _review_day(tmp_path, monkeypatch, ideas=[stale])
    assert advice.verdict == "EXIT" and buys == []

    redived = stale.model_copy(update={"dived": "2026-07-11"})
    (tmp_path / "again").mkdir()
    advice, buys = _review_day(tmp_path / "again", monkeypatch, ideas=[redived])
    assert (advice.verdict, advice.switch_candidate) == ("SWITCH", "CAND")
    assert buys == ["CAND"]


# ---------------------------------------------------------------------------
# The scorecard's idea-quality line
# ---------------------------------------------------------------------------

def shelf_grade(added, sym, horizon, excess, graded_on):
    return AuditOutcome(
        ref=f"shelf:{added}|{sym}", lane="shelf", user_id="u1", symbol=sym, issued_on=added,
        horizon_td=horizon, graded_on=graded_on, entry_close=100.0, exit_close=100.0,
        return_pct=0.0, bench_entry=1.0, bench_exit=1.0, bench_pct=0.0, excess_pct=excess,
        correct=None, graded_at="2026-01-01T00:00:00+00:00", conviction=0.7)


def test_idea_quality_counts_shelf_grades_that_matured_by_the_week_end():
    sunday = date(2026, 3, 8)
    rows = [
        shelf_grade("2026-01-05", "A", 30, +4.0, "2026-02-16"),
        shelf_grade("2026-01-05", "B", 30, -1.0, "2026-02-16"),
        shelf_grade("2026-01-12", "C", 30, +2.0, "2026-02-23"),
        shelf_grade("2026-02-02", "D", 30, +9.0, "2026-03-16"),   # matures after the week
        shelf_grade("2026-02-16", "A2", 10, -3.0, "2026-03-02"),
        shelf_grade("2026-02-16", "A2", 10, -3.0, "2026-03-02"),  # a duplicate row
        shelf_grade("2026-02-16", "B2", 10, +1.0, "2026-03-02"),
        AuditOutcome(ref="2026-01-05|X|h", lane="advice", user_id="u1", symbol="X",
                     verdict="EXIT", issued_on="2026-01-05", horizon_td=30,
                     graded_on="2026-02-16", entry_close=1, exit_close=1, return_pct=0,
                     bench_entry=1, bench_exit=1, bench_pct=0, excess_pct=50.0,
                     correct=False, graded_at="2026-01-01T00:00:00+00:00"),
    ]
    row = R.build_row(week=R.covered_week(sunday), txns=[], points=[], audit_rows=rows,
                      close_on=lambda d: 100.0, holdings=0,
                      computed_at="2026-01-01T00:00:00+00:00")
    # 30 sessions: A +4, B -1, C +2 -> 2 of 3 beat it, median +2.0. D is next week's.
    # 10 sessions: A2 -3 (once), B2 +1 -> 1 of 2, median (-3 + 1) / 2 = -1.0.
    assert row["idea_quality"] == [
        {"horizon_td": 10, "graded": 2, "beat": 1, "share_pct": 50.0, "median_excess_pct": -1.0},
        {"horizon_td": 30, "graded": 3, "beat": 2, "share_pct": 66.67, "median_excess_pct": 2.0},
    ]
    line = next(x for x in row["lines"] if x.get("label") == "Idea quality")
    assert line["text"] == ("Shelf ideas against the Nifty after they were shelved: at 30 "
                            "sessions 2 of 3 beat it (67%, median +2.0 points); at 10 sessions "
                            "1 of 2 beat it (50%, median -1.0 points).")
    text = R.render_scorecard_text(row)
    assert "Idea quality: Shelf ideas against the Nifty" in "\n".join(text)


def test_idea_quality_with_no_grades_says_so_and_an_old_row_still_renders():
    row = R.build_row(week=R.covered_week(date(2026, 3, 8)), txns=[], points=[],
                      audit_rows=[], close_on=lambda d: 100.0, holdings=0,
                      computed_at="2026-01-01T00:00:00+00:00")
    line = next(x for x in row["lines"] if x.get("label") == "Idea quality")
    assert line["text"] == "No shelf idea has been graded against the Nifty yet."
    old = {k: v for k, v in row.items() if k != "idea_quality"}       # stored before PR-004
    assert all(x.get("label") != "Idea quality" for x in R.scorecard_lines(old))
