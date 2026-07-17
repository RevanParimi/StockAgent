# Audit Wave D — Cost / Resilience (AUD-105, AUD-101, AUD-088) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make LLM cost telemetry tier-correct (AUD-105), cap the chat retry×model fan-out with a per-turn wall-clock budget (AUD-101), and add a nightly zip+email backup of the Railway volume's `data/` ledgers (AUD-088).

**Architecture:** (1) A per-model rate table in `config.yaml` + a `settings.llm_cost_usd(model, pt, ct)` helper replaces the flat BULK rate at all 9 cost sites. (2) `_chat_completion` gets `deadline=` + retries-per-model 3→2; `chat()`/`chat_stream()` compute one deadline per user turn and always allow one final no-tools synthesis. (3) New `services/data/backup.py` zips ledgers (SQLite via the backup API), rotates 7 local copies under `data/backups/`, and emails the zip through the live SMTP transport; scheduler Job 15 runs it nightly 23:30 IST.

**Tech Stack:** Python, FastAPI, APScheduler, stdlib zipfile/sqlite3/email.mime, pytest.

## Global Constraints

- TDD: failing test before implementation, per repo convention.
- Work in a git worktree branch `audit-wave-d`; ff-merge to main when green.
- `data/` layout is the Railway volume — backup must EXCLUDE rebuildable caches (`market_cache`, `tavily_cache`, `nse`, `macro_news`, `eval`) and `backups/` itself.
- Delivery tests: the autouse `_no_real_deliveries` conftest fixture (AUD-106) forces transports off — email tests must monkeypatch the enable flags AND fake `smtplib.SMTP`; never send real mail.
- Live OpenRouter rates pulled 2026-07-17 (public /api/v1/models): glm-5.2 = 1.218/3.828, deepseek-v4-flash = 0.098/0.196, qwen3.6-flash = 0.1875/1.125 (USD per M tokens). glm-5.2 was repriced upstream from the 0.686/2.156 documented at the 2026-07-03 bench.
- Keep prod endpoint/auth/cash specifics out of committed docs (public repo).
- Suite baseline: ~1962P/5S/1F known (event_ingestor date test); worktree runs also skip/fail the gitignored-data harness test — both pre-existing.

---

### Task 1: AUD-105 — per-model rate table + `llm_cost_usd` helper

**Files:**
- Modify: `config.yaml` (llm block, after line 38)
- Modify: `src/backend/shared/config/settings/base.py:38-41`
- Test: `tests/unit/test_llm_cost.py` (new)

**Interfaces:**
- Produces: `settings.LLM_COST_RATES: dict[str, tuple[float, float]]` and `settings.llm_cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float` — used by Task 2 at all 9 cost sites.

- [ ] **Step 1: Write the failing test**

```python
"""AUD-105: per-model cost rates — REASONING calls must not be costed at the BULK rate."""
from backend.shared.config import settings


def test_known_model_uses_its_own_rate():
    # glm-5.2 live rate 1.218/3.828 per M (2026-07-17)
    cost = settings.llm_cost_usd("z-ai/glm-5.2", 1_000_000, 1_000_000)
    assert cost == (1.218 + 3.828)


def test_reasoning_call_no_longer_costed_at_bulk_rate():
    reasoning = settings.llm_cost_usd(settings.LLM_MODEL_REASONING, 7440, 2957)
    bulk_flat = (7440 * settings.LLM_INPUT_COST_PER_M
                 + 2957 * settings.LLM_OUTPUT_COST_PER_M) / 1_000_000
    assert reasoning > 5 * bulk_flat  # the AUD-105 ~10x undercount is gone


def test_unknown_model_falls_back_to_flat_rate():
    cost = settings.llm_cost_usd("some/unknown-model", 1000, 500)
    expected = (1000 * settings.LLM_INPUT_COST_PER_M
                + 500 * settings.LLM_OUTPUT_COST_PER_M) / 1_000_000
    assert cost == expected


def test_zero_tokens_zero_cost():
    assert settings.llm_cost_usd("z-ai/glm-5.2", 0, 0) == 0.0


def test_all_three_tier_models_have_rates():
    for m in (settings.LLM_MODEL_FAST, settings.LLM_MODEL_REASONING, settings.LLM_MODEL_BULK):
        assert m in settings.LLM_COST_RATES
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_llm_cost.py -v`
Expected: FAIL — `AttributeError: module ... has no attribute 'llm_cost_usd'`

- [ ] **Step 3: Implement — config.yaml rates + settings helper**

`config.yaml` — insert after the `output_cost_per_m: 0.18` line:

```yaml
  # Per-model cost rates (USD per million tokens) — AUD-105. Keyed on the exact
  # OpenRouter model id each call site logs; models not listed fall back to the
  # flat input/output_cost_per_m above. Live OpenRouter prices 2026-07-17
  # (NB glm-5.2 was repriced upstream from 0.686/2.156 at the 2026-07-03 bench).
  cost_rates:
    "z-ai/glm-5.2": [1.218, 3.828]
    "deepseek/deepseek-v4-flash": [0.098, 0.196]
    "qwen/qwen3.6-flash": [0.1875, 1.125]
```

`src/backend/shared/config/settings/base.py` — after the `LLM_OUTPUT_COST_PER_M` line:

