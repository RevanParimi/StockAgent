"""
core/intelligence/rl/stores/store_inventory.py
==============================================
SA-009: a read-only manifest of the prediction-store tree.

    python -m core.intelligence.rl.stores.store_inventory [--base-dir DIR]
        [--managed data/managed_tickers.json] [--out manifest.json]

A ticker's history can sit in more than one store. Before SA-009 the startup
self-heal looked for every managed ticker in automobile/<TICKER> and ran the
automobile graph into it, so a renewable-energy name such as SUZLON had both
automobile/SUZLON (automobile dimensions) and renewable_energy/SUZLON. The
evaluators walk every directory, so both stores reach them.

The manifest lists, for every store (a <sector>/<TICKER> directory, or a
legacy flat <TICKER> directory):

  * identity: its path, ticker, file count and one digest over its files;
  * sector evidence: the directory, the managed roster's sector, the ticker
    map's sector, the sector each file declares, and the dimension roster its
    rows and weights carry. A directory name alone never confirms a sector:
    `confirmed` needs a recognised roster that agrees with the directory's
    graph. The `sector` fields of feedback logs, weight memory and ledgers are
    reported but never used as evidence: before SA-009 the store created them
    with the schema default "automobile";
  * ownership: the canonical store is <managed sector>/<TICKER>, the one the
    scheduled forecast and review write. A ticker without a managed entry has
    no owner, and nothing guesses one;
  * schema markers, and the consumer classes whose lookup rule reaches it.

It also lists duplicates: tickers with more than one store, envelopes whose
cycle id appears in more than one store, and graded days (ticker and date)
recorded more than once, each marked identical or conflicting.

Read-only: files are read, never written, and no directory is created (it
never constructs a PredictionStore, whose constructor creates one). The
manifest is sanitized: store paths, tickers, sector keys, counts, SHA-256
digests, dimension names and schema field names; no prices, verdicts, text or
user data. Its digest excludes `generated_at`, so an unchanged tree gives the
same digest on every run.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

logger = logging.getLogger(__name__)

SCHEMA = "sa009.store_inventory/1"
DEFAULT_MANAGED_PATH = "data/managed_tickers.json"

# Which code reaches a store, by the rule it uses to pick <sector>/<TICKER>.
# KT section 3 has the file-level table these classes summarise.
CONSUMER_CLASSES: dict[str, str] = {
    "managed": "scheduled forecast, review, pre-open check, event ingest, weekly ledger "
               "cleanup, RL monitor and scheduler API: <managed sector>/<TICKER>",
    "analysis_graph": "orchestrator weight read and agent prompt-enhancement/dossier reads "
                      "during an analysis: <graph sector>/<TICKER>",
    "automobile_default": "callers that default a missing sector to automobile "
                          "(manual CLIs, bundle builder, UI fallback): automobile/<TICKER>",
    "discovery": "scorecard, eval harness, learning evidence, analytics and universe walk "
                 "every <dir>/<dir> pair",
    "discovery_misread": "the same walks read a legacy flat store as a sector named after "
                         "the ticker",
    "flat_cli": "run_schedule feedback-status: <TICKER>/",
}

# File kinds inside a store. The ticker prefix is matched literally.
_KIND_PATTERNS: tuple[tuple[str, str], ...] = (
    ("envelope", r"{T}_\d{{4}}-\d{{2}}_prediction_envelope\.json"),
    ("feedback_log", r"{T}_\d{{4}}-\d{{2}}_daily_feedback_log\.json"),
    ("control_log", r"{T}_\d{{4}}-\d{{2}}_control_log\.json"),
    ("prompt_enhancements", r"{T}_\d{{4}}-\d{{2}}_prompt_enhancements\.json"),
    ("weight_memory", r"{T}_agent_weight_memory\.json"),
    ("weight_observations", r"{T}_weight_observations\.json"),
    ("learning_ledger", r"{T}_learning_ledger\.json"),
    ("archived_lessons", r"{T}_archived_lessons\.json"),
    ("dossier", r"{T}_dossier\.json"),
    ("offmarket", r"{T}_\d{{4}}-\d{{2}}-\d{{2}}_offmarket\.json"),
    ("thesis_calls", r"thesis_calls\.jsonl"),
)
# Kinds whose `sector` field the writer sets from the store's own sector.
_WRITER_DECLARED = ("envelope", "archived_envelope", "control_log", "prompt_enhancements")
# Kinds whose `sector` field took the schema default "automobile" before SA-009.
_DEFAULT_PRONE = ("feedback_log", "weight_memory", "learning_ledger")
_JSON_KINDS = set(_WRITER_DECLARED) | set(_DEFAULT_PRONE)

_ENVELOPE_MARKERS = ("learning_mode", "decision_gate", "instrument", "row_data_gate",
                     "row_instrument", "row_agent_subscores", "reforecast_history")
_FEEDBACK_MARKERS = ("graded_verdict", "agent_scores", "claims_fired")


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def canonical_json(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def digest_of(obj) -> str:
    return hashlib.sha256(canonical_json(obj).encode("ascii")).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def list_store_files(store_dir: Path) -> list[dict]:
    """[{path, sha256, size}] for every file under store_dir, sorted by the
    POSIX path string (Path ordering ignores case on Windows, which would
    change every digest between a Windows checkout and the Linux volume)."""
    out = []
    for p in store_dir.rglob("*"):
        if p.is_file():
            out.append({"path": p.relative_to(store_dir).as_posix(),
                        "sha256": sha256_file(p), "size": p.stat().st_size})
    return sorted(out, key=lambda f: f["path"])


def store_digest(files: list[dict]) -> str:
    return digest_of([[f["path"], f["sha256"], f["size"]] for f in files])


def file_kind(ticker: str, rel: str) -> str:
    parts = rel.split("/")
    if len(parts) > 1:
        return "archived_envelope" if parts[0] == "archived_envelopes" else "other"
    name = parts[0]
    if name.endswith(".tmp"):
        return "temp"
    for kind, pattern in _KIND_PATTERNS:
        if re.fullmatch(pattern.format(T=re.escape(ticker)), name):
            return kind
    return "other"


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return None


def _dicts(value) -> list[dict]:
    """The dict items of a stored list; anything malformed contributes nothing."""
    return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []


def _keys(value) -> frozenset:
    return frozenset(value) if isinstance(value, dict) else frozenset()


# ---------------------------------------------------------------------------
# Reference data (injectable for tests)
# ---------------------------------------------------------------------------

def default_rosters() -> dict[str, list[str]]:
    """Each graph's current dimension roster: the keys of its AGENT_WEIGHTS.
    get_sector_weights routes through the sector toggles, so a native sector
    switched off takes the generic roster; the manifest's summary then lists
    the two under roster_collisions."""
    from backend.sectors.registry import GENERIC_SECTOR, NATIVE_SECTORS
    from core.intelligence.rl.workflows.sector_router import get_sector_weights
    return {g: sorted(get_sector_weights(g)) for g in sorted(NATIVE_SECTORS | {GENERIC_SECTOR})}


def default_registry() -> dict[str, str]:
    """The explicit ticker map only: the name-fragment and fallback paths guess."""
    from backend.sectors.registry import TICKER_SECTOR
    return {t.upper(): s for t, s in TICKER_SECTOR.items()}


def default_graph_of(sector: str) -> str:
    from backend.sectors.registry import SectorRegistry
    return SectorRegistry.get_graph_sector(sector)


def default_resolve(ticker: str) -> str:
    """The sector an analysis of this ticker resolves to (fallbacks included).
    Used only to say which analysis-time lookup reaches a store, never to
    assign an owner."""
    from backend.sectors.registry import SectorRegistry
    return SectorRegistry.resolve(ticker)


def default_known_sectors() -> set[str]:
    from backend.sectors.registry import GENERIC_SECTOR, TICKER_SECTOR, SectorRegistry
    return set(TICKER_SECTOR.values()) | {s["sector"] for s in SectorRegistry.all_sectors()} \
        | {GENERIC_SECTOR}


def load_managed(path: str | Path | None) -> dict:
    """Read the managed roster without the bootstrap that
    log_buffer.load_managed_tickers() performs (it writes a seed file when the
    roster is missing). Returns {status, sha256, entries, index}; index maps
    TICKER -> list of entries (more than one entry is a conflict)."""
    out = {"status": "not_given", "sha256": None, "entries": 0, "index": {}}
    if path is None:
        return out
    p = Path(path)
    if not p.exists():
        out["status"] = "missing"
        return out
    raw = p.read_bytes()
    out["sha256"] = hashlib.sha256(raw).hexdigest()
    try:
        data = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        out["status"] = "unreadable"
        return out
    if not isinstance(data, list):
        out["status"] = "unreadable"
        return out
    index: dict[str, list[dict]] = defaultdict(list)
    for entry in data:
        if isinstance(entry, dict) and isinstance(entry.get("sym"), str) and entry["sym"].strip():
            index[entry["sym"].strip().upper()].append(entry)
    out.update(status="ok", entries=len(data), index=dict(index))
    return out


def owner_of(ticker: str, managed_index: dict[str, list[dict]]) -> tuple[str | None, str]:
    """The canonical owner of a ticker's history: (sector, source).

    source is "managed" (one entry with an explicit sector: the store the
    scheduled forecast and review use), "unmanaged" (no entry: no owner),
    "managed_without_sector" (the scheduler would default it to automobile;
    SA-009 does not act on a default) or "managed_conflict" (two entries
    disagree). Only "managed" yields a sector."""
    entries = managed_index.get(ticker.upper(), [])
    if not entries:
        return None, "unmanaged"
    sectors = {(e.get("sector") or "").strip() for e in entries}
    if len(sectors) > 1:
        return None, "managed_conflict"
    (sector,) = sectors
    if not sector:
        return None, "managed_without_sector"
    return sector, "managed"


# ---------------------------------------------------------------------------
# Store scan
# ---------------------------------------------------------------------------

def _roster_graph(keys: Iterable[str], rosters: dict[str, frozenset]) -> str | None:
    """The graph whose roster equals this key set, "unrecognized", or None
    when there are no keys (no evidence). When two graphs share a roster the
    first one wins; the summary's roster_collisions says so."""
    s = frozenset(keys)
    if not s:
        return None
    for graph, roster in rosters.items():
        if roster == s:
            return graph
    return "unrecognized"


