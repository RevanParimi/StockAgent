"""AUD-088: send_email grows optional file attachments (zip backup rider)."""
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


def _enable_email(monkeypatch):
    monkeypatch.setattr(channels.settings, "DELIVERY_EMAIL_ENABLED", True)
    monkeypatch.setattr(channels.settings, "SMTP_HOST", "smtp.test")
    monkeypatch.setattr(channels.settings, "SMTP_USER", "u@test")
    monkeypatch.setattr(channels.settings, "SMTP_PASSWORD", "pw")
    monkeypatch.setattr(channels.settings, "DELIVERY_EMAIL_TO", "to@test")
    monkeypatch.setattr(channels.smtplib, "SMTP", _FakeSMTP)
    _FakeSMTP.sent = []


def test_email_with_attachment_is_multipart(monkeypatch, tmp_path):
    _enable_email(monkeypatch)
    f = tmp_path / "backup.zip"
    f.write_bytes(b"PK\x03\x04fakezip")
    assert channels.send_email("subj", "body text", attachments=[f]) is True
    payload = _FakeSMTP.sent[0]
    assert "multipart" in payload.lower()
    assert 'filename="backup.zip"' in payload
    assert "body text" in payload


def test_email_without_attachment_unchanged(monkeypatch):
    _enable_email(monkeypatch)
    assert channels.send_email("subj", "plain body") is True
    assert "multipart" not in _FakeSMTP.sent[0].lower()


def test_missing_attachment_file_fails_closed(monkeypatch, tmp_path):
    _enable_email(monkeypatch)
    assert channels.send_email("subj", "body", attachments=[tmp_path / "nope.zip"]) is False
    assert _FakeSMTP.sent == []
