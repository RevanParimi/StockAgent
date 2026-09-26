"""
tests/unit/shared/test_data_health_contract.py
===============================================
SA-002 — data-health records describe usable evidence (audit F07).

Production evidence (spec 2026-08-24 §15.1): two TATAMOTORS runs against a
symbol whose price source answered HTTP 404 were recorded `health=ok`,
`live=10`, `dims 9/9`. Each producer had wrapped its failure in a sentence,
and B2 classified any nonempty sentence as `ok`; `derive_health` then looked
at dimensions only.

The expected values below come from what each fixture MEANS — "the price
source returned nothing", "the statement is a year old" — never from running
the implementation. Every provider is patched, and an autouse guard fails any
non-loopback connection, so nothing here can reach a real service.
"""
from __future__ import annotations

import importlib
import json
import os
import socket
import sqlite3
from contextlib import contextmanager
from datetime import date, timedelta
from unittest import mock
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

import services.data.stores.data_health as dh
import services.data.stores.log_store as log_store
from backend.shared.pipeline.base_orchestrator import BaseSectorOrchestrator
from backend.shared.pipeline.unified_analyst import DIMENSIONS
from core.schemas.pipeline import AgentOutput, FinalReport, StockQuery
from services.data.context import bundle_builder as bb
from services.data.context import fetch_result as fr

LIVE = {fr.STATUS_OK, fr.STATUS_CACHE_HIT}
TODAY = date.today()


# ---------------------------------------------------------------------------
# Isolation: no real transport, no real data directory
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    real_connect = socket.socket.connect
    real_getaddrinfo = socket.getaddrinfo

    def _loopback(host) -> bool:
        return str(host) in ("localhost", "::1") or str(host).startswith("127.")

    def connect(self, address):
        host = address[0] if isinstance(address, tuple) else address
        if not _loopback(host):
            raise AssertionError(f"test tried to reach {address!r}")
        return real_connect(self, address)

    def getaddrinfo(host, *a, **k):
        if not _loopback(host):
            raise AssertionError(f"test tried to resolve {host!r}")
        return real_getaddrinfo(host, *a, **k)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)


@pytest.fixture()
def health_log(tmp_path):
    target = tmp_path / "logs"
    clean = {k: v for k, v in os.environ.items() if k != "LOGS_DIR"}
    clean["LOGS_DIR"] = str(target)
    with mock.patch.dict(os.environ, clean, clear=True):
        importlib.reload(dh)
        yield target / "data_health.jsonl"
    importlib.reload(dh)


@pytest.fixture()
def fresh_db(tmp_path, monkeypatch):
    db_path = tmp_path / "telemetry.db"
    monkeypatch.setattr(log_store.settings, "TELEMETRY_DB_PATH", str(db_path), raising=False)
    monkeypatch.setattr(log_store, "_conn", None)
    yield db_path
    if log_store._conn is not None:
        log_store._conn.close()
        log_store._conn = None


# ---------------------------------------------------------------------------
# Provider fixtures
# ---------------------------------------------------------------------------

def _last_session(day: date) -> date:
    """The last weekday on or before `day`: the newest bar a market can have."""
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


def _bars(last: date, n: int = 300) -> pd.DataFrame:
    """`n` daily bars, the newest on the last session on or before `last`.

    Roll back first (review M1, 2026-09-26): with pandas 3,
    `bdate_range(end=<Sat or Sun>, periods=n)` returns n-1 dates, the frame
    below then raised inside the fake download, and every producer saw an
    empty frame whenever a fixture date fell on a weekend.
    """
    idx = pd.bdate_range(end=pd.offsets.BDay().rollback(pd.Timestamp(last)), periods=n)
    close = 100.0 + np.cumsum(np.sin(np.arange(n) / 7.0))
    return pd.DataFrame({"Open": close, "High": close + 1, "Low": close - 1,
                         "Close": close, "Volume": np.arange(n) * 10.0 + 1000}, index=idx)


def _quarter_ends(newest_quarter_end: date) -> list[date]:
    """The five listed quarter ends, newest first."""
    return [newest_quarter_end - timedelta(days=91 * i) for i in range(5)]


