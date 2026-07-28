# RL Hard-Bind Verdict Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bind the graded/acted-on RL verdict to the learned composite behind one default-OFF flag, fixing the frozen-verdict reward poisoning (AUD-117) and resolving AUD-077.

**Architecture:** Two flag-gated bindings driven by a single new setting `RL_HARD_BIND_VERDICT_ENABLED`. **Binding 1** (aggregator): after the LLM report is parsed, capture the raw verdict for the shadow lane, then rebind `report.verdict = verdict_from_composite(composite)` — `final_score` untouched, so the Monte-Carlo price path is undisturbed. **Binding 2** (daily_review): grade `direction_correct` against the *fresh daily* verdict (which, under Binding 1, is the threshold verdict) from the orchestrator re-run the workflow already performs, instead of the frozen month-start `predicted_verdict`; skip-rerun days keep the frozen fallback. Merged OFF ⇒ byte-identical no-op deploy.

**Tech Stack:** Python 3.13, Pydantic v2, pytest. Config via `cfg()` (env > config.yaml > fallback). Canonical source tree is `src/backend/shared/…` (the `core/pipeline/signal_aggregator.py` file is only a re-export shim — never edit it).

## Global Constraints

- **One flag, default OFF:** `RL_HARD_BIND_VERDICT_ENABLED: bool` (fallback `False`). Merged OFF ⇒ byte-identical no-op deploy. Rollback = set flag false.
- **No hardcoded magic:** the flag goes through `cfg("rl.hard_bind_verdict_enabled", env="RL_HARD_BIND_VERDICT_ENABLED", fallback=False)` and `config.yaml` (`rl.hard_bind_verdict_enabled: false`). [[feedback-config-over-hardcode]]
- **Never touch `report.final_score`,** the MC price path, `envelope_direction`, EXIT/TRIM logic, or stored/historical `predicted_verdict` / `direction_correct` rows. `direction_correct` semantics change **forward** from enable-date only (deliberate accuracy-series break, cf. AUD-060).
- **Canonical tree:** edit `src/backend/shared/pipeline/signal_aggregator.py`, NOT `core/pipeline/signal_aggregator.py` (shim).
- **A/B fail-set gate:** after each task and at the end, the full-suite fail-set must equal the known-red baseline (**10F / 10E**: AUD-022 stale mocks + event_ingestor date test). Adding failures is a regression.
- **Dev shell is Windows PowerShell.** Run pytest via the project interpreter (`python -m pytest ...`).

---

### Task 1: Feature flag (settings + config.yaml)

**Files:**
- Modify: `src/backend/shared/config/settings/base.py` (RL block, immediately after `RL_CALIBRATION_WEIGHT` ~line 571)
- Modify: `config.yaml` (under `rl:`, near `calibration_reward_enabled` ~line 266)
- Test: `tests/unit/shared/test_hard_bind_flag.py` (create)

**Interfaces:**
- Produces: `settings.RL_HARD_BIND_VERDICT_ENABLED: bool` — default `False`; consumed by Tasks 2 and 4.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/shared/test_hard_bind_flag.py
"""AUD-117 / AUD-077 — hard-bind verdict flag defaults OFF (byte-identical deploy)."""
from backend.shared.config import settings


def test_hard_bind_flag_exists_and_is_bool():
    assert isinstance(settings.RL_HARD_BIND_VERDICT_ENABLED, bool)


