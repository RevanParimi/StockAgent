# Production assurance review — 2026-09-23

Scope: every open task board, cross-checked against what production actually does. The question
is where "done on paper" differs from "working in production", and which tricky parts need a close
watch. Read-only. The only production change this day was the reviewed `nse` pin fix
(`a2c19c9`, deployed 22:44 IST).

**Evidence labels.** **Measured** = observed today in production: the user-run volume probe,
filtered deployment and build logs, and deployment metadata. **Code** = read in source at
`a2c19c9`. **Inferred** = reasoning over the two. **User-reported** = stated by the owner, not
verified independently. Raw output stays in ignored `analysis_data/`. This file holds counts only.

## 1. The boards

| Board | State | Notes |
|---|---|---|
| PI-2026-09 (Three Loops) | DOC-001 `review_required`; **32 SA stories `todo`, 0 accepted** | Ready now (no dependencies): SA-001, SA-002, SA-004, SA-005, SA-006, SA-007, SA-009, SA-010. `production_verification` is `not_started` everywhere. |
| PI Prospect (IPO) | Sprints 1–4 built; Sprint 5 (`IPO-5a`/`5b`) not started | `IPO-0a` open and must stay open (§2.1). `IPO-0c` has a measured counter, and the decision is the owner's. The definition-of-done line "a T−1 deep dive runs unattended for a real issue and produces a sourced, structured analysis" is **not met**: the first real run stored nothing. |
| Production milestones (`config/milestones.yaml`) | **8 of 9 past deadline** | See §1.1. Each lapsed entry re-raises a `critical` alert every 7 days, which trains the operator to ignore critical alerts. |

The August card board (A1–E5, including D6) is already mapped onto SA stories in the PI README,
so it is not a separate board.

### 1.1 Lapsed production-verification milestones

| Milestone (deadline) | What is actually left | Recommendation |
|---|---|---|
| `atlas_c11_cutover` (08-23) | Nothing. `atlas.enabled: true`, and its check self-satisfies (**code**). | Delete the entry. |
| `a1_routing_prod_verify` (09-08) | Part (b): no new `automobile` prediction stub for a non-automobile ticker. Needs a directory-count probe. | One probe, then close or hand to SA-009. |
| `b1_run_history_prod_verify` (09-15) | Only (b): `run_summaries` count survives a redeploy. **There were 4 redeploys today.** | One probe; easy to judge now. |
| `b2_data_health_prod_verify` (09-15) | Acceptances met on 26 Aug, but the entry itself says "DO NOT CLOSE AS HEALTHY" (card B6). | Close the milestone and carry B6 as SA-002 input. |
| `e1_error_capture_prod_verify` (09-15) | (a), (b), (d) closed; (c) "will not close as written". | Close with (c) marked not applicable. |
| `f3_checkpoint` (09-04) | Never judged: are `Lesson.evidence` and `DossierObservation.source` populated on real rows? | One probe. |
| `hard_bind_observation` (08-31) | Never judged: `direction_accuracy_7d` inflation review. | Fold into SA-012/SA-014; the audit already found the target defective. |
| `ipo_p0_live_window_check` (09-15) | Ledger capture was broken until tonight. | Keep open until capture is verified (§2.1). |
| `ipo_verdicts_visible_gate` (12-31) | In date. | — |

## 2. What production showed today

### 2.1 IPO — capture broken, now fixed but not yet verified

- **Measured.** Every bid-ladder fetch failed: `'NSE' object has no attribute '_req'` for VARMORA
  and four SME issues. The capture ledger has NSE rows to 19 Sep 07:00 UTC, SONA to 18 Sep 12:15,
  and VARMORA none. `nse` 4.0 (31 Aug) removed `_req`, and the 21 Sep image installed 4.0.1.
  **Fixed** by `a2c19c9` (`nse>=2.0.0,<4.0`); the new build installed 3.2.1.
- **User-reported:** 19–21 Sep coincided with the Hobby plan and undeployed commits.
- **Measured.** The refresh logged `degraded=False` while every ladder fetch failed. The 22 Sep
  brief showed category figures that were 2–3 days stale under "bidding closed" (NSE QIB 1.53×;
  final 12.68×), with no as-of marker.
- **Measured.** `ipo_deep_dive` ran once, at 19:01 on 23 Sep, for VARMORA: 16 docs, 9 extracted,
  `demand=None substance=None`, **not stored**. The 22 Sep deploy went live at 19:02, two minutes
  after that day's 19:00 slot, so the first run was missed.
- **Measured.** The P1 spine `data/ipo/ipo_history.jsonl` **does not exist in production**; only
  the manual `scripts/ipo_backfill.py` writes it.

### 2.2 Operations

| Area | Measured today | Status |
|---|---|---|
| Email (D6) | Since the 21 Sep redeploy: 8 email delivered, 0 dead (3 dead before it); push 11 delivered. One transient SMTP read timeout warning, which left no dead row. | **Closeable** |
| Brief / review | 08:50 brief `completed` (1 user); 16:30 review and portfolio pipeline `completed`; watchdog evaluated 17 checks. | Working |
| **Backup** | Nightly zip created (8.98 MB), but `emailed=False` and "no off-site copy landed". **The only copy is on the same volume.** | **At risk** — SA-007 |
| Learning loop | `WeightAdapter` adjusting weights in production daily. The audit's P0 finding says the grading target is wrong (KT §5). | **Live on a known-bad target** |
| Sector benchmark | `^CNXAUTO` "possibly delisted", 18× in the 16:30 review. The PI README calls D4's failures "older"; they are current. | SA-010 is live now |
| Instrument lifecycle | One ticker returns HTTP 404 at quoteSummary (4×). | SA-008 |
| LLM output | `ThesisReviewer` JSON parse errors (2×; unterminated string, i.e. truncation). Reviews are skipped silently. | Watch |
| Serper | Counter 2,590 in September against the default 2,500 budget. No alert fired. | Check serper.dev |

