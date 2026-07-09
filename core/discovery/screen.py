"""
Compass Phase B — Stage-1 weekly quant screen (spec §6.1).

Funnel: EOD window -> universe (EQ, price floor) -> 7 signal slots ->
weighted percentile-rank composite (renormalized over LIVE signals) ->
top shortlist_size -> per-symbol guards -> top max_candidates.

Persistence: {DISCOVERY_DATA_DIR}/screens/{screen_date}_screen.json
(screen_date = the EOD store's latest session, not the wall-clock date).
"""
from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

import pandas as pd

from core.config import settings
from backend.shared.schemas.discovery import DiscoveryCandidate, ScreenResult
from core.discovery.guards import apply_guards
from core.discovery.signals import compute_signals
from core.discovery.universe import build_universe
from services.data.fetchers.bulk_block import load_bulk_block
from services.data.stores.eod_store import EodStore

logger = logging.getLogger(__name__)


def _screens_dir() -> Path:
    d = Path(settings.DISCOVERY_DATA_DIR) / "screens"
    d.mkdir(parents=True, exist_ok=True)
    return d


def run_screen(on: date | None = None) -> ScreenResult:
    """Run the full quant screen as of `on` (default today). Never raises."""
    on = on or date.today()
    store = EodStore()
    window = store.load_window(end=on, sessions=settings.DISCOVERY_HISTORY_DAYS)
    screen_date = (store.latest_day() or on).isoformat()

    if window.empty:
        logger.warning("[discovery.screen] EOD store empty — screen skipped")
        result = ScreenResult(screen_date=screen_date, universe_size=0,
                              shortlist_size=0)
        _persist(result)
        return result

    universe = build_universe(window)

    bulk_cache = load_bulk_block()
    if bulk_cache.get("degraded") and not bulk_cache.get("deals"):
        bulk_cache = None            # fully dark, not just stale
    raw_signals = compute_signals(window, universe, bulk_cache)

    live = {k: v.rank(pct=True) for k, v in raw_signals.items() if v is not None}
    dark = [k for k, v in raw_signals.items() if v is None]

    if not live:
        logger.warning("[discovery.screen] ALL signals dark — screen degraded to empty")
        result = ScreenResult(screen_date=screen_date, universe_size=len(universe),
                              shortlist_size=0, dark_signals=dark)
        _persist(result)
        return result

    weights = {k: settings.DISCOVERY_SIGNAL_WEIGHTS.get(k, 0.0) for k in live}
    total_w = sum(weights.values()) or 1.0
    weights = {k: w / total_w for k, w in weights.items()}

    composite = pd.Series(0.0, index=pd.Index(universe, name="symbol"))
    for name, ranks in live.items():
        composite = composite + ranks.reindex(universe).fillna(0.5) * weights[name]

    shortlist = composite.sort_values(ascending=False).head(
        settings.DISCOVERY_SHORTLIST_SIZE).index.tolist()

    passed, rejected, degraded = apply_guards(shortlist, window)
    ranked_passed = sorted(passed, key=lambda s: composite[s], reverse=True)[
        : settings.DISCOVERY_MAX_CANDIDATES]

    latest_close = (
        window[window["date"] == window["date"].max()]
        .set_index("symbol")["close"].to_dict()
    )
    candidates = [
        DiscoveryCandidate(
            symbol=s,
            close=float(latest_close.get(s, 0.0)),
            composite=round(float(composite[s]), 4),
            signal_ranks={n: round(float(r.reindex([s]).fillna(0.5).iloc[0]), 4)
                          for n, r in live.items()},
        )
        for s in ranked_passed
    ]

    result = ScreenResult(
        screen_date=screen_date,
        universe_size=len(universe),
        shortlist_size=len(shortlist),
        candidates=candidates,
        rejected=rejected,
        dark_signals=dark,
        degraded_checks=degraded,
    )
    _persist(result)
    logger.info(
        "[discovery.screen] %s: universe=%d shortlist=%d candidates=%d dark=%s",
        screen_date, len(universe), len(shortlist), len(candidates), dark,
    )
    return result


def _persist(result: ScreenResult) -> None:
    try:
        path = _screens_dir() / f"{result.screen_date}_screen.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(result.model_dump_json(indent=2), encoding="utf-8")
        tmp.replace(path)
    except OSError as exc:
        logger.error("[discovery.screen] persist failed: %s", exc)


def load_latest_screen() -> ScreenResult | None:
    files = sorted(_screens_dir().glob("*_screen.json"))
    if not files:
        return None
    try:
        return ScreenResult(**json.loads(files[-1].read_text(encoding="utf-8")))
    except Exception as exc:
        logger.error("[discovery.screen] latest screen unreadable: %s", exc)
        return None
