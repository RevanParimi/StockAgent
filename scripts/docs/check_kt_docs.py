"""Check current KT links, PI coverage, job IDs, config claims, header revision
and PDF freshness.

Read-only source/document inspection. No application imports or transports;
the only subprocess is local read-only `git`, used to check the KT header's
declared revision. Requires pypdf and PyYAML (available in the local
validation environment).

The KT digest is SHA-256 over LF-normalized bytes, as in build_kt_pdf.py, so a
CRLF Windows checkout and an LF Linux checkout agree on PDF freshness. It
equals the committed blob only when git stores the file with LF, which is true
of TECHNICAL_DESIGN.md but not of every older file. Review manifests record
git's actual blob instead; see kt_manifest.py.
"""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path, PurePosixPath
import posixpath
import re
import subprocess
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
    "docs/planning/PI-2026-09/evidence/DOC-001-review.md",
]
LINK = r"\[[^\]\n]+\]\(([^)]+)\)"


def canonical_sha256(path: Path) -> str:
    """SHA-256 of the file with CRLF normalized to LF (checkout-independent)."""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)


def check_header_revision(kt: str, documented_jobs: list[str], errors: list[str]) -> dict:
    """The KT header must name the revision its body describes.

    Fails when the declared revision is unknown, is not an ancestor of HEAD,
    postdates the edition, or lacks any source file the KT links to or any job
    ID the scheduler table documents -- i.e. the body describes code the
    declared revision does not contain. Linked sources that changed after the
    revision are reported, not failed: per-commit churn is expected, and the
    list tells the maintainer which sections to re-read before bumping it.
    """
    rev_match = re.search(r"\*\*Code inspected:\*\* `([0-9a-f]{40})`", kt)
    edition_match = re.search(r"\*\*Edition:\*\* (\d{4}-\d{2}-\d{2})", kt)
    if not rev_match or not edition_match:
        errors.append("KT header lacks an Edition date or a full 40-character Code inspected revision")
        return {}
    rev, edition = rev_match.group(1), edition_match.group(1)
    if _git("cat-file", "-e", rev + "^{commit}").returncode:
        errors.append("KT header revision is not a known commit: " + rev)
        return {"declared_revision": rev}
    if _git("merge-base", "--is-ancestor", rev, "HEAD").returncode:
        errors.append("KT header revision is not an ancestor of HEAD: " + rev)
    committed = _git("show", "-s", "--format=%cs", rev).stdout.strip()
    if edition < committed:
        errors.append(f"KT edition {edition} predates its declared revision's commit date {committed}")
    tracked = _git("ls-tree", "-r", "--name-only", rev).stdout.splitlines()
    tracked_set = set(tracked)
    tracked_dirs = {str(PurePosixPath(p).parent) for p in tracked}
    sources = set()
    for href in re.findall(LINK, kt):
        href = href.strip("<>")
        target = unquote(href.split("#", 1)[0])
        if not target or re.match(r"^[a-zA-Z]+:", href):
            continue
        rel = posixpath.normpath(posixpath.join("docs", target))
        if rel.startswith("docs/") or rel.startswith(".."):
            continue  # documentation is maintained alongside; only source must exist at the revision
        sources.add(rel.rstrip("/"))
    for rel in sorted(sources):
        if rel not in tracked_set and rel not in tracked_dirs:
            errors.append(f"KT links {rel}, which is absent at its declared revision {rev[:12]}")
    scheduler = _git("show", f"{rev}:services/scheduler/python/scheduler.py").stdout
    for job in documented_jobs:
        needle = "ipo_refresh_" if job.startswith("ipo_refresh_") else job
        if needle not in scheduler:
            errors.append(f"KT documents job {job}, which is absent at its declared revision {rev[:12]}")
    changed = _git("diff", "--name-only", rev, "HEAD", "--", *sorted(sources)).stdout.split()
    return {"declared_revision": rev, "edition": edition, "linked_sources": len(sources),
            "linked_sources_changed_since_revision": changed}


def main() -> None:
    errors: list[str] = []
    links = 0
    for name in DOCS:
        path = ROOT / name
        if not path.is_file():
            errors.append("Missing document: " + name)
            continue
        source = path.read_text(encoding="utf-8-sig")
        for href in re.findall(LINK, source):
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
    header = check_header_revision(kt, documented, errors)

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
    digest = canonical_sha256(kt_path)
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
               "source_sha256": digest, "header": header, "errors": errors}
    out = ROOT / "analysis_data/kt_20260915"
    out.mkdir(parents=True, exist_ok=True)
    (out / "doc_checks.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
