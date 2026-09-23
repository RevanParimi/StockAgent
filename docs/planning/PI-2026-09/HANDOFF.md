# Current handoff - 2026-09-23

## START HERE — DOC-001 is ready for its fresh-session review

**2026-09-23:** the changes-requested remediation is complete, including the
PDF rebuild; Node v24.21.0 was installed that day. `STATE.json` says
`DOC-001: review_required`, `next_phase: fresh-session review`. The review input
is **`7b04fa718dbaf958c71413f21e0d99454b9184801cc530d4d3f1cec2fb03deca`**,
from the [manifest](evidence/DOC-001-manifest.json). The receipt is the
[2026-09-23 section](evidence/DOC-001-implementation.md#remediation-phase--2026-09-23).
All 32 `SA-` stories remain `todo`. **Self-review only so far.**

**Before the review: commit the payload.** It is uncommitted. Then:

```text
python scripts/docs/kt_manifest.py verify docs/planning/PI-2026-09/evidence/DOC-001-manifest.json --rev HEAD
```

This must report 0 mismatches; any mismatch is F1 again. The pre-existing
untracked `DOC-001-review.md` is part of the payload, so commit it too.

**Chat opener (new conversation):** `Continue — fresh-session review of DOC-001`

| Finding | Now |
|---|---|
| F1 manifest unreproducible | **Fixed.** The new `scripts/docs/kt_manifest.py` records git's blob id plus the SHA-256 of the same bytes. |
| F2 stale PDF | **Fixed.** Rebuilt, 18 pages; `check_kt_docs.py` has **0 errors**. |
| F3 stale header | **Fixed.** Header at `d105a44`, and `check_kt_docs.py` now guards it (it fails the reviewed KT with 10 errors). |
| F4 delivery undocumented | **Fixed.** §10 rewritten; §1, §8, §11 and §13 reconciled. Testing case 10-E added: **60** cases. |
| F5 ambient-credential tests | **Routed** to [SA-005](stories/SA-005.md), noted on [SA-006](stories/SA-006.md). The harness still shows those 2 failures, by design. |

For the reviewer, the things most worth attacking:

- **The header guard can pass while the header is wrong.** It proves linked
  files and job IDs exist at the declared revision. It cannot see changed
  behaviour inside a file that already existed there, which is how
  `590bc9f`'s `channels.py` change slipped through.
- **§10's production sentences.** "One triggered brief reached the inbox"
  comes from the 2026-09-21 handoff, not from inspection. Whether production
  sets `RESEND_API_KEY` was not inspected.
- **Case 10-E expects a result current code does not give.** On a failed
  account lookup, the brief goes to the owner. That is marked as the SA-006
  target, not as current behaviour; check that the guide reads that way.

After acceptance, select **SA-001**, but do not start it in the review
conversation.

### Production read — 2026-09-23 (read-only; supersedes "no railway access" notes below)

The Railway CLI now works here (Node installed, folder linked to project `carefree-renewal` /
`production` / `StockAgent`). The user ran one read-only probe through `railway ssh`; Claude's own
`railway ssh` is blocked by the auto-mode classifier. The probe is
`analysis_data/prod_probe_20260923.py` (ignored). Run it from Git Bash:
`railway ssh "cd /app && echo $(gzip -9c <probe> | base64 -w0) | base64 -d | python -c 'import sys,zlib;exec(zlib.decompress(sys.stdin.buffer.read(),31))'"`.

- **Deploy:** `b68bc02` is SUCCESS (2026-09-23 07:59 UTC).
- **D6 — closeable.** In the outbox, before 21 Sep there were 77 email rows dead and 77 push
  delivered. Since 21 Sep: 3 email dead, all before the redeploy (last at 07:52 UTC on the 21st);
  **8 email delivered, 0 dead since**, and 11 push delivered (email/push parity). "Delivered" means
  provider-accepted. This is production evidence toward SA-006, **not** its acceptance.
- **IPO live capture is broken in production since ~18–19 Sep.** Every `fetch_bid_ladder` fails;
  locally it works. The 22 Sep brief's category figures were 2–3 days stale (NSE QIB 1.53× shown,
  final 12.68×). VARMORA has no ledger rows, and `ipo_signals_accruing` is warning. **Do not close
  IPO-0a.** Full evidence is under IPO-0a in the plan.
- **P1 spine absent in production** (`data/ipo/ipo_history.jsonl` missing).
- **IPO-0c:** serper counter 2,590 in September (default budget 2,500). Recommend GMP stays dark;
  check serper.dev for real remaining credits.
