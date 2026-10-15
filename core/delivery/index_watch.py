"""
Compass Phase C — index-inclusion watch (spec §10 Phase C row).

Weekly snapshot of DELIVERY_INDEX_WATCH constituents via the nse pkg;
diff vs the previous snapshot -> inclusion/exclusion AlertEvents for
held + watchlist + shelf symbols only. First snapshot never alerts;
per-index fetch failures keep the stale snapshot (degraded mode).

Audience (FIX-009): an event about an active shelf idea is a market notice,
because the shelf is shared, so it goes to everyone as a shelf add does
(`emit_alerts_broadcast`). Every other event goes only to the accounts that
hold or watch that stock, one bundle each (`emit_alerts`), so no account
learns another's holdings or watchlist. A stock that is both reaches an
account once: with the shelf's notice, or in the account's own bundle when
the shelf's notice did not include the account (no push subscription). An
account whose portfolio cannot be read misses its own events; nothing is
broadcast in their place.
"""
from __future__ import annotations

import json
import logging
import pathlib
import tempfile
from datetime import date, datetime, timezone

from core.config import settings
from core.delivery.alerts import AlertEvent, emit_alerts, emit_alerts_broadcast

logger = logging.getLogger(__name__)

_DEFAULT_CACHE = "data/market_cache/index_constituents.json"


def _make_nse_client():
    from nse import NSE
    return NSE(download_folder=pathlib.Path(tempfile.mkdtemp()))


def _shelf_symbols() -> set[str]:
    """The shared discovery shelf's active ideas. Never raises."""
    try:
        from core.discovery.shelf import ShelfStore
        return {i.symbol for i in ShelfStore().load().ideas if i.status == "active"}
    except Exception as exc:
        logger.warning("[index_watch] shelf read failed (non-fatal): %s", exc)
        return set()


def _account_symbols() -> dict[str, set[str]]:
    """Held + watchlist symbols for each account, by user id. Never raises.

    Accounts are active_user_ids(), or the default user when there are none.
    An account whose portfolio cannot be read is left out, and a failed
    account lookup leaves every account out: their events are skipped, never
    sent to anyone else."""
    try:
        from core.portfolio.store import PortfolioStore, active_user_ids
        users = active_user_ids() or [settings.PORTFOLIO_DEFAULT_USER_ID]
    except Exception as exc:
        logger.warning("[index_watch] account lookup failed, account notices "
                       "skipped (non-fatal): %s", exc)
        return {}
    accounts: dict[str, set[str]] = {}
    for uid in users:
        try:
            p = PortfolioStore(user_id=uid).load()
        except Exception as exc:
            logger.warning("[index_watch] portfolio read failed for %s, its "
                           "notices skipped (non-fatal): %s", uid, exc)
            continue
        accounts[uid] = ({h.symbol for h in p.holdings}
                         | {w.symbol for w in p.watchlist})
    return accounts


def run_index_watch(on: date | None = None, cache_path: str | None = None) -> dict:
    """Snapshot + diff + alert. Never raises."""
    on = on or date.today()
    path = pathlib.Path(cache_path or _DEFAULT_CACHE)
    try:
        cache = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except Exception:
        cache = {}

    shelf = _shelf_symbols()
    accounts = _account_symbols()
    watched = shelf.union(*accounts.values())
    events: list[AlertEvent] = []
    degraded: list[str] = []

    for index in settings.DELIVERY_INDEX_WATCH:
        try:
            nse = _make_nse_client()
            try:
                raw = nse.listEquityStocksByIndex(index)
            finally:
                from services.data.fetchers.nse_client import close_nse
                close_nse(nse)  # exit() + rmtree(download_folder) — AUD-017
            symbols = sorted({
                str(r.get("symbol", "")).upper()
                for r in (raw.get("data", []) if isinstance(raw, dict) else [])
                if str(r.get("symbol", "")).strip()
                and str(r.get("symbol", "")).upper() != index.upper()
            })
            if not symbols:
                raise ValueError("empty constituent list")
            previous = set(cache.get(index, {}).get("symbols", []))
            if previous:                       # first snapshot never alerts
                for sym in sorted((set(symbols) - previous) & watched):
                    events.append(AlertEvent(
                        date=on.isoformat(), kind="index_inclusion", symbol=sym,
                        message=f"included in {index}", severity="info"))
                for sym in sorted((previous - set(symbols)) & watched):
                    events.append(AlertEvent(
                        date=on.isoformat(), kind="index_exclusion", symbol=sym,
                        message=f"excluded from {index}", severity="warning"))
            cache[index] = {"fetched_at": datetime.now(timezone.utc).isoformat(),
                            "symbols": symbols}
        except Exception as exc:
            logger.warning("[index_watch] %s failed — keeping stale (non-fatal): %s",
                           index, exc)
            degraded.append(index)

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(cache, indent=2), encoding="utf-8")
        tmp.replace(path)
    except OSError as exc:
        logger.error("[index_watch] cache write failed (non-fatal): %s", exc)

    title = f"Index reconstitution — {on}"
    market = [e for e in events if e.symbol in shelf]
    reached: set[str] = set()
    if market:                                       # the shelf is shared (AUD-015)
        reached = set(emit_alerts_broadcast(market, title=title).get("users", {}))
    for uid, symbols in accounts.items():            # FIX-009: the account's own only
        # A shelf idea the account also holds came with the shelf's notice,
        # unless the account is outside that audience (no push subscription).
        own = [e for e in events if e.symbol in symbols
               and (e.symbol not in shelf or uid not in reached)]
        if own:
            emit_alerts(own, user_id=uid, title=title)
    return {"indices": len(settings.DELIVERY_INDEX_WATCH),
            "events": len(events), "degraded": degraded}
