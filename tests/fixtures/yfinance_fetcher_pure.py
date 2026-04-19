"""
tools/yfinance_fetcher_pure.py
==============================
Frozen pure-Python copy of the technical indicator functions from
yfinance_fetcher.py.  Used by Phase 1 parity tests to provide a
reference implementation when the C++ extension is compiled.

Do NOT import yfinance or any network-dependent code here.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from config import settings


def compute_rsi(close: pd.Series, period: int = settings.RSI_PERIOD) -> float:
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return float(rsi.iloc[-1]) if not rsi.empty else 50.0


def compute_macd(close: pd.Series) -> dict[str, float]:
    ema_fast = close.ewm(span=settings.MACD_FAST, adjust=False).mean()
    ema_slow = close.ewm(span=settings.MACD_SLOW, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=settings.MACD_SIGNAL, adjust=False).mean()
    histogram = macd_line - signal_line
    return {
        "macd": round(float(macd_line.iloc[-1]), 4),
        "signal": round(float(signal_line.iloc[-1]), 4),
        "histogram": round(float(histogram.iloc[-1]), 4),
        "bullish_crossover": bool(
            macd_line.iloc[-1] > signal_line.iloc[-1]
            and macd_line.iloc[-2] <= signal_line.iloc[-2]
        ),
    }


def compute_bollinger_bands(
    close: pd.Series,
    period: int = settings.BB_PERIOD,
    std_dev: float = settings.BB_STD,
) -> dict[str, float]:
    ma = close.rolling(period).mean()
    std = close.rolling(period).std()
    upper = ma + std_dev * std
    lower = ma - std_dev * std
    current = float(close.iloc[-1])
    upper_val = float(upper.iloc[-1])
    lower_val = float(lower.iloc[-1])
    band_width = upper_val - lower_val
    pct_b = (current - lower_val) / band_width if band_width != 0 else 0.5
    return {
        "upper": round(upper_val, 2),
        "middle": round(float(ma.iloc[-1]), 2),
        "lower": round(lower_val, 2),
        "current": round(current, 2),
        "pct_b": round(pct_b, 4),
    }
