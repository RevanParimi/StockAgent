# SA-006 review receipt — repair delivery transport and expose dead letters

## Re-review (rework 1): ACCEPTED (2026-09-28, fresh session)

- **Story:** [SA-006](../stories/SA-006.md). Implementation receipt:
  [SA-006-implementation.md](SA-006-implementation.md), section "Rework 1".
- **Review context:** a **fresh-session re-review** in a new conversation on 2026-09-28. It did not
  implement the story or the rework, and it read neither chat. The review ran about 19:40–20:45 IST.
  An outage of the tool-safety check blocked every shell command for a while, so only code
  reading happened then; the checks below ran from about 20:15 IST.
  - **SA-039 P1** was due (17:00) and ran first, read-only, in this conversation. It **passed**
    (recorded in the [activation record](SA-039-activation-2026-09-26.md)).
  - All 17 peer sessions were idle at the start and before bookkeeping. STATE and HANDOFF were last
    written at 18:24 IST by the previous session's D12 bookkeeping, which matches what this review
    read.
- **Reviewed input:**
  - `kt_manifest.py verify SA-006-manifest.json` on the worktree: 18 files, **0 mismatches**.
    The review input SHA-256 is **`b8273b2c0d0fc79a326aa688b2de50105189ecfecc0bf9bbb9e9019d29dcaf16`**,
    as in STATE. The first review's input, [SA-006-manifest-review1.json](SA-006-manifest-review1.json),
    still hashes to `516d2aec…`.
  - **Full diff against `9e65c7a`,** rebuilt by the reviewer's own script with the receipt's recipe:
    **`e01c4913bce8d72b7e3fc152c3dcfda61df1ef42e30b59a2c4f3d2e9f4e1f5c9`**, 149,033 bytes over 17
    text files, as in the receipt.
  - **The reviewed tree of the first review, rebuilt independently.** Start from the baseline
    blobs and apply the kept first-review diff (`analysis_data/sa006/SA-006-review1.diff`, itself
    `79ec6b54…`, 135,768 bytes, which matches the first review). Result: **17 of 17** files match
    the first review's manifest blobs.
  - **Rework diff** (first review's input → now): **`713e1675dc912b4ab918637520afca81e9c8521834e0f27da559260299a2633a`**,
    29,760 bytes, as in the receipt. It is computed with the receipt's relative paths, after
    checking that the implementer's rebuilt tree equals the reviewer's rebuild, line endings
    aside.
  - **What changed since the first review,** by manifest blob: `channels.py`, the three delivery
    test files, the KT, ARCHITECTURE, the guide, and the PDF. The other 10 paths, including
    `outbox.py`, are byte-identical to what the first review saw.
  - **Completeness:** every modified or untracked file is either in the manifest or is one of the
    excluded bookkeeping files. Besides those, this conversation's SA-039 P1 record touched two
    files outside SA-006: the activation record and the [SA-001](../stories/SA-001.md) carry-over
    box.
  - **Baseline:** HEAD `9e65c7a` (local `main`, 3 ahead of `origin/main`; the push is on hold).
- **Verdict: `accepted`** for review input `b8273b2c…` (full diff `e01c4913…`), plus the
  documentation-only status edits listed under "Review edits".

### F1 and F2: fixed

**F1 (a push could reach a phone twice): fixed.** `send_push_result`
(`core/delivery/channels.py:563-583`) now retries a push exception only when
`_push_never_connected` (`channels.py:481-510`) finds requests' `ConnectTimeout` or urllib3's
`ConnectTimeoutError` in the exception's `args`, `reason` or `__cause__`. Every other exception is
an unknown outcome, and the row dead-letters.

- **Checked against the installed libraries, not only the docstring:**
  - requests 2.33.1 `adapters.py:183-187`: the default adapter uses `Retry(0, read=False)`, so
    urllib3 makes one attempt and never retries by itself.
  - `adapters.py:662-678`: a connect-phase failure arrives as `MaxRetryError` whose `reason` is a
    `ConnectTimeoutError`. That is `ConnectTimeout`, or a `ConnectionError` over `NewConnectionError`
    or `NameResolutionError`, both subclasses.
  - A failure after the request was written is re-raised as `ProtocolError('Connection aborted.', …)`
    and wrapped at `adapters.py:659-660`, with no `ConnectTimeoutError` in its chain.
  - pywebpush 2.3.0 calls `requests.post` with no session (`__init__.py:159-160`). So every push
    opens a fresh connection, and a reused keep-alive connection cannot be what dropped.
  - urllib3 2.6.3 raises `ConnectTimeoutError`, `NewConnectionError` and `NameResolutionError`
    only in `HTTPConnection._new_conn` (`connection.py:211-219`), before any byte is written.
  - urllib3's own `Retry._is_connection_error` (`util/retry.py:381-387`), whose docstring reads
    "we're fairly sure that the server did not receive the request, so it should be safe to
    retry", makes exactly this test: a `ConnectTimeoutError`, with a `ProxyError` unwrapped first.
    `_is_read_error` treats `ProtocolError` as "the server began processing it". The rework's
    rule is the library's own.
- The two real-stack tests (a loopback push service reached through pywebpush → requests →
  urllib3) pass. The first stores the push and then drops the connection: 1 copy, 1 connection, dead
  after 1 attempt. The second is a real refused connection: queued as transient, then delivered
  once on attempt 2.
- **The first review's fixture R1 is now a permanent repo test.** This review's mutation RR1 (the
  plausible wrong fix, "treat any `ConnectionError` as transient") makes it fail.

**F2 (the owner report could show a user id): fixed.** The reason is now "permanent: no email on
file for this account" (`channels.py:235`). The I5 test adds an account without an address and
asserts that neither `u_a` nor `u_9f3a1c2e` appears in the report or in any stored reason.
`test_atlas_outbox.py` asserts the same. RR7 (the `permanent:` prefix dropped) was caught.

### Rulings on the rework's decisions

- **D10 (a push TLS error is an unknown outcome): upheld.**
  - urllib3 wraps a TLS error as `SSLError` both when it connects and when it reads the response
    (`connectionpool.py:481` and `:826`). It is not one of urllib3's own safe-to-retry connection
    errors, and requests raises the same `SSLError` for both. So the type cannot prove that
    nothing was sent.
  - A certificate fault also fails on every attempt, so retrying it would only delay the dead
    letter.
  - Probe PR2 (an HTTPS endpoint whose server closes at once) gives an unknown outcome, 1
    connection, dead after 1 attempt. On Windows the error surfaced as `('Connection aborted.',
    ConnectionAbortedError)`, not `SSLError`; it is classified the same way.
  - **Cost:** a brief TLS glitch loses that push, and the dead letter shows it.
- **D11 (one subscription's unknown outcome stops the row): upheld.**
  - Retrying the row would re-send to the phone that may already have it, which the card
    forbids.
  - It is the same rule as partial acceptance, which is not retried either.
  - Probe PR6 ran it through the real stack: phone A's connection is refused and phone B stores
    the push, then drops. The row is dead after 1 attempt; B has 1 copy, and A none.
  - **Cost:** A loses that notification, visibly. Retry state per subscription would need a
    schema change and is not required by the card.
- **D12 (no notification `tag` in `sw.js` for now): upheld.** `sw.js:135-140` calls
  `showNotification` with no tag.
  - After F1 our own retries cannot duplicate a push; RR1–RR5 prove the tests guard that.
  - A tag merges a copy only while the first is still on screen, so it cannot make any retry
    safe.
  - A change to every phone's service worker, with no automated test of the push handler, is not
    justified by a duplicate nobody has observed.
  - The revisit trigger (guide case 10-C, or any report of a notification shown twice) is recorded.

### Independent adversarial examples (re-review)

These probes are written by the reviewer and are not in the repo. They run under the SA-005
hermetic boundary from the scratchpad, with a `conftest.py` that imports `tests.hermetic`. They
reuse the test module's loopback push service and fixtures. Expected results come from the
contract: at most once, and a retry only when the request cannot have reached the service.

| # | Fixture | Expected | Observed |
|---|---|---|---|
| PR1 | Real stack. The service reads the headers, then closes without reading the body, so nothing is stored | Unknown outcome (conservative), 0 copies, not re-sent | Dead after 1 attempt, 1 connection: `ConnectionError: ('Connection aborted.', ConnectionResetError(10054, …))`. D1's price: lost, visibly |
| PR2 | Real stack. An `https://` endpoint whose server accepts TCP and closes at once | Unknown outcome (D10) | Dead after 1 attempt, 1 connection |
| PR3 | A proxy that refuses: `ProxyError(MaxRetryError(reason=urllib3 ProxyError(…, NewConnectionError)))` | The push service was never reached, so retry | `_push_never_connected` is True |
| PR4 | A cyclic exception graph (`a.__cause__ = b`, `b.__cause__ = a`) | Terminates | False |
| PR5 | A `NewConnectionError` under 20 wrappers; and the real 3-node shape | Beyond the 16-node bound: not found, so unknown (conservative); real shape found | False; True |
| PR6 | Real stack. Phone A refused, phone B stores and drops (D11) | The row stops; B has 1 copy, A none; never re-sent | Dead after 1 attempt; A 0, B 1, B 1 connection |
| PR7 | Real stack. Phone A 201, phone B refused | Accepted 1/2; not retried | `delivered`, `webpush 1/2 subscriptions`; A 1, B 0 |

**Seven of seven behave as the contract requires.**

**The consumers traced again:**

- The only push senders are `outbox._send_row`, then `send_push_result`, and the inline
  `deliver()` path, which never retries.
- `deliver()` does not fall back to inline after a queue attempt: `enqueue` catches its own errors
  and returns `None`, so an outbox failure there yields "not delivered", not a second, inline send.
- `drain_once` writes an unknown outcome as `dead`, and nothing re-queues a dead row. `outbox.py`
  is byte-identical to the first review, which traced the report, retention and the route.

### Findings

| ID | Severity | Location | Evidence | Disposition |
|---|---|---|---|---|
| — | — | — | None found. F1 and F2 are fixed, and D10–D12 are upheld above. | — |

**Observations, not findings:**

- **Mutation RR8 was caught only incidentally.** RR8 dead-letters a row that has one accepted
  phone and one unknown outcome. The real-drop test caught it through its message assertion. No
  test pins the accepted-plus-unknown case directly. Either result avoids a duplicate, and only
  the row's reported status differs, so no change is needed.
- **The KT's §1 line said "awaits its fresh review", and §11 said "review pending".** The rework
  updated §10 and §12 but not these two. Both are corrected under "Review edits".

### Commands, environment, results

Environment: Windows 11, Python 3.13.11 (`.stockai`), pytest 9.0.3, pywebpush 2.3.0,
requests 2.33.1, urllib3 2.6.3, and the SA-005 hermetic boundary. The owner's checkout has `.env`,
and the boundary keeps it out.

| Check | Command | Result |
|---|---|---|
| Manifest | `python scripts/docs/kt_manifest.py verify docs/planning/PI-2026-09/evidence/SA-006-manifest.json` | 18 files, 0 mismatches, `b8273b2c…`, at the start and after the mutations |
| Diffs | Reviewer's script, described above | full `e01c4913…`; first review `79ec6b54…`; review-1 tree 17 of 17; rework `713e1675…` |
| Focused delivery tests | The receipt's 9-file command | **124 passed**, 0 failed (22 s) |
| Broad-except guard | `PYTHONPATH=".;src" python scripts/ci/check_broad_except.py` | OK (154 grandfathered) |
| KT check | `python scripts/docs/check_kt_docs.py` | errors `[]`; 26 pages; source `622c8437…` (the receipt's) |
| Reviewer mutations | A scratchpad script. It applies each mutation alone to `channels.py`, runs `test_delivery_channels.py`, `test_delivery_sa006_invariants.py` and `test_atlas_outbox.py` with `-x`, and restores the bytes, checked by SHA-256 (`c420cd6e…` before and after) | **8 of 8 caught.** RR1: any `ConnectionError` retried (the real-drop test). RR2: the walk skips `reason` (the table's refused case). RR3: only requests' `ConnectTimeout` (the real refused test). RR4: D11 inverted (the one-device drop test). RR5: an unknown outcome not permanent (the read-timeout test). RR6: TLS counted as never connected (the table's TLS case). RR7: the F2 prefix dropped (the recipient test). RR8: incidental, see above |
| Reviewer probes | `pytest -s --rootdir <scratch>/probe <scratch>/probe/test_rereview_probes.py` (with `PYTHONPATH=<repo>;<repo>\src`) | **7 passed** (6 s) |
| Full suite | `python -m pytest -q -p no:cacheprovider -rfEs tests` | **3837 passed, 12 skipped, 0 failed** in 7 min 12 s (20:29–20:37 IST), the same count as the receipt. `data/`, `logs/` and `outputs/`: 800 files before and after, 0 changed, added or removed (size and mtime). It ran after the mutations had finished and the source was restored |

**Not exercised:**

- a live SMTP relay, the live Resend API, or a real push service. Resend's idempotency comes from
  its documentation;
- a real connect timeout or DNS failure through the stack, because the hermetic boundary refuses
  non-loopback connections and lookups. The exception-type table covers them, built from the
  library's own classes;
- Linux or Python 3.11. CI has never run; it needs the held push;
- a production outbox read. The owner probe `analysis_data/sa006/prod_probe_outbox.py` has not
  been run.

### Review edits (documentation only)

These replace "re-review pending" and similar wording with the accepted state:

- the KT's §1 row, the §10 heading, the §11 Operations row and the §12 summary;
- the ARCHITECTURE row;
- guide cases 10-B, 10-C, 10-E and 10-F.

The PDF is rebuilt. `build_kt_pdf.py`: 26 pages, source `38ddf518…`, PDF blob `98c0dc42…`; `check_kt_docs.py` errors `[]`. Nothing else changed: the code, tests and configuration
bytes are as reviewed. So `kt_manifest.py verify SA-006-manifest.json` now mismatches exactly
these four files: the KT, the PDF, ARCHITECTURE and the guide.

### Acceptance checklist

| Criterion | Verdict |
|---|---|
| Transport acceptance and user delivery are reported separately | **Met** (unchanged since the first review) |
| Transient errors retry within policy; permanent auth or config errors stop with actionable diagnostics | **Met.** A push is retried only when its connection was never made |
| No duplicate notification is created during retry or replay | **Met.** Push: F1 fixed and tested through the real stack (1 copy). SMTP: unchanged since the first review. Resend: by its documented `Idempotency-Key`. A stopped process: dead-lettered, not re-sent |
| Historical dead letters are retained | **Met** (`outbox.py` and `retention.py` unchanged since the first review) |
| Evidence: timeout, rejection, retry-after, success, crash after acceptance | **Met.** Push crash-after-acceptance is now covered by a real dropped connection, not only `ReadTimeout` |
| Evidence: attachments, recipient isolation, redacted logs, disabled channel | **Met.** The report and stored reasons carry no user id (F2) |
| Delivery evidence re-established without `.env` | **Met** through the SA-005 boundary |
| Read-only diagnosis; external configuration prepared, not requested | **Met** |
| Documentation updated | **Met**, with the status edits above |
| Hard review: provider idempotency limitations stated honestly | **Met.** KT §10 and the receipt claim at most once, except where the provider deduplicates, and never exactly-once receipt |

### Decision and follow-up state

- **Accepted.** SA-006 is `done`, for review input `b8273b2c…` plus the documentation edits above.
- **`production_verification`: `pending_deployment`.** It needs the owner's commit and push (the
  hold stands; use a job-free window, 00:10–06:20 IST).
- **After the deploy (read-only):**
  - `GET /delivery/outbox` with the machine key, or the owner probe. Historical dead letters
    should be listed with masked reasons, and new accepted rows should carry `accepted_by`.
  - Then human cases 10-B, 10-C, 10-E and 10-F.
  - A real test email or push, or re-sending a dead letter, needs the owner's explicit messaging
    authorization.
- **Follow-ups:**
  - the routed notes stand: SA-011 (dead-letter alerting), SA-031 (`run_kt_checks.py` and the
    Windows rename flake), SA-007 (the backup email), SA-042 (the heartbeat and Learning Evidence
    email);
  - D12 revisit trigger: guide case 10-C;
  - no new follow-up.
- **Next ready story: [SA-007](../stories/SA-007.md)** (make backups recoverable; P1, sprint 1, no
  dependencies). It starts in a new conversation; this review did not start it.
- **Not committed, pushed, deployed or sent** by this review.

## First review: CHANGES REQUESTED (2026-09-28, fresh session)

- **Story:** [SA-006](../stories/SA-006.md). Implementation receipt:
  [SA-006-implementation.md](SA-006-implementation.md).
- **Review context:** a **fresh-session review** in a new conversation on 2026-09-28, about
  15:08–15:35 IST. It is not the implementing conversation, and it did not read that chat.
  No SA-039 production check was due: P1 is today at 17:00 IST. All 15 peer sessions were idle.
- **Reviewed input:**
  - `kt_manifest.py verify SA-006-manifest.json` on the worktree: 18 files, **0 mismatches**.
    The review input SHA-256 is **`516d2aec6ab365c08295e69fad0681f921edbba06810c810a73c870ceb14bb0d`**,
    which matches STATE. The same check at the end of the review also gave 0 mismatches.
  - The reviewer's own script rebuilt the diff. It takes every manifest path except the PDF, sorted;
    `git diff 9e65c7a` for a tracked path, `--no-index /dev/null` for a new one. Result:
    **`79ec6b542beed36baa42474b8c473ca09ea69585b70cd3b1154f0a3fa5afc146`**, 135,768 bytes over
    17 text files, the same as the receipt.
  - **Completeness:** every modified or untracked file is either in the manifest or is one of the
    four bookkeeping files the receipt excludes (STATE, HANDOFF, the receipt, the manifest).
  - **Baseline:** HEAD `9e65c7a` (local `main`, 3 ahead of `origin/main`; the push is on hold).
  - This input is preserved as [SA-006-manifest-review1.json](SA-006-manifest-review1.json), so
    the rework can regenerate `SA-006-manifest.json`.
- **Verdict: `changes_requested`.**
  - Most of the contract holds, and the tests catch its main defects. The implementer's 16
    mutations and this review's 10 were all caught. They include the `590bc9f` owner fallback.
  - **But a push can reach the phone twice (F1, medium).** In that case the push service received
    the push and then the connection dropped before it answered. The drainer calls this transient
    and sends again. The card's criterion "no duplicate notification is created during retry" is
    therefore not met. The receipt, the KT and the test module's invariant I1 all claim otherwise.
  - F2 (low) is a one-line fix with its test. It goes in the same rework.

### Contract checked

- **Every transport returns a `SendResult`.** `accepted` means the transport accepted the message,
  never that someone received it. The owner's report shows the stored `delivered` as `accepted`,
  with `user_receipt: "not observable"`. **Holds** (RM6 was caught).
- **Transient failures retry on the backoff or the provider's `Retry-After`, capped at 6 h.**
  After 3 attempts the row dead-letters as "retries exhausted". **Holds** (RM9 was caught).
- **Permanent failures dead-letter after one attempt, with a hint.** These are auth,
  configuration, a disabled channel, a rejected recipient and a missing address. **Holds** (RM2 was
  caught). The hints name the setting to check (SMTP 535 → `SMTP_USER`/`SMTP_PASSWORD`,
  Resend 401/403 → `RESEND_API_KEY`/`RESEND_FROM`).
- **An unknown outcome dead-letters and is never re-sent.**
  - **Holds for SMTP.** A drop inside `sendmail` is caught by RM3. A drop at MAIL or RCPT is
    also treated as unknown (probe R3). That is conservative, and it matches D1.
  - **Holds for a process killed mid-send.** Rows left `sending` for more than 60 minutes are
    dead-lettered (RM5 was caught).
  - **Holds for Resend,** through the per-row `Idempotency-Key`: RM7 was caught. It relies on
    Resend's documentation and was not tried against the live API.
  - **Does not hold for web push (F1).**
- **Recipient isolation.** A real account never falls back to `DELIVERY_EMAIL_TO`. **Holds.**
  - RM1 was caught. It restores the `590bc9f` defect, where a failed lookup fell back to the
    owner.
  - The inline path follows the same rule (`test_inline_deliver_mails_the_account_not_the_owner`).
  - D4 was checked: the default id is `primary` (`src/backend/shared/config/settings/base.py:882`),
    which is not a real account.
- **Redaction.** Addresses, URL paths and the configured secrets are masked in reasons, logs and
  the report. **Holds** (RM4 was caught). But the report can carry a user id (F2).
- **History.** Dead letters are kept for 180 days, and their payload is cleared at 30 days.
  Nothing re-queues a dead row. **Holds** (RM8 was caught).
- **Migration.** `accepted_by` and `claimed_at` are added to an existing table without changing
  its rows. **Holds** (test on a pre-SA-006 table).
- **Authorization.** `GET /delivery/outbox` uses `require_owner`: without credentials it returns
  401, and with the machine key 200 (the test). Every other caller of the changed functions was
  checked with a grep. Only `outbox.py`, `deliver()` and the tests use `SendResult` and
  `Recipient`. `send_email` and `send_push` keep their bool and int returns.
- **Scheduler change.** `json_path` is assigned (line 1312) before the new warning uses it.

### Independent adversarial examples

The reviewer wrote these. They run under the repo's SA-005 hermetic boundary, from the scratchpad,
with a `conftest.py` that imports `tests.hermetic`. None is in the repo.

| # | Fixture | Expected (by the contract) | Observed |
|---|---|---|---|
| R1 | Real pywebpush 2.3.0, requests 2.33.1 and urllib3 2.6.3, with a real VAPID key and subscription keys. The push service is a loopback HTTP server. It reads the whole POST, counts it as stored, then closes the connection with no response on the first call, and answers 201 after that. One outbox push row is drained at 0, 1, 6 and 36 minutes. | An unknown outcome: dead after one attempt, with 1 copy stored | Attempt 1 returns `transient: ConnectionError: ('Connection aborted.', RemoteDisconnected('Remote end closed connection without response'))`. The drainer retries at 1 minute and the service accepts. **The service stored 2 copies**, and the row is `delivered` with `attempts` 2 (**F1**) |
| R2 | An email row for `u_9f3a1c2e`, which has an atlas row but no `users.db` account | A dead letter. The report carries no user id (per the report's docstring, the route comment and KT §10) | Dead after 1 attempt, which is correct. The report's reason is `no email on file for user 'u_9f3a1c2e'` (**F2**) |
| R3 | SMTP: `sendmail` raises `SMTPServerDisconnected` before DATA | An unknown outcome (D1, conservative) | `unknown outcome: …`, permanent. As designed |
| A1 | The receipt's own example, traced through the code: `u_b`'s lookup raises `OperationalError`, then works | Transient, then `u_b`'s own address, once | As expected (`resolve_recipient` lines 218–228, then drain). RM1 proves the test would catch the old fallback |
| A2 | `requests.post` to a closed loopback port | For the F1 fix: the exception type shows nothing was sent | `ConnectionError(MaxRetryError(reason=NewConnectionError))`. R1's drop is `ConnectionError(ProtocolError('Connection aborted.', …))`. The two can be told apart by type, with no message-text matching (D7) |

**The consumers traced:**

- `_send_row` → `drain_once` writes `status`, `attempts`, `last_error`, `accepted_by` and
  `claimed_at`;
- `outbox_report` → `GET /delivery/outbox` (owner only);
- `retention._prune_outbox` (C9);
- nothing re-sends or re-queues a dead row;
- the `drain_once` summary is read by no one but the loop, which ignores it.

**Why the suite cannot see F1.** `FakePushService` in the new test module fakes only one kind of
"accepted, then no answer": a `ReadTimeout`. The code checks exactly that class name
(`channels.py:543`). A connection that drops after the request was sent is the same unknown
outcome, but the code puts it on the retry list (`channels.py:545-546`).

### Findings

| ID | Severity | Location | Trigger → observed / expected | Impact | Disposition |
|---|---|---|---|---|---|
| F1 | **Medium**, confirmed (R1); **unmet acceptance criterion** | `core/delivery/channels.py:541-546` (`send_push_result`: only `ReadTimeout` counts as unknown; any other non-HTTP exception goes to `retry`), acted on by `core/delivery/outbox.py:277-291` | The push service stores the push, then the connection drops before its 201. Observed: transient, retried, **2 copies stored**, row `delivered`. Expected: unknown outcome, dead-lettered, 1 copy. The service worker shows each push with no `tag` (`src/frontend/prototypes/sw.js:135-140`), so the phone shows two notifications. The same happens when one subscription drops after storing, another returns 5xx, and none accepts: the whole row is retried. | A duplicate brief or alert on a user's device. There is no misrouting or loss. It is unlikely: pywebpush opens a fresh connection for each call, so a stale keep-alive reset cannot cause it; it needs a drop between the request and the response. It contradicts the card's "no duplicate notification … during retry", the receipt's classification table ("network error **before anything was sent**" → transient), I1 ("whatever the transport does (… dropped connections …)") and KT §10 "At most once". | **Required change (rework).** Count a push transport exception as transient only when it was raised while connecting, so the request cannot have left: `requests.exceptions.ConnectTimeout`, or a `ConnectionError` wrapping urllib3's `NewConnectionError` or `NameResolutionError` (A2). The implementer decides TLS handshake errors. Count every other exception as an unknown outcome: read timeouts, `('Connection aborted.', …)`, `ChunkedEncodingError` and so on. Classify by type, not by message text (D7). Add boundary tests: a fake push service that stores, then raises `requests.exceptions.ConnectionError(urllib3.exceptions.ProtocolError('Connection aborted.', RemoteDisconnected(...)))`, gives 1 copy and a dead letter; a refused connect is still retried. Correct the receipt's table, the KT §10 "At most once" bullet and the `send_push_result` docstring. **Optional, the owner's choice (new frontend scope):** a stable per-row notification `tag` would collapse duplicates on the device. |
| F2 | Low, confirmed (R2) | `core/delivery/channels.py:233` (the reason text). It is persisted at `outbox.py:280-281`, returned by `outbox_report` (`outbox.py:341-344`) and logged at `outbox.py:283` | An email row for an account with no address. Observed: the report's reason is `no email on file for user 'u_9f3a1c2e'`. Expected: no user id, as the report's docstring (`outbox.py:315`), the route comment (`delivery_api.py:107-108`) and KT §10 state. | Only the owner sees the report, and the id is internal and random (`u_` plus 8 hex digits). This is a contract and documentation mismatch, not a leak to a third party. The I5 test checks that `u_a` is absent, but it never triggers this reason. User ids in log lines are pre-existing, and I5 does not claim otherwise. | **Fix in the same rework:** drop the id from the reason, and prefix it `permanent:` like the others. The row id already identifies it. Add this case to the I5 test. |

**Considered and accepted (not findings):**

- **D1 at most once.** A message dropped at MAIL or RCPT is lost, visibly (R3). This is the
  card's stated trade-off: no duplicates.
- **D2** (the 60-minute stale window) and **D3** (the stored `delivered`, reported as `accepted`).
  The worst case for a 50-subscription push is about 50 × (20 s connect + 20 s read), about
  33 minutes, which is less than 60.
- **D4, D5 and D7–D9.** D5 is dead letters kept for 180 days. Note that production's C9 has
  already deleted dead letters older than 30 days under the old code; the rest are kept once this
  deploys.
- **D6: a 12-hour push TTL.** This is a product decision taken from the library's defaults, and
  the KT marks it as unmeasured. Human case 10-F is the check.
- **Partial push acceptance is not retried.** No accepting device gets a second copy. This is
  documented.
- **The KT, ARCHITECTURE and guide status lines still say "review pending".** The review did not
  edit them, so the reviewed input stays intact. The rework updates them along with F1's wording.

### Commands, environment, results

Environment: Windows 11, Python 3.13.11 (`.stockai`), pytest 9.0.3, pywebpush 2.3.0,
requests 2.33.1, urllib3 2.6.3, and the SA-005 hermetic boundary. The owner's checkout has `.env`,
and the boundary keeps it out.

| Check | Command | Result |
|---|---|---|
| Manifest | `python scripts/docs/kt_manifest.py verify docs/planning/PI-2026-09/evidence/SA-006-manifest.json` | 18 files, 0 mismatches, `516d2aec…`, at the start and again at the end |
| Diff digest | Reviewer's script (described above) | `79ec6b54…`, 135,768 bytes, 17 text files |
| Focused delivery tests | The receipt's command (9 files) | **112 passed**, 0 failed (27 s) |
| Broad-except guard | `PYTHONPATH=".;src" python scripts/ci/check_broad_except.py` | OK (154 grandfathered) |
| KT check | `python scripts/docs/check_kt_docs.py` | errors `[]`. The PDF matches its source, and the declared revision is `48143ed` |
| Reviewer mutations | A scratchpad script. It applies each mutation alone, runs the 4 delivery test files with `-x`, and restores the bytes, checked by SHA-256 | **10 of 10 caught.** RM1: the `590bc9f` fallback. RM2: permanence ignored. RM3: an SMTP send-phase drop retried. RM4: addresses not redacted. RM5: stale rows re-queued. RM6: the report says `delivered`. RM7: the idempotency key changes on each attempt. RM8: retention deletes dead letters at 30 days. RM9: Retry-After uncapped. RM10: TTL 0 |
| Reviewer probes | `pytest -s --rootdir <scratch>/probe <scratch>/probe/test_review_probes.py` (with `PYTHONPATH=<repo>;<repo>\src`) | R3 passed. **R1 and R2 fail as described above (F1, F2)** |
| Full suite | `python -m pytest -q -p no:cacheprovider -rfEs tests` | **3825 passed, 12 skipped, 0 failed** in 11 min 26 s, as the receipt says. `data/`, `logs/` and `outputs/` were unchanged: 800 files before and after, 0 changed, added or removed (size and mtime) |

**Not exercised:**

- a live SMTP relay, the live Resend API, or a real push service. Resend's idempotency comes from
  its documentation;
- Linux or Python 3.11. CI has never run; it needs the held push;
- a real two-container deploy overlap;
- a production outbox read. The owner probe `analysis_data/sa006/prod_probe_outbox.py` has not
  been run.

### Documentation

KT §10 describes the contract accurately, except for two things. Its "At most once" bullet
promises that an unknown push outcome is never re-sent (F1). Its "Visibility" bullet says the
report carries no user id (F2). The testing guide adds three cases: 10-B (`accepted`), 10-C (one
transient and one permanent failure) and 10-F (TTL). It also updates 10-E, which is still a
production check. CODEBASE.md and config.yaml agree with the code. The PDF matches its source
(`check_kt_docs` errors `[]`). The rework must correct the F1 and F2 wording and the status lines,
then rebuild the PDF.

### Acceptance checklist

| Criterion | Verdict |
|---|---|
| Transport acceptance and user delivery are reported separately | **Met** |
| Transient errors retry within policy; permanent auth or config errors stop with actionable diagnostics | **Met** |
| No duplicate notification is created during retry or replay | **Not met for web push** (F1). Met for SMTP, for Resend (by its documentation) and for a stopped process |
| Historical dead letters are retained | **Met** |
| Evidence: timeout, rejection, retry-after, success, crash after acceptance | **Met**, except that the push crash-after-acceptance fixture covers only `ReadTimeout` (F1) |
| Evidence: attachments, recipient isolation, redacted logs, disabled channel | **Met**, but the report can carry a user id (F2) |
| Delivery evidence re-established without `.env` (routed from `590bc9f`) | **Met** through the SA-005 boundary |
| Read-only diagnosis; external configuration prepared, not requested | **Met.** Transport selection is unchanged, and the Resend switch has a rollback |
| Documentation updated | **Met**, with the F1 and F2 wording to correct |

### Decision and follow-up state

- **`changes_requested`.** SA-006 returns to implementation. STATE: `status: changes_requested`,
  `next_phase: implementation`. The rework fixes F1 and F2, then regenerates the manifest and
  records a rework diff. A **fresh re-review in a new conversation** signs off the new revision.
- **Production verification** stays `not_started`. Nothing was committed, pushed, deployed or sent.
- **No other story is started** by this review.
