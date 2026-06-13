# Research Loop — Active Open-Question Resolution (RL Phase 4)

**Date:** 2026-06-13
**Status:** DRAFT
**Depends on:** Dossier knowledge layer (Phase 0) + event ingestion (Phase 3) — both live.

---

## 1. Problem

Dossier `open_questions` are raised by the daily DossierCurator (miss-day unknowns) and
the weekly EventIngestor (forward-looking guidance checks), but nothing ever goes
*looking* for answers. Resolution today is opportunistic only: an answer must happen to
drift through a later day's market context (curator `resolve` action) or the weekly
distillation. Questions can sit open indefinitely while occupying the digest's
"Open questions" section (top 4 injected into every forecast prompt).

Live example: MARUTI's "management guided ~1% growth FY27 — do monthly dispatch numbers
confirm?" has no path to resolution unless dispatch numbers coincidentally appear in a
daily review context.

## 2. Goal

A weekly per-ticker research pass that selects the most promising unresolved open
questions, runs **targeted** searches crafted from the question text (not generic sector
news), judges via one LLM call whether the search answered each question, and writes
results back through the existing bounded merge. Questions that repeatedly find no
public signal expire instead of burning searches forever.

Bounded, flag-gated, never raises — exactly the EventIngestor pattern.

## 3. Schema change (`src/backend/shared/schemas/dossier.py`)

`OpenQuestion` gains two backward-compatible fields (defaults make old dossier JSON
load unchanged):

```python
class OpenQuestion(BaseModel):
    question: str
    raised_on: str
    resolved_on: str = ""
    answer: str = ""
    attempts: int = 0        # NEW — research attempts that found no/partial signal
    last_attempt: str = ""   # NEW — ISO date of the most recent research attempt
```

No other schema changes. `to_digest()` is untouched.

## 4. Component — QuestionResearcher

New `core/intelligence/rl/agents/question_researcher.py`, mirroring EventIngestor's
structure (module-level pure helpers + a small class with `_call_llm` + `run`).

### 4.1 Selection (pure, deterministic, no LLM)

```python
def select_questions(dossier: TickerDossier, today: str, cap: int) -> list[OpenQuestion]
```

- Candidates: unresolved (`resolved_on == ""`) AND `attempts < RL_RESEARCH_MAX_ATTEMPTS`
  AND `last_attempt != today` (idempotent re-runs the same day).
- Order: fewest `attempts` first, then newest `raised_on` first (fresh questions get
  priority; stalled ones aren't starved because attempts dominate).
- Return at most `cap` (= `RL_RESEARCH_MAX_QUESTIONS_PER_RUN`, default 2).

### 4.2 Expiry (pure, deterministic)

```python
def expire_stale_questions(dossier: TickerDossier, today: str) -> int
```

- Any unresolved question with `attempts >= RL_RESEARCH_MAX_ATTEMPTS` (default 3) is
  resolved with `resolved_on=today`, `answer="expired: no public signal after N research
  attempts"`. Returns count expired. Runs at the START of each `run()` so the dossier
  digest stays clean even when selection finds nothing new.

### 4.3 Search (1 Serper per question, ≤1 Tavily fallback per run)

```python
def _search_question(ticker: str, company_name: str, question: str,
                     tavily_budget: list[int]) -> str
```

- Query = `f"{company_name or ticker} {question}"` truncated to 120 chars — the
  question text itself is the query; that is the whole point (targeted, not generic).
- One Serper news search via `services.data.fetchers.news.fetch_news_context`
  (`max_queries=1`) — same client as preopen_check.
- If the result is empty or a `"[No results"` placeholder AND the run's Tavily budget
  (1 per ticker run, tracked via the mutable `tavily_budget` cell) is unspent: one
  `fetch_tavily_context([query], max_queries=1, max_results_per_query=1)` fallback.
- Returns the combined text truncated to `RL_RESEARCH_CONTEXT_MAX_CHARS` (default 6000).
  Company name comes from `symbol_resolver`'s learned cache helper (same one
  base_orchestrator uses) — failure → ticker string, never raises.

### 4.4 Judgment (ONE LLM call per ticker run, all questions batched)

New prompt module `core/config/prompts/shared/question_researcher.py`. One
`settings.LLM_MODEL` call (json_object, temp 0.2, max_tokens 900 — same client pattern
as DossierCurator/EventIngestor `_call_llm`):

System prompt rules: grounded in the provided search context only; never invent
numbers; quantified answers preferred; `status` definitions:
- `answered` — the context contains a direct, citable answer.
- `partial` — the context narrows it but doesn't settle it; `finding` holds what was
  learned.
- `no_signal` — nothing relevant found.

Contract (all keys required):

```json
{
  "results": [
    {"question": "<verbatim question text>",
     "status": "answered|partial|no_signal",
     "answer": "",
     "finding": "",
     "tags": ["..."]}
  ]
}
```

`tags` must come from EVENT_TAGS (same vocabulary as the curator).

### 4.5 Write-back (reuses `merge_curator_output` — no new merge code)

Map LLM results into a curator-shaped dict and apply via the SAME
`merge_curator_output(dossier, data, today, outcome_link="")`:

