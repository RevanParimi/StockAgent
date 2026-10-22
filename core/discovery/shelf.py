"""
Compass Phase B — Discovery Shelf (spec §6.3).

Top deep-dive ideas live here with a paper envelope each (paper_lane.py).
Cap DISCOVERY_SHELF_SIZE active ideas: a stronger idea displaces the weakest
active one. An idea whose latest deep dive is more than DISCOVERY_STALE_DAYS
old rotates out. One-command promote-to-watchlist hands an idea to the Phase A
portfolio machinery (source="discovery", weekly cadence).

PR-004, enough diverse, checked ideas to fill 12 holdings:
- At most DISCOVERY_MAX_IDEAS_PER_SECTOR active ideas share a market sector
  (0 = no cap). A newcomer to a full sector replaces that sector's weakest
  idea only when its conviction is higher; the drop event says so. An idea
  with no known market sector is not capped: a missing classification is
  not a sector, and lumping unknowns together is the "generic" label again.
- An idea is re-dived once its latest deep dive is older than
  DISCOVERY_REDIVE_AFTER_DAYS, and first of all when it was shelved before
  the data gate existed. A re-dive refreshes the idea in place, or drops it
  with the reason when its analysis is not actionable or its conviction
  falls below the floor. The rotation clock counts from the latest dive, so
  an idea that keeps passing its monthly re-dive stays; one that fails is
  dropped, and one that cannot be re-dived ages out.
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
from backend.shared.pipeline import decision_gate as dg
from backend.shared.schemas.discovery import DeepDiveResult, Shelf, ShelfIdea
from backend.shared.schemas.portfolio import WatchlistItem
from core.portfolio.promotion import promote_symbol
from core.portfolio.store import PortfolioStore

logger = logging.getLogger(__name__)


def cap_key(idea) -> str:
    """The sector max_ideas_per_sector counts: the market sector, case-folded.
    "" = unknown, never capped."""
    return str(getattr(idea, "market_sector", "") or "").strip().casefold()


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
        whose market sector is full replaces that sector's weakest idea if it
        is stronger, else is skipped (`capped`); otherwise, when the shelf is
        full, it displaces the weakest active idea if it is stronger. Under
        the enforced data gate a dive that is not actionable is skipped
        (`gated`, SA-003); in record mode, which withholds nothing, it is
        kept."""
        shelf = self.load()
        added: list[str] = []
        displaced: list[str] = []
        skipped: list[str] = []
        capped: list[str] = []
        gated: list[str] = []
        cap = settings.DISCOVERY_MAX_IDEAS_PER_SECTOR
        enforced = dg.enforcing()

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
            key = cap_key(dive)
            peers = [i for i in active if key and cap_key(i) == key] if cap > 0 else []
            if cap > 0 and len(peers) >= cap:
                weakest = min(peers, key=lambda i: i.conviction)
                if weakest.conviction >= dive.conviction:
                    skipped.append(dive.symbol)
                    capped.append(dive.symbol)
                    logger.info("[shelf] %s not added: %d ideas already in %s, weakest %s "
                                "%.2f >= %.2f", dive.symbol, len(peers), dive.market_sector,
                                weakest.symbol, weakest.conviction, dive.conviction)
                    continue
                weakest.status = "dropped"
                displaced.append(weakest.symbol)
                self._event("dropped", weakest.symbol,
                            f"sector cap: {len(peers)} ideas in {dive.market_sector}; "
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
        """Drop the weakest active ideas of any market sector holding more
        than the cap. Adds never overfill a sector; this catches a re-dive or
        a backfill that names an idea's sector for the first time."""
        cap = settings.DISCOVERY_MAX_IDEAS_PER_SECTOR
        if cap <= 0:
            return []
        groups: dict[str, list[ShelfIdea]] = defaultdict(list)
        for idea in shelf.ideas:
            if idea.status == "active" and cap_key(idea):
                groups[cap_key(idea)].append(idea)
        dropped: list[str] = []
        for ideas in groups.values():
            ideas.sort(key=lambda i: i.conviction, reverse=True)
            for idea in ideas[cap:]:
                idea.status = "dropped"
                dropped.append(idea.symbol)
                self._event("dropped", idea.symbol,
                            f"sector cap: {len(ideas)} ideas in {idea.market_sector}, "
                            f"weakest beyond {cap} ({idea.conviction:.2f})")
        return dropped

    def apply_redives(self, dives: list[DeepDiveResult], on: date) -> dict:
        """Refresh each re-dived active idea in place, or drop it with the
        reason: the analysis is not actionable (abstain, or no gate), or its
        conviction is below the floor. `added` and `close_at_add` stay, so the
        auditor's shelf grades keep their start; the new `dived` date restarts
        the rotation clock."""
        shelf = self.load()
        by_symbol = {d.symbol: d for d in dives}
        refreshed: list[str] = []
        dropped: dict[str, str] = {}
        floor = settings.DISCOVERY_MIN_CONVICTION
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
            refreshed.append(idea.symbol)
            self._event("redived", idea.symbol,
                        f"conviction {before:.2f} -> {dive.conviction:.2f}, "
                        f"gate {dive.data_gate}, band {dive.entry_low:g}-{dive.entry_high:g}")
        capped = self._enforce_sector_cap(shelf)
        if refreshed or dropped or capped:
            self.save(shelf)
        return {"refreshed": refreshed, "dropped": dropped, "capped": capped}

    def redive_due(self, on: date) -> list[ShelfIdea]:
        """Active ideas to re-dive, most urgent first: those shelved before
        the data gate existed (no gate status), then those whose latest dive
        is older than DISCOVERY_REDIVE_AFTER_DAYS, each oldest dive first.
        An idea that rotates out this run (its latest dive more than
        DISCOVERY_STALE_DAYS old) is left to rotate. [] when re-dives are off
        (0)."""
        days = settings.DISCOVERY_REDIVE_AFTER_DAYS
        if days <= 0:
            return []
        active = [i for i in self.load().ideas if i.status == "active"
                  and _dive_age(i, on) <= settings.DISCOVERY_STALE_DAYS]
        oldest = lambda i: last_dived(i) or date.min       # noqa: E731
        pre_gate = sorted((i for i in active if not i.data_gate), key=oldest)
        stale = sorted((i for i in active if i.data_gate and not dive_is_fresh(i, on)),
                       key=oldest)
        return pre_gate + stale

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
        source='discovery' + managed-universe promotion (weekly cadence)."""
        symbol = symbol.strip().upper()
        shelf = self.load()
        idea = next((i for i in shelf.ideas
                     if i.symbol == symbol and i.status == "active"), None)
        if idea is None:
            return {"status": "not_on_shelf", "symbol": symbol}

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
