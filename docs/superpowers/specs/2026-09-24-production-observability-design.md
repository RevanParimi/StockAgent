# Production observability — design

Status: **adopted as the plan** on 2026-09-24. Owner decisions (§9): D1 yes, D2 Telegram, D3 key
limit, D4 Sentry deferred, D5 on the board as SA-040–SA-042, with SA-034/035/036 widened. Nothing
is implemented yet. Author: Claude + Revan. Date: 2026-09-24.
Extends the [operational watchdog design](2026-08-10-operational-watchdog-design.md) and revises
its D5 in one respect (§5.4). Current-code claims were checked at `c832145`. Production figures
are dated observations from the [2026-09-23 assurance review](../../audit/2026-09-23-production-assurance-review.md)
and from read-only `railway logs` on 2026-09-24.

---

## 0. Summary for the owner

**Recommendation: no Prometheus, no OpenTelemetry SDK and no Arize for now.** Build three small
things inside the app, add one free service outside it, and switch on Railway's own alerts.
Expected extra running cost: **$0 a month**.

| Piece | What it does | Where |
|---|---|---|
| **Ops ledger** | Records durably whether each job ran and what it produced, whether each outside source worked, and how much credit is left | Inside the app (`telemetry.db`, which already exists) |
| **Evaluator** | The existing watchdog, checking that ledger against expectations right after each critical job as well as at 06:30 | Inside the app |
| **Fetcher** | One read-only `GET /ops/status` plus a small command-line script, so anyone, Claude included, can ask "is production OK?" without `railway ssh` | Inside the app, plus `scripts/ops/` |
| **Outside witness** | Healthchecks.io (free) notices when a job did **not** check in, and messages you on Telegram | Outside the app |
| **Railway alerts** | Deploy failed or crashed, and the volume filling up | Railway settings, no code |

The one-line reason: every recent failure already left a trace (a warning line, a counter, a
missing file). Nothing compared that trace with an expectation in time, and the only alarm bell
(email or push) sat inside the thing that was broken.

---

## 1. What went wrong, and how long it took to notice

Each row is a dated observation. The last column is what this design would have done instead
(§6 replays them in detail).

| Incident | Trace that existed | Noticed | With this design |
|---|---|---|---|
| **Email dead**: Railway Hobby blocked SMTP, `[Errno 101]` on every send | WARNING lines in `app_logs`; outbox dead rows | 16 Jul → 21 Sep, about **9 weeks** | Day 1: the `smtp` source goes 0% successful, and the alert travels by Telegram, not email |
| **Sunday heartbeat never arrived** for those 9 weeks | The heartbeat is email-only (`runner.py`) | Never noticed | Healthchecks sees no `ops_watchdog` ping within 24 h and messages Telegram |
| **IPO capture broken** by `nse` 4.0 (`'NSE' object has no attribute '_req'`) | 10 WARNING lines per refresh, but `degraded=False` | Last good rows 18–19 Sep; found 23 Sep by a manual probe (about **4 days**, with perishable data lost) | Minutes after the 17:45 refresh: a new error signature, plus the `nse.bid_ladder` source at 0 of 5 |
| **Stale IPO figures** in the 22 Sep brief (QIB 1.53× shown, 12.68× final) | Ledger timestamps | Found by reading the brief | Freshness check: "NSE last captured 2.9 days ago" |
| **Deep dive missed** (22 Sep deploy came up at 19:02) | No outcome row | Found in review | Healthchecks: no `ipo_deep_dive` ping by 19:30 |
| **OpenRouter at $0.97** | No reading anywhere; yesterday's review alone logged **$0.40** | Owner looked at the dashboard | Daily runway reading: "about 2 days of credit left" |
| **Serper 2,590 / 2,500** | App counter | Found in review | Budget check at 80% |
| **Backup not off-site** (`emailed=False`) | One log line | Found in review | The backup job reports `partial` and the witness gets a fail ping |
| **Claude could not verify production** | Data on the volume | Needed owner-run `railway ssh` | `scripts/ops/fetch_status.py` with a read-only token |

