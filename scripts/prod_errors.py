"""Print the durable-error backlog (SA-011), or triage one issue.

Remote, with the app's own credentials only (no Railway CLI):
    STOCKAGENT_TOKEN=<owner session> python scripts/prod_errors.py --base https://<host>
    SCHEDULER_KEY=<key>             python scripts/prod_errors.py --base https://<host> --json
    python scripts/prod_errors.py --base https://<host> --triage <fp> --status fixed --task SA-016
    python scripts/prod_errors.py --base https://<host> --triage <fp> --status fixed \
        --fixed-at 2026-10-05T08:00+05:30          # the fix took effect then (IST)

Offline, on copies (nothing is written to the source; the registry is in memory):
    python scripts/prod_errors.py --db path/to/telemetry.db
    python scripts/prod_errors.py --railway-json export.jsonl   # `railway logs --json` output

A remote read folds new app_logs rows into the production registry first:
that is the endpoint's normal behaviour, not a side effect of this script.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path[:0] = [str(Path(__file__).resolve().parents[1]),
                str(Path(__file__).resolve().parents[1] / "src")]


def _headers() -> dict:
    headers = {"Accept": "application/json"}
    if os.getenv("STOCKAGENT_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['STOCKAGENT_TOKEN']}"
    if os.getenv("SCHEDULER_KEY"):
        headers["X-Scheduler-Key"] = os.environ["SCHEDULER_KEY"]
    return headers


def _request(url: str, body: dict | None = None) -> str:
    data = None if body is None else json.dumps(body).encode("utf-8")
    headers = _headers() | ({"Content-Type": "application/json"} if data else {})
    req = urllib.request.Request(url, data=data, headers=headers,
                                 method="POST" if data else "GET")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"HTTP {exc.code}: {exc.read().decode('utf-8', 'replace')[:300]}")


def _offline(args) -> str:
    from core.ops import error_backlog as eb
    p = eb.params()
    now = datetime.now(timezone.utc)
    reg = eb.open_registry(":memory:")
    if args.db:
        src = sqlite3.connect(f"file:{Path(args.db).resolve().as_posix()}?mode=ro", uri=True)
        from dataclasses import replace
        eb.refresh(reg, source_conn=src, p=replace(p, max_rows_per_refresh=10**9), now=now)
        header = ""
    else:
        lines = Path(args.railway_json).read_text(encoding="utf-8", errors="replace").splitlines()
        occs, stats = eb.railway_occurrences(lines)
        reg.execute("BEGIN IMMEDIATE")
        eb.ingest(reg, occs, p)
        reg.execute("COMMIT")
        header = ("Railway export, by the app's own level: "
                  + ", ".join(f"{k} {v}" for k, v in stats.items()) + "\n\n")
    if args.json:
        rows = [eb.public_issue(i, eb.classify(i, now, eb.coverage(reg), p))
                for i in eb.issues(reg)]
        return json.dumps(rows, indent=2, sort_keys=True)
    return header + eb.build_digest(eb.issues(reg), now, eb.coverage(reg), p)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--base", help="the app's base URL")
    src.add_argument("--db", help="a local copy of telemetry.db (read only)")
    src.add_argument("--railway-json", help="a `railway logs --json` export")
    ap.add_argument("--json", action="store_true", help="ranked issues as JSON")
    ap.add_argument("--include", choices=("attention", "active", "all"), default="active")
    ap.add_argument("--triage", metavar="FINGERPRINT")
    ap.add_argument("--status", choices=("open", "acknowledged", "fixed", "wontfix"))
    ap.add_argument("--assignee")
    ap.add_argument("--task")
    ap.add_argument("--note")
    ap.add_argument("--fixed-at", help="with --status fixed: when the fix took effect, with its "
                    "UTC offset, e.g. 2026-10-05T08:00+05:30 (IST); a time without one is "
                    "refused. Default: now")
    args = ap.parse_args(argv)

    if not args.base:
        if args.triage:
            ap.error("--triage needs --base: offline registries are not kept")
        print(_offline(args))
        return 0
    base = args.base.rstrip("/")
    if args.triage:
        body = {k: v for k, v in (("status", args.status), ("assignee", args.assignee),
                                  ("task", args.task), ("note", args.note),
                                  ("fixed_at", args.fixed_at)) if v is not None}
        print(_request(f"{base}/ops/errors/{args.triage}", body))
    elif args.json:
        print(_request(f"{base}/ops/errors?include={args.include}"))
    else:
        print(_request(f"{base}/ops/errors/digest"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
