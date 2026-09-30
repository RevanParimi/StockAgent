"""
src/backend/shared/data/instruments.py
======================================
SA-008 (audit F08): security identity survives renames, demergers,
suspensions and provider-symbol changes.

Before this module, `settings.YF_SYMBOL_OVERRIDES` mapped TATAMOTORS to
TMPV.NS by hand: no date, no evidence, and nothing downstream knew that the
prices might belong to a different economic entity than the name. With TMPV's
data healthy, the TATAMOTORS analysis was `actionable`.

The registry, config/instruments.yaml, holds effective-dated segments for
each app ticker whose identity is not simply "the NSE listing of the same
name". A segment says which provider symbol to ask for data in that period,
which price basis those prices sit on, and whether the identity is resolved:

  resolved     the segment is `active`, and its symbol is the ticker's own
               listing, an alias with a stated reason, or a rename/demerger/
               relisting successor with recorded evidence.
  unresolved   an `unresolved` segment, a date no segment covers, an invalid
               record, or an unreadable registry (fail closed).
  suspended    a `suspended` segment: trading is halted.
  delisted     a `delisted` segment: the ticker no longer trades.

Evidence is required to resolve an identity, never to quarantine one.

The price basis
---------------
Prices on different bases are not comparable. A rename keeps the basis (the
same company under a new code); a demerger or a relisting starts a new one
(the continuing entity's price excludes what was spun off). A forecast issued
on one basis is never graded against a close on another, and a holding bought
on one basis is not advised on another until an operator reconciles it
(core/portfolio/identity_reconcile.py).

This module reads the registry only. The combined order (registry, then the
learned symbol cache, then the naive "{TICKER}.NS") is
symbol_resolver.resolve_identity.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

RESOLVED = "resolved"
UNRESOLVED = "unresolved"
SUSPENDED = "suspended"
DELISTED = "delisted"

ACTIVE = "active"                      # a segment status; it resolves
_SEGMENT_STATUSES = (ACTIVE, UNRESOLVED, SUSPENDED, DELISTED)
MIGRATIONS = ("rename", "demerger", "relisting")
_VIA = ("alias",) + MIGRATIONS
_SEGMENT_FIELDS = {"from", "until", "status", "symbol", "basis", "via",
                   "evidence", "reason", "successors"}
_EVIDENCE_FIELDS = ("source", "ref", "date")
_ENTRY_FIELDS = {"name", "segments"}
_SUFFIXES = (".NS", ".BO")

_RELPATH = Path("config") / "instruments.yaml"
_ENV_PATH = "INSTRUMENT_REGISTRY_PATH"


class RegistryError(Exception):
    """config/instruments.yaml, or one entry in it, is malformed."""


@dataclass(frozen=True)
class Successor:
    """Where a holding of the old basis goes: `ratio` new shares per old
    share and `cost_fraction` of the old cost basis (the company's published
    cost-of-acquisition split). The fractions of one event sum to 1."""
    ticker: str
    ratio: float
    cost_fraction: float


@dataclass(frozen=True)
class Segment:
    start: date | None                 # inclusive; None = since listing
    until: date | None                 # exclusive; None = open
    status: str
    symbol: str
    basis: str
    via: str = ""
    evidence: tuple[dict, ...] = ()
    reason: str = ""
    successors: tuple[Successor, ...] = ()

    def covers(self, on: date) -> bool:
        return (self.start is None or self.start <= on) and (self.until is None or on < self.until)

    def overlaps(self, since: date, until: date) -> bool:
        """True when the segment covers any day in [since, until]."""
        return (self.start is None or self.start <= until) and (self.until is None or since < self.until)


@dataclass(frozen=True)
class Identity:
    """What one app ticker is on one date."""
    ticker: str
    on: date
    status: str                        # resolved | unresolved | suspended | delisted
    symbol: str                        # the provider (Yahoo) symbol to ask
    basis: str                         # price-basis id: different bases never compare
    via: str = "listing"               # listing | alias | rename | demerger | relisting | learned | symbol
    source: str = "default"            # registry | learned | default | symbol
    reasons: tuple[str, ...] = field(default_factory=tuple)

    @property
    def resolved(self) -> bool:
        return self.status == RESOLVED

    def reason_text(self) -> str:
        return "; ".join(self.reasons) or self.status

    def stamp(self) -> dict[str, str]:
        """The identity an artifact was made on, for forecast rows, reports and advice."""
        return {"ticker": self.ticker, "symbol": self.symbol, "basis": self.basis,
                "status": self.status, "source": self.source}


@dataclass(frozen=True)
class Registry:
    entries: dict[str, tuple[Segment, ...]]
    errors: dict[str, str]             # ticker -> why its record is invalid
    failure: str | None = None         # the whole file is unusable
    path: str = ""


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def norm(ticker: str) -> str:
    return str(ticker or "").strip().upper()


def symbol_root(symbol: str) -> str:
    """'TMPV.NS' -> 'TMPV'; a symbol without an exchange suffix is its own root."""
    s = norm(symbol)
    for suffix in _SUFFIXES:
        if s.endswith(suffix):
            return s[: -len(suffix)]
    return s


def _as_date(value: Any, what: str) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError as exc:
        raise RegistryError(f"{what} {value!r} is not an ISO date") from exc


def _text(raw: dict, key: str) -> str:
    value = raw.get(key)
    return str(value).strip() if value is not None else ""


# ---------------------------------------------------------------------------
# Parsing and validation
# ---------------------------------------------------------------------------

def _parse_evidence(raw: Any, where: str) -> tuple[dict, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise RegistryError(f"{where}: evidence must be a list")
    out = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise RegistryError(f"{where}: evidence[{i}] must be a mapping")
        missing = [k for k in _EVIDENCE_FIELDS if not _text(item, k)]
        if missing:
            raise RegistryError(f"{where}: evidence[{i}] lacks {', '.join(missing)}")
        _as_date(item["date"], f"{where}: evidence[{i}] date")
        out.append({k: _text(item, k) for k in item})
    return tuple(out)


def _parse_successors(raw: Any, where: str) -> tuple[Successor, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list) or not raw:
        raise RegistryError(f"{where}: successors must be a non-empty list")
    out: list[Successor] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict) or not _text(item, "ticker"):
            raise RegistryError(f"{where}: successors[{i}] needs a ticker")
        try:
            ratio = float(item.get("ratio"))
            cost = float(item.get("cost_fraction"))
        except (TypeError, ValueError) as exc:
            raise RegistryError(f"{where}: successors[{i}] needs numeric ratio and cost_fraction") from exc
        if not ratio > 0 or not 0.0 <= cost <= 1.0:
            raise RegistryError(f"{where}: successors[{i}] needs ratio > 0 and 0 <= cost_fraction <= 1")
        out.append(Successor(norm(item["ticker"]), ratio, cost))
    if len({s.ticker for s in out}) != len(out):
        raise RegistryError(f"{where}: successor tickers repeat")
    total = sum(s.cost_fraction for s in out)
    if abs(total - 1.0) > 1e-6:
        raise RegistryError(f"{where}: successor cost fractions sum to {total:g}, not 1")
    return tuple(out)


def _parse_segment(ticker: str, i: int, raw: Any) -> Segment:
    where = f"{ticker} segment {i}"
    if not isinstance(raw, dict):
        raise RegistryError(f"{where} must be a mapping")
    extra = set(raw) - _SEGMENT_FIELDS
    if extra:
        raise RegistryError(f"{where}: unknown field(s) {sorted(extra)}")
    start = _as_date(raw.get("from"), f"{where}: from")
    until = _as_date(raw.get("until"), f"{where}: until")
    if start and until and not start < until:
        raise RegistryError(f"{where}: from {start} is not before until {until}")
    status = _text(raw, "status")
    if status not in _SEGMENT_STATUSES:
        raise RegistryError(f"{where}: status {status!r} is not one of {_SEGMENT_STATUSES}")
    symbol = norm(raw.get("symbol") or "")
    via = _text(raw, "via")
    if via and via not in _VIA:
        raise RegistryError(f"{where}: via {via!r} is not one of {_VIA}")
    reason = _text(raw, "reason")
    evidence = _parse_evidence(raw.get("evidence"), where)
    successors = _parse_successors(raw.get("successors"), where)
    basis = norm(raw.get("basis") or "") or (symbol_root(symbol) if symbol else ticker)

    if status in (ACTIVE, SUSPENDED) and not symbol:
        raise RegistryError(f"{where}: status {status} needs a symbol")
    if status != ACTIVE and not reason:
        raise RegistryError(f"{where}: status {status} needs a reason")
    if status == ACTIVE and symbol_root(symbol) != ticker:
        # The ticker is priced from another code: say how, and prove a migration.
        if not via:
            raise RegistryError(f"{where}: {ticker} -> {symbol} needs via (alias, rename, demerger or relisting)")
        if via == "alias" and not reason:
            raise RegistryError(f"{where}: an alias needs a reason")
    if via in MIGRATIONS and not evidence:
        raise RegistryError(f"{where}: a {via} needs evidence (source, ref, date)")
    if successors and via not in MIGRATIONS:
        raise RegistryError(f"{where}: successors need via rename, demerger or relisting")
    if successors and not evidence:
        raise RegistryError(f"{where}: successors need evidence (source, ref, date)")
    if successors and start is None:
        raise RegistryError(f"{where}: successors need the from date the new basis starts")
    return Segment(start=start, until=until, status=status, symbol=symbol, basis=basis,
                   via=via, evidence=evidence, reason=reason, successors=successors)


def _parse_entry(ticker: str, raw: Any) -> tuple[Segment, ...]:
    if not isinstance(raw, dict):
        raise RegistryError(f"{ticker}: entry must be a mapping")
    extra = set(raw) - _ENTRY_FIELDS
    if extra:
        raise RegistryError(f"{ticker}: unknown field(s) {sorted(extra)}")
    segs = raw.get("segments")
    if not isinstance(segs, list) or not segs:
        raise RegistryError(f"{ticker}: segments must be a non-empty list")
    segments = tuple(_parse_segment(ticker, i, s) for i, s in enumerate(segs))
    for a, b in zip(segments, segments[1:]):
        if a.until is None or b.start is None or b.start < a.until:
            raise RegistryError(f"{ticker}: segments overlap or are out of order")
    return segments


def parse_registry(text: str, path: str = "") -> Registry:
    """Parse registry text. A file-level problem raises RegistryError; a bad
    entry is kept in `errors` and quarantines only that ticker."""
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise RegistryError(f"not valid YAML: {exc}") from exc
    if not isinstance(data, dict) or data.get("version") != 1:
        raise RegistryError("top level must be a mapping with version: 1")
    instruments = data.get("instruments")
    if instruments is None:
        instruments = {}
    if not isinstance(instruments, dict):
        raise RegistryError("instruments must be a mapping")
    entries: dict[str, tuple[Segment, ...]] = {}
    errors: dict[str, str] = {}
    for raw_ticker, raw in instruments.items():
        ticker = norm(raw_ticker)
        try:
            entries[ticker] = _parse_entry(ticker, raw)
        except RegistryError as exc:
            errors[ticker] = str(exc)
    return Registry(entries=entries, errors=errors, path=path)


# ---------------------------------------------------------------------------
# Loading (cached by path and modification time)
# ---------------------------------------------------------------------------

_memo: dict[str, tuple[int, Registry]] = {}
_warned: set[str] = set()


def registry_path() -> Path | None:
    """INSTRUMENT_REGISTRY_PATH, else config/instruments.yaml in the working
    directory (/app in the image), else next to this package's repo root."""
    override = os.getenv(_ENV_PATH)
    if override:
        return Path(override)
    candidate = Path.cwd() / _RELPATH
    if candidate.exists():
        return candidate
    for parent in Path(__file__).resolve().parents:
        candidate = parent / _RELPATH
        if candidate.exists():
            return candidate
    return None