def test_hard_bind_flag_defaults_off():
    # Merged OFF ⇒ deploy is a byte-identical no-op (spec §3.1).
    assert settings.RL_HARD_BIND_VERDICT_ENABLED is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/shared/test_hard_bind_flag.py -v`
Expected: FAIL — `AttributeError: module 'backend.shared.config.settings' has no attribute 'RL_HARD_BIND_VERDICT_ENABLED'`.

- [ ] **Step 3: Add the setting**

In `src/backend/shared/config/settings/base.py`, immediately after the `RL_CALIBRATION_WEIGHT` line (~571):

```python
# ---------------------------------------------------------------------------
# AUD-117 / AUD-077 — Hard-bind the graded/acted-on verdict to the learned
# composite. When True: (1) SignalAggregator.run rebinds report.verdict to
# verdict_from_composite(composite) (final_score untouched); (2) daily_review
# grades direction_correct against the FRESH daily (threshold) verdict instead
# of the frozen month-start predicted_verdict. Default OFF ⇒ byte-identical.
# ---------------------------------------------------------------------------
RL_HARD_BIND_VERDICT_ENABLED: bool = cfg(
    "rl.hard_bind_verdict_enabled", env="RL_HARD_BIND_VERDICT_ENABLED", fallback=False)
```

- [ ] **Step 4: Add the config.yaml default**

In `config.yaml`, under `rl:`, just after the calibration-reward block (~line 267):

```yaml
  # -- Hard-bind verdict (AUD-117 / AUD-077) -------------------------------
  hard_bind_verdict_enabled: false   # bind graded+aggregator verdict to learned composite
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/unit/shared/test_hard_bind_flag.py -v`
Expected: PASS (2 passed).

- [ ] **Step 6: Commit**

```bash
git add src/backend/shared/config/settings/base.py config.yaml tests/unit/shared/test_hard_bind_flag.py
git commit -m "feat(rl): add RL_HARD_BIND_VERDICT_ENABLED flag (default off) — AUD-117"
```

---

### Task 2: Binding 1 — aggregator verdict bind

**Files:**
- Modify: `src/backend/shared/pipeline/signal_aggregator.py` (lines ~192–204, the `_parse` → shadow-log → return block)
- Test: `tests/unit/shared/test_signal_aggregator.py` (append a `TestHardBindVerdict` class)

**Interfaces:**
- Consumes: `settings.RL_HARD_BIND_VERDICT_ENABLED` (Task 1); `verdict_from_composite(composite: float) -> str` (existing, `backend.shared.pipeline.verdict_shadow`).
- Produces: under the flag, `report.verdict == verdict_from_composite(composite)`; the shadow row's `llm_verdict` is the **raw** LLM verdict in both flag states; `report.final_score` never overridden.

- [ ] **Step 1: Confirm the settings import in the test file**

`tests/unit/shared/test_signal_aggregator.py` must import the settings module for patching. If it does not already have it, add near the top imports:

```python
from backend.shared.config import settings
```

(The file already imports `pytest`, `patch`, and `SignalAggregator`.)

- [ ] **Step 2: Write the failing tests**

Append to `tests/unit/shared/test_signal_aggregator.py`:

```python
class TestHardBindVerdict:
    """AUD-117/AUD-077 Binding 1: under the flag, report.verdict is rebound to
    the composite→threshold verdict; the shadow lane still logs the RAW LLM
    verdict; final_score is never overridden."""

    def _make_output(self, name, score, error=""):
        from core.schemas.pipeline import AgentOutput
        return AgentOutput(agent=name, ticker="MARUTI", overall_score=score, error=error)

    def _run(self, outputs, weights, flag_on):
        from tests.conftest import make_aggregator_json
        shadow_kwargs = {}

        def fake_llm(system_prompt, user_prompt):
            return make_aggregator_json(0.66)          # verdict="BUY", final_score=0.66

        def fake_shadow(**kwargs):
            shadow_kwargs.update(kwargs)
            return None

        with patch.object(SignalAggregator, "_call_llm", side_effect=fake_llm), \
             patch("backend.shared.pipeline.verdict_shadow.log_verdict_shadow", fake_shadow), \
             patch("services.clients.llm_client.OpenAI"), \
             patch.object(settings, "RL_HARD_BIND_VERDICT_ENABLED", flag_on):
            agg = SignalAggregator()
            report = agg.run("MARUTI", "Maruti Suzuki India Ltd", outputs,
                             learned_weights=weights)
        return report, shadow_kwargs

    def test_flag_off_verdict_and_shadow_unchanged(self):
        # composite = 0.1 (both agents 0.1) -> threshold verdict would be STRONG SELL,
        # but flag OFF must leave the raw LLM "BUY" verdict in place.
        outputs = {"sales_demand": self._make_output("sales_demand", 0.1),
                   "fundamentals": self._make_output("fundamentals", 0.1)}
        weights = {"sales_demand": 0.5, "fundamentals": 0.5}
        report, shadow = self._run(outputs, weights, flag_on=False)
        assert report.verdict == "BUY"                    # raw LLM verdict, untouched
        assert shadow["llm_verdict"] == "BUY"
        assert report.final_score == pytest.approx(0.66)

    def test_flag_on_verdict_bound_shadow_keeps_raw(self):
        from backend.shared.pipeline.verdict_shadow import verdict_from_composite
        outputs = {"sales_demand": self._make_output("sales_demand", 0.1),
                   "fundamentals": self._make_output("fundamentals", 0.1)}
        weights = {"sales_demand": 0.5, "fundamentals": 0.5}
        report, shadow = self._run(outputs, weights, flag_on=True)
        assert verdict_from_composite(0.1) == "STRONG SELL"   # lock the band map
        assert report.verdict == "STRONG SELL"                # bound to composite
        assert shadow["llm_verdict"] == "BUY"                 # shadow logs RAW, not bound
        assert report.final_score == pytest.approx(0.66)      # final_score NEVER overridden
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/unit/shared/test_signal_aggregator.py::TestHardBindVerdict -v`
Expected: `test_flag_off_...` PASSES (current behavior already leaves "BUY"); `test_flag_on_...` FAILS with `assert 'BUY' == 'STRONG SELL'` (bind not implemented yet).

- [ ] **Step 4: Implement the bind**

In `src/backend/shared/pipeline/signal_aggregator.py`, replace the block that currently reads (lines ~192–204):

```python
        report = self._parse(raw, ticker, company_name, weighted_scores, agent_outputs)
        # AUD-077 shadow lane (observe-only): what the verdict WOULD be if
        # bound to the learned composite — never substituted for the LLM's.
        from backend.shared.pipeline.verdict_shadow import log_verdict_shadow
        log_verdict_shadow(
            ticker=ticker,
            composite=composite,
            llm_verdict=report.verdict,
            llm_final_score=report.final_score,
            learned_weights_used=bool(learned_weights),
            sector=sector,
        )
        return report
