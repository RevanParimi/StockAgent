# Operational Watchdog — design

**Date:** 2026-08-10
**Status:** approved, not yet implemented
**Codename:** the watchdog

---

## 1. Problem

On 2026-08-08 the Atlas C11 live cutover missed its window. The fallback slot
(Sun 2026-08-09) was missed too. Both were discovered on 2026-08-10 only
because the user asked a question that happened to touch prod state. The next
slot is Sat 2026-08-15 — the miss cost a full week, and nothing in the system
would have surfaced it.

This is not an isolated incident. The same shape has recurred:

- The Aug 1 scorecard and monthly forecast ran on a Saturday, and whether the
  Learning Evidence email actually went out is *still* unknown.
- The auditor graded 0/119 on its first prod run. 84 green tests hid it,
  because the one function that touched the network was the one function
  never tested against it.
- Several validation checkpoints (F2 ≈ 8/28, F3 ≈ 9/04, hard-bind observation)
  exist only as dates in prose.

### Root cause

**Every milestone lives in Claude's memory files, which prod cannot read.**

`MEMORY.md` and `project_*.md` sit on the user's workstation, outside the
deployed image. Prod has a scheduler running 20 jobs, a delivery layer with
push and email, and an ops-alert channel — and no knowledge whatsoever of what
it is supposed to be waiting for. Discovery is therefore *pull*: it happens
when, and only when, a human asks.

The fix is not "add a notification." It is to move date-bound truth into a
place prod can see, then let prod do the watching.

---

## 2. Goals / non-goals

**Goals**

1. Prod detects, unprompted, that a milestone is due, at risk, or lapsed.
2. Prod auto-runs the safe, idempotent preparation so the human's remaining
   step is a single action, already validated.
3. Standing invariants ("this should always be true") are checked continuously,
   not only when someone SSHs in.
4. Silence is trustworthy: if nothing arrives, nothing is due — and the user
   can distinguish that from a dead watchdog.
5. Milestones survive Claude losing all context.

**Non-goals**

- No UI. No runtime editing of the registry. No new infrastructure.
- The watchdog does not perform irreversible actions (see §8).
- Not a general alerting platform; `ops_alerts` already covers job crashes,
  zero-output, and LLM failure streaks, and is reused rather than replaced.

---

## 3. Decisions taken

| # | Decision | Rationale |
|---|---|---|
| D1 | Notify **+ auto-run safe prep**; the irreversible step stays human | Prod has no Railway token, so it cannot flip env vars. Prep is what it *can* do. |
| D2 | **Silent unless actionable**, plus a weekly heartbeat | A message that usually says "nothing to do" is the message people stop opening. |
| D3 | Track **milestones and standing invariants** | Same engine; an invariant is a check with a recurring window and no deadline. |
| D4 | **Committed registry is authoritative**; memory points at it | Kills the root cause. Prod ships with it; it cannot disagree with what Claude believes. |
| D5 | Build **inside the app** (new scheduler job), not external cron | Reuses scheduler + delivery + ops_alerts. Liveness bought via the heartbeat instead. |
| D6 | **No Railway API token** | See §9. A volume-backed runtime flag is strictly better and is sequenced as follow-on work. |

---

## 4. Architecture

```
config/milestones.yaml            authoritative registry (ships in the image)
        |
        v
core/ops/watchdog/
    registry.py    load + validate YAML -> list[Milestone]
    checks.py      named check functions -> CheckResult
    prep.py        named prep functions  -> PrepResult (idempotent, safe)
    engine.py      PURE: (registry, now, results, prior_state)
                         -> (notifications, new_state)
        |
        v
services/scheduler/python/scheduler.py     job "ops_watchdog", 06:30 IST daily
        |
        v
core/delivery/ops_alerts.py -> alerts.emit_alerts_broadcast -> push + email
        |
        v
data/watchdog_state.json    last level notified per id, last_run_ts
```

The engine is a pure function so the entire escalation ladder is table-testable
against a synthetic clock, with no prod, no scheduler, and no I/O.

---

## 5. The registry

`config/milestones.yaml` — a separate file, not a new section of the already
large `config.yaml`.

```yaml
milestones:
  - id: atlas_c11_cutover
    kind: milestone
    title: "Atlas C11 live cutover"
    check: atlas_cutover_pending
    prep: atlas_cutover_prep
    window: {weekdays: [sat, sun]}     # when the action may be performed
    deadline: 2026-08-15               # after this, escalate and keep escalating
    lead_days: 3                       # begin warning this far ahead
    action: >
      Set ATLAS_ENABLED=true in Railway and redeploy.
      Rollback at any time: set it false.
    docs: docs/superpowers/plans/2026-07-26-atlas-user-data-program.md

invariants:
  - id: serper_month_rollover
    kind: invariant
    title: "Serper quota counter rolled into the current month"
    check: serper_counter_current_month
    schedule: monthly                  # evaluated on/after the 1st
```

