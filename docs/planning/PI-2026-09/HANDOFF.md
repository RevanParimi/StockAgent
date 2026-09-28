# Current handoff - 2026-09-28 (updated about 20:45 IST)

## START HERE — resume checklist, in order

**0. Before any story work, check STATE `pending_production_checks`.** It holds the SA-039 `observe`
verification. **P1 passed** (checked Mon 28 Sep 20:19 IST). P2 is due Tue 29 Sep 17:00 and P3 Thu
1 Oct 09:30. Run every check that is due and unrecorded (read-only; the steps are in the carry-over
box on [SA-001](stories/SA-001.md), and [SA-003](stories/SA-003.md) carries a pointer to it). Record
each in the [activation record](evidence/SA-039-activation-2026-09-26.md) and in STATE.
[SA-038](stories/SA-038.md) is the backstop.

- **P1, in one example.** Monday's 16:30 review graded Friday's session for all 20 tickers in
  `observe` mode. For SUZLON the adapter proposed v57 and it was not written: the stored version
  stays v56, the same as the 26 Sep baseline. The same holds for all 19 tickers with weights, and
  no `Weights → v` line was logged. WELCORP has no weights, as before SA-039.
- **The P1 rule had the wrong date.** It expected observations dated 28 Sep, but a review grades
  the previous session, so they say 25 Sep; they were recorded today (16:31–16:54 IST). P2 should
  see `review_date` 2026-09-28.
- **For P2:** `analysis_data/sa039/p1_probe.py 2026-09-29 <deploy id>` (ignored; read-only; prints
  counts and versions only). Take the deploy id from `railway deployment list`.

- **When P3 passes (Thu 1 Oct), make the SA-003 enforce decision.** On 2026-09-27 the owner
  delegated it to Claude: decide by the written rules, log the decision, and tell the owner. SA-039's
  observation window ends with P3. The rules are in STATE, under P3's `then_decision`:
  - **Wait** until all of these hold:
    - SA-003 is deployed in record mode. **Met:** deploy `0106fc89`, 27 Sep 09:27 IST (step 1);
    - P1–P3 have passed;
    - the live envelopes carry `data_gate` (otherwise wait for the 1 Nov forecast);
    - `decision_gate.jsonl` holds at least 5 scheduled review days of rows;
    - no other policy flag changed in this window.
  - **No-go**, and route a fix, if either of these holds:
    - more than 20% of analyses would abstain, not counting forecast rows issued before the gate;
    - a spot check of 5 abstain rows finds one whose data was actually fine.
  - **Otherwise go:**
    - set `DECISION_GATE_MODE=enforce` in a safe window (00:10–06:20 IST). If Claude cannot set
      the Railway variable, give the owner the exact command;
    - verify read-only after the next scheduled review;
    - roll back to `record` if a verified run was withheld, or if skips far exceed the prediction.
  - **Also report two inputs to the owner.** The SA-003 review added them; they do not change the
    rules above:
    - **F1:** how many month-start envelopes carry `abstain`. Under `enforce`, each such ticker
      would have no envelope for that month, because only a restart retries it;
    - **F2:** how many `actual_close` gate rows name `source nse` with the previous session's bar
      (the close-verifier case);
    - count analyses by distinct `run_id` against the data-health rows, not by raw gate-log rows.
      A re-run review appends its rows again.
  - Log the decision in `evidence/SA-003-enforce-decision-<date>.md`, in STATE history and in
    SA-003's `production_verification`. The [SA-003 receipt](evidence/SA-003-implementation.md)
    has the steps, under "Rollout", and the [review](evidence/SA-003-review.md) has F1 and F2.

**1. Next PI phase: SA-007 implementation** ([SA-007](stories/SA-007.md), make backups
independently recoverable; P1, sprint 1, no dependencies), in a new conversation. Opener:
`Continue`. STATE: `active_task: null`, `next_task: SA-007`, `next_phase: implementation`.
**Run step 0 first** if P2 is due by then (Tue 29 Sep 17:00 IST).

- SA-007 is the first `todo` story in STATE order whose dependencies are all `done`. Its card:
  recovery must not depend on the application volume or the email channel. That means a minimal
  object-storage backup adapter with integrity metadata, and a restore into an isolated
  directory. Provisioning paid resources is not allowed.
- Routed input from SA-006: the backup email is still a direct send, with no outbox retry or dead
  letter. Its failure reason is now logged (STATE `SA-006.routed_notes.SA-007`).

**SA-006 was ACCEPTED by its fresh re-review on 2026-09-28** (this conversation, about
19:40–20:45 IST, after P1). Receipt: [SA-006-review.md](evidence/SA-006-review.md), section
"Re-review". Nothing was committed, pushed, deployed or sent.

- **F1 is fixed, in one example.** A phone's push service stores the morning brief's push, then
  drops the connection. The brief now shows once; the row dead-letters with the reason. A
  refused connection is still retried and shows once.
  - The rule matches urllib3's own "safe to retry" test (`Retry._is_connection_error`).
  - Real-stack tests prove both cases.
- **F2 is fixed:** the owner report carries no user id.
- **D10, D11 and D12 are upheld:**
  - D10: a TLS error is an unknown outcome;
  - D11: one phone's unknown outcome stops the row;
  - D12: no `sw.js` tag for now. It is revisited if guide case 10-C shows a double.
- **Checks:**
  - the input `b8273b2c…` verified, and the diffs `e01c4913…` and `713e1675…` rebuilt;
  - focused tests 124 passed;
  - full suite **3837 passed, 12 skipped, 0 failed** (7 min 12 s), `data/` unchanged;
  - the reviewer's 8 of 8 mutations caught, and 7 of 7 probes as the contract requires;
  - `check_kt_docs` errors `[]`.
  - No findings.
- **Review edits (docs only):** the SA-006 status wording in the KT (§1, §10, §11, §12), ARCHITECTURE
  and guide 10-B/C/E/F; the PDF is rebuilt (26 pages, source `38ddf518…`). So `verify
  SA-006-manifest.json` now mismatches exactly those 4 files.
- **Production verification: `pending_deployment`.**
  - It needs the owner's commit and push.
  - After the deploy, read `GET /delivery/outbox` (machine key) or run the owner probe
    `analysis_data/sa006/prod_probe_outbox.py`.
  - Then human cases 10-B, 10-C, 10-E and 10-F.
  - A real test email or push needs explicit messaging authorization.
- **Committed as `15dcda1`** at the owner's word ("commit and push with revan.datta132@gmail.com",
  about 22:18 IST Mon 28 Sep). The author is `Revan <revan.datta132@gmail.com>`, the same as
  earlier commits.
  - `verify SA-006-manifest.json --rev 15dcda1` mismatches only the 4 review-edited docs, so every
    reviewed code and test byte is committed as reviewed.
  - A follow-up commit bumps the KT to `15dcda1` (§1, §10, §11 and §12 now say "committed"; PDF
    26 pages, `check_kt_docs` errors `[]`) and records the commit in STATE.

**The push hold is lifted** (owner, about 22:18 IST Mon 28 Sep: "commit and push"). The push
carries 5 commits: `7901f35`, `48143ed` (SA-005), `9e65c7a`, `15dcda1` (SA-006) and the KT bump.
It is timed so the deploy lands before the 22:55–00:05 blocked window (23:00 atlas jobs, 23:30
backup). **After the push:**

- check the deploy with `railway deployment list`;
- read the Actions page and record CI's three jobs against SA-005 (human case 12-E);
- do SA-006's first read-only production read (`GET /delivery/outbox` or the owner probe).

The push result is recorded below, and in the next commit.

**SA-006 rework 1 was done on 2026-09-28** (a new conversation, about 15:38–16:25 IST, baseline
`9e65c7a`). Receipt: [SA-006-implementation.md](evidence/SA-006-implementation.md), section
"Rework 1". No SA-039 check was due. Nothing was committed, pushed, deployed or sent.

- **F1 fixed, in one example.** A push service stores a brief's push, then the connection
  drops before its 201.
  - Before: the drainer retried it, so the phone showed it twice.
  - Now: it is an unknown outcome and dead-letters after one attempt, so the phone shows it once
    and the owner report says why.
  - A push is retried only when its connection was never made: refused, a DNS failure or a
    connect timeout. The check uses exception types, found along `args`, `reason` and
    `__cause__`, never message text.
- **F2 fixed.** The dead letter for an account with no address now reads "permanent: no email on
  file for this account", with no user id.
- **Two new decisions for the re-reviewer:**
  - **D10:** TLS errors count as unknown outcomes, because their type cannot prove that nothing
    was sent.
  - **D11:** one phone's unknown outcome stops the row for all of that account's phones. A phone
    whose service answered 5xx then loses that notification, visibly, as a dead letter.
- **D12, decided by Claude on the owner's delegation:** no notification `tag` in the service
  worker for now.
  - Our own retries can no longer duplicate a push.
  - A tag only merges a copy that is still on screen, so it makes no retry safe.
  - It would change code on every phone, and no automated test covers that code.
  - Revisit if a phone ever shows one notification twice (guide case 10-C).
- **Tests:**
  - 12 new tests. One is the review's R1, kept as a permanent test: the real pywebpush →
    requests → urllib3 stack against a loopback push service. The service stores 1 copy and the
    row dead-letters after 1 attempt; the reviewed code fails this test. Another uses a real
    refused connection, which is retried and ends with 1 copy stored.
  - A 9-case table of exception types, and I5 extended with an account that has no address.
  - Focused: 124 passed. Full suite: **3837 passed, 12 skipped, 0 failed** (11 min 02 s).
    `data/`, `logs/` and `outputs/` were unchanged.
  - 5 of 5 rework mutations were caught, the broad-except guard is OK, and `check_kt_docs`
    errors are `[]` (PDF 26 pages).
- **Docs:** KT §10 (the transient, at-most-once and visibility bullets); the status lines in the
  KT, ARCHITECTURE and the guide, which now say "re-review pending"; and guide case 10-C.

**SA-006's fresh review requested changes on 2026-09-28** (a new conversation, about
15:08–15:35 IST). Receipt: [SA-006-review.md](evidence/SA-006-review.md). The review input
`516d2aec…` was verified (18 files, 0 mismatches) and the diff `79ec6b54…` rebuilt
independently. No SA-039 check was due. The review edited no code or docs, and nothing was
committed, pushed, deployed or sent.

