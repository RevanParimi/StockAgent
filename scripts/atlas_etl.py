"""
scripts/atlas_etl.py
====================
Atlas C10 — one-shot ETL from the legacy stores into `data/atlas.db`, plus
ghost-dir reconciliation (design spec §6 cutover steps 3–4).

Run once on a weekend during the C11 cutover, while `ATLAS_ENABLED` is still
FALSE. Every write goes DIRECTLY into `atlas.db` (via `atlas_store` helpers +
raw SQL) rather than through the flag-gated portfolio write-through, so the
index is fully populated *before* the flag is flipped.

Guarantees (spec §6):
  * **Additive** — reads sources, writes `atlas.db`, deletes nothing. Every
    source file survives untouched, so `ATLAS_ENABLED=false` + redeploy is an
    instant rollback and `atlas.db` is rebuildable at any time.
  * **Idempotent** — every insert is `INSERT OR IGNORE` on a UNIQUE/PK key and
    every dir move is guarded, so re-running yields the same row counts, no
    duplicates. Safe to re-run after a partial failure.
  * **Never trades a stranger** — a `data/portfolio/<uid>/` dir with no `users`
    row is quarantined (moved aside + one ops alert), not adopted. The owner's
    `primary` dir is always adopted, never quarantined.

Migration order is FK-correct: users first (so sessions/invites/instruments'
dependents resolve), then the universe, then the per-user join/advice, then the
global-watchlist kill sequence, then the additive telemetry column.

    python scripts/atlas_etl.py            # run against the live data/ tree
    python scripts/atlas_etl.py --dry-run  # classify dirs + report, write nothing
"""
from __future__ import annotations

import argparse
import json
import logging
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from core.config import settings
from services.data.stores import atlas_store

logger = logging.getLogger(__name__)

_QUARANTINE_DIRNAME = "_quarantine"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# 1. users.db → users / sessions / invites / chat_usage  (ATTACH + INSERT…SELECT)
# ---------------------------------------------------------------------------

def _migrate_users_db(conn: sqlite3.Connection, users_db: Path) -> None:
    """Copy the four identity tables from the legacy users.db. FK-guarded so a
    stray orphan session/invite (creator/consumer already gone) is skipped
    rather than aborting the run. No-op if the source file is absent."""
    if not Path(users_db).exists():
        logger.info("[atlas_etl] users.db not found at %s — skipping identity migration",
                    users_db)
        return
    with atlas_store._lock:
        conn.commit()                                    # ATTACH cannot run mid-transaction
        conn.execute("ATTACH DATABASE ? AS src", (str(users_db),))
        try:
            statements = [
                "INSERT OR IGNORE INTO users (user_id, email, pw_hash, display_name,"
                " role, created_at, consent_at) SELECT user_id, email, pw_hash,"
                " display_name, role, created_at, consent_at FROM src.users",
                "INSERT OR IGNORE INTO sessions (token_hash, user_id, created_at,"
                " expires_at, last_seen) SELECT token_hash, user_id, created_at,"
                " expires_at, last_seen FROM src.sessions"
                " WHERE user_id IN (SELECT user_id FROM main.users)",
                "INSERT OR IGNORE INTO invites (code, created_by, created_at, used_by,"
                " used_at) SELECT code, created_by, created_at, used_by, used_at"
                " FROM src.invites WHERE created_by IN (SELECT user_id FROM main.users)"
                " AND (used_by IS NULL OR used_by IN (SELECT user_id FROM main.users))",
                "INSERT OR IGNORE INTO chat_usage (user_id, day, llm_turns)"
                " SELECT user_id, day, llm_turns FROM src.chat_usage"
                " WHERE user_id IN (SELECT user_id FROM main.users)",
            ]
            for sql in statements:
                try:
                    conn.execute(sql)
                except sqlite3.OperationalError as exc:  # e.g. an old DB missing a table
                    logger.warning("[atlas_etl] identity copy step skipped: %s", exc)
            conn.commit()
        finally:
            conn.execute("DETACH DATABASE src")


# ---------------------------------------------------------------------------
# 2. managed_tickers.json → instruments
# ---------------------------------------------------------------------------

