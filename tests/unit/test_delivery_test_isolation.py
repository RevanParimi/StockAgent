"""Regression guard for the 2026-07-16 incident: the AUD-050 quarantine tests
(fixture users u1/u9) emailed REAL [ALERT]s through live SMTP creds sitting in
the developer's .env, and test alerts polluted the repo's real
data/delivery/alerts_sent.jsonl. Under pytest, delivery transports must be
inert and the default sent-log must never be the repo's real one — enforced by
the autouse _no_real_deliveries fixture in tests/conftest.py."""
from pathlib import Path


def test_delivery_transports_forced_off_under_pytest():
    from core.config import settings
    assert settings.DELIVERY_EMAIL_ENABLED is False
    assert settings.DELIVERY_PUSH_ENABLED is False


def test_default_sent_log_redirected_away_from_repo():
    from core.delivery import alerts
    p = alerts._sent_log_path(None)
    assert p.resolve() != Path("data/delivery/alerts_sent.jsonl").resolve()


def test_emit_alerts_does_not_write_repo_sent_log():
    from core.delivery.alerts import AlertEvent, emit_alerts
    repo_log = Path("data/delivery/alerts_sent.jsonl")
    before = repo_log.read_text(encoding="utf-8") if repo_log.exists() else None
    emit_alerts([AlertEvent(date="2026-01-01", kind="isolation_probe",
                            message="conftest isolation probe")])
    after = repo_log.read_text(encoding="utf-8") if repo_log.exists() else None
    assert before == after
