"""
scripts/api_exploration/nse_insider_scraper.py
===============================================
NSE Market Intelligence Scraper — No API key, uses nsepython library.

pip install nsepython

Data covered:
  1. Bulk deals   — single transaction >0.5% of total listed shares
  2. Block deals  — min Rs.10 Cr, conducted in 35-min opening window
  3. FII/DII      — daily institutional buying/selling (published 6-8 PM IST)
  4. NSE events   — upcoming board meetings, earnings dates, dividends
  5. Top gainers/losers — market-level momentum scan
  6. Pre-open movers   — early demand signal before market opens

Signal value for StockAgent:
  Bulk buy by known prop desks / FIIs = institutional conviction.
  FII net negative + DII net positive = domestic support vs FII exodus.
  Earnings date from nse_events = trigger for conviction spike in RL system.

Note: NSE has bot protection — direct requests fail. nsepython handles
the cookie handshake internally and is the community-standard workaround.
"""

from __future__ import annotations

import sys

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

import json
from datetime import date

# pip install nsepython
try:
    from nsepython import (
        get_bulkdeals,
        get_blockdeals,
        nse_fiidii,
        nse_events,
        nse_get_top_gainers,
        nse_get_top_losers,
        nse_preopen_movers,
        nse_eq,
        equity_history,
        nse_most_active,
    )
    import pandas as pd
    _DEPS_OK = True
except ImportError:
    _DEPS_OK = False
    print("[setup] Run: pip install nsepython")


# ─── BULK AND BLOCK DEALS ─────────────────────────────────────────────────────

def show_bulk_deals(top_n: int = 15) -> pd.DataFrame | None:
    """
    Bulk deals — >0.5% of total shares in a single transaction.
    High-value signal: institutional accumulation or distribution.
    """
    df = get_bulkdeals()
    if df.empty:
        print("=== Bulk Deals: none today ===")
        return None

    print(f"\n=== Bulk Deals — {date.today()} ({len(df)} total, showing {min(top_n, len(df))}) ===")
    print(f"  {'Symbol':15s} | {'Client':40s} | {'B/S':4s} | {'Qty':>12s} | {'Price':>9s}")
    print("  " + "-" * 90)
    for _, row in df.head(top_n).iterrows():
        print(
            f"  {str(row.get('Symbol',''))[:15]:15s} | "
            f"{str(row.get('Client Name',''))[:40]:40s} | "
            f"{str(row.get('Buy/Sell',''))[:4]:4s} | "
            f"{int(row.get('Quantity Traded', 0) or 0):>12,} | "
            f"{float(row.get('Trade Price / Wght. Avg. Price', 0) or 0):>9.2f}"
        )
    return df


def show_block_deals(top_n: int = 10) -> pd.DataFrame | None:
    """Block deals — minimum Rs.10 Cr single transaction in 35-min window."""
    df = get_blockdeals()
    if df.empty:
        print("=== Block Deals: none today ===")
        return None

    print(f"\n=== Block Deals — {date.today()} ({len(df)} total) ===")
    print(f"  {'Symbol':15s} | {'Client':40s} | {'B/S':4s} | {'Qty':>12s} | {'Price':>9s}")
    print("  " + "-" * 90)
    for _, row in df.head(top_n).iterrows():
        print(
            f"  {str(row.get('Symbol',''))[:15]:15s} | "
            f"{str(row.get('Client Name',''))[:40]:40s} | "
            f"{str(row.get('Buy/Sell',''))[:4]:4s} | "
            f"{int(row.get('Quantity Traded', 0) or 0):>12,} | "
            f"{float(row.get('Trade Price / Wght. Avg. Price', 0) or 0):>9.2f}"
        )
    return df


# ─── FII / DII ─────────────────────────────────────────────────────────────────

def show_fii_dii() -> None:
    """
    FII and DII daily net buying/selling.
    Published by NSE around 6-8 PM IST each trading day.
    FII net negative + DII positive = classic domestic cushion signal.
    """
    df = nse_fiidii()
    print(f"\n=== FII / DII Daily Activity ===")
    if isinstance(df, pd.DataFrame):
        print(df.to_string(index=False))
    else:
        print(df)

    # Compute net signal
    if isinstance(df, pd.DataFrame) and "netValue" in df.columns and "category" in df.columns:
        fii_net = df.loc[df["category"].str.contains("FII|FPI", na=False), "netValue"]
        dii_net = df.loc[df["category"].str.contains("DII", na=False), "netValue"]
        if not fii_net.empty and not dii_net.empty:
            fii_v = float(fii_net.iloc[0])
            dii_v = float(dii_net.iloc[0])
            combined = fii_v + dii_v
            print(f"\n  FII net: {fii_v:+,.2f} Cr | DII net: {dii_v:+,.2f} Cr | Combined: {combined:+,.2f} Cr")
            if fii_v < 0 and dii_v > 0:
                print("  Signal: DII absorbing FII selling — moderate support")
            elif fii_v > 0 and dii_v > 0:
                print("  Signal: Both buying — strong bullish conviction")
            elif fii_v < 0 and dii_v < 0:
                print("  Signal: Both selling — risk-off, reduce exposure")
            elif fii_v > 0 and dii_v < 0:
                print("  Signal: FII buying, DII selling — FII-led rally, watch for DII re-entry")


# ─── NSE CORPORATE EVENTS ─────────────────────────────────────────────────────

