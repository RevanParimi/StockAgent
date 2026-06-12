"""
Unit tests for the learned-symbol-cache guard against wrong-company mappings.

Incident: data/yf_symbol_cache.json contained {"MARUTI": "JAYBARMARU.NS"} —
the self-healing learn path learned "Jay Bharat Maruti" (a different,
~Rs 131 company) as the symbol for MARUTI (~Rs 13,000, Maruti Suzuki).

The guard:
  - REJECTS learning a mapping whose symbol ROOT (part before .NS/.BO)
    differs from the ticker being learned, WHENEVER the ticker is a known
    Indian listing (present in backend.sectors.registry.TICKER_SECTOR).
  - For unknown tickers, fuzzy learning stays allowed (that is the feature).
  - On READ, a poisoned cache entry that violates the guard is pruned from
    the file and resolution falls through to the naive "{TICKER}.NS" symbol
    — so a production volume self-heals on first read after deploy.
  - Comparison is case- and exchange-suffix-insensitive.
  - If the TICKER_SECTOR import fails, the guard degrades to "unknown
    ticker" semantics (allow), and never raises.
"""
import importlib
import json

import pytest

import backend.shared.data.fetchers.symbol_resolver as sr


@pytest.fixture
def fresh_resolver(tmp_path, monkeypatch):
    """Isolate the cache file + in-process state for each test."""
    cache_file = tmp_path / "yf_symbol_cache.json"
    company_file = tmp_path / "company_names.json"
    monkeypatch.setattr(sr, "_CACHE_FILE", cache_file)
    monkeypatch.setattr(sr, "_cache", None)
    monkeypatch.setattr(sr, "_session_unresolved", set())
    monkeypatch.setattr(sr, "_COMPANY_NAME_CACHE_FILE", company_file)
    monkeypatch.setattr(sr, "_company_name_cache", None)
    return sr


# ── learn() guard: known Indian tickers ────────────────────────────────────

def test_learn_rejects_wrong_company_root_for_known_ticker(fresh_resolver):
    # MARUTI is in TICKER_SECTOR; JAYBARMARU.NS has a different root → reject.
    fresh_resolver._persist("MARUTI", "JAYBARMARU.NS")

    assert not fresh_resolver._CACHE_FILE.exists() or \
        "MARUTI" not in json.loads(fresh_resolver._CACHE_FILE.read_text(encoding="utf-8"))
    assert fresh_resolver.resolve_yf_symbol("MARUTI") == "MARUTI.NS"


def test_learn_accepts_matching_root_for_known_ticker(fresh_resolver):
    # MARUTI -> MARUTI.NS: same root → accepted.
    fresh_resolver._persist("MARUTI", "MARUTI.NS")

    on_disk = json.loads(fresh_resolver._CACHE_FILE.read_text(encoding="utf-8"))
    assert on_disk["MARUTI"] == "MARUTI.NS"
    assert fresh_resolver.resolve_yf_symbol("MARUTI") == "MARUTI.NS"


def test_learn_allows_fuzzy_for_unknown_ticker(fresh_resolver):
    # ATHER is not a known Indian listing in TICKER_SECTOR → fuzzy learning
    # is the whole point of the self-heal feature, so it must be allowed.
    fresh_resolver._persist("ATHER", "ATHERENERG.NS")

    on_disk = json.loads(fresh_resolver._CACHE_FILE.read_text(encoding="utf-8"))
    assert on_disk["ATHER"] == "ATHERENERG.NS"
    assert fresh_resolver.resolve_yf_symbol("ATHER") == "ATHERENERG.NS"


# ── case / exchange-suffix insensitivity ───────────────────────────────────

def test_learn_rejection_is_case_and_suffix_insensitive(fresh_resolver):
    # lowercase ticker, .BO suffix on the mismatched candidate — still rejected.
    fresh_resolver._persist("maruti", "JAYBARMARU.BO")

    assert not fresh_resolver._CACHE_FILE.exists() or \
        "MARUTI" not in json.loads(fresh_resolver._CACHE_FILE.read_text(encoding="utf-8"))
    assert fresh_resolver.resolve_yf_symbol("MARUTI") == "MARUTI.NS"


# ── prune-on-read: self-heal an already-poisoned cache ─────────────────────

def test_resolve_prunes_poisoned_entry_and_falls_back_to_naive(fresh_resolver):
    # Simulate the real incident: a poisoned cache file written before the
    # guard existed (e.g. the Railway volume).
    fresh_resolver._CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    fresh_resolver._CACHE_FILE.write_text(
        json.dumps({"MARUTI": "JAYBARMARU.NS"}), encoding="utf-8"
    )
    # Force a fresh load from disk.
    fresh_resolver._cache = None

    result = fresh_resolver.resolve_yf_symbol("MARUTI")

    assert result == "MARUTI.NS"
    on_disk = json.loads(fresh_resolver._CACHE_FILE.read_text(encoding="utf-8"))
    assert "MARUTI" not in on_disk


