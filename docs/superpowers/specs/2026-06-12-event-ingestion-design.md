# Event-Driven Dossier Ingestion — RL Phase 3

**Date:** 2026-06-12
**Status:** Design — approved direction (roadmap Phase 3)
**Depends on:** June-11 knowledge layer (TickerDossier, DossierCurator merge bounds) — IMPLEMENTED.

---

## 1. Problem

The dossier learns only through the daily prediction loop's market context. Real company
knowledge — management guidance from earnings calls, results commentary, investor
presentations — arrives as *events*, mostly quarterly, and is currently captured only if
a headline happens to surface in a daily news snippet. An analyst who "knows the company"
reads the filings and the call, not just the tape.

## 2. Goal

A flag-gated **event ingestor** that scans NSE corporate announcements for qualifying
events (results, concalls, guidance, investor presentations), enriches each with article
text, and digests them into the **existing dossier sections** (guidance, business
summary, recurring catalysts, observations, open questions) through the **same bounded
merge** the daily curator uses. Weekly scan + on-demand CLI. Zero new daily cost; a few
LLM calls per ticker per quarter.

## 3. Component 1 — Event scan (STATIC)

New `core/intelligence/rl/agents/event_ingestor.py`:

```python
QUALIFYING_KEYWORDS = (
    "result", "earnings", "concall", "conference call", "transcript", "guidance",
    "investor presentation", "investor meet", "analyst", "dividend",
    "board meeting outcome", "financial statement",
)

def find_qualifying_events(ticker: str, lookback_days: int) -> list[dict]
```
- Calls the existing `services.data.fetchers.nse_announcements.prefetch_nse_data(ticker)`
  and filters `announcements` + `board_meetings` items whose subject/description contains
  a qualifying keyword (case-insensitive) and whose date is within `lookback_days`.
- Dedup against the dossier watermark: `TickerDossier` gains
  `ingested_event_keys: list[str] = []` (rolling, cap 40) — key = `"{date}|{subject[:60]}"`.
  Already-ingested events are skipped.
- Returns at most `EVENT_INGEST_MAX_EVENTS_PER_SCAN` (default 3) newest-first.
- Pure filter logic must be a separately testable function
  (`_is_qualifying(subject: str) -> bool`).

## 4. Component 2 — Enrichment (existing clients, capped)

Per qualifying event, build a text bundle:
1. The announcement's own subject + description fields (free).
2. ONE Tavily full-page extraction via the existing
   `services.clients.tavily_fetcher.fetch_tavily_context` with query
   `"{company} {subject keywords} earnings guidance"` — reuse its built-in caching;
   skip silently when `TAVILY_API_KEY` empty or fetch fails.
Bundle truncated to `EVENT_INGEST_TEXT_MAX_CHARS` (6000). No Serper calls (keeps the
free-tier budget untouched); Tavily is capped at one page per event, ≤3 events per scan.

## 5. Component 3 — Digestion (LLM) + merge reuse

`EventIngestor` LLM step (same client pattern as DossierCurator: json_object, temp 0.2,
≤900 tokens, never raises). New prompts module
`core/config/prompts/shared/event_ingestor.py`. The LLM output contract is the **same
shape the daily curator emits** (so the existing bounded merge applies unchanged):

```json
{
  "event_tags_today": [],
  "new_observations": [{"observation": "...", "tags": ["earnings_event"], "materiality": 0.8}],
  "signature_updates": [],
  "guidance_updates": [{"action": "add|met|missed|withdrawn", "guidance": "...", "source": "Q4 FY26 earnings call"}],
  "catalyst_updates": [{"action": "add", "name": "...", "typical_timing": "...", "expected_effect": "..."}],
  "thesis_update": null,
  "flow_note": "",
  "open_question_updates": [{"action": "raise|resolve", "question": "...", "answer": "..."}],
  "business_summary_update": ""
}
```

- Merge: refactor `DossierCurator._merge(d, data, entry)` so its body is callable without
  a `FeedbackEntry` — extract module-level
  `merge_curator_output(d, data, today: str, outcome_link: str = "") -> None` in
  `dossier_curator.py`; `DossierCurator._merge` delegates to it (existing curator tests
  are the regression net). The ingestor calls `merge_curator_output(dossier, data,
  today=event_date, outcome_link="")`.
