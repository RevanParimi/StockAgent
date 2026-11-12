"""SA-044: a valuation is compared only with same-industry peers.

The rule (services/data/context/peers.py): the stock's Yahoo industry, the
known symbols in exactly that industry, nearest market cap first, at most
five; fewer than three -> `peers unavailable`, never another industry's list.

Every profile here is a stub: `lookup_profile` and `known_symbols` are
replaced, or yfinance's Ticker is, so no test reaches Yahoo. The oracle in
the invariant test is written independently of the implementation: it
ranks by the larger-over-smaller cap ratio, not by a logarithm.
"""
from __future__ import annotations

import json
import random
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from core.schemas.pipeline import StockQuery
from services.data.context import bundle_builder as bb
from services.data.context import fetch_result as fr
from services.data.context import peers as P

TODAY = date(2026, 11, 12)
CR = 1e7      # one crore, in rupees

# Yahoo industry and market cap per provider symbol (illustrative caps).
AUTO = "Auto Manufacturers"
BANK = "Banks - Regional"
IT = "Information Technology Services"
RENEW = "Utilities - Renewable"
PHARMA = "Drug Manufacturers - Specialty & Generic"
STEEL = "Steel"
TABLE: dict[str, tuple[str, float | None]] = {
    "MARUTI.NS": (AUTO, 400_000 * CR), "M&M.NS": (AUTO, 380_000 * CR),
    "TMPV.NS": (AUTO, 150_000 * CR), "BAJAJ-AUTO.NS": (AUTO, 250_000 * CR),
    "EICHERMOT.NS": (AUTO, 150_000 * CR), "HEROMOTOCO.NS": (AUTO, 90_000 * CR),
    "TVSMOTOR.NS": (AUTO, 160_000 * CR), "ASHOKLEY.NS": (AUTO, 60_000 * CR),
    "HDFCBANK.NS": (BANK, 1_500_000 * CR), "ICICIBANK.NS": (BANK, 1_000_000 * CR),
    "SBIN.NS": (BANK, 800_000 * CR), "KOTAKBANK.NS": (BANK, 400_000 * CR),
    "AXISBANK.NS": (BANK, 350_000 * CR), "INDUSINDBK.NS": (BANK, 70_000 * CR),
    "TCS.NS": (IT, 1_200_000 * CR), "INFY.NS": (IT, 650_000 * CR),
    "WIPRO.NS": (IT, 260_000 * CR), "HCLTECH.NS": (IT, 430_000 * CR),
    "TECHM.NS": (IT, 150_000 * CR), "LTIM.NS": (IT, 160_000 * CR),
    "ADANIGREEN.NS": (RENEW, 160_000 * CR), "NHPC.NS": (RENEW, 85_000 * CR),
    "SJVN.NS": (RENEW, 40_000 * CR), "JSWENERGY.NS": (RENEW, 90_000 * CR),
    "SUNPHARMA.NS": (PHARMA, 400_000 * CR), "CIPLA.NS": (PHARMA, 120_000 * CR),
    "DRREDDY.NS": (PHARMA, 105_000 * CR), "LUPIN.NS": (PHARMA, 95_000 * CR),
    "ZYDUSLIFE.NS": (PHARMA, 100_000 * CR),
    "TATASTEEL.NS": (STEEL, 200_000 * CR), "JSWSTEEL.NS": (STEEL, 240_000 * CR),
    "NOCLASS.NS": ("", 5_000 * CR),          # Yahoo gives no industry
}
UNIVERSE = sorted({k[:-3] for k in TABLE} | {"TATAMOTORS", "TVSMOTORS"})


def _industry_of(app_ticker: str) -> str:
    """The test's own map from app ticker to industry (not the module's)."""
    alias = {"TVSMOTORS": "TVSMOTOR"}
    return TABLE.get(f"{alias.get(app_ticker, app_ticker)}.NS", ("", None))[0]


class Stub:
    """`lookup_profile` from TABLE, counting calls; `fail` symbols raise."""

    def __init__(self, table=None, fail=()):
        self.table = TABLE if table is None else table
        self.fail = set(fail)
        self.calls: list[str] = []

    def __call__(self, provider_symbol: str) -> dict:
        self.calls.append(provider_symbol)
        if provider_symbol in self.fail:
            raise ConnectionError("rate limited")
        industry, cap = self.table.get(provider_symbol, ("", None))
        return {"industry": industry, "sector": "", "market_cap": cap}


