# FIX-008 — implementation receipt

**Story:** [FIX-008](../stories/FIX-008.md) · **Phase:** implementation, with same-conversation
self-review only · **Date:** 2026-10-13, about 08:25–09:20 IST · **Baseline:** `33ae170`
(`33ae170` = SA-011, FIX-007 and their docs, committed; pushed by a peer session at the owner's
word at 09:07:07 IST, during this phase) plus the owner's uncommitted `docs/README.md` probe
line, which is not FIX-008's · **Status after this phase:** `review_required`

## How this phase came about

A new conversation opened with "continue". FIX-008 was STATE's `next_task`: the first planned
`todo` story whose dependency (SA-011) is `done`. No production state was read, nothing was
committed, pushed or deployed by this session, no production variable was changed and no
notification was sent. All 38 peer sessions were idle at the start; one (`stockagent-main-3d`)
later pushed the four held commits at the owner's word and left the push note to this session's
bookkeeping.

## What changed

**Before (code inspection).** `alert_audience()` (`core/delivery/alerts.py`) is every account
with a push subscription plus `PORTFOLIO_DEFAULT_USER_ID`, and the seven operator callers sent
through `emit_alerts_broadcast()` to each. Each audience account gets its own push and its own
email: since SA-006, `resolve_recipient()` gives each account its own address. The Inbox's
`GET /delivery/alerts` returned the shared sent-log's tail to any signed-in account: every
account's records, so a member also read the owner's advisor escalations and lock-in alerts.

**After.**

- **One owner audience.** `owner_audience()`: every `users.db` account whose role is `owner`
  (`user_store.owner_ids()`), or the default user when there is none. A failed lookup also falls
  back to the default user, with a warning: it narrows, never widens. The first signup is the
  owner and takes the default portfolio id (`auth_api.signup`), so this is normally one id; its
  email goes to the owner's account address, or `DELIVERY_EMAIL_TO` when no account row exists.
- **Operator callers** now use `emit_owner_alerts()`:

  | Caller | Notice |
  |---|---|
  | `core/ops/watchdog/runner.py` `_broadcast` (also the registry-broken path) | Watchdog milestones and invariants |
  | `core/delivery/ops_alerts.py` `_emit`, `alert_job_partial_output` | LLM failure streak, crashed, zero or partial job output |
  | `core/audit/thresholds.py` `emit_breaches` | Verification-audit breaches |
  | `core/portfolio/reconcile.py` `_alert` | Ledger drift, names a user |
  | `core/portfolio/store.py` `PortfolioStore._alert_quarantine` | Corrupt `portfolio.json`, names a user |
  | `core/portfolio/universe.py` `_emit_ops_alert` | Universe budget governor |
  | `scripts/atlas_etl.py` `_emit_ops_alert` | Atlas ETL quarantine |

- **Market callers are unchanged** on `emit_alerts_broadcast()`: index reconstitution
  (`index_watch.run_index_watch`), discovery shelf adds (`run_discovery_cycle`), the pre-open
  re-forecast (`AutomobileScheduler._preopen_shock_check_job`). Both functions share `_emit_to`.
- **Inbox.** `load_recent_alerts(user_id=...)` keeps only that account's records, newest first;
  a record written with no user id, or `""`, belongs to the default user. The route passes the
  caller's id.
- **Registry.** `config/milestones.yaml` gains the invariant `error_backlog_triaged`
  (`check: error_backlog`; no window, deadline or schedule, so daily). Its action names
  `GET /ops/errors` and `python scripts/prod_errors.py --base <app URL>` and the three triage
  statuses. The engine's ladder for it: pending → one warning ("Due now.") per day; unknown → one
  warning per day; satisfied after anything else → one "resolved" notice with no next step, then
  silence. It has no deadline, so it never lapses to a weekly critical. The check's docstring and
  SA-011's pinning test change with it.

**Example.**

