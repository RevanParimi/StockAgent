# Research Loop (RL Phase 4) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Weekly per-ticker pass that actively researches dossier open_questions via targeted Serper/Tavily searches + one batched LLM judgment, writing results back through the existing bounded merge; stale questions expire.

**Architecture:** Mirror EventIngestor exactly — module-level pure helpers + small class with `_call_llm` + never-raises `run()`; reuse `merge_curator_output` for ALL dossier mutation except attempts/last_attempt bookkeeping. Spec: `docs/superpowers/specs/2026-06-13-research-loop-design.md` (authoritative for every contract).

**Tech Stack:** Python, pydantic, pytest (unit, fully mocked LLM/search), APScheduler job, argparse CLI.

**Branch:** main directly (user-authorized). Run tests with `$env:PYTHONPATH=".;src"`.

---

### Task 1: Schema fields, settings, pure selection + expiry logic

**Files:**
- Modify: `src/backend/shared/schemas/dossier.py` (OpenQuestion)
- Modify: `src/backend/shared/config/settings/base.py` (4 settings, next to the RL_EVENT_INGEST block)
- Create: `core/intelligence/rl/agents/question_researcher.py` (pure parts only)
- Create: `tests/unit/intelligence/rl/test_question_researcher.py`

- [ ] **Step 1:** Write failing tests for: OpenQuestion backward compat (dict WITHOUT attempts/last_attempt parses, defaults 0/""); `select_questions` ordering (attempts asc then raised_on desc), cap respected, excludes resolved / attempts>=max / last_attempt==today; `expire_stale_questions` resolves at-cap questions with answer `"expired: no public signal after {N} research attempts"`, returns count, leaves under-cap untouched.
- [ ] **Step 2:** Run, verify FAIL (functions missing).
- [ ] **Step 3:** Implement: add `attempts: int = 0` and `last_attempt: str = ""` to OpenQuestion; add settings `RL_RESEARCH_LOOP_ENABLED=true`, `RL_RESEARCH_MAX_QUESTIONS_PER_RUN=2`, `RL_RESEARCH_MAX_ATTEMPTS=3`, `RL_RESEARCH_CONTEXT_MAX_CHARS=6000` (os.getenv pattern identical to EVENT_INGEST block); create question_researcher.py with module docstring + `select_questions(dossier, today, cap)` and `expire_stale_questions(dossier, today)` per spec §4.1/§4.2 (read settings inside functions via `from core.config import settings`).
- [ ] **Step 4:** Run tests → PASS. Run the dossier schema + curator suites too (`pytest tests/unit/intelligence/rl/test_dossier_schema.py tests/unit/intelligence/rl/test_dossier_curator.py -q`) → no regressions.
- [ ] **Step 5:** Commit `feat(rl-research): OpenQuestion attempt tracking + selection/expiry logic`.

### Task 2: Prompts + QuestionResearcher search/judge/merge/run

**Files:**
- Create: `core/config/prompts/shared/question_researcher.py`
- Modify: `core/intelligence/rl/agents/question_researcher.py`
- Modify: `tests/unit/intelligence/rl/test_question_researcher.py`

- [ ] **Step 1:** Write failing tests (mock `fetch_news_context`, `fetch_tavily_context`, `_call_llm`, PredictionStore): flag off → zeros + zero store/search/LLM calls; no dossier → zeros; open questions empty but one at-cap → expiry still saves; answered → question resolved + `[research] ...` observation + saved; partial → attempts+1 + `[research-partial] ...` observation + question still open; no_signal → attempts+1 only; LLM garbage JSON → all attempted get attempts+1, never raises; cost caps (≤2 news fetches, ≤1 Tavily only when news placeholder, exactly 1 LLM call, 0 LLM when nothing selected); unmatched LLM question text dropped; last_attempt set on all attempted.
- [ ] **Step 2:** Run, verify FAIL.
- [ ] **Step 3:** Implement per spec §4.3–§4.6: prompt module (system rules: grounded-only, EVENT_TAGS vocabulary, status definitions; strict JSON contract `{"results": [...]}`; double-brace any literal braces for .format); `_search_question` (query = company/ticker + question, 120 chars; Serper via fetch_news_context max_queries=1; Tavily fallback only on empty/`[No results` and unspent budget; truncate to RL_RESEARCH_CONTEXT_MAX_CHARS); `QuestionResearcher._call_llm` copied from EventIngestor pattern (LLM_MODEL, temp 0.2, max_tokens 900, json_object); `run(ticker, sector)` = gate → load dossier (None → zeros) → expire → select → (nothing selected and nothing expired → zeros, no save) → search each → ONE batched LLM call → map results to curator-shaped dict → `merge_curator_output(dossier, data, today, outcome_link="")` → set attempts/last_attempt directly → save via PredictionStore only if changed → return counts dict. Company name: `from backend.shared.data.fetchers.symbol_resolver import ...` learned-cache helper used by base_orchestrator (`_company_name_for` equivalent — check symbol_resolver's public function, fall back to ticker on any failure). Never raises anywhere.
- [ ] **Step 4:** Run task tests + full `pytest tests/unit -q` → all green.
- [ ] **Step 5:** Commit `feat(rl-research): QuestionResearcher agent with batched judgment + bounded merge`.

### Task 3: Scheduler job + CLI subcommand

**Files:**
- Modify: `services/scheduler/python/scheduler.py` (Job: `research_loop_weekly`, Sat 11:00 IST)
- Modify: `services/scheduler/run_schedule.py` (`research` subcommand)
- Modify: `tests/unit/intelligence/rl/test_question_researcher.py` (or the existing scheduler-test file if one covers job registration — check `tests/unit` for how event_ingest job registration is tested and mirror it)

- [ ] **Step 1:** Write failing tests: job registered when `RL_RESEARCH_LOOP_ENABLED` true / absent when false (mirror existing event-ingest job tests if present; otherwise test the job function's flag gate + per-ticker isolation with a raising researcher mock).
- [ ] **Step 2:** Run, verify FAIL.
- [ ] **Step 3:** Implement: `_research_loop_job` copied from `_event_ingest_job` structure (same ticker discovery + `_sector_for`, per-ticker try/except, `_job_banner`, log counts); CronTrigger sat 11:00 Asia/Kolkata, id `research_loop_weekly`, misfire 3600, coalesce; registration gated on flag with the same log-line style as Job 9. CLI `cmd_research(args)` + `research` subparser with optional `--ticker` mirroring `cmd_ingest_events` exactly — ASCII-only prints (no rupee/arrow glyphs).
- [ ] **Step 4:** Run new tests + `pytest tests/unit -q` → green.
- [ ] **Step 5:** Commit `feat(rl-research): weekly scheduler job + research CLI subcommand`.

### Task 4 (controller-owned): Live verification + docs

- [ ] `$env:PYTHONPATH=".;src"; python -m services.scheduler.run_schedule research --ticker MARUTI` against the real dossier; inspect dossier diff (FY27 guidance question attempted/answered, attempts/last_attempt set, observations added).
- [ ] Update `docs/RL_DESIGN.md` (new §28 Research Loop), brief mentions in README.md/CODEBASE.md where the other weekly jobs are listed; flip spec status to IMPLEMENTED with live evidence.
- [ ] Full suite green; push to main.