- **P3:** no `ipo_verdicts.jsonl` yet. That is expected for NSE/SONA, because their T−1 run predates
  the deploy. VARMORA's T−1 run is 23 Sep 19:00 IST, but its demand inputs are dark (no ledger rows).
- **Next evidence to get:** the production failure reason. It shows as `[ipo_bids] fetch failed for
  VARMORA (non-fatal): …` in the logs after the 17:45 IST refresh, or from a one-off fetch through
  `railway ssh`.

### IPO stays paused

`ed1b900` (IPO-4c) is pushed and `origin/main` is current, which closes **Sprint 4** of PI "Prospect".
The user chose to **pause IPO work and wait for live production evidence** rather than start `IPO-5a`.
Do not start an `IPO-` task unless the user brings evidence or says so. One encouraging note from the
review: the incremental-documentation discipline DOC-001 introduced **is** being followed — the 23→24
job-count change propagated correctly to four documents, and cases 05-F/05-G were added with their
stories.

After DOC-001 is accepted, `SA-001` is the first remediation story — select it, do not start it in the
acceptance conversation.

### Why IPO is waiting, and what arrives on its own

Everything through Sprint 4 is built and now deployed-on-push; **none of it has been measured in
production.** The first real evidence appears without anyone doing anything:

- **Tonight and each evening after**, the `ipo_deep_dive` job (19:00 IST) should hit its `post_close`
  slot for **NSE** and **SONA**, both `bidding closed — awaiting listing`.
- **2026-09-23** is the first genuine **T−1** candidate: **VARMORA** closes 24 Sep (the 22 Sep brief
  said "closes in 2 days"), so the expensive research slot should fire that evening.

Check `GET /scheduler/status` for the `ipo_deep_dive` last-run outcome, or whether
`data/ipo/ipo_verdicts.jsonl` now exists on the volume. Until a row exists, `IPO-5a` would be surfacing
code written against an imagined row.

### IPO-0a — criterion 1 is MET; one piece of evidence remains

The user supplied the **22 Sep 08:50 IST production brief**. It satisfies the live-observation half in
full — this is the subject the milestone had never had:

| Issue | Heading rendered | Subscription rendered |
|---|---|---|
| NSE | `bidding closed — awaiting listing` | 3.78261× overall (QIB 1.52996×, retail 0.722428×, 39% at cut-off) |
| SONA | `bidding closed — awaiting listing` | 1.45233× overall (QIB 0.459178×, retail 1.28955×, 58% at cut-off) |
| VARMORA | `closes in 2 days` (open) | `data pending` — correct; it opened that morning |

Real × values, not `data pending`, under correct state headings. **Still needed:** the ledger half —
either no `ipo_signals_accruing` `pending` alert since NSE/SONA opened on the 17th (Inbox or
`GET /delivery/alerts`), or a volume read. ⚠ `railway ssh` is NOT available: this machine has no Node,
so the CLI's npm install route is closed too (a standalone binary from Railway's releases would work).
Do not delete the milestone entry on the brief alone.

### ⚠ Open question raised by that brief — worth one look before IPO-5b

Both closed issues rendered **"(NSE only)"**. Per `services/data/fetchers/ipo.py`, `total_x_nse_only`
clears only when the all-exchange **combined** ladder is fetched, and `_enrich_open_issues` fetches a
live ladder only while `issue_state == "open"` — a closed issue inherits via `_carry_forward`. So the
final book recorded in production for NSE and SONA looks like the **NSE-only under-report**.

Against the 21 Sep 14:15 IST scratch fetch in the plan's IPO-0a note (total 3.817×, **QIB 7.81×, retail
1.10×, 14% at cut-off**) the totals are close and the categories are not. Combined-vs-NSE-only would
explain it; so would something wrong. **This is unresolved and was not investigated** — it needs
production data this machine cannot reach.

**Why it matters:** P3's `demand` is computed from exactly those category figures (`qib_x`, `retail_x`,
`cutoff_share`), and `IPO-1` fitted its thresholds on the spine's combined subscription. If production's
final book is habitually NSE-only, `demand` is being computed on a different quantity than it was fitted
on — which would undercut the forward hit-rate `IPO-5b`'s gate depends on. Resolve before `IPO-5b`.

### Also outstanding, user-side

- `IPO-0c` still waits on the production Serper counter (`cat data/logs/api_usage.json`, or the boot log
  `[api_usage] counter intact at boot ... serper=N/2500`). `fetch_gmp()` also has no production caller.