- **F1 (medium; an acceptance criterion is not met), in one example.** A push service receives
  a brief's push, then the connection drops before it answers. The drainer calls that
  transient and sends it again a minute later, so the phone shows the brief twice. This was
  reproduced with the real pywebpush and requests stack against a loopback push service, which
  stored 2 copies. Today only a `ReadTimeout` counts as an unknown outcome.
  - **The fix:** retry a push only when the exception shows the connection was never made
    (`ConnectTimeout`, `NewConnectionError`, `NameResolutionError`). Treat anything else as an
    unknown outcome, which dead-letters.
- **F2 (low).** The dead letter for an account with no address reads "no email on file for
  user 'u_…'". So the owner report shows a user id, although its contract says it shows none.
  The fix is to drop the id.
- **Everything else holds.**
  - 112 focused tests passed.
  - Full suite: 3825 passed, 12 skipped, 0 failed (11 min 26 s), data/logs/outputs unchanged.
  - 10 of 10 reviewer mutations were caught, including the `590bc9f` owner fallback.
  - The broad-except guard is OK, and `check_kt_docs` errors are `[]`.

**SA-006 was implemented on 2026-09-28** (one conversation, about 13:15–15:05 IST, baseline
`9e65c7a`). Receipt: [SA-006-implementation.md](evidence/SA-006-implementation.md). No SA-039
check was due. Nothing was committed, pushed, deployed or sent.

- **What it does, in one example.** A beta account's brief meets a locked `users.db`: before, it
  went to the owner's `DELIVERY_EMAIL_TO`; now it waits a minute and goes to the account's own
  address, once. The owner's brief meets a rejected Gmail password: before, 3 tries and a raw
  error; now one try and a dead letter saying "check SMTP_USER and SMTP_PASSWORD".
- **The contract:** every transport returns a `SendResult`, meaning acceptance, never receipt.
  Transient failures retry on the backoff or the provider's `Retry-After` (capped at 6 h).
  Permanent ones dead-letter at once with a hint. Unknown outcomes (a drop inside the SMTP send,
  a push read timeout, a process killed mid-send) dead-letter and are never re-sent. Resend gets
  a per-row `Idempotency-Key`. Reasons and logs are redacted. `GET /delivery/outbox` (owner)
  shows counts, dead letters and retrying rows, with `delivered` shown as `accepted`. Dead
  letters are kept 180 days (payload cleared at 30). Pushes carry a 12 h TTL (pywebpush's default
  0 lets a push service drop them).
- **Production, read-only:** the live deploy `b3fb00dd` logged 3 outbox enqueues, 0 dead letters
  and 0 send failures from 27 Sep 16:05 to 28 Sep 12:01. The 23 Sep probe had 8 email rows
  accepted and 0 dead since the Pro redeploy. SMTP works; SA-006 does not change transport
  selection. A read-only outbox probe for the owner is `analysis_data/sa006/prod_probe_outbox.py`
  (not yet run in production).
- **Tests:** full suite 3825 passed, 12 skipped, 0 failed (SA-005's 3800 plus 25 new), with
  `data/`, `logs/` and `outputs/` unchanged; 22 new invariant tests at the network boundary
  (fake relay, Resend and push service count what they accepted); 16 of 16 mutations caught,
  including the `590bc9f` owner fallback; broad-except guard OK; `check_kt_docs` errors `[]`;
  PDF rebuilt (26 pages).
- **Found and routed to SA-031:** `scripts/docs/run_kt_checks.py` has not run since SA-005 (it
  does not copy the tracked seed `data/nse/key_registry.json`, exits 4 and then prints a stale
  24 Sep XML); a Windows rename flake in `core/ipo/signals.py`.
- **Nine decisions for the reviewer,** in the receipt (D1 at most once; D3 stored status stays
  `delivered`, reported as `accepted`; D5 dead-letter retention; D6 push TTL; D8 direct senders
  stay direct).
- **Open:** receipt is not observed (no webhooks); direct senders (monthly report, heartbeat,
  backup) have no retry; no dead-letter alert (SA-011); CI never ran.

- **Earlier plan note:** SA-006 was the first planned `todo` story in STATE's order whose
  dependencies are done. SA-005's acceptance also unblocked [SA-012](stories/SA-012.md).

**SA-005 was ACCEPTED on 2026-09-28 by a fresh-session review** (a new conversation, about
07:25–07:55 IST). Receipt: [SA-005-review.md](evidence/SA-005-review.md). SA-005 is `done`. Its
`production_verification` stays `pending_deployment`: CI has never run on GitHub. No SA-039 check
was due. The review committed, pushed and deployed nothing.

- **Input verified:** `ef0e3a31…` (51 files, 0 mismatches). The completeness check found no
  unlisted change, and the diff `7274a199…` was rebuilt with the reviewer's own script. The three
  action pins are the upstream tags' commits (`git ls-remote`).
- **Tests:**
  - owner's checkout (`.env` present): 3800 passed, 12 skipped, 0 failed. `data/`, `logs/` and
    `outputs/` were unchanged (800 files);
  - reviewer's fresh copy (`git archive 7901f35` plus the manifest, run from the long temp path):
    3799 passed, 13 skipped, 0 failed. `git status` was empty afterwards, and `logs/` and
    `outputs/` were never created;
  - reviewer's 6 mutations: all caught. They include the original F22 defect (the old MARUTI
    test fails without local data) and the F5 defect (the old outbox tests fail without
    `DELIVERY_EMAIL_TO`);
  - probes: yfinance's real call path is refused and fails the test (P1); the owner's real `.env`
    does not reach settings (P6);
  - no Python 3.12-only syntax in 730 files (a tokenizer scan, since `ast` feature_version misses
    PEP 701).
- **Findings.** None critical, high or medium.
  - **L1 (low), in one example.** A test that read
    `C:\Users\REVANP~1\…\data\nse\key_registry.json` (the 8.3 spelling of the checkout) got the
    file instead of a refusal. The same holds for `listdir`/`exists`, pyarrow reads, SQLite
    `file:` URIs and a numeric-IP connection on Windows' asyncio loop. The application reaches
    none of these today. The KT and `tests/TEST_DOCUMENTATION.md` now say so; the docstring and
    optional hardening go to [SA-031](stories/SA-031.md).
  - **L2 (low):** fixing one grandfathered broad `except` and adding a new silent one in the same
    function passes the guard. Routed to SA-031, and the KT states it.
  - I1 and I2 are info only.
- **Review edits (documentation only):** KT §13 (two passages) and the SA-005 status wording
  (§1, §10, §12, the §13 heading), the PDF rebuilt (source `f407a930…`), `tests/TEST_DOCUMENTATION.md` rule 4, and the SA-031 card. `verify
  SA-005-manifest.json` now mismatches exactly these four files. The code, test, CI and tooling
  bytes are as reviewed.
- **Committed at the owner's word** ("commit and push now", about 07:58 IST Mon 28 Sep).
  - **`48143ed`:** SA-005 and its review bookkeeping. `verify SA-005-manifest.json --rev 48143ed`
    mismatches only the four review-edited docs, so every reviewed code, test and CI byte is
    committed as reviewed.
  - **The next commit is the KT bump:** it declares `48143ed`, links the five new or changed
    files, changes the status lines to "committed as `48143ed`", records `implementation_commit`
    and rebuilds the PDF (source `abec1a58…`; `check_kt_docs` errors `[]`).
  - **The push was held for the window.** The word came at 07:58, inside the 07:25–09:05
    morning-job window (`ipo_refresh_am` 08:00, `preopen_shock_check` 08:45, `morning_brief`
    08:50, `macro_market_news` 09:00). A push then would have restarted the container about
    08:06, during the IPO refresh. (Superseded: the owner put the push on hold at 08:46 IST; see step 1.) It
    carries `7901f35`, `48143ed` and the KT bump, and it is CI's first run: afterwards, read
    the Actions page and record the three jobs against SA-005 (human case 12-E).

**Earlier: the SA-005 implementation (27–28 Sep).**

- **SA-005 was implemented** in one conversation (27 Sep about 16:25–17:30 IST and 28 Sep about
  06:45–07:45 IST, baseline `7901f35`). Receipt:
  [SA-005-implementation.md](evidence/SA-005-implementation.md). No SA-039 check was due. Nothing
  was committed, pushed or deployed.
  - **What it does, in one example.** Before, the owner's test run loaded `.env`, and yfinance's
    requests went out unseen by the old socket guard. The first run under the new boundary refused
    286 Yahoo requests, 178 OpenRouter attempts and 124 NSE session attempts. The old suite also
    changed 15 files in the local `data/`, including the MARUTI toggle (I3). Now every test runs in
    an empty working directory, with no `.env` and no network, and the final run left `data/`
    byte-identical.
  - **The boundary:** `tests/hermetic.py`, imported first by `tests/conftest.py`. A test that
    reaches the network or the checkout's `data/`, `logs/` or `outputs/` fails, naming the target
    and the application line, even when the application swallowed the error.
  - **CI:** `.github/workflows/ci.yml` (the whole tree on Linux / Python 3.11, the broad-except
    ratchet and `check_kt_docs`, the browser suite; `contents: read`, no secrets),
    `requirements-test.txt`, `scripts/ci/check_broad_except.py` (154 handlers grandfathered, not
    reviewed one by one).
  - **Nine decisions for the reviewer,** in the receipt. For example: D1 one working-directory
    sandbox instead of ~40 path redirects; D3 an obsolete TypeScript-client contract test removed;
    D4 a Windows-only rename retry in three production writers; D6 the guard is a whole-tree
    ratchet.
  - **Tests:** owner's checkout 3800 passed, 12 skipped, 0 failed; a fresh git checkout outside
    OneDrive 3799 passed, 13 skipped, 0 failed; the reverse-order run found one leak, now fixed;
    12 of 12 mutations caught; `check_kt_docs` 0 errors; PDF rebuilt.
  - **Open:** CI has never run (it needs a push, and every push redeploys); no pinned-date run
    (routed to SA-012); child processes are outside the boundary; cached store connections are
    shared between tests.
  - **Routed:** [SA-012](stories/SA-012.md), [SA-018](stories/SA-018.md),
    [SA-029](stories/SA-029.md), [SA-031](stories/SA-031.md).
  - **Local data restored.** The old suite's measurement run changed 15 files in `data/`; they
    were restored from the ignored `analysis_data/sa005/data_before` copy and are identical to it.
  - **Running tests here:** plain `python -m pytest tests`. `-p nonet` and
    `RL_LEARNING_MODE=adapt` are no longer needed in this checkout; a checkout without SA-005
    still needs them.

