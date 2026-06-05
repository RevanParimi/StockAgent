"""
core/intelligence/seasonal/calendar.py
======================================
SeasonalCalendar — loads pre-seeded sector seasonal patterns from YAML and
merges them with RL-discovered seasonal lessons from the learning ledger.

Two-layer architecture:
  Layer 1 (pre-seeded) — domain knowledge authored once; never auto-deleted.
                          Comes from core/intelligence/seasonal/seeds/{sector}.yaml
  Layer 2 (RL-discovered) — seasonal lessons in the LearningLedger (category="seasonal")
                             Discovered reactively; reinforces or contradicts Layer 1.

Both layers are merged into a SeasonalContext at call time. The context is:
  • Injected per-day into generate_forecast.py to adjust DailyForecast agent scores.
  • Injected into daily_review.py to prevent FeedbackAgent from re-discovering
    what is already a known pattern.

Design decisions:
  • Seed patterns are loaded once and cached class-level — no re-read on every call.
  • lunar_dependency=True patterns have their deltas halved (0.5×) because the exact
    Gregorian date of the pattern is uncertain within the declared month window.
  • Multiple active patterns: agent deltas are summed, then capped at ±MAX_AGENT_DELTA.
  • No pattern can push an agent score outside [0.0, 1.0] — the caller is responsible
    for clamping when applying the deltas to a real score.
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import ClassVar

import yaml
from pydantic import ValidationError

from core.schemas.feedback import (
    LearningLedger,
    Lesson,
    SeasonalContext,
    SeasonalPattern,
)

logger = logging.getLogger(__name__)

# Maximum signed delta any single agent can receive from all active patterns combined.
# Keeps adjustments nudges, not overrides.
MAX_AGENT_DELTA: float = 0.20

# Path to the seeds directory (relative to this file)
_SEEDS_DIR: Path = Path(__file__).parent / "seeds"

# Valid sector names (must match seed file names)
SUPPORTED_SECTORS: frozenset[str] = frozenset(
    {"automobile", "banking_bfsi", "it_sector", "renewable_energy"}
)


class SeasonalCalendar:
    """
    Provides seasonal context for a given date and sector.

    Usage:
        calendar = SeasonalCalendar("automobile")
        ctx = calendar.get_context(date(2026, 12, 10), ledger)
        # ctx.agent_adjustments → {"sales_demand": +0.06, "fundamentals": -0.08}
        # ctx.narrative         → "December model clearance month: ..."
    """

    # Class-level seed cache: sector → list[SeasonalPattern]
    # Populated on first access per sector; never re-loaded unless tests force it.
    _seed_cache: ClassVar[dict[str, list[SeasonalPattern]]] = {}

    def __init__(self, sector: str) -> None:
        if sector not in SUPPORTED_SECTORS:
            logger.warning(
                "[SeasonalCalendar] Unknown sector '%s' — no seeds will load. "
                "Supported: %s",
                sector, sorted(SUPPORTED_SECTORS),
            )
        self.sector = sector
        self._patterns: list[SeasonalPattern] = self._load_seeds(sector)

    # ------------------------------------------------------------------
    # Seed loading
    # ------------------------------------------------------------------

    @classmethod
    def _load_seeds(cls, sector: str) -> list[SeasonalPattern]:
        """Load and cache seed patterns for a sector from YAML."""
        if sector in cls._seed_cache:
            return cls._seed_cache[sector]

        seed_path = _SEEDS_DIR / f"{sector}.yaml"
        if not seed_path.exists():
            logger.info(
                "[SeasonalCalendar] No seed file for sector '%s' at %s", sector, seed_path
            )
            cls._seed_cache[sector] = []
            return []

        try:
            raw = yaml.safe_load(seed_path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            logger.error("[SeasonalCalendar] Failed to parse %s: %s", seed_path, exc)
            cls._seed_cache[sector] = []
            return []

        patterns: list[SeasonalPattern] = []
        for entry in raw.get("patterns", []):
            try:
                patterns.append(SeasonalPattern(**entry))
            except (ValidationError, TypeError) as exc:
                logger.warning(
                    "[SeasonalCalendar] Skipping malformed pattern '%s' in %s: %s",
                    entry.get("id", "?"), seed_path.name, exc,
                )

        cls._seed_cache[sector] = patterns
        logger.info(
            "[SeasonalCalendar] Loaded %d seed patterns for sector '%s'",
            len(patterns), sector,
        )
        return patterns

    @classmethod
    def clear_cache(cls) -> None:
        """Force reload seeds on next access. Used in tests."""
        cls._seed_cache.clear()

    # ------------------------------------------------------------------
    # Active pattern detection
    # ------------------------------------------------------------------

    def _is_active(self, pattern: SeasonalPattern, d: date) -> bool:
        """Return True if the pattern applies to date d."""
        # F&O expiry week patterns are handled exclusively by _get_fno_expiry_context().
        if getattr(pattern, "fno_week_only", False):
            return False
        if d.month not in pattern.months:
            return False
        if pattern.day_range is not None:
            start, end = pattern.day_range
            if not (start <= d.day <= end):
                return False
        return True

    def _active_rl_seasonal_lessons(
        self, ledger: LearningLedger | None
    ) -> list[Lesson]:
        """Return RL-discovered seasonal lessons from the ledger that are still valid."""
        if ledger is None:
            return []
        return [
            l for l in ledger.lessons
            if l.still_valid and l.category == "seasonal"
        ]

    # ------------------------------------------------------------------
    # F&O expiry week context
    # ------------------------------------------------------------------

    def _get_fno_expiry_context(self, d: date) -> dict | None:
        """
        Returns expiry-week adjustment dict if d is in F&O expiry week, else None.
        Keys: 'adjustments' (dict[str, float]) and 'conf_modifier' (float).
        """
        from core.intelligence.rl.nse_calendar import is_fno_expiry_week, is_fno_expiry_day
        if not is_fno_expiry_week(d):
            return None
        adjustments = {"risk_macro": 0.04, "pattern_analysis": 0.03}
        conf_modifier = -0.08 if is_fno_expiry_day(d) else -0.05
        return {"adjustments": adjustments, "conf_modifier": conf_modifier}

    # ------------------------------------------------------------------
    # Core context assembly
    # ------------------------------------------------------------------

    def get_context(
        self,
        target_date: date,
        learning_ledger: LearningLedger | None = None,
    ) -> SeasonalContext:
        """
        Return a SeasonalContext for target_date.

        Merges Layer 1 (seed patterns) + Layer 2 (RL seasonal lessons).
        When no patterns are active, returns a neutral context with
        is_seasonal_period=False — callers can short-circuit.

        Parameters
        ----------
        target_date : date
            The trading date to evaluate.
        learning_ledger : LearningLedger | None
            The ticker's current ledger. If provided, RL seasonal lessons
            are merged into the narrative. If None, only seeds are used.
        """
        active_seeds = [p for p in self._patterns if self._is_active(p, target_date)]
        rl_lessons   = self._active_rl_seasonal_lessons(learning_ledger)
        fno_ctx      = self._get_fno_expiry_context(target_date)

        if not active_seeds and not rl_lessons and not fno_ctx:
            return SeasonalContext(target_date=target_date, is_seasonal_period=False)

        # ----- merge agent adjustments from seeds -----
        merged: dict[str, float] = {}
        for pattern in active_seeds:
            # Halve deltas for lunar-dependent patterns — exact Gregorian date uncertain
            multiplier = 0.5 if pattern.lunar_dependency else 1.0
            for agent, raw_delta in pattern.agents_affected.items():
                adjusted = raw_delta * multiplier
                merged[agent] = merged.get(agent, 0.0) + adjusted

        # Cap each agent's total delta at ±MAX_AGENT_DELTA
        merged = {
            agent: max(-MAX_AGENT_DELTA, min(MAX_AGENT_DELTA, delta))
            for agent, delta in merged.items()
        }

        # ----- confidence modifier -----
        # Patterns with net-positive adjustments slightly boost confidence;
        # net-negative adjustments slightly reduce it.
        # Formula: Σ (confidence × ±0.04/0.05) per pattern, capped at ±0.10.
        conf_modifier = 0.0
        for pattern in active_seeds:
            net = sum(pattern.agents_affected.values())
            if net > 0:
                conf_modifier += pattern.confidence * 0.05
            elif net < 0:
                conf_modifier -= pattern.confidence * 0.04
        conf_modifier = round(max(-0.10, min(0.10, conf_modifier)), 4)

        # ----- narrative -----
        seed_narratives = [p.narrative.strip() for p in active_seeds]
        rl_narratives   = [
            f"[RL lesson {l.lesson_id}] {l.rule}"
            for l in rl_lessons
        ]
        all_narratives = seed_narratives + rl_narratives

        # ----- F&O expiry week overlay -----
        if fno_ctx:
            from core.intelligence.rl.nse_calendar import is_fno_expiry_day
            for agent, delta in fno_ctx["adjustments"].items():
                merged[agent] = merged.get(agent, 0.0) + delta
            # Cap again after adding F&O deltas
            merged = {
                agent: max(-MAX_AGENT_DELTA, min(MAX_AGENT_DELTA, delta))
                for agent, delta in merged.items()
            }
            conf_modifier = round(
                max(-0.10, min(0.10, conf_modifier + fno_ctx["conf_modifier"])), 4
            )
            fno_narrative = (
                "F&O expiry DAY — maximum OI unwinding risk; price pinning near max pain likely."
                if is_fno_expiry_day(target_date)
                else "F&O expiry week — elevated volatility, options pinning dynamics active."
            )
            all_narratives.append(fno_narrative)

        combined = " | ".join(all_narratives) if all_narratives else ""

        return SeasonalContext(
            target_date=target_date,
            active_pattern_ids=[p.id for p in active_seeds],
            active_rl_lesson_ids=[l.lesson_id for l in rl_lessons],
            agent_adjustments=merged,
            narrative=combined,
            confidence_modifier=conf_modifier,
            is_seasonal_period=True,
        )

    # ------------------------------------------------------------------
    # Convenience: list all patterns for the given month
    # ------------------------------------------------------------------

    def patterns_for_month(self, month: int) -> list[SeasonalPattern]:
        """Return all seed patterns that include this month."""
        return [p for p in self._patterns if month in p.months]

    def active_patterns_on(self, d: date) -> list[SeasonalPattern]:
        """Return all seed patterns active on date d."""
        return [p for p in self._patterns if self._is_active(p, d)]
