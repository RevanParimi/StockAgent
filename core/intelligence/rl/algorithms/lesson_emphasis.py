"""
Executable-claim application: tagged lessons nudge agent scores on matching days.

apply_lesson_emphasis() is the ONLY place trigger_tags lessons act numerically —
deltas come from settings at call time, never stored on the lesson (they'd go stale).
Untagged legacy lessons remain handled by the category micro-adjustment in
generate_forecast._apply_ledger_micro_adjustments.
"""
from __future__ import annotations

import logging
from datetime import date

logger = logging.getLogger(__name__)


def matching_lessons(ledger, today_tags: list) -> list:
    """Return still-valid lessons whose trigger_tags fire on today's tags.

    Gates (same as apply_lesson_emphasis's inline loop):
      - lesson.still_valid is True
      - lesson.trigger_tags is non-empty
      - lesson.trigger_tags intersects today_tags
      - ledger.effective_confidence(lesson) >= settings.RL_LESSON_MATCH_MIN_CONF

    Pure with respect to inputs; reads settings at call time; never raises.
    Returns [] when ledger is None/empty or today_tags is empty. A lesson
    that raises during gate evaluation is skipped, not propagated.
    """
    from core.config import settings

    if ledger is None or not getattr(ledger, "lessons", None) or not today_tags:
        return []

    tagset = set(today_tags)
    min_conf = settings.RL_LESSON_MATCH_MIN_CONF

    matched = []
    for lesson in ledger.lessons:
        try:
            if not lesson.still_valid or not lesson.trigger_tags:
                continue
            if not tagset.intersection(lesson.trigger_tags):
                continue
            eff = (ledger.effective_confidence(lesson)
                   if hasattr(ledger, "effective_confidence") else lesson.confidence)
            if eff < min_conf:
                continue
            matched.append(lesson)
        except Exception as exc:                       # one bad lesson never blocks the rest
            logger.debug("[lesson_emphasis] skipped lesson: %s", exc)

    return matched


def apply_lesson_emphasis(day_agent_scores: dict, ledger, today_tags: list) -> dict:
    """Boost/dampen agent scores for still-valid tagged lessons firing today.

    Pure with respect to inputs; reads settings at call time; never raises.
    """
    from core.config import settings

    if not getattr(settings, "RL_CLAIMS_ENABLED", True):
        return dict(day_agent_scores)

    adj = {a: 0.0 for a in day_agent_scores}
    delta = settings.RL_LESSON_EMPHASIS_DELTA

    for lesson in matching_lessons(ledger, today_tags):
        try:
            for a in lesson.prioritise_agents:
                if a in adj:
                    adj[a] += delta
            for a in lesson.discount_agents:
                if a in adj:
                    adj[a] -= delta
        except Exception as exc:                       # one bad lesson never blocks the rest
            logger.debug("[lesson_emphasis] skipped lesson: %s", exc)

    cap = settings.RL_LESSON_EMPHASIS_CAP
    return {
        a: round(min(1.0, max(0.0, s + max(-cap, min(cap, adj[a])))), 4)
        for a, s in day_agent_scores.items()
    }


def calendar_day_tags(d: date) -> list:
    """Calendar-derivable event tags for a (possibly future) date. Pure, never raises."""
    tags: set = set()
    if 6 <= d.month <= 9:
        tags.add("monsoon")
    if (d.month == 2 and d.day <= 7) or (d.month == 1 and d.day >= 25):
        tags.add("budget_event")
    if d.month in (10, 11):
        tags.add("seasonal")            # festive window (Navratri–Diwali)
    try:
        from core.intelligence.rl.nse_calendar import is_fno_expiry_week
        if is_fno_expiry_week(d):
            tags.add("expiry_week")
    except Exception:
        pass
    return sorted(tags)