```python
# Per-model cost rates (AUD-105) — flat rates above remain the unknown-model
# fallback. Values: (input_usd_per_m, output_usd_per_m).
_DEFAULT_COST_RATES = {
    "z-ai/glm-5.2": (1.218, 3.828),
    "deepseek/deepseek-v4-flash": (0.098, 0.196),
    "qwen/qwen3.6-flash": (0.1875, 1.125),
}
LLM_COST_RATES: dict[str, tuple[float, float]] = {
    str(k): (float(v[0]), float(v[1]))
    for k, v in (cfg("llm.cost_rates", fallback=_DEFAULT_COST_RATES) or {}).items()
    if isinstance(v, (list, tuple)) and len(v) == 2
}


def llm_cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Tier-correct USD cost of one LLM call (AUD-105)."""
    in_rate, out_rate = LLM_COST_RATES.get(
        model, (LLM_INPUT_COST_PER_M, LLM_OUTPUT_COST_PER_M))
    return (prompt_tokens * in_rate + completion_tokens * out_rate) / 1_000_000
```

Verify `settings/__init__.py` re-exports base symbols (it star-imports; `get_serper_key` is the precedent for functions).

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_llm_cost.py -v` — Expected: 5 PASS

- [ ] **Step 5: Commit**

```bash
git add config.yaml src/backend/shared/config/settings/base.py tests/unit/test_llm_cost.py
git commit -m "feat(cost): per-model LLM cost rate table + llm_cost_usd helper (AUD-105)"
```

### Task 2: AUD-105 — switch all 9 cost sites to `llm_cost_usd`

**Files:**
- Modify: `src/backend/shared/pipeline/base_agent.py:119,163`
- Modify: `src/backend/shared/pipeline/unified_analyst.py:356-359`
- Modify: `src/backend/shared/pipeline/signal_aggregator.py:161-164`
- Modify: `src/backend/shared/pipeline/base_orchestrator.py:82-86,412,515-518`
- Modify: `src/backend/shared/pipeline/graphs/nodes.py:83,401`
- Test: `tests/unit/test_llm_cost.py` (extend)

**Interfaces:**
- Consumes: `settings.llm_cost_usd` from Task 1.
- Produces: `sum_run_usage(agent_outputs, resolve_usage, aggregator)` keeps its exact signature/return `(pt, ct, cost)` — but now costs resolve tokens at BULK and aggregator tokens at REASONING.

- [ ] **Step 1: Write the failing test** (append to `tests/unit/test_llm_cost.py`)

```python
def test_sum_run_usage_splits_rates_by_model():
    """base_orchestrator.sum_run_usage: resolve tokens=BULK rate, aggregator=REASONING rate."""
    from backend.shared.pipeline.base_orchestrator import sum_run_usage

    class _Agg:
        _last_prompt_tokens = 1_000_000
        _last_completion_tokens = 0

    pt, ct, cost = sum_run_usage({}, (1_000_000, 0), _Agg())
    bulk_in = settings.LLM_COST_RATES[settings.LLM_MODEL_BULK][0]
    reason_in = settings.LLM_COST_RATES[settings.LLM_MODEL_REASONING][0]
    assert pt == 2_000_000 and ct == 0
    assert cost == round(bulk_in + reason_in, 6)  # 1M resolve @ bulk + 1M agg @ reasoning
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_llm_cost.py::test_sum_run_usage_splits_rates_by_model -v`
Expected: FAIL — cost computed on the flat rate for both halves.

- [ ] **Step 3: Implement the 9 site swaps**

`base_agent.py:119` and `:163` (identical lines):
```python
        cost = settings.llm_cost_usd(settings.LLM_MODEL_BULK, pt, ct)
```

`unified_analyst.py:356-359`:
```python
            cost = settings.llm_cost_usd(
                settings.LLM_MODEL_REASONING,
                self._last_prompt_tokens, self._last_completion_tokens,
            )
```

`signal_aggregator.py:161-164`:
```python
        cost = settings.llm_cost_usd(
            settings.LLM_MODEL_REASONING,
            self._last_prompt_tokens, self._last_completion_tokens,
        )
```

`base_orchestrator.py` `sum_run_usage` (lines 82-86):
```python
    resolve_pt, resolve_ct = resolve_usage
    agg_pt = getattr(aggregator, "_last_prompt_tokens", 0)
    agg_ct = getattr(aggregator, "_last_completion_tokens", 0)
    # AUD-105: resolve runs on BULK, the aggregator on REASONING — cost each at its rate.
    cost += settings.llm_cost_usd(settings.LLM_MODEL_BULK, resolve_pt, resolve_ct)
    cost += settings.llm_cost_usd(settings.LLM_MODEL_REASONING, agg_pt, agg_ct)
    return pt + resolve_pt + agg_pt, ct + resolve_ct + agg_ct, round(cost, 6)
```

`base_orchestrator.py:412` (ticker resolution, BULK):
```python
                cost = settings.llm_cost_usd(settings.LLM_MODEL_BULK, pt, ct)
```

`base_orchestrator.py:515-518` (`_run_unified` stamp, REASONING):
```python
            first.cost_usd = settings.llm_cost_usd(
                settings.LLM_MODEL_REASONING,
                analyst._last_prompt_tokens, analyst._last_completion_tokens,
            )