**Pattern:** detection took days to weeks, and that delay is where the damage happened. The fix
is a quicker, independent look at data that mostly already exists, not more data.

---

## 2. Requirements

Each one is testable. Expected times are in IST.

| # | Requirement | Example of "met" |
|---|---|---|
| R1 | **Every critical job**: did it run, on time, and did it produce what it should? The answer must survive redeploys. | "`morning_brief` 24 Sep: ran 08:50:03, 1 brief built, 1 push accepted." |
| R2 | **Every outside source**: successes and failures per day, by error type, the last success time, and the first appearance of a new error type. | "`nse.bid_ladder`: 0 ok / 5 fail today; new error `AttributeError` first seen 17:45." |
| R3 | **Freshness** for each dataset that has a cadence. | "VARMORA last capture 08:00 (0.3 h ago)." |
| R4 | **Credit runway** for each paid provider: remaining ÷ recent daily spend, in days. A failed reading shows as *unknown*, never $0. | "OpenRouter: about 2.4 days left at $0.40/day." |
| R5 | **Time to detect**: within 15 minutes of the job that reveals a job-scoped failure; within 24 h for slow drift; within 1 day, *from outside*, that the watcher itself has died. | §6 |
| R6 | **An independent alarm path** that works even if email, push, the container or the scheduler is down. | A Telegram message while SMTP is dead. |
| R7 | **One read-only fetcher**, sanitized, with least privilege: its token can read status and cannot trigger jobs. | `fetch_status.py` → "AMBER: 1 warning (OpenRouter runway 2.4 d)". |
| R8 | **Alarm hygiene**: every alert says what broke, since when and the first action to take. It is deduplicated, and it has a quiet-state test. | No alert on a quiet IPO month or a holiday. |
| R9 | **Monitoring never hurts the product**: a failed ledger write, ping or balance read never slows or breaks a job. | Each ping has a 3 s timeout on a background thread. |
| R10 | **Works with this runtime**: one container, `uvicorn --workers 2`, a TCP-singleton scheduler, SQLite on the volume, and redeploy on every push. | No new always-on service to host. |
| R11 | **Privacy**: nothing that identifies a user, no prompt text and no secret leaves Railway. | The witness receives job names, times and a short status word only. |

**Non-goals:** request-latency tracing, distributed tracing, dashboards for their own sake, and
model-quality evaluation on labels the audit found wrong (F02). "Changed weights" is also never
reported as learning benefit.

---

## 3. What exists today (verified at `c832145`)

- `data/telemetry.db` on the volume:
  - `llm_calls`: model, tokens, latency and a `success` flag, but no status code (SA-035).
  - `app_logs`: **every WARNING+ log line, durably**, via `SQLiteLogHandler`. For example,
    yesterday's `_req` failures are in it.
  - `run_summaries`, `data_health` and `cost_by_user_day`.
- `data/scheduler_job_outcomes.json`: last-run outcomes, written by only 2 of 24 jobs (SA-036).
- The watchdog: a registry in `config/milestones.yaml`, checks in `core/ops/watchdog/checks.py`,
  and a run at 06:30 daily. It alerts through the existing push and email alerts, with dedupe. The
  Sunday heartbeat is email only.
- `ops_alerts`: job crash, zero output, and an LLM failure streak (needs 10 *consecutive* failures).
- Auth: `require_owner` accepts an owner session **or** `SCHEDULER_KEY`. That key can also
  *trigger* jobs, so it is too powerful to hand to a status reader.
- `/health` only says the web process is up. `/scheduler/status` shows the learning state per
  ticker and is owner-gated.
- Already on the board:
  - SA-033 (dependency lock: prevention);
  - SA-034 (degradation checks);
  - SA-035 (credit exhaustion);
  - SA-036 (job outcomes);
  - SA-037 (missed jobs at deploy);
  - SA-038 (lapsed-alarm hygiene).

  This design gives those stories one shared contract and adds the three missing pieces
  (§8).

---

## 4. Tools considered

