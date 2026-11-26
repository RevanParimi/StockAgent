"""FIX-030 — a generic-graph analysis sees no automobile evidence; a key the
old Yahoo table set is re-examined; an unnamed idea stops taking a weekly
re-dive; the peer cache never stores a hidden failure and keeps both
workers' fills.

Expected results are worked out by hand from the card's examples (the
comments say how), never asked of the code under test. The analyst is the
FIX-026 stub world (no LLM); Yahoo, mfapi.in and NSE are stubs; every other
transport is blocked by tests/hermetic.py; each test runs in its own sandbox.

Decisions (receipt evidence/FIX-030-implementation.md):
  D1 (R1) a Yahoo answer with a market cap and neither an industry nor a
     sector is a failed profile call: raised, never stored.
  D2 (R2) a save takes a file lock, merges with the file (the later lookup
     wins) and writes atomically.
  D3 (M2) a sector with no ETF list reads none: "no sector ETFs".
  D4 (L1) an idea's configured key is decided only by an analysis (carried as
     `named_on`), a managed record or the ticker map; a table-set key joins
     the first re-dive group and is named by that analysis.
  D5 (L2) the second re-dive in a row that leaves an idea unnamed drops it.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

import core.discovery.deep_dive as dd
import core.discovery.shelf as shelf_mod
from backend.shared.schemas.discovery import (
    DiscoveryCandidate, SectorReading, Shelf, ShelfIdea,
)
from core.config import settings
from core.discovery import candidates as cands_mod
from core.discovery import sector_naming as sn
from core.ops.watchdog import checks as wd
from core.schemas.pipeline import StockQuery
from services.data.context import bundle_builder as bb
from services.data.context import fetch_result as fr
from services.data.context import peers as P
from services.data.fetchers import mf_herding as mf
from tests.unit.test_peer_choice_sa044 import PHARMA, market  # noqa: F401  (a fixture)
from tests.unit.test_sector_naming_fix026 import (  # noqa: F401  (world is a fixture)
    DRUG_YAHOO, MON, ON, ask, run, world,
)

REPO = Path(__file__).resolve().parents[2]
HOSP_YAHOO = {"sector": "Healthcare", "industry": "Medical Care Facilities"}
PF = SimpleNamespace(holdings=[], watchlist=[])
DAY = date(2026, 11, 12)

# Every automobile name the generic bundle used to carry: the five car makers
# of the old peer list and the three auto ETFs' names (hand copied).
AUTO_NAMES = ("MARUTI", "TATAMOTORS", "M&M", "HEROMOTOCO", "BAJAJ-AUTO",
              "Nifty Auto", "Auto ETF")
# The native graphs' ETF scheme codes, hand copied from AMFI's registrations.
NATIVE_ETFS = {
    "automobile": [148620, 149075, 148553],
    "banking_bfsi": [102885, 120716, 120717],
    "it_sector": [120706, 101485, 143534],
    "renewable_energy": [149365, 150716],
}


# ===========================================================================
# M2: the generic bundle carries no other sector's peers or ETF flows
# ===========================================================================

@pytest.fixture
def navs(monkeypatch):
    """mfapi.in stub: every scheme rose 2% over the window. Records codes."""
    asked: list[int] = []

    def history(code, days=40):
        asked.append(code)
        return [{"date": "2026-10-12", "nav": 100.0}, {"date": "2026-11-11", "nav": 102.0}]
    monkeypatch.setattr(mf, "_fetch_nav_history", history)
    monkeypatch.setattr(mf, "_CACHE", {})
    return asked


@pytest.mark.parametrize("sector", ["generic", "pharma", "hospitals", ""])
def test_m2_a_sector_without_an_etf_list_reads_no_funds_and_calls_nothing(navs, sector):
    out = mf.get_sector_mf_herding(sector)
    assert navs == []                                   # no fund of any sector is read
    assert out["error"] == mf.NO_SECTOR_ETFS == "no_sector_etfs"
    assert out["individual"] == [] and out["fund_count"] == 0
    assert mf.format_mf_herding_context(out) == ""


@pytest.mark.parametrize("sector", sorted(NATIVE_ETFS))
def test_m2_native_graphs_keep_their_own_etfs(navs, sector):
    out = mf.get_sector_mf_herding(sector)
    assert navs == NATIVE_ETFS[sector]
    # 100 -> 102 is +2.000% for every fund, so the mean is +2.000%: INFLOW (>= 0.5).
    assert (out["avg_momentum_pct"], out["institutional_flow"]) == (2.0, "INFLOW")
    assert out["fund_count"] == len(NATIVE_ETFS[sector])


@pytest.fixture
def nse(monkeypatch):
    monkeypatch.setattr("services.data.fetchers.nse_market.get_nse_market_data", lambda: {})
    monkeypatch.setattr("services.data.fetchers.nse_market.format_nse_market_context",
                        lambda data, focus=None, ticker=None: f"[{focus} for {ticker or 'all'}]")


def test_m2_the_flows_line_of_a_generic_stock_says_no_sector_etfs(navs, nse):
    q = StockQuery(ticker="RAINBOW", company_name="Rainbow Children's Medicare", nse_data={})
    res = bb._fetch_flows_sentiment(q, "generic")
    assert navs == []
    assert res.status == fr.STATUS_OK                   # bulk deals and FII/DII came back
    assert res.reason == "MF herding: no sector ETFs for generic"
    assert res.text == "[bulk_deals for RAINBOW]\n\n[fii_dii for all]"
    assert not any(n.lower() in (res.text + res.reason).lower() for n in AUTO_NAMES)


def test_m2_the_flows_line_of_a_native_stock_keeps_its_etfs(navs, nse):
    q = StockQuery(ticker="MARUTI", company_name="Maruti Suzuki", nse_data={})
    res = bb._fetch_flows_sentiment(q, "automobile")
    assert navs == NATIVE_ETFS["automobile"]
    assert "[MF HERDING SIGNAL — automobile sector" in res.text
    assert "Mirae Asset Nifty Auto ETF: +2.000%" in res.text
    assert res.reason is None or "MF herding" not in res.reason


def test_m2_a_whole_generic_bundle_names_no_automobile_peer_or_flow(market, navs, nse):
    """SUNPHARMA runs the generic graph. Its peers come from the SA-044 world
    (four pharma names) and its flows from the stubs above. By hand: no car
    maker and no auto ETF anywhere in the two sections, their reasons or the
    prompt text; the flows reason says why there is no MF line."""
    stubbed = {n: (lambda *a, **k: fr.FetchResult("x", fr.STATUS_OK, "fixture"))
               for n in ("_fetch_company_news", "_fetch_sector_policy_news",
                         "_fetch_macro_context", "_fetch_policy_deep_dive",
                         "_fetch_fundamentals", "_fetch_technicals", "_fetch_commodities",
                         "_fetch_dossier")}
    from unittest.mock import patch
    with patch.multiple(bb, **stubbed):
        bundle = bb.build_sector_bundle(
            StockQuery(ticker="SUNPHARMA", company_name="Sun Pharma", nse_data={}), "generic")
    prov = bundle.section_provenance
    seen = " ".join([bundle.sections["peers_valuation"], bundle.sections["flows_sentiment"],
                     str(prov["peers_valuation"]), str(prov["flows_sentiment"])])
    assert not any(n.lower() in seen.lower() for n in AUTO_NAMES), seen
    assert prov["flows_sentiment"]["reason"] == "MF herding: no sector ETFs for generic"
    assert prov["peers_valuation"]["peers"].startswith(f'peers: same Yahoo industry "{PHARMA}"')
    assert navs == []
    assert "Nifty Auto" not in bundle.to_prompt_text()


# ===========================================================================
# R1: a profile call yfinance hides is never stored (decision D1)
# ===========================================================================

class _Resp:
    status_code = 500
    text = '{"finance":{"result":null,"error":{"code":"Internal Server Error"}}}'


class _NotFound:
    status_code = 404
    text = '{"quoteSummary":{"result":null,"error":{"code":"Not Found"}}}'


@pytest.fixture()
def yahoo_transport(monkeypatch):
    """yfinance 1.3.0's real Ticker.info, with the transport stubbed at
    YfData.get_raw_json. `down`: quoteSummary (the profile) answers HTTP 500
    while the v7 quote answers a market cap. `unlisted`: both answer as for a
    code Yahoo does not list (404, no quote)."""
    from curl_cffi.requests.exceptions import HTTPError
    from yfinance.data import YfData
    state = {"down": True, "unlisted": set(), "calls": []}

    def get_raw_json(self, url, params=None, timeout=30):
        sym = url.rsplit("/", 1)[-1] if "quoteSummary" in url else (params or {}).get("symbols")
        state["calls"].append(sym)
        if sym in state["unlisted"]:
            if "quoteSummary" in url:
                raise HTTPError("HTTP Error 404: ", response=_NotFound())
            return {"quoteResponse": {"result": [], "error": None}}
        if "quoteSummary" in url:
            if state["down"]:
                raise HTTPError("HTTP Error 500: ", response=_Resp())
            return {"quoteSummary": {"result": [{"assetProfile": {
                "industry": PHARMA, "sector": "Healthcare"},
                "price": {"marketCap": 4.0e12}}], "error": None}}
        return {"quoteResponse": {"result": [{"symbol": sym, "quoteType": "EQUITY",
                                              "marketCap": 4.0e12}], "error": None}}

    class _Text:
        text = '{"timeseries":{"result":[{}],"error":null}}'
    monkeypatch.setattr(YfData, "get_raw_json", get_raw_json)
    monkeypatch.setattr(YfData, "cache_get", lambda self, url=None, **k: _Text())
    return state


def _stored() -> dict:
    if not P.PROFILE_PATH.exists():
        return {}
    return json.loads(P.PROFILE_PATH.read_text(encoding="utf-8"))["profiles"]


def test_r1_the_reviewers_case_a_hidden_failure_is_never_stored(yahoo_transport):
    """SA-044 review RV4, inverted. 12 Nov: Yahoo's profile endpoint fails,
    its quote answers a cap. By hand: lookup_profile raises, nothing is
    stored, the note says the industry could not be looked up. The next build
    the same day asks again; with Yahoo back, 13 Nov reads PHARMA."""
    with pytest.raises(P.ProfileCallFailed):
        P.lookup_profile("SUNPHARMA.NS")
    first = P.choose_peers("SUNPHARMA", today=DAY, universe=["SUNPHARMA"])
    assert first.note() == "peers unavailable: the industry of SUNPHARMA could not be looked up"
    assert "SUNPHARMA.NS" not in _stored()
    before = len(yahoo_transport["calls"])
    P.choose_peers("SUNPHARMA", today=DAY, universe=["SUNPHARMA"])
    assert len(yahoo_transport["calls"]) > before        # asked again, not read from the file
    yahoo_transport["down"] = False
    again = P.choose_peers("SUNPHARMA", today=DAY + timedelta(days=1), universe=["SUNPHARMA"])
    assert again.industry == PHARMA
    assert _stored()["SUNPHARMA.NS"]["industry"] == PHARMA


def test_r1_a_code_yahoo_does_not_list_stays_cached(yahoo_transport):
    """ACCCEMENT: no profile and no cap (Yahoo answers 404 and an empty
    quote). That is an answer, kept for cache_days: the next day makes no
    call."""
    yahoo_transport["unlisted"].add("ACCCEMENT.NS")
    choice = P.choose_peers("ACCCEMENT", today=DAY, universe=["ACCCEMENT"])
    assert choice.note() == "peers unavailable: Yahoo gives no industry for ACCCEMENT"
    assert _stored()["ACCCEMENT.NS"] == {"industry": "", "sector": "", "market_cap": None,
                                         "as_of": "2026-11-12"}
    calls = len(yahoo_transport["calls"])
    P.choose_peers("ACCCEMENT", today=DAY + timedelta(days=1), universe=["ACCCEMENT"])
    assert len(yahoo_transport["calls"]) == calls


def test_r1_a_hidden_failure_stored_before_the_fix_is_asked_again(yahoo_transport):
    """data/peer_profiles.json from f368f20 holds SUNPHARMA with a cap and no
    profile, looked up on 11 Nov. By hand on 12 Nov (1 day old, inside 30):
    it is due anyway and never read as "no industry". While Yahoo still
    fails, the note says the lookup failed and the old entry stays; once
    Yahoo answers, PHARMA replaces it the same day."""
    P.PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    P.PROFILE_PATH.write_text(json.dumps({"version": 1, "profiles": {"SUNPHARMA.NS": {
        "industry": "", "sector": "", "market_cap": 4.0e12, "as_of": "2026-11-11"}}}),
        encoding="utf-8")
    first = P.choose_peers("SUNPHARMA", today=DAY, universe=["SUNPHARMA"])
    assert first.note() == "peers unavailable: the industry of SUNPHARMA could not be looked up"
    assert "SUNPHARMA.NS" in yahoo_transport["calls"]
    yahoo_transport["down"] = False
    again = P.choose_peers("SUNPHARMA", today=DAY, universe=["SUNPHARMA"])
    assert again.industry == PHARMA
    assert _stored()["SUNPHARMA.NS"]["as_of"] == "2026-11-12"


@pytest.mark.parametrize("info, outcome", [
    # (Yahoo's .info, what lookup_profile does) worked by hand from D1.
    ({"marketCap": 4.0e12}, "raises"),                                   # the hidden failure
    ({"marketCap": 4.0e12, "industry": "", "sector": ""}, "raises"),
    ({"marketCap": 4.0e12, "sector": "Healthcare"}, ("", "Healthcare", 4.0e12)),
    ({"marketCap": 4.0e12, "industry": PHARMA}, (PHARMA, "", 4.0e12)),
    ({"industry": PHARMA, "sector": "Healthcare"}, (PHARMA, "Healthcare", None)),
    ({}, ("", "", None)),                                                # not listed
    ({"marketCap": "n/a"}, ("", "", None)),                              # no usable cap
])
def test_r1_only_a_cap_without_any_profile_is_a_failure(monkeypatch, info, outcome):
    monkeypatch.setattr("yfinance.Ticker", lambda s: SimpleNamespace(info=dict(info)))
    if outcome == "raises":
        with pytest.raises(P.ProfileCallFailed):
            P.lookup_profile("X.NS")
        return
    got = P.lookup_profile("X.NS")
    assert (got["industry"], got["sector"], got["market_cap"]) == outcome


# ===========================================================================
# R2: two workers keep both fills (decision D2)
# ===========================================================================

def test_r2_the_reviewers_case_two_interleaved_fills_keep_both():
    """SA-044 review RV5, inverted: each worker read the empty file before the
    other saved. Both X and Y survive."""
    a = {"X.NS": {"industry": "W", "sector": "", "market_cap": 1.0}}
    b = {"Y.NS": {"industry": "W", "sector": "", "market_cap": 2.0}}
    pa, pb = P._load_profiles(), P._load_profiles()
    pa.update({k: {**v, "as_of": DAY.isoformat()} for k, v in a.items()})
    P._save_profiles(pa)
    pb.update({k: {**v, "as_of": DAY.isoformat()} for k, v in b.items()})
    saved = P._save_profiles(pb)
    assert {"X.NS", "Y.NS"} <= set(_stored()) and set(saved) == set(_stored())


def test_r2_the_later_lookup_wins_and_a_tie_keeps_this_build():
    """File: X looked up 12 Nov by the other worker, Y 1 Nov, W 12 Nov. This
    build read the file on 10 Nov's state (X from 10 Nov), looked up Z on
    12 Nov and re-looked up W on 12 Nov (a tie). By hand: X 12 Nov (file),
    Y (file), Z (mine), W (mine, the tie)."""
    on_file = {"X.NS": {"industry": "file", "as_of": "2026-11-12"},
               "Y.NS": {"industry": "file", "as_of": "2026-11-01"},
               "W.NS": {"industry": "file", "as_of": "2026-11-12"}}
    mine = {"X.NS": {"industry": "mine", "as_of": "2026-11-10"},
            "Z.NS": {"industry": "mine", "as_of": "2026-11-12"},
            "W.NS": {"industry": "mine", "as_of": "2026-11-12"}}
    got = P.merge_profiles(mine, on_file)
    assert {k: v["industry"] for k, v in got.items()} == {
        "X.NS": "file", "Y.NS": "file", "Z.NS": "mine", "W.NS": "mine"}
    # An undatable profile is older than any dated one.
    assert P.merge_profiles({"X.NS": {"industry": "mine"}}, on_file)["X.NS"]["industry"] == "file"


def test_r2_a_held_lock_writes_nothing(monkeypatch):
    from filelock import FileLock
    P._save_profiles({"X.NS": {"industry": "W", "as_of": "2026-11-12"}})
    monkeypatch.setattr(P, "LOCK_TIMEOUT_S", 0.05)
    with FileLock(str(P.PROFILE_PATH) + ".lock"):
        mine = {"Y.NS": {"industry": "W", "as_of": "2026-11-12"}}
        assert P._save_profiles(mine) == mine            # returned, not written
    assert set(_stored()) == {"X.NS"}


_CHILD = """
import tests.hermetic  # the suite's network guard, in the child too
import sys
from services.data.context import peers as P
tag = sys.argv[1]
for k in range(25):
    profiles = P._load_profiles()
    profiles[f"{tag}{k:02d}.NS"] = {"industry": "W", "sector": "", "market_cap": 1.0,
                                    "as_of": "2026-11-12"}
    P._save_profiles(profiles)
