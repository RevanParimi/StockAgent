"""
Compass Phase A — NSE corporate-events calendar (spec §5.2, §8).

Two feeds, both behind the house non-fatal pattern:
  * fetch_corp_actions(symbol)      -> raw NSE actions() rows (splits/bonus/dividend)
  * refresh_events_calendar(syms)   -> forward board-meeting dates ("results" kind
                                       feeds the advisor's earnings-gap rule)

Degraded mode: a symbol whose fetch fails keeps its stale cache entry and is
listed under "degraded" — no feed is a single point of failure.
"""
from __future__ import annotations

import json
import logging
import pathlib
import tempfile
import time
from datetime import date, datetime, timezone

from backend.shared.schemas.portfolio import CorporateEvent

logger = logging.getLogger(__name__)

_DEFAULT_CACHE = "data/market_cache/corporate_events.json"
_SLEEP_BETWEEN_CALLS = 0.5   # same safe margin as nse_announcements.py

# NSE date strings look like "15-Jul-2026"
_NSE_DATE_FMTS = ("%d-%b-%Y", "%d-%m-%Y", "%Y-%m-%d")

_RESULTS_KEYWORDS = ("financial results", "results", "audited", "unaudited", "quarterly")


def _make_nse_client():
    """Isolated factory so tests can monkeypatch it."""
    from nse import NSE
    return NSE(download_folder=pathlib.Path(tempfile.mkdtemp()))


def _parse_nse_date(raw: str) -> str | None:
    raw = (raw or "").strip()
    for fmt in _NSE_DATE_FMTS:
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _first_str(item: dict, *keys: str) -> str:
    for k in keys:
        v = item.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def fetch_corp_actions(symbol: str) -> list[dict]:
    """Raw NSE actions() rows for a symbol. [] on any failure — never raises."""
    try:
        nse = _make_nse_client()
    except Exception as exc:
        logger.warning("[corporate_events] NSE client unavailable: %s", exc)
        return []
    try:
        raw = nse.actions(symbol=symbol)
        items = raw if isinstance(raw, list) else raw.get("data", [])
        return items if isinstance(items, list) else []
    except Exception as exc:
        logger.warning("[corporate_events] actions() failed for %s: %s", symbol, exc)
        return []
    finally:
        try:
            nse.exit()
        except Exception:
            pass


def refresh_events_calendar(symbols: list[str], cache_path: str | None = None) -> dict:
    """Fetch forward board meetings for each symbol into the cache file.
    Failed symbols keep their previous (stale) entries and are flagged."""
    path = pathlib.Path(cache_path or _DEFAULT_CACHE)
    previous = load_events_calendar(cache_path=str(path))
    events: dict[str, list[dict]] = dict(previous.get("events", {}))
    degraded: list[str] = []

    try:
        nse = _make_nse_client()
    except Exception as exc:
        logger.warning("[corporate_events] NSE client unavailable — calendar fully degraded: %s", exc)
        result = {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "degraded": list(symbols),
            "events": events,
        }
        _write_cache(path, result)
        return result

    try:
        for sym in symbols:
            try:
                raw = nse.boardMeetings(symbol=sym)
                items = raw if isinstance(raw, list) else raw.get("data", [])
                sym_events: list[dict] = []
                for item in items if isinstance(items, list) else []:
                    dt = _parse_nse_date(_first_str(item, "bm_date", "date", "meetingDate"))
                    desc = _first_str(item, "bm_purpose", "purpose", "bm_desc", "desc")
                    if not dt:
                        continue
                    kind = "results" if any(k in desc.lower() for k in _RESULTS_KEYWORDS) else "meeting"
                    sym_events.append(
                        CorporateEvent(symbol=sym, date=dt, kind=kind, desc=desc).model_dump()
                    )
                events[sym] = sorted(sym_events, key=lambda e: e["date"])
            except Exception as exc:
                logger.warning(
                    "[corporate_events] boardMeetings() failed for %s — keeping stale entry: %s",
                    sym, exc,
                )
                degraded.append(sym)
            time.sleep(_SLEEP_BETWEEN_CALLS)
    finally:
        try:
            nse.exit()
        except Exception:
            pass

    result = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "degraded": degraded,
        "events": events,
    }
    _write_cache(path, result)
    return result


def load_events_calendar(cache_path: str | None = None) -> dict:
    path = pathlib.Path(cache_path or _DEFAULT_CACHE)
    if not path.exists():
        return {"fetched_at": "", "degraded": [], "events": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.error("[corporate_events] cache unreadable %s: %s", path, exc)
        return {"fetched_at": "", "degraded": [], "events": {}}


def next_results_event(symbol: str, on: date, calendar: dict) -> CorporateEvent | None:
    """Earliest future results-kind event for symbol, or None."""
    best: CorporateEvent | None = None
    for raw in calendar.get("events", {}).get(symbol, []):
        try:
            ev = CorporateEvent(**raw)
            ev_date = date.fromisoformat(ev.date)
        except Exception:
            continue
        if ev.kind == "results" and ev_date >= on:
            if best is None or ev.date < best.date:
                best = ev
    return best


def _write_cache(path: pathlib.Path, data: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
    except OSError as exc:
        logger.error("[corporate_events] cache write failed %s: %s", path, exc)