def _statement(newest_quarter_end: date, revenue: bool = True,
               blank: dict[str, list[int]] | None = None, fill=np.nan) -> pd.DataFrame:
    """A quarterly income statement. `blank` maps a row to the quarter
    indexes (0 = newest) that hold `fill` instead of a figure: NaN is how
    yfinance lists an announced quarter before its numbers are populated."""
    ends = [pd.Timestamp(d) for d in _quarter_ends(newest_quarter_end)]
    rows = {"Operating Income": [2e9, 1.8e9, 1.7e9, 1.6e9, 1.5e9]}
    if revenue:
        rows["Total Revenue"] = [1e10, 9e9, 8.5e9, 8e9, 7.5e9]
    df = pd.DataFrame(rows, index=ends).T
    if fill is None:
        df = df.astype(object)
    for row, quarters in (blank or {}).items():
        for i in quarters:
            df.loc[row, ends[i]] = fill
    return df


_GOOD_INFO = {"trailingPE": 22.5, "forwardPE": 20.1, "priceToBook": 3.2, "trailingEps": 45.0,
              "forwardEps": 50.0, "marketCap": 5e11, "enterpriseToEbitda": 12.0,
              "priceToSalesTrailingTwelveMonths": 2.1, "heldPercentInstitutions": 0.35,
              "heldPercentInsiders": 0.5, "fullTimeEmployees": 1000, "currentPrice": 101.0}


class Market:
    """What every provider answers, per symbol. Defaults are a healthy market."""

    def __init__(self):
        self.today = TODAY                             # the day the defaults are fresh for
        self.bars_last: dict[str, date | None] = {}      # symbol -> newest bar; None = 404
        self.statement: dict[str, pd.DataFrame | Exception] = {}
        self.info: dict[str, dict] = {}
        self.serper_answers = True
        self.tavily_results = [{"title": "Circular", "content": "Policy text", "url": "u"}]

    def download(self, sym, *a, **k):
        fresh = self.today - timedelta(days=1)
        if isinstance(sym, list):                      # index correlation pair
            frames = {}
            for s in sym:
                last = self.bars_last.get(s.replace(".NS", ""), fresh)
                if last is None:
                    return pd.DataFrame()
                frames[("Close", s)] = _bars(last)["Close"]
            return pd.DataFrame(frames)
        last = self.bars_last.get(sym.replace(".NS", ""), fresh)
        return pd.DataFrame() if last is None else _bars(last)

    def ticker(self, sym):
        base = sym.replace(".NS", "")
        t = MagicMock()
        t.info = self.info.get(base, _GOOD_INFO)
        st = self.statement.get(base, _statement(self.today - timedelta(days=88)))
        if isinstance(st, Exception):
            type(t).quarterly_income_stmt = mock.PropertyMock(side_effect=st)
        else:
            t.quarterly_income_stmt = st
        t.major_holders = pd.DataFrame([["50.0%"]])
        return t

    def serper(self, query, **k):
        if not self.serper_answers:
            return []
        return [{"title": f"Story on {query[:24]}", "snippet": "text", "link": "l",
                 "date": "2 days ago"}]


@pytest.fixture()
def market(tmp_path):
    m = Market()
    from services.data.fetchers import macro as macro_mod
    from services.data.fetchers import news as news_mod
    from services.clients import tavily_fetcher as tav
    patches = [
        patch("yfinance.download", side_effect=m.download),
        patch("yfinance.Ticker", side_effect=m.ticker),
        patch("time.sleep", return_value=None),
        patch("backend.shared.data.fetchers.symbol_resolver.resolve_yf_symbol",
              side_effect=lambda t: f"{t}.NS"),
        patch("backend.shared.data.fetchers.symbol_resolver.heal_symbol", return_value=None),
        patch.object(news_mod, "search_serper", side_effect=m.serper),
        patch.object(news_mod, "search_newsapi", return_value=[]),
        patch.object(tav, "_TAVILY_CACHE_DIR", tmp_path / "tavily"),
        patch.object(tav, "search_tavily", side_effect=lambda q, **k: list(m.tavily_results)),
        patch.object(macro_mod, "_fetch_rubber_price_via_news", return_value={}),
        patch.dict(macro_mod._COMMODITY_CACHE, {}, clear=True),
        patch.dict(macro_mod._RBI_CACHE, {}, clear=True),
        patch("services.data.cache.macro_cache.get_macro_cache", return_value=None),
        patch("services.data.fetchers.nse_market.get_nse_market_data", return_value={
            "fetched_at": TODAY.isoformat(), "fii_net_cr": 1200.0, "dii_net_cr": -300.0,
            "bulk_deal_net_buyers": ["ABC"], "bulk_deal_net_sellers": [],
            "bulk_deals_by_ticker": {}}),
        patch("services.data.fetchers.mf_herding.get_sector_mf_herding", return_value={
            "avg_momentum_pct": 1.2, "institutional_flow": "INFLOW", "fund_count": 3,
            "sector": "automobile", "fetched_at": TODAY.isoformat(), "individual": []}),
        patch("core.intelligence.rl.stores.prediction_store.PredictionStore",
              return_value=MagicMock(load_dossier=MagicMock(return_value=None))),
        patch.object(bb.settings, "get_serper_key", return_value="fixture-key"),
    ]
    for p in patches:
        p.start()
    try:
        yield m
    finally:
        for p in reversed(patches):
            p.stop()


