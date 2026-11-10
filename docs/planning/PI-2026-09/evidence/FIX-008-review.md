# FIX-008 review receipt — operator notices reach only the owner

## Fresh-session review: ACCEPTED (2026-10-13)

**Context:** a fresh-session review in a new conversation opened with "continue" (13 Oct, about
12:37–13:10 IST). It is not the implementing conversation. All 39 peer sessions were idle at
the start. Nothing was committed, pushed, deployed or configured, no production state was read
and no notification was sent.

**Story:** [FIX-008](../stories/FIX-008.md). **Reviewed input:**
[FIX-008-manifest.json](FIX-008-manifest.json) `a7a7b58ec545b22d31ece03f8cb375dce51b8ae694c4feb5759aa0ab9709a682`
(24 files) and diff `48b3521d7bebda03faf39bb02df1bd3ab7c4d7c42b5f5af5dabae9aaf5da2658` (74,505
bytes, 23 paths). The baseline is `33ae170` (= HEAD; SA-011 and FIX-007 committed). The review
made one documentation edit to the reviewed files, listed under "Review edits".

**In one example.** The owner (the default portfolio id, two devices) and an invited member
(one phone) both have push on. A member-named `portfolio.json` is found corrupt at 02:10, and
the 06:30 watchdog runs the next three mornings.

- **The quarantine notice** is queued in the outbox for the owner only: one push to each owner
  device and one email to the owner's mailbox. It names the affected user's id. The member's
  phone, mailbox and outbox rows: nothing.
- **The archived ERROR line** becomes a backlog issue. At 06:30 the scheduler's own job sends
  one "Every new, regressed or spiking error is triaged" warning, to the owner alone. A re-run
  that morning sends nothing. The next morning sends one more.
- **The owner triages** over HTTP; the member gets 403 on both the read and the triage. The next
  morning brings one "Now satisfied — closing." with no next step, then silence.
- **The member's Alerts tab** (`limit=20`) is empty; the owner's lists the quarantine and the
  watchdog notices. No backlog notice carries the quarantined user's id.

### Review input verified

- **At the start:** the manifest's LF bytes hash to `a7a7b58e…`, and `kt_manifest.py verify`
  gives 0 mismatches over 24 files.
- **Own digest** (`analysis_data/fix008/review/rv_digest.py`): `33ae170` is HEAD; the diff over
  the manifest's 23 non-PDF paths, rebuilt from `33ae170` (the new test file against
  `/dev/null`), is `48b3521d…`, 74,505 bytes, matching the receipt.
- **Other worktree changes:** only `docs/README.md` (the owner's probe line), STATE, HANDOFF, the
  implementation receipt and the manifest. The receipt changed at 12:35 IST, after the
  manifest, to record the owner's two decisions; it is outside the manifest.
- **At the end:** `verify` mismatches exactly `docs/TEAM_TESTING_GUIDE.md`, this review's edit.
  Every code, test and other documentation file still has its reviewed bytes.

### Contract checked

The card's five acceptance criteria and its four hard-review items:

- **Every caller of the delivery layer**, not just the table. A grep of `core/`, `services/`,
  `scripts/` and `src/` for `emit_alerts*`, `emit_owner_alerts`, `alert_audience`,
  `owner_audience`, `deliver(`, `send_email(`, `send_push(` and every `user_ids()` /
  `active_user_ids()` fan-out finds:
  - the 8 operator sites on `emit_owner_alerts` and the 3 market sites on
    `emit_alerts_broadcast`, as the guard test lists them;
  - `emit_alerts` and `deliver` only with the iterated account's own id (`brief.py`,
    `pipeline.py`, `weekly.py`);
  - `send_email` without `to` only for the owner's own reports (watchdog heartbeat, backup,
    monthly report, learning evidence), which go to `DELIVERY_EMAIL_TO`;
  - no other loop over push subscribers. `alert_audience()` is the only one.
- **Readers of the sent-log:** `load_recent_alerts` (now per account, the Inbox route passes the
  caller, `delivery_api.py:101`), the auditor's `_load_alert_rows` (filters by `user_id` and
  `advice_ref`, `core/audit/outcomes.py:225-228`) and a UI fixture script. The Inbox is the only
  member-facing reader.
- **The owner audience.** `owner_ids()` (`user_store.py:184`) selects `role='owner'`; signup gives
  that role only to the first account, under `PORTFOLIO_DEFAULT_USER_ID`
  (`auth_api.py:69-74`, unchanged since the auth routes were added on 26 Jul), and no route
  promotes a member. The owner's push subscriptions are stored under the session's id
  (`delivery_api.py:142`), which is that same id, so `owner_audience()` reaches the owner's
  devices. Its email goes to the account's address (`resolve_recipient`), as before.
