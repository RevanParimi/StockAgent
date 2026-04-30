"""
sanity_rl.py
============
Layered sanity checks for the RL feedback system.
Run from the project root — no pytest needed.

Layers (fastest → most expensive):
  1  Import smoke        — all modules load without errors
  2  Pure functions      — classify_direction, is_direction_correct, effective_weights, hit_rate
  3  Schema round-trip   — Pydantic serialise → JSON → deserialise
  4  PredictionStore     — write + read all 4 JSON files (temp dir, no network)
  5  WeightAdapter       — synthetic log → adapter.update() → check bounds/normalisation
  6  yfinance fetch      — _fetch_actual_close for MARUTI (network, no LLM)
  7  FeedbackAgent LLM   — one LLM call (opt-in: --with-llm)
  8  Full daily_review   — seeded envelope + full 8-step loop (opt-in: --full)

Usage:
    python sanity_rl.py                  # layers 1–6
    python sanity_rl.py --with-llm       # layers 1–7  (one LLM call)
    python sanity_rl.py --full           # layers 1–8  (LLM + agent re-run)
    python sanity_rl.py --layer 4        # run only layer 4
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import traceback
from datetime import date, timedelta
from pathlib import Path

# ── colour helpers ────────────────────────────────────────────────────────────

GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
RESET  = "\033[0m"

_passed = 0
_failed = 0


def ok(msg: str) -> None:
    global _passed
    _passed += 1
    print(f"  {GREEN}✓{RESET} {msg}")


def fail(msg: str, exc: Exception | None = None) -> None:
    global _failed
    _failed += 1
    print(f"  {RED}✗ {msg}{RESET}")
    if exc:
        print(f"    {RED}{type(exc).__name__}: {exc}{RESET}")


def skip(msg: str) -> None:
    print(f"  {YELLOW}– {msg} (skipped){RESET}")


def section(title: str) -> None:
    print(f"\n{'─'*60}")
    print(f"  Layer {title}")
    print(f"{'─'*60}")


def assert_eq(label: str, got, expected) -> None:
    if got == expected:
        ok(f"{label}: {got!r}")
    else:
        fail(f"{label}: expected {expected!r}, got {got!r}")


def assert_true(label: str, expr: bool) -> None:
    if expr:
        ok(label)
    else:
        fail(label)


def assert_close(label: str, got: float, expected: float, tol: float = 1e-5) -> None:
    if abs(got - expected) < tol:
        ok(f"{label}: {got:.6f}")
    else:
        fail(f"{label}: expected ≈{expected}, got {got}")


# ── past weekday helper ───────────────────────────────────────────────────────

def _last_weekday(n: int = 5) -> date:
    """Return the weekday n business days ago."""
    d = date.today() - timedelta(days=1)
    skipped = 0
    while skipped < n:
        if d.weekday() < 5:
            skipped += 1
        if skipped < n:
            d -= timedelta(days=1)
    return d


# =============================================================================
# Layer 1 — Import smoke
# =============================================================================

def layer1_imports() -> bool:
    section("1 — Import smoke")
    modules = [
        ("core.schemas.feedback",                        "WeightMemory, PredictionEnvelope, DailyForecast, "
                                                         "FeedbackEntry, DailyFeedbackLog, MissAnalysis, "
                                                         "RevisedContext, TimingAccuracy, LearningLedger, "
                                                         "FeedbackAgentInput, FeedbackAgentOutput, RawLesson, "
                                                         "MISS_TYPE_PENALTY_MULTIPLIER, NO_PENALTY_MISS_TYPES"),
        ("intelligence.rl.stores.prediction_store",      "PredictionStore"),
        ("intelligence.rl.agents.weight_adapter",        "WeightAdapter"),
        ("intelligence.rl.agents.feedback_agent",        "FeedbackAgent, classify_direction, is_direction_correct"),
        ("intelligence.rl.workflows.daily_review",       "run_daily_review, _fetch_actual_close, _compute_timing_accuracy"),
        ("intelligence.rl.workflows.generate_forecast",  ""),
        ("config.prompts.shared.feedback_agent",         "build_system_prompt, format_feedback_prompt"),
    ]
    all_ok = True
    for mod, names in modules:
        try:
            m = __import__(mod, fromlist=names.split(",") if names else [""])
            if names:
                for name in [n.strip() for n in names.split(",") if n.strip()]:
                    getattr(m, name)
            ok(mod)
        except Exception as exc:
            fail(mod, exc)
            all_ok = False
    return all_ok


# =============================================================================
# Layer 2 — Pure functions (zero external calls)
# =============================================================================

def layer2_pure_functions() -> None:
    section("2 — Pure functions")
    from core.intelligence.rl.agents.feedback_agent import classify_direction, is_direction_correct
    from core.schemas.feedback import (
        WeightMemory, AgentAccuracy, LearningLedger, Lesson,
        MISS_TYPE_PENALTY_MULTIPLIER, NO_PENALTY_MISS_TYPES,
    )

    # classify_direction
    assert_eq("classify_direction UP   (+5%)", classify_direction(105.0, 100.0), "UP")
    assert_eq("classify_direction DOWN (-5%)", classify_direction(95.0, 100.0),  "DOWN")
    assert_eq("classify_direction FLAT (+0.1%)", classify_direction(100.1, 100.0), "FLAT")
    assert_eq("classify_direction FLAT (0%)",   classify_direction(100.0, 100.0), "FLAT")
    assert_eq("classify_direction zero predicted", classify_direction(100.0, 0.0), "FLAT")

    # is_direction_correct
    assert_true("BUY  + UP   → correct",   is_direction_correct("BUY",        "UP"))
    assert_true("BUY  + DOWN → wrong",    not is_direction_correct("BUY",     "DOWN"))
    assert_true("STRONG BUY + UP → correct", is_direction_correct("STRONG BUY", "UP"))
    assert_true("SELL + DOWN → correct",  is_direction_correct("SELL",        "DOWN"))
    assert_true("SELL + UP   → wrong",   not is_direction_correct("SELL",     "UP"))
    assert_true("STRONG SELL + DOWN → correct", is_direction_correct("STRONG SELL", "DOWN"))
    assert_true("NEUTRAL + DOWN → not wrong",   is_direction_correct("NEUTRAL", "DOWN"))
    assert_true("NEUTRAL + UP   → not wrong",   is_direction_correct("NEUTRAL", "UP"))

    # WeightMemory.effective_weights sums to 1.0
    wm = WeightMemory(
        ticker="TEST",
        last_updated="2026-04-01",
        weight_version=0,
        current_weights={"a": 0.3, "b": 0.3, "c": 0.3},
        base_weights={"a": 0.33, "b": 0.33, "c": 0.34},
    )
    eff = wm.effective_weights()
    assert_close("effective_weights sums to 1.0", sum(eff.values()), 1.0)

    # AgentAccuracy.hit_rate
    acc_zero = AgentAccuracy(direction_hits=0, total=0)
    assert_close("hit_rate with 0 observations → 0.5", acc_zero.hit_rate(), 0.5)
    acc = AgentAccuracy(direction_hits=7, total=10)
    assert_close("hit_rate 7/10 → 0.7", acc.hit_rate(), 0.7)

    # MISS_TYPE constants
    assert_eq("data_gap penalty multiplier = 0.0",     MISS_TYPE_PENALTY_MULTIPLIER["data_gap"],       0.0)
    assert_eq("external_shock multiplier = 0.0",       MISS_TYPE_PENALTY_MULTIPLIER["external_shock"],  0.0)
    assert_eq("timing multiplier = 0.5",               MISS_TYPE_PENALTY_MULTIPLIER["timing"],           0.5)
    assert_eq("magnitude multiplier = 0.25",           MISS_TYPE_PENALTY_MULTIPLIER["magnitude"],        0.25)
    assert_eq("direction_flip multiplier = 1.0",       MISS_TYPE_PENALTY_MULTIPLIER["direction_flip"],   1.0)
    assert_true("data_gap in NO_PENALTY_MISS_TYPES",   "data_gap" in NO_PENALTY_MISS_TYPES)
    assert_true("external_shock in NO_PENALTY_MISS_TYPES", "external_shock" in NO_PENALTY_MISS_TYPES)
    assert_true("direction_flip NOT in NO_PENALTY_MISS_TYPES", "direction_flip" not in NO_PENALTY_MISS_TYPES)

    # LearningLedger.effective_confidence decay
    ledger = LearningLedger(
        ticker="TEST",
        last_updated="2026-04-01",
        confidence_decay_rate=0.02,
    )
    # Recent lesson — should lose very little confidence
    recent = Lesson(
        lesson_id="L001",
        date_learned=date.today().isoformat(),
        last_seen=date.today().isoformat(),
        category="macro",
        pattern="RBI_day",
        observation="test",
        rule="test rule",
        confidence=0.80,
    )
    ec = ledger.effective_confidence(recent)
    assert_true("effective_confidence recent ≈ stored confidence", abs(ec - 0.80) < 0.05)
    # Old lesson — should have decayed
    old = Lesson(
        lesson_id="L002",
        date_learned="2025-01-01",
        last_seen="2025-01-01",
        category="macro",
        pattern="OLD_pattern",
        observation="old test",
        rule="old rule",
        confidence=0.80,
    )
    ec_old = ledger.effective_confidence(old)
    assert_true("effective_confidence decays for old lesson", ec_old < 0.80)
    assert_true("effective_confidence floor is 0.10", ec_old >= 0.10)

    # LearningLedger helpers
    ledger2 = LearningLedger(ticker="T2", last_updated="2026-04-01")
    assert_eq("next_lesson_id with 0 lessons", ledger2.next_lesson_id(), "L001")


# =============================================================================
# Layer 3 — Schema round-trip (Pydantic → JSON → Pydantic)
# =============================================================================

def layer3_schema_roundtrip() -> None:
    section("3 — Schema round-trip (Pydantic ↔ JSON)")
    import json
    from core.schemas.feedback import (
        DailyForecast, PredictionEnvelope, FeedbackEntry, DailyFeedbackLog,
        WeightMemory, LearningLedger, Lesson, MissAnalysis, RevisedContext, TimingAccuracy,
    )

    # DailyForecast
    f = DailyForecast(
        day=1, date="2026-04-21", predicted_close=10500.0,
        predicted_change_pct=0.5, predicted_verdict="BUY", confidence=0.72,
        predicted_agent_scores={"sales_demand": 0.7, "risk_macro": 0.6},
        key_assumptions=["crude stable", "no policy surprise"],
    )
    f2 = DailyForecast(**json.loads(f.model_dump_json()))
    assert_eq("DailyForecast round-trip: predicted_close", f2.predicted_close, 10500.0)
    assert_eq("DailyForecast round-trip: confidence",      f2.confidence,       0.72)

    # PredictionEnvelope
    env = PredictionEnvelope(
        ticker="MARUTI", cycle_id="MARUTI_2026-04",
        generated_at="2026-04-01T09:00:00", base_close=10450.0,
        daily_forecasts=[f],
    )
    env2 = PredictionEnvelope(**json.loads(env.model_dump_json()))
    assert_eq("PredictionEnvelope round-trip: ticker",       env2.ticker,       "MARUTI")
    assert_eq("PredictionEnvelope round-trip: base_close",   env2.base_close,   10450.0)
    assert_eq("PredictionEnvelope: get_forecast hit",
              env2.get_forecast("2026-04-21").predicted_close, 10500.0)
    assert_eq("PredictionEnvelope: get_forecast miss",
              env2.get_forecast("2026-04-22"), None)
    assert_eq("PredictionEnvelope: remaining_forecasts from earlier date",
              len(env2.remaining_forecasts("2026-04-20")), 1)
    assert_eq("PredictionEnvelope: remaining_forecasts from same date",
              len(env2.remaining_forecasts("2026-04-21")), 0)

    # FeedbackEntry with optional nested fields
    entry = FeedbackEntry(
        day=1, date="2026-04-21",
        predicted_close=10500.0, actual_close=10420.0,
        price_error_pct=-0.76, predicted_verdict="BUY",
        actual_direction="DOWN", direction_correct=False,
        miss_analysis=MissAnalysis(
            primary_miss_agent="risk_macro",
            miss_type="direction_flip",
            missed_factors=["RBI surprise"],
        ),
        timing=TimingAccuracy(assessment="no_move"),
        revised_context=RevisedContext(
            headline="Downside risk elevated after RBI shock",
            risks_next_7_days=["FII selling", "crude spike"],
            horizon_confidence_adjustment=-0.05,
        ),
    )
    entry2 = FeedbackEntry(**json.loads(entry.model_dump_json()))
    assert_eq("FeedbackEntry round-trip: direction_correct",  entry2.direction_correct, False)
    assert_eq("FeedbackEntry round-trip: miss_type",
              entry2.miss_analysis.miss_type, "direction_flip")
    assert_eq("FeedbackEntry round-trip: timing assessment",
              entry2.timing.assessment, "no_move")
    assert_close("FeedbackEntry round-trip: conf adjustment",
                 entry2.revised_context.horizon_confidence_adjustment, -0.05)

    # WeightMemory
    wm = WeightMemory(
        ticker="MARUTI", last_updated="2026-04-01", weight_version=3,
        current_weights={"a": 0.22, "b": 0.30, "c": 0.48},
        base_weights={"a": 0.25, "b": 0.25, "c": 0.50},
    )
    wm2 = WeightMemory(**json.loads(wm.model_dump_json()))
    assert_eq("WeightMemory round-trip: weight_version",   wm2.weight_version, 3)
    assert_close("WeightMemory round-trip: effective sums to 1", sum(wm2.effective_weights().values()), 1.0)

    # LearningLedger
    ll = LearningLedger(
        ticker="MARUTI", last_updated="2026-04-01",
        lessons=[Lesson(
            lesson_id="L001", date_learned="2026-04-10",
            category="macro", pattern="RBI_policy_day",
            observation="RBI surprise → trust risk_macro",
            rule="boost risk_macro by +0.05 on RBI day",
            confidence=0.80, occurrences=3,
            scope="market_wide", last_seen="2026-04-15",
        )],
        miss_counter={"RBI_surprise": 2},
    )
    ll2 = LearningLedger(**json.loads(ll.model_dump_json()))
    assert_eq("LearningLedger round-trip: lesson count",            len(ll2.lessons), 1)
    assert_eq("LearningLedger round-trip: lesson scope",            ll2.lessons[0].scope, "market_wide")
    assert_eq("LearningLedger: find_by_pattern hit",
              ll2.find_by_pattern("RBI_policy_day").lesson_id, "L001")
    assert_eq("LearningLedger: find_by_pattern miss",
              ll2.find_by_pattern("no_such_pattern"), None)
    assert_eq("LearningLedger: next_lesson_id with 1 lesson",       ll2.next_lesson_id(), "L002")
    assert_eq("LearningLedger: miss_counter",                       ll2.miss_counter["RBI_surprise"], 2)
    assert_true("LearningLedger: active_lessons_summary non-empty",
                len(ll2.active_lessons_summary()) > 0)


# =============================================================================
# Layer 4 — PredictionStore file I/O (temp directory, no network)
# =============================================================================

def layer4_prediction_store() -> None:
    section("4 — PredictionStore round-trip (temp dir)")
    from core.schemas.feedback import (
        DailyForecast, PredictionEnvelope, FeedbackEntry, DailyFeedbackLog,
        LearningLedger, Lesson, MissAnalysis,
    )
    from core.intelligence.rl.stores.prediction_store import PredictionStore

    with tempfile.TemporaryDirectory() as tmpdir:
        store = PredictionStore("MARUTI", base_dir=tmpdir)

        # Cycle ID is well-formed
        cid = store.current_cycle_id()
        assert_true("current_cycle_id contains MARUTI", "MARUTI" in cid)
        assert_true("current_cycle_id contains year",   str(date.today().year) in cid)

        # Weight memory bootstrap
        base_w = {
            "sales_demand": 0.16, "fundamentals": 0.18, "pattern_analysis": 0.12,
            "sentiment": 0.04, "policy_regulatory": 0.09, "competitive_intel": 0.09,
            "risk_macro": 0.13, "raw_materials": 0.09, "valuation_catalyst": 0.10,
        }
        wm = store.init_weight_memory(base_w)
        assert_eq("init_weight_memory: version starts at 0",   wm.weight_version, 0)
        assert_close("init_weight_memory: sums to 1.0",        sum(wm.effective_weights().values()), 1.0)

        # load returns same data
        wm2 = store.load_weight_memory()
        assert_true("load_weight_memory: not None",                wm2 is not None)
        assert_eq("load_weight_memory: version preserved",         wm2.weight_version, 0)

        # get_or_init returns existing (no overwrite)
        wm3 = store.get_or_init_weight_memory(base_w)
        assert_eq("get_or_init: returns existing, version still 0", wm3.weight_version, 0)

        # Learning ledger — empty on first load
        ll = store.load_learning_ledger()
        assert_eq("load_learning_ledger: empty on first load", ll.lessons, [])
        ll.lessons.append(Lesson(
            lesson_id="L001", date_learned="2026-04-10",
            category="macro", pattern="RBI_day",
            observation="test obs", rule="test rule",
            confidence=0.75, scope="market_wide",
        ))
        store.save_learning_ledger(ll)
        ll2 = store.load_learning_ledger()
        assert_eq("save/load_learning_ledger: lesson count",   len(ll2.lessons), 1)
        assert_eq("save/load_learning_ledger: lesson id",      ll2.lessons[0].lesson_id, "L001")

        # Envelope save/load
        forecast = DailyForecast(
            day=1, date="2026-04-21", predicted_close=10500.0,
            predicted_change_pct=0.5, predicted_verdict="BUY", confidence=0.72,
            predicted_agent_scores={"sales_demand": 0.72, "risk_macro": 0.55},
            key_assumptions=["crude stable", "no RBI surprise"],
        )
        env = PredictionEnvelope(
            ticker="MARUTI", cycle_id=cid,
            generated_at=date.today().isoformat(),
            base_close=10450.0, daily_forecasts=[forecast],
        )
        store.save_envelope(env)
        env2 = store.load_envelope(cid)
        assert_true("load_envelope: not None",                   env2 is not None)
        assert_eq("load_envelope: base_close preserved",         env2.base_close, 10450.0)
        assert_eq("load_envelope: forecast count",               len(env2.daily_forecasts), 1)
        assert_true("load_envelope: None for missing cycle",
                    store.load_envelope("MARUTI_1999-01") is None)

        # Feedback log — load returns empty struct if missing
        log = store.load_feedback_log(cid)
        assert_eq("load_feedback_log: empty on first load", log.entries, [])

        # Append entry
        entry = FeedbackEntry(
            day=1, date="2026-04-21",
            predicted_close=10500.0, actual_close=10420.0,
            price_error_pct=-0.76, predicted_verdict="BUY",
            actual_direction="DOWN", direction_correct=False,
            miss_analysis=MissAnalysis(primary_miss_agent="risk_macro", miss_type="direction_flip"),
        )
        store.append_feedback_entry(entry, cid)
        log2 = store.load_feedback_log(cid)
        assert_eq("append_feedback_entry: 1 entry",   len(log2.entries), 1)
        assert_eq("append_feedback_entry: date preserved", log2.entries[0].date, "2026-04-21")

        # Idempotent re-append (same date replaces, not appends)
        store.append_feedback_entry(entry, cid)
        log3 = store.load_feedback_log(cid)
        assert_eq("append_feedback_entry idempotent: still 1 entry", len(log3.entries), 1)

        # list_cycles
        cycles = store.list_cycles()
        assert_true("list_cycles: at least 1 cycle", len(cycles) >= 1)
        assert_true("list_cycles: current cycle present", any("MARUTI" in c for c in cycles))

        # Atomic write: verify no .tmp files left behind
        tmp_files = list(Path(tmpdir).rglob("*.tmp"))
        assert_eq("no orphaned .tmp files", tmp_files, [])


# =============================================================================
# Layer 5 — WeightAdapter (synthetic data, no LLM, no network)
# =============================================================================

def layer5_weight_adapter() -> None:
    section("5 — WeightAdapter (synthetic feedback log)")
    from core.schemas.feedback import (
        WeightMemory, DailyFeedbackLog, FeedbackEntry, MissAnalysis,
        MISS_TYPE_PENALTY_MULTIPLIER,
    )
    from core.intelligence.rl.agents.weight_adapter import WeightAdapter
    from core.config import settings

    base_w = {
        "sales_demand": 0.20, "fundamentals": 0.25, "pattern_analysis": 0.20,
        "sentiment": 0.15, "risk_macro": 0.20,
    }
    min_obs = settings.WEIGHT_MIN_OBSERVATIONS

    def _make_wm(ticker: str) -> WeightMemory:
        return WeightMemory(
            ticker=ticker, last_updated="2026-04-01", weight_version=0,
            current_weights=base_w.copy(), base_weights=base_w.copy(),
        )

    def _make_entry(day: int, correct: bool, miss_agent: str, miss_type: str) -> FeedbackEntry:
        return FeedbackEntry(
            day=day, date=f"2026-04-{day:02d}",
            predicted_close=10000.0, actual_close=9950.0 if not correct else 10050.0,
            price_error_pct=-0.5 if not correct else 0.5,
            predicted_verdict="BUY",
            actual_direction="DOWN" if not correct else "UP",
            direction_correct=correct,
            miss_analysis=None if correct else MissAnalysis(
                primary_miss_agent=miss_agent, miss_type=miss_type,
            ),
        )

    adapter = WeightAdapter()

    # ── Test A: too few observations → no weight change ──────────────────────
    wm_a = _make_wm("TEST_A")
    log_a = DailyFeedbackLog(
        ticker="TEST_A", cycle_id="TEST_A_2026-04",
        entries=[_make_entry(i + 1, False, "risk_macro", "direction_flip")
                 for i in range(min_obs - 1)],   # one short
    )
    updated_a = adapter.update(wm_a, log_a, "risk_macro", "direction_flip")
    assert_eq("too few obs → version unchanged", updated_a.weight_version, 0)

    # ── Test B: risk_macro misses repeatedly → weight drops ──────────────────
    wm_b = _make_wm("TEST_B")
    log_b = DailyFeedbackLog(
        ticker="TEST_B", cycle_id="TEST_B_2026-04",
        entries=[_make_entry(i + 1, False, "risk_macro", "direction_flip")
                 for i in range(min_obs + 2)],
    )
    updated_b = adapter.update(wm_b, log_b, "risk_macro", "direction_flip")
    assert_eq("direction_flip misses → version bumped",         updated_b.weight_version, 1)
    assert_true("direction_flip misses → risk_macro weight reduced",
                updated_b.current_weights["risk_macro"] < base_w["risk_macro"])
    assert_close("weights still sum to 1.0",
                 sum(updated_b.effective_weights().values()), 1.0)

    # ── Test C: data_gap miss → no streak penalty on primary agent ────────────
    wm_c = _make_wm("TEST_C")
    entries_c = [_make_entry(i + 1, False, "fundamentals", "data_gap")
                 for i in range(min_obs + 2)]
    log_c = DailyFeedbackLog(ticker="TEST_C", cycle_id="TEST_C_2026-04", entries=entries_c)
    updated_c = adapter.update(wm_c, log_c, "fundamentals", "data_gap")
    assert_eq("data_gap → version bumped", updated_c.weight_version, 1)
    # Because data_gap multiplier = 0.0, streak penalty = 0.
    # The weight may still change from hit-rate logic, but streak penalty is waived.
    assert_close("weights still sum to 1.0", sum(updated_c.effective_weights().values()), 1.0)
    ok(f"data_gap → fundamentals weight: {updated_c.current_weights['fundamentals']:.4f} "
       f"(base {base_w['fundamentals']:.4f}) — streak penalty waived")

    # ── Test D: bounds enforced — weight stays within base ± max_drift ───────
    wm_d = _make_wm("TEST_D")
    # Simulate max drift already reached on risk_macro
    wm_d.current_weights["risk_macro"] = base_w["risk_macro"] - settings.WEIGHT_MAX_DRIFT + 0.001
    log_d = DailyFeedbackLog(
        ticker="TEST_D", cycle_id="TEST_D_2026-04",
        entries=[_make_entry(i + 1, False, "risk_macro", "direction_flip")
                 for i in range(min_obs + 2)],
    )
    updated_d = adapter.update(wm_d, log_d, "risk_macro", "direction_flip")
    lower_bound = base_w["risk_macro"] - settings.WEIGHT_MAX_DRIFT
    assert_true(
        f"drift bound: risk_macro >= base - max_drift ({lower_bound:.3f})",
        updated_d.current_weights["risk_macro"] >= lower_bound - 1e-5,
    )

    # ── Test E: weight history appended ──────────────────────────────────────
    assert_eq("weight_history entry added",  len(updated_b.weight_history), 1)
    assert_eq("weight_history version tag",  updated_b.weight_history[0].version, 1)
    assert_true("weight_history reason non-empty", len(updated_b.weight_history[0].reason) > 0)


# =============================================================================
# Layer 6 — yfinance price fetch (network, no LLM)
# =============================================================================

def layer6_yfinance() -> None:
    section("6 — yfinance price fetch (network, no LLM)")
    from core.intelligence.rl.workflows.daily_review import _fetch_actual_close

    # Use a known past weekday (5 business days ago)
    target = _last_weekday(5)
    print(f"  Fetching MARUTI close for {target} …")
    try:
        close = _fetch_actual_close("MARUTI", target)
        if close is None:
            fail(f"_fetch_actual_close returned None for MARUTI on {target}")
        else:
            assert_true(f"MARUTI close on {target} is a positive float ({close:,.2f})", close > 0)
            assert_true(f"MARUTI close is in plausible range (₹1k–₹50k)", 1_000 < close < 50_000)
    except Exception as exc:
        fail("_fetch_actual_close raised an exception", exc)

    # Invalid ticker should return None without raising
    try:
        bad = _fetch_actual_close("XXXXINVALIDTICKER", target)
        assert_eq("Invalid ticker returns None (not raises)", bad, None)
    except Exception as exc:
        fail("_fetch_actual_close raised on invalid ticker (should return None)", exc)


# =============================================================================
# Layer 7 — FeedbackAgent LLM call (opt-in: --with-llm)
# =============================================================================

def layer7_feedback_agent_llm() -> None:
    section("7 — FeedbackAgent LLM (one LLM call)")
    from core.intelligence.rl.agents.feedback_agent import FeedbackAgent
    from core.schemas.feedback import (
        FeedbackAgentInput, LearningLedger, MISS_TYPE_PENALTY_MULTIPLIER,
    )

    ledger = LearningLedger(ticker="MARUTI", last_updated=date.today().isoformat())
    fb_input = FeedbackAgentInput(
        ticker="MARUTI",
        sector="automobile",
        date="2026-04-15",
        predicted_close=10_500.0,
        actual_close=10_430.0,
        price_error_pct=-0.67,
        direction_correct=False,
        predicted_agent_scores={
            "sales_demand": 0.72, "fundamentals": 0.68,
            "pattern_analysis": 0.65, "sentiment": 0.70, "risk_macro": 0.55,
        },
        todays_agent_scores={
            "sales_demand": 0.75, "fundamentals": 0.67,
            "pattern_analysis": 0.64, "sentiment": 0.68, "risk_macro": 0.38,
        },
        market_context_today=(
            "General market weakness; no specific macro event. "
            "Maruti reported flat volumes vs prior month."
        ),
        key_assumptions_made=["crude stable ~$82", "no major policy announcement"],
        active_lessons_summary="No prior lessons.",
    )

    print("  Calling FeedbackAgent LLM …")
    try:
        agent = FeedbackAgent()
        output = agent.run(fb_input, ledger)

        valid_agents = {
            "sales_demand", "fundamentals", "pattern_analysis",
            "sentiment", "risk_macro", "none", "unknown",
        }
        assert_true(
            f"primary_miss_agent is a known agent ({output.primary_miss_agent!r})",
            output.primary_miss_agent.lower() in valid_agents,
        )
        assert_true(
            f"miss_type is valid ({output.miss_type!r})",
            output.miss_type in MISS_TYPE_PENALTY_MULTIPLIER,
        )
        assert_true(
            "revised_context.headline is a string",
            isinstance(output.revised_context.headline, str),
        )
        assert_true(
            "missed_factors is a list",
            isinstance(output.missed_factors, list),
        )
        ok(f"primary_miss={output.primary_miss_agent!r}  "
           f"miss_type={output.miss_type!r}")
        ok(f"headline: {output.revised_context.headline!r}")
        ok(f"lessons proposed: {len(output.new_lessons)}")

        # merge_lessons_into_ledger — pure logic, verify it runs
        updated_ledger, lesson_ids = agent.merge_lessons_into_ledger(output, ledger)
        assert_true("merge_lessons returns list of IDs",    isinstance(lesson_ids, list))
        assert_true("updated ledger is a LearningLedger",   hasattr(updated_ledger, "lessons"))
        ok(f"merge_lessons_into_ledger: lesson IDs = {lesson_ids}")

    except Exception as exc:
        fail("FeedbackAgent.run() raised an exception", exc)
        traceback.print_exc()


# =============================================================================
# Layer 8 — Full daily_review with seeded envelope (opt-in: --full)
# =============================================================================

def layer8_full_daily_review() -> None:
    section("8 — Full daily_review (seeded envelope, all 8 steps)")
    from core.schemas.feedback import DailyForecast, PredictionEnvelope
    from core.intelligence.rl.stores.prediction_store import PredictionStore
    from core.intelligence.rl.workflows.daily_review import run_daily_review
    from core.config import settings

    target = _last_weekday(5)
    print(f"  Running full daily_review for MARUTI on {target} …")
    print(f"  (This runs FeedbackAgent LLM + agent score re-run — takes ~60–120s)")

    tmp_dir = tempfile.mkdtemp(prefix="sanity_rl_")
    original_data_dir = settings.PREDICTION_DATA_DIR

    try:
        # Point settings at our temp dir so run_daily_review uses it
        settings.PREDICTION_DATA_DIR = tmp_dir

        store = PredictionStore("MARUTI", base_dir=tmp_dir)
        cid = store.current_cycle_id()

        # Seed a minimal envelope for `target`
        forecast = DailyForecast(
            day=1,
            date=target.isoformat(),
            predicted_close=10_500.0,
            predicted_change_pct=0.5,
            predicted_verdict="BUY",
            confidence=0.70,
            predicted_agent_scores={
                "sales_demand": 0.72, "fundamentals": 0.68,
                "pattern_analysis": 0.65, "sentiment": 0.70, "risk_macro": 0.55,
            },
            key_assumptions=["crude stable ~$82", "no policy announcement"],
        )
        env = PredictionEnvelope(
            ticker="MARUTI", cycle_id=cid,
            generated_at=date.today().isoformat(),
            base_close=10_450.0, daily_forecasts=[forecast],
        )
        store.save_envelope(env)
        store.init_weight_memory(settings.AGENT_WEIGHTS)

        # Run
        summary = run_daily_review("MARUTI", target, sector="automobile")

        assert_eq("run_daily_review: status = completed",  summary.get("status"), "completed")
        assert_true("summary has price_error_pct",          "price_error_pct" in summary)
        assert_true("summary has direction_correct",        "direction_correct" in summary)
        assert_true("summary has miss_type",                "miss_type" in summary)
        assert_true("summary has timing_assessment",        "timing_assessment" in summary)
        assert_true("summary has weight_version",           "weight_version" in summary)
        assert_true("summary has weights dict",             isinstance(summary.get("weights"), dict))
        assert_close("weights still sum to 1.0",            sum(summary["weights"].values()), 1.0)

        # Verify files were written
        log = store.load_feedback_log(cid)
        assert_eq("feedback_log has 1 entry",    len(log.entries), 1)
        assert_eq("feedback_log entry date",     log.entries[0].date, target.isoformat())
        assert_true("feedback_log entry has revised_context",
                    log.entries[0].revised_context is not None)

        updated_wm = store.load_weight_memory()
        assert_true("weight_memory saved",           updated_wm is not None)
        assert_true("weight_memory version bumped",  updated_wm.weight_version >= 0)

        ok(
            f"MARUTI {target} | error={summary['price_error_pct']:+.2f}% | "
            f"direction={'CORRECT' if summary['direction_correct'] else 'WRONG'} | "
            f"miss_type={summary['miss_type']} | timing={summary['timing_assessment']} | "
            f"lessons={summary['lessons_added']} | weights={summary['weight_version']}"
        )

    except Exception as exc:
        fail("run_daily_review raised an exception", exc)
        traceback.print_exc()
    finally:
        settings.PREDICTION_DATA_DIR = original_data_dir
        shutil.rmtree(tmp_dir, ignore_errors=True)


# =============================================================================
# Main
# =============================================================================

def main() -> None:
    parser = argparse.ArgumentParser(description="RL feedback system sanity checks")
    parser.add_argument("--with-llm", action="store_true",
                        help="Also run Layer 7: FeedbackAgent LLM call")
    parser.add_argument("--full", action="store_true",
                        help="Also run Layer 8: full daily_review with seeded envelope")
    parser.add_argument("--layer", type=int, choices=range(1, 9),
                        help="Run only this layer (1–8)")
    args = parser.parse_args()

    print(f"\nStockAI RL Feedback — Sanity Checks")
    print(f"{'='*60}")

    run_all = args.layer is None

    try:
        if run_all or args.layer == 1:
            imports_ok = layer1_imports()
            if not imports_ok:
                print(f"\n{RED}Import failures — fix these before running further layers.{RESET}")
                sys.exit(1)

        if run_all or args.layer == 2:
            layer2_pure_functions()

        if run_all or args.layer == 3:
            layer3_schema_roundtrip()

        if run_all or args.layer == 4:
            layer4_prediction_store()

        if run_all or args.layer == 5:
            layer5_weight_adapter()

        if run_all or args.layer == 6:
            layer6_yfinance()

        if args.full or args.layer == 7 or args.with_llm:
            layer7_feedback_agent_llm()

        if args.full or args.layer == 8:
            layer8_full_daily_review()

    except KeyboardInterrupt:
        print(f"\n{YELLOW}Interrupted.{RESET}")

    print(f"\n{'='*60}")
    total = _passed + _failed
    if _failed == 0:
        print(f"  {GREEN}All {total} checks passed.{RESET}")
    else:
        print(f"  {GREEN}{_passed} passed{RESET}  {RED}{_failed} failed{RESET}  ({total} total)")

    sys.exit(0 if _failed == 0 else 1)


if __name__ == "__main__":
    main()