```

`graphs/nodes.py:83` and `:401` (both BULK):
```python
                cost = settings.llm_cost_usd(settings.LLM_MODEL_BULK, pt, ct)
```

Then confirm no flat-rate cost site remains:
`grep -rn "LLM_INPUT_COST_PER_M" src/ services/ core/ --include=*.py` — only `settings/base.py` (definition + fallback inside `llm_cost_usd`) may remain.

- [ ] **Step 4: Run tests — new test passes, no regression in touched modules**

Run: `python -m pytest tests/unit/test_llm_cost.py tests/unit -k "orchestrator or unified or aggregator or base_agent or usage or telemetry" -v`
Expected: PASS (fix any test that asserted flat-rate cost values — update expected numbers to `llm_cost_usd`).

- [ ] **Step 5: Commit**

```bash
git add src/backend/shared/pipeline tests/unit/test_llm_cost.py
git commit -m "fix(cost): all 9 cost sites use tier-correct per-model rates (AUD-105)"
```

### Task 3: AUD-101 — `_chat_completion` retry cap + deadline

**Files:**
- Modify: `services/api/routes/ui_data.py:2995,3007-3043`
- Test: `tests/unit/test_chat_turn_budget.py` (new)

**Interfaces:**
- Produces: `_chat_completion(client, *, models=None, caller="ui_chat", deadline: float | None = None, **kwargs)` — `deadline` is a `time.monotonic()` timestamp; module constants `_CHAT_RETRIES_PER_MODEL = 2`, `_CHAT_TURN_BUDGET_S = 45.0`. Task 4 consumes both.

- [ ] **Step 1: Write the failing test**

```python
"""AUD-101: chat fan-out — retry cap per model + wall-clock deadline."""
import asyncio
import time
import pytest

from services.api.routes import ui_data


class _Transient(Exception):
    status_code = 429


class _FakeCompletions:
    def __init__(self, fail_times=10**9, exc=_Transient("429")):
        self.calls = 0
        self.fail_times = fail_times
        self.exc = exc

    async def create(self, **kwargs):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise self.exc
        class _Msg:  # minimal response shape
            content = "ok"
            tool_calls = None
        class _Choice:
            message = _Msg()
        class _Resp:
            choices = [_Choice()]
            usage = None
        return _Resp()


class _FakeClient:
    def __init__(self, completions):
        self.chat = type("C", (), {"completions": completions})()


@pytest.fixture(autouse=True)
def _fast_sleep(monkeypatch):
    slept = []
    async def _sleep(s):
        slept.append(s)
    monkeypatch.setattr(ui_data.asyncio, "sleep", _sleep)
    return slept


def test_retries_capped_at_two_per_model():
    fake = _FakeCompletions()  # always 429
    with pytest.raises(Exception):
        asyncio.run(ui_data._chat_completion(_FakeClient(fake), messages=[]))
    # 2 attempts on FAST + 2 on the REASONING fallback = 4 upstream calls max (was 6)
    assert fake.calls == 2 * 2


def test_escalation_to_fallback_still_works():
    fake = _FakeCompletions(fail_times=2)  # primary model exhausted, fallback succeeds
    resp = asyncio.run(ui_data._chat_completion(_FakeClient(fake), messages=[]))
    assert resp.choices[0].message.content == "ok"
    assert fake.calls == 3


def test_deadline_skips_backoff_sleep(_fast_sleep):
    fake = _FakeCompletions()  # always 429
    deadline = time.monotonic() + 0.05  # tighter than the first 0.8s backoff
    with pytest.raises(Exception):
        asyncio.run(ui_data._chat_completion(_FakeClient(fake), messages=[], deadline=deadline))
    assert fake.calls == 1          # one attempt, then budget bails out
    assert _fast_sleep == []        # never slept toward a blown deadline