def _file_roster(kind: str, data: dict, rosters: dict[str, frozenset]) -> tuple[str | None, set]:
    """(graph, unrecognized key sets) for one parsed file. A file whose rows or
    weight tables name more than one graph is "mixed"."""
    sets: list[frozenset] = []
    if kind in ("envelope", "archived_envelope"):
        sets = [_keys(r.get("predicted_agent_scores")) for r in _dicts(data.get("daily_forecasts"))]
    elif kind == "feedback_log":
        sets = [_keys(e.get("predicted_agent_scores")) for e in _dicts(data.get("entries"))]
    elif kind == "weight_memory":
        sets = [_keys(data.get("base_weights")), _keys(data.get("current_weights"))]
    graphs = set()
    unknown = set()
    for s in sets:
        g = _roster_graph(s, rosters)
        if g is None:
            continue
        graphs.add(g)
        if g == "unrecognized":
            unknown.add(tuple(sorted(s)))
    if not graphs:
        return None, unknown
    if len(graphs) > 1:
        return "mixed", unknown
    return graphs.pop(), unknown


def _markers(kind: str, data: dict) -> set[str]:
    found = set()
    if kind in ("envelope", "archived_envelope"):
        rows = _dicts(data.get("daily_forecasts"))
        if "learning_mode" in data:
            found.add("learning_mode")
        if data.get("decision_gate"):
            found.add("decision_gate")
        if data.get("instrument"):
            found.add("instrument")
        if any(r.get("data_gate") for r in rows):
            found.add("row_data_gate")
        if any(r.get("instrument") for r in rows):
            found.add("row_instrument")
        if any(r.get("predicted_agent_subscores") for r in rows):
            found.add("row_agent_subscores")
        if data.get("reforecast_history"):
            found.add("reforecast_history")
    elif kind == "feedback_log":
        entries = _dicts(data.get("entries"))
        if any(e.get("graded_verdict") for e in entries):
            found.add("graded_verdict")
        if any(e.get("predicted_agent_scores") for e in entries):
            found.add("agent_scores")
        if any(e.get("claims_fired") for e in entries):
            found.add("claims_fired")
    return found