"""


def test_r2_two_real_processes_filling_at_once_keep_every_profile(tmp_path):
    """Two Python processes, as the two uvicorn workers, each add 25 profiles
    one save at a time, at the same time, in one data/ directory. By hand:
    50 profiles, A00-A24 and B00-B24, and the file reads as JSON."""
    env = {k: v for k, v in os.environ.items()
           if k.upper() in {"SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP", "COMSPEC",
                            "PATHEXT", "LOCALAPPDATA", "APPDATA", "HOME", "USERPROFILE"}}
    env.update({"PYTHONPATH": os.pathsep.join([str(REPO), str(REPO / "src")]),
                "PYTHONUTF8": "1"})
    procs = [subprocess.Popen([sys.executable, "-c", _CHILD, tag], cwd=tmp_path, env=env,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)
             for tag in ("A", "B")]
    for p in procs:
        _, err = p.communicate(timeout=120)
        assert p.returncode == 0, err.decode(errors="replace")[-800:]
    data = json.loads((tmp_path / "data" / "peer_profiles.json").read_text(encoding="utf-8"))
    assert set(data["profiles"]) == ({f"A{k:02d}.NS" for k in range(25)}
                                     | {f"B{k:02d}.NS" for k in range(25)})


# ===========================================================================
# L1: only an analysis, a managed record or the ticker map decides (D4)
# ===========================================================================

def _redive(world, symbol, on):
    return dd.run_deep_dives([DiscoveryCandidate(symbol=symbol, close=0.0, composite=0.0,
                                                 flags=["redive"])],
                             on=on, listing=world["listing"])


def _legacy(symbol, key, conviction, yahoo, dived="2026-11-07", reading=None):
    """An idea as shelf.json holds it from before FIX-026 (no reading), or
    with the reading a FIX-026 re-dive wrote (`reading`)."""
    return ShelfIdea(symbol=symbol, sector=key, added=dived, dived=dived, verdict="BUY", model_verdict="BUY",
                     conviction=conviction, data_gate="actionable", source_screen_date=dived,
                     entry_low=970.0, entry_high=1020.0, invalidation_level=880.0,
                     close_at_add=1000.0, market_sector=yahoo["sector"],
                     industry=yahoo["industry"], sector_reading=reading)


def _events(store) -> list[dict]:
    return [json.loads(line) for line in
            store._events_path.read_text(encoding="utf-8").splitlines()]


@pytest.fixture
def no_holdings(monkeypatch):
    monkeypatch.setattr(wd, "_held_positions", lambda: [])


def test_l1_the_reviewers_case_a_table_key_is_named_by_its_next_analysis(world, no_holdings):
    """RV1, inverted. ODDCO, a hospital chain outside the ticker map, was filed
    as "pharma" on Sat 7 Nov by FIX-011's table ("Healthcare" -> pharma). By
    hand under FIX-030: it is not offered and the watchdog names it; it is due
    on Sat 14 Nov (first group, though its dive is only 7 days old); that
    re-dive's reasoned "generic" becomes its key (source "analysis"), the
    event says "sector pharma -> generic", and the summary keeps nothing."""
    keys = sn.configured_sectors()
    store = shelf_mod.ShelfStore()
    store.save(Shelf(ideas=[_legacy("ODDCO", "pharma", 0.70, HOSP_YAHOO)]))
    idea = store.load().ideas[0]
    why = 'filed as "pharma" from Yahoo\'s labels before an analysis named sectors'
    assert sn.unnamed_why(idea, keys) == why
    offered, excluded = cands_mod.buy_candidates(PF, MON, store.load().ideas, managed={})
    assert offered == [] and excluded == {
        "ODDCO": f"sector unnamed: {why}; waits for a re-dive to name it"}
    check = wd.sector_keys()
    assert check.state == "pending" and f"shelf ODDCO has no sector key: {why}" in check.detail
    assert [i.symbol for i in store.redive_due(ON)] == ["ODDCO"]

    ask(world, "ODDCO", HOSP_YAHOO,
        {"key": "generic", "reason": "A hospital chain; none of our keys fits.",
         "yahoo_fits": True})
    redived = _redive(world, "ODDCO", ON)
    assert (redived[0].sector, redived[0].sector_reading.source) == ("generic", "analysis")
    assert sn.summarise(redived, keys)["kept"] == {}
    out = store.apply_redives(redived, on=ON)
    assert out["refreshed"] == ["ODDCO"] and out["dropped"] == {}
    idea = store.load().ideas[0]
    assert (idea.sector, idea.sector_reading.answer) == ("generic", "generic")
    assert any(e["event"] == "redived" and e["symbol"] == "ODDCO"
               and e["detail"].endswith(", sector pharma -> generic") for e in _events(store))
    # Now a reasoned "generic": not offered (no cap can count it), and the
    # watchdog names it with its reason; due again only after 30 days.
    assert sn.status(idea, keys) == "generic"
    assert "shelf ODDCO generic: A hospital chain; none of our keys fits." in wd.sector_keys().detail
    assert [i.symbol for i in store.redive_due(ON + timedelta(days=28))] == []


def test_l1_a_table_key_a_fix026_redive_kept_is_still_reexamined(world):
    """14 Nov's run (FIX-026's code) re-dives ODDCO and keeps "pharma" as
    "earlier" while answering "generic". That reading has no `named_on`: no
    analysis ever named pharma, so FIX-030 still re-examines it."""
    keys = sn.configured_sectors()
    kept = SectorReading(answer="generic", reason="A hospital chain.", yahoo_fits=True,
                         source="earlier")
    idea = _legacy("ODDCO", "pharma", 0.70, HOSP_YAHOO, dived="2026-11-14", reading=kept)
    assert not sn.key_decided(idea, keys)
    assert sn.known_key("ODDCO", managed={}, idea=idea, keys=keys) == ("", "")
    store = shelf_mod.ShelfStore()
    store.save(Shelf(ideas=[idea]))
    assert [i.symbol for i in store.redive_due(date(2026, 11, 21))] == ["ODDCO"]


def test_l1_a_table_key_a_later_analysis_answered_itself_is_decided(world):
    """The same 14 Nov re-dive for a table-set "pharma" drug maker whose
    analysis answered "pharma": an analysis named that very key, so it is
    decided, offered, and not re-dived again until 30 days pass."""
    keys = sn.configured_sectors()
    kept = SectorReading(answer="pharma", reason="Generic formulations.", yahoo_fits=True,
                         source="earlier")
    idea = _legacy("NEWDRUG", "pharma", 0.70, DRUG_YAHOO, dived="2026-11-14", reading=kept)
    assert sn.key_decided(idea, keys) and sn.analysis_named_on(idea, keys) == "2026-11-14"
    store = shelf_mod.ShelfStore()
    store.save(Shelf(ideas=[idea]))
    offered, _ = cands_mod.buy_candidates(PF, MON, store.load().ideas, managed={})
    assert [(i.symbol, i.sector) for i in offered] == [("NEWDRUG", "pharma")]
    assert store.redive_due(date(2026, 12, 12)) == []                     # 28 days
    assert [i.symbol for i in store.redive_due(date(2026, 12, 19))] == ["NEWDRUG"]  # 35


def test_l1_an_analysis_named_key_survives_later_answers_that_disagree(world):
    """NEWDRUG is named "pharma" by its analysis on 14 Nov. Re-dived on Sat
    19 Dec (35 days) answering "chemicals", and on Sat 23 Jan answering
    nothing: the key stays "pharma" both times (source "earlier"), and the
    reading still says 14 Nov's analysis named it. Offered after each."""
    keys = sn.configured_sectors()
    ask(world, "NEWDRUG", DRUG_YAHOO, {"key": "pharma", "reason": "Generic formulations.",
                                       "yahoo_fits": True})
    store = shelf_mod.ShelfStore()
    store.apply_deep_dives(run(world, "NEWDRUG"), on=ON)
    assert store.load().ideas[0].sector_reading.named_on == "2026-11-14"
    for sat, answer in ((date(2026, 12, 19), {"key": "chemicals", "reason": "r"}),
                        (date(2027, 1, 23), None)):
        assert [i.symbol for i in store.redive_due(sat)] == ["NEWDRUG"], sat
        ask(world, "NEWDRUG", DRUG_YAHOO, answer)
        [d] = _redive(world, "NEWDRUG", sat)
        assert (d.sector, d.sector_reading.source, d.sector_reading.named_on) == (
            "pharma", "earlier", "2026-11-14")
        store.apply_redives([d], on=sat)
        idea = store.load().ideas[0]
        assert (idea.status, idea.sector, idea.unnamed_redives) == ("active", "pharma", 0)
        assert sn.unnamed_why(idea, keys) == ""
        offered, _ = cands_mod.buy_candidates(PF, sat + timedelta(days=2), [idea], managed={})
        assert [(i.symbol, i.sector) for i in offered] == [("NEWDRUG", "pharma")]