def test_resolve_keeps_valid_learned_entry(fresh_resolver):
    # A legitimately-learned entry for an unknown ticker must survive prune-on-read.
    fresh_resolver._CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    fresh_resolver._CACHE_FILE.write_text(
        json.dumps({"ATHER": "ATHERENERG.NS"}), encoding="utf-8"
    )
    fresh_resolver._cache = None

    assert fresh_resolver.resolve_yf_symbol("ATHER") == "ATHERENERG.NS"
    on_disk = json.loads(fresh_resolver._CACHE_FILE.read_text(encoding="utf-8"))
    assert on_disk["ATHER"] == "ATHERENERG.NS"


def test_resolve_keeps_valid_same_root_entry_for_known_ticker(fresh_resolver):
    # A known ticker legitimately re-mapped to a different exchange/suffix of
    # the SAME root (e.g. MARUTI -> MARUTI.BO) must survive prune-on-read.
    fresh_resolver._CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    fresh_resolver._CACHE_FILE.write_text(
        json.dumps({"MARUTI": "MARUTI.BO"}), encoding="utf-8"
    )
    fresh_resolver._cache = None

    assert fresh_resolver.resolve_yf_symbol("MARUTI") == "MARUTI.BO"
    on_disk = json.loads(fresh_resolver._CACHE_FILE.read_text(encoding="utf-8"))
    assert on_disk["MARUTI"] == "MARUTI.BO"


# ── registry import failure degrades to "unknown ticker" (allow) ───────────

def test_registry_import_failure_degrades_to_allow(fresh_resolver, monkeypatch):
    import builtins

    real_import = builtins.__import__

    def _broken_import(name, *args, **kwargs):
        if name == "backend.sectors.registry" or name.endswith("sectors.registry"):
            raise ImportError("registry unavailable")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _broken_import)

    # Should not raise, and should behave like "unknown ticker" → fuzzy allowed.
    fresh_resolver._persist("MARUTI", "JAYBARMARU.NS")

    on_disk = json.loads(fresh_resolver._CACHE_FILE.read_text(encoding="utf-8"))
    assert on_disk["MARUTI"] == "JAYBARMARU.NS"


# ── heal_symbol() routes through the guarded persist ───────────────────────

def test_heal_symbol_rejects_wrong_company_for_known_ticker(fresh_resolver, monkeypatch):
    # Reproduce the actual incident path: heal_symbol("MARUTI") finds
    # JAYBARMARU.NS as the sole valid candidate during a transient yfinance
    # error. MARUTI is a known Indian ticker → the guard must refuse to
    # persist this, and heal_symbol must not return the bad symbol either.
    monkeypatch.setattr(fresh_resolver, "_india_candidates", lambda q: ["JAYBARMARU.NS"])
    monkeypatch.setattr(fresh_resolver, "_has_price", lambda s: True)

    healed = fresh_resolver.heal_symbol("MARUTI")

    assert healed is None
    assert not fresh_resolver._CACHE_FILE.exists() or \
        "MARUTI" not in json.loads(fresh_resolver._CACHE_FILE.read_text(encoding="utf-8"))


# ── learn_company_name(): _yf_info cannot receive a mismatched symbol ──────

def test_company_name_lookup_never_uses_a_mismatched_symbol():
    """
    Documents why learn_company_name() needs no separate guard for the
    MARUTI/JAYBARMARU incident.

    base_orchestrator._yf_info(ticker) builds the yfinance symbol ONLY from
    settings.YF_SYMBOL_OVERRIDES.get(ticker.upper()) (a curated, trusted
    override) or the naive "{ticker}{YFINANCE_SUFFIX}" — it NEVER consults
    the learned yf_symbol_cache and never receives a fuzzy-search result.
    So _company_name_for() can never call learn_company_name(ticker, name)
    with a name sourced from a different company's symbol; the MARUTI ->
    JAYBARMARU class of bug cannot reach learn_company_name via this path.
    """
    import inspect

    from backend.shared.pipeline.base_orchestrator import BaseSectorOrchestrator

    src = inspect.getsource(BaseSectorOrchestrator._yf_info)
    assert "YF_SYMBOL_OVERRIDES" in src
    assert "_load_cache" not in src
    assert "yf_symbol_cache" not in src