**Fields.** `id` (stable, used as the state key and alert dedup key), `kind`,
`title`, `check`, optional `prep`, optional `window`, optional `deadline`,
`lead_days` (default 3), `action` (human instructions, embedded verbatim in the
notification), `docs`.

**Evaluation frequency.** Every entry's check runs on every daily run. `window`
and `schedule` govern *notification*, never evaluation — the watchdog always
knows current state, it just stays quiet outside the relevant period. An
invariant with no `schedule` may notify on any day; `schedule: monthly` means
it may notify only on or after the 1st of a month, once per month.

**`lead_days` against a recurring window.** For a milestone with both a
recurring `window` and a `deadline`, `lead_days` counts back from **the next
occurrence of the window**, not from the deadline. Atlas C11 with
`weekdays: [sat, sun]` and `lead_days: 3` therefore warns from Wednesday,
every week, until it is satisfied or the deadline lapses. Without a `window`,
`lead_days` counts back from the `deadline`.

**Validation** at load: unknown `check`/`prep` names, duplicate ids, malformed
dates, and unknown fields are hard errors surfaced as an `unknown`-state alert
rather than a silent skip. A registry that fails to parse must be loud.

---

## 6. Checks

```python
@dataclass(frozen=True)
class CheckResult:
    state: Literal["satisfied", "pending", "blocked", "unknown"]
    detail: str            # one line of evidence, shown to the human
    evidence: dict         # structured, persisted to state
```

Registered by name so YAML stays declarative while logic stays testable:

```python
@check("atlas_cutover_pending")
def atlas_cutover_pending() -> CheckResult: ...
```

**State semantics**

- `satisfied` — nothing to do. **This is how a milestone closes.** When the user
  finally sets `ATLAS_ENABLED`, the check flips to satisfied on its own; there
  is no checkbox to tick and no bookkeeping to forget.
- `pending` — action needed, preconditions met.
- `blocked` — action needed but a precondition fails (e.g. pre-flight dirty).
  Distinct from `pending` because the human's next step is different.
- `unknown` — the check itself raised. **Notifies.** A check that cannot answer
  must never be silently treated as satisfied.

That last point deliberately inverts the codebase's usual "never raise, stay
quiet" posture. Every other job swallows errors so it cannot take down the
process; the watchdog swallows the error but *reports* it, because a watchdog
that fails quietly is worse than no watchdog. The job wrapper still never
propagates an exception to the scheduler.

### v1 checks

| id | Kind | What it asserts |
|---|---|---|
| `atlas_cutover_pending` | milestone | `ATLAS_ENABLED` set; if unset, reports pre-flight cleanliness (`atlas.db` absent, `portfolio/` = only `primary`) |
| `f2_validation_due` | milestone | 20 trading days elapsed since 2026-07-31; miss_type distribution comparable |
| `f3_checkpoint_due` | milestone | 20 trading days elapsed since the 2026-08-07 deploy |
| `hard_bind_observation` | milestone | Post-bind observation window elapsed since 2026-08-03 |
| `serper_counter_current_month` | invariant | `api_usage` counter month == current IST month |
| `audit_graded_when_due` | invariant | Nightly graded > 0 on days where rows matured (the 0/119 signature) |
| `monthly_scorecard_written` | invariant | Previous month's `<YYYY-MM>_scorecard.json` exists |
| `news_blind_rate_ok` | invariant | Blind ratio in the last review stays at/near 0 (F1 regression guard) |
| `deploy_matches_origin` | invariant | Running commit == `origin/main` HEAD |

`deploy_matches_origin` earns its place specifically because it catches the one
way this whole design can rot: a milestone added to the registry but never
deployed leaves prod blind to it.

---

## 7. Escalation ladder

Evaluated per milestone, per run:

| Condition | Level | Repeat |
|---|---|---|
| Outside lead window | — | silent |
| Within `lead_days` of window/deadline | `info` | once |
| Action window open, state `pending` | `warning` | once per day open |
| Action window open, state `blocked` | `warning` | once per day, different copy |
| Past `deadline`, still pending | `critical` | weekly, indefinitely |
| `unknown` | `warning` | once per day |
| Transitions to `satisfied` | `resolved` | once, then silent |

Transitions are computed against `data/watchdog_state.json`, which stores the
last level emitted per id. The alerts layer's existing `date|kind` dedup is the
second line of defence against duplicates.

