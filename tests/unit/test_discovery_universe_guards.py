"""Compass Phase B — universe construction + threshold gates (spec §6.1/§9)."""
from datetime import date, timedelta

import pandas as pd
import pytest

from core.discovery.guards import apply_guards
from core.discovery.universe import build_universe


def _window(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _sessions(symbol, n, *, close=100.0, series="EQ", tv=6.0, uc_tail=0,
              start=date(2026, 4, 1)):
    """n sessions; the last uc_tail sessions are upper-circuit days
    (close == high, +10% daily)."""
    rows, px, d = [], close, start
    for i in range(n):
        is_uc = i >= n - uc_tail
        prev = px
        px = px * 1.10 if is_uc else px
        rows.append({"symbol": symbol, "series": series, "date": d.isoformat(),
                     "prev_close": prev, "open": prev, "high": px if is_uc else px * 1.01,
                     "low": prev * 0.99, "close": px, "volume": 10000.0,
                     "traded_value_cr": tv, "delivery_qty": 4000.0,
                     "delivery_pct": 40.0})
        d += timedelta(days=1)
    return rows


def test_build_universe_filters_series_and_price():
    win = _window(
        _sessions("GOODCO", 3)
        + _sessions("T2TCO", 3, series="BE")
        + _sessions("PENNY", 3, close=8.0)
    )
    assert build_universe(win) == ["GOODCO"]


def test_guards_liquidity_and_circuit(monkeypatch):
    import core.discovery.guards as g
    monkeypatch.setattr(g, "get_symbol_meta",
                        lambda s: {"surveillance": None, "suspended": False,
                                   "industry": "X", "degraded": False})
    monkeypatch.setattr(g, "float_mcap_cr", lambda s: 2000.0)

    win = _window(
        _sessions("LIQCO", 70)
        + _sessions("THINCO", 70, tv=0.5)          # ₹0.5 cr median < ₹5 cr floor
        + _sessions("PUMPCO", 70, uc_tail=5)       # 5 straight UC days > max 3
    )
    passed, rejected, degraded = apply_guards(["LIQCO", "THINCO", "PUMPCO"], win)
    assert passed == ["LIQCO"]
    assert "low_liquidity" in rejected["THINCO"]
    assert "upper_circuit_streak" in rejected["PUMPCO"]
    assert "promoter_pledge" in degraded            # dark guard always reported


def test_guards_surveillance_and_float(monkeypatch):
    import core.discovery.guards as g
    metas = {
        "ASMCO":  {"surveillance": "ASM ST1", "suspended": False, "industry": None, "degraded": False},
        "SUSPCO": {"surveillance": None, "suspended": True, "industry": None, "degraded": False},
        "TINYCO": {"surveillance": None, "suspended": False, "industry": None, "degraded": False},
        "DARKCO": {"surveillance": None, "suspended": False, "industry": None, "degraded": True},
    }
    monkeypatch.setattr(g, "get_symbol_meta", lambda s: metas[s])
    monkeypatch.setattr(g, "float_mcap_cr",
                        lambda s: {"ASMCO": 900.0, "SUSPCO": 900.0,
                                   "TINYCO": 100.0, "DARKCO": None}[s])

    win = _window(sum((_sessions(s, 70) for s in metas), []))
    passed, rejected, degraded = apply_guards(list(metas), win)
    assert "surveillance_asm_gsm" in rejected["ASMCO"]
    assert "suspended" in rejected["SUSPCO"]
    assert "low_float_mcap" in rejected["TINYCO"]
    assert "DARKCO" in passed                       # unverifiable float -> keep, degrade
    assert "float_mcap:DARKCO" in degraded
    assert "surveillance:DARKCO" in degraded