@pytest.fixture()
def stub(monkeypatch):
    s = Stub()
    monkeypatch.setattr(P, "known_symbols", lambda: list(UNIVERSE))
    monkeypatch.setattr(P, "lookup_profile", s)
    monkeypatch.setattr(P, "max_lookups", lambda: 1000)
    return s


def _choose(ticker, **kw):
    return P.choose_peers(ticker, today=TODAY, **kw)


# ---------------------------------------------------------------------------
# The card's fixtures
# ---------------------------------------------------------------------------

class TestCardFixtures:
    def test_sunpharma_with_four_pharma_symbols_gets_pharma_peers_only(self, stub):
        choice = _choose("SUNPHARMA", sector="generic")
        assert set(choice.symbols) == {"CIPLA", "DRREDDY", "LUPIN", "ZYDUSLIFE"}
        assert choice.industry == PHARMA
        assert choice.note().startswith(f'peers: same Yahoo industry "{PHARMA}"')
        assert "(4)" in choice.note()

    def test_tatasteel_with_one_metals_symbol_gets_peers_unavailable(self, stub):
        choice = _choose("TATASTEEL", sector="generic")
        assert choice.symbols == ()
        assert choice.note().startswith("peers unavailable: 1 other known symbol(s)")
        assert '"Steel"' in choice.note() and "3 needed" in choice.note()

    def test_unknown_industry_gets_peers_unavailable(self, stub):
        choice = _choose("NOCLASS", sector="generic")
        assert choice.symbols == ()
        assert choice.note() == "peers unavailable: Yahoo gives no industry for NOCLASS"

    def test_a_symbol_yahoo_does_not_know_gets_peers_unavailable(self, stub):
        choice = _choose("ZZUNLISTED", sector="generic")
        assert choice.symbols == ()
        assert "no industry" in choice.note()

    def test_a_bank_keeps_bank_peers(self, stub):
        choice = _choose("HDFCBANK", sector="banking_bfsi")
        assert choice.symbols and all(_industry_of(s) == BANK for s in choice.symbols)
        assert "HDFCBANK" not in choice.symbols

    @pytest.mark.parametrize("ticker,sector,industry", [
        ("MARUTI", "automobile", AUTO), ("HDFCBANK", "banking_bfsi", BANK),
        ("INFY", "it_sector", IT), ("ADANIGREEN", "renewable_energy", RENEW),
    ])
    def test_the_four_native_sectors_keep_same_industry_peers(self, stub, ticker, sector, industry):
        choice = _choose(ticker, sector=sector)
        assert 3 <= len(choice.symbols) <= 5
        assert all(_industry_of(s) == industry for s in choice.symbols), choice
        assert ticker not in choice.symbols


# ---------------------------------------------------------------------------
# Nearest by market cap, derived by hand
# ---------------------------------------------------------------------------

class TestNearestByMarketCap:
    def test_five_symbol_fixture_order_by_hand(self, monkeypatch):
        # X is 10,000 Cr. Larger-over-smaller cap ratios: C 12,000 -> 1.2;
        # A 20,000 -> 2.0; F 5,000 -> 2.0 (tie, A before F by symbol);
        # B 4,000 -> 2.5; D 50,000 -> 5.0. So C, A, F, B, D.
        table = {"X.NS": ("Widgets", 10_000 * CR), "A.NS": ("Widgets", 20_000 * CR),
                 "B.NS": ("Widgets", 4_000 * CR), "C.NS": ("Widgets", 12_000 * CR),
                 "D.NS": ("Widgets", 50_000 * CR), "F.NS": ("Widgets", 5_000 * CR)}
        monkeypatch.setattr(P, "lookup_profile", Stub(table))
        choice = P.choose_peers("X", today=TODAY, universe=["X", "A", "B", "C", "D", "F"])
        assert choice.symbols == ("C", "A", "F", "B", "D")

    def test_at_most_five_and_unknown_caps_last(self, monkeypatch):
        table = {"X.NS": ("Widgets", 10_000 * CR), "A.NS": ("Widgets", 10_500 * CR),
                 "B.NS": ("Widgets", None), "C.NS": ("Widgets", 9_000 * CR),
                 "D.NS": ("Widgets", 30_000 * CR), "E.NS": ("Widgets", 2_000 * CR),
                 "G.NS": ("Widgets", 11_000 * CR)}
        monkeypatch.setattr(P, "lookup_profile", Stub(table))
        choice = P.choose_peers("X", today=TODAY, universe=list("XABCDEG"))
        # ratios A 1.05, G 1.1, C 1.11, D 3.0, E 5.0; B unknown -> after all, cut at five
        assert choice.symbols == ("A", "G", "C", "D", "E")

    def test_stock_without_a_cap_takes_largest_first(self, monkeypatch):
        table = {"X.NS": ("Widgets", None), "A.NS": ("Widgets", 1_000 * CR),
                 "B.NS": ("Widgets", 9_000 * CR), "C.NS": ("Widgets", 5_000 * CR)}
        monkeypatch.setattr(P, "lookup_profile", Stub(table))
        choice = P.choose_peers("X", today=TODAY, universe=list("XABC"))
        assert choice.symbols == ("B", "C", "A")