| Notice | Before | After |
|---|---|---|
| 06:30 watchdog: backup not confirmed off-site | the owner's devices and the member's phone; one email to each account's address | the owner's devices; one email to the owner |
| Ledger drift "for user '<id>'" | the same; the id reaches the member | the owner only |
| Discovery shelf add (market) | both | both, unchanged |
| The member opens Inbox → Alerts | every account's records: operator notices, the owner's advisor exits | the member's own alerts and market notices |

**Scope decision (delegated, recorded).** The card's table lists broadcasters; grepping the
delivery layer (its hard-review item) found that the Inbox read serves the shared log to everyone.
Without the filter a member still reads every operator notice in the Inbox, so the card's
"the member gets nothing" would be false on one channel. It is one function and a route argument,
with its own tests, so it is included under the privacy-first rule rather than routed to a new
card.

**The card's "two emails in one mailbox"** holds only if the member's address lands in the
owner's mailbox (a plus-alias, say): by code each account's email goes to its own address. Either
way the member's copy is gone and the owner's mailbox gets one email per notice.

## Invariant tests

`tests/unit/test_operator_notices_owner_only_fix008.py`, **22 tests**. Transports are recorded at
their lowest seams: pywebpush's `webpush` and `smtplib.SMTP`. Everything above them is real: a
temporary `users.db` with an owner (the default portfolio id) and a member, both push-subscribed
(the owner on two devices); the real `PushStore`, `deliver`, `resolve_recipient`, `send_email`
and sent-log; the real application for the Inbox.

- **Operator callers** (9, one per path, each through its own code): the registry-broken watchdog
  run, a due watchdog entry, a crashed job, partial output, an audit breach, ledger drift, a real
  corrupt `portfolio.json` quarantined on load, the universe budget, an Atlas ETL quarantine. Each
  owner device gets 1 push, the member's 0; the owner's mailbox gets exactly 1 email and no other
  address gets any.
- **Market callers** (3): the real `run_index_watch` with a fake NSE client, the real
  `run_discovery_cycle` with stage seams, the real pre-open job with `run_preopen_check` stubbed.
  Both accounts get it; the member's email goes to the member's address.
- **A planted user id** (2): drift and quarantine name `u_planted7f3a9c`. It reaches the owner's
  push, email and Inbox, and never the member's push, email or Inbox (member session, real app).
- **Inbox** (1): each account sees its own advisor alert and not the other's; legacy records with
  no key or a blank id belong to the owner; market notices appear once per account; newest first.
- **Outbox path** (1): with Atlas on, an operator notice queues rows for the owner only and a
  market notice for both; nothing is sent inline.
- **No accounts** (1): the default user's subscription and `DELIVERY_EMAIL_TO` get it once; an
  orphan subscription under another id gets nothing.
- **Failed owner lookup** (1): the default user only, with a warning; the member gets nothing.
- **Role** (1): members never become the owner audience; an owner account with another id
  replaces the default.
