"""
DossierCurator — daily knowledge extraction into the TickerDossier (Step 8.5).

Runs EVERY trading day, hit or miss. LLM proposes updates; this module's merge
code enforces all bounds deterministically. Contract: NEVER raises — any failure
returns the dossier unchanged so the daily review is never blocked.
"""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import date as _date

from backend.shared.schemas.dossier import (
    DossierObservation, GuidanceItem, OpenQuestion, RecurringCatalyst,
    ResponseSignature, TickerDossier,
)
from backend.shared.schemas.feedback import EVENT_TAGS
from core.config.prompts.shared.dossier_curator import (
    CURATOR_SYSTEM_PROMPT, CURATOR_USER_TEMPLATE, DISTILL_SYSTEM_PROMPT,
)

logger = logging.getLogger(__name__)


def _strip_think(raw: str) -> str:
    return re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()


def _next_signature_id(d: TickerDossier) -> str:
    """Monotonic RS-id. Migrates legacy dossiers (counter still at default 1) by seeding from
    the max existing numeric suffix."""
    existing = [int(s.signature_id[2:]) for s in d.response_signatures
                if s.signature_id.startswith("RS") and s.signature_id[2:].isdigit()]
    if d.next_signature_id <= max(existing, default=0):
        d.next_signature_id = max(existing, default=0) + 1
    sid = f"RS{d.next_signature_id:03d}"
    d.next_signature_id += 1
    return sid


def _make_signature(d: TickerDossier, su: dict, today: str, *, occurrences: int,
                     confidence: float, evidence_dates: list[str] | None = None
                     ) -> ResponseSignature | None:
    tags = [t for t in su.get("trigger_tags", []) if t in EVENT_TAGS]
    resp = (su.get("response") or "").strip()
    if not (tags and resp):
        return None
    return ResponseSignature(signature_id=_next_signature_id(d), trigger_tags=tags,
                             response=resp[:200], occurrences=occurrences,
                             first_seen=today, last_seen=today, confidence=confidence,
                             evidence_dates=evidence_dates or [])


