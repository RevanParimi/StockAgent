"""tests/unit/test_startup_api_usage_report.py

The F4 durability check must run itself. A counter that silently restarted on
every deploy is exactly the class of bug nobody notices, so the boot sequence
reports the counter alongside the volume check — and a startup report that
throws must never take the server down with it.
"""
import services.api.server as server


def test_startup_reports_api_usage_state(monkeypatch):
    called: list[bool] = []
    monkeypatch.setattr(
        "services.data.stores.api_usage.log_boot_state",
        lambda: called.append(True) or {"present": True},
    )
    server._log_api_usage_check()
    assert called == [True]


def test_startup_report_failure_is_non_fatal(monkeypatch):
    def _boom():
        raise OSError("volume not mounted")

    monkeypatch.setattr("services.data.stores.api_usage.log_boot_state", _boom)
    server._log_api_usage_check()      # must not raise