def test_l1_never_rekeys_a_managed_stock_or_a_ticker_map_stock(world, tmp_path):
    """Hard review: SOLDAUTO is managed under "automobile" (sold by the
    autopilot); its idea was filed "logistics" by the table. MARUTI is in the
    ticker map as "automobile", its legacy idea has no reading. Both re-dives
    answer "logistics". By hand: SOLDAUTO's dive keeps the managed key (and the
    idea, undecided, takes it, so it matches the record its forecasts live
    under); the managed record is untouched. MARUTI's key is decided by the
    map: not due early, never re-keyed."""
    keys = sn.configured_sectors()
    record = {"sym": "SOLDAUTO", "sector": "automobile", "enabled": True}
    world["managed"].append(dict(record))
    store = shelf_mod.ShelfStore()
    store.save(Shelf(ideas=[_legacy("SOLDAUTO", "logistics", 0.70, HOSP_YAHOO),
                            _legacy("MARUTI", "automobile", 0.70, HOSP_YAHOO)]))
    assert sn.key_decided(store.load().ideas[1], keys)                   # the ticker map
    assert [i.symbol for i in store.redive_due(ON)] == ["SOLDAUTO"]
    for s in ("SOLDAUTO", "MARUTI"):
        ask(world, s, HOSP_YAHOO, {"key": "logistics", "reason": "r", "yahoo_fits": False})
    dives = dd.run_deep_dives(
        [DiscoveryCandidate(symbol=s, close=0.0, composite=0.0, flags=["redive", "sold"])
         for s in ("SOLDAUTO", "MARUTI")], on=ON, listing=world["listing"])
    # MARUTI is not managed, so its "sold"-flagged re-dive runs too.
    assert {d.symbol: (d.sector, d.sector_reading.source) for d in dives} == {
        "SOLDAUTO": ("automobile", "managed"), "MARUTI": ("automobile", "ticker_map")}
    store.apply_redives(dives, on=ON)
    assert {i.symbol: i.sector for i in store.load().ideas} == {
        "SOLDAUTO": "automobile", "MARUTI": "automobile"}
    assert world["managed"] == [record]


