"""SA-039 — learning containment: rl.learning_mode = adapt | observe.

Independent invariants, not implementation echoes:

- Expected weights are the sector default tables copied by hand from
  config.yaml / the sector settings modules, and the expected composite is
  computed by hand from them (never from the code under test).
- Observe mode: every decision consumer (forecast, re-forecast, public
  analysis, the review's re-scoring and Step-7 revision) aggregates with the
  sector defaults; the stored weight file is byte-identical after a full
  review; one diagnostic record carries what the adapter would have written.
- Lessons are recorded but never move agent scores in observe mode.
- adapt mode still writes weights; an unknown value fails closed to observe.
- Rollback: back in adapt, the stored weights are used byte for byte.

All external transports are blocked: every network connect or DNS lookup
during a full review is recorded and asserted absent.
"""
from __future__ import annotations

import hashlib
import json
import logging
import socket
from datetime import date, timedelta

import pytest

from core.intelligence.rl.stores.prediction_store import PredictionStore
from core.schemas.feedback import (
    DailyFeedbackLog,
    FeedbackEntry,
    LearningLedger,
    Lesson,
    RawLesson,
    WeightMemory,
)

# Hand copies of the configured default tables (not read from the code).
AUTOMOBILE_DEFAULTS = {
    "sales_demand": 0.15, "raw_materials": 0.09, "fundamentals": 0.18,
    "pattern_analysis": 0.11, "sentiment": 0.04, "policy_regulatory": 0.09,
    "competitive_intel": 0.09, "risk_macro": 0.13, "valuation_catalyst": 0.12,
}
GENERIC_DEFAULTS = {
    "business": 0.14, "fundamentals": 0.18, "valuation": 0.14, "technical": 0.12,
    "macro": 0.12, "risk": 0.12, "management": 0.09, "earnings": 0.09,
}

# Learned state that diverges from the defaults the way production did on
# 2026-09-23/24: the chart-signal agent trained down to 0.0.
AUTOMOBILE_LEARNED = dict(AUTOMOBILE_DEFAULTS, pattern_analysis=0.0, sales_demand=0.26)
GENERIC_LEARNED = dict(GENERIC_DEFAULTS, technical=0.0, fundamentals=0.30)


@pytest.fixture
def mode(monkeypatch):
    """Set rl.learning_mode for one test; clears the once-per-value warning memo."""
    from core.config import settings
    from core.intelligence.rl import learning_mode as lm
    lm._warned.clear()

    def _set(value):
        monkeypatch.setattr(settings, "RL_LEARNING_MODE", value)
    return _set


@pytest.fixture
def no_network(monkeypatch):
    """Record (and refuse) every outbound connect / DNS lookup."""
    attempts: list = []

    def _connect(self, address, *a, **k):
        attempts.append(("connect", address))
        raise OSError("network blocked in SA-039 tests")

    def _getaddrinfo(host, *a, **k):
        attempts.append(("dns", host))
        raise socket.gaierror("network blocked in SA-039 tests")

    monkeypatch.setattr(socket.socket, "connect", _connect)
    monkeypatch.setattr(socket.socket, "connect_ex", _connect)
    monkeypatch.setattr(socket, "getaddrinfo", _getaddrinfo)
    return attempts


def _wm(ticker, sector, current, base, version=41):
    return WeightMemory(
        ticker=ticker, sector=sector, last_updated="2026-09-23",
        weight_version=version, current_weights=dict(current), base_weights=dict(base),
    )


def _sha(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# The switch itself
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw, expected", [
    ("adapt", "adapt"), ("observe", "observe"), (" Observe ", "observe"), ("ADAPT", "adapt"),
])
def test_recognised_values(mode, raw, expected):
    from core.intelligence.rl.learning_mode import learning_mode
    mode(raw)
    assert learning_mode() == expected


@pytest.mark.parametrize("raw", ["freeze", "", "adaptive", None, 1])
def test_unrecognised_value_fails_closed_to_observe_with_warning(mode, caplog, raw):
    from core.intelligence.rl.learning_mode import learning_mode_state
    mode(raw)
    with caplog.at_level(logging.WARNING, logger="core.intelligence.rl.learning_mode"):
        got, reason = learning_mode_state()
    assert got == "observe"
    assert "failed closed" in reason
    assert any("failing closed" in r.getMessage() for r in caplog.records)


