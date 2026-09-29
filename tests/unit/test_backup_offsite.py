"""SA-007: the encrypted off-site copy — signing, encryption, confirmation,
interrupted uploads, retention and recovery from the off-site store alone.

No real transport: S3 is an in-memory double that enforces what a real bucket
enforces (x-amz-content-sha256 must match the body; ListObjectsV2 pages), and
the hermetic guard blocks sockets. Signatures are checked against AWS's own
published examples, not against this implementation.
"""
import base64
import hashlib
import json
import logging
import re
import sqlite3
import zipfile
from urllib.parse import parse_qsl, unquote, urlsplit

import pytest

from services.data import backup, offsite, restore

KEY = base64.b64encode(bytes(range(32))).decode()
SECRET = "wJalrXUtnFEMI-TEST-SECRET-9c1d"
LEDGER = b'{"txn_id": "t0", "cash_before": 100.0, "cash_after": 90.0}\n'


@pytest.fixture()
def data_dir(tmp_path):
    d = tmp_path / "data"
    (d / "portfolio" / "primary").mkdir(parents=True)
    (d / "portfolio" / "primary" / "transactions.jsonl").write_bytes(LEDGER)
    conn = sqlite3.connect(d / "scores.db")
    conn.execute("CREATE TABLE s (x)")
    conn.executemany("INSERT INTO s VALUES (?)", [(1,), (2,)])
    conn.commit()
    conn.close()
    return d


def _archive(data_dir):
    archive = backup.create_backup_archive(data_dir=data_dir)
    return archive, json.loads(backup.sidecar_path(archive).read_text())


def dir_cfg(root, **kw):
    return offsite.OffsiteConfig(**{"target": "dir", "encryption_key": KEY,
                                    "dir_path": str(root), **kw})


def s3_cfg(**kw):
    return offsite.OffsiteConfig(**{
        "target": "s3", "encryption_key": KEY, "s3_endpoint": "https://s3.example.test",
        "s3_bucket": "bk", "s3_region": "eu-test-1", "s3_prefix": "stockagent/",
        "s3_access_key_id": "AKIDTEST", "s3_secret_access_key": SECRET, **kw})


# --------------------------------------------------------------------------
# AWS Signature V4 — AWS's published S3 examples (access key
# AKIAIOSFODNN7EXAMPLE, 2013-05-24, us-east-1, bucket examplebucket)
# --------------------------------------------------------------------------

AWS_SECRET = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
EMPTY = hashlib.sha256(b"").hexdigest()


@pytest.mark.parametrize("method,uri,query,extra,payload,signature", [
    ("GET", "/test.txt", {}, {"Range": "bytes=0-9"}, EMPTY,
     "f0e8bdb87c964420e857bd35b5d6ed310bd44f0170aba48dd91039c6036bdb41"),
    ("PUT", "/test%24file.text", {},
     {"Date": "Fri, 24 May 2013 00:00:00 GMT", "x-amz-storage-class": "REDUCED_REDUNDANCY"},
     hashlib.sha256(b"Welcome to Amazon S3.").hexdigest(),
     "98ad721746da40c64f1a55b78f14c238d841ea1380cd77a1b5971af0ece108bd"),
    ("GET", "/", {"max-keys": "2", "prefix": "J"}, {}, EMPTY,
     "34b48302e7b5fa45bde8084f4b7868a86f0a534bc59db6670ed5711ef69dc6f7"),
])
def test_sigv4_matches_aws_published_examples(method, uri, query, extra, payload, signature):
    headers = {"Host": "examplebucket.s3.amazonaws.com", "x-amz-content-sha256": payload,
               "x-amz-date": "20130524T000000Z", **extra}
    auth = offsite.sigv4_authorization(method, uri, query, headers, payload,
                                       access_key_id="AKIAIOSFODNN7EXAMPLE",
                                       secret_key=AWS_SECRET, amz_date="20130524T000000Z",
                                       region="us-east-1")
    assert auth.startswith("AWS4-HMAC-SHA256 Credential=AKIAIOSFODNN7EXAMPLE/20130524/"
                           "us-east-1/s3/aws4_request,SignedHeaders=")
    assert auth.endswith("Signature=" + signature)