def _warn_once(key: str, message: str, *args) -> None:
    if key not in _warned:
        _warned.add(key)
        logger.error(message, *args)


def load_registry() -> Registry:
    """The registry as it stands on disk. Never raises: a missing or broken
    file is a Registry with `failure` set, which quarantines every ticker."""
    path = registry_path()
    if path is None or not path.exists():
        where = str(path) if path else str(_RELPATH)
        _warn_once(f"missing:{where}",
                   "[instruments] registry %s not found: every identity is unresolved", where)
        return Registry(entries={}, errors={}, failure=f"{where} not found", path=where)
    key = str(path.resolve())
    try:
        mtime = path.stat().st_mtime_ns
    except OSError as exc:
        return Registry(entries={}, errors={}, failure=f"{path}: {exc}", path=key)
    cached = _memo.get(key)
    if cached and cached[0] == mtime:
        return cached[1]
    try:
        registry = parse_registry(path.read_text(encoding="utf-8-sig"), path=key)
    except (OSError, RegistryError) as exc:
        _warn_once(f"broken:{key}:{mtime}",
                   "[instruments] registry %s is unusable (%s): every identity is unresolved",
                   key, exc)
        registry = Registry(entries={}, errors={}, failure=str(exc), path=key)
    for ticker, err in registry.errors.items():
        _warn_once(f"entry:{key}:{mtime}:{ticker}",
                   "[instruments] invalid record for %s (quarantined): %s", ticker, err)
    _memo[key] = (mtime, registry)
    return registry


