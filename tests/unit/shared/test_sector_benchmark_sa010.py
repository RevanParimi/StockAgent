"""
tests/unit/shared/test_sector_benchmark_sa010.py
=================================================
SA-010 — sector benchmarks reach the technical-data calls (audit F20).

Before: `get_technical_result(ticker)` called `get_peer_correlation(ticker)`,
whose default index was `^CNXAUTO`, for every sector. On 2026-09-23 and
2026-10-02 every review analysis, banks and IT included, asked Yahoo for
`^CNXAUTO`; Yahoo had no data for it, and the prompt then read
"Nifty Auto Correlation: 0.0 | Beta: 1.0", a substitute shaped like a
measurement.

The expected values here come from what each fixture means: the index table
is written out below, not read from settings, and every correlation and beta
is computed with numpy from the fixture's own closes. Yahoo is a fake that
records each call; nothing here reaches a real service.
"""
from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from backend.shared.pipeline.base_orchestrator import BaseSectorOrchestrator
from core.intelligence.algorithms.indicators import fetcher
from core.schemas.pipeline import StockQuery
from services.data.context import bundle_builder as bb
from services.data.context import fetch_result as fr
from services.data.context.builder import ContextBuilder

# The benchmark each sector must be measured against, written out by hand.
EXPECTED_INDEX = {
    "automobile":       ("^CNXAUTO",   "Nifty Auto"),
    "banking_bfsi":     ("^NSEBANK",   "Nifty Bank"),
    "it_sector":        ("^CNXIT",     "Nifty IT"),
    "renewable_energy": ("^CNXENERGY", "Nifty Energy"),
    "generic":          ("^NSEI",      "Nifty 50 (broad market)"),
}
AUTO_INDEX = "^CNXAUTO"
NON_AUTO = ["banking_bfsi", "it_sector", "renewable_energy", "generic"]
INDEXES = {sym for sym, _ in EXPECTED_INDEX.values()}


# ---------------------------------------------------------------------------
# Fixtures: a fake Yahoo and deterministic closes
# ---------------------------------------------------------------------------

def _sessions(n: int, last: date | None = None) -> pd.DatetimeIndex:
    """`n` weekday sessions ending on the last weekday on or before `last`
    (rolled back first: pandas 3's bdate_range drops a weekend end date)."""
    end = pd.offsets.BDay().rollback(pd.Timestamp(last or date.today()))
    return pd.bdate_range(end=end, periods=n)


def _closes(index: pd.DatetimeIndex, seed: int, beta: float = 1.0,
            base: np.ndarray | None = None) -> pd.Series:
    """A close series. With `base` (another series' daily returns) its own
    returns are beta * base + noise, so the pair is truly correlated."""
    rng = np.random.default_rng(seed)
    noise = rng.normal(0.0, 0.01, len(index) - 1)
    rets = noise if base is None else beta * base + noise
    return pd.Series(100.0 * np.cumprod(np.r_[1.0, 1.0 + rets]), index=index)


def _returns(s: pd.Series) -> np.ndarray:
    v = s.to_numpy()
    return v[1:] / v[:-1] - 1.0


def _expected(stock: pd.Series, index: pd.Series) -> tuple[float, float, int]:
    """Correlation and beta over the sessions both series have a close for,
    computed with numpy, independent of the fetcher's pandas code."""
    common = sorted(set(stock.dropna().index) & set(index.dropna().index))
    rs, ri = _returns(stock.loc[common]), _returns(index.loc[common])
    corr = float(np.corrcoef(rs, ri)[0, 1])
    beta = float(np.cov(rs, ri, ddof=1)[0, 1] / np.var(ri, ddof=1))
    return round(corr, 4), round(beta, 4), len(rs)