**Earlier: SA-004 accepted, committed and deployed (27 Sep).**

- **SA-004 was ACCEPTED on 2026-09-27 by a fresh-session review** (a new conversation, about
  15:23–15:50 IST). Receipt: [SA-004-review.md](evidence/SA-004-review.md). SA-004 is `done`. Its
  `production_verification` is `pending_observation`: it was deployed at 16:06 (see below). No SA-039 check was due. The review itself
  committed, pushed and deployed nothing; the commit and push followed at the owner's word (below).
  - **Input verified:** `a5e77a74…` (13 files, 0 mismatches), and the diff `648b7b68…`, rebuilt
    with the reviewer's own script.
    - Payload update 1 (`5d9030e0…`, diff `e16a8e3f…`) arrived during the review, from the
      concurrent planning session (the backlog bullet below).
    - The reviewer rebuilt it too. The code, tests and `CODEBASE.md` are byte-identical, and the
      four doc changes are planning content only. The acceptance covers both inputs.
  - **Traced:**
    - `completed` implies a stored feedback entry, because a failed write raises;
    - the ticker and date pass through unchanged, so `classify` cannot misread a real review;
    - `/scheduler/status` is the only reader of the record;
    - the HTTP task and the paper lane already counted only `completed`;
    - no watchdog check reads review outcomes.
  - **Hard review.** The five counts always add up to `required`. Within the counting, the zero-
    and partial-output alerts fire for every `produced < required`.
  - **F1 (low, reproduced), in one example.** Suppose Friday's record for 1 Oct had a wrong type
    in it, for example `"attempts": [1]`. On Mon 5 Oct, `summarize` raises before the portfolio
    pipeline:
    - the crash pages;
    - that day's advisor → autopilot → digest does not run.

    The only writer writes integers, so this needs a hand edit. Routed to
    [SA-036](stories/SA-036.md): wrap the block and fall back to no merge. I1 and I2 (info) are
    routed there too.
  - **I3 (info, predates SA-004).** `test_api_auth_lockdown.py:82` flips MARUTI's `enabled` flag
    in the checkout's real `data/managed_tickers.json` on every full run. It now holds MARUTI
    enabled, TCS and HDFCBANK disabled. This is local only. Routed to [SA-005](stories/SA-005.md).
  - **The implementer's five decisions:** the review agreed with each.
  - **Tests** (network guard on, `RL_LEARNING_MODE=adapt`):
    - focused: 376 passed;
    - the reviewer's 5 runtime mutations: all caught. The baseline scheduler, which is F09
      itself, fails 30 of 61;
    - pinned Mon 28 Sep and Fri 2 Oct: 71 passed each;
    - the reviewer's probes: 8 passed;
    - full `tests/unit`: 3502 passed, 5 skipped, 1 failed, the known `test_delivery_api` rename
      flake (5 of 5 alone); the guard blocked the pre-existing 194;
    - `check_kt_docs`: 0 errors.
  - **Review edits (documentation only):**
    - status wording in the KT (§1, §5, §9, §11, §12), ARCHITECTURE, 01-A and 01-F, `CODEBASE.md`
      and the SA-034 note;
    - the PDF rebuilt (source `bf3d73d3…`).

    `verify SA-004-manifest.json` now mismatches exactly the KT, the PDF, ARCHITECTURE,
    TEAM_TESTING_GUIDE and `CODEBASE.md`.
  - **Committed at the owner's word** ("commit and push", about 15:55 IST on Sun 27 Sep).
    - **`241c393`:** SA-004 and this review's bookkeeping. It also carries the planning session's
      SA-048…SA-051 cards and PI README, because the docs interleave the two.
    - `verify SA-004-manifest.json --rev 241c393` mismatches only the five status-edited docs, so
      every reviewed code, test and config byte is committed as reviewed.
    - **The next commit is the KT bump.** It declares `241c393`, links `review_outcomes.py`,
      changes the status lines to "committed as `241c393`", records `implementation_commit` in
      STATE and rebuilds the PDF.
  - **Pushed and deployed.** `a61fafe..90353f3` was pushed at 16:00:04 IST, and it also carried
    `0a5bf9e`. On a Sunday nothing runs between 09:05 and the daily `ipo_refresh_pm` at 17:45.
    - Deploy `b3fb00dd` reached SUCCESS at about 16:06 IST. The build was cached, about 6 minutes
      from the push.
    - The boot log (read-only, filtered) shows the scheduler started with 24 jobs registered and
      startup complete at 16:05:52, with 0 error or warning lines. No job fell in the switch.
    - SA-004's `production_verification` is now `pending_observation`.
    - This record is committed locally and rides the next push.
  - **Verify read-only across one scheduled session,** as the receipt's "Rollout" says. The first
    is Mon 28 Sep 16:30, alongside SA-039-P1 and the SA-003 cohort check. In
    `/scheduler/status` → `last_runs.daily_review`:
    - `by_ticker` holds every enabled ticker once;
    - the five counts add up to `required`;
    - `produced` equals the tickers whose `feedback_log.last_date` is 2026-09-25.

    Expect most outcomes to read `degraded` until the 1 Oct envelopes, because the rows were issued
    before the data gate. A skip (for example `no_envelope`) now sends a partial-output alert,
    which is intended. SA-004 is live before Fri 2 Oct, so Mon 5 Oct's record should read
    `runs: 2` for 1 Oct.
- **Backlog added at the owner's request (2026-09-27, after SA-004).** The owner reviewed the live
  portfolio screen: ₹9,99,611 equity, 81% cash, 2 holdings, a flat total return with nothing to
  compare it with. Four stories were added; the task order is unchanged, and they follow SA-047:
  - [SA-048](stories/SA-048.md) (S3, 3 points): costs and tax in paper P&L. ACMESOLAR's
    +₹37,551 would be about ₹29,660 in hand.
  - [SA-049](stories/SA-049.md) (S3, 5 points): put idle cash to work in normal markets. **Owner
    decision:** deploy idle cash in a normal market, and hold it only in a crisis ("if it's some
    war"). The regime targets and the per-day limit are proposals the owner confirms; the switch
    ships off. It depends on SA-050 and SA-051.
  - [SA-050](stories/SA-050.md) (S2, 2 points): one sizing rule for every autopilot buy. Today a
    SWITCH buy spends all its proceeds, with no 10% cap.
  - [SA-051](stories/SA-051.md) (S2, 3 points): the portfolio against the Nifty, with honest
    labels ("Invested" is really capital added) and a closed-trade record.

  Totals: 48 planned stories, 171 points (Sprints 1–6: 41 / 35 / 31 / 29 / 24 / 11). If the owner
  wants these sooner, SA-050 and SA-051 have no dependencies and could come next instead of
  SA-005; that resequencing needs the owner's word.
- **SA-004 was implemented on 2026-09-27** (a conversation, about 11:45–12:35 IST, on baseline
  `0a5bf9e`). Receipt: [SA-004-implementation.md](evidence/SA-004-implementation.md). No SA-039
  check was due. Nothing was committed, pushed or deployed.
  - **What it does, in one example.** The 8 Sep production record said `produced=20`,
    `expected=20`, `pipeline_ok=true`, while WELCORP had no envelope and 19 feedback rows existed.
    The same day now reads 19 of 20, `status: partial` and
    `missing: {WELCORP: "skipped: no_envelope"}`. The partial-output alert says
    "completed 19/20 — missing: skipped no_envelope: WELCORP".
  - **Outcomes.** The new `core/intelligence/rl/workflows/review_outcomes.py` gives each enabled
    ticker exactly one outcome:
    - `completed`;
    - `degraded`: completed on an input SA-003's record mode flags;
    - `data_gated`;
    - `skipped`: no envelope, no forecast row, or no close;
    - `failed`: an exception, a malformed result, or a timeout.

    Only completed and degraded (feedback written) are output.
  - **Also:**
    - required and attempted are counted separately;
    - disabled tickers are `excluded`, and a duplicate entry is reviewed once;
    - a second scheduled run of the same session merges: attempts add up, completion does not;
    - job `status` is `ok`, `partial`, `failed` or `empty`;
    - `pipeline_ok` is false for a malformed or raising pipeline, and when a review failed.
  - **Decisions flagged for the reviewer:** 5, in the receipt. For example, `degraded` counts as
    output, and the alerts use the merged cohort, not only this run.
  - **Tests** (network guard on, `RL_LEARNING_MODE=adapt`):
    - new files: 61 passed, including an integration test through the real `run_daily_review`
      that checks the persisted record against the stored feedback rows;
    - focused (36 existing files plus the 2 new): 376 passed;
    - 13 runtime mutations, 13 caught;
    - 7-day sweep: 91 passed each day, after one known `test_ops_alerts` flake on the Tuesday pin;
    - full `tests/unit`: 3503 passed, 5 skipped, 0 failed; the guard blocked the pre-existing 194;
    - `check_kt_docs`: 0 errors, and the PDF is rebuilt.
  - **Docs:** KT §1, §5, §9 (a new "Daily-review outcomes" paragraph), §11 and §12; the PDF;
    ARCHITECTURE; human cases 01-A and 01-B, plus a new 01-F (a rerun of the same session);
    `CODEBASE.md`.
  - **Routed:**
    - [SA-005](stories/SA-005.md): the new job-outcome test isolation, and leaks still open;
    - [SA-015](stories/SA-015.md): see the heads-up below;
    - [SA-034](stories/SA-034.md): no watchdog check reads this record yet;
    - [SA-036](stories/SA-036.md): one outcome contract; the pipeline's own `completed` hides
      per-holding advisor failures.
  - **Heads-up, pre-existing (F10, routed to SA-015).** The Mon–Fri 16:30 cron does not skip a
    weekday holiday, so each weekday holiday reviews a session twice.
    - Fri 2 Oct (NSE holiday) reviews Thu 1 Oct, and Mon 5 Oct reviews Thu 1 Oct again.
    - Each ticker runs a full `run_daily_review` for 1 Oct twice.
    - SA-004 would count that once; it does not stop the second run's learning writes.
  - **At commit:** the KT names `review_outcomes.py` in code formatting. The commit that lands
    SA-004 should link it and bump the KT header past `167f08b`.
- Before SA-005: run every test with the network guard `-p nonet` and `RL_LEARNING_MODE=adapt`
  (see step 4). With SA-005 in the checkout, plain `python -m pytest tests` is enough.
- **SA-003 is committed, pushed and deployed** at the owner's word ("commit and push", about
  09:00 IST on Sun 27 Sep).
  - **Commits.** SA-003 is `167f08b`; the KT bump is `a61fafe`, which declares `167f08b`, links
    `decision_gate.py` and rebuilds the PDF. `check_kt_docs` reports no errors.
    `verify SA-003-manifest.json --rev 167f08b` mismatches only the five status-edited docs. So
    every reviewed code, test and config byte is committed as reviewed.
  - **Push.** `f1c7eba..a61fafe` was pushed at 09:05:01 IST; it also carried `da90ee5`. On a
    Sunday, the time after 09:05 IST is job-free until `weekly_review` at 18:00.
  - **Deploy.** `0106fc89` reached SUCCESS at 09:27:57 IST. The boot log (read-only) shows startup
    complete, the scheduler started with 24 jobs registered, and 0 error or warning lines. No job
    fell in the switch.
  - **The build was a full rebuild, about 22 minutes.**
    - Docker Hub had moved the floating `python:3.11-slim` tag (base digest `da047cb8…` became
      `e41613d4…`). That invalidated every cached layer, so pip re-resolved the unpinned
      requirements.
    - Against the 23 Sep install, 15 packages changed (all minor or patch, for example uvicorn
      0.53→0.54 and opentelemetry 1.44→1.45), and 1 transitive package was added.
    - pandas, yfinance, nse (3.2.1), APScheduler (3.11.3), openai and torch are unchanged.
    - Routed to [SA-033](stories/SA-033.md): pin the base-image digest as well as the packages.
  - It ships `record` (`DECISION_GATE_MODE` is not set), so the deploy changes no outcome and is
    not a policy-flag change. It is live before the 1 Oct 09:00 forecast, so the October envelopes
    will carry `data_gate`.
  - **This record is committed locally** and rides the next push.
  - **Verify read-only across one scheduled cohort,** as the receipt's "Rollout" says. The first
    cohort is Mon 28 Sep, at the 16:30 review; check it alongside SA-039-P1.
    - `data/logs/decision_gate.jsonl` gains rows. Until 1 Oct, every review names
      `stage: forecast_row`, "issued before the data gate existed".
    - Reports carry `decision_gate`.
    - The weight and feedback behaviour is unchanged; SA-039-P1 checks this anyway.

