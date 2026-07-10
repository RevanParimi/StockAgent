"""
Compass Phase C — Stage-2 IPO / new-listing tracker (spec §6.2).

Research-calibrated: oversubscription != performance, so post-listing
EVIDENCE outweighs subscription froth. Sub-scores (each 0-1, renormalized
over what's available — dark-signal pattern):

  listing_evidence 0.40  last close vs issue price (fallback: first cached close)
  delivery_trend   0.20  mean delivery% last 5 sessions vs prior sessions
  bulk_accum       0.15  net same-side bulk/block accumulation > 0
  subscription     0.25  (qib_weight*qib_x + retail_x)/(qib_weight+1), capped at 50x

Guards (before scoring): >=5 sessions on the tape, close >= DISCOVERY_MIN_PRICE,
median traded value >= DISCOVERY_LIQUIDITY_FLOOR_CR, EQ series only.
Lock-in cliffs (SEBI 2022): anchor 50% at 30d, remainder at 90d, pre-IPO at
180d — flags/alerts only, never buy signals.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

import pandas as pd

from core.config import settings
from backend.shared.schemas.discovery import DiscoveryCandidate, LockinEvent
from services.data.fetchers.bulk_block import load_bulk_block, net_accumulation
from services.data.fetchers.ipo import load_ipo_cache

logger = logging.getLogger(__name__)

_LOCKIN_OFFSETS: tuple[tuple[int, str], ...] = (
    (30, "anchor_50pct"),
    (90, "anchor_remaining"),
    (180, "pre_ipo_6mo"),
)
_MIN_SESSIONS = 5
_SUB_WEIGHTS = {"listing_evidence": 0.40, "delivery_trend": 0.20,
                "bulk_accum": 0.15, "subscription": 0.25}
_SUBSCRIPTION_CAP_X = 50.0


def lockin_events(symbol: str, listing_date: date) -> list[LockinEvent]:
    return [
        LockinEvent(symbol=symbol,
                    expiry=(listing_date + timedelta(days=days)).isoformat(),
                    kind=kind)
        for days, kind in _LOCKIN_OFFSETS
    ]


def _recent_listings(cache: dict, on: date) -> list[dict]:
    out = []
    for rec in cache.get("past", []):
        raw = rec.get("listing_date") or ""
        try:
            listed = date.fromisoformat(raw)
        except ValueError:
            continue
        age = (on - listed).days
        if 0 <= age <= settings.DISCOVERY_IPO_LISTING_WINDOW_DAYS:
            out.append({**rec, "_listed": listed})
    return out


def _clip01(x: float) -> float:
    return max(0.0, min(1.0, x))


def build_ipo_candidates(
    on: date,
    window: pd.DataFrame | None = None,
    cache: dict | None = None,
) -> list[DiscoveryCandidate]:
    """Recent listings -> guarded, scored DiscoveryCandidates (flags=['ipo']).
    Never raises; empty list on any total failure."""
    try:
        cache = cache or load_ipo_cache()
        listings = _recent_listings(cache, on)
        if not listings:
            return []
        if window is None:
            from services.data.stores.eod_store import EodStore
            window = EodStore().load_window(end=on, sessions=90)
        try:
            bulk_net = net_accumulation(load_bulk_block())
        except Exception:
            bulk_net = {}

        out: list[DiscoveryCandidate] = []
        for rec in listings:
            sym = rec["symbol"]
            sw = window[(window["symbol"] == sym) & (window["series"] == "EQ")] \
                .sort_values("date")
            if len(sw) < _MIN_SESSIONS:
                continue
            close = float(sw["close"].iloc[-1])
            if close < settings.DISCOVERY_MIN_PRICE:
                continue
            if float(sw["traded_value_cr"].median()) < settings.DISCOVERY_LIQUIDITY_FLOOR_CR:
                continue

            flags = ["ipo"]
            scores: dict[str, float] = {}

            # listing evidence: % over issue price (fallback: first cached close)
            base = rec.get("issue_price") or float(sw["close"].iloc[0])
            if base and base > 0:
                ret_pct = (close / base - 1.0) * 100.0
                scores["listing_evidence"] = _clip01(0.5 + ret_pct / 50.0)

            # delivery trend: last-5 mean vs prior mean (percentage points)
            deliv = sw["delivery_pct"].dropna()
            if len(deliv) >= _MIN_SESSIONS:
                last5 = float(deliv.tail(5).mean())
                prior = float(deliv.iloc[:-5].mean()) if len(deliv) > 5 else last5
                scores["delivery_trend"] = _clip01(0.5 + (last5 - prior) / 20.0)

            # institutional adds via bulk/block net accumulation
            scores["bulk_accum"] = 1.0 if bulk_net.get(sym, 0.0) > 0 else 0.0

            # subscription: QIB weighted 3x retail (spec §6.2); optional
            qib, retail = rec.get("qib_x"), rec.get("retail_x")
            if qib is not None and retail is not None:
                w = settings.DISCOVERY_IPO_QIB_WEIGHT
                blended = (w * float(qib) + float(retail)) / (w + 1.0)
                scores["subscription"] = _clip01(blended / _SUBSCRIPTION_CAP_X)
            else:
                flags.append("subscription_dark")

            live_w = {k: _SUB_WEIGHTS[k] for k in scores}
            total_w = sum(live_w.values()) or 1.0
            composite = sum(scores[k] * live_w[k] for k in scores) / total_w

            if any(0 <= (date.fromisoformat(e.expiry) - on).days
                   <= settings.DISCOVERY_IPO_LOCKIN_WARN_DAYS
                   for e in lockin_events(sym, rec["_listed"])):
                flags.append("lockin_upcoming")

            out.append(DiscoveryCandidate(
                symbol=sym, close=close, composite=round(composite, 4),
                signal_ranks={k: round(v, 4) for k, v in scores.items()},
                flags=flags,
            ))
        return sorted(out, key=lambda c: c.composite, reverse=True)
    except Exception as exc:
        logger.warning("[ipo_tracker] build failed (non-fatal): %s", exc)
        return []


def upcoming_lockin_alerts(
    on: date, symbols: set[str] | None = None, cache: dict | None = None
) -> list[LockinEvent]:
    """Lock-in expiries within DISCOVERY_IPO_LOCKIN_WARN_DAYS of `on`, optionally
    filtered to a symbol set (held + watchlist + shelf). Never raises."""
    try:
        cache = cache or load_ipo_cache()
        alerts: list[LockinEvent] = []
        for rec in _recent_listings(cache, on) + [
            {**r, "_listed": date.fromisoformat(r["listing_date"])}
            for r in cache.get("past", [])
            if r.get("listing_date")
            and 0 <= (on - date.fromisoformat(r["listing_date"])).days <= 200
            and (on - date.fromisoformat(r["listing_date"])).days
            > settings.DISCOVERY_IPO_LISTING_WINDOW_DAYS
        ]:
            sym = rec["symbol"]
            if symbols is not None and sym not in symbols:
                continue
            for ev in lockin_events(sym, rec["_listed"]):
                days_out = (date.fromisoformat(ev.expiry) - on).days
                if 0 <= days_out <= settings.DISCOVERY_IPO_LOCKIN_WARN_DAYS:
                    alerts.append(ev)
        # dedupe (recent+older scan can overlap on window boundary)
        seen: set[tuple[str, str, str]] = set()
        unique = []
        for a in alerts:
            key = (a.symbol, a.expiry, a.kind)
            if key not in seen:
                seen.add(key)
                unique.append(a)
        return sorted(unique, key=lambda a: a.expiry)
    except Exception as exc:
        logger.warning("[ipo_tracker] lockin scan failed (non-fatal): %s", exc)
        return []
