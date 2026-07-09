"""
Compass Phase B — quant screen signals (spec §6.1). Pure pandas, zero LLM.

Each sig_* returns a pd.Series indexed by symbol (higher = better, raw
values — screen.py converts to percentile ranks) or None when the signal is
DARK (insufficient history / feed unavailable). Dark signals are reported in
ScreenResult.dark_signals and the composite renormalizes over live ones
(spec §8 degraded mode).

v1 live signals: momentum (6m+12m vol-adjusted, NSE Momentum-50 style),
delivery_surge, volume_breakout, bulk_block, high_52wk_rs.
v1 dark signals: insider_buying, mf_holding — their data sources (NSE
insider-trading disclosures, AMC portfolio parsing) are sub-projects of
their own; config weights are reserved so they plug in without re-tuning.
"""
from __future__ import annotations

import logging

import pandas as pd

logger = logging.getLogger(__name__)

_MOMENTUM_MIN_SESSIONS = 252


def _pivot(window: pd.DataFrame, value: str) -> pd.DataFrame:
    return window.pivot_table(
        index="date", columns="symbol", values=value, aggfunc="last"
    ).sort_index()


def sig_momentum(window: pd.DataFrame) -> pd.Series | None:
    """6m+12m volatility-adjusted momentum: mean over L in (126, 252) of
    (close_t/close_{t-L} - 1) / std(daily returns over L)."""
    px = _pivot(window, "close")
    if len(px) < _MOMENTUM_MIN_SESSIONS:
        return None
    daily = px.pct_change()
    parts = []
    for lookback in (126, 252):
        ret = px.iloc[-1] / px.iloc[-lookback] - 1.0
        vol = daily.tail(lookback).std()
        parts.append(ret / vol.replace(0, pd.NA))
    out = (parts[0] + parts[1]) / 2.0
    return out.dropna()


def sig_delivery_surge(window: pd.DataFrame) -> pd.Series | None:
    """Mean delivery% of last 5 sessions vs the prior 20 sessions."""
    piv = _pivot(window, "delivery_pct")
    if len(piv) < 25:
        return None
    recent = piv.tail(5).mean()
    base = piv.iloc[-25:-5].mean()
    return (recent / base.replace(0, pd.NA)).dropna()


def sig_volume_breakout(window: pd.DataFrame) -> pd.Series | None:
    """5d/60d volume ratio, gated on proximity to the 60d high (accumulation
    signature = volume anomaly WITH the price pressing its range top;
    a volume spike far from highs scores only 30% of its ratio)."""
    vol = _pivot(window, "volume")
    px = _pivot(window, "close")
    if len(vol) < 60:
        return None
    ratio = vol.tail(5).mean() / vol.tail(60).mean().replace(0, pd.NA)
    near_high = px.iloc[-1] >= 0.97 * px.tail(60).max()
    return ratio.where(near_high, ratio * 0.3).dropna()


def sig_bulk_block(window: pd.DataFrame, bulk_cache: dict | None) -> pd.Series | None:
    """Net same-side bulk/block BUY qty over the cached ~4wk window,
    normalised by the symbol's 20d average volume. Symbols without deals = 0."""
    if bulk_cache is None:
        return None
    from services.data.fetchers.bulk_block import net_accumulation
    net = net_accumulation(bulk_cache)
    vol = _pivot(window, "volume")
    if len(vol) < 20:
        return None
    avg20 = vol.tail(20).mean()
    ser = pd.Series(net, dtype=float).reindex(avg20.index).fillna(0.0)
    return (ser / avg20.replace(0, pd.NA)).fillna(0.0)


def sig_high_52wk_rs(window: pd.DataFrame) -> pd.Series | None:
    """52-wk-high proximity + 3m relative strength vs the universe median
    (median 3m return as the market proxy — no external index fetch)."""
    px = _pivot(window, "close")
    if len(px) < _MOMENTUM_MIN_SESSIONS:
        return None
    proximity = px.iloc[-1] / px.tail(252).max()
    r3 = px.iloc[-1] / px.iloc[-63] - 1.0
    rs = r3 - r3.median()
    return (proximity + rs).dropna()


def sig_insider_buying(window: pd.DataFrame) -> pd.Series | None:
    """DARK in v1 — NSE insider-trading (corporates-pit) fetcher not built yet."""
    return None


def sig_mf_holding(window: pd.DataFrame) -> pd.Series | None:
    """DARK in v1 — AMC monthly portfolio parsing is its own sub-project."""
    return None


def compute_signals(
    window: pd.DataFrame, universe: list[str], bulk_cache: dict | None
) -> dict[str, pd.Series | None]:
    """All 7 signal slots, restricted to `universe` symbols. None = dark."""
    win = window[window["symbol"].isin(universe)]
    out: dict[str, pd.Series | None] = {
        "momentum": sig_momentum(win),
        "delivery_surge": sig_delivery_surge(win),
        "volume_breakout": sig_volume_breakout(win),
        "bulk_block": sig_bulk_block(win, bulk_cache),
        "high_52wk_rs": sig_high_52wk_rs(win),
        "insider_buying": sig_insider_buying(win),
        "mf_holding": sig_mf_holding(win),
    }
    dark = [k for k, v in out.items() if v is None]
    if dark:
        logger.info("[discovery.signals] dark signals: %s", dark)
    return out