**2. SA-003 was ACCEPTED on 2026-09-27 by a fresh-session review** (a new conversation, about
08:30–09:15 IST). Receipt: [SA-003-review.md](evidence/SA-003-review.md). SA-003 is `done`, and its
`production_verification` is now `pending_observation`, after the deploy in step 1. No SA-039
check was due. The review itself committed, pushed and deployed nothing; the commit and push
followed at the owner's word (step 1).

- **Input verified:**
  - the review input `dbe16714…`: 38 files, 0 mismatches;
  - the diff `a46a6846…`, rebuilt with the reviewer's own script;
  - the PDF blob.
- **Traced:**
  - all 8 non-test `analyse` callers;
  - the one `decide` caller;
  - both autopilot buy paths;
  - every weight and lesson writer;
  - the re-forecast paths.

  Each acts only through the gate, or is display-only and routed.
- **F1 (medium), in one example.** With `enforce` on, TATAMOTORS' 09:00 analysis on 1 Nov
  abstains.
  - No November envelope is built.
  - Nothing scheduled retries it before 1 Dec; only a restart's self-heal does.
  - Until then its reviews return `no_envelope`, and its ADDs stay blocked.

  The KT said "the next scheduled run retries", and the review corrected it. The retry and the log
  text are routed to [SA-036](stories/SA-036.md).
- **F2 (medium, predates SA-003), in one example.** Friday's review: yfinance has Friday's close,
  110. NSE has not listed Friday yet, and its newest row is Thursday's, 100.
  - The verifier returns 100, from Thursday.
  - Before SA-003, Friday was graded against Thursday's close.
  - SA-003 dates it Thursday, so it is not fresh: `record` logs it, and `enforce` skips the day.

  Routed to [SA-012](stories/SA-012.md).
- **The implementer's seven decisions:** the review agreed with each. EXIT and TRIM are never
  blocked (verified).
- **Tests** (network guard on):
  - full `tests/unit`: 3442 passed, 5 skipped, 0 failed; the guard blocked the pre-existing 194;
  - the 4 new files: 119 passed;
  - the reviewer's 5 runtime mutations: all caught (34, 5, 11, 13 and 32 failing);
  - the 7-day sweep: 119 passed each day;
  - the NSE-lag probe: 3 passed;
  - `check_kt_docs`: 0 errors.
- **Review edits (documentation only):**
  - status wording in the KT, ARCHITECTURE, 02-C, 03-C and `CODEBASE.md`;
  - the KT's F1 sentence corrected, and the F2 case named;
  - the PDF rebuilt (source `3735be42…`).

  `verify SA-003-manifest.json` now mismatches exactly those five files. No code, test or config
  changed.

**3. SA-003 was implemented on 2026-09-27** (a new conversation, about 03:40–05:15 IST, on baseline
`da90ee5`). Receipt: [SA-003-implementation.md](evidence/SA-003-implementation.md). No SA-039 check
was due. Nothing was committed, pushed or deployed.

- **What it does, in one example.** TATAMOTORS' price source answers 404, and the aggregator still
  says STRONG BUY on 9 of 9 dimensions.
  - The report now carries a typed `decision_gate`, `abstain`, naming the three unusable essential
    sections and the run id.
  - In `record` (the checked-in mode) nothing else changes, and a row in
    `data/logs/decision_gate.jsonl` says what enforcement would have withheld.
  - In `enforce` the report reads INSUFFICIENT DATA. No envelope is built on it, and the small
    holding's ADD becomes HOLD with no buy.
  - With a live price source, the same chain still buys.
- **Where it acts** (in `enforce`):
  - public analysis;
  - the month-start forecast and re-forecast;
  - the daily review: the graded row, a close from the session's own bar, and the re-run;
  - discovery's shelf;
  - the advisor's ADD and SWITCH destinations;
  - the autopilot's SWITCH buy leg.

  EXIT and TRIM are never blocked.
- **Tests** (network guard on, `RL_LEARNING_MODE=adapt`):
  - new files: 119 passed;
  - focused (32 affected existing files plus the new 4): 570 passed, 2 pre-existing failures that
    need the local Atlas DB (identical on baseline);
  - full `tests/unit`: 3442 passed, 5 skipped, 0 failed; the guard blocked the pre-existing 194;
  - 12 runtime mutations, 12 caught;
  - 7-day sweep (27 Sep – 3 Oct, across the month rollover and the 2 Oct holiday): 119 passed
    each day;
  - `check_kt_docs`: 0 errors.
- **Docs:** KT §1, §3, §4, §5, §6, §11 and §12; the PDF is rebuilt; ARCHITECTURE; human cases
  02-C, 02-F and 03-C; `CODEBASE.md`.
- **Routed:** [SA-004](stories/SA-004.md) (count `data_gated` separately),
  [SA-005](stories/SA-005.md) (the loader reload, the Atlas-dependent pipeline tests, the locking
  flake), [SA-008](stories/SA-008.md) (what the gate gives; TATAMOTORS maps to TMPV, and the gate
  cannot see that), and [SA-024](stories/SA-024.md) (the screens show a score next to INSUFFICIENT
  DATA).
- **At commit:** the KT names `src/backend/shared/pipeline/decision_gate.py` in code formatting.
  The commit that lands SA-003 should link it and bump the KT header past `8413b59`;
  `check_kt_docs.py` fails on a link to a file absent at the header's revision.