def scan_store(store_dir: Path, store_id: str, ticker: str, directory_sector: str | None,
               rosters: dict[str, frozenset]) -> tuple[dict, list[dict], list[dict]]:
    """One store's record, plus its envelope and graded-day identities for the
    duplicate pass: ([{id, file, digest}], [{id, file, digest}])."""
    files = list_store_files(store_dir)
    kinds = Counter()
    declared: dict[str, Counter] = defaultdict(Counter)
    by_roster: dict[str, list[str]] = defaultdict(list)
    unrecognized: set = set()
    unreadable: list[str] = []
    env_markers, fb_markers = Counter(), Counter()
    rows = entries = 0
    cycles: dict[str, list[str]] = defaultdict(list)
    envelope_ids: list[dict] = []
    graded_days: list[dict] = []

    for f in files:
        rel = f["path"]
        kind = file_kind(ticker, rel)
        kinds[kind] += 1
        if kind == "archived_envelope":
            cycles["archived_envelopes"].append(rel.split("/")[-1][:7])
        if kind not in _JSON_KINDS:
            continue
        data = _read_json(store_dir / rel)
        if not isinstance(data, dict):
            unreadable.append(rel)
            continue
        sector = data.get("sector")
        declared[kind][sector if isinstance(sector, str)
                       else "<absent>" if sector is None else "<invalid>"] += 1
        graph, unknown = _file_roster(kind, data, rosters)
        unrecognized |= unknown
        if graph is not None:
            by_roster[graph].append(rel)
        if kind in ("envelope", "archived_envelope"):
            for m in _markers(kind, data):
                env_markers[m] += 1
        if kind == "envelope":
            rows += len(_dicts(data.get("daily_forecasts")))
            cycle_id = rel[: -len("_prediction_envelope.json")]
            cycles["envelopes"].append(cycle_id[len(ticker) + 1:])
            envelope_ids.append({"id": cycle_id.upper(), "file": rel, "digest": digest_of(data)})
        elif kind == "feedback_log":
            for m in _markers(kind, data):
                fb_markers[m] += 1
            log_entries = _dicts(data.get("entries"))
            entries += len(log_entries)
            cycles["feedback_logs"].append(rel[len(ticker) + 1: len(ticker) + 8])
            for e in log_entries:
                graded_days.append({"id": f"{ticker.upper()}:{e.get('date', '')}", "file": rel,
                                    "digest": digest_of(e)})

    record = {
        "store_id": store_id,
        "layout": "sector" if directory_sector is not None else "legacy_flat",
        "ticker": ticker,
        "files": len(files),
        "bytes": sum(f["size"] for f in files),
        "store_sha256": store_digest(files),
        "kinds": dict(sorted(kinds.items())),
        "cycles": {k: sorted(v) for k, v in sorted(cycles.items())},
        "unreadable_files": unreadable,
        "declared_sectors": {k: dict(sorted(v.items())) for k, v in sorted(declared.items())},
        "files_by_roster": {k: sorted(v) for k, v in sorted(by_roster.items())},
        "unrecognized_rosters": [list(s) for s in sorted(unrecognized)],
        "schema": {
            "envelope_rows": rows,
            "envelope_markers": dict(sorted(env_markers.items())),
            "feedback_entries": entries,
            "feedback_markers": dict(sorted(fb_markers.items())),
        },
    }
    return record, envelope_ids, graded_days


