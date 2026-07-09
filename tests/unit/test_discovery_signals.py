"""Compass Phase B — quant screen signals (spec §6.1), pure pandas."""
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from core.discovery import signals as sig


def _make_window(specs: dict[str, dict], sessions: int = 280) -> pd.DataFrame:
    """specs: symbol -> {drift: daily pct, vol_mult, deliv_recent, deliv_base,
    vol_recent_mult}. Deterministic geometric price paths."""
    rows = []
    start = date(2026, 1, 1)
    rng = np.random.default_rng(42)
    for sym, s in specs.items():
        px = 100.0
        for i in range(sessions):
            d = start + timedelta(days=i)
            drift = s.get("drift", 0.0)
            noise = rng.normal(0, 0.005 * s.get("vol_mult", 1.0))
            prev = px
            px = px * (1 + drift + noise)
            recent = i >= sessions - 5
            vol = 10000.0 * (s.get("vol_recent_mult", 1.0) if recent else 1.0)
            deliv = s.get("deliv_recent", 40.0) if recent else s.get("deliv_base", 40.0)
            rows.append({"symbol": sym, "series": "EQ", "date": d.isoformat(),
                         "prev_close": prev, "open": prev, "high": max(prev, px),
                         "low": min(prev, px), "close": px, "volume": vol,
                         "traded_value_cr": 6.0, "delivery_qty": vol * deliv / 100,
                         "delivery_pct": deliv})
    return pd.DataFrame(rows)


@pytest.fixture(scope="module")
def window():
    return _make_window({
        "UPTREND":  {"drift": 0.002},
        "FLATCO":   {"drift": 0.0},
        "DELIVCO":  {"drift": 0.0, "deliv_base": 30.0, "deliv_recent": 70.0},
        "VOLSPIKE": {"drift": 0.001, "vol_recent_mult": 5.0},
    })


def test_momentum_ranks_uptrend_first(window):
    s = sig.sig_momentum(window)
    assert s is not None
    assert s.idxmax() == "UPTREND"
    assert s["UPTREND"] > s["FLATCO"]


def test_momentum_dark_without_history():
    short = _make_window({"AAA": {}}, sessions=100)
    assert sig.sig_momentum(short) is None


def test_delivery_surge(window):
    s = sig.sig_delivery_surge(window)
    assert s.idxmax() == "DELIVCO"


def test_volume_breakout_rewards_spike_near_high(window):
    s = sig.sig_volume_breakout(window)
    assert s["VOLSPIKE"] > s["FLATCO"]


def test_bulk_block_uses_cache(window):
    cache = {"deals": [
        {"symbol": "FLATCO", "side": "BUY", "qty": 50000.0, "kind": "bulk", "date": "2026-07-01"},
    ]}
    s = sig.sig_bulk_block(window, cache)
    assert s["FLATCO"] > 0
    assert s.get("UPTREND", 0.0) == 0.0


def test_bulk_block_dark_without_cache(window):
    assert sig.sig_bulk_block(window, None) is None


def test_high_52wk_rs(window):
    s = sig.sig_high_52wk_rs(window)
    assert s["UPTREND"] > s["FLATCO"]


def test_compute_signals_keys_and_dark(window):
    out = sig.compute_signals(window, ["UPTREND", "FLATCO", "DELIVCO", "VOLSPIKE"], None)
    assert set(out) == {"momentum", "delivery_surge", "volume_breakout",
                        "bulk_block", "high_52wk_rs", "insider_buying", "mf_holding"}
    assert out["insider_buying"] is None and out["mf_holding"] is None   # dark v1
    assert out["bulk_block"] is None                                     # no cache passed