```

with:

```python
        report = self._parse(raw, ticker, company_name, weighted_scores, agent_outputs)
        # AUD-077/AUD-117 hard-bind. Capture the RAW LLM verdict FIRST so the
        # shadow lane keeps comparing raw-LLM vs threshold even after the bind.
        raw_llm_verdict = report.verdict
        from backend.shared.pipeline.verdict_shadow import (
            log_verdict_shadow,
            verdict_from_composite,
        )
        log_verdict_shadow(
            ticker=ticker,
            composite=composite,
            llm_verdict=raw_llm_verdict,
            llm_final_score=report.final_score,
            learned_weights_used=bool(learned_weights),
            sector=sector,
        )
        # Bind only the categorical verdict to the learned composite; final_score
        # is left as the LLM's (it feeds base_confidence -> MC path width, so the
        # price path is undisturbed). Deterministic verdict unblocks AUD-098.
        if settings.RL_HARD_BIND_VERDICT_ENABLED:
            report.verdict = verdict_from_composite(composite)
        return report
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/unit/shared/test_signal_aggregator.py -v`
Expected: PASS — the new `TestHardBindVerdict` cases green **and** every pre-existing aggregator test still green (byte-identical flag-off path).

- [ ] **Step 6: Commit**

```bash
git add src/backend/shared/pipeline/signal_aggregator.py tests/unit/shared/test_signal_aggregator.py
git commit -m "feat(rl): Binding 1 — flag-gated aggregator verdict bind, shadow keeps raw (AUD-077)"
```

---

### Task 3: `FeedbackEntry.graded_verdict` schema field

**Files:**
- Modify: `src/backend/shared/schemas/feedback.py` (`FeedbackEntry`, right after `direction_correct: bool` ~line 273)
- Test: `tests/unit/shared/test_feedback_graded_verdict.py` (create)

**Interfaces:**
- Produces: `FeedbackEntry.graded_verdict: str` (default `""`) — the verdict `direction_correct` was actually graded against; consumed/persisted by Task 4.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/shared/test_feedback_graded_verdict.py
"""AUD-117 — FeedbackEntry records the verdict direction_correct was graded against."""
from backend.shared.schemas.feedback import FeedbackEntry


def _entry(**over):
    base = dict(day=1, date="2026-07-28", predicted_close=100.0, actual_close=99.0,
                price_error_pct=-1.0, predicted_verdict="BUY",
                actual_direction="DOWN", direction_correct=False)
    base.update(over)
    return FeedbackEntry(**base)


def test_graded_verdict_defaults_empty():
    # Backward-compatible: entries written before the field carry "".
    assert _entry().graded_verdict == ""


def test_graded_verdict_set_and_roundtrips():
    e = _entry(graded_verdict="STRONG SELL")
    assert e.graded_verdict == "STRONG SELL"
    assert FeedbackEntry(**e.model_dump()).graded_verdict == "STRONG SELL"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/shared/test_feedback_graded_verdict.py -v`