- **The email path for the default user**, with and without an account row: the account's
  address, else `DELIVERY_EMAIL_TO`. Unchanged; the trace and the implementer's no-account test
  each see exactly one email per notice (criterion 2).
- **Delivery failure and watchdog state.** `run_watchdog` keeps its state only when the notify
  call raises (`runner.py:181-187`). `emit_owner_alerts` never raises, as the broadcast never
  did, so an undelivered notice still advances the state (the implementer's I2). The engine and
  the runner are unchanged apart from `_broadcast`'s target.
- **The registered entry's ladder** (`engine.py`, unchanged): an invariant with no window,
  deadline or schedule. Pending → one "Due now." warning a day; unknown → one warning a day;
  satisfied after anything else → one "resolved" with no next step, then silence; satisfied on
  the very first run → silence. It can never lapse to a weekly critical. The real registry loads
  with 11 entries, and the trace drove the real ladder through all of these but "unknown".
- **No test reaches a real transport.** Both the implementer's tests and this trace replace only
  pywebpush's `webpush` and `smtplib.SMTP`, under SA-005's hermetic network guard. The
  implementer's outbox test stubs `enqueue_message`; this trace runs the real outbox and drainer.

### Independent adversarial examples

The reviewer's own trace is `analysis_data/fix008/review/test_rv_trace.py` (5 tests, its own
`conftest.py` loading the hermetic guard). Production shape: `AUTH_REQUIRED` on, **Atlas on
with a real `atlas.db`** (accounts mirrored as signup does), the real outbox and `drain_once`,
the real `SQLiteLogHandler` archiving into a real `telemetry.db`, the real registry, the
scheduler's own `_watchdog_job`, and the real app over `TestClient`. Expected results come from
the card, not from the implementation. It calls only public entry points, so the same file runs
on the base tree.

1. **Quarantine → archive → backlog → watchdog → outbox → transports → Inbox and triage**, in
   production time order (the example above). Also: every outbox row belongs to the owner; no
   address but the owner's receives email; the Sunday heartbeat (day 4 is Sunday 18 Oct) is the
   only later email, to the owner, with no push; anonymous Inbox → 401.
2. **The deploy day.** Earlier that day the old broadcast recorded a drift notice under both
   ids (base `emit_alerts_broadcast` was `emit_alerts` once per audience id, and that writer is
   unchanged). After the deploy the same drift fires twice: no second push or email to the
   owner, nothing to the member. The switch-over does not double-notify.
3. **A member's records buried in the owner's traffic.** 3 member records under 2,500 of the
   owner's and a legacy blank-id row: the member's `?limit=20` returns exactly its 3, newest
   first; the owner's returns its 20 newest; `?limit=500` returns 500.
4. **`AUTH_REQUIRED` off, anonymous:** the owner passthrough reads the owner's records only.
5. **A characterization, not an acceptance check** (finding L2): the owner alone watches BBB, the
   member watches nothing, the shelf is empty. An index reconstitution dropping BBB reaches the
   member's phone.

**Corrections to the reviewer's own harness, made during the review:**

- The first run faked only the watchdog's clock. The outbox's dedupe key carries its own date,
  so the day-2 notice, with the same body, collided with day 1's row and was not queued (recorded
  `delivered: false`; by the code, the watchdog still advanced its state: I1 below). The final
  harness puts `outbox._now` on the same clock. Real days differ, so this is not a production
  path.
- The first run assumed no Sunday in range; day 4 is a Sunday, and the heartbeat email arrived
  to the owner. The final harness expects it.

### Tests

