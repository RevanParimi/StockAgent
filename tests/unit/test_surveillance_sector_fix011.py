"""FIX-011 — NSE's per-symbol meta API is gone.

- The ASM/GSM and suspension gates read NSE's daily Surveillance Indicator
  report, once a run, dated on or before the screen's latest session.
- A source that answers for no symbol is one dark check a run, the weekly
  summary names it, and the watchdog warns once it lasts a week.
- Yahoo's classification is stored beside every dive as evidence; since
  FIX-026 the analysis names the key (tests/unit/test_sector_naming_fix026.py),
  and a managed record's sector and a shelf idea's named key are never re-keyed.

No test reaches the network: the NSE client and Yahoo are fakes
(tests/hermetic.py fails any test that tries).
"""
from __future__ import annotations

import json
import random
from datetime import date, timedelta
from types import SimpleNamespace

import pandas as pd
import pytest

import core.discovery as disc
import core.discovery.candidates as cands_mod
import core.discovery.guards as guards
import services.data.fetchers.surveillance as surv
from backend.sectors.registry import TICKER_SECTOR
from backend.shared.schemas.discovery import (
    DeepDiveResult, ScreenResult, SectorReading, Shelf, ShelfIdea,
)
from core.config import settings
from core.discovery.shelf import ShelfStore
from core.intelligence.rl.stores.prediction_store import PredictionStore
from core.ops.watchdog import checks as wd

# The first 19 of the report's 63 columns, as NSE published them on 29 Oct 2026.
HEADER = ("ScripCode,Symbol,Nse Exclusive,Status,Series,GSM,"
          "Long_Term_Additional_Surveillance_Measure (Long Term ASM),Unsolicited_SMS,"
          "Insolvency_Resolution_Process(IRP),"
          "Short_Term_Additional_Surveillance_Measure (Short Term ASM),Default,ICA,Filler4,"
          "Filler5,Pledge,Add-on_PB,Total Pledge,Social Media Platforms,ESM")
# Positions in that layout, read off NSE's header, not off the code under test.
STATUS, GSM, LT_ASM, IRP, ST_ASM, ESM = 3, 5, 6, 8, 9, 18

FRI = date(2026, 10, 30)          # a Friday session; 29 Oct is the Thursday before


def _row(symbol, status="A", series="EQ", **stages) -> str:
    cells = ["NA", symbol, "N", status, series] + ["100"] * 14
    cells[12] = cells[13] = ""                                  # Filler4, Filler5
    for name, value in stages.items():
        cells[{"gsm": GSM, "lt": LT_ASM, "irp": IRP, "st": ST_ASM, "esm": ESM}[name]] = value
    return ",".join(cells)


def _report(*rows) -> str:
    return "\n".join((HEADER,) + rows) + "\n"


REPORT_29 = _report(
    _row("MARUTI"),                       # under no measure
    _row("A2ZINFRA", lt="1"),             # long-term ASM stage I (true on 29 Oct)
    _row("GSMZERO", gsm="0"),             # GSM stage 0 is a stage, not "none"
    _row("STASM", st="2"),
    _row("SUSPCO", status="S", series="BZ"),
    _row("IBCCO", irp="1"),               # insolvency only: not an ASM/GSM gate
    _row("ESMCO", esm="1"),               # ESM only: not an ASM/GSM gate
    ",,N,A,EQ" + ",100" * 14,             # a row without a symbol
)


class _FakeNSE:
    """Answers the archive files it holds; 404 for any other (NSE's answer
    before a day's report is published)."""

    def __init__(self, files: dict[str, str]):
        self.files, self.asked, self.closed = files, [], False

    def _req(self, url, params=None):
        name = url.rsplit("/", 1)[-1]
        self.asked.append(name)
        if name not in self.files:
            raise ConnectionError(f"{url} 404: Not Found")
        return SimpleNamespace(content=self.files[name].encode("utf-8"))

    def exit(self):
        self.closed = True


@pytest.fixture
def nse(monkeypatch, tmp_path):
    """The fetcher's NSE client is `env.client` (None: NSE cannot be reached)."""
    monkeypatch.setattr(settings, "DISCOVERY_DATA_DIR", str(tmp_path / "discovery"))
    monkeypatch.setattr(surv.time, "sleep", lambda s: None)
    env = SimpleNamespace(client=_FakeNSE({}), made=0)

    def make():
        env.made += 1
        if env.client is None:
            raise ConnectionError("nseindia.com unreachable")
        return env.client
    monkeypatch.setattr(surv, "_make_nse_client", make)
    return env