def test_non_transient_raises_immediately():
    class _Fatal(Exception):
        status_code = 400
    fake = _FakeCompletions(exc=_Fatal("bad request"))
    with pytest.raises(_Fatal):
        asyncio.run(ui_data._chat_completion(_FakeClient(fake), messages=[]))
    assert fake.calls == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_chat_turn_budget.py -v`
Expected: `test_retries_capped_at_two_per_model` FAILS (6 calls), `test_deadline_skips_backoff_sleep` FAILS (unexpected keyword `deadline`).

- [ ] **Step 3: Implement**

Replace line 2995 area:
```python
_CHAT_MAX_TOOL_ROUNDS = 4              # max tool rounds before forcing a final answer
_CHAT_RETRIES_PER_MODEL = 2            # AUD-101: was 3 — caps the retry x model product at 4
_CHAT_TURN_BUDGET_S = 45.0             # AUD-101: soft wall-clock budget per user turn
```

Replace `_chat_completion` (3007-3043) with:
```python
async def _chat_completion(client, *, models: tuple[str, ...] | list[str] | None = None,
                           caller: str = "ui_chat", deadline: float | None = None,
                           **kwargs):
    """
    chat.completions.create with resilience: retry the primary model on transient
    rate-limit/5xx errors (exponential backoff), then ESCALATE to the reasoning
    tier (deliberate: quality over cost while the fast tier is rate-limited).
    `models` overrides the model chain (used by the model-comparison harness).
    Raises the last exception only if every model+retry is exhausted.
    AUD-092: reasoning is disabled by default — chat output is user-visible text
    and <think> blocks are stripped downstream, so paying for them is waste.
    AUD-093: every attempt is recorded to telemetry.
    AUD-101: `deadline` (time.monotonic() stamp) is the per-turn wall-clock
    budget — chat is latency-bound, so once it's blown we fail fast with the
    last transient error (the caller shows an honest "retry shortly" message)
    instead of sleeping through more backoff.
    """
    from services.clients.llm_client import JSON_MODE_EXTRA_BODY, record_llm_call
    kwargs.setdefault("extra_body", JSON_MODE_EXTRA_BODY)
    last_exc: Exception | None = None
    for model in (models or (_CHAT_MODEL, _CHAT_FALLBACK_MODEL)):
        for attempt in range(_CHAT_RETRIES_PER_MODEL):
            t0 = time.monotonic()
            try:
                resp = await client.chat.completions.create(model=model, **kwargs)
            except Exception as exc:  # noqa: BLE001 — inspect then re-raise non-transient
                record_llm_call(caller, model, 0, 0, int((time.monotonic() - t0) * 1000), False)
                last_exc = exc
                if not _is_transient_llm_error(exc):
                    raise
                sleep_s = 0.8 * (2 ** attempt)  # 0.8s, 1.6s
                if deadline is not None and time.monotonic() + sleep_s >= deadline:
                    logger.warning("[chat] turn budget exhausted — giving up early")
                    raise last_exc
                await asyncio.sleep(sleep_s)
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

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_chat_turn_budget.py -v` — Expected: 4 PASS

- [ ] **Step 5: Commit**

```bash
git add services/api/routes/ui_data.py tests/unit/test_chat_turn_budget.py
git commit -m "fix(chat): cap retries at 2/model + honor wall-clock deadline in _chat_completion (AUD-101)"
```

### Task 4: AUD-101 — per-turn deadline in `chat()` and `chat_stream()`

**Files:**
- Modify: `services/api/routes/ui_data.py` `chat()` (~2900-2970) and `chat_stream generate()` (~3283-3335)
- Test: `tests/unit/test_chat_turn_budget.py` (extend)

**Interfaces:**
- Consumes: `_chat_completion(..., deadline=)`, `_CHAT_TURN_BUDGET_S`, `_CHAT_MAX_TOOL_ROUNDS` from Task 3.
- Produces: no signature changes — both routes behave the same, just budgeted.

- [ ] **Step 1: Write the failing test** (append)

```python
def test_stream_turn_stops_tool_rounds_after_deadline(monkeypatch):
    """A turn whose budget is spent stops tool rounds and still forces ONE final
    no-tools synthesis (deadline=None on the last call)."""
    calls = []

    async def _fake_completion(client, **kwargs):
        calls.append(kwargs.get("deadline", "absent"))
        class _Msg:
            content = "final answer"
            tool_calls = None
        class _Choice:
            message = _Msg()
        class _Resp:
            choices = [_Choice()]
        return _Resp()

    monkeypatch.setattr(ui_data, "_chat_completion", _fake_completion)
    monkeypatch.setattr(ui_data, "_CHAT_TURN_BUDGET_S", -1.0)  # budget already blown

    import asyncio as _a
    async def _run():
        resp = ui_data.chat_stream  # route function
        # call the endpoint the way FastAPI would
        sr = await ui_data.chat_stream(message="hello there", session_id="t1")
        chunks = []
        async for chunk in sr.body_iterator:
            chunks.append(chunk)
        return "".join(c if isinstance(c, str) else c.decode() for c in chunks)

    body = _a.run(_run())
    assert "final answer" in body
    # Exactly one LLM call happened (the forced synthesis), with no deadline gate.
    assert calls == [None]
```

NOTE: adjust the invocation to `chat_stream`'s real signature (it takes Query params — check at implementation time; if it's `(message: str, session_id: str | None)` keep as above, else construct via `TestClient`). If FastAPI wiring makes direct-call awkward, use `fastapi.testclient.TestClient(app)` against `/ui/chat/stream` with the same monkeypatches — the assertion stays: one `_chat_completion` call, `deadline is None`.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_chat_turn_budget.py::test_stream_turn_stops_tool_rounds_after_deadline -v`
Expected: FAIL — current code runs up to 4 tool rounds regardless and passes no `deadline` kwarg (`calls == ["absent"]`).

- [ ] **Step 3: Implement**

`chat_stream generate()` — restructure the round loop (current 3287-3332): drop the `for…else`, add the deadline:
```python
        final_text = ""
        try:
            client = get_async_llm_client()
            turn_deadline = time.monotonic() + _CHAT_TURN_BUDGET_S  # AUD-101

            for _round in range(_CHAT_MAX_TOOL_ROUNDS):
                if time.monotonic() >= turn_deadline:
                    logger.warning("[chat] turn budget spent after %d tool rounds — forcing final answer", _round)
                    break
                resp = await _chat_completion(
                    client,
                    messages=messages,
                    temperature=0.4,
                    max_tokens=700,
                    tools=_CHAT_TOOLS,
                    tool_choice="auto",
                    deadline=turn_deadline,
                )
                msg = resp.choices[0].message
                tcs = getattr(msg, "tool_calls", None) or []

                if not tcs:
                    final_text = _strip_think(msg.content or "")
                    break
                # …(existing tool-execution block unchanged)…

            if not final_text:
                # Budget/rounds exhausted with tool context pending → ONE final
                # no-tools synthesis, always allowed (deadline=None): the user
                # gets a grounded answer over a mock even when the turn ran long.
                resp = await _chat_completion(
                    client, messages=messages, temperature=0.4, max_tokens=700,
                )
                final_text = _strip_think(resp.choices[0].message.content or "")

            if not final_text:
                final_text = "I couldn't compose a grounded answer from the live data this time — try rephrasing."
            else:
                final_text = _sanitize_answer(final_text)
```