def _query(ticker="TATAMOTORS"):
    return StockQuery(ticker=ticker, company_name=f"{ticker} Ltd", nse_data={})


# ---------------------------------------------------------------------------
# 0. The fixtures mean the same on every weekday (review M1, 2026-09-26)
# ---------------------------------------------------------------------------

WEEK = [date(2026, 9, 21) + timedelta(days=i) for i in range(7)]   # Mon 21 .. Sun 27 Sep


def _weekday(day: date) -> str:
    return day.strftime("%a")


@contextmanager
def _run_on(market, day: date):
    """Run as if on `day`: the market's defaults, and the one clock the
    freshness rule reads (`fetch_result.is_stale`). The date class is
    replaced in that module only; a process-wide shim breaks other code."""
    pinned = type("_PinnedDate", (date,), {"today": classmethod(lambda cls: day)})
    market.today = day
    with patch.object(fr, "date", pinned):
        yield


class TestFixturesHoldOnEveryWeekday:
    """The suite first passed on the Saturday it was written and failed on
    Sundays, Mondays and Tuesdays: the price fixture broke whenever its end
    date fell on a weekend, so the healthy series read `empty`. These pin a
    fixed Monday-to-Sunday week instead of the day the suite happens to run."""

    @pytest.mark.parametrize("end", WEEK, ids=_weekday)
    def test_bars_hold_every_bar_and_end_on_the_last_session(self, end):
        df = _bars(end)
        assert len(df) == 300
        assert df.index.is_unique and df.index.is_monotonic_increasing
        assert {ts.weekday() for ts in df.index} <= {0, 1, 2, 3, 4}
        assert df.index[-1].date() == _last_session(end)

    @pytest.mark.parametrize("day", WEEK, ids=_weekday)
    def test_the_price_fixtures_mean_fresh_and_stale_on_every_run_day(self, market, day):
        from core.intelligence.algorithms.indicators.fetcher import (
            get_technical_result, get_valuation_result,
        )
        with _run_on(market, day):
            fresh = get_technical_result("TATAMOTORS")
            valuation = get_valuation_result("TATAMOTORS", peer_tickers=["MARUTI"])
            market.bars_last["TATAMOTORS"] = day - timedelta(days=30)
            old = get_technical_result("TATAMOTORS")
        assert fresh.status == fr.STATUS_OK, fresh
        assert fresh.as_of == _last_session(day - timedelta(days=1)).isoformat()
        assert valuation.status == fr.STATUS_OK, valuation
        assert old.status == fr.STATUS_STALE, old


# ---------------------------------------------------------------------------
# 1. Producers: each case's status is decided by the producer, not its text
# ---------------------------------------------------------------------------

