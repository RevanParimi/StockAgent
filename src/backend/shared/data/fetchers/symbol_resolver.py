"""
src/backend/shared/data/fetchers/symbol_resolver.py
===================================================
Self-healing NSE ticker -> yfinance symbol resolution.

Two tiers, cheapest first. The happy path makes ZERO network calls:

  1. Curated overrides (settings.YF_SYMBOL_OVERRIDES) — authoritative, for the
     handful of AMBIGUOUS demergers a machine cannot disambiguate (e.g. Tata
     Motors -> TMCV vs TMPV). A human picks the entity once.
  2. Learned cache (data/yf_symbol_cache.json) — populated on demand for the
     long tail of renames / typos / Yahoo code quirks (CANARABANK -> CANBK).

`resolve_yf_symbol(ticker)` is CHEAP: override -> cache -> naive "{TICKER}.NS".
It never touches the network, so it is safe to call on every price fetch.

`heal_symbol(ticker, company_name)` is the EXPENSIVE lazy step: callers invoke
it ONLY after a naive fetch came back empty. It searches Yahoo, validates that a
candidate actually returns price data, persists the winner, and returns it.

Healing deliberately refuses to guess in two cases:
  * >1 valid Yahoo match  -> a demerger; logs a request for a curated override.
  * 0 matches             -> a genuine Yahoo gap (e.g. LTIM); returns None and is
                             NOT cached, so we retry later when Yahoo restores it.
"""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path

from core.config import settings

logger = logging.getLogger(__name__)

_CACHE_FILE = Path("data/yf_symbol_cache.json")
_LOCK = threading.Lock()
_cache: dict[str, str] | None = None     # in-process memo of the JSON file
_session_unresolved: set[str] = set()    # tickers we already failed to heal this run

# ---------------------------------------------------------------------------
# Ticker -> company name (curated overrides + learned cache)
# ---------------------------------------------------------------------------

_COMPANY_NAME_CACHE_FILE = Path("data/company_names.json")
_COMPANY_NAME_LOCK = threading.Lock()
_company_name_cache: dict[str, str] | None = None  # in-process memo of the JSON file

# Curated seed — confidently-known long names for the managed tickers across
# the four active sectors (automobile, banking_bfsi, it_sector,
# renewable_energy). Anything not listed here is learned on first live
# yfinance hit via learn_company_name().
COMPANY_NAME_OVERRIDES: dict[str, str] = {
    # automobile
    "MARUTI":     "Maruti Suzuki India Limited",
    "TATAMOTORS": "Tata Motors Limited",
    "M&M":        "Mahindra & Mahindra Limited",
    "HEROMOTOCO": "Hero MotoCorp Limited",
    "BAJAJ-AUTO": "Bajaj Auto Limited",
    "EICHERMOT":  "Eicher Motors Limited",
    "TVSMOTORS":  "TVS Motor Company Limited",
    "ASHOKLEY":   "Ashok Leyland Limited",
    # banking_bfsi
    "HDFCBANK":   "HDFC Bank Limited",
    "ICICIBANK":  "ICICI Bank Limited",
    "SBIN":       "State Bank of India",
    "KOTAKBANK":  "Kotak Mahindra Bank Limited",
    "AXISBANK":   "Axis Bank Limited",
    "INDUSINDBK": "IndusInd Bank Limited",
    "BANKBARODA": "Bank of Baroda",
    # it_sector
    "TCS":        "Tata Consultancy Services Limited",
    "INFY":       "Infosys Limited",
    "WIPRO":      "Wipro Limited",
    "HCLTECH":    "HCL Technologies Limited",
    "TECHM":      "Tech Mahindra Limited",
    "LTIM":       "LTIMindtree Limited",
    "COFORGE":    "Coforge Limited",
    # renewable_energy
    "ADANIGREEN": "Adani Green Energy Limited",
    "TATAPOWER":  "Tata Power Company Limited",
    "TORNTPOWER": "Torrent Power Limited",
    "CESC":       "CESC Limited",
    "SJVN":       "SJVN Limited",
    "NHPC":       "NHPC Limited",
}


# ---------------------------------------------------------------------------
# Cache (persistent JSON + in-process memo)
# ---------------------------------------------------------------------------

def _norm(ticker: str) -> str:
    return ticker.strip().upper()


def _symbol_root(yf_symbol: str) -> str:
    """Strip a .NS/.BO exchange suffix and normalize case, e.g. 'jaybarmaru.bo' -> 'JAYBARMARU'."""
    s = _norm(yf_symbol)
    for suffix in (".NS", ".BO"):
        if s.endswith(suffix):
            return s[: -len(suffix)]
    return s