`chat()` (non-stream) — same shape: `turn_deadline = time.monotonic() + _CHAT_TURN_BUDGET_S` before the `for _ in range(4):` loop; add `if time.monotonic() >= turn_deadline: break` at the top of the loop and `deadline=turn_deadline` to the in-loop `_chat_completion` call; convert the loop so the final synthesis call after it runs whenever the loop didn't `return` (it already does — the loop `return`s on a no-tools reply, so only add the break + kwarg; the trailing synthesis call stays deadline-free).

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/unit/test_chat_turn_budget.py tests/unit -k "chat" -v`
Expected: all PASS (existing chat tests unaffected — same behavior under no upstream stress).

- [ ] **Step 5: Commit**

```bash
git add services/api/routes/ui_data.py tests/unit/test_chat_turn_budget.py
git commit -m "fix(chat): per-turn wall-clock budget on both chat routes; final synthesis always allowed (AUD-101)"
```

### Task 5: AUD-088 — email attachments support in `send_email`

**Files:**
- Modify: `core/delivery/channels.py:17-18,84-103`
- Test: `tests/unit/test_delivery_channels_attachments.py` (new)

**Interfaces:**
- Produces: `send_email(subject: str, body: str, attachments: list[Path] | None = None) -> bool` — backward compatible; Task 6 consumes.

- [ ] **Step 1: Write the failing test**

```python
"""AUD-088: send_email grows optional file attachments (zip backup rider)."""
from pathlib import Path

import core.delivery.channels as channels


class _FakeSMTP:
    sent = []

    def __init__(self, host, port, timeout=20):
        pass
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False
    def starttls(self):
        pass
    def login(self, u, p):
        pass
    def sendmail(self, frm, to, payload):
        _FakeSMTP.sent.append(payload)


def _enable_email(monkeypatch, tmp_path):
    monkeypatch.setattr(channels.settings, "DELIVERY_EMAIL_ENABLED", True)
    monkeypatch.setattr(channels.settings, "SMTP_HOST", "smtp.test")
    monkeypatch.setattr(channels.settings, "SMTP_USER", "u@test")
    monkeypatch.setattr(channels.settings, "SMTP_PASSWORD", "pw")
    monkeypatch.setattr(channels.settings, "DELIVERY_EMAIL_TO", "to@test")
    monkeypatch.setattr(channels.smtplib, "SMTP", _FakeSMTP)
    _FakeSMTP.sent = []


def test_email_with_attachment_is_multipart(monkeypatch, tmp_path):
    _enable_email(monkeypatch, tmp_path)
    f = tmp_path / "backup.zip"
    f.write_bytes(b"PK\x03\x04fakezip")
    assert channels.send_email("subj", "body text", attachments=[f]) is True
    payload = _FakeSMTP.sent[0]
    assert "multipart" in payload.lower()
    assert 'filename="backup.zip"' in payload
    assert "body text" in payload


def test_email_without_attachment_unchanged(monkeypatch, tmp_path):
    _enable_email(monkeypatch, tmp_path)
    assert channels.send_email("subj", "plain body") is True
    assert "multipart" not in _FakeSMTP.sent[0].lower()