- One ingestor-specific extension handled OUTSIDE the shared merge:
  `business_summary_update` (non-empty → replaces `business_summary`, capped 500 chars —
  events like annual results are exactly when the business summary should refresh).
- Prompt rules: ground ONLY in the provided bundle; prefer quantified guidance
  ("FY27 dispatch growth 8-10%") over vague text; observation tags from EVENT_TAGS
  (typically `earnings_event` / `guidance_change`); never invent numbers.
- After each successful event digestion: append the event key to
  `ingested_event_keys` and `store.save_dossier(dossier)`.

```python
class EventIngestor:
    def run(self, ticker: str, sector: str, lookback_days: int | None = None) -> int:
        """Scan → enrich → digest → merge → save. Returns events ingested. NEVER raises."""
```

## 6. Component 4 — Surfaces

- **Scheduler**: new weekly job `event_ingest_weekly` (CronTrigger: Saturday 10:00 IST —
  after Friday's filings settle), gated `RL_EVENT_INGEST_ENABLED`, iterating managed
  tickers, non-fatal per ticker (mirror `ledger_cleanup_weekly`'s loop style).
- **CLI**: `python -m services.scheduler.run_schedule ingest-events
  [--ticker ...] [--days N]` — prints per-ticker `ingested: N events` + the dossier's
  guidance section after.

## 7. New settings (real file `src/backend/shared/config/settings/base.py`)

| Setting | Default | Controls |
|---|---|---|
| `RL_EVENT_INGEST_ENABLED` | `True` | Weekly scan job + ingestor |
| `EVENT_INGEST_LOOKBACK_DAYS` | `8` | Scan window (weekly cadence + margin) |
| `EVENT_INGEST_MAX_EVENTS_PER_SCAN` | `3` | LLM-call cap per ticker per scan |
| `EVENT_INGEST_TEXT_MAX_CHARS` | `6000` | Per-event bundle truncation |

## 8. Safety

- Flag off → byte-identical (no job, no schema behavior change; `ingested_event_keys`
  defaults `[]`).
- `EventIngestor.run` never raises; per-event failures skip that event only.
- All merge bounds enforced by the SAME code as the daily curator (no second merge
  implementation). Dossier saves atomic via existing store.
- Cost ceiling: ≤3 LLM calls + ≤3 Tavily pages per ticker per week, typically 0 on
  non-event weeks (scan itself is free NSE API).

## 9. Validation

- TDD: `_is_qualifying` cases; watermark dedup (same event not ingested twice; cap 40);
  enrichment skip when Tavily unavailable; merge-reuse parity (curator tests unchanged
  after `merge_curator_output` extraction); `business_summary_update` applied + capped;
  flag off → scheduler job no-op; CLI smoke.
- Live: `ingest-events --ticker MARUTI --days 30` against real NSE/Tavily/LLM — show
  events found, the dossier's guidance/business sections after, and that a rerun ingests
  0 (watermark).

## 10. Not in scope

- PDF/transcript-attachment parsing (Tavily page text is the source; PDFs later).
- Real-time event triggers (weekly + CLI only).
- Chat surfacing beyond what `get_ticker_dossier` already shows.

## 11. File map

| File | Change |
|---|---|
| `core/intelligence/rl/agents/event_ingestor.py` | NEW — scan, enrich, digest, run |
| `core/config/prompts/shared/event_ingestor.py` | NEW — digestion prompt |
| `core/intelligence/rl/agents/dossier_curator.py` | `merge_curator_output` extraction (behavior identical) |
| `src/backend/shared/schemas/dossier.py` | `ingested_event_keys: list[str] = []` (cap enforced at merge site) |
| `src/backend/shared/config/settings/base.py` | 4 settings |
| `services/scheduler/python/scheduler.py` | `event_ingest_weekly` job |
| `services/scheduler/run_schedule.py` | `ingest-events` subcommand |
| tests | `test_event_ingestor.py` (+ curator tests as regression net) |
