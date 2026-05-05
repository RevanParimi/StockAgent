"""
main.py
=======
CLI entry point for the Automobile Agent.

Usage
-----
    python main.py MARUTI
    python main.py "Tata Motors" --output json
    python main.py BAJAJ-AUTO --output markdown --save
    python main.py --list-tickers

Options
-------
    ticker          NSE/BSE ticker or company name (positional)
    --output        Output format: json (default) | markdown
    --save          Save report to outputs/ directory
    --list-tickers  Print supported automobile tickers and exit
    --log-level     Logging verbosity: DEBUG | INFO | WARNING (default INFO)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import threading
import time
from datetime import date
from pathlib import Path

# ---------------------------------------------------------------------------
# Logging setup (must happen before importing agents so their loggers pick it up)
# ---------------------------------------------------------------------------
def _setup_logging(level: str) -> None:
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_dir / "automobile_agent.log", encoding="utf-8"),
        ],
    )


# ---------------------------------------------------------------------------
# Supported tickers (for --list-tickers)
# ---------------------------------------------------------------------------
KNOWN_TICKERS = {
    "MARUTI":     "Maruti Suzuki India Ltd",
    "TATAMOTORS": "Tata Motors Ltd",
    "M&M":        "Mahindra & Mahindra Ltd",
    "HEROMOTOCO": "Hero MotoCorp Ltd",
    "BAJAJ-AUTO": "Bajaj Auto Ltd",
    "EICHERMOT":  "Eicher Motors Ltd (Royal Enfield)",
    "TVSMOTORS":  "TVS Motor Company Ltd",
    "ASHOKLEY":   "Ashok Leyland Ltd",
    "ESCORTS":    "Escorts Kubota Ltd",
    "FORCEMOT":   "Force Motors Ltd",
}


# ---------------------------------------------------------------------------
# Output formatters
# ---------------------------------------------------------------------------

def _format_json(report) -> str:
    return report.model_dump_json(indent=2)


def _format_markdown(report) -> str:
    lines = [
        f"# Automobile Agent Report — {report.ticker}",
        f"**Company:** {report.company_name}  ",
        f"**Date:** {report.report_date}  ",
        f"**Verdict:** {report.verdict_emoji()} {report.verdict}  ",
        f"**Final Score:** {report.final_score:.3f} / 1.000",
        "",
        "## Agent Scores",
        "| Agent | Raw Score | Weight | Weighted |",
        "|---|---|---|---|",
    ]
    for name, ws in report.weighted_agent_scores.items():
        lines.append(f"| {name} | {ws.raw:.3f} | {ws.weight:.2f} | {ws.weighted:.4f} |")

    lines += [
        "",
        "## Investment Thesis",
        report.investment_thesis,
        "",
        "## Conviction Drivers",
    ]
    for d in report.conviction_drivers:
        lines.append(f"- {d}")

    lines += ["", "## Top Risks"]
    for r in report.top_risks:
        lines.append(f"- {r}")

    if report.conflicts_resolved:
        lines += ["", "## Conflicts Resolved"]
        for c in report.conflicts_resolved:
            lines.append(f"- {c}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Micro search loop
# ---------------------------------------------------------------------------

# Per-sector macro query presets.
# These are sector-level questions — the answer is the same regardless of
# which individual stock is being analysed within that sector.
# Results are cached in tools/macro_cache.py under the sector key and consumed
# by ContextBuilder._build_risk_macro() (auto), _build_macro_policy() (bfsi),
# and _build_it_risk_macro() (it) to avoid repeating the same Serper queries
# for every stock in a batch.
#
# RE sector is excluded — its macro signals (MNRE auctions, DISCOM payments)
# are per-company, not sector-wide, so no shared cache benefit exists.
_SECTOR_MACRO_QUERIES: dict[str, list[str]] = {
    "automobile": [
        # Nifty Auto momentum + commodity input costs (steel, aluminium, crude)
        "Nifty Auto index India automobile sector outlook crude oil steel aluminium commodity prices",
        # Demand-side + policy signals (EV incentives, FADA dispatch, RBI auto loan EMI)
        "India EV policy electric vehicle incentives FADA retail dispatch RBI repo rate auto loan EMI",
    ],
    "bfsi": [
        # RBI monetary policy + banking system liquidity (same answer for any bank stock on a given day)
        "RBI MPC repo rate decision India banking system credit growth CASA deposit liquidity",
        # Regulatory environment + asset quality signals (sector-wide, not stock-specific)
        "Indian banking NPA slippage credit quality SEBI RBI regulatory action PSU private NBFC",
    ],
    "it": [
        # US tech spending + Fed rate + USD/INR (primary revenue and margin drivers for Indian IT)
        "US IT spending enterprise software cloud capex Federal Reserve rate USD INR exchange rate Indian IT",
        # Visa + AI disruption + sector demand signals (sector-wide, applies to TCS/Infosys/HCL equally)
        "H1B visa India IT sector GenAI AI deal demand TCS Infosys Wipro HCL quarterly results outlook",
    ],
}


def _micro_search_loop() -> None:
    """
    Background daemon thread: pre-fetches sector-level macro news for
    Automobile, BFSI, and IT on a configurable schedule and stores results
    in the in-memory macro cache (tools/macro_cache.py).

    Each cycle fetches MICRO_QUERIES_PER_RUN queries per sector sequentially.
    RE sector is excluded — its signals are per-company, not sector-wide.

    Configuration (.env):
        MICRO_CYCLES_PER_DAY   default 6  → runs every 4 hours
        MICRO_QUERIES_PER_RUN  default 2  → 2 Serper calls per sector per run

    Monthly Serper budget from this loop:
        3 sectors × 2 queries × 6 cycles × 30 days = 1,080 calls/month

    Each cache HIT saves 3 Serper calls per stock analysis:
        At 5 tickers/day across 3 sectors: 3 × 5 × 3 sectors × 22 days = 990 calls/month saved
    """
    from core.config import settings
    from data.news import fetch_news_context
    from data.cache import set_macro_cache

    n = settings.MICRO_QUERIES_PER_RUN
    interval = (24 * 3600) / settings.MICRO_CYCLES_PER_DAY

    _log = logging.getLogger(__name__)
    _log.info(
        "[micro_loop] Starting — %d sectors × %d cycles/day (every %.0fm) × %d queries/run",
        len(_SECTOR_MACRO_QUERIES),
        settings.MICRO_CYCLES_PER_DAY,
        interval / 60,
        n,
    )

    while True:
        for sector, queries in _SECTOR_MACRO_QUERIES.items():
            try:
                _log.info("[micro_loop] Fetching %s macro context...", sector)
                key = settings.get_serper_key(sector)
                text = fetch_news_context(queries[:n], max_queries=n, api_key=key)
                set_macro_cache(sector, text)
                _log.info("[micro_loop] %s cache refreshed (%d chars)", sector, len(text))
            except Exception as exc:
                _log.warning("[micro_loop] %s pre-fetch failed: %s", sector, exc)
        time.sleep(interval)


def start_micro_loop() -> threading.Thread:
    """
    Launch the micro search loop as a daemon thread.

    Daemon threads die automatically when the main process exits.
    Call this before the main analysis loop when running in scheduler/daemon mode.
    """
    t = threading.Thread(target=_micro_search_loop, name="micro-search-loop", daemon=True)
    t.start()
    return t


# ---------------------------------------------------------------------------
# Save to disk
# ---------------------------------------------------------------------------

def _save_report(content: str, ticker: str, fmt: str) -> Path:
    out_dir = Path("outputs")
    out_dir.mkdir(exist_ok=True)
    ext = "json" if fmt == "json" else "md"
    filename = out_dir / f"{ticker}_{date.today().isoformat()}.{ext}"
    filename.write_text(content, encoding="utf-8")
    return filename


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Automobile Agent – Indian auto stock analyser"
    )
    parser.add_argument(
        "ticker",
        nargs="?",
        help="NSE/BSE ticker symbol or company name",
    )
    parser.add_argument(
        "--output",
        choices=["json", "markdown"],
        default="json",
        help="Output format (default: json)",
    )
    parser.add_argument(
        "--save",
        action="store_true",
        help="Save report to outputs/ directory",
    )
    parser.add_argument(
        "--list-tickers",
        action="store_true",
        help="List supported automobile tickers and exit",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity",
    )
    parser.add_argument(
        "--micro-loop",
        action="store_true",
        help=(
            "Start the micro search loop in a background thread before running analysis. "
            "Pre-fetches automobile sector macro news and caches it to save Serper calls. "
            "Useful when running multiple tickers in sequence."
        ),
    )

    args = parser.parse_args()
    _setup_logging(args.log_level)

    if args.list_tickers:
        print("\nSupported Indian Automobile Tickers (NSE)\n")
        for ticker, name in KNOWN_TICKERS.items():
            print(f"  {ticker:<14} {name}")
        print()
        sys.exit(0)

    if not args.ticker:
        parser.print_help()
        sys.exit(1)

    # Start micro search loop if requested (background daemon thread)
    if args.micro_loop:
        start_micro_loop()
        # Give the first run a moment to complete before analysis starts
        time.sleep(2)

    # Lazy import here so logging is configured first
    from pipeline.orchestrator import AutomobileAgentOrchestrator

    logger = logging.getLogger(__name__)
    logger.info("Starting Automobile Agent for: %s", args.ticker)

    try:
        orchestrator = AutomobileAgentOrchestrator()
        report = orchestrator.analyse(args.ticker)
    except Exception as exc:
        logger.error("Pipeline failed: %s", exc, exc_info=True)
        print(f"\nError: {exc}", file=sys.stderr)
        sys.exit(1)

    # Format output
    if args.output == "markdown":
        content = _format_markdown(report)
    else:
        content = _format_json(report)

    sys.stdout.buffer.write((content + "\n").encode("utf-8", errors="replace"))
    sys.stdout.buffer.flush()

    if args.save:
        path = _save_report(content, report.ticker, args.output)
        print(f"\nReport saved to: {path}", file=sys.stderr)


if __name__ == "__main__":
    main()