def test_missing_attachment_file_fails_closed(monkeypatch, tmp_path):
    _enable_email(monkeypatch, tmp_path)
    assert channels.send_email("subj", "body", attachments=[tmp_path / "nope.zip"]) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_delivery_channels_attachments.py -v`
Expected: FAIL — `send_email() got an unexpected keyword argument 'attachments'`

- [ ] **Step 3: Implement**

Imports (top of channels.py, next to the MIMEText import):
```python
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from pathlib import Path
```

Replace `send_email`:
```python
def send_email(subject: str, body: str, attachments: list[Path] | None = None) -> bool:
    """SMTP STARTTLS send to DELIVERY_EMAIL_TO. False when disabled/unconfigured
    or on any failure — never raises. `attachments` (AUD-088): file paths to
    attach; the whole send fails closed if any is unreadable."""
    if not (settings.DELIVERY_EMAIL_ENABLED and settings.SMTP_HOST
            and settings.DELIVERY_EMAIL_TO):
        return False
    try:
        if attachments:
            msg = MIMEMultipart()
            msg.attach(MIMEText(body, "plain", "utf-8"))
            for path in attachments:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(Path(path).read_bytes())
                encoders.encode_base64(part)
                part.add_header("Content-Disposition",
                                f'attachment; filename="{Path(path).name}"')
                msg.attach(part)
        else:
            msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = settings.SMTP_USER or "stockagent@localhost"
        msg["To"] = settings.DELIVERY_EMAIL_TO
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20) as s:
            s.starttls()
            if settings.SMTP_USER:
                s.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            s.sendmail(msg["From"], [settings.DELIVERY_EMAIL_TO], msg.as_string())
        return True
    except Exception as exc:
        logger.warning("[delivery] email send failed (non-fatal): %s", exc)
        return False
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/unit/test_delivery_channels_attachments.py tests/unit -k "delivery" -v`
Expected: new 3 PASS, existing delivery tests unchanged.

- [ ] **Step 5: Commit**

```bash
git add core/delivery/channels.py tests/unit/test_delivery_channels_attachments.py
git commit -m "feat(delivery): send_email optional file attachments (AUD-088 rider)"
```

### Task 6: AUD-088 — backup module (zip + sqlite snapshot + rotate + email)

**Files:**
- Create: `services/data/backup.py`
- Test: `tests/unit/test_backup.py` (new)

**Interfaces:**
- Consumes: `core.delivery.channels.send_email(subject, body, attachments=)` from Task 5.
- Produces: `create_backup_archive(data_dir: Path = DATA_DIR, dest_dir: Path | None = None) -> Path`, `prune_backups(dest_dir: Path, keep: int = BACKUP_KEEP) -> int`, `run_backup_job(data_dir: Path = DATA_DIR) -> dict` (keys: `archive`, `bytes`, `emailed`, `pruned`). Task 7 consumes `run_backup_job`.

- [ ] **Step 1: Write the failing test**

```python
"""AUD-088: nightly data/ backup — zip ledgers, snapshot sqlite, rotate, email offsite."""
import sqlite3
import zipfile
from pathlib import Path

import pytest

from services.data import backup


@pytest.fixture()
def data_dir(tmp_path):
    d = tmp_path / "data"
    (d / "portfolio").mkdir(parents=True)
    (d / "portfolio" / "portfolio.json").write_text('{"ok": true}')
    (d / "portfolio" / "transactions.jsonl").write_text('{"t": 1}\n')
    (d / "predictions" / "SUZLON").mkdir(parents=True)
    (d / "predictions" / "SUZLON" / "feedback_log.jsonl").write_text("{}\n")
    (d / "market_cache").mkdir()                      # rebuildable — excluded
    (d / "market_cache" / "big.json").write_text("x" * 1000)
    (d / "managed_tickers.json").write_text("[]")
    conn = sqlite3.connect(d / "telemetry.db")        # live sqlite — snapshot API
    conn.execute("CREATE TABLE t (x)"); conn.execute("INSERT INTO t VALUES (1)")
    conn.commit(); conn.close()
    return d


def test_archive_includes_ledgers_excludes_caches(data_dir):
    path = backup.create_backup_archive(data_dir=data_dir)
    names = zipfile.ZipFile(path).namelist()
    assert "portfolio/portfolio.json" in names
    assert "portfolio/transactions.jsonl" in names
    assert "predictions/SUZLON/feedback_log.jsonl" in names
    assert "managed_tickers.json" in names
    assert "telemetry.db" in names
    assert not any(n.startswith("market_cache") for n in names)
    assert not any(n.startswith("backups") for n in names)


def test_sqlite_snapshot_is_valid_db(data_dir, tmp_path):
    path = backup.create_backup_archive(data_dir=data_dir)
    out = tmp_path / "restored.db"
    with zipfile.ZipFile(path) as z:
        out.write_bytes(z.read("telemetry.db"))
    rows = sqlite3.connect(out).execute("SELECT x FROM t").fetchall()
    assert rows == [(1,)]


def test_prune_keeps_newest(data_dir):
    dest = data_dir / "backups"
    dest.mkdir()
    for i in range(10):
        (dest / f"stockagent-backup-2026071{i}-0000.zip").write_bytes(b"x")
    removed = backup.prune_backups(dest, keep=7)
    assert removed == 3
    left = sorted(p.name for p in dest.glob("*.zip"))
    assert len(left) == 7 and left[0].startswith("stockagent-backup-20260713")


def test_run_backup_job_emails_archive(data_dir, monkeypatch):
    sent = {}
    def _fake_send(subject, body, attachments=None):
        sent["attachments"] = attachments
        return True
    monkeypatch.setattr("core.delivery.channels.send_email", _fake_send)
    summary = backup.run_backup_job(data_dir=data_dir)
    assert summary["emailed"] is True
    assert Path(summary["archive"]).exists()
    assert sent["attachments"] == [Path(summary["archive"])]


def test_run_backup_job_skips_email_when_oversize(data_dir, monkeypatch):
    monkeypatch.setattr(backup, "EMAIL_MAX_BYTES", 1)   # force oversize
    called = []
    monkeypatch.setattr("core.delivery.channels.send_email",
                        lambda *a, **k: called.append(1) or True)
    summary = backup.run_backup_job(data_dir=data_dir)
    assert summary["emailed"] is False and called == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_backup.py -v`
Expected: FAIL — `ModuleNotFoundError: services.data.backup`

- [ ] **Step 3: Implement `services/data/backup.py`**

```python
"""
Nightly data/ backup (AUD-088).

The Railway volume is the ONLY home of the trade ledgers (portfolio.json,
transactions.jsonl, value_history), the RL predictions tree and telemetry.db.
This module zips the non-rebuildable state, keeps a small local rotation under
data/backups/ (guards against app-level corruption / fat-fingered writes), and
emails the archive through the existing SMTP transport (the off-site copy that
guards against volume loss). Caches are excluded — they rebuild themselves.
"""
from __future__ import annotations

