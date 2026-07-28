"""AUD-017: NSE client helper removes its temp download_folder.

NSE.exit() closes the session + unlinks the cookie file but NEVER removes
`download_folder` — so every NSE(download_folder=mkdtemp()) orphaned its temp
dir for the container's lifetime. These tests pin the cleanup contract.
"""
import tempfile
from pathlib import Path

import services.data.fetchers.nse_client as nc


class _FakeNSE:
    """Mimics the nse.NSE surface the helper relies on: `.dir` + `.exit()`.

    Deliberately does NOT remove its dir on exit() — reproducing the real
    package behaviour the helper must compensate for.
    """

    def __init__(self, download_folder):
        self.dir = Path(download_folder)
        self.exited = False

    def exit(self):
        self.exited = True  # NSE.exit does not rmtree self.dir


def test_close_nse_exits_and_removes_download_dir():
    d = Path(tempfile.mkdtemp())
    nse = _FakeNSE(d)
    assert d.exists()
    nc.close_nse(nse)
    assert nse.exited is True
    assert not d.exists()


def test_close_nse_tolerates_none_and_missing_dir():
    nc.close_nse(None)  # must not raise
    d = Path(tempfile.mkdtemp())
    nse = _FakeNSE(d)
    d.rmdir()  # dir already gone
    nc.close_nse(nse)  # still must not raise
    assert nse.exited is True


def test_close_nse_removes_dir_even_if_exit_raises():
    d = Path(tempfile.mkdtemp())
    nse = _FakeNSE(d)

    def _boom():
        raise RuntimeError("session already closed")

    nse.exit = _boom
    nc.close_nse(nse)
    assert not d.exists()  # cleanup must not depend on exit() succeeding


def test_make_nse_uses_a_fresh_temp_dir(monkeypatch):
    seen = {}

    def _fake_ctor(folder):
        seen["folder"] = Path(folder)
        return _FakeNSE(folder)

    monkeypatch.setattr(nc, "_new_nse", _fake_ctor)
    nse = nc.make_nse()
    assert seen["folder"].exists() and nse.dir == seen["folder"]
    nc.close_nse(nse)


def test_nse_session_creates_then_cleans_up(monkeypatch):
    created = {}

    def _fake_ctor(folder):
        created["folder"] = Path(folder)
        return _FakeNSE(folder)

    monkeypatch.setattr(nc, "_new_nse", _fake_ctor)
    with nc.nse_session() as nse:
        assert created["folder"].exists()
        assert nse.dir == created["folder"]
    assert not created["folder"].exists()  # cleaned on context exit


def test_offmarket_fetcher_close_removes_tempdir(monkeypatch):
    import nse as nse_pkg
    monkeypatch.setattr(nse_pkg, "NSE", _FakeNSE)
    from core.intelligence.rl.stores.offmarket_fetcher import OffMarketFetcher
    f = OffMarketFetcher()
    d = f._nse.dir
    assert d.exists()
    f.close()
    assert not d.exists()


def test_fno_fetcher_close_removes_tempdir(monkeypatch):
    import nse as nse_pkg
    monkeypatch.setattr(nse_pkg, "NSE", _FakeNSE)
    from core.intelligence.fno.fetcher import FnOFetcher
    f = FnOFetcher()
    d = f._nse.dir
    assert d.exists()
    f.close()
    assert not d.exists()