def _sector_status(record: dict, directory_graph: str | None) -> str:
    """How far the store's own data supports the sector its directory names.

    confirmed       every roster-bearing file names one graph, the directory's
    conflicting     a file names another graph, several graphs, or declares
                    another sector than its directory (writer-declared kinds)
    directory_only  a sector directory, but no file carries a recognised roster
    roster_only     a legacy flat store whose rosters name one graph
    missing         a legacy flat store with no recognised roster
    empty           no files
    """
    if record["files"] == 0:
        return "empty"
    graphs = {g for g in record["files_by_roster"] if g != "unrecognized"}
    directory = record["store_id"].split("/")[0] if record["layout"] == "sector" else None
    if record["layout"] == "legacy_flat":
        if len(graphs) == 1 and "mixed" not in graphs:
            return "roster_only"
        return "conflicting" if graphs else "missing"
    declared_other = any(
        s not in (directory, "<absent>")
        for kind in _WRITER_DECLARED
        for s in record["declared_sectors"].get(kind, {})
    )
    if declared_other or "mixed" in graphs or len(graphs) > 1:
        return "conflicting"
    if not graphs:
        return "directory_only"
    return "confirmed" if graphs == {directory_graph} else "conflicting"


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------

def _walk(base: Path) -> tuple[list[tuple[Path, str, str, str | None]], list[dict], list[dict]]:
    """Stores as (dir, store_id, ticker, directory_sector); sector dirs; root files."""
    stores, sectors, root_files = [], [], []
    for top in sorted(base.iterdir(), key=lambda p: p.name):
        if top.is_file():
            root_files.append({"path": top.name, "sha256": sha256_file(top),
                               "size": top.stat().st_size})
            continue
        if not top.is_dir():
            continue
        flat = any(c.is_file() and c.name.startswith(f"{top.name}_") for c in top.iterdir())
        if flat:
            stores.append((top, top.name, top.name, None))
            continue
        shared, tickers = [], 0
        for child in sorted(top.iterdir(), key=lambda p: p.name):
            if child.is_dir():
                tickers += 1
                stores.append((child, f"{top.name}/{child.name}", child.name, top.name))
            elif child.is_file():
                shared.append({"path": f"{top.name}/{child.name}",
                               "sha256": sha256_file(child), "size": child.stat().st_size})
        sectors.append({"dir": top.name, "tickers": tickers, "shared_files": shared})
    return stores, sectors, root_files


