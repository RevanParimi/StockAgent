"""
Compass Phase B — Discovery Shelf (spec §6.3).

Top deep-dive ideas live here with a paper envelope each (paper_lane.py).
Cap DISCOVERY_SHELF_SIZE active ideas: a stronger idea displaces the weakest
active one. Stale ideas (> DISCOVERY_STALE_DAYS without promotion) rotate
out. One-command promote-to-watchlist hands an idea to the Phase A
portfolio machinery (source="discovery", weekly cadence).

Every mutation appends a JSONL event (shelf_events.jsonl) — the add/drop
feed that M4 proactive delivery consumes in Phase C.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path

from core.config import settings
from backend.shared.schemas.discovery import DeepDiveResult, Shelf, ShelfIdea
from backend.shared.schemas.portfolio import WatchlistItem
from core.portfolio.promotion import promote_symbol
from core.portfolio.store import PortfolioStore

logger = logging.getLogger(__name__)


class ShelfStore:
    def __init__(self, path: str | None = None) -> None:
        base = Path(settings.DISCOVERY_DATA_DIR)
        base.mkdir(parents=True, exist_ok=True)
        self._path = Path(path) if path else base / "shelf.json"
        self._events_path = base / "shelf_events.jsonl"

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
        """Add qualifying dives (conviction >= floor), displacing the weakest
        active idea when the cap is full and the newcomer is stronger."""
        shelf = self.load()
        added: list[str] = []
        displaced: list[str] = []
        skipped: list[str] = []

        for dive in sorted(dives, key=lambda d: d.conviction, reverse=True):
            if dive.conviction < settings.DISCOVERY_MIN_CONVICTION:
                skipped.append(dive.symbol)
                continue
            if any(i.symbol == dive.symbol and i.status == "active"
                   for i in shelf.ideas):
                skipped.append(dive.symbol)
                continue
            active = [i for i in shelf.ideas if i.status == "active"]
            if len(active) >= settings.DISCOVERY_SHELF_SIZE:
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
            ))
            added.append(dive.symbol)
            self._event("added", dive.symbol, f"conviction={dive.conviction:.2f}")

        self.save(shelf)
        return {"added": added, "displaced": displaced, "skipped": skipped}

    def rotate_stale(self, on: date) -> list[str]:
        """Drop active ideas older than DISCOVERY_STALE_DAYS (spec: stale
        ideas >60d without trigger rotate out)."""
        shelf = self.load()
        rotated: list[str] = []
        for idea in shelf.ideas:
            if idea.status != "active":
                continue
            age = (on - date.fromisoformat(idea.added)).days
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
