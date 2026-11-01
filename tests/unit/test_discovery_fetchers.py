"""Compass Phase B — bulk/block + surveillance guard-data fetchers."""
from datetime import date

import pytest

import services.data.fetchers.bulk_block as bb
import services.data.fetchers.surveillance as surv


class _FakeNSE:
    def __init__(self, bulk=None, block=None, boom=False):
        self._bulk, self._block = bulk or [], block or []
        self._boom = boom
    def bulkdeals(self, option_type, fromdate, todate):
        if self._boom:
            raise RuntimeError("403")
        return self._bulk if option_type == "bulk_deals" else self._block
    def exit(self):
        pass


def test_refresh_and_net_accumulation(tmp_path, monkeypatch):
    deals = [
        {"BD_SYMBOL": "AAA", "BD_BUY_SELL": "BUY",  "BD_QTY_TRD": "10000",
         "BD_DT_DATE": "01-Jul-2026"},
        {"BD_SYMBOL": "AAA", "BD_BUY_SELL": "SELL", "BD_QTY_TRD": "2000",
         "BD_DT_DATE": "02-Jul-2026"},
        {"BD_SYMBOL": "BBB", "BD_BUY_SELL": "SELL", "BD_QTY_TRD": "5000",
         "BD_DT_DATE": "02-Jul-2026"},
    ]
    monkeypatch.setattr(bb, "_make_nse_client", lambda: _FakeNSE(bulk=deals))
    cache = bb.refresh_bulk_block(weeks=4, cache_path=str(tmp_path / "bb.json"))
    assert cache["degraded"] is False
    assert len(cache["deals"]) == 3

    net = bb.net_accumulation(cache)
    assert net["AAA"] == 8000.0
    assert net["BBB"] == 0.0            # net seller floored at 0


def test_refresh_degrades_and_keeps_stale(tmp_path, monkeypatch):
    path = str(tmp_path / "bb.json")
    monkeypatch.setattr(bb, "_make_nse_client", lambda: _FakeNSE(
        bulk=[{"BD_SYMBOL": "AAA", "BD_BUY_SELL": "BUY", "BD_QTY_TRD": "100",
               "BD_DT_DATE": "01-Jul-2026"}]))
    bb.refresh_bulk_block(weeks=4, cache_path=path)

    monkeypatch.setattr(bb, "_make_nse_client", lambda: _FakeNSE(boom=True))
    cache = bb.refresh_bulk_block(weeks=4, cache_path=path)
    assert cache["degraded"] is True
    assert len(cache["deals"]) == 1     # stale deals kept


def test_float_mcap_cr(monkeypatch):
    monkeypatch.setattr(surv, "_yf_info",
                        lambda t: {"floatShares": 100_000_000, "currentPrice": 250.0})
    assert surv.float_mcap_cr("AAA") == pytest.approx(2500.0)
    monkeypatch.setattr(surv, "_yf_info", lambda t: {})
    assert surv.float_mcap_cr("AAA") is None
