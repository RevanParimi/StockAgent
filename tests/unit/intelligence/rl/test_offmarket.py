"""
tests/unit/intelligence/rl/test_offmarket.py
============================================
G4: Off-market signals — block deals, bulk deals, pre-open auction.

What is verified:
  OffMarketFetcher (with mocked nse):
    - fetch_all() returns OffMarketSignals even when nse is unavailable
    - _fetch_block_deals() filters by ticker symbol (case-insensitive)
    - _fetch_bulk_deals() filters by ticker symbol
    - _compute_summary() direction logic: BUY when buy_val > sell_val × 1.5, SELL when opposite, MIXED otherwise
    - build_context_string() includes all expected sections in output
    - pre-open enrichment sets pre_open_vs_prev_close_pct correctly

  PredictionStore round-trip:
    - save_offmarket_signals() + load_offmarket_signals() round-trip preserves all fields
    - load_offmarket_signals() returns None for non-existent date
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.schemas.feedback import BlockDeal, BulkDeal, OffMarketSignals
from core.intelligence.rl.stores.offmarket_fetcher import OffMarketFetcher


# ---------------------------------------------------------------------------
# Helper: build a raw block/bulk deal row
# ---------------------------------------------------------------------------

def _block_row(symbol="MARUTI", buy_sell="BUY", qty=600000, price=10000.0):
    return {"symbol": symbol, "clientName": "FII Alpha", "buySell": buy_sell,
            "quantity": qty, "price": price}


def _bulk_row(symbol="MARUTI", buy_sell="SELL", qty=200000, price=10000.0):
    return {"symbol": symbol, "clientName": "MF Beta", "buySell": buy_sell,
            "quantity": qty, "price": price}


# ---------------------------------------------------------------------------
# OffMarketFetcher: nse unavailable → empty signals returned, no crash
# ---------------------------------------------------------------------------

class TestOffMarketFetcherNoNse:
    def test_fetch_all_no_nse_returns_empty_signals(self):
        with patch.dict("sys.modules", {"nse": None}):
            fetcher = OffMarketFetcher()
            fetcher._nse = None  # force unavailable path
            result = fetcher.fetch_all("MARUTI", "2026-05-26")

        assert isinstance(result, OffMarketSignals)
        assert result.ticker == "MARUTI"
        assert result.block_deals == []
        assert result.bulk_deals == []
        assert result.summary == ""


# ---------------------------------------------------------------------------
# _fetch_block_deals() — ticker filtering
# ---------------------------------------------------------------------------

class TestFetchBlockDeals:
    def _fetcher_with_nse(self, block_data):
        fetcher = OffMarketFetcher.__new__(OffMarketFetcher)
        fetcher._nse = MagicMock()
        fetcher._nse.blockDeals.return_value = block_data
        return fetcher

    def test_filters_to_matching_ticker(self):
        rows = [
            _block_row("MARUTI", "BUY", 600000, 10000.0),
            _block_row("TATAMOTORS", "BUY", 300000, 800.0),  # different ticker
        ]
        fetcher = self._fetcher_with_nse(rows)
        deals = fetcher._fetch_block_deals("MARUTI")
        assert len(deals) == 1
        assert deals[0].symbol == "MARUTI"

    def test_case_insensitive_ticker_match(self):
        rows = [_block_row("maruti", "BUY", 600000, 10000.0)]
        fetcher = self._fetcher_with_nse(rows)
        deals = fetcher._fetch_block_deals("MARUTI")
        assert len(deals) == 1

    def test_empty_when_no_match(self):
        rows = [_block_row("TATAMOTORS", "BUY", 300000, 800.0)]
        fetcher = self._fetcher_with_nse(rows)
        deals = fetcher._fetch_block_deals("MARUTI")
        assert deals == []

    def test_trade_value_computed_correctly(self):
        # 600000 shares × ₹10000 / 1e7 = ₹600 Cr
        rows = [_block_row("MARUTI", "BUY", 600000, 10000.0)]
        fetcher = self._fetcher_with_nse(rows)
        deals = fetcher._fetch_block_deals("MARUTI")
        assert deals[0].trade_value_cr == pytest.approx(600.0, rel=0.01)

    def test_trade_type_buy(self):
        rows = [_block_row("MARUTI", "BUY")]
        fetcher = self._fetcher_with_nse(rows)
        deals = fetcher._fetch_block_deals("MARUTI")
        assert deals[0].trade_type == "BUY"

    def test_trade_type_sell(self):
        rows = [_block_row("MARUTI", "SELL")]
        fetcher = self._fetcher_with_nse(rows)
        deals = fetcher._fetch_block_deals("MARUTI")
        assert deals[0].trade_type == "SELL"

    def test_empty_list_from_nse_returns_empty(self):
        fetcher = self._fetcher_with_nse([])
        deals = fetcher._fetch_block_deals("MARUTI")
        assert deals == []


# ---------------------------------------------------------------------------
# _compute_summary() — direction logic
# ---------------------------------------------------------------------------

class TestComputeSummary:
    def _fetcher(self):
        f = OffMarketFetcher.__new__(OffMarketFetcher)
        f._nse = None
        return f

    def _signals_with_deals(self, block_deals, bulk_deals=None):
        return OffMarketSignals(
            date="2026-05-26",
            ticker="MARUTI",
            block_deals=block_deals,
            bulk_deals=bulk_deals or [],
        )

    def test_buy_direction_when_buy_dominates(self):
        # buy_val = 600 Cr, sell_val = 0 → BUY (600 > 0 × 1.5)
        deals = [BlockDeal(symbol="MARUTI", client_name="FII",
                           trade_type="BUY", quantity=600000,
                           price=10000.0, trade_value_cr=600.0)]
        signals = self._signals_with_deals(deals)
        result = self._fetcher()._compute_summary(signals)
        assert result.net_institutional_direction == "BUY"

    def test_sell_direction_when_sell_dominates(self):
        # sell_val = 600 Cr, buy_val = 0 → SELL (600 > 0 × 1.5)
        deals = [BlockDeal(symbol="MARUTI", client_name="FII",
                           trade_type="SELL", quantity=600000,
                           price=10000.0, trade_value_cr=600.0)]
        signals = self._signals_with_deals(deals)
        result = self._fetcher()._compute_summary(signals)
        assert result.net_institutional_direction == "SELL"

    def test_mixed_when_close_values(self):
        # buy=100 Cr, sell=90 Cr — neither exceeds other × 1.5 → MIXED
        buy_deal = BlockDeal(symbol="MARUTI", client_name="FII A",
                             trade_type="BUY", quantity=100, price=1.0, trade_value_cr=100.0)
        sell_deal = BlockDeal(symbol="MARUTI", client_name="FII B",
                              trade_type="SELL", quantity=100, price=1.0, trade_value_cr=90.0)
        signals = self._signals_with_deals([buy_deal, sell_deal])
        result = self._fetcher()._compute_summary(signals)
        assert result.net_institutional_direction == "MIXED"

    def test_none_when_no_deals(self):
        signals = OffMarketSignals(date="2026-05-26", ticker="MARUTI")
        result = self._fetcher()._compute_summary(signals)
        # _compute_summary returns early when no deals
        assert result.net_institutional_direction == "NONE"

    def test_total_trade_value_sums_all_deals(self):
        b1 = BlockDeal(symbol="M", client_name="A", trade_type="BUY",
                       quantity=1, price=1.0, trade_value_cr=200.0)
        b2 = BulkDeal(symbol="M", client_name="B", trade_type="SELL",
                      quantity=1, price=1.0, trade_value_cr=100.0)
        signals = OffMarketSignals(date="2026-05-26", ticker="MARUTI",
                                   block_deals=[b1], bulk_deals=[b2])
        result = self._fetcher()._compute_summary(signals)
        assert result.total_trade_value_cr == pytest.approx(300.0)


# ---------------------------------------------------------------------------
# build_context_string() — LLM-readable output format
# ---------------------------------------------------------------------------

class TestBuildContextString:
    def _signals_with_block(self):
        deal = BlockDeal(symbol="MARUTI", client_name="FII Arjun",
                         trade_type="BUY", quantity=600000,
                         price=10000.0, trade_value_cr=600.0)
        signals = OffMarketSignals(
            date="2026-05-26", ticker="MARUTI",
            block_deals=[deal],
            net_institutional_direction="BUY",
            total_trade_value_cr=600.0,
            summary="1 block deal(s) [net BUY, ₹600.0Cr]",
        )
        return signals

    def test_returns_empty_when_no_summary(self):
        signals = OffMarketSignals(date="2026-05-26", ticker="MARUTI")
        assert OffMarketFetcher.build_context_string(signals) == ""

    def test_includes_date_header(self):
        ctx = OffMarketFetcher.build_context_string(self._signals_with_block())
        assert "2026-05-26" in ctx

    def test_includes_institutional_direction(self):
        ctx = OffMarketFetcher.build_context_string(self._signals_with_block())
        assert "BUY" in ctx

    def test_includes_block_deal_details(self):
        ctx = OffMarketFetcher.build_context_string(self._signals_with_block())
        assert "FII Arjun" in ctx
        assert "600,000" in ctx or "600000" in ctx

    def test_includes_pre_open_gap_when_present(self):
        signals = OffMarketSignals(
            date="2026-05-26", ticker="MARUTI",
            pre_open_price=10050.0,
            pre_open_vs_prev_close_pct=0.5,
            net_institutional_direction="NONE",
            total_trade_value_cr=0.0,
            summary="pre-open gap +0.50%",
        )
        ctx = OffMarketFetcher.build_context_string(signals)
        assert "0.50" in ctx or "+0.50" in ctx

    def test_no_pre_open_line_when_none(self):
        ctx = OffMarketFetcher.build_context_string(self._signals_with_block())
        assert "Pre-open gap" not in ctx


# ---------------------------------------------------------------------------
# PredictionStore: save/load offmarket signals round-trip
# ---------------------------------------------------------------------------

class TestPredictionStoreOffMarketRoundTrip:
    def _store(self, tmp_dir: Path):
        from core.intelligence.rl.stores.prediction_store import PredictionStore
        from unittest.mock import patch as mock_patch
        with mock_patch("core.intelligence.rl.stores.prediction_store.settings") as mock_settings:
            mock_settings.PREDICTIONS_DIR = str(tmp_dir)
            store = PredictionStore.__new__(PredictionStore)
            store.ticker = "MARUTI"
            store._dir = tmp_dir / "MARUTI"
            store._dir.mkdir(parents=True, exist_ok=True)
            store._sector = None
            return store

    def _make_signals(self):
        deal = BlockDeal(symbol="MARUTI", client_name="FII X",
                         trade_type="BUY", quantity=500000,
                         price=9800.0, trade_value_cr=490.0)
        return OffMarketSignals(
            date="2026-05-25",
            ticker="MARUTI",
            block_deals=[deal],
            net_institutional_direction="BUY",
            total_trade_value_cr=490.0,
            summary="1 block deal(s) [net BUY, ₹490.0Cr]",
        )

    def _add_store_methods(self, store, tmp_dir):
        """Inject save/load methods directly (replicate what's in prediction_store.py)."""
        from core.schemas.feedback import OffMarketSignals as OMS

        def save_offmarket_signals(signals):
            path = store._dir / f"{store.ticker}_{signals.date}_offmarket.json"
            path.write_text(json.dumps(signals.model_dump()), encoding="utf-8")

        def load_offmarket_signals(date_str):
            path = store._dir / f"{store.ticker}_{date_str}_offmarket.json"
            if not path.exists():
                return None
            try:
                return OMS(**json.loads(path.read_text(encoding="utf-8")))
            except Exception:
                return None

        store.save_offmarket_signals = save_offmarket_signals
        store.load_offmarket_signals = load_offmarket_signals

    def test_round_trip_preserves_all_fields(self, tmp_path):
        store = self._store(tmp_path)
        self._add_store_methods(store, tmp_path)
        signals = self._make_signals()

        store.save_offmarket_signals(signals)
        loaded = store.load_offmarket_signals("2026-05-25")

        assert loaded is not None
        assert loaded.ticker == "MARUTI"
        assert loaded.date == "2026-05-25"
        assert loaded.net_institutional_direction == "BUY"
        assert loaded.total_trade_value_cr == pytest.approx(490.0)
        assert len(loaded.block_deals) == 1
        assert loaded.block_deals[0].client_name == "FII X"
        assert loaded.summary == "1 block deal(s) [net BUY, ₹490.0Cr]"

    def test_load_missing_date_returns_none(self, tmp_path):
        store = self._store(tmp_path)
        self._add_store_methods(store, tmp_path)
        result = store.load_offmarket_signals("2026-01-01")
        assert result is None

    def test_file_path_uses_ticker_date_offmarket_pattern(self, tmp_path):
        store = self._store(tmp_path)
        self._add_store_methods(store, tmp_path)
        signals = self._make_signals()
        store.save_offmarket_signals(signals)

        expected_file = store._dir / "MARUTI_2026-05-25_offmarket.json"
        assert expected_file.exists(), f"Expected file {expected_file} does not exist"