def test_shipped_default_is_adapt():
    """The implementation ships with adapt; activation is a separate commit."""
    from backend.shared.config.settings.loader import cfg
    assert cfg("rl.learning_mode") == "adapt"


# ---------------------------------------------------------------------------
# Default tables: each sector resolves its own
# ---------------------------------------------------------------------------

def test_observe_uses_each_sectors_own_default_table(mode):
    from core.intelligence.rl.learning_mode import decision_weights
    mode("observe")
    generic_wm = _wm("X", "pharma", GENERIC_LEARNED, GENERIC_DEFAULTS)
    auto_wm = _wm("Y", "automobile", AUTOMOBILE_LEARNED, AUTOMOBILE_DEFAULTS)
    # pharma has no native graph -> the generic table (technical 0.12).
    assert decision_weights(generic_wm, "pharma") == GENERIC_DEFAULTS
    assert decision_weights(auto_wm, "automobile") == AUTOMOBILE_DEFAULTS


def test_observe_ignores_a_base_weights_table_from_another_sector(mode):
    """daily_review initialises missing memory from the automobile table, so a
    file's base_weights can be the wrong sector's. Observe must not use them."""
    from core.intelligence.rl.learning_mode import decision_weights
    mode("observe")
    wrong_base = _wm("X", "pharma", AUTOMOBILE_LEARNED, AUTOMOBILE_DEFAULTS)
    assert decision_weights(wrong_base, "pharma") == GENERIC_DEFAULTS


def test_workflow_and_orchestrator_defaults_agree():
    """The review/forecast path (get_sector_weights) and the public-analysis
    path (_get_default_weights) must name the same table."""
    from backend.sectors.generic.pipeline.orchestrator import GenericSectorOrchestrator
    from backend.shared.pipeline.base_orchestrator import BaseSectorOrchestrator
    orch = object.__new__(GenericSectorOrchestrator)
    assert orch._get_default_weights() == GENERIC_DEFAULTS
    assert BaseSectorOrchestrator._get_default_weights(orch) == AUTOMOBILE_DEFAULTS


def test_adapt_uses_stored_weights(mode):
    from core.intelligence.rl.learning_mode import decision_weights
    mode("adapt")
    wm = _wm("X", "pharma", GENERIC_LEARNED, GENERIC_DEFAULTS)
    assert decision_weights(wm, "pharma") == wm.effective_weights()
    assert decision_weights(None, "pharma") is None      # caller's fallback, unchanged


# ---------------------------------------------------------------------------
# The composite a decision actually gets — real SignalAggregator
# ---------------------------------------------------------------------------

def _composite(monkeypatch, weights, scores) -> float:
    """Run the real SignalAggregator (LLM and loggers stubbed); return the composite."""
    import backend.shared.pipeline.signal_aggregator as sa
    import backend.shared.pipeline.verdict_shadow as vs
    from core.schemas.pipeline import AgentOutput
    from tests.conftest import make_aggregator_json

    seen: dict = {}
    monkeypatch.setattr(vs, "log_verdict_shadow", lambda **kw: seen.update(kw))
    monkeypatch.setattr(sa, "log_llm_call", lambda **kw: None)
    agg = object.__new__(sa.SignalAggregator)
    agg._last_prompt_tokens = agg._last_completion_tokens = 0
    agg._call_llm = lambda system, user: make_aggregator_json()
    outputs = {a: AgentOutput(agent=a, ticker="X", overall_score=s) for a, s in scores.items()}
    agg.run(ticker="X", company_name="X", agent_outputs=outputs,
            learned_weights=weights, sector="generic")
    return seen["composite"]


# Every agent at 0.5 except technical at 1.0: the composite is
# 0.5 + 0.5 * w_technical. By hand: defaults -> 0.5 + 0.5*0.12 = 0.56;
# learned (technical 0.0) -> 0.50.
_SCORES = {a: (1.0 if a == "technical" else 0.5) for a in GENERIC_DEFAULTS}


def _seed_weights(root, ticker, sector, current, base, version=41):
    store = PredictionStore(ticker, sector=sector, base_dir=str(root))
    store.save_weight_memory(_wm(ticker, sector, current, base, version))
    return store


