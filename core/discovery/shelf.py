"""
Compass Phase B — Discovery Shelf (spec §6.3).

Top deep-dive ideas live here with a paper envelope each (paper_lane.py).
Cap DISCOVERY_SHELF_SIZE active ideas: a stronger idea displaces the weakest
active one. An idea whose latest deep dive is more than DISCOVERY_STALE_DAYS
old rotates out. One-command promote-to-watchlist hands an idea to the Phase A
portfolio machinery (source="discovery", weekly cadence).

PR-004, enough diverse, checked ideas to fill 12 holdings:
- At most DISCOVERY_MAX_IDEAS_PER_SECTOR active ideas share a sector key
  (0 = no cap), the key SA-050's sector cap counts too (FIX-026). A newcomer
  to a full sector replaces that sector's weakest idea only when its
  conviction is higher; the drop event says so. An idea with no key named
  yet, or "generic", is not capped: lumping stocks of unknown or unrelated
  sectors together is not a sector.
- An idea is re-dived once its latest deep dive is older than
  DISCOVERY_REDIVE_AFTER_DAYS, sooner when it was shelved before the data gate
  existed or no analysis has named its sector key, and first of all when the
  autopilot sold its stock since its latest dive (FIX-025). A re-dive
  refreshes the idea in place, or drops it with the reason when its analysis
  is not actionable or its conviction falls below the floor. It names the
  key of an idea that has none (or "generic"), and never changes a named one
  (FIX-026). The rotation clock counts from the latest dive, so an idea that
  keeps passing its monthly re-dive stays; one that fails is dropped, and one
  that cannot be re-dived ages out.
- An idea NSE lists as something other than a company is dropped.
- A dive memo (dives.json) keeps each dive's date and result for
  DISCOVERY_REDIVE_AFTER_DAYS, an abstained one included in either gate
  mode, so a candidate left off the shelf is not dived again every week
  while momentum keeps it in the screen.

Every mutation appends a JSONL event (shelf_events.jsonl) — the add/drop
feed that M4 proactive delivery consumes in Phase C.
"""
from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable

from core.config import settings
from core.intelligence.rl.nse_calendar import IST, session_close_at
from backend.shared.pipeline import decision_gate as dg
from backend.shared.schemas.discovery import DeepDiveResult, Shelf, ShelfIdea
from backend.shared.schemas.portfolio import WatchlistItem
from core.discovery.sector_naming import configured_sectors, key_named, unnamed_why
from core.portfolio.promotion import promote_symbol
from core.portfolio.store import PortfolioStore

logger = logging.getLogger(__name__)


def cap_key(idea, keys: dict[str, str] | None = None) -> str:
    """The sector max_ideas_per_sector counts: the idea's sector key, the one
    SA-050's sector cap counts (FIX-026). "" = never capped: no key named
    yet, or "generic". Example: two drug makers shelved as "pharma" share a
    cap whatever Yahoo calls them."""
    keys = configured_sectors() if keys is None else keys
    return str(idea.sector).strip().lower() if key_named(idea, keys) else ""


def last_dived(idea) -> date | None:
    """Date of the idea's latest deep dive: `dived`, else the dive that
    shelved it (source_screen_date), else the day it was shelved."""
    for value in (getattr(idea, "dived", ""), getattr(idea, "source_screen_date", ""),
                  getattr(idea, "added", "")):
        try:
            return date.fromisoformat(str(value)[:10])
        except ValueError:
            continue
    return None


def sale_day(txn) -> date | None:
    """The IST day a ledger sale was decided, None when undatable. The 16:30
    run dates its sale by the session it reviews, so its stamp can be the later
    day: a sale booked at Friday's close by Monday's run is Monday's, after a
    deep dive dated Saturday, which could not have known of it. A sale the user
    entered keeps its own date: an import stamps it long after the fact."""
    days = []
    try:
        days.append(date.fromisoformat(str(txn.date)[:10]))
    except ValueError:
        pass
    if txn.source == "autopilot":
        try:
            decided = datetime.fromisoformat(str(txn.ts).replace("Z", "+00:00"))
        except ValueError:
            decided = None
        if decided is not None and decided.tzinfo is not None:
            days.append(decided.astimezone(IST).date())
    return max(days, default=None)


