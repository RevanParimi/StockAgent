"""AUD-086: OffMarketFetcher and FnOFetcher called NSE() without the required
download_folder arg → constructor raised TypeError, the except branch logged
'nse package unavailable' (mislabel), and off-market + F&O context was
structurally empty (~16×/day in prod)."""
import sys
import types

import pytest


class _StrictNSE:
    """Mimics nse.NSE: download_folder is a REQUIRED positional arg."""
    def __init__(self, download_folder):
        self.download_folder = download_folder


@pytest.fixture()
def strict_nse_module(monkeypatch):
    mod = types.ModuleType("nse")
    mod.NSE = _StrictNSE
    monkeypatch.setitem(sys.modules, "nse", mod)


def test_offmarket_fetcher_constructs_client(strict_nse_module):
    from core.intelligence.rl.stores.offmarket_fetcher import OffMarketFetcher
    f = OffMarketFetcher()
    assert f._nse is not None, "NSE() ctor failed — download_folder not passed (AUD-086)"


def test_fno_fetcher_constructs_client(strict_nse_module):
    from core.intelligence.fno.fetcher import FnOFetcher
    f = FnOFetcher()
    assert f._nse is not None, "NSE() ctor failed — download_folder not passed (AUD-086)"