- `docs/StockAgent-Three-Loops.pdf` is stale and cannot be rebuilt here — no Node, no Chromium cache,
  although `node_modules/playwright` is vendored. Install Node LTS, then
  `npx playwright install chromium` and `python scripts/docs/build_kt_pdf.py`. It is the only
  `check_kt_docs.py` error; 24 job IDs, 221 local links and 13 configuration claims are green.

**IPO-4c is done** (2026-09-22): the audit lane. `Lane` gains `"ipo"`; `core/ipo/listing.py` resolves the
listing date and issue price (P1 spine first, NSE cache second); `grade_ipo_lane` in
`core/audit/outcomes.py` grades the newest stored verdict per issue at 1/5/21/63/126/252 trading days
from listing, with `entry_close` = the **issue price**, documented at the schema field rather than left
to be inferred. Three design points the plan's outline did not reach, all now in its step detail:
`is_correct` was **not** taught an IPO word — `core/audit/rules.py` gains `is_ipo_correct` beside
`is_switch_correct`, on the precedent that a different question gets its own answer; **only one row per
issue can carry True/False** (the listing-day horizon, of a post-close verdict, whose lean asserts a
direction), every other horizon carrying the return and no claim; and an issue with no tape yet counts as
`awaiting_listing`, deliberately **not** `skipped_unpriceable`, because the nightly job feeds that
counter to `alert_job_partial_output`. IPO rows are excluded from the rendered audit report and reach no
surface. 37 offline tests; full suite **3126 passed, 5 skipped**. `TEAM_TESTING_GUIDE.md` gained case
**05-G** (12 duties, **59** cases, all still NOT RUN).

⚠ **`IPO-4c` has had implementation and same-conversation self-review only — no fresh-session review.**
That matches how `IPO-3*`/`IPO-4a`/`IPO-4b` were closed under this plan's own "commit per task"
discipline, and it is not the `REVIEW.md` gate. If a fresh review is wanted, the three highest-value
targets are: the horizon off-by-one (horizon 1 must be the listing day, not the day after); the
scoreability rule (nothing outside an evidenced, directional, listing-day row may carry True/False); and
containment (no IPO row may move a number in `build_report`). All three have tests; the question a
reviewer should ask is whether the tests can pass while the property is false.

⚠ **No production IPO row has been graded and none can be yet**, for three reasons that are not code:
the `ipo_deep_dive` job reaches production only on deploy; `data/ipo/ipo_verdicts.jsonl` does not exist
there until it does; and grading additionally needs the issue in the P1 spine, which
`scripts/ipo_backfill.py` rebuilds **manually** from the bhavcopy volume. Until an issue reaches the
spine the NSE cache is the only resolver, and NSE drops issues from `past` after a few months — so a
252-td horizon on an issue that never reached the spine sits in `awaiting_listing` for good. That is a
visible counter in the lane summary, not a silent loss. Wiring the spine to a job is unclaimed work; it
is not in this plan.

**IPO-4b is done** (2026-09-22): `core/ipo/narrate.py` + `core/config/prompts/shared/ipo_narrate.py`.
The note is the `IPO-5a` explainer content, stored on the verdict row and reaching **no surface**.
What the plan put in the prompt, the build put in the code path: the verdict is never passed to the
narrator at all; every number in the prose must appear in the structured findings (rounding yes,
arithmetic no); an advice/verdict vocabulary rejects the note; and a rejected or failed note falls back
to a deterministic template from the same facts. The model is handed source COUNTS, never URLs — the
"Sources:" line and the "research view — not advice" framing are appended in code on both routes.
Cost shape: a note is bought only for a row that will actually be stored, and reused while the facts
digest holds, so an issue costs at most two model calls — T−1 and the close (the note states which).
⚠ This nuances `IPO-4a`'s "post-close costs nothing": that remains true for network and extraction; the
narration adds exactly one call at the close. 45 offline tests.

