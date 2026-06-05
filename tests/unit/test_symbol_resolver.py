"""
Unit tests for the self-healing yfinance symbol resolver.
Yahoo network calls (_india_candidates / _has_price) are mocked — no real I/O.
"""
import importlib
import json

import pytest

import backend.shared.data.fetchers.symbol_resolver as sr


@pytest.fixture
def fresh_resolver(tmp_path, monkeypatch):
    """Isolate the cache file + in-process state for each test."""
    cache_file = tmp_path / "yf_symbol_cache.json"
    monkeypatch.setattr(sr, "_CACHE_FILE", cache_file)
    monkeypatch.setattr(sr, "_cache", None)
    monkeypatch.setattr(sr, "_session_unresolved", set())
    return sr


# ── Tier 1 / Tier 2 cheap resolution (no network) ──────────────────────────

def test_curated_override_wins(fresh_resolver):
    # TATAMOTORS is a curated override (demerger → TMPV)
    assert fresh_resolver.resolve_yf_symbol("TATAMOTORS") == "TMPV.NS"
    assert fresh_resolver.resolve_yf_symbol("tatamotors") == "TMPV.NS"  # case-insensitive


def test_naive_default(fresh_resolver):
    assert fresh_resolver.resolve_yf_symbol("MARUTI") == "MARUTI.NS"


def test_passthrough_full_symbols(fresh_resolver):
    assert fresh_resolver.resolve_yf_symbol("MARUTI.NS") == "MARUTI.NS"
    assert fresh_resolver.resolve_yf_symbol("^NSEI") == "^NSEI"
    assert fresh_resolver.resolve_yf_symbol("SI=F") == "SI=F"


def test_learned_cache_hit(fresh_resolver):
    fresh_resolver._CACHE_FILE.write_text(json.dumps({"FOOBANK": "FOO.NS"}), encoding="utf-8")
    assert fresh_resolver.resolve_yf_symbol("FOOBANK") == "FOO.NS"


# ── Tier 2 healing (Yahoo mocked) ──────────────────────────────────────────

def test_heal_single_match_persists(fresh_resolver, monkeypatch):
    # OLDBANK is NOT a curated override → must go through search + persist.
    monkeypatch.setattr(sr, "_india_candidates", lambda q: ["NEWBANK.NS"])
    monkeypatch.setattr(sr, "_has_price", lambda s: s == "NEWBANK.NS")

    healed = fresh_resolver.heal_symbol("OLDBANK")
    assert healed == "NEWBANK.NS"
    # persisted → next cheap resolve hits cache, no network
    assert fresh_resolver.resolve_yf_symbol("OLDBANK") == "NEWBANK.NS"
    on_disk = json.loads(fresh_resolver._CACHE_FILE.read_text(encoding="utf-8"))
    assert on_disk["OLDBANK"] == "NEWBANK.NS"


def test_heal_ambiguous_demerger_refuses(fresh_resolver, monkeypatch):
    # Two valid matches (a demerger) → refuse, do NOT cache, return None
    monkeypatch.setattr(sr, "_india_candidates", lambda q: ["TMCV.NS", "TMPV.NS"])
    monkeypatch.setattr(sr, "_has_price", lambda s: True)

    assert fresh_resolver.heal_symbol("SOMESPLIT") is None
    assert not fresh_resolver._CACHE_FILE.exists() or \
        "SOMESPLIT" not in json.loads(fresh_resolver._CACHE_FILE.read_text(encoding="utf-8"))


def test_heal_dual_listing_not_ambiguous(fresh_resolver, monkeypatch):
    # Same company on NSE + BSE is ONE company → prefer .NS, not "ambiguous".
    monkeypatch.setattr(sr, "_india_candidates", lambda q: ["NEWCO.NS", "NEWCO.BO"])
    monkeypatch.setattr(sr, "_has_price", lambda s: True)
    assert fresh_resolver.heal_symbol("OLDCO") == "NEWCO.NS"


def test_heal_falls_back_to_bse(fresh_resolver, monkeypatch):
    # No usable .NS, but a valid .BO → use BSE.
    monkeypatch.setattr(sr, "_india_candidates", lambda q: ["ONLYBSE.BO"])
    monkeypatch.setattr(sr, "_has_price", lambda s: s == "ONLYBSE.BO")
    assert fresh_resolver.heal_symbol("ONLYBSE") == "ONLYBSE.BO"


def test_heal_yahoo_gap_returns_none(fresh_resolver, monkeypatch):
    # No candidates at all (genuine Yahoo gap, e.g. LTIM) → None, not cached
    monkeypatch.setattr(sr, "_india_candidates", lambda q: [])
    monkeypatch.setattr(sr, "_has_price", lambda s: False)

    assert fresh_resolver.heal_symbol("LTIM") is None


def test_heal_skips_naive_candidate(fresh_resolver, monkeypatch):
    # If search only returns the naive symbol that already failed → no valid pick
    monkeypatch.setattr(sr, "_india_candidates", lambda q: ["DEADTKR.NS"])
    monkeypatch.setattr(sr, "_has_price", lambda s: True)
    assert fresh_resolver.heal_symbol("DEADTKR") is None  # naive filtered out → 0 valid


def test_heal_session_memo_prevents_repeat(fresh_resolver, monkeypatch):
    calls = {"n": 0}

    def _cand(q):
        calls["n"] += 1
        return []

    monkeypatch.setattr(sr, "_india_candidates", _cand)
    monkeypatch.setattr(sr, "_has_price", lambda s: False)

    assert fresh_resolver.heal_symbol("GHOST") is None
    assert fresh_resolver.heal_symbol("GHOST") is None
    assert calls["n"] == 1  # second call short-circuited by _session_unresolved
