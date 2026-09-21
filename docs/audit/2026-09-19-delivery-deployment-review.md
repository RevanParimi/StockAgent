# Missing scheduled emails and deployment review - 2026-09-19

> ## ⚠ SUPERSEDED 2026-09-21 — findings 1 and 3 are wrong on cause
>
> This document is retained as a record of what was believed on 2026-09-19.
> Do not use it as current diagnosis.
>
> **What it got right:** that the outage was real, that a green `/health` proves
> nothing about scheduler or delivery health, and that Railway's SMTP plan
> restriction was a plausible cause.
>
> **What it got wrong:**
> - **Finding 1** leans on a Gmail credential/App Password hypothesis. Production
>   logs show `[delivery] email send failed (non-fatal): [Errno 101] Network is
>   unreachable` — no TCP connection is ever established, so the credential was
>   never reached. The SMTP auth errors (`5.7.8`/`5.7.9`) that informed this
>   hypothesis came from **local** telemetry, not production.
> - The **246 email-failure record count** is contaminated. 146 of the records in
>   `data/telemetry.db` are pytest artifacts from `test_missing_attachment_file`.
>   The measured production figure is **n=103 over 21 distinct days** (card D6,
>   spec `2026-08-24-three-loops-pi-design.md` §15.4).
> - **Finding 3** presents the backup "no off-site copy" records as evidence of
>   SMTP failure. That log line reads `(email disabled, oversize, or send failed)`
>   and cannot distinguish those cases — consistent with, but not proof of, the outage.
>
> **Actual cause and fix:** Railway disables outbound SMTP on Free/Trial/Hobby.
> Upgrading to Pro **and redeploying** resolved it; the upgrade alone does nothing
> to an already-running container. Verified 2026-09-21.
>
> This audit also never cites card **D6**, which had already triaged this with
> production counts on 2026-08-24.

The strongest available evidence is a persistent email transport failure while
notification generation continued. A complete current Railway audit is **pending
authenticated access**. Today's public HTTP checks cannot establish scheduler
health, and September 10 production counts must not be treated as current counts.

## Scope and evidence

- User-requested operational review, temporarily ahead of DOC-001 review.
- Current checkout: `042c05ff30d949e48b6127fd3a59deeee4a2df0a`, branch
  `feat/e2-error-fingerprint-digest`; initial working tree clean.
- Remote branch tips were checked with `git ls-remote`, not inferred from cached refs.
- Public production HTTP checked September 19, 01:20 UTC (06:50 IST): `/` 200,
  `/health` 200, `/scheduler/status` 401 without credentials. No protected data fetched.
- Historical evidence: [September 10 audit](2026-09-10-repository-production-review.md)
  and its saved local aggregate evidence, captured `2026-09-10T06:46:22Z`.
- September 15 deployment verification in the existing handoff recorded SUCCESS at
  `9a805878ed19c0cda7833d5b897ac05ee407436d`. This was not independently refreshed today.
- No application imports, job triggers, emails, push messages, deployments,
  production configuration changes, commits or pushes were performed.

## Findings

### 1. P1: scheduled content was generated but email delivery failed

Historical retained outbox cohort:

| Notification kind | Email dead after three attempts | Push recorded delivered |
|---|---:|---:|
| Morning brief | 14 | 14 |
| Daily digest | 13 | 13 |
| Weekly review | 3 | 3 |
| Alerts | 27 | 27 |
| Total | 57 | 57 |

The historical telemetry contains 246 email failure log records over 36 dates,
July 16 through September 10. These are log records, not unique emails.
The latest retained brief was generated September 10 at 08:50 IST; the latest
digest was September 9, and weekly review September 6. Push transport success
does not prove device display or human receipt. This establishes historical
delivery failure without establishing that all jobs have stopped today.

Current code uses SMTP with STARTTLS and a 20-second timeout in
[`send_email`](../../core/delivery/channels.py). Exceptions become warnings and
`False`. The outbox retries and eventually marks failed rows `dead`.
There is no HTTPS email-provider transport in this path.

