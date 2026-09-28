# SA-006 implementation receipt — repair delivery transport and expose dead letters

- **Story:** [SA-006](../stories/SA-006.md). Audit finding F17 in the
  [September audit](../../../audit/2026-09-10-repository-production-review.md).
- **Phase:** implementation, one conversation, 2026-09-28 about 13:15–15:05 IST. It includes a
  same-conversation self-review, which is **not** the fresh-session review. Its
  [fresh review](SA-006-review.md) requested changes (F1, F2). **Rework 1** (a new conversation,
  about 15:38–16:25 IST, section below) fixes both. The **fresh re-review accepted** rework 1 on
  2026-09-28 (about 19:40–20:45 IST; see the [review](SA-006-review.md)), with documentation-only
  status edits. STATE: `done`; production verification `pending_deployment`.
- **Baseline:** `9e65c7a955c7c408191857ec556f697be7c34c89` (the SA-005 KT bump), committed locally and **unpushed**:
  the owner put the push on hold at 08:46 IST, and local `main` is 3 ahead of `origin/main`. The
  tree was clean. Production runs deploy `b3fb00dd` (`90353f3`), which has none of SA-005 or SA-006.
- **SA-039 checks:** none was due. P1 is today, Mon 28 Sep, after 17:00 IST.
- **Peers:** 14 other sessions on this checkout, all idle at the start and before bookkeeping.
- **Review input:** [SA-006-manifest.json](SA-006-manifest.json). Its SHA-256 and the diff digest
  are under "Manifest and digests".

## Rework 1 — review F1 and F2 (2026-09-28)

- **Context:** a new conversation, about 15:38–16:25 IST, after the
  [fresh review](SA-006-review.md) requested changes. Same baseline `9e65c7a`; the push is still on
  hold. No SA-039 check was due (P1 is 17:00 IST). All 16 peer sessions were idle. Nothing was
  committed, pushed, deployed or sent.
- **Scope:** only F1 and F2, their tests and the documentation they touch. The other code files
  are byte-identical to the reviewed input (proven below).

**F1 in one example.** A user's phone has one push subscription. The push service reads and
stores the morning brief's push, then the connection drops before its 201.

| Case | Reviewed code | After rework 1 |
|---|---|---|
| Service stored the push, then the connection dropped (`ConnectionError(ProtocolError('Connection aborted.', …))`) | transient; retried a minute later, so **the phone shows it twice** | unknown outcome; dead after 1 attempt, so the phone shows it once and the owner report says why |
| Connection refused, DNS failure, connect timeout | transient, retried | transient, retried (unchanged); shown once when the service is back |
| Read timeout | unknown outcome | unknown outcome (unchanged) |
| TLS error | transient | unknown outcome (D10) |
| One phone's service stored the push and dropped; another phone's answered 503 | the row is retried, so the first phone gets it twice | dead: the first phone has it once, the second none (D11) |

**How.** `send_push_result` retries a push exception only when `_push_never_connected(exc)` is
true. That walks the exception's `args`, `reason` and `__cause__` (bounded to 16 nodes) and looks for
requests' `ConnectTimeout` or urllib3's `ConnectTimeoutError`. The urllib3 class is the base of
`NewConnectionError` (refused) and `NameResolutionError` (DNS). requests raises these only in the
connect phase, before a byte of the request is written (checked in requests 2.33.1
`adapters.py` and urllib3 2.6.3). Every other exception is an unknown outcome. The check uses
types only, no message text (D7).

**F2.** The reason for an account with no address is now `permanent: no email on file for this
account`. The row id identifies the row, so the owner report carries no user id, as its contract
says.

**Two decisions for the re-reviewer:**

- **D10: TLS errors are unknown outcomes.** urllib3 wraps a handshake failure and a TLS error
  mid-response in the same `SSLError`, so type alone cannot prove the request was never sent. A
  certificate fault repeats on every try anyway, so a dead letter with the reason is the useful
  signal.
- **D11: one unknown outcome stops the row for every subscription.** Retrying the row would re-send
  to the device that may already have it. The price: another device whose service answered 5xx
  loses that notification, visibly, as a dead letter. Per-subscription retry state would avoid
  this, but it needs a schema change; it is not done here.

**D12, the notification `tag`:** not added. The review left this optional choice to the owner,
who delegated it to Claude on 2026-09-28 ("take a call"). The ruling is under "Decisions for the
reviewer" below.