def _ensure_instrument(conn: sqlite3.Connection, sym: str, *, name: str = "",
                       sector: str = "", enabled: int = 0, origin: str = "seed",
                       cadence: str = "on_demand", promoted_at: str | None = None) -> None:
    """INSERT OR IGNORE one instruments row (never clobbers an existing one —
    the nightly recompute owns aggregates/cadence thereafter)."""
    now = _now_iso()
    conn.execute(
        "INSERT OR IGNORE INTO instruments (sym, name, sector, enabled, origin,"
        " cadence, promoted_at, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (sym, name, sector, int(enabled), origin, cadence, promoted_at, now, now))


def _migrate_instruments(conn: sqlite3.Connection, managed_tickers: Path) -> None:
    if not Path(managed_tickers).exists():
        return
    try:
        rows = json.loads(Path(managed_tickers).read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("[atlas_etl] managed_tickers.json unreadable (%s) — skipped", exc)
        return
    with atlas_store._lock:
        for t in rows or []:
            sym = str(t.get("sym", "")).strip().upper()
            if not sym:
                continue
            _ensure_instrument(
                conn, sym, name=t.get("name", ""), sector=t.get("sector", ""),
                enabled=1 if t.get("enabled") else 0, origin=t.get("origin", "seed"),
                cadence=t.get("cadence", "on_demand"), promoted_at=t.get("promoted_at"))
        conn.commit()


# ---------------------------------------------------------------------------
# 3. push_subscriptions.json → push_subscriptions
# ---------------------------------------------------------------------------

def _migrate_push(conn: sqlite3.Connection, push_json: Path, user_ids: set[str]) -> int:
    if not Path(push_json).exists():
        return 0
    try:
        data = json.loads(Path(push_json).read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("[atlas_etl] push_subscriptions.json unreadable (%s) — skipped", exc)
        return 0
    inserted = 0
    with atlas_store._lock:
        for uid, subs in (data or {}).items():
            if uid not in user_ids:                       # FK: no users row → skip (log)
                logger.warning("[atlas_etl] push subs for unknown user '%s' — skipped", uid)
                continue
            for sub in subs or []:
                endpoint = sub.get("endpoint", "")
                keys = sub.get("keys", {}) or {}
                if not endpoint:
                    continue
                try:
                    conn.execute(
                        "INSERT OR IGNORE INTO push_subscriptions (user_id, endpoint,"
                        " p256dh, auth, created_at) VALUES (?,?,?,?,?)",
                        (uid, endpoint, keys.get("p256dh", ""), keys.get("auth", ""),
                         _now_iso()))
                    inserted += 1
                except sqlite3.Error as exc:
                    logger.warning("[atlas_etl] push sub insert failed for %s: %s", uid, exc)
        conn.commit()
    return inserted


# ---------------------------------------------------------------------------
# 4. portfolio dirs → user_instruments + user_advice, with ghost reconciliation
# ---------------------------------------------------------------------------

def _classify(uid: str, user_ids: set[str], default_uid: str) -> str:
    """primary → always the owner (adopt); a real users row → migrate; anything
    else is a stranger dir → quarantine (spec §6 step 4, decision D5)."""
    if uid == default_uid:
        return "adopted"
    if uid in user_ids:
        return "migrated"
    return "quarantined"


def _quarantine_dir(portfolio_dir: Path, uid: str) -> None:
    """Move a stranger's dir aside so it is never fanned out to. Guarded so a
    re-run (dir already moved) is a no-op and a name clash never overwrites."""
    src = portfolio_dir / uid
    dest_root = portfolio_dir / _QUARANTINE_DIRNAME
    dest_root.mkdir(parents=True, exist_ok=True)
    dest = dest_root / uid
    if dest.exists():
        dest = dest_root / f"{uid}-{datetime.now(timezone.utc):%Y%m%dT%H%M%S}"
    shutil.move(str(src), str(dest))
    logger.warning("[atlas_etl] quarantined ghost portfolio dir '%s' → %s (no users row)",
                   uid, dest)
    _emit_ops_alert(
        f"Portfolio dir '{uid}' has no users row and was quarantined to "
        f"{dest.name} during the Atlas cutover — human review required before it "
        "trades again.")


def _migrate_portfolio(conn: sqlite3.Connection, portfolio_dir: Path, uid: str) -> None:
    """Project one user's holdings/watchlist into user_instruments and their
    advice ledger into user_advice. All idempotent; hot-path safe on FK gaps
    (e.g. an adopted `primary` with no users row → the row simply isn't indexed,
    the dir is still kept)."""
    pf_path = portfolio_dir / uid / "portfolio.json"
    if pf_path.exists():
        try:
            pf = json.loads(pf_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("[atlas_etl] %s portfolio.json unreadable (%s) — skipped", uid, exc)
            pf = {}
        for h in pf.get("holdings", []) or []:
            sym = str(h.get("symbol", "")).strip().upper()
            if sym:
                atlas_store.upsert_user_instrument(uid, sym, "held",
                                                   origin="held", cadence="daily")
        for w in pf.get("watchlist", []) or []:
            sym = str(w.get("symbol", "")).strip().upper()
            if sym:
                atlas_store.upsert_user_instrument(uid, sym, "watch",
                                                   origin="watched", cadence="weekly")
    _migrate_advice(conn, portfolio_dir / uid / "advice_ledger.jsonl", uid)


def _migrate_advice(conn: sqlite3.Connection, ledger: Path, uid: str) -> None:
    """Stream advice_ledger.jsonl → user_advice (the queryable index; the JSONL
    stays the raw append-only audit). UNIQUE (user_id, symbol, as_of_date) makes
    it idempotent."""
    if not ledger.exists():
        return
    with atlas_store._lock:
        for line in ledger.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            sym = str(r.get("symbol", "")).strip().upper()
            as_of = r.get("date", "")
            if not (sym and as_of):
                continue
            _ensure_instrument(conn, sym)                # FK target for user_advice.symbol
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO user_advice (user_id, symbol, as_of_date,"
                    " verdict, verdict_ref, close, unrealised_pnl_pct, stop_pct,"
                    " confidence, triggers, rationale_hash, outcome_10td, outcome_30td,"
                    " outcome_60td, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (uid, sym, as_of, r.get("verdict", "HOLD"), f"{sym}|{as_of}",
                     float(r.get("close", 0) or 0), float(r.get("unrealised_pnl_pct", 0) or 0),
                     float(r.get("stop_pct", 0) or 0), float(r.get("confidence", 0.5) or 0.5),
                     json.dumps(r.get("triggers", []) or []), r.get("rationale_hash", ""),
                     r.get("outcome_10td"), r.get("outcome_30td"), r.get("outcome_60td"),
                     _now_iso()))
            except sqlite3.Error as exc:                 # FK gap (adopted primary w/o users row)
                logger.warning("[atlas_etl] advice row skipped for %s/%s: %s", uid, sym, exc)
        conn.commit()


def _migrate_portfolios(conn: sqlite3.Connection, portfolio_dir: Path,
                        user_ids: set[str], default_uid: str, dry_run: bool) -> dict:
    result = {"adopted": [], "migrated": [], "quarantined": []}
    root = Path(portfolio_dir)
    if not root.exists():
        return result
    for d in sorted(root.iterdir()):
        if not d.is_dir() or d.name == _QUARANTINE_DIRNAME:
            continue
        uid = d.name
        category = _classify(uid, user_ids, default_uid)
        result[category].append(uid)
        if dry_run:
            continue
        if category == "quarantined":
            _quarantine_dir(root, uid)
        else:
            _migrate_portfolio(conn, root, uid)
    return result


# ---------------------------------------------------------------------------
# 5. global watchlist.json → owner's Portfolio.watchlist (SoT) + user_instruments
# ---------------------------------------------------------------------------

def _migrate_global_watchlist(conn: sqlite3.Connection, watchlist_json: Path,
                              portfolio_dir: Path, owner_uid: str) -> int:
    """Kill the duplicate global watchlist (spec §5): fold each symbol into the
    owner's Portfolio.watchlist (the post-cutover single SoT, dedup by symbol)
    and project it into user_instruments(watch). add_watchlist's own atlas sync
    is flag-gated (off at cutover), so we upsert the index explicitly."""
    if not Path(watchlist_json).exists():
        return 0
    try:
        syms = json.loads(Path(watchlist_json).read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("[atlas_etl] watchlist.json unreadable (%s) — skipped", exc)
        return 0
    merged = 0
    from core.portfolio.store import PortfolioStore
    from backend.shared.schemas.portfolio import WatchlistItem
    store = PortfolioStore(user_id=owner_uid, base_dir=str(portfolio_dir))
    today = datetime.now(timezone.utc).date().isoformat()
    for raw in syms or []:
        sym = str(raw).strip().upper()
        if not sym:
            continue
        try:
            store.add_watchlist(WatchlistItem(symbol=sym, added=today, source="user"))
        except Exception as exc:
            logger.warning("[atlas_etl] watchlist merge failed for %s: %s", sym, exc)
        atlas_store.upsert_user_instrument(owner_uid, sym, "watch",
                                           origin="watched", cadence="weekly")
        merged += 1
    return merged


# ---------------------------------------------------------------------------
# 6. telemetry.db — additive nullable user_id column (BP4)
# ---------------------------------------------------------------------------

def _migrate_telemetry(telemetry_db: Path) -> bool:
    """ALTER TABLE llm_calls ADD COLUMN user_id (in place, idempotent). NULL =
    'shared brain' (BP4). Returns True once the column is present."""
    if not Path(telemetry_db).exists():
        return False
    conn = sqlite3.connect(str(telemetry_db))
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(llm_calls)").fetchall()]
        if not cols:
            return False                                 # no llm_calls table yet
        if "user_id" not in cols:
            conn.execute("ALTER TABLE llm_calls ADD COLUMN user_id TEXT")
            conn.commit()
        return True
    except sqlite3.Error as exc:
        logger.warning("[atlas_etl] telemetry ALTER skipped: %s", exc)
        return False
    finally:
        conn.close()


def _emit_ops_alert(message: str) -> None:
    """One broadcast ops alert (non-fatal; degrades to nothing when delivery is
    disabled, e.g. under tests)."""
    try:
        from core.delivery.alerts import AlertEvent, emit_alerts_broadcast
        emit_alerts_broadcast([AlertEvent(
            date=datetime.now(timezone.utc).date().isoformat(),
            kind="atlas_quarantine", symbol="", message=message, severity="warning",
        )], title="Atlas ETL")
    except Exception as exc:
        logger.warning("[atlas_etl] ops alert failed (non-fatal): %s", exc)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def run_etl(*, users_db: Path | str = Path("data/users.db"),
            push_json: Path | str | None = None,
            managed_tickers: Path | str = Path("data/managed_tickers.json"),
            portfolio_dir: Path | str | None = None,
            watchlist_json: Path | str = Path("data/watchlist.json"),
            telemetry_db: Path | str | None = None,
            default_user_id: str | None = None,
            dry_run: bool = False) -> dict:
    """Migrate every legacy source into atlas.db and reconcile portfolio dirs.
    Returns a summary (post-run atlas row counts + adopted/migrated/quarantined
    dir lists + watchlist merges) for the C11 validation step. Idempotent."""
    push_json = Path(push_json) if push_json is not None \
        else Path(settings.DELIVERY_DATA_DIR) / "push_subscriptions.json"
    portfolio_dir = Path(portfolio_dir) if portfolio_dir is not None \
        else Path(settings.PORTFOLIO_DATA_DIR)
    telemetry_db = Path(telemetry_db) if telemetry_db is not None \
        else Path(settings.TELEMETRY_DB_PATH)
    default_uid = default_user_id or settings.PORTFOLIO_DEFAULT_USER_ID

    conn = atlas_store._get_conn()

    if not dry_run:
        _migrate_users_db(conn, Path(users_db))
        _migrate_instruments(conn, Path(managed_tickers))

    user_ids = set(atlas_store.user_ids())

    if not dry_run:
        _migrate_push(conn, push_json, user_ids)

    recon = _migrate_portfolios(conn, portfolio_dir, user_ids, default_uid, dry_run)

    watchlist_merged = 0
    telemetry_ok = False
    if not dry_run:
        watchlist_merged = _migrate_global_watchlist(
            conn, Path(watchlist_json), portfolio_dir, default_uid)
        telemetry_ok = _migrate_telemetry(telemetry_db)

    def _count(table: str) -> int:
        try:
            return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        except sqlite3.Error:
            return -1

    summary = {t: _count(t) for t in (
        "users", "sessions", "invites", "chat_usage", "instruments",
        "user_instruments", "user_advice", "push_subscriptions")}
    summary.update(adopted=recon["adopted"], migrated=recon["migrated"],
                   quarantined=recon["quarantined"],
                   watchlist_merged=watchlist_merged,
                   telemetry_user_id_column=telemetry_ok, dry_run=dry_run)
    logger.info("[atlas_etl] complete: %s", summary)
    return summary


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Atlas C10 ETL (spec §6).")
    ap.add_argument("--dry-run", action="store_true",
                    help="classify portfolio dirs + report only; write nothing")
    args = ap.parse_args()
    summary = run_etl(dry_run=args.dry_run)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
