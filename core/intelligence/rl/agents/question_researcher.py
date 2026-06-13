"""
QuestionResearcher — active open-question resolution (RL Phase 4).

Weekly per-ticker pass: select the most promising unresolved dossier
open_questions, run targeted Serper/Tavily searches built from the question
text (not generic sector news), judge via one batched LLM call whether the
search answered each question, and write results back through the SAME bounded
merge (`merge_curator_output`) the daily curator uses. Questions that keep
finding no public signal expire instead of burning searches forever.

Spec: docs/superpowers/specs/2026-06-13-research-loop-design.md. Mirrors
EventIngestor exactly — module-level pure helpers + a small class with
`_call_llm` + a never-raises `run()`.
"""
from __future__ import annotations

from backend.shared.schemas.dossier import OpenQuestion, TickerDossier
from core.config import settings

# ---------------------------------------------------------------------------
# Component 1 — Selection (pure, deterministic, no LLM)
# ---------------------------------------------------------------------------


def select_questions(dossier: TickerDossier, today: str, cap: int) -> list[OpenQuestion]:
    """Pick at most `cap` unresolved questions worth researching today.

    Candidates: unresolved AND under the attempts cap AND not already attempted
    today (idempotent same-day re-runs). Ordered fewest attempts first, then
    newest raised_on first — fresh questions get priority while stalled ones
    aren't starved because attempts dominates the sort.
    """
    max_attempts = settings.RL_RESEARCH_MAX_ATTEMPTS
    candidates = [
        q for q in dossier.open_questions
        if not q.resolved_on
        and q.attempts < max_attempts
        and q.last_attempt != today
    ]
    # Stable sort: raised_on desc first, then attempts asc dominates.
    candidates.sort(key=lambda q: q.raised_on, reverse=True)
    candidates.sort(key=lambda q: q.attempts)
    return candidates[:cap]


# ---------------------------------------------------------------------------
# Component 2 — Expiry (pure, deterministic)
# ---------------------------------------------------------------------------


def expire_stale_questions(dossier: TickerDossier, today: str) -> int:
    """Resolve any unresolved question at/over the attempts cap. Returns count.

    Runs at the START of each run() so the dossier digest stays clean even when
    selection finds nothing new to research.
    """
    max_attempts = settings.RL_RESEARCH_MAX_ATTEMPTS
    expired = 0
    for q in dossier.open_questions:
        if q.resolved_on:
            continue
        if q.attempts >= max_attempts:
            q.resolved_on = today
            q.answer = f"expired: no public signal after {max_attempts} research attempts"
            expired += 1
    return expired
