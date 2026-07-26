# Atlas M1 Data-Architecture — Reviewer Memo (Task B3)

> **Role:** Reviewer pass of the Atlas Phase-B 3-agent loop (Researcher → Designer → **Reviewer**).
> The reviewer drives the loop to **APPROVED** ([[feedback-3agent-loop]]); genuine
> user-judgment calls are routed to the B4 ratification gate rather than decided here.
> **Date:** 2026-07-26 · **Branch:** `atlas-b` (docs only) · **Under review:**
> `docs/superpowers/specs/2026-07-26-m1-data-architecture-design.md` (Task B2), against the
> Researcher memo, `docs/SCALING_BLUEPRINTS.md` (BP1/2/4/5 + R1–R4), `docs/LEGAL_AND_COMPLIANCE.md`.
> **Method:** every load-bearing code claim in the spec was re-checked against source, not trusted.

---

## Verification log (what the reviewer checked in code)

| Spec claim | Check | Result |
|---|---|---|
| App runs SQLite on the volume; "second process" is the future trigger (§1) | `Dockerfile:47` | **`uvicorn … --workers 2`** — two API-writer processes exist **today** → Finding **R1** |
| R1 "Enforced by the **existing** import-boundary test" (spec §Learning-Constitution; memo l.135) | grep tests for import-boundary / ast-walk / "must not import" | **No such test exists.** Blueprint only *prescribes* it in the "Enforced how" column (`SCALING_BLUEPRINTS.md:231`) → Finding **R2** |
| Outbox worker "in-process (a thread/async loop draining outbox)" (§8) | `server.py:306-388` | Lifespan runs in **every** worker; a localhost-socket **singleton lock** already exists because "every cron job fired twice" pre-guard → Finding **R3** |
| `demand_score = 3·holders + 1·watchers + 0.5·chat_hits_7d` (§4) | `llm_calls` schema (memo #7); `chat_turns` schema (A2) | Neither carries `(symbol, ts)` — `chat_hits_7d` has **no source** → Finding **R4** |
| DPDP delete cascade (§Learning-Constitution/DPDP) | DDL FK actions | telemetry anonymized, `feedback_events` hard-cascaded — asymmetric, unjustified → Finding **R5** |
| `advisor.py:21` imports `PredictionStore`; 3-call surface | `advisor.py:19-24`, `prediction_store.py` | **Confirmed** exactly as documented (facade design is sound) |
| `delete_user` clears only sessions/chat_usage/users | `user_store.py:169-175` | **Confirmed** (DPDP gap real; spec closes it correctly) |
| Intelligence plane user-free | memo Part 3 grep | **Confirmed** — R1 holds *by construction* today (but see R2 re: enforcement) |

---

## Findings

### R1 — [Correction · Medium] Migration-trigger #1 points at an event that has already happened
`Dockerfile:47` runs `uvicorn --workers 2`. Two API-worker processes already write the same
SQLite files (signup/session, and — post-M1 — `add_holding` write-through, `chat_usage`,
`push_subscribe`, `feedback_events`), plus the scheduler-owner worker doing batch writes. So the
spec's primary Postgres trigger — *"the outbox worker becomes a **second Railway process** writing
`atlas.db` … This is the primary trigger"* (§1) and the risk line *"single-writer ceiling once a
**second process** writes the same DB"* — describes a condition that is **already true on day one**,
making the trigger un-monitorable.

The **conclusion is still correct** (SQLite is right for M1): `users.db` and `chat_sessions.db`
already run under `--workers 2` with WAL + `busy_timeout` and serialize fine at this scale. But the
deferred trigger must be reframed as a **measurable quantity** — sustained `SQLITE_BUSY` rate / p99
write latency under contention / write throughput — not "a second process appears."
**Required:** rewrite trigger #1 so it can actually be watched.

### R2 — [Factual error · Medium-High] The "existing import-boundary test" does not exist
Spec §Learning-Constitution: *"Enforced by the **existing** import-boundary test … Phase C
**extends** it to name `services/data/verdict_store.py` and `feedback_events` as forbidden imports."*
Researcher memo l.135 repeats *"Enforced by import-boundary test."* **Verified false:** no test in
`tests/` walks `core/intelligence/` imports or asserts a forbidden-import set. `SCALING_BLUEPRINTS.md:231`
lists the import-boundary check only in its **"Enforced how"** column — a *prescription*, not an
existing artifact. Today R1 holds **by construction** (memo Part 3 grep: zero tenant-identity refs in
`core/intelligence/`), i.e. by discipline, not by an automated guard.

This matters because R1 is the spec's central safety guarantee for the entire plane boundary, and the
spec leans on this test as R1's enforcement. **Required:** correct both docs (drop "existing" /
"extends"); make **"create the import-boundary test"** an explicit Phase C task — an AST/import walk
asserting `core/intelligence/**` imports none of {`services/data/verdict_store.py`, the feedback
store, `atlas.db`/user stores}. Ship it *with* the VerdictStore, so the boundary is enforced the
moment the facade lands.