The test for each tool: would it have caught the incidents in §1 sooner, at what cost, and what
data leaves Railway?

| Tool | Good at | Fit here | Cost and upkeep | Verdict |
|---|---|---|---|---|
| **Prometheus + Grafana** (self-hosted) | Continuous metrics from long-running services: request rates, latency, memory | Poor. Our failures are **once-a-day batch jobs**. An 8-second 08:00 refresh is one blip among thousands of scrapes, and batch jobs need a Pushgateway. `--workers 2` needs multiprocess mode. Two extra Railway services to run and secure, and its alerts still need a channel. | 2–3 new services, paid Railway usage, ongoing upkeep | **No** |
| **Grafana Cloud** (free: 10k series, 50 GB logs, 14-day retention) | Hosted log search, alerting on log patterns, and it accepts OTel | Could alert on `_req`, but only after shipping every log line off-platform. 14 days of retention. The things we care about (did the job produce rows?) still need our own code. | Free, but a second account and exported logs | **Not now**; possible later export target |
| **OpenTelemetry SDK** | A standard way to emit traces, metrics and logs to *any* backend | Does nothing without a backend. Adds many packages, against SA-033's lock goal. | Dependency churn | **Adopt its field names now, not the SDK** (§5.5) |
| **Arize** (AX SaaS / Phoenix, source-available) | LLM and ML observability: prompt traces, evals, drift | Our LLM *label* is known to be wrong (F02, until SA-012–SA-016), so drift or accuracy charts would look precise and mislead. Prompts carry portfolio context, which would be exported. Cost, tokens and failures are already in `llm_calls`. | SaaS data export, or a self-hosted Phoenix | **Not now.** Revisit after SA-016/SA-022. Phoenix locally on sanitized fixtures is fine for prompt debugging. |
| **Langfuse** (MIT) | LLM tracing, prompt versions, cost | Same label problem. Self-hosting needs Postgres + ClickHouse + Redis + S3. | Heavy | **Not now** |
| **Sentry** (free: 5k errors/month, 1 user, 30 days) | "A new kind of error appeared", with grouping | Would have flagged `_req` on day 1, but only if caught warnings were sent as events. Exports stack traces. `app_logs` gives us most of this in-app (§5.1). | Free, but data export | **Optional later** (D4) |
| **Healthchecks.io** (free: 20 checks, Telegram/Slack/email and more) | **Noticing silence**: a job that did not check in | Exactly the gap: container down, scheduler lost a job, email broken. It receives only a ping and a short status word. | Free, zero upkeep | **Yes** (D1) |
| **Railway built-ins** | Deploy failed/crashed webhooks, volume and CPU/RAM monitors, email and in-app notice | Covers a crashed container and a full volume. No log-pattern alerts. | Free, settings only | **Yes** (owner action) |

*Example, Prometheus vs. a ledger row:* on 23 Sep the 17:45 refresh finished "successfully" in
8 seconds with every ladder fetch failed. A Prometheus gauge would show "job ran". What we needed
was "ran, but produced 0 of 5 ladders". That is a fact the job must *write down*, whatever tool
stores it.

---

## 5. Design

```
 jobs & fetchers ──write facts──▶ OPS LEDGER (telemetry.db on the volume)
        │                              │
        │ after each critical job      ▼
        └──────────────────────▶ EVALUATOR (watchdog engine + registry)
                                       │  alert (deduped)   ──▶ push / email (existing)
                                       │  ok / fail ping    ──▶ HEALTHCHECKS.IO ──▶ Telegram
                                       ▼
                     GET /ops/status (read-only token) ◀── scripts/ops/fetch_status.py
                                                          (owner, Claude, any session)
 Railway: deploy failed/crashed, volume usage ──▶ email / in-app (no code)
```

### 5.1 Ops ledger: the facts (inside the app)

It lives in `data/telemetry.db`, the same file and migration style (`_add_column`) as today. It
needs no new database, and both workers already write to it.