def merge_curator_output(d: TickerDossier, data: dict, today: str, outcome_link: str = "") -> None:
    """Deterministic, bounded application of curator-shaped LLM output. Mutates d.

    Shared by DossierCurator._merge (daily review, hit/miss outcome_link) and
    EventIngestor.run (weekly/on-demand event digestion, outcome_link="").
    """
    from core.config import settings

    # 1. Observations — top-N by materiality, valid tags only, cap total buffer.
    cands = []
    for o in data.get("new_observations", []):
        text = (o.get("observation") or "").strip()
        if not text:
            continue
        cands.append(DossierObservation(
            date=today, observation=text[:300],
            tags=[t for t in o.get("tags", []) if t in EVENT_TAGS],
            materiality=max(0.0, min(1.0, float(o.get("materiality", 0.5)))),
            outcome_link=outcome_link,
            # F3 provenance — supplied by the research loop, absent from daily
            # curator output (its evidence is the whole day, not one article).
            source=(o.get("source") or "")[:120]))
    cands.sort(key=lambda o: o.materiality, reverse=True)
    d.observations.extend(cands[: settings.DOSSIER_MAX_NEW_OBS_PER_DAY])
    if len(d.observations) > settings.DOSSIER_MAX_OBSERVATIONS:
        d.observations = d.observations[-settings.DOSSIER_MAX_OBSERVATIONS:]

    # 2. Signature updates.
    by_id = {s.signature_id: s for s in d.response_signatures}
    for su in data.get("signature_updates", []):
        action = su.get("action")
        if action == "confirm" and su.get("signature_id") in by_id:
            s = by_id[su["signature_id"]]
            s.occurrences += 1
            s.confidence = min(0.95, round(s.confidence + 0.05, 4))
            s.last_seen = today
            s.evidence_dates = (s.evidence_dates + [today])[-10:]
        elif action == "contradict" and su.get("signature_id") in by_id:
            s = by_id[su["signature_id"]]
            s.contradictions += 1
            s.confidence = max(0.0, round(s.confidence - 0.10, 4))
        elif action == "create":
            sig = _make_signature(d, su, today, occurrences=1, confidence=0.5,
                                   evidence_dates=[today])
            if sig:
                d.response_signatures.append(sig)

    # 3. Guidance.
    for gu in data.get("guidance_updates", []):
        action, text = gu.get("action"), (gu.get("guidance") or "").strip()
        if action == "add" and text:
            d.guidance.append(GuidanceItem(
                date=today, source=(gu.get("source") or "market context")[:80],
                guidance=text[:200]))
        elif action in ("met", "missed", "withdrawn") and text:
            for g in d.guidance:
                if g.status == "open" and text.lower() in g.guidance.lower():
                    g.status = action
    d.guidance = d.guidance[-20:]

    # 4. Catalysts (add-only daily; hit_rate is distillation's job).
    known = {c.name.lower() for c in d.recurring_catalysts}
    for cu in data.get("catalyst_updates", []):
        name = (cu.get("name") or "").strip()
        if cu.get("action") == "add" and name and name.lower() not in known:
            d.recurring_catalysts.append(RecurringCatalyst(
                name=name[:80],
                typical_timing=(cu.get("typical_timing") or "")[:60],
                expected_effect=(cu.get("expected_effect") or "")[:120]))
    d.recurring_catalysts = d.recurring_catalysts[:10]

    # 5. Thesis + flows.
    if data.get("thesis_update"):
        d.current_thesis = str(data["thesis_update"])[:400]
        d.thesis_since = today
    if data.get("flow_note"):
        d.flow_notes = str(data["flow_note"])[:300]

    # 6. Open questions.
    for qu in data.get("open_question_updates", []):
        q = (qu.get("question") or "").strip()
        if qu.get("action") == "raise" and q:
            if all(q.lower() != ex.question.lower() for ex in d.open_questions):
                d.open_questions.append(OpenQuestion(question=q[:200], raised_on=today))
        elif qu.get("action") == "resolve" and q:
            for ex in d.open_questions:
                if not ex.resolved_on and q.lower() in ex.question.lower():
                    ex.resolved_on = today
                    ex.answer = (qu.get("answer") or "")[:200]
    d.open_questions = d.open_questions[-12:]


class DossierCurator:
    """LLM client pattern mirrors FeedbackAgent (json_object, low temp, retry-free)."""

    def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        from core.config import settings
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
            record_llm_call("dossier_curator", settings.LLM_MODEL_BULK, 0, 0,
                            int((time.time() - t0) * 1000), False)
            raise
        usage = getattr(resp, "usage", None)
        record_llm_call("dossier_curator", settings.LLM_MODEL_BULK,
                        getattr(usage, "prompt_tokens", 0) or 0,
                        getattr(usage, "completion_tokens", 0) or 0,
                        int((time.time() - t0) * 1000), True)
        return resp.choices[0].message.content or ""

    # ------------------------------------------------------------------

    def run(self, dossier: TickerDossier, entry, market_context: str,
            fb_output) -> TickerDossier:
        """Extract today's knowledge. On ANY failure, returns dossier unchanged."""
        from core.config import settings
        try:
            system = CURATOR_SYSTEM_PROMPT.format(
                ticker=dossier.ticker, sector=dossier.sector,
                event_tags=", ".join(sorted(EVENT_TAGS)))
            user = CURATOR_USER_TEMPLATE.format(
                date=entry.date,
                predicted_close=entry.predicted_close,
                actual_close=entry.actual_close,
                price_error_pct=entry.price_error_pct,
                direction_correct=entry.direction_correct,
                miss_type=(entry.miss_analysis.miss_type
                           if getattr(entry, "miss_analysis", None) else "n/a (hit)"),
                market_context=(market_context or "unavailable")[:4000],
                missed_factors=(fb_output.missed_factors if fb_output else []),
                over_weighted_factors=(fb_output.over_weighted_factors if fb_output else []),
                dossier_digest=dossier.to_digest(settings.DOSSIER_DIGEST_MAX_CHARS),
            )
            raw = self._call_llm(system, user)
            data = json.loads(_strip_think(raw))
            updated = dossier.model_copy(deep=True)
            self._merge(updated, data, entry)
            return updated
        except Exception as exc:
            logger.warning("[DossierCurator] non-fatal failure for %s on %s: %s",
                           dossier.ticker, getattr(entry, "date", "?"), exc)
            return dossier

    # ------------------------------------------------------------------

    def _merge(self, d: TickerDossier, data: dict, entry) -> None:
        """Deterministic, bounded application of curator output. Mutates d.

        Thin delegate to the module-level merge_curator_output (shared with
        EventIngestor) — preserves the hit/miss outcome_link derived from `entry`.
        """
        today = entry.date
        outcome = "hit" if entry.direction_correct else "miss"
        merge_curator_output(d, data, today, outcome_link=outcome)


