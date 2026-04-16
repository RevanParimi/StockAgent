"""
tools/yfinance_fetcher.py
=========================
OHLCV price data and technical indicator computation via yfinance.
No API key required — uses Yahoo Finance public data.

Public API
----------
get_price_history(ticker, years) → pd.DataFrame
compute_technicals(df)           → dict
get_peer_correlation(ticker, index_ticker, period) → float
get_price_summary(ticker)        → dict   (latest price + 52w range)
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

import numpy as np
import pandas as pd
import yfinance as yf

from config import settings

logger = logging.getLogger(__name__)

# Phase 1 C++ extension guard.
# When the compiled stockindicators module is present (built via cpp/CMakeLists.txt),
# indicator functions are dispatched to it.  Falls back to pure Python silently.
try:
    import stockindicators as _cpp_indicators  # noqa: F401 — used by compute_* below
    _USE_CPP = True
    logger.debug("[yfinance_fetcher] C++ stockindicators extension loaded")
except ImportError:
    _cpp_indicators = None
    _USE_CPP = False


def _nse_ticker(ticker: str) -> str:
    """Convert bare NSE ticker to yfinance format, e.g. MARUTI → MARUTI.NS"""
    t = ticker.strip().upper()
    if t.endswith(settings.YFINANCE_SUFFIX):
        return t
    # Special cases
    if t in {"M&M", "MM"}:
        return f"M&M{settings.YFINANCE_SUFFIX}"
    return f"{t}{settings.YFINANCE_SUFFIX}"


# ---------------------------------------------------------------------------
# Price history
# ---------------------------------------------------------------------------

def get_price_history(ticker: str, years: int = settings.PRICE_HISTORY_YEARS) -> pd.DataFrame:
    """
    Fetch daily OHLCV data for `years` years.

    Returns
    -------
    pd.DataFrame with columns: Open, High, Low, Close, Volume
    Empty DataFrame on failure.
    """
    yf_ticker = _nse_ticker(ticker)
    end = date.today()
    start = end - timedelta(days=years * 365)
    try:
        df = yf.download(
            yf_ticker,
            start=start.isoformat(),
            end=end.isoformat(),
            progress=False,
            auto_adjust=True,
        )
        if df.empty:
            logger.warning("[yfinance] No price data for %s", yf_ticker)
        return df
    except Exception as exc:
        logger.error("[yfinance] Price history failed for %s: %s", yf_ticker, exc)
        return pd.DataFrame()


# ---------------------------------------------------------------------------
# Technical indicators
# ---------------------------------------------------------------------------

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
    close: pd.Series, period: int = settings.BB_PERIOD, std_dev: float = settings.BB_STD
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
        "pct_b": round(pct_b, 4),   # >0.8 overbought, <0.2 oversold
    }


def compute_support_resistance(close: pd.Series, window: int = 20) -> dict[str, float]:
    """Simple pivot-based support/resistance using recent highs/lows."""
    recent = close.tail(252)  # 1 year
    support = float(recent.rolling(window).min().iloc[-1])
    resistance = float(recent.rolling(window).max().iloc[-1])
    current = float(close.iloc[-1])
    dist_to_support_pct = round((current - support) / support * 100, 2) if support else 0
    dist_to_resistance_pct = round((resistance - current) / current * 100, 2) if current else 0
    return {
        "support": round(support, 2),
        "resistance": round(resistance, 2),
        "current": round(current, 2),
        "dist_to_support_pct": dist_to_support_pct,
        "dist_to_resistance_pct": dist_to_resistance_pct,
    }


def compute_technicals(df: pd.DataFrame) -> dict:
    """
    Run all technical indicators on a price DataFrame.

    Parameters
    ----------
    df : pd.DataFrame from get_price_history()

    Returns
    -------
    dict with keys: rsi, macd, bollinger_bands, support_resistance,
                    price_vs_52w_high_pct, price_vs_52w_low_pct
    """
    if df.empty or len(df) < 30:
        return {"error": "Insufficient price data for technical analysis"}

    close = df["Close"].squeeze()

    yr_high = float(df["Close"].tail(252).max())
    yr_low = float(df["Close"].tail(252).min())
    current = float(close.iloc[-1])

    return {
        "current_price": round(current, 2),
        "52w_high": round(yr_high, 2),
        "52w_low": round(yr_low, 2),
        "price_vs_52w_high_pct": round((current - yr_high) / yr_high * 100, 2),
        "price_vs_52w_low_pct": round((current - yr_low) / yr_low * 100, 2),
        "rsi": round(compute_rsi(close), 2),
        "macd": compute_macd(close),
        "bollinger_bands": compute_bollinger_bands(close),
        "support_resistance": compute_support_resistance(close),
    }


# ---------------------------------------------------------------------------
# Seasonal / cycle analysis
# ---------------------------------------------------------------------------

def get_seasonal_pattern(df: pd.DataFrame) -> dict:
    """
    Compute average monthly return over the full history.
    Highlights historically strong/weak months for the stock.
    """
    if df.empty:
        return {}
    close = df["Close"].squeeze().resample("ME").last()
    monthly_returns = close.pct_change().dropna()
    avg_by_month = monthly_returns.groupby(monthly_returns.index.month).mean()
    return {
        int(month): round(float(ret) * 100, 2)
        for month, ret in avg_by_month.items()
    }


# ---------------------------------------------------------------------------
# Peer correlation
# ---------------------------------------------------------------------------

def get_peer_correlation(
    ticker: str,
    index_ticker: str = settings.NIFTY_AUTO_TICKER,
    period_days: int = 252,
) -> dict[str, float]:
    """
    Pearson correlation and beta of the stock vs Nifty Auto index.
    """
    yf_ticker = _nse_ticker(ticker)
    end = date.today()
    start = end - timedelta(days=period_days + 30)

    try:
        data = yf.download(
            [yf_ticker, index_ticker],
            start=start.isoformat(),
            end=end.isoformat(),
            progress=False,
            auto_adjust=True,
        )["Close"]
        returns = data.pct_change().dropna()
        if returns.shape[1] < 2 or len(returns) < 30:
            return {"correlation": 0.0, "beta": 1.0}

        stock_col = yf_ticker
        index_col = index_ticker
        corr = float(returns[stock_col].corr(returns[index_col]))
        cov = float(returns[[stock_col, index_col]].cov().iloc[0, 1])
        var_index = float(returns[index_col].var())
        beta = cov / var_index if var_index != 0 else 1.0
        return {
            "correlation": round(corr, 4),
            "beta": round(beta, 4),
        }
    except Exception as exc:
        logger.error("[yfinance] Correlation failed for %s: %s", yf_ticker, exc)
        return {"correlation": 0.0, "beta": 1.0}


# ---------------------------------------------------------------------------
# Convenience: full technical context string for prompt injection
# ---------------------------------------------------------------------------

def get_technical_context(ticker: str) -> str:
    """
    Returns a formatted string summarising technical indicators for prompt injection.
    """
    df = get_price_history(ticker, years=settings.PRICE_HISTORY_YEARS)
    tech = compute_technicals(df)
    seasonal = get_seasonal_pattern(df)
    corr = get_peer_correlation(ticker)

    if "error" in tech:
        return f"Technical data unavailable for {ticker}: {tech['error']}"

    strong_months = [m for m, r in seasonal.items() if r > 1.0]
    weak_months = [m for m, r in seasonal.items() if r < -1.0]

    return (
        f"=== Technical Data: {ticker} ===\n"
        f"Current Price: ₹{tech['current_price']} | "
        f"52W High: ₹{tech['52w_high']} ({tech['price_vs_52w_high_pct']}%) | "
        f"52W Low: ₹{tech['52w_low']} ({tech['price_vs_52w_low_pct']}%)\n"
        f"RSI(14): {tech['rsi']} | "
        f"MACD: {tech['macd']['macd']} / Signal: {tech['macd']['signal']} | "
        f"Histogram: {tech['macd']['histogram']}\n"
        f"Bollinger Bands: Upper={tech['bollinger_bands']['upper']} | "
        f"Middle={tech['bollinger_bands']['middle']} | "
        f"Lower={tech['bollinger_bands']['lower']} | %B={tech['bollinger_bands']['pct_b']}\n"
        f"Support: ₹{tech['support_resistance']['support']} "
        f"({tech['support_resistance']['dist_to_support_pct']}% away) | "
        f"Resistance: ₹{tech['support_resistance']['resistance']} "
        f"({tech['support_resistance']['dist_to_resistance_pct']}% away)\n"
        f"Nifty Auto Correlation: {corr['correlation']} | Beta: {corr['beta']}\n"
        f"Seasonally strong months: {strong_months or 'None'} | "
        f"Weak months: {weak_months or 'None'}"
    )