class Yahoo:
    """What yfinance.download answers, per symbol: a close series, or None
    for "possibly delisted; no price data" (^CNXAUTO and ^CNXENERGY on
    2026-10-05). Every call's symbol argument and keywords are recorded."""

    def __init__(self, closes: dict[str, pd.Series | None]):
        self.closes = closes
        self.calls: list[tuple[object, dict]] = []
        self.raise_on_pair: Exception | None = None

    def _series(self, sym: str) -> pd.Series | None:
        return self.closes.get(sym)

    def download(self, sym, *a, **k):
        self.calls.append((sym, k))
        if isinstance(sym, list):
            if self.raise_on_pair is not None:
                raise self.raise_on_pair
            cols = {}
            for s in sym:
                series = self._series(s)
                # yfinance keeps an all-NaN column for a symbol it has no data for
                cols[("Close", s)] = series if series is not None else pd.Series(dtype=float)
            frame = pd.DataFrame(cols)
            return frame if frame.notna().any().any() else pd.DataFrame()
        series = self._series(sym)
        if series is None:
            return pd.DataFrame()
        return pd.DataFrame({"Open": series, "High": series + 1, "Low": series - 1,
                             "Close": series, "Volume": 1000.0}, index=series.index)

    def paired_calls(self) -> list[list[str]]:
        return [s for s, _ in self.calls if isinstance(s, list)]

    def symbols(self) -> set[str]:
        out: set[str] = set()
        for s, _ in self.calls:
            out.update(s if isinstance(s, list) else [s])
        return out


def _market(stock: str = "HDFCBANK", n: int = 300, dead: tuple[str, ...] = ()) -> Yahoo:
    """Every configured index answers with `n` sessions, except `dead` ones;
    the stock's returns follow each index loosely."""
    idx = _sessions(n)
    base = _closes(idx, seed=1)
    closes: dict[str, pd.Series | None] = {f"{stock}.NS": _closes(idx, 2, 1.1, _returns(base))}
    for i, sym in enumerate(sorted(INDEXES)):
        closes[sym] = None if sym in dead else _closes(idx, 10 + i, 0.8, _returns(base))
    return Yahoo(closes)


@pytest.fixture()
def yahoo(monkeypatch):
    """Install a fake Yahoo; also block the symbol self-heal and resolve
    tickers to `<T>.NS` without the instrument registry."""
    holder = SimpleNamespace(y=None)

    def install(y: Yahoo) -> Yahoo:
        holder.y = y
        return y

    monkeypatch.setattr(fetcher.yf, "download", lambda *a, **k: holder.y.download(*a, **k))
    monkeypatch.setattr(fetcher, "_nse_ticker", lambda t: f"{t}.NS")
    monkeypatch.setattr(fetcher.time, "sleep", lambda s: None)
    monkeypatch.setattr("backend.shared.data.fetchers.symbol_resolver.heal_symbol",
                        lambda t: None)
    return install


def _query(ticker: str = "HDFCBANK") -> StockQuery:
    return StockQuery(ticker=ticker, company_name=f"{ticker} Ltd", nse_data={})


def _corr_line(text: str) -> str:
    return next(line for line in text.splitlines() if "Correlation:" in line)


# ---------------------------------------------------------------------------
# 1. Provider-call arguments for every sector and the generic routing
# ---------------------------------------------------------------------------

