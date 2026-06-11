"""
tests/unit/intelligence/rl/test_calibration_reward.py
=======================================================
RL Intelligence Phase, Component 2 — Per-Agent Calibration Reward.

Covers:
  - WeightAdapter._compute_accuracy populates calibration_hits/calibration_total
    per agent based on whether predicted_agent_scores[agent] (>=
    AGENT_BULLISH_THRESHOLD = bullish lean) matched the realized direction.
  - NEUTRAL-verdict days are excluded from the calibration denominator.
  - AgentAccuracy.hit_rate() blends direction_hit_rate and calibration_hit_rate
    using RL_CALIBRATION_WEIGHT when RL_CALIBRATION_REWARD_ENABLED is True.
  - RL_CALIBRATION_REWARD_ENABLED=False reproduces pre-Component-2 behavior
    byte-for-byte (hit_rate == direction_hit_rate, calibration fields stay 0).
  - End-to-end: a month of synthetic entries where agent A is consistently
    calibrated and agent B is consistently anti-calibrated → A's hit_rate >
    B's hit_rate under flag ON, and they're equal under flag OFF.

Target: core/intelligence/rl/agents/weight_adapter.py (_compute_accuracy)
        src/backend/shared/schemas/feedback.py (AgentAccuracy, FeedbackEntry)
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from core.intelligence.rl.agents.weight_adapter import (
    WeightAdapter,
    AGENT_BULLISH_THRESHOLD,
    _BULLISH_VERDICTS,
)
from core.schemas.feedback import (
    AgentAccuracy,
    DailyFeedbackLog,
    FeedbackEntry,
    MissAnalysis,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _entry(
    day: int,
    iso_date: str,
    predicted_verdict: str,
    direction_correct: bool,
    predicted_agent_scores: dict[str, float] | None = None,
    primary_miss_agent: str | None = None,
    actual_direction: str | None = None,
) -> FeedbackEntry:
    """Build a minimal FeedbackEntry for calibration testing.

    actual_direction defaults to the direction implied by the verdict and
    direction_correct, mirroring how daily_review's classify_direction output
    and direction_correct can never disagree in real data: a correct BUY/STRONG
    BUY means the stock went UP, a correct SELL/STRONG SELL means it went DOWN
    (and a miss flips that). Pass actual_direction explicitly (e.g. "FLAT") to
    test cases where the realized move diverges from the verdict.
    """
    miss_analysis = None
    if not direction_correct:
        miss_analysis = MissAnalysis(
            primary_miss_agent=primary_miss_agent or "fundamentals",
            miss_type="direction_flip",
        )
    if actual_direction is None:
        verdict_bullish = predicted_verdict in _BULLISH_VERDICTS
        up_if_correct = verdict_bullish
        actual_up = up_if_correct if direction_correct else not up_if_correct
        actual_direction = "UP" if actual_up else "DOWN"
    return FeedbackEntry(
        day=day,
        date=iso_date,
        predicted_close=100.0,
        actual_close=101.0 if direction_correct else 99.0,
        price_error_pct=1.0 if direction_correct else -1.0,
        predicted_verdict=predicted_verdict,
        actual_direction=actual_direction,
        direction_correct=direction_correct,
        miss_analysis=miss_analysis,
        predicted_agent_scores=predicted_agent_scores or {},
    )


def _log(entries: list[FeedbackEntry], ticker: str = "TEST", cycle_id: str = "2026-06") -> DailyFeedbackLog:
    log = DailyFeedbackLog(ticker=ticker, sector="automobile", cycle_id=cycle_id)
    log.entries = entries
    return log


# ---------------------------------------------------------------------------
# AGENT_BULLISH_THRESHOLD constant
# ---------------------------------------------------------------------------

class TestAgentBullishThreshold:
    def test_threshold_is_half(self):
        assert AGENT_BULLISH_THRESHOLD == 0.5


# ---------------------------------------------------------------------------
# Per-agent calibration hit/miss
# ---------------------------------------------------------------------------

class TestCalibrationHitMiss:
    """
    realized_up = (entry.actual_direction == "UP")
    agent_bullish = predicted_agent_scores[agent] >= AGENT_BULLISH_THRESHOLD
    calibrated = agent_bullish == realized_up
    """

    def setup_method(self):
        self.adapter = WeightAdapter()
        self.ref = date(2026, 6, 11)

    def test_calibrated_agent_accrues_calibration_hit(self):
        # BUY verdict, direction_correct=True → actual_direction="UP" → realized_up=True.
        # agent score 0.7 >= 0.5 → agent_bullish = True → matches realized_up → hit.
        entries = [
            _entry(
                day=1, iso_date="2026-06-10", predicted_verdict="BUY",
                direction_correct=True,
                predicted_agent_scores={"sales_demand": 0.70, "risk_macro": 0.30},
            ),
        ]
        log = _log(entries)
        accuracy = self.adapter._compute_accuracy(log, ["sales_demand", "risk_macro"], reference_date=self.ref)

        # sales_demand: bullish (0.70 >= 0.5) == realized_up (True) → calibrated hit
        assert accuracy["sales_demand"].calibration_total == 1
        assert accuracy["sales_demand"].calibration_hits == 1

        # risk_macro: bullish? 0.30 >= 0.5 is False; realized_up is True → mismatch → no hit
        assert accuracy["risk_macro"].calibration_total == 1
        assert accuracy["risk_macro"].calibration_hits == 0

    def test_anti_calibrated_agent_does_not_accrue_hit(self):
        # SELL verdict, direction_correct=True → actual_direction="DOWN" → realized_up=False
        # (the stock went down as the SELL verdict predicted).
        # agent score 0.8 >= 0.5 → agent_bullish=True → mismatch with realized_up=False → no hit.
        entries = [
            _entry(
                day=1, iso_date="2026-06-10", predicted_verdict="SELL",
                direction_correct=True,
                predicted_agent_scores={"pattern_analysis": 0.80},
            ),
        ]
        log = _log(entries)
        accuracy = self.adapter._compute_accuracy(log, ["pattern_analysis"], reference_date=self.ref)

        assert accuracy["pattern_analysis"].calibration_total == 1
        assert accuracy["pattern_analysis"].calibration_hits == 0

    def test_realized_up_flips_on_miss_day(self):
        # BUY verdict, direction_correct=False → the BUY call missed because the
        # stock actually went DOWN → actual_direction="DOWN" → realized_up=False.
        # agent score 0.2 (bearish lean) matches realized_up=False → calibrated hit.
        entries = [
            _entry(
                day=1, iso_date="2026-06-10", predicted_verdict="BUY",
                direction_correct=False,
                actual_direction="DOWN",
                predicted_agent_scores={"risk_macro": 0.20},
                primary_miss_agent="sales_demand",
            ),
        ]
        log = _log(entries)
        accuracy = self.adapter._compute_accuracy(log, ["risk_macro", "sales_demand"], reference_date=self.ref)

        assert accuracy["risk_macro"].calibration_total == 1
        assert accuracy["risk_macro"].calibration_hits == 1

    def test_agent_with_no_score_on_a_day_excluded_from_that_days_calibration(self):
        entries = [
            _entry(
                day=1, iso_date="2026-06-10", predicted_verdict="BUY",
                direction_correct=True,
                predicted_agent_scores={"sales_demand": 0.70},  # risk_macro absent
            ),
        ]
        log = _log(entries)
        accuracy = self.adapter._compute_accuracy(log, ["sales_demand", "risk_macro"], reference_date=self.ref)

        assert accuracy["sales_demand"].calibration_total == 1
        assert accuracy["risk_macro"].calibration_total == 0
        assert accuracy["risk_macro"].calibration_hits == 0


# ---------------------------------------------------------------------------
# NEUTRAL verdict exclusion
# ---------------------------------------------------------------------------

class TestNeutralExcludedFromCalibration:
    def test_neutral_verdict_day_not_counted_in_denominator(self):
        adapter = WeightAdapter()
        ref = date(2026, 6, 11)
        entries = [
            _entry(
                day=1, iso_date="2026-06-09", predicted_verdict="NEUTRAL",
                direction_correct=True,
                predicted_agent_scores={"sales_demand": 0.70},
            ),
            _entry(
                day=2, iso_date="2026-06-10", predicted_verdict="BUY",
                direction_correct=True,
                predicted_agent_scores={"sales_demand": 0.70},
            ),
        ]
        log = _log(entries)
        accuracy = adapter._compute_accuracy(log, ["sales_demand"], reference_date=ref)

        # Only the BUY day counts toward calibration; the NEUTRAL day is skipped.
        assert accuracy["sales_demand"].calibration_total == 1
        assert accuracy["sales_demand"].calibration_hits == 1
        # But both days still count toward direction totals (existing behavior).
        assert accuracy["sales_demand"].total == 2


# ---------------------------------------------------------------------------
# FLAT realized-direction exclusion
# ---------------------------------------------------------------------------

class TestFlatExcludedFromCalibration:
    def test_flat_day_with_directional_verdict_not_counted_in_denominator(self):
        # Directional (BUY) verdict, but the stock didn't move enough to count
        # as UP or DOWN — actual_direction="FLAT". FLAT carries no directional
        # information, so it must be excluded from the calibration denominator
        # for every agent, exactly like a NEUTRAL verdict.
        adapter = WeightAdapter()
        ref = date(2026, 6, 11)
        entries = [
            _entry(
                day=1, iso_date="2026-06-10", predicted_verdict="BUY",
                direction_correct=False,
                actual_direction="FLAT",
                predicted_agent_scores={"sales_demand": 0.70, "risk_macro": 0.30},
            ),
        ]
        log = _log(entries)
        accuracy = adapter._compute_accuracy(log, ["sales_demand", "risk_macro"], reference_date=ref)

        for agent in ("sales_demand", "risk_macro"):
            assert accuracy[agent].calibration_total == 0
            assert accuracy[agent].calibration_hits == 0

        # Direction totals are unaffected by the FLAT calibration exclusion.
        assert accuracy["sales_demand"].total == 1
        assert accuracy["risk_macro"].total == 1


# ---------------------------------------------------------------------------
# Blend math on AgentAccuracy.hit_rate()
# ---------------------------------------------------------------------------

class TestBlendMath:
    def test_blend_with_w_half_direction_one_calibration_zero(self, monkeypatch):
        import core.config.settings as settings_mod
        monkeypatch.setattr(settings_mod, "RL_CALIBRATION_REWARD_ENABLED", True)
        monkeypatch.setattr(settings_mod, "RL_CALIBRATION_WEIGHT", 0.5)

        acc = AgentAccuracy(
            direction_hits=10, total=10,           # direction_hit_rate = 1.0
            calibration_hits=0, calibration_total=10,  # calibration_hit_rate = 0.0
        )
        # hit_rate = (1 - 0.5) * 1.0 + 0.5 * 0.0 = 0.5
        assert acc.hit_rate() == pytest.approx(0.5)

    def test_blend_with_custom_weight(self, monkeypatch):
        import core.config.settings as settings_mod
        monkeypatch.setattr(settings_mod, "RL_CALIBRATION_REWARD_ENABLED", True)
        monkeypatch.setattr(settings_mod, "RL_CALIBRATION_WEIGHT", 0.25)

        acc = AgentAccuracy(
            direction_hits=10, total=10,             # direction_hit_rate = 1.0
            calibration_hits=2, calibration_total=10,  # calibration_hit_rate = 0.2
        )
        # hit_rate = 0.75 * 1.0 + 0.25 * 0.2 = 0.80
        assert acc.hit_rate() == pytest.approx(0.80)

    def test_no_calibration_observations_falls_back_to_direction_rate(self, monkeypatch):
        import core.config.settings as settings_mod
        monkeypatch.setattr(settings_mod, "RL_CALIBRATION_REWARD_ENABLED", True)
        monkeypatch.setattr(settings_mod, "RL_CALIBRATION_WEIGHT", 0.5)

        acc = AgentAccuracy(direction_hits=7, total=10, calibration_hits=0, calibration_total=0)
        assert acc.hit_rate() == pytest.approx(0.7)


# ---------------------------------------------------------------------------
# Flag OFF → byte-identical to pre-Component-2 behavior
# ---------------------------------------------------------------------------

class TestFlagOffPreservesOldBehavior:
    def test_flag_off_hit_rate_equals_pure_direction_rate(self, monkeypatch):
        import core.config.settings as settings_mod
        monkeypatch.setattr(settings_mod, "RL_CALIBRATION_REWARD_ENABLED", False)

        acc = AgentAccuracy(
            direction_hits=8, total=10,
            calibration_hits=9, calibration_total=10,  # would push hit_rate up if blended
        )
        assert acc.hit_rate() == pytest.approx(0.8)
        assert acc.hit_rate() == acc.direction_hit_rate()

    def test_flag_off_compute_accuracy_does_not_populate_calibration_fields(self, monkeypatch):
        import core.intelligence.rl.agents.weight_adapter as wa_mod
        monkeypatch.setattr(wa_mod.settings, "RL_CALIBRATION_REWARD_ENABLED", False)

        adapter = WeightAdapter()
        ref = date(2026, 6, 11)
        entries = [
            _entry(
                day=1, iso_date="2026-06-10", predicted_verdict="BUY",
                direction_correct=True,
                predicted_agent_scores={"sales_demand": 0.70, "risk_macro": 0.30},
            ),
        ]
        log = _log(entries)
        accuracy = adapter._compute_accuracy(log, ["sales_demand", "risk_macro"], reference_date=ref)

        for agent_acc in accuracy.values():
            assert agent_acc.calibration_hits == 0
            assert agent_acc.calibration_total == 0
            # hit_rate is unaffected — pure direction rate
            assert agent_acc.hit_rate() == agent_acc.direction_hit_rate()


# ---------------------------------------------------------------------------
# Mechanism end-to-end: a month of synthetic entries
# ---------------------------------------------------------------------------

class TestMechanismEndToEnd:
    """
    Build ~21 trading-day-equivalent entries (within WEIGHT_ACCURACY_WINDOW
    lookback — but _window_entries filters by trading days, so use a 7-day
    window matching settings.WEIGHT_ACCURACY_WINDOW=7) where:
      - agent A's predicted_agent_scores always matches the realized direction
        (consistently calibrated).
      - agent B's predicted_agent_scores always opposes the realized direction
        (consistently anti-calibrated).
    Both A and B share the SAME direction_hits/total (ensemble outcome is
    identical for both — neither is ever the primary_miss_agent on a miss day,
    so both get direction credit identically per the existing all-credit logic).

    Under flag ON: A's hit_rate > B's hit_rate (calibration breaks the tie).
    Under flag OFF: A's hit_rate == B's hit_rate (both reduce to direction rate).
    """

    def _build_log(self) -> DailyFeedbackLog:
        entries = []
        base_date = date(2026, 5, 11)  # a Monday
        # 5 trading days (Mon-Fri) — within WEIGHT_ACCURACY_WINDOW=7.
        # Alternate BUY/SELL verdicts, all direction_correct=True so neither
        # agent A nor B is ever the primary_miss_agent (no miss days at all).
        verdicts = ["BUY", "SELL", "BUY", "SELL", "BUY"]
        for i, verdict in enumerate(verdicts):
            d = base_date + timedelta(days=i)
            verdict_bullish = verdict == "BUY"
            # direction_correct=True → realized_up == verdict_bullish
            realized_up = verdict_bullish

            # Agent A: always calibrated (lean matches realized_up)
            a_score = 0.80 if realized_up else 0.20
            # Agent B: always anti-calibrated (lean opposes realized_up)
            b_score = 0.20 if realized_up else 0.80

            entries.append(_entry(
                day=i + 1,
                iso_date=d.isoformat(),
                predicted_verdict=verdict,
                direction_correct=True,
                predicted_agent_scores={"agent_a": a_score, "agent_b": b_score},
            ))
        return _log(entries)

    def test_calibration_on_agent_a_outperforms_agent_b(self, monkeypatch):
        import core.intelligence.rl.agents.weight_adapter as wa_mod
        import core.config.settings as settings_mod
        monkeypatch.setattr(wa_mod.settings, "RL_CALIBRATION_REWARD_ENABLED", True)
        monkeypatch.setattr(settings_mod, "RL_CALIBRATION_REWARD_ENABLED", True)
        monkeypatch.setattr(settings_mod, "RL_CALIBRATION_WEIGHT", 0.5)

        adapter = WeightAdapter()
        log = self._build_log()
        ref = date(2026, 5, 15)  # the Friday — last entry date

        accuracy = adapter._compute_accuracy(log, ["agent_a", "agent_b"], reference_date=ref)

        acc_a = accuracy["agent_a"]
        acc_b = accuracy["agent_b"]

        # Both agents share identical ensemble direction accuracy (no misses at all).
        assert acc_a.direction_hit_rate() == acc_b.direction_hit_rate() == 1.0

        # Agent A is always calibrated; agent B is always anti-calibrated.
        assert acc_a.calibration_hit_rate() == pytest.approx(1.0)
        assert acc_b.calibration_hit_rate() == pytest.approx(0.0)

        # Under flag ON, blended hit_rate diverges: A > B.
        assert acc_a.hit_rate() > acc_b.hit_rate()
        assert acc_a.hit_rate() == pytest.approx(1.0)   # (1-0.5)*1.0 + 0.5*1.0
        assert acc_b.hit_rate() == pytest.approx(0.5)   # (1-0.5)*1.0 + 0.5*0.0

    def test_calibration_off_agent_a_and_b_are_equal(self, monkeypatch):
        import core.intelligence.rl.agents.weight_adapter as wa_mod
        import core.config.settings as settings_mod
        monkeypatch.setattr(wa_mod.settings, "RL_CALIBRATION_REWARD_ENABLED", False)
        monkeypatch.setattr(settings_mod, "RL_CALIBRATION_REWARD_ENABLED", False)

        adapter = WeightAdapter()
        log = self._build_log()
        ref = date(2026, 5, 15)

        accuracy = adapter._compute_accuracy(log, ["agent_a", "agent_b"], reference_date=ref)

        acc_a = accuracy["agent_a"]
        acc_b = accuracy["agent_b"]

        # No calibration data recorded when the flag is off.
        assert acc_a.calibration_total == 0
        assert acc_b.calibration_total == 0

        # hit_rate falls back to identical direction rates for both agents.
        assert acc_a.hit_rate() == acc_b.hit_rate() == pytest.approx(1.0)
