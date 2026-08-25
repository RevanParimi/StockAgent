"""tests/unit/test_startup_run_history_report.py

Task B1: the run-history durability check must run itself.

`run_summaries.jsonl` sat at 13 rows for 53 days and nobody noticed, because
noticing required someone to ssh in and count. The boot sequence now reports
the surviving row count next to the API-counter check — and, like that one, a
report that throws must never take the server down with it.
"""
import services.api.server as server


def test_startup_reports_run_history_state(monkeypatch):
    called: list[bool] = []
    monkeypatch.setattr(
        "services.data.stores.run_logger.log_boot_state",
        lambda: called.append(True) or {"db_rows": 0},
    )
    server._log_run_history_check()
    assert called == [True]


def test_startup_report_failure_is_non_fatal(monkeypatch):
    def _boom():
        raise OSError("volume not mounted")

    monkeypatch.setattr("services.data.stores.run_logger.log_boot_state", _boom)
    server._log_run_history_check()      # must not raise