class TestEverySectorCallsItsOwnBenchmark:

    @pytest.mark.parametrize("sector", list(EXPECTED_INDEX))
    def test_the_bundle_section_downloads_the_sector_index(self, yahoo, sector):
        y = yahoo(_market())
        res = bb._fetch_technicals(_query(), sector)
        symbol, label = EXPECTED_INDEX[sector]
        assert y.paired_calls() == [["HDFCBANK.NS", symbol]]
        assert res.provenance()["benchmark"] == symbol
        assert _corr_line(res.text).startswith(f"{label} Correlation: ")

    @pytest.mark.parametrize("sector", NON_AUTO)
    def test_no_other_sector_asks_for_the_automobile_index(self, yahoo, sector):
        y = yahoo(_market())
        res = bb._fetch_technicals(_query(), sector)
        assert AUTO_INDEX not in y.symbols()
        assert "Nifty Auto" not in res.text

    @pytest.mark.parametrize("sector", ["", "insurance", "pharma", "Automobile"])
    def test_a_sector_without_its_own_index_gets_the_market_not_auto(self, yahoo, sector):
        """The deliberate generic policy: an empty, unregistered or
        misspelt sector is measured against the broad market, named as such."""
        y = yahoo(_market())
        res = fetcher.get_technical_result("HDFCBANK", sector=sector)
        assert y.paired_calls() == [["HDFCBANK.NS", "^NSEI"]]
        assert _corr_line(res.text).startswith("Nifty 50 (broad market) Correlation: ")

    def test_get_peer_correlation_has_no_default_index(self):
        with pytest.raises(TypeError):
            fetcher.get_peer_correlation("HDFCBANK")          # noqa — the point of the test

    def test_the_technical_result_has_no_default_sector(self):
        with pytest.raises(TypeError):
            fetcher.get_technical_result("HDFCBANK")          # noqa — the point of the test

    @pytest.mark.parametrize("sector", list(EXPECTED_INDEX))
    def test_the_full_bundle_passes_its_sector_to_technicals(self, yahoo, sector):
        """build_sector_bundle, with every other section stubbed: the sector
        given to the bundle is the one technicals are measured against."""
        y = yahoo(_market())
        stub = fr.FetchResult("stub", fr.STATUS_OK, "fixture")
        others = ["_fetch_company_news", "_fetch_sector_policy_news", "_fetch_macro_context",
                  "_fetch_policy_deep_dive", "_fetch_fundamentals", "_fetch_commodities",
                  "_fetch_flows_sentiment", "_fetch_peers_valuation", "_fetch_dossier"]
        with patch.object(bb.settings, "get_serper_key", return_value="k"), \
             patch.multiple(bb, **{name: MagicMock(return_value=stub) for name in others}):
            bundle = bb.build_sector_bundle(_query(), sector)
        assert y.paired_calls() == [["HDFCBANK.NS", EXPECTED_INDEX[sector][0]]]
        assert bundle.section_provenance["technicals"]["benchmark"] == EXPECTED_INDEX[sector][0]


class TestScheduledAndApiPathsCarryTheSector:
    """The scheduled forecast/review and the API both pick an orchestrator by
    sector key (sector_router -> SectorRegistry), and its `_run_unified`
    builds the bundle with its own SECTOR_NAME."""

    @pytest.mark.parametrize("sector_key,index", [
        ("automobile", "^CNXAUTO"),
        ("banking_bfsi", "^NSEBANK"),
        ("it_sector", "^CNXIT"),
        ("renewable_energy", "^CNXENERGY"),
        ("insurance", "^NSEI"),        # STARHEALTH's sector: no native graph -> generic
    ])
    def test_the_routed_orchestrator_measures_against_its_index(self, yahoo, sector_key, index):
        from core.intelligence.rl.workflows.sector_router import get_orchestrator_class

        y = yahoo(_market())
        cls = get_orchestrator_class(sector_key)
        stub = fr.FetchResult("stub", fr.STATUS_OK, "fixture")
        others = ["_fetch_company_news", "_fetch_sector_policy_news", "_fetch_macro_context",
                  "_fetch_policy_deep_dive", "_fetch_fundamentals", "_fetch_commodities",
                  "_fetch_flows_sentiment", "_fetch_peers_valuation", "_fetch_dossier"]
        orch = SimpleNamespace(SECTOR_NAME=cls.SECTOR_NAME,
                               _record_data_health=lambda *a, **k: None)
        analyst = MagicMock()
        analyst.run.return_value = {}
        with patch.object(bb.settings, "get_serper_key", return_value="k"), \
             patch.multiple(bb, **{name: MagicMock(return_value=stub) for name in others}), \
             patch("backend.shared.pipeline.unified_analyst.UnifiedAnalyst",
                   return_value=analyst):
            BaseSectorOrchestrator._run_unified(orch, _query(), run_id="r1")
        bundle = analyst.run.call_args[0][1]
        assert y.paired_calls() == [["HDFCBANK.NS", index]]
        assert bundle.section_provenance["technicals"]["benchmark"] == index


