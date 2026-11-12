"""
services/data/context/peers.py
==============================
SA-044: the companies a stock's valuation is compared with.

One rule for every graph:

- The stock's industry is Yahoo Finance's classification (FIX-011's one
  industry source).
- The candidates are the symbols the app knows: the sector registry's ticker
  map, the native sectors' ticker lists, the managed tickers and the active
  shelf ideas. A candidate whose identity is not resolved (SA-008: the
  quarantined TATAMOTORS) is left out, and two app tickers for one listing
  count once.
- The peers are the candidates in exactly the stock's industry, nearest
  market cap first, at most `peers.count` (5). Nearness is the ratio of the
  two caps, so a 10,000 Cr company is as near to 5,000 Cr as to 20,000 Cr.
  Candidates without a known cap come after those with one; ties go by symbol.
- With fewer than `peers.minimum` (3) such candidates there are no peers:
  the bundle says `peers unavailable` and why. Another industry's list is
  never borrowed.

Example: SUNPHARMA (Yahoo industry "Drug Manufacturers - Specialty &
Generic") with CIPLA, DRREDDY, LUPIN and ZYDUSLIFE in that industry is
compared with those four, nearest cap first. TATASTEEL ("Steel") with one
other steel maker among the known symbols gets `peers unavailable`.

Industry and market cap come from one yfinance `.info` call per listing and
are kept in data/peer_profiles.json for `peers.cache_days` days. A build looks
up at most `peers.max_lookups` listings that are missing or older than that:
the stock itself first, then missing before old, and its registry sector's
members first within each. It stops after three failed lookups in a row. An
old profile is used until it is refreshed. Once the known symbols are
profiled, choosing peers makes no network call.
"""
from __future__ import annotations

import importlib
import json
import logging
import math
import threading
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable, Iterable

logger = logging.getLogger(__name__)

RULE = "same_industry_nearest_market_cap"
# Relative, like data/yf_symbol_cache.json: the Railway volume layout under /app.
PROFILE_PATH = Path("data/peer_profiles.json")
FAILURES_BEFORE_STOP = 3
_NATIVE_SETTINGS = (
    "backend.sectors.automobile.config.settings",
    "backend.sectors.banking_bfsi.config.settings",
    "backend.sectors.it_sector.config.settings",
    "backend.sectors.renewable_energy.config.settings",
)
# One build fills the file at a time; parallel analyses wait, then read it.
_LOCK = threading.Lock()


def _cfg_int(key: str, fallback: int) -> int:
    try:
        from backend.shared.config.settings.loader import cfg
        return int(cfg(key, fallback=fallback))
    except Exception as exc:
        logger.debug("[peers] %s unreadable, using %d: %s", key, fallback, exc)
        return fallback


def peer_count() -> int:
    return _cfg_int("peers.count", 5)


def peer_minimum() -> int:
    return _cfg_int("peers.minimum", 3)


def cache_days() -> int:
    return _cfg_int("peers.cache_days", 30)


def max_lookups() -> int:
    return _cfg_int("peers.max_lookups", 25)


@dataclass(frozen=True)
class PeerChoice:
    """The peers one valuation compares with, and how they were chosen."""

    ticker: str
    symbols: tuple[str, ...]      # app tickers, nearest market cap first; () = none
    industry: str                 # the stock's Yahoo industry ("" when unknown)
    reason: str | None = None     # why there are none; None when chosen

    @property
    def available(self) -> bool:
        return bool(self.symbols)

    def note(self) -> str:
        """The selection as the bundle text and the health record state it."""
        if self.symbols:
            return (f'peers: same Yahoo industry "{self.industry}", nearest market cap first '
                    f'({len(self.symbols)}): {", ".join(self.symbols)}')
        return f"peers unavailable: {self.reason or 'none chosen'}"


# ---------------------------------------------------------------------------
# The known symbols
# ---------------------------------------------------------------------------