# ---------------------------------------------------------------------------
# Invariants over random universes, against an independent oracle
# ---------------------------------------------------------------------------

def _oracle(stock: str, table: dict[str, tuple[str, float | None]]) -> tuple[str, ...]:
    industry, my_cap = table[f"{stock}.NS"]
    if not industry:
        return ()
    same = [(s[:-3], cap) for s, (ind, cap) in table.items()
            if s[:-3] != stock and ind.lower() == industry.lower()]
    if len(same) < 3:
        return ()

    def rank(item):
        sym, cap = item
        if cap is None:
            return (2, 0.0, sym)
        if my_cap is None:
            return (1, -cap, sym)
        return (1, max(cap / my_cap, my_cap / cap), sym)
    return tuple(sym for sym, _ in sorted(same, key=rank)[:5])


@pytest.mark.parametrize("seed", range(40))
def test_random_universes_match_the_oracle(monkeypatch, seed):
    rng = random.Random(seed)
    industries = ["Alpha", "Beta", "Gamma", "Delta", ""]
    names = [f"S{i:02d}" for i in range(rng.randint(4, 30))]
    table = {}
    for name in names:
        cap = None if rng.random() < 0.15 else float(rng.choice(
            [rng.uniform(100, 500_000), rng.choice([1_000, 2_000, 4_000, 8_000])])) * CR
        table[f"{name}.NS"] = (rng.choice(industries), cap)
    monkeypatch.setattr(P, "lookup_profile", Stub(table))
    monkeypatch.setattr(P, "max_lookups", lambda: 1000)
    for stock in names:
        choice = P.choose_peers(stock, today=TODAY, universe=names)
        industry = table[f"{stock}.NS"][0]
        assert stock not in choice.symbols
        assert len(choice.symbols) <= 5
        assert all(table[f"{s}.NS"][0] == industry for s in choice.symbols), (seed, stock)
        assert len(choice.symbols) in (0,) + tuple(range(3, 6))
        assert choice.symbols == _oracle(stock, table), (seed, stock)


# ---------------------------------------------------------------------------
# The known symbols
# ---------------------------------------------------------------------------

def test_known_symbols_are_registry_native_lists_managed_and_active_shelf():
    from pathlib import Path

    from backend.sectors.banking_bfsi.config import settings as bfsi
    from backend.sectors.registry import TICKER_SECTOR
    from backend.shared.schemas.discovery import Shelf, ShelfIdea
    from core.discovery.shelf import ShelfStore

    Path("data").mkdir(exist_ok=True)
    Path("data/managed_tickers.json").write_text(json.dumps(
        [{"sym": "zzmanaged", "enabled": False}, {"sym": ""}, "junk"]), encoding="utf-8")
    store = ShelfStore()
    store.save(Shelf(ideas=[
        ShelfIdea(symbol="ZZACTIVE", sector="generic", added="2026-11-07", conviction=0.6),
        ShelfIdea(symbol="ZZDROPPED", sector="generic", added="2026-11-07", conviction=0.6,
                  status="dropped"),
    ]))
    known = P.known_symbols()
    assert known == sorted(set(known))
    assert set(TICKER_SECTOR) <= set(known) and set(bfsi.TICKERS) <= set(known)
    assert "ZZMANAGED" in known and "ZZACTIVE" in known
    assert "ZZDROPPED" not in known and "" not in known


def test_known_symbols_survive_an_unreadable_source():
    from pathlib import Path
    Path("data/discovery").mkdir(parents=True, exist_ok=True)
    Path("data/discovery/shelf.json").write_text("{broken", encoding="utf-8")
    Path("data/managed_tickers.json").write_text("{broken", encoding="utf-8")
    assert "MARUTI" in P.known_symbols()


# ---------------------------------------------------------------------------
# Identity (SA-008): never a quarantined listing, one listing counts once
# ---------------------------------------------------------------------------