**4. SA-001 and SA-002 were committed, pushed and deployed on 2026-09-27.** They are committed as
`8413b59` (about 03:40 IST, at the owner's "commit and push", inside the 00:10–06:20 safe window).

- **Network guard.** Use `-p nonet` for every test run. Without it, a missed patch reaches real
  providers (see the incident in step 8). Check any date-relative fixture on 7 consecutive days;
  see the SA-005 note.
- **Commit and deploy:**
  - Commit checks passed. `verify SA-001-manifest.json --rev 8413b59` (17 files) and
    `verify SA-002-manifest.json --rev 8413b59` (19 files) each mismatch only in the five
    status-edited docs: the KT, the PDF, ARCHITECTURE, TEAM_TESTING_GUIDE and `CODEBASE.md`.
  - `npm run test:frontend`: 14 of 14 passed before the push.
  - The next commit bumps the KT header to `8413b59` (edition 2026-09-27), links
    `chat-markdown.js` and `fetch_result.py`, and changes the status lines to "committed".
  - **Pushed and deployed.** `16e7ea7..f1c7eba` was pushed at 03:41:25 IST; it also carried
    `994a7b6` and `103f2b8`. Deploy `0509de45` reached SUCCESS at about 03:42:48 IST.
    - The boot log (read-only) shows startup complete at 03:42:34 and the scheduler started with
      24 jobs registered. It has no error or warning lines.
    - No job fell in the switch; the next is the 06:30 watchdog.
    - Both stories' `production_verification` is now `pending_observation`.
    - This record is committed locally and rides the next push.
  - **Owner's post-deploy checks:**
    - SA-001: open the app twice, so that sw v8 takes over. Run human case 11-C in an isolated
      test account. Confirm that `marked@12.0.2` and `dompurify@3.4.16` load with status 200 and no
      SRI error.
    - SA-002: read-only, across one scheduled cohort, as in the Rollout section of its receipt.

**5. SA-002 was ACCEPTED on 2026-09-26 by a fresh-session re-review** (a new conversation, about
21:57–22:25 IST). Receipt: [SA-002-review.md](evidence/SA-002-review.md), under "Re-review". SA-002
is `done`, and `production_verification` is `pending_deployment`. No SA-039 check was due.

- **Input verified:**
  - the review input `c88edda5…`: 19 files, 0 mismatches;
  - the full diff `dc7e850b…` and the rework diff `56544c46…` both reproduced;
  - the first review's blobs exist in the object database.
- **M1 resolved, in one example.** Run as if on Monday 28 Sep, the whole contract file now passes.
  The reviewer reran the 7-day sweep: 7 of 7 days pass 155 of 155. With the old fixture put back,
  it fails on every day, through the guard.
- **M2 resolved, in one example.** The reviewer's own fixture uses yfinance's real shape: every row
  is NaN in the newest quarter (30 Jun), and the oldest column is sparse. The first review's code
  says `ok`, as of 30 Jun. The reworked code says `fallback`, as of 31 Mar, and names 30 Jun.
  - The same holds for three more shapes: the EBIT fallback row, a `pd.NA` nullable frame, and no
    quarter reported.
  - The prompt text is byte-identical to HEAD in 8 of 8 cases.
- **Decided:** an older blank quarter keeps `ok`, as the first review specified. The growth figure
  then shows `nan`, and SA-045's note covers it.
- **New findings (both low, both predate SA-002):**
  - **N1 → [SA-045](stories/SA-045.md).** The prompt's "Revenue YoY" compares the newest quarter
    with the one three quarters back. Revenue growing 10% a quarter shows +33.1%, where the true
    year-over-year change is +46.4%.
  - **T3 → [SA-005](stories/SA-005.md).** The full run failed 2 tests on Windows rename flakes.
    `test_delivery_api` fails 2 of 5 runs even alone, and `test_ops_alerts` loses its streak when a
    save fails.
- **Tests:**
  - focused: 289 passed, with 0 connections blocked;
  - full: 3321 passed, 2 failed (the flakes above), 5 skipped; the guard blocked the pre-existing
    194;
  - `check_kt_docs`: 0 errors.
- **Docs:** status wording in the KT (§1, §4, §11, §12), ARCHITECTURE, 02-F and `CODEBASE.md`. The
  PDF is rebuilt (source `333895c4…`). `verify SA-002-manifest.json` now mismatches exactly those
  five files.
- **Rollout (owner, after commit and push):** follow the "Rollout" section of the
  [implementation receipt](evidence/SA-002-implementation.md). It is additive: 7 nullable columns,
  and expect more `degraded` rows. Verify read-only across one scheduled cohort. Rollback is
  `observability.data_health_enabled: false`.
- Nothing was committed, pushed or deployed.

**6. The SA-002 rework was done on 2026-09-26** (a new conversation, about 20:50–21:30 IST).
The rework section is in the [implementation receipt](evidence/SA-002-implementation.md). No
SA-039 check was due.

- **M1, in one example.** Before, running on Monday 28 Sep made the fake "fresh" series end on
  Sunday. pandas 3 then built 299 dates for 300 values, so technicals read `empty` and 5 tests
  failed.
  - Now `_bars` rolls weekend dates back to the last session.
  - 14 guard tests pin a fixed Mon–Sun week and do not depend on the run day.
  - The whole contract file passes as if run on each of 7 days (Sun 27 Sep – Sat 3 Oct).
  - With the old fixture body put back, the original tests fail only on Sun, Mon and Tue, but the
    guard fails on every day.
- **M2, in one example.** Before, yfinance listing the quarter ended 27 Aug with NaN figures made
  fundamentals read `ok`, as of 27 Aug.
  - Now they read `fallback`, as of 28 May (the newest fully reported quarter), and the reason
    names the blank quarter. The row is `degraded`.
  - NaN, `None` and infinity all count as missing. The new key is `get_financials`
    `missing_values`.
  - The prompt text is byte-identical to HEAD in 13 of 13 cases.
  - Three runtime mutations are each caught: 9, 9 and 2 failing tests.
- **I1** had already been corrected in the receipt and in step 8 below before the rework began.
  The rework checked that no doc repeats the claim.
- **Tests:**
  - contract file: 155 passed (132 before + 23 new);
  - focused: 289 passed, with 0 connections blocked;
  - full: 3323 passed, 5 skipped, 0 failed; the guard blocked the pre-existing 194;
  - `check_kt_docs`: 0 errors; the PDF was rebuilt (source `0979ad97…`).
- **Docs:** status wording in the KT (§1, §4, §11, §12), ARCHITECTURE, TEAM_TESTING_GUIDE 02-F and
  `CODEBASE.md`. The KT §4 `fallback` meaning now includes a blank newest quarter, and 02-F gains
  that expectation. Routed: a note on [SA-045](stories/SA-045.md) (the Growth factor must read
  `missing_values`).
- Nothing was committed, pushed or deployed.

**7. The SA-002 fresh review requested changes on 2026-09-26** (a new conversation, about
13:20–14:00 IST). Receipt: [SA-002-review.md](evidence/SA-002-review.md).

- **Input verified:** `4d8968fd…`, 19 files, 0 mismatches; the diff digest `f605966c…` reproduced.
- **The production code has no critical or high defect:**
  - every essential producer decides its status from structured data;
  - the analyst's only input is the bundle, and nothing branches on the row;
  - the migration is additive, and there is no new secret sink.
- **The reviewer's own fixtures:**
  - A frozen symbol reads `stale` on all three essential sections (`degraded`). Correct.
  - Serper over quota reads `degraded`, with no essential section flagged. Correct.
  - With B2's rule put back at runtime, 100 of 104 health tests fail. Correct.
- **Why changes were requested, in one example.** Run the suite on Monday 28 Sep. The fake
  "healthy" price series then ends on Sunday 27 Sep. The test helper cannot build a price frame
  ending on a weekend, so the healthy technicals read `empty`, and 5 tests fail. They passed on
  2026-09-26 only because that was a Saturday.
  - **Second finding:** yfinance lists a quarter ended 30 days ago with no figures in it. The row
    says fundamentals `ok`, as of that quarter, while the prompt shows `₹nanCr`.
- **Tests:**
  - focused: 266 passed, with 0 connections blocked;
  - full: 3299 passed, 1 failed, 5 skipped. The failure is a Windows rename flake in
    `test_delivery_api`, which passes 16 of 16 alone; routed to SA-005. The guard blocked 194
    connections, the pre-existing set;
  - `check_kt_docs`: 0 errors.
- **Routed:** L1 (the Gross Profit EBITDA proxy) to SA-045; the flake and date-dependent fixtures
  to SA-005.
- **Doc edits:** status wording in the KT, ARCHITECTURE, TEAM_TESTING_GUIDE 02-F and CODEBASE.md,
  and the PDF is rebuilt. Nothing was committed, pushed or deployed.

**8. SA-002 was implemented on 2026-09-26** (a conversation from about 10:24 to 11:20 IST). Its
fresh review requested changes (step 7); the rework is step 6, and the re-review accepted it (step 5).

- **What it does, in one example:** TATAMOTORS' price source answers 404, while news, macro and
  flows answer, and the analyst scores 9/9.
  - Before, the data-health row said `ok`, with 10 live sections: every "Technical data
    unavailable for …" sentence counted as data.
  - Now each section producer returns a typed `FetchResult` (status, source, as-of, reason), so
    technicals and fundamentals read `empty`, peers valuation `fallback`, and the row `degraded`,
    with `essential_unusable` naming all three.
  - The analyst's prompt text is byte-identical: 24 producer cases and 5 whole-bundle scenarios
    were compared against the HEAD code.
  - Nothing branches on the row yet; SA-003 gates.
- **Evidence:**
  - 132 new tests;
  - the full unit suite: 3300 passed, 5 skipped, under a network guard;
  - 12 of 12 reintroduced defects caught;
  - `check_kt_docs`: 0 errors; the PDF was rebuilt.
- **Incident (recorded in the receipt).** One intermediate run of the existing sector tests, before
  their patches were retargeted, reached real providers with the local `.env` keys. It made +2
  Serper and +10 Tavily successful calls, plus public yfinance calls. The 8 Tavily cache pairs it
  wrote were deleted. Nothing in production was touched.
- **Found, pre-existing (routed to SA-005 as T2).** With the guard on, the *existing* suite tried
  194 outbound connections: `openrouter.ai` 120 (four RL review test files), NSE 68 and Serper 6.
  The pre-SA-002 code shows the same pattern. **In a normal unguarded run with `.env` keys, these
  are real calls, and the OpenRouter ones likely spend LLM credit on every suite run.** Consider
  running the suite with the guard until SA-005 lands.
- **Other routed notes:** SA-003 (gate on the record, not `has_real_data`), SA-044 (F1: the
  automobile peer P/E fallback query), SA-045 (F3: substitute zeros and defaults as factor inputs).
- **Rollout (owner, after acceptance).** Deploy is additive: 7 nullable DB columns are added on
  boot, and old rows are untouched. Expect more `degraded` rows, which is the point. Tavily cache
  entries from September read `unverified` until 1 Oct.
- **Serper credit, answered (owner, 2026-09-26):** the serper.dev dashboard shows **37,747 credits
  left**. The app's "2,590 of 2,500" was never a limit: `SERPER_MONTHLY_LIMIT` only feeds the usage
  log, and no code enforces it. Recorded on [SA-035](stories/SA-035.md). This closes the open
  "check serper.dev for real remaining credits" item from 23 Sep. IPO-0c's decision (GMP stays
  dark) stands on its own reasons.

  Rollback: `observability.data_health_enabled: false`. Production verification is read-only,
  across one scheduled cohort; see the receipt.
- **Commit interaction.** SA-001 and SA-002 are both uncommitted in one worktree and share six
  files. If they are committed together, SA-001's commit check will also show `CODEBASE.md`, which
  is SA-002's hunk. The receipt explains. Commit and push only at the owner's word, in a safe
  window.