Expected: FAIL — `AttributeError: 'FeedbackEntry' object has no attribute 'graded_verdict'`.

- [ ] **Step 3: Add the field**

In `src/backend/shared/schemas/feedback.py`, inside `FeedbackEntry`, immediately after `direction_correct: bool` (line ~273):

```python
    # AUD-117: the verdict direction_correct was actually graded against. Under
    # the hard-bind flag + a fresh daily re-run this is the daily threshold
    # verdict; otherwise it equals predicted_verdict (frozen month-start). ""
    # for entries written before the field existed (backward-compatible).
    graded_verdict: str = ""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/shared/test_feedback_graded_verdict.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/backend/shared/schemas/feedback.py tests/unit/shared/test_feedback_graded_verdict.py
git commit -m "feat(rl): add FeedbackEntry.graded_verdict (default empty) — AUD-117"
```

---

### Task 4: Binding 2 — daily_review grades against the bound verdict

**Files:**
- Modify: `core/intelligence/rl/workflows/daily_review.py`
  - `_run_todays_agent_scores` (~line 207): add a `capture` out-param
  - grading init (~line 547): initialize `graded_verdict`
  - re-run else-branch (~lines 573–584): pass `capture`, add flag-ON override
  - both `FeedbackEntry(...)` constructions (~lines 978 and 1266): persist `graded_verdict`
- Test: `tests/unit/intelligence/rl/test_hard_bind_daily_review.py` (create)

**Interfaces:**
- Consumes: `settings.RL_HARD_BIND_VERDICT_ENABLED` (Task 1); `is_direction_correct` (already imported at line 37); `FeedbackEntry.graded_verdict` (Task 3); the fresh report's `.verdict` from `orchestrator.analyse` (a `FinalReport`).
- Produces: when flag ON **and** a fresh daily report exists, `direction_correct = is_direction_correct(fresh_report.verdict, actual_direction)` and `graded_verdict = fresh_report.verdict`; on skip-rerun days or flag OFF, both fall back to the frozen `today_forecast.predicted_verdict`.

**Design note (why an out-param, not a new function):** three existing tests (`test_shock_path`, `test_daily_review_dossier`, `test_paper_lane_isolation`) monkeypatch `_run_todays_agent_scores` to return a fixed scores dict. Keeping that function's name and dict return keeps them green with zero edits, and the optional `capture` dict lets the workflow reuse the **same** re-run's verdict without a second (costly) orchestrator pass. All three stubs use `lambda *a, **k:` so the extra `capture=` kwarg is harmless.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/intelligence/rl/test_hard_bind_daily_review.py
"""AUD-117 Binding 2 — daily_review grades direction_correct against the FRESH
daily verdict (the threshold verdict under Binding 1) from the same orchestrator
re-run, not the frozen month-start predicted_verdict. Skip-rerun days keep the
frozen fallback. Flag OFF => unchanged."""
from __future__ import annotations

