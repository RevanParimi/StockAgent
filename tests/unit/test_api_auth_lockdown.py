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