### R3 — [Concurrency gap · Medium] In-process outbox worker double-fires under `--workers 2`
§8 defers the BP2 service split and runs the outbox drainer "in-process (a thread/async loop)."
But the FastAPI lifespan executes in **every** uvicorn worker (`server.py:307`), and this app has
**already been bitten** by exactly this: pre-guard, "every cron job fired twice," which is why
`server.py:306-388` binds a localhost socket so only **one** worker runs the scheduler/self-heal.
An unguarded outbox drainer in both workers would **double-send** pushes/emails. The `dedupe_key`
UNIQUE constraint prevents duplicate *rows* — it does **not** prevent two workers both `SELECT`-ing
the same `queued` row and POST-ing it before either flips `status`.
**Required:** the spec must name the mechanism — run the drainer **only in the existing
singleton-lock owner** (reuse `server.py`'s guard), and/or claim each row with an atomic
compare-and-swap (`UPDATE outbox SET status='sending' WHERE id=? AND status='queued'`, act only if
`rowcount==1`). Either is cheap; leaving it unspecified invites duplicate deliveries.

### R4 — [Design gap · Medium] `chat_hits_7d` has no data source
The demand formula weights `chat_hits_7d` at 0.5, but nothing stores per-symbol chat mentions:
`llm_calls` has no `symbol` column (memo #7) and `chat_turns` is free-text `content` only. "chat_hits_7d
from telemetry/chat mentions" (§4) is **not implementable** against the current schema.
**Required:** either (a) specify the source — a small `(symbol, user_id, ts)` tap written when chat
resolves a ticker (the NSE-first resolver already identifies the symbol) — or (b) default
`chat_hits_7d = 0` for M1 and defer the tap to a named follow-up. As written, one-third of the
demand score is undefined; pick one and say so. (Recommend (b) for M1 — holders/watchers alone drive
cadence adequately at ≤1k users; the chat tap is a clean M1.x add.)

### R5 — [Compliance consistency · Medium → route to B4] Asymmetric DPDP delete: telemetry anonymized, feedback hard-deleted
On user delete the spec **anonymizes** telemetry (`llm_calls.user_id → NULL`, preserving aggregate
cost) but **hard-cascades** `feedback_events` (FK `ON DELETE CASCADE`). Both retain aggregate value
after the user is gone: `feedback_events` feeds R4's standing bias audit and the eventual R2 universe
ranking. The spec justifies the telemetry choice but is silent on why feedback is treated oppositely,
and the B4 open-questions list raises telemetry (Q3) but **omits feedback_events**.
Hard-delete is *defensible* (feedback is behavioral PII, arguably more sensitive than a token count) —
but it's a genuine privacy-vs-learning-value judgment, not an implementation detail.
**Required:** state the default + rationale in the spec, and **add feedback_events delete policy to the
B4 gate** as an explicit question alongside telemetry.

### R6 — [Polish · Low] Two small items
- **(a) `invites` FK asymmetry.** `created_by ON DELETE CASCADE` contradicts the audit intent that
  motivated `used_by ON DELETE SET NULL`: deleting a *member who created invites* erases invite rows
  whose `used_by` still points to **existing** members, destroying their join-audit edge. Align
  `created_by` to `ON DELETE SET NULL` (keep the row, null the creator) — or justify the asymmetry.
- **(b) R2 citation for `instruments` aggregates.** `instruments` now carries user-derived
  `holders/watchers/demand_score`, read by the scheduler to pick cadence — the design's closest
  approach to the R1 line. It **is** permitted (R2: *"aggregates … may rank the universe (Blueprint
  1's demand score)"*, `SCALING_BLUEPRINTS.md:232`), but the spec should cite R2 explicitly for the
  demand→cadence path and state these counts never enter reward/scorecard/envelope math, so a future
  reader can't mistake universe-ranking for a reward-path leak.

---

## What the review did **not** find wrong (accepted as designed)
- **Store engine = SQLite `atlas.db`, FKs on.** Correct — integrity is a schema gap, not an engine
  gap; portable SQL keeps Postgres open; $0/mo (accurate — no addon, no new service).
- **VerdictStore facade duck-typing the 3-call surface.** Verified against `advisor.py`/
  `prediction_store.py`; the one-line advisor swap claim holds. Dependency points user→intelligence.
- **`user_instruments` membership-only (no economics).** Right call — `portfolio.json` stays the one
  money SoT; avoids dual-write drift.
- **Freeze-cutover, weekend, `ATLAS_ENABLED` flag, ETL deletes nothing, instant rollback.** Sound for
  a 0-user/1-`primary`-dir dataset; `active_user_ids()` fixes ghost-dir autopilot (finding #6) and
  preserves the anonymous⇒owner path.
- **DPDP single-cascade** honestly scoped (relational core = one transaction; 3 non-`atlas` artifacts
  = idempotent follow-ups in the same function).
- **Ghost-dir `primary`→owner / others→quarantine.** No silent adoption of strangers. Good.

---

## Verdict

**Round 1: CHANGES REQUESTED** — findings R1–R6. None sink the architecture; all are corrections /
specifications the Designer can close in-loop, except R5's policy call, which is routed to B4.

**Round 2 (after Designer revisions applied to the spec — same session):**
- R1 fixed — trigger #1 reframed to measurable `SQLITE_BUSY`/latency/throughput; "already-2-workers"
  fact stated; SQLite-still-correct rationale (users.db/chat_sessions.db already multi-worker) added.
- R2 fixed — "existing"/"extends" removed; **create the import-boundary test** added as a Phase-C
  requirement and to the R1-compliance section; "R1 holds by construction today" stated honestly.
- R3 fixed — outbox drainer pinned to the singleton-lock owner **and** atomic claim CAS specified.
- R4 fixed — `chat_hits_7d = 0` for M1 (deferred tap named); demand formula annotated.
- R5 addressed — default (hard-delete, behavioral PII) stated with rationale; **B4 Q5 added** for the
  privacy-vs-learning judgment.
- R6 fixed — `invites.created_by → ON DELETE SET NULL`; R2 citation added for `instruments` aggregates.

**→ APPROVED for the B4 user-ratification gate.** The residual user-judgment surface at B4 is now:
D2 (verdict-store writer direction), §4 (universe recompute plane), Q3 (telemetry anonymize vs
hard-delete), Q4 (`invites.used_by` retention), **Q5 (feedback_events delete policy — new)**.
Phase C is **not** appended until the user approves (per plan: B4 does not start Phase C in the same
session).
