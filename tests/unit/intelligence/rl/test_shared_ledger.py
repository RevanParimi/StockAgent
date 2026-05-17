"""
tests/unit/test_shared_ledger.py
=================================
Unit tests for P2 — Shared Sector + Market Ledger Propagation.

Coverage:
  - PredictionStore sector-aware path construction
  - PredictionStore: load/save sector ledger, market ledger, load_all_ledgers
  - Empty-ledger defaults (file missing → empty, not error)
  - LedgerPropagator: propagate_lesson_to_ledger (new pattern, repeated pattern,
    cross-ticker boost, same-ticker no-boost, confidence blend)
  - LedgerPropagator: propagate_lessons routing by scope
  - stock_specific lessons are NOT propagated
  - market_wide lessons propagate to both sector AND market ledger
  - contributing_tickers grows correctly across multiple tickers
  - build_tiered_lessons_summary: tier limits (6/3/2), tier labels,
    sort by effective confidence, empty inputs
  - Lesson schema: contributing_tickers defaults to empty list
"""

import json
import tempfile
from datetime import date
from pathlib import Path

import pytest

from core.intelligence.rl.stores.prediction_store import PredictionStore
from core.intelligence.rl.stores.ledger_propagator import (
    _BLEND_EXISTING,
    _BLEND_INCOMING,
    _CROSS_TICKER_BOOST,
    build_tiered_lessons_summary,
    propagate_lesson_to_ledger,
    propagate_lessons,
)
from core.schemas.feedback import LearningLedger, Lesson


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_lesson(
    pattern: str = "rbi_rate_cut",
    scope: str = "stock_specific",
    confidence: float = 0.6,
    lesson_id: str = "L001",
    contributing_tickers: list[str] | None = None,
) -> Lesson:
    return Lesson(
        lesson_id=lesson_id,
        date_learned="2026-04-01",
        category="macro",
        pattern=pattern,
        observation="RBI surprise rate cut",
        rule="When RBI cuts rate, risk_macro weight +0.05",
        confidence=confidence,
        occurrences=1,
        still_valid=True,
        scope=scope,
        last_seen="2026-04-01",
        contributing_tickers=contributing_tickers or [],
    )


def _make_ledger(ticker: str = "MARUTI", lessons: list[Lesson] | None = None) -> LearningLedger:
    return LearningLedger(
        ticker=ticker,
        sector="automobile",
        last_updated="2026-04-01",
        lessons=lessons or [],
    )


def _empty_shared_ledger() -> LearningLedger:
    return LearningLedger(
        ticker="_shared_automobile",
        sector="automobile",
        last_updated="2026-04-01",
    )


def _empty_market_ledger() -> LearningLedger:
    return LearningLedger(
        ticker="_market",
        sector="all",
        last_updated="2026-04-01",
    )


# ---------------------------------------------------------------------------
# PredictionStore — path construction
# ---------------------------------------------------------------------------

class TestPredictionStorePaths:
    def test_flat_path_when_no_sector(self, tmp_path):
        store = PredictionStore("MARUTI", base_dir=str(tmp_path))
        assert store._dir == tmp_path / "MARUTI"
        assert store._dir.exists()

    def test_sector_path_includes_sector(self, tmp_path):
        store = PredictionStore("MARUTI", sector="automobile", base_dir=str(tmp_path))
        assert store._dir == tmp_path / "automobile" / "MARUTI"
        assert store._dir.exists()

    def test_ticker_uppercased(self, tmp_path):
        store = PredictionStore("maruti", sector="automobile", base_dir=str(tmp_path))
        assert store.ticker == "MARUTI"

    def test_shared_ledger_path(self, tmp_path):
        store = PredictionStore("MARUTI", sector="automobile", base_dir=str(tmp_path))
        expected = tmp_path / "automobile" / "_shared_ledger.json"
        assert store._shared_ledger_path() == expected

    def test_market_ledger_path(self, tmp_path):
        store = PredictionStore("MARUTI", sector="automobile", base_dir=str(tmp_path))
        expected = tmp_path / "_market_ledger.json"
        assert store._market_ledger_path() == expected

    def test_shared_ledger_path_raises_without_sector(self, tmp_path):
        store = PredictionStore("MARUTI", base_dir=str(tmp_path))
        with pytest.raises(ValueError, match="sector="):
            store._shared_ledger_path()


