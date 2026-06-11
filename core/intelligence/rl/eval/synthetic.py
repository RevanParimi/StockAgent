"""
core/intelligence/rl/eval/synthetic.py
=======================================
SyntheticLogGenerator — fabricates deterministic, realistic
`(PredictionEnvelope, DailyFeedbackLog)` pairs so the evaluation harness
yields physical numbers without depending on real recorded history.

Determinism
------------
All randomness is drawn from a single `random.Random(seed)` instance created
fresh inside `generate()`. The same `(seed, n_tickers, n_cycles, accuracy_rate,
vol, ablate)` always produces byte-identical Pydantic models. A different seed
(or any other parameter) produces different output.

Schema parity
--------------
The generated `PredictionEnvelope` / `DailyFeedbackLog` objects use the same
`core.schemas.feedback` models as real `PredictionStore` data, with the same
field relationships (`direction_correct` / `actual_direction` /
`price_error_pct` derived consistently with
`core.intelligence.rl.agents.feedback_agent.classify_direction`). The harness
therefore replays synthetic and real data through one identical code path.

Ablation model (synthetic-only — see harness.py for the real-data no-op)
--------------------------------------------------------------------------
Components 2 (`calibration_reward`) and 3 (`forgetting`) don't exist yet, so
there is nothing in the live loop to actually disable. To still let the
harness report a meaningful delta on synthetic data, this generator encodes a
small, documented, deterministic model of what each flag is *expected* to do:

- `"calibration_reward"`: when ablated, the effective `accuracy_rate` used for
  the direction-hit Bernoulli draw is reduced by
  `CALIBRATION_REWARD_ACCURACY_BONUS` (0.05) for every cycle. This represents
  the per-agent calibration credit (Component 2) sharpening the ensemble's
  hit rate uniformly across time.
- `"forgetting"`: when ablated, the effective `accuracy_rate` degrades further
  with each successive cycle (`FORGETTING_DECAY_PER_CYCLE`, 0.03/cycle,
  capped at `FORGETTING_MAX_DECAY`). This represents stale lessons
  accumulating and dragging down later-cycle accuracy when nothing prunes
  them (Component 3).

Both deltas are additive and only ever *reduce* accuracy_rate when the
corresponding key is present in `ablate` — i.e. "ablate" means "simulate the
loop with this improvement turned off", matching the harness's framing of
ablation deltas as (with-feature minus without-feature).
"""
from __future__ import annotations

import random
from datetime import date, timedelta

from core.schemas.feedback import (
    DailyFeedbackLog,
    DailyForecast,
    FeedbackEntry,
    PredictionEnvelope,
)

# ---------------------------------------------------------------------------
# Tunable constants for the ablation model (see module docstring)
# ---------------------------------------------------------------------------
CALIBRATION_REWARD_ACCURACY_BONUS = 0.05
FORGETTING_DECAY_PER_CYCLE = 0.03
FORGETTING_MAX_DECAY = 0.15

_SECTORS = ["automobile", "banking_bfsi", "it_sector", "renewable_energy"]
_TICKERS_BY_SECTOR = {
    "automobile": ["MARUTI", "TATAMOTORS", "M&M", "BAJAJ-AUTO", "HEROMOTOCO"],
    "banking_bfsi": ["HDFCBANK", "ICICIBANK", "SBIN", "AXISBANK", "KOTAKBANK"],
    "it_sector": ["TCS", "INFY", "WIPRO", "HCLTECH", "TECHM"],
    "renewable_energy": ["NTPC", "ADANIGREEN", "TATAPOWER", "SUZLON", "JSWENERGY"],
}

_VERDICTS_BULLISH = ["BUY", "STRONG BUY"]
_VERDICTS_BEARISH = ["SELL", "STRONG SELL"]
_VERDICT_NEUTRAL = "NEUTRAL"

# Single source of truth for direction semantics — keeps synthetic data coupled
# to the live classifier if settings.RL_FLAT_THRESHOLD_PCT ever changes.
from core.intelligence.rl.agents.feedback_agent import classify_direction as _classify_direction
from core.intelligence.rl.agents.feedback_agent import FLAT_THRESHOLD_PCT as _FLAT_THRESHOLD_PCT

_DAYS_PER_CYCLE = 10       # short synthetic cycle keeps generation fast
_BASE_CLOSE = 1000.0