**9. SA-001 was ACCEPTED on 2026-09-26 by a fresh-session review** (a new conversation, about
07:35–07:55 IST). Receipt: [SA-001-review.md](evidence/SA-001-review.md). SA-001 is `done`;
`production_verification` is `pending_deployment`. No SA-039 check was due during the review.

- **What the review checked:**
  - The input was verified first: `2ded4b43…`, 17 files, 0 mismatches, on baseline `103f2b8`.
  - The reviewer re-traced model and tool text to every client sink. There is one HTML sink, the
    bubble; the only URL sink, `sw.js` `openWindow`, takes server constants.
  - The previously executable fixture was re-run on the pre-fix files: 0 of 14 pass, and
    `img-onerror`/`img-split` execute. The reviewed files pass 14 of 14.
  - 20 of the reviewer's own payloads went through at every prefix: 0 executions, and the output is
    stable on re-parse.
  - The live CDN bytes equal all five SRI hashes.
  - Focused pytest: 12 passed. `check_kt_docs`: 0 errors, after the review's status-wording edits
    and the PDF rebuild.
- **Findings:** none critical, high or medium.
  - **L1 (low):** the browser suite skips on machines without Node, and the repo has no CI. Routed
    to [SA-005](stories/SA-005.md). Until then, run `npm run test:frontend` before any push that
    touches `src/frontend/prototypes/`.
  - **I1 (info):** the harness flags an inert partial `href="https://"`. Noted on
    [SA-028](stories/SA-028.md).
- **Uncommitted in the worktree:**
  - the SA-001 implementation (the 17 manifest files, plus its receipt and manifest);
  - the review bookkeeping: the review receipt, STATE, this file, and the notes on SA-005, SA-028
    and SA-002;
  - status wording in the KT, the PDF, ARCHITECTURE and TEAM_TESTING_GUIDE.

  Commit at the owner's word. Before committing, run
  `python scripts/docs/kt_manifest.py verify docs/planning/PI-2026-09/evidence/SA-001-manifest.json --rev <commit>`.
  Expect mismatches only in `TECHNICAL_DESIGN.md`, the PDF, `ARCHITECTURE.md` and
  `TEAM_TESTING_GUIDE.md`. Bump the KT header revision to the commit, and link `chat-markdown.js`
  there. `994a7b6` and `103f2b8` are also still unpushed.
- **What it does, in one example:** the model quotes `Tata Motors <img src=x onerror="…">`. Before,
  the chat bubble created the image and the handler ran, next to the stored login token. Now the
  bubble shows that text literally, and nothing runs. Bold, lists, code, tables and https links
  still render. Links open in a new tab that cannot reach the app.
- **How:** the new `src/frontend/prototypes/chat-markdown.js` has two layers:
  - marked shows raw HTML as text;
  - DOMPurify 3.4.16 keeps Markdown tags and http(s) links only, with no images, styles or events.

  It fails closed to escaped text. index.html pins marked 12.0.2 (the same bytes as before) and
  DOMPurify with SRI, and takes marked off `window` immediately. That covers a pre-fix `sphere.jsx`
  still cached by the service worker, which goes to v8.
- **Evidence:**
  - 14 real-browser tests through the actual `ChatOverlay`, with no network, stable over 3 runs;
  - 9 static pytest guards (the sink inventory, including URL sinks, and the exact pins);
  - full unit suite: 3166 passed, 5 skipped (with `RL_LEARNING_MODE=adapt`);
  - on the pre-fix files the suite records the fixture executing, and five weakened fixes are each
    caught;
  - `check_kt_docs`: 0 errors, and the PDF is rebuilt.
- **Routed:** CSP and bearer-token storage go to [SA-028](stories/SA-028.md) (a routed note). CSP
  needs the compiled client first.
- **Rollout (owner):** commit at the owner's word, and bump the KT header to that commit, linking
  `chat-markdown.js`. Every push redeploys, so push only in a safe window (step 0 rules; read IST
  with plain `date`). This change affects the served client. After the deploy, open the app twice so
  sw v8 takes over, then run human case 11-C in an isolated test account. The fixture only changes
  the tab title if it ever runs. Also confirm that `marked@12.0.2` and `dompurify@3.4.16` load with
  status 200 and no SRI error. `production_verification` stays `pending_deployment` until then.

**2026-09-26, owner-adopted design (no story started): [one engine with sector lenses](../../superpowers/specs/2026-09-26-one-engine-sector-lenses-design.md).**
This is the single reference for both the learning-exit logic (§1) and the analysis redesign.

- **The per-sector graphs go.**
  - Sector knowledge becomes lens YAML (real peers, benchmark, KPIs), resolved from NSE's
    industry field.
  - Code computes five factors: Value, Quality, Growth, Momentum and Risk.
  - One LLM reader returns dated events, and code turns them into Catalyst.
  - Code decides at equal weights; below 4 of 6 factors it gives no verdict. The LLM explains.
  - Learning uses six pooled factor weights.
- **Board:**
  - New stories: SA-044 (peer fix, Sprint 2), SA-045 (factors, Sprint 4), SA-046 (reader,
    Sprint 4) and SA-047 (decide, shadow and switch on non-inferiority, Sprint 5).
  - SA-026 is now the lens story (Sprint 3). SA-043 learns pooled factor weights (Sprint 4).
  - SA-022 and SA-027 now also depend on SA-047.
  - Totals: 44 planned stories, 158 points (Sprints 1–6: 41 / 30 / 23 / 29 / 24 / 11).
- **Found while inspecting (a live defect, fixed by SA-044):** generic-graph stocks are valued
  against car makers (SUNPHARMA → MARUTI, TATAMOTORS, M&M, HEROMOTOCO, BAJAJ-AUTO).
- KT sections 1, 4, 5, 11 and 12, ARCHITECTURE and the PI README are updated; the PDF is rebuilt
  (`check_kt_docs`: 0 errors, 47 stories).