def test_l1_table_keys_join_the_first_redive_group_oldest_first(world):
    """Decision D4's budget. Shelf on Sat 21 Nov: two table-set ideas (dived
    2 and 7 Nov), an analysis-named idea (14 Nov), a ticker-map legacy idea
    (MARUTI, 7 Nov) and a reasoned-generic idea (14 Nov). By hand: only the
    two table-set ideas are due, 2 Nov first; they take 2 of the week's 20
    calls once."""
    named = SectorReading(answer="pharma", reason="r", named_on="2026-11-14")
    chose = SectorReading(answer="generic", reason="none fits", named_on="2026-11-14")
    store = shelf_mod.ShelfStore()
    store.save(Shelf(ideas=[
        _legacy("ODDCO", "pharma", 0.70, HOSP_YAHOO, dived="2026-11-07"),
        _legacy("CHEMCO", "chemicals", 0.70, HOSP_YAHOO, dived="2026-11-02"),
        _legacy("NEWDRUG", "pharma", 0.70, DRUG_YAHOO, dived="2026-11-14", reading=named),
        _legacy("MARUTI", "automobile", 0.70, HOSP_YAHOO, dived="2026-11-07"),
        _legacy("HOLDCO", "generic", 0.70, HOSP_YAHOO, dived="2026-11-14", reading=chose)]))
    assert [i.symbol for i in store.redive_due(date(2026, 11, 21))] == ["CHEMCO", "ODDCO"]