class TestIdentity:
    @pytest.fixture(autouse=True)
    def _shipped_registry(self, monkeypatch):
        """The suite reads an empty instrument registry (conftest); these
        tests are about the shipped identity decisions."""
        from pathlib import Path
        shipped = Path(__file__).resolve().parents[2] / "config" / "instruments.yaml"
        monkeypatch.setenv("INSTRUMENT_REGISTRY_PATH", str(shipped))

    def test_unresolved_tatamotors_is_never_a_peer_and_aliases_count_once(self, stub):
        choice = _choose("MARUTI", sector="automobile")
        assert "TATAMOTORS" not in choice.symbols
        assert not ({"TVSMOTOR", "TVSMOTORS"} <= set(choice.symbols))
        assert "TATAMOTORS.NS" not in stub.calls

    def test_an_unresolved_stock_gets_no_peers(self, stub):
        choice = _choose("TATAMOTORS", sector="automobile")
        assert choice.symbols == ()
        assert "identity is unresolved" in choice.note()
        assert stub.calls == []


# ---------------------------------------------------------------------------
# Cache: no per-peer network call once profiled; failures never cached
# ---------------------------------------------------------------------------

class TestCache:
    def test_second_build_makes_no_lookup(self, stub):
        first = _choose("SUNPHARMA", sector="generic")
        n = len(stub.calls)
        assert n > 0
        again = _choose("SUNPHARMA", sector="generic")
        other = _choose("CIPLA", sector="generic")
        assert len(stub.calls) == n
        assert again == first and other.symbols
        stored = json.loads(P.PROFILE_PATH.read_text(encoding="utf-8"))["profiles"]
        assert stored["CIPLA.NS"]["industry"] == PHARMA
        assert stored["CIPLA.NS"]["as_of"] == TODAY.isoformat()

    def test_old_profiles_are_used_and_refreshed(self, stub, monkeypatch):
        _choose("SUNPHARMA")
        stub.calls.clear()
        later = TODAY + timedelta(days=P.cache_days() + 1)
        monkeypatch.setattr(P, "max_lookups", lambda: 2)
        choice = P.choose_peers("SUNPHARMA", today=later)
        assert stub.calls[0] == "SUNPHARMA.NS" and len(stub.calls) == 2
        assert set(choice.symbols) == {"CIPLA", "DRREDDY", "LUPIN", "ZYDUSLIFE"}

    def test_budget_bounds_lookups_and_puts_the_stock_and_its_sector_first(self, monkeypatch):
        s = Stub()
        monkeypatch.setattr(P, "known_symbols", lambda: list(UNIVERSE))
        monkeypatch.setattr(P, "lookup_profile", s)
        monkeypatch.setattr(P, "max_lookups", lambda: 6)
        choice = _choose("HDFCBANK", sector="banking_bfsi")
        assert len(s.calls) == 6
        assert s.calls[0] == "HDFCBANK.NS"
        from backend.sectors.registry import TICKER_SECTOR
        assert all(TICKER_SECTOR.get(c[:-3]) == "banking_bfsi" for c in s.calls[1:]), s.calls
        assert choice.symbols and all(_industry_of(x) == BANK for x in choice.symbols)

    def test_failed_lookups_are_not_cached_and_three_in_a_row_stop(self, monkeypatch):
        table = {f"{s}.NS": ("Widgets", 1_000 * CR) for s in "XABCDE"}
        s = Stub(table, fail={"A.NS", "B.NS", "C.NS"})
        monkeypatch.setattr(P, "lookup_profile", s)
        choice = P.choose_peers("X", today=TODAY, universe=list("XABCDE"))
        # X answers, then A, B and C fail: the build stops before D and E.
        assert s.calls == ["X.NS", "A.NS", "B.NS", "C.NS"]
        assert choice.note() == ('peers unavailable: 0 other known symbol(s) in Yahoo industry '
                                 '"Widgets", 3 needed (0 of 5 known symbols profiled)')
        stored = json.loads(P.PROFILE_PATH.read_text(encoding="utf-8"))["profiles"]
        assert set(stored) == {"X.NS"}
        # The next build asks again and, with Yahoo back, finds all five.
        s.fail.clear()
        assert len(P.choose_peers("X", today=TODAY, universe=list("XABCDE")).symbols) == 5

    def test_a_failure_between_answers_does_not_stop_the_build(self, monkeypatch):
        table = {f"{s}.NS": ("Widgets", 1_000 * CR) for s in "XABCDE"}
        s = Stub(table, fail={"A.NS", "B.NS", "D.NS"})
        monkeypatch.setattr(P, "lookup_profile", s)
        choice = P.choose_peers("X", today=TODAY, universe=list("XABCDE"))
        assert s.calls == ["X.NS", "A.NS", "B.NS", "C.NS", "D.NS", "E.NS"]
        assert choice.symbols == () and "(2 of 5 known symbols profiled)" in choice.note()

    def test_a_failed_lookup_of_the_stock_is_said(self, monkeypatch):
        monkeypatch.setattr(P, "lookup_profile", Stub(fail={"SUNPHARMA.NS"}))
        choice = P.choose_peers("SUNPHARMA", today=TODAY, universe=["SUNPHARMA"])
        assert choice.note() == "peers unavailable: the industry of SUNPHARMA could not be looked up"

    def test_an_unreadable_profile_file_starts_empty(self, stub):
        P.PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
        P.PROFILE_PATH.write_text("{not json", encoding="utf-8")
        choice = _choose("SUNPHARMA")
        assert len(choice.symbols) == 4


