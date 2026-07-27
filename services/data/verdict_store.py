"""
services/data/verdict_store.py
==============================
Atlas M1 plane boundary — the user-plane read seam over ticker-keyed
intelligence output (design spec §3).

Before Atlas, `core/portfolio/advisor.py` and `core/portfolio/pipeline.py`
imported `PredictionStore` straight out of `core.intelligence.rl.stores` — the
user plane reaching into the intelligence plane. `VerdictStore` is the ONLY
user-plane module allowed to import the intelligence plane; everything else in
the user plane goes through this facade. The dependency direction is strictly
user→intelligence (this file imports `PredictionStore`; the intelligence plane
imports neither this facade nor any user store — enforced by
tests/unit/test_atlas_import_boundary.py). That keeps the intelligence plane
user-free (Learning Constitution R1).

Two surfaces:
  * The three advisor reads (`cycle_id_for`, `load_envelope`,
    `load_feedback_log`) DELEGATE to `PredictionStore` and return its objects
    unchanged, so the advisor/pipeline swap is a pure import + type-hint change
    with zero logic change. Each read is hot-path safe (degrades to None on a
    store exception; the advisor already treats missing artifacts as
    conservative defaults, advisor.py:152-171).
  * The projection surface (`publish_projection` → one `ticker_verdicts` row;
    `get_verdict_card` reads it back) is the fast multi-user read model served
    from `atlas.db` — no per-user envelope re-reads at 1k users. It carries NO
    user columns (R1). Dormant until a caller (C4/briefs) wires it in.
"""
from __future__ import annotations

import json
import logging
from datetime import date

from core.intelligence.rl.stores.prediction_store import PredictionStore
from services.data.stores import atlas_store

logger = logging.getLogger(__name__)

# ticker_verdicts columns writable via publish_projection (spec §2). `symbol`
# and `as_of_date` form the PK and are supplied positionally.
_PROJECTION_FIELDS = (
    "verdict", "confidence", "regime", "triggers", "envelope_direction",
    "predicted_close", "confidence_trend", "reversion_prior", "reforecast_reason",
    "direction_accuracy_7d", "thesis_intact", "cycle_id", "source",
)


class VerdictStore:
    """User-plane read seam over ticker-keyed intelligence output."""

    def __init__(self, ticker: str, sector: str | None = None) -> None:
        self.ticker = ticker
        self.sector = sector
        # Constructed here (not module-level) so tests can monkeypatch the
        # PredictionStore symbol on this module before instantiation.
        self._ps = PredictionStore(ticker, sector=sector)

    # -- delegated intelligence reads (byte-for-byte advisor surface) --------

    def cycle_id_for(self, target: date) -> str:
        return self._ps.cycle_id_for(target)

    def load_envelope(self, cycle_id: str | None = None):
        """Delegate to PredictionStore; None on any failure (hot-path safe)."""
        try:
            return self._ps.load_envelope(cycle_id)
        except Exception as exc:
            logger.warning("[verdict_store] envelope read failed for %s (non-fatal): %s",
                           self.ticker, exc)
            return None

    def load_feedback_log(self, cycle_id: str | None = None):
        """Delegate to PredictionStore; None on any failure (the advisor reads
        `log.entries if log else []`, so None degrades to no entries)."""
        try:
            return self._ps.load_feedback_log(cycle_id)
        except Exception as exc:
            logger.warning("[verdict_store] feedback read failed for %s (non-fatal): %s",
                           self.ticker, exc)
            return None

    # -- projection read model (atlas.db ticker_verdicts, user-free) ---------

    def get_verdict_card(self, symbol: str, as_of: date) -> dict | None:
        """The denormalized card for one (symbol, date) from the projection
        table. None on miss or any store failure (never raises into fan-out)."""
        try:
            conn = atlas_store._get_conn()
            row = conn.execute(
                "SELECT * FROM ticker_verdicts WHERE symbol=? AND as_of_date=?",
                (symbol.upper(), as_of.isoformat()),
            ).fetchone()
            return dict(row) if row is not None else None
        except Exception as exc:
            logger.warning("[verdict_store] get_verdict_card failed for %s (non-fatal): %s",
                           symbol, exc)
            return None

    def publish_projection(self, symbol: str, as_of: date, **fields) -> bool:
        """Upsert one `ticker_verdicts` row (the user-plane projection of
        ticker-keyed intelligence output — D2). Ensures the `instruments` FK
        target exists first. Hot-path safe: returns False on any failure, never
        raises into the post-review pipeline. `triggers` may be a list (JSON-
        encoded) or a string. Unknown fields are ignored."""
        sym = symbol.upper()
        cols = {k: fields[k] for k in _PROJECTION_FIELDS if k in fields}
        triggers = cols.get("triggers")
        if isinstance(triggers, (list, tuple)):
            cols["triggers"] = json.dumps(list(triggers))
        try:
            conn = atlas_store._get_conn()
            with atlas_store._lock:
                # FK target: the universe row must exist (spec §4 — held/watched
                # instruments are created on the write path; this is a backstop).
                conn.execute(
                    "INSERT OR IGNORE INTO instruments (sym, created_at, updated_at)"
                    " VALUES (?, ?, ?)",
                    (sym, as_of.isoformat(), as_of.isoformat()))
                names = ["symbol", "as_of_date", *cols.keys()]
                placeholders = ",".join("?" for _ in names)
                updates = ",".join(f"{c}=excluded.{c}" for c in cols)
                sql = (
                    f"INSERT INTO ticker_verdicts ({','.join(names)})"
                    f" VALUES ({placeholders})"
                    " ON CONFLICT(symbol, as_of_date) DO UPDATE SET "
                    + (updates or "symbol=excluded.symbol")
                )
                conn.execute(sql, [sym, as_of.isoformat(), *cols.values()])
                conn.commit()
            return True
        except Exception as exc:
            logger.warning("[verdict_store] publish_projection failed for %s (non-fatal): %s",
                           symbol, exc)
            return False