@pytest.mark.parametrize("value, expected_composite", [("observe", 0.56), ("adapt", 0.50)])
def test_public_analysis_path_composite(tmp_path, monkeypatch, mode, value, expected_composite):
    """base_orchestrator._resolve_weights_for (the /analyse path) -> aggregator."""
    from core.config import settings
    from backend.sectors.generic.pipeline.orchestrator import GenericSectorOrchestrator
    monkeypatch.setattr(settings, "PREDICTION_DATA_DIR", str(tmp_path))
    _seed_weights(tmp_path, "GENCO", "generic", GENERIC_LEARNED, GENERIC_DEFAULTS)
    mode(value)

    orch = object.__new__(GenericSectorOrchestrator)
    orch._aggregator_weights = None
    orch._aggregator_weights_ticker = None
    orch._resolve_weights_for("GENCO")

    assert _composite(monkeypatch, orch._aggregator_weights, _SCORES) == pytest.approx(
        expected_composite, abs=1e-9)
    if value == "observe":
        assert orch._aggregator_weights == GENERIC_DEFAULTS


def test_public_analysis_async_path_uses_the_same_loader(mode, monkeypatch, tmp_path):
    """analyse_async resolves via _load_learned_weights too: observe -> None."""
    from core.config import settings
    from backend.sectors.generic.pipeline.orchestrator import GenericSectorOrchestrator
    monkeypatch.setattr(settings, "PREDICTION_DATA_DIR", str(tmp_path))
    _seed_weights(tmp_path, "GENCO", "generic", GENERIC_LEARNED, GENERIC_DEFAULTS)
    orch = object.__new__(GenericSectorOrchestrator)
    mode("observe")
    assert orch._load_learned_weights("GENCO") is None
    mode("adapt")
    assert orch._load_learned_weights("GENCO")["technical"] == 0.0


class _ComposingOrchestrator:
    """Stands in for the sector graph: records the injected weights and
    aggregates fixed agent scores with the real SignalAggregator."""

    def __init__(self, monkeypatch):
        self._mp = monkeypatch
        self.injected: list[dict] = []
        self.composites: list[float] = []

    def set_aggregator_weights(self, weights, ticker):
        self.injected.append(dict(weights))

    def analyse(self, ticker):
        from core.schemas.pipeline import FinalReport, WeightedAgentScore
        self.composites.append(_composite(self._mp, self.injected[-1], _SCORES))
        return FinalReport(
            ticker=ticker, company_name=ticker, verdict="NEUTRAL", final_score=0.5,
            weighted_agent_scores={a: WeightedAgentScore(raw=s, weight=0.1, weighted=0.05)
                                   for a, s in _SCORES.items()},
            agent_outputs={},
        )


