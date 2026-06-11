"""
tests/unit/intelligence/rl/test_forgetting.py
==============================================
RL Intelligence Phase, Component 3 — Forgetting & Recency.

Covers:
  (a) LearningLedger.recency_weighted_miss_scores() + PromptEnhancer.enhance()
      ranking by recency-weighted score instead of raw miss_counter.
  (b) ledger_propagator.archive_stale_lessons() + resurrect_lesson() — cold
      store archival of invalidated, low-value, stale lessons with
      resurrection on re-occurrence.
  (c) PredictionStore.load_recent_feedback_entries(recency_weighted=True) +
      PriceInterpolator.compute_historical_avg_return() weighted median.
  Accuracy invariance — forgetting changes ONLY ranking/archival/interpolation
  weighting, never the direction_accuracy metric.

All file I/O uses tmp_path — never data/predictions.
"""

from __future__ import annotations

import json
import math
from datetime import date, timedelta

import pytest

from core.intelligence.prompt_enhancer.enhancer import PromptEnhancer
from core.intelligence.rl.algorithms.price_interpolator import compute_historical_avg_return
from core.intelligence.rl.eval.metrics import direction_accuracy
from core.intelligence.rl.stores.ledger_propagator import (
    archive_stale_lessons,
    resurrect_lesson,
)
from core.intelligence.rl.stores.prediction_store import PredictionStore
from core.schemas.feedback import (
    DailyFeedbackLog,
    FeedbackAgentOutput,
    FeedbackEntry,
    LearningLedger,
    Lesson,
    MissAnalysis,
    MissEvent,
    RawLesson,
    TimingAccuracy,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ledger(**kwargs) -> LearningLedger:
    base = dict(ticker="MARUTI", sector="automobile", last_updated=date.today().isoformat())
    base.update(kwargs)
    return LearningLedger(**base)


def _miss_event(days_ago: int, miss_type: str = "model_bias", cycle_id: str = "MARUTI_2026-05") -> MissEvent:
    d = (date.today() - timedelta(days=days_ago)).isoformat()
    return MissEvent(date=d, miss_type=miss_type, cycle_id=cycle_id)


def _lesson(
    lesson_id: str = "L001",
    pattern: str = "RBI_policy_day",
    category: str = "macro",
    confidence: float = 0.5,
    occurrences: int = 1,
    still_valid: bool = True,
    last_seen: str | None = None,
    date_learned: str | None = None,
    semantic_tags: list[str] | None = None,
) -> Lesson:
    today_str = date.today().isoformat()
    return Lesson(
        lesson_id=lesson_id,
        date_learned=date_learned or today_str,
        category=category,
        pattern=pattern,
        observation="obs",
        rule="rule",
        confidence=confidence,
        occurrences=occurrences,
        still_valid=still_valid,
        last_seen=last_seen if last_seen is not None else today_str,
        semantic_tags=semantic_tags or [],
    )


def _feedback_entry(
    day: int,
    iso_date: str,
    predicted_verdict: str = "BUY",
    direction_correct: bool = True,
    actual_direction: str = "UP",
    price_error_pct: float = 1.0,
    actual_close: float = 101.0,
    predicted_close: float = 100.0,
) -> FeedbackEntry:
    return FeedbackEntry(
        day=day,
        date=iso_date,
        predicted_close=predicted_close,
        actual_close=actual_close,
        price_error_pct=price_error_pct,
        predicted_verdict=predicted_verdict,
        actual_direction=actual_direction,
        direction_correct=direction_correct,
    )


# ---------------------------------------------------------------------------
# (a) Recency-weighted miss ranking — LearningLedger.recency_weighted_miss_scores
# ---------------------------------------------------------------------------

class TestRecencyWeightedMissScores:
    def test_recent_miss_outranks_old_frequent_miss(self):
        """
        factor X: 5 misses 90 days ago.
        factor Y: 2 misses this week.
        Y should score higher than X (recency dominates raw frequency).
        """
        ledger = _ledger(
            miss_counter={"factor_X": 5, "factor_Y": 2},
            miss_events={
                "factor_X": [_miss_event(90, "model_bias") for _ in range(5)],
                "factor_Y": [_miss_event(1, "model_bias"), _miss_event(2, "model_bias")],
            },
        )
        scores = ledger.recency_weighted_miss_scores()
        assert scores["factor_Y"] > scores["factor_X"]

    def test_external_shock_discounted(self):
        """
        Two factors with identical recency/count, but one is all
        external_shock (non-penalizable) — it should score lower by
        the MISS_PENALIZABLE_DISCOUNT factor (0.3).
        """
        ledger = _ledger(
            miss_counter={"factor_bias": 2, "factor_shock": 2},
            miss_events={
                "factor_bias":  [_miss_event(1, "model_bias"), _miss_event(2, "model_bias")],
                "factor_shock": [_miss_event(1, "external_shock"), _miss_event(2, "external_shock")],
            },
        )
        scores = ledger.recency_weighted_miss_scores()
        assert scores["factor_shock"] == pytest.approx(scores["factor_bias"] * 0.3)

    def test_empty_miss_events_falls_back_to_miss_counter(self):
        """Legacy ledger: miss_events empty, miss_counter populated."""
        ledger = _ledger(miss_counter={"factor_A": 5, "factor_B": 2}, miss_events={})
        scores = ledger.recency_weighted_miss_scores()
        assert scores["factor_A"] == 5.0
        assert scores["factor_B"] == 2.0
        # ranking matches raw miss_counter ranking
        assert sorted(scores, key=scores.get, reverse=True) == ["factor_A", "factor_B"]

    def test_halflife_decay_value(self):
        """A single miss exactly HALFLIFE days ago scores ~0.5 (for penalizable types)."""
        from core.config import settings
        halflife = settings.MISS_RECENCY_HALFLIFE_DAYS
        ledger = _ledger(
            miss_counter={"factor_A": 1},
            miss_events={"factor_A": [_miss_event(int(halflife), "model_bias")]},
        )
        scores = ledger.recency_weighted_miss_scores()
        assert scores["factor_A"] == pytest.approx(math.exp(-1.0), rel=0.05)


# ---------------------------------------------------------------------------
# (a) PromptEnhancer ranking shift between flag on/off
# ---------------------------------------------------------------------------

class TestPromptEnhancerRecencyRanking:
    def _build_ledger(self) -> LearningLedger:
        """
        Two factors:
          - FII_outflow_spike: 5 misses, all ~90 days ago (old, frequent)
          - crude_oil_spot_price: 1 miss, this week (recent, rare)

        miss_counter ranking (flag off): FII_outflow_spike (5) > crude_oil_spot_price (1)
        recency-weighted ranking (flag on): crude_oil_spot_price should outrank
        FII_outflow_spike since its single miss is recent vs FII's misses being old.
        """
        return _ledger(
            miss_counter={"FII_outflow_spike": 5, "crude_oil_spot_price": 1},
            miss_events={
                "FII_outflow_spike": [_miss_event(90, "model_bias") for _ in range(5)],
                "crude_oil_spot_price": [_miss_event(1, "model_bias")],
            },
        )

    def test_top_factor_changes_with_flag(self, monkeypatch):
        import core.config.settings as settings_mod
        ledger = self._build_ledger()

        # Flag ON → recency-weighted ranking
        monkeypatch.setattr(settings_mod, "RL_FORGETTING_ENABLED", True)
        result_on = PromptEnhancer().enhance("MARUTI", ledger, sector="automobile", top_n=1)

        # Flag OFF → raw miss_counter ranking
        monkeypatch.setattr(settings_mod, "RL_FORGETTING_ENABLED", False)
        result_off = PromptEnhancer().enhance("MARUTI", ledger, sector="automobile", top_n=1)

        # Both produce some output (both factors have templates), but the
        # SET of queries selected should differ because the top-1 factor differs.
        assert result_on != result_off

    def test_flag_off_uses_miss_counter_order(self, monkeypatch):
        import core.config.settings as settings_mod
        monkeypatch.setattr(settings_mod, "RL_FORGETTING_ENABLED", False)
        ledger = self._build_ledger()

        result = PromptEnhancer().enhance("MARUTI", ledger, sector="automobile", top_n=1)
        # top_n=1 with flag off picks FII_outflow_spike (miss_counter=5, the max)
        all_queries = " ".join(q for queries in result.values() for q in queries).lower()
        assert "fii" in all_queries or "dii" in all_queries

    def test_flag_on_uses_recency_weighted_order(self, monkeypatch):
        import core.config.settings as settings_mod
        monkeypatch.setattr(settings_mod, "RL_FORGETTING_ENABLED", True)
        ledger = self._build_ledger()

        result = PromptEnhancer().enhance("MARUTI", ledger, sector="automobile", top_n=1)
        # top_n=1 with flag on picks crude_oil_spot_price (recent miss outranks
        # FII_outflow_spike's old misses)
        all_queries = " ".join(q for queries in result.values() for q in queries).lower()
        assert "crude" in all_queries or "brent" in all_queries


# ---------------------------------------------------------------------------
# (b) Lesson archival
# ---------------------------------------------------------------------------

class TestLessonArchival:
    def test_lesson_meeting_all_criteria_is_archived(self, tmp_path):
        cold_store = tmp_path / "MARUTI_archived_lessons.json"
        old_date = (date.today() - timedelta(days=100)).isoformat()
        lesson = _lesson(
            lesson_id="L001",
            pattern="dead_pattern",
            category="global_macro",   # fast decay → low effective_confidence
            confidence=0.10,
            occurrences=1,
            still_valid=False,
            last_seen=old_date,
            date_learned=old_date,
        )
        ledger = _ledger(
            lessons=[lesson],
            miss_counter={"dead_pattern": 10},
            correction_counter={"dead_pattern": 0},
        )

        n = archive_stale_lessons(ledger, cold_store)

        assert n == 1
        assert ledger.lessons == []
        assert cold_store.exists()
        data = json.loads(cold_store.read_text())
        archived_patterns = [l["pattern"] for l in data["archived_lessons"]]
        assert "dead_pattern" in archived_patterns

    def test_lesson_failing_confidence_floor_stays(self, tmp_path):
        """High confidence (above floor) → not archived even if stale + ineffective."""
        cold_store = tmp_path / "MARUTI_archived_lessons.json"
        old_date = (date.today() - timedelta(days=100)).isoformat()
        lesson = _lesson(
            lesson_id="L001",
            pattern="strong_pattern",
            category="seasonal",       # decay-exempt → confidence stays at 0.9
            confidence=0.9,
            occurrences=5,
            still_valid=False,
            last_seen=old_date,
            date_learned=old_date,
        )
        ledger = _ledger(
            lessons=[lesson],
            miss_counter={"strong_pattern": 10},
            correction_counter={"strong_pattern": 0},
        )

        n = archive_stale_lessons(ledger, cold_store)

        assert n == 0
        assert len(ledger.lessons) == 1
        assert not cold_store.exists()

    def test_lesson_failing_effectiveness_floor_stays(self, tmp_path):
        """Effectiveness >= floor → not archived even if low confidence + stale."""
        cold_store = tmp_path / "MARUTI_archived_lessons.json"
        old_date = (date.today() - timedelta(days=100)).isoformat()
        lesson = _lesson(
            lesson_id="L001",
            pattern="effective_pattern",
            category="global_macro",
            confidence=0.10,
            occurrences=1,
            still_valid=False,
            last_seen=old_date,
            date_learned=old_date,
        )
        # effectiveness = correction / (correction + miss) = 8 / (8 + 2) = 0.8 >= 0.25
        ledger = _ledger(
            lessons=[lesson],
            miss_counter={"effective_pattern": 2},
            correction_counter={"effective_pattern": 8},
        )

        n = archive_stale_lessons(ledger, cold_store)

        assert n == 0
        assert len(ledger.lessons) == 1

    def test_lesson_failing_staleness_floor_stays(self, tmp_path):
        """Recently seen → not archived even if low confidence + low effectiveness."""
        cold_store = tmp_path / "MARUTI_archived_lessons.json"
        recent_date = date.today().isoformat()
        lesson = _lesson(
            lesson_id="L001",
            pattern="recent_pattern",
            category="global_macro",
            confidence=0.10,
            occurrences=1,
            still_valid=False,
            last_seen=recent_date,
            date_learned=recent_date,
        )
        ledger = _ledger(
            lessons=[lesson],
            miss_counter={"recent_pattern": 10},
            correction_counter={"recent_pattern": 0},
        )

        n = archive_stale_lessons(ledger, cold_store)

        assert n == 0
        assert len(ledger.lessons) == 1

    def test_still_valid_lessons_never_archived(self, tmp_path):
        """still_valid=True → never archived regardless of other criteria."""
        cold_store = tmp_path / "MARUTI_archived_lessons.json"
        old_date = (date.today() - timedelta(days=100)).isoformat()
        lesson = _lesson(
            lesson_id="L001",
            pattern="valid_pattern",
            category="global_macro",
            confidence=0.10,
            occurrences=1,
            still_valid=True,    # still valid!
            last_seen=old_date,
            date_learned=old_date,
        )
        ledger = _ledger(
            lessons=[lesson],
            miss_counter={"valid_pattern": 10},
            correction_counter={"valid_pattern": 0},
        )

        n = archive_stale_lessons(ledger, cold_store)

        assert n == 0
        assert len(ledger.lessons) == 1
        assert not cold_store.exists()

    def test_zero_zero_effectiveness_treated_as_zero(self, tmp_path):
        """0/0 effectiveness (no correction, no miss) → treated as 0.0 (archivable)."""
        cold_store = tmp_path / "MARUTI_archived_lessons.json"
        old_date = (date.today() - timedelta(days=100)).isoformat()
        lesson = _lesson(
            lesson_id="L001",
            pattern="untested_pattern",
            category="global_macro",
            confidence=0.10,
            occurrences=1,
            still_valid=False,
            last_seen=old_date,
            date_learned=old_date,
        )
        ledger = _ledger(lessons=[lesson], miss_counter={}, correction_counter={})

        n = archive_stale_lessons(ledger, cold_store)

        assert n == 1
        assert ledger.lessons == []


# ---------------------------------------------------------------------------
# (b) Resurrection
# ---------------------------------------------------------------------------

class TestLessonResurrection:
    def test_resurrect_by_pattern_preserves_occurrences(self, tmp_path):
        cold_store = tmp_path / "MARUTI_archived_lessons.json"
        archived = _lesson(
            lesson_id="L005",
            pattern="RBI_policy_day",
            confidence=0.40,
            occurrences=7,
            still_valid=False,
        )
        archived.invalidation_reason = "3 consecutive contradictions"
        archived.invalidation_streak = 3
        # Pre-populate cold store
        cold_store.write_text(json.dumps({
            "ticker": "MARUTI", "sector": "automobile",
            "archived_lessons": [archived.model_dump()],
        }))

        ledger = _ledger(lessons=[])
        restored = resurrect_lesson(ledger, cold_store, pattern="RBI_policy_day", new_confidence=0.5)

        assert restored is not None
        assert restored.occurrences == 7   # history preserved
        assert restored.still_valid is True
        assert restored.last_seen == date.today().isoformat()
        assert restored.invalidation_streak == 0
        assert restored.invalidation_reason == ""
        # confidence = max(old*0.8, new) = max(0.32, 0.5) = 0.5
        assert restored.confidence == pytest.approx(0.5)
        assert ledger.lessons == [restored]

        # Cold store should no longer contain the resurrected lesson
        data = json.loads(cold_store.read_text())
        assert data["archived_lessons"] == []

    def test_resurrect_confidence_floor_from_old(self, tmp_path):
        """confidence = max(old*0.8, new) — old*0.8 wins when it's larger."""
        cold_store = tmp_path / "MARUTI_archived_lessons.json"
        archived = _lesson(lesson_id="L005", pattern="RBI_policy_day", confidence=0.80, occurrences=3, still_valid=False)
        cold_store.write_text(json.dumps({
            "ticker": "MARUTI", "sector": "automobile",
            "archived_lessons": [archived.model_dump()],
        }))
        ledger = _ledger(lessons=[])
        restored = resurrect_lesson(ledger, cold_store, pattern="RBI_policy_day", new_confidence=0.3)
        # max(0.80*0.8, 0.3) = max(0.64, 0.3) = 0.64
        assert restored.confidence == pytest.approx(0.64)

    def test_no_match_returns_none(self, tmp_path):
        cold_store = tmp_path / "MARUTI_archived_lessons.json"
        archived = _lesson(lesson_id="L005", pattern="some_other_pattern", still_valid=False)
        cold_store.write_text(json.dumps({
            "ticker": "MARUTI", "sector": "automobile",
            "archived_lessons": [archived.model_dump()],
        }))
        ledger = _ledger(lessons=[])
        restored = resurrect_lesson(ledger, cold_store, pattern="RBI_policy_day", new_confidence=0.5)
        assert restored is None
        assert ledger.lessons == []

    def test_no_cold_store_file_returns_none(self, tmp_path):
        cold_store = tmp_path / "MARUTI_archived_lessons.json"  # does not exist
        ledger = _ledger(lessons=[])
        restored = resurrect_lesson(ledger, cold_store, pattern="RBI_policy_day", new_confidence=0.5)
        assert restored is None

    def test_merge_lessons_into_ledger_resurrects_instead_of_duplicating(self, tmp_path):
        """
        feedback_agent.merge_lessons_into_ledger: a NEW lesson from the LLM
        with the same `pattern` as a previously-archived lesson should restore
        the archived one (occurrences preserved) rather than create a duplicate.
        """
        from core.intelligence.rl.agents.feedback_agent import FeedbackAgent

        cold_store = tmp_path / "MARUTI_archived_lessons.json"
        archived = _lesson(
            lesson_id="L009",
            pattern="dealer_inventory_flush",
            confidence=0.30,
            occurrences=4,
            still_valid=False,
        )
        cold_store.write_text(json.dumps({
            "ticker": "MARUTI", "sector": "automobile",
            "archived_lessons": [archived.model_dump()],
        }))

        ledger = _ledger(lessons=[])
        output = FeedbackAgentOutput(
            primary_miss_agent="sales_demand",
            miss_type="model_bias",
            new_lessons=[
                RawLesson(
                    category="seasonal",
                    pattern="dealer_inventory_flush",
                    observation="dealer inventory spike again",
                    rule="discount sales_demand near month-end",
                    confidence=0.55,
                    scope="stock_specific",
                ),
            ],
        )

        agent = FeedbackAgent.__new__(FeedbackAgent)  # bypass __init__ (no LLM client needed)
        updated_ledger, lesson_ids = agent.merge_lessons_into_ledger(
            output, ledger, cold_store_path=cold_store
        )

        assert len(updated_ledger.lessons) == 1   # no duplicate created
        restored = updated_ledger.lessons[0]
        assert restored.lesson_id == "L009"
        assert restored.occurrences == 4          # history preserved
        assert restored.still_valid is True
        assert lesson_ids == ["L009"]

    def test_merge_lessons_into_ledger_no_cold_store_path_unchanged(self):
        """cold_store_path=None (default) — behavior unchanged from before Component 3."""
        from core.intelligence.rl.agents.feedback_agent import FeedbackAgent

        ledger = _ledger(lessons=[])
        output = FeedbackAgentOutput(
            primary_miss_agent="sales_demand",
            miss_type="model_bias",
            new_lessons=[
                RawLesson(
                    category="seasonal",
                    pattern="brand_new_pattern",
                    observation="obs",
                    rule="rule",
                    confidence=0.55,
                    scope="stock_specific",
                ),
            ],
        )
        agent = FeedbackAgent.__new__(FeedbackAgent)
        updated_ledger, lesson_ids = agent.merge_lessons_into_ledger(output, ledger)

        assert len(updated_ledger.lessons) == 1
        assert updated_ledger.lessons[0].pattern == "brand_new_pattern"
        assert updated_ledger.lessons[0].lesson_id == "L001"


# ---------------------------------------------------------------------------
# (c) Recency-weighted feedback aggregation
# ---------------------------------------------------------------------------

class TestRecencyWeightedFeedbackAggregation:
    def _make_feedback_log_file(self, ticker, cycle_id, rows, tmp_dir, sector="automobile"):
        entries = []
        for i, row in enumerate(rows):
            entries.append(
                FeedbackEntry(
                    day=i + 1,
                    date=row["date"],
                    predicted_close=100.0,
                    actual_close=row["actual_close"],
                    price_error_pct=row["price_error_pct"],
                    predicted_verdict=row["verdict"],
                    actual_direction="UP" if row["price_error_pct"] >= 0 else "DOWN",
                    direction_correct=True,
                )
            )
        log = DailyFeedbackLog(ticker=ticker, cycle_id=cycle_id, sector=sector, entries=entries)
        sector_dir = tmp_dir / sector / ticker
        sector_dir.mkdir(parents=True, exist_ok=True)
        log_path = sector_dir / f"{cycle_id}_daily_feedback_log.json"
        log_path.write_text(log.model_dump_json())
        return log_path

    def test_current_cycle_weight_is_one(self, tmp_path, monkeypatch):
        from unittest.mock import patch

        self._make_feedback_log_file("MARUTI", "MARUTI_2026-06", [
            {"date": "2026-06-01", "actual_close": 101.0, "price_error_pct": 1.0, "verdict": "BUY"},
        ], tmp_path)

        with patch("core.intelligence.rl.stores.prediction_store.settings") as ms:
            ms.PREDICTION_DATA_DIR = str(tmp_path)
            ms.FEEDBACK_HALFLIFE_MONTHS = 3.0
            store = PredictionStore("MARUTI", sector="automobile")
            weighted = store.load_recent_feedback_entries(n_cycles=6, recency_weighted=True)

        assert len(weighted) == 1
        entry, weight = weighted[0]
        assert weight == pytest.approx(1.0)

    def test_three_cycles_old_weight_approx_exp_minus_one(self, tmp_path):
        from unittest.mock import patch

        # Most recent cycle first when sorted descending: 2026-06 (age 0), ...
        # 2026-03 (age 3) for halflife=3 → exp(-3/3) = exp(-1)
        self._make_feedback_log_file("MARUTI", "MARUTI_2026-03", [
            {"date": "2026-03-01", "actual_close": 99.0, "price_error_pct": -1.0, "verdict": "SELL"},
        ], tmp_path)
        self._make_feedback_log_file("MARUTI", "MARUTI_2026-04", [
            {"date": "2026-04-01", "actual_close": 100.0, "price_error_pct": 0.0, "verdict": "NEUTRAL"},
        ], tmp_path)
        self._make_feedback_log_file("MARUTI", "MARUTI_2026-05", [
            {"date": "2026-05-01", "actual_close": 100.5, "price_error_pct": 0.5, "verdict": "BUY"},
        ], tmp_path)
        self._make_feedback_log_file("MARUTI", "MARUTI_2026-06", [
            {"date": "2026-06-01", "actual_close": 101.0, "price_error_pct": 1.0, "verdict": "BUY"},
        ], tmp_path)

        with patch("core.intelligence.rl.stores.prediction_store.settings") as ms:
            ms.PREDICTION_DATA_DIR = str(tmp_path)
            ms.FEEDBACK_HALFLIFE_MONTHS = 3.0
            store = PredictionStore("MARUTI", sector="automobile")
            weighted = store.load_recent_feedback_entries(n_cycles=6, recency_weighted=True)

        # 4 cycles, sorted descending by filename → ages 0, 1, 2, 3
        weights_by_date = {entry.date: w for entry, w in weighted}
        assert weights_by_date["2026-06-01"] == pytest.approx(1.0)
        assert weights_by_date["2026-03-01"] == pytest.approx(math.exp(-1), rel=1e-6)

    def test_default_call_signature_returns_plain_entries_unchanged(self, tmp_path):
        """recency_weighted defaults to False — output identical to pre-Component-3."""
        from unittest.mock import patch

        self._make_feedback_log_file("MARUTI", "MARUTI_2026-03", [
            {"date": "2026-03-10", "actual_close": 102.0, "price_error_pct": 2.0, "verdict": "BUY"},
            {"date": "2026-03-11", "actual_close": 98.0,  "price_error_pct": -2.0, "verdict": "BUY"},
        ], tmp_path)
        self._make_feedback_log_file("MARUTI", "MARUTI_2026-04", [
            {"date": "2026-04-10", "actual_close": 103.0, "price_error_pct": 3.0, "verdict": "BUY"},
        ], tmp_path)

        with patch("core.intelligence.rl.stores.prediction_store.settings") as ms:
            ms.PREDICTION_DATA_DIR = str(tmp_path)
            ms.FEEDBACK_HALFLIFE_MONTHS = 3.0
            store = PredictionStore("MARUTI", sector="automobile")
            default_call = store.load_recent_feedback_entries(n_cycles=6)
            explicit_false = store.load_recent_feedback_entries(n_cycles=6, recency_weighted=False)

        assert len(default_call) == 3
        assert all(isinstance(e, FeedbackEntry) for e in default_call)
        assert [e.date for e in default_call] == [e.date for e in explicit_false]
        assert [e.model_dump() for e in default_call] == [e.model_dump() for e in explicit_false]


# ---------------------------------------------------------------------------
# (c) PriceInterpolator.compute_historical_avg_return weighted median
# ---------------------------------------------------------------------------

class TestComputeHistoricalAvgReturnWeighted:
    def test_weighted_input_shifts_median_toward_recent(self, monkeypatch):
        import core.config.settings as settings_mod
        monkeypatch.setattr(settings_mod, "RL_FORGETTING_ENABLED", True)

        # Old entries cluster around 5.0%, recent entries cluster around 1.0%.
        old_entries = [
            _feedback_entry(i + 1, f"2026-01-{10+i:02d}", price_error_pct=5.0)
            for i in range(5)
        ]
        recent_entries = [
            _feedback_entry(i + 1, f"2026-06-{10+i:02d}", price_error_pct=1.0)
            for i in range(5)
        ]
        # weight old entries low, recent entries high
        weighted = [(e, 0.05) for e in old_entries] + [(e, 1.0) for e in recent_entries]

        result = compute_historical_avg_return(weighted, "BUY")
        # Weighted median should be pulled toward the recent cluster (1.0)
        assert result == pytest.approx(1.0)

    def test_unweighted_plain_list_unchanged(self):
        """Plain list of FeedbackEntry (no tuples) — unweighted median, same as before."""
        entries = [
            _feedback_entry(i + 1, f"2026-03-{10+i:02d}", price_error_pct=float(i + 1))
            for i in range(5)
        ]
        result = compute_historical_avg_return(entries, "BUY")
        assert result == pytest.approx(3.0)  # median of 1,2,3,4,5

    def test_flag_off_ignores_weights(self, monkeypatch):
        """RL_FORGETTING_ENABLED=False — even tuple input falls back to unweighted median."""
        import core.config.settings as settings_mod
        monkeypatch.setattr(settings_mod, "RL_FORGETTING_ENABLED", False)

        entries = [
            _feedback_entry(i + 1, f"2026-03-{10+i:02d}", price_error_pct=float(i + 1))
            for i in range(5)
        ]
        weighted = [(e, 0.01) for e in entries[:4]] + [(entries[4], 100.0)]

        result_weighted = compute_historical_avg_return(weighted, "BUY")
        result_plain = compute_historical_avg_return(entries, "BUY")
        assert result_weighted == result_plain == pytest.approx(3.0)

    def test_empty_list_returns_none(self):
        assert compute_historical_avg_return([], "BUY") is None

    def test_none_returns_none(self):
        assert compute_historical_avg_return(None, "BUY") is None


# ---------------------------------------------------------------------------
# Accuracy invariance — forgetting must not change direction_accuracy
# ---------------------------------------------------------------------------

class TestAccuracyInvariance:
    def test_direction_accuracy_identical_flag_on_off(self, monkeypatch):
        """
        direction_accuracy is computed purely from FeedbackEntry.direction_correct,
        which forgetting (ranking/archival/interpolation weighting) never touches.
        """
        import core.config.settings as settings_mod

        entries = [
            _feedback_entry(1, "2026-06-01", direction_correct=True),
            _feedback_entry(2, "2026-06-02", direction_correct=False),
            _feedback_entry(3, "2026-06-03", direction_correct=True),
            _feedback_entry(4, "2026-06-04", direction_correct=True),
            _feedback_entry(5, "2026-06-05", direction_correct=False),
        ]

        monkeypatch.setattr(settings_mod, "RL_FORGETTING_ENABLED", True)
        acc_on = direction_accuracy(entries)

        monkeypatch.setattr(settings_mod, "RL_FORGETTING_ENABLED", False)
        acc_off = direction_accuracy(entries)

        assert acc_on == acc_off == pytest.approx(3 / 5)
