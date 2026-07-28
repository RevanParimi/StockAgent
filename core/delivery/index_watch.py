"""
Compass Phase C — index-inclusion watch (spec §10 Phase C row).

Weekly snapshot of DELIVERY_INDEX_WATCH constituents via the nse pkg;
diff vs the previous snapshot -> inclusion/exclusion AlertEvents for
held + watchlist + shelf symbols only. First snapshot never alerts;
per-index fetch failures keep the stale snapshot (degraded mode).
"""
from __future__ import annotations

import json
import logging
import pathlib
import tempfile
from datetime import date, datetime, timezone

from core.config import settings
from core.delivery.alerts import AlertEvent, emit_alerts_broadcast

logger = logging.getLogger(__name__)

_DEFAULT_CACHE = "data/market_cache/index_constituents.json"


def _make_nse_client():
    from nse import NSE
    return NSE(download_folder=pathlib.Path(tempfile.mkdtemp()))


def _watched_symbols() -> set[str]:
    """held + watchlist + active shelf. Never raises."""
    watched: set[str] = set()
    try:
        from core.portfolio.store import PortfolioStore, active_user_ids
        for uid in active_user_ids() or [settings.PORTFOLIO_DEFAULT_USER_ID]:
            p = PortfolioStore(user_id=uid).load()
            watched |= {h.symbol for h in p.holdings}
            watched |= {w.symbol for w in p.watchlist}
    except Exception as exc:
        logger.warning("[index_watch] portfolio read failed (non-fatal): %s", exc)
    try:
        from core.discovery.shelf import ShelfStore
        watched |= {i.symbol for i in ShelfStore().load().ideas if i.status == "active"}
    except Exception as exc:
        logger.warning("[index_watch] shelf read failed (non-fatal): %s", exc)
    return watched


def run_index_watch(on: date | None = None, cache_path: str | None = None) -> dict:
    """Snapshot + diff + alert. Never raises."""
    on = on or date.today()
    path = pathlib.Path(cache_path or _DEFAULT_CACHE)
    try:
        cache = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except Exception:
        cache = {}

    watched = _watched_symbols()
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

    if events:
        emit_alerts_broadcast(events, title=f"Index reconstitution — {on}")   # AUD-015
    return {"indices": len(settings.DELIVERY_INDEX_WATCH),
            "events": len(events), "degraded": degraded}
