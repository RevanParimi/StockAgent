"""
Compass Phase B — guard data for the post-rank shortlist (spec §6.1 threshold
gates: ASM/GSM, suspension, free-float mcap floor) and a company's market
classification.

Surveillance and suspension come from NSE's daily "Surveillance Indicator"
report (CM segment; `REG1_IND<ddmmyy>.csv` in the archive). It has one row
per listed security: its stage under each surveillance measure, "100" meaning
not under it, and its status, "A" active or "S" suspended. One file covers
every symbol, so a run fetches it once. NSE's per-symbol equity-meta-info API,
read before, answers 404 (probed 2026-10-20). Example: the report for 29 Oct
2026 lists 3,216 securities, 16 of them suspended; its GSM, long-term ASM and
short-term ASM members match NSE's own lists of 30 Oct, a day later (the
reportASM and reportGSM APIs), but for 2 long-term ASM and 3 GSM symbols.

Float mcap and classification come from Yahoo Finance, per symbol.
"""
from __future__ import annotations

import io
import json
import logging
import pathlib
import time
from datetime import date, timedelta

import pandas as pd

from core.config import settings
from core.intelligence.rl.nse_calendar import is_trading_day
from services.data.fetchers.nse_client import close_nse, make_nse

logger = logging.getLogger(__name__)

_SURVEILLANCE_URL = "https://nsearchives.nseindia.com/content/cm/REG1_IND{:%d%m%y}.csv"
# Report column -> the measure's short name. Any value but "100" is a stage.
_MEASURES = {
    "GSM": "GSM",
    "Long_Term_Additional_Surveillance_Measure (Long Term ASM)": "LT-ASM",
    "Short_Term_Additional_Surveillance_Measure (Short Term ASM)": "ST-ASM",
}
_NOT_UNDER = "100"
_ACTIVE = "A"
# A report older than this, counted back from the screen's latest session,
# no longer says who is under surveillance now.
SURVEILLANCE_MAX_AGE_DAYS = 7
_SLEEP_BETWEEN_CALLS = 0.5


def _make_nse_client():
    """Isolated factory so tests can monkeypatch it."""
    return make_nse()


def _yf_info(ticker: str) -> dict:
    """yfinance .info with the repo's NSE suffix convention. {} on failure."""
    try:
        import yfinance as yf
        from datetime import date
        from backend.shared.data.instruments import registry_identity
        from core.config import settings
        suffix = settings.YFINANCE_SUFFIX
        registered = registry_identity(ticker, date.today())      # SA-008
        yf_ticker = registered.symbol if registered is not None else (
            ticker if ticker.endswith(suffix) else f"{ticker}{suffix}"
        )
        return yf.Ticker(yf_ticker).info or {}
    except Exception as exc:
        logger.debug("[surveillance] yfinance info failed for %s: %s", ticker, exc)
        return {}


def parse_surveillance(text: str) -> dict[str, dict] | None:
    """{symbol: {"status": "A" | "S" | …, "measures": ["GSM", "LT-ASM", …]}}
    from the report's CSV text, "measures" naming those the symbol is under.
    None when a column it needs is missing (a format change)."""
    raw = pd.read_csv(io.StringIO(text), dtype=str, skipinitialspace=True)
    raw.columns = [str(c).strip() for c in raw.columns]
    missing = [c for c in ("Symbol", "Status", *_MEASURES) if c not in raw.columns]
    if missing:
        logger.warning("[surveillance] report lacks columns %s", missing)
        return None
    out: dict[str, dict] = {}
    columns = [raw[c].fillna("").str.strip() for c in _MEASURES]
    for i, (sym, status) in enumerate(zip(raw["Symbol"].fillna(""), raw["Status"].fillna(""))):
        sym = sym.strip().upper()
        if not sym:
            continue
        row = {"status": status.strip().upper(),
               "measures": [name for name, col in zip(_MEASURES.values(), columns)
                            if col.iloc[i] not in ("", _NOT_UNDER)]}
        held = out.get(sym)
        if held is not None:          # never seen; keep the stricter reading
            row = {"status": held["status"] if held["status"] != _ACTIVE else row["status"],
                   "measures": sorted(set(held["measures"]) | set(row["measures"]))}
        out[sym] = row
    return out or None