from types import SimpleNamespace

from tests.unit.intelligence.rl.test_shock_path import (
    TICKER, SECTOR, REVIEW_DATE,
    _patch_common, _setup_store, _fb_output,
)


def _stub_fresh_report(dr, monkeypatch, verdict):
    """Replace _run_todays_agent_scores with a stub that returns fixed scores AND
    populates the capture out-param with a fresh report carrying `verdict`
    (mimics orchestrator.analyse without a real LLM run)."""
    def _stub(*a, **k):
        cap = k.get("capture")
        if cap is not None:
            cap["report"] = SimpleNamespace(verdict=verdict)
        return {"risk_macro": 0.5, "sales_demand": 0.5}
    monkeypatch.setattr(dr, "_run_todays_agent_scores", _stub)


def _quiet_feedback(dr, monkeypatch):
    from core.intelligence.rl.agents.feedback_agent import FeedbackAgent
    monkeypatch.setattr(FeedbackAgent, "run",
                        lambda self, fb_input, ledger: _fb_output("magnitude"))
    monkeypatch.setattr(dr, "regenerate_envelope", lambda **kw: None)
    monkeypatch.setattr(dr, "_revise_remaining_forecasts", lambda **kw: None)


def test_flag_on_grades_against_fresh_bound_verdict(tmp_path, monkeypatch):
    import core.intelligence.rl.workflows.daily_review as dr
    store, cycle_id = _setup_store(tmp_path, verdict="BUY")       # frozen = BUY
    _patch_common(dr, monkeypatch, tmp_path, actual_close=98.0)   # -2% => DOWN
    _quiet_feedback(dr, monkeypatch)
    monkeypatch.setattr(dr.settings, "RL_HARD_BIND_VERDICT_ENABLED", True)
    _stub_fresh_report(dr, monkeypatch, verdict="STRONG SELL")    # correct on DOWN

    summary = dr.run_daily_review(TICKER, REVIEW_DATE, sector=SECTOR)

    assert summary["direction_correct"] is True                  # graded on STRONG SELL
    entry = store.load_feedback_log(cycle_id).get_entry(REVIEW_DATE.isoformat())
    assert entry.graded_verdict == "STRONG SELL"
    assert entry.direction_correct is True
    assert entry.predicted_verdict == "BUY"                      # frozen thesis NOT rewritten


def test_flag_off_grades_against_frozen_verdict(tmp_path, monkeypatch):
    import core.intelligence.rl.workflows.daily_review as dr
    store, cycle_id = _setup_store(tmp_path, verdict="BUY")
    _patch_common(dr, monkeypatch, tmp_path, actual_close=98.0)   # DOWN
    _quiet_feedback(dr, monkeypatch)
    monkeypatch.setattr(dr.settings, "RL_HARD_BIND_VERDICT_ENABLED", False)
    _stub_fresh_report(dr, monkeypatch, verdict="STRONG SELL")    # would flip it IF read

    summary = dr.run_daily_review(TICKER, REVIEW_DATE, sector=SECTOR)

    assert summary["direction_correct"] is False                 # frozen BUY vs DOWN = wrong
    entry = store.load_feedback_log(cycle_id).get_entry(REVIEW_DATE.isoformat())
    assert entry.graded_verdict == "BUY"                         # == frozen predicted_verdict