def is_registered(ticker: str) -> bool:
    """True when the registry owns this ticker's identity: it has a record
    (valid or not), or the registry itself is unusable."""
    registry = load_registry()
    t = norm(ticker)
    return bool(registry.failure) or t in registry.entries or t in registry.errors


# ---------------------------------------------------------------------------
# Identity on a date
# ---------------------------------------------------------------------------

def _current_symbol(segments: tuple[Segment, ...], seg: Segment, today: date) -> str:
    """The code a basis trades under now. A rename keeps the basis, and the
    provider moves the history to the new code, so a close for a day before
    the rename is asked of the new symbol. A different basis keeps its own."""
    symbol = seg.symbol
    for other in segments:
        if other.basis == seg.basis and other.symbol and (other.start is None or other.start <= today):
            symbol = other.symbol
    return symbol


def registry_identity(ticker: str, on: date, *, today: date | None = None) -> Identity | None:
    """The registry's identity for `ticker` on `on`, or None when the registry
    is readable and holds no record for it (the caller then falls back to the
    learned cache and the ticker's own listing)."""
    t = norm(ticker)
    registry = load_registry()
    naive = f"{t}.NS"
    if registry.failure:
        return Identity(t, on, UNRESOLVED, naive, t, via="", source="registry",
                        reasons=(f"instrument registry unusable: {registry.failure}",))
    if t in registry.errors:
        return Identity(t, on, UNRESOLVED, naive, t, via="", source="registry",
                        reasons=(f"invalid instrument record: {registry.errors[t]}",))
    segments = registry.entries.get(t)
    if segments is None:
        return None
    seg = next((s for s in segments if s.covers(on)), None)
    if seg is None:
        return Identity(t, on, UNRESOLVED, naive, t, via="", source="registry",
                        reasons=(f"no identity record for {t} on {on.isoformat()}",))
    symbol = _current_symbol(segments, seg, today or date.today()) or naive
    via = seg.via or "listing"
    if seg.status == ACTIVE:
        return Identity(t, on, RESOLVED, symbol, seg.basis, via=via, source="registry")
    status = {UNRESOLVED: UNRESOLVED, SUSPENDED: SUSPENDED, DELISTED: DELISTED}[seg.status]
    return Identity(t, on, status, symbol, seg.basis, via=via, source="registry",
                    reasons=(seg.reason,))


def registry_bases(ticker: str, since: date, until: date) -> set[str]:
    """Every price basis the registry gives `ticker` over [since, until].
    Empty when the ticker is not registered."""
    registry = load_registry()
    segments = registry.entries.get(norm(ticker)) or ()
    return {s.basis for s in segments if s.overlaps(since, until)}


def segment_on(ticker: str, on: date) -> Segment | None:
    """The registry segment covering `on`, or None."""
    segments = load_registry().entries.get(norm(ticker)) or ()
    return next((s for s in segments if s.covers(on)), None)


def basis_start(ticker: str, basis: str) -> date | None:
    """The first day the registry gives `ticker` this basis (None: since listing)."""
    segments = load_registry().entries.get(norm(ticker)) or ()
    starts = [s.start for s in segments if s.basis == basis]
    if not starts or any(s is None for s in starts):
        return None
    return min(starts)