A lapsed deadline **never goes quiet**. That is the specific failure being
designed against.

### Heartbeat

The Sunday run additionally emits an email-only digest: everything tracked, its
state, and the next due date. Email-only because a push notification saying
"all clear" trains the user to dismiss push. Its real job is liveness: **no
heartbeat on Sunday means the watchdog is dead**, which is the cheap substitute
for external monitoring (§ D5).

---

## 8. Prep (auto-run)

A milestone may name a `prep` function. Prep must be **idempotent** and must not
perform the irreversible step. For Atlas C11 that means: run the pre-flight
assertions, run `scripts/atlas_etl.py`, run the step-5 validations from §6 of
`docs/superpowers/plans/2026-07-26-atlas-user-data-program.md` — and stop. It
does not flip the flag.

```python
@dataclass(frozen=True)
class PrepResult:
    ok: bool
    transcript: list[str]     # appended verbatim to the notification
```

The transcript rides in the notification so the message reads "prep done and
verified, one step left," not "go and check." Gated by `watchdog.prep_enabled`
(config.yaml, no env) so it can be disarmed to notify-only without a code
change. Prep runs only when the window is open and the check is `pending`.

---

## 9. Rejected alternative: a Railway API token

Considered so prod could flip `ATLAS_ENABLED` itself. Rejected:

1. **Blast radius.** A project token inside the container can rewrite every
   variable in the environment, including `OPENROUTER_API_KEY`,
   `SMTP_PASSWORD`, `VAPID_PRIVATE_KEY` and `GITHUB_TOKEN`. That is a large
   new credential in a process that serves public traffic, in exchange for
   setting a boolean.
2. **It does not avoid the redeploy.** Setting a Railway variable triggers a
   new deployment, which kills the watchdog mid-cutover. Hard to make atomic,
   harder to verify.
3. **It contradicts the standing config rule** that non-secret toggles use
   `cfg()` with no `env=`, because managing Railway env is painful.

**Sequenced follow-on instead:** a volume-backed runtime flag —
`data/runtime_flags.json`, read through `cfg()` with precedence
`runtime > env > yaml > fallback`, restricted to an allowlist of non-secret
keys. Strictly better: instant flip, instant rollback, no redeploy, no restart,
an audit row per change, no new credential.

Its real cost, to be scoped separately: `ATLAS_ENABLED` was designed as a
*freeze-cutover* gate where the redeploy supplied a clean process boundary.
Hot-flipping requires auditing every module that reads the flag once at import
and ensuring caches and connections tolerate a mid-process change.

---

## 10. Scheduling

New job `ops_watchdog`, **daily 06:30 IST**, `misfire_grace_time=6h`,
`coalesce=True`, `replace_existing=True`, gated by `watchdog.enabled`
(default true, config.yaml).

Deliberately *not* in the 23:xx cluster with the other jobs: a "your window is
open today" notice delivered at 23:45 has wasted the day it is announcing.
06:30 on a Saturday leaves the whole weekend to act.

---

## 11. Testing

- **Engine** — table-driven over a synthetic clock and synthetic
  `CheckResult`s, covering every rung of §7 including deadline lapse,
  re-escalation, `unknown`, and `satisfied` auto-close. No I/O.
- **Registry** — valid load; duplicate id, unknown check name, malformed date,
  and unknown field each rejected loudly.
- **Checks** — each against fixtures for satisfied / pending / blocked, plus a
  raising dependency yielding `unknown` rather than an exception.
- **Prep** — idempotence (running twice equals running once) and that it never
  performs the irreversible step.
- **Integration** — the job registers, runs, and cannot raise into the
  scheduler; a registry that fails to parse still produces an alert.

Suite must stay green: baseline at time of writing is 2525 passed / 12 skipped.

---

## 12. Memory change (part of the work, not a follow-up)

`MEMORY.md` and the `project_*.md` files stop carrying dates for anything in the
registry and instead point at `config/milestones.yaml`. New milestones land in
the **same commit** as the work that creates them.

Without this step the design fails D4: two lists that drift, with the drift
invisible until something is missed again — exactly today's failure mode.

---

## 13. Known limitations

1. **Registry reaches prod only on deploy.** A milestone added but not pushed
   leaves prod blind. Mitigated by the `deploy_matches_origin` invariant.
2. **The watchdog cannot complete the Atlas cutover.** By §9 it prepares and
   notifies; the flag flip is human until the runtime-flag work lands.
3. **Single-process liveness.** If the app is down the watchdog is down; a
   missing Sunday heartbeat is the signal.
4. **Trading-day arithmetic** for the 20-td checkpoints depends on the existing
   market calendar; a calendar gap yields `unknown`, not a wrong date.