# ---------------------------------------------------------------------------
# The bundle section and the data-health record
# ---------------------------------------------------------------------------

def _bars(end: date, n: int = 300) -> pd.DataFrame:
    idx = pd.DatetimeIndex([pd.Timestamp(end - timedelta(days=n - 1 - i)) for i in range(n)])
    close = np.linspace(100.0, 130.0, n)
    return pd.DataFrame({"Open": close, "High": close * 1.01, "Low": close * 0.99,
                         "Close": close, "Volume": np.full(n, 1e6)}, index=idx)


class _Yahoo:
    """yfinance stub: every symbol's .info from TABLE (industry, marketCap)
    plus ratios; `no_pe` symbols lack a P/E. Records every symbol asked."""

    def __init__(self, no_pe=()):
        self.no_pe = set(no_pe)
        self.asked: list[str] = []

    def __call__(self, symbol):
        self.asked.append(symbol)
        industry, cap = TABLE.get(symbol, ("", None))
        info = {"industry": industry, "marketCap": cap, "trailingPE": 25.0, "priceToBook": 3.0,
                "trailingEps": 40.0, "currentPrice": 1000.0}
        if symbol in self.no_pe:
            info.pop("trailingPE")
        t = MagicMock()
        t.info = info
        return t


@pytest.fixture()
def market(monkeypatch):
    """The valuation producer's providers: fresh prices, Yahoo from TABLE,
    a Serper that records its queries."""
    from core.intelligence.algorithms.indicators import fetcher as F
    yahoo = _Yahoo()
    searches: list[list[str]] = []

    def serper(queries, max_queries):
        searches.append(list(queries)[:max_queries])
        return "[snippets]", True
    monkeypatch.setattr(F, "get_price_history", lambda t, years=2: _bars(date.today()))
    monkeypatch.setattr("yfinance.Ticker", yahoo)
    monkeypatch.setattr(F, "_serper_fallback", serper)
    monkeypatch.setattr("services.data.fetchers.nse_announcements.format_nse_context",
                        lambda *a, **k: "")
    monkeypatch.setattr(P, "known_symbols", lambda: list(UNIVERSE))
    monkeypatch.setattr(P, "max_lookups", lambda: 1000)
    return yahoo, searches


def _query(ticker):
    return StockQuery(ticker=ticker, company_name=f"{ticker} Ltd", nse_data={})