**IPO-4a is done** (2026-09-22): `core/ipo/deep_dive.py` + the `ipo_deep_dive` job at 19:00 IST.
The design point that was not in the plan's table: the visibility gate counts only `short.evidenced`
rows, which exist only after the book closes, so the sweep has **two slots** — the T−1 research run and
a post-close re-read off the cached dossier + cached extraction (zero network). A verdict with every index
dark is not stored (the capture ledger's "a row asserts a reading was taken"). 32 offline tests. ⚠ The
job reaches prod only on deploy; until then `data/ipo/ipo_verdicts.jsonl` does not exist in production.
The first real T−1 candidate after deploy is whichever mainboard issue closes the day after.
⚠ `docs/StockAgent-Three-Loops.pdf` is stale (was already stale at `5f7238c`; §8/§9 of the KT changed at
`IPO-4a`, §8 again at `IPO-4b`, and §7 + §8 again at `IPO-4c`). No Node/Chromium on this machine —
rebuild with `python scripts/docs/build_kt_pdf.py` where there is. It is the only `check_kt_docs.py`
error; 24 job IDs, 221 local links and 13 configuration claims are green.

**IPO-0a status (2026-09-21 afternoon):** worked, not closeable that day — nothing was in the
`closed — awaiting listing` state until NSE and SONA closed that night. Read the "Progress 2026-09-21"
note under IPO-0a in the plan; it names the two pieces of production evidence the 22 Sep 08:50 brief
provides. Do not delete the milestone entry without both.

**IPO-0b is done** (size-tiered demand lean; see the plan's "Done 2026-09-21" note).

**IPO-1 is done** (2026-09-21 evening): the per-horizon read is in the plan under IPO-1 with the decision — fit the SHORT (post-close listing-day) horizon to QIB/total demand, LONG stays dark, OFS never scored. `ipo_p1_backtest_review` removed from the registry. Sprints 3–5 may now get step detail.

**IPO-0c is blocked on you:** it needs the production Serper counter (`railway ssh` → `cat data/logs/api_usage.json`, or the boot log line `[api_usage] counter intact at boot ... serper=N/2500`). Also found: `fetch_gmp()` has no production caller, so provisioning the key would need a wiring change too — see the plan's IPO-0c progress note.

**Sprint 2 is done** (2026-09-21 evening, `e8abda3` + `c8e54c2`): `core/ipo/research.py` (Tavily dossier, cached per issue) and `core/ipo/extract.py` (per-document extraction, corroboration gate). 60 offline tests over three real captures. Not yet wired to any job — that is `IPO-4a`.

**Sprint 3 is DONE** (`4c26072`, `c60f602`, and `IPO-3c`/`3d`/`3e` on 2026-09-22): `hype.py` (fitted `demand` + unfitted `froth`), `substance.py` (S, never fitted), `verdict.py` (the §3 grid, SHORT from `demand`, LONG hard-wired dark) and `verdicts.py` (the append-only store). The model runs end to end on the recorded dossiers and reaches no job and no surface.

**`ipo_verdicts_visible_gate` is now in `config/milestones.yaml`**, deadline 2026-12-31 or 60 days of forward P2 rows, whichever comes first. It is the gate P3 has to pass before any verdict is shown. ⚠ A milestone reaches prod only on deploy — the `registry_is_current` invariant watches for that.

**Sprint 4 is complete.** `IPO-4a` (the `ipo_deep_dive` job at 19:00 IST) wired Sprints 2–3 to the clock,
`IPO-4b` (the narrator) gave the row its prose, and `IPO-4c` (the audit lane) gave it forward grading.
The model now runs, writes, narrates and will be measured — and still reaches no user.

Still open from Sprint 0: `IPO-0a` closes on the 22 Sep brief; `IPO-0c` still waits on the production Serper counter (see below).

Read that plan's "State of play as of 2026-09-21" section first. Sprints 0–4 are
executable and built; Sprint 5 carries acceptance criteria and a gate column but
no step detail yet.

The Three Loops PI below is **paused, not abandoned** — DOC-001 still awaits its
fresh-session review and all 32 `SA-` stories remain `todo`. `STATE.json` was
deliberately not touched by any IPO task: it describes PI-2026-09, which has zero
IPO scope, and writing an IPO `active_task` into it would misrepresent that PI.

## Resolved since September 19 — the email outage

The September 19 investigation below is superseded on its central question.

- **Cause:** Railway disables outbound SMTP on Free/Trial/Hobby. Production
  logged `[Errno 101] Network is unreachable` on every send since 2026-07-16
  (n=103 over 21 days — card **D6**, spec `2026-08-24-three-loops-pi-design.md` §15.4).
- **Fix:** upgraded to Pro **and redeployed**. The upgrade alone changes nothing
  for an already-running container; the 25-day-old deployment was still under the
  Hobby network policy. Verified 2026-09-21 — a triggered brief reached the inbox.
- **D6 is closeable** after a day of clean logs.
- ⚠ The [September 19 audit](../../audit/2026-09-19-delivery-deployment-review.md)
  advances a Gmail-credential hypothesis that production evidence **disproved**.
  Its §1 and §3 are wrong on cause. Treat it as a record of what was believed on
  the 19th, not as current diagnosis.

### Shipped in `590bc9f` (on `origin/main`, deployed)

- `outbox.last_error`, written on retry and dead-letter, cleared on recovery —
  a failed send now explains itself without container logs. Partially satisfies **SA-006**.
- An HTTPS Resend transport beside SMTP; `EMAIL_TRANSPORT=auto` picks it only
  when `RESEND_API_KEY` is set, so current behaviour is unchanged on Pro+SMTP.
- Per-account recipients via `resolve_recipient()`. ⚠ **Known gap:** a transient
  `users.db` lookup failure falls back to `DELIVERY_EMAIL_TO`, which in multi-user
  beta could route a tester's brief to the owner's inbox. Tighten before beta.
- Tests: 2832 passed, 5 skipped (full `tests/unit`).

## Operational investigation requested September 19

The user temporarily resequenced a read-only review of missing scheduled emails
and Railway deployment state. See the [dated findings](../../audit/2026-09-19-delivery-deployment-review.md).
Public HTTP and remote Git checks are current; private production logs/configuration
could not be refreshed because this machine has no Railway CLI/login/token.
September 10 delivery counts remain historical. Current service inventory, source
branch, scheduler activity and SMTP connectivity still need authenticated inspection.
No application, deployment, variable, job or notification was changed. This is
an operational investigation, not DOC-001 acceptance or SA-006 implementation.
The PI state and unresolved dependencies below are preserved.

## PI handoff retained from September 15

**DOC-001 implementation is complete; fresh-session review is required.**
No remediation code was changed or accepted. All 29 planned SA stories and
three stretch stories remain `todo`.

Next task: [DOC-001](stories/DOC-001.md). Next phase: **fresh-session review**
under [REVIEW.md](REVIEW.md). Read the [implementation receipt](evidence/DOC-001-implementation.md),
verify the [manifest](evidence/DOC-001-manifest.json) and inspect the worktree.
Review-input SHA-256: `90c005c46417db97d6e3f6feba2431aae66a8ad93037e852e9823ad7936125c0`.
Do not sign off this phase using its same-conversation self-review.

## Scope and deliverables

The user explicitly resequenced two tasks ahead of SA-001:

1. Current-code KT Markdown/PDF including all PI targets, clearly separate
   from implemented and production-verified behavior.
2. A separate human testing guide: assignable duties, practical cases,
   expected results and evidence; no code-intensive review or named assignment.

The updated entry points are [Technical KT](../../TECHNICAL_DESIGN.md),
[generated PDF](../../StockAgent-Three-Loops.pdf),
[architecture](../../ARCHITECTURE.md) and
[team testing guide](../../TEAM_TESTING_GUIDE.md).
The guide has 12 duties and 60 cases (05-F added at `IPO-4b`, 05-G at `IPO-4c`, 10-E at the 2026-09-23 DOC-001 remediation), all NOT RUN.

Every future implementation updates its affected living docs/test cases and
regenerates the PDF when its source changes. SA-031 now means the final
consistency check; SA-024/SA-027/SA-029 remain unresolved dependencies. After
DOC-001 acceptance, select SA-001 as the first remediation story, but do not
start it in that review conversation.

## Verification and limitations

- HEAD and September 15 Railway deployment metadata match
  `9a805878ed19c0cda7833d5b897ac05ee407436d`; deployment status SUCCESS.
  Only deployment context was refreshed. The [September 10 audit](../../audit/2026-09-10-repository-production-review.md)
  remains the detailed dated production evidence.
- 323 existing tests passed across 30 files, Python 3.13.11 on Windows,
  in an isolated source copy with dotenv disabled and external transports
  blocked. TestClient and a Windows asyncio local socket pair are allowed.
  No full-suite or Linux/Python-3.11 parity claim.
- 16-page PDF: searchable, source-hash matched, rendered and visually checked.
  All 32 SA targets/dependencies/titles, 23 possible scheduler IDs (24 since `IPO-4a`), 13 config
  assertions and local documentation links checked. Receipt has exact results.
- Known grading, timing, health, weight-bound, delivery and recovery gaps
  remain. Neither tests describing existing behavior nor this KT establishes
  learning benefit. Human acceptance and future market evidence remain pending.

## Preserve and continue safely

- Pre-existing user audit banners/provenance were retained. The original PDF
  is preserved byte-for-byte in [the archive](../../archive/README.md); the user
  explicitly requested updating its primary path.
- No application source/configuration change, deployment, production job,
  backfill, notification, commit or push was performed.
- Do not read/expose `.env` or private raw logs. Raw local diagnostics are
  ignored under `analysis_data/kt_20260915/`; audit history under
  `analysis_data/audit_20260910/` may be absent elsewhere.
- Preserve other unrelated worktree changes. Manifest covers the intended
  payload; inspect STATE, HANDOFF and receipt bookkeeping separately.