# --------------------------------------------------------------------------
# Encryption
# --------------------------------------------------------------------------

def test_encryption_round_trip_and_every_tamper_fails(tmp_path):
    key = base64.b64decode(KEY)
    plain = tmp_path / "p.zip"
    plain.write_bytes(LEDGER * 5000)
    enc = tmp_path / "p.zip.enc"
    meta = offsite.encrypt_file(plain, enc, key)
    blob = enc.read_bytes()
    assert meta == {"bytes": len(blob), "sha256": hashlib.sha256(blob).hexdigest()}
    assert LEDGER not in blob
    out = tmp_path / "out.zip"
    offsite.decrypt_file(enc, out, key)
    assert out.read_bytes() == plain.read_bytes()

    def fails(data, use_key=key):
        bad = tmp_path / "bad.enc"
        bad.write_bytes(data)
        target = tmp_path / "bad.zip"
        with pytest.raises(offsite.OffsiteError):
            offsite.decrypt_file(bad, target, use_key)
        assert not target.exists() and not (tmp_path / "bad.zip.part").exists()

    flipped = bytearray(blob)
    flipped[len(blob) // 2] ^= 1
    fails(bytes(flipped))                                   # ciphertext byte
    header = bytearray(blob)
    header[6] ^= 1
    fails(bytes(header))                                    # nonce (authenticated header)
    fails(blob[:-1])                                        # truncated tag
    fails(blob[:10])                                        # shorter than the header
    fails(b"PK\x03\x04" + blob[4:])                         # not our format
    fails(blob, use_key=bytes(32))                          # wrong key


@pytest.mark.parametrize("raw,needle", [("", "unset"), ("not base64!", "not valid base64"),
                                        (base64.b64encode(b"short").decode(), "32 bytes")])
def test_encryption_key_errors_never_echo_the_value(raw, needle):
    with pytest.raises(offsite.OffsiteError) as err:
        offsite.encryption_key(offsite.OffsiteConfig(encryption_key=raw))
    assert needle in str(err.value)
    assert not raw or raw not in str(err.value)


def test_urlsafe_key_alphabet_is_accepted():
    raw = bytes([251, 255] * 16)
    urlsafe = base64.urlsafe_b64encode(raw).decode()
    assert "-" in urlsafe or "_" in urlsafe
    assert offsite.encryption_key(offsite.OffsiteConfig(encryption_key=urlsafe)) == raw


# --------------------------------------------------------------------------
# Directory target: recovery from the off-site copy alone
# --------------------------------------------------------------------------

def test_offsite_copy_alone_restores_the_volume(data_dir, tmp_path):
    archive, sidecar = _archive(data_dir)
    root = tmp_path / "second-disk"
    result = offsite.push(archive, sidecar, dir_cfg(root), data_dir=data_dir)
    assert result.confirmed, result.as_dict()
    stored = sorted(p.name for p in root.iterdir())
    assert stored == [archive.name + ".enc", archive.name + ".manifest.json"]
    blob = (root / (archive.name + ".enc")).read_bytes()
    assert not blob.startswith(b"PK") and LEDGER not in blob
    remote = json.loads((root / (archive.name + ".manifest.json")).read_text())
    assert remote["sha256"] == sidecar["sha256"] and "files" in remote
    assert "transactions" not in json.dumps(remote)          # no file paths off-site in clear

    for p in list(data_dir.rglob("*")):                      # the volume is lost
        if p.is_file():
            p.unlink()
    got = offsite.fetch(None, tmp_path / "download", dir_cfg(root), data_dir=data_dir)
    drill = restore.verify_archive(got, tmp_path / "restored", protected=(data_dir,))
    assert drill.clean, drill.as_dict()
    assert (tmp_path / "restored/portfolio/primary/transactions.jsonl").read_bytes() == LEDGER
    conn = sqlite3.connect(tmp_path / "restored/scores.db")
    try:
        assert conn.execute("SELECT COUNT(*) FROM s").fetchone() == (2,)
    finally:
        conn.close()


@pytest.mark.parametrize("where", ["same", "inside", "parent"])
def test_dir_target_overlapping_the_volume_is_refused(data_dir, where):
    archive, sidecar = _archive(data_dir)
    root = {"same": data_dir, "inside": data_dir / "offsite", "parent": data_dir.parent}[where]
    result = offsite.push(archive, sidecar, dir_cfg(root), data_dir=data_dir)
    assert not result.confirmed and "not off-site" in result.reason
    assert not (data_dir / "offsite").exists()


def test_unconfigured_or_keyless_push_is_refused_and_writes_nothing(data_dir, tmp_path):
    archive, sidecar = _archive(data_dir)
    off = offsite.push(archive, sidecar, offsite.OffsiteConfig(), data_dir=data_dir)
    assert off.target is None and not off.confirmed and "not configured" in off.reason
    root = tmp_path / "disk"
    keyless = offsite.push(archive, sidecar, dir_cfg(root, encryption_key=""), data_dir=data_dir)
    assert not keyless.confirmed and "BACKUP_ENCRYPTION_KEY is unset" in keyless.reason
    assert not root.exists()


def test_fetch_rejects_ciphertext_that_does_not_match_its_manifest(data_dir, tmp_path):
    archive, sidecar = _archive(data_dir)
    root = tmp_path / "disk"
    assert offsite.push(archive, sidecar, dir_cfg(root), data_dir=data_dir).confirmed
    enc = root / (archive.name + ".enc")
    enc.write_bytes(enc.read_bytes()[:-5])
    with pytest.raises(offsite.OffsiteError, match="does not match its manifest"):
        offsite.fetch(archive.name, tmp_path / "dl", dir_cfg(root), data_dir=data_dir)
    assert not (tmp_path / "dl" / archive.name).exists()


def test_fetch_refuses_names_that_are_not_archives(data_dir, tmp_path):
    with pytest.raises(offsite.OffsiteError, match="not a backup archive name"):
        offsite.fetch("../../etc/passwd", tmp_path / "dl", dir_cfg(tmp_path / "disk"),
                      data_dir=data_dir)


# --------------------------------------------------------------------------
# Retention
# --------------------------------------------------------------------------

def _seed_remote(root, stamps):
    root.mkdir(parents=True, exist_ok=True)
    for s in stamps:
        (root / f"stockagent-backup-{s}.zip.enc").write_bytes(b"c")
        (root / f"stockagent-backup-{s}.zip.manifest.json").write_text("{}")


def test_remote_retention_boundary(data_dir, tmp_path):
    root = tmp_path / "disk"
    _seed_remote(root, ["20260901-180000", "20260902-180000", "20260903-180000"])
    (root / "stockagent-backup-20260902-190000.zip.enc").write_bytes(b"orphan")   # interrupted
    (root / "notes.txt").write_text("the owner's file")
    archive, sidecar = _archive(data_dir)                   # stamped now: the newest
    result = offsite.push(archive, sidecar, dir_cfg(root, keep=3), data_dir=data_dir)
    assert result.confirmed and result.pruned == 1
    assert sorted(p.name for p in root.iterdir()) == sorted([
        "notes.txt",
        "stockagent-backup-20260902-180000.zip.enc",
        "stockagent-backup-20260902-180000.zip.manifest.json",
        "stockagent-backup-20260903-180000.zip.enc",
        "stockagent-backup-20260903-180000.zip.manifest.json",
        archive.name + ".enc", archive.name + ".manifest.json"])


def test_remote_retention_zero_keeps_everything(data_dir, tmp_path):
    root = tmp_path / "disk"
    _seed_remote(root, [f"202609{d:02d}-180000" for d in range(1, 6)])
    archive, sidecar = _archive(data_dir)
    result = offsite.push(archive, sidecar, dir_cfg(root, keep=0), data_dir=data_dir)
    assert result.confirmed and result.pruned == 0
    assert len(list(root.iterdir())) == 12


def test_prune_drops_the_manifest_before_the_ciphertext():
    order = []

    class Spy:
        def list(self):
            return ["stockagent-backup-20260901-180000.zip.enc",
                    "stockagent-backup-20260901-180000.zip.manifest.json",
                    "stockagent-backup-20260902-180000.zip.enc",
                    "stockagent-backup-20260902-180000.zip.manifest.json"]

        def delete(self, name):
            order.append(name)
    assert offsite.prune_remote(Spy(), keep=1) == 1
    assert order == ["stockagent-backup-20260901-180000.zip.manifest.json",
                     "stockagent-backup-20260901-180000.zip.enc"]


# --------------------------------------------------------------------------
# S3 target through an in-memory bucket
# --------------------------------------------------------------------------

AUTH_RE = re.compile(r"AWS4-HMAC-SHA256 Credential=AKIDTEST/\d{8}/eu-test-1/s3/aws4_request,"
                     r"SignedHeaders=host;x-amz-content-sha256;x-amz-date,"
                     r"Signature=[0-9a-f]{64}")


class Resp:
    def __init__(self, status, headers=None, content=b"", text=None):
        self.status_code = status
        self.headers = headers or {}
        self.content = content
        self.text = text if text is not None else content.decode("latin-1")

    def iter_content(self, n):
        for i in range(0, len(self.content), n):
            yield self.content[i:i + n]

    def close(self):
        pass


class FakeS3:
    """Path-style bucket `bk` at s3.example.test with 2-key list pages."""
    PAGE = 2

    def __init__(self, drop_on=None, corrupt=False, head_delta=0):
        self.objects: dict[str, bytes] = {}
        self.calls: list[tuple[str, str, dict]] = []
        self.drop_on, self.corrupt, self.head_delta = drop_on, corrupt, head_delta

    def request(self, method, url, headers=None, data=None, timeout=None, stream=False):
        parts = urlsplit(url)
        headers = dict(headers or {})
        self.calls.append((method, url, headers))
        assert parts.scheme == "https" and parts.netloc == "s3.example.test"
        assert AUTH_RE.fullmatch(headers["Authorization"]), headers["Authorization"]
        path = unquote(parts.path)
        assert path == "/bk" or path.startswith("/bk/")
        key = path[len("/bk/"):]
        if method == "PUT":
            body = data.read()
            assert int(headers["Content-Length"]) == len(body)
            if self.drop_on and key.endswith(self.drop_on):
                self.objects[key] = body[:len(body) // 2]   # worst case: a partial object
                raise ConnectionResetError("connection reset by peer")
            if self.corrupt:
                body = body[:-1] + bytes([body[-1] ^ 1])
            if hashlib.sha256(body).hexdigest() != headers["x-amz-content-sha256"]:
                return Resp(400, text="<Error><Code>XAmzContentSHA256Mismatch</Code></Error>")
            self.objects[key] = body
            return Resp(200)
        if method == "HEAD":
            if key not in self.objects:
                return Resp(404)
            return Resp(200, headers={"Content-Length": str(len(self.objects[key]) + self.head_delta)})
        if method == "DELETE":
            self.objects.pop(key, None)
            return Resp(204)
        if method == "GET" and key:
            if key not in self.objects:
                return Resp(404, text="<Error><Code>NoSuchKey</Code></Error>")
            return Resp(200, content=self.objects[key])
        query = dict(parse_qsl(parts.query))
        assert method == "GET" and query["list-type"] == "2"
        keys = sorted(k for k in self.objects if k.startswith(query["prefix"]))
        start = int(query.get("continuation-token", 0))
        page, more = keys[start:start + self.PAGE], start + self.PAGE < len(keys)
        xml = ('<?xml version="1.0" encoding="UTF-8"?>'
               '<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
               + "".join(f"<Contents><Key>{k}</Key></Contents>" for k in page)
               + f"<IsTruncated>{'true' if more else 'false'}</IsTruncated>"
               + (f"<NextContinuationToken>{start + self.PAGE}</NextContinuationToken>"
                  if more else "") + "</ListBucketResult>")
        return Resp(200, content=xml.encode())


def test_s3_push_confirms_lists_across_pages_and_restores(data_dir, tmp_path):
    s3 = FakeS3()
    for stamp in ("20260901-180000", "20260902-180000"):           # older copies: 2+ pages
        s3.objects[f"stockagent/stockagent-backup-{stamp}.zip.enc"] = b"c"
        s3.objects[f"stockagent/stockagent-backup-{stamp}.zip.manifest.json"] = b"{}"
    s3.objects["elsewhere/stockagent-backup-20260101-180000.zip.manifest.json"] = b"{}"
    archive, sidecar = _archive(data_dir)
    result = offsite.push(archive, sidecar, s3_cfg(), data_dir=data_dir, http=s3)
    assert result.confirmed and result.target == "s3", result.as_dict()
    puts = [unquote(urlsplit(url).path) for method, url, _ in s3.calls if method == "PUT"]
    assert puts == [f"/bk/stockagent/{archive.name}.enc",
                    f"/bk/stockagent/{archive.name}.manifest.json"]      # manifest LAST
    lists = [c for c in s3.calls if c[0] == "GET" and "list-type" in c[1]]
    assert len(lists) == 3                                            # 6 keys, 2 per page

    got = offsite.fetch(None, tmp_path / "dl", s3_cfg(), data_dir=data_dir, http=s3)
    assert got.name == archive.name                                   # the newest confirmed
    assert restore.verify_archive(got, tmp_path / "restored", protected=(data_dir,)).clean
    for _, url, headers in s3.calls:
        seen = url + json.dumps(headers)
        assert SECRET not in seen and KEY not in seen


def test_interrupted_s3_upload_is_not_confirmed_and_is_cleaned_later(data_dir, tmp_path, monkeypatch):
    s3 = FakeS3(drop_on=".zip.enc")
    first, first_side = _archive(data_dir)
    result = offsite.push(first, first_side, s3_cfg(), data_dir=data_dir, http=s3)
    assert not result.confirmed and "ConnectionResetError" in result.reason
    assert list(s3.objects) == [f"stockagent/{first.name}.enc"]      # partial, no manifest
    with pytest.raises(offsite.OffsiteError, match="no confirmed off-site backup"):
        offsite.fetch(None, tmp_path / "dl", s3_cfg(), data_dir=data_dir, http=s3)

    import itertools
    from datetime import datetime, timezone
    tick = itertools.count(1)

    class Later(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2099, 1, 1, 0, 0, next(tick), tzinfo=timezone.utc)
    monkeypatch.setattr(backup, "datetime", Later)
    s3.drop_on = None
    second, second_side = _archive(data_dir)
    assert offsite.push(second, second_side, s3_cfg(), data_dir=data_dir, http=s3).confirmed
    assert sorted(s3.objects) == [f"stockagent/{second.name}.enc",
                                  f"stockagent/{second.name}.manifest.json"]


def test_copy_that_reads_back_at_the_wrong_size_is_not_confirmed(data_dir):
    s3 = FakeS3(head_delta=-1)
    archive, sidecar = _archive(data_dir)
    result = offsite.push(archive, sidecar, s3_cfg(), data_dir=data_dir, http=s3)
    assert not result.confirmed and "did not read back" in result.reason
    assert not any(k.endswith(".manifest.json") for k in s3.objects)


def test_body_corrupted_in_transit_is_rejected_by_the_signed_hash(data_dir):
    s3 = FakeS3(corrupt=True)
    archive, sidecar = _archive(data_dir)
    result = offsite.push(archive, sidecar, s3_cfg(), data_dir=data_dir, http=s3)
    assert not result.confirmed
    assert "HTTP 400 XAmzContentSHA256Mismatch" in result.reason and s3.objects == {}


@pytest.mark.parametrize("endpoint", ["http://s3.example.test", "https://s3.example.test/bk",
                                      "s3.example.test"])
def test_s3_endpoint_must_be_a_bare_https_url(data_dir, endpoint):
    archive, sidecar = _archive(data_dir)
    result = offsite.push(archive, sidecar, s3_cfg(s3_endpoint=endpoint), data_dir=data_dir,
                          http=FakeS3())
    assert not result.confirmed and "bare https://" in result.reason


def test_missing_s3_credentials_are_named_not_shown(data_dir):
    archive, sidecar = _archive(data_dir)
    result = offsite.push(archive, sidecar, s3_cfg(s3_access_key_id=""), data_dir=data_dir,
                          http=FakeS3())
    assert "BACKUP_S3_ACCESS_KEY_ID" in result.reason and SECRET not in result.reason


# --------------------------------------------------------------------------
# Secrets stay out of logs, status and errors
# --------------------------------------------------------------------------

def test_secrets_never_reach_reasons_logs_status_or_repr(data_dir, monkeypatch, caplog):
    caplog.set_level(logging.DEBUG)

    class Leaky(FakeS3):
        def request(self, method, url, **kw):
            raise OSError(f"proxy refused credentials {SECRET} / {KEY}")
    monkeypatch.setattr("requests.request", Leaky().request)
    for name, value in (("BACKUP_OFFSITE_TARGET", "s3"), ("BACKUP_ENCRYPTION_KEY", KEY),
                        ("BACKUP_S3_ENDPOINT", "https://s3.example.test"),
                        ("BACKUP_S3_BUCKET", "bk"), ("BACKUP_S3_REGION", "eu-test-1"),
                        ("BACKUP_S3_ACCESS_KEY_ID", "AKIDTEST"),
                        ("BACKUP_S3_SECRET_ACCESS_KEY", SECRET)):
        monkeypatch.setattr(f"core.config.settings.{name}", value, raising=False)
    monkeypatch.setattr("core.delivery.channels.send_email", lambda *a, **k: False)

    cfg = offsite.config_from_settings()
    assert SECRET not in repr(cfg) and KEY not in repr(cfg)
    summary = backup.run_backup_job(data_dir=data_dir)
    assert summary["offsite_confirmed"] is False
    assert "<secret>" in summary["offsite_reason"]
    status = (data_dir / "backups" / backup.STATUS_NAME).read_text()
    with zipfile.ZipFile(summary["archive"]) as z:
        archived = b"".join(z.read(n) for n in z.namelist())
    for text in (summary["offsite_reason"], status, caplog.text, json.dumps(summary)):
        assert SECRET not in text and KEY not in text
    assert SECRET.encode() not in archived and KEY.encode() not in archived


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def test_cli_drill_and_fetch(data_dir, tmp_path, monkeypatch, capsys):
    archive, sidecar = _archive(data_dir)
    assert restore.main(["drill", str(archive), "--dest", str(tmp_path / "d1")]) == 0
    assert json.loads(capsys.readouterr().out)["clean"] is True

    root = tmp_path / "disk"
    assert offsite.push(archive, sidecar, dir_cfg(root), data_dir=data_dir).confirmed
    for name, value in (("BACKUP_OFFSITE_TARGET", "dir"), ("BACKUP_OFFSITE_DIR", str(root)),
                        ("BACKUP_ENCRYPTION_KEY", KEY)):
        monkeypatch.setattr(f"core.config.settings.{name}", value, raising=False)
    assert restore.main(["fetch", "--dest", str(tmp_path / "d2")]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["clean"] and out["restored_to"].endswith("restored")
    assert (tmp_path / "d2/restored/portfolio/primary/transactions.jsonl").read_bytes() == LEDGER

    busy = tmp_path / "d2"                                  # not empty any more
    assert restore.main(["fetch", "--dest", str(busy)]) == 1
    assert "not an empty directory" in json.loads(capsys.readouterr().out)["error"]