def test_l1_a_table_key_counts_in_no_sector_cap_until_named(world):  # world: sandboxed shelf, cap 3
    """P1-P3 are named "pharma"; ODDCO's "pharma" is the table's. By hand: the
    shelf's cap of 3 counts P1-P3 only, so nothing is dropped, and ODDCO's cap
    key is "" (not capped, like an unnamed idea)."""
    named = lambda s, c: _legacy(s, "pharma", c, DRUG_YAHOO,  # noqa: E731
                                 reading=SectorReading(answer="pharma", named_on="2026-11-14"))
    store = shelf_mod.ShelfStore()
    shelf = Shelf(ideas=[named("P1", 0.80), named("P2", 0.75), named("P3", 0.72),
                         _legacy("ODDCO", "pharma", 0.60, HOSP_YAHOO)])
    assert [shelf_mod.cap_key(i) for i in shelf.ideas] == ["pharma", "pharma", "pharma", ""]
    assert store._enforce_sector_cap(shelf) == []


# ===========================================================================
# L2: an unnamed idea stops taking a weekly re-dive (decision D5)
# ===========================================================================

def test_l2_the_reviewers_case_an_unnamed_idea_is_dropped_after_two_redives(world):
    """RV2, inverted. MUTECO is shelved on Sat 14 Nov with no answer, and no
    analysis ever names it. By hand: due on 21 Nov (count 1, kept) and 28 Nov
    (count 2: dropped with the reason); not due on 5 Dec; 3 analyst calls in
    all, against 13 by 6 Feb before. Never offered."""
    keys = sn.configured_sectors()
    ask(world, "MUTECO", DRUG_YAHOO, None)
    store = shelf_mod.ShelfStore()
    store.apply_deep_dives(run(world, "MUTECO"), on=ON)
    sat21, sat28, dec5 = date(2026, 11, 21), date(2026, 11, 28), date(2026, 12, 5)

    assert [i.symbol for i in store.redive_due(sat21)] == ["MUTECO"]
    out = store.apply_redives(_redive(world, "MUTECO", sat21), on=sat21)
    idea = store.load().ideas[0]
    assert out["refreshed"] == ["MUTECO"] and (idea.status, idea.unnamed_redives) == ("active", 1)

    assert [i.symbol for i in store.redive_due(sat28)] == ["MUTECO"]
    dives28 = _redive(world, "MUTECO", sat28)
    out = store.apply_redives(dives28, on=sat28)
    reason = ("re-dive 2026-11-28: no sector key after 2 re-dives in a row "
              "(the analysis gave no sector answer)")
    assert out == {"refreshed": [], "dropped": {"MUTECO": reason}, "capped": []}
    idea = store.load().ideas[0]
    assert (idea.status, idea.unnamed_redives) == ("dropped", 2)
    assert {"event": "dropped", "symbol": "MUTECO", "detail": reason} in [
        {k: e[k] for k in ("event", "symbol", "detail")} for e in _events(store)]

    assert store.redive_due(dec5) == []
    assert world["analyst"].calls.count("MUTECO") == 3
    assert sn.unnamed_why(idea, keys)
    # The dive memo (the run records the week's dives) keeps it from a new
    # dive for 30 days after 28 Nov.
    store.record_dives(dives28, on=sat28)
    assert "MUTECO" in store.recently_dived(date(2026, 12, 26))
    assert "MUTECO" not in store.recently_dived(date(2027, 1, 2))


