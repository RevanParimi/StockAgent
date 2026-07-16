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
