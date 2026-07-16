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

import json
import logging
import time
from datetime import date as _date

from backend.shared.data.fetchers.symbol_resolver import resolve_company_name
from backend.shared.schemas.dossier import OpenQuestion, TickerDossier
from backend.shared.schemas.feedback import EVENT_TAGS
from core.config import settings
from core.config.prompts.shared.question_researcher import (
    RESEARCH_QUESTION_BLOCK, RESEARCH_SYSTEM_PROMPT, RESEARCH_USER_TEMPLATE,
)
from core.intelligence.rl.agents.dossier_curator import (
    _strip_think, merge_curator_output,
)
from services.clients.tavily_fetcher import fetch_tavily_context
from services.data.fetchers.news import fetch_news_context

logger = logging.getLogger(__name__)

# Query length cap — the question text itself is the query (targeted, not generic).
_QUERY_MAX_CHARS = 120

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


# ---------------------------------------------------------------------------
# Component 3 — Search (1 Serper per question, <=1 Tavily fallback per run)
# ---------------------------------------------------------------------------


def _search_question(ticker: str, company_name: str, question: str,
                     tavily_budget: list[int]) -> str:
    """Targeted search for one question. The question text IS the query.

    One Serper news search; if it comes back empty or as a "[No results"
    placeholder AND the run's single Tavily budget (the mutable `tavily_budget`
    cell) is unspent, one Tavily page is fetched as fallback. Result truncated
    to RL_RESEARCH_CONTEXT_MAX_CHARS. Never raises.
    """
    query = f"{company_name or ticker} {question}"[:_QUERY_MAX_CHARS]

    news = ""
    try:
        news = fetch_news_context([query], max_queries=1) or ""
    except Exception as exc:
        logger.debug("[QuestionResearcher] %s: news search failed: %s", ticker, exc)
        news = ""

    needs_fallback = (not news.strip()) or ("[No results" in news)
    if needs_fallback and tavily_budget and tavily_budget[0] > 0:
        tavily_budget[0] -= 1
        try:
            tav = fetch_tavily_context([query], max_queries=1, max_results_per_query=1)
            if tav and "No Tavily" not in tav:
                news = f"{news}\n\n{tav}" if news.strip() else tav
        except Exception as exc:
            logger.debug("[QuestionResearcher] %s: Tavily fallback failed: %s", ticker, exc)

    return news[: settings.RL_RESEARCH_CONTEXT_MAX_CHARS]


# ---------------------------------------------------------------------------
# Component 4 — Judgment (one batched LLM call) + write-back via shared merge
# ---------------------------------------------------------------------------


