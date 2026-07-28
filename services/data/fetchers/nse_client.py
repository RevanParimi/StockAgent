"""Shared NSE client factory with guaranteed temp-dir cleanup (AUD-017).

Every NSE call site created its own `download_folder` via `tempfile.mkdtemp()`,
but `nse.NSE.exit()` only closes the session and unlinks the cookie file — it
never removes that directory. The dirs therefore accumulated for the whole
container lifetime (worst offenders: OffMarketFetcher/FnOFetcher, rebuilt per
ticker). This module centralises client creation and makes cleanup mandatory:

    with nse_session() as nse:          # factory-style, one-shot usage
        rows = nse.listCurrentIPO()

    # long-lived / instance-stored:
    self._nse = make_nse()
    track_for_cleanup(self, self._nse)  # rmtree when the owner is GC'd
    ...
    close_nse(self._nse)                # or clean up explicitly

Each client keeps a private temp dir (no shared cookie file → no races under
`--workers 2`); cleanup removes exactly that dir.
"""
from __future__ import annotations

import contextlib
import logging
import shutil
import tempfile
import weakref
from pathlib import Path

logger = logging.getLogger(__name__)


def _new_nse(download_folder: Path):
    """Thin seam over the nse package so tests can inject a fake (no network)."""
    from nse import NSE
    return NSE(download_folder=download_folder)


def make_nse():
    """An NSE client on a private temp dir. MUST be paired with `close_nse()`
    (or use `nse_session`) — `NSE.exit()` does NOT remove `download_folder`."""
    return _new_nse(Path(tempfile.mkdtemp(prefix="nse-")))


def close_nse(nse) -> None:
    """Close the client's session and remove its temp `download_folder`.

    Idempotent and never raises: safe to call twice, on `None`, or when the
    dir is already gone. rmtree runs even if `exit()` fails.
    """
    if nse is None:
        return
    folder = getattr(nse, "dir", None)
    try:
        nse.exit()
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("[nse_client] exit() failed (non-fatal): %s", exc)
    if folder is not None:
        shutil.rmtree(folder, ignore_errors=True)


@contextlib.contextmanager
def nse_session():
    """Context-managed NSE client with guaranteed temp-dir cleanup."""
    nse = make_nse()
    try:
        yield nse
    finally:
        close_nse(nse)


def track_for_cleanup(owner: object, nse) -> None:
    """Clean up `nse`'s temp dir when `owner` is garbage-collected.

    Safety net for instance-stored clients whose callers don't (and can't
    easily) close them explicitly. The finalizer holds `nse` (not `owner`),
    so it never keeps the owner alive.
    """
    if nse is not None:
        weakref.finalize(owner, close_nse, nse)
