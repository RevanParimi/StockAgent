"""SA-044 regression: the 2026-09-26 reproduction, SUNPHARMA valued against
car makers.

Before SA-044 the generic graph's bundle passed MARUTI, TATAMOTORS, M&M,
HEROMOTOCO and BAJAJ-AUTO as SUNPHARMA's peers. This file imports nothing
SA-044 added at module level and stubs only yfinance, so it runs unchanged
on the code before the fix, where it fails, and on the code after it.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from core.schemas.pipeline import StockQuery
from services.data.context import bundle_builder as bb
from services.data.context import fetch_result as fr

PHARMA = "Drug Manufacturers - Specialty & Generic"
AUTO = "Auto Manufacturers"
YAHOO = {
    "SUNPHARMA": (PHARMA, 4.0e12), "CIPLA": (PHARMA, 1.2e12), "DRREDDY": (PHARMA, 1.05e12),
    "LUPIN": (PHARMA, 0.95e12), "ZYDUSLIFE": (PHARMA, 1.0e12),
    "MARUTI": (AUTO, 4.0e12), "TATAMOTORS": (AUTO, 1.5e12), "M&M": (AUTO, 3.8e12),
    "HEROMOTOCO": (AUTO, 0.9e12), "BAJAJ-AUTO": (AUTO, 2.5e12),
}


def _ticker(symbol):
    industry, cap = YAHOO.get(symbol.removesuffix(".NS"), ("", None))
    t = MagicMock()
    t.info = {"industry": industry, "marketCap": cap, "trailingPE": 25.0}
    return t


def test_sunpharma_is_not_valued_against_car_makers(monkeypatch):
    monkeypatch.setattr("yfinance.Ticker", _ticker)
    try:
        from services.data.context import peers as chooser       # SA-044 and later
    except ImportError:                                            # before SA-044
        chooser = None
    if chooser is not None:
        monkeypatch.setattr(chooser, "known_symbols", lambda: sorted(YAHOO))
    seen = {}

    def valuation(ticker, peer_tickers=None, **kw):
        seen["peers"] = list(peer_tickers or [])
        return fr.FetchResult("v", fr.STATUS_OK, "fixture")
    monkeypatch.setattr("core.intelligence.algorithms.indicators.fetcher.get_valuation_result",
                        valuation)
    monkeypatch.setattr("services.data.fetchers.nse_announcements.format_nse_context",
                        lambda *a, **k: "")

    bb._fetch_peers_valuation(StockQuery(ticker="SUNPHARMA", company_name="Sun Pharma",
                                         nse_data={}), "generic")

    assert seen["peers"], "SUNPHARMA has four pharma peers here"
    wrong = [p for p in seen["peers"] if YAHOO.get(p, ("",))[0] != PHARMA]
    assert not wrong, f"valued against another industry: {wrong}"
