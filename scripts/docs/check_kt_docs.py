"""Check current KT links, PI coverage, job IDs, config claims and PDF freshness.

Read-only source/document inspection. No application imports or transports.
Requires pypdf and PyYAML (available in the local validation environment).
"""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import unquote

from pypdf import PdfReader
import yaml

ROOT = Path(__file__).resolve().parents[2]
DOCS = [
    "docs/TECHNICAL_DESIGN.md", "docs/ARCHITECTURE.md", "docs/TEAM_TESTING_GUIDE.md",
    "docs/README.md", "docs/archive/README.md", "docs/planning/PI-2026-09/README.md",
    "docs/planning/PI-2026-09/HANDOFF.md", "docs/planning/PI-2026-09/REVIEW.md",
    "docs/planning/PI-2026-09/stories/DOC-001.md", "docs/planning/PI-2026-09/stories/SA-031.md",
    "docs/planning/PI-2026-09/evidence/README.md",
    "docs/planning/PI-2026-09/evidence/DOC-001-implementation.md",
]


def main() -> None:
    errors: list[str] = []
    links = 0
    for name in DOCS:
        path = ROOT / name
        if not path.is_file():
            errors.append("Missing document: " + name)
            continue
        source = path.read_text(encoding="utf-8-sig")
        for href in re.findall(r"\[[^\]\n]+\]\(([^)]+)\)", source):
            href = href.strip("<>")
            if re.match(r"^[a-zA-Z]+:", href):
                continue
            target = unquote(href.split("#", 1)[0])
            if target:
                links += 1
                if not (path.parent / target).exists():
                    errors.append(f"Broken link in {name}: {target}")
    kt_path = ROOT / DOCS[0]
    kt = kt_path.read_text(encoding="utf-8")
    state = json.loads((ROOT / "docs/planning/PI-2026-09/STATE.json").read_text(encoding="utf-8"))
    sa = [t for t in state["tasks"] if t["id"].startswith("SA-")]
    for task in sa:
        row = next((line for line in kt.splitlines() if line.startswith(f"| [{task['id']}")), None)
        if row is None:
            errors.append("Missing PI row: " + task["id"])
        elif any(dep not in row for dep in task["depends_on"]):
            errors.append("PI dependency mismatch: " + task["id"])
        elif task["title"] not in row:
            errors.append("PI title mismatch: " + task["id"])
    if "Every SA story remains" in kt and "`todo`" in kt:
        if any(t["status"] != "todo" for t in sa):
            errors.append("KT's all-todo status is stale; update it for accepted story progress")

    scheduler_path = ROOT / "services/scheduler/python/scheduler.py"
    tree = ast.parse(scheduler_path.read_text(encoding="utf-8"))
    jobs = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "add_job":
            kw = {k.arg: k.value for k in node.keywords}
            ident = kw.get("id")
            if isinstance(ident, ast.Constant):
                jobs.append(ident.value)
            elif isinstance(ident, ast.JoinedStr):
                # The source loop currently has two IPO slots, am and pm.
                if ast.unparse(ident) != "f'ipo_refresh_{slot}'":
                    errors.append("New dynamic job ID requires inventory review")
                jobs.extend(["ipo_refresh_am", "ipo_refresh_pm"])
    clock = kt.split("## 9.", 1)[1].split("## 10.", 1)[0]
    documented = re.findall(r"^\| `([^`]+)` \|", clock, re.M)
    if set(jobs) != set(documented) or len(jobs) != len(documented):
        errors.append("Scheduler job inventory differs from KT table")
    if f"**{len(jobs)} possible job IDs**" not in clock:
        errors.append("Scheduler count in KT is stale")

    config = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    claims = {"scheduler.enabled": False, "scheduler.feedback_cron": "30 16 * * mon-fri",
              "rl.hard_bind_verdict_enabled": True, "rl.control_lane_enabled": True,
              "rl.scorecard_enabled": True, "ipo.enabled": True, "ipo.gmp_enabled": False,
              "delivery.enabled": True, "delivery.email_enabled": False, "delivery.push_enabled": True,
              "watchdog.enabled": True, "watchdog.prep_enabled": True, "audit.enabled": True}
    for key, expected in claims.items():
        actual = config
        for part in key.split("."):
            actual = actual.get(part) if isinstance(actual, dict) else None
        if actual != expected:
            errors.append("Documented repository config needs review: " + key)

    pdf_path = ROOT / "docs/StockAgent-Three-Loops.pdf"
    pdf = PdfReader(pdf_path)
    texts = [p.extract_text() or "" for p in pdf.pages]
    text = "\n".join(texts)
    compact = re.sub(r"\s+", "", text)
    digest = hashlib.sha256(kt_path.read_bytes()).hexdigest()
    if digest[:12] not in compact:
        errors.append("PDF source digest does not match current Markdown")
    for title in re.findall(r"^## (.+)$", kt, re.M):
        if re.sub(r"\s+", "", title) not in compact:
            errors.append("PDF missing chapter: " + title)
    for task in sa:
        if task["id"] not in text:
            errors.append("PDF missing PI story: " + task["id"])
    if any(len(t.strip()) < 40 for t in texts):
        errors.append("PDF contains an empty or nearly-empty page")
    if "C:\\Users\\" in text or "file:///" in text:
        errors.append("PDF exposes a local filesystem path")
    original = ROOT / "docs/archive/StockAgent-Three-Loops.original-before-2026-09-15.pdf"
    if hashlib.sha256(original.read_bytes()).hexdigest() != "1fc2402b6bdda4ac088630e1f1caf8d10f89799409dd9e0eff559ab3df4f66d9":
        errors.append("Original PDF archive changed")
    summary = {"documents": len(DOCS), "local_links_checked": links, "pi_stories": len(sa),
               "scheduler_job_ids": len(jobs), "configuration_claims": len(claims),
               "pdf_pages": len(pdf.pages), "pdf_text_characters": len(text),
               "source_sha256": digest, "errors": errors}
    out = ROOT / "analysis_data/kt_20260915"
    out.mkdir(parents=True, exist_ok=True)
    (out / "doc_checks.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
