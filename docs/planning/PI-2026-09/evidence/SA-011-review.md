# SA-011 review receipt — durable errors as a deterministic operations backlog

## Re-review of rework 2: ACCEPTED (2026-10-12, fresh session)

- **Story:** [SA-011](../stories/SA-011.md). Implementation receipt:
  [SA-011-implementation.md](SA-011-implementation.md), section "Rework 2".
- **Review context:** a **fresh-session re-review** in a new conversation opened with "continue"
  on 2026-10-12, from about 08:06 IST. It is none of the implementing conversations and neither
  earlier reviewing one, and it did not read their chats. All 35 listed peer sessions were idle,
  at the start and before these records were written.
- **Reviewed input:**
  - `kt_manifest.py verify SA-011-manifest.json` on the worktree: 13 files, **0 mismatches**,
    review input SHA-256 **`0323f2a893f76e18b09058fbfb2ddeea51e1ea2205afa93ce7f8efce704d59e1`**,
    which matches STATE. The reviewer's own `git hash-object` of the 13 paths gives the same 13
    blobs. The same check at the end of the review: 0 mismatches, the same digest.
  - **Rework diff, rebuilt independently.** The reviewer's script
    (`analysis_data/sa011/rereview2/rr2_diff.py`) hashed the snapshot of the re-review's input
    (`analysis_data/sa011/rework2/base/`) against the blob ids in
    [SA-011-manifest-review2.json](SA-011-manifest-review2.json): 13 of 13 match. Eight paths
    changed (seven text files and the PDF), as the receipt says. The reviewer's own diff has
    byte-identical hunks to the implementer's (only the header paths are spelled differently),
    and it was read in full. The implementer's recipe reproduces **`ad35960c…`** (36,162 bytes).
  - **Cumulative diff** `c8965571…` (145,148 bytes, 12 files) reproduced by the first reviewer's
    `rv_digest.py`. Its `rv.diff` was restored afterwards (`b669cf36…`).
  - **Completeness.** The worktree held the same 40 modified and untracked entries at the start
    and the end. Nothing outside the manifest is part of the story. **Baseline:** HEAD `b9cc851`.
- **Verdict: `accepted`** for this revision, the uncommitted working tree on `b9cc851` with
  input `0323f2a8`.
  - **RR-M1 is fixed.** A fix time without a UTC offset is refused, in every notation the
    reviewer tried, and nothing is written. With an offset, the mark is refused when a recorded
    recurrence contradicts it. That holds through the real app, in both read orders.
  - **The optional RR-I1 and RR-I4 hold.** Rows the real log writer stamps within the same
    second as the fix get the same outcome in both read orders. The digest and the refusals
    show IST.
  - **No critical, high, medium or low finding.** Three infos are below. One is a test gap,
    routed to SA-031.

### In one example (RR-M1, now)

1. A fix for the malformed miss-factor warning takes effect at 08:00 IST. The warning is back
   at 10:00 IST, and the registry has read that row.
2. The owner types the deploy time as the app shows it, without an offset. The reviewer tried 9
   notations: `2026-10-05T08:00`, a space for `T`, the hour alone, `20261005T0800`, an ISO
   week date, a fraction of a second, padding spaces, a lower-case `t`, and the date alone.
   - **Each gets 422:** "has no UTC offset, so it could be IST or UTC: give
     2026-10-05T08:00+05:30 for IST or 2026-10-05T08:00Z for UTC". For the date alone, the form
     shown is `…T00:00+05:30`.
   - **Nothing is written:** the task, assignee and note sent in the same request are not
     stored either.
3. With an offset (`+05:30`, `+0530`, `Z` or `+00:00`), the mark is refused: "last seen at
   2026-10-05T10:00:00+05:30, after fixed_at 2026-10-05T08:00:00+05:30 … that fix did not
   hold". A lower-case `z` is refused as "not an ISO time"; it is never misread.
4. A later fix at 11:00 IST, after the recurrence, is accepted. With no recurrence since and the
   archive alive 9 days on, it reads `verified`.

**Reproduced through the real app.** The trace is
`analysis_data/sa011/rereview2/test_rr2_trace.py::test_every_bare_notation_is_refused_with_the_form_and_writes_nothing`.
It uses `server.app`, a real signup, the real auth dependency and log_store's real schema. The
fix was 9 days ago and the recurrence 2 hours later. The previous re-reviewer's
`test_rr_trace.py` passes unchanged (2 of 2). On the re-reviewed module, swapped in memory, its
naive-time case and this trace fail, as they should.

### The rework's changes, checked

| Finding | What the reviewer checked | Result |
|---|---|---|
| RR-M1 | The 9 bare notations and 5 offset forms above, through HTTP. The previous re-reviewer's trace and probe A1, in both read orders. `prod_errors.py --help`, the API field, KT section 10 and guide 12-J all state the rule | **Fixed** |
| RR-I1 | The real `SQLiteLogHandler` stamps rows with microseconds. (A) A default-now mark, then the warning 2.7 ms later in the same second: reopened as `regressed`. (B) The warning read first, then a mark from 78 µs before it: 422, naming the row's exact IST time. (C) A mark with an explicit sub-second time, then the warning: reopened. Stored times keep their precision (`last_seen` equals the row's `ts`) | **Holds** |
| RR-I1, side effects | 20,000 random stored times with mixed precision (half whole seconds) sort and take their `max` in time order, because `+` sorts before `.`. That is what the cursor's `max` and retention's sort rely on. Through HTTP, out-of-order row ids give coverage = the newest row, `first_seen` = the oldest | **Holds** |
| RR-I4 | The digest through HTTP, for rows at 20:00 and 21:00:07.25 UTC (the next IST day): `first <IST date>, last <IST date> 02:30 IST`, `status fixed since … 03:00 IST`. It truncates to the minute (02:30:59.9 → 02:30). The JSON API keeps UTC with `+00:00`. A refusal's IST time pasted back as `fixed_at` is the same instant (2,000 random times) | **Holds** |