class TestSection:
    def test_chosen_peers_are_stated_in_text_and_provenance(self, market):
        res = bb._fetch_peers_valuation(_query("SUNPHARMA"), "generic")
        first = res.text.splitlines()[0]
        assert first.startswith(f'peers: same Yahoo industry "{PHARMA}", nearest market cap first (4):')
        assert res.provenance()["peers"] == first
        assert res.status == fr.STATUS_OK
        for auto in ("MARUTI", "M&M", "HEROMOTOCO", "BAJAJ-AUTO", "TMPV"):
            assert f"  {auto}:" not in res.text

    def test_peers_unavailable_is_said_with_its_reason(self, market):
        yahoo, searches = market
        res = bb._fetch_peers_valuation(_query("TATASTEEL"), "generic")
        assert res.text.startswith("peers unavailable: 1 other known symbol(s)")
        assert "No peer comparison" in res.text.splitlines()[0]
        assert res.reason.startswith("peers unavailable:")
        assert "no peers to compare with" in res.reason
        assert res.provenance()["peers"].startswith("peers unavailable:")
        assert searches == []            # no peer search at all, automobile or other
        assert "=== Peer Valuation" not in res.text

    @pytest.mark.parametrize("ticker", ["SUNPHARMA", "TATASTEEL", "NOCLASS"])
    def test_the_status_is_the_own_data_and_peers_never_make_the_gate_abstain(self, market,
                                                                              ticker):
        """Decision recorded in the receipt: peers_valuation is essential, and an
        abstaining gate drops a re-dived shelf idea and refuses a watchlist buy
        even in record mode. A stock whose own price and ratios are verified
        keeps `ok` with peers, without them, or with no industry at all."""
        from services.data.stores.data_health import assess_health
        res = bb._fetch_peers_valuation(_query(ticker), "generic")
        assert res.status == fr.STATUS_OK, res
        verdict = assess_health(sections={"peers_valuation": res.status, "fundamentals": "ok",
                                          "technicals": "ok"},
                                dimensions_scored=8, dimensions_expected=8)
        assert verdict["essential_unusable"] == {}

    def test_own_data_missing_is_still_not_ok_without_peers(self, market, monkeypatch):
        from core.intelligence.algorithms.indicators import fetcher as F
        monkeypatch.setattr(F, "get_price_history", lambda t, years=2: pd.DataFrame())
        res = bb._fetch_peers_valuation(_query("TATASTEEL"), "generic")
        assert res.status == fr.STATUS_FALLBACK
        assert res.reason.startswith("peers unavailable:")

    def test_no_peer_pe_searches_the_chosen_peers_never_automobile(self, market):
        yahoo, searches = market
        yahoo.no_pe = {"CIPLA.NS", "DRREDDY.NS", "LUPIN.NS", "ZYDUSLIFE.NS"}
        res = bb._fetch_peers_valuation(_query("SUNPHARMA"), "generic")
        assert res.status == fr.STATUS_OK
        assert "peer P/E unavailable; Serper fallback (chosen peers) found results" in res.reason
        flat = " ".join(q for qs in searches for q in qs)
        assert PHARMA in flat
        assert "automobile" not in flat.lower() and "MARUTI" not in flat
        assert all(s in flat for s in res.provenance()["peers"].split(": ")[-1].split(", ")[:3])

    def test_bundle_and_health_record_carry_the_rule_and_count(self, market):
        from services.data.stores.data_health import build_record
        stubbed = {n: (lambda *a, **k: fr.FetchResult("x", fr.STATUS_OK, "fixture"))
                   for n in ("_fetch_company_news", "_fetch_sector_policy_news",
                             "_fetch_macro_context", "_fetch_policy_deep_dive",
                             "_fetch_fundamentals", "_fetch_technicals", "_fetch_commodities",
                             "_fetch_flows_sentiment", "_fetch_dossier")}
        with patch.multiple(bb, **stubbed):
            bundle = bb.build_sector_bundle(_query("INFY"), "it_sector")
        prov = bundle.section_provenance["peers_valuation"]
        assert prov["peers"].startswith(f'peers: same Yahoo industry "{IT}", nearest market cap first (5):')
        row = build_record(run_id="r", ticker="INFY", sector="it_sector",
                           section_status=bundle.section_status, api_calls={},
                           dimensions_expected=[], dimensions_missing=[],
                           section_provenance=bundle.section_provenance)
        assert row["section_provenance"]["peers_valuation"]["peers"] == prov["peers"]
        assert "## PEERS_VALUATION\npeers: same Yahoo industry" in bundle.to_prompt_text()

    def test_warm_cache_adds_no_network_call_beyond_the_valuation(self, market):
        yahoo, _ = market
        bb._fetch_peers_valuation(_query("SUNPHARMA"), "generic")
        yahoo.asked.clear()
        res = bb._fetch_peers_valuation(_query("SUNPHARMA"), "generic")
        chosen = res.provenance()["peers"].split(": ")[-1].split(", ")
        # The valuation's own calls only: the stock once and each chosen peer once.
        assert sorted(yahoo.asked) == sorted(["SUNPHARMA.NS"] + [f"{c}.NS" for c in chosen])

    def test_legacy_valuation_builder_uses_the_same_rule(self, market):
        from services.data.context.builder import ContextBuilder
        cb = ContextBuilder()
        cb._sector = "automobile"
        text = cb._build_valuation_catalyst(_query("SUNPHARMA"))
        assert text.startswith(f'peers: same Yahoo industry "{PHARMA}"')
        assert "  MARUTI:" not in text
