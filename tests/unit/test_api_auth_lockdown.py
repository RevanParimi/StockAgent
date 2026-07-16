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
