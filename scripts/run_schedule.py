"""
scripts/run_schedule.py
=======================
CLI for Phase 4 — scheduled and on-demand pipeline runs.

Usage
-----
# Start the persistent scheduler daemon (blocks, uses SCHEDULER_CRON)
python scripts/run_schedule.py start

# Run all configured tickers once right now
python scripts/run_schedule.py run-now

# Run a single ticker immediately
python scripts/run_schedule.py run-now --ticker MARUTI

# Show scheduler status and next run time
python scripts/run_schedule.py status

# Show score history for a ticker
python scripts/run_schedule.py history --ticker MARUTI --rows 10

# Show latest scores for all tracked tickers
python scripts/run_schedule.py latest
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Sub-command handlers
# ---------------------------------------------------------------------------

def cmd_start(args) -> None:
    """Start the blocking scheduler daemon."""
    from tools.scheduler import AutomobileScheduler
    from config import settings

    if not settings.SCHEDULER_ENABLED:
        print(
            "\nScheduler is disabled.\n"
            "Set SCHEDULER_ENABLED=true in your .env file to activate it.\n"
            "Or use 'run-now' to trigger a one-off run without enabling the daemon.\n"
        )
        sys.exit(0)

    print(f"\nStarting Automobile Agent Scheduler")
    print(f"  Cron  : {settings.SCHEDULER_CRON}")
    print(f"  Tickers: {', '.join(settings.SCHEDULER_TICKERS)}")
    print("  Press Ctrl+C to stop.\n")

    AutomobileScheduler().start()


def cmd_run_now(args) -> None:
    """Run one or all tickers immediately."""
    from tools.scheduler import AutomobileScheduler

    tickers = [args.ticker.upper()] if args.ticker else None
    sched = AutomobileScheduler()

    if tickers:
        print(f"\nRunning pipeline for: {tickers[0]}")
        sched.run_ticker(tickers[0])
    else:
        from config import settings
        print(f"\nRunning pipeline for all configured tickers: {settings.SCHEDULER_TICKERS}")
        sched.run_now()

    print("\nDone.")


def cmd_status(args) -> None:
    """Show scheduler and database status."""
    from tools.scheduler import AutomobileScheduler
    from config import settings

    sched = AutomobileScheduler()
    status = sched.status()

    print("\n=== Automobile Agent Scheduler Status ===")
    print(f"  Enabled    : {status['enabled']}")
    print(f"  Cron       : {status['cron']}")
    print(f"  Tickers    : {', '.join(status['tickers'])}")
    print(f"  Next run   : {status['next_run'] or 'N/A (scheduler not running)'}")
    print(f"  DB runs    : {status['db_total_runs']}")
    print(f"  DB tickers : {status['db_ticker_count']}")
    print(f"  Alert channels: {', '.join(settings.ALERT_CHANNELS)}")
    print()


def cmd_history(args) -> None:
    """Display score history for a ticker."""
    from tools.score_store import ScoreStore

    if not args.ticker:
        print("Error: --ticker is required for history command.")
        sys.exit(1)

    ticker = args.ticker.upper()
    store = ScoreStore()
    rows = store.get_history(ticker, limit=args.rows)

    if not rows:
        print(f"\nNo history found for {ticker}.")
        return

    print(f"\n=== Score History: {ticker} (last {len(rows)} runs) ===")
    print(f"{'Run At':<26} {'Score':>7} {'Verdict':<14} Thesis (truncated)")
    print("-" * 80)
    for r in rows:
        thesis = (r.get("investment_thesis") or "")[:40]
        print(f"{r['run_at']:<26} {r['final_score']:>7.3f} {r['verdict']:<14} {thesis}")
    print()

    delta = store.get_score_delta(ticker)
    if delta is not None:
        direction = "▲" if delta > 0 else "▼"
        print(f"  Score change (latest vs previous): {direction}{abs(delta):.3f}")
    if store.get_verdict_changed(ticker):
        print("  ⚠  Verdict changed on last run!")
    print()


def cmd_latest(args) -> None:
    """Display the latest score for every ticker in the database."""
    from tools.score_store import ScoreStore

    store = ScoreStore()
    rows = store.get_all_latest()

    if not rows:
        print("\nNo data yet. Run 'python scripts/run_schedule.py run-now' first.\n")
        return

    print(f"\n=== Latest Scores — All Tickers ===")
    print(f"{'Ticker':<14} {'Score':>7} {'Verdict':<14} {'Run At'}")
    print("-" * 65)
    for r in rows:
        print(
            f"{r['ticker']:<14} {r['final_score']:>7.3f} "
            f"{r['verdict']:<14} {r['run_at'][:19]}"
        )
    print()


# ---------------------------------------------------------------------------
# CLI parser
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Automobile Agent — Phase 4 Scheduler CLI"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # start
    sub.add_parser("start", help="Start the scheduler daemon (blocking)")

    # run-now
    run_p = sub.add_parser("run-now", help="Run pipeline immediately")
    run_p.add_argument("--ticker", help="Single ticker to run (default: all configured)")

    # status
    sub.add_parser("status", help="Show scheduler and database status")

    # history
    hist_p = sub.add_parser("history", help="Show score history for a ticker")
    hist_p.add_argument("--ticker", required=True, help="NSE ticker, e.g. MARUTI")
    hist_p.add_argument("--rows", type=int, default=10, help="Number of rows (default: 10)")

    # latest
    sub.add_parser("latest", help="Show latest scores for all tickers")

    args = parser.parse_args()

    dispatch = {
        "start":   cmd_start,
        "run-now": cmd_run_now,
        "status":  cmd_status,
        "history": cmd_history,
        "latest":  cmd_latest,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
