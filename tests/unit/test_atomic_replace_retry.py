"""SA-005: the rename step retries Windows' transient sharing violation, and
nothing else.

The Windows suite lost writes to os.replace raising PermissionError (WinError
5) while another handle held the target: test_delivery_api's push store,
test_ops_alerts' streak state and test_portfolio_locking's cross-process
adds. POSIX renames do not fail this way, so there the step stays one call.
"""
from __future__ import annotations

import json
import os

import pytest

from core.utils import atomic_io


class _FlakyReplace:
    """os.replace that raises PermissionError for the first `fails` calls."""

    def __init__(self, fails: int, error: type[OSError] = PermissionError) -> None:
        self.fails, self.error, self.calls = fails, error, 0
        self._real = os.replace

    def __call__(self, src, dst):
        self.calls += 1
        if self.calls <= self.fails:
            raise self.error(13, "The process cannot access the file")
        self._real(src, dst)


@pytest.fixture
def windows_retries(monkeypatch):
    """The Windows schedule, without the sleeping."""
    monkeypatch.setattr(atomic_io, "_REPLACE_RETRY_DELAYS", (0.0, 0.0, 0.0, 0.0, 0.0))
    monkeypatch.setattr(atomic_io.time, "sleep", lambda s: None)


def test_windows_schedule_is_five_retries_within_half_a_second():
    delays = atomic_io._retry_delays("nt")
    assert len(delays) == 5 and sum(delays) < 0.5


def test_posix_schedule_never_retries():
    assert atomic_io._retry_delays("posix") == ()
    assert atomic_io._REPLACE_RETRY_DELAYS == atomic_io._retry_delays(os.name)


def test_transient_violation_is_retried_until_the_write_lands(tmp_path, monkeypatch, windows_retries):
    flaky = _FlakyReplace(fails=2)
    monkeypatch.setattr(os, "replace", flaky)
    target = tmp_path / "state.json"
    atomic_io.atomic_write_json(target, {"llm_consecutive_failures": 7})
    assert flaky.calls == 3
    assert json.loads(target.read_text(encoding="utf-8")) == {"llm_consecutive_failures": 7}
    assert [p.name for p in tmp_path.iterdir()] == ["state.json"]


def test_persistent_violation_raises_after_the_last_attempt(tmp_path, monkeypatch, windows_retries):
    flaky = _FlakyReplace(fails=99)
    monkeypatch.setattr(os, "replace", flaky)
    with pytest.raises(PermissionError):
        atomic_io.atomic_write_text(tmp_path / "x.txt", "x")
    assert flaky.calls == 6                      # five retries, then the final try
    assert list(tmp_path.iterdir()) == []        # temp file cleaned up


def test_without_a_schedule_there_is_exactly_one_attempt(tmp_path, monkeypatch):
    monkeypatch.setattr(atomic_io, "_REPLACE_RETRY_DELAYS", ())
    flaky = _FlakyReplace(fails=1)
    monkeypatch.setattr(os, "replace", flaky)
    with pytest.raises(PermissionError):
        atomic_io.atomic_write_text(tmp_path / "x.txt", "x")
    assert flaky.calls == 1


def test_other_os_errors_are_not_retried(tmp_path, monkeypatch, windows_retries):
    flaky = _FlakyReplace(fails=1, error=FileNotFoundError)
    monkeypatch.setattr(os, "replace", flaky)
    with pytest.raises(FileNotFoundError):
        atomic_io.atomic_write_text(tmp_path / "x.txt", "x")
    assert flaky.calls == 1


def test_push_store_survives_a_transient_violation(tmp_path, monkeypatch, windows_retries):
    from core.delivery.channels import PushStore
    monkeypatch.setattr(os, "replace", _FlakyReplace(fails=1))
    store = PushStore(path=str(tmp_path / "push_subscriptions.json"))
    assert store.add({"endpoint": "https://push.example/1"}, user_id="u1") == 1
    assert store.list("u1") == [{"endpoint": "https://push.example/1"}]


def test_portfolio_store_survives_a_transient_violation(tmp_path, monkeypatch, windows_retries):
    from backend.shared.schemas.portfolio import Holding
    from core.portfolio.store import PortfolioStore
    monkeypatch.setattr(os, "replace", _FlakyReplace(fails=1))
    store = PortfolioStore(user_id="u1", base_dir=str(tmp_path))
    store.add_holding(Holding(symbol="MARUTI", sector="automobile", qty=3.0, avg_buy_price=100.0,
                              adj_avg_price=100.0, adj_qty=3.0, buy_date="2026-07-01"))
    assert [(h.symbol, h.qty) for h in store.load().holdings] == [("MARUTI", 3.0)]
