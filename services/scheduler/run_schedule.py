"""
scripts/run_schedule.py
=======================
CLI for Phase 4 — scheduled and on-demand pipeline runs.
Phase 5 — RL Feedback daily review commands added.

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

# ── Phase 5: RL Feedback ──────────────────────────────────────────────────
# Generate 30-day prediction envelope for all (or one) tickers (month-start)
python scripts/run_schedule.py forecast
python scripts/run_schedule.py forecast --ticker MARUTI

# Run daily feedback review for yesterday (or a specific date)
python scripts/run_schedule.py daily-review
python scripts/run_schedule.py daily-review --ticker MARUTI
python scripts/run_schedule.py daily-review --ticker MARUTI --date 2026-04-09

# Show prediction envelope and feedback log for a ticker
python scripts/run_schedule.py feedback-status --ticker MARUTI

# Start the full scheduler daemon (analysis cron + daily-review cron)
python scripts/run_schedule.py start
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

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
    from services.scheduler.python.scheduler import AutomobileScheduler
    from core.config import settings

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
    from services.scheduler.python.scheduler import AutomobileScheduler

    tickers = [args.ticker.upper()] if args.ticker else None
    sched = AutomobileScheduler()

    if tickers:
        print(f"\nRunning pipeline for: {tickers[0]}")
        sched.run_ticker(tickers[0])
    else:
        from core.config import settings
        print(f"\nRunning pipeline for all configured tickers: {settings.SCHEDULER_TICKERS}")
        sched.run_now()

    print("\nDone.")


def cmd_status(args) -> None:
    """Show scheduler and database status."""
    from services.scheduler.python.scheduler import AutomobileScheduler
    from core.config import settings

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
    from services.data.stores.score_store import ScoreStore

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
    from services.data.stores.score_store import ScoreStore

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
# Phase 5 — RL Feedback sub-command handlers
# ---------------------------------------------------------------------------

def cmd_forecast(args) -> None:
    """Generate month-start 30-day prediction envelope(s)."""
    from core.intelligence.rl.workflows.generate_forecast import generate_forecast
    from core.config import settings

    tickers = [args.ticker.upper()] if args.ticker else settings.SCHEDULER_TICKERS

    print(f"\nGenerating forecast envelopes for: {', '.join(tickers)}\n")
    for ticker in tickers:
        try:
            envelope = generate_forecast(ticker)
            print(
                f"  [OK] {ticker} — cycle={envelope.cycle_id} | "
                f"base_close=₹{envelope.base_close:.2f} | "
                f"horizon={len(envelope.daily_forecasts)} trading days"
            )
        except Exception as exc:
            print(f"  [FAIL] {ticker} — {exc}")
    print()


def cmd_daily_review(args) -> None:
    """Run daily RL feedback review for one or all tickers."""
    from core.intelligence.rl.workflows.daily_review import run_daily_review
    from core.config import settings
    from datetime import date, timedelta

    tickers = [args.ticker.upper()] if args.ticker else settings.SCHEDULER_TICKERS

    if args.date:
        review_date = date.fromisoformat(args.date)
    else:
        review_date = date.today() - timedelta(days=1)
        while review_date.weekday() >= 5:
            review_date -= timedelta(days=1)

    print(f"\nRunning daily review for {review_date} | tickers: {', '.join(tickers)}\n")
    for ticker in tickers:
        try:
            summary = run_daily_review(ticker, review_date)
            status = summary.get("status", "unknown")
            if status == "completed":
                direction = "CORRECT" if summary["direction_correct"] else "WRONG"
                print(
                    f"  [OK] {ticker} | error={summary['price_error_pct']:+.2f}% | "
                    f"direction={direction} | lessons={summary['lessons_added']} | "
                    f"weights={summary['weight_version']}"
                )
            else:
                print(f"  [SKIP] {ticker} — {status}")
        except Exception as exc:
            print(f"  [FAIL] {ticker} — {exc}")
    print()


def cmd_feedback_status(args) -> None:
    """Show prediction envelope and feedback log summary for a ticker."""
    from core.intelligence.rl.stores.prediction_store import PredictionStore
    from core.config import settings

    if not args.ticker:
        print("Error: --ticker is required for feedback-status.")
        sys.exit(1)

    ticker = args.ticker.upper()
    store = PredictionStore(ticker)
    cycle_id = store.current_cycle_id()

    envelope = store.load_envelope(cycle_id)
    feedback_log = store.load_feedback_log(cycle_id)
    wm = store.load_weight_memory()
    ledger = store.load_learning_ledger()

    print(f"\n=== RL Feedback Status: {ticker} | Cycle: {cycle_id} ===\n")

    if envelope:
        total = len(envelope.daily_forecasts)
        reviewed = len(feedback_log.entries)
        remaining = total - reviewed
        print(f"  Forecast horizon : {total} days")
        print(f"  Days reviewed    : {reviewed}")
        print(f"  Days remaining   : {remaining}")
        print(f"  Base close       : ₹{envelope.base_close:.2f}")
        print(f"  Weight version   : v{envelope.weight_version_used}")
    else:
        print("  No envelope found. Run 'forecast' command first.")

    if wm:
        print(f"\n  Current weights (v{wm.weight_version}):")
        for agent, w in wm.effective_weights().items():
            base = wm.base_weights.get(agent, 0)
            drift = round(w - base, 4)
            drift_str = f"({drift:+.4f} from base)" if drift != 0 else "(at base)"
            print(f"    {agent:<20} {w:.4f}  {drift_str}")

    if feedback_log.entries:
        hits = sum(1 for e in feedback_log.entries if e.direction_correct)
        hit_rate = hits / len(feedback_log.entries) * 100
        print(f"\n  Direction accuracy: {hits}/{len(feedback_log.entries)} ({hit_rate:.1f}%)")
        print(f"\n  Last 5 entries:")
        print(f"  {'Date':<12} {'Error%':>8} {'Direction':<12} {'Miss Agent':<20} Lessons")
        print("  " + "-" * 70)
        for e in feedback_log.entries[-5:]:
            miss_agent = e.miss_analysis.primary_miss_agent if e.miss_analysis else "-"
            correct_str = "CORRECT" if e.direction_correct else "WRONG  "
            print(
                f"  {e.date:<12} {e.price_error_pct:>+8.2f}% {correct_str:<12} "
                f"{miss_agent:<20} {e.lessons_generated}"
            )

    if ledger.lessons:
        print(f"\n  Learning ledger: {len(ledger.lessons)} lessons")
        for lesson in ledger.lessons[-3:]:
            print(
                f"    [{lesson.lesson_id}] {lesson.pattern} "
                f"(confidence={lesson.confidence:.2f}, seen={lesson.occurrences}x)"
            )
        if ledger.miss_counter:
            top_misses = sorted(ledger.miss_counter.items(), key=lambda x: -x[1])[:3]
            print(f"\n  Top missed factors: {top_misses}")
    else:
        print("\n  No lessons learned yet.")

    print()


def cmd_dossier_status(args) -> None:
    """Print per-ticker dossier health: size, version, staleness, counts."""
    from core.intelligence.rl.stores.prediction_store import PredictionStore
    from services.api.log_buffer import get_active_tickers_with_sector

    rows = get_active_tickers_with_sector()
    if getattr(args, "ticker", None):
        rows = [r for r in rows if r["sym"] in args.ticker]
    for r in rows:
        store = PredictionStore(ticker=r["sym"], sector=r["sector"])
        d = store.load_dossier()
        if d is None:
            print(f"{r['sym']:12s}  — no dossier yet")
            continue
        alive = sum(1 for s in d.response_signatures if s.is_alive)
        open_q = sum(1 for q in d.open_questions if not q.resolved_on)
        print(f"{r['sym']:12s}  v{d.version}  updated={d.last_updated}  "
              f"obs={len(d.observations)}  signatures={alive}  "
              f"guidance_open={sum(1 for g in d.guidance if g.status == 'open')}  "
              f"open_questions={open_q}  digest_chars={len(d.to_digest(99999))}")


# ---------------------------------------------------------------------------
# CLI parser
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Automobile Agent — Scheduler & RL Feedback CLI"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # start
    sub.add_parser("start", help="Start the scheduler daemon (blocking) — runs analysis + daily review crons")

    # run-now
    run_p = sub.add_parser("run-now", help="Run analysis pipeline immediately")
    run_p.add_argument("--ticker", help="Single ticker to run (default: all configured)")

    # status
    sub.add_parser("status", help="Show scheduler and database status")

    # history
    hist_p = sub.add_parser("history", help="Show score history for a ticker")
    hist_p.add_argument("--ticker", required=True, help="NSE ticker, e.g. MARUTI")
    hist_p.add_argument("--rows", type=int, default=10, help="Number of rows (default: 10)")

    # latest
    sub.add_parser("latest", help="Show latest scores for all tickers")

    # ── Phase 5: RL Feedback ─────────────────────────────────────────────
    # forecast
    forecast_p = sub.add_parser("forecast", help="Generate 30-day prediction envelope (run on month-start)")
    forecast_p.add_argument("--ticker", help="Single ticker (default: all SCHEDULER_TICKERS)")

    # daily-review
    review_p = sub.add_parser("daily-review", help="Run daily RL feedback review")
    review_p.add_argument("--ticker", help="Single ticker (default: all SCHEDULER_TICKERS)")
    review_p.add_argument("--date", help="ISO date to review e.g. 2026-04-09 (default: yesterday)")

    # feedback-status
    fstatus_p = sub.add_parser("feedback-status", help="Show RL feedback state for a ticker")
    fstatus_p.add_argument("--ticker", required=True, help="NSE ticker, e.g. MARUTI")

    # dossier-status
    dstatus_p = sub.add_parser("dossier-status", help="RL dossier health per ticker")
    dstatus_p.add_argument("--ticker", nargs="*", help="One or more NSE tickers (default: all managed)")

    args = parser.parse_args()

    dispatch = {
        "start":           cmd_start,
        "run-now":         cmd_run_now,
        "status":          cmd_status,
        "history":         cmd_history,
        "latest":          cmd_latest,
        "forecast":        cmd_forecast,
        "daily-review":    cmd_daily_review,
        "feedback-status": cmd_feedback_status,
        "dossier-status":  cmd_dossier_status,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