**Tests fail on the re-reviewed revision.** The reviewer's own swap plugin
(`rr2_swap_plugin.py`, `RR2_SWAP=base`) loads the re-review's `error_backlog.py` in memory.
**11 story tests fail and 100 pass**: the same 11 the receipt lists. All 4 tests of the
reviewer's trace fail there too. Expected values are literals or plain arithmetic (UTC plus
5 h 30 min), not the module's helpers.

**The reviewer's own mutants** (one line each, in memory; no repo file written):

| Mutant | Story file (111) | Caught by |
|---|---|---|
| X4 a bare time read as IST | 4 fail | story, own trace |
| X5 a date alone read as midnight UTC | 2 fail | story, own trace |
| X6 a bare time with seconds read as UTC | 1 fails | story, both re-review traces |
| X9 the digest's last seen as a UTC minute labelled IST | 1 fails | story, own trace |
| X10 the digest's first seen as the UTC date | 1 fails | story, own trace |
| X12 `last_seen` stored at whole seconds | 3 fail | story, own trace |
| X1 the fix time truncated to whole seconds at triage | **all pass** | own trace (A, C), the first reviewer's lifecycle trace, probe P3 |
| X2 an occurrence exactly at the fix time counts as after it | **all pass** | probe P3 only |
| X3 triage refuses a fix time equal to `last_seen` | **all pass** | probe P3 only |

The code is correct for X1 to X3 today, as the trace and probe show. The story file's gap is
RR2-I1.

### Independent adversarial examples