def _dupe_groups(items: list[dict], store_key: str = "store") -> list[dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for it in items:
        groups[it["id"]].append(it)
    out = []
    for key in sorted(groups):
        occ = groups[key]
        if len(occ) < 2:
            continue
        status = "identical" if len({o["digest"] for o in occ}) == 1 else "conflicting"
        out.append({"id": key, "status": status,
                    "occurrences": sorted(({store_key: o[store_key], "file": o["file"]}
                                           for o in occ),
                                          key=lambda o: (o[store_key], o["file"]))})
    return out


def build_inventory(
    base_dir: str | Path,
    managed_path: str | Path | None = DEFAULT_MANAGED_PATH,
    *,
    rosters: dict[str, list[str]] | None = None,
    registry: dict[str, str] | None = None,
    graph_of: Callable[[str], str] | None = None,
    resolve: Callable[[str], str] | None = None,
    known_sectors: set[str] | None = None,
) -> dict:
    """The manifest for the predictions tree at base_dir (read-only)."""
    base = Path(base_dir)
    rosters = rosters if rosters is not None else default_rosters()
    registry = registry if registry is not None else default_registry()
    graph_of = graph_of or default_graph_of
    resolve = resolve or default_resolve
    known = set(known_sectors) if known_sectors is not None else default_known_sectors()
    managed = load_managed(managed_path)
    index = managed["index"]
    known |= {(e.get("sector") or "") for es in index.values() for e in es} - {""}
    roster_sets = {g: frozenset(r) for g, r in rosters.items()}
    # Graphs with the same roster cannot be told apart by it (SA-009 change 1).
    sharing: dict[frozenset, list[str]] = defaultdict(list)
    for g, r in roster_sets.items():
        sharing[r].append(g)
    roster_collisions = sorted(sorted(gs) for gs in sharing.values() if len(gs) > 1)

    if not base.is_dir():
        raise FileNotFoundError(f"predictions root not found: {base}")
    walked, sectors, root_files = _walk(base)
    for s in sectors:
        s["known_sector"] = s["dir"] in known

    records, all_envelopes, all_days = [], [], []
    for store_dir, store_id, name, directory in walked:
        # File names use the directory's own spelling; lookups use upper case.
        record, envs, days = scan_store(store_dir, store_id, name, directory, roster_sets)
        ticker = name.upper()
        record["ticker"] = ticker
        directory_graph = graph_of(directory) if directory is not None else None
        owner, owner_source = owner_of(ticker, index)
        owner_graph = graph_of(owner) if owner else None
        entries = index.get(ticker, [])
        graphs = {g for g in record["files_by_roster"] if g not in ("unrecognized", "mixed")}
        if owner is None:
            roster_vs_owner = "no_owner"
        elif not record["files_by_roster"]:
            roster_vs_owner = "no_roster"
        elif "mixed" in record["files_by_roster"] or len(graphs) > 1:
            roster_vs_owner = "mixed"
        elif not graphs:
            roster_vs_owner = "unrecognized"
        elif graphs == {owner_graph} and "unrecognized" not in record["files_by_roster"]:
            roster_vs_owner = "match"
        else:
            roster_vs_owner = "wrong_roster"
        if owner is None:
            role = "unowned"
        elif directory == owner:
            role = "canonical"
        else:
            role = "non_canonical"
        consumers = []
        if directory is None:
            consumers = ["discovery_misread", "flat_cli"]
        else:
            consumers.append("discovery")
            if owner and directory == owner:
                consumers.append("managed")
            # Scheduled runs pick the graph from the managed sector, API
            # analyses from the ticker map; either orchestrator reads its own
            # graph's directory.
            analysis_dirs = {graph_of(resolve(ticker))}
            if owner:
                analysis_dirs.add(graph_of(owner))
            if directory in analysis_dirs:
                consumers.append("analysis_graph")
            if directory == "automobile":
                consumers.append("automobile_default")
        record["sector_evidence"] = {
            "directory": directory,
            "directory_known": (directory in known) if directory is not None else None,
            "directory_graph": directory_graph,
            "managed": sorted({(e.get("sector") or "") for e in entries}) if entries else None,
            "managed_enabled": sorted({bool(e.get("enabled", True)) for e in entries})
                               if entries else None,
            "registry": registry.get(ticker),
            "status": _sector_status(record, directory_graph),
        }
        record["ownership"] = {
            "owner_sector": owner,
            "owner_source": owner_source,
            "owner_graph": owner_graph,
            "role": role,
            "roster_vs_owner": roster_vs_owner,
            "registry_agrees": (registry[ticker] == owner)
                               if (owner and ticker in registry) else None,
        }
        record["consumers"] = consumers
        records.append(record)
        for e in envs:
            all_envelopes.append({**e, "store": store_id})
        for d in days:
            all_days.append({**d, "store": store_id})

    stores_by_ticker: dict[str, list[str]] = defaultdict(list)
    for r in records:
        if r["files"]:
            stores_by_ticker[r["ticker"]].append(r["store_id"])
    dup_tickers = [{"ticker": t, "stores": sorted(s)}
                   for t, s in sorted(stores_by_ticker.items()) if len(s) > 1]
    dup_envelopes = _dupe_groups(all_envelopes)
    dup_days = _dupe_groups(all_days)

    status_counts = Counter(r["sector_evidence"]["status"] for r in records)
    role_counts = Counter(r["ownership"]["role"] for r in records if r["files"])
    summary = {
        "stores": len(records),
        "empty_stores": status_counts.get("empty", 0),
        "legacy_flat_stores": sum(1 for r in records if r["layout"] == "legacy_flat"),
        "sector_status": dict(sorted(status_counts.items())),
        "roles": dict(sorted(role_counts.items())),
        "wrong_roster_stores": sum(1 for r in records
                                   if r["ownership"]["roster_vs_owner"] == "wrong_roster"),
        "unknown_sector_dirs": sorted(s["dir"] for s in sectors if not s["known_sector"]),
        "duplicate_tickers": len(dup_tickers),
        "duplicate_envelopes": dict(sorted(Counter(d["status"] for d in dup_envelopes).items())),
        "duplicate_graded_days": dict(sorted(Counter(d["status"] for d in dup_days).items())),
        "unreadable_files": sum(len(r["unreadable_files"]) for r in records),
        "roster_collisions": roster_collisions,
    }
    body = {
        "schema": SCHEMA,
        "managed": {k: managed[k] for k in ("status", "sha256", "entries")},
        "rosters": {g: sorted(r) for g, r in sorted(rosters.items())},
        "consumer_classes": CONSUMER_CLASSES,
        "summary": summary,
        "root_files": root_files,
        "sectors": sectors,
        "stores": records,
        "duplicates": {"tickers": dup_tickers, "envelopes": dup_envelopes,
                       "graded_days": dup_days},
    }
    manifest = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), **body}
    manifest["digest"] = digest_of(body)
    return manifest


def manifest_body(manifest: dict) -> dict:
    return {k: v for k, v in manifest.items() if k not in ("generated_at", "digest")}


def write_json(path: str | Path, obj) -> None:
    Path(path).write_bytes(
        (json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=True) + "\n").encode("ascii"))


def _default_base_dir() -> str:
    from core.config import settings
    return settings.PREDICTION_DATA_DIR


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Read-only prediction-store manifest (SA-009).")
    ap.add_argument("--base-dir", default=None,
                    help="predictions root (default settings.PREDICTION_DATA_DIR)")
    ap.add_argument("--managed", default=DEFAULT_MANAGED_PATH,
                    help="managed roster JSON, read without bootstrapping")
    ap.add_argument("--out", default=None, help="write the manifest here (default stdout)")
    args = ap.parse_args(argv)
    manifest = build_inventory(args.base_dir or _default_base_dir(), args.managed)
    if args.out:
        write_json(args.out, manifest)
    else:
        sys.stdout.write(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"digest": manifest["digest"], **manifest["summary"]}, sort_keys=True),
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