def _cache(tmp_path) -> dict:
    return json.loads((tmp_path / "discovery" / "surveillance.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# The report
# ---------------------------------------------------------------------------

def test_the_report_reads_each_measure_and_the_status():
    assert surv.parse_surveillance(REPORT_29) == {
        "MARUTI": {"status": "A", "measures": []},
        "A2ZINFRA": {"status": "A", "measures": ["LT-ASM"]},
        "GSMZERO": {"status": "A", "measures": ["GSM"]},
        "STASM": {"status": "A", "measures": ["ST-ASM"]},
        "SUSPCO": {"status": "S", "measures": []},
        "IBCCO": {"status": "A", "measures": []},
        "ESMCO": {"status": "A", "measures": []},
    }


def test_a_report_without_a_needed_column_is_no_report():
    """A renamed column must not read as "under no measure"."""
    renamed = REPORT_29.replace(",GSM,", ",GSM Stage,", 1)
    assert surv.parse_surveillance(renamed) is None


def test_the_newest_report_on_or_before_the_session_is_used_and_cached(nse, tmp_path):
    nse.client.files = {"REG1_IND291026.csv": REPORT_29}
    securities, as_of = surv.surveillance_list(FRI)
    assert as_of == "2026-10-29" and securities["A2ZINFRA"]["measures"] == ["LT-ASM"]
    assert nse.client.asked == ["REG1_IND301026.csv", "REG1_IND291026.csv"]
    assert nse.client.closed
    assert _cache(tmp_path)["as_of"] == "2026-10-29"

    nse.client = _FakeNSE({})                   # the cache serves its own day: no request
    assert surv.surveillance_list(date(2026, 10, 29)) == (securities, "2026-10-29")
    assert nse.client.asked == [] and nse.made == 1


def test_a_report_dated_after_the_session_is_never_used(nse):
    """A replay of the 28 Oct screen must not see what NSE published on 29 or
    30 Oct, from the archive or from the cache."""
    nse.client.files = {"REG1_IND301026.csv": REPORT_29}
    assert surv.surveillance_list(FRI)[1] == "2026-10-30"          # now cached
    nse.client = _FakeNSE({"REG1_IND291026.csv": REPORT_29, "REG1_IND301026.csv": REPORT_29})
    assert surv.surveillance_list(date(2026, 10, 28)) == (None, None)
    assert not {"REG1_IND291026.csv", "REG1_IND301026.csv"} & set(nse.client.asked)


def test_a_cached_report_serves_for_seven_days_and_no_longer(nse):
    nse.client.files = {"REG1_IND301026.csv": REPORT_29}
    securities, _ = surv.surveillance_list(FRI)
    nse.client = None                                                # NSE down from here
    assert surv.surveillance_list(date(2026, 11, 6)) == (securities, "2026-10-30")
    assert surv.surveillance_list(date(2026, 11, 9)) == (None, None)


def test_a_run_makes_at_most_five_requests(nse):
    assert surv.surveillance_list(FRI) == (None, None)
    assert nse.client.asked == ["REG1_IND301026.csv", "REG1_IND291026.csv",
                                "REG1_IND281026.csv", "REG1_IND271026.csv",
                                "REG1_IND261026.csv"]
    assert nse.made == 1 and nse.client.closed


# ---------------------------------------------------------------------------
# The gates
# ---------------------------------------------------------------------------

def _window(symbols, end=FRI, n=70) -> pd.DataFrame:
    rows = []
    for s in symbols:
        for i in range(n):
            rows.append({"symbol": s, "series": "EQ",
                         "date": (end - timedelta(days=n - 1 - i)).isoformat(),
                         "prev_close": 100.0, "open": 100.0, "high": 101.0, "low": 99.0,
                         "close": 100.0, "volume": 10000.0, "traded_value_cr": 6.0,
                         "delivery_qty": 4000.0, "delivery_pct": 40.0})
    return pd.DataFrame(rows)


@pytest.fixture
def gates(nse, monkeypatch):
    monkeypatch.setattr(guards, "float_mcap_cr", lambda s: 2000.0)
    monkeypatch.setattr(guards, "pledge_snapshots", lambda symbols: {})   # one pledge check
    return nse


def test_a_fixture_list_rejects_listed_symbols_and_passes_the_others(gates):
    gates.client.files = {"REG1_IND291026.csv": REPORT_29}
    symbols = ["MARUTI", "A2ZINFRA", "GSMZERO", "STASM", "SUSPCO", "IBCCO", "ESMCO", "NEWLIST"]
    passed, rejected, degraded = guards.apply_guards(symbols, _window(symbols))
    assert passed == ["MARUTI", "IBCCO", "ESMCO", "NEWLIST"]
    assert rejected == {"A2ZINFRA": ["surveillance_asm_gsm"],
                        "GSMZERO": ["surveillance_asm_gsm"],
                        "STASM": ["surveillance_asm_gsm"],
                        "SUSPCO": ["suspended"]}
    assert degraded == ["promoter_pledge", "surveillance:NEWLIST"]     # not in NSE's report


def test_no_report_is_one_dark_check_and_the_gates_then_pass_every_symbol(gates):
    """The hard-review question: with the source down, can an ASM stock reach
    the shelf? Yes, and visibly: one `surveillance` check, never one per
    symbol, and the watchdog warns after a week (below)."""
    gates.client = None
    symbols = ["MARUTI", "A2ZINFRA", "SUSPCO"]
    passed, rejected, degraded = guards.apply_guards(symbols, _window(symbols))
    assert passed == symbols and rejected == {}
    assert degraded == ["promoter_pledge", "surveillance"]


def test_a_per_symbol_source_that_answers_for_no_symbol_is_one_check(gates, monkeypatch):
    gates.client.files = {"REG1_IND291026.csv": _report(_row("SOMEONEELSE"))}
    monkeypatch.setattr(guards, "float_mcap_cr", lambda s: None)
    symbols = ["AAA", "BBB", "CCC"]
    window = _window(symbols)
    _, _, degraded = guards.apply_guards(symbols + ["NOHISTORY"], window)
    assert sorted(degraded) == ["float_mcap", "promoter_pledge", "surveillance"]

    monkeypatch.setattr(guards, "float_mcap_cr", lambda s: 2000.0 if s == "BBB" else None)
    _, _, degraded = guards.apply_guards(symbols, window)
    assert "float_mcap:AAA" in degraded and "float_mcap:CCC" in degraded
    assert "float_mcap" not in degraded                         # BBB answered


def test_the_report_is_asked_for_once_a_run_for_the_windows_session(monkeypatch):
    asked = []
    monkeypatch.setattr(guards, "surveillance_list",
                        lambda session: asked.append(session) or ({}, None))
    monkeypatch.setattr(guards, "float_mcap_cr", lambda s: 2000.0)
    monkeypatch.setattr(guards, "pledge_snapshots", lambda symbols: {})
    symbols = ["AAA", "BBB", "CCC"]
    guards.apply_guards(symbols, _window(symbols, end=date(2026, 9, 4)))
    assert asked == [date(2026, 9, 4)]                  # the session, not the wall clock

    asked.clear()                                       # nothing shortlisted: nothing asked,
    _, _, degraded = guards.apply_guards([], _window(symbols))     # and nothing called dark
    assert asked == [] and "surveillance" not in degraded


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
def test_property_a_symbol_passes_iff_nse_shows_it_active_under_no_asm_or_gsm(gates, seed):
    """Random reports through the whole path (archive file -> cache -> gates)
    against an oracle that reads NSE's column positions directly."""
    rng = random.Random(seed)
    stage = ["100"] * 8 + ["0", "1", "2", "3", "4", "6", ""]
    raw: dict[str, list[str]] = {}
    for i in range(150):
        cells = ["NA", f"SYM{i:03d}", "N", rng.choice("AAAAAAS"), "EQ"] + [
            rng.choice(stage) for _ in range(14)]
        raw[cells[1]] = cells
    gates.client.files = {"REG1_IND301026.csv": "\n".join(
        [HEADER] + [",".join(c) for c in raw.values()]) + "\n"}
    symbols = list(raw) + ["NOTLISTED"]
    passed, rejected, degraded = guards.apply_guards(symbols, _window(symbols, n=61))

    for sym, cells in raw.items():
        expected = ([] if all(cells[p] in ("100", "") for p in (GSM, LT_ASM, ST_ASM))
                    else ["surveillance_asm_gsm"]) + ([] if cells[STATUS] == "A"
                                                      else ["suspended"])
        assert rejected.get(sym, []) == expected, sym
        assert (sym in passed) == (not expected), sym
    assert "NOTLISTED" in passed and "surveillance:NOTLISTED" in degraded
    assert not any(d.startswith("surveillance:SYM") for d in degraded)


# ---------------------------------------------------------------------------
# The weekly summary and the watchdog
# ---------------------------------------------------------------------------

def test_the_weekly_summary_names_the_checks_dark_for_the_whole_run(monkeypatch, tmp_path):
    screen = ScreenResult(screen_date="2026-10-30", universe_size=1800, shortlist_size=80,
                          degraded_checks=["instrument_listing",
                                           "insider_buying: 3 of 10 filings unread",
                                           "surveillance", "float_mcap:ACME",
                                           "promoter_pledge:ACME"])
    monkeypatch.setattr(settings, "DISCOVERY_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "DISCOVERY_IPO_ENABLED", False)
    for name, value in {"sync_recent": {}, "refresh_bulk_block": {}, "load_listing": None,
                        "refresh_insider_trades": {}, "run_deep_dives": [],
                        "refresh_listing": {"as_of": None, "fresh": False, "securities": 0},
                        "run_paper_reviews": {"reviewed": [], "failed": [], "skipped": []},
                        "run_screen": screen}.items():
        monkeypatch.setattr(disc, name, lambda *a, _v=value, **k: _v)
    result = disc.run_discovery_cycle(on=date(2026, 10, 31))
    assert result["dark_checks"] == ["instrument_listing",
                                     "insider_buying: 3 of 10 filings unread", "surveillance"]


def _write_screen(base, day, checks, shortlist=80):
    d = base / "screens"
    d.mkdir(parents=True, exist_ok=True)
    rec = ScreenResult(screen_date=day, universe_size=1800, shortlist_size=shortlist,
                       degraded_checks=checks)
    (d / f"{day}_screen.json").write_text(rec.model_dump_json(), encoding="utf-8")


@pytest.fixture
def screens(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "DISCOVERY_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "DISCOVERY_PLEDGE_GUARD", True)
    return tmp_path


def test_the_watchdog_warns_when_a_source_is_dark_in_two_screens_a_week_apart(screens):
    _write_screen(screens, "2026-10-16", ["surveillance:ABC"])
    _write_screen(screens, "2026-10-23", ["surveillance", "float_mcap"])
    _write_screen(screens, "2026-10-30", ["surveillance", "promoter_pledge:XYZ"])
    res = wd.run_check("discovery_guard_sources")
    assert res.state == "pending"
    assert res.detail == ("surveillance dark in every screen from 2026-10-23 to 2026-10-30: "
                          "the ASM/GSM and suspension gates pass every symbol.")
    assert res.evidence["dark_since"] == {"surveillance": "2026-10-23"}


@pytest.mark.parametrize("history", [
    [("2026-10-23", ["float_mcap:A"]), ("2026-10-30", ["surveillance"])],   # dark once
    [("2026-10-23", ["surveillance"]), ("2026-10-30", [])],                 # recovered
    [("2026-10-23", ["surveillance"]), ("2026-10-26", ["surveillance"])],   # 3 days
    [("2026-10-23", ["surveillance"]), ("2026-10-30", ["surveillance"], 0)],  # no guards
    [],
])
def test_the_watchdog_stays_quiet_under_a_week_or_after_recovery(screens, history):
    for day, checks, *shortlist in history:
        _write_screen(screens, day, checks, *shortlist)
    assert wd.run_check("discovery_guard_sources").state == "satisfied"


def test_the_pledge_source_is_judged_only_while_its_guard_is_on(screens, monkeypatch):
    _write_screen(screens, "2026-10-23", ["promoter_pledge"])
    _write_screen(screens, "2026-10-30", ["promoter_pledge"])
    assert wd.run_check("discovery_guard_sources").state == "pending"
    monkeypatch.setattr(settings, "DISCOVERY_PLEDGE_GUARD", False)      # off: dark on purpose
    assert wd.run_check("discovery_guard_sources").state == "satisfied"


def test_the_registry_watches_the_guard_sources():
    from core.ops.watchdog.registry import load_registry
    from core.ops.watchdog.checks import CHECKS
    entry = {e.id: e for e in load_registry("config/milestones.yaml")}[
        "discovery_guard_sources_live"]
    assert entry.kind == "invariant" and entry.check in CHECKS


# ---------------------------------------------------------------------------
# The industry source (FIX-026: evidence for the analysis, never a key)
# ---------------------------------------------------------------------------
#
# FIX-011's Yahoo-to-key tables (`sector_from_classification`, `infer_sector`)
# are gone: the deep dive's analysis names the key from the configured list
# (tests/unit/test_sector_naming_fix026.py pins the naming, the graph guess and
# the routing). What FIX-011 promised and still holds is below.

def test_an_existing_holdings_store_is_never_rekeyed(monkeypatch, tmp_path):
    """The hard-review question: a stock held under "generic" keeps its
    managed sector, so its forecasts stay in data/predictions/generic/<SYMBOL>;
    nothing else is asked."""
    monkeypatch.setattr(cands_mod, "ticker_map_sector",
                        lambda s: pytest.fail("a managed stock's sector was looked up again"))
    sector = cands_mod.holding_sector("CHEMCO", "", {"CHEMCO": "generic"})
    assert sector == "generic"
    store = PredictionStore("CHEMCO", sector=sector, base_dir=str(tmp_path))
    assert store._dir == tmp_path / "generic" / "CHEMCO"


def _redive(symbol, key, *, source="analysis", answer=None):
    return DeepDiveResult(symbol=symbol, sector=key, graph="generic", conviction=0.7,
                          verdict="BUY", thesis="t", entry_low=97.0, entry_high=102.0,
                          invalidation_level=85.0, close=100.0, composite=0.0,
                          dive_date="2026-10-31", data_gate="actionable",
                          market_sector="Basic Materials", industry="Specialty Chemicals",
                          sector_reading=SectorReading(answer=answer or key, source=source))


def test_a_named_ideas_key_and_paper_store_survive_its_redive(monkeypatch, tmp_path):
    """A re-dive refreshes the idea's market classification and its reading,
    never a named key: its paper-lane store (keyed by sector) stays where it
    is, and it is bought under that same key. The answer is recorded."""
    monkeypatch.setattr(settings, "DISCOVERY_DATA_DIR", str(tmp_path))
    store = ShelfStore()
    store.save(Shelf(ideas=[ShelfIdea(
        symbol="CHEMCO", sector="chemicals", added="2026-09-05", conviction=0.6,
        data_gate="actionable", sector_reading=SectorReading(answer="chemicals"))]))
    # The dive kept the earlier key and recorded the other answer.
    dive = _redive("CHEMCO", "chemicals", source="earlier", answer="agrochem")
    assert store.apply_redives([dive], on=date(2026, 10, 31))["refreshed"] == ["CHEMCO"]
    idea = store.load().ideas[0]
    assert (idea.sector, idea.industry) == ("chemicals", "Specialty Chemicals")
    assert idea.sector_reading.answer == "agrochem"
    assert cands_mod.holding_sector("CHEMCO", idea.sector, {}) == "chemicals"


def test_an_idea_shelved_as_generic_is_named_by_its_redive(monkeypatch, tmp_path):
    """FIX-026: an idea with no key (here shelved as "generic" before the
    analysis named sectors) takes the key its re-dive names; its paper lane
    then writes under the new key (the card accepts that split for an idea
    no portfolio holds)."""
    monkeypatch.setattr(settings, "DISCOVERY_DATA_DIR", str(tmp_path))
    store = ShelfStore()
    store.save(Shelf(ideas=[ShelfIdea(symbol="CHEMCO", sector="generic", added="2026-09-05",
                                      conviction=0.6, data_gate="actionable")]))
    store.apply_redives([_redive("CHEMCO", "chemicals")], on=date(2026, 10, 31))
    idea = store.load().ideas[0]
    assert (idea.sector, idea.sector_reading.source) == ("chemicals", "analysis")


def test_a_watchlist_stock_outside_the_ticker_map_needs_a_key(monkeypatch):
    """PR-004 re-review RR-L1, under FIX-026: CEATLTD is outside the ticker
    map. Managed under "automobile" (the home page's record), it is held as
    "automobile" and SA-050's cap counts it with MARUTI and M&M. Not managed
    and with no configured key of its own, no Yahoo table names one: it is
    not offered (`watchlist_idea` says why)."""
    assert "CEATLTD" not in TICKER_SECTOR
    assert cands_mod.holding_sector("CEATLTD", "", {"CEATLTD": "automobile"}) == "automobile"
    assert cands_mod.holding_sector("CEATLTD", "automobile", {}) == "automobile"
    assert cands_mod.holding_sector("CEATLTD", "", {}) == ""