def sold_since_dive(idea, sale: date | None) -> bool:
    """Whether a sale on `sale` came on or after the idea's latest deep dive.
    The one rule behind two things: the stock is not bought back
    (autopilot._deploy_check), and its idea is re-dived first
    (`ShelfStore.redive_due`). An undatable dive counts as before the sale."""
    if sale is None:
        return False
    dived = last_dived(idea)
    return dived is None or sale >= dived


def autopilot_sales() -> dict[str, date]:
    """Each stock's latest exit by the autopilot, across the portfolios the
    scheduler runs. A sale the user made by hand is left out: it says nothing
    about the idea's case. So is a TRIM that leaves shares: the stock is still
    held, and no re-dive could bring it back."""
    from core.portfolio.store import active_user_ids
    out: dict[str, date] = {}
    for user_id in active_user_ids():
        for txn in PortfolioStore(user_id=user_id).load_transactions(limit=2000):
            if txn.side == "SELL" and txn.source == "autopilot" and txn.holding_qty_after <= 1e-9:
                day = sale_day(txn)
                if day is not None:
                    out[txn.symbol] = max(day, out.get(txn.symbol, day))
    return out


def no_longer_held(symbols) -> set[str]:
    """Those of `symbols` that no portfolio the scheduler runs holds now. No
    symbols reads no portfolio."""
    symbols = set(symbols)
    if not symbols:
        return set()
    from core.portfolio.store import active_user_ids
    held = {h.symbol for user_id in active_user_ids()
            for h in PortfolioStore(user_id=user_id).load().holdings}
    return symbols - held


def _age(iso, on: date) -> int:
    """Days from an ISO date to `on`; a very large age when undatable."""
    try:
        return (on - date.fromisoformat(str(iso)[:10])).days
    except ValueError:
        return 10 ** 6


def _dive_age(idea, on: date) -> int:
    """Days since the idea's latest deep dive; very large when undatable."""
    dived = last_dived(idea)
    return (on - dived).days if dived else 10 ** 6


def dive_is_fresh(idea, on: date) -> bool:
    """True when the idea may be bought on `on` as far as its age goes: its
    latest deep dive is at most DISCOVERY_REDIVE_AFTER_DAYS old (always true
    when re-dives are off). An undatable dive is not fresh."""
    days = settings.DISCOVERY_REDIVE_AFTER_DAYS
    if days <= 0:
        return True
    dived = last_dived(idea)
    return dived is not None and (on - dived).days <= days


def decision_time(idea) -> tuple[datetime, bool] | None:
    """(when the idea's band, conviction and case were decided, whether that
    time is known to the minute), or None when undatable (FIX-024). A
    watchlist analysis keeps its own time (`analysed_at`). A deep dive keeps
    only its day, so it counts as made at that day's close: after the close
    of a trading day, before the next session's."""
    stamp = str(getattr(idea, "analysed_at", "") or "")
    if stamp:
        try:
            at = datetime.fromisoformat(stamp)
        except ValueError:
            at = None
        if at is not None and at.tzinfo is not None:
            return at.astimezone(IST), True
    dived = last_dived(idea)
    return (session_close_at(dived), False) if dived else None


def close_before_decision(bar: date | None, at: datetime, timed: bool, what: str) -> str:
    """Why a close from bar `bar` cannot price a buy decided at `at` (the
    `what` of an idea: "deep dive" or "analysis"), or "" when it can: the
    close must be struck after the decision, or the buy would be booked at a
    price from before the news the decision read. An undated bar cannot be
    shown to be after it. Examples: an analysis of Mon 2 Nov 20:00 IST is not
    bought at Monday's 15:30 close, but is at Tuesday's; one of 11:00 IST is
    bought at Monday's close; a deep dive dated Fri 30 Oct is bought at
    Monday's close, never Friday's."""
    when = f"{at:%Y-%m-%d %H:%M} IST" if timed else at.date().isoformat()
    if bar is None:
        return f"close from an undated bar; cannot be placed after the {what} of {when}"
    if bar < at.date():
        return f"close of {bar} is before the {what} of {when}"
    if session_close_at(bar) > at:
        return ""
    if timed:
        return f"{what} of {when} is after the close of {bar}"
    return f"{what} of {when} has no time, so it counts as made after that day's close"


