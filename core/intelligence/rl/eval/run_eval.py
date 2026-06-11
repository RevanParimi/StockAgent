"""
core/intelligence/rl/eval/run_eval.py
======================================
CLI entry point for the RL Evaluation Harness (Component 1).

Usage
-----
    python -m core.intelligence.rl.eval.run_eval --synthetic
    python -m core.intelligence.rl.eval.run_eval                       # real data
    python -m core.intelligence.rl.eval.run_eval --synthetic --ablate calibration_reward forgetting

Writes a machine-readable report to `outputs/eval/{YYYY-MM-DD}_report.json`
and prints a human-readable summary table to stdout. Read-only: never writes
to `data/predictions`.
"""
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from core.intelligence.rl.eval.harness import EvalHarness, EvalReport

# Project-root-relative output directory.
_OUTPUT_DIR = Path(__file__).resolve().parents[4] / "outputs" / "eval"


def _format_pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def _print_metrics_block(title: str, metrics: dict) -> None:
    print(f"\n{title}")
    print(f"  n_entries          : {metrics['n_entries']}")
    print(f"  direction_accuracy : {_format_pct(metrics['direction_accuracy'])}")
    print(f"  brier_score        : {metrics['brier_score']:.4f}")
    print(f"  band_coverage      : {_format_pct(metrics['band_coverage'])}")
    print(f"  mae_pct            : {metrics['mae_pct']:.4f}%")
    reliability = metrics.get("reliability_table") or {}
    if reliability:
        print("  reliability_table  :")
        for bucket, stats in sorted(reliability.items()):
            print(
                f"    {bucket:>9} -> n={stats['n']:>3}  "
                f"hit_rate={_format_pct(stats['hit_rate']):>7}  "
                f"avg_confidence={stats['avg_confidence']:.3f}"
            )


def print_report(report: EvalReport) -> None:
    print("=" * 70)
    print("RL Evaluation Harness Report")
    print("=" * 70)
    print(f"source       : {report.source}")
    print(f"generated_at : {report.generated_at}")
    print(f"n_entries    : {report.n_entries}")

    _print_metrics_block("AGGREGATE", report.aggregate)

    if report.per_sector:
        print("\nPER-SECTOR")
        for sector, metrics in sorted(report.per_sector.items()):
            _print_metrics_block(f"  [{sector}]", metrics)

    if report.per_ticker:
        print("\nPER-TICKER")
        for ticker, metrics in sorted(report.per_ticker.items()):
            _print_metrics_block(f"  [{ticker}]", metrics)

    if report.ablations_run:
        print("\nABLATIONS")
        for key in report.ablations_run:
            delta = report.ablation_deltas.get(key)
            if delta is None:
                print(f"  {key}: no-op (real data — recorded history cannot be re-run)")
            else:
                print(
                    f"  {key}: direction_accuracy_delta="
                    f"{delta['direction_accuracy_delta']:+.4f}  "
                    f"brier_score_delta={delta['brier_score_delta']:+.4f}"
                )
    print("=" * 70)


def write_report(report: EvalReport, output_dir: Path | None = None) -> Path:
    out_dir = output_dir or _OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{date.today().isoformat()}_report.json"
    out_path.write_text(
        json.dumps(report.model_dump(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="RL Evaluation Harness — replay prediction/feedback history and emit metrics."
    )
    parser.add_argument(
        "--synthetic", action="store_true",
        help="Use SyntheticLogGenerator instead of real data/predictions logs.",
    )
    parser.add_argument(
        "--ablate", nargs="*", default=None,
        help="Ablation keys (e.g. calibration_reward forgetting). "
             "Synthetic runs report a delta; real runs are a logged no-op.",
    )
    parser.add_argument("--n-tickers", type=int, default=4, help="Synthetic only.")
    parser.add_argument("--n-cycles", type=int, default=1, help="Synthetic only.")
    parser.add_argument("--accuracy-rate", type=float, default=0.6, help="Synthetic only.")
    parser.add_argument("--vol", type=float, default=1.0, help="Synthetic only.")
    parser.add_argument("--seed", type=int, default=42, help="Synthetic only.")
    args = parser.parse_args()

    harness = EvalHarness()
    report = harness.run_eval(
        synthetic=args.synthetic,
        ablate=args.ablate,
        n_tickers=args.n_tickers,
        n_cycles=args.n_cycles,
        accuracy_rate=args.accuracy_rate,
        vol=args.vol,
        seed=args.seed,
    )

    print_report(report)
    out_path = write_report(report)
    print(f"\nReport written to {out_path}")


if __name__ == "__main__":
    main()
