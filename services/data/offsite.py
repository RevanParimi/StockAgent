"""
Independent off-site copy of the nightly backup (SA-007).

The nightly archive (services/data/backup.py) sits on the Railway volume it
protects, and its email copy rides a channel that failed for months (audit
F17). This module pushes an ENCRYPTED copy of each archive that passed its
restore drill to storage the app volume does not host:

  s3   any S3-compatible bucket (Backblaze B2, Cloudflare R2, AWS S3, MinIO),
       path-style over HTTPS, signed with AWS Signature V4. No SDK.
  dir  a separately mounted directory. Refused when it overlaps data/,
       because a copy on the volume it protects is not off-site.

Nothing here provisions storage. The owner creates the bucket and a key
scoped to it, then sets the BACKUP_* variables (KT section 10).

Objects per archive, under the configured prefix:
  <name>.zip.enc            the zip, AES-256-GCM encrypted with BACKUP_ENCRYPTION_KEY
  <name>.zip.manifest.json  archive-level integrity metadata (no file paths).
                            Uploaded LAST, so its presence means the archive
                            upload completed and read back at the right size.
Encrypted form: b"SABK" 0x01 | 12-byte nonce | ciphertext | 16-byte tag; the
17-byte header is the GCM associated data. A copy counts as confirmed only
when both objects read back (HEAD) at their uploaded sizes.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import logging
import os
import re
import shutil
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlsplit

from services.data.backup import ARCHIVE_RE, SIDECAR_SUFFIX, file_digest

logger = logging.getLogger(__name__)

ENC_SUFFIX = ".enc"
DEFAULT_KEEP = 30
EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()
_MAGIC = b"SABK\x01"
_NONCE_LEN = 12
_TAG_LEN = 16
_CHUNK = 1024 * 1024
_TIMEOUT = (10, 300)          # (connect, read) seconds


class OffsiteError(RuntimeError):
    """A configuration or store failure. Messages never carry a secret."""


@dataclass(frozen=True)
class OffsiteConfig:
    target: str = ""                        # "" (off) | "s3" | "dir"
    encryption_key: str = field(default="", repr=False)
    keep: int = DEFAULT_KEEP                # confirmed copies kept; <= 0 keeps all
    dir_path: str = ""
    s3_endpoint: str = ""
    s3_bucket: str = ""
    s3_region: str = "auto"
    s3_prefix: str = "stockagent/"
    s3_access_key_id: str = field(default="", repr=False)
    s3_secret_access_key: str = field(default="", repr=False)

    def secrets(self) -> tuple[str, ...]:
        return tuple(s for s in (self.encryption_key, self.s3_secret_access_key,
                                 self.s3_access_key_id) if s)


def config_from_settings() -> OffsiteConfig:
    from core.config import settings

    def val(name: str, default: str = "") -> str:
        return str(getattr(settings, name, default) or default).strip()

    try:
        keep = int(val("BACKUP_OFFSITE_KEEP", str(DEFAULT_KEEP)))
    except ValueError:
        keep = DEFAULT_KEEP
    return OffsiteConfig(
        target=val("BACKUP_OFFSITE_TARGET").lower(),
        encryption_key=val("BACKUP_ENCRYPTION_KEY"),
        keep=keep,
        dir_path=val("BACKUP_OFFSITE_DIR"),
        s3_endpoint=val("BACKUP_S3_ENDPOINT"),
        s3_bucket=val("BACKUP_S3_BUCKET"),
        s3_region=val("BACKUP_S3_REGION", "auto"),
        s3_prefix=val("BACKUP_S3_PREFIX", "stockagent/"),
        s3_access_key_id=val("BACKUP_S3_ACCESS_KEY_ID"),
        s3_secret_access_key=val("BACKUP_S3_SECRET_ACCESS_KEY"),
    )


def scrub(text: object, cfg: OffsiteConfig) -> str:
    """Mask every configured secret; one line, capped at 300 characters."""
    out = str(text)
    for secret in cfg.secrets():
        if len(secret) >= 4:
            out = out.replace(secret, "<secret>")
    return out.replace("\n", " ")[:300]


# ---------------------------------------------------------------------------
# Encryption
# ---------------------------------------------------------------------------

def encryption_key(cfg: OffsiteConfig) -> bytes:
    """The 32-byte AES key from BACKUP_ENCRYPTION_KEY (base64, either alphabet)."""
    raw = cfg.encryption_key
    if not raw:
        raise OffsiteError("BACKUP_ENCRYPTION_KEY is unset; an unencrypted off-site "
                           "copy is refused")
    try:
        key = base64.b64decode(raw.replace("-", "+").replace("_", "/"), validate=True)
    except (binascii.Error, ValueError):
        raise OffsiteError("BACKUP_ENCRYPTION_KEY is not valid base64") from None
    if len(key) != 32:
        raise OffsiteError("BACKUP_ENCRYPTION_KEY must decode to 32 bytes")
    return key


def encrypt_file(src: Path, dst: Path, key: bytes) -> dict:
    """Stream `src` into the SABK1 form at `dst`. Returns {bytes, sha256} of dst."""
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    nonce = os.urandom(_NONCE_LEN)
    header = _MAGIC + nonce
    enc = Cipher(algorithms.AES(key), modes.GCM(nonce)).encryptor()
    enc.authenticate_additional_data(header)
    part = dst.with_name(dst.name + ".part")
    try:
        with open(src, "rb") as fin, open(part, "wb") as fout:
            fout.write(header)
            while chunk := fin.read(_CHUNK):
                fout.write(enc.update(chunk))
            fout.write(enc.finalize())
            fout.write(enc.tag)
        os.replace(part, dst)
    except BaseException:
        part.unlink(missing_ok=True)
        raise
    return file_digest(dst)


def decrypt_file(src: Path, dst: Path, key: bytes) -> None:
    """Inverse of encrypt_file. Nothing is left at `dst` unless the GCM tag
    verifies: a wrong key, a flipped byte or a truncated file all raise."""
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    size = src.stat().st_size
    head_len = len(_MAGIC) + _NONCE_LEN
    if size < head_len + _TAG_LEN:
        raise OffsiteError(f"{src.name} is truncated")
    part = dst.with_name(dst.name + ".part")
    try:
        with open(src, "rb") as fin:
            header = fin.read(head_len)
            if header[:len(_MAGIC)] != _MAGIC:
                raise OffsiteError(f"{src.name} is not a StockAgent encrypted backup")
            fin.seek(size - _TAG_LEN)
            tag = fin.read(_TAG_LEN)
            fin.seek(head_len)
            dec = Cipher(algorithms.AES(key),
                         modes.GCM(header[len(_MAGIC):], tag)).decryptor()
            dec.authenticate_additional_data(header)
            remaining = size - head_len - _TAG_LEN
            with open(part, "wb") as fout:
                while remaining:
                    chunk = fin.read(min(_CHUNK, remaining))
                    if not chunk:
                        raise OffsiteError(f"{src.name} ended early")
                    remaining -= len(chunk)
                    fout.write(dec.update(chunk))
                fout.write(dec.finalize())
        os.replace(part, dst)
    except InvalidTag:
        part.unlink(missing_ok=True)
        raise OffsiteError(f"{src.name} failed authentication: wrong key or "
                           "corrupted ciphertext") from None
    except BaseException:
        part.unlink(missing_ok=True)
        raise


# ---------------------------------------------------------------------------
# Stores. Methods take bare object names; a store applies its own prefix.
# ---------------------------------------------------------------------------

class DirStore:
    kind = "dir"

    def __init__(self, root: Path):
        self.root = Path(root)

    def put(self, name: str, src: Path, sha256: str) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        part = self.root / (name + ".part")
        try:
            shutil.copyfile(src, part)
            os.replace(part, self.root / name)
        except BaseException:
            part.unlink(missing_ok=True)
            raise

    def head(self, name: str) -> int | None:
        path = self.root / name
        return path.stat().st_size if path.is_file() else None

    def get(self, name: str, dst: Path) -> None:
        src = self.root / name
        if not src.is_file():
            raise OffsiteError(f"{name} is not in the off-site directory")
        shutil.copyfile(src, dst)

    def list(self) -> list[str]:
        if not self.root.is_dir():
            return []
        return sorted(p.name for p in self.root.iterdir() if p.is_file())

    def delete(self, name: str) -> None:
        (self.root / name).unlink(missing_ok=True)


def _quote(value: str) -> str:
    return quote(value, safe="-_.~")


def sigv4_authorization(method: str, canonical_uri: str, query: dict[str, str],
                        headers: dict[str, str], payload_sha256: str, *,
                        access_key_id: str, secret_key: str, amz_date: str,
                        region: str, service: str = "s3") -> str:
    """AWS Signature Version 4 `Authorization` value. `canonical_uri` is
    already URI-encoded; every header passed is signed."""
    canonical_query = "&".join(f"{_quote(k)}={_quote(v)}" for k, v in sorted(query.items()))
    items = sorted((k.lower(), " ".join(str(v).split())) for k, v in headers.items())
    signed = ";".join(k for k, _ in items)
    canonical = "\n".join([method, canonical_uri, canonical_query,
                           "".join(f"{k}:{v}\n" for k, v in items), signed, payload_sha256])
    scope = f"{amz_date[:8]}/{region}/{service}/aws4_request"
    to_sign = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope,
                         hashlib.sha256(canonical.encode()).hexdigest()])
    key = ("AWS4" + secret_key).encode()
    for part in (amz_date[:8], region, service, "aws4_request"):
        key = hmac.new(key, part.encode(), hashlib.sha256).digest()
    signature = hmac.new(key, to_sign.encode(), hashlib.sha256).hexdigest()
    return (f"AWS4-HMAC-SHA256 Credential={access_key_id}/{scope},"
            f"SignedHeaders={signed},Signature={signature}")


class S3Store:
    """Path-style S3 client: PUT, HEAD, GET, DELETE and ListObjectsV2."""
    kind = "s3"

    def __init__(self, cfg: OffsiteConfig, http=None, now=None):
        ep = urlsplit(cfg.s3_endpoint)
        if ep.scheme != "https" or not ep.netloc or ep.path not in ("", "/"):
            raise OffsiteError("BACKUP_S3_ENDPOINT must be a bare https:// URL")
        missing = [n for n, v in (("BACKUP_S3_BUCKET", cfg.s3_bucket),
                                  ("BACKUP_S3_ACCESS_KEY_ID", cfg.s3_access_key_id),
                                  ("BACKUP_S3_SECRET_ACCESS_KEY", cfg.s3_secret_access_key))
                   if not v]
        if missing:
            raise OffsiteError(f"unset: {', '.join(missing)}")
        if http is None:
            import requests as http
        self._cfg = cfg
        self._http = http
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._base = f"https://{ep.netloc}"
        self._host = ep.netloc
        self._bucket_uri = "/" + _quote(cfg.s3_bucket)
        self._prefix = cfg.s3_prefix

    def _request(self, method: str, name: str = "", *, query: dict | None = None,
                 body: Path | None = None, payload_sha256: str = EMPTY_SHA256,
                 stream: bool = False):
        uri = self._bucket_uri
        if name:
            uri += "/" + quote(self._prefix + name, safe="/-_.~")
        query = query or {}
        amz_date = self._now().strftime("%Y%m%dT%H%M%SZ")
        headers = {"host": self._host, "x-amz-content-sha256": payload_sha256,
                   "x-amz-date": amz_date}
        headers["Authorization"] = sigv4_authorization(
            method, uri, query, headers, payload_sha256,
            access_key_id=self._cfg.s3_access_key_id,
            secret_key=self._cfg.s3_secret_access_key,
            amz_date=amz_date, region=self._cfg.s3_region or "auto")
        url = self._base + uri
        if query:
            url += "?" + "&".join(f"{_quote(k)}={_quote(v)}" for k, v in sorted(query.items()))
        try:
            if body is not None:
                with open(body, "rb") as fh:
                    headers["Content-Length"] = str(os.fstat(fh.fileno()).st_size)
                    return self._http.request(method, url, headers=headers, data=fh,
                                              timeout=_TIMEOUT)
            return self._http.request(method, url, headers=headers, timeout=_TIMEOUT,
                                      stream=stream)
        except Exception as exc:
            raise OffsiteError(scrub(f"{method} {name or 'bucket'}: {type(exc).__name__}: "
                                     f"{exc}", self._cfg)) from None

    def _check(self, resp, method: str, name: str, ok=(200,)) -> None:
        if resp.status_code in ok:
            return
        code = ""
        if method != "HEAD":
            match = re.search(r"<Code>([^<]{1,64})</Code>", getattr(resp, "text", "") or "")
            code = match.group(1) if match else ""
        raise OffsiteError(scrub(f"{method} {name or 'bucket'}: HTTP {resp.status_code} "
                                 f"{code}".strip(), self._cfg))

    def put(self, name: str, src: Path, sha256: str) -> None:
        self._check(self._request("PUT", name, body=src, payload_sha256=sha256), "PUT", name)

    def head(self, name: str) -> int | None:
        resp = self._request("HEAD", name)
        if resp.status_code == 404:
            return None
        self._check(resp, "HEAD", name)
        try:
            return int(resp.headers.get("Content-Length"))
        except (TypeError, ValueError):
            return None

    def get(self, name: str, dst: Path) -> None:
        resp = self._request("GET", name, stream=True)
        try:
            self._check(resp, "GET", name)
            part = dst.with_name(dst.name + ".part")
            try:
                with open(part, "wb") as fh:
                    for chunk in resp.iter_content(_CHUNK):
                        fh.write(chunk)
                os.replace(part, dst)
            except BaseException:
                part.unlink(missing_ok=True)
                raise
        finally:
            close = getattr(resp, "close", None)
            if close:
                close()

    def delete(self, name: str) -> None:
        self._check(self._request("DELETE", name), "DELETE", name, ok=(200, 204))

    def list(self) -> list[str]:
        names: list[str] = []
        token = None
        while True:
            query = {"list-type": "2", "prefix": self._prefix}
            if token:
                query["continuation-token"] = token
            resp = self._request("GET", query=query)
            self._check(resp, "LIST", "")
            root = ET.fromstring(resp.content)
            token, truncated = None, False
            for el in root.iter():
                tag = el.tag.rsplit("}", 1)[-1]
                if tag == "Key" and el.text and el.text.startswith(self._prefix):
                    rest = el.text[len(self._prefix):]
                    if rest and "/" not in rest:
                        names.append(rest)
                elif tag == "IsTruncated":
                    truncated = (el.text or "").strip().lower() == "true"
                elif tag == "NextContinuationToken":
                    token = el.text
            if not (truncated and token):
                return sorted(names)


def make_store(cfg: OffsiteConfig, *, data_dir: Path, http=None):
    if cfg.target == "s3":
        return S3Store(cfg, http=http)
    if cfg.target == "dir":
        if not cfg.dir_path:
            raise OffsiteError("BACKUP_OFFSITE_DIR is unset")
        root = Path(cfg.dir_path).resolve()
        data = Path(data_dir).resolve()
        if root == data or data in root.parents or root in data.parents:
            raise OffsiteError("BACKUP_OFFSITE_DIR overlaps the data directory, so it "
                               "is not off-site")
        return DirStore(root)
    raise OffsiteError(f"unknown BACKUP_OFFSITE_TARGET {cfg.target!r} (use s3 or dir)")


# ---------------------------------------------------------------------------
# Push, retention, fetch
# ---------------------------------------------------------------------------

@dataclass
class OffsiteResult:
    target: str | None
    confirmed: bool
    object: str | None = None
    reason: str | None = None
    pruned: int = 0

    def as_dict(self) -> dict:
        return {"target": self.target, "confirmed": self.confirmed, "object": self.object,
                "reason": self.reason, "pruned": self.pruned}


def _confirmed_archives(names: list[str]) -> list[str]:
    """Archive names that have a manifest object, oldest first."""
    return sorted(n[:-len(SIDECAR_SUFFIX)] for n in names
                  if n.endswith(SIDECAR_SUFFIX) and ARCHIVE_RE.fullmatch(n[:-len(SIDECAR_SUFFIX)]))


def prune_remote(store, keep: int) -> int:
    """Keep the newest `keep` confirmed copies (<= 0 keeps all). A pruned
    copy loses its manifest first, so no manifest ever names a missing
    archive. Ciphertext without a manifest (an interrupted upload) is removed
    once a newer copy is confirmed. Objects not named like a backup are never
    touched. Returns the number of confirmed copies removed."""
    if keep <= 0:
        return 0
    names = store.list()
    confirmed = _confirmed_archives(names)
    for archive in confirmed[:-keep]:
        store.delete(archive + SIDECAR_SUFFIX)
        if archive + ENC_SUFFIX in names:
            store.delete(archive + ENC_SUFFIX)
    newest = confirmed[-1] if confirmed else None
    for n in names:
        archive = n[:-len(ENC_SUFFIX)] if n.endswith(ENC_SUFFIX) else None
        if (archive and ARCHIVE_RE.fullmatch(archive) and archive not in confirmed
                and newest and archive < newest):
            store.delete(n)
    return max(0, len(confirmed) - keep)


def push(archive: Path, sidecar: dict, cfg: OffsiteConfig, *, data_dir: Path,
         http=None) -> OffsiteResult:
    """Encrypt `archive`, upload it, then its manifest; confirm both by HEAD.
    Never raises: every failure is a result with a scrubbed reason."""
    if not cfg.target:
        return OffsiteResult(None, False, reason="not configured: BACKUP_OFFSITE_TARGET "
                                                 "is unset")
    try:
        key = encryption_key(cfg)
        store = make_store(cfg, data_dir=data_dir, http=http)
        enc_name = archive.name + ENC_SUFFIX
        side_name = archive.name + SIDECAR_SUFFIX
        with tempfile.TemporaryDirectory(prefix="stockagent-offsite-") as td:
            enc_path = Path(td) / enc_name
            enc = encrypt_file(archive, enc_path, key)
            store.put(enc_name, enc_path, enc["sha256"])
            if store.head(enc_name) != enc["bytes"]:
                raise OffsiteError(f"{enc_name} did not read back at {enc['bytes']} bytes")
            remote = dict(sidecar, encrypted={"alg": "AES-256-GCM", "format": "SABK1", **enc})
            side_path = Path(td) / side_name
            side_path.write_bytes(json.dumps(remote, indent=2, sort_keys=True).encode("utf-8"))
            side = file_digest(side_path)
            store.put(side_name, side_path, side["sha256"])
            if store.head(side_name) != side["bytes"]:
                raise OffsiteError(f"{side_name} did not read back at {side['bytes']} bytes")
        pruned = 0
        try:
            pruned = prune_remote(store, cfg.keep)
        except Exception as exc:
            logger.warning("[backup] off-site prune failed; the new copy is confirmed: %s",
                           scrub(exc, cfg))
        return OffsiteResult(store.kind, True, object=enc_name, pruned=pruned)
    except OffsiteError as exc:
        return OffsiteResult(cfg.target, False, reason=scrub(exc, cfg))
    except Exception as exc:
        return OffsiteResult(cfg.target, False,
                             reason=scrub(f"{type(exc).__name__}: {exc}", cfg))


def fetch(name: str | None, dest: Path, cfg: OffsiteConfig, *, data_dir: Path,
          http=None) -> Path:
    """Download one confirmed copy (the newest when `name` is None) into
    `dest`, check its ciphertext against its manifest and decrypt it. Returns
    the plaintext archive path; its manifest is written beside it."""
    key = encryption_key(cfg)
    store = make_store(cfg, data_dir=data_dir, http=http)
    if name is None:
        confirmed = _confirmed_archives(store.list())
        if not confirmed:
            raise OffsiteError("no confirmed off-site backup found")
        name = confirmed[-1]
    if not ARCHIVE_RE.fullmatch(name):
        raise OffsiteError(f"{name!r} is not a backup archive name")
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    side_path = dest / (name + SIDECAR_SUFFIX)
    store.get(name + SIDECAR_SUFFIX, side_path)
    meta = (json.loads(side_path.read_text(encoding="utf-8")).get("encrypted") or {})
    enc_path = dest / (name + ENC_SUFFIX)
    store.get(name + ENC_SUFFIX, enc_path)
    got = file_digest(enc_path)
    if (got["bytes"], got["sha256"]) != (meta.get("bytes"), meta.get("sha256")):
        raise OffsiteError(f"{name + ENC_SUFFIX} does not match its manifest (corrupt "
                           "or incomplete download)")
    archive = dest / name
    decrypt_file(enc_path, archive, key)
    enc_path.unlink()
    return archive
