"""
eval/evaluate.py
================
StockAgent model accuracy evaluation — CLI entry point.

Usage
-----
  # Full evaluation (all sectors, reads data/predictions/ + outputs/)
  python eval/evaluate.py

  # Single sector
  python eval/evaluate.py --sector automobile

  # Save report to a specific file (useful for before/after comparisons)
  python eval/evaluate.py --output eval/reports/before_change.json

  # Compare two saved reports to measure improvement
  python eval/evaluate.py --compare eval/reports/before.json eval/reports/after.json

  # Quiet: JSON only, no console table
  python eval/evaluate.py --json-only

Output
------
  eval/reports/eval_{YYYY-MM-DD}.json   — saved automatically
  Console: hierarchical accuracy table
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

# Allow running as `python eval/evaluate.py` from project root
_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

from eval.engine import build_eval_report
from eval.schemas import (
    AgentEvalResult,
    EvalReport,
    SectorEvalResult,
    SubScoreAccuracy,
)


# ─────────────────────────────────────────────────────────────────────────────
# Console reporter
# ─────────────────────────────────────────────────────────────────────────────

_GRADE_COLOUR = {
    "A":   "[A]",
    "B":   "[B]",
    "C":   "[C]",
    "D":   "[D]",
    "F":   "[F]",
    "N/A": "[-]",
}


def _bar(value: float, width: int = 20) -> str:
    """ASCII progress bar for a 0-1 value."""
    filled = round(value * width)
    return "[" + "#" * filled + "." * (width - filled) + f"] {value:.1%}"


def _grade_symbol(grade: str) -> str:
    return _GRADE_COLOUR.get(grade, "⬜") + f" {grade}"


def _sep(char: str = "-", width: int = 90) -> str:
    return char * width


def _print_sub_scores(sub_scores: dict[str, SubScoreAccuracy], indent: int = 6) -> None:
    pad = " " * indent
    header = f"{'Sub-score':<35} {'Avg':>6} {'Std':>6} {'Samples':>8} {'Corr w/Dir':>11} {'Grade':>6}"
    print(pad + header)
    print(pad + "-" * len(header))
    for dim, ss in sorted(sub_scores.items()):
        corr_str = f"{ss.correlation_with_direction:+.3f}" if ss.correlation_with_direction is not None else "  N/A "
        grade_sym = _grade_symbol(ss.grade)
        print(pad + f"{dim:<35} {ss.avg:>6.3f} {ss.std:>6.3f} {ss.sample_count:>8} {corr_str:>11} {grade_sym}")


def _print_calibration(calib_buckets: list, label: str = "Final score calibration", indent: int = 6) -> None:
    if not calib_buckets:
        return
    pad = " " * indent
    print(f"\n{pad}{label}:")
    print(pad + f"  {'Score Range':<14} {'Samples':>8} {'Hit Rate':>10} {'Ideal':>8} {'CalibErr':>10}")
    print(pad + "  " + "-" * 52)
    for b in calib_buckets:
        print(pad + f"  {b.bucket:<14} {b.sample_count:>8} {b.direction_hit_rate:>10.1%} {b.ideal_hit_rate:>8.1%} {b.calibration_error:>10.3f}")


def _print_agent(ar: AgentEvalResult, show_sub_scores: bool = True) -> None:
    drift_str = f"{ar.weight_drift:+.3f}" if ar.weight_drift != 0 else " 0.000"
    print(f"      +- {ar.agent.upper()}")
    print(f"      |  Weight:        base={ar.weight_base:.3f}  current={ar.weight_current:.3f}  drift={drift_str}")
    print(f"      |  Direction:     {_bar(ar.direction_hit_rate)}  ({ar.direction_hits}/{ar.total_evaluated})")
    print(f"      |  Score spread:  avg={ar.avg_score:.3f}  std={ar.score_std:.3f}" +
          ("  ! bunching" if ar.score_std < 0.08 and ar.avg_score > 0 else ""))
    if ar.primary_miss_count:
        mt = ", ".join(f"{k}:{v}" for k, v in ar.miss_type_breakdown.items())
        print(f"      |  Primary miss:  {ar.primary_miss_count}x  ({mt})")
    if ar.regime_hit_rates:
        regime_parts = "  ".join(f"{r}={v:.1%}" for r, v in sorted(ar.regime_hit_rates.items()))
        print(f"      |  By regime:     {regime_parts}")
    print(f"      |  Grade:         {_grade_symbol(ar.grade)}")
    if show_sub_scores and ar.sub_scores:
        print(f"      |  Sub-scores:")
        _print_sub_scores(ar.sub_scores, indent=9)
    print(f"      +" + "-" * 60)


def _print_verdict_table(verdict_acc: dict) -> None:
    if not verdict_acc:
        return
    print(f"\n   Verdict Accuracy:")
    print(f"   {'Verdict':<15} {'Calls':>7} {'Correct':>8} {'Precision':>10}  Actual distribution")
    print(f"   {'-'*70}")
    for verdict in ["STRONG BUY", "BUY", "NEUTRAL", "SELL", "STRONG SELL", "UNKNOWN"]:
        if verdict not in verdict_acc:
            continue
        va = verdict_acc[verdict]
        dist = " | ".join(f"{k}:{v}" for k, v in sorted(va.actual_distribution.items()))
        print(f"   {verdict:<15} {va.total_calls:>7} {va.correct_calls:>8} {va.precision:>10.1%}  {dist}")


def _print_ticker_table(tickers: dict) -> None:
    if not tickers:
        return
    print(f"\n   Ticker Accuracy:")
    print(f"   {'Ticker':<15} {'Days':>6} {'Hits':>6} {'HitRate':>9} {'AvgErr%':>9}  Most blamed agent")
    print(f"   {'-'*70}")
    for ticker, ts in sorted(tickers.items(), key=lambda x: -x[1].direction_hit_rate):
        print(f"   {ticker:<15} {ts.total_days:>6} {ts.direction_hits:>6} {ts.direction_hit_rate:>9.1%} {ts.avg_price_error_pct:>9.2f}  {ts.most_blamed_agent}")


def print_report(report: EvalReport, verbose: bool = True) -> None:
    """Pretty-print the full evaluation report to stdout."""
    print()
    print(_sep("="))
    print(f"  STOCKAGENT MODEL EVALUATION  --  {report.eval_date}")
    print(_sep("="))

    if report.warnings:
        print("\n!  WARNINGS:")
        for w in report.warnings:
            print(f"   * {w}")

    # ── Overall summary ───────────────────────────────────────────────────
    ov = report.overall
    if ov:
        print(f"\n{'-'*40}  OVERALL  {'-'*40}")
        print(f"  Total predictions:      {ov.total_predictions}")
        print(f"  Direction hit rate:     {_bar(ov.overall_direction_hit_rate)}")
        print(f"  Avg price error:        {ov.overall_avg_price_error_pct:.2f}%")
        print(f"  Best sector:            {ov.best_sector or 'N/A'}")
        print(f"  Worst sector:           {ov.worst_sector or 'N/A'}")
        print(f"  Best agent (global):    {ov.best_agent_global or 'N/A'}")
        print(f"  Worst agent (global):   {ov.worst_agent_global or 'N/A'}")
        if ov.most_reliable_sub_score:
            print(f"  Most reliable score:    {ov.most_reliable_sub_score}")
        if ov.least_reliable_sub_score:
            print(f"  Least reliable score:   {ov.least_reliable_sub_score}")

    # ── Sector summaries ─────────────────────────────────────────────────
    print(f"\n{'-'*37}  BY SECTOR  {'-'*37}")
    print(f"  {'Sector':<20} {'Preds':>6} {'HitRate':>9} {'AvgErr%':>8} {'Conflicts':>10} {'Grade':>8}")
    print(f"  {'-'*72}")
    for sector, sr in sorted(report.sectors.items()):
        if sr.total_predictions == 0:
            print(f"  {sector:<20}       (no data)")
            continue
        print(
            f"  {sector:<20} {sr.total_predictions:>6} {sr.direction_hit_rate:>9.1%} "
            f"{sr.avg_price_error_pct:>8.2f} {sr.conflict_rate:>10.1%} "
            f"  {_grade_symbol(sr.grade)}"
        )

    # ── Per-sector detail ─────────────────────────────────────────────────
    for sector, sr in sorted(report.sectors.items()):
        if sr.total_predictions == 0:
            continue
        print(_sep("="))
        print(f"  SECTOR: {sector.upper()}")
        print(f"  {sr.total_predictions} predictions  |  hit rate {sr.direction_hit_rate:.1%}  |  grade {_grade_symbol(sr.grade)}")
        print(f"  best agent: {sr.best_agent}   worst agent: {sr.worst_agent}")
        print(_sep())

        _print_verdict_table(sr.verdict_accuracy)

        if verbose:
            _print_calibration(sr.final_score_calibration, "  Final score calibration", indent=3)

        # -- Per-agent detail
        print(f"\n   {'-'*40}  AGENTS  {'-'*40}")
        for agent_name, ar in sorted(sr.agents.items(), key=lambda x: -x[1].direction_hit_rate):
            _print_agent(ar, show_sub_scores=verbose)

        _print_ticker_table(sr.tickers)

    print()
    print(_sep("="))
    print(f"  Report saved to: eval/reports/eval_{report.eval_date}.json")
    print(_sep("="))
    print()


# ─────────────────────────────────────────────────────────────────────────────
# Compare two saved reports
# ─────────────────────────────────────────────────────────────────────────────

def _delta_str(before: float, after: float, pct: bool = True) -> str:
    delta = after - before
    symbol = "^" if delta > 0.001 else ("v" if delta < -0.001 else "~")
    if pct:
        return f"{before:.1%} -> {after:.1%}  {symbol}{abs(delta):.1%}"
    return f"{before:.4f} -> {after:.4f}  {symbol}{abs(delta):.4f}"


def _change_icon(delta: float, threshold: float = 0.01) -> str:
    if delta > threshold:
        return "&#x25B2; Better"
    if delta < -threshold:
        return "&#x25BC; Worse"
    return "&#x2014; Same"


def _save_comparison_md(doc: dict, md_path: Path) -> None:
    """Render a comparison doc dict as a human-readable Markdown report."""
    lines: list[str] = []

    before_date = doc.get("before_date", "?")
    after_date  = doc.get("after_date",  "?")
    before_file = Path(doc.get("before_report", "before.json")).name
    after_file  = Path(doc.get("after_report",  "after.json")).name

    lines += [
        f"# StockAgent Eval Comparison Report",
        f"",
        f"| | Value |",
        f"|---|---|",
        f"| **Before** | `{before_file}` ({before_date}) |",
        f"| **After**  | `{after_file}` ({after_date}) |",
        f"",
    ]

    # ── Overall ──────────────────────────────────────────────────────────
    ov = doc.get("overall", {})
    if ov:
        bhr = ov.get("before_hit_rate", 0.0)
        ahr = ov.get("after_hit_rate",  0.0)
        dhr = ov.get("delta_hit_rate",  0.0)
        bpe = ov.get("before_price_error", 0.0)
        ape = ov.get("after_price_error",  0.0)
        dpe = ov.get("delta_price_error",  0.0)
        lines += [
            "## Overall",
            "",
            "| Metric | Before | After | Delta | Verdict |",
            "|--------|-------:|------:|------:|---------|",
            f"| Direction Hit Rate | {bhr:.1%} | {ahr:.1%} | {dhr:+.1%} | {_change_icon(dhr)} |",
            f"| Avg Price Error    | {bpe:.4f}% | {ape:.4f}% | {dpe:+.4f}% | {_change_icon(-dpe)} |",
            "",
        ]

    # ── Sectors ──────────────────────────────────────────────────────────
    sectors = doc.get("sectors", [])
    if sectors:
        lines += [
            "## By Sector",
            "",
            "| Sector | Before HR | After HR | Delta | Verdict |",
            "|--------|----------:|---------:|------:|---------|",
        ]
        for row in sectors:
            delta = row.get("delta", 0.0)
            lines.append(
                f"| {row['sector']} "
                f"| {row['before_hit_rate']:.1%} "
                f"| {row['after_hit_rate']:.1%} "
                f"| {delta:+.1%} "
                f"| {_change_icon(delta)} |"
            )
        lines.append("")

    # ── Agents grouped by sector ──────────────────────────────────────────
    agents = doc.get("agents", [])
    if agents:
        lines.append("## By Agent")
        lines.append("")
        # group
        from collections import defaultdict
        by_sector: dict[str, list[dict]] = defaultdict(list)
        for row in agents:
            by_sector[row["sector"]].append(row)

        for sector, rows in sorted(by_sector.items()):
            lines += [
                f"### {sector.replace('_', ' ').title()}",
                "",
                "| Agent | Before HR | After HR | Delta | Verdict |",
                "|-------|----------:|---------:|------:|---------|",
            ]
            for row in rows:
                delta = row.get("delta", 0.0)
                lines.append(
                    f"| {row['agent']} "
                    f"| {row['before_hit_rate']:.1%} "
                    f"| {row['after_hit_rate']:.1%} "
                    f"| {delta:+.1%} "
                    f"| {_change_icon(delta)} |"
                )
            lines.append("")

    # ── Legend ────────────────────────────────────────────────────────────
    lines += [
        "---",
        "",
        "**Legend**",
        "",
        "- &#x25B2; Better &mdash; hit rate improved by > 1 pp",
        "- &#x25BC; Worse &mdash; hit rate dropped by > 1 pp",
        "- &#x2014; Same &mdash; change within +/- 1 pp",
        "",
        "> Hit Rate = fraction of direction predictions (up/down) that matched actual outcome.",
        "> Lower price error is better; its verdict is inverted accordingly.",
        "",
    ]

    md_path.parent.mkdir(parents=True, exist_ok=True)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def print_comparison(before_path: Path, after_path: Path, output_path: Path | None = None) -> None:
    """Diff two EvalReport JSON files and show what improved/degraded."""
    def _load(p: Path) -> EvalReport:
        with open(p, encoding="utf-8") as f:
            return EvalReport.model_validate(json.load(f))

    before = _load(before_path)
    after  = _load(after_path)

    print()
    print(_sep("="))
    print(f"  COMPARISON: {before.eval_date}  ->  {after.eval_date}")
    print(_sep("="))

    bov, aov = before.overall, after.overall

    overall_delta: dict = {}
    if bov and aov:
        print(f"\n  Overall hit rate:   {_delta_str(bov.overall_direction_hit_rate, aov.overall_direction_hit_rate)}")
        print(f"  Avg price error:    {_delta_str(bov.overall_avg_price_error_pct, aov.overall_avg_price_error_pct, pct=False)}%")
        overall_delta = {
            "before_hit_rate": bov.overall_direction_hit_rate,
            "after_hit_rate":  aov.overall_direction_hit_rate,
            "delta_hit_rate":  aov.overall_direction_hit_rate - bov.overall_direction_hit_rate,
            "before_price_error": bov.overall_avg_price_error_pct,
            "after_price_error":  aov.overall_avg_price_error_pct,
            "delta_price_error":  aov.overall_avg_price_error_pct - bov.overall_avg_price_error_pct,
        }

    print(f"\n  {'Sector':<20} {'Before HR':>10} {'After HR':>10} {'Delta':>10} {'Change'}")
    print(f"  {'-'*64}")
    sector_rows: list[dict] = []
    for sector in sorted(set(before.sectors) | set(after.sectors)):
        bsr = before.sectors.get(sector)
        asr = after.sectors.get(sector)
        if bsr is None or asr is None or bsr.total_predictions == 0 or asr.total_predictions == 0:
            continue
        delta = asr.direction_hit_rate - bsr.direction_hit_rate
        symbol = "^ BETTER" if delta > 0.01 else ("v WORSE" if delta < -0.01 else "~ same")
        print(f"  {sector:<20} {bsr.direction_hit_rate:>10.1%} {asr.direction_hit_rate:>10.1%} {delta:>+10.1%}  {symbol}")
        sector_rows.append({
            "sector": sector,
            "before_hit_rate": bsr.direction_hit_rate,
            "after_hit_rate":  asr.direction_hit_rate,
            "delta":           delta,
            "change":          symbol,
        })

    # Agent-level diff
    print(f"\n  {'Agent (sector)':<35} {'Before HR':>10} {'After HR':>10} {'Delta':>10}")
    print(f"  {'-'*70}")
    agent_rows: list[dict] = []
    for sector in sorted(set(before.sectors) | set(after.sectors)):
        bsr = before.sectors.get(sector)
        asr = after.sectors.get(sector)
        if bsr is None or asr is None:
            continue
        for agent in sorted(set(bsr.agents) | set(asr.agents)):
            bar = bsr.agents.get(agent)
            aar = asr.agents.get(agent)
            if bar is None or aar is None:
                continue
            if bar.total_evaluated < 5 and aar.total_evaluated < 5:
                continue
            delta = aar.direction_hit_rate - bar.direction_hit_rate
            symbol = "^" if delta > 0.01 else ("v" if delta < -0.01 else "~")
            label = f"{agent} ({sector})"
            print(f"  {label:<35} {bar.direction_hit_rate:>10.1%} {aar.direction_hit_rate:>10.1%} {delta:>+10.1%}  {symbol}")
            agent_rows.append({
                "agent":           agent,
                "sector":          sector,
                "before_hit_rate": bar.direction_hit_rate,
                "after_hit_rate":  aar.direction_hit_rate,
                "delta":           delta,
                "change":          symbol,
            })
    print()

    # ── Save comparison JSON + Markdown if requested ──────────────────────
    if output_path is not None:
        comparison_doc = {
            "before_report": str(before_path),
            "after_report":  str(after_path),
            "before_date":   before.eval_date,
            "after_date":    after.eval_date,
            "overall":       overall_delta,
            "sectors":       sector_rows,
            "agents":        agent_rows,
        }
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(comparison_doc, f, indent=2, ensure_ascii=False)
        sys.stderr.write(f"\nComparison saved: {output_path}\n")

        md_path = output_path.with_suffix(".md")
        _save_comparison_md(comparison_doc, md_path)
        sys.stderr.write(f"Markdown saved:   {md_path}\n")


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="StockAgent model accuracy evaluator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python eval/evaluate.py
  python eval/evaluate.py --sector automobile
  python eval/evaluate.py --output eval/reports/baseline.json
  python eval/evaluate.py --compare eval/reports/before.json eval/reports/after.json
  python eval/evaluate.py --json-only
""",
    )
    parser.add_argument("--sector",    help="Evaluate only this sector", default=None)
    parser.add_argument("--output",    help="Path to save JSON report", default=None)
    parser.add_argument("--compare",   help="Compare two saved JSON reports", nargs=2, metavar=("BEFORE", "AFTER"))
    parser.add_argument("--json-only", help="Print JSON to stdout only (no table)", action="store_true")
    parser.add_argument("--no-sub-scores", help="Skip sub-score detail in console output", action="store_true")
    args = parser.parse_args()

    # ── Compare mode ──────────────────────────────────────────────────────
    if args.compare:
        out = Path(args.output) if args.output else None
        print_comparison(Path(args.compare[0]), Path(args.compare[1]), output_path=out)
        return

    # ── Evaluation mode ───────────────────────────────────────────────────
    target_sectors = [args.sector] if args.sector else None

    report = build_eval_report(
        base_dir=_ROOT,
        target_sectors=target_sectors,
    )

    # Determine output path
    reports_dir = _ROOT / "eval" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    output_path = Path(args.output) if args.output else reports_dir / f"eval_{report.eval_date}.json"

    # Save JSON
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report.model_dump(), f, indent=2, ensure_ascii=False)

    if args.json_only:
        print(json.dumps(report.model_dump(), indent=2, ensure_ascii=False))
    else:
        print_report(report, verbose=not args.no_sub_scores)

    # Always print the JSON path for scripting
    if not args.json_only:
        sys.stderr.write(f"\nJSON saved: {output_path}\n")


if __name__ == "__main__":
    main()