def test_flag_on_skip_rerun_falls_back_to_frozen(tmp_path, monkeypatch):
    """Direction correct + tiny error => orchestrator re-run skipped => no fresh
    report => grading falls back to the frozen envelope verdict."""
    import core.intelligence.rl.workflows.daily_review as dr
    store, cycle_id = _setup_store(tmp_path, verdict="BUY")
    _patch_common(dr, monkeypatch, tmp_path, actual_close=101.0)  # +1% => UP => BUY correct
    _quiet_feedback(dr, monkeypatch)
    monkeypatch.setattr(dr.settings, "RL_HARD_BIND_VERDICT_ENABLED", True)
    monkeypatch.setattr(dr.settings, "RL_AGENT_RERUN_THRESHOLD_PCT", 5.0)  # |1%|<5% => skip
    _stub_fresh_report(dr, monkeypatch, verdict="STRONG SELL")    # never consulted on skip

    summary = dr.run_daily_review(TICKER, REVIEW_DATE, sector=SECTOR)

    assert summary["direction_correct"] is True                  # frozen BUY vs UP = correct
    entry = store.load_feedback_log(cycle_id).get_entry(REVIEW_DATE.isoformat())
    assert entry.graded_verdict == "BUY"                         # frozen fallback, no re-run
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/intelligence/rl/test_hard_bind_daily_review.py -v`
Expected: `test_flag_on_grades_against_fresh_bound_verdict` FAILS (`summary["direction_correct"]` is still `False` — override not implemented; and `entry.graded_verdict` is `""`). The flag-off and skip-rerun cases may already pass except the `graded_verdict` assertion, which fails until persistence is added.

- [ ] **Step 3: Add the `capture` out-param to `_run_todays_agent_scores`**

In `core/intelligence/rl/workflows/daily_review.py`, change the signature (~line 207) and populate `capture` before the return:

```python
def _run_todays_agent_scores(
    ticker: str,
    sector: str = "automobile",
    learned_weights: dict[str, float] | None = None,
    capture: dict | None = None,
) -> dict[str, float]:
    """
    Re-run all sub-agents with live data to compute today's scores.
    Used to measure agent_score_drift vs the frozen predicted scores.

    Routes to the correct orchestrator/graph based on sector.
    Falls back to empty dict on any failure (non-fatal).

    AUD-117: when `capture` is provided, the fresh FinalReport is stored at
    capture["report"] so the caller can reuse this single re-run's verdict for
    hard-bind grading (avoids a second orchestrator pass). Left unset on failure.
    """
    try:
        from core.intelligence.rl.workflows.sector_router import get_orchestrator
        orchestrator = get_orchestrator(sector)
        if learned_weights:
            orchestrator.set_aggregator_weights(learned_weights, ticker)
        report = orchestrator.analyse(ticker)
        if capture is not None:
            capture["report"] = report
        return {name: ws.raw for name, ws in report.weighted_agent_scores.items()}
    except Exception as exc:
        logger.warning(
            "[daily_review] Agent re-run failed for %s (%s): %s", ticker, sector, exc
        )
        return {}
```

- [ ] **Step 4: Initialize `graded_verdict` next to the frozen grading**

In `run_daily_review`, right after the frozen grading line (~line 547):

```python
    actual_direction = classify_direction(actual_close, predicted_close)
    direction_correct = is_direction_correct(today_forecast.predicted_verdict, actual_direction)
    # AUD-117: the verdict grading is actually done against. Defaults to the
    # frozen envelope verdict (skip-rerun days + flag OFF); overridden below to
    # the fresh daily verdict when the hard-bind flag is on and a re-run exists.
    graded_verdict = today_forecast.predicted_verdict
```

- [ ] **Step 5: Capture the fresh report and override grading in the else-branch**

Replace the re-run `else:` block (~lines 573–584) so it passes `capture` and applies the flag-gated override after the existing scores handling:

```python
    else:
        _todays_capture: dict = {}
        todays_scores = _run_todays_agent_scores(
            ticker,
            sector=sector,
            learned_weights=wm_for_scores.effective_weights() if wm_for_scores else None,
            capture=_todays_capture,
        )
        if not todays_scores and today_forecast.predicted_agent_scores:
            todays_scores = dict(today_forecast.predicted_agent_scores)
            logger.info(
                "[daily_review] Agent re-run unavailable for %s — "
                "using envelope predicted scores as fallback for drift analysis", ticker,
            )
        # AUD-117 Binding 2: grade against the FRESH daily verdict (the threshold
        # verdict under Binding 1) from this same re-run, not the frozen
        # month-start predicted_verdict. Flag OFF or no fresh report => unchanged.
        if settings.RL_HARD_BIND_VERDICT_ENABLED:
            _fresh_report = _todays_capture.get("report")
            if _fresh_report is not None:
                graded_verdict = _fresh_report.verdict
                direction_correct = is_direction_correct(graded_verdict, actual_direction)
                logger.info(
                    "[daily_review] %s hard-bind grading: %s -> %s | direction_correct=%s",
                    ticker, today_forecast.predicted_verdict, graded_verdict, direction_correct,
                )