- **The registered entry, end to end** (1): a real `telemetry.db` holds one fresh WARNING row
  whose text carries a planted user id and a marker word that survives normalisation, so it is in
  the stored template. The real check reads it through the real backlog `report()`; the real
  registry (the hermetic sandbox's copy of `config/milestones.yaml`), engine and runner act on it.
  Day 0: one warning with the entry's title, "Due now." and `GET /ops/errors`. Day 0 again:
  nothing. Day 1: one more. After `triage(..., status="acknowledged")`, day 2: one "Now satisfied
  — closing." with no next step. Days 3 and 4: nothing. Three emails in all, every one to the
  owner; none carries the marker word or the planted id; the fingerprint is named.
- **Registry file** (1): exactly one entry uses `error_backlog`; it sits under `invariants:` with
  no window, deadline or schedule; its action names the steps.
- **Guard** (1): an AST scan of `core/`, `services/`, `scripts/` and `src/` finds every call to
  `emit_owner_alerts`, `emit_alerts_broadcast`, `emit_alerts`, `owner_audience`, `alert_audience`
  and `_emit_to`, following import aliases. Outside `alerts.py` it must equal the classified table:
  8 operator sites, 3 market sites and 2 own-account sites (`run_morning_brief`,
  `run_post_review_pipeline`). Inside `alerts.py`, only the expected wiring.

**Existing tests changed:** `tests/unit/ops/test_error_backlog_sa011.py` (the pin "no registry
entry enables the check" becomes "one entry enables it and `_broadcast` emits to the owner only";
docstring); `tests/unit/test_alerts_wave_f.py` (the source assertion now expects operator sites on
`emit_owner_alerts`); `tests/unit/audit/test_audit_thresholds.py` and the two SA-004 tests
(`test_review_outcomes_feedback_sa004.py`, `test_daily_review_outcomes_sa004.py`) patch
`emit_owner_alerts`, the function their operator alerts now call.

**Mutations** (in memory; repo files never written; `analysis_data/fix008/swap_plugin.py`,
`FIX008_SWAP`), over the new file and SA-011's (133 tests):

| Variant | Result |
|---|---|
| None (the change as written) | 133 passed |
| `base`: the 11 changed modules as at `33ae170`, proved by blob id | **caught:** 18 failed (the member received; the planted id reached the member; the owner's Inbox listed the member's alert; the outbox queued both; the backlog sent 2 emails) |
| M1: `emit_owner_alerts` sends to `alert_audience()` | **caught:** 16 failed |
| M2: the Inbox filter ignored | **caught:** 3 failed |
| M3: `reconcile._alert` left on the broadcast | **caught:** 5 failed |
| M4: a failed owner lookup widens to `alert_audience()` | **caught:** 1 failed |
| M5: the default user always added to the owners | **caught:** 1 failed |
| M6: a blank `user_id` no longer belongs to the default user | **caught:** 1 failed |
| M7: `owner_ids()` returns every account | **caught:** 14 failed |
| M8: the watchdog runner left on the broadcast | **caught:** 4 failed |
| M9: the Inbox route stops passing the caller | **caught:** 3 failed |
| M10: the backlog notice carries the template | **caught:** 2 failed |
| M11: the owner also emitted as a blank id (a second push and email) | **caught:** 15 failed |
| M12: a market caller moved to the owner only | **caught:** 3 failed |

After these runs one test, `test_without_accounts_the_default_user_is_the_owner`, was reordered so
that on base it fails on behaviour before it reaches the new function; rerun alone on base, it
fails because the orphan subscription received the push.

The guard reads source files, which an in-memory swap cannot change, so
`analysis_data/fix008/guard_probe.py` runs the guard's own code (taken from the test file by AST)
over a temporary copy of the four source folders:

| Planted change | Guard |
|---|---|
| None (control) | passed |
| G1: a new module calling `emit_alerts_broadcast` under an import alias | **caught** |
| G2: `reconcile._alert` back on the broadcast | **caught** |
| G3: a module looping `emit_alerts` over `alert_audience()` | **caught** |
| G4: a second market call inside `brief.py` | **caught** |

## Commands and environment

Windows 11, Python 3.13, pytest 9.0.3, the project's `.stockai` virtual environment; every
Python run passes through `tests/hermetic.py`.

- `python -m pytest tests/unit/test_operator_notices_owner_only_fix008.py -q -p no:cacheprovider`
  → 22 passed (about 16 s).
- Neighbours: the new file, `tests/unit/ops`, `test_alerts_wave_f.py`, `test_delivery_alerts.py`,
  `test_delivery_api.py`, `audit/test_audit_thresholds.py`, both SA-004 files,
  `test_index_watch.py`, `test_discovery_cycle_ipo.py`, `test_preopen_check_scheduler.py`,
  `test_atlas_etl.py`, `test_delivery_test_isolation.py` and the reconcile, portfolio-store,
  universe, user-store and auth files → **502 passed**.
- `python scripts/ci/check_broad_except.py` → OK (154 grandfathered); `test_broad_except_guard.py`
  passes.
- Mutants: `bash analysis_data/fix008/run_swaps.sh` (results in `swap_results.txt`); guard probe:
  `python analysis_data/fix008/guard_probe.py` (`guard_probe.txt`).
- Full suite: `python -u -m pytest -q -rfEs -p no:cacheprovider tests -o console_output_style=count`
  → **4493 passed, 12 skipped, 0 failed** (10 min 28 s), on the manifest's code and test bytes. The KT wording and the PDF changed during the run; no test reads them, and `check_kt_docs` ran after.
- Runtime data: `analysis_data/fix008/data_fingerprint.py` (path, size and mtime of every file
  under `data/`, `logs/`, `outputs/` and `config/`; no contents read): 801 files, `e715a34c…` before and after the full suite (unchanged)
- Docs: KT PDF rebuilt (source `5835a9677b62597c7b344eca543b1ac3be8709875b751c4051565b0157e3370d`,
  393,629 bytes); `check_kt_docs` errors `[]`.

## Documentation

- [KT](../../../TECHNICAL_DESIGN.md) section 10: "Delivery" gains the alert audiences (operator,
  market, an account's own; the Inbox's per-account read; the classifying test) with the backup
  example; "Observability and the watchdog" says its notices reach only the owner; the backlog's
  "Watchdog" bullet describes the registered entry instead of "No `milestones.yaml` entry uses
  it". Section 3's `error_backlog.*` row. Section 12: the fixes outside the SA numbering include
  FIX-008, and its roadmap row is added as `Open` until the commit, as FIX-007's was. PDF rebuilt.
- [ARCHITECTURE](../../../ARCHITECTURE.md) Operations: Delivery, Operations backlog and Watchdog.
- [PRODUCT_MAP](../../../PRODUCT_MAP.md): section 11's Alerts row; section 17's Watchdog and
  Operations backlog.
- [CODEBASE](../../../../CODEBASE.md): the `alerts.py` tree note, the `/delivery/alerts` row, the
  watchdog and backlog module rows.
- [Testing guide](../../../TEAM_TESTING_GUIDE.md): cases **10-G** (a member with push on receives
  no watchdog notice; each Alerts tab lists its own) and **12-K** (the backlog entry's daily
  warning and single close); HT-10's and HT-12's related PI lists.

## Manifest and digest

- **Review input:** [FIX-008-manifest.json](FIX-008-manifest.json), 24 files. The SHA-256 of its
  LF bytes is **`a7a7b58ec545b22d31ece03f8cb375dce51b8ae694c4feb5759aa0ab9709a682`**, and `kt_manifest.py verify` gives 0 mismatches.
  - Code and config (12): `config/milestones.yaml`, `core/audit/thresholds.py`,
    `core/delivery/alerts.py`, `core/delivery/ops_alerts.py`, `core/ops/watchdog/checks.py`,
    `core/ops/watchdog/runner.py`, `core/portfolio/reconcile.py`, `core/portfolio/store.py`,
    `core/portfolio/universe.py`, `scripts/atlas_etl.py`, `services/api/routes/delivery_api.py`,
    `services/data/stores/user_store.py`.
  - Tests (6): the new file and the five changed ones above.
  - Docs (6): CODEBASE, ARCHITECTURE, PRODUCT_MAP, the guide, the KT and its PDF.
  - Excluded: STATE, HANDOFF and this receipt (bookkeeping), and the owner's `docs/README.md`.
- **Diff digest:** **`48b3521d7bebda03faf39bb02df1bd3ab7c4d7c42b5f5af5dabae9aaf5da2658`**, 74,505 bytes over 23 paths (every manifest path except the PDF).
  - **The base** is `33ae170`, which holds SA-011's and FIX-007's accepted files; no
    uncommitted peer change sits under FIX-008's paths. `analysis_data/fix008/base_snapshot.py`
    writes the 11 swapped modules from `33ae170` and proves each by blob id.
  - **To rebuild:** `analysis_data/fix008/diff_digest.py`: `git diff --no-color 33ae170 -- PATH`
    for tracked paths and `git diff --no-index --no-color /dev/null PATH` for the new test file,
    over the sorted paths, concatenated.

## Self-review

No critical, high or medium finding. Most severe first:

- **I1 (low, residual; owner decision). Copies already in the sent-log.** Before this deploy the
  broadcast recorded each operator notice once per audience account, so the member's own id
  carries copies in `data/delivery/alerts_sent.jsonl`. They are the member's records, so the new
  Inbox read still lists them to that member until rotation trims the log (at 4,000 lines, keeping
  2,000). Nothing new is added. The only member today is the owner's test account. Options: leave
  them, or an owner-authorized one-off cleanup of operator-kind records under non-owner ids. That
  changes production data, so it was not done. **Owner decision (13 Oct about 12:35 IST): leave them.** Only
  the pre-fix test account carries copies, they reached its phone when sent, and its Alerts tab
  shows its 20 newest records, so they drop off as new notices arrive. A cleanup would rewrite
  the live sent-log, which also deduplicates notices. If the test account goes to someone who
  should not see operator notices, delete that account instead.
- **I2 (info, pre-existing; the card's hard-review item). Delivery failure and watchdog state.**
  The runner keeps its state only when the notify call raises. `emit_owner_alerts` never raises,
  as `emit_alerts_broadcast` never did, so a notice no transport accepted still advances the
  state: its sent-log record says `delivered: false` and the owner's Inbox lists it. A pending
  entry warns again the next day; a one-time "resolved" notice would not repeat. FIX-008 does not
  change this.
- **I3 (info). An owner account whose id is not the default portfolio id** (signup cannot create
  one) gets operator notices under its own id, and does not see legacy records that carry no user
  id.
- **I4 (info). `owner_ids()` creates an empty `users.db` where none exists** (a local run with
  AUTH off), as `count_users()` does at signup. An empty table has no owner, so the default user is
  used.
- **I5 (info). Rollout order.** SA-011 is now deploying first (the peer's push), which the card
  asks for. If the backlog's first reads leave issues untriaged when FIX-008 deploys, the owner
  gets one warning a morning naming counts and the top three issues, not one notice per issue,
  until they are triaged.

## Owner decisions

Both recorded 13 Oct about 12:35 IST ("yup i agree", after the recommendation in this conversation):

1. **I1: leave the old copies** (above). No production data change; not a review finding to
   reopen.
2. **The `milestones.yaml` allow rules stay off.** Adding this entry worked without them. The
   only dated entry left is `ipo_verdicts_visible_gate` (deadline 2026-12-31), and a deletion
   silences an alert, so the owner approves each one: when one is due, Claude shows the entry,
   the evidence and the exact edit. The owner may instead add `"Edit(config/milestones.yaml)"`
   to `.claude/settings.local.json`; Claude does not grant itself that permission.

## Production check (after an owner-authorized deploy, read-only)

1. The next 06:30 run's notices, if any fire, reach the owner once by push and email.
2. On the test member's device: no watchdog, job or drift notice after the deploy. The member's
   Alerts tab lists no operator notice dated after the deploy (older copies: I1).
3. A new warning in the backlog produces one "Every new, regressed or spiking error is triaged"
   notice the next morning, to the owner only; after triage, one "resolved", then silence.

Rollback is a revert. Removing the `milestones.yaml` entry alone silences the backlog's notices.
This receipt does not authorize deploying, pushing, changing production variables or sending
notifications.

## Next

A fresh-session review in a new conversation ("continue"), by [REVIEW.md](../REVIEW.md). Then
PR-001.