# ---------------------------------------------------------------------------
# PredictionStore — sector + market ledger I/O
# ---------------------------------------------------------------------------

class TestPredictionStoreSectorLedger:
    def test_load_sector_ledger_returns_empty_when_missing(self, tmp_path):
        store = PredictionStore("MARUTI", sector="automobile", base_dir=str(tmp_path))
        ledger = store.load_sector_ledger()
        assert ledger.lessons == []
        assert ledger.ticker == "_shared_automobile"
        assert ledger.sector == "automobile"

    def test_save_and_load_sector_ledger_roundtrip(self, tmp_path):
        store = PredictionStore("MARUTI", sector="automobile", base_dir=str(tmp_path))
        ledger = _empty_shared_ledger()
        ledger.lessons.append(_make_lesson(pattern="rbi_rate_cut", scope="sector_wide"))
        store.save_sector_ledger(ledger)

        loaded = store.load_sector_ledger()
        assert len(loaded.lessons) == 1
        assert loaded.lessons[0].pattern == "rbi_rate_cut"

    def test_save_sector_ledger_creates_parent_dir(self, tmp_path):
        store = PredictionStore("MARUTI", sector="new_sector", base_dir=str(tmp_path))
        ledger = LearningLedger(
            ticker="_shared_new_sector", sector="new_sector", last_updated="2026-04-01"
        )
        store.save_sector_ledger(ledger)
        assert (tmp_path / "new_sector" / "_shared_ledger.json").exists()

    def test_save_sector_ledger_noop_without_sector(self, tmp_path, caplog):
        import logging
        store = PredictionStore("MARUTI", base_dir=str(tmp_path))
        ledger = _empty_shared_ledger()
        with caplog.at_level(logging.WARNING):
            store.save_sector_ledger(ledger)
        assert "skipped" in caplog.text.lower()

    def test_load_market_ledger_returns_empty_when_missing(self, tmp_path):
        store = PredictionStore("MARUTI", sector="automobile", base_dir=str(tmp_path))
        ledger = store.load_market_ledger()
        assert ledger.lessons == []
        assert ledger.ticker == "_market"
        assert ledger.sector == "all"

    def test_save_and_load_market_ledger_roundtrip(self, tmp_path):
        store = PredictionStore("MARUTI", sector="automobile", base_dir=str(tmp_path))
        ledger = _empty_market_ledger()
        ledger.lessons.append(_make_lesson(pattern="fed_rate_hike", scope="market_wide"))
        store.save_market_ledger(ledger)

        loaded = store.load_market_ledger()
        assert len(loaded.lessons) == 1
        assert loaded.lessons[0].pattern == "fed_rate_hike"

    def test_load_all_ledgers_returns_triple(self, tmp_path):
        store = PredictionStore("MARUTI", sector="automobile", base_dir=str(tmp_path))
        t, s, m = store.load_all_ledgers()
        assert t.ticker == "MARUTI"
        assert s.ticker == "_shared_automobile"
        assert m.ticker == "_market"

    def test_load_all_ledgers_no_sector_returns_empty_sector(self, tmp_path):
        store = PredictionStore("MARUTI", base_dir=str(tmp_path))
        t, s, m = store.load_all_ledgers()
        assert t.ticker == "MARUTI"
        assert s.ticker == "_empty_sector"
        assert m.ticker == "_market"


# ---------------------------------------------------------------------------
# LedgerPropagator — propagate_lesson_to_ledger
# ---------------------------------------------------------------------------