class TestEssentialProducers:
    """Parameterised over the case table the story names: verified, empty,
    exception, provider error text, stale, synthetic."""

    @pytest.mark.parametrize("case,setup,expected", [
        ("verified", {}, fr.STATUS_OK),
        ("empty: price source 404", {"bars_last": None}, fr.STATUS_EMPTY),
        ("stale: newest bar 30 days old",
         {"bars_last": TODAY - timedelta(days=30)}, fr.STATUS_STALE),
    ])
    def test_technicals(self, market, case, setup, expected):
        from core.intelligence.algorithms.indicators.fetcher import get_technical_result
        if "bars_last" in setup:
            market.bars_last["TATAMOTORS"] = setup["bars_last"]
        res = get_technical_result("TATAMOTORS")
        assert res.status == expected, (case, res)
        assert res.text.strip()               # nonempty in every case, including the dead one
        if expected != fr.STATUS_OK:
            assert res.reason

    @pytest.mark.parametrize("case,statement,expected", [
        ("verified", _statement(TODAY - timedelta(days=88)), fr.STATUS_OK),
        ("empty: no statement", pd.DataFrame(), fr.STATUS_EMPTY),
        ("exception inside the provider", ValueError("HTTP 404 Quote not found"),
         "failed:ValueError"),
        ("stale: newest quarter 300 days old", _statement(TODAY - timedelta(days=300)),
         fr.STATUS_STALE),
        ("synthetic: revenue row absent, zeros shown",
         _statement(TODAY - timedelta(days=88), revenue=False), fr.STATUS_FALLBACK),
    ])
    def test_fundamentals(self, market, case, statement, expected):
        from services.data.fetchers.fundamentals import get_fundamentals_result
        market.statement["TATAMOTORS"] = statement
        res = get_fundamentals_result("TATAMOTORS")
        assert res.status == expected, (case, res)
        assert res.text.startswith("=== Fundamentals: TATAMOTORS ===")
        if expected != fr.STATUS_OK:
            assert res.reason

    def test_fundamentals_as_of_is_the_newest_quarter(self, market):
        from services.data.fetchers.fundamentals import get_fundamentals_result
        newest = TODAY - timedelta(days=88)
        market.statement["TATAMOTORS"] = _statement(newest)
        assert get_fundamentals_result("TATAMOTORS").as_of == newest.isoformat()

    BOTH = ("Total Revenue", "Operating Income")

    @pytest.mark.parametrize("case,blank,fill,expected,reported", [
        ("newest quarter listed but unpopulated (every row NaN)",
         {r: [0] for r in BOTH}, np.nan, fr.STATUS_FALLBACK, 1),
        ("newest quarter revenue NaN", {"Total Revenue": [0]}, np.nan, fr.STATUS_FALLBACK, 1),
        ("newest quarter operating income NaN", {"Operating Income": [0]}, np.nan,
         fr.STATUS_FALLBACK, 1),
        ("newest quarter revenue None, rendered as a 0.0 figure", {"Total Revenue": [0]}, None,
         fr.STATUS_FALLBACK, 1),
        ("newest quarter revenue infinite", {"Total Revenue": [0]}, np.inf,
         fr.STATUS_FALLBACK, 1),
        ("newest two quarters NaN", {"Total Revenue": [0, 1]}, np.nan, fr.STATUS_FALLBACK, 2),
        ("no quarter has a figure", {r: [0, 1, 2, 3, 4] for r in BOTH}, np.nan,
         fr.STATUS_FALLBACK, None),
        ("only an older quarter NaN: named, not a status change", {"Total Revenue": [2]},
         np.nan, fr.STATUS_OK, 0),
    ])
    def test_fundamentals_quarters_without_figures(self, market, case, blank, fill, expected,
                                                   reported):
        """Review M2: a listed quarter is not a reported one. The newest
        quarter ended 30 days ago, so it is inside every freshness bound: only
        the missing figures can make the section unverified."""
        from core.config import settings as s
        from services.data.fetchers.fundamentals import get_fundamentals_result
        newest = TODAY - timedelta(days=30)
        ends = _quarter_ends(newest)
        market.statement["TATAMOTORS"] = _statement(newest, blank=blank, fill=fill)
        res = get_fundamentals_result("TATAMOTORS")
        assert res.status == expected, (case, res)
        assert res.as_of == (None if reported is None else ends[reported].isoformat()), case
        for row, quarters in blank.items():         # every blank quarter the section reads is named
            for i in quarters:
                if i < s.FINANCIALS_LOOKBACK_QUARTERS:
                    assert ends[i].isoformat() in res.reason, (case, row, i, res.reason)
        assert res.text.startswith("=== Fundamentals: TATAMOTORS ===")

    @pytest.mark.parametrize("case,price,info,serper,expected", [
        ("verified", "fresh", "good", True, fr.STATUS_OK),
        ("stale price", "old", "good", True, fr.STATUS_STALE),
        ("synthetic: price replaced by search snippets", "none", "good", True,
         fr.STATUS_FALLBACK),
        ("synthetic: ratios replaced by search snippets", "fresh", "none", True,
         fr.STATUS_FALLBACK),
        ("provider error text only: nothing found anywhere", "none", "none", False,
         fr.STATUS_EMPTY),
    ])
    def test_valuation(self, market, case, price, info, serper, expected):
        from core.intelligence.algorithms.indicators.fetcher import get_valuation_result
        market.bars_last["TATAMOTORS"] = {"fresh": TODAY - timedelta(days=1),
                                          "old": TODAY - timedelta(days=30),
                                          "none": None}[price]
        if info == "none":
            market.info["TATAMOTORS"] = {}
        market.serper_answers = serper
        res = get_valuation_result("TATAMOTORS", peer_tickers=["MARUTI", "M&M"])
        assert res.status == expected, (case, res)
        assert res.text.strip()
        if expected == fr.STATUS_EMPTY:
            assert "[No results for:" in res.text   # the sentence that used to read `ok`


