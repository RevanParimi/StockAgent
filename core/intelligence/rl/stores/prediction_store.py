"""
tools/prediction_store.py
=========================
JSON-backed persistence layer for the RL Feedback / Adaptive Prediction Loop.

Manages four file types per ticker:
  - prediction_envelope      (per cycle, e.g. MARUTI_2026-04)
  - daily_feedback_log       (per cycle)
  - agent_weight_memory      (permanent, persists across cycles)
  - learning_ledger          (permanent, persists across cycles)

Directory layout (with sector):
  data/predictions/
    _market_ledger.json                       ← P2: scope=market_wide across all sectors
    automobile/
      _shared_ledger.json                     ← P2: scope=sector_wide for this sector
      MARUTI/
        MARUTI_2026-04_prediction_envelope.json
        MARUTI_2026-04_daily_feedback_log.json
        MARUTI_agent_weight_memory.json
        MARUTI_learning_ledger.json

Directory layout (legacy, no sector):
  data/predictions/
    MARUTI/
      MARUTI_2026-04_prediction_envelope.json
      ...

Public API
----------
PredictionStore(ticker, sector=None)
  .save_envelope(env)
  .load_envelope(cycle_id)                  → PredictionEnvelope | None
  .save_feedback_log(log)
  .load_feedback_log(cycle_id)              → DailyFeedbackLog
  .append_feedback_entry(cycle_id, entry)
  .save_weight_memory(wm)
  .load_weight_memory()                     → WeightMemory | None
  .save_learning_ledger(ll)
  .load_learning_ledger()                   → LearningLedger
  .load_sector_ledger()                     → LearningLedger  [P2]
  .save_sector_ledger(ll)                               [P2]
  .load_market_ledger()                     → LearningLedger  [P2]
  .save_market_ledger(ll)                               [P2]
  .load_all_ledgers()   → tuple[LearningLedger, LearningLedger, LearningLedger]  [P2]
  .current_cycle_id()                       → str  e.g. "MARUTI_2026-04"
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import date
from pathlib import Path

from core.config import settings

# ---------------------------------------------------------------------------
# Module-level per-path locks — protect shared ledger files from concurrent
# reads/writes when the scheduler runs multiple tickers in parallel.
# Per-ticker files don't need this (each ticker has its own directory).
# ---------------------------------------------------------------------------
_SHARED_LOCKS: dict[str, threading.Lock] = {}
_SHARED_LOCKS_META = threading.Lock()


def _get_shared_lock(path: Path) -> threading.Lock:
    key = str(path.resolve())
    with _SHARED_LOCKS_META:
        if key not in _SHARED_LOCKS:
            _SHARED_LOCKS[key] = threading.Lock()
        return _SHARED_LOCKS[key]
from core.schemas.feedback import (
    DailyFeedbackLog,
    FeedbackEntry,
    LearningLedger,
    PredictionEnvelope,
    WeightMemory,
)

logger = logging.getLogger(__name__)


class PredictionStore:
    """
    File-system JSON store for all RL feedback data for one ticker.

    All methods are synchronous. Files are written atomically by writing to a
    temp file then renaming, so a crash mid-write never leaves a corrupt file.

    Parameters
    ----------
    ticker : str
        NSE ticker symbol (e.g. "MARUTI").
    sector : str | None
        Sector name (e.g. "automobile"). When provided, the ticker directory is
        placed under {base_dir}/{sector}/{ticker}/ and shared/market ledger
        methods become available. When None, uses flat {base_dir}/{ticker}/ for
        backward compatibility.
    base_dir : str | None
        Override the predictions root directory (default: settings.PREDICTION_DATA_DIR).
    """

    def __init__(
        self,
        ticker: str,
        sector: str | None = None,
        base_dir: str | None = None,
    ) -> None:
        self.ticker   = ticker.strip().upper()
        self._sector  = sector
        self._base_dir = Path(base_dir or settings.PREDICTION_DATA_DIR)

        if sector:
            self._dir = self._base_dir / sector / self.ticker
        else:
            self._dir = self._base_dir / self.ticker
        self._dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Cycle ID helpers
    # ------------------------------------------------------------------

    def current_cycle_id(self) -> str:
        """Returns e.g. 'MARUTI_2026-04' for the current calendar month."""
        today = date.today()
        return f"{self.ticker}_{today.year}-{today.month:02d}"

    def _cycle_prefix(self, cycle_id: str) -> str:
        return cycle_id  # already includes ticker

    # ------------------------------------------------------------------
    # File path helpers
    # ------------------------------------------------------------------

    def _envelope_path(self, cycle_id: str) -> Path:
        return self._dir / f"{cycle_id}_prediction_envelope.json"

    def _feedback_log_path(self, cycle_id: str) -> Path:
        return self._dir / f"{cycle_id}_daily_feedback_log.json"

    def _weight_memory_path(self) -> Path:
        return self._dir / f"{self.ticker}_agent_weight_memory.json"

    def _learning_ledger_path(self) -> Path:
        return self._dir / f"{self.ticker}_learning_ledger.json"

    # ------------------------------------------------------------------
    # Atomic write helper
    # ------------------------------------------------------------------

    def _write_json(self, path: Path, data: dict) -> None:
        """Write JSON atomically via a temp file to avoid partial writes."""
        tmp = path.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            tmp.replace(path)
            logger.debug("[PredictionStore] Wrote %s", path.name)
        except OSError as exc:
            logger.error("[PredictionStore] Write failed for %s: %s", path.name, exc)
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            raise RuntimeError(f"Write failed for {path.name}: {exc}") from exc

    def _read_json(self, path: Path) -> dict | None:
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.error("[PredictionStore] Failed to read %s: %s", path.name, exc)
            return None

    # ------------------------------------------------------------------
    # Prediction Envelope
    # ------------------------------------------------------------------

    def save_envelope(self, envelope: PredictionEnvelope) -> None:
        path = self._envelope_path(envelope.cycle_id)
        self._write_json(path, envelope.model_dump())
        logger.info("[PredictionStore] Saved envelope for cycle %s", envelope.cycle_id)

    def load_envelope(self, cycle_id: str | None = None) -> PredictionEnvelope | None:
        cid = cycle_id or self.current_cycle_id()
        data = self._read_json(self._envelope_path(cid))
        if data is None:
            logger.info("[PredictionStore] No envelope found for cycle %s", cid)
            return None
        return PredictionEnvelope(**data)

    # ------------------------------------------------------------------
    # Daily Feedback Log
    # ------------------------------------------------------------------

    def save_feedback_log(self, log: DailyFeedbackLog) -> None:
        path = self._feedback_log_path(log.cycle_id)
        self._write_json(path, log.model_dump())
        logger.info(
            "[PredictionStore] Saved feedback log for %s (%d entries)",
            log.cycle_id, len(log.entries),
        )

    def load_feedback_log(self, cycle_id: str | None = None) -> DailyFeedbackLog:
        cid = cycle_id or self.current_cycle_id()
        data = self._read_json(self._feedback_log_path(cid))
        if data is None:
            return DailyFeedbackLog(ticker=self.ticker, cycle_id=cid)
        return DailyFeedbackLog(**data)

    def load_recent_feedback_entries(self, n_cycles: int = 6) -> list:
        """
        Aggregate FeedbackEntry objects from the last n_cycles completed logs.
        Returns a flat list — most recent cycle first.
        Silently skips unreadable files.
        """
        from core.schemas.feedback import DailyFeedbackLog
        pattern = f"{self.ticker}_*_daily_feedback_log.json"
        log_files = sorted(self._dir.glob(pattern), reverse=True)[:n_cycles]
        entries = []
        for path in log_files:
            try:
                log = DailyFeedbackLog.model_validate_json(path.read_text(encoding="utf-8"))
                entries.extend(log.entries)
            except Exception as exc:
                logger.debug("[PredictionStore] Skipping unreadable log %s: %s", path.name, exc)
        return entries

    def append_feedback_entry(self, entry: FeedbackEntry, cycle_id: str | None = None) -> None:
        """
        Add one FeedbackEntry to the log for the given cycle.
        Replaces any existing entry for the same date (idempotent re-runs).
        """
        cid = cycle_id or self.current_cycle_id()
        log = self.load_feedback_log(cid)
        log.entries = [e for e in log.entries if e.date != entry.date]
        log.entries.append(entry)
        log.entries.sort(key=lambda e: e.date)
        self.save_feedback_log(log)

    # ------------------------------------------------------------------
    # Weight Memory  (permanent across cycles)
    # ------------------------------------------------------------------

    def save_weight_memory(self, wm: WeightMemory) -> None:
        self._write_json(self._weight_memory_path(), wm.model_dump())
        logger.info(
            "[PredictionStore] Saved weight memory v%d for %s",
            wm.weight_version, self.ticker,
        )

    def load_weight_memory(self) -> WeightMemory | None:
        data = self._read_json(self._weight_memory_path())
        if data is None:
            return None
        return WeightMemory(**data)

    def init_weight_memory(self, base_weights: dict[str, float]) -> WeightMemory:
        """
        Bootstrap a fresh WeightMemory from the config base weights.
        Only called when no prior weight_memory file exists for this ticker.
        """
        from datetime import date as _date
        wm = WeightMemory(
            ticker=self.ticker,
            last_updated=_date.today().isoformat(),
            weight_version=0,
            current_weights=base_weights.copy(),
            base_weights=base_weights.copy(),
            adjustment_bounds={
                "max_single_step": settings.WEIGHT_MAX_STEP,
                "max_total_drift_from_base": settings.WEIGHT_MAX_DRIFT,
            },
        )
        self.save_weight_memory(wm)
        logger.info("[PredictionStore] Initialised fresh WeightMemory for %s", self.ticker)
        return wm

    def get_or_init_weight_memory(self, base_weights: dict[str, float]) -> WeightMemory:
        """Load existing memory or create a fresh one from base_weights."""
        existing = self.load_weight_memory()
        if existing is not None:
            return existing
        return self.init_weight_memory(base_weights)

    # ------------------------------------------------------------------
    # Learning Ledger  (permanent across cycles)
    # ------------------------------------------------------------------

    def save_learning_ledger(self, ledger: LearningLedger) -> None:
        self._write_json(self._learning_ledger_path(), ledger.model_dump())
        logger.info(
            "[PredictionStore] Saved learning ledger for %s (%d lessons)",
            self.ticker, len(ledger.lessons),
        )

    def load_learning_ledger(self) -> LearningLedger:
        data = self._read_json(self._learning_ledger_path())
        if data is None:
            return LearningLedger(
                ticker=self.ticker,
                last_updated=date.today().isoformat(),
            )
        return LearningLedger(**data)

    # ------------------------------------------------------------------
    # P2: Shared sector ledger  (_shared_ledger.json in sector folder)
    # ------------------------------------------------------------------

    def _shared_ledger_path(self) -> Path:
        if not self._sector:
            raise ValueError(
                "PredictionStore must be initialised with a sector= argument "
                "to use shared sector ledger methods."
            )
        return self._base_dir / self._sector / "_shared_ledger.json"

    def _market_ledger_path(self) -> Path:
        return self._base_dir / "_market_ledger.json"

    def load_sector_ledger(self) -> LearningLedger:
        """
        Load the sector-wide shared ledger from {base_dir}/{sector}/_shared_ledger.json.
        Returns an empty LearningLedger if the file does not yet exist.
        Requires the store to be initialised with sector=.
        Thread-safe: acquires a per-path lock before reading.
        """
        path = self._shared_ledger_path()
        with _get_shared_lock(path):
            data = self._read_json(path)
        if data is None:
            return LearningLedger(
                ticker=f"_shared_{self._sector}",
                sector=self._sector or "unknown",
                last_updated=date.today().isoformat(),
            )
        return LearningLedger(**data)

    def save_sector_ledger(self, ledger: LearningLedger) -> None:
        """Atomically write the sector shared ledger. Thread-safe."""
        if not self._sector:
            logger.warning(
                "[PredictionStore] save_sector_ledger called without a sector — skipped."
            )
            return
        ledger.last_updated = date.today().isoformat()
        path = self._shared_ledger_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with _get_shared_lock(path):
            self._write_json(path, ledger.model_dump())
        logger.info(
            "[PredictionStore] Saved sector ledger for '%s' (%d lessons)",
            self._sector, len(ledger.lessons),
        )

    def load_market_ledger(self) -> LearningLedger:
        """
        Load the market-wide shared ledger from {base_dir}/_market_ledger.json.
        Returns an empty LearningLedger if the file does not yet exist.
        Thread-safe: acquires a per-path lock before reading.
        """
        path = self._market_ledger_path()
        with _get_shared_lock(path):
            data = self._read_json(path)
        if data is None:
            return LearningLedger(
                ticker="_market",
                sector="all",
                last_updated=date.today().isoformat(),
            )
        return LearningLedger(**data)

    def save_market_ledger(self, ledger: LearningLedger) -> None:
        """Atomically write the market-wide ledger. Thread-safe."""
        ledger.last_updated = date.today().isoformat()
        path = self._market_ledger_path()
        with _get_shared_lock(path):
            self._write_json(path, ledger.model_dump())
        logger.info(
            "[PredictionStore] Saved market ledger (%d lessons)", len(ledger.lessons)
        )

    def load_all_ledgers(
        self,
    ) -> tuple[LearningLedger, LearningLedger, LearningLedger]:
        """
        Load all three ledger tiers in one call.

        Returns
        -------
        (ticker_ledger, sector_ledger, market_ledger)
          - ticker_ledger  : stock-specific lessons for this ticker
          - sector_ledger  : sector-wide lessons from all tickers in this sector
                             (empty if store was created without sector=)
          - market_ledger  : market-wide cross-sector lessons
        """
        ticker_ledger = self.load_learning_ledger()
        if self._sector:
            sector_ledger = self.load_sector_ledger()
        else:
            sector_ledger = LearningLedger(
                ticker="_empty_sector",
                sector="unknown",
                last_updated=date.today().isoformat(),
            )
        market_ledger = self.load_market_ledger()
        return ticker_ledger, sector_ledger, market_ledger

    # ------------------------------------------------------------------
    # P4: Prompt Enhancements  (*_{cycle_id}_prompt_enhancements.json)
    # ------------------------------------------------------------------

    def _enhancements_path(self, cycle_id: str) -> Path:
        return self._dir / f"{cycle_id}_prompt_enhancements.json"

    def load_enhancements(self, cycle_id: str | None = None) -> dict[str, list[str]]:
        """
        Load the prompt_enhancements.json for the given cycle.
        Returns {} when the file does not exist (first cycle — no miss history yet).
        """
        cid  = cycle_id or self.current_cycle_id()
        data = self._read_json(self._enhancements_path(cid))
        if data is None:
            return {}
        return data.get("agent_enhancements", {})

    # ------------------------------------------------------------------
    # G4: Off-market signals  ({ticker}_{date}_offmarket.json)
    # ------------------------------------------------------------------

    def save_offmarket_signals(self, signals) -> None:
        from core.schemas.feedback import OffMarketSignals
        path = self._dir / f"{self.ticker}_{signals.date}_offmarket.json"
        self._write_json(path, signals.model_dump())
        logger.debug("[PredictionStore] Saved offmarket signals for %s on %s", self.ticker, signals.date)

    def load_offmarket_signals(self, date_str: str):
        from core.schemas.feedback import OffMarketSignals
        path = self._dir / f"{self.ticker}_{date_str}_offmarket.json"
        data = self._read_json(path)
        if data is None:
            return None
        try:
            return OffMarketSignals(**data)
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Convenience: list all cycle IDs for this ticker
    # ------------------------------------------------------------------

    def list_cycles(self) -> list[str]:
        """Return all cycle IDs for which an envelope file exists."""
        cycles = []
        for p in self._dir.glob(f"{self.ticker}_*_prediction_envelope.json"):
            # Extract cycle_id from filename
            cycle_id = p.stem.replace("_prediction_envelope", "")
            cycles.append(cycle_id)
        return sorted(cycles)
