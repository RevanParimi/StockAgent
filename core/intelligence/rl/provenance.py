"""F3 (sensing audit 2026-07-31) — provenance retention for learned artifacts.

Lessons and dossier observations used to store their conclusion and nothing
else: "[research] {answer}", a rule, a pattern. The headline and date that
produced them were discarded at write-back, so nothing downstream could tell a
claim grounded in a dated article from one the model invented.

This module is the one pure parser both writers share. It reads the bullets
already present in `market_context_today` / a research search context — the
shapes `services/data/fetchers/news.py::_recent_article_lines` and
`MacroNewsCache.get_for_daily_review` emit — and returns short
"YYYY-MM-DD — headline" strings.

Retention only: nothing here re-fetches or verifies a URL (explicitly rejected
as over-engineering in the audit). It is worth keeping now only because F1/F6
made those articles arrive dated and recent; before that fix it would have
persisted stale provenance.
"""
from __future__ import annotations

from datetime import date

# Header F2 injects before market-wide items. Everything after it describes the
# market, not the stock, and must stay distinguishable in what we persist.
_MARKET_WIDE_HEADER = "[MARKET-WIDE CONTEXT"
_MARKET_WIDE_PREFIX = "market-wide "


def extract_context_evidence(
    market_context: str, max_items: int, max_chars: int = 160,
) -> list[str]:
    """Provenance strings for the dated bullets in `market_context`.

    Only bullets carrying a parseable ISO date survive — the AUD-041 rule
    applied to what we persist, since undated provenance cannot be correlated
    with anything later. Order is preserved, duplicates dropped, market-wide
    items prefixed so a macro headline can never read as company evidence.
    """
    if not market_context or max_items <= 0:
        return []

    out: list[str] = []
    market_wide = False

    for line in market_context.splitlines():
        line = line.strip()
        if _MARKET_WIDE_HEADER in line:
            market_wide = True
            continue
        if not line.startswith("•"):
            continue

        rest = line[1:].strip()
        if not rest.startswith("[") or "]" not in rest:
            continue
        bracket, _, remainder = rest[1:].partition("]")
        remainder = remainder.strip()
        if not remainder:
            continue

        raw_date = bracket.strip()
        if raw_date.lower().startswith("date:"):
            raw_date = raw_date.split(":", 1)[1].strip()
        try:
            iso = date.fromisoformat(raw_date).isoformat()
        except ValueError:
            continue                      # undated / "date unknown" — no provenance

        entry = f"{_MARKET_WIDE_PREFIX if market_wide else ''}{iso} — {remainder}"
        entry = entry[:max_chars]
        if entry not in out:
            out.append(entry)
        if len(out) >= max_items:
            break

    return out


def merge_evidence(existing: list[str], incoming: list[str], max_items: int) -> list[str]:
    """Append unseen provenance, newest last, capped.

    Reinforcement appends rather than replaces — a lesson confirmed 20 times
    should show what kept confirming it — but the cap keeps a long-lived lesson
    bounded. Eviction takes the oldest lines, which are also the stalest.
    """
    if not incoming:
        return existing
    merged = existing + [e for e in incoming if e not in existing]
    return merged[-max_items:] if max_items > 0 else []