**Tests added or changed in rework 1** (12 new tests, all in
`tests/unit/test_delivery_sa006_invariants.py`):

- `test_real_push_dropped_after_the_service_stored_it_is_not_resent`: the review's R1 as a
  permanent test. The real pywebpush 2.3.0 → requests 2.33.1 → urllib3 2.6.3 stack talks to
  `LoopbackPushService`, a raw-socket push service on 127.0.0.1. The SA-005 boundary allows
  loopback. Each test generates its own VAPID and subscription keys. The service reads the whole
  request, stores it, and closes. Result: 1 stored, 1 connection, dead after 1 attempt, and the
  library's own "Connection aborted" in the reason, with the endpoint path redacted.
- `test_real_push_refused_connection_is_retried_and_shown_once`: a real refused connect (the port is
  bound but not listening; about 2 s on Windows). The row is queued as transient. The service then
  listens, and the row is delivered on attempt 2 with 1 stored.
- `test_a_push_drop_on_one_device_stops_the_row_for_all`: D11 at the fake boundary.
- `test_push_is_retried_only_when_the_connection_was_never_made`, 9 cases, one per exception
  type. Retried: connect timeout, refused, DNS. Not retried: dropped after sending, read timeout,
  TLS, chunked encoding, any other error, and a `ConnectionError` whose message says "refused" but
  whose type does not. The last case proves there is no text matching.
- I5 (`test_nothing_private_reaches_logs_rows_or_the_report`) now includes an account with no
  address. Neither the report nor any stored reason contains `u_a` or `u_9f3a1c2e`.
- The F2 reason text is updated in `test_delivery_channels.py` and `test_atlas_outbox.py`. The
  outbox test also asserts that the id is absent.

**Rework mutations** (scratchpad script: each mutation applied alone, the 3 delivery test files
run with `-x`, and `channels.py` restored and checked by SHA-256, `c420cd6e…` before and after):

| # | Mutation | Caught by |
|---|---|---|
| RW1 | The reviewed classification (only `ReadTimeout` is unknown) | `test_real_push_dropped_after_the_service_stored_it_is_not_resent` |
| RW2 | No push exception is ever retried | `test_real_push_refused_connection_is_retried_and_shown_once` |
| RW3 | Classify by message text ("refused", "Max retries") | `test_push_is_retried_only_when_the_connection_was_never_made[tls]` |
| RW4 | No cause-chain walk (top exception only) | `test_real_push_refused_connection_is_retried_and_shown_once` |
| RW5 | The user id back in the reason (F2) | `test_nothing_private_reaches_logs_rows_or_the_report` |

**5 of 5 caught.**

| Check | Command | Result |
|---|---|---|
| Focused delivery tests | the 9-file command under "Tests" below | **124 passed**, 0 failed (38 s): the reviewed 112 plus the 12 new ones |
| Full suite, owner's checkout (`.env` present) | `python -m pytest -q -p no:cacheprovider -rfEs tests` | **3837 passed, 12 skipped, 0 failed** in 11 min 02 s: the reviewed 3825 plus the 12 new tests. `data/`, `logs/` and `outputs/`: 800 files before and after, 0 changed, added or removed (size and mtime) |
| Broad-except guard | `PYTHONPATH=".;src" python scripts/ci/check_broad_except.py` | OK (154 grandfathered, 0 new) |
| KT | `python scripts/docs/build_kt_pdf.py`, then `check_kt_docs.py` | 26 pages; source `622c8437…`; errors `[]` |

**Documentation changed in rework 1:**

- KT §10: the "Transient failures retry" and "At most once" bullets now describe the push rule and
  D11, the "Visibility" bullet the F2 text, and the status line.
- The KT §12 summary, the ARCHITECTURE row and the four guide status lines now read "re-review
  pending". Guide case 10-C also expects "no phone shows the same notification twice".
- The PDF is rebuilt.
- In this receipt: the classification table and the visibility paragraph.

**Manifest and digests (rework 1):**

- **New review input:** [SA-006-manifest.json](SA-006-manifest.json), 18 paths (the same list),
  SHA-256 **`b8273b2c0d0fc79a326aa688b2de50105189ecfecc0bf9bbb9e9019d29dcaf16`**. `verify` gives 0
  mismatches. The reviewed input stays as [SA-006-manifest-review1.json](SA-006-manifest-review1.json)
  (`516d2aec…`). The new manifest also excludes `SA-006-review.md` and that copy.