def distill_dossier(dossier: TickerDossier) -> TickerDossier:
    """Weekly consolidation: episodic observations → durable sections.

    LLM pass when available; static fallback (dead-signature drop + buffer cap)
    when not. Never raises.
    """
    from core.config import settings
    d = dossier.model_copy(deep=True)

    # Static hygiene runs in BOTH paths.
    d.response_signatures = [s for s in d.response_signatures if s.is_alive]
    if len(d.observations) > settings.DOSSIER_MAX_OBSERVATIONS:
        d.observations = d.observations[-settings.DOSSIER_MAX_OBSERVATIONS:]

    try:
        curator = DossierCurator()
        system = DISTILL_SYSTEM_PROMPT.format(
            ticker=d.ticker, sector=d.sector, event_tags=", ".join(sorted(EVENT_TAGS)))
        raw = curator._call_llm(
            system, json.dumps(d.model_dump(), default=str)[:settings.DOSSIER_DISTILL_INPUT_MAX_CHARS])
        data = json.loads(_strip_think(raw))

        if data.get("business_summary"):
            d.business_summary = str(data["business_summary"])[:500]
        if data.get("flow_notes"):
            d.flow_notes = str(data["flow_notes"])[:300]
        fold = set(data.get("observations_to_fold", []))
        if fold:
            d.observations = [o for o in d.observations if o.date not in fold]
        today = _date.today().isoformat()
        by_id = {s.signature_id: s for s in d.response_signatures}
        for su in data.get("signature_updates", []):
            action = su.get("action")
            if action == "drop" and su.get("signature_id") in by_id:
                d.response_signatures = [s for s in d.response_signatures
                                         if s.signature_id != su["signature_id"]]
            elif action == "create":
                # Distill-created signatures start at occurrences=2/confidence=0.55 because
                # they fold a repeated observed pattern (not a single new occurrence).
                sig = _make_signature(d, su, today, occurrences=2, confidence=0.55)
                if sig:
                    d.response_signatures.append(sig)
        rates = {r.get("name", "").lower(): r.get("hit_rate", "")
                 for r in data.get("catalyst_hit_rates", [])}
        for c in d.recurring_catalysts:
            if c.name.lower() in rates and rates[c.name.lower()]:
                c.hit_rate = str(rates[c.name.lower()])[:40]
        for stale in data.get("stale_guidance", []):
            for g in d.guidance:
                if g.status == "open" and str(stale).lower() in g.guidance.lower():
                    g.status = "withdrawn"
        for rq in data.get("resolved_questions", []):
            qtext = (rq.get("question") or "").lower()
            for q in d.open_questions:
                if not q.resolved_on and qtext and qtext in q.question.lower():
                    q.resolved_on = today
                    q.answer = (rq.get("answer") or "")[:200]
        d.version += 1
    except Exception as exc:
        logger.warning("[distill_dossier] LLM pass failed for %s — static fallback only: %s",
                       d.ticker, exc)
    return d