```

- [ ] **Step 6: Persist `graded_verdict` on both FeedbackEntry constructions**

In the **provisional** entry (~line 978) add `graded_verdict=graded_verdict` next to `direction_correct=direction_correct`:

```python
        predicted_verdict=today_forecast.predicted_verdict,
        actual_direction=actual_direction,
        direction_correct=direction_correct,
        graded_verdict=graded_verdict,
```

In the **final** entry (~line 1266) add the same line next to its `direction_correct=direction_correct`:

```python
        predicted_verdict=today_forecast.predicted_verdict,
        actual_direction=actual_direction,
        direction_correct=direction_correct,
        graded_verdict=graded_verdict,
        regime_label=sticky_regime_label,
```

- [ ] **Step 7: Run the new tests to verify they pass**

Run: `python -m pytest tests/unit/intelligence/rl/test_hard_bind_daily_review.py -v`
Expected: PASS (3 passed).

- [ ] **Step 8: Run the three pre-existing tests that patch `_run_todays_agent_scores`**

Run: `python -m pytest tests/unit/intelligence/rl/test_shock_path.py tests/unit/intelligence/rl/test_daily_review_dossier.py tests/unit/intelligence/rl/test_paper_lane_isolation.py -v`
Expected: PASS — unchanged (their `lambda *a, **k:` stubs absorb the new `capture=` kwarg; flag defaults OFF so grading is byte-identical).

- [ ] **Step 9: Commit**

```bash
git add core/intelligence/rl/workflows/daily_review.py tests/unit/intelligence/rl/test_hard_bind_daily_review.py
git commit -m "feat(rl): Binding 2 — daily_review grades against fresh bound verdict, records graded_verdict (AUD-117)"
```

---

### Task 5: Full-suite A/B fail-set verification

**Files:** none (verification checkpoint).

- [ ] **Step 1: Run the full suite**

Run: `python -m pytest -q 2>&1 | tail -30`

- [ ] **Step 2: Confirm the fail-set equals the known-red baseline**

Expected: exactly the known-red baseline — **10 failed / 10 errored** (AUD-022 stale mocks + the event_ingestor date test), plus the **7 new tests** from Tasks 1–4 passing. No *new* failures or errors. If any new red appears, STOP and diagnose (use superpowers:systematic-debugging) — the flag-off path must be inert.

- [ ] **Step 3: Prove flag-off inertness on the two touched modules**

Run: `python -m pytest tests/unit/shared/test_signal_aggregator.py tests/unit/shared/test_verdict_shadow.py tests/unit/intelligence/rl/ -q`
Expected: no regressions vs. baseline; every prior test in these paths still green.

---

### Task 6: Ledger + spec status update (docs)

**Files:**
- Modify: `docs/audit/LEDGER.md` (append a new wave section)
- Modify: `docs/superpowers/specs/2026-07-28-rl-hard-bind-verdict-design.md` (status line)

- [ ] **Step 1: Append the ledger wave section**

At the end of `docs/audit/LEDGER.md`:

```markdown
## Hard-Bind Verdict — AUD-077 decision + AUD-117 fix (2026-07-28, branch rl-hard-bind-verdict)

