"""
TickerDossier — per-ticker living knowledge document (RL knowledge layer).

Persisted as data/predictions/{sector}/{TICKER}/{TICKER}_dossier.json (PERMANENT).
Updated daily by DossierCurator (Step 8.5 of daily review), consolidated weekly
by distill_dossier(). Consumed as a markdown digest by the forecast agents and
the chat `get_ticker_dossier` tool. See spec 2026-06-11.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class DossierObservation(BaseModel):
    """One day's factual observation — the episodic buffer entry."""
    date: str
    observation: str
    tags: list[str] = Field(default_factory=list)
    materiality: float = Field(ge=0.0, le=1.0, default=0.5)
    outcome_link: str = ""            # "hit" | "miss" | ""


class ResponseSignature(BaseModel):
    """Quantified behavioral pattern: trigger → typical price response."""
    signature_id: str
    trigger_tags: list[str] = Field(default_factory=list)
    response: str
    occurrences: int = 1
    contradictions: int = 0
    first_seen: str = ""
    last_seen: str = ""
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    evidence_dates: list[str] = Field(default_factory=list)   # cap 10 at merge time

    @property
    def is_alive(self) -> bool:
        return self.contradictions < self.occurrences


class GuidanceItem(BaseModel):
    date: str
    source: str
    guidance: str
    status: str = "open"              # open | met | missed | withdrawn


class RecurringCatalyst(BaseModel):
    name: str
    typical_timing: str
    expected_effect: str
    hit_rate: str = ""


class OpenQuestion(BaseModel):
    question: str
    raised_on: str
    resolved_on: str = ""
    answer: str = ""


class TickerDossier(BaseModel):
    ticker: str
    sector: str
    created_at: str
    last_updated: str
    version: int = 1
    business_summary: str = ""
    current_thesis: str = ""
    thesis_since: str = ""
    response_signatures: list[ResponseSignature] = Field(default_factory=list)
    guidance: list[GuidanceItem] = Field(default_factory=list)
    recurring_catalysts: list[RecurringCatalyst] = Field(default_factory=list)
    flow_notes: str = ""
    open_questions: list[OpenQuestion] = Field(default_factory=list)
    observations: list[DossierObservation] = Field(default_factory=list)

    def to_digest(self, max_chars: int = 2500) -> str:
        """Markdown digest for prompt injection. Whole sections only, priority order.

        The header line is always included even if it alone exceeds max_chars —
        realistic budgets are far larger than a single header, so callers must
        not pass tiny budgets.
        """
        sections: list[str] = []
        if self.business_summary:
            sections.append(f"## Business\n{self.business_summary}")
        if self.current_thesis:
            since = self.thesis_since or self.created_at
            sections.append(f"## Thesis (since {since})\n{self.current_thesis}")
        live = sorted((s for s in self.response_signatures if s.is_alive),
                      key=lambda s: s.confidence, reverse=True)[:8]
        if live:
            lines = [f"- [{', '.join(s.trigger_tags)}] {s.response}"
                     f" (seen {s.occurrences}x, conf {s.confidence:.2f})" for s in live]
            sections.append("## Response signatures\n" + "\n".join(lines))
        open_g = [g for g in self.guidance if g.status == "open"][-5:]
        if open_g:
            sections.append("## Open guidance\n" + "\n".join(
                f"- {g.date} ({g.source}): {g.guidance}" for g in open_g))
        if self.recurring_catalysts:
            sections.append("## Recurring catalysts\n" + "\n".join(
                f"- {c.name} ({c.typical_timing}): {c.expected_effect}"
                + (f" [hit rate {c.hit_rate}]" if c.hit_rate else "")
                for c in self.recurring_catalysts[:6]))
        if self.flow_notes:
            sections.append(f"## Institutional flows\n{self.flow_notes}")
        open_q = [q for q in self.open_questions if not q.resolved_on][:4]
        if open_q:
            sections.append("## Open questions\n" + "\n".join(
                f"- {q.question} (since {q.raised_on})" for q in open_q))
        if self.observations:
            recent = sorted(self.observations, key=lambda o: o.date)[-5:]
            sections.append("## Recent observations\n" + "\n".join(
                f"- {o.date}: {o.observation}" for o in recent))

        out = f"# {self.ticker} dossier (updated {self.last_updated}, v{self.version})"
        for sec in sections:
            if len(out) + len(sec) + 2 > max_chars:
                break
            out += "\n\n" + sec
        return out