[Railway's current outbound-networking documentation](https://docs.railway.com/networking/outbound-networking)
says SMTP is disabled on Free, Trial and Hobby plans and available on Pro and
above. Plan restrictions are a plausible cause, **not a confirmed diagnosis**:
the project plan, current provider, credentials, port and connectivity were not
available for verification. SA-006 remains the delivery remediation story.

### 2. P1: job completion and the green health endpoint can hide failures

- [`run_morning_brief`](../../core/delivery/brief.py) and
  [`run_weekly_review`](../../core/delivery/weekly.py) save content and count a user
  after calling `deliver`, without requiring successful email delivery.
- With the outbox enabled, [`deliver`](../../core/delivery/channels.py) returns
  `delivered=True` when rows were merely enqueued; final transport outcome is later.
- [`/health`](../../services/api/server.py) returns unconditional `status=ok`.
  It does not test scheduler ownership, next runs, delivery backlog or storage.
- The two-worker server elects a background owner only during startup. A surviving
  non-owner does not periodically take over. Scheduler startup failure is non-fatal.
  This is a code-level resilience risk, not an observed current owner failure.

Consequently Railway's green deployment and today's HTTP 200 do not establish
that scheduled mail is working. Track delivery in SA-006, truthful daily output
counts in SA-004, and background readiness/recovery in SA-029.

### 3. P1: the same historical email failure affects off-site backups

The retained logs contain 34 `no off-site copy` records over 34 dates, August 7
through September 9. [`run_backup_job`](../../services/data/backup.py) uses the
same email transport. Local archives existed in the earlier audit; current local
backup freshness and Railway-managed backups have not been rechecked. Do not
interpret local backup rotation as verified disaster recovery. SA-007 is pending.

### 4. Deployment age does not indicate an undeployed runtime fix

Remote `main` still points to `9a805878ed19c0cda7833d5b897ac05ee407436d`, matching
the commit message in the supplied active-deployment screenshot. Remote
`feat/e2-error-fingerprint-digest` points to local HEAD `042c05f`.

The feature branch adds one commit containing docs, planning, AGENTS.md and
documentation tooling. `core/`, `services/`, `src/`, Dockerfile, `config.yaml`,
`config/` and requirements have no changes relative to main. Merging this commit
would not fix the SMTP or scheduler behavior. The feature branch name is not
evidence that an email or error-digest implementation exists on it.

The screenshot and old metadata do not establish Railway's currently configured
source branch. All-service inventory, latest deployment SHA, source branch,
autodeploy status, skipped builds, replicas and runtime settings remain unverified.

The PI records all 29 planned remediation stories as `todo`; DOC-001 is awaiting
fresh-session review. The audit identified problems but did not deploy their fixes.

## Expected schedules from code, not live registration

These jobs run inside the API's Python APScheduler, not necessarily as separate
Railway cron services. Cron triggers use `Asia/Kolkata` despite the US hosting region.

| Work | Code schedule / trigger |
|---|---|
| Morning brief | Weekdays 08:50 IST, then a trading-day check |
| Daily review and subsequent digest pipeline | Configured `FEEDBACK_CRON`; default weekdays 16:30 IST; digest follows pipeline completion |
| Weekly review | Sunday 18:00 IST |
| Local backup and attempted email copy | Daily 23:30 IST |

Scheduler startup requires `SCHEDULER_ENABLED`; morning/weekly registration also
requires `DELIVERY_ENABLED`. Email has a separate enable/configuration gate.
The YAML scheduler default is false; production environment overrides must be
verified. September 19 is Saturday, so there is no ordinary morning-brief run
scheduled today. That does not explain the historical missing weekday emails.

## Remaining authenticated investigation

This Windows environment has no usable Railway CLI at the previous audit's path,
no Railway config/login at the standard user path, and no `RAILWAY_TOKEN` or
`RAILWAY_API_TOKEN` environment variable. No Railway/browser connector is available.
Python is also absent apart from the Windows Store alias. Tokens and `.env` were
not read or displayed. The missing access prevents fresh private log collection.

Once authenticated access or a user-provided export is available, inspect:

1. Every production service and active deployment: exact source SHA/branch,
   build/start commands, latest runtime restart, replicas, healthcheck and volume.
2. September 10 onward logs, especially September 18's morning brief, review and
   digest: registration, actual starts/completions, misfires, worker exits and
   outbox drainer lifecycle. Interpret application severity, not Railway's outer
   stderr level alone.
3. Aggregate outbox counts by day/channel/kind/status, attempts, oldest queued or
   sending row; recent SMTP exception categories. Exclude recipients and payloads.
4. Provider/plan compatibility, configured port, boolean credential presence and
   non-sending connectivity diagnostics. Distinguish blocked network, timeout,
   authentication failure, provider rejection and mailbox delivery.
5. Persisted brief/weekly/digest freshness, daily job outcomes and local backup
   freshness. Read SQLite with `mode=ro` and `PRAGMA query_only=ON`; avoid application
   imports that initialize stores or background tasks.

Retain raw exports only under ignored `analysis_data/railway_20260919/`. Do not
resend dead letters, restart services or trigger jobs as a diagnostic step. A
transport repair should preserve historical evidence and separate provider
acceptance from recipient receipt. Deployment and real notification tests need
their own applicable authorization under AGENTS.md.

## Verification and handoff

Commands: `git status --short`, `git branch --show-current`, `git log -6`,
`git ls-remote --heads origin main feat/e2-error-fingerprint-digest`,
`git rev-parse HEAD main`, `git show --stat HEAD`, and
`git diff main..HEAD --name-only -- core services src Dockerfile config.yaml config requirements.txt`.
The last command returned no files. HTTP checks used PowerShell
`Invoke-WebRequest -UseBasicParsing -TimeoutSec 20` for the three paths above.
Historical JSON was read locally with only aggregate counts emitted. Relevant
scheduler, delivery, outbox, backup and server code was inspected statically.

No application behavior changed, so no unit test run or full-suite claim is made.
Changed-file manifest: this report, PI `STATE.json` (scope history only), and
`HANDOFF.md` (operational handoff). No story was accepted or marked implemented.
DOC-001 remains `review_required`; SA-006/SA-007/SA-029 dependencies and production
verification remain unresolved. Finish current authenticated inspection before
claiming the complete Railway review is done.
