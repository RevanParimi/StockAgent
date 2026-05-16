from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

logger = logging.getLogger(__name__)

PROFILES_DIR = Path("data/user_profiles")
_DEFAULT_TIER = "active"


def load_profile(session_id: str) -> dict:
    """Load user profile from disk. Returns safe defaults if missing or corrupt."""
    path = PROFILES_DIR / f"{session_id}.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return _default_profile(session_id)


def save_profile(
    session_id: str,
    tier: str,
    tier_confidence: float,
    topics: list[str],
) -> None:
    """Persist updated profile. Increments sessions_seen, merges topics."""
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    existing = load_profile(session_id)
    merged_topics = list(set(existing.get("topics_seen", []) + topics))[:20]
    existing.update(
        {
            "session_id": session_id,
            "detected_tier": tier,
            "tier_confidence": tier_confidence,
            "sessions_seen": existing.get("sessions_seen", 0) + 1,
            "topics_seen": merged_topics,
            "last_seen": str(date.today()),
        }
    )
    path = PROFILES_DIR / f"{session_id}.json"
    try:
        path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    except Exception as exc:
        logger.warning("Failed to save user profile %s: %s", session_id, exc)


def _default_profile(session_id: str) -> dict:
    return {
        "session_id": session_id,
        "detected_tier": _DEFAULT_TIER,
        "tier_confidence": 0.5,
        "sessions_seen": 0,
        "topics_seen": [],
        "last_seen": str(date.today()),
    }
