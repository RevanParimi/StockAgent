"""
core/intelligence/rl/stores/store_migration.py
==============================================
SA-009: a reversible quarantine of prediction stores that no live writer owns.

    python -m core.intelligence.rl.stores.store_migration plan
        [--base-dir DIR] [--managed data/managed_tickers.json] [--out plan.json]
    python -m core.intelligence.rl.stores.store_migration apply
        --plan plan.json --approve <digest> [--base-dir DIR] [--managed ...]
        [--quarantine-root DIR]
    python -m core.intelligence.rl.stores.store_migration rollback --migration DIR

`plan` is read-only. From the store inventory it proposes to quarantine each
non-empty store of a managed ticker that is not <managed sector>/<TICKER>, the
store the scheduled forecast and review use. SUZLON (managed as
renewable_energy) keeps renewable_energy/SUZLON, and automobile/SUZLON, which
the old startup self-heal filled with the automobile graph, is proposed for
quarantine. The plan holds, and never moves, anything that needs an owner's
decision: duplicates of an unmanaged ticker, a managed sector that disagrees
with the ticker map, a managed entry without a sector, and a canonical store
carrying another graph's roster. The plan lists every file (path, SHA-256,
size) of every store it would move and ends with one digest.

`apply` recomputes the plan and refuses unless the digest is the approved
one. It creates a new migration directory (never reusing one), writes its
lineage record, then for each store re-hashes the files immediately before
moving them and refuses on any difference. A store moves by one directory
rename, so its bytes are never copied, rewritten, merged or deleted; they are
hashed again after the move. The quarantine mirrors the live layout
(<migration>/stores/<sector>/<TICKER>/), so PredictionStore(ticker, sector,
base_dir=<migration>/stores) still reads it.

`rollback` renames each moved store back after checking its bytes. It
refuses a live path that holds any file (it never merges); an empty directory
there, which any read through PredictionStore creates, is removed first. A
refused store is retried on the next run, and a run reports "rolled_back"
only when every store is back with its recorded bytes. A rollback after a
complete apply restores the live tree byte for byte.

The quarantine root defaults to prediction_quarantine/ beside the
predictions root: under data/, so the nightly backup keeps it, and outside
the directory walk the evaluators do. Run apply in a job-free window: a
writer racing the move is detected, not prevented.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from core.intelligence.rl.stores import store_inventory as inv

logger = logging.getLogger(__name__)

PLAN_SCHEMA = "sa009.store_migration_plan/1"
LINEAGE_SCHEMA = "sa009.store_migration_lineage/1"
QUARANTINE_DIRNAME = "prediction_quarantine"


class MigrationRefused(RuntimeError):
    """The plan, the tree or the quarantine is not in the state approved."""


# ---------------------------------------------------------------------------
# Plan (read-only)
# ---------------------------------------------------------------------------

def build_plan(manifest: dict, store_files: dict[str, list[dict]]) -> dict:
    """The migration plan for a manifest. store_files maps store_id to its
    [{path, sha256, size}] (the plan pins every byte it would move)."""
    stores = [s for s in manifest["stores"] if s["files"]]
    by_ticker: dict[str, list[dict]] = {}
    for s in stores:
        by_ticker.setdefault(s["ticker"], []).append(s)

    items, holds, flags = [], [], []
    for ticker in sorted(by_ticker):
        group = sorted(by_ticker[ticker], key=lambda s: s["store_id"])
        own = group[0]["ownership"]
        source = own["owner_source"]
        owner = own["owner_sector"]
        owner_store = f"{owner}/{ticker}" if owner else None
        canonical = [s for s in group if s["ownership"]["role"] == "canonical"]
        others = [s for s in group if s["ownership"]["role"] != "canonical"]

        if source != "managed":
            if len(group) > 1:
                holds.append({"ticker": ticker, "reason": f"{source}_duplicate",
                              "stores": [s["store_id"] for s in group]})
            elif source in ("managed_without_sector", "managed_conflict"):
                holds.append({"ticker": ticker, "reason": source,
                              "stores": [s["store_id"] for s in group]})
            continue
        if own["registry_agrees"] is False and others:
            holds.append({"ticker": ticker, "reason": "owner_registry_conflict",
                          "stores": [s["store_id"] for s in group],
                          "owner_sector": owner,
                          "registry": group[0]["sector_evidence"]["registry"]})
            continue
        if len(canonical) > 1:
            # Directory names differing only in case (a case-sensitive volume):
            # which one is the owner's is a decision, not a rule.
            holds.append({"ticker": ticker, "reason": "several_owner_stores",
                          "stores": [s["store_id"] for s in group]})
            continue
        # Kept, but its files carry another graph's dimensions: row-level
        # lineage for SA-017, not a store move.
        for s in canonical:
            if s["ownership"]["roster_vs_owner"] in ("wrong_roster", "mixed", "unrecognized"):
                flags.append({"ticker": ticker, "store": s["store_id"],
                              "reason": "canonical_roster_" + s["ownership"]["roster_vs_owner"],
                              "files_by_roster": s["files_by_roster"]})
        for s in others:
            files = store_files[s["store_id"]]
            items.append({
                "store_id": s["store_id"],
                "ticker": ticker,
                "action": "quarantine",
                "reason": "legacy_flat" if s["layout"] == "legacy_flat" else "non_canonical",
                "owner_store": owner_store,
                "owner_store_present": bool(canonical),
                "evidence": {
                    "sector_status": s["sector_evidence"]["status"],
                    "roster_vs_owner": s["ownership"]["roster_vs_owner"],
                    "rosters": sorted(s["files_by_roster"]),
                    "consumers": s["consumers"],
                },
                "files": files,
                "store_sha256": inv.store_digest(files),
            })
    body = {
        "schema": PLAN_SCHEMA,
        "managed_sha256": manifest["managed"]["sha256"],
        "managed_status": manifest["managed"]["status"],
        "items": items,
        "holds": holds,
        "flags": flags,
    }
    return {**body, "manifest_digest": manifest["digest"], "digest": inv.digest_of(body)}


def make_plan(base_dir: str | Path, managed_path: str | Path | None = inv.DEFAULT_MANAGED_PATH,
              **inventory_kwargs) -> dict:
    manifest = inv.build_inventory(base_dir, managed_path, **inventory_kwargs)
    base = Path(base_dir)
    files = {s["store_id"]: inv.list_store_files(base / s["store_id"])
             for s in manifest["stores"] if s["files"]}
    return build_plan(manifest, files)


# ---------------------------------------------------------------------------
# Apply / rollback
# ---------------------------------------------------------------------------

def _write_lineage(path: Path, lineage: dict) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes((json.dumps(lineage, indent=2, sort_keys=True, ensure_ascii=True) + "\n")
                    .encode("ascii"))
    os.replace(tmp, path)


def _append_event(root: Path, event: dict) -> None:
    with open(root / "migrations.jsonl", "a", encoding="utf-8") as f:
        f.write(inv.canonical_json(event) + "\n")


def _diff(expected: list[dict], actual: list[dict]) -> dict:
    e = {f["path"]: (f["sha256"], f["size"]) for f in expected}
    a = {f["path"]: (f["sha256"], f["size"]) for f in actual}
    return {"added": sorted(set(a) - set(e)), "removed": sorted(set(e) - set(a)),
            "changed": sorted(p for p in set(e) & set(a) if e[p] != a[p])}


def default_quarantine_root(base_dir: str | Path) -> Path:
    return Path(base_dir).resolve().parent / QUARANTINE_DIRNAME


def _inside(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def apply_plan(plan: dict, approve: str, base_dir: str | Path,
               managed_path: str | Path | None = inv.DEFAULT_MANAGED_PATH,
               quarantine_root: str | Path | None = None,
               now: datetime | None = None, **inventory_kwargs) -> dict:
    """Quarantine the plan's stores. Returns the lineage record."""
    base = Path(base_dir).resolve()
    root = Path(quarantine_root).resolve() if quarantine_root else default_quarantine_root(base)
    if _inside(root, base) or _inside(base, root):
        raise MigrationRefused(f"quarantine root {root} overlaps the predictions root {base}")
    if approve != plan.get("digest"):
        raise MigrationRefused("the approved digest is not this plan's digest")
    fresh = make_plan(base, managed_path, **inventory_kwargs)
    if fresh["digest"] != plan["digest"]:
        raise MigrationRefused(
            f"the tree or the managed roster changed since the plan: fresh plan digest "
            f"{fresh['digest']} != approved {plan['digest']}; make and review a new plan")
    if not fresh["items"]:
        return {"status": "nothing_to_do", "plan_digest": plan["digest"]}

    now = now or datetime.now(timezone.utc)
    migration_id = f"{now:%Y%m%dT%H%M%SZ}-{plan['digest'][:12]}"
    root.mkdir(parents=True, exist_ok=True)
    mig = root / migration_id
    try:
        mig.mkdir(exist_ok=False)      # a migration directory is never reused
    except FileExistsError as exc:
        raise MigrationRefused(f"migration directory {mig} already exists") from exc
    lineage = {
        "schema": LINEAGE_SCHEMA,
        "migration_id": migration_id,
        "plan_digest": plan["digest"],
        "manifest_digest": fresh["manifest_digest"],
        "managed_sha256": fresh["managed_sha256"],
        "base_dir": str(base),
        "created_at": now.isoformat(timespec="seconds"),
        "holds": fresh["holds"],
        "flags": fresh["flags"],
        "items": [{k: it[k] for k in ("store_id", "ticker", "reason", "owner_store",
                                      "owner_store_present", "evidence", "files",
                                      "store_sha256")}
                  | {"to": f"stores/{it['store_id']}", "status": "pending"}
                  for it in fresh["items"]],
        "events": [],
    }
    lpath = mig / "lineage.json"
    _write_lineage(lpath, lineage)

    status = "applied"
    for item in lineage["items"]:
        src = base / item["store_id"]
        dst = mig / item["to"]
        current = inv.list_store_files(src) if src.is_dir() else []
        if current != item["files"]:
            item["status"] = "refused_changed"
            item["diff"] = _diff(item["files"], current)
            status = "stopped"
            break
        if dst.exists():
            item["status"] = "refused_destination_exists"
            status = "stopped"
            break
        dst.parent.mkdir(parents=True, exist_ok=True)
        try:
            src.rename(dst)
        except OSError as exc:
            item["status"] = "failed"
            item["error"] = f"{type(exc).__name__}: {exc}"
            status = "stopped"
            break
        after = inv.list_store_files(dst)
        item["after_files"] = after
        if after == item["files"]:
            item["status"] = "moved"
        else:
            item["status"] = "moved_changed"
            item["diff"] = _diff(item["files"], after)
        _write_lineage(lpath, lineage)
    for item in lineage["items"]:
        if item["status"] == "pending" and status == "stopped":
            item["status"] = "not_attempted"
    lineage["status"] = status
    lineage["events"].append({"event": "apply", "at": now.isoformat(timespec="seconds"),
                              "status": status})
    _write_lineage(lpath, lineage)
    _append_event(root, {"event": "apply", "migration_id": migration_id, "status": status,
                         "plan_digest": plan["digest"],
                         "moved": sum(1 for i in lineage["items"]
                                      if i["status"] in ("moved", "moved_changed")),
                         "items": len(lineage["items"])})
    return lineage


