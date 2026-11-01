"""Compass Phase B — Stage-3 deep dive: sector inference + one-call conviction."""
from datetime import date

import pandas as pd
import pytest

import core.discovery.deep_dive as dd
from backend.shared.schemas.discovery import DiscoveryCandidate


def test_infer_sector_exact_registry_hit():
    assert dd.infer_sector("SUNPHARMA") == "pharma"       # TICKER_SECTOR map
    assert dd.infer_sector("MARUTI") == "automobile"


def test_infer_sector_industry_keyword(monkeypatch):
    monkeypatch.setattr(dd, "market_classification",
                        lambda s: {"sector": "Healthcare",
                                   "industry": "Drug Manufacturers - Specialty & Generic"})
    assert dd.infer_sector("NEWPHARMACO") == "pharma"


def test_infer_sector_falls_back_generic(monkeypatch):
    monkeypatch.setattr(dd, "market_classification",
                        lambda s: {"sector": "", "industry": ""})     # Yahoo has nothing
    assert dd.infer_sector("MYSTERYCO") == "generic"


def _companies(*symbols):
    """A listing in which every symbol is a company's shares (ISIN INE...)."""
    return {s: {"series": "EQ", "isin": "INE000000000"} for s in symbols}


class _FakeReport:
    final_score = 0.72
    verdict = "BUY"
    investment_thesis = "Strong momentum with improving delivery."


def _window(symbol="NEWCO", n=30):
    rows = []
    for i in range(n):
        rows.append({"symbol": symbol, "series": "EQ", "date": f"2026-06-{i+1:02d}",
                     "prev_close": 100.0, "open": 100.0, "high": 104.0, "low": 98.0,
                     "close": 100.0, "volume": 1.0, "traded_value_cr": 6.0,
                     "delivery_qty": 1.0, "delivery_pct": 40.0})
    return pd.DataFrame(rows)


def test_run_deep_dives_skips_managed_and_builds_result(monkeypatch):
    monkeypatch.setattr(dd, "load_managed_tickers",
                        lambda: [{"sym": "MANAGED", "enabled": True}])

    class _FakeShelfStore:
        def load(self):
            from backend.shared.schemas.discovery import Shelf, ShelfIdea
            return Shelf(ideas=[ShelfIdea(symbol="SHELVED", sector="generic",
                                          added="2026-07-01", conviction=0.6)])
    monkeypatch.setattr(dd, "ShelfStore", _FakeShelfStore)

    class _FakeStore:
        def load_window(self, end, sessions):
            return _window()
    monkeypatch.setattr(dd, "EodStore", lambda: _FakeStore())

    monkeypatch.setattr(dd, "infer_sector", lambda s, c=None: "pharma")
    monkeypatch.setattr(dd, "load_listing",
                        lambda: _companies("MANAGED", "SHELVED", "NEWCO", "EXTRA"))
    monkeypatch.setattr(dd, "market_classification",
                        lambda s: {"sector": "Healthcare", "industry": "Drug Manufacturers"})
    monkeypatch.setattr(dd, "get_orchestrator",
                        lambda sector: type("O", (), {"analyse": lambda self, t: _FakeReport()})())

    cands = [DiscoveryCandidate(symbol=s, close=100.0, composite=0.9 - i * 0.1)
             for i, s in enumerate(["MANAGED", "SHELVED", "NEWCO", "EXTRA"])]
    results = dd.run_deep_dives(cands, on=date(2026, 7, 4), max_n=1)

    assert len(results) == 1
    r = results[0]
    assert r.symbol == "NEWCO"                    # managed + shelved skipped
    assert r.sector == "pharma" and r.graph == "generic"
    assert r.conviction == 0.72 and r.verdict == "BUY"
    assert r.entry_low == pytest.approx(97.0) and r.entry_high == pytest.approx(102.0)
    assert r.invalidation_level < r.close         # ATR-scaled stop below close
    assert r.dive_date == "2026-07-04"
    assert r.market_sector == "Healthcare" and r.industry == "Drug Manufacturers"


def test_run_deep_dives_orchestrator_failure_is_nonfatal(monkeypatch):
    monkeypatch.setattr(dd, "load_managed_tickers", lambda: [])

    class _EmptyShelf:
        def load(self):
            from backend.shared.schemas.discovery import Shelf
            return Shelf()
    monkeypatch.setattr(dd, "ShelfStore", _EmptyShelf)

    class _FakeStore:
        def load_window(self, end, sessions):
            return _window()
    monkeypatch.setattr(dd, "EodStore", lambda: _FakeStore())
    monkeypatch.setattr(dd, "infer_sector", lambda s, c=None: "generic")
    monkeypatch.setattr(dd, "market_classification", lambda s: {"sector": "", "industry": ""})
    monkeypatch.setattr(dd, "load_listing", lambda: _companies("NEWCO"))

    class _Boom:
        def analyse(self, t):
            raise RuntimeError("LLM down")
    monkeypatch.setattr(dd, "get_orchestrator", lambda sector: _Boom())

    cands = [DiscoveryCandidate(symbol="NEWCO", close=100.0, composite=0.9)]
    calls = []
    monkeypatch.setattr(dd, "get_orchestrator",
                        lambda sector: calls.append(sector) or _Boom())
    assert dd.run_deep_dives(cands, on=date(2026, 7, 4)) == []
    assert calls == ["generic"]                   # the analyst was reached, then failed