| # | Example | Expected (contract) | Observed |
|---|---|---|---|
| B1 | 9 bare notations of a fix time, a recurrence 2 h later, with task, assignee and note | 422 with the form; nothing written | As expected |
| B2 | The same time with `+05:30`, `+0530`, `Z`, `+00:00`; and a lower-case `z` | Refused, naming last seen in IST; never misread | Refused; `z` refused as not ISO |
| B3 | A recurrence in the same second as the fix, real log writer, both read orders | Never `fixed`; the same in both orders | Read first: 422. Marked first: reopened |
| B4 | An occurrence exactly at the fix time, to the microsecond, both orders | The same outcome in both | `fixed` in both (implementer's I13) |
| B5 | Digest rows around IST midnight; a fixed issue | IST dates and minutes; the fix time shown | As expected |
| B6 | Mixed-precision stored times; out-of-order row ids | Coverage, sort and first/last in time order | As expected |

### Findings

| ID | Severity | Location | Evidence | Disposition |
|---|---|---|---|---|
| RR2-I1 | Info (test gap) | `tests/unit/ops/test_error_backlog_sa011.py:518-544` (the same-second tests use whole-second fix times and never an occurrence at exactly the fix time) | Mutants X1, X2 and X3 pass all 111 story tests. X1 in production would refuse a default-now mark made in the same second as the last warning read, and reopen on a row logged just before the mark. That direction is conservative: never a false `verified`. X2 and X3 differ only at one microsecond | **Routed to [SA-031](../stories/SA-031.md).** Add two story tests: a default-now mark after a same-second, fractional `last_seen` is accepted; an occurrence exactly at the fix time leaves the issue `fixed` in both read orders. Use `rr2_probe.py` P3 and `test_rr2_trace.py` (A, C) as the fixtures |
| RR2-I2 | Info | `core/ops/error_backlog.py:821` | An explicit offset is taken as given: `+05` parses as +05:00, 30 minutes from IST; `+0530` is accepted (the implementer's I12) | None. The offset is explicit, and every message and document shows `+05:30` |
| RR2-I3 | Info | `core/ops/error_backlog.py:826` | A bare time with a fraction is refused with a form that drops it (`08:00:15.5` → `08:00:15+05:30`), half a second earlier. Copying it errs toward refusal | None |

The re-review's RR-I2 (an acknowledged monthly burst needs attention) and RR-I3 (a bare,
all-letter `Basic` credential stays) stand as agreed. The implementer's I11–I13 are agreed;
probe P3 confirms I13. I7, registering the watchdog entry, stays the owner's decision at rollout.

### Commands, environment, results

Windows 11, Python 3.13.11, pytest 9.0.3, in the `.stockai` venv, through `tests/hermetic.py`
(the reviewer's `conftest.py` imports the same hooks).

| Check | Command | Result |
|---|---|---|
| Input | `python scripts/docs/kt_manifest.py verify docs/planning/PI-2026-09/evidence/SA-011-manifest.json`; `git hash-object` per path | 13 files, 0 mismatches, `0323f2a8…`, at the start and the end |
| Rework diff | `python analysis_data/sa011/rereview2/rr2_diff.py`; `python analysis_data/sa011/rework2/rw2_diff_digest.py` | Snapshot 13/13 = review2 blobs; 8 paths changed; the same hunks; `ad35960c…`, 36,162 bytes |
| Cumulative diff | `python analysis_data/sa011/review/rv_digest.py` (its `rv.diff` restored) | `c8965571…`, 145,148 bytes, 12 files |
| Story tests, all suites, base and mutants | `python analysis_data/sa011/rereview2/rr2_run.py none base X1 … X12` (each runs the story file and the three trace files with `-p rr2_swap_plugin`) | Unswapped: story 111, own trace 4, `test_rv_trace.py` 3, `test_rr_trace.py` 2, all passed. Base: 11 story tests fail; mutants as tabled |
| Own trace | `python -m pytest analysis_data/sa011/rereview2/test_rr2_trace.py -q -s -p no:cacheprovider --rootdir=analysis_data/sa011/rereview2` | 4 passed |
| Own probe | `python analysis_data/sa011/rereview2/rr2_probe.py` | 6 of 6; P3 fails under X1, X2 and X3 |
| Previous probe | `python analysis_data/sa011/rereview1/rr_probe.py` | 23 of 24; the failure is RR-I3, agreed |
| KT and PDF | `check_kt_docs.py` (with `PYTHONPATH=analysis_data/kt_docs_deps`) | errors `[]`; PDF 40 pages, source `b4445b0a…` = the manifest's KT |
| Full suite | `python -u -m pytest -q -p no:cacheprovider -o console_output_style=count` | **4429 passed, 12 skipped, 0 failed** (5 min 54 s, about 08:24–08:30 IST) |
| Runtime data | `python analysis_data/sa011/review/rv_tree.py`, before and after the full suite | 798 files, `d9fa2376…` before and after (paths and bytes): unchanged |

**Not exercised:** production (nothing was read); two real uvicorn processes (the hermetic
guard forbids subprocesses); a browser (no UI in this story).

### Documentation

KT section 10 (lifecycle and access bullets), guide 12-J, the CODEBASE row, the API field's
description and the script's `--fixed-at` help describe what the trace observed: the offset
rule and its form, IST in refusals and in the digest, and the same outcome within one second.
ARCHITECTURE and PRODUCT_MAP summarise the refusals without contradicting them. The PDF matches
its source. **This review edited no living document.** KT section 12's table still shows
SA-011 as `Open`, while STATE now says `done`. `check_kt_docs` does not compare the two.
Changing the row here would change reviewed bytes, so the reviewer decided to leave it. **At
commit:** set the row to `Done` together with the KT header's revision bump (as after FIX-005's
commit), and rebuild the PDF.

### Acceptance checklist

| Criterion | Result |
|---|---|
| INFO on Railway stderr is not an error from its envelope alone | Met (unchanged since the first review) |
| Identical causes group without leaking payloads or secrets | Met (RR-I3 is an agreed residual) |
| Acknowledged issues can regress | Met (35 quiet days, decided in rework 1) |
| Pending verification reconciles against measured evidence | **Met**, with or without an offset given (one without is refused), in both read orders, within one second |
| Tests: timestamps/ids, tracebacks, floods, severity, tenant authorization | Met (RR2-I1 is a test gap at equality edges, routed) |
| Deterministic digest; retention without losing active issues | Met; mixed-precision stored times keep time order |
| Hard review: no LLM; usable to assign and close a real defect | Met |
| Rollout: raw capture intact, no automatic message | Met |
| Documentation | Met |

### Decision and follow-up state

- **`accepted`.** SA-011 is `done` for the reviewed revision: the uncommitted working tree on
  `b9cc851`, input `0323f2a8`. STATE: `active_task: null`, `next_task: FIX-007`.
- **Nothing was committed, pushed, deployed, configured or sent, and no production state was
  read.** SA-011's files are still uncommitted, together with the peer's product-results docs.
  Commit and deploy only on the owner's word, in a job-free window. With the commit, set KT
  section 12's SA-011 row to `Done`, bump the KT header's revision and rebuild the PDF.
- **Production verification: `pending_deployment`.** After a deploy, run the read-only check in
  the implementation receipt's "Rollout" section. Watch RR-I2 after rollout. I7, registering the
  watchdog entry, is the owner's decision.
- **Routed:** RR2-I1 → [SA-031](../stories/SA-031.md).
- **Next:** FIX-007, in a new conversation ("continue"). It was not started here.

## Re-review of rework 1: CHANGES REQUESTED (2026-10-12, fresh session)

- **Story:** [SA-011](../stories/SA-011.md). Implementation receipt:
  [SA-011-implementation.md](SA-011-implementation.md), section "Rework 1".
- **Review context:** a **fresh-session re-review** in a new conversation opened with "continue"
  on 2026-10-12, from about 07:07 IST. It is neither the implementing conversation nor the
  first reviewing one, and it did not read either chat. All 33 listed peer sessions were idle.
- **Reviewed input:**
  - `kt_manifest.py verify SA-011-manifest.json` on the worktree: 13 files, **0 mismatches**,
    review input SHA-256 **`158479b48f00ac51f7f2227b69b15b2e2a061a7d135312a92431d311337ca4a3`**,
    which matches STATE. The reviewer's own `git hash-object` of the 13 paths gives the same 13
    blobs.
  - **Rework diff, rebuilt independently.** The reviewer's script
    (`analysis_data/sa011/rereview1/rr_diff.py`) hashed the snapshot of the first review's input
    (`analysis_data/sa011/rework1/base/`) against the blob ids in
    [SA-011-manifest-review1.json](SA-011-manifest-review1.json): 13 of 13 match. Ten paths
    changed since then (nine text files and the PDF), as the receipt says. That diff was read in
    full.
  - The implementer's recipes reproduce the recorded digests: rework diff
    **`13164cff…`** (46,098 bytes) and cumulative diff **`36b27f3a…`** (133,594 bytes, by the
    first reviewer's `rv_digest.py`; its own `rv.diff` was restored afterwards, `b669cf36…`).
  - **Completeness.** The modified and untracked files are the first review's set plus the
    rework's receipts and manifests. `docs/README.md` still carries only the owner's `railway
    ssh` probe line, which is not SA-011's.
  - **Baseline:** HEAD `b9cc851`.
  - This input is preserved as [SA-011-manifest-review2.json](SA-011-manifest-review2.json), a
    byte copy, so rework 2 can regenerate `SA-011-manifest.json`.
- **Verdict: `changes_requested`.**
  - **Every finding of the first review is fixed as recorded**, and the reworked behaviour holds
    on the reviewer's own examples (table below).
  - **But a fix can still read `verified` after a measured recurrence (RR-M1, medium).** This
    happens when `fixed_at` is given without a UTC offset, for example the deploy time as the
    app shows it, in IST. The server reads such a time as UTC, 5 hours 30 minutes later than
    meant. A recurrence in that gap then counts as "before the fix", whatever the read order.
    This is the outcome M1 was about, and the criterion is the same: a pending verification
    must reconcile against measured evidence. Nothing in the API, the script or the docs asks
    for an offset.
  - The fix is small and is cheapest before the first deploy.

### In one example (RR-M1)

1. A fix for the malformed miss-factor warning is deployed on Monday 5 Oct at 08:00 IST.
2. The warning comes back at 10:00 IST: the fix did not hold. The registry reads that row.
3. On Wednesday the owner runs `prod_errors.py --triage <fp> --status fixed --fixed-at
   2026-10-05T08:00`. That is the deploy time as the digest's IST clock shows it.
4. The server reads `08:00` as UTC, which is 13:30 IST. The 10:00 recurrence is now before
   the fix.
   - **The mark is accepted.** A week later the issue reads **`fixed, verified`**, leaves the
     default list, and the digest says "fixed, verified".
   - Had the registry not read the 10:00 row first, the result is the same: the row is folded
     in as an occurrence before the fix.
   - With `2026-10-05T08:00+05:30` the same mark is refused, naming the last-seen time, as it
     should be.
   - Only a recurrence within 5.5 hours of the real fix is hidden. The usual deploy window is
     00:10–06:20 IST, so that gap can cover the morning's scheduled jobs.

**Reproduced through the real app.** The trace is
`analysis_data/sa011/rereview1/test_rr_trace.py::test_naive_ist_fix_time_with_a_recorded_recurrence`.
It uses `server.app`, a real signup, the real auth dependency and log_store's real schema. The
fix was 9 days ago and the recurrence 2 hours later. The triage response returns `200`,
`status: fixed`, `verification: verified`, with a stored `fixed_at` 5.5 hours after the meant
time. The issue is missing from `GET /ops/errors`, and the digest says "fixed, verified". The
control, the same time with `+05:30`, gets 422. The pure probe `rr_probe.py` gives the same in
both read orders.

### The rework's fixes, checked

| Finding | What the reviewer checked | Result |
|---|---|---|
| M1 | First reviewer's trace, unchanged: R1 through HTTP → **422** naming last seen. Story tests: 3 read orders × 2 prior statuses, the refused mark writes nothing, `recurred` never verifies. Code: the check runs inside `BEGIN IMMEDIATE` against `last_seen`, compares `fixed_at` as stored, and rolls back on refusal | **Holds** for a time with an offset (RR-M1 is the exception; RR-I1 is a one-second edge) |
| L1 | A `fixed_at` 1 hour and 30 days ahead → 422; 2 minutes ahead accepted | Holds |
| L2 | 9 more shapes, one issue inside and outside a run: `M&M`, `BAJAJ-AUTO` and `$BAJAJ-AUTO.NS`, a `$MARUTI.NS` column, a ticker named three times, a path, a traceback's `KeyError`. Whole words only: `ITCHY` and `ITC_LTD` are not touched by a row ticker `ITC` | Holds. Residuals as the receipt says (`3MINDIA`, a keep-list word such as `NIFTY`) |
| L3 | 6 more shapes masked: `Proxy-Authorization: Basic`, `authorization=` in a header dump, `Digest` (its quoted values), lowercase `bearer`, two `%40` addresses. "basic validation failed" and "Basic auth not configured" keep their words | Holds. Residual: RR-I3 |
| L4 | Guide 12-J: two digests minutes apart; a backdated mark refused | Holds |
| L5 | A monthly job's acknowledged warning (20 rows on the 1st, April to October) and a weekly one stay `acknowledged` with their task. More than 35 quiet days regresses | Holds for the status. Attention: RR-I2 |
| I1 | `GET` on the POST-only path and `GET /ops/errorz` through `server.app` | 404 JSON |

**Tests fail on the reviewed revision.** The reviewer's own swap plugin (`rr_swap_plugin.py`)
loads the first review's `error_backlog.py` in memory. **22 of the story file's tests fail**
(M1, L1, L2, L3, L5); 74 pass. `server.py` was not swapped, so the I1 test passes there. This
agrees with the implementer's 23. Expected values come from the scenario (counts, digest lines,
refusal text), not from the algorithm.

### Independent adversarial examples

| # | Example | Expected (contract) | Observed |
|---|---|---|---|
| A1 | `fixed_at` without an offset, meant as IST; a recurrence 2 h after the real fix; read before or after the mark (real app and pure) | Refused, or reopened; never verified | **Accepted; `fixed, verified`** in both orders (RR-M1) |
| A2 | The same time with `+05:30` | Refused or reopened | Read first → 422; marked first → reopened as `regressed` |
| A3 | A recurrence 0.4 s after `fixed_at`, in the same second | Same outcome in both orders | Read first → `verified`; marked first → reopened (RR-I1) |
| A4 | Rows of one cause inside a run (row ticker set) and outside, 9 shapes | One issue | One issue in all 9 |
| A5 | 7 credential and address shapes beyond the story's fixtures | Masked | 6 masked; a bare all-letter `Basic` credential kept (RR-I3) |
| A6 | An acknowledged monthly burst of 20 warnings, 7 months | Stays acknowledged | Acknowledged, 0 regressions; flagged spiking and needing attention on each 1st (RR-I2) |

### Findings

| ID | Severity | Location | Evidence | Disposition |
|---|---|---|---|---|
| RR-M1 | **Medium (AC3; the M1 outcome by another input)** | `core/ops/error_backlog.py:342` (`parse_ts` reads a time with no offset as UTC), used by `triage` at `:816`; `services/api/routes/ops_api.py:66-68` (field described only as "ISO"); `scripts/prod_errors.py:90` (`--fixed-at`, no help) | A1 above, through the real app and the pure probe. Trigger: `fixed_at` with no offset, meant as IST, with a recurrence within 5.5 h after the real fix. KT section 10 says such a mark is refused | **Rework 2.** Refuse a `fixed_at` without an explicit offset (a date alone too) with a 422 that shows the form, for example `2026-10-05T08:00+05:30`; the default (now) is unchanged. Say so in the API field, the script's help, KT section 10 and guide 12-J. Reading such a time as IST is the alternative, but a machine-key caller may mean UTC, so refusal is the safer default. Tests: refused through HTTP; `Z` and `+05:30` accepted. The reviewer's `test_rr_trace.py` should pass unchanged |
| RR-I1 | Info | `core/ops/error_backlog.py:346` (`_iso` keeps whole seconds) with `:394` (the occurrence's own fractional time) | A3: a recurrence in the same second as `fixed_at` verifies when read first and reopens when marked first. KT section 10's "the same rows give the same outcome whether they were read before the mark or after it" holds except within that second | Optional in rework 2: compare an occurrence at the stored precision. Otherwise none |
| RR-I2 | Info | `core/ops/error_backlog.py:423-439` (`_spiking`) | A6: a monthly job's 14-day baseline is all zeros, so any burst of at least `spike_min` (10) is a spike. An acknowledged monthly warning therefore needs attention on the 1st and 2nd of each month, though its status and task stay. Weekly: only in its second week | None now. Consistent with KT ("it still needs attention if it spikes"). Watch it after rollout; `wontfix` is available if it is noise |
| RR-I3 | Info | `core/ops/error_backlog.py:147` | A bare `Basic` credential with only letters (no digit, `+`, `/` or padding) and outside a header or quotes stays. The trade-off keeps "basic validation failed". A header value and a quoted value are masked | None (agreed trade-off) |
| RR-I4 | Info | `core/ops/error_backlog.py:560` (digest first/last), `:837` (refusal) | The digest prints first and last seen as UTC dates under an IST time line, and the refusal names `last_seen` in UTC. That invites the confusion behind RR-M1 | Optional in rework 2: show IST there too |

The implementer's I8–I10 are agreed. I7, registering the watchdog entry, stays the owner's
decision at rollout.

### Commands, environment, results

Windows 11, Python 3.13.11, pytest 9.0.3, in the `.stockai` venv, through `tests/hermetic.py`
(the reviewer's `conftest.py` imports the same hooks).

| Check | Command | Result |
|---|---|---|
| Input | `python scripts/docs/kt_manifest.py verify docs/planning/PI-2026-09/evidence/SA-011-manifest.json`; `git hash-object` per path | 13 files, 0 mismatches, `158479b4…`; same 13 blobs |
| Rework diff | `python analysis_data/sa011/rereview1/rr_diff.py analysis_data/sa011/rereview1/out`; `python analysis_data/sa011/rework1/rw_diff_digest.py` | Snapshot 13/13 = review1 blobs; 10 paths changed; `13164cff…`, 46,098 bytes |
| Cumulative diff | `python analysis_data/sa011/review/rv_digest.py` (its `rv.diff` restored) | `36b27f3a…`, 133,594 bytes, 12 files |
| The story's tests | `python -m pytest tests/unit/ops/test_error_backlog_sa011.py -q -p no:cacheprovider` | 96 passed |
| On the reviewed module | the same, with `PYTHONPATH=analysis_data/sa011/rereview1` and `-p rr_swap_plugin` | 22 failed, 74 passed |
| First reviewer's trace | `python -m pytest analysis_data/sa011/review/test_rv_trace.py -q -s -p no:cacheprovider --rootdir=analysis_data/sa011/review` | 3 passed, unchanged (R1 → 422; I1 → 404 JSON) |
| This reviewer's trace | `python -m pytest analysis_data/sa011/rereview1/test_rr_trace.py -q -s -p no:cacheprovider --rootdir=analysis_data/sa011/rereview1` | control passed; **naive-time case failed (RR-M1, as expected on this revision)** |
| Probes | `python analysis_data/sa011/rereview1/rr_probe.py` | 21 of 24; the failures are A1 (both orders) and RR-I3 |
| KT and PDF | `check_kt_docs.py` (with `PYTHONPATH=analysis_data/kt_docs_deps`) | errors `[]`; PDF 40 pages, source `65c2dd68…` = the manifest's KT |
| Full suite | `python -u -m pytest -q -p no:cacheprovider -o console_output_style=count` | **4414 passed, 12 skipped, 0 failed** (8 min 39 s, about 07:13–07:22 IST) |
| Runtime data | `python analysis_data/sa011/review/rv_tree.py`, before and after the full suite | 798 files, `d9fa2376…` before and after (paths and bytes): unchanged |
| Input, again at the end | `kt_manifest.py verify` | 0 mismatches, `158479b4…` |

**Not exercised:** production (nothing was read); two real uvicorn processes (the hermetic
guard forbids subprocesses); a browser (no UI in this story).

### Documentation

KT sections 3 and 10, guide 12-J, ARCHITECTURE, PRODUCT_MAP, CODEBASE and `config.yaml` describe
the reworked code, and the PDF matches its source. Two gaps: none of them says that `fixed_at`
needs an offset (RR-M1), and KT section 10's read-order sentence has the one-second exception
(RR-I1). **This review edited no living document.**

### Acceptance checklist

| Criterion | Result |
|---|---|
| INFO on Railway stderr is not an error from its envelope alone | Met (unchanged since the first review) |
| Identical causes group without leaking payloads or secrets | Met; L2 and L3 fixed (RR-I3 is an agreed residual) |
| Acknowledged issues can regress | Met; L5 decided at 35 quiet days |
| Pending verification reconciles against measured evidence | **Not met for a fix time without an offset (RR-M1)**; met with one |
| Tests: timestamps/ids, tracebacks, floods, severity, tenant authorization | Met |
| Deterministic digest; retention without losing active issues | Met |
| Hard review: no LLM; usable to assign and close a real defect | No LLM: met. Assign and close: met, except a fix time given in local time (RR-M1) |
| Rollout: raw capture intact, no automatic message | Met |
| Documentation | Met apart from RR-M1's missing offset rule |

### Decision and follow-up state

- **`changes_requested`.** SA-011 returns to implementation (rework 2) in a new conversation:
  STATE `status: changes_requested`, `next_task: SA-011`.
  - Rework 2 fixes RR-M1. RR-I1 and RR-I4 are optional; RR-I2 and RR-I3 need no change.
  - It regenerates `SA-011-manifest.json`, records a rework-2 diff against
    [SA-011-manifest-review2.json](SA-011-manifest-review2.json), and reruns the full suite. Both
    reviewers' trace files should pass unchanged.
- A **fresh re-review in another new conversation** signs off the new revision.
- **Production verification** stays `not_started`. Nothing was committed, pushed, deployed,
  configured or sent, and no production state was read.
- **FIX-007 stays next after SA-011.** No other story was started.

## First review: CHANGES REQUESTED (2026-10-12, fresh session)

- **Story:** [SA-011](../stories/SA-011.md). Implementation receipt:
  [SA-011-implementation.md](SA-011-implementation.md).
- **Review context:** a **fresh-session review** in a new conversation opened with "continue" on
  2026-10-12, from about 01:00 IST. It is not the implementing conversation, and it did not read
  that chat. All 31 listed peer sessions were idle.
- **Reviewed input:**
  - `kt_manifest.py verify SA-011-manifest.json` on the worktree: 13 files, **0 mismatches**.
    The review input SHA-256 is **`f4343eaec750e7cef8b93c9531b77dcb06f4044d67c621fa932a763edd473cfb`**,
    which matches STATE.
  - The reviewer's own script (`analysis_data/sa011/review/rv_digest.py`) rebuilt the diff by the
    receipt's recipe. Result: **`b669cf365c762f9ec710a6b4df0c2096b94b2013a7da4a62f438101dc364f94f`**,
    114,636 bytes over 12 files, the same as the receipt.
    - The KT is diffed from the peer's blob `0155b79a`. The base file
      `analysis_data/sa011/kt_peer_base.md` hashes to that blob. The blob differs from `b9cc851`
      only by the peer's product-results text.
    - A first attempt from a temporary path gave another digest: the `--no-index` header names the
      base path. The receipt's path is part of the recipe.
  - **Completeness.** Every modified or untracked file is one of these:
    - in the manifest;
    - bookkeeping (STATE, HANDOFF, the receipt, the manifest);
    - the peer's product-results block (the dated audit, FIX-007, PR-001 to PR-012, the PI README,
      SA-046/049/050/051);
    - `docs/README.md`. It changed at 01:00:16 IST, just before this review: one `railway ssh`
      probe line. It is not SA-011's, and this review did not touch it.
  - **Baseline:** HEAD `b9cc851`.
  - The input is preserved as [SA-011-manifest-review1.json](SA-011-manifest-review1.json),
    so the rework can regenerate `SA-011-manifest.json`.
- **Verdict: `changes_requested`.**
  - Most of the contract holds:
    - grouping and severity are deterministic, with no model;
    - the registry is owner-only;
    - the raw archive is never changed;
    - nothing is sent;
    - the main lifecycle works through the real app.
  - **But a fix can read `verified` after a measured recurrence (M1, medium).** When the owner
    marks an issue `fixed` from the time the fix took effect, which is what `fixed_at` is for, a
    recurrence after that time that the registry already holds is ignored. The fix then reads
    `verified`. This is the criterion's own example: a pending verification must reconcile against
    measured evidence. The receipt, KT section 10 and guide case 12-J all say otherwise.
  - Five low findings (L1 to L5) go in the same rework. Three of them change templates or
    fingerprints, and those are cheapest before the first deploy, because afterwards a change
    re-keys every issue (implementer's I2).

### In one example (M1)

1. On Monday at 08:00 a fix for the malformed miss-factor warning is deployed.
2. On Monday at 20:00 the warning appears again: the fix did not hold. The owner's Tuesday read
   folds that row into the issue.
3. On Wednesday the owner marks the issue `fixed`, with `fixed_at` Monday 08:00.
4. The issue is not reopened.
   - The following Monday it reads **`fixed, verified`**. It leaves the default list, and the
     digest files it under "Fixed".
   - Had the owner not read the registry on Tuesday, the same Monday-evening row would have been
     folded in after the triage and reopened the issue as `regressed`.
   - So the outcome depends on when the owner happened to read, not on the evidence.

**Reproduced through the real app.** The trace is
`analysis_data/sa011/review/test_rv_trace.py::test_real_app_backdated_fix_with_a_recorded_recurrence`.
It uses rows 10, 8.5 and 1 days old and `fixed_at` 9 days ago. The triage response itself
returns `status: fixed` and `verification: verified`, with `last_seen` 12 hours after `fixed_at`.
The issue is missing from `GET /ops/errors`, and the digest says "fixed, verified". The pure probe
`rv_probe.py` R1 gives the same.

### Contract checked

- **AC1, the app's level, not Railway's envelope: met.**
  - The backlog reads only `app_logs`, whose `level` is the record's own.
  - `railway_occurrences` takes the level from the console line. It counts an `error` envelope
    over INFO only as a statistic.
  - Tests: three envelope tests and the archive-level test.
- **AC2, identical causes group without leaking: met, with L2 and L3.**
  - **Grouping:**
    - the implementer's variants;
    - the reviewer's trace: three real `FeedbackAgent` lines become one issue;
    - local corpus: the F21 warning is **one** issue with 390 rows.
    - But a row's ticker column splits a cause (L2).
  - **Leaks:**
    - 0 of 535 local templates hit the reviewer's detectors (`@`, 4+ digit runs, a URL path,
      `sk-`, `eyJ`);
    - a scan of WARNING+ call sites found none that logs chat text, an email or a request body
      unquoted. Search queries are logged quoted (`'%s'`), and the quoted-value rule masks them;
    - two secret shapes are missed (L3).
- **AC3, an acknowledged issue regresses: met.** Pending verification against measured evidence:
  **not met (M1).**
  - **The reading is confirmed.** Audit F21's sentence is "several watchdog verification
    milestones remain pending after their evidence arrived". SA-038 judged and retired those
    milestones, and the one left (`ipo_verdicts_visible_gate`) is a judgement gate. The backlog's
    own fix verification is this story's version of the rule.
  - But that verification must use all the measured evidence, and M1 shows it does not.
- **Unit and integration evidence: present.** The tests cover timestamps and ids, traceback
  variants, a 5,000-row flood, severity, tenant authorization, a deterministic digest, and
  retention without losing active issues. The fixtures use blocked transports: the outbox test
  stubs `_send_row`, and the HTTP tests use `TestClient`.
- **Hard review:**
  - **No LLM:** confirmed. The module imports only the standard library and the config loader.
  - **Usable to assign and close a real defect:** met on the main path. The reviewer's real-app
    trace runs signup, then a member by invite, then real capture, acknowledge with a task, fix,
    recurrence, and `regressed`, keeping its task. On the local corpus, the miss-factor issue
    was assigned and closed. Closing from the fix's own time is unreliable (M1).
- **Rollout:** met.
  - The module's only SQL on `app_logs` is `PRAGMA table_info` and `SELECT`.
  - Nothing is sent: the watchdog runs only the checks a `milestones.yaml` entry names
    (`runner.py:171`), and none names `error_backlog`.

### Independent adversarial examples

| # | Example | Expected (contract) | Observed |
|---|---|---|---|
| R1 | A fix marked with a `fixed_at` before a recurrence the registry already holds | Not verified; reopened, or refused | **`verified`**, missing from the active list, "fixed, verified" in the digest (M1) |
| R2 | A `fixed_at` 30 days in the future, then a recurrence 2 days later | Refused, or reopened | Accepted; it stays `fixed` (L1) |
| R3 | `Authorization: Basic <base64>`; `investor%40example.com`; bytes literal; unlisted `auth=`/`p256dh=`; phone; PAN; bare JWT; OpenRouter key | Masked | 6 masked; **Basic credential and `%40` address kept** (L3) |
| R4 | Seven pathological 4,000-character messages | Bounded | Worst 0.77 s (`a-a-a-…`); the others 2–145 ms (I3) |
| R5 | An acknowledged warning from a weekly job, 7 days and 1 minute apart | Stays owned | Reopened 3 times in 4 weeks (L5) |
| T1 | Real app (`server.app`, its catch-all; lifespan not started), real signup and invite, real `SQLiteLogHandler`, the backlog on its own connection to the same file | Owner reads and triages; member 403; anonymous 401; no log text in refusals; regression keeps its task; `app_logs` unchanged | All as expected (`test_real_app_owner_member_anonymous_and_a_real_defect_lifecycle` passed) |
| T2 | The same message logged inside a run (ticker column set) and outside | One issue | **Two issues**: `$<id>.NS …` and `<sym> …`. Local corpus: 4 causes split into 8 issues (L2) |
| T3 | `GET` on the POST-only triage path, and `GET /ops/errorz` | 404 or 405 | 200 `index.html` from the catch-all (I1) |
| C1 | Copy of the local `data/telemetry.db`: 67,462 rows, 2 Jul to 27 Sep (local reproduction, not production) | Usable, bounded | 535 issues, 20 seen once, 0 detector hits; batches of 2,000 rows median 0.47 s, max 0.62 s in the write transaction (I2) |

### Findings

| ID | Severity | Location | Evidence | Disposition |
|---|---|---|---|---|
| M1 | **Medium (unmet AC3)** | `core/ops/error_backlog.py:772-789` (`triage` sets `fixed_at` without looking at `last_seen`); `:425-432` (`classify` verifies on time and coverage only) | R1 and the real-app trace above. Trigger: `fixed_at` < `last_seen` at triage, the documented use of `fixed_at`. The same rows give `verified` or `regressed` depending on read order | **Rework.** Refuse (422) a `fixed_at` earlier than the issue's `last_seen`, naming `last_seen`; or reopen it at once as `regressed`. Also make `classify` never report `verified` while `last_seen > fixed_at`. Add an order-independence invariant: the same rows read before or after the triage give the same state. The reviewer's trace test is a ready fixture |
| L1 | Low | `core/ops/error_backlog.py:772-776` | R2: a future `fixed_at` is accepted, and recurrences until then neither reopen the issue nor count against the fix | **Rework.** Refuse a `fixed_at` later than now, with a small clock tolerance |
| L2 | Low (AC2 grouping) | `core/ops/error_backlog.py:246-247` with `:198-200` | T2. The row's ticker becomes `<id>` while the symbol rules make `<sym>`, so a cause splits by run context. The receipt claims "the row's own run id and ticker never split a cause"; its test compares only two rows that both carry the column | **Rework, before the first deploy.** Mask the row's ticker exactly as the symbol rules do, including `$…​.NS`/`.BO`. Test the same message inside and outside a run |
| L3 | Low (privacy residual; the implementer's L1 class) | `core/ops/error_backlog.py:129-134` | R3: `Authorization: Basic dXNl…` keeps the credential (only the scheme word is masked); `investor%40example.com` keeps the address | **Rework, before the first deploy.** Mask a Basic credential like Bearer, and `%40` addresses; add both to the test's secrets |
| L4 | Low (docs) | `docs/TEAM_TESTING_GUIDE.md:303` (12-J) | It expects a digest taken a day later of an unchanged registry to be identical except its time line. States (`new` → `ongoing`) and 7-day counts depend on the clock, so a correct build can fail the step | **Rework.** Reword: two reads minutes apart with no new warning give the same digest, apart from its time line |
| L5 | Low (design; decide and record) | `core/ops/error_backlog.py:363-370` | R5: an acknowledged warning from a weekly job reopens whenever this week's run is a minute later than last week's (3 times in 4 weeks in R5), because the gap reaches `quiet_days` (7). A monthly job's warning reopens every month | **Rework: decide and record.** Keep it, and the guide tells the owner to use `wontfix` for a known periodic warning. Or regress an acknowledged issue only on a gap longer than its own usual cadence |
| I1 | Info | `services/api/server.py:531-534` | `ops/` is not in `_API_NAMESPACES` (T3). Not a security issue: `index.html` is public | Optional in the rework (one word) |
| I2 | Info | `core/ops/error_backlog.py:688-719` | Each batch normalises inside `BEGIN IMMEDIATE`. Other telemetry writers wait up to 0.62 s locally, well under the 5 s busy timeout | None. Watch the first production catch-up |
| I3 | Info | `core/ops/error_backlog.py:152` (token rule) | 0.77 s for one pathological message. Real rows take about 0.2 ms each | None |

The implementer's L1 and I1–I7 are agreed. I7, registering the watchdog entry, stays the owner's
decision at rollout.

### Commands, environment, results

Windows 11, Python 3.13.11, pytest 9.0.3, in the `.stockai` venv, through `tests/hermetic.py`
(the review's own `conftest.py` imports the same hooks).

| Check | Command | Result |
|---|---|---|
| Input | `python scripts/docs/kt_manifest.py verify docs/planning/PI-2026-09/evidence/SA-011-manifest.json` | 13 files, 0 mismatches, `f4343eae…` |
| Diff | `python analysis_data/sa011/review/rv_digest.py` | `b669cf36…`, 114,636 bytes, 12 files |
| The story's tests | `python -m pytest tests/unit/ops/test_error_backlog_sa011.py -q -p no:cacheprovider` | 66 passed |
| The reviewer's trace | `python -m pytest analysis_data/sa011/review/test_rv_trace.py -q -p no:cacheprovider -s --rootdir=analysis_data/sa011/review` | 2 passed, **1 failed (M1, as expected on this revision)** |
| Probes | `python analysis_data/sa011/review/rv_probe.py` | 7 of 14 pass; the failures are R1 (3 checks), R2, R3 (2 shapes) and R5 |
| Ticker split | `python analysis_data/sa011/review/rv_split.py` | 3 of 3 pairs split; local corpus 4 causes, 8 issues |
| Local corpus | `python analysis_data/sa011/review/rv_corpus.py` (a copy, deleted afterwards) | As in C1 |
| Routes | `python analysis_data/sa011/review/rv_routes.py` | 14 `include_router` calls (13 at `b9cc851`), 89 router endpoints, 1 WebSocket: PRODUCT_MAP is right |
| KT and PDF | `check_kt_docs.py` (with `PYTHONPATH=analysis_data/kt_docs_deps`) | errors `[]`; PDF 40 pages, source `c9a8e239…` = the manifest's KT |
| Full suite | `python -u -m pytest -q -p no:cacheprovider -o console_output_style=count` | **4384 passed, 12 skipped, 0 failed** (8 min 54 s, about 01:09–01:18 IST) |
| Runtime data | `python analysis_data/sa011/review/rv_tree.py`, before and after the full suite | 798 files, `d9fa2376…` before and after (path and bytes): unchanged |
| Input, again at the end | `kt_manifest.py verify` | 0 mismatches, `f4343eae…` |

**Not exercised:**

- production: nothing was read, and no Railway export, so the implementer's I6 stays open;
- two real uvicorn processes: the hermetic guard forbids subprocesses, so the implementer's
  unwrapped-refresh model stands;
- a browser: there is no UI in this story.

### Documentation

KT section 10 "Operations backlog", sections 3, 9, 11 and 13, ARCHITECTURE, CODEBASE, PRODUCT_MAP
and guide 12-A/12-J describe the reviewed code, except in two places:

- the claim "verified only after 7 days with no recurrence", which M1 contradicts;
- 12-J's day-apart determinism step (L4).

The PDF matches its source. **This review edited no living document.** The rework edits them with
its fixes.

### Acceptance checklist

| Criterion | Result |
|---|---|
| INFO on Railway stderr is not an error from its envelope alone | Met |
| Identical causes group without leaking payloads or secrets | Met, with L2 (split by ticker column) and L3 (two secret shapes) for the rework |
| Acknowledged issues can regress | Met (L5 is a cadence decision) |
| Pending verification reconciles against measured evidence | **Not met: M1** |
| Tests: timestamps/ids, tracebacks, floods, severity, tenant authorization | Met |
| Deterministic digest; retention without losing active issues | Met |
| Hard review: no LLM; usable to assign and close a real defect | No LLM: met. Assign and close: met on the main path; M1 on a backdated fix |
| Rollout: raw capture intact, no automatic message | Met |
| Documentation | Met apart from M1's claim and L4 |

### Decision and follow-up state

- **`changes_requested`.** SA-011 returns to implementation (rework 1) in a new conversation:
  STATE `status: changes_requested`, `next_task: SA-011`.
  - The rework fixes M1, L1, L2, L3 and L4, decides and records L5, and may take I1.
  - It regenerates `SA-011-manifest.json`, records a rework diff against this input, and reruns
    the full suite.
- A **fresh re-review in another new conversation** signs off the new revision. The trace test
  above should pass on it unchanged.
- **Production verification** stays `not_started`. Nothing was committed, pushed, deployed,
  configured or sent, and no production state was read.
- **FIX-007 stays next after SA-011.** No other story was started.