def test_l2_a_redive_that_names_the_idea_resets_the_count(world):
    """MUTECO: no answer on 14 Nov (shelved) and 21 Nov (count 1); 28 Nov
    answers "pharma". By hand: count 0, key pharma, offered on Mon 30 Nov,
    and next due when the dive is over 30 days old: not 26 Dec (28 days), but
    Sat 2 Jan (35 days)."""
    ask(world, "MUTECO", DRUG_YAHOO, None)
    store = shelf_mod.ShelfStore()
    store.apply_deep_dives(run(world, "MUTECO"), on=ON)
    store.apply_redives(_redive(world, "MUTECO", date(2026, 11, 21)), on=date(2026, 11, 21))
    assert store.load().ideas[0].unnamed_redives == 1
    ask(world, "MUTECO", DRUG_YAHOO, {"key": "pharma", "reason": "Generic formulations.",
                                      "yahoo_fits": True})
    sat28 = date(2026, 11, 28)
    store.apply_redives(_redive(world, "MUTECO", sat28), on=sat28)
    idea = store.load().ideas[0]
    assert (idea.status, idea.sector, idea.unnamed_redives) == ("active", "pharma", 0)
    assert idea.sector_reading.named_on == "2026-11-28"
    offered, _ = cands_mod.buy_candidates(PF, date(2026, 11, 30), [idea], managed={})
    assert [(i.symbol, i.sector) for i in offered] == [("MUTECO", "pharma")]
    assert store.redive_due(date(2026, 12, 26)) == []
    assert [i.symbol for i in store.redive_due(date(2027, 1, 2))] == ["MUTECO"]