### 2.3 Systemic findings

1. **Unpinned runtime dependencies (code + measured).** 28 of 31 requirements are lower-bound
   only, and there is no lock file. The Docker pip layer is cached until `requirements.txt`
   changes, so versions shift only on an unrelated edit, in bulk, untested. Production ≠ local:
   `nse` 3.2.1 vs 2.1.3, `sentence-transformers` 6.1 vs 5.4, `langgraph` 1.2.12 vs 1.1.9, and
   Python 3.11 vs 3.13. Pending majors upstream: `openai` 3.x (held at 2.x today by some
   transitive constraint) and APScheduler 4.0 (alpha; its final release removes
   `BackgroundScheduler`, which would stop every job).
2. **The watchdog misses silent degradation (code).** `serper_counter_current_month` checks only
   the month rollover, not the budget. `ipo_signals_accruing` fires only when an open issue has
   *no* snapshot, never on a stale one. The IPO refresh's `degraded` flag ignores ladder failures.
3. **Two of 24 jobs record outcomes (code).** Only `ipo_deep_dive` and `daily_review` call
   `record_job_outcome`. The brief, digest, autopilot, backup, watchdog and IPO refresh leave only
   logs, which go with each deployment.
4. **Every push redeploys (code + measured).** There is no `railway.json` watch-path rule, and the
   scheduler's jobstore is in memory. A job whose time falls inside a deploy is lost; this was
   observed on 22 Sep. Docs-only pushes carry the same risk.
5. **CUDA wheels in a CPU image (measured).** torch pulls `nvidia-*`/`cuda-*` packages, which makes
   the image and build time larger.

## 3. Recommended additions

| # | Task | Priority | Where |
|---|---|---|---|
| N1 | **Reproducible runtime dependencies**: a lock/constraints file built from the working production set, used by Docker and the local venv, plus a check that they match. | P1 | New SA story (SA-005 covers only test/CI) |
| N2 | **Off-site backup that actually lands**, plus one restore drill. | P1, do early | Raise SA-007 |
| N3 | **Watchdog for silent degradation**: Serper budget at 80%; IPO capture staleness per open issue; refresh `degraded` counting ladder failures; "critical job ran today" invariants. | P1 | New story, or widen SA-011 |
| N4 | **Durable outcomes for every critical job** (brief, digest, autopilot, backup, IPO refresh, watchdog). | P1 | Widen SA-004 / SA-029 |
| N5 | **Deploy hygiene**: watch paths so docs-only commits do not redeploy; avoid deploy windows around job times; catch-up for missed critical jobs. | P2 | New small story |
| N6 | **Brief freshness**: show the capture time on IPO figures; never render a carried-forward ladder as final. | P1 | IPO plan (`IPO-0d`) |
| N7 | **Milestone hygiene**: judge or close the lapsed entries in §1.1; delete the Atlas entry. | P1, ~1 session | Operational |
| N8 | **Learning containment decision**: whether to promote SA-003's observe-only containment ahead of SA-001, given the adapter runs on a known-bad target. | Decision | PI resequencing (owner) |
| N9 | **P1 spine in production**: build `ipo_history.jsonl` on the volume, or wire it to a job. | P2 | IPO plan (unclaimed today) |
| N10 | **Serper budget**: read serper.dev, set `SERPER_MONTHLY_LIMIT` to the real plan, decide IPO-0c. | P1, owner | IPO-0c |
| N11 | **CPU-only torch wheels.** | P3 | SA-028 |

## 4. Close-watch list — prove it in production, not on paper

| Item | Why it is tricky | How to verify |
|---|---|---|
| IPO capture after the fix | Nothing has landed yet; the 19–21 Sep cause is unverified. | 24 Sep: VARMORA rows after the 08:00 and 17:45 refreshes (re-run the probe). |
| First stored P3 verdict | With demand dark, nothing is stored. Substance was also dark despite 9 extractions, so the corroboration gate may be too strict for real issues. | 24 Sep 19:00 post-close slot: `ipo_verdicts.jsonl` exists; `substance` non-null. |
| Narrator | Never exercised in production. Its numeric guard could reject every note, silently falling back to the template. | The first stored row's note source (model vs template). |
| IPO grading | Production has only the NSE-cache resolver (no spine). NSE drops past issues after months, so 252-td horizons may never resolve. | The `awaiting_listing` counter trend in the lane summary. |
| Recipient isolation | `resolve_recipient` falls back to the owner on a lookup error. | Before any beta user: testing case 10-E, SA-006. |
| Backups | A local zip is not recovery. | Off-site copy present, plus one restore into a scratch environment. |
| Learned weights | They drift daily on a known-wrong target. | Weight history vs the frozen baseline; the SA-003 containment decision. |
| Durability across redeploys | B1's open half. | `run_summaries` count before and after today's redeploys. |
| Dependency majors | APScheduler 4 final or the lifting of the `openai` cap arrives at the next cache miss. | N1 lock; until then, read the build log on any `requirements.txt` change. |

## 5. Limits

No production writes, job triggers or notifications. Not inspected: environment variables, the
serper.dev dashboard, restore, user data, `telemetry.db` contents, and prediction-store directory
counts. Log windows are those Railway retains per deployment; the 26 Aug deployment's logs
returned nothing for 17–21 Sep.