# Item states whose store is still in quarantine, or whose rollback was
# refused. rollback retries every one of them on each run (SA-009 change 1:
# a refused store used to be skipped for good once refused).
_NOT_BACK = ("moved", "moved_changed", "pending", "refused_live_path_exists",
             "refused_quarantine_changed", "refused_quarantine_missing")
_RESTORED = ("rolled_back", "found_live")


def _remove_empty_dir(path: Path) -> bool:
    """Remove path if it is an empty directory. PredictionStore's constructor
    creates its directory on every read, so a read after the apply leaves an
    empty one at a quarantined store's live path. Removing it merges and
    deletes nothing, and rmdir refuses a directory holding any file, so a
    writer's file that lands first is never lost."""
    try:
        path.rmdir()
        return True
    except OSError:
        return False


def rollback(migration_dir: str | Path, now: datetime | None = None) -> dict:
    """Return each quarantined store to its live path. Returns the lineage.

    The run's status is "rolled_back" only when no store is left in
    quarantine or refused, and every restored store has its recorded bytes."""
    mig = Path(migration_dir).resolve()
    lpath = mig / "lineage.json"
    lineage = json.loads(lpath.read_text(encoding="utf-8"))
    if lineage.get("schema") != LINEAGE_SCHEMA:
        raise MigrationRefused(f"{lpath} is not an SA-009 migration lineage")
    base = Path(lineage["base_dir"])
    now = now or datetime.now(timezone.utc)
    for item in reversed(lineage["items"]):
        if item["status"] not in _NOT_BACK:
            continue
        src = base / item["store_id"]
        dst = mig / item["to"]
        # After a crash between the rename and the lineage write, the item
        # still reads "pending" but its store is in quarantine.
        expected = item.get("after_files", item["files"])
        if not dst.is_dir():
            if item["status"] == "pending" and src.is_dir():
                item["status"] = "not_moved"        # the crash came before its rename
            elif src.is_dir() and inv.list_store_files(src) == expected:
                item["status"] = "found_live"       # already back, byte for byte
            else:
                item["status"] = "refused_quarantine_missing"
            continue
        held = inv.list_store_files(dst)
        if held != expected:
            item["status"] = "refused_quarantine_changed"
            item["rollback_diff"] = _diff(expected, held)
            continue
        item.pop("rollback_diff", None)
        if src.exists():
            if not (src.is_dir() and _remove_empty_dir(src)):
                item["status"] = "refused_live_path_exists"
                continue
            item["removed_empty_live_dir"] = True
        src.parent.mkdir(parents=True, exist_ok=True)
        dst.rename(src)
        restored = inv.list_store_files(src)
        item["status"] = "rolled_back" if restored == expected else "rolled_back_changed"
        _write_lineage(lpath, lineage)
    outcome = ("partial" if any(i["status"] in _NOT_BACK + ("rolled_back_changed",)
                                for i in lineage["items"]) else "rolled_back")
    lineage["status"] = outcome
    lineage["events"].append({"event": "rollback", "at": now.isoformat(timespec="seconds"),
                              "status": outcome})
    _write_lineage(lpath, lineage)
    _append_event(mig.parent, {"event": "rollback", "migration_id": lineage["migration_id"],
                               "status": outcome,
                               "restored": sum(1 for i in lineage["items"]
                                               if i["status"] in _RESTORED)})
    return lineage


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Prediction-store quarantine (SA-009).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("plan", "apply"):
        p = sub.add_parser(name)
        p.add_argument("--base-dir", default=None,
                       help="predictions root (default settings.PREDICTION_DATA_DIR)")
        p.add_argument("--managed", default=inv.DEFAULT_MANAGED_PATH)
    sub.choices["plan"].add_argument("--out", default=None)
    sub.choices["apply"].add_argument("--plan", required=True)
    sub.choices["apply"].add_argument("--approve", required=True)
    sub.choices["apply"].add_argument("--quarantine-root", default=None)
    rb = sub.add_parser("rollback")
    rb.add_argument("--migration", required=True)
    args = ap.parse_args(argv)

    try:
        if args.cmd == "plan":
            plan = make_plan(args.base_dir or inv._default_base_dir(), args.managed)
            if args.out:
                inv.write_json(args.out, plan)
            else:
                sys.stdout.write(json.dumps(plan, indent=2, sort_keys=True) + "\n")
            print(json.dumps({"digest": plan["digest"], "quarantine": len(plan["items"]),
                              "holds": len(plan["holds"]), "flags": len(plan["flags"])}),
                  file=sys.stderr)
        elif args.cmd == "apply":
            plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
            result = apply_plan(plan, args.approve, args.base_dir or inv._default_base_dir(),
                                args.managed, args.quarantine_root)
            print(json.dumps({k: result.get(k) for k in ("status", "migration_id")}))
            return 0 if result.get("status") in ("applied", "nothing_to_do") else 1
        else:
            result = rollback(args.migration)
            print(json.dumps({k: result.get(k) for k in ("status", "migration_id")}))
            return 0 if result["status"] == "rolled_back" else 1
    except MigrationRefused as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