def _client_or_none():
    try:
        return _make_nse_client()
    except Exception as exc:
        logger.warning("[surveillance] NSE client unavailable: %s", exc)
        return None


def _fetch_report(nse, day: date) -> dict[str, dict] | None:
    """The day's report, parsed. None on any failure (holiday, not yet
    published, archive down, format change)."""
    try:
        resp = nse._req(_SURVEILLANCE_URL.format(day))
        return parse_surveillance(resp.content.decode("utf-8", errors="replace"))
    except Exception as exc:
        logger.warning("[surveillance] report for %s unavailable: %s", day, exc)
        return None


def _surveillance_path() -> pathlib.Path:
    return pathlib.Path(settings.DISCOVERY_DATA_DIR) / "surveillance.json"


def _load_cached() -> tuple[dict | None, str | None]:
    path = _surveillance_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, None
    except (OSError, ValueError) as exc:
        logger.warning("[surveillance] cache unreadable %s: %s", path, exc)
        return None, None
    securities = data.get("securities") if isinstance(data, dict) else None
    as_of = data.get("as_of") if isinstance(data, dict) else None
    if isinstance(securities, dict) and securities and isinstance(as_of, str):
        return securities, as_of
    return None, None


def _save(securities: dict, as_of: str) -> None:
    path = _surveillance_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"as_of": as_of, "securities": securities}), encoding="utf-8")
        tmp.replace(path)
    except OSError as exc:
        logger.error("[surveillance] cache write failed %s: %s", path, exc)


def surveillance_list(session: date, tries: int = 5) -> tuple[dict[str, dict] | None, str | None]:
    """(securities, as_of): the newest Surveillance Indicator report dated on
    or before `session`, the screen's latest EOD session, and at most
    SURVEILLANCE_MAX_AGE_DAYS before it. Trading days are taken newest first:
    the cached report serves for its own day, any other is fetched (at most
    `tries` fetches) and cached. A report dated after `session` is never used,
    so a replay of a past screen sees only what was published by then.
    (None, None) when no report qualifies: the gate is dark for the run.
    Never raises.

    Example: a screen whose latest session is Friday 30 Oct, run before NSE
    has published that day's report, uses Thursday 29 Oct's. When NSE does
    not answer, a cached 30 Oct report serves a screen of 6 Nov but not one
    of 9 Nov."""
    oldest = session - timedelta(days=SURVEILLANCE_MAX_AGE_DAYS)
    cached, cached_as_of = _load_cached()
    nse, fetched = None, 0
    try:
        day = session
        while day >= oldest:
            if is_trading_day(day):
                if cached is not None and cached_as_of == day.isoformat():
                    return cached, cached_as_of
                if fetched < tries:
                    fetched += 1
                    if nse is None:
                        nse = _client_or_none()
                    if nse is None:
                        fetched = tries           # NSE unreachable: only the cache can answer
                    else:
                        securities = _fetch_report(nse, day)
                        if securities:
                            _save(securities, day.isoformat())
                            logger.info("[surveillance] report as of %s: %d securities",
                                        day, len(securities))
                            return securities, day.isoformat()
                        time.sleep(_SLEEP_BETWEEN_CALLS)
            day -= timedelta(days=1)
    finally:
        close_nse(nse)
    logger.warning("[surveillance] no report from %s to %s (cached as of %s): the "
                   "ASM/GSM and suspension gates are dark", oldest, session, cached_as_of)
    return None, None


def market_classification(symbol: str) -> dict:
    """The company's market sector and industry from Yahoo Finance, e.g.
    {"sector": "Healthcare", "industry": "Drug Manufacturers - General"};
    "" for either when unknown (Yahoo gives a fund neither). NSE's
    equity-meta-info answers 404 (probed 2026-10-20) and its quote API refused
    this machine (403). Never raises."""
    info = _yf_info(symbol)
    return {"sector": str(info.get("sector") or "").strip(),
            "industry": str(info.get("industry") or "").strip()}


def float_mcap_cr(symbol: str) -> float | None:
    """Free-float market cap in ₹ crore via yfinance; None when unknown."""
    info = _yf_info(symbol)
    shares = info.get("floatShares")
    price = info.get("currentPrice") or info.get("regularMarketPrice") \
        or info.get("previousClose")
    if not shares or not price:
        return None
    return float(shares) * float(price) / 1e7
