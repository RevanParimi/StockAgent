"""
scripts/api_exploration/iima_ff_factors.py
==========================================
IIMA India Fama-French 4-Factor Data Explorer — Free CSV download.

Factors: SMB (size), HML (value), WML (momentum), MF (market), RF (risk-free)
Source:  www.iimahd.ernet.in/~iffm/Indian-Fama-French-Momentum/
Vintage: 2023-03 (latest available on server as of May 2026)
Coverage: October 1993 onwards (monthly).

Note: IIMA has a TLS cert mismatch on iimahd.ernet.in — verify=False is intentional.
Note: faculty.iima.ac.in (the primary URL) returns 200 but with an HTML error page.

Signal value for StockAgent:
  - WML (momentum): positive = momentum regime; negative = reversal.
    Feed into weight_adapter to boost/dampen short-term conviction.
  - SMB: positive = small-cap outperforming; negative = large-cap leadership.
  - HML: positive = value stocks leading; negative = growth stocks leading.
  - MF:  market premium for the period (India Nifty/Sensex level).
"""

from __future__ import annotations

import io
import sys
import warnings
from pathlib import Path

import requests
import pandas as pd

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

# ─── CONFIG ───────────────────────────────────────────────────────────────────
IIMA_BASE  = "https://www.iimahd.ernet.in/~iffm/Indian-Fama-French-Momentum"
INDEX_URL  = f"{IIMA_BASE}/"
CACHE_DIR  = Path(__file__).parent / ".iima_cache"
TIMEOUT    = 30
# ──────────────────────────────────────────────────────────────────────────────