- **Rework diff** (reviewed input → now):
  **`713e1675dc912b4ab918637520afca81e9c8521834e0f27da559260299a2633a`**, 29,760 bytes over 7 text
  files. The files are `core/delivery/channels.py`, the 3 test files, the KT, ARCHITECTURE and the
  guide. The PDF blob went from `f636514d…` to `44756c87…`. The other 10 manifest paths are
  byte-identical to the reviewed input.
  - **How it is built:** `analysis_data/sa006/sa006_rework_diff.py` (ignored). It rebuilds the
    reviewed tree: the baseline blobs, plus `git apply` of the reviewed full diff (`79ec6b54…`,
    kept as `analysis_data/sa006/SA-006-review1.diff`), under `analysis_data/sa006/review1/`.
  - It checks all 17 rebuilt text files against the review-1 manifest: **17 of 17 match**.
  - It then concatenates `git diff --no-color --no-ext-diff --no-index -- analysis_data/sa006/review1/PATH PATH`
    for each changed text path, sorted.
- **Full diff against `9e65c7a`**, rebuilt with the same recipe as before (below):
  **`e01c4913bce8d72b7e3fc152c3dcfda61df1ef42e30b59a2c4f3d2e9f4e1f5c9`**, 149,033 bytes over 17
  text files.

The sections below are the original implementation record. Where rework 1 changed a statement,
the text says so.

## What it does, in one example

A beta account `u_b` has a morning brief queued for email. The account lookup in `users.db` hits
"database is locked", then works a minute later. In the same run, the owner's own brief meets a
Gmail relay that rejects the password.

| | Before (`590bc9f`, deployed) | After |
|---|---|---|
| `u_b`'s brief, lookup fails | sent to the owner's `DELIVERY_EMAIL_TO` | not sent; retried in 1 minute, reason "transient: account email lookup failed (OperationalError); will retry" |
| `u_b`'s brief, a minute later | — | sent to `u_b`'s own address, once |
| Owner's brief, password rejected | tried 3 times over 6 minutes, then `dead` with the raw SMTP error | tried once, then `dead`: "permanent: SMTP login rejected (…) — check SMTP_USER and SMTP_PASSWORD (Gmail needs an app password)" |
| What the owner can see | the container log (lost at the next redeploy) or a database shell | `GET /delivery/outbox`: counts per channel, both reasons, and "user receipt: not observable" |

`test_each_account_gets_only_its_own_mail_even_when_lookup_fails` and
`test_auth_rejection_stops_after_one_attempt` run exactly this, against a fake SMTP relay that
records what it accepted.

## The contract

Every transport (SMTP, Resend, web push) now returns one `SendResult` (in
[channels.py](../../../../core/delivery/channels.py)):

| Field | Meaning |
|---|---|
| `accepted` / `accepted_count` | The transport ACCEPTED it: SMTP 250, Resend 2xx, a push service's 201 (count = subscriptions). Never "received". |
| `reason` | Why not, redacted; `""` when accepted. Persisted to `outbox.last_error`. |
| `permanent` | A retry cannot help, or cannot be made safely. |
| `retry_after_s` | The provider's `Retry-After`, when it sent one. |
| `accepted_by` | `smtp`, `resend id=<Resend's id>`, or `webpush N/M subscriptions`. |

How each failure is classified:

| Failure | Class | Drainer action |
|---|---|---|
| SMTP network error before anything was sent (connect, TLS, login phase); a push whose connection was never made (`ConnectTimeout`, or a `ConnectionError` over urllib3's `NewConnectionError`/`NameResolutionError`; rework 1); any Resend request error (its `Idempotency-Key` deduplicates the retry); SMTP 4xx; HTTP 429 or 5xx; Resend 409 `concurrent_idempotent_requests`; users.db lookup error for an account | transient | retry after 1, then 5 minutes (configured backoff), or the provider's `Retry-After` if longer, capped at 6 h; dead after 3 attempts: "retries exhausted (3/3): …" |
| Rejected login (535); any SMTP 5xx (for example 550 no such user); no STARTTLS/AUTH; Resend 400/401/403/404/422 and 409 `invalid_idempotent_request`; push 401/413 and other 4xx | permanent | dead after this one attempt, with a hint |
| Channel disabled; channel unconfigured (no SMTP_HOST, no RESEND_API_KEY, no VAPID key, no recipient); no push subscription; account without an address; unreadable payload or attachment | permanent | dead after one attempt, no transport call where none is possible |
| SMTP connection lost **inside** `sendmail`; **any push exception other than a connection never made** (a read timeout, a connection dropped after the request was sent, a TLS error, pywebpush's own errors; rework 1, review F1); a row left `sending` by a stopped process for more than 60 minutes; a transport that raised | unknown outcome | dead, never re-sent: "unknown outcome: … not retried — a retry could duplicate it". One subscription's unknown outcome stops the whole row |
| QUIT fails after the 250 | accepted | the relay already accepted it |
| Push: some subscriptions accept, others fail | accepted | not retried, so no accepting device gets a copy twice; `accepted_by` says `1/2` |
| Push: 400/403/404/410 | pruned | the subscription is removed (unchanged); if none are left the row is permanent |

**At most once, except where the provider deduplicates.** SMTP and web push have no idempotency,
so an unknown outcome is not retried. Resend documents an `Idempotency-Key` header (24-hour
window, at most 256 characters; checked on 2026-09-28 against
<https://resend.com/docs/api-reference/emails/send-email> and its errors page). Each outbox row
sends `stockagent-outbox-<sha256(dedupe_key)[:40]>`, which is stable across the row's retries and
does not name the internal user id. So a Resend request that timed out after Resend accepted it
is retried, and Resend returns the first result instead of sending again. Retries end well inside
the 24-hour window: two waits, each capped at 6 hours. This relies on the provider's documented
behaviour; it was not exercised against the live API.

**Recipient isolation.** `resolve_recipient()` now returns a `Recipient(address, reason,
permanent)`. `DELIVERY_EMAIL_TO` is used only on the single-user path: no user id, or the default
portfolio id `primary`, which is not a real account. For any other account, a lookup error is
transient and a missing account or address is permanent; neither falls back to the owner. The
inline path in `deliver()` (Atlas off, or the outbox unreachable) used to call `send_email` with
no recipient, which meant `DELIVERY_EMAIL_TO` for every user; it now uses the same rule.

**Redaction.** `channels.redact()` masks configured secrets (`RESEND_API_KEY`, `SMTP_PASSWORD`,
`VAPID_PRIVATE_KEY`), email addresses, URL paths (a push endpoint path is a bearer capability; the
host stays) and urllib3's `url: …` fields, and caps text at 500 characters. Every reason and every
transport log line passes through it. The report re-redacts stored reasons, so rows written by
`590bc9f` (which could hold a refused recipient's address) are masked on the way out.

**Visibility.** `GET /delivery/outbox?limit=N` (owner session or machine key, `require_owner`)
returns `outbox_report()`: counts per channel and status with `delivered` shown as `accepted`; the
newest dead letters and retrying rows with id, channel, kind, time, attempts and reason; the last
acceptance per channel; `accepted_means`; and `user_receipt: "not observable: …"`. No payload,
address or user id (an account without an address reads "permanent: no email on file for this
account" since rework 1; before, the reason named the user id, review F2).

**History.** The outbox has two new columns, `accepted_by` and `claimed_at`, added by the existing
additive migration in `atlas_store._migrate` (also in `_SCHEMA` for new databases). Nothing re-queues
or rewrites a dead row. Nightly retention (C9) now deletes accepted rows after 30 days as before,
but keeps dead letters for `outbox_dead_letter_retention_days` (180); after 30 days only a dead
row's payload is cleared, because the message content is private and stale by then.

**Push TTL.** pywebpush's `webpush()` defaults to `timeout=None` and `ttl=0` (checked with
`inspect.signature` on the installed version). So a hung push service could block the drainer
thread forever. With `ttl=0` a push service may drop a notification for a phone that is offline
when it arrives, even though it accepted the push. Every push now passes `timeout=20` and
`ttl=delivery.push_ttl_seconds` (12 h). This comes from reading the library; how many past pushes
were dropped is not known.

**Direct senders.** The monthly Learning Evidence email, the watchdog heartbeat and the backup
email still call `send_email` directly: no outbox row, retry or dead letter. `send_email_result`
now logs its "unconfigured" refusals, SMTP/Resend failures already log their redacted reason, and
the scheduler logs when the Learning Evidence email is not accepted, with the saved report's
path. Moving these onto the outbox is not done here (the backup attaches a zip; the outbox `kind`
check has no report kind). SA-007 owns backups; SA-042 adds an outside witness.

## Read-only production diagnosis

| Evidence | Kind | Result |
|---|---|---|
| 2026-09-23 probe (recorded in HANDOFF) | measured, owner-run | Since the 21 Sep Pro redeploy: 8 email rows accepted, 0 dead; 11 push accepted. Before: 77 email dead, 77 push accepted. |
| `railway deployment list` today | measured | Live deploy `b3fb00dd` = `90353f3`, SUCCESS 2026-09-27 10:30 UTC. |
| `railway logs b3fb00dd -n 5000`, counted, nothing printed | measured | 389 lines retrievable, 27 Sep 16:05 → 28 Sep 12:01. Drainer started 1; "queued to outbox" 3; dead-lettered 0; `[delivery] email send failed` 0; `Errno 101` 0; push send failed 0; 0-subscription drops 0; "landed NOWHERE" 0. The drainer does not log successes, so acceptance is not counted here. |
| Which transport production uses | inference | SMTP: the 23 Sep acceptances came after a plan change that only affects SMTP, and no Resend rejection was ever logged. `RESEND_API_KEY` was not inspected. |

So the transport-level cause (F17, D6: Railway Hobby blocks outbound SMTP) was resolved by the
owner's plan upgrade and redeploy on 21 Sep. SA-006 does not change transport selection. It
changes what happens when a transport fails, and makes that visible.

A read-only probe for the owner, `analysis_data/sa006/prod_probe_outbox.py` (ignored), reads
`atlas.db` with `mode=ro` and prints counts per channel and status before/since 21 Sep, stuck
`sending` rows, dead reasons since 21 Sep (masked), the last acceptance per channel and whether
each transport setting is present (booleans and the `EMAIL_TRANSPORT` mode only). It was dry-run
against a synthetic database. It has not been run in production.

## External configuration (prepared, not requested)

Nothing is required for the current setup: SMTP on Railway Pro works. Two optional changes, with
their rollback:

- **Per-account email over Resend** (only if SMTP is dropped): verify a sending domain in Resend,
  then set `RESEND_API_KEY` and `RESEND_FROM="StockAgent <alerts@your-domain>"` in Railway.
  `EMAIL_TRANSPORT=auto` then picks Resend. Rollback: unset `RESEND_API_KEY` (auto returns to
  SMTP). Each variable change redeploys. Without a verified domain, the shared
  `onboarding@resend.dev` sender reaches only the Resend account owner, and every other account's
  row would dead-letter with Resend's 403 and the RESEND_FROM hint.
- **Tuning**, all in `config.yaml` → `delivery.*`: `outbox_retry_after_cap_minutes`,
  `outbox_sending_stale_minutes`, `outbox_dead_letter_retention_days`, `push_ttl_seconds`
  (set `0` to restore pywebpush's old behaviour).

## Decisions for the reviewer

- **D1 At most once.** An unknown outcome dead-letters instead of retrying. The alternative (at
  least once) risks a duplicate brief; the card asks for no duplicates. The cost: a message whose
  connection dropped mid-send, but which the relay never accepted, is lost, visibly.
- **D2 Stale window 60 minutes.** It must exceed the longest send (20 s per network step, up to
  50 push subscriptions). A row claimed before `claimed_at` existed uses its last schedule time.
- **D3 Stored status unchanged.** `status='delivered'` stays in the table (changing the CHECK
  constraint needs a table rebuild); the report, KT and docstrings call it `accepted`.
- **D4 Default id keeps the fallback.** `primary` is the single-user path, so `DELIVERY_EMAIL_TO`
  stays its address, including when the lookup fails.
- **D5 Dead-letter retention.** 180 days, payload cleared at 30. Before, retention deleted dead
  rows with delivered ones at 30 days, so the dead-letter history vanished within a month.
- **D6 Push TTL 12 hours.** A behaviour change in what users can receive, based on library
  defaults, not a production measurement. A notification can arrive up to 12 hours late instead
  of never.
- **D7 Classification by structured signals only:** SMTP reply codes and exception types, HTTP
  status codes and Resend's error `name`. No message-text matching, except the `Errno 101` hint.
- **D8 Direct senders stay direct** (see above); only their logging changed.
- **D9 A `SendResult` class instead of the old `(ok, reason)` tuples.** Only the outbox and tests
  used the tuples; `send_email` and `send_push` keep their bool/int returns.

Added by rework 1. The re-review should rule on each of these:

- **D10: a push TLS error is an unknown outcome, not transient.**
  - **Example.** The push service's certificate fails verification. Before rework 1 the row was
    retried 3 times; now it dead-letters after one attempt, with the TLS reason.
  - **Why.** urllib3 raises the same `SSLError` for a failed handshake and for a TLS failure
    while the response is being read. So the type cannot prove that the request was never sent.
    A certificate fault would also fail on every retry.
  - **Cost.** A brief TLS glitch while connecting loses that push, visibly.
- **D11: one subscription's unknown outcome stops the row for every subscription.**
  - **Example.** Phone A's service stores the push and the connection drops; phone B's service
    answers 503. The row dead-letters: A has the push once, and B does not get it.
  - **Why.** Retrying the row would send it to A a second time.
  - **The alternative, not done here.** Retry state per subscription needs a schema change.
    The row-level rule is the same one the reviewed code already applies when some phones accept
    and others fail: that row is not retried either (see the classification table).
- **D12: no notification `tag` in the service worker, for now.** The owner delegated this choice
  on 2026-09-28; Claude decided.
  - **What the tag would do.** A per-message `tag` in `sw.js` `showNotification` would make a phone
    replace a second copy of the same message instead of showing two.
  - **Why not now:**
    1. After F1 our own retries cannot duplicate a push. Real-stack tests prove it.
    2. A tag cannot make a retry safe. It merges a copy only while the first is still on screen,
       so it would not change D10, D11 or any server rule.
    3. The only source of a duplicate left is the push service redelivering by itself. RFC 8030
       allows this when the phone's acknowledgement is lost. Nothing here shows it happening.
    4. The change runs on every user's phone, and no automated test runs the service worker's push
       handler, so a slip would stop all notifications. That risk is not worth taking inside a
       story under review for a gain nobody has observed.
  - **Trigger to revisit.** Guide case 10-C (or any user report) sees one notification shown
    twice. Then pass the outbox row's idempotency key as the payload's `tag`, set it in `sw.js`,
    and add a browser test.

## Tests

Environment: Windows 11, Python 3.13.11 (`.stockai`), pytest 9.0.3, the SA-005 hermetic boundary
(no `.env`, no network, sandboxed working directory). No real SMTP, HTTP or push call exists in
any test: fakes replace `smtplib.SMTP`, `requests.post` and `webpush` at the module boundary.

**New: `tests/unit/test_delivery_sa006_invariants.py`**, 22 tests. Fake servers (an SMTP relay, the
Resend API as documented, a push service) count what they accepted; a controlled clock drives the
drainer; a `BaseException` stands in for the container dying mid-send. Invariants: at most one
accepted copy per row (I1); transient retries on schedule and Retry-After, capped (I2); permanent
stops after one attempt with a hint (I3); each account gets only its own mail (I4); no address,
secret, endpoint or payload in logs, rows or the report (I5); acceptance is not reported as
receipt and history is untouched (I6); plus the owner-only route and the additive migration on a
pre-SA-006 table.

**Changed:** `test_delivery_channels.py` (the Resend and recipient tests now assert the contract;
the old test that asserted a fallback to the owner on a lookup error encoded the defect and is
replaced; new inline-path isolation test; push fakes take `timeout`/`ttl`),
`test_atlas_outbox.py` (`SendResult`, exhausted-retry reason, idempotency key passed),
`test_atlas_retention.py` (dead letters kept, payload cleared, 180-day cap).

| Check | Command | Result |
|---|---|---|
| Focused delivery tests | `python -m pytest -q -p no:cacheprovider tests/unit/test_delivery_channels.py tests/unit/test_delivery_channels_attachments.py tests/unit/test_delivery_sa006_invariants.py tests/unit/test_atlas_outbox.py tests/unit/test_atlas_retention.py tests/unit/test_delivery_api.py tests/unit/test_delivery_alerts.py tests/unit/test_backup.py tests/unit/audit/test_audit_monthly_section.py` | **112 passed**, 0 failed (35 s) |
| Mutations | `analysis_data/sa006/mutate.py`: each mutation applied alone, its named tests run, source restored (`git diff --stat` identical before and after) | **16 of 16 caught** (table below), run twice: after the first green run and on the final code |
| Full suite, owner's checkout (`.env` present) | `python -m pytest -q -p no:cacheprovider -rfEs tests` | **3825 passed, 12 skipped, 0 failed** in 12 min 42 s. That is SA-005's 3800 plus the 25 new tests. `data/`, `logs/` and `outputs/`: 800 files before and after, 0 changed, added or removed (size and mtime) |
| Broad-except guard | `PYTHONPATH=".;src" python scripts/ci/check_broad_except.py` | OK (154 grandfathered, 0 new). The first run found 2 new silent handlers (JSON parsing in the Resend path); both now catch only `ValueError`. |
| KT document check | `python scripts/docs/check_kt_docs.py` (after `build_kt_pdf.py`) | errors `[]`; 26 pages; source `34f79b83…` |
| KT test runner | `python scripts/docs/run_kt_checks.py` | **Did not run, before SA-006 too:** exit 4, conftest import error. Since SA-005, `tests/hermetic.py` seeds from the tracked `data/nse/key_registry.json`, which this runner does not copy. Its printed "324 tests, 2 failures" is a stale 24 Sep `pytest.xml`. Routed to SA-031. Its selection is a subset of the full suite above. |

Mutations, all expected to be caught:

| # | Mutation | Caught by |
|---|---|---|
| M1 | A users.db lookup error falls back to the owner (the `590bc9f` defect) | `test_each_account_gets_only_its_own_mail_even_when_lookup_fails` |
| M2 | An account without an address falls back to the owner | `test_an_account_without_an_address_is_not_mailed_to_the_owner` |
| M3 | Permanent failures retry like transient ones | `test_auth_rejection_stops_after_one_attempt` |
| M4 | Stale `sending` rows are re-queued (at least once) | `test_process_killed_after_acceptance_is_never_resent` |
| M5 | No `Idempotency-Key` sent to Resend | `test_resend_timeout_retry_is_deduplicated_by_the_idempotency_key` |
| M6 | `Retry-After` ignored | `test_resend_retry_after_is_honoured_and_capped` |
| M7 | SMTP reason not redacted | `test_nothing_private_reaches_logs_rows_or_the_report` |
| M8 | A push read timeout is retried | `test_push_read_timeout_is_an_unknown_outcome_and_not_resent` |
| M9 | An SMTP drop inside the send is retried | `test_connection_dropped_after_acceptance_is_not_resent` |
| M10 | Retention deletes dead letters at 30 days | `test_prune_outbox_removes_only_old_terminal_rows` |
| M11 | The report shows `delivered` | `test_report_separates_acceptance_from_receipt_and_keeps_history` |
| M12 | Push TTL left at pywebpush's 0 | `test_send_push_fans_out_and_prunes_expired` |
| M13 | The inline path mails `DELIVERY_EMAIL_TO` | `test_inline_deliver_mails_the_account_not_the_owner` |
| M14 | A disabled channel is retried | `test_a_disabled_channel_is_dead_lettered_without_a_send` |
| M15 | A partially accepted push is retried | `test_push_partial_acceptance_is_not_retried` |
| M16 | The migration omits `claimed_at` | `test_existing_outbox_gains_the_new_columns_without_touching_rows` |

An earlier full run on a busy machine (mutation runs alongside; 3824 passed, 12 skipped, 1
failed, 12 min 19 s) failed `test_ipo_signals.py::test_prune_keeps_a_row_whose_timestamp_cannot_be_parsed`
with `PermissionError: [WinError 5]` from `os.replace` in `core/ipo/signals.py:181`. It passed
3 of 3 times alone. Neither file is touched by SA-006. It is the Windows rename race that SA-005's
`replace_with_retry` covers for three other writers; this writer does not use it (routed to
SA-031 with the other Windows notes).

Not exercised: a live SMTP relay, the live Resend API (its idempotency behaviour is taken from its
documentation), a real push service, Linux/Python 3.11 (CI has never run; it needs the held push),
and a real two-container deploy overlap.

## Documentation

- [KT §10](../../../TECHNICAL_DESIGN.md): the delivery contract (accepted is not received,
  transient/permanent, at most once, recipient isolation, redaction, push TTL, the outbox view,
  history, direct senders), the dated production observation with the 23 Sep counts, and the
  remaining limits. §1, §11, §12 and §13 status lines. PDF rebuilt with
  `scripts/docs/build_kt_pdf.py`: 26 pages, source `34f79b83…`; `check_kt_docs.py` errors `[]`.
- [ARCHITECTURE.md](../../../ARCHITECTURE.md): the current-versus-planned row.
- [TEAM_TESTING_GUIDE.md](../../../TEAM_TESTING_GUIDE.md): 10-B (the outbox view says `accepted`),
  10-C (one transient and one permanent failure, both visible with reasons), 10-E (status), and a
  new 10-F (a phone offline across a scheduled push still receives it).
- [CODEBASE.md](../../../../CODEBASE.md): the `delivery.*` settings table (five new keys, two
  changed meanings).
- `config.yaml`: the stale "SMTP cannot work in prod" comment corrected; the new keys.
- Story cards: [SA-011](../stories/SA-011.md) (dead letters as a backlog source) and
  [SA-031](../stories/SA-031.md) (the Windows rename flake), each under a routed-input heading.

## Rollout and rollback

- **Deploy:** needs the owner's push (every push redeploys; the current hold stands). The two
  columns are added on the first connection after the deploy. Deploy outside 16:25–17:15 IST.
- **First read after the deploy (read-only):** `GET /delivery/outbox` with the machine key, or the
  probe above. Expected: historical dead letters listed with their old reasons (masked); new
  accepted rows carry `accepted_by`.
- **Rollback:** revert the commit. The two extra columns are harmless to the old code (it names
  its columns). Dead letters kept past 30 days would then be pruned by the old retention.
- **Production verification** stays `pending_deployment`, then needs: one observed transient
  failure retried to acceptance or one permanent failure dead-lettered with its hint (human case
  10-C), and 10-E with two test accounts. A real test email or push, or re-sending a dead letter,
  needs the owner's explicit messaging authorization. None was sent.

## Open limitations and routed follow-ups

- Receipt is not observed: no bounce/delivery webhooks. A Resend id can be looked up by hand.
  Wiring Resend's delivery events would be new scope (not routed; the owner may add a card).
- Direct senders have no retry or dead letter (D8): backup → SA-007; heartbeat visibility →
  SA-042.
- Dead-letter alerting: nothing pushes a notice when email dead-letters. `ops_alerts` broadcasts to
  every user, so it is the wrong channel. Routed to SA-011 (card: "Routed input — 2026-09-28").
- The inline path (Atlas off) has no retry at all; production runs the outbox.

## Manifest and digests

- **Review input (first review):** then `SA-006-manifest.json`, now kept as
  [SA-006-manifest-review1.json](SA-006-manifest-review1.json); rework 1 regenerated
  `SA-006-manifest.json` (see "Rework 1"). SHA-256 of its LF bytes
  **`516d2aec6ab365c08295e69fad0681f921edbba06810c810a73c870ceb14bb0d`**. 18 paths:
  - 7 code and configuration files: `core/delivery/channels.py`, `core/delivery/outbox.py`,
    `core/portfolio/retention.py`, `services/api/routes/delivery_api.py`,
    `services/data/stores/atlas_store.py`, `services/scheduler/python/scheduler.py`, `config.yaml`;
  - 4 test files: `tests/unit/test_delivery_sa006_invariants.py` (new), `test_delivery_channels.py`,
    `test_atlas_outbox.py`, `test_atlas_retention.py`;
  - 7 documentation files: the KT, the PDF, `docs/ARCHITECTURE.md`, `docs/TEAM_TESTING_GUIDE.md`,
    `CODEBASE.md`, and the SA-011 and SA-031 cards.

  `python scripts/docs/kt_manifest.py verify docs/planning/PI-2026-09/evidence/SA-006-manifest.json`
  gives 0 mismatches. `git status` shows no other change: every modified tracked file is listed,
  except STATE.json.
- **Excluded,** because they are written after the manifest: STATE.json, HANDOFF.md and this
  receipt.
- **Full diff** against `9e65c7a`:
  **`79ec6b542beed36baa42474b8c473ca09ea69585b70cd3b1154f0a3fa5afc146`**, 135,768 bytes over 17
  text files. The PDF is pinned by its blob, `f636514d…` (source `34f79b83…`).
- **To rebuild the diff:** take every manifest path except the PDF, sorted.
  - For a path tracked at the baseline, run `git diff --no-color --no-ext-diff 9e65c7a -- PATH`.
  - For a new file, run `git diff --no-color --no-ext-diff --no-index -- /dev/null PATH`.
  - Concatenate the bytes. The ignored `analysis_data/sa006/sa006_diff.py` does exactly this.
- **After a commit:** `verify --rev <commit>` compares against the commit instead.
