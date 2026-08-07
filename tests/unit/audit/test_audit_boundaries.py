"""The auditor must not import the components it grades.

Static source scan, not a runtime module-graph check: core.portfolio.pricing
imports daily_review, which imports feedback_agent and weight_adapter at
module level, so ANY use of close_on transitively loads the agents. That is
unavoidable without duplicating price code. The meaningful invariant is that
the auditor's own source never names them.
"""
from pathlib import Path

FORBIDDEN = ("core.intelligence.rl.agents", "core.portfolio.advisor")

AUDIT_DIR = Path(__file__).resolve().parents[3] / "core" / "audit"


def test_audit_package_exists():
    assert AUDIT_DIR.is_dir(), f"expected package at {AUDIT_DIR}"


def test_no_forbidden_imports_in_audit_sources():
    offenders = []
    for py in sorted(AUDIT_DIR.rglob("*.py")):
        text = py.read_text(encoding="utf-8")
        for line in text.splitlines():
            stripped = line.strip()
            if not (stripped.startswith("import ") or stripped.startswith("from ")):
                continue
            for banned in FORBIDDEN:
                if banned in stripped:
                    offenders.append(f"{py.name}: {stripped}")
    assert offenders == [], (
        "core/audit must not import the components it grades: " + "; ".join(offenders)
    )
