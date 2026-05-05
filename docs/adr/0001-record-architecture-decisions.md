# ADR 0001: Record Architecture Decisions

**Date:** 2026-05-05
**Status:** Accepted
**Author:** <TBD>

---

## Context

StockAgent is growing across multiple languages (Python, TypeScript, React, C++), multiple
sectors (Automobile, BFSI, IT, Renewable Energy), and multiple infrastructure concerns
(scheduling, persistence, LLM routing, RL feedback loops). Decisions that seem obvious in
the moment become hard to reconstruct six months later — especially when they involve
rejected alternatives or compliance constraints.

Without a record, the team re-litigates settled questions, makes changes that silently
contradict earlier choices, and loses the reasoning that would help evaluate future
proposals.

---

## Decision

We will record architecturally significant decisions as Architecture Decision Records (ADRs)
stored in `docs/adr/`.

An ADR is required for any change that meets one or more of these criteria:
- Reversing it would cost more than a week of work
- It changes a service boundary, data store, or external contract
- It has compliance implications (SEBI, data licensing, PII)
- It involves a technology choice where alternatives were seriously considered

ADRs are numbered sequentially (`0001`, `0002`, …) and named with a short slug
(`0002-langgraph-for-orchestration.md`). Numbers are never reused.

**ADR lifecycle:**

| Status | Meaning |
|--------|---------|
| Proposed | Under discussion; not yet binding |
| Accepted | Decision made; applies going forward |
| Superseded | Replaced by a later ADR (link to successor) |
| Deprecated | No longer applies; not replaced |

**Template for new ADRs:**

```markdown
# ADR NNNN: Title

**Date:** YYYY-MM-DD
**Status:** Proposed | Accepted | Superseded by ADRNNN | Deprecated
**Author:** <name>

## Context
What situation forced this decision? What constraints existed?

## Decision
What was decided, stated plainly.

## Alternatives considered
What else was on the table and why it was rejected.

## Consequences
What becomes easier, harder, or different as a result.
What tech debt or follow-on work is introduced.
```

---

## Alternatives considered

**No formal records:** Fast in the short term. Leads to "why did we do it this way?"
archaeology in every planning session. Rejected.

**Confluence / Notion pages:** Better discoverability for non-engineers, but adds an
external dependency and gets out of sync with the codebase. ADRs in-repo stay close to
the code they describe. Rejected for now; revisit if team grows beyond ~5 engineers.

**Inline code comments:** Too granular and invisible to anyone not reading that file.
Rejected for cross-cutting decisions.

---

## Consequences

- Every PR that changes service boundaries, data stores, or external contracts must include
  or reference an ADR. This is a team norm, not an automated gate (yet).
- ADRs accumulate over time and are never deleted — only superseded. History is intentionally
  preserved.
- The doc owner is responsible for ensuring the ADR index stays up to date. Index is
  maintained by directory listing; no separate index file required.