class TestPropagateLessonToLedger:
    def test_new_pattern_added_to_empty_ledger(self):
        shared = _empty_shared_ledger()
        lesson = _make_lesson(pattern="rbi_rate_cut", confidence=0.70)
        result_id = propagate_lesson_to_ledger(lesson, shared, "MARUTI")

        assert len(shared.lessons) == 1
        added = shared.lessons[0]
        assert added.pattern == "rbi_rate_cut"
        assert added.confidence == 0.70
        assert added.contributing_tickers == ["MARUTI"]
        assert result_id == "L001"

    def test_existing_pattern_blends_confidence(self):
        shared = _empty_shared_ledger()
        existing_lesson = _make_lesson(pattern="rbi_rate_cut", confidence=0.70)
        existing_lesson.contributing_tickers = ["MARUTI"]
        shared.lessons.append(existing_lesson)

        # Same ticker, so no cross-ticker boost; only confidence blend
        incoming = _make_lesson(pattern="rbi_rate_cut", confidence=0.50)
        propagate_lesson_to_ledger(incoming, shared, "MARUTI")

        assert len(shared.lessons) == 1
        updated = shared.lessons[0]
        expected_conf = round(_BLEND_EXISTING * 0.70 + _BLEND_INCOMING * 0.50, 4)
        assert updated.confidence == expected_conf
        assert updated.occurrences == 2

    def test_new_ticker_earns_cross_ticker_boost(self):
        shared = _empty_shared_ledger()
        existing_lesson = _make_lesson(pattern="rbi_rate_cut", confidence=0.70)
        existing_lesson.contributing_tickers = ["MARUTI"]
        shared.lessons.append(existing_lesson)

        blended = round(_BLEND_EXISTING * 0.70 + _BLEND_INCOMING * 0.65, 4)
        expected_conf = min(1.0, round(blended + _CROSS_TICKER_BOOST, 4))

        incoming = _make_lesson(pattern="rbi_rate_cut", confidence=0.65)
        propagate_lesson_to_ledger(incoming, shared, "SBIN")

        updated = shared.lessons[0]
        assert updated.confidence == expected_conf
        assert "SBIN" in updated.contributing_tickers
        assert "MARUTI" in updated.contributing_tickers

    def test_same_ticker_no_cross_ticker_boost(self):
        shared = _empty_shared_ledger()
        existing_lesson = _make_lesson(pattern="rbi_rate_cut", confidence=0.70)
        existing_lesson.contributing_tickers = ["MARUTI"]
        shared.lessons.append(existing_lesson)

        blended = round(_BLEND_EXISTING * 0.70 + _BLEND_INCOMING * 0.60, 4)

        incoming = _make_lesson(pattern="rbi_rate_cut", confidence=0.60)
        propagate_lesson_to_ledger(incoming, shared, "MARUTI")

        updated = shared.lessons[0]
        # No boost — MARUTI already in contributing_tickers
        assert updated.confidence == blended
        assert updated.contributing_tickers.count("MARUTI") == 1

    def test_contributing_tickers_accumulates(self):
        shared = _empty_shared_ledger()
        lesson = _make_lesson(pattern="rbi_rate_cut", confidence=0.60)
        propagate_lesson_to_ledger(lesson, shared, "MARUTI")
        propagate_lesson_to_ledger(lesson, shared, "SBIN")
        propagate_lesson_to_ledger(lesson, shared, "HDFCBANK")

        assert shared.lessons[0].contributing_tickers == ["MARUTI", "SBIN", "HDFCBANK"]

    def test_confidence_capped_at_1(self):
        shared = _empty_shared_ledger()
        existing_lesson = _make_lesson(pattern="rbi_rate_cut", confidence=0.99)
        existing_lesson.contributing_tickers = ["MARUTI"]
        shared.lessons.append(existing_lesson)

        incoming = _make_lesson(pattern="rbi_rate_cut", confidence=0.99)
        propagate_lesson_to_ledger(incoming, shared, "SBIN")

        assert shared.lessons[0].confidence <= 1.0

    def test_pattern_search_is_case_sensitive(self):
        shared = _empty_shared_ledger()
        lesson1 = _make_lesson(pattern="rbi_rate_cut", confidence=0.60)
        lesson2 = _make_lesson(pattern="RBI_RATE_CUT", confidence=0.70)
        propagate_lesson_to_ledger(lesson1, shared, "MARUTI")
        propagate_lesson_to_ledger(lesson2, shared, "SBIN")
        # Different patterns → two distinct entries
        assert len(shared.lessons) == 2


