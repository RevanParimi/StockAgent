"""Per-call evidence the miss taxonomy needs, captured when it is knowable.

`news_available` is computed on every daily review and was only ever
aggregated into one scheduler log line, so "was this call made blind?" could
not be answered afterwards. That made every miss attributable to the model's
reasoning by default — including the ones where it simply had no news, which
is a plumbing problem wearing a knowledge-gap costume.

Append-only; the index takes the LAST record for a (symbol, date), so a re-run
corrects rather than duplicates. Never raises: this is telemetry about
telemetry and must not be able to fail the review it describes.
"""
from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_PATH = Path("data") / "rl" / "news_availability.jsonl"


def _path(path: str | None) -> Path:
    return Path(path) if path else _DEFAULT_PATH


def record_news_availability(symbol: str, on: date, news_available: bool,
                             macro_fallback_used: bool = False,
                             path: str | None = None) -> None:
    """Append one availability record. Never raises."""
    try:
        p = _path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "date": on.isoformat(), "symbol": symbol,
                "news_available": bool(news_available),
                "macro_fallback_used": bool(macro_fallback_used),
            }) + "\n")
    except Exception as exc:
        logger.warning("[audit] news-availability write failed (non-fatal): %s", exc)


def news_availability_index(path: str | None = None) -> dict:
    """{(symbol, iso_date): news_available}. {} when absent. Never raises.

    A later record for the same key overwrites an earlier one — the file is
    append-only, so a corrected re-run must win rather than collide.
    """
    out: dict = {}
    try:
        p = _path(path)
        if not p.exists():
            return out
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                out[(rec["symbol"], rec["date"])] = bool(rec["news_available"])
            except Exception:
                continue
    except Exception as exc:
        logger.warning("[audit] news-availability read failed (non-fatal): %s", exc)
    return out
