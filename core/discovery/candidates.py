"""
The ideas one portfolio's autopilot may buy on a review day (PR-004).

Today the autopilot buys an idea only as a SWITCH destination; SA-049 will
also buy with idle cash. Either way it buys only from this list, which has
two sources:

- **Shelf ideas whose deep dive is fresh** (`shelf.dive_is_fresh`). An idea
  whose latest deep dive is older than DISCOVERY_REDIVE_AFTER_DAYS waits for
  Saturday's re-dive: its band and conviction describe a month-old price.
- **The user's own watchlist BUYs** (DISCOVERY_WATCHLIST_BUYS). A stock the
  user added, or promoted from the shelf, qualifies when its latest analysis
  in the score history is a BUY or STRONG BUY, passed the data gate as
  actionable, reaches the shelf's conviction floor, is fresh by the same
  rule (and within DISCOVERY_STALE_DAYS), and NSE lists it as a company. It
  gets an entry band and an invalidation level from its close on the
  analysis day, exactly as a deep dive sets them, so SA-050's entry rule
  applies to it unchanged. A stock the autopilot sold onto the watchlist
  (source "autopilot") does not qualify: the exit rule has just sold it,
  and buying it back needs a new deep dive.

Example: on Tuesday 20 Oct, a shelf idea last dived on 12 Sep (38 days ago)
is not a candidate until Saturday's re-dive. A stock the user added to the
watchlist, analysed on 17 Oct as a BUY at 0.68 with an actionable gate, is a
candidate whose band is 97-102% of its 17 Oct close.

**The sector a candidate carries** is the one it will be held under, so it
must be the key its forecasts are written under. A managed stock keeps its
managed record's sector: the daily review and the monthly forecast write its
predictions there, and `promote_symbol` keeps that record when the
autopilot buys it. So a fresh shelf idea whose stock is managed under
another sector is offered under the managed one. A watchlist stock that is
not managed takes the item's own sector, else the deep dive's
`infer_sector`; never a fixed "generic". Example: HEROMOTOCO added on the
home page is stored with no sector, but it is managed under "automobile",
so it is bought as "automobile" and SA-050's sector cap counts it with
MARUTI and M&M.

`buy_candidates` is pure given its readers: the pipeline passes the score
history, the EOD window and the NSE listing; tests pass fakes.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Callable

import pandas as pd

from backend.shared.pipeline import decision_gate as dg
from backend.shared.schemas.discovery import ShelfIdea
from core.config import settings
from core.discovery.deep_dive import entry_levels, infer_sector
from core.discovery.shelf import dive_is_fresh, last_dived
from core.discovery.universe import COMPANY, instrument_kind
from core.portfolio.promotion import is_valid_sector

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))
BUY_VERDICTS = ("BUY", "STRONG BUY")
# The autopilot's own exits land on the watchlist with this source.
_NOT_QUALIFYING_SOURCES = ("autopilot",)


def _ist_day(stamp) -> date | None:
    """The IST calendar day of a score-history `run_at` (naive UTC ISO)."""
    try:
        dt = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(IST).date()


def _gate_status(record: dict) -> str:
    """The data-gate status stored with the analysis; "" when it has none."""
    try:
        report = json.loads(record.get("report_json") or "{}")
    except (TypeError, ValueError):
        return dg.UNKNOWN
    gate = report.get("decision_gate") if isinstance(report, dict) else None
    return str((gate or {}).get("status") or dg.UNKNOWN) if isinstance(gate, dict) else dg.UNKNOWN


def _managed_sectors() -> dict[str, str]:
    from services.api.log_buffer import managed_sectors
    return managed_sectors()


def holding_sector(symbol: str, own_sector: str, managed: dict[str, str]) -> str:
    """The sector a bought candidate is held under: the managed record's when
    the stock is managed, else its own well-formed sector, else
    `infer_sector` (the registry, NSE's industry, "generic")."""
    symbol = symbol.strip().upper()
    if managed.get(symbol):
        return managed[symbol]
    own = (own_sector or "").strip().lower()
    if own and is_valid_sector(own):
        return own
    return infer_sector(symbol)


def watchlist_window_days() -> int:
    """How old a watchlist analysis may be: the re-dive age when re-dives are
    on, and never more than the shelf's stale age."""
    days = settings.DISCOVERY_STALE_DAYS
    if settings.DISCOVERY_REDIVE_AFTER_DAYS > 0:
        days = min(days, settings.DISCOVERY_REDIVE_AFTER_DAYS)
    return days


def watchlist_idea(item, on: date, latest_analysis: Callable[[str], dict | None],
                   window: pd.DataFrame | None, listing: dict | None,
                   managed: dict[str, str] | None = None,
                   ) -> tuple[ShelfIdea | None, str]:
    """(the candidate built from one watchlist item, "") or (None, why not).
    `managed` maps managed symbols to their sectors (default: the managed
    file, read once every other check has passed)."""
    symbol = item.symbol.strip().upper()
    if item.source in _NOT_QUALIFYING_SOURCES:
        return None, "sold onto the watchlist by the autopilot"
    record = latest_analysis(symbol)
    if not record:
        return None, "no analysis in the score history"
    verdict = str(record.get("verdict") or "").strip().upper()
    if verdict not in BUY_VERDICTS:
        return None, f"latest analysis is {verdict or 'without a verdict'}"
    analysed = _ist_day(record.get("run_at"))
    if analysed is None:
        return None, "latest analysis is undated"
    age, limit = (on - analysed).days, watchlist_window_days()
    if age < 0 or age > limit:
        return None, f"latest analysis of {analysed} is {age} days old (limit {limit})"
    gate = _gate_status(record)
    if not dg.is_actionable(gate):
        return None, f"latest analysis data gate {gate or 'missing'}"
    try:
        conviction = float(record.get("final_score"))
    except (TypeError, ValueError):
        return None, "latest analysis has no score"
    if conviction < settings.DISCOVERY_MIN_CONVICTION:
        return None, (f"conviction {conviction:.2f} below "
                      f"{settings.DISCOVERY_MIN_CONVICTION:.2f}")
    kind = instrument_kind(symbol, listing)
    if kind != COMPANY:
        return None, f"NSE listing says {kind}, not a company"
    sym_win = (window[(window["symbol"] == symbol)
                      & (pd.to_datetime(window["date"]).dt.date <= analysed)]
               if window is not None and not window.empty else pd.DataFrame())
    if sym_win.empty:
        return None, f"no close on or before {analysed}"
    close = float(sym_win.sort_values("date")["close"].iloc[-1])
    if close <= 0:
        return None, f"no close on or before {analysed}"
    entry_low, entry_high, invalidation = entry_levels(close, sym_win)
    day = analysed.isoformat()
    if managed is None:
        managed = _managed_sectors()
    return ShelfIdea(
        symbol=symbol, sector=holding_sector(symbol, item.sector, managed), added=day,
        conviction=conviction, verdict=verdict,
        thesis=str(record.get("investment_thesis") or "")[:800],
        entry_low=entry_low, entry_high=entry_high, invalidation_level=invalidation,
        close_at_add=close, source_screen_date=day, data_gate=gate, dived=day,
        source="watchlist",
    ), ""


def buy_candidates(portfolio, on: date, shelf_ideas: list, *,
                   latest_analysis: Callable[[str], dict | None] | None = None,
                   window: pd.DataFrame | None = None,
                   listing: dict | None = None,
                   managed: dict[str, str] | None = None) -> tuple[list, dict[str, str]]:
    """(the ideas this portfolio may buy on `on`, {excluded symbol: why}).

    Shelf ideas keep their order; watchlist candidates follow. A symbol
    already held, or active on the shelf, is not offered from the watchlist
    (the shelf idea, fresh or not, is the record of it). Each carries the
    sector it will be held under: a shelf idea whose stock is managed under
    another sector is offered as a copy under that one; a watchlist stock
    takes `holding_sector`.
    Readers default to the score history, the EOD store and the cached NSE
    listing, each read only when a watchlist item needs it, and the managed
    file (`managed`), read when there is a fresh shelf idea or a watchlist
    item to check."""
    out: list = []
    excluded: dict[str, str] = {}
    active = [i for i in shelf_ideas if getattr(i, "status", "active") == "active"]
    for idea in active:
        if dive_is_fresh(idea, on):
            if managed is None:
                managed = _managed_sectors()
            # Its own sector came from the deep dive's infer_sector.
            sector = managed.get(idea.symbol.strip().upper()) or idea.sector
            out.append(idea if sector == idea.sector
                       else idea.model_copy(update={"sector": sector}))
        else:
            excluded[idea.symbol] = (
                f"deep dive of {last_dived(idea)} is older than "
                f"{settings.DISCOVERY_REDIVE_AFTER_DAYS} days; waits for its re-dive")
    if not settings.DISCOVERY_WATCHLIST_BUYS:
        return out, excluded

    taken = {i.symbol for i in active} | {h.symbol for h in portfolio.holdings}
    items = [w for w in portfolio.watchlist if w.symbol.strip().upper() not in taken]
    # The readers below cost a score-history query and a 90-session EOD read;
    # skip them when only the autopilot's own exits are left, which never qualify.
    if all(w.source in _NOT_QUALIFYING_SOURCES for w in items):
        for w in items:
            excluded[w.symbol.strip().upper()] = "sold onto the watchlist by the autopilot"
        return out, excluded
    if latest_analysis is None:
        from services.data.stores.score_store import ScoreStore
        latest_analysis = ScoreStore().get_latest
    if window is None:
        from services.data.stores.eod_store import EodStore
        window = EodStore().load_window(end=on, sessions=90)
    if listing is None:
        from services.data.fetchers.bhavcopy import load_listing
        listing = load_listing()
    if managed is None:
        managed = _managed_sectors()
    for item in items:
        try:
            idea, why = watchlist_idea(item, on, latest_analysis, window, listing, managed)
        except Exception as exc:
            logger.warning("[candidates] watchlist %s not read (non-fatal): %s",
                           item.symbol, exc)
            idea, why = None, f"could not be read: {exc}"
        if idea is None:
            excluded[item.symbol.strip().upper()] = why
        else:
            out.append(idea)
    return out, excluded