# ---------------------------------------------------------------------------
# LedgerPropagator — propagate_lessons (scope routing)
# ---------------------------------------------------------------------------

class TestPropagateLessons:
    def test_stock_specific_not_propagated(self):
        ticker_ledger = _make_ledger(lessons=[_make_lesson(scope="stock_specific")])
        sector_ledger = _empty_shared_ledger()
        market_ledger = _empty_market_ledger()

        propagate_lessons("MARUTI", ticker_ledger, sector_ledger, market_ledger, ["L001"])

        assert len(sector_ledger.lessons) == 0
        assert len(market_ledger.lessons) == 0

    def test_sector_wide_goes_to_sector_only(self):
        lesson = _make_lesson(scope="sector_wide")
        ticker_ledger = _make_ledger(lessons=[lesson])
        sector_ledger = _empty_shared_ledger()
        market_ledger = _empty_market_ledger()

        propagate_lessons("MARUTI", ticker_ledger, sector_ledger, market_ledger, ["L001"])

        assert len(sector_ledger.lessons) == 1
        assert len(market_ledger.lessons) == 0

    def test_market_wide_goes_to_both_ledgers(self):
        lesson = _make_lesson(scope="market_wide")
        ticker_ledger = _make_ledger(lessons=[lesson])
        sector_ledger = _empty_shared_ledger()
        market_ledger = _empty_market_ledger()

        propagate_lessons("MARUTI", ticker_ledger, sector_ledger, market_ledger, ["L001"])

        assert len(sector_ledger.lessons) == 1
        assert len(market_ledger.lessons) == 1

    def test_only_lesson_ids_in_set_are_propagated(self):
        lesson1 = _make_lesson(pattern="rbi_rate_cut", scope="sector_wide", lesson_id="L001")
        lesson2 = _make_lesson(pattern="crude_oil_spike", scope="sector_wide", lesson_id="L002")
        ticker_ledger = _make_ledger(lessons=[lesson1, lesson2])
        sector_ledger = _empty_shared_ledger()
        market_ledger = _empty_market_ledger()

        # Only propagate L001; L002 is from a prior cycle
        propagate_lessons("MARUTI", ticker_ledger, sector_ledger, market_ledger, ["L001"])

        assert len(sector_ledger.lessons) == 1
        assert sector_ledger.lessons[0].pattern == "rbi_rate_cut"

    def test_empty_lesson_ids_is_no_op(self):
        lesson = _make_lesson(scope="sector_wide")
        ticker_ledger = _make_ledger(lessons=[lesson])
        sector_ledger = _empty_shared_ledger()
        market_ledger = _empty_market_ledger()

        propagate_lessons("MARUTI", ticker_ledger, sector_ledger, market_ledger, [])

        assert len(sector_ledger.lessons) == 0

    def test_returns_updated_ledgers(self):
        lesson = _make_lesson(scope="sector_wide")
        ticker_ledger = _make_ledger(lessons=[lesson])
        sector_ledger = _empty_shared_ledger()
        market_ledger = _empty_market_ledger()

        s, m = propagate_lessons("MARUTI", ticker_ledger, sector_ledger, market_ledger, ["L001"])
        assert s is sector_ledger
        assert m is market_ledger


# ---------------------------------------------------------------------------
# build_tiered_lessons_summary
# ---------------------------------------------------------------------------

