# Audit LLM Cost Wave (AUD-087, 092–094, 096, 097) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the fixable LLM cost/telemetry findings from Lighthouse Phase 5 slice 1: disable paid-and-discarded reasoning on chat (092), make every LLM call land in telemetry (093), sum real usage into run summaries (087), fix the chat fallback docstring/stale-literal and route both chat paths through the resilience helper (094), retire the `LLM_MODEL` catch-all alias (096), and route all inline `OpenAI(...)` constructions through the `get_llm_client()` factory (097).

**Architecture:** All changes are parameter/instrumentation-level — no behavior of any LLM prompt or parse changes. Telemetry uses the existing `services.clients.llm_client.record_llm_call` (never raises). Run-summary totals flow through new excluded-from-serialisation fields on `AgentOutput` plus a pure module-level `sum_run_usage()` helper.

**Tech Stack:** Python, pytest, pydantic v2, openai SDK (OpenRouter).

**Explicitly OUT of scope (user-decision rows):** AUD-095 (legacy DAG deletion → Wave-2 docket), AUD-098 (tier down-shift → bench-gated, control-lane blocked on AUD-060/077).

## Global Constraints

- Every `response_format={"type": "json_object"}` call MUST pass `extra_body=JSON_MODE_EXTRA_BODY` (house rule; already true — do not regress).
- `record_llm_call(caller, model, input_tokens, output_tokens, latency_ms, success)` — exact positional signature; it never raises.
- Chat fallback escalation FAST→REASONING is DELIBERATE (comment at ui_data.py:2979 says "escalate") — fix the docstring, not the direction.
- No renaming of prompts, temperatures, max_tokens, or tiers anywhere (098 is out of scope).
- Baseline test failures (AUD-022 stale mocks ~19) are pre-existing — the bar is "no NEW failures".
- Pushing to main auto-deploys to Railway prod — push only at the end, after full suite.

---

### Task 0: Baseline

- [ ] **Step 1:** `python -m pytest tests -q` — record pass/fail counts as the baseline (expect ~19 pre-existing failures per AUD-022).

---

### Task 1: Chat hardening — AUD-092 + 094 + chat half of 093

**Files:**
- Modify: `services/api/routes/ui_data.py` (imports ~line 25; `_CHAT_FALLBACK_MODEL` fallback literal :2982; `_chat_completion` :2995-3013; non-stream calls :2915, :2948)
- Test: `tests/unit/test_chat_llm_hardening.py` (create)

**Interfaces:**
- Produces: `_chat_completion(client, *, models=None, caller="ui_chat", **kwargs)` — same return, now defaults `extra_body` to reasoning-off and records every attempt to telemetry.

- [ ] **Step 1: Write failing tests** (`tests/unit/test_chat_llm_hardening.py`):

```python
"""AUD-092/093/094: chat calls disable reasoning + record telemetry."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import services.clients.llm_client as llm_mod
from services.api.routes.ui_data import _chat_completion, _CHAT_FALLBACK_MODEL


def _fake_resp():
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="hi", tool_calls=None))],
        usage=SimpleNamespace(prompt_tokens=11, completion_tokens=7),
    )


def _fake_client(side_effect=None):
    create = AsyncMock(return_value=_fake_resp(), side_effect=side_effect)
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


@pytest.fixture
def recorded(monkeypatch):
    calls = []
    monkeypatch.setattr(llm_mod, "record_llm_call", lambda *a: calls.append(a))
    return calls


def test_reasoning_disabled_by_default(recorded):
    client = _fake_client()
    asyncio.run(_chat_completion(client, messages=[], temperature=0.4, max_tokens=600))
    kwargs = client.chat.completions.create.call_args.kwargs
    assert kwargs["extra_body"] == {"reasoning": {"enabled": False}}


def test_explicit_extra_body_wins(recorded):
    client = _fake_client()
    asyncio.run(_chat_completion(client, messages=[], extra_body={"x": 1}))
    assert client.chat.completions.create.call_args.kwargs["extra_body"] == {"x": 1}


def test_success_recorded(recorded):
    asyncio.run(_chat_completion(_fake_client(), messages=[]))
    assert len(recorded) == 1
    caller, model, pt, ct, latency, success = recorded[0]
    assert caller == "ui_chat" and pt == 11 and ct == 7 and success is True


def test_nontransient_failure_recorded_and_raised(recorded):
    client = _fake_client(side_effect=ValueError("boom"))
    with pytest.raises(ValueError):
        asyncio.run(_chat_completion(client, messages=[]))
    assert len(recorded) == 1 and recorded[0][5] is False


def test_stale_fallback_literal_gone():
    assert _CHAT_FALLBACK_MODEL != "qwen/qwen3.7-max"
```