class TestLegacyWorkerPoolCarriesTheSector:
    """The legacy per-agent fallback (fallback_legacy: true) builds each
    agent's context through ContextBuilder with the agent's own sector."""

    @staticmethod
    def _agent(sector: str, name: str):
        if sector == "automobile_orchestrator":
            from backend.sectors.automobile.pipeline.orchestrator import _SUB_AGENTS
            return _SUB_AGENTS[name]
        if sector == "generic":
            from backend.sectors.generic.pipeline.orchestrator import GenericSectorOrchestrator
            with patch("backend.shared.pipeline.base_orchestrator.get_llm_client",
                       return_value=MagicMock()):
                return GenericSectorOrchestrator()._sub_agents[name]
        import importlib
        return importlib.import_module(f"backend.sectors.{sector}.config.registry").AGENTS[name]

    @pytest.mark.parametrize("sector,name,index", [
        ("automobile_orchestrator", "pattern_analysis", "^CNXAUTO"),  # declares no sector
        ("automobile", "pattern_analysis", "^CNXAUTO"),
        ("renewable_energy", "technical", "^CNXENERGY"),
        ("generic", "technical", "^NSEI"),
    ])
    def test_a_technicals_agent_downloads_its_sectors_index(self, yahoo, sector, name, index):
        y = yahoo(_market())
        agent = self._agent(sector, name)
        context, live = agent._gather_context(_query())
        assert live is True
        assert y.paired_calls() == [["HDFCBANK.NS", index]]

    @pytest.mark.parametrize("sector", ["banking_bfsi", "it_sector"])
    def test_bank_and_it_chart_agents_fetch_no_index_at_all(self, yahoo, sector):
        """Their legacy pattern builders are search-only; neither reaches the
        automobile index (nor any other)."""
        y = yahoo(_market())
        agent = self._agent(sector, "pattern_analysis")
        with patch("services.data.fetchers.fundamentals.get_fundamentals_context",
                   return_value="fundamentals"), \
             patch("services.data.fetchers.news.fetch_news_context", return_value="news"):
            agent._gather_context(_query())
        assert not (y.symbols() & INDEXES)


# ---------------------------------------------------------------------------
# 2. The measurement: equal and unequal sessions, short history, null returns
# ---------------------------------------------------------------------------

class TestMeasurement:

    def test_auto_with_sufficient_data_is_the_measured_value(self, yahoo):
        """Equal sessions: the numbers are numpy's, the call window is the
        earlier one (252 + 30 days back to today), and the prompt line keeps
        its pre-SA-010 wording for automobile."""
        y = yahoo(_market("MARUTI"))
        corr = fetcher.get_peer_correlation("MARUTI", "^CNXAUTO")
        c, b, n = _expected(y.closes["MARUTI.NS"], y.closes["^CNXAUTO"])
        assert corr == {"benchmark": "^CNXAUTO", "correlation": c, "beta": b, "sessions": n}
        assert n == 299
        _, kw = y.calls[0]
        assert kw["start"] == (date.today() - timedelta(days=282)).isoformat()
        assert kw["end"] == date.today().isoformat()
        res = fetcher.get_technical_result("MARUTI", sector="automobile")
        assert _corr_line(res.text) == f"Nifty Auto Correlation: {c} | Beta: {b}"
        assert res.status == fr.STATUS_OK and res.reason is None

    def test_unequal_sessions_are_paired_over_common_sessions(self, yahoo):
        """The 2026-10-05 probe: the stock had 193 sessions, each index 188,
        and the index's newest bar lagged a day. Every return pairs the same
        two sessions for both series, so a gap in one never pairs a two-day
        return with a one-day return."""
        idx = _sessions(260)
        base = _closes(idx, seed=3)
        stock = _closes(idx, 4, 1.3, _returns(base))
        holidays = idx[::9].append(idx[-1:])               # index misses these sessions
        index = _closes(idx, 5, 0.9, _returns(base)).drop(holidays)
        yahoo(Yahoo({"HDFCBANK.NS": stock, "^NSEBANK": index}))
        corr = fetcher.get_peer_correlation("HDFCBANK", "^NSEBANK")
        c, b, n = _expected(stock, index)
        assert (corr["correlation"], corr["beta"], corr["sessions"]) == (c, b, n)
        assert n == len(index) - 1

    @pytest.mark.parametrize("closes,returns", [(31, 30), (30, 29), (2, 1)])
    def test_short_history_is_missing_evidence_below_30_returns(self, yahoo, closes, returns):
        idx = _sessions(closes)
        base = _closes(idx, seed=6)
        stock = _closes(idx, 7, 1.0, _returns(base))
        yahoo(Yahoo({"HDFCBANK.NS": stock, "^NSEBANK": base}))
        corr = fetcher.get_peer_correlation("HDFCBANK", "^NSEBANK")
        assert corr["sessions"] == returns
        if returns >= 30:
            c, b, _ = _expected(stock, base)
            assert (corr["correlation"], corr["beta"]) == (c, b)
            assert "unavailable" not in corr
        else:
            assert corr["correlation"] is None and corr["beta"] is None
            assert f"only {returns} paired daily returns" in corr["unavailable"]

    @pytest.mark.parametrize("case", ["stock all null", "no common session", "flat index"])
    def test_null_or_flat_returns_are_missing_evidence(self, yahoo, case):
        idx = _sessions(120)
        stock = _closes(idx, seed=8)
        index = _closes(idx, seed=9)
        if case == "stock all null":
            stock = pd.Series(np.nan, index=idx)
        elif case == "no common session":                  # alternate sessions only
            stock, index = stock.iloc[::2], index.iloc[1::2]
        else:
            index = pd.Series(18000.0, index=idx)
        yahoo(Yahoo({"HDFCBANK.NS": stock, "^NSEBANK": index}))
        corr = fetcher.get_peer_correlation("HDFCBANK", "^NSEBANK")
        assert corr["correlation"] is None and corr["beta"] is None
        assert corr["unavailable"]
        assert corr["benchmark"] == "^NSEBANK"

    def test_a_failed_download_is_missing_evidence(self, yahoo):
        y = yahoo(_market())
        y.raise_on_pair = ConnectionError("reset by peer")
        corr = fetcher.get_peer_correlation("HDFCBANK", "^NSEBANK")
        assert corr["correlation"] is None and corr["beta"] is None
        assert "ConnectionError" in corr["unavailable"]


