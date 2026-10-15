"""Compass Phase C â€” index constituent diff -> inclusion/exclusion alerts."""
import json
from datetime import date
from unittest.mock import patch

import core.delivery.index_watch as iw


class _FakeNSE:
    def __init__(self, symbols_by_index):
        self._by_index = symbols_by_index

    def listEquityStocksByIndex(self, index="NIFTY 50"):
        return {"data": [{"symbol": index}] +      # index summary row (filtered)
                        [{"symbol": s} for s in self._by_index[index]]}

    def exit(self):
        pass


def test_first_snapshot_never_alerts(tmp_path, monkeypatch):
    cache = str(tmp_path / "idx.json")
    monkeypatch.setattr(iw.settings, "DELIVERY_INDEX_WATCH", ["NIFTY 50"])
    monkeypatch.setattr(iw, "_make_nse_client",
                        lambda: _FakeNSE({"NIFTY 50": ["AAA", "BBB"]}))
    monkeypatch.setattr(iw, "_shelf_symbols", lambda: {"AAA"})
    monkeypatch.setattr(iw, "_account_symbols", lambda: {"u1": {"BBB"}})
    with patch.object(iw, "emit_alerts_broadcast") as m, \
            patch.object(iw, "emit_alerts") as own:
        out = iw.run_index_watch(on=date(2026, 7, 5), cache_path=cache)
    assert out["events"] == 0 and not m.called and not own.called
    assert set(json.loads(open(cache).read())["NIFTY 50"]["symbols"]) == {"AAA", "BBB"}


def test_diff_alerts_only_watched_symbols(tmp_path, monkeypatch):
    cache = str(tmp_path / "idx.json")
    (tmp_path / "idx.json").write_text(json.dumps(
        {"NIFTY 50": {"fetched_at": "old", "symbols": ["AAA", "BBB"]}}), encoding="utf-8")
    monkeypatch.setattr(iw.settings, "DELIVERY_INDEX_WATCH", ["NIFTY 50"])
    monkeypatch.setattr(iw, "_make_nse_client",
                        lambda: _FakeNSE({"NIFTY 50": ["AAA", "CCC", "DDD"]}))
    monkeypatch.setattr(iw, "_shelf_symbols", lambda: {"BBB"})
    monkeypatch.setattr(iw, "_account_symbols", lambda: {"u1": {"CCC"}})
    with patch.object(iw, "emit_alerts_broadcast") as m, \
            patch.object(iw, "emit_alerts") as own:
        out = iw.run_index_watch(on=date(2026, 7, 5), cache_path=cache)
    assert out["events"] == 2                       # CCC included, BBB excluded (DDD unwatched)
    assert {(e.symbol, e.kind) for e in m.call_args.args[0]} == {("BBB", "index_exclusion")}
    assert {(e.symbol, e.kind) for e in own.call_args.args[0]} == {("CCC", "index_inclusion")}
    assert own.call_args.kwargs["user_id"] == "u1"


def test_fetch_failure_keeps_stale_and_no_alerts(tmp_path, monkeypatch):
    cache = str(tmp_path / "idx.json")
    (tmp_path / "idx.json").write_text(json.dumps(
        {"NIFTY 50": {"fetched_at": "old", "symbols": ["AAA"]}}), encoding="utf-8")
    monkeypatch.setattr(iw.settings, "DELIVERY_INDEX_WATCH", ["NIFTY 50"])

    def _boom():
        raise RuntimeError("NSE down")
    monkeypatch.setattr(iw, "_make_nse_client", _boom)
    monkeypatch.setattr(iw, "_shelf_symbols", lambda: {"AAA"})
    monkeypatch.setattr(iw, "_account_symbols", lambda: {"u1": {"AAA"}})
    with patch.object(iw, "emit_alerts_broadcast") as m, \
            patch.object(iw, "emit_alerts") as own:
        out = iw.run_index_watch(on=date(2026, 7, 5), cache_path=cache)
    assert out["events"] == 0 and "NIFTY 50" in out["degraded"] and not m.called
    assert not own.called
    assert json.loads(open(cache).read())["NIFTY 50"]["symbols"] == ["AAA"]