- [ ] **Step 2:** `python -m pytest tests/unit/test_chat_llm_hardening.py -q` → expect FAIL (no `extra_body`, no recording).
- [ ] **Step 3: Implement.** In `ui_data.py`: add `import time` to the stdlib import block; change the except-branch literal `_CHAT_FALLBACK_MODEL = "qwen/qwen3.7-max"` → `"z-ai/glm-5.2"`; replace `_chat_completion` with:

```python
async def _chat_completion(client, *, models: tuple[str, ...] | list[str] | None = None,
                           caller: str = "ui_chat", **kwargs):
    """
    chat.completions.create with resilience: retry the primary model on transient
    rate-limit/5xx errors (exponential backoff), then ESCALATE to the reasoning
    tier (deliberate: quality over cost while the fast tier is rate-limited).
    `models` overrides the model chain (used by the model-comparison harness).
    Raises the last exception only if every model+retry is exhausted.
    AUD-092: reasoning is disabled by default — chat output is user-visible text
    and <think> blocks are stripped downstream, so paying for them is waste.
    AUD-093: every attempt is recorded to telemetry.
    """
    from services.clients.llm_client import JSON_MODE_EXTRA_BODY, record_llm_call
    kwargs.setdefault("extra_body", JSON_MODE_EXTRA_BODY)
    last_exc: Exception | None = None
    for model in (models or (_CHAT_MODEL, _CHAT_FALLBACK_MODEL)):
        for attempt in range(3):
            t0 = time.monotonic()
            try:
                resp = await client.chat.completions.create(model=model, **kwargs)
            except Exception as exc:  # noqa: BLE001 — inspect then re-raise non-transient
                record_llm_call(caller, model, 0, 0, int((time.monotonic() - t0) * 1000), False)
                last_exc = exc
                if not _is_transient_llm_error(exc):
                    raise
                await asyncio.sleep(0.8 * (2 ** attempt))  # 0.8s, 1.6s, 3.2s
            else:
                usage = getattr(resp, "usage", None)
                record_llm_call(
                    caller, model,
                    getattr(usage, "prompt_tokens", 0) or 0,
                    getattr(usage, "completion_tokens", 0) or 0,
                    int((time.monotonic() - t0) * 1000), True,
                )
                return resp
        logger.warning("[chat] model %s exhausted retries — falling back", model)
    raise last_exc  # type: ignore[misc]
```

Then route the non-stream endpoint through it (AUD-094): at :2915 replace
`resp = await client.chat.completions.create(model=_CHAT_MODEL, messages=messages, temperature=0.4, max_tokens=600, tools=_CHAT_TOOLS, tool_choice="auto")` with
`resp = await _chat_completion(client, messages=messages, temperature=0.4, max_tokens=600, tools=_CHAT_TOOLS, tool_choice="auto")`, and at :2948 replace
`resp = await client.chat.completions.create(model=_CHAT_MODEL, messages=messages, temperature=0.4, max_tokens=600)` with
`resp = await _chat_completion(client, messages=messages, temperature=0.4, max_tokens=600)`.

- [ ] **Step 4:** `python -m pytest tests/unit/test_chat_llm_hardening.py -q` → PASS.
- [ ] **Step 5:** Commit: `fix(chat): disable reasoning on chat calls, record telemetry, unify resilience path (AUD-092/093/094)`

---

### Task 2: Run-summary usage totals — AUD-087