| Code | The implementer's 22 tests | The reviewer's trace (1–4) |
|---|---|---|
| Reviewed | 22 passed (209 with the five changed files) | 4 passed |
| True base: a `git archive` of `33ae170` with only the new test files added | **caught:** 19 failed, 3 passed (the 3 market callers) | **caught:** 3 failed (1, 3, 4); 2 passes on both, as a transition check should |
| The implementer's in-memory base (`FIX008_SWAP=base`) | caught: 18 failed (their receipt; the registry and guard tests read disk) | **caught:** 3 failed |
| M1 owner = market audience | caught: 16 | **caught:** 1 |
| M2 Inbox filter ignored | caught: 3 | **caught:** 3 |
| M3 drift left on the broadcast | caught: 5 | survives (the trace has no first-time drift) |
| M7 `owner_ids()` = every account | caught: 14 | **caught:** 1 |
| M8 watchdog left on the broadcast | caught: 4 | **caught:** 1 |
| M9 the route stops passing the caller | caught: 3 | **caught:** 3 |
| M11 the owner also emitted as a blank id | caught: 15 | **caught:** 1 |
| **X1** (reviewer's): the per-account read filters only the log's last `limit` lines | **survives:** 58 passed (with `test_delivery_alerts.py` and `test_delivery_api.py`) | **caught:** test 3 |
| **X6** (reviewer's): the per-account read ignores `limit` | **survives:** 58 passed | **caught:** test 3 |

The base failures are behavioural: the member received the operator push and email, the
planted id reached the member, the Inbox listed the other account's records, the outbox queued
the member. X1 and X6 are `analysis_data/fix008/review/rv_mut_plugin.py` (`RV_MUT`).

### Findings

| ID | Severity | Location | Evidence | Disposition |
|---|---|---|---|---|
| L1 | Low (docs; behaviour correct) | `docs/TEAM_TESTING_GUIDE.md:263` (10-G) | 10-G expected the member's Alerts tab to show no watchdog, drift or job notice at all. By the owner's I1 decision, the copies the old broadcast wrote under the test member's id stay in its tab until newer alerts push them out of its 20 newest, so a tester could record a correct result as a failure. The implementation receipt's production check already says "dated after the deploy". | **Fixed** in 10-G by this review. |
| L2 | Low (privacy; pre-existing; outside FIX-008's acceptance) | `core/delivery/index_watch.py:30-46`, `:104` | The index-reconstitution notice is selected from every account's holdings and watchlists plus the shared shelf, then sent to every account. A member is told about a symbol that only the owner holds or watches. Fixture: trace test 5 (reproduced). The card keeps the market callers' audience, so FIX-008 meets its criteria. Impact is small: reconstitutions are rare and the notice names a public index change, not the account. | **Routed** as [FIX-009](../stories/FIX-009.md) (P2, 1 point, ordered next after FIX-008) on 13 Oct about 14:15 IST; the owner delegated the call. |
| L3 | Low (tests; code correct) | `core/delivery/alerts.py:226-255`; `tests/unit/test_operator_notices_owner_only_fix008.py` | No test pins how the per-account read applies `limit` (the Alerts tab asks for 20). X1 and X6 pass all 58 related tests. Under X1, a member whose records are older than the shared log's last 20 lines sees an empty tab. The trace's test 3 catches both. | **Routed** to [SA-031](../stories/SA-031.md), with the fixture. |
| I1 | Info (pre-existing; confirmed) | `core/ops/watchdog/runner.py:181-187` | The implementer's I2: an undelivered notice advances the watchdog state. Seen in the trace's first, mis-clocked run: the outbox ignored a duplicate row and the sent-log recorded `delivered: false`, while `_broadcast` returned normally, so by the code above the state was saved. A pending entry warns again the next day; a one-time "resolved" would not repeat. Unchanged by FIX-008. | No action in this story. |
| I2 | Info (docs; pre-existing) | `CODEBASE.md:445-452` | The `/delivery/*` route table's Auth column says "optional key" or "none"; the routes take the caller's session or the owner. | **Routed** to SA-031's final consistency pass. |
| I3 | Info (inference) | — | With the backlog entry registered, delivery problems feed back as backlog issues: an "[alerts] … NOT delivered" warning becomes an issue, and the next morning's notice to the owner says so. At most one warning a day, so it cannot run away; triage closes it. | No action. |

**The implementer's own items:**

- **I1 (old copies in the member's Inbox):** the owner decided to leave them (13 Oct about
  12:35 IST). L1 brings guide 10-G in line with that.
- **I2:** confirmed (I1 above).
- **I3 (an owner account with another id):** agreed; signup cannot create one.
- **I4 (`owner_ids()` creates an empty `users.db`):** agreed; production has one.
- **I5 (rollout order):** agreed; see "Production check".

No critical, high or medium finding.

### Decisions

Upheld:

- **The Inbox filter is in scope** (the implementer's delegated call): without it the member
  still reads every operator notice in the Inbox, and criterion "the member gets nothing" fails
  on that channel.
- **A record with no user id belongs to the default user**, so legacy operator records stay the
  owner's and no member sees them.
- **A failed owner lookup narrows to the default user** and never widens.

### Commands and results

Environment: Windows 11, the project's `.stockai` virtual environment (Python 3.13.11, FastAPI
0.136.1, Starlette 1.0.0), SA-005's hermetic guard on every run.

| Check | Command | Result |
|---|---|---|
| Input | `python scripts/docs/kt_manifest.py verify docs/planning/PI-2026-09/evidence/FIX-008-manifest.json`; `python analysis_data/fix008/review/rv_digest.py` | 0 mismatches at the start; `a7a7b58e…`; diff `48b3521d…`, 74,505 bytes |
| Story and changed tests | `python -m pytest tests/unit/test_operator_notices_owner_only_fix008.py tests/unit/ops/test_error_backlog_sa011.py tests/unit/test_alerts_wave_f.py tests/unit/audit/test_audit_thresholds.py tests/unit/intelligence/rl/test_review_outcomes_feedback_sa004.py tests/unit/test_daily_review_outcomes_sa004.py -q -p no:cacheprovider` | 209 passed |
| True base | `git archive 33ae170` (code, config, tests, data seeds) into `analysis_data/fix008/review/base_tree/`, the new test file and the trace copied in, run there | 19 failed, 3 passed; trace 3 failed, 1 passed |
| The reviewer's trace | `python -m pytest analysis_data/fix008/review/test_rv_trace.py -q -p no:cacheprovider` | 5 passed |
| Trace vs the implementer's swaps | `FIX008_SWAP=<mode> PYTHONPATH=analysis_data/fix008 python -m pytest -p swap_plugin analysis_data/fix008/review/test_rv_trace.py` | `review/trace_vs_swaps.txt` (table above; 5 tests including the characterization) |
| Reviewer's mutants | `RV_MUT=X1\|X6 PYTHONPATH=analysis_data/fix008/review python -m pytest -p rv_mut_plugin …` | X1, X6 survive the 58 tests; caught by the trace |
| Full suite | `python -u -m pytest -q -rfEs -p no:cacheprovider tests -o console_output_style=count` | **4493 passed, 12 skipped, 0 failed** (10 min 5 s, about 12:54–13:04 IST), the same 4,505 tests as the implementer's run |
| Runtime data | `python analysis_data/fix008/data_fingerprint.py` (path, size and mtime under `data/`, `logs/`, `outputs/`, `config/`; no contents read), before and after the full suite | 801 files, `e715a34c…` before and after, equal to the implementer's value |
| Broad-except guard | `python scripts/ci/check_broad_except.py` | OK (154 grandfathered) |
| KT and PDF | `check_kt_docs.py` (with `PYTHONPATH=analysis_data/kt_docs_deps`) | errors `[]`; PDF source `5835a967…` = the KT's bytes; 41 pages; re-run after the guide edit: errors `[]` |

**Not exercised:**

- production, which was not read;
- a real push service or mail server (recorded at pywebpush and `smtplib`);
- two uvicorn workers or the outbox drainer thread (the trace calls `drain_once` directly);
- the watchdog's "unknown" rung for this entry (a check that raises), which the engine handles
  the same way for every entry.

### Review edits (documentation only)

- **Guide 10-G:** pre-deploy copies on the test member's account (L1); blob `f47ffb71`.
- **The SA-031 card:** L3 and I2, with the fixture.
- This receipt, STATE and HANDOFF.
- **Not edited:** code, tests, the KT and its PDF, ARCHITECTURE, PRODUCT_MAP, CODEBASE and the
  implementation receipt. The KT's section 12 row stays `Open` until the commit, as FIX-007's
  did.

### Acceptance and what remains

| Criterion | Result |
|---|---|
| 1. One owner audience (role `owner`, else the default user) for the 7 operator callers; the 3 market callers unchanged | Met: code, grep, the implementer's 9 + 3 caller tests, trace 1, M1/M7 caught |
| 2. One email per notice | Met: each operator notice reaches the owner's mailbox once (implementer's tests, trace 1, trace 2 on the deploy day) |
| 3. Tests with fake transports: owner only / both; a planted id never reaches the member; a guard classifying every caller | Met: 22 tests at the lowest seams; the guard (AST, aliases) and its 4 plants; L3 adds the limit case |
| 4. Register `error_backlog` with the triage steps; SA-011's pin changes | Met: `config/milestones.yaml:152`; trace 1 through the scheduler's job; SA-011's test now asserts one entry and an owner-only emit |
| 5. Documentation as current design; a human test case | Met: KT sections 3, 10 and 12 with the PDF matching its source; ARCHITECTURE; PRODUCT_MAP; CODEBASE; guide 10-G (corrected here, L1) and 12-K |

**Production check, after an owner-authorized deploy (read-only).** Order: SA-011's deploy (pushed
09:07 IST 13 Oct) is confirmed and its first backlog read triaged before FIX-008 deploys.

1. The next 06:30 notices, if any fire, reach the owner's devices and mailbox once.
2. The test member's phone gets no watchdog, job, drift or backlog notice after the deploy. Its
   Alerts tab lists none dated after the deploy (older copies stay, by the owner's decision).
3. A new backlog warning brings one "Every new, regressed or spiking error is triaged" notice the
   next morning, to the owner only; after triage, one "resolved", then silence.

Rollback is a revert; removing the `milestones.yaml` entry alone silences the backlog notices.
This receipt authorizes no deploy, push, configuration change or notification.

**Verdict: ACCEPTED** for the reviewed input `a7a7b58e` with this review's guide edit. FIX-008 is
`done`; production verification is `pending_deployment` until an owner-authorized deploy. Open items:
L2 (routed as FIX-009), L3 and I2 (SA-031). Next ready story: FIX-009, then PR-001, each in a new
conversation.
