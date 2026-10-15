"""One-time backfill of the score history from the analysis run log (FIX-010).

From 21 Apr 2026 (ce1eeb5) until FIX-010, no analysis wrote the score history,
while every analysis was still logged in telemetry.db's `run_summaries`. This
copies those logged runs into `score_history`, so Home's scores and Portfolio's
verdict changes cover the past instead of starting empty.

It runs ONLY at the owner's explicit word, at rollout. It is a production data
write: the default mode is a dry run that prints counts and writes nothing.

    Mode (env SCORE_BACKFILL, or the first argument): dry-run (default) | apply | remove
    Paths: settings.SCORE_DB_PATH and settings.TELEMETRY_DB_PATH, or env
           SCORE_BACKFILL_SCORE_DB / SCORE_BACKFILL_TELEMETRY_DB (tests).

What a copied row holds: ticker, the run's time as run_at (naive UTC, the
format ScoreStore.save writes), final_score, verdict, company, and each agent's
score as {"raw": x}; thesis, drivers and risks empty; report_json carries the
marker {"backfill": "run_summaries", "run_id": ...}, so `remove` deletes
exactly these rows.

Rules:
- a run with no verdict or no score is skipped;
- nothing at or after a stock's first live (non-backfilled) row is copied, so
  a run is never recorded twice;
- a run already present (same stock and run_at) is skipped: a second apply
  adds nothing;
- a stock keeps at most SCORE_HISTORY_MAX_ROWS rows (the newest), as the
  store's own pruning does;
- `apply` and `remove` first copy the score database to
  <SCORE_DB_PATH>.bak-<UTC stamp> with SQLite's backup API.

Prints counts only (no tickers, verdicts, users or log lines). Production, from
Git Bash in the repo (dry run; add SCORE_BACKFILL=apply after `python`'s env to write):
    railway ssh "cd /app && echo $(gzip -9c scripts/backfill_score_history.py | base64 -w0) | base64 -d | python -c 'import sys,zlib;exec(zlib.decompress(sys.stdin.buffer.read(),31))'"
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from datetime import datetime, timezone

MARKER = "run_summaries"


def _paths() -> tuple[str, str, int]:
    score_db = os.environ.get("SCORE_BACKFILL_SCORE_DB")
    tele_db = os.environ.get("SCORE_BACKFILL_TELEMETRY_DB")
    max_rows = 90
    try:
        from core.config import settings
        score_db = score_db or settings.SCORE_DB_PATH
        tele_db = tele_db or getattr(settings, "TELEMETRY_DB_PATH", "data/telemetry.db")
        max_rows = int(settings.SCORE_HISTORY_MAX_ROWS)
    except ImportError:
        score_db = score_db or "data/scores.db"
        tele_db = tele_db or "data/telemetry.db"
    return score_db, tele_db, max_rows


def _naive_utc(ts: str) -> str | None:
    """'2026-10-15T11:16:23.5+00:00' -> '2026-10-15T11:16:23.500000' (ScoreStore's format)."""
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt.isoformat()


def _agent_scores(raw) -> str:
    try:
        scores = json.loads(raw) if raw else {}
    except ValueError:
        scores = {}
    out = {}
    for k, v in (scores.items() if isinstance(scores, dict) else []):
        try:
            out[str(k)] = {"raw": float(v)}
        except (TypeError, ValueError):
            continue
    return json.dumps(out)


def _is_backfilled(report_json: str | None) -> bool:
    try:
        return json.loads(report_json or "{}").get("backfill") == MARKER
    except (ValueError, AttributeError):
        return False


def plan(score_db: str, tele_db: str, max_rows: int) -> tuple[list[tuple], dict]:
    """The rows to insert and the counts, reading both databases only."""
    sc = sqlite3.connect(f"file:{os.path.abspath(score_db)}?mode=ro", uri=True)
    existing: set[tuple[str, str]] = set()
    live_first: dict[str, str] = {}
    kept: dict[str, int] = {}
    for ticker, run_at, report_json in sc.execute("SELECT ticker, run_at, report_json FROM score_history"):
        t = ticker.upper()
        existing.add((t, run_at))
        kept[t] = kept.get(t, 0) + 1
        if not _is_backfilled(report_json) and (t not in live_first or run_at < live_first[t]):
            live_first[t] = run_at
    sc.close()

    tc = sqlite3.connect(f"file:{os.path.abspath(tele_db)}?mode=ro", uri=True)
    runs = tc.execute("SELECT run_id, ts, ticker, company_name, final_score, verdict, agent_scores "
                      "FROM run_summaries ORDER BY ts").fetchall()
    tc.close()

    counts = {"runs_logged": len(runs), "skipped_no_verdict_or_score": 0, "skipped_bad_time": 0,
              "skipped_at_or_after_live_rows": 0, "skipped_already_present": 0, "skipped_over_cap": 0}
    by_ticker: dict[str, list[tuple]] = {}
    for run_id, ts, ticker, company, score, verdict, agents in runs:
        t = (ticker or "").strip().upper()
        if not t or score is None or not (verdict or "").strip():
            counts["skipped_no_verdict_or_score"] += 1
            continue
        run_at = _naive_utc(ts)
        if run_at is None:
            counts["skipped_bad_time"] += 1
            continue
        if t in live_first and run_at >= live_first[t]:
            counts["skipped_at_or_after_live_rows"] += 1
            continue
        if (t, run_at) in existing:
            counts["skipped_already_present"] += 1
            continue
        existing.add((t, run_at))
        by_ticker.setdefault(t, []).append((
            t, company or t, run_at, float(score), verdict.strip(), _agent_scores(agents), "", "[]", "[]",
            json.dumps({"backfill": MARKER, "run_id": run_id})))
    rows: list[tuple] = []
    for t, cands in by_ticker.items():
        room = max(0, max_rows - kept.get(t, 0))
        cands.sort(key=lambda r: r[2])
        take = cands[-room:] if room else []
        counts["skipped_over_cap"] += len(cands) - len(take)
        rows += take
    counts["would_insert"] = len(rows)
    counts["stocks"] = len({r[0] for r in rows})
    counts["oldest_run"] = min((r[2] for r in rows), default="")[:10]
    counts["newest_run"] = max((r[2] for r in rows), default="")[:10]
    return rows, counts


def _backup(score_db: str) -> str:
    dest = f"{score_db}.bak-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    src = sqlite3.connect(score_db)
    dst = sqlite3.connect(dest)
    with dst:
        src.backup(dst)
    dst.close()
    src.close()
    return dest


def run(mode: str) -> dict:
    score_db, tele_db, max_rows = _paths()
    if mode not in ("dry-run", "apply", "remove"):
        raise SystemExit(f"unknown mode {mode!r}: dry-run | apply | remove")
    if not os.path.exists(score_db) or not os.path.exists(tele_db):
        return {"mode": mode, "error": "score or telemetry database missing; nothing done"}
    if mode == "remove":
        backup = _backup(score_db)
        con = sqlite3.connect(score_db)
        ids = [i for i, rj in con.execute("SELECT id, report_json FROM score_history") if _is_backfilled(rj)]
        with con:
            con.executemany("DELETE FROM score_history WHERE id = ?", [(i,) for i in ids])
        con.close()
        return {"mode": mode, "removed": len(ids), "backup": os.path.basename(backup)}
    rows, counts = plan(score_db, tele_db, max_rows)
    counts["mode"] = mode
    if mode == "apply" and rows:
        counts["backup"] = os.path.basename(_backup(score_db))
        con = sqlite3.connect(score_db)
        with con:
            con.executemany(
                "INSERT INTO score_history (ticker, company_name, run_at, final_score, verdict, agent_scores, "
                "investment_thesis, conviction_drivers, top_risks, report_json) VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
        con.close()
        counts["inserted"] = len(rows)
    return counts


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-c")]
    print(json.dumps(run(args[0] if args else os.environ.get("SCORE_BACKFILL", "dry-run")), indent=1))