def close_before_dive(bar: date | None, idea) -> str:
    """Why a close from bar `bar` cannot price a buy that opens a position in
    `idea`, or "" when it can (FIX-023, FIX-024): `close_before_decision` at
    the idea's `decision_time`. Applies in either data-gate mode. Example: the
    review session is Mon 2 Nov, its bar is missing, and the close comes from
    Fri 30 Oct, while the idea was dived on Sat 31 Oct: "close of 2026-10-30
    is before the deep dive of 2026-10-31"."""
    decided = decision_time(idea) if idea is not None else None
    if decided is None:
        return ""
    what = "analysis" if getattr(idea, "source", "") == "watchlist" else "deep dive"
    return close_before_decision(bar, decided[0], decided[1], what)


class ShelfStore:
    def __init__(self, path: str | None = None) -> None:
        base = Path(settings.DISCOVERY_DATA_DIR)
        base.mkdir(parents=True, exist_ok=True)
        self._path = Path(path) if path else base / "shelf.json"
        self._events_path = base / "shelf_events.jsonl"
        self._dives_path = base / "dives.json"

    # -- persistence -----------------------------------------------------

    def load(self) -> Shelf:
        if not self._path.exists():
            return Shelf()
        try:
            return Shelf(**json.loads(self._path.read_text(encoding="utf-8")))
        except Exception as exc:
            logger.error("[shelf] unreadable %s: %s — starting empty", self._path, exc)
            return Shelf()

    def save(self, shelf: Shelf) -> None:
        shelf.updated_at = datetime.now(timezone.utc).isoformat()
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(shelf.model_dump_json(indent=2), encoding="utf-8")
        tmp.replace(self._path)

    def _event(self, event: str, symbol: str, detail: str = "") -> None:
        try:
            line = json.dumps({
                "ts": datetime.now(timezone.utc).isoformat(),
                "event": event, "symbol": symbol, "detail": detail,
            })
            with open(self._events_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError as exc:
            logger.warning("[shelf] event write failed: %s", exc)

    # -- mutations ---------------------------------------------------------

    def apply_deep_dives(self, dives: list[DeepDiveResult], on: date) -> dict:
        """Add qualifying dives (conviction >= floor), strongest first. A dive
        whose sector key is full replaces that sector's weakest idea if it
        is stronger, else is skipped (`capped`); otherwise, when the shelf is
        full, it displaces the weakest active idea if it is stronger. Under
        the enforced data gate a dive that is not actionable is skipped
        (`gated`, SA-003); in record mode, which withholds nothing, it is
        kept. A dive with no sector key named is shelved too (FIX-026): its
        paper lane runs and its re-dive asks again, but nothing buys it."""
        shelf = self.load()
        added: list[str] = []
        displaced: list[str] = []
        skipped: list[str] = []
        capped: list[str] = []
        gated: list[str] = []
        cap = settings.DISCOVERY_MAX_IDEAS_PER_SECTOR
        enforced = dg.enforcing()
        keys = configured_sectors()

        for dive in sorted(dives, key=lambda d: d.conviction, reverse=True):
            if enforced and not dg.is_actionable(dive.data_gate):
                skipped.append(dive.symbol)
                gated.append(dive.symbol)
                logger.info("[shelf] %s not added: data gate %s (enforced)",
                            dive.symbol, dive.data_gate or "missing")
                continue
            if dive.conviction < settings.DISCOVERY_MIN_CONVICTION:
                skipped.append(dive.symbol)
                continue
            if any(i.symbol == dive.symbol and i.status == "active"
                   for i in shelf.ideas):
                skipped.append(dive.symbol)
                continue
            active = [i for i in shelf.ideas if i.status == "active"]
            key = cap_key(dive, keys)
            peers = [i for i in active if key and cap_key(i, keys) == key] if cap > 0 else []
            if cap > 0 and len(peers) >= cap:
                weakest = min(peers, key=lambda i: i.conviction)
                if weakest.conviction >= dive.conviction:
                    skipped.append(dive.symbol)
                    capped.append(dive.symbol)
                    logger.info("[shelf] %s not added: %d ideas already in %s, weakest %s "
                                "%.2f >= %.2f", dive.symbol, len(peers), key,
                                weakest.symbol, weakest.conviction, dive.conviction)
                    continue
                weakest.status = "dropped"
                displaced.append(weakest.symbol)
                self._event("dropped", weakest.symbol,
                            f"sector cap: {len(peers)} ideas in {key}; "
                            f"replaced by {dive.symbol} "
                            f"({dive.conviction:.2f} > {weakest.conviction:.2f})")
            elif len(active) >= settings.DISCOVERY_SHELF_SIZE:
                weakest = min(active, key=lambda i: i.conviction)
                if weakest.conviction >= dive.conviction:
                    skipped.append(dive.symbol)
                    continue
                weakest.status = "dropped"
                displaced.append(weakest.symbol)
                self._event("dropped", weakest.symbol,
                            f"displaced by {dive.symbol} "
                            f"({dive.conviction:.2f} > {weakest.conviction:.2f})")
            shelf.ideas.append(ShelfIdea(
                symbol=dive.symbol, sector=dive.sector, graph=dive.graph,
                added=on.isoformat(), conviction=dive.conviction,
                verdict=dive.verdict, thesis=dive.thesis,
                entry_low=dive.entry_low, entry_high=dive.entry_high,
                invalidation_level=dive.invalidation_level,
                close_at_add=dive.close, source_screen_date=dive.dive_date,
                data_gate=dive.data_gate, dived=dive.dive_date,
                market_sector=dive.market_sector, industry=dive.industry,
                sector_reading=dive.sector_reading,
            ))
            added.append(dive.symbol)
            self._event("added", dive.symbol, f"conviction={dive.conviction:.2f}")

        displaced += self._enforce_sector_cap(shelf)
        self.save(shelf)
        summary = {"added": added, "displaced": displaced, "skipped": skipped}
        if capped:
            summary["capped"] = capped
        if gated:
            summary["gated"] = gated
        return summary

    def _enforce_sector_cap(self, shelf: Shelf) -> list[str]:
        """Drop the weakest active ideas of any sector key holding more than
        the cap. Adds never overfill a sector; this catches a re-dive that
        names an idea's key for the first time."""
        cap = settings.DISCOVERY_MAX_IDEAS_PER_SECTOR
        if cap <= 0:
            return []
        keys = configured_sectors()
        groups: dict[str, list[ShelfIdea]] = defaultdict(list)
        for idea in shelf.ideas:
            key = cap_key(idea, keys) if idea.status == "active" else ""
            if key:
                groups[key].append(idea)
        dropped: list[str] = []
        for key, ideas in groups.items():
            ideas.sort(key=lambda i: i.conviction, reverse=True)
            for idea in ideas[cap:]:
                idea.status = "dropped"
                dropped.append(idea.symbol)
                self._event("dropped", idea.symbol,
                            f"sector cap: {len(ideas)} ideas in {key}, "
                            f"weakest beyond {cap} ({idea.conviction:.2f})")
        return dropped

    def apply_redives(self, dives: list[DeepDiveResult], on: date) -> dict:
        """Refresh each re-dived active idea in place, or drop it with the
        reason: the analysis is not actionable (abstain, or no gate), or its
        conviction is below the floor. `added` and `close_at_add` stay, so the
        auditor's shelf grades keep their start; the new `dived` date restarts
        the rotation clock.

        FIX-026: the re-dive's sector reading replaces the idea's. Its key
        changes only when the idea has no configured key yet (unnamed, or
        "generic"): a named key is decided once, so a different answer is
        recorded, never applied. The paper lane then writes under the new key.
        Example: an idea filed as "generic" in October, re-dived with the
        answer "pharma", becomes a "pharma" idea; one named "pharma" stays
        "pharma" whatever a later answer says."""
        shelf = self.load()
        by_symbol = {d.symbol: d for d in dives}
        refreshed: list[str] = []
        dropped: dict[str, str] = {}
        floor = settings.DISCOVERY_MIN_CONVICTION
        keys = configured_sectors()
        for idea in shelf.ideas:
            dive = by_symbol.get(idea.symbol)
            if idea.status != "active" or dive is None:
                continue
            if not dg.is_actionable(dive.data_gate):
                reason = f"re-dive {dive.dive_date}: data gate {dive.data_gate or 'missing'}"
            elif dive.conviction < floor:
                reason = (f"re-dive {dive.dive_date}: conviction {dive.conviction:.2f} "
                          f"below {floor:.2f}")
            else:
                reason = ""
            if reason:
                idea.status = "dropped"
                dropped[idea.symbol] = reason
                self._event("dropped", idea.symbol, reason)
                continue
            before = idea.conviction
            idea.conviction = dive.conviction
            idea.verdict, idea.thesis = dive.verdict, dive.thesis
            idea.entry_low, idea.entry_high = dive.entry_low, dive.entry_high
            idea.invalidation_level = dive.invalidation_level
            idea.data_gate, idea.dived = dive.data_gate, dive.dive_date
            if dive.market_sector:
                idea.market_sector, idea.industry = dive.market_sector, dive.industry
            named = ""
            if dive.sector_reading is not None:
                if dive.sector != idea.sector and not key_named(idea, keys):
                    named = f", sector {idea.sector} -> {dive.sector}"
                    idea.sector, idea.graph = dive.sector, dive.graph
                idea.sector_reading = dive.sector_reading
            refreshed.append(idea.symbol)
            self._event("redived", idea.symbol,
                        f"conviction {before:.2f} -> {dive.conviction:.2f}, "
                        f"gate {dive.data_gate}, band {dive.entry_low:g}-{dive.entry_high:g}"
                        f"{named}")
        capped = self._enforce_sector_cap(shelf)
        if refreshed or dropped or capped:
            self.save(shelf)
        return {"refreshed": refreshed, "dropped": dropped, "capped": capped}

    def redive_due(self, on: date, sold: dict[str, date] | None = None) -> list[ShelfIdea]:
        """Active ideas to re-dive, most urgent first, each group oldest dive
        first: those whose stock was sold on or after their latest dive
        (`sold` maps a symbol to its latest autopilot sale), since a re-dive is
        all that can bring them back; those not yet verified: shelved before
        the data gate existed (no gate status), or with no sector key named
        (FIX-026), which nothing buys until a re-dive names one; then those
        whose latest dive is older than DISCOVERY_REDIVE_AFTER_DAYS. An idea
        that rotates out this run (its latest dive more than
        DISCOVERY_STALE_DAYS old) is left to rotate. [] when re-dives are off
        (0). Example: analysed 24 Oct and sold 27 Oct, an idea is due on Sat
        31 Oct, not Sat 28 Nov."""
        days = settings.DISCOVERY_REDIVE_AFTER_DAYS
        if days <= 0:
            return []
        sold = sold or {}
        keys = configured_sectors()
        active = [i for i in self.load().ideas if i.status == "active"
                  and _dive_age(i, on) <= settings.DISCOVERY_STALE_DAYS]
        oldest = lambda i: last_dived(i) or date.min       # noqa: E731
        was_sold = [i for i in active if sold_since_dive(i, sold.get(i.symbol))]
        rest = [i for i in active if not sold_since_dive(i, sold.get(i.symbol))]
        unverified = {i.symbol for i in rest if not i.data_gate or unnamed_why(i, keys)}
        pre_gate = sorted((i for i in rest if i.symbol in unverified), key=oldest)
        stale = sorted((i for i in rest if i.symbol not in unverified
                        and not dive_is_fresh(i, on)), key=oldest)
        return sorted(was_sold, key=oldest) + pre_gate + stale

    # -- the dive memo --------------------------------------------------------

    def _load_dives(self) -> dict:
        if not self._dives_path.exists():
            return {}
        try:
            memo = json.loads(self._dives_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            logger.warning("[shelf] dive memo unreadable %s: %s", self._dives_path, exc)
            return {}
        return memo if isinstance(memo, dict) else {}

    def record_dives(self, dives: list[DeepDiveResult], on: date) -> None:
        """Remember the date and result of each dive. Entries older than
        DISCOVERY_REDIVE_AFTER_DAYS are pruned; nothing is kept when re-dives
        are off."""
        days = settings.DISCOVERY_REDIVE_AFTER_DAYS
        if days <= 0:
            return
        memo = {sym: rec for sym, rec in self._load_dives().items()
                if isinstance(rec, dict) and _age(rec.get("date"), on) <= days}
        for d in dives:
            memo[d.symbol] = {"date": d.dive_date, "conviction": round(d.conviction, 4),
                              "verdict": d.verdict, "data_gate": d.data_gate}
        try:
            tmp = self._dives_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(memo, indent=1, sort_keys=True), encoding="utf-8")
            tmp.replace(self._dives_path)
        except OSError as exc:
            logger.warning("[shelf] dive memo write failed: %s", exc)

    def recently_dived(self, on: date) -> set[str]:
        """Symbols dived within DISCOVERY_REDIVE_AFTER_DAYS. A screen or IPO
        candidate among them that is not on the shelf fell below the floor,
        abstained or lost to stronger ideas; diving it again within the
        month would spend the week's budget on a known answer. Empty when
        re-dives are off."""
        days = settings.DISCOVERY_REDIVE_AFTER_DAYS
        if days <= 0:
            return set()
        return {sym for sym, rec in self._load_dives().items()
                if isinstance(rec, dict) and _age(rec.get("date"), on) <= days}

    def drop_non_companies(self, listing: dict | None) -> dict[str, str]:
        """Drop each active idea that NSE lists as a fund's units, a REIT or
        an InvIT, or any non-company security, with the reason. An idea the
        listing does not know is kept: it is never re-dived (the deep dive
        refuses unverified symbols), so it ages out."""
        from core.discovery.universe import COMPANY, UNKNOWN, instrument_kind
        if not listing:
            return {}
        shelf = self.load()
        dropped: dict[str, str] = {}
        for idea in shelf.ideas:
            if idea.status != "active":
                continue
            kind = instrument_kind(idea.symbol, listing)
            if kind in (COMPANY, UNKNOWN):
                continue
            row = listing.get(idea.symbol, {})
            reason = (f"not a company: NSE lists it as {kind} "
                      f"(series {row.get('series', '?')}, ISIN {row.get('isin', '?')})")
            idea.status = "dropped"
            dropped[idea.symbol] = reason
            self._event("dropped", idea.symbol, reason)
        if dropped:
            self.save(shelf)
        return dropped

    def backfill_classification(self, classify: Callable[[str], dict]) -> list[str]:
        """Name the market sector of active ideas that have none (shelved
        before PR-004, or when Yahoo had no answer), with classify(symbol) ->
        {"sector", "industry"}; then enforce the sector cap. Returns the
        symbols classified."""
        shelf = self.load()
        named: list[str] = []
        for idea in shelf.ideas:
            if idea.status != "active" or cap_key(idea):
                continue
            try:
                found = classify(idea.symbol) or {}
            except Exception as exc:
                logger.warning("[shelf] classification failed for %s: %s", idea.symbol, exc)
                continue
            if found.get("sector"):
                idea.market_sector = str(found["sector"])
                idea.industry = str(found.get("industry") or "")
                named.append(idea.symbol)
        capped = self._enforce_sector_cap(shelf)
        if named or capped:
            self.save(shelf)
        return named

    def rotate_stale(self, on: date) -> list[str]:
        """Drop active ideas whose latest deep dive is more than
        DISCOVERY_STALE_DAYS old (spec: stale ideas >60d without trigger
        rotate out). Without re-dives the latest dive is the one that shelved
        the idea, so this is its age on the shelf. An undatable idea rotates."""
        shelf = self.load()
        rotated: list[str] = []
        for idea in shelf.ideas:
            if idea.status != "active":
                continue
            age = _dive_age(idea, on)
            if age > settings.DISCOVERY_STALE_DAYS:
                idea.status = "dropped"
                rotated.append(idea.symbol)
                self._event("dropped", idea.symbol, f"stale after {age}d")
        if rotated:
            self.save(shelf)
        return rotated

    def promote(self, symbol: str, user_id: str | None = None) -> dict:
        """One-command promote-to-watchlist (spec §6.3): watchlist item with
        source='discovery' + managed-universe promotion (weekly cadence).
        An idea with no sector key named is refused (`sector_unnamed`,
        FIX-026): the managed record would keep "generic" for good."""
        symbol = symbol.strip().upper()
        shelf = self.load()
        idea = next((i for i in shelf.ideas
                     if i.symbol == symbol and i.status == "active"), None)
        if idea is None:
            return {"status": "not_on_shelf", "symbol": symbol}
        why = unnamed_why(idea, configured_sectors())
        if why:
            return {"status": "sector_unnamed", "symbol": symbol,
                    "detail": f"{symbol} has no sector key yet ({why}); its next deep dive "
                              "names one"}

        item = WatchlistItem(
            symbol=symbol, sector=idea.sector, added=date.today().isoformat(),
            reason=f"discovery shelf (conviction {idea.conviction:.2f})",
            source="discovery",
        )
        PortfolioStore(user_id=user_id).add_watchlist(item)
        promotion = promote_symbol(symbol, idea.sector, origin="watchlist")

        idea.status = "promoted"
        self.save(shelf)
        self._event("promoted", symbol, f"user_id={user_id or 'default'}")
        return {"status": "promoted", "symbol": symbol, "promotion": promotion}

    def drop(self, symbol: str, reason: str = "manual") -> bool:
        symbol = symbol.strip().upper()
        shelf = self.load()
        idea = next((i for i in shelf.ideas
                     if i.symbol == symbol and i.status == "active"), None)
        if idea is None:
            return False
        idea.status = "dropped"
        self.save(shelf)
        self._event("dropped", symbol, reason)
        return True