- `answered` → `open_question_updates: [{"action": "resolve", "question": q,
  "answer": ...}]` **plus** `new_observations: [{"observation": "[research] " + answer,
  "tags": [...], "materiality": 0.6}]` so the finding enters the episodic buffer too.
- `partial` → `new_observations` only (`"[research-partial] " + finding`,
  materiality 0.4); question stays open; `attempts += 1`.
- `no_signal` → nothing merged; `attempts += 1`.
- ALL attempted questions get `last_attempt = today` (set directly on the schema —
  attempts/last_attempt bookkeeping is outside the merge by design; merge stays
  curator-shaped).
- Defensive matching: LLM `question` text matched to selected questions
  case-insensitively by substring (same convention `merge_curator_output` already uses
  for resolve); unmatched results dropped.

### 4.6 Runner

```python
class QuestionResearcher:
    def run(self, ticker: str, sector: str) -> dict:
        """Expire -> select -> search -> judge -> merge -> save.
        Returns {"selected": n, "answered": n, "partial": n, "expired": n}.
        NEVER raises. Flag off or no dossier or no open questions -> zeros, no
        searches, no LLM call, no save (except: expiry alone still saves)."""
```

- Gate: `RL_RESEARCH_LOOP_ENABLED` (default true).
- No dossier file → zeros (research never creates a dossier).
- Save only when something changed (expiry, resolve, observation, or attempts bump).

## 5. Scheduling + CLI

- Scheduler job `research_loop_weekly` in `services/scheduler/python/scheduler.py`:
  **Saturdays 11:00 IST** — one hour after `event_ingest_weekly` (10:00), so questions
  raised by that morning's filings ingestion are immediately researchable. Same
  ticker-discovery loop and per-ticker non-fatal style as `_event_ingest_job`. Gated on
  the flag at registration AND inside the job.
- CLI: `python -m services.scheduler.run_schedule research [--ticker TICKER]` —
  mirrors `ingest-events` (all managed tickers with dossiers, or one). ASCII-only output
  (Windows cp1252 console).

## 6. Settings (`src/backend/shared/config/settings/base.py`)

| Setting | Default |
|---|---|
| `RL_RESEARCH_LOOP_ENABLED` | `true` |
| `RL_RESEARCH_MAX_QUESTIONS_PER_RUN` | `2` |
| `RL_RESEARCH_MAX_ATTEMPTS` | `3` |
| `RL_RESEARCH_CONTEXT_MAX_CHARS` | `6000` |

## 7. Cost ceiling

Per ticker per week: ≤2 Serper + ≤1 Tavily fallback + exactly 1 LLM call (0 of each
when no open questions). 4 active tickers → ~8 Serper + ~4 LLM calls/week ≈ negligible
against the 50k Serper credit pool.

## 8. Safety

- Flag off → byte-identical behavior, zero I/O.
- `run()` never raises; per-question search failures degrade to `no_signal`.
- All dossier mutation bounds enforced by the existing `merge_curator_output`
  (observation caps, answer 200 chars, question-list cap 12).
- Old dossiers (no attempts/last_attempt fields) load via pydantic defaults — verified
  by test against the on-disk MARUTI dossier shape.

## 9. Validation

TDD suite `tests/unit/intelligence/rl/test_question_researcher.py`:
- selection: ordering (attempts asc, raised_on desc), cap, excludes resolved/maxed/
  already-attempted-today.
- expiry: at-cap questions resolved with expiry answer; count returned; under-cap
  untouched.
- run(): flag off → zeros + no store I/O (mock); no dossier → zeros; no open questions
  → zeros, no LLM; answered → question resolved + observation added + saved; partial →
  attempts+1, observation, still open; no_signal → attempts+1 only; LLM garbage →
  attempts+1 (degrades to no_signal), never raises; cost cap (mock: ≤2 news fetches,
  ≤1 Tavily, exactly 1 LLM call); unmatched LLM question text dropped.
- schema: OpenQuestion without new fields parses (backward compat).
- scheduler/CLI: job registered when flag on, skipped when off; CLI smoke via
  monkeypatched researcher.

Live verification: `run_schedule research --ticker MARUTI` against the real dossier
(it has the FY27-guidance question) — show selection, real search, judgment, and the
dossier diff; suite green.

## 10. Not in scope

LLM-crafted search queries (question text is the query — revisit only if live quality
is poor); researching guidance items (they have their own met/missed flow); Phase 2
signature validation; any change to daily review.

## 11. File map

| File | Change |
|---|---|
| `src/backend/shared/schemas/dossier.py` | OpenQuestion + attempts/last_attempt |
| `core/intelligence/rl/agents/question_researcher.py` | NEW — selection, expiry, search, judge, run |
| `core/config/prompts/shared/question_researcher.py` | NEW — system + user prompts |
| `services/scheduler/python/scheduler.py` | `research_loop_weekly` job (Sat 11:00 IST) |
| `services/scheduler/run_schedule.py` | `research` subcommand |
| `src/backend/shared/config/settings/base.py` | 4 settings |
| `tests/unit/intelligence/rl/test_question_researcher.py` | NEW — full TDD suite |