class QuestionResearcher:
    """LLM client pattern mirrors DossierCurator/EventIngestor (json_object,
    low temp, retry-free). `run()` NEVER raises."""

    def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        from services.clients.llm_client import JSON_MODE_EXTRA_BODY, get_llm_client, record_llm_call
        client = get_llm_client()
        t0 = time.time()
        try:
            resp = client.chat.completions.create(
                model=settings.LLM_MODEL_BULK,
                temperature=0.2,
                max_tokens=900,
                response_format={"type": "json_object"},
                extra_body=JSON_MODE_EXTRA_BODY,
                messages=[{"role": "system", "content": system_prompt},
                          {"role": "user", "content": user_prompt}],
            )
        except Exception:
            record_llm_call("question_researcher", settings.LLM_MODEL_BULK, 0, 0,
                            int((time.time() - t0) * 1000), False)
            raise
        usage = getattr(resp, "usage", None)
        record_llm_call("question_researcher", settings.LLM_MODEL_BULK,
                        getattr(usage, "prompt_tokens", 0) or 0,
                        getattr(usage, "completion_tokens", 0) or 0,
                        int((time.time() - t0) * 1000), True)
        return resp.choices[0].message.content or ""

    # ------------------------------------------------------------------

    def run(self, ticker: str, sector: str) -> dict:
        """Expire -> select -> search -> judge -> merge -> save.

        Returns {"selected", "answered", "partial", "expired"}. NEVER raises.
        Flag off / no dossier / no work -> zeros, no searches, no LLM call, no
        save (except: expiry alone still saves so the digest stays clean).
        """
        zeros = {"selected": 0, "answered": 0, "partial": 0, "expired": 0}

        if not getattr(settings, "RL_RESEARCH_LOOP_ENABLED", True):
            return dict(zeros)

        try:
            from core.intelligence.rl.stores.prediction_store import PredictionStore

            store = PredictionStore(ticker, sector=sector)
            dossier = store.load_dossier()
            if dossier is None:
                return dict(zeros)            # research never creates a dossier

            today = _date.today().isoformat()
            expired = expire_stale_questions(dossier, today)
            selected = select_questions(
                dossier, today, cap=settings.RL_RESEARCH_MAX_QUESTIONS_PER_RUN)

            if not selected:
                if expired:
                    store.save_dossier(dossier)
                return {"selected": 0, "answered": 0, "partial": 0, "expired": expired}

            try:
                company = resolve_company_name(ticker) or ticker
            except Exception:
                company = ticker

            tavily_budget = [1]               # one Tavily fallback per run
            contexts = {
                q.question: _search_question(ticker, company, q.question, tavily_budget)
                for q in selected
            }

            results_by_q = self._judge(ticker, sector, selected, contexts)

            answered, partial = self._apply(dossier, selected, results_by_q, today)

            store.save_dossier(dossier)
            return {"selected": len(selected), "answered": answered,
                    "partial": partial, "expired": expired}
        except Exception as exc:
            logger.warning("[QuestionResearcher] %s: non-fatal run failure: %s",
                           ticker, exc)
            return dict(zeros)

    # ------------------------------------------------------------------

    def _judge(self, ticker: str, sector: str, selected: list[OpenQuestion],
               contexts: dict[str, str]) -> dict[str, dict]:
        """One batched LLM call judging every selected question. Returns a map
        of selected-question-text -> result dict (status/answer/finding/tags).
        Garbage or unmatched output degrades that question to no_signal."""
        blocks = "\n".join(
            RESEARCH_QUESTION_BLOCK.format(
                idx=i + 1, question=q.question,
                context=contexts.get(q.question, "") or "(no search results)")
            for i, q in enumerate(selected))
        system = RESEARCH_SYSTEM_PROMPT.format(
            ticker=ticker, sector=sector, event_tags=", ".join(sorted(EVENT_TAGS)))
        user = RESEARCH_USER_TEMPLATE.format(
            ticker=ticker, sector=sector, questions_block=blocks)

        try:
            data = json.loads(_strip_think(self._call_llm(system, user)))
            raw_results = data.get("results", []) if isinstance(data, dict) else []
        except Exception as exc:
            logger.warning("[QuestionResearcher] %s: judgment parse failed: %s",
                           ticker, exc)
            raw_results = []

        # Match each LLM result to a selected question by case-insensitive
        # substring (same convention merge_curator_output uses for resolve).
        out: dict[str, dict] = {}
        for res in raw_results:
            if not isinstance(res, dict):
                continue
            rq = (res.get("question") or "").strip().lower()
            if not rq:
                continue
            for q in selected:
                if q.question in out:
                    continue
                if rq in q.question.lower():
                    out[q.question] = res
                    break
        return out

    def _apply(self, dossier: TickerDossier, selected: list[OpenQuestion],
               results_by_q: dict[str, dict], today: str) -> tuple[int, int]:
        """Map judgments onto the curator-shaped dict + apply via the shared
        bounded merge, then do the attempts/last_attempt bookkeeping (which is
        intentionally OUTSIDE the merge). Returns (answered, partial) counts."""
        new_observations: list[dict] = []
        question_updates: list[dict] = []
        answered = partial = 0

        for q in selected:
            res = results_by_q.get(q.question)
            status = (res or {}).get("status", "no_signal")
            tags = [t for t in (res or {}).get("tags", []) if t in EVENT_TAGS]

            if status == "answered" and (res.get("answer") or "").strip():
                ans = res["answer"].strip()
                question_updates.append(
                    {"action": "resolve", "question": q.question, "answer": ans})
                new_observations.append(
                    {"observation": f"[research] {ans}", "tags": tags,
                     "materiality": 0.6})
                answered += 1
            elif status == "partial" and (res.get("finding") or "").strip():
                finding = res["finding"].strip()
                new_observations.append(
                    {"observation": f"[research-partial] {finding}", "tags": tags,
                     "materiality": 0.4})
                q.attempts += 1
                partial += 1
            else:                              # no_signal / unmatched / garbage
                q.attempts += 1

            q.last_attempt = today             # every attempted question, always

        merge_curator_output(
            dossier,
            {"new_observations": new_observations,
             "open_question_updates": question_updates},
            today=today, outcome_link="")

        return answered, partial