def known_symbols() -> list[str]:
    """Every symbol the app knows, upper case, sorted, once each. A source
    that cannot be read adds nothing; the rest still count."""
    found: set[str] = set()
    try:
        from backend.sectors.registry import TICKER_SECTOR
        found.update(TICKER_SECTOR)
    except Exception as exc:
        logger.debug("[peers] registry ticker map unreadable: %s", exc)
    for module_path in _NATIVE_SETTINGS:
        try:
            module = importlib.import_module(module_path)
            found.update(getattr(module, "TICKERS", None) or [])
            found.update(getattr(module, "PEER_TICKERS", None) or [])
        except Exception as exc:
            logger.debug("[peers] %s unreadable: %s", module_path, exc)
    try:
        from services.api.log_buffer import read_managed_tickers
        found.update(str(t.get("sym") or "") for t in (read_managed_tickers() or [])
                     if isinstance(t, dict))
    except Exception as exc:
        logger.debug("[peers] managed tickers unreadable: %s", exc)
    try:
        from core.discovery.shelf import ShelfStore
        found.update(i.symbol for i in ShelfStore().load().ideas if i.status == "active")
    except Exception as exc:
        logger.debug("[peers] shelf unreadable: %s", exc)
    return sorted({str(s).strip().upper() for s in found if str(s or "").strip()})


def _registry_key(ticker: str) -> str:
    try:
        from backend.sectors.registry import TICKER_SECTOR
        return str(TICKER_SECTOR.get(ticker, "") or "")
    except Exception as exc:
        logger.debug("[peers] registry ticker map unreadable: %s", exc)
        return ""


# ---------------------------------------------------------------------------
# Profiles: industry and market cap per listing, cached on disk
# ---------------------------------------------------------------------------

def lookup_profile(provider_symbol: str) -> dict:
    """One yfinance `.info` call for a provider symbol (e.g. "SUNPHARMA.NS"):
    {"industry", "sector", "market_cap"}, "" or None when Yahoo gives none.
    Raises when the call fails, so a failure is never cached as an answer."""
    import yfinance as yf

    info = yf.Ticker(provider_symbol).info or {}
    return {
        "industry": str(info.get("industry") or "").strip(),
        "sector": str(info.get("sector") or "").strip(),
        "market_cap": _cap(info.get("marketCap")),
    }


def _cap(value) -> float | None:
    try:
        cap = float(value)
    except (TypeError, ValueError):
        return None
    return cap if math.isfinite(cap) and cap > 0 else None


def _load_profiles() -> dict[str, dict]:
    try:
        data = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        logger.warning("[peers] %s unreadable, starting empty: %s", PROFILE_PATH, exc)
        return {}
    profiles = data.get("profiles") if isinstance(data, dict) else None
    if not isinstance(profiles, dict):
        return {}
    return {str(k): v for k, v in profiles.items() if isinstance(v, dict)}


def _save_profiles(profiles: dict[str, dict]) -> None:
    try:
        PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = PROFILE_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps({"version": 1, "profiles": profiles}, sort_keys=True),
                       encoding="utf-8")
        tmp.replace(PROFILE_PATH)
    except OSError as exc:
        logger.warning("[peers] %s not written: %s", PROFILE_PATH, exc)


def _age_days(profile: dict, today: date) -> int | None:
    try:
        return (today - date.fromisoformat(str(profile.get("as_of"))[:10])).days
    except (TypeError, ValueError):
        return None


def _due(profiles: dict[str, dict], symbol: str, today: date, days: int) -> bool:
    profile = profiles.get(symbol)
    if profile is None:
        return True
    age = _age_days(profile, today)
    return age is None or age > days


def _refresh(profiles: dict[str, dict], mine: str, my_key: str,
             candidates: dict[str, str], today: date,
             lookup: Callable[[str], dict]) -> int:
    """Look up the due profiles, within the budget. Returns how many were
    written."""
    budget = max_lookups()
    days = cache_days()
    order = [mine] if _due(profiles, mine, today, days) else []
    due = [p for p in candidates if _due(profiles, p, today, days)]
    due.sort(key=lambda p: (p in profiles,
                            not my_key or _registry_key(candidates[p]) != my_key,
                            candidates[p]))
    order += due
    written, failures = 0, 0
    for symbol in order[:max(budget, 0)]:
        try:
            profile = lookup(symbol)
        except Exception as exc:
            failures += 1
            logger.info("[peers] profile of %s not looked up: %s", symbol, exc)
            if failures >= FAILURES_BEFORE_STOP:
                logger.warning("[peers] %d lookups failed in a row; the rest wait for a "
                               "later build", failures)
                break
            continue
        failures = 0
        profiles[symbol] = {
            "industry": str(profile.get("industry") or "").strip(),
            "sector": str(profile.get("sector") or "").strip(),
            "market_cap": _cap(profile.get("market_cap")),
            "as_of": today.isoformat(),
        }
        written += 1
    return written