class TestNoDataTextIsNeverHealthy:
    """Acceptance 1: a provider no-data message never becomes healthy merely
    because it is nonempty. Each fixture's text is asserted nonempty first,
    so the test cannot pass on an empty string."""

    def test_news_no_results(self, market):
        from services.data.fetchers.news import fetch_news_result
        market.serper_answers = False
        res = fetch_news_result(["anything"], max_queries=1)
        assert res.text == "[No results for: anything]"
        assert res.status not in LIVE

    def test_tavily_no_results_live_and_then_from_cache(self, market):
        from services.clients.tavily_fetcher import fetch_tavily_result
        market.tavily_results = []
        first = fetch_tavily_result(["q"], max_queries=1, max_results_per_query=1)
        again = fetch_tavily_result(["q"], max_queries=1, max_results_per_query=1)
        assert first.text == again.text == "[No Tavily results for: q]"
        assert first.status not in LIVE
        assert again.source == "tavily_cache" and again.status not in LIVE

    def test_tavily_cache_with_results_is_a_cache_hit(self, market):
        from services.clients.tavily_fetcher import fetch_tavily_result
        fetch_tavily_result(["q2"], max_queries=1, max_results_per_query=1)
        hit = fetch_tavily_result(["q2"], max_queries=1, max_results_per_query=1)
        assert hit.status == fr.STATUS_CACHE_HIT

    def test_tavily_cache_entry_without_result_count_is_unverified(self, market):
        """A pre-SA-002 entry cannot say whether it holds results. It is still
        served (no extra Tavily call), but not counted as evidence."""
        from services.clients import tavily_fetcher as tav
        path = tav._cache_path(["legacy"], 1)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("[No Tavily results for: legacy]", encoding="utf-8")
        with patch.object(tav, "search_tavily") as live:
            res = tav.fetch_tavily_result(["legacy"], max_queries=1, max_results_per_query=1)
        live.assert_not_called()
        assert res.status == fr.STATUS_UNVERIFIED

    def test_technicals_unavailable_sentence(self, market):
        from core.intelligence.algorithms.indicators.fetcher import get_technical_result
        market.bars_last["TATAMOTORS"] = None
        res = get_technical_result("TATAMOTORS")
        assert res.text.startswith("Technical data unavailable for TATAMOTORS")
        assert res.status not in LIVE

    def test_macro_without_core_values(self, market):
        from core.config import settings as s
        from services.data.fetchers import macro as macro_mod
        market.bars_last[s.INR_USD_TICKER] = None
        res = macro_mod.get_macro_result()
        assert res.status not in LIVE and "INR/USD" in res.reason

    def test_flows_with_no_part(self, market):
        with patch("services.data.fetchers.nse_market.get_nse_market_data", return_value={}), \
             patch("services.data.fetchers.mf_herding.get_sector_mf_herding", return_value={}):
            res = bb._fetch_flows_sentiment(_query(), "automobile")
        assert res.status == fr.STATUS_EMPTY and res.reason


# ---------------------------------------------------------------------------
# 2. Health derivation — independent of any producer
# ---------------------------------------------------------------------------

NINE = list(DIMENSIONS["automobile"])
NOT_LIVE = [fr.STATUS_EMPTY, "failed:HTTPError", fr.STATUS_STALE, fr.STATUS_FALLBACK,
            fr.STATUS_UNVERIFIED]


