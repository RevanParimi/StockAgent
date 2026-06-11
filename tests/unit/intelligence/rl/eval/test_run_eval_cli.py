"""
CLI smoke tests for core/intelligence/rl/eval/run_eval.py

Verifies the module is invocable as `python -m core.intelligence.rl.eval.run_eval`,
prints a summary table, and writes outputs/eval/{date}_report.json.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[5]


def test_cli_synthetic_smoke(tmp_path, monkeypatch):
    """Run the CLI module directly and verify stdout + JSON report."""
    env = {
        **__import__("os").environ,
        "PYTHONPATH": f"{PROJECT_ROOT}{__import__('os').pathsep}{PROJECT_ROOT / 'src'}",
    }

    result = subprocess.run(
        [sys.executable, "-m", "core.intelligence.rl.eval.run_eval", "--synthetic",
         "--n-tickers", "2", "--n-cycles", "1"],
        cwd=str(PROJECT_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert result.returncode == 0, result.stderr
    assert "RL Evaluation Harness Report" in result.stdout
    assert "AGGREGATE" in result.stdout
    assert "direction_accuracy" in result.stdout
    assert "Report written to" in result.stdout

    report_path = PROJECT_ROOT / "outputs" / "eval" / f"{date.today().isoformat()}_report.json"
    assert report_path.exists()

    data = json.loads(report_path.read_text(encoding="utf-8"))
    assert data["source"] == "synthetic"
    assert data["n_entries"] > 0
    assert "direction_accuracy" in data["aggregate"]