- **Committed as `5a27683` and pushed on 2026-09-26 at 06:22:29 IST** (the reflog says "update
  by push" from this checkout). The owner asked to commit and push. The push was not run by
  Claude's commands, most likely through VS Code. It carried `0b3ebb9` too.
  - Deploy `82c945da` reached SUCCESS, and the new container registered its jobs at 06:31:09.
  - The old container ran the 06:30 watchdog first (`evaluated=17 notified=0 levels=[]`), so
    nothing was missed.
  - Documentation only; production still runs `adapt`.
- **`observe` is ACTIVE in production since 2026-09-26, about 06:40 IST.** The owner set the
  Railway variable `RL_LEARNING_MODE=observe`. Deploys `786faf7f` and `da9df6cf` (`16e7ea7`)
  reached SUCCESS. A read-only RL-monitor check shows all 20 tickers in `observe`, using the default
  weights. Record: [SA-039-activation-2026-09-26.md](evidence/SA-039-activation-2026-09-26.md).
  STATE: `production_verification: pending_observation`. Rollback is deleting the variable.
  **Checks still due (read-only):**
  - **Mon 28 Sep after 16:30:** the logs show `learning_mode=observe` and `Proposal (not
    applied)`; `/ui/rl/summary` versions match the baseline in ignored
    `analysis_data/sa039_activation_versions_20260926.json`; `/ui/rl/weights` has a
    `latest_observation` dated 2026-09-28.
  - **Tue 29 Sep:** the versions are still unchanged.
  - **Thu 1 Oct after 09:00:** the new envelopes carry `learning_mode: observe`.
- **Local side effect:** the owner's local environment (probably `.env`) now also resolves
  `observe`, so **7 lesson-emphasis unit tests fail locally**. They assume `adapt`, and SA-001 did
  not cause this. Until SA-005 pins the mode in `tests/conftest.py` (routed note added), run tests
  with `RL_LEARNING_MODE=adapt`, or remove that line from the local `.env`.
- The docs for this (the activation record, STATE, this file, KT sections 1/5/12, ARCHITECTURE,
  04-F, the SA-005 note and the PDF) are committed locally and ride the next push.

**2026-09-26, owner-requested planning (no story started): how learning leaves `observe`.**

- **New [SA-043](stories/SA-043.md)** (Sprint 3, 3 points, after SA-015): a shadow learner.
  - A separate weight file starts from the defaults and learns every night on the corrected
    target. Decisions stay on the defaults.
  - For each issued decision it records the default verdict and the shadow verdict, computed from
    the same agent scores.
- **[SA-022](stories/SA-022.md) is amended** with predeclared gates. They are scored only on
  disagreements between the two verdicts:
  - at least 100 effective disagreements, over at least 3 months and 3 sectors;
  - the shadow right on at least 60% of them;
  - wins consistent month to month and robust to dropping the best sector;
  - sane weights, with no agent collapsing to 0.

  A pass must hold at two consecutive monthly looks, and the owner decides. Promotion resumes from
  the shadow's weights, never the stored pre-fix ones. A reverse tally below 45% returns learning
  to `observe`.
- Totals are now 40 planned stories and 143 points (Sprint 3: 21). KT sections 1, 5 and 12 and the
  PI README are updated; the PDF is rebuilt (`check_kt_docs`: 0 errors). This is uncommitted,
  alongside the SA-039 review bookkeeping below.
- Owner-decided backlog changes are recorded in STATE; nothing changed in the task order, and the
  next story is still SA-001.

**SA-039 was ACCEPTED on 2026-09-25** by a fresh-session review at `4c4728a`, with review input
`1efe361f…` (0 mismatches). Receipt: [SA-039-review.md](evidence/SA-039-review.md). SA-039 is `done`.
STATE has `active_task: null`, `next_task: SA-001` and `next_phase: implementation`.
`production_verification` stays `not_started`, because production still runs `adapt`.

- **Next PI phase: implement [SA-001](stories/SA-001.md)** in a new conversation. It has no
  dependencies. Opener: `Continue — implement SA-001`.
- **Review bookkeeping is uncommitted** in the worktree:
  - the review receipt, STATE, this file and the implementation-receipt banner;
  - routed notes on SA-022 (I2) and SA-026 (L2);
  - post-acceptance docs maintenance: KT §1, §5 and §12 status lines, the L1 paper-lane wording
    and the I1 timing sentence in §5, ARCHITECTURE, TEAM_TESTING_GUIDE 04-F, and the rebuilt PDF
    (`check_kt_docs`: 0 errors).

  Commit at the owner's word. `0b3ebb9` is also still unpushed. Every push redeploys, so push only
  in a safe window (Step 0 rules; read IST with plain `date`).
- **Owner decision: activate `observe`.** Either a one-line `rl.learning_mode: observe` commit or
  the Railway variable `RL_LEARNING_MODE=observe` (checked: the env value overrides the yaml).
  **Timing (review I1):** rows already issued keep their verdicts; the review re-weights only their
  confidence. If activation lands before the **1 Oct 09:00 IST** monthly forecast, October is the
  first clean `observe` cohort. The activation commit should also update the "Production is still
  `adapt`" and status lines in the KT, ARCHITECTURE and 04-F, then rebuild the PDF. Afterwards,
  verify read-only against the [baseline](evidence/SA-039-baseline-2026-09-24.md).
- Findings: L1 is fixed (wording). L2, which predates SA-039, is routed to SA-026: the review
  initialises missing weight memory from the automobile table. I2 is routed to SA-022: observe
  freezes the numeric channels only. Earlier routes stand: T1 → SA-005, F1 → SA-024, F2 → SA-016.

### Previous state (SA-039 implemented and pushed, 2026-09-24/25)

**SA-039 implementation is done and awaits a fresh-session review** (2026-09-24, one conversation).
STATE: `active_task: SA-039`, status `review_required`, `next_phase: review`. Receipt:
[SA-039-implementation.md](evidence/SA-039-implementation.md). Review input: `1efe361f…` from
[SA-039-manifest.json](evidence/SA-039-manifest.json) (18 files) on top of HEAD `3742fff`.

- **Next PI phase: the fresh review of SA-039** in a new conversation. Opener:
  `Continue — fresh review of SA-039`. First step:
  `python scripts/docs/kt_manifest.py verify docs/planning/PI-2026-09/evidence/SA-039-manifest.json --rev 4c4728a`
  (expect 0 mismatches), then follow [REVIEW.md](REVIEW.md). Without `--rev`, the KT and PDF
  mismatch by design, because the next commit bumped the KT header. The receipt lists every decision
  consumer and the test that covers it. It also flags one scope interpretation for the reviewer:
  the untagged lesson micro-adjustment is contained too.
- **Committed and pushed on 2026-09-25 at the owner's word.** **Correction:** the owner asked at
  16:18 IST, not 10:48. `TZ=Asia/Kolkata date` returns UTC in Git Bash, so the push went out at
  about 16:22 IST, inside the blocked review window. Deploy `7ebd06c5` (`309d801`) reached SUCCESS.
  The new container was up at 16:28:56, so the 16:30 review still ran, on the new code in `adapt`
  mode: 19 completions and 19 weight writes, done at 16:54. The 20th ticker (metals) returned
  `no_envelope`; it has no forecast envelope, an existing gap. The job and its portfolio pipeline
  finished at 16:55. Nothing was missed.
  This correction is committed locally and **not pushed**; it rides the next push. Read IST with
  plain `date` from now on.
  `4c4728a` is the SA-039 change exactly as the review input describes it. The next commit bumps
  the KT header's `Code inspected` revision to `4c4728a` (edition 2026-09-25), links
  `learning_mode.py` and rebuilds the PDF. The deploy outcome is recorded in the commit after that.
  The code ships as `adapt`, so the deploy changes no decision.
- **What it does, in one example:** a ticker stores `technical = 0.0` at v41. With
  `rl.learning_mode: observe`, its forecast and analysis use the 0.12 default. After the review the
  file still says 0.0 at v41, and `<TICKER>_weight_observations.json` shows what v42 would have
  been. The code ships as `adapt`, so nothing changes until activation.
- **Activation is a separate owner decision after acceptance:** a one-line config commit, or the
  Railway variable `RL_LEARNING_MODE=observe`. Push only in a safe window (Step 0 rules). Afterwards,
  verify production read-only against the
  [baseline](evidence/SA-039-baseline-2026-09-24.md).
- **R2 done:** the baseline comes from today's 16:30 review logs (deploy `d9c459ae`). Chart weight
  was 0.0 for 9 of 18 logged tickers; 5 of the 6 `technical` tickers were at 0.0, which reproduces
  the 23 Sep figure; all 19 reviews wrote a new version. KT §1 and §5 now cite it. §5 also corrects
  the default: 0.12 generic, 0.10 renewable.
- **Routed self-review follow-ups:**
  - T1: the shared review test harness still constructs a live NSE session. Routed to SA-005, and
    it may explain the `key_registry.json` leak.
  - F1: chat context, `/scheduler/status` and the CLI show stored weights as if live. Routed to
    SA-024.
  - F2: the FeedbackAgent drift summary. Routed to SA-016.
- The Step 1 production checks below are otherwise unchanged. **OpenRouter was recharged**
  (owner, 2026-09-25). IPO-0a is still open.

### Previous state (DOC-001 accepted, earlier on 2026-09-24)

**DOC-001 was ACCEPTED on 2026-09-24** by a second fresh-session review, at `c832145` with review
input `63ff474c…`. The receipt is [DOC-001-review-2026-09-24.md](evidence/DOC-001-review-2026-09-24.md).
DOC-001 is `done`. STATE now has `active_task: null`, `next_task: SA-039` and `next_phase: implementation`.

- **Next PI phase: implement [SA-039](stories/SA-039.md)** in a new conversation. Opener:
  `Continue — implement SA-039`. Read the card's new "Routed input (R2)" section: the
  implementation must also record a sanitized pre-activation weight baseline. That record becomes
  the evidence for KT §5's "5 of 6 tickers" sentence, and §1's production row should name the
  2026-09-23 inspection when §5 is rewritten.
- The low follow-ups are routed, not waived. R3 (the KT harness imports nse 4.0.1, outside the
  `<4.0` pin) is on SA-033, and F5 stays on SA-005/SA-006.
- **Committed locally, not pushed** (at the owner's "commit", 2026-09-24): this conversation's work
  in one commit on top of `c832145`:
  - the review bookkeeping: the review receipt, STATE, this file, the implementation-receipt banner,
    and routed notes on SA-033 and SA-039;
  - the observability backlog (below).

  `origin/main` is still `e8df088`, so both local commits ride the next push. Push only on the
  owner's explicit word, in a safe window (Step 0 rules). The commits are docs-only, but every push
  still redeploys. **Manifest note:** the backlog changes
  three DOC-001 payload files (the KT, the PDF and the PI README) as normal post-acceptance
  maintenance. Verify the accepted input with `kt_manifest.py verify <manifest> --rev c832145`
  (0 mismatches). Against a later HEAD those three files will differ, and that is expected.
- **Step 1 production checks, 24 Sep**, from read-only `railway logs` (no ssh):
  - The build installed **nse 3.2.1**, so the pin works, and the fix has been live since
    23 Sep 22:44 IST (deploy `dfd7a15d`).
  - The **08:00 `ipo_refresh_am` logged no bid-ladder fetch failure**: current=7, 50 s, where the
    23 Sep 17:45 run had 10 `_req` failures. Rows on the volume are not visible from logs, so
    **IPO-0a stays open**; the 06:30 watchdog on 25 Sep or an owner probe confirms them.
  - The 06:30 watchdog raised 1 `warning`. The log doesn't name the check; it is inferred to be
    `ipo_signals_accruing`.
  - **0 OpenRouter 402s** since 23 Sep 13:30. The 23 Sep 16:30 review logged 18 runs costing
    **$0.40**, so a $0.97 balance leaves about 2 days. **Top up before 25 Sep 16:30.**
  - Still due: VARMORA rows after 17:45, and whether the 19:00 `ipo_deep_dive` stores its first
    verdict.

### Production observability — adopted 2026-09-24 (owner decisions D1–D5)

The owner asked for a proper production "fetcher" and a careful tool evaluation. The design is
[2026-09-24-production-observability-design.md](../../superpowers/specs/2026-09-24-production-observability-design.md).

- **Verdict:** no Prometheus, no OpenTelemetry SDK (field names only), no Arize or Langfuse for
  now, and Sentry deferred. Instead:
  - an in-app ops ledger in `telemetry.db`: `job_runs`, `source_health_day`, `error_signatures`
    and `budget_readings`;
  - the watchdog as evaluator, now also run right after each critical job;
  - a read-only `GET /ops/status` with `OPS_READ_TOKEN`, plus a fetcher CLI;
  - Healthchecks.io as the outside witness, alerting by Telegram.
- **Board:** SA-040 (S1, 3 points), SA-041 (S2, 3 points) and SA-042 (S1, 2 points) are added.
  SA-034 goes 5 → 6 points, SA-036 goes 3 → 4, and SA-035 is amended. That makes 39 planned
  stories and 140 points; Sprint 1 is 41 and Sprint 2 is 28. SA-039 is still first. The KT §12
  rows are added and the PDF is rebuilt (`check_kt_docs.py`: 0 errors).
- **Owner actions (settings only, no code). The owner will do these at the end**, so don't press
  for them earlier. Remind when a rollout needs one: the OpenRouter key limit for SA-035, and
  Healthchecks.io for SA-042.
  - Railway: turn on alerts for deploy failed/crashed and volume usage.
  - OpenRouter: set a monthly credit limit on the production key.
  - Healthchecks.io: create the account and connect Telegram, ready for SA-042.
- **Suggested ops order after SA-039:** SA-036 → SA-035 → SA-040 → SA-042 → SA-034 → SA-041.
  STATE's task order is unchanged, so "continue" still follows the existing sequence.

**Pushed 2026-09-24 06:56 IST at the owner's explicit "push it".** `a2c19c9..e8df088` was pushed, and
deploy `d9c459ae` reached SUCCESS at 07:03 IST. The boot log shows 24 jobs registered, no errors,
and the serper counter at 2,590/2,500. The 06:30 watchdog had already finished, and no job was due
before 07:30. Production now runs `e8df088`, which adds no application code over `a2c19c9`. The rest
of Step 0 below is the record of how the push was arranged.

### Step 0 — push the two local commits (done; see above)

Done at the owner's go-ahead, 23:30 IST:

- **`650c01c`** holds the earlier 22-path batch: the production assurance review, SA-033…SA-038,
  routed notes, and the DOC-001 payload `d5516ae0…`. `verify --rev HEAD` reported 0 mismatches.
- **The commit after it** holds the owner's three decisions (Step 2, now resolved). That is the
  SA-039 card, the SA-003 split, the SA-024 routed note, STATE, the PI README, KT §1/§5/§12, the
  rebuilt PDF, the IPO-0c record, this HANDOFF, the DOC-001 receipt ("Payload update 2") and the
  regenerated manifest (**review input `63ff474c…`**). After it, `verify --rev HEAD` must again
  report 0 mismatches.

**The push is still pending.** The owner chose "commit now, push later". At 23:28 IST a push would
have redeployed over `data_backup_nightly` (23:30), and probably over `audit_nightly` (23:45) and
`prompt_daily_deploy` (00:00).

**Every push redeploys production** (no watch-path rule until SA-037), and the in-memory scheduler
loses any job whose time falls inside the roughly 8-minute deploy.

- **Safest window: 00:10–06:20 IST.**
- Otherwise avoid 07:25–09:05, 11:55–12:05, 14:55–15:05, 16:25–17:05, 17:40–17:55, 18:55–19:20
  and 22:55–00:05.
- Push only when the owner says "push". Afterwards, confirm with `railway deployment list --json` that
  the new deploy reached SUCCESS. The two commits change documentation only, with no application code
  or requirements. The deploy still rebuilds and restarts the scheduler.

### Step 1 — time-sensitive production checks (read-only; the owner runs the probe)

| When (IST) | Check | Why |
|---|---|---|
| 24 Sep after 08:00 and 17:45 | VARMORA rows appear in `data/ipo/ipo_signals.jsonl` | First proof that `a2c19c9` fixed capture. VARMORA closes on the 24th. |
| 24 Sep after 19:00 | `ipo_deep_dive` post-close for VARMORA stored a row: `ipo_verdicts.jsonl` exists; note whether `substance` is still null | First stored P3 verdict. The 23 Sep T−1 run stored nothing (`demand=None substance=None`). |
| Until 25 Sep | `railway logs \| grep -i "error code: 402"` | The owner reported an OpenRouter balance of **$0.97**, with a top-up on 25 Sep. The existing streak alert can miss a low-balance pattern (SA-035). |
| After capture is proven | Close `IPO-0a`: delete `ipo_p0_live_window_check` from `config/milestones.yaml`, evidence in the commit message | Not before. |

The probe is `analysis_data/prod_probe_20260923.py`. It is ignored, so it may be missing in another
checkout; it prints counts and IPO fields only. Run it from Git Bash at the repo root:

```bash
railway ssh "cd /app && echo $(gzip -9c analysis_data/prod_probe_20260923.py | base64 -w0) | base64 -d | python -c 'import sys,zlib;exec(zlib.decompress(sys.stdin.buffer.read(),31))'"
```

Claude can run `railway status`, `railway deployment list --json` and `railway logs <id> -n 2000`
(plus `--build`), after prepending `/c/Program Files/nodejs:$HOME/AppData/Roaming/npm` to PATH.
**Claude's `railway ssh` is blocked by the auto-mode classifier.** Volume reads go through the
owner.

### Step 2 — owner decisions: all three resolved 2026-09-23, about 23:30 IST

1. **Learning containment: yes, reset to defaults.** The containment is split out of SA-003 as
   **[SA-039](stories/SA-039.md)** (P0, Sprint 1, 3 points, no dependencies). It is placed first in
   STATE's task order, and SA-003 went from 5 to 4 points. SA-039 resets on the **read side**:
   - Decision consumers (forecast, public analysis, and the review's re-scoring and re-forecast) use
     the sector's configured default table.
   - Lesson emphasis stops.
   - The adapter keeps computing into a diagnostic record, and stored `WeightMemory` is never
     mutated.

   So there is no production data migration, and rollback is exact. Example: stored
   `technical = 0.0` stays 0.0 on disk, while the forecast uses 0.12. The code ships with `adapt` as
   the default. Activation is a separate one-line config commit, pushed only with the owner's
   go-ahead.

   Also found while writing the card, by code inspection: the verdict-shadow field
   `learned_weights_used` is true whenever any weights are passed, defaults included, so it
   overstates learned-weight use. That is routed to SA-024, and SA-039 must not use it as evidence.
2. **IPO-0c: GMP stays dark.** It is closed in the IPO plan with no code change, because `gmp_pct` is
   already a dark froth input. The serper.dev dashboard was **not** read, so the question of real
   account credit stays with SA-035.
3. **Push timing:** commit now, and push only when the owner says so, after 00:10 IST (Step 0).

### Step 3 — then the normal PI sequence

- ✅ **DOC-001 accepted 2026-09-24** (see START HERE). The bullets below are the pre-review record.
- **DOC-001** was `review_required`, with review input
  **`63ff474cec51a5810af84dca279a8fcdaa93239cd65230e6f5cd738b01128dd0`**.
  - Its fresh-session review runs in a **new conversation**. It can run against the local commits
    before the push. Opener: `Continue — fresh-session review of DOC-001`.
  - Receipt: [the 2026-09-23 section](evidence/DOC-001-implementation.md#remediation-phase--2026-09-23).
    F1–F4 are fixed, F5 is routed to SA-005/SA-006, F6 is done, and F2 was fixed by the PDF rebuild.
  - The payload changed twice more. The first change added the SA-033–SA-038 KT rows ("Payload
    update"). The second added SA-039's row and a labelled PI-target paragraph in KT §5 ("Payload
    update 2"). Check that §5 paragraph against `daily_review.py` Step 5.
- **After DOC-001 is accepted:** select the next ready story, but do not start it in the review
  chat. By STATE's order that is **SA-039**, then SA-001.
- **Ready now** (all dependencies done): SA-039 (S1, P0), SA-001 (S1, P0), SA-002 (S1), SA-004 (S1),
  SA-005 (S1), SA-007 (S1), SA-033 (S1), SA-035 (S1), SA-036 (S1), SA-038 (S1), SA-006 (S2), SA-009
  (S2) and SA-010 (S2, P2). There are 39 SA stories in total: 36 planned (130 points) and 3 stretch.
  Sprint 1 is 35 points, and Sprint 2 is 24.
- **IPO (PI Prospect)** stays paused apart from the Step 1 checks. Open items: IPO-0a (Step 1),
  IPO-0d (brief freshness), IPO-0e (P1 spine in production), and IPO-5a/5b (gated). IPO-0c is
  closed as "no". See `docs/superpowers/plans/2026-09-21-ipo-prospect-p3-substance.md`.

### How the owner likes to work (observed this session)

- Explain each decision with a small concrete example (e.g. ₹100 → predicted ₹110 → closed ₹105).
- Welcomes deep research and wants every recommendation turned into board tasks.
- Commits and pushes happen only when the owner says so; each push is asked separately.

### Backlog additions and owner decisions — 2026-09-23 (late)

At the user's request, every recommendation in the
[production assurance review](../../audit/2026-09-23-production-assurance-review.md) is now on a
board. **New stories:** SA-033 (dependency lock), SA-034 (silent-degradation watchdog), SA-035
(LLM/Serper credit exhaustion; OpenRouter was at $0.97, top-up 25 Sep), SA-036 (job outcomes),
SA-037 (deploy/missed-job hygiene), SA-038 (lapsed milestones). **SA-007 moved to Sprint 1** (no
off-site backup). Notes were routed to SA-003, SA-008, SA-010, SA-011, SA-023 and SA-028. The IPO
plan gains `IPO-0d` (brief freshness) and `IPO-0e` (P1 spine in production).

**Decisions that were waiting on the owner** have all been resolved; see Step 2 above. Containment
became SA-039, GMP stays dark, and the push waits for the owner's word after 00:10 IST.

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
- **IPO live capture is broken in production since ~18–19 Sep.** Cause confirmed from the logs:
  `'NSE' object has no attribute '_req'`. `nse` 4.0 (31 Aug) removed `NSE._req`, and the 21 Sep
  rebuild installed 4.0.1 under the open-ended pin `nse>=2.0.0`. The fix is the pin
  `nse>=2.0.0,<4.0` plus tests of the real dependency. The 19–21 Sep window, on the old 3.2.1
  image, is still unexplained. The 22 Sep brief's category figures were 2–3 days stale (NSE QIB 1.53× shown,
  final 12.68×). VARMORA has no ledger rows, and `ipo_signals_accruing` is warning. **Do not close
  IPO-0a.** Full evidence is under IPO-0a in the plan.
- **P1 spine absent in production** (`data/ipo/ipo_history.jsonl` missing).
- **IPO-0c:** serper counter 2,590 in September (default budget 2,500). Recommend GMP stays dark;
  check serper.dev for real remaining credits.
- **P3:** no `ipo_verdicts.jsonl` yet. That is expected for NSE/SONA, because their T−1 run predates
  the deploy. VARMORA's T−1 run is 23 Sep 19:00 IST, but its demand inputs are dark (no ledger rows).
- **P3 run observed:** `ipo_deep_dive` fired at 19:01 IST for VARMORA (`t_minus_1`, 16 docs, 9
  extracted), with demand and substance both dark, so `written=False` ("every index dark, not
  stored").
- **After the fix deploys:** confirm VARMORA ledger rows land at the 08:00 / 17:45 IST refreshes on
  24 Sep, the day it closes (re-run the probe). Only then revisit IPO-0a.

### IPO stays paused

`ed1b900` (IPO-4c) is pushed and `origin/main` is current, which closes **Sprint 4** of PI "Prospect".
The user chose to **pause IPO work and wait for live production evidence** rather than start `IPO-5a`.
Do not start an `IPO-` task unless the user brings evidence or says so. One encouraging note from the
review: the incremental-documentation discipline DOC-001 introduced **is** being followed — the 23→24
job-count change propagated correctly to four documents, and cases 05-F/05-G were added with their
stories.

After DOC-001 is accepted, `SA-039` is the first remediation story. It was promoted ahead of `SA-001`
by the owner on 2026-09-23 (Step 2). Select it, but do not start it in the acceptance conversation.

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
start it in that review conversation. *(Superseded 2026-09-23: SA-039 now comes first.)*

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