Merged flag OFF (`RL_HARD_BIND_VERDICT_ENABLED`, default false) → byte-identical
no-op deploy; prod-enable gated on user go. Analysis (fresh prod pull, n=81):
three verdict channels, not two — the graded/acted-on `predicted_verdict` is a
FROZEN month-start value (14.8% dir-acc) vs the daily threshold verdict (33.3%);
threshold beats production 16–1, sign-test p=0.0003. Spec:
docs/superpowers/specs/2026-07-28-rl-hard-bind-verdict-design.md.

- **AUD-077 | PATTERN | P1 → DECISION MADE (BIND, flag-gated).** Binding 1:
  `SignalAggregator.run` rebinds `report.verdict = verdict_from_composite(composite)`
  under the flag (final_score untouched; shadow lane still logs RAW llm_verdict vs
  threshold). Aggregator verdict now deterministic.
- **AUD-117 | DESIGN | P1 | NEW → FIXED (Binding 2).** Frozen month-start
  `predicted_verdict`, stamped on every envelope day, poisoned the RL reward signal
  + ADD gate. daily_review now grades `direction_correct` against the fresh daily
  (threshold) verdict from the same orchestrator re-run; skip-rerun days fall back
  to the frozen value; the graded verdict is recorded on `FeedbackEntry.graded_verdict`.
  Stored envelope verdicts + historical `direction_correct` are never rewritten
  (forward-only break, cf. AUD-060).
- **AUD-098 | COST | P3 | UNBLOCKED.** Aggregator verdict now deterministic →
  thesis_reviewer/control_lane down-tier A/B no longer gated on the RL-semantics
  verdict (still bench-gated).
```

- [ ] **Step 2: Flip the spec status**

In `docs/superpowers/specs/2026-07-28-rl-hard-bind-verdict-design.md`, change line 4 from:

```markdown
**Status:** APPROVED (design), pending spec review → plan
```

to:

```markdown
**Status:** SHIPPED (flag OFF, byte-identical no-op) — pending prod-enable on user go
```

- [ ] **Step 3: Commit**

```bash
git add docs/audit/LEDGER.md docs/superpowers/specs/2026-07-28-rl-hard-bind-verdict-design.md
git commit -m "docs(rl): ledger + spec status — hard-bind shipped flag-off (AUD-077/117/098)"
```

---

## Rollout (post-merge, not part of TDD)

Merge to main with the flag OFF (no-op deploy). Enable via `config.yaml`
`rl.hard_bind_verdict_enabled: true` (or the Railway env var) when the user gives
the go — ideally after the optional 2026-07-31 reconfirmation re-run (`p=0.0003`
is already decisive, so this is confirmation, not a gate). Watch the first
post-enable `daily_review`: `direction_correct` should track the daily threshold
verdict and `graded_verdict` should be populated; the shadow lane keeps logging
raw-LLM vs threshold. Rollback = set the flag false (instant; no redeploy if
env-driven). Avoid pushing to main 16:25–17:15 IST on trading days.

## Self-Review

**Spec coverage:**
- §3.1 flag → Task 1. §3.2 Binding 1 (capture raw, shadow logs raw, bind under flag, final_score untouched) → Task 2. §3.3 Binding 2 (grade against fresh rerun, skip-rerun fallback, `graded_verdict` field) → Tasks 3 + 4. §5 testing (band boundary, flag on/off aggregator, shadow raw, daily grading + fallback, full-suite A/B) → Tasks 2, 4, 5. §7 ledger → Task 6. Non-goals (§4: no final_score/price-path/envelope_direction/EXIT-TRIM/history rewrite) honored — none of those files are touched.
- Per-sector `SCORE_THRESHOLDS` (§2/§4) is explicitly DEFERRED — no task, by design.

**Placeholder scan:** none — every step carries concrete code or an exact command + expected output.

**Type consistency:** `verdict_from_composite(float) -> str`, `is_direction_correct(str, str) -> bool`, `FeedbackEntry.graded_verdict: str`, `_run_todays_agent_scores(..., capture: dict | None) -> dict[str, float]` with `capture["report"].verdict: str` — consistent across Tasks 2–4. Flag name `RL_HARD_BIND_VERDICT_ENABLED` identical in Tasks 1, 2, 4.