# ---------------------------------------------------------------------------
# The choice
# ---------------------------------------------------------------------------

def _same_industry(profile: dict | None, industry: str) -> bool:
    if not profile:
        return False
    return str(profile.get("industry") or "").strip().casefold() == industry.casefold()


def nearest_first(entries: list[tuple[str, float | None]],
                  my_cap: float | None) -> list[str]:
    """Symbols ordered nearest market cap first: by |ln(cap / my_cap)|.
    Unknown caps last; ties by symbol. With no cap of its own the stock's
    peers go largest first."""
    def key(entry: tuple[str, float | None]):
        symbol, cap = entry
        if cap is None:
            return (1, 0.0, symbol)
        if my_cap is None:
            return (0, -cap, symbol)
        return (0, abs(math.log(cap / my_cap)), symbol)
    return [symbol for symbol, _ in sorted(entries, key=key)]


def choose_peers(ticker: str, *, sector: str = "", today: date | None = None,
                 universe: Iterable[str] | None = None,
                 lookup: Callable[[str], dict] | None = None) -> PeerChoice:
    """The peers `ticker`'s valuation is compared with (module docstring).
    `sector` is the graph the stock runs: with no registry key of its own, a
    native graph's members are looked up first. Never raises."""
    t = (ticker or "").strip().upper()
    try:
        return _choose(t, sector, today or date.today(), universe, lookup or lookup_profile)
    except Exception as exc:
        logger.warning("[peers] choice for %s failed: %s", t, exc, exc_info=True)
        return PeerChoice(t, (), "", f"the choice failed ({type(exc).__name__})")


def _choose(t: str, sector: str, today: date, universe: Iterable[str] | None,
            lookup: Callable[[str], dict]) -> PeerChoice:
    from backend.shared.data.fetchers.symbol_resolver import resolve_identity

    me = resolve_identity(t, today)
    if not me.resolved:
        return PeerChoice(t, (), "", f"{t}'s identity is {me.status} ({me.reason_text()})")

    members = sorted({str(s).strip().upper() for s in
                      (known_symbols() if universe is None else universe)
                      if str(s or "").strip()})
    candidates: dict[str, str] = {}          # provider symbol -> app ticker
    for symbol in members:
        if symbol == t:
            continue
        identity = resolve_identity(symbol, today)
        if identity.resolved and identity.symbol != me.symbol:
            candidates.setdefault(identity.symbol, symbol)

    my_key = _registry_key(t) or ("" if sector in ("", "generic") else sector)
    with _LOCK:
        profiles = _load_profiles()
        if _refresh(profiles, me.symbol, my_key, candidates, today, lookup):
            _save_profiles(profiles)

    mine = profiles.get(me.symbol)
    if mine is None:
        return PeerChoice(t, (), "", f"the industry of {t} could not be looked up")
    industry = str(mine.get("industry") or "").strip()
    if not industry:
        return PeerChoice(t, (), "", f"Yahoo gives no industry for {t}")

    same = [(app, _cap(profiles[p].get("market_cap"))) for p, app in candidates.items()
            if _same_industry(profiles.get(p), industry)]
    needed = peer_minimum()
    if len(same) < needed:
        profiled = sum(1 for p in candidates if p in profiles)
        return PeerChoice(
            t, (), industry,
            f'{len(same)} other known symbol(s) in Yahoo industry "{industry}", '
            f"{needed} needed ({profiled} of {len(candidates)} known symbols profiled)")
    ordered = nearest_first(same, _cap(mine.get("market_cap")))
    return PeerChoice(t, tuple(ordered[:peer_count()]), industry)