def _row(sections, missing=()):
    return dh.build_record(run_id="r", ticker="TATAMOTORS", sector="automobile",
                           section_status=sections, api_calls=None,
                           dimensions_expected=NINE, dimensions_missing=list(missing))


class TestHealthDerivation:
    @pytest.mark.parametrize("live_section", bb.SECTION_ORDER)
    @pytest.mark.parametrize("dead", NOT_LIVE)
    def test_nine_of_nine_with_one_live_section_is_never_ok(self, live_section, dead):
        """Acceptance 2, over every choice of the one live section and every
        way the other nine can be dead."""
        sections = {n: dead for n in bb.SECTION_ORDER}
        sections[live_section] = fr.STATUS_OK
        row = _row(sections)
        assert row["dimensions_scored"] == 9
        assert row["health"] != dh.HEALTH_OK
        assert row["health_reasons"]

    def test_every_section_verified_and_every_dimension_scored_is_ok(self):
        row = _row({n: fr.STATUS_OK for n in bb.SECTION_ORDER})
        assert row["health"] == dh.HEALTH_OK
        assert row["health_reasons"] == [] and row["essential_unusable"] == {}

    def test_not_applicable_is_a_decision_not_a_defect(self):
        sections = {n: fr.STATUS_OK for n in bb.SECTION_ORDER}
        sections["commodities"] = fr.STATUS_NOT_APPLICABLE
        sections["dossier"] = fr.STATUS_NOT_APPLICABLE
        sections["macro_context"] = fr.STATUS_CACHE_HIT
        assert _row(sections)["health"] == dh.HEALTH_OK

    @pytest.mark.parametrize("dead", NOT_LIVE)
    @pytest.mark.parametrize("section", bb.SECTION_ORDER)
    def test_any_single_unusable_section_degrades(self, section, dead):
        sections = {n: fr.STATUS_OK for n in bb.SECTION_ORDER}
        sections[section] = dead
        row = _row(sections)
        assert row["health"] == dh.HEALTH_DEGRADED
        essential = section in dh.DEFAULT_ESSENTIAL_SECTIONS
        assert (section in row["essential_unusable"]) is essential

    def test_counts_partition_the_sections(self):
        statuses = [fr.STATUS_OK, fr.STATUS_CACHE_HIT, fr.STATUS_EMPTY, "failed:X",
                    fr.STATUS_NOT_APPLICABLE, fr.STATUS_STALE, fr.STATUS_FALLBACK,
                    fr.STATUS_UNVERIFIED, "surprise", fr.STATUS_OK]
        row = _row(dict(zip(bb.SECTION_ORDER, statuses)))
        assert (row["live"], row["degraded"], row["empty"], row["not_applicable"],
                row["stale"], row["fallback"], row["unverified"]) == (3, 1, 1, 1, 1, 1, 2)
        assert sum(row[k] for k in ("live", "degraded", "empty", "not_applicable",
                                    "stale", "fallback", "unverified")) == 10

    def test_hollow_thresholds_are_unchanged(self):
        assert _row({n: fr.STATUS_OK for n in bb.SECTION_ORDER}, missing=NINE)["health"] \
            == dh.HEALTH_HOLLOW
        assert _row({n: fr.STATUS_STALE for n in bb.SECTION_ORDER})["health"] \
            == dh.HEALTH_HOLLOW


# ---------------------------------------------------------------------------
# 3. Readers: legacy rows accepted, provenance labelled unknown
# ---------------------------------------------------------------------------

_V1_SCHEMA = """
CREATE TABLE data_health (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, run_id TEXT NOT NULL,
    ticker TEXT NOT NULL, sector TEXT, sections TEXT,
    live INTEGER NOT NULL DEFAULT 0, degraded INTEGER NOT NULL DEFAULT 0,
    empty INTEGER NOT NULL DEFAULT 0, not_applicable INTEGER NOT NULL DEFAULT 0,
    dimensions_expected INTEGER NOT NULL DEFAULT 0, dimensions_scored INTEGER NOT NULL DEFAULT 0,
    dimensions_missing TEXT, api_calls TEXT, health TEXT);
"""
_V1_SECTIONS = {n: "ok" for n in bb.SECTION_ORDER}