def _patch_forecast(gf, monkeypatch, tmp_path, orch):
    monkeypatch.setattr(gf.settings, "PREDICTION_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(gf, "get_orchestrator", lambda sector: orch)
    monkeypatch.setattr(gf, "_fetch_actual_close", lambda ticker: 100.0)
    monkeypatch.setattr(gf, "_compute_forecast_profile",
                        lambda *a, **k: (None, "NORMAL"))
    monkeypatch.setattr(gf, "_fetch_fno_snapshot", lambda *a, **k: None)

    class _NoEnhancer:
        def enhance(self, *a, **k):
            return {}
    monkeypatch.setattr(gf, "PromptEnhancer", _NoEnhancer)


@pytest.mark.parametrize("value, expected_composite", [("observe", 0.56), ("adapt", 0.50)])
def test_month_start_forecast_composite(tmp_path, monkeypatch, mode, no_network,
                                        value, expected_composite):
    from core.intelligence.rl.workflows import generate_forecast as gf
    store = _seed_weights(tmp_path, "GENCO", "pharma", GENERIC_LEARNED, GENERIC_DEFAULTS)
    wm_path = store._weight_memory_path()
    before = _sha(wm_path)
    orch = _ComposingOrchestrator(monkeypatch)
    _patch_forecast(gf, monkeypatch, tmp_path, orch)
    mode(value)

    envelope = gf.generate_forecast("GENCO", sector="pharma")

    assert orch.composites == [pytest.approx(expected_composite, abs=1e-9)]
    assert envelope.learning_mode == value
    assert envelope.weight_version_used == 41
    assert _sha(wm_path) == before            # a forecast never writes weights
    assert no_network == []


def test_reforecast_uses_sector_defaults_in_observe(tmp_path, monkeypatch, mode, no_network):
    """regenerate_envelope (Living Envelope re-forecast) is a decision path too."""
    from core.intelligence.rl.workflows import generate_forecast as gf
    from core.schemas.feedback import DailyForecast, PredictionEnvelope
    today = date.today()
    store = _seed_weights(tmp_path, "GENCO", "pharma", GENERIC_LEARNED, GENERIC_DEFAULTS)
    store.save_envelope(PredictionEnvelope(
        ticker="GENCO", sector="pharma", cycle_id=store.cycle_id_for(today),
        generated_at=today.isoformat(), base_close=100.0, weight_version_used=41,
        daily_forecasts=[
            DailyForecast(day=1, date=today.isoformat(), predicted_close=100.0,
                          predicted_verdict="BUY", confidence=0.5),
            DailyForecast(day=2, date=(today + timedelta(days=1)).isoformat(),
                          predicted_close=101.0, predicted_verdict="BUY", confidence=0.5),
        ],
    ))
    orch = _ComposingOrchestrator(monkeypatch)
    _patch_forecast(gf, monkeypatch, tmp_path, orch)
    monkeypatch.setattr(gf.settings, "RL_REFORECAST_ENABLED", True)
    mode("observe")

    env = gf.regenerate_envelope(ticker="GENCO", sector="pharma", review_date=today,
                                 reason="test", trigger="manual")

    assert env is not None
    assert orch.injected == [GENERIC_DEFAULTS]
    assert orch.composites == [pytest.approx(0.56, abs=1e-9)]
    assert env.learning_mode == "observe"
    assert no_network == []


# ---------------------------------------------------------------------------
# Lessons: recorded, never acted on in observe mode
# ---------------------------------------------------------------------------

def _tagged_ledger():
    return LearningLedger(ticker="T", sector="automobile", last_updated="2026-09-01", lessons=[
        Lesson(lesson_id="L1", date_learned="2026-09-01", category="macro",
               pattern="p", observation="o", rule="r", confidence=0.9, occurrences=3,
               last_seen=date.today().isoformat(), trigger_tags=["monsoon"],
               prioritise_agents=["risk_macro"], discount_agents=["sales_demand"]),
        Lesson(lesson_id="L2", date_learned="2026-09-01", category="macro",
               pattern="p2", observation="o", rule="r", confidence=0.9, occurrences=3,
               last_seen=date.today().isoformat()),
    ])


def test_lesson_emphasis_is_a_no_op_in_observe(mode):
    from core.intelligence.rl.algorithms.lesson_emphasis import apply_lesson_emphasis
    from core.intelligence.rl.workflows.generate_forecast import (
        _apply_ledger_micro_adjustments)
    scores = {"risk_macro": 0.5, "sales_demand": 0.5}

    mode("observe")
    assert apply_lesson_emphasis(scores, _tagged_ledger(), ["monsoon"]) == scores
    assert _apply_ledger_micro_adjustments(scores, _tagged_ledger()) == scores

    mode("adapt")   # sanity: the same fixture does move scores when acting
    assert apply_lesson_emphasis(scores, _tagged_ledger(), ["monsoon"])["risk_macro"] > 0.5
    assert _apply_ledger_micro_adjustments(scores, _tagged_ledger())["risk_macro"] > 0.5


def test_forecast_rows_carry_unmoved_scores_in_observe(mode):
    from core.intelligence.rl.workflows.generate_forecast import _build_daily_forecasts
    from core.schemas.pipeline import FinalReport, WeightedAgentScore
    report = FinalReport(
        ticker="T", company_name="T", verdict="NEUTRAL", final_score=0.5,
        weighted_agent_scores={a: WeightedAgentScore(raw=0.5, weight=0.5, weighted=0.25)
                               for a in ("risk_macro", "sales_demand")},
        agent_outputs={},
    )
    mode("observe")
    rows = _build_daily_forecasts(
        report, base_close=100.0, trading_dates=[date(2026, 9, 15)],   # monsoon tag
        seasonal_calendar=None, learning_ledger=_tagged_ledger(),
        forecast_profile=None, agent_predictions=None, regime_label="NORMAL",
    )
    assert rows[0].predicted_agent_scores == {"risk_macro": 0.5, "sales_demand": 0.5}


# ---------------------------------------------------------------------------
# Full daily review
# ---------------------------------------------------------------------------

from tests.unit.intelligence.rl.test_shock_path import (  # noqa: E402
    REVIEW_DATE, SECTOR, TICKER, _patch_common, _setup_store,
)

_LESSON = RawLesson(category="macro", pattern="sa039-pattern", observation="obs",
                    rule="sa039 rule", confidence=0.8, trigger_tags=["monsoon"],
                    prioritise_agents=["risk_macro"])


def _review(tmp_path, monkeypatch, *, actual_close=98.0, paper=False):
    """One real run_daily_review over an automobile store holding learned
    weights at v41 plus two earlier feedback rows (enough to adapt)."""
    import core.intelligence.rl.workflows.daily_review as dr
    from core.intelligence.rl.agents.feedback_agent import FeedbackAgent
    from core.intelligence.rl.agents.thesis_reviewer import ThesisReviewer
    from core.schemas.feedback import FeedbackAgentOutput, RegimeSnapshot, RevisedContext

    store, cycle_id = _setup_store(tmp_path)
    store.save_weight_memory(_wm(TICKER, SECTOR, AUTOMOBILE_LEARNED, AUTOMOBILE_DEFAULTS))
    prior = [
        FeedbackEntry(day=0, date=(REVIEW_DATE - timedelta(days=d)).isoformat(),
                      predicted_close=100.0, actual_close=97.0, price_error_pct=-3.0,
                      predicted_verdict="BUY", actual_direction="DOWN",
                      direction_correct=False,
                      predicted_agent_scores={"risk_macro": 0.8, "sales_demand": 0.8})
        for d in (2, 1)
    ]
    store.save_feedback_log(DailyFeedbackLog(ticker=TICKER, cycle_id=cycle_id, entries=prior))

    _patch_common(dr, monkeypatch, tmp_path, actual_close=actual_close)
    # The shared harness stubs fetch_all() only; the constructor still opens a
    # live NSE session (make_nse). Block it so the no_network guard holds.
    import core.intelligence.rl.stores.offmarket_fetcher as offmarket_mod
    monkeypatch.setattr(offmarket_mod.OffMarketFetcher, "__init__",
                        lambda self: setattr(self, "_nse", None))
    monkeypatch.setattr(dr.settings, "RL_DOSSIER_ENABLED", False)
    monkeypatch.setattr(dr.settings, "RL_REFORECAST_ENABLED", False)
    monkeypatch.setattr(dr.settings, "REGIME_MULTIPLIERS", {})
    monkeypatch.setattr(dr.RegimeDetector, "detect",
                        lambda self, d, s: RegimeSnapshot(multipliers={}))
    monkeypatch.setattr(ThesisReviewer, "should_review", lambda self, *a, **k: False)
    monkeypatch.setattr(FeedbackAgent, "run", lambda self, fb_input, ledger: FeedbackAgentOutput(
        primary_miss_agent="risk_macro", miss_type="model_bias", new_lessons=[_LESSON],
        revised_context=RevisedContext(headline="Test.", horizon_confidence_adjustment=0.0),
    ))

    rescoring: list = []
    monkeypatch.setattr(dr, "_run_todays_agent_scores", lambda t, sector, learned_weights=None,
                        capture=None: rescoring.append(learned_weights) or
                        {"risk_macro": 0.5, "sales_demand": 0.5})
    revisions: list = []
    original_revise = dr._revise_remaining_forecasts
    monkeypatch.setattr(dr, "_revise_remaining_forecasts",
                        lambda **kw: revisions.append(kw) or original_revise(**kw))

    summary = dr.run_daily_review(TICKER, REVIEW_DATE, sector=SECTOR, paper=paper)
    return store, summary, rescoring, revisions


def test_full_review_in_observe_leaves_weights_byte_identical(
        tmp_path, monkeypatch, mode, no_network):
    store = PredictionStore(TICKER, sector=SECTOR, base_dir=str(tmp_path))
    mode("observe")
    wm_path = store._weight_memory_path()

    # Seed happens inside _review; hash the seeded bytes via a first pass.
    store.save_weight_memory(_wm(TICKER, SECTOR, AUTOMOBILE_LEARNED, AUTOMOBILE_DEFAULTS))
    before = _sha(wm_path)
    store, summary, rescoring, revisions = _review(tmp_path, monkeypatch)

    assert summary["status"] == "completed"
    assert summary["learning_mode"] == "observe"
    # Stored memory: same bytes, so current_weights, weight_version and
    # weight_history are all unchanged.
    assert _sha(wm_path) == before
    assert summary["weight_version"] == "v41"
    # Every decision consumer got the automobile default table.
    assert rescoring == [AUTOMOBILE_DEFAULTS]
    assert summary["weights"] == AUTOMOBILE_DEFAULTS
    assert len(revisions) == 1 and revisions[0]["new_weights"] == pytest.approx(AUTOMOBILE_DEFAULTS)
    # Exactly one diagnostic record for the review date.
    records = store.load_weight_observations()
    assert len(records) == 1
    rec = records[0]
    assert rec["review_date"] == REVIEW_DATE.isoformat()
    assert rec["mode"] == "observe" and rec["mode_reason"] == "rl.learning_mode=observe"
    assert rec["applied"] is False
    assert rec["stored_version"] == 41 and rec["would_be_version"] == 42
    assert rec["stored_weights"] == AUTOMOBILE_LEARNED
    assert rec["deltas"] == {a: pytest.approx(rec["would_be_weights"][a] - AUTOMOBILE_LEARNED[a])
                             for a in rec["deltas"]}
    assert rec["deltas"], "fixture should make the adapter propose a real change"
    assert rec["decision_weights"] == AUTOMOBILE_DEFAULTS
    # Lessons are still recorded ...
    ledger = store.load_learning_ledger()
    assert any(l.rule == "sa039 rule" for l in ledger.lessons)
    # ... but none fired: the claim-day scorecard must not credit them.
    entry = store.load_feedback_log(store.cycle_id_for(REVIEW_DATE)).entries[-1]
    assert entry.claims_fired == []
    assert no_network == []


def test_observe_diagnostic_is_exactly_what_adapt_writes(tmp_path, monkeypatch, mode, no_network):
    """The would-be weights are the adapter's real output, not an approximation:
    the same fixture reviewed in adapt mode writes exactly those weights."""
    mode("observe")
    obs_store, *_ = _review(tmp_path / "observe", monkeypatch)
    proposal = obs_store.load_weight_observations()[0]

    mode("adapt")
    adapt_store, summary, rescoring, _ = _review(tmp_path / "adapt", monkeypatch)
    written = adapt_store.load_weight_memory()

    assert summary["learning_mode"] == "adapt"
    assert written.weight_version == 42                         # adapt still writes
    assert written.current_weights == proposal["would_be_weights"]
    assert rescoring == [_wm("x", SECTOR, AUTOMOBILE_LEARNED, AUTOMOBILE_DEFAULTS)
                         .effective_weights()]
    assert adapt_store.load_weight_observations() == []          # no diagnostic in adapt
    assert no_network == []


def test_rerun_of_the_same_date_replaces_its_diagnostic(tmp_path, monkeypatch, mode):
    mode("observe")
    store, *_ = _review(tmp_path, monkeypatch)
    store, *_ = _review(tmp_path, monkeypatch)
    assert [r["review_date"] for r in store.load_weight_observations()] == [REVIEW_DATE.isoformat()]


def test_invalid_mode_review_writes_no_weights(tmp_path, monkeypatch, mode):
    mode("adaptive")
    store = PredictionStore(TICKER, sector=SECTOR, base_dir=str(tmp_path))
    store.save_weight_memory(_wm(TICKER, SECTOR, AUTOMOBILE_LEARNED, AUTOMOBILE_DEFAULTS))
    before = _sha(store._weight_memory_path())
    store, summary, *_ = _review(tmp_path, monkeypatch)
    assert summary["learning_mode"] == "observe"
    assert _sha(store._weight_memory_path()) == before
    assert "failed closed" in store.load_weight_observations()[0]["mode_reason"]


def test_absurd_error_path_is_unchanged_in_observe(tmp_path, monkeypatch, mode):
    """A broken input still skips the adapter entirely — no proposal, no record."""
    from core.intelligence.rl.agents.weight_adapter import WeightAdapter
    calls: list = []
    monkeypatch.setattr(WeightAdapter, "update", lambda self, **kw: calls.append(kw))
    mode("observe")
    store, summary, *_ = _review(tmp_path, monkeypatch, actual_close=5.0)
    assert summary["miss_type"] == "data_stale"
    assert calls == []
    assert store.load_weight_observations() == []


def test_paper_lane_is_unchanged_in_observe(tmp_path, monkeypatch, mode):
    """Paper reviews still never train and never write under either root."""
    import core.intelligence.rl.workflows.daily_review as dr
    from core.intelligence.rl.agents.weight_adapter import WeightAdapter
    paper_root = tmp_path / "paper"
    calls: list = []
    monkeypatch.setattr(WeightAdapter, "update", lambda self, **kw: calls.append(kw))
    monkeypatch.setattr(dr.settings, "PAPER_PREDICTION_DATA_DIR", str(paper_root))
    mode("observe")
    _, summary, *_ = _review(paper_root, monkeypatch, paper=True)
    # _review seeded a weight file into the paper store for the fixture; paper
    # mode must neither train on it nor record an observation.
    assert summary["paper"] is True
    assert calls == []
    assert not list(paper_root.rglob("*weight_observations*"))


# ---------------------------------------------------------------------------
# Rollback
# ---------------------------------------------------------------------------

def test_rollback_to_adapt_resumes_stored_weights_byte_for_byte(tmp_path, monkeypatch, mode):
    from backend.sectors.generic.pipeline.orchestrator import GenericSectorOrchestrator
    from core.intelligence.rl.learning_mode import decision_weights

    # Reference bytes: the seed as the store serialises it, in a separate root.
    seeded = _wm(TICKER, SECTOR, AUTOMOBILE_LEARNED, AUTOMOBILE_DEFAULTS)
    ref = PredictionStore(TICKER, sector=SECTOR, base_dir=str(tmp_path / "ref"))
    ref.save_weight_memory(seeded)

    mode("observe")
    store, *_ = _review(tmp_path / "live", monkeypatch)
    assert store._weight_memory_path().read_bytes() == ref._weight_memory_path().read_bytes()

    mode("adapt")
    assert decision_weights(store.load_weight_memory(), SECTOR) == seeded.effective_weights()

    # The public-analysis path reads the configured root (the review harness
    # pointed it at tmp_path / "live").
    gstore = _seed_weights(tmp_path / "live", "GENCO", "generic", GENERIC_LEARNED,
                           GENERIC_DEFAULTS)
    orch = object.__new__(GenericSectorOrchestrator)
    mode("observe")
    assert orch._load_learned_weights("GENCO") is None
    mode("adapt")
    assert orch._load_learned_weights("GENCO") == gstore.load_weight_memory().effective_weights()


# ---------------------------------------------------------------------------
# Read-only surface
# ---------------------------------------------------------------------------

def test_rl_monitor_shows_mode_and_live_weights(tmp_path, monkeypatch, mode):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import services.api.routes.rl_monitor as rlm
    monkeypatch.setattr(rlm, "_managed", lambda: [{"sym": "GENCO", "sector": "pharma"}])
    monkeypatch.setattr(rlm, "_BASE_DIR_OVERRIDE", str(tmp_path), raising=False)
    _seed_weights(tmp_path, "GENCO", "pharma", GENERIC_LEARNED, GENERIC_DEFAULTS)
    app = FastAPI()
    app.include_router(rlm.router)
    client = TestClient(app)

    mode("observe")
    body = client.get("/ui/rl/weights/GENCO").json()
    assert body["learning_mode"] == "observe"
    assert body["decision_weights"] == GENERIC_DEFAULTS
    assert body["current_weights"] == GENERIC_LEARNED        # stored, shown, not live

    mode("adapt")
    body = client.get("/ui/rl/weights/GENCO").json()
    assert body["learning_mode"] == "adapt"
    assert body["decision_weights"]["technical"] == 0.0