class SyntheticLogGenerator:
    """
    Deterministic fabricator of (PredictionEnvelope, DailyFeedbackLog) pairs.

    Parameters
    ----------
    seed : int
        Seed for the internal `random.Random`. Same seed + same generate()
        arguments => identical output.
    """

    def __init__(self, seed: int = 42) -> None:
        self.seed = seed

    def generate(
        self,
        n_tickers: int = 4,
        n_cycles: int = 1,
        accuracy_rate: float = 0.6,
        vol: float = 1.0,
        ablate: set[str] | list[str] | None = None,
    ) -> list[tuple[PredictionEnvelope, DailyFeedbackLog]]:
        """
        Fabricate `n_tickers * n_cycles` (envelope, feedback_log) pairs.

        Parameters
        ----------
        n_tickers : int
            Number of distinct tickers to fabricate (cycles through the
            built-in sector/ticker roster, wrapping if n_tickers exceeds it).
        n_cycles : int
            Number of monthly cycles per ticker.
        accuracy_rate : float
            Target fraction of days where `direction_correct` is True
            (before ablation adjustments).
        vol : float
            Volatility multiplier controlling the spread of
            `actual_close` around `predicted_close` and the width of the
            [price_lower, price_upper] Monte Carlo band.
        ablate : set[str] | list[str] | None
            Ablation keys to apply to this synthetic run. Recognised keys:
            "calibration_reward", "forgetting" (see module docstring).
            Unrecognised keys are accepted and ignored (no-op), so future
            ablation flags don't break existing callers.

        Returns
        -------
        list[tuple[PredictionEnvelope, DailyFeedbackLog]]
        """
        ablate_set = set(ablate or [])
        rng = random.Random(self.seed)

        roster = self._build_roster(n_tickers)
        pairs: list[tuple[PredictionEnvelope, DailyFeedbackLog]] = []

        for ticker, sector in roster:
            for cycle_idx in range(n_cycles):
                effective_accuracy = self._effective_accuracy_rate(
                    accuracy_rate, cycle_idx, ablate_set
                )
                pairs.append(
                    self._generate_cycle(
                        rng=rng,
                        ticker=ticker,
                        sector=sector,
                        cycle_idx=cycle_idx,
                        accuracy_rate=effective_accuracy,
                        vol=vol,
                    )
                )
        return pairs

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_roster(self, n_tickers: int) -> list[tuple[str, str]]:
        """Deterministically pick (ticker, sector) pairs, wrapping the roster if needed."""
        flat: list[tuple[str, str]] = []
        for sector in _SECTORS:
            for ticker in _TICKERS_BY_SECTOR[sector]:
                flat.append((ticker, sector))

        if n_tickers <= len(flat):
            return flat[:n_tickers]

        # Wrap around with a numeric suffix to keep tickers unique.
        roster = list(flat)
        i = 0
        while len(roster) < n_tickers:
            base_ticker, sector = flat[i % len(flat)]
            wrap_n = i // len(flat) + 1
            roster.append((f"{base_ticker}{wrap_n}", sector))
            i += 1
        return roster

    def _effective_accuracy_rate(
        self, accuracy_rate: float, cycle_idx: int, ablate_set: set[str]
    ) -> float:
        """Apply the documented ablation deltas (see module docstring)."""
        rate = accuracy_rate
        if "calibration_reward" in ablate_set:
            rate -= CALIBRATION_REWARD_ACCURACY_BONUS
        if "forgetting" in ablate_set:
            decay = min(FORGETTING_DECAY_PER_CYCLE * cycle_idx, FORGETTING_MAX_DECAY)
            rate -= decay
        return min(max(rate, 0.0), 1.0)

    def _generate_cycle(
        self,
        rng: random.Random,
        ticker: str,
        sector: str,
        cycle_idx: int,
        accuracy_rate: float,
        vol: float,
    ) -> tuple[PredictionEnvelope, DailyFeedbackLog]:
        cycle_start = date(2026, 1, 1) + timedelta(days=30 * cycle_idx)
        cycle_id = f"{ticker}_{cycle_start.year}-{cycle_start.month:02d}"
        base_close = _BASE_CLOSE * (1.0 + 0.01 * cycle_idx)

        daily_forecasts: list[DailyForecast] = []
        feedback_entries: list[FeedbackEntry] = []

        predicted_close = base_close
        for day in range(1, _DAYS_PER_CYCLE + 1):
            forecast_date = cycle_start + timedelta(days=day)

            # Predicted move for this day (small drift, scaled by vol).
            predicted_change_pct = rng.uniform(-0.5, 0.5) * vol
            predicted_close = round(predicted_close * (1 + predicted_change_pct / 100), 4)

            confidence = round(min(max(rng.uniform(0.4, 0.95), 0.0), 1.0), 4)
            verdict = self._verdict_for_change(predicted_change_pct)

            # Monte Carlo band scales with vol; centred on predicted_close.
            band_half_width_pct = 1.0 * vol
            price_lower = round(predicted_close * (1 - band_half_width_pct / 100), 4)
            price_upper = round(predicted_close * (1 + band_half_width_pct / 100), 4)

            forecast = DailyForecast(
                day=day,
                date=forecast_date.isoformat(),
                predicted_close=predicted_close,
                price_lower=price_lower,
                price_upper=price_upper,
                predicted_change_pct=predicted_change_pct,
                predicted_verdict=verdict,
                confidence=confidence,
            )
            daily_forecasts.append(forecast)

            # Decide whether this day is a "hit" via the seeded RNG.
            is_hit = rng.random() < accuracy_rate

            actual_close, actual_direction = self._actual_close_for_day(
                rng=rng,
                predicted_close=predicted_close,
                verdict=verdict,
                is_hit=is_hit,
                vol=vol,
            )
            price_error_pct = round(
                (actual_close - predicted_close) / predicted_close * 100, 4
            )
            # For NEUTRAL verdicts, "correct" means the actual move stayed FLAT.
            # For BUY/SELL verdicts, correctness is the `is_hit` draw that
            # `_actual_close_for_day` already encoded into actual_close.
            if verdict == _VERDICT_NEUTRAL:
                direction_correct = actual_direction == "FLAT"
            else:
                direction_correct = is_hit

            entry = FeedbackEntry(
                day=day,
                date=forecast_date.isoformat(),
                predicted_close=predicted_close,
                actual_close=actual_close,
                price_error_pct=price_error_pct,
                predicted_verdict=verdict,
                actual_direction=actual_direction,
                direction_correct=bool(direction_correct),
            )
            feedback_entries.append(entry)

        envelope = PredictionEnvelope(
            ticker=ticker,
            sector=sector,
            cycle_id=cycle_id,
            generated_at=cycle_start.isoformat() + "T00:00:00",
            base_close=base_close,
            daily_forecasts=daily_forecasts,
        )
        feedback_log = DailyFeedbackLog(
            ticker=ticker,
            sector=sector,
            cycle_id=cycle_id,
            entries=feedback_entries,
        )
        return envelope, feedback_log

    @staticmethod
    def _verdict_for_change(predicted_change_pct: float) -> str:
        if predicted_change_pct > _FLAT_THRESHOLD_PCT:
            return "BUY"
        if predicted_change_pct < -_FLAT_THRESHOLD_PCT:
            return "SELL"
        return _VERDICT_NEUTRAL

    def _actual_close_for_day(
        self,
        rng: random.Random,
        predicted_close: float,
        verdict: str,
        is_hit: bool,
        vol: float,
    ) -> tuple[float, str]:
        """
        Fabricate `actual_close` such that `_classify_direction(actual,
        predicted)` matches the verdict's implied direction iff `is_hit`.
        """
        move_pct = rng.uniform(0.4, 1.5) * vol  # magnitude of the actual move

        if verdict in _VERDICTS_BULLISH:
            target_up = is_hit
        elif verdict in _VERDICTS_BEARISH:
            target_up = not is_hit
        else:
            # NEUTRAL: a "hit" means the actual move stays FLAT; a "miss"
            # means it moves meaningfully in either direction.
            if is_hit:
                actual_close = round(predicted_close * (1 + rng.uniform(-0.1, 0.1) / 100), 4)
                return actual_close, _classify_direction(actual_close, predicted_close)
            target_up = rng.random() < 0.5

        sign = 1 if target_up else -1
        actual_close = round(predicted_close * (1 + sign * move_pct / 100), 4)
        return actual_close, _classify_direction(actual_close, predicted_close)