# ---------------------------------------------------------------------------
# 3. An unavailable benchmark reads as missing, not as beta 1 / correlation 0
# ---------------------------------------------------------------------------

class TestUnavailableBenchmark:

    @pytest.mark.parametrize("sector", ["automobile", "renewable_energy"])
    def test_a_dead_index_is_unavailable_not_neutral(self, yahoo, sector):
        """^CNXAUTO and ^CNXENERGY served no data on 2026-10-05."""
        symbol, label = EXPECTED_INDEX[sector]
        yahoo(_market("TVSMOTOR", dead=("^CNXAUTO", "^CNXENERGY")))
        res = fetcher.get_technical_result("TVSMOTOR", sector=sector)
        line = _corr_line(res.text)
        assert line == (f"{label} Correlation: unavailable | Beta: unavailable "
                        f"(benchmark {symbol} returned no price data)")
        assert "0.0" not in line and "1.0" not in line
        assert f"{label} correlation unavailable: benchmark {symbol} returned no price data" \
            in res.reason
        # The stock's own data decide the status; the benchmark is context.
        assert res.status == fr.STATUS_OK
        assert res.provenance()["benchmark"] == symbol

    def test_the_bundle_records_why_in_the_health_provenance(self, yahoo):
        yahoo(_market("TVSMOTOR", dead=("^CNXAUTO",)))
        res = bb._fetch_technicals(_query("TVSMOTOR"), "automobile")
        prov = res.provenance()
        assert prov["benchmark"] == "^CNXAUTO"
        assert "returned no price data" in prov["reason"]

    def test_a_short_index_history_names_the_sessions_in_the_reason(self, yahoo):
        y = yahoo(_market("INFY"))
        y.closes["^CNXIT"] = y.closes["^CNXIT"].iloc[-12:]
        res = fetcher.get_technical_result("INFY", sector="it_sector")
        assert "Nifty IT correlation unavailable: only 11 paired daily returns with ^CNXIT" \
            in res.reason
        assert "Nifty IT Correlation: unavailable | Beta: unavailable" in res.text

    def test_the_log_line_names_ticker_sector_and_benchmark(self, yahoo, caplog):
        """Production verification greps these lines (correlated fetch logs)."""
        yahoo(_market("HDFCBANK", dead=("^CNXAUTO",)))
        with caplog.at_level("INFO", logger=fetcher.logger.name):
            fetcher.get_technical_result("HDFCBANK", sector="banking_bfsi")
        lines = [r.getMessage() for r in caplog.records if "[technicals]" in r.getMessage()]
        assert len(lines) == 1
        assert lines[0].startswith("[technicals] HDFCBANK sector=banking_bfsi benchmark=^NSEBANK")
        assert "returns" in lines[0] and "unavailable" not in lines[0]