def _get(url: str) -> requests.Response:
    """GET with SSL verify=False (IIMA has cert mismatch) and suppressed warnings."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return requests.get(url, verify=False, timeout=TIMEOUT)


def discover_latest_vintage() -> str:
    """
    Scrape the IIMA index page to find the most recent data vintage (e.g. '2023-03').
    Returns the latest prefix string.
    """
    import re
    resp = _get(INDEX_URL)
    resp.raise_for_status()
    prefixes = sorted(set(
        m.group(1)
        for m in re.finditer(r'DATA/(\d{4}-\d{2})_', resp.text)
    ))
    if not prefixes:
        raise RuntimeError("Could not discover any data vintage from IIMA index page")
    latest = prefixes[-1]
    print(f"[iima] Available vintages: {prefixes} — using latest: {latest}")
    return latest


def download_four_factors_monthly(vintage: str | None = None, force_refresh: bool = False) -> pd.DataFrame:
    """
    Download the 4-factor monthly data (survivorship-bias adjusted).

    Columns: Date (YYYY-MM), SMB, HML, WML, MF, RF
      SMB = Small Minus Big (size factor)
      HML = High Minus Low (value factor)
      WML = Winners Minus Losers (momentum factor)
      MF  = Market Factor (Rm - Rf)
      RF  = Risk-Free rate
    All values are monthly % returns.
    """
    CACHE_DIR.mkdir(exist_ok=True)

    if vintage is None:
        vintage = discover_latest_vintage()

    filename  = f"{vintage}_FourFactors_and_Market_Returns_Monthly_SurvivorshipBiasAdjusted.csv"
    cache_path = CACHE_DIR / filename

    if cache_path.exists() and not force_refresh:
        from datetime import date
        age_days = (date.today() - date.fromtimestamp(cache_path.stat().st_mtime)).days
        if age_days < 30:
            print(f"[cache] Using cached {filename} ({age_days}d old)")
            return pd.read_csv(cache_path)

    url = f"{IIMA_BASE}/DATA/{filename}"
    print(f"[download] {url}")
    resp = _get(url)
    resp.raise_for_status()

    df = pd.read_csv(io.StringIO(resp.text))
    df.to_csv(cache_path, index=False)
    print(f"[cache] Saved to {cache_path}")
    return df


def explore_data(df: pd.DataFrame) -> None:
    """Print structure, date range, and recent values."""
    print(f"\n=== IIMA 4-Factor Monthly Data ===")
    print(f"  Shape:      {df.shape}")
    print(f"  Columns:    {list(df.columns)}")
    print(f"  Date range: {df['Date'].iloc[0]} -> {df['Date'].iloc[-1]}")
    print(f"\n  Last 12 months:")
    print(df.tail(12).to_string(index=False))
    print(f"\n  Descriptive stats (all history):")
    print(df.drop(columns=["Date"]).describe().round(4).to_string())


def momentum_regime(df: pd.DataFrame, lookback_months: int = 12) -> dict:
    """
    Current momentum regime from WML factor.
    Positive WML = momentum regime (past winners keep winning).
    Negative WML = reversal regime.
    Used to tune conviction weight direction in weight_adapter.
    """
    recent   = df.tail(lookback_months).copy()
    wml      = recent["WML"].dropna()
    avg_wml  = float(wml.mean())
    std_wml  = float(wml.std())
    last_wml = float(wml.iloc[-1])
    z        = (last_wml - avg_wml) / std_wml if std_wml else 0.0

    regime   = "MOMENTUM" if avg_wml > 0 else "REVERSAL"
    strength = "STRONG" if abs(z) > 1.5 else "MODERATE" if abs(z) > 0.5 else "WEAK"

    return {
        "regime":         regime,
        "strength":       strength,
        "last_wml_pct":   round(last_wml, 3),
        "avg_wml_pct":    round(avg_wml, 3),
        "z_score":        round(z, 2),
        "lookback_months": lookback_months,
        "signal":         f"{strength} {regime} — " + (
            "recent sector winners likely to keep outperforming."
            if regime == "MOMENTUM" else
            "sector rotation / mean-reversion in play; laggards may catch up."
        ),
    }


def market_tilt(df: pd.DataFrame, lookback_months: int = 12) -> dict:
    """
    Current size (SMB) and style (HML) tilt from factor data.
    Tells you whether the Indian market is favouring small/large and value/growth.
    """
    recent  = df.tail(lookback_months)
    smb_avg = float(recent["SMB"].mean())
    hml_avg = float(recent["HML"].mean())
    mf_avg  = float(recent["MF"].mean())

    return {
        "size_tilt":     "SMALL_CAP" if smb_avg > 0 else "LARGE_CAP",
        "style_tilt":    "VALUE"     if hml_avg > 0 else "GROWTH",
        "mf_avg_pct":    round(mf_avg,  3),
        "smb_avg_pct":   round(smb_avg, 3),
        "hml_avg_pct":   round(hml_avg, 3),
        "lookback_months": lookback_months,
    }


def monthly_factor_chart(df: pd.DataFrame, months: int = 12) -> None:
    """ASCII bar chart of recent WML values — quick regime visualisation."""
    recent = df.tail(months)
    print(f"\n=== WML Momentum Factor — Last {months} months ===")
    for _, row in recent.iterrows():
        val = row["WML"]
        if pd.isna(val):
            continue
        bar_len = int(abs(val) / 1.0)
        bar     = "+" * bar_len if val >= 0 else "-" * bar_len
        print(f"  {row['Date']}  {val:+7.2f}%  {bar}")


# ─── ENTRY POINT ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=== IIMA India Fama-French 4-Factor Explorer ===\n")

    df = download_four_factors_monthly()
    explore_data(df)

    mom = momentum_regime(df, lookback_months=12)
    print(f"\n=== Momentum Regime (last 12 months) ===")
    for k, v in mom.items():
        print(f"  {k:20s}: {v}")

    tilt = market_tilt(df, lookback_months=12)
    print(f"\n=== Market Tilt (Size + Style, last 12 months) ===")
    for k, v in tilt.items():
        print(f"  {k:20s}: {v}")

    monthly_factor_chart(df, months=12)

    print("\n[integration] Feed momentum_regime() output into weight_adapter.py")
    print("  positive WML -> boost short-term sector momentum bets")
    print("  negative WML -> favour contrarian/reversal signals")
