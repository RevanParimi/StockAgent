# Current handoff - 2026-09-21

## START HERE — next task is outside this PI

The user resequenced onto **PI "Prospect" (IPO intelligence)**. The next task is
**not** an `SA-` story and is not selected from `STATE.json`. Do not apply the
AGENTS.md step-2 story-selection rule this conversation; it would route you into
Three Loops and skip the work that was actually asked for.

**Next task:** `IPO-0a`, then `IPO-0b`, in
[the P3/Substance plan](../../superpowers/plans/2026-09-21-ipo-prospect-p3-substance.md).

**Chat opener:**
`Work task IPO-0a from docs/superpowers/plans/2026-09-21-ipo-prospect-p3-substance.md`

**IPO-0a status (2026-09-21 afternoon):** worked, not closeable today — nothing is in the `closed — awaiting listing` state until NSE and SONA close tonight. Read the "Progress 2026-09-21" note under IPO-0a in the plan; it names the two pieces of production evidence the 22 Sep 08:50 brief provides. Do not delete the milestone entry without both.

**IPO-0b is done** (size-tiered demand lean; see the plan's "Done 2026-09-21" note).

**IPO-1 is done** (2026-09-21 evening): the per-horizon read is in the plan under IPO-1 with the decision — fit the SHORT (post-close listing-day) horizon to QIB/total demand, LONG stays dark, OFS never scored. `ipo_p1_backtest_review` removed from the registry. Sprints 3–5 may now get step detail.

**IPO-0c is blocked on you:** it needs the production Serper counter (`railway ssh` → `cat data/logs/api_usage.json`, or the boot log line `[api_usage] counter intact at boot ... serper=N/2500`). Also found: `fetch_gmp()` has no production caller, so provisioning the key would need a wiring change too — see the plan's IPO-0c progress note.

Next after 0a closes and 0c is decided: Sprint 2 (`IPO-2a`).

Read that plan's "State of play as of 2026-09-21" section first. Sprints 0–2 are
executable; Sprints 3–5 are design-level until `IPO-1` (the P1 backtest read,
milestone due 2026-09-30) answers whether there is measurable signal to weight.

The Three Loops PI below is **paused, not abandoned** — DOC-001 still awaits its
fresh-session review and all 32 `SA-` stories remain `todo`.

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
The guide has 12 duties and 57 cases, all NOT RUN.

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
  All 32 SA targets/dependencies/titles, 23 possible scheduler IDs, 13 config
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