class TestLegacyRows:
    def test_a_pre_sa002_database_migrates_and_both_contracts_read_back(self, fresh_db, health_log):
        """The prod table predates SA-002: create it with the B2 schema and a
        B2 row (the TATAMOTORS shape), then let the store open it."""
        con = sqlite3.connect(fresh_db)
        con.executescript(_V1_SCHEMA)
        con.execute(
            "INSERT INTO data_health (ts, run_id, ticker, sector, sections, live, degraded, "
            "empty, not_applicable, dimensions_expected, dimensions_scored, dimensions_missing, "
            "api_calls, health) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("2026-08-26T11:10:00+00:00", "v1run", "TATAMOTORS", "automobile",
             json.dumps(_V1_SECTIONS), 10, 0, 0, 0, 9, 9, "[]", "{}", "ok"))
        con.commit()
        con.close()

        mod = importlib.import_module("services.data.stores.data_health")
        sections = {n: fr.STATUS_OK for n in bb.SECTION_ORDER}
        sections["technicals"] = fr.STATUS_EMPTY
        mod.record_data_health(run_id="v2run", ticker="TATAMOTORS", sector="automobile",
                               section_status=sections, api_calls={},
                               dimensions_expected=NINE, dimensions_missing=[])

        rows = {r["run_id"]: r for r in mod.recent_health_rows(10)}
        v1, v2 = rows["v1run"], rows["v2run"]
        assert v1["contract_version"] == dh.LEGACY_CONTRACT_VERSION
        assert v1["provenance_known"] is False
        assert v1["health"] == "ok"                                  # kept as written...
        assert v1["health_basis"].startswith("v1")                   # ...and labelled
        assert {p["source"] for p in v1["section_provenance"].values()} == {"unknown"}
        assert v1["essential_unusable"] is None
        assert v2["contract_version"] == dh.CONTRACT_VERSION and v2["provenance_known"] is True
        assert v2["health"] == dh.HEALTH_DEGRADED
        assert v2["essential_unusable"] == {"technicals": fr.STATUS_EMPTY}

        assert log_store.data_health_count() == 2
        assert log_store.data_health_count(health="ok", contract_version=1) == 1
        assert log_store.data_health_count(health="ok", contract_version=2) == 0

    def test_a_v1_jsonl_line_normalizes_with_unknown_provenance(self):
        line = json.dumps({"ts": "2026-08-26T11:10:00+00:00", "run_id": "x",
                           "ticker": "TATAMOTORS", "sector": "automobile",
                           "sections": _V1_SECTIONS, "live": 10, "degraded": 0, "empty": 0,
                           "not_applicable": 0, "dimensions_expected": 9,
                           "dimensions_scored": 9, "dimensions_missing": [], "api_calls": {},
                           "health": "ok"})
        row = dh.normalize_health_row(json.loads(line))
        assert row["contract_version"] == 1 and row["provenance_known"] is False
        assert set(row["section_provenance"]) == set(bb.SECTION_ORDER)

    @pytest.mark.parametrize("bad", ["two", {"x": 1}, 0])
    def test_a_malformed_version_is_read_as_unknown_not_raised(self, bad):
        row = dh.normalize_health_row({"contract_version": bad, "sections": "{not json"})
        assert row["provenance_known"] is False


# ---------------------------------------------------------------------------
# 4. Integration: bundle -> health row -> what a watchdog or the UI reads
# ---------------------------------------------------------------------------

class _DummyAgent:
    def run(self, query, run_id):  # pragma: no cover - the graph is never invoked
        return AgentOutput(agent="dummy", ticker=query.ticker, overall_score=0.5)


class _AutoOrchestrator(BaseSectorOrchestrator):
    SECTOR_NAME = "automobile"

    def __init__(self) -> None:
        self._sub_agents = {"dummy": _DummyAgent()}
        super().__init__()


def _nine_scored():
    return {d: AgentOutput(agent=d, ticker="TATAMOTORS", overall_score=0.6) for d in NINE}


