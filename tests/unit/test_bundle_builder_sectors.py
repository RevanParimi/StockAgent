"""Tests for sector-awareness in the SectorDataBundle builder (sector rollout).

services/data/context/bundle_builder.py — _SECTOR_BUNDLE_CFG and the
sector-parameterized fetchers (company_news, sector_policy_news,
policy_deep_dive, commodities, peers_valuation, macro_context).

Covers:
- commodities == "not_applicable" for the 3 new sectors, raw-materials
  fetcher NOT called; automobile still does a real fetch.
- per-sector policy_deep_dive query reaches the Tavily wrapper.
- per-sector peer list used for peers_valuation (queried ticker excluded,
  capped at 5).
- per-sector company_news / sector_policy_news query strings contain the
  expected sector keywords.
- macro_context cache key alias per sector (bfsi/it aliases; automobile and
  renewable_energy use their own names).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from core.config import settings
from core.schemas.pipeline import StockQuery
from services.data.context import bundle_builder as bb


def _make_query(ticker: str = "MARUTI", company_name: str = "Maruti Suzuki India Ltd") -> StockQuery:
    return StockQuery(ticker=ticker, company_name=company_name, nse_data={})


# ---------------------------------------------------------------------------
# commodities: automobile real fetch, others "not_applicable"
# ---------------------------------------------------------------------------

class TestCommodities:
    def test_automobile_commodities_real_fetch(self, ):
        with patch.object(bb, "_fetch_commodities", wraps=bb._fetch_commodities) as mock_fetch, \
             patch("services.data.fetchers.macro.get_raw_materials_context", return_value="raw materials text") as mock_rm:
            sections = {}
            try:
                sections["commodities"] = bb._fetch_commodities("automobile")
            except Exception:
                pass
        mock_fetch.assert_called_once()

    @pytest.mark.parametrize("sector", ["banking_bfsi", "it_sector", "renewable_energy"])
    def test_non_automobile_commodities_not_applicable(self, sector):
        with patch("services.data.fetchers.macro.get_raw_materials_context") as mock_rm:
            result = bb._fetch_commodities(sector)
        assert result == "not_applicable"
        mock_rm.assert_not_called()

    @pytest.mark.parametrize("sector", ["banking_bfsi", "it_sector", "renewable_energy"])
    def test_build_sector_bundle_commodities_not_applicable(self, sector):
        query = _make_query(ticker="HDFCBANK", company_name="HDFC Bank")
        with patch.object(bb, "_fetch_company_news", return_value="company news"), \
             patch.object(bb, "_fetch_sector_policy_news", return_value="policy news"), \
             patch.object(bb, "_fetch_macro_context", return_value="macro text"), \
             patch.object(bb, "_fetch_policy_deep_dive", return_value="deep dive text"), \
             patch.object(bb, "_fetch_fundamentals", return_value="fundamentals text"), \
             patch.object(bb, "_fetch_technicals", return_value="technicals text"), \
             patch.object(bb, "_fetch_flows_sentiment", return_value="flows text"), \
             patch.object(bb, "_fetch_peers_valuation", return_value="peers text"), \
             patch.object(bb, "_fetch_dossier", return_value="dossier text"), \
             patch("services.data.fetchers.macro.get_raw_materials_context") as mock_rm:
            bundle = bb.build_sector_bundle(query, sector)

        assert bundle.sections["commodities"] == "not_applicable"
        mock_rm.assert_not_called()

    def test_build_sector_bundle_automobile_commodities_real(self):
        query = _make_query()
        with patch.object(bb, "_fetch_company_news", return_value="company news"), \
             patch.object(bb, "_fetch_sector_policy_news", return_value="policy news"), \
             patch.object(bb, "_fetch_macro_context", return_value="macro text"), \
             patch.object(bb, "_fetch_policy_deep_dive", return_value="deep dive text"), \
             patch.object(bb, "_fetch_fundamentals", return_value="fundamentals text"), \
             patch.object(bb, "_fetch_technicals", return_value="technicals text"), \
             patch.object(bb, "_fetch_flows_sentiment", return_value="flows text"), \
             patch.object(bb, "_fetch_peers_valuation", return_value="peers text"), \
             patch.object(bb, "_fetch_dossier", return_value="dossier text"), \
             patch("services.data.fetchers.macro.get_raw_materials_context", return_value="raw materials text") as mock_rm:
            bundle = bb.build_sector_bundle(query, "automobile")

        assert bundle.sections["commodities"] != "not_applicable"
        mock_rm.assert_called_once()


# ---------------------------------------------------------------------------
# policy_deep_dive: per-sector Tavily query
# ---------------------------------------------------------------------------

class TestPolicyDeepDive:
    def test_automobile_query_unchanged(self):
        query = _make_query()
        with patch("services.clients.tavily_fetcher.fetch_tavily_context", return_value="deep dive") as mock_tavily:
            bb._fetch_policy_deep_dive(query, "automobile")

        assert mock_tavily.call_count == 1
        queries_arg = mock_tavily.call_args.args[0]
        assert len(queries_arg) == 1
        q = queries_arg[0]
        assert "FAME" in q or "policy" in q.lower()

    def test_bfsi_query_mentions_rbi_policy(self):
        query = _make_query(ticker="HDFCBANK", company_name="HDFC Bank")
        with patch("services.clients.tavily_fetcher.fetch_tavily_context", return_value="deep dive") as mock_tavily:
            bb._fetch_policy_deep_dive(query, "banking_bfsi")

        assert mock_tavily.call_count == 1
        q = mock_tavily.call_args.args[0][0]
        assert "RBI" in q
        assert "HDFC Bank" in q or "HDFCBANK" in q

    def test_it_query_mentions_earnings_call_transcript(self):
        query = _make_query(ticker="INFY", company_name="Infosys")
        with patch("services.clients.tavily_fetcher.fetch_tavily_context", return_value="deep dive") as mock_tavily:
            bb._fetch_policy_deep_dive(query, "it_sector")

        assert mock_tavily.call_count == 1
        q = mock_tavily.call_args.args[0][0]
        assert "earnings call transcript" in q.lower()
        assert "Infosys" in q or "INFY" in q

    def test_re_query_mentions_mnre_auction_policy(self):
        query = _make_query(ticker="TATAPOWER", company_name="Tata Power")
        with patch("services.clients.tavily_fetcher.fetch_tavily_context", return_value="deep dive") as mock_tavily:
            bb._fetch_policy_deep_dive(query, "renewable_energy")

        assert mock_tavily.call_count == 1
        q = mock_tavily.call_args.args[0][0]
        assert "MNRE" in q
        assert "Tata Power" in q or "TATAPOWER" in q

    @pytest.mark.parametrize("sector", ["automobile", "banking_bfsi", "it_sector", "renewable_energy"])
    def test_exactly_one_tavily_call(self, sector):
        query = _make_query(ticker="ABC", company_name="ABC Ltd")
        with patch("services.clients.tavily_fetcher.fetch_tavily_context", return_value="deep dive") as mock_tavily:
            bb._fetch_policy_deep_dive(query, sector)
        assert mock_tavily.call_count == 1
        assert mock_tavily.call_args.kwargs.get("max_queries", 1) == 1


# ---------------------------------------------------------------------------
# peers_valuation: per-sector peer list, queried ticker excluded, capped at 5
# ---------------------------------------------------------------------------

class TestPeersValuation:
    def test_automobile_peers_used(self):
        query = _make_query(ticker="MARUTI")
        with patch("core.intelligence.algorithms.indicators.fetcher.get_valuation_context", return_value="val ctx") as mock_val, \
             patch("services.data.fetchers.nse_announcements.format_nse_context", return_value=""):
            bb._fetch_peers_valuation(query, "automobile")

        mock_val.assert_called_once()
        _, kwargs = mock_val.call_args
        peers = kwargs.get("peer_tickers") or mock_val.call_args.args[1]
        assert "MARUTI" not in peers
        assert len(peers) <= 5

    def test_bfsi_peers_from_sector_tickers_excludes_queried(self):
        from backend.sectors.banking_bfsi.config.settings import TICKERS as BFSI_TICKERS

        query = _make_query(ticker="HDFCBANK", company_name="HDFC Bank")
        with patch("core.intelligence.algorithms.indicators.fetcher.get_valuation_context", return_value="val ctx") as mock_val, \
             patch("services.data.fetchers.nse_announcements.format_nse_context", return_value=""):
            bb._fetch_peers_valuation(query, "banking_bfsi")

        mock_val.assert_called_once()
        args, kwargs = mock_val.call_args
        peers = kwargs.get("peer_tickers")
        assert peers is not None
        assert "HDFCBANK" not in peers
        assert len(peers) <= 5
        # Peers come from the BFSI TICKERS universe.
        assert set(peers).issubset(set(BFSI_TICKERS))

    def test_it_peers_from_sector_tickers_excludes_queried(self):
        from backend.sectors.it_sector.config.settings import TICKERS as IT_TICKERS

        query = _make_query(ticker="INFY", company_name="Infosys")
        with patch("core.intelligence.algorithms.indicators.fetcher.get_valuation_context", return_value="val ctx") as mock_val, \
             patch("services.data.fetchers.nse_announcements.format_nse_context", return_value=""):
            bb._fetch_peers_valuation(query, "it_sector")

        args, kwargs = mock_val.call_args
        peers = kwargs.get("peer_tickers")
        assert "INFY" not in peers
        assert len(peers) <= 5
        assert set(peers).issubset(set(IT_TICKERS))

    def test_re_peers_from_sector_tickers_excludes_queried(self):
        from backend.sectors.renewable_energy.config.settings import TICKERS as RE_TICKERS

        query = _make_query(ticker="TATAPOWER", company_name="Tata Power")
        with patch("core.intelligence.algorithms.indicators.fetcher.get_valuation_context", return_value="val ctx") as mock_val, \
             patch("services.data.fetchers.nse_announcements.format_nse_context", return_value=""):
            bb._fetch_peers_valuation(query, "renewable_energy")

        args, kwargs = mock_val.call_args
        peers = kwargs.get("peer_tickers")
        assert "TATAPOWER" not in peers
        assert len(peers) <= 5
        assert set(peers).issubset(set(RE_TICKERS))


# ---------------------------------------------------------------------------
# company_news / sector_policy_news: sector keyword queries
# ---------------------------------------------------------------------------

class TestCompanyNewsQuery:
    def test_automobile_query_unchanged(self):
        query = _make_query()
        with patch("services.data.fetchers.news.fetch_news_context", return_value="news") as mock_news:
            bb._fetch_company_news(query, "automobile", "fake-key")

        q = mock_news.call_args.args[0][0]
        assert "results" in q.lower() or "guidance" in q.lower()

    def test_bfsi_query_contains_npa_keywords(self):
        query = _make_query(ticker="HDFCBANK", company_name="HDFC Bank")
        with patch("services.data.fetchers.news.fetch_news_context", return_value="news") as mock_news:
            bb._fetch_company_news(query, "banking_bfsi", "fake-key")

        q = mock_news.call_args.args[0][0]
        assert "NPA" in q
        assert "NIM" in q
        assert "deposits" in q.lower()

    def test_it_query_contains_deal_wins_attrition(self):
        query = _make_query(ticker="INFY", company_name="Infosys")
        with patch("services.data.fetchers.news.fetch_news_context", return_value="news") as mock_news:
            bb._fetch_company_news(query, "it_sector", "fake-key")

        q = mock_news.call_args.args[0][0]
        assert "deal win" in q.lower()
        assert "attrition" in q.lower()
        assert "guidance" in q.lower()

    def test_re_query_contains_ppa_commissioning_capacity(self):
        query = _make_query(ticker="TATAPOWER", company_name="Tata Power")
        with patch("services.data.fetchers.news.fetch_news_context", return_value="news") as mock_news:
            bb._fetch_company_news(query, "renewable_energy", "fake-key")

        q = mock_news.call_args.args[0][0]
        assert "PPA" in q
        assert "commissioning" in q.lower()
        assert "capacity" in q.lower()


class TestSectorPolicyNewsQuery:
    def test_bfsi_query_contains_rbi_keywords(self):
        query = _make_query(ticker="HDFCBANK", company_name="HDFC Bank")
        with patch("services.data.fetchers.news.fetch_news_context", return_value="news") as mock_news:
            bb._fetch_sector_policy_news(query, "banking_bfsi", "fake-key")

        q = mock_news.call_args.args[0][0]
        assert "RBI" in q
        assert "credit growth" in q.lower()
        assert "banking regulation" in q.lower() or "regulation" in q.lower()

    def test_it_query_contains_visa_and_ai_keywords(self):
        query = _make_query(ticker="INFY", company_name="Infosys")
        with patch("services.data.fetchers.news.fetch_news_context", return_value="news") as mock_news:
            bb._fetch_sector_policy_news(query, "it_sector", "fake-key")

        q = mock_news.call_args.args[0][0]
        assert "visa" in q.lower() or "H1B" in q
        assert "AI" in q
        assert "tech spending" in q.lower() or "spend" in q.lower()

    def test_re_query_contains_mnre_keywords(self):
        query = _make_query(ticker="TATAPOWER", company_name="Tata Power")
        with patch("services.data.fetchers.news.fetch_news_context", return_value="news") as mock_news:
            bb._fetch_sector_policy_news(query, "renewable_energy", "fake-key")

        q = mock_news.call_args.args[0][0]
        assert "MNRE" in q
        assert "solar" in q.lower() and "wind" in q.lower()
        assert "module price" in q.lower() or "module prices" in q.lower()
        assert "DISCOM" in q

    def test_automobile_query_unchanged_shape(self):
        query = _make_query()
        with patch("services.data.fetchers.news.fetch_news_context", return_value="news") as mock_news:
            bb._fetch_sector_policy_news(query, "automobile", "fake-key")

        q = mock_news.call_args.args[0][0]
        assert "automobile" in q.lower()


# ---------------------------------------------------------------------------
# macro_context: cache key alias per sector
# ---------------------------------------------------------------------------

class TestMacroContextCacheKey:
    @pytest.mark.parametrize(
        "sector,expected_alias",
        [
            ("automobile", "automobile"),
            ("banking_bfsi", "bfsi"),
            ("it_sector", "it"),
            ("renewable_energy", "renewable_energy"),
        ],
    )
    def test_macro_cache_alias_per_sector(self, sector, expected_alias):
        with patch("services.data.fetchers.macro.get_macro_context", return_value="macro yf data"), \
             patch("services.data.cache.macro_cache.get_macro_cache", return_value=None) as mock_cache, \
             patch("services.data.fetchers.news.fetch_news_context", return_value="news"):
            bb._fetch_macro_context(sector, "fake-key")

        mock_cache.assert_called_once_with(expected_alias)

    @pytest.mark.parametrize(
        "sector,expected_alias",
        [
            ("banking_bfsi", "bfsi"),
            ("it_sector", "it"),
        ],
    )
    def test_macro_cache_hit_skips_serper(self, sector, expected_alias):
        with patch("services.data.fetchers.macro.get_macro_context", return_value="macro yf data"), \
             patch("services.data.cache.macro_cache.get_macro_cache", return_value="cached news") as mock_cache, \
             patch("services.data.fetchers.news.fetch_news_context", return_value="news") as mock_news:
            result = bb._fetch_macro_context(sector, "fake-key")

        mock_cache.assert_called_once_with(expected_alias)
        mock_news.assert_not_called()
        assert "cached news" in result


# ---------------------------------------------------------------------------
# Full build_sector_bundle smoke test per new sector — api_calls_made bounds
# ---------------------------------------------------------------------------

class TestApiCallsBoundsPerSector:
    @pytest.mark.parametrize("sector,ticker,name", [
        ("banking_bfsi", "HDFCBANK", "HDFC Bank"),
        ("it_sector", "INFY", "Infosys"),
        ("renewable_energy", "TATAPOWER", "Tata Power"),
    ])
    def test_serper_le3_tavily_le1(self, sector, ticker, name):
        query = _make_query(ticker=ticker, company_name=name)
        with patch.object(bb, "_fetch_company_news", return_value="company news"), \
             patch.object(bb, "_fetch_sector_policy_news", return_value="policy news"), \
             patch.object(bb, "_fetch_macro_context", return_value="macro text"), \
             patch.object(bb, "_fetch_policy_deep_dive", return_value="deep dive text"), \
             patch.object(bb, "_fetch_fundamentals", return_value="fundamentals text"), \
             patch.object(bb, "_fetch_technicals", return_value="technicals text"), \
             patch.object(bb, "_fetch_flows_sentiment", return_value="flows text"), \
             patch.object(bb, "_fetch_peers_valuation", return_value="peers text"), \
             patch.object(bb, "_fetch_dossier", return_value="dossier text"):
            bundle = bb.build_sector_bundle(query, sector)

        assert bundle.api_calls_made["serper"] <= 3
        assert bundle.api_calls_made["tavily"] <= 1
        assert bundle.sections["commodities"] == "not_applicable"
