# Wave B — API Security Lockdown Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the Phase 8 security findings — AUD-099 (unauth prompt routes + unsafe `.py` string encoding), AUD-102 (unauth `/ui/*` writes + empty-sym clobber), AUD-012 (push-subscribe hardening), AUD-103 (`str(exc)` leaks), CORS credentials cleanup — without breaking the deployed PWA.

**Architecture:** One shared optional-key auth helper (`services/api/auth.py`) replaces the four copy-pasted `_check_auth` functions and extends the same gate to the prompts router and all `ui_data` mutation routes. The gate stays OPTIONAL (enforced only when the `SCHEDULER_KEY` env var is set — same semantics as today's portfolio/delivery/discovery/scheduler routers), so shipping this wave changes nothing in prod until the user flips the env var. A frontend fetch wrapper teaches the prototype PWA to send `X-Scheduler-Key` from localStorage so flipping the key does not brick the UI. The prompt-file writer's escaping bug is fixed independently of auth (defense in depth).

**Tech Stack:** FastAPI + Header dependency, pytest + TestClient (mini-app pattern from `tests/unit/test_delivery_api.py`), vanilla JS fetch wrapper in `index.html`.

## Global Constraints

- The auth gate must be a no-op when `SCHEDULER_KEY` is unset (prod today) — zero behavior change until the user sets the key in Railway. **Do NOT set SCHEDULER_KEY anywhere in this wave.**
- Chat endpoints (`/ui/chat`, `/ui/chat/stream`) stay ungated — product surface, separate user decision.
- `GET /delivery/push/public-key` and `POST /delivery/push/subscribe` stay keyless by design (pre-login 🔔 flow; AUD-085 depends on it).
- Suite baseline: 10 failed / 10 errors / 2150 passed / 12 skipped (pre-existing AUD-022 stale mocks + 1 event_ingestor date test). No new failures allowed.
- Error responses must never contain `str(exc)` of internal exceptions — follow the `/analyse` pattern (log with `exc_info`, return generic text).
- Commit messages end with the Co-Authored-By line per house rules. Branch: `audit-wave-b-security` off `main`.

---

### Task 0: Setup — commit audit record, create branch

**Files:**
- Modify: none (git only)

- [ ] **Step 1: Commit the uncommitted LEDGER.md audit record on main**

```bash
git add docs/audit/LEDGER.md
git commit -m "docs(audit): Phase 8 API/UI census (AUD-099..104), Phase 9 wave ranking, Ph5 slice 2 spend model (AUD-105)"
```

- [ ] **Step 2: Create the wave branch**

```bash
git checkout -b audit-wave-b-security
```

---

### Task 1: Shared auth helper

**Files:**
- Create: `services/api/auth.py`
- Modify: `services/api/routes/portfolio_api.py:45-51`, `services/api/routes/delivery_api.py:29-35`, `services/api/routes/discovery_api.py:24-27`, `services/api/routes/scheduler_api.py` (its `_check_auth`)
- Test: `tests/unit/test_api_auth_lockdown.py`

**Interfaces:**
- Produces: `check_scheduler_key(key: str | None, context: str = "api") -> None` — raises `HTTPException(403)` when `SCHEDULER_KEY` env is set and `key` mismatches; logs one warning when unset. Later tasks import exactly this.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_api_auth_lockdown.py
"""Wave B (AUD-099/102/012): optional X-Scheduler-Key gate across routers."""
from fastapi import HTTPException
import pytest


def test_check_scheduler_key_open_when_env_unset(monkeypatch):
    monkeypatch.delenv("SCHEDULER_KEY", raising=False)
    from services.api.auth import check_scheduler_key
    check_scheduler_key(None)          # must not raise
    check_scheduler_key("whatever")    # must not raise


def test_check_scheduler_key_enforced_when_env_set(monkeypatch):
    monkeypatch.setenv("SCHEDULER_KEY", "sekret")
    from services.api.auth import check_scheduler_key
    with pytest.raises(HTTPException) as exc:
        check_scheduler_key(None)
    assert exc.value.status_code == 403
    with pytest.raises(HTTPException):
        check_scheduler_key("wrong")
    check_scheduler_key("sekret")      # correct key passes
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/unit/test_api_auth_lockdown.py -v`
Expected: FAIL — `ModuleNotFoundError: services.api.auth`

- [ ] **Step 3: Implement `services/api/auth.py`**

```python
"""
services/api/auth.py
====================
Shared optional X-Scheduler-Key gate (Wave B, AUD-099/102).

Semantics (unchanged from the per-router copies this replaces):
enforced only when the SCHEDULER_KEY env var is set; otherwise open,
with a warning so the posture is visible in logs. Lockdown = set the
env var in Railway — no code change needed.
"""
from __future__ import annotations

import logging
import os

from fastapi import HTTPException

logger = logging.getLogger(__name__)


def check_scheduler_key(key: str | None, context: str = "api") -> None:
    """Raise 403 when SCHEDULER_KEY is set and `key` does not match."""
    required = os.getenv("SCHEDULER_KEY", "")
    if required and key != required:
        raise HTTPException(status_code=403,
                            detail="Invalid or missing X-Scheduler-Key header.")
    if not required:
        logger.warning("[%s] SCHEDULER_KEY not set — endpoint is open.", context)
```

- [ ] **Step 4: Refactor the four existing `_check_auth` copies to delegate**

In each of `portfolio_api.py`, `delivery_api.py`, `discovery_api.py`, `scheduler_api.py`, replace the `_check_auth` body with:

```python
def _check_auth(key: str | None) -> None:
    from services.api.auth import check_scheduler_key
    check_scheduler_key(key, context="portfolio_api")  # module's own name in each file
```

(Keep the local `_check_auth` name so no call sites change. Delete the now-unused `import os` only if nothing else in the module uses it — check before removing.)

- [ ] **Step 5: Run new tests + the four routers' existing suites**

Run: `python -m pytest tests/unit/test_api_auth_lockdown.py tests/unit/test_delivery_api.py tests/unit/test_discovery_api.py tests/unit/test_portfolio_api.py -q`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add services/api/auth.py services/api/routes/portfolio_api.py services/api/routes/delivery_api.py services/api/routes/discovery_api.py services/api/routes/scheduler_api.py tests/unit/test_api_auth_lockdown.py
git commit -m "refactor(api): shared optional X-Scheduler-Key gate (Wave B groundwork)"
```

---

### Task 2: AUD-099a — gate all six prompts routes

**Files:**
- Modify: `services/api/routes/prompts.py` (routes at :445, :462, :467, :490, :512, :562)
- Test: `tests/unit/test_api_auth_lockdown.py` (extend)

**Interfaces:**
- Consumes: `check_scheduler_key` from Task 1.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/unit/test_api_auth_lockdown.py
def _prompts_client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from services.api.routes.prompts import router
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_prompts_routes_locked_when_key_set(monkeypatch):
    monkeypatch.setenv("SCHEDULER_KEY", "sekret")
    c = _prompts_client()
    assert c.get("/ui/prompts/catalogue").status_code == 403
    assert c.put("/ui/prompts/automobile/fundamentals",
                 json={"system_prompt": "x", "analysis_prompt": "y",
                       "context_search_queries": []}).status_code == 403
    assert c.post("/ui/prompts/deploy").status_code == 403
    # correct key passes the gate (200 for catalogue — no filesystem dependency)
    ok = c.get("/ui/prompts/catalogue", headers={"X-Scheduler-Key": "sekret"})
    assert ok.status_code == 200


def test_prompts_routes_open_when_key_unset(monkeypatch):
    monkeypatch.delenv("SCHEDULER_KEY", raising=False)
    c = _prompts_client()
    assert c.get("/ui/prompts/catalogue").status_code == 200
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/unit/test_api_auth_lockdown.py -v -k prompts`
Expected: FAIL — routes return 200 without key (no gate yet)

- [ ] **Step 3: Add the gate to all six routes**

In `prompts.py`: add imports `from fastapi import Header` (extend the existing fastapi import line) and `from services.api.auth import check_scheduler_key`. Then each route gains the header param + gate as its first statement. Pattern (repeat for `get_catalogue`, `get_pending`, `get_deploy_status`, `get_prompt`, `put_prompt`, `deploy_prompts`):

```python
@router.get("/catalogue", summary="List all sectors and their agent names")
async def get_catalogue(x_scheduler_key: str | None = Header(default=None)) -> dict:
    check_scheduler_key(x_scheduler_key, context="prompts")
    ...
```

For routes with existing params, the header param goes last, e.g.:

```python
async def put_prompt(sector: str, agent: str, body: PromptBody,
                     x_scheduler_key: str | None = Header(default=None)) -> dict:
    check_scheduler_key(x_scheduler_key, context="prompts")
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/unit/test_api_auth_lockdown.py -q && python -m pytest tests -q -k prompt`
Expected: PASS (plus no regressions in existing prompt tests)

- [ ] **Step 5: Commit**

```bash
git add services/api/routes/prompts.py tests/unit/test_api_auth_lockdown.py
git commit -m "fix(security): auth-gate all /ui/prompts routes (AUD-099a)"
```

---

### Task 3: AUD-099b — safe Python string encoding in the prompt writer

**Files:**
- Modify: `services/api/routes/prompts.py:169-172` (`_safe_triple_quote`)
- Test: `tests/unit/test_prompt_file_encoding.py`

**Interfaces:**
- Produces: `_py_string_literal(s: str) -> str` (replaces `_safe_triple_quote`; `_write_prompt_file` calls it).

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_prompt_file_encoding.py
"""AUD-099b: prompt-file writer must emit UNBREAKABLE string literals.

The old _safe_triple_quote escaped only embedded triple-quotes; a payload
ending in a single backslash escaped the closing delimiter and broke out
of the string in a file that gets importlib-imported (code injection).
"""
import ast

import pytest

PAYLOADS = [
    'ends with a backslash \\',
    'embedded """ triple quotes',
    'both \\""" and a trailing backslash \\',
    '"""\nimport os\nos.system("pwned")\nX = """',
    'plain multi\nline\nprompt with unicode ₹ and "quotes"',
]


@pytest.mark.parametrize("payload", PAYLOADS)
def test_written_file_is_safe_and_round_trips(tmp_path, payload):
    from services.api.routes.prompts import _write_prompt_file
    f = tmp_path / "prompt_mod.py"
    _write_prompt_file(f, '"""doc"""', payload, "analysis", ["q1"])
    src = f.read_text(encoding="utf-8")

    tree = ast.parse(src)  # must be valid Python
    # SAFETY: only a docstring + the three expected assignments — nothing injected
    for node in tree.body:
        assert isinstance(node, (ast.Expr, ast.Assign)), f"injected node: {ast.dump(node)[:80]}"
    names = [t.id for n in tree.body if isinstance(n, ast.Assign) for t in n.targets]
    assert names == ["SYSTEM_PROMPT", "ANALYSIS_PROMPT", "CONTEXT_SEARCH_QUERIES"]

    ns: dict = {}
    exec(compile(src, "<prompt>", "exec"), ns)   # noqa: S102 — test-only
    assert ns["SYSTEM_PROMPT"] == payload         # exact round-trip
    assert ns["ANALYSIS_PROMPT"] == "analysis"
    assert ns["CONTEXT_SEARCH_QUERIES"] == ["q1"]
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/unit/test_prompt_file_encoding.py -v`
Expected: FAIL — trailing-backslash payloads produce a SyntaxError or wrong round-trip

- [ ] **Step 3: Replace the encoder**

In `prompts.py`, replace `_safe_triple_quote` (lines 169-172) with:

```python
def _py_string_literal(s: str) -> str:
    """Encode s as a SAFE multi-line Python string literal (AUD-099b).

    Escape backslashes FIRST, then double quotes — so no payload can
    terminate the triple-quoted literal (the old version escaped only
    literal triple-quotes; a trailing single backslash broke out).
    """
    escaped = s.replace("\\", "\\\\").replace('"', '\\"')
    return f'"""{escaped}"""'
```

Update the two call sites in `_write_prompt_file` (lines 187, 189) from `_safe_triple_quote(...)` to `_py_string_literal(...)`. Grep first to confirm no other references:

```bash
grep -rn "_safe_triple_quote" services/ tests/ src/ --include="*.py"
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/unit/test_prompt_file_encoding.py -q && python -m pytest tests -q -k prompt`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add services/api/routes/prompts.py tests/unit/test_prompt_file_encoding.py
git commit -m "fix(security): unbreakable string encoding in prompt-file writer (AUD-099b)"
```

---

### Task 4: AUD-102 — gate ui_data mutations + reject empty syms

**Files:**
- Modify: `services/api/routes/ui_data.py` (9 mutating routes: `update_agent_weights`:655, `update_agent_tasks`:1009, `update_watchlist`:1044, `update_category_tickers`:1092, `replace_managed_tickers`:3395, `add_managed_ticker`:3447, `trigger_envelope_generation`:3542, `remove_managed_ticker`:3554, `toggle_managed_ticker`:3581)
- Test: `tests/unit/test_api_auth_lockdown.py` (extend)

**Interfaces:**
- Consumes: `check_scheduler_key` from Task 1.

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/unit/test_api_auth_lockdown.py
def _ui_client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from services.api.routes.ui_data import router
    app = FastAPI()
    app.include_router(router)
    return TestClient(app, raise_server_exceptions=False)


def test_ui_mutations_locked_when_key_set(monkeypatch):
    monkeypatch.setenv("SCHEDULER_KEY", "sekret")
    c = _ui_client()
    assert c.put("/ui/watchlist", json={"watchlist": ["MARUTI"]}).status_code == 403
    assert c.put("/ui/agents/tasks", json={"flags": {}}).status_code == 403
    assert c.put("/ui/tickers/managed", json=[]).status_code == 403
    assert c.delete("/ui/tickers/managed/MARUTI").status_code == 403
    assert c.patch("/ui/tickers/managed/MARUTI/toggle").status_code == 403
    assert c.post("/ui/tickers/managed/MARUTI/generate-envelope").status_code == 403


def test_ui_reads_stay_open_when_key_set(monkeypatch):
    monkeypatch.setenv("SCHEDULER_KEY", "sekret")
    c = _ui_client()
    # GET endpoints stay ungated — read-only, the PWA needs them pre-key
    assert c.get("/ui/tickers/managed").status_code == 200


def test_replace_managed_tickers_rejects_empty_sym(monkeypatch):
    monkeypatch.delenv("SCHEDULER_KEY", raising=False)
    c = _ui_client()
    resp = c.put("/ui/tickers/managed",
                 json=[{"sym": "  ", "sector": "automobile"}])
    assert resp.status_code == 422
    assert "sym" in resp.text
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/unit/test_api_auth_lockdown.py -v -k ui`
Expected: FAIL — mutations return non-403 without key; empty sym accepted

- [ ] **Step 3: Add gate + validation**

In `ui_data.py`: extend the fastapi import with `Header` and add `from services.api.auth import check_scheduler_key` near the other service imports. Each of the 9 mutating routes gains the header param (last position) + gate as first statement — same pattern as Task 2:

```python
async def update_watchlist(body: _WatchlistBody,
                           x_scheduler_key: str | None = Header(default=None)) -> dict:
    check_scheduler_key(x_scheduler_key, context="ui_data")
```

In `replace_managed_tickers` (after the gate, before the sector loop), reject blank syms and normalize:

```python
    tickers = [t.model_dump() for t in body]
    for t in tickers:
        t["sym"] = (t.get("sym") or "").strip().upper()
        if not t["sym"]:
            raise HTTPException(status_code=422,
                                detail="Each ticker needs a non-empty 'sym'.")
        if t["sector"] not in valid_sectors:
            ...  # existing check unchanged
```

(`HTTPException` is already imported locally inside the function at :3400 — hoist a module-level `from fastapi import HTTPException` if not already present at top; ui_data.py:34-39 region has the fastapi imports.)

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/unit/test_api_auth_lockdown.py -q && python -m pytest tests -q -k "ui_data or managed or watchlist"`
Expected: PASS, no regressions

- [ ] **Step 5: Commit**

```bash
git add services/api/routes/ui_data.py tests/unit/test_api_auth_lockdown.py
git commit -m "fix(security): auth-gate /ui/* mutations; reject empty sym in managed-list replace (AUD-102)"
```

---

### Task 5: AUD-012 — push-subscribe hardening

**Files:**
- Modify: `services/api/routes/delivery_api.py:114-122` (`push_subscribe`)
- Test: `tests/unit/test_delivery_api.py` (extend)

**Design note (resolves the seeded row):** POST stays keyless BY DESIGN — the pre-login 🔔 flow needs it and it only stores the caller's own subscription (AUD-085's user action depends on this working). The hardening is: (a) `endpoint` must be an `https://` URL, (b) per-user cap of 50 subscriptions so an anonymous caller can't grow the store unboundedly. DELETE stays keyless: removing requires knowing the exact push endpoint URL, which is an unguessable capability URL.

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/unit/test_delivery_api.py
def test_push_subscribe_rejects_non_https_endpoint(monkeypatch, tmp_path):
    monkeypatch.setattr(dapi.settings, "DELIVERY_DATA_DIR", str(tmp_path), raising=False)
    c = _client()
    assert c.post("/delivery/push/subscribe",
                  json={"endpoint": "http://evil.example/x"}).status_code == 422
    assert c.post("/delivery/push/subscribe",
                  json={"endpoint": 123}).status_code == 422


def test_push_subscribe_caps_store_size(monkeypatch, tmp_path):
    monkeypatch.setattr(dapi.settings, "DELIVERY_DATA_DIR", str(tmp_path), raising=False)
    from core.delivery.channels import PushStore
    store = PushStore(path=str(tmp_path / "push_subscriptions.json"))
    for i in range(50):
        store.add({"endpoint": f"https://push.example/{i}"})
    with patch.object(dapi, "PushStore", lambda: store):
        c = _client()
        resp = c.post("/delivery/push/subscribe",
                      json={"endpoint": "https://push.example/one-too-many"})
    assert resp.status_code == 429
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/unit/test_delivery_api.py -v -k push_subscribe`
Expected: FAIL — non-https accepted (200), cap absent

- [ ] **Step 3: Harden the route**

Replace `push_subscribe` in `delivery_api.py`:

```python
_MAX_PUSH_SUBS_PER_USER = 50   # AUD-012: bound anonymous store growth


# Browser push clients don't hold the scheduler key; these endpoints only
# store/remove the caller's own subscription (keyless BY DESIGN — the
# pre-login 🔔 flow and AUD-085 recovery depend on it). AUD-012 hardening:
# https-only endpoints + per-user cap.
@router.post("/push/subscribe", summary="Store a web-push subscription")
async def push_subscribe(
    subscription: dict,
    user_id: str | None = Query(default=None),
) -> dict:
    endpoint = subscription.get("endpoint")
    if not (isinstance(endpoint, str) and endpoint.startswith("https://")):
        raise HTTPException(status_code=422,
                            detail="subscription.endpoint must be an https:// URL")
    store = PushStore()
    if len(store.list(user_id=user_id)) >= _MAX_PUSH_SUBS_PER_USER:
        raise HTTPException(status_code=429,
                            detail="Subscription limit reached for this user.")
    count = store.add(subscription, user_id=user_id)
    return {"status": "subscribed", "subscriptions": count}
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/unit/test_delivery_api.py -q`
Expected: PASS (existing `_SUB` fixture uses `https://push.example/abc` — unaffected)

- [ ] **Step 5: Commit**

```bash
git add services/api/routes/delivery_api.py tests/unit/test_delivery_api.py
git commit -m "fix(security): https-only + per-user cap on push subscribe (AUD-012)"
```

---

### Task 6: AUD-103 — sanitize the `str(exc)` leak sites

**Files:**
- Modify: `services/api/routes/stream.py:67-69`, `services/api/routes/ui_data.py:2666-2668`, `services/api/routes/prompts.py:501-502,534-535,553-559`
- Test: `tests/test_api_routes.py` (extend — same leak-test style as the existing `/analyse` test)

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_api_routes.py
def test_ws_stream_error_event_does_not_leak_exception_detail():
    """AUD-103: /ws/stream error events must not carry raw str(exc)."""
    from unittest.mock import patch, AsyncMock, MagicMock
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from services.api.routes.stream import router as stream_router
    import json as _json

    app = FastAPI()
    app.include_router(stream_router)
    client = TestClient(app)

    internal = "/internal/path/secret_module.py line 99 KeyError('OPENROUTER_API_KEY')"
    mock_orch = MagicMock()
    mock_orch.analyse_async = AsyncMock(side_effect=RuntimeError(internal))

    with patch("services.api.routes.stream.detect_sector", return_value="automobile"), \
         patch("services.api.routes.stream.get_orchestrator", return_value=lambda: mock_orch):
        with client.websocket_connect("/ws/stream?ticker=MARUTI") as ws:
            event = _json.loads(ws.receive_text())

    assert event["event"] == "error"
    assert "/internal/path" not in event["detail"]
    assert "OPENROUTER" not in event["detail"]
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_api_routes.py -v -k ws_stream`
Expected: FAIL — detail contains the internal path

- [ ] **Step 3: Sanitize all sites (the `/analyse` pattern: log server-side, generic client text)**

`stream.py:67-69` — in `run_pipeline`'s except:

```python
        except Exception as exc:
            logger.error("[WS /ws/stream] pipeline failed for %s: %s",
                         ticker, exc, exc_info=True)
            err_event = json.dumps({
                "event": "error",
                "detail": "Analysis pipeline failed. Please try again later.",
            })
            await queue.put(err_event)
```

`ui_data.py:2666-2668` — `_chat_tool_portfolio_brief`'s except (keep the existing except structure, change only the return + add the log):

```python
        logger.warning("[chat] portfolio brief failed: %s", exc, exc_info=True)
        return "Brief unavailable right now — try again in a moment."
```

`prompts.py:501-502` (`get_prompt`, RuntimeError → 500):

```python
    except RuntimeError as exc:
        logger.error("[prompts] load failed for %s/%s: %s", sector, agent, exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Prompt module failed to load — see server logs.")
```

`prompts.py:534-535` (`put_prompt` write failure):

```python
    except Exception as exc:
        logger.error("[prompts] write failed for %s/%s: %s", sector, agent, exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to write prompt file — see server logs.")
```

`prompts.py:553-559` (`put_prompt` response) — stop leaking the server filesystem path; return the repo-relative deploy path instead:

```python
    return {
        "status":  "saved",
        "sector":  sector,
        "agent":   agent,
        "path":    _github_path_for(sector, agent),
        "pending": _load_pending(),
    }
```

(The two 404 `str(exc)` sites at prompts.py:500/:522 KEEP — that text is our own crafted `FileNotFoundError` message from `_locate_prompt_file`, not raw internals.)

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_api_routes.py tests/unit/test_api_auth_lockdown.py -q && python -m pytest tests -q -k prompt`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add services/api/routes/stream.py services/api/routes/ui_data.py services/api/routes/prompts.py tests/test_api_routes.py
git commit -m "fix(security): sanitize str(exc) leaks on ws/chat-brief/prompts paths (AUD-103, absorbs AUD-014)"
```

---

### Task 7: CORS cleanup

**Files:**
- Modify: `services/api/server.py:394-400`
- Test: none (config one-liner; verified by suite + manual preflight check in Task 9)

- [ ] **Step 1: Flip the contradictory flag**

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # Frontend is same-origin; broad allow for API clients
    allow_credentials=False,   # AUD Phase 8: '*'+credentials is a rejected combo; no route uses cookies
    allow_methods=["*"],
    allow_headers=["*"],
)
```

- [ ] **Step 2: Run the API test files to confirm nothing depended on credentials**

Run: `python -m pytest tests/test_api_routes.py tests/unit/test_delivery_api.py tests/unit/test_portfolio_api.py -q`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add services/api/server.py
git commit -m "fix(api): drop allow_credentials from wildcard CORS (Phase 8 note)"
```

---

### Task 8: Frontend — send X-Scheduler-Key so lockdown doesn't brick the PWA

**Files:**
- Modify: `src/frontend/prototypes/index.html` (insert new script after the marked-config block ending at line 90)
- Modify: `src/frontend/prototypes/sw.js` (bump cache version if a versioned cache name exists — check `grep -n "CACHE" src/frontend/prototypes/sw.js`)

**Design:** global fetch wrapper — the prototype has ~40 raw `fetch()` call sites across 14 JSX files; wrapping once in `index.html` (loaded before all JSX) beats editing every site. Key lives in `localStorage.sa_key` (same `sa_` prefix the app already uses). On the first 403 the wrapper prompts once for the key, stores it, and retries.

- [ ] **Step 1: Insert the wrapper script**

After the `</script>` at line 90 of `index.html` (the marked-config block), insert:

```html
<script>
  /* Wave B (AUD-099/102): attach X-Scheduler-Key to same-origin API calls.
     The key is optional — when the server has no SCHEDULER_KEY set, requests
     work without it. Set it once via the prompt that appears on a 403, or
     manually: saSetKey('your-key'). */
  (function () {
    const realFetch = window.fetch.bind(window);
    window.saSetKey = function (k) {
      if (k) localStorage.setItem('sa_key', k);
      else localStorage.removeItem('sa_key');
    };
    window.fetch = async function (input, init) {
      const url = typeof input === 'string' ? input : ((input && input.url) || '');
      const sameOrigin = url.startsWith('/') || url.startsWith(window.location.origin);
      const key = localStorage.getItem('sa_key');
      if (sameOrigin && key) {
        init = init || {};
        init.headers = Object.assign({}, init.headers || {}, { 'X-Scheduler-Key': key });
      }
      const resp = await realFetch(input, init);
      if (resp.status === 403 && sameOrigin && !window.__saKeyPrompting) {
        window.__saKeyPrompting = true;
        try {
          const entered = window.prompt('This action needs the API key. Enter it to unlock:');
          if (entered && entered.trim()) {
            window.saSetKey(entered.trim());
            return window.fetch(input, init);
          }
        } finally {
          window.__saKeyPrompting = false;
        }
      }
      return resp;
    };
  })();
</script>
```

- [ ] **Step 2: Bump the service-worker cache version so deployed clients pick up the new index.html**

Check: `grep -n "CACHE\|VERSION\|cacheName" src/frontend/prototypes/sw.js` — if a versioned name exists (e.g. `stockagent-v3`), increment it. If sw.js is network-first for index.html, skip this step and note why.

- [ ] **Step 3: Manual verification (no JS test rig in this repo)**

Run: `python -m http.server 8099 --directory src/frontend/prototypes` and open `http://localhost:8099` — confirm the console shows no wrapper syntax error and `saSetKey` is defined (`typeof saSetKey` → `"function"` in devtools). Stop the server.

- [ ] **Step 4: Commit**

```bash
git add src/frontend/prototypes/index.html src/frontend/prototypes/sw.js
git commit -m "feat(pwa): X-Scheduler-Key fetch wrapper + 403 key prompt (lockdown-ready UI)"
```

---

### Task 9: Full suite, ledger + memory updates, merge

**Files:**
- Modify: `docs/audit/LEDGER.md` (status flips), memory files (outside repo)

- [ ] **Step 1: Full test suite**

Run: `python -m pytest tests -q`
Expected: no NEW failures vs baseline 10F/10E/2150P/12S (AUD-022 stale-mock family + 1 event_ingestor date test are pre-existing)

- [ ] **Step 2: Update ledger rows**

In `docs/audit/LEDGER.md`: AUD-099 → `FIXED (2026-07-16 Wave B — gate + encoder; enforcement live once SCHEDULER_KEY is set)`; AUD-102 → `FIXED (2026-07-16 Wave B — same enforcement note)`; AUD-012 → `FIXED (2026-07-16 Wave B — https-only + cap; POST keyless BY DESIGN, rationale in plan)`; AUD-103 → `FIXED (2026-07-16 Wave B)`; AUD-014 → `FIXED (absorbed by AUD-103)`. Add a short "Wave B SHIPPED" block after the Phase 9 section following the house style of the "Wave — LLM cost/telemetry SHIPPED" block.

- [ ] **Step 3: Merge and push**

```bash
git checkout main
git merge --ff-only audit-wave-b-security
git push origin main
```

- [ ] **Step 4: Tell the user the one thing code can't do**

Lockdown activates only when they set `SCHEDULER_KEY` in Railway (Variables → add `SCHEDULER_KEY=<strong random value>`); after the next deploy, the PWA will prompt once for the key on the first gated action. Until then, posture is unchanged (gates dormant).