| Table | One row per | Key fields | Story |
|---|---|---|---|
| `job_runs` | job execution | `job_id`, `scheduled_for`, `started_at`, `finished_at`, `status` (`ok`/`partial`/`failed`/`skipped_by_gate`), `produced` and `expected` (small JSON counts), `error_type`, `deploy_id` and `git_sha` (Railway env vars) | SA-036 (widened) |
| `source_health_day` | (day, source) | `ok`, `fail`, `last_ok_at`, `last_fail_at`, `last_error_type`, `last_error_sig` | **SA-040** (new) |
| `error_signatures` | normalized warning shape | `sig`, `logger`, `error_type`, `first_seen`, `last_seen`, `count` | **SA-040** |
| `budget_readings` | provider reading | `provider`, `ts`, `remaining`, `limit`, `usage_daily`, `status` (`ok`/`dark`) | SA-035 |
| `llm_calls` (existing) | LLM call | adds `status_code` and `error_class` (`credits`/`auth`/`rate_limit`/`network`/`invalid_output`/`other`) | SA-035 |

- **Sources** are a short fixed list:
  - `nse.bid_ladder`, `nse.calendar` and `nse.bhavcopy`;
  - `yfinance`;
  - `openrouter`, `tavily`, `serper` and `newsapi`;
  - `smtp`, `resend` and `webpush`.

  Each fetcher calls one helper, `record_source_result(source, ok, error_type)`. The helper
  never raises.
- **Error signatures** come from what `SQLiteLogHandler` already sees. The signature is the logger
  plus the message with numbers, dates and symbols masked. For example,
  `ipo_bids | fetch failed for <SYM> (non-fatal): 'NSE' object has no attribute '_req'`. At
  rollout the last 30 days of `app_logs` are loaded as *already known*, so today's routine noise
  (for example `^CNXAUTO possibly delisted`) does not alert on day one.
