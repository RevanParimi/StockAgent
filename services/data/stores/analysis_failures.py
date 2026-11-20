"""
services/data/stores/analysis_failures.py
==========================================
CLEAN-005: one row per analysis that scored nothing.

When the one analysis call fails there is no backup analysis: the stock gets
no analysis that run (`backend/shared/pipeline/no_analysis.py`). Each such run
appends a row here; `failed_count_today` is the `analyses_failed_today` field
of GET /scheduler/status, the slot the old fallback count used.

"Today" is the IST date, the day the owner reads the status page in. Both
functions never raise: observability must not take down the run it observes.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

_PATH = Path("data") / "rl" / "analysis_failures.jsonl"
_IST = ZoneInfo("Asia/Kolkata")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def record_analysis_failure(sector: str, ticker: str, reason: str, run_id: str = "") -> None:
    """Append one failed analysis. Never raises."""
    try:
        now = _now()
        rec = {
            "ts": now.isoformat(),
            "ist_date": now.astimezone(_IST).date().isoformat(),
            "sector": sector,
            "ticker": ticker,
            "run_id": run_id,
            "reason": str(reason)[:300],
        }
        _PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(_PATH, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")
    except Exception as exc:
        logger.warning("[analysis_failures] record failed (non-fatal): %s", exc)


def failed_count_today() -> int:
    """Failed analyses dated today (IST). 0 when absent or unreadable; never raises."""
    try:
        if not _PATH.exists():
            return 0
        today = _now().astimezone(_IST).date().isoformat()
        count = 0
        with open(_PATH, encoding="utf-8") as fh:
            for line in fh:
                try:
                    if json.loads(line).get("ist_date") == today:
                        count += 1
                except (ValueError, AttributeError):
                    continue
        return count
    except Exception as exc:
        logger.warning("[analysis_failures] count failed (non-fatal): %s", exc)
        return 0