**Files:**
- Modify: `src/backend/shared/schemas/pipeline.py` (AgentOutput, after `error` field :126)
- Modify: `src/backend/shared/pipeline/base_agent.py` (:117-126 sync, :158-167 async)
- Modify: `src/backend/shared/pipeline/base_orchestrator.py` (module-level helper; log_run_summary sites :154, :214; `_run_unified` :481; `_resolve_ticker` :359+ and its `_llm_call` :383-391)
- Test: `tests/unit/shared/test_run_usage_totals.py` (create)

**Interfaces:**
- Produces: `AgentOutput.prompt_tokens/completion_tokens: int = 0`, `AgentOutput.cost_usd: float = 0.0` (all `exclude=True`); `sum_run_usage(agent_outputs: dict[str, AgentOutput], resolve_usage: tuple[int, int], aggregator: object) -> tuple[int, int, float]` in `base_orchestrator`.

- [ ] **Step 1: Write failing tests** (`tests/unit/shared/test_run_usage_totals.py`):

```python
"""AUD-087: run summaries report real summed usage, not hardcoded zeros."""
from types import SimpleNamespace

from backend.shared.pipeline.base_orchestrator import sum_run_usage
from backend.shared.schemas.pipeline import AgentOutput


def _out(agent, pt, ct, cost):
    o = AgentOutput(agent=agent, ticker="MARUTI", overall_score=0.5)
    o.prompt_tokens = pt
    o.completion_tokens = ct
    o.cost_usd = cost
    return o


def test_sums_agents_resolve_and_aggregator():
    outputs = {"a": _out("a", 100, 50, 0.001), "b": _out("b", 200, 70, 0.002)}
    agg = SimpleNamespace(_last_prompt_tokens=30, _last_completion_tokens=10)
    pt, ct, cost = sum_run_usage(outputs, (5, 2), agg)
    assert pt == 335 and ct == 132
    assert cost > 0.003  # agent costs + priced resolve/aggregator tokens


def test_defaults_are_zero_and_excluded_from_reports():
    o = AgentOutput(agent="a", ticker="T", overall_score=0.5)
    assert o.prompt_tokens == 0 and o.completion_tokens == 0 and o.cost_usd == 0.0
    dumped = o.model_dump()
    assert "prompt_tokens" not in dumped and "cost_usd" not in dumped


def test_aggregator_without_usage_attrs_is_safe():
    pt, ct, cost = sum_run_usage({}, (0, 0), object())
    assert (pt, ct, cost) == (0, 0, 0.0)
```

- [ ] **Step 2:** Run → FAIL (`sum_run_usage` not defined; AgentOutput has no fields).
- [ ] **Step 3: Implement.**

`schemas/pipeline.py`, after `error: str | None = None`:

```python
    # Telemetry (AUD-087): per-call usage, excluded from serialised reports.
    prompt_tokens: int = Field(default=0, exclude=True)
    completion_tokens: int = Field(default=0, exclude=True)
    cost_usd: float = Field(default=0.0, exclude=True)
```

`base_agent.py` — in BOTH `run` (after `cost = ...` :119) and `run_async` (:160), before `log_llm_call`:

```python
        output.prompt_tokens = pt
        output.completion_tokens = ct
        output.cost_usd = cost
```

`base_orchestrator.py` — module-level, above the class:

```python
def sum_run_usage(
    agent_outputs: dict[str, "AgentOutput"],
    resolve_usage: tuple[int, int],
    aggregator: object,
) -> tuple[int, int, float]:
    """Run totals for log_run_summary (AUD-087): agents + ticker-resolve + aggregator."""
    pt = sum(o.prompt_tokens for o in agent_outputs.values())
    ct = sum(o.completion_tokens for o in agent_outputs.values())
    cost = sum(o.cost_usd for o in agent_outputs.values())
    extra_pt = resolve_usage[0] + getattr(aggregator, "_last_prompt_tokens", 0)
    extra_ct = resolve_usage[1] + getattr(aggregator, "_last_completion_tokens", 0)
    cost += (extra_pt * settings.LLM_INPUT_COST_PER_M
             + extra_ct * settings.LLM_OUTPUT_COST_PER_M) / 1_000_000
    return pt + extra_pt, ct + extra_ct, round(cost, 6)
```

