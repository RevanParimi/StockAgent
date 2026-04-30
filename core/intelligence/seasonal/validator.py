"""
core/intelligence/seasonal/validator.py
========================================
SeasonalValidator — tracks whether pre-seeded patterns are actually confirmed
or contradicted by the RL feedback loop over time.

State is stored in a per-sector JSON file:
    data/predictions/{sector}/_seasonal_validation.json

This deliberately does NOT mutate the YAML seed files, which are the immutable
source of truth. Instead, validation state is a runtime overlay that the
SeasonalCalendar can optionally read to enrich SeasonalPattern.validated_by_rl.

Lifecycle of a seed pattern:
    SEEDED       → active, unvalidated (validated_by_rl=False)
    REINFORCED   → 1 RL cycle confirms the pattern direction
    VALIDATED    → ≥ MIN_HITS cycles confirm (validated_by_rl flipped True in state)
    INVALIDATED  → ≥ MAX_MISSES cycles contradict (still_valid=False in state)

"Confirms" = the actual stock direction on an active-pattern day matches
             the seed's net direction (net-positive adjustments → expect UP;
             net-negative → expect DOWN).

Design decisions:
  • Validation state is JSON (not YAML) — it is written by the system at runtime.
  • The validator only updates state; it does not mutate the in-memory pattern objects.
  • Callers read validation state via load_validation_state() and can overlay it.
  • A "contradicted" pattern still runs at half-confidence until INVALIDATED —
    giving it a chance to recover if market conditions change.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from core.schemas.feedback import DailyFeedbackLog, SeasonalPattern

logger = logging.getLogger(__name__)

# Thresholds (configurable via constructor args)
MIN_HITS_TO_VALIDATE: int = 2     # RL cycles confirming before validated_by_rl → True
MAX_MISSES_TO_INVALIDATE: int = 3  # RL cycles contradicting before still_valid → False


@dataclass
class PatternValidationRecord:
    """Runtime state for one seed pattern."""
    pattern_id: str
    hits: int = 0                   # cycles where actual direction matched pattern expectation
    misses: int = 0                 # cycles where actual direction contradicted
    validated_by_rl: bool = False
    invalidated: bool = False
    last_checked: str = ""          # ISO date of last validation check

    def to_dict(self) -> dict:
        return {
            "pattern_id":      self.pattern_id,
            "hits":            self.hits,
            "misses":          self.misses,
            "validated_by_rl": self.validated_by_rl,
            "invalidated":     self.invalidated,
            "last_checked":    self.last_checked,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PatternValidationRecord":
        return cls(**d)


@dataclass
class ValidationResult:
    """Result of one validate_pattern() call."""
    pattern_id: str
    was_active: bool                # was the pattern active on the reviewed date?
    direction_matched: bool | None  # None if not active or direction undetermined
    record: PatternValidationRecord


class SeasonalValidator:
    """
    Reads feedback log entries to validate or invalidate seed patterns.

    Usage (called from daily_review.py after Step 8):

        validator = SeasonalValidator(sector="automobile", base_dir="data/predictions")
        active_patterns = calendar.active_patterns_on(review_date)
        for pattern in active_patterns:
            result = validator.validate_pattern(
                pattern=pattern,
                review_date=review_date,
                feedback_log=feedback_log,
            )
        validator.save_state()
    """

    def __init__(
        self,
        sector: str,
        base_dir: str = "data/predictions",
        min_hits: int = MIN_HITS_TO_VALIDATE,
        max_misses: int = MAX_MISSES_TO_INVALIDATE,
    ) -> None:
        self.sector    = sector
        self._path     = Path(base_dir) / sector / "_seasonal_validation.json"
        self._min_hits = min_hits
        self._max_misses = max_misses
        self._state: dict[str, PatternValidationRecord] = self._load_state()

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def _load_state(self) -> dict[str, PatternValidationRecord]:
        if not self._path.exists():
            return {}
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            return {
                pid: PatternValidationRecord.from_dict(rec)
                for pid, rec in raw.items()
            }
        except Exception as exc:
            logger.warning("[SeasonalValidator] Could not load state from %s: %s", self._path, exc)
            return {}

    def save_state(self) -> None:
        """Persist current validation state atomically."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        payload = {pid: rec.to_dict() for pid, rec in self._state.items()}
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(self._path)
        logger.debug("[SeasonalValidator] Saved validation state to %s", self._path)

    def get_record(self, pattern_id: str) -> PatternValidationRecord:
        """Return existing record or a fresh one."""
        if pattern_id not in self._state:
            self._state[pattern_id] = PatternValidationRecord(pattern_id=pattern_id)
        return self._state[pattern_id]

    def load_validation_state(self) -> dict[str, PatternValidationRecord]:
        """Return the full current state dict (read-only for callers)."""
        return dict(self._state)

    # ------------------------------------------------------------------
    # Core validation logic
    # ------------------------------------------------------------------

    def validate_pattern(
        self,
        pattern: SeasonalPattern,
        review_date: date,
        feedback_log: DailyFeedbackLog,
    ) -> ValidationResult:
        """
        Check if the pattern's expected direction matched reality on review_date.

        Expected direction is derived from the net sign of agents_affected:
          net > 0  → pattern predicts UP / positive sentiment
          net < 0  → pattern predicts DOWN / negative sentiment
          net == 0 → volatile / no directional expectation (skip validation)

        Direction match is checked against the FeedbackEntry for review_date.
        """
        record = self.get_record(pattern.id)
        record.last_checked = review_date.isoformat()

        # Determine pattern's net directional expectation
        net_delta = sum(pattern.agents_affected.values())
        if abs(net_delta) < 0.02:
            # Volatile or neutral pattern — no directional validation possible
            return ValidationResult(
                pattern_id=pattern.id,
                was_active=True,
                direction_matched=None,
                record=record,
            )

        expected_up = net_delta > 0

        # Find the feedback entry for this date
        date_str = review_date.isoformat()
        entry = feedback_log.get_entry(date_str)
        if entry is None:
            logger.debug(
                "[SeasonalValidator] No feedback entry for %s on %s — skipping",
                pattern.id, date_str,
            )
            return ValidationResult(
                pattern_id=pattern.id,
                was_active=True,
                direction_matched=None,
                record=record,
            )

        actual_up = entry.actual_direction == "UP"
        matched   = (expected_up == actual_up)

        if matched:
            record.hits += 1
            logger.info(
                "[SeasonalValidator] Pattern %s CONFIRMED on %s "
                "(hits=%d, misses=%d)",
                pattern.id, date_str, record.hits, record.misses,
            )
            if record.hits >= self._min_hits and not record.validated_by_rl:
                record.validated_by_rl = True
                logger.info(
                    "[SeasonalValidator] Pattern %s now VALIDATED by RL "
                    "(%d confirmed cycles)",
                    pattern.id, record.hits,
                )
        else:
            record.misses += 1
            logger.info(
                "[SeasonalValidator] Pattern %s CONTRADICTED on %s "
                "(hits=%d, misses=%d)",
                pattern.id, date_str, record.hits, record.misses,
            )
            if record.misses >= self._max_misses and not record.invalidated:
                record.invalidated = True
                logger.warning(
                    "[SeasonalValidator] Pattern %s INVALIDATED after %d contradictions. "
                    "Will run at half-confidence until RL re-validates.",
                    pattern.id, record.misses,
                )

        return ValidationResult(
            pattern_id=pattern.id,
            was_active=True,
            direction_matched=matched,
            record=record,
        )

    # ------------------------------------------------------------------
    # Helpers for callers
    # ------------------------------------------------------------------

    def is_invalidated(self, pattern_id: str) -> bool:
        rec = self._state.get(pattern_id)
        return rec.invalidated if rec else False

    def is_validated(self, pattern_id: str) -> bool:
        rec = self._state.get(pattern_id)
        return rec.validated_by_rl if rec else False

    def confidence_multiplier(self, pattern_id: str) -> float:
        """
        Return a multiplier to apply to a seed pattern's confidence based on
        its RL validation state:
          Validated   → 1.0  (full confidence)
          Unvalidated → 1.0  (seeds trusted at face value until contradicted)
          Invalidated → 0.5  (run at half-confidence; still active for monitoring)
        """
        if self.is_invalidated(pattern_id):
            return 0.5
        return 1.0

    def summary(self) -> str:
        """Return a human-readable summary of all validation records."""
        if not self._state:
            return "No patterns validated yet."
        lines = [
            f"  {pid}: hits={rec.hits} misses={rec.misses} "
            f"validated={rec.validated_by_rl} invalidated={rec.invalidated} "
            f"last={rec.last_checked}"
            for pid, rec in sorted(self._state.items())
        ]
        return "\n".join(lines)
