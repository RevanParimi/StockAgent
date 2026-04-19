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
    if _USE_CPP:
        return _cpp_indicators.compute_rsi(close.tolist(), period)
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return float(rsi.iloc[-1]) if not rsi.empty else 50.0


def compute_macd(close: pd.Series) -> dict[str, float]:
    if _USE_CPP:
        return _cpp_indicators.compute_macd(
            close.tolist(), settings.MACD_FAST, settings.MACD_SLOW, settings.MACD_SIGNAL
        )
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
    if _USE_CPP:
        return _cpp_indicators.compute_bollinger_bands(close.tolist(), period, std_dev)
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

    yr_high = float(close.tail(252).max())
    yr_low = float(close.tail(252).min())
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
# Valuation context — deep pattern data, no analyst opinion
# ---------------------------------------------------------------------------

def get_valuation_context(ticker: str, peer_tickers: list[str] | None = None) -> str:
    """
    Build a rich pattern + valuation context for the valuation_catalyst agent.

    Priority: yfinance (structured, free) → Serper (text snippets, API call) for each
    section that yfinance fails to provide.  No analyst opinions — Serper is used only
    to recover raw price/ratio facts when yfinance returns nothing.

    Returns a formatted string for prompt injection.
    """
    import yfinance as yf
    from datetime import date as _date

    today = _date.today()
    yf_ticker = _nse_ticker(ticker)

    # --- 2-year price history for trend analysis ---
    df = get_price_history(ticker, years=2)
    lines: list[str] = [f"=== Self-Derived Valuation Data: {ticker} ==="]
    price_history_available = not df.empty and len(df) >= 30

    if not price_history_available:
        lines.append("[yfinance] Price history unavailable — falling back to Serper for price data.")
        try:
            from services.data.fetchers.news import fetch_news_context
            fallback = fetch_news_context([
                f"{ticker} NSE current stock price 52 week high low {today.year}",
                f"{ticker} share price trend momentum {today.strftime('%B')} {today.year}",
                f"{ticker} NSE stock performance chart support resistance {today.year}",
            ], max_queries=3)
            lines.append(f"[Serper fallback — price/technical]\n{fallback}")
        except Exception as exc:
            lines.append(f"Serper price fallback also failed: {exc}")
    else:
        close = df["Close"].squeeze()
        volume = df["Volume"].squeeze() if "Volume" in df.columns else None

        current = float(close.iloc[-1])
        ath_2yr = float(close.max())
        atl_2yr = float(close.min())

        # Multi-timeframe price anchors
        p1m  = float(close.iloc[-21])  if len(close) >= 21  else current
        p3m  = float(close.iloc[-63])  if len(close) >= 63  else current
        p6m  = float(close.iloc[-126]) if len(close) >= 126 else current
        p1y  = float(close.iloc[-252]) if len(close) >= 252 else current

        lines.append(
            f"Current: {current:.2f} | 1M ago: {p1m:.2f} ({(current/p1m-1)*100:+.1f}%) | "
            f"3M ago: {p3m:.2f} ({(current/p3m-1)*100:+.1f}%) | "
            f"6M ago: {p6m:.2f} ({(current/p6m-1)*100:+.1f}%) | "
            f"1Y ago: {p1y:.2f} ({(current/p1y-1)*100:+.1f}%)"
        )
        lines.append(
            f"2Y High: {ath_2yr:.2f} ({(current/ath_2yr-1)*100:+.1f}% from ATH) | "
            f"2Y Low: {atl_2yr:.2f} ({(current/atl_2yr-1)*100:+.1f}% from ATL)"
        )

        # Moving averages and their slopes
        ma20  = float(close.rolling(20).mean().iloc[-1])
        ma50  = float(close.rolling(50).mean().iloc[-1])
        ma200 = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else None

        # Slope: % change in MA over last 20 bars — direction of trend
        ma50_20d_ago  = float(close.rolling(50).mean().iloc[-21]) if len(close) >= 70  else ma50
        ma200_20d_ago = float(close.rolling(200).mean().iloc[-21]) if len(close) >= 220 else (ma200 or ma50)

        ma50_slope  = (ma50  - ma50_20d_ago)  / ma50_20d_ago  * 100
        ma200_slope = ((ma200 or ma50) - ma200_20d_ago) / ma200_20d_ago * 100 if ma200 else 0.0

        ma200_str = f"{ma200:.2f} (slope {ma200_slope:+.2f}%/20d)" if ma200 else "N/A (<200 bars)"
        lines.append(
            f"MA20: {ma20:.2f} | MA50: {ma50:.2f} (slope {ma50_slope:+.2f}%/20d) | "
            f"MA200: {ma200_str}"
        )
        lines.append(
            f"Price vs MA20: {(current/ma20-1)*100:+.1f}% | "
            f"Price vs MA50: {(current/ma50-1)*100:+.1f}% | "
            + (f"Price vs MA200: {(current/(ma200)-1)*100:+.1f}%" if ma200 else "Price vs MA200: N/A")
        )

        # Golden/death cross
        if ma200:
            cross = "GOLDEN (MA50>MA200, bullish)" if ma50 > ma200 else "DEATH (MA50<MA200, bearish)"
            lines.append(f"MA Cross: {cross}")

        # RSI, MACD, BB
        rsi = round(compute_rsi(close), 2)
        macd = compute_macd(close)
        bb = compute_bollinger_bands(close)
        sr = compute_support_resistance(close)

        lines.append(
            f"RSI(14): {rsi} {'(oversold<30)' if rsi < 30 else '(overbought>70)' if rsi > 70 else '(neutral)'} | "
            f"MACD: {macd['macd']:.3f} / Signal: {macd['signal']:.3f} | "
            f"Histogram: {macd['histogram']:.3f} {'(bullish cross)' if macd['bullish_crossover'] else ''}"
        )
        lines.append(
            f"Bollinger: Upper={bb['upper']:.2f} Mid={bb['middle']:.2f} Lower={bb['lower']:.2f} "
            f"| %B={bb['pct_b']:.3f} {'(near upper band)' if bb['pct_b'] > 0.8 else '(near lower band)' if bb['pct_b'] < 0.2 else ''}"
        )
        lines.append(
            f"Support: {sr['support']:.2f} ({sr['dist_to_support_pct']:+.1f}%) | "
            f"Resistance: {sr['resistance']:.2f} ({sr['dist_to_resistance_pct']:+.1f}%)"
        )

        # Volume trend: 20-day avg vs 90-day avg
        if volume is not None and len(volume) >= 90:
            vol_20d = float(volume.tail(20).mean())
            vol_90d = float(volume.tail(90).mean())
            vol_trend = (vol_20d / vol_90d - 1) * 100
            lines.append(
                f"Volume trend: 20d avg {vol_20d:,.0f} vs 90d avg {vol_90d:,.0f} "
                f"({vol_trend:+.1f}%) {'(rising volume = confirmation)' if vol_trend > 10 else ''}"
            )

        # Trend channel estimate: linear regression on 6-month close
        try:
            y = close.tail(126).values.astype(float)
            x = np.arange(len(y))
            slope, intercept = np.polyfit(x, y, 1)
            channel_proj_1q = intercept + slope * (len(y) + 63)   # ~1 quarter forward
            channel_proj_2q = intercept + slope * (len(y) + 126)
            lines.append(
                f"6M Linear trend slope: {slope:+.3f}/day | "
                f"Channel projection: 1Q={channel_proj_1q:.2f}  2Q={channel_proj_2q:.2f}"
            )
        except Exception:
            pass

    # --- Fundamental valuation ratios (yfinance .info) ---
    lines.append("")
    lines.append("=== Fundamental Ratios ===")
    fundamentals_available = False
    eps_ttm_val: float | None = None
    try:
        info = yf.Ticker(yf_ticker).info or {}
        trailing_pe  = info.get("trailingPE")
        forward_pe   = info.get("forwardPE")
        pb           = info.get("priceToBook")
        eps_ttm      = info.get("trailingEps")
        eps_fwd      = info.get("forwardEps")
        mktcap       = info.get("marketCap", 0)
        ev_ebitda    = info.get("enterpriseToEbitda")
        price_sales  = info.get("priceToSalesTrailingTwelveMonths")

        fundamentals_available = any(v is not None for v in [trailing_pe, eps_ttm, pb, price_sales])
        if fundamentals_available:
            lines.append(
                f"Trailing P/E: {round(trailing_pe,2) if trailing_pe else 'N/A'} | "
                f"Forward P/E: {round(forward_pe,2) if forward_pe else 'N/A'} | "
                f"P/B: {round(pb,2) if pb else 'N/A'} | "
                f"EV/EBITDA: {round(ev_ebitda,2) if ev_ebitda else 'N/A'} | "
                f"P/S: {round(price_sales,2) if price_sales else 'N/A'}"
            )
            if eps_ttm:
                eps_ttm_val = eps_ttm
                lines.append(f"EPS (TTM): {eps_ttm:.2f} | EPS (Fwd): {eps_fwd or 'N/A'}")
                if trailing_pe:
                    lines.append(
                        f"EPS-implied price at P/E 20: {eps_ttm*20:.2f} | "
                        f"P/E 25: {eps_ttm*25:.2f} | P/E 30: {eps_ttm*30:.2f}"
                    )
            if mktcap:
                lines.append(f"Market Cap: {mktcap/1e7:.0f} Cr")
    except Exception as exc:
        logger.warning("[valuation_context] yfinance fundamentals failed for %s: %s", ticker, exc)

    if not fundamentals_available:
        lines.append("[yfinance] Fundamentals unavailable — falling back to Serper for ratio data.")
        try:
            from services.data.fetchers.news import fetch_news_context
            fallback = fetch_news_context([
                f"{ticker} NSE PE ratio EPS earnings revenue {today.year}",
                f"{ticker} P/E price to earnings market cap valuation {today.year}",
            ], max_queries=2)
            lines.append(f"[Serper fallback — fundamentals]\n{fallback}")
        except Exception as exc:
            lines.append(f"Serper fundamentals fallback also failed: {exc}")

    # --- Peer P/E from yfinance (data-driven, no opinion) ---
    if peer_tickers:
        lines.append("")
        lines.append("=== Peer Valuation (yfinance, no analyst input) ===")
        peer_pes: list[float] = []
        for peer in peer_tickers[:6]:
            try:
                p_info = yf.Ticker(_nse_ticker(peer)).info or {}
                p_pe  = p_info.get("trailingPE")
                p_pb  = p_info.get("priceToBook")
                p_cur = p_info.get("currentPrice") or p_info.get("previousClose")
                if p_pe:
                    peer_pes.append(p_pe)
                lines.append(
                    f"  {peer}: Price={round(p_cur,2) if p_cur else 'N/A'} | "
                    f"P/E={round(p_pe,1) if p_pe else 'N/A'} | "
                    f"P/B={round(p_pb,2) if p_pb else 'N/A'}"
                )
            except Exception:
                lines.append(f"  {peer}: data unavailable")

        if peer_pes:
            median_pe = float(np.median(peer_pes))
            lines.append(f"Peer median P/E: {median_pe:.1f}")
            if eps_ttm_val and eps_ttm_val > 0:
                lines.append(
                    f"Fair value at peer-median P/E ({median_pe:.1f}) = "
                    f"{eps_ttm_val * median_pe:.2f}"
                )
        else:
            lines.append("[yfinance] No peer P/E data — falling back to Serper for sector valuation.")
            try:
                from services.data.fetchers.news import fetch_news_context
                fallback = fetch_news_context([
                    f"Indian automobile EV sector PE ratio peer comparison NSE {today.year}",
                    f"MARUTI TATAMOTORS HEROMOTOCO PE ratio valuation {today.year}",
                ], max_queries=2)
                lines.append(f"[Serper fallback — peer P/E]\n{fallback}")
            except Exception as exc:
                lines.append(f"Serper peer fallback also failed: {exc}")

    # --- Seasonal pattern ---
    if not df.empty:
        seasonal = get_seasonal_pattern(df)
        today_month = date.today().month
        strong = [m for m, r in seasonal.items() if r > 1.5]
        weak   = [m for m, r in seasonal.items() if r < -1.5]
        cur_avg = seasonal.get(today_month)
        lines.append("")
        lines.append(
            f"Seasonality: Historically strong months={strong} | Weak months={weak} | "
            f"Current month avg return: {cur_avg:+.2f}%" if cur_avg is not None
            else f"Seasonality: Historically strong={strong} | Weak={weak}"
        )

    return "\n".join(lines)


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