class TestBuildTieredLessonsSummary:
    def _make_ledger_with_lessons(
        self, ticker: str, scopes: list[str], confidences: list[float]
    ) -> LearningLedger:
        lessons = [
            _make_lesson(
                pattern=f"pattern_{i}",
                scope=scopes[i],
                confidence=confidences[i],
                lesson_id=f"L{i + 1:03d}",
            )
            for i in range(len(scopes))
        ]
        return _make_ledger(ticker=ticker, lessons=lessons)

    def test_empty_all_tiers_returns_no_lessons_string(self):
        result = build_tiered_lessons_summary(
            _make_ledger(), _empty_shared_ledger(), _empty_market_ledger()
        )
        assert result == "No lessons learned yet."

    def test_tier1_label_present(self):
        ticker_ledger = self._make_ledger_with_lessons(
            "MARUTI", ["stock_specific"], [0.70]
        )
        result = build_tiered_lessons_summary(
            ticker_ledger, _empty_shared_ledger(), _empty_market_ledger()
        )
        assert "TIER 1" in result

    def test_tier2_label_present(self):
        sector_ledger = _empty_shared_ledger()
        sector_lesson = _make_lesson(pattern="sector_lesson", scope="sector_wide")
        sector_lesson.contributing_tickers = ["MARUTI"]
        sector_ledger.lessons.append(sector_lesson)

        result = build_tiered_lessons_summary(
            _make_ledger(), sector_ledger, _empty_market_ledger()
        )
        assert "TIER 2" in result

    def test_tier3_label_present(self):
        market_ledger = _empty_market_ledger()
        market_lesson = _make_lesson(pattern="market_lesson", scope="market_wide")
        market_lesson.contributing_tickers = ["MARUTI"]
        market_ledger.lessons.append(market_lesson)

        result = build_tiered_lessons_summary(
            _make_ledger(), _empty_shared_ledger(), market_ledger
        )
        assert "TIER 3" in result

    def test_tier1_capped_at_6_lessons(self):
        lessons = [
            _make_lesson(
                pattern=f"p{i}",
                scope="stock_specific",
                confidence=0.5,
                lesson_id=f"L{i:03d}",
            )
            for i in range(1, 10)  # 9 lessons
        ]
        ticker_ledger = _make_ledger(lessons=lessons)
        result = build_tiered_lessons_summary(
            ticker_ledger, _empty_shared_ledger(), _empty_market_ledger()
        )
        # Only 6 should appear
        tier1_lines = [
            l for l in result.splitlines()
            if l.strip().startswith("L") or l.strip().startswith("[TIER")
        ]
        lesson_lines = [l for l in result.splitlines() if l.strip().startswith("L")]
        assert len(lesson_lines) <= 6

    def test_tier2_capped_at_3_lessons(self):
        sector_ledger = _empty_shared_ledger()
        for i in range(6):
            l = _make_lesson(pattern=f"sec_{i}", scope="sector_wide", lesson_id=f"L{i:03d}")
            l.contributing_tickers = ["MARUTI"]
            sector_ledger.lessons.append(l)
        result = build_tiered_lessons_summary(
            _make_ledger(), sector_ledger, _empty_market_ledger()
        )
        tier2_lines = [l for l in result.splitlines() if "sec_" in l]
        assert len(tier2_lines) <= 3

    def test_tier1_filters_non_stock_specific(self):
        # sector_wide lessons in ticker ledger should NOT appear in tier 1
        lessons = [
            _make_lesson(pattern="sector_p", scope="sector_wide"),
        ]
        ticker_ledger = _make_ledger(lessons=lessons)
        result = build_tiered_lessons_summary(
            ticker_ledger, _empty_shared_ledger(), _empty_market_ledger()
        )
        assert "TIER 1" not in result  # no stock_specific lessons

    def test_sorted_by_effective_confidence_descending(self):
        lessons = [
            _make_lesson(pattern="low_conf", scope="stock_specific", confidence=0.40, lesson_id="L001"),
            _make_lesson(pattern="high_conf", scope="stock_specific", confidence=0.80, lesson_id="L002"),
        ]
        ticker_ledger = _make_ledger(lessons=lessons)
        result = build_tiered_lessons_summary(
            ticker_ledger, _empty_shared_ledger(), _empty_market_ledger()
        )
        high_pos = result.find("high_conf")
        low_pos  = result.find("low_conf")
        assert high_pos < low_pos, "high_conf should appear before low_conf"

    def test_contributing_tickers_shown_in_tier2(self):
        sector_ledger = _empty_shared_ledger()
        l = _make_lesson(pattern="rbi_cut", scope="sector_wide")
        l.contributing_tickers = ["MARUTI", "SBIN"]
        sector_ledger.lessons.append(l)
        result = build_tiered_lessons_summary(
            _make_ledger(), sector_ledger, _empty_market_ledger()
        )
        assert "MARUTI" in result
        assert "SBIN" in result


