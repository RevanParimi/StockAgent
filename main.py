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

    # Lazy import here so logging is configured first
    from agents.orchestrator import AutomobileAgentOrchestrator

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

    print(content)

    if args.save:
        path = _save_report(content, report.ticker, args.output)
        print(f"\nReport saved to: {path}", file=sys.stderr)


if __name__ == "__main__":
    main()