- **One outcome contract** (SA-036's rule). A single `record_job_run()` writes the history row and
  keeps `scheduler_job_outcomes.json` as the "last run" view that `/scheduler/status` already
  reads.

### 5.2 Evaluator: expectations (the existing watchdog, used more often)

These are new check types in `checks.py`, registered in `milestones.yaml`, with every threshold in
`config.yaml` via `cfg()` (SA-034's rule).

| Check | Fires when (example) |
|---|---|
| `job_ran` | A critical job has no `job_runs` row within its grace period: "`morning_brief` due 08:50, nothing by 09:05". Trading days and holidays come from the existing market calendar. |
| `job_output` | `produced` falls short of `expected`: "IPO refresh: ladders 0 of 5". |
| `source_failing` | The success ratio drops below a threshold across at least N attempts: "`smtp` 0 of 12 today". |
| `new_error_signature` | A WARNING+ signature appears for the first time in 30 days from a watched logger. At most one alert per signature per day. |
| `dataset_stale` | Per open IPO issue, the newest capture is older than K refresh cycles (SA-034's staleness). This also covers the EOD cache and the brief. |
| `credit_runway` | Remaining ÷ average daily spend is under D days: "OpenRouter 2.4 d < 5 d". A dark reading gives *unknown*, which is a warning and never "$0". |
| `budget_pct` | Monthly counter reaches 80% of plan (Serper, Tavily). |

**Cadence.** Checks still run at 06:30. In addition, **the job wrapper evaluates the checks scoped
to that job as soon as it finishes.** The IPO refresh therefore checks `job_output`,
`source_failing(nse.*)` and `dataset_stale(ipo)` at 17:45:10, not the next morning. This is what
achieves R5, and it is a small change (SA-034, widened).

### 5.3 Fetcher: `GET /ops/status` and `scripts/ops/fetch_status.py` (SA-041, new)

- **Auth:** a new `OPS_READ_TOKEN` header, read-only by construction. The route can only read and
  is **not** accepted by `require_owner`. An owner session also works. `SCHEDULER_KEY` is
  deliberately *not* accepted, so the more powerful key never needs to be handed out.
- **Sanitized payload:** counts, times, error types and signatures, public IPO symbols and budget
  numbers. No user ids or emails, no prompt text, no raw log lines. Rate-limited.
- **Verdict rules:** **RED** if a critical job is missed or failed today, a source is at 0% over
  at least N attempts, or runway is under 2 days. **AMBER** if something is stale, partial or
  under a warning threshold. **GREEN** otherwise. Every RED or AMBER line carries its evidence.
- **The CLI** prints a human summary and exits 0/1/2 for green/amber/red. It reads the token from
  the local environment, never from the repository, so the owner, Claude in any session, or a
  scheduled agent can run it. It replaces the ad-hoc `analysis_data/prod_probe_*.py` plus
  `railway ssh` routine.

Illustrative output. The job, source and freshness lines are **hypothetical**, since the 08:00 refresh had not been observed when this was written. The budget lines use measured figures:

```
StockAgent ops status — 2026-09-24 08:06 IST — deploy d9c459ae @ e8df088 — AMBER
 jobs     ipo_refresh_am 08:00 ok (ladders 5/5, snapshots 5) · ops_watchdog 06:30 ok
 sources  nse.bid_ladder 5/5 today (last fail 23 Sep 17:45 AttributeError) · openrouter 129/129 yday
 fresh    VARMORA captured 08:00 (0.1 h) · SWASTIKAIN 08:00 (0.1 h)
 budget   openrouter ~2.4 d left at $0.40/d  ← AMBER: top up before 25 Sep 16:30
          serper 2,590/2,500 (104%)          ← AMBER: set the real plan limit (SA-035)
 alerts   1 open: credit_runway(openrouter)
```

### 5.4 Outside witness: Healthchecks.io → Telegram (SA-042, new)

This revises the 2026-08-10 design's **D5** ("inside the app, liveness via a Sunday email
heartbeat"). The checks stay inside, but a **machine outside** now watches for silence. Relying on
a human to notice a missing Sunday email failed for nine weeks, because the email path was the
very thing that was down.

- About 11 checks, within the free tier's 20. They use cron schedules in `Asia/Kolkata` with
  grace periods:
  - `ops_watchdog`, `ipo_refresh_am`, `ipo_refresh_pm`, `morning_brief`, `rl_daily_review`,
    `ipo_deep_dive`, `bhavcopy_daily_sync`, `data_backup_nightly`, `audit_nightly` and
    `weekly_review`;
  - one `ops_status_green`, pinged by the 06:30 evaluator only when the verdict is not RED. It needs the SA-041 verdict, so SA-041 adds it.
- The job wrapper pings `/start` at the start and success or `/fail` at the end, with a status
  word (`ok`, `partial:ladders 0/5`). The ping runs on a daemon thread with a 3 s timeout and is
  never retried inline (R9). Ping URLs come from one env var, `HC_PING_KEY`. With it unset, the
  witness is off (the default in tests and locally).
- **The alert channel is Telegram** (D2), which is independent of Gmail/SMTP, of web push and of
  Railway.
- Healthchecks.io itself being down means no witness alerts that day. The inside path still
  works, and the two failing together is unlikely.

### 5.5 Standards without the weight

Records use OpenTelemetry semantic-convention names where one exists, for example `error.type`,
`gen_ai.request.model`, `gen_ai.usage.input_tokens` and `gen_ai.usage.output_tokens`. A future
export to Grafana Cloud, Sentry or Phoenix is then a mapping, not a rewrite. No OTel packages are
added now.

### 5.6 OpenRouter balance without a dangerous key

- `GET /api/v1/key` works with the **normal** API key. It returns `usage_daily` and
  `usage_weekly`, plus `limit_remaining` **if the key has a credit limit set**.
- `GET /api/v1/credits` (the true account balance) requires a **management key**. That key can
  create and delete API keys, so it must **not** live in production. The watchdog design's §9
  rejected a Railway token for the same blast-radius reason.
- **Plan (D3):**
  - The owner sets a monthly limit on the production key in the OpenRouter dashboard, for
    example $15/month. The app reads `/api/v1/key` daily and derives runway from
    `limit_remaining` and `usage_daily`.
  - SA-035's first-402 alert catches the case where the *account* runs dry before the key
    limit.
  - Optionally, the owner-side CLI can also read `/credits` with a management key kept only on
    the owner's machine.
- *Example:* after the 25 Sep top-up to about $10, with a $15 monthly key limit and roughly
  $0.40/day of spend, the reading is "25 days left (key limit)". If the account itself empties
  first, the first 402 raises "OpenRouter CREDITS exhausted" within minutes.

---

## 6. Replaying the incidents: acceptance fixtures

Each row becomes a deterministic test fixture (blocked transports, synthetic ledgers). An
independent invariant asserts both *detected* and *not falsely raised on the quiet twin*.

| Fixture | Expected detection | Quiet twin (must not fire) |
|---|---|---|
| SMTP `[Errno 101]` on every send | `source_failing(smtp)` on the first day, witness `/fail` from `morning_brief` | One transient timeout followed by success |
| `_req` AttributeError at the 17:45 refresh | `new_error_signature` plus `job_output` (ladders 0/5) at 17:45, `partial` to the witness | No open IPO window: 0 ladders expected, so nothing fires |
| NSE/SONA last capture 2.9 days old, issue still in the book | `dataset_stale(ipo)` | An issue's opening morning before 08:00 (the existing guard) |
| Deploy lands at 19:02, `ipo_deep_dive` due 19:00 | `job_ran` at the next evaluation, plus a missed witness ping by 19:30 | A holiday, or a gate-disabled job recorded as `skipped_by_gate` |
| OpenRouter $0.97, $0.40/day | `credit_runway` AMBER (2.4 d) | The reading fails (dark), giving *unknown*, never "$0 → RED" |
| Low-balance pattern: large calls get 402 while small ones succeed | First `credits`-class failure alerts at once | Interleaved 429s (rate limit), which are not classed as credits |
| Serper 2,590/2,500 | `budget_pct` | The month rolls over |
| Backup `emailed=False` | `job_output` gives `partial`; witness `/fail` | Backup disabled by config: `skipped_by_gate` |
| Container down for 26 h | Healthchecks: `ops_watchdog` and `ops_status_green` missing | — |

---

## 7. Risks and how the design contains them

| Risk | Containment |
|---|---|
| Alarm fatigue (8 of 9 milestones lapsed, with weekly criticals) | SA-038 first; every new check has a quiet-state test. Per-signature and per-check daily dedupe. Every alert names a first action. |
| A monitoring bug breaks a job | Every write, ping and read is wrapped and never raises (R9). Tests include a crashing ledger and an unreachable witness. |
| SQLite contention across 2 workers | Short transactions (the pattern `app_logs` already uses). Day-bucketed counters are upserts, not a row per call. |
| Token leakage | `OPS_READ_TOKEN` can only read sanitized status. Rotate it by changing the env var. Tokens are never logged. |
| Job-time drift and holidays | Expectations come from the scheduler's own triggers plus the market calendar, not a second hand-kept list. An inventory test fails if a registered job has no expectation. |
| Data leaving Railway | Only Healthchecks.io, which receives job names, times and status words. No user data (R11). |

---

## 8. Mapping to the board

The owner has ordered **SA-039 first**. Nothing here changes that.

| Story | Change | Size | Depends on |
|---|---|---|---|
| **SA-036** (widen) | `record_job_run()` → `job_runs` history with `expected`/`produced`, `deploy_id`/`git_sha`, plus the last-run JSON view. This is also the single wrapper that later pings the witness and triggers post-job evaluation. | 3 → 4 | — |
| **SA-035** (amend) | Add the `budget_readings` table. Use `/api/v1/key` with the normal key, not a management key. Add `invalid_output` as an LLM error class (the ThesisReviewer truncation). | 3 | — |
| **SA-040** (new) | Per-source health ledger and new-error-signature detection, seeded from 30 days of `app_logs` | 3 | — |
| **SA-034** (widen) | The evaluator checks in §5.2, **plus post-job evaluation** of job-scoped checks | 5 → 6 | SA-036, SA-040 |
| **SA-041** (new) | `GET /ops/status` with `OPS_READ_TOKEN`, plus `scripts/ops/fetch_status.py`, with the verdict rules and a sanitization test; also pings `ops_status_green` when the witness is enabled | 3 | SA-036, SA-040 |
| **SA-042** (new) | Healthchecks.io witness: pings from the job wrapper, off unless `HC_PING_KEY` is set. Includes a runbook for the account and Telegram setup. | 2 | SA-036 |
| SA-033, SA-037, SA-038 | Unchanged. SA-033 *prevents* the next `nse`-style break; SA-037 recovers missed runs; SA-038 clears alarm noise. | — | — |

**Owner actions** (settings only, no code and no deploy):

- On Railway: turn on alerts for deploy failed/crashed and volume usage.
- On OpenRouter: set a monthly credit limit on the production key.
- If D1 and D2 are yes: create the Healthchecks.io account and connect Telegram.

**Suggested order:** SA-039 → SA-036 → SA-035 → SA-040 → SA-042 → SA-034 → SA-041, with
SA-038 whenever convenient. The first four fit Sprint 1's spirit (make failure visible). Where
SA-040–SA-042 sit in sprints is D5.

**Later, only if needed:**

- Export to Grafana Cloud or Sentry through the §5.5 names.
- Arize Phoenix or Langfuse, once SA-012–SA-016 fix the label and SA-022 needs prospective
  evaluation.
- A learning-health panel in `/ops/status` (weight drift against defaults, from SA-039's
  diagnostic record), shown as data, never as a benefit claim.

---

## 9. Decisions for the owner

| # | Question | Plain example | Recommendation |
|---|---|---|---|
| D1 | Allow **one outside service** (Healthchecks.io, free)? | It would receive "`morning_brief` started 08:50:01, ok". Nothing about you or your portfolio. | **Yes.** It is the only way to hear about silence when the container or email is down. |
| D2 | Which **independent alert channel**? | During the email outage, a Telegram message would still have arrived. | **Telegram** (free, a phone app). Email to a *second* address as a backup. |
| D3 | **OpenRouter key limit** instead of a management key in the app? | A $15/month limit lets the app see "25 days left" with its normal key. A management key could delete your keys if leaked. | **Yes, set the limit.** Keep any management key on your machine only. |
| D4 | **Sentry** now or later? | Sentry would group `_req` as a new issue. SA-040's signatures do the same inside the app, with no export. | **Later**, only if SA-040 proves too noisy or too blind. |
| D5 | **Board:** add SA-040–SA-042 and widen SA-034/035/036 as in §8? | This is +8 new points plus +2 widened; Sprint 1 is at 35 points today. | **Yes.** Place SA-040 and SA-042 in Sprint 1 and SA-041 in Sprint 2, after SA-039. |

---

## Sources (external facts checked 2026-09-24)

- OpenRouter: [`/api/v1/key` and limits](https://openrouter.ai/docs/api-reference/limits),
  [`/api/v1/credits` needs a management key](https://openrouter.ai/docs/api/api-reference/credits/get-remaining-credits).
- [Healthchecks.io plans](https://healthchecks.io/pricing/) (Hobbyist: 20 checks, integrations include Telegram).
- Railway: [observability dashboard and monitors](https://docs.railway.com/observability),
  [webhooks](https://docs.railway.com/observability/webhooks),
  [alerts for crashes and failed deploys](https://docs.railway.com/guides/alerts-crashes-failed-deploys).
- [Sentry pricing overview](https://blog.struct.ai/sentry-pricing-error-monitoring-2026/) (Developer: 5k errors/month, 1 user, 30 days).
- [Grafana Cloud free tier](https://grafana.com/products/cloud/free-tier/) (10k series, 50 GB logs, 14-day retention).
- [Arize Phoenix vs Langfuse](https://www.morphllm.com/comparisons/arize-phoenix-vs-langfuse) (licensing and self-host footprint).