def _run(ticker="TATAMOTORS"):
    with patch("backend.shared.pipeline.base_orchestrator.get_llm_client",
               return_value=MagicMock()):
        orch = _AutoOrchestrator()
    orch._aggregator = MagicMock()
    analyst = MagicMock()
    analyst.run.return_value = _nine_scored()
    analyst._last_prompt_tokens = analyst._last_completion_tokens = 0
    captured = {}
    real_build = bb.build_sector_bundle

    def build(query, sector):
        captured["bundle"] = real_build(query, sector)
        return captured["bundle"]

    with patch("services.data.context.bundle_builder.build_sector_bundle", side_effect=build), \
         patch("backend.shared.pipeline.unified_analyst.UnifiedAnalyst", return_value=analyst):
        orch._run_unified(_query(ticker), run_id=f"run-{ticker}")
    report = FinalReport(ticker=ticker, company_name=f"{ticker} Ltd", final_score=0.6,
                         verdict="BUY", weighted_agent_scores={})
    report.data_health = orch._last_data_health
    return captured["bundle"], orch._last_data_health, report.model_dump()


class TestBundleToRecordToReaders:
    def test_the_tatamotors_404_run_is_not_healthy_anywhere(self, market, health_log, fresh_db):
        """The §15.1 case end to end: every other source answers, the price
        source returns nothing, the analyst still scores 9/9. B2 wrote
        `health=ok, live=10`; each consumer must now see why it is not."""
        market.bars_last["TATAMOTORS"] = None
        market.statement["TATAMOTORS"] = pd.DataFrame()
        market.info["TATAMOTORS"] = {}

        bundle, record, payload = _run()

        # Bundle: the producers said so, with their text still nonempty.
        for name in ("technicals", "fundamentals", "peers_valuation"):
            assert bundle.sections[name].strip()
            assert bundle.section_status[name] not in LIVE, name
        assert bundle.has_real_data is True       # B2's flag is deliberately unchanged

        # Record.
        assert record["contract_version"] == dh.CONTRACT_VERSION
        assert record["dimensions_scored"] == 9
        assert record["health"] == dh.HEALTH_DEGRADED
        assert set(record["essential_unusable"]) == {"technicals", "fundamentals",
                                                     "peers_valuation"}

        # UI: the report payload the analyse/stream routes return.
        assert payload["data_health"]["health"] == dh.HEALTH_DEGRADED
        assert payload["data_health"]["essential_unusable"] == record["essential_unusable"]

        # Watchdog-style readers: the JSONL line and the telemetry row agree.
        line = json.loads(health_log.read_text(encoding="utf-8").strip().splitlines()[-1])
        db_row = dh.recent_health_rows(1)[0]
        for row in (dh.normalize_health_row(line), db_row):
            assert row["provenance_known"] is True
            assert row["health"] == dh.HEALTH_DEGRADED
            assert set(row["essential_unusable"]) == set(record["essential_unusable"])
        assert log_store.data_health_count(health=dh.HEALTH_OK, contract_version=2) == 0

    def test_the_same_run_with_a_live_price_source_is_ok(self, market, health_log, fresh_db):
        """The counterpart that keeps the gate honest: with every provider
        answering, every real producer reports verified data and the run is
        `ok` — so `degraded` above is caused by the dead source, not by a
        rule that never says `ok`."""
        bundle, record, payload = _run()

        assert {p["source"] for p in bundle.section_provenance.values()}.isdisjoint({"untyped"})
        assert record["health"] == dh.HEALTH_OK, record["health_reasons"]
        assert record["essential_unusable"] == {}
        assert bundle.section_provenance["technicals"]["as_of"] == \
            _last_session(TODAY - timedelta(days=1)).isoformat()
        assert payload["data_health"]["health"] == dh.HEALTH_OK

    def test_a_listed_but_unpopulated_quarter_is_not_usable_evidence(self, market, health_log,
                                                                     fresh_db):
        """Review M2 end to end: every provider answers, but yfinance lists
        the newest quarter (ended 30 days ago) before its figures exist."""
        newest = TODAY - timedelta(days=30)
        market.statement["TATAMOTORS"] = _statement(
            newest, blank={"Total Revenue": [0], "Operating Income": [0]})

        bundle, record, payload = _run()

        assert bundle.section_status["fundamentals"] == fr.STATUS_FALLBACK
        assert bundle.section_provenance["fundamentals"]["as_of"] == \
            _quarter_ends(newest)[1].isoformat()
        assert record["health"] == dh.HEALTH_DEGRADED
        assert record["essential_unusable"] == {"fundamentals": fr.STATUS_FALLBACK}
        assert payload["data_health"]["essential_unusable"] == record["essential_unusable"]
        assert dh.recent_health_rows(1)[0]["essential_unusable"] == record["essential_unusable"]