`_resolve_ticker`: first line of the method body → `self._last_resolve_usage = (0, 0)`; inside its `_llm_call` after `ct = response.usage.completion_tokens` → `self._last_resolve_usage = (pt, ct)`.

Both `log_run_summary` call sites — insert above the call:

```python
        total_pt, total_ct, total_cost = sum_run_usage(
            agent_outputs, getattr(self, "_last_resolve_usage", (0, 0)), self._aggregator
        )
```

and replace `total_prompt_tokens=0, total_completion_tokens=0, total_cost_usd=0.0,` with
`total_prompt_tokens=total_pt, total_completion_tokens=total_ct, total_cost_usd=total_cost,`.

`_run_unified` :481 — keep the analyst instance, pass run_id (it was silently dropped), stamp the single call's usage once:

```python
        analyst = UnifiedAnalyst()
        outputs = analyst.run(query, bundle, self.SECTOR_NAME, run_id=run_id)
        if outputs:
            # One LLM call produced all outputs — stamp totals on one output so
            # sum_run_usage() over the dict counts them exactly once.
            first = next(iter(outputs.values()))
            first.prompt_tokens = analyst._last_prompt_tokens
            first.completion_tokens = analyst._last_completion_tokens
            first.cost_usd = (
                analyst._last_prompt_tokens * settings.LLM_INPUT_COST_PER_M
                + analyst._last_completion_tokens * settings.LLM_OUTPUT_COST_PER_M
            ) / 1_000_000
```

- [ ] **Step 4:** `python -m pytest tests/unit/shared/test_run_usage_totals.py -q` → PASS.
- [ ] **Step 5:** Commit: `fix(telemetry): sum real usage into run summaries instead of hardcoded zeros (AUD-087)`

---

### Task 3: Telemetry + factory at RL/background sites — AUD-093 + 097

**Files:**
- Modify (9 call sites): `core/intelligence/rl/workflows/preopen_check.py`, `core/intelligence/rl/agents/control_lane.py`, `core/intelligence/rl/agents/thesis_reviewer.py`, `core/intelligence/rl/agents/question_researcher.py`, `core/intelligence/rl/agents/event_ingestor.py`, `core/intelligence/rl/agents/dossier_curator.py`, `core/intelligence/rl/algorithms/price_interpolator.py`, `core/intelligence/prompt_enhancer/enhancer.py`, `services/background/macro_news_fetcher.py`
- Test: `tests/unit/test_llm_telemetry_coverage.py` (create)

**Uniform instrumentation pattern** (nested try around the existing `create(...)` — works identically inside or outside retry loops; enclosing except clauses still see the original exception):

```python
        t0 = time.time()
        try:
            resp = <client>.chat.completions.create(<UNCHANGED ARGS>)
        except Exception:
            record_llm_call(<CALLER>, <MODEL>, 0, 0, int((time.time() - t0) * 1000), False)
            raise
        usage = getattr(resp, "usage", None)
        record_llm_call(<CALLER>, <MODEL>,
                        getattr(usage, "prompt_tokens", 0) or 0,
                        getattr(usage, "completion_tokens", 0) or 0,
                        int((time.time() - t0) * 1000), True)
```