import logging
import sqlite3
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

DATA_DIR = Path("data")
BACKUP_SUBDIR = "backups"
BACKUP_KEEP = 7
EMAIL_MAX_BYTES = 20 * 1024 * 1024   # Gmail cap is 25MB; leave headroom for base64

# Rebuildable caches — never backed up. Everything else under data/ goes in.
EXCLUDE_DIRS = {BACKUP_SUBDIR, "market_cache", "tavily_cache", "nse", "macro_news", "eval"}
# Live SQLite files — copied via the sqlite3 backup API, not a raw file read.
SQLITE_NAMES = {"telemetry.db", "scores.db"}


def _snapshot_sqlite(src: Path, dst: Path) -> None:
    """Consistent point-in-time copy of a possibly-live SQLite db."""
    with sqlite3.connect(src) as conn, sqlite3.connect(dst) as out:
        conn.backup(out)


def create_backup_archive(data_dir: Path = DATA_DIR, dest_dir: Path | None = None) -> Path:
    """Zip the non-rebuildable state under `data_dir`. Returns the archive path."""
    data_dir = Path(data_dir)
    dest_dir = Path(dest_dir) if dest_dir else data_dir / BACKUP_SUBDIR
    dest_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    archive = dest_dir / f"stockagent-backup-{stamp}.zip"

    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
        for path in sorted(data_dir.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(data_dir)
            if rel.parts[0] in EXCLUDE_DIRS:
                continue
            if path.name in SQLITE_NAMES:
                with tempfile.TemporaryDirectory() as td:
                    snap = Path(td) / path.name
                    _snapshot_sqlite(path, snap)
                    z.write(snap, rel.as_posix())
            else:
                z.write(path, rel.as_posix())
    return archive


def prune_backups(dest_dir: Path, keep: int = BACKUP_KEEP) -> int:
    """Delete all but the newest `keep` archives (by name — names carry the stamp)."""
    archives = sorted(Path(dest_dir).glob("stockagent-backup-*.zip"))
    stale = archives[:-keep] if keep else archives
    for p in stale:
        try:
            p.unlink()
        except OSError as exc:
            logger.warning("[backup] could not prune %s: %s", p.name, exc)
    return len(stale)


def run_backup_job(data_dir: Path = DATA_DIR) -> dict:
    """Create the nightly archive, rotate local copies, email the off-site copy.
    Never raises for delivery problems — but archive-creation errors DO raise
    (the scheduler's job-error alerting must hear about a failed backup)."""
    from core.delivery.channels import send_email

    archive = create_backup_archive(data_dir=data_dir)
    size = archive.stat().st_size
    pruned = prune_backups(archive.parent)

    emailed = False
    if size <= EMAIL_MAX_BYTES:
        emailed = send_email(
            f"StockAgent nightly backup — {archive.name}",
            f"Nightly data/ backup attached ({size / 1024:.0f} KB). "
            "Ledgers + predictions + telemetry; caches excluded.",
            attachments=[archive],
        )
    else:
        logger.warning("[backup] archive %s is %.1f MB — over the email cap, "
                       "NOT sent off-site", archive.name, size / 1e6)
    if not emailed:
        logger.warning("[backup] no off-site copy landed for %s (email disabled, "
                       "oversize, or send failed) — local rotation only", archive.name)
    summary = {"archive": str(archive), "bytes": size, "emailed": emailed, "pruned": pruned}
    logger.info("[backup] %s", summary)
    return summary
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_backup.py -v` — Expected: 5 PASS
(If `run_backup_job` tests fail on the send_email import seam: the module imports it INSIDE the function from `core.delivery.channels`, so `monkeypatch.setattr("core.delivery.channels.send_email", ...)` is the right target.)

- [ ] **Step 5: Commit**

```bash
git add services/data/backup.py tests/unit/test_backup.py
git commit -m "feat(ops): nightly data/ backup — zip ledgers, sqlite snapshot, rotate 7, email offsite (AUD-088)"
```

### Task 7: AUD-088 — scheduler Job 15 (nightly 23:30 IST)

**Files:**
- Modify: `services/scheduler/python/scheduler.py` (`_build_scheduler` after Job 14 block ~line 400; new `_backup_job` method near `_ledger_cleanup_job`)
- Test: `tests/unit/test_backup.py` (extend) or the existing scheduler-jobs test file (check `grep -rl "rl_daily_review" tests/` and follow its pattern)

**Interfaces:**
- Consumes: `services.data.backup.run_backup_job()` from Task 6.
- Produces: APScheduler job id `data_backup_nightly`.

- [ ] **Step 1: Write the failing test** (follow the existing scheduler-build test pattern; shape below)

```python
def test_scheduler_registers_nightly_backup_job():
    from services.scheduler.python.scheduler import RLScheduler  # match actual class name
    sched = RLScheduler()._build_scheduler()
    try:
        ids = {j.id for j in sched.get_jobs()}
        assert "data_backup_nightly" in ids
    finally:
        sched.shutdown(wait=False)
```

(At implementation time: mirror however the existing tests construct the scheduler — there IS an existing test asserting job ids from prior waves; extend it instead of duplicating setup if cleaner.)

- [ ] **Step 2: Run test to verify it fails**

Expected: FAIL — `data_backup_nightly` not in ids.

- [ ] **Step 3: Implement**

In `_build_scheduler`, after the Job 13/14 delivery block (before `return scheduler`):
```python
        # ── Job 15: Nightly data backup (23:30 IST daily — AUD-088) ─────────
        scheduler.add_job(
            func=self._backup_job,
            trigger=CronTrigger(hour=23, minute=30, timezone="Asia/Kolkata"),
            id="data_backup_nightly",
            name="Nightly data backup (zip + email off-site)",
            misfire_grace_time=3600,
            coalesce=True,
            replace_existing=True,
        )
        logger.info("[Scheduler] Backup job: daily at 11:30 pm IST")
```

New method (near `_ledger_cleanup_job`):
```python
    def _backup_job(self) -> None:
        """Job 15 — nightly data/ backup (AUD-088). Archive-creation failures
        raise so the EVENT_JOB_ERROR listener pages a human; a missing off-site
        copy only warns (run_backup_job logs it)."""
        from services.data.backup import run_backup_job
        summary = run_backup_job()
        logger.info("[Scheduler] nightly backup done: emailed=%s bytes=%d",
                    summary["emailed"], summary["bytes"])
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/unit/test_backup.py tests/unit -k "scheduler" -v`
Expected: PASS, existing scheduler tests unchanged.

- [ ] **Step 5: Commit**

```bash
git add services/scheduler/python/scheduler.py tests/unit/test_backup.py
git commit -m "feat(scheduler): Job 15 nightly data backup at 23:30 IST (AUD-088)"
```

### Task 8: Full suite, LEDGER + docs, merge, deploy watch

**Files:**
- Modify: `docs/audit/LEDGER.md` (rows AUD-101/105/088 → FIXED; Wave D section; glm-5.2 repricing note on the Phase 5 slice-2 spend model)
- Modify: `CODEBASE.md` env/config table if it lists the flat cost rows (point at `llm.cost_rates`)

- [ ] **Step 1: Full suite on the worktree**

Run: `python -m pytest tests/ -q`
Expected: baseline (~1962P/5S) + new tests; only known fails (event_ingestor date test; worktree-only harness data test). Investigate anything else.

- [ ] **Step 2: LEDGER updates**

- AUD-105 → FIXED (rate table + helper; all 9 sites swapped; note glm-5.2 upstream repricing 0.686/2.156 → 1.218/3.828 per M observed 2026-07-17 — tier-correct scheduled spend estimate rises to ≈$3.3-3.6/mo, still far under cap).
- AUD-101 → FIXED (retries 3→2 per model = ≤4 upstream/logical call; per-turn 45s wall-clock budget on both chat routes; final no-tools synthesis always allowed; honest rate-limit message preserved).
- AUD-088 → FIXED (nightly Job 15: zip ledgers/predictions/telemetry, sqlite backup API, 7-copy local rotation, email off-site when ≤20MB; no off-site copy → WARNING).
- Wave D section: telemetry $ pull remains data-gated — run the LEDGER SQL against prod telemetry.db ~2026-07-21+ (needs a few trading days of the new caller rows); recompute from tokens × `llm.cost_rates`, and AUD-105 now makes stored cost_usd trustworthy going forward. AUD-098 stays bench-gated on the RL-semantics verdict (060/066/077).
- Keep cash/host specifics out (public repo).

- [ ] **Step 3: Commit docs, ff-merge `audit-wave-d` to main, push**

```bash
git add docs/audit/LEDGER.md CODEBASE.md docs/superpowers/plans/2026-07-17-audit-wave-d-cost-resilience.md
git commit -m "docs(audit): Wave D shipped — AUD-101/105/088 FIXED"
# from the main checkout:
git merge --ff-only audit-wave-d && git push
```

- [ ] **Step 4: Deploy watch**

Railway auto-deploys on push. Verify: deploy healthy; startup log shows `[Scheduler] Backup job: daily at 11:30 pm IST`; next morning check `data/backups/` has one zip and the backup email landed. Also still watching Wave C riders: today ~16:35 IST review logs must have NO "nsepython not installed" lines; next weekday 08:50 brief renders populated Overnight/FII-DII lines.

## Self-Review

- Spec coverage: AUD-105 (Tasks 1-2, all 9 sites enumerated), AUD-101 (Tasks 3-4, both routes), AUD-088 (Tasks 5-7, create/rotate/off-site/schedule), ledger/docs/deploy (Task 8). Telemetry pull explicitly deferred (data-gated), AUD-098 explicitly skipped (gated) — both recorded in Task 8.
- Placeholders: none — every code step carries the code. Two implementation-time checks are flagged inline (FastAPI invocation shape in Task 4's test; scheduler test pattern in Task 7) with the assertion pinned either way.
- Type consistency: `llm_cost_usd(model, prompt_tokens, completion_tokens)` used identically in Tasks 1-2; `deadline: float | None` monotonic stamp in Tasks 3-4; `send_email(subject, body, attachments)` in Tasks 5-6; `run_backup_job(data_dir) -> dict` keys match between Tasks 6-7.