def test_l2_a_legacy_generic_idea_counts_the_same(world):
    """An idea shelved as "generic" before FIX-026 (no reading) is unnamed.
    Two re-dives with an answer that is not a key ("Healthcare") drop it on
    the second, with that problem in the reason."""
    store = shelf_mod.ShelfStore()
    store.save(Shelf(ideas=[_legacy("HOLDCO", "generic", 0.70, HOSP_YAHOO)]))
    ask(world, "HOLDCO", HOSP_YAHOO, {"key": "Healthcare", "reason": "r"})
    for k, sat in enumerate((ON, date(2026, 11, 21)), start=1):
        assert [i.symbol for i in store.redive_due(sat)] == ["HOLDCO"]
        out = store.apply_redives(_redive(world, "HOLDCO", sat), on=sat)
    assert out["dropped"] == {"HOLDCO": (
        "re-dive 2026-11-21: no sector key after 2 re-dives in a row "
        "(the analysis answered 'Healthcare', not one of our keys)")}


def test_l2_a_limit_of_zero_keeps_the_weekly_redive(world, monkeypatch):
    monkeypatch.setattr(settings, "DISCOVERY_MAX_UNNAMED_REDIVES", 0)
    ask(world, "MUTECO", DRUG_YAHOO, None)
    store = shelf_mod.ShelfStore()
    store.apply_deep_dives(run(world, "MUTECO"), on=ON)
    for sat in (date(2026, 11, 21), date(2026, 11, 28), date(2026, 12, 5)):
        store.apply_redives(_redive(world, "MUTECO", sat), on=sat)
    idea = store.load().ideas[0]
    assert (idea.status, idea.unnamed_redives) == ("active", 3)


def test_l2_the_shipped_limit_is_two():
    from backend.shared.config.settings.loader import cfg
    assert int(cfg("discovery.max_unnamed_redives")) == 2 == settings.DISCOVERY_MAX_UNNAMED_REDIVES


def test_l2_a_stored_shelf_from_before_fix030_loads_with_a_zero_count(tmp_path):
    """shelf.json written before FIX-030 has neither field; it loads with
    `unnamed_redives` 0 and readings with `named_on` ""."""
    raw = {"ideas": [{"symbol": "OLD", "sector": "pharma", "added": "2026-11-07",
                      "conviction": 0.7,
                      "sector_reading": {"answer": "pharma", "source": "analysis"}}]}
    shelf = Shelf.model_validate(raw)
    assert shelf.ideas[0].unnamed_redives == 0 and shelf.ideas[0].sector_reading.named_on == ""