def show_upcoming_events(days_ahead: int = 7, top_n: int = 20) -> None:
    """
    Upcoming board meetings, earnings dates, dividends from NSE.
    High value for RL system: earnings trigger = pre-event conviction spike.
    """
    df = nse_events()
    print(f"\n=== Upcoming NSE Events (next {days_ahead} days, first {top_n}) ===")
    if isinstance(df, pd.DataFrame):
        print(f"  {'Symbol':15s} | {'Date':12s} | {'Purpose':60s}")
        print("  " + "-" * 92)
        for _, row in df.head(top_n).iterrows():
            print(
                f"  {str(row.get('symbol',''))[:15]:15s} | "
                f"{str(row.get('date',''))[:12]:12s} | "
                f"{str(row.get('purpose',''))[:60]:60s}"
            )
    else:
        print(df)


# ─── MARKET MOMENTUM ──────────────────────────────────────────────────────────

def show_top_movers(top_n: int = 10) -> None:
    """Top gainers and losers — quick market momentum snapshot."""
    try:
        gainers = nse_get_top_gainers()
        print(f"\n=== Top Gainers ===")
        if isinstance(gainers, pd.DataFrame):
            for _, row in gainers.head(top_n).iterrows():
                print(
                    f"  {str(row.get('symbol',''))[:15]:15s} | "
                    f"LTP={float(row.get('lastPrice',0) or 0):>9.2f} | "
                    f"Change={float(row.get('pChange',0) or 0):>+6.2f}%"
                )
        else:
            print(str(gainers)[:400])
    except Exception as e:
        print(f"  gainers error: {e}")

    try:
        losers = nse_get_top_losers()
        print(f"\n=== Top Losers ===")
        if isinstance(losers, pd.DataFrame):
            for _, row in losers.head(top_n).iterrows():
                print(
                    f"  {str(row.get('symbol',''))[:15]:15s} | "
                    f"LTP={float(row.get('lastPrice',0) or 0):>9.2f} | "
                    f"Change={float(row.get('pChange',0) or 0):>+6.2f}%"
                )
        else:
            print(str(losers)[:400])
    except Exception as e:
        print(f"  losers error: {e}")


def show_preopen_movers(top_n: int = 10) -> None:
    """
    Pre-open session movers — demand signal before market opens 9:15 AM.
    Strong pre-open buy interest = likely gap-up at open.
    """
    try:
        df = nse_preopen_movers("nifty50")
        print(f"\n=== Pre-Open Movers (Nifty 50) ===")
        if isinstance(df, pd.DataFrame):
            for _, row in df.head(top_n).iterrows():
                print(
                    f"  {str(row.get('symbol',''))[:15]:15s} | "
                    f"IEP={float(row.get('iep',0) or 0):>9.2f} | "
                    f"Change={float(row.get('perCng',0) or 0):>+6.2f}%"
                )
        else:
            print(str(df)[:400])
    except Exception as e:
        print(f"  preopen error: {e}")


def show_most_active(top_n: int = 10) -> None:
    """Most actively traded stocks by value — liquidity signal."""
    try:
        df = nse_most_active()
        print(f"\n=== Most Active by Value ===")
        if isinstance(df, pd.DataFrame):
            for _, row in df.head(top_n).iterrows():
                print(
                    f"  {str(row.get('symbol',''))[:15]:15s} | "
                    f"Value={float(row.get('totalTurnover',0) or 0):>14,.0f} | "
                    f"Vol={int(row.get('totalTradedVolume',0) or 0):>12,}"
                )
        else:
            print(str(df)[:400])
    except Exception as e:
        print(f"  most_active error: {e}")


# ─── USEFUL SUMMARY FOR STOCKAGENT ────────────────────────────────────────────

def stockagent_daily_context() -> dict:
    """
    Produce a compact context dict for injection into StockAgent agents.
    Use this as a daily pre-market intelligence snapshot.
    """
    context: dict = {}

    try:
        bd = get_bulkdeals()
        if not bd.empty:
            # Net bulk buying per symbol
            buys  = bd[bd["Buy/Sell"].str.upper() == "BUY"].groupby("Symbol")["Quantity Traded"].sum()
            sells = bd[bd["Buy/Sell"].str.upper() == "SELL"].groupby("Symbol")["Quantity Traded"].sum()
            net   = buys.subtract(sells, fill_value=0).sort_values(ascending=False)
            context["bulk_deal_net_buyers"]  = net[net > 0].index.tolist()[:5]
            context["bulk_deal_net_sellers"] = net[net < 0].index.tolist()[:5]
    except Exception:
        pass

    try:
        fii_df = nse_fiidii()
        if isinstance(fii_df, pd.DataFrame):
            for _, row in fii_df.iterrows():
                cat = str(row.get("category", "")).upper()
                if "FII" in cat or "FPI" in cat:
                    context["fii_net_cr"] = float(row.get("netValue", 0))
                elif "DII" in cat:
                    context["dii_net_cr"] = float(row.get("netValue", 0))
    except Exception:
        pass

    try:
        events_df = nse_events()
        if isinstance(events_df, pd.DataFrame):
            context["upcoming_earnings"] = events_df["symbol"].head(10).tolist()
    except Exception:
        pass

    return context


# ─── ENTRY POINT ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if not _DEPS_OK:
        print("Run: pip install nsepython")
    else:
        print("=== NSE Market Intelligence (nsepython) ===\n")

        show_bulk_deals(top_n=10)
        show_block_deals(top_n=10)
        show_fii_dii()
        show_upcoming_events(top_n=10)
        show_top_movers(top_n=5)
        show_most_active(top_n=5)

        print("\n=== StockAgent Daily Context Dict ===")
        ctx = stockagent_daily_context()
        print(json.dumps(ctx, indent=2, default=str))
