"""
services/data/stores/fallback_events.py
========================================
Record of legacy-pool fallback engagements (Wave I).

The unified analyst failing over to the legacy multi-agent pool was only a
log WARNING — invisible unless someone read the Railway console at the right
moment. Each fallback costs ~6-8x the Serper credits of the unified path, so
a quietly elevated fallback rate breaks the cost model without any signal.

`record_fallback` appends one JSONL row per engagement;
`fallback_count_today` is merged into GET /scheduler/status. Both never
raise — observability must not take down the analysis it observes.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_EVENTS_PATH = Path("data") / "rl" / "fallback_events.jsonl"


def record_fallback(sector: str, ticker: str, reason: str = "unified_analyst_failed") -> None:
    """Append one fallback engagement. Never raises."""
    try:
        _EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        rec = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "sector": sector,
            "ticker": ticker,
            "reason": reason,
        }
        with open(_EVENTS_PATH, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")
    except Exception as exc:
        logger.warning("[fallback_events] record failed (non-fatal): %s", exc)


def fallback_count_today() -> int:
    """Engagements whose UTC date is today. 0 when absent/corrupt; never raises."""
    try:
        if not _EVENTS_PATH.exists():
            return 0
        today = datetime.now(timezone.utc).date().isoformat()
        count = 0
        with open(_EVENTS_PATH, encoding="utf-8") as fh:
            for line in fh:
                try:
                    if json.loads(line).get("ts", "").startswith(today):
                        count += 1
                except Exception:
                    continue
        return count
    except Exception as exc:
        logger.warning("[fallback_events] count failed (non-fatal): %s", exc)
        return 0