def _is_known_indian_ticker(ticker: str) -> bool:
    """
    True if `ticker` is a known Indian listing (present in
    backend.sectors.registry.TICKER_SECTOR). Lazy import; any failure
    (import error, missing attribute, etc.) degrades to "unknown ticker"
    (False) — never raises.
    """
    try:
        from backend.sectors.registry import TICKER_SECTOR
        return _norm(ticker) in {_norm(k) for k in TICKER_SECTOR}
    except Exception as exc:
        logger.debug("[symbol_resolver] TICKER_SECTOR lookup failed (treating as unknown): %s", exc)
        return False


def _is_safe_mapping(ticker: str, yf_symbol: str) -> bool:
    """
    Guard against learning a wrong-company mapping.

    For KNOWN Indian tickers (present in TICKER_SECTOR), the learned
    symbol's root MUST match the ticker itself (case/suffix-insensitive) —
    e.g. MARUTI -> MARUTI.NS or MARUTI.BO is fine, MARUTI -> JAYBARMARU.NS
    is not.

    For UNKNOWN tickers, any root is allowed — that's the whole point of
    the fuzzy-search self-heal (e.g. ATHER -> ATHERENERG.NS).
    """
    if not _is_known_indian_ticker(ticker):
        return True
    return _symbol_root(yf_symbol) == _norm(ticker)


def _load_cache() -> dict[str, str]:
    global _cache
    if _cache is not None:
        return _cache
    try:
        if _CACHE_FILE.exists():
            # utf-8-sig: tolerate a BOM from hand-edits/PowerShell on Windows
            raw = json.loads(_CACHE_FILE.read_text("utf-8-sig"))
            _cache = {str(k).upper(): str(v) for k, v in raw.items()}
        else:
            _cache = {}
    except Exception as exc:
        logger.warning("[symbol_resolver] cache load failed: %s", exc)
        _cache = {}
    return _cache


def _remove_from_cache_file(ticker: str) -> None:
    """Delete `ticker` from the in-memory memo AND the on-disk cache file."""
    with _LOCK:
        cache = _load_cache()
        if ticker not in cache:
            return
        del cache[ticker]
        try:
            _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            _CACHE_FILE.write_text(
                json.dumps(cache, indent=2, sort_keys=True), encoding="utf-8"
            )
        except Exception as exc:
            logger.warning("[symbol_resolver] cache prune-write failed: %s", exc)


def _persist(ticker: str, yf_symbol: str) -> None:
    t = _norm(ticker)
    if not _is_safe_mapping(t, yf_symbol):
        logger.warning(
            "[symbol_resolver] REFUSING to learn %s -> %s: %s is a known Indian "
            "ticker and the symbol root (%s) does not match — possible wrong-company "
            "mapping, not cached",
            t, yf_symbol, t, _symbol_root(yf_symbol),
        )
        return
    with _LOCK:
        cache = _load_cache()
        cache[t] = yf_symbol                # mutates the memo in place
        try:
            _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            _CACHE_FILE.write_text(
                json.dumps(cache, indent=2, sort_keys=True), encoding="utf-8"
            )
            logger.info("[symbol_resolver] learned %s -> %s (cached)", t, yf_symbol)
        except Exception as exc:
            logger.warning("[symbol_resolver] cache write failed: %s", exc)


# ---------------------------------------------------------------------------
# Ticker -> company name (curated overrides + learned cache)
# ---------------------------------------------------------------------------

def _load_company_name_cache() -> dict[str, str]:
    global _company_name_cache
    if _company_name_cache is not None:
        return _company_name_cache
    try:
        if _COMPANY_NAME_CACHE_FILE.exists():
            # utf-8-sig: tolerate a BOM from hand-edits/PowerShell on Windows
            raw = json.loads(_COMPANY_NAME_CACHE_FILE.read_text("utf-8-sig"))
            _company_name_cache = {str(k).upper(): str(v) for k, v in raw.items()}
        else:
            _company_name_cache = {}
    except Exception as exc:
        logger.warning("[symbol_resolver] company-name cache load failed: %s", exc)
        _company_name_cache = {}
    return _company_name_cache


def resolve_company_name(ticker: str) -> str | None:
    """
    Curated override -> learned cache -> None (caller fetches live + learns).

    Cheap, zero-network. Never raises.
    """
    t = _norm(ticker)
    override = COMPANY_NAME_OVERRIDES.get(t)
    if override:
        return override
    return _load_company_name_cache().get(t)


def learn_company_name(ticker: str, name: str) -> None:
    """Persist a discovered ticker -> company-name mapping. Never raises."""
    t = _norm(ticker)
    with _COMPANY_NAME_LOCK:
        cache = _load_company_name_cache()
        cache[t] = name  # mutates the memo in place
        try:
            _COMPANY_NAME_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            _COMPANY_NAME_CACHE_FILE.write_text(
                json.dumps(cache, indent=2, sort_keys=True), encoding="utf-8"
            )
            logger.info("[symbol_resolver] learned company name %s -> %s (cached)", t, name)
        except Exception as exc:
            logger.warning("[symbol_resolver] company-name cache write failed: %s", exc)