Per-site substitutions (add `record_llm_call` to the site's existing `from services.clients.llm_client import ...`; add `import time` where missing):

| File | CALLER | MODEL expression |
|------|--------|------------------|
| preopen_check.py:66 | `"preopen_check"` | `model` (existing local) |
| control_lane.py:48 | `"control_lane"` | `model` (existing local) |
| thesis_reviewer.py:223 | `"thesis_reviewer"` | `settings.LLM_MODEL_REASONING` |
| question_researcher.py:136 | `"question_researcher"` | `settings.LLM_MODEL` |
| event_ingestor.py:176 | `"event_ingestor"` | `settings.LLM_MODEL` |
| dossier_curator.py:152 | `"dossier_curator"` | `settings.LLM_MODEL` |
| price_interpolator.py:383 | `"price_interpolator"` | `settings.LLM_MODEL` |
| enhancer.py:426 | `"prompt_enhancer"` | `settings.LLM_MODEL` |
| macro_news_fetcher.py:337 | `"macro_reviewer"` | `_s.LLM_MODEL` |

**Factory fixes (AUD-097, widened to 3 sites):**
- `price_interpolator.py:372-377`: replace `from openai import OpenAI, APIError, APITimeoutError, RateLimitError` + inline `OpenAI(...)` with `from openai import APIError, APITimeoutError, RateLimitError` + `from services.clients.llm_client import get_llm_client, record_llm_call` + `client = get_llm_client()`.
- `enhancer.py:420-425`: replace `from openai import OpenAI` + inline `OpenAI(...)` with `from services.clients.llm_client import get_llm_client, record_llm_call` + `client = get_llm_client()`.
- `thesis_reviewer.py:126-131` (`__init__`): replace inline `OpenAI(...)` with `from services.clients.llm_client import get_llm_client` + `self._client = get_llm_client()` (discovered during planning — same defect class).

- [ ] **Step 1: Write failing tests** (`tests/unit/test_llm_telemetry_coverage.py`):

```python
"""AUD-093/097: RL + background LLM call sites record telemetry via the factory client."""
from types import SimpleNamespace

import pytest

import services.clients.llm_client as llm_mod


class _Completions:
    def __init__(self, content='{"ok": true}'):
        self.kwargs = None
        self._content = content

    def create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self._content))],
            usage=SimpleNamespace(prompt_tokens=9, completion_tokens=4),
        )


@pytest.fixture
def fake_client(monkeypatch):
    client = SimpleNamespace(chat=SimpleNamespace(completions=_Completions()))
    monkeypatch.setattr(llm_mod, "get_llm_client", lambda: client)
    return client


@pytest.fixture
def recorded(monkeypatch):
    calls = []
    monkeypatch.setattr(llm_mod, "record_llm_call", lambda *a: calls.append(a))
    return calls


def _assert_recorded(recorded, caller):
    assert recorded, f"{caller}: record_llm_call never invoked"
    assert recorded[0][0] == caller
    assert recorded[0][2] == 9 and recorded[0][3] == 4 and recorded[0][5] is True


def test_preopen_check(fake_client, recorded):
    from core.intelligence.rl.workflows import preopen_check
    preopen_check._call_llm("sys", "user")
    _assert_recorded(recorded, "preopen_check")


def test_control_lane(fake_client, recorded):
    from core.intelligence.rl.agents import control_lane
    control_lane._call_llm("sys", "user")
    _assert_recorded(recorded, "control_lane")


def test_thesis_reviewer(fake_client, recorded):
    from core.intelligence.rl.agents.thesis_reviewer import ThesisReviewer
    ThesisReviewer._call_llm(SimpleNamespace(_client=fake_client), "user")
    _assert_recorded(recorded, "thesis_reviewer")


def test_question_researcher(fake_client, recorded):
    from core.intelligence.rl.agents.question_researcher import QuestionResearcher
    QuestionResearcher._call_llm(SimpleNamespace(), "sys", "user")
    _assert_recorded(recorded, "question_researcher")


def test_event_ingestor(fake_client, recorded):
    from core.intelligence.rl.agents.event_ingestor import EventIngestor
    EventIngestor._call_llm(SimpleNamespace(), "sys", "user")
    _assert_recorded(recorded, "event_ingestor")


def test_dossier_curator(fake_client, recorded):
    from core.intelligence.rl.agents.dossier_curator import DossierCurator
    DossierCurator._call_llm(SimpleNamespace(), "sys", "user")
    _assert_recorded(recorded, "dossier_curator")


def test_price_interpolator(fake_client, recorded):
    from core.intelligence.rl.algorithms.price_interpolator import PriceInterpolator
    PriceInterpolator._call_llm(SimpleNamespace(), "user")
    _assert_recorded(recorded, "price_interpolator")


def test_failure_is_recorded(fake_client, recorded, monkeypatch):
    def boom(**kwargs):
        raise ValueError("boom")
    monkeypatch.setattr(fake_client.chat.completions, "create", boom)
    from core.intelligence.rl.agents import control_lane
    with pytest.raises(ValueError):
        control_lane._call_llm("sys", "user")
    assert recorded and recorded[0][5] is False
```

(enhancer `_generate_queries_llm` and the macro reviewer are exercised indirectly — their instrumentation is identical; the class constructors there need heavier scaffolding than the value of the extra test. If `PriceInterpolator._call_llm` or others reference `self` beyond `_client`, adapt the `SimpleNamespace` at implementation time.)

- [ ] **Step 2:** Run → FAIL (no recording; price_interpolator ignores the patched factory).
- [ ] **Step 3:** Apply the pattern at all 9 sites + the 3 factory fixes.
- [ ] **Step 4:** `python -m pytest tests/unit/test_llm_telemetry_coverage.py -q` → PASS.
- [ ] **Step 5:** Commit: `fix(telemetry): record every RL/background LLM call; route stray clients through factory (AUD-093/097)`

---

### Task 4: Retire the LLM_MODEL catch-all — AUD-096

**Files:**
- Modify: `src/backend/shared/config/settings/base.py:34-35` (delete comment + alias)
- Modify (rename `settings.LLM_MODEL` → `settings.LLM_MODEL_BULK`, and `_s.LLM_MODEL` → `_s.LLM_MODEL_BULK`): `base_agent.py`, `base_orchestrator.py`, `graphs/nodes.py`, `macro_news_fetcher.py`, `question_researcher.py`, `event_ingestor.py`, `dossier_curator.py`, `price_interpolator.py`, `enhancer.py` (including the record_llm_call lines added in Task 3)
- Modify tests: `tests/contract/test_phase0_llm_migration.py:81-83`, `tests/unit/shared/test_config.py:67,79-81`, `tests/unit/test_config.py:67,79-81` — assert on `settings.LLM_MODEL_BULK`

- [ ] **Step 1:** Per file, verify no other `settings.LLM_MODEL_*` tier refs would be corrupted by prefix match (`grep -n "LLM_MODEL_" <file>` first), then `replace_all` the exact string `settings.LLM_MODEL` → `settings.LLM_MODEL_BULK` (files above have no REASONING/FAST refs on the same prefix except thesis_reviewer/signal_aggregator/unified_analyst, which are NOT in the rename set).
- [ ] **Step 2:** Delete from `base.py`:

```python
# Back-compat catch-all: any call-site still reading LLM_MODEL gets the BULK tier.
LLM_MODEL: str = os.getenv("LLM_MODEL", LLM_MODEL_BULK)
```

- [ ] **Step 3:** Guard: `grep -rn "LLM_MODEL_BULK_" core src services tests` → must be empty; `grep -rn "settings.LLM_MODEL\b\|_s.LLM_MODEL\b" core src services` → must be empty.
- [ ] **Step 4:** Update the 3 test files to `LLM_MODEL_BULK` (family assertion `qwen|deepseek` still holds — deepseek).
- [ ] **Step 5:** `python -m pytest tests/unit/shared/test_config.py tests/unit/test_config.py tests/contract/test_phase0_llm_migration.py -q` → no NEW failures vs baseline.
- [ ] **Step 6:** Commit: `refactor(config): retire LLM_MODEL catch-all alias — explicit BULK tier at all call sites (AUD-096)`

---

### Task 5: Full verification + ledger + ship

- [ ] **Step 1:** `python -m pytest tests -q` — compare to Task 0 baseline; zero NEW failures.
- [ ] **Step 2:** Update `docs/audit/LEDGER.md`: append a "Wave — LLM cost/telemetry SHIPPED" note under the Phase 5 section; mark AUD-092/093/094/096/097 → FIXED (commit hash), AUD-087 → FIXED, note 097 widened to include thesis_reviewer `__init__`; AUD-095/098 unchanged (user-decision).
- [ ] **Step 3:** Update audit-program memory + MEMORY.md index.
- [ ] **Step 4:** Commit ledger, push (auto-deploys to Railway).