# ---------------------------------------------------------------------------
# Lesson schema — contributing_tickers default
# ---------------------------------------------------------------------------

class TestLessonSchema:
    def test_contributing_tickers_defaults_to_empty_list(self):
        lesson = Lesson(
            lesson_id="L001",
            date_learned="2026-04-01",
            category="macro",
            pattern="test",
            observation="obs",
            rule="rule",
        )
        assert lesson.contributing_tickers == []

    def test_contributing_tickers_persists_in_round_trip(self, tmp_path):
        """contributing_tickers survives JSON serialisation → deserialisation."""
        lesson = _make_lesson(contributing_tickers=["MARUTI", "SBIN"])
        ledger = _make_ledger(lessons=[lesson])
        path = tmp_path / "test_ledger.json"
        path.write_text(json.dumps(ledger.model_dump(), indent=2), encoding="utf-8")
        loaded = LearningLedger(**json.loads(path.read_text()))
        assert loaded.lessons[0].contributing_tickers == ["MARUTI", "SBIN"]


# ---------------------------------------------------------------------------
# downgrade_stale_lessons
# ---------------------------------------------------------------------------

from datetime import date, timedelta
from core.intelligence.rl.stores.ledger_propagator import downgrade_stale_lessons


def _stale_lesson(scope: str, days_inactive: int, n_tickers: int = 1):
    """Create a Lesson that has been inactive for days_inactive days."""
    from core.schemas.feedback import Lesson
    last_seen = (date.today() - timedelta(days=days_inactive)).isoformat()
    return Lesson(
        lesson_id="L_TEST",
        date_learned="2026-01-01",
        last_seen=last_seen,
        category="macro",
        scope=scope,
        pattern="test_pattern",
        observation="test observation",
        rule="test rule",
        confidence=0.75,
        occurrences=2,
        still_valid=True,
        contributing_tickers=[f"TICK{i}" for i in range(n_tickers)],
    )


def test_downgrade_market_wide_single_ticker_stale():
    """market_wide + 1 ticker + inactive >30d → downgraded to sector_wide."""
    from core.schemas.feedback import LearningLedger
    ledger = LearningLedger(ticker="SHARED", sector="automobile", last_updated="2026-01-01",
                            lessons=[_stale_lesson("market_wide", days_inactive=35, n_tickers=1)])
    n = downgrade_stale_lessons(ledger, staleness_days=30)
    assert n == 1
    assert ledger.lessons[0].scope == "sector_wide"


def test_downgrade_sector_wide_single_ticker_very_stale():
    """sector_wide + 1 ticker + inactive >60d → still_valid=False."""
    from core.schemas.feedback import LearningLedger
    ledger = LearningLedger(ticker="SHARED", sector="automobile", last_updated="2026-01-01",
                            lessons=[_stale_lesson("sector_wide", days_inactive=65, n_tickers=1)])
    n = downgrade_stale_lessons(ledger, staleness_days=30)
    assert n == 1
    assert ledger.lessons[0].still_valid is False


def test_no_downgrade_multi_ticker_lesson():
    """market_wide + 3 tickers → NOT downgraded even if stale."""
    from core.schemas.feedback import LearningLedger
    ledger = LearningLedger(ticker="SHARED", sector="automobile", last_updated="2026-01-01",
                            lessons=[_stale_lesson("market_wide", days_inactive=45, n_tickers=3)])
    n = downgrade_stale_lessons(ledger, staleness_days=30)
    assert n == 0
    assert ledger.lessons[0].scope == "market_wide"


def test_no_downgrade_fresh_lesson():
    """Lesson seen 5 days ago is not touched."""
    from core.schemas.feedback import LearningLedger
    ledger = LearningLedger(ticker="SHARED", sector="automobile", last_updated="2026-01-01",
                            lessons=[_stale_lesson("market_wide", days_inactive=5, n_tickers=1)])
    n = downgrade_stale_lessons(ledger, staleness_days=30)
    assert n == 0
    assert ledger.lessons[0].scope == "market_wide"