# ---------------------------------------------------------------------------
# Tier 1 + 2 — cheap resolution (no network)
# ---------------------------------------------------------------------------

def resolve_yf_symbol(ticker: str) -> str:
    """
    Cheap, zero-network resolution: curated override -> learned cache ->
    naive "{TICKER}.NS". Safe to call on every price fetch.
    """
    t = _norm(ticker)
    # Already a full yfinance symbol (MARUTI.NS, ^NSEI, SI=F, BRK-B) — pass through.
    if t.endswith(settings.YFINANCE_SUFFIX) or t.endswith(".BO") or "=" in t or t.startswith("^"):
        return t
    override = settings.YF_SYMBOL_OVERRIDES.get(t)
    if override:
        return override
    cached = _load_cache().get(t)
    if cached:
        if _is_safe_mapping(t, cached):
            return cached
        # Poisoned entry from before the guard existed (e.g. an old Railway
        # volume) — prune it on read so production self-heals, and fall
        # through to the naive symbol below.
        logger.warning(
            "[symbol_resolver] pruning poisoned cache entry %s -> %s "
            "(wrong-company mapping for a known Indian ticker)",
            t, cached,
        )
        _remove_from_cache_file(t)
    return f"{t}{settings.YFINANCE_SUFFIX}"


# ---------------------------------------------------------------------------
# Tier 2 healing — expensive, lazy (only on a real fetch miss)
# ---------------------------------------------------------------------------

def _has_price(yf_symbol: str) -> bool:
    """True if the symbol returns any recent price data."""
    try:
        import yfinance as yf
        h = yf.Ticker(yf_symbol).history(period="5d", auto_adjust=True)
        return h is not None and not h.empty
    except Exception:
        return False


def _india_candidates(query: str) -> list[str]:
    """India-preferred (.NS then .BO) symbol candidates from Yahoo search."""
    try:
        import yfinance as yf
        res = yf.Search(query, max_results=8, news_count=0)
        quotes = getattr(res, "quotes", []) or []
    except Exception:
        return []
    ns = [str(q.get("symbol")) for q in quotes if str(q.get("symbol", "")).endswith(".NS")]
    bo = [str(q.get("symbol")) for q in quotes if str(q.get("symbol", "")).endswith(".BO")]
    seen: set[str] = set()
    out: list[str] = []
    for s in ns + bo:
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def heal_symbol(ticker: str, company_name: str | None = None) -> str | None:
    """
    Expensive lazy self-heal — call ONLY after a naive fetch returned empty.

    Searches Yahoo, validates a candidate actually has price data, caches and
    returns the winner. Returns None when nothing is found (Yahoo gap) or when
    more than one candidate is valid (demerger -> needs a curated override).
    """
    t = _norm(ticker)
    if t in _session_unresolved:
        return None
    # Someone may have resolved it since (override added, or healed concurrently).
    if t in settings.YF_SYMBOL_OVERRIDES:
        return settings.YF_SYMBOL_OVERRIDES[t]
    cached = _load_cache().get(t)
    if cached:
        return cached

    naive = f"{t}{settings.YFINANCE_SUFFIX}"
    query = (company_name or t).replace(".NS", "").replace(".BO", "")
    candidates = [c for c in _india_candidates(query) if c != naive]

    # Evaluate NSE first, then BSE. A name dual-listed on both exchanges
    # (SUZLON.NS + SUZLON.BO) is ONE company, not ambiguous — so we tier by
    # exchange and only flag ambiguity when a single exchange yields several
    # DIFFERENT valid symbols (a real demerger, e.g. NIITLTD.NS + NIITMTS.NS).
    for tier in ([c for c in candidates if c.endswith(".NS")],
                 [c for c in candidates if c.endswith(".BO")]):
        valid = [c for c in tier[:5] if _has_price(c)]
        if len(valid) == 1:
            if not _is_safe_mapping(t, valid[0]):
                logger.warning(
                    "[symbol_resolver] refusing fuzzy match %s -> %s for known Indian "
                    "ticker %s (wrong-company root mismatch)",
                    t, valid[0], t,
                )
                _session_unresolved.add(t)
                return None
            _persist(t, valid[0])
            return valid[0]
        if len(valid) > 1:
            logger.warning(
                "[symbol_resolver] %s is AMBIGUOUS (%s) — add a curated entry to "
                "settings.YF_SYMBOL_OVERRIDES to pick the intended entity",
                t, ", ".join(valid),
            )
            _session_unresolved.add(t)
            return None

    logger.info("[symbol_resolver] no working Yahoo symbol for %s (Yahoo gap)", t)
    _session_unresolved.add(t)
    return None
