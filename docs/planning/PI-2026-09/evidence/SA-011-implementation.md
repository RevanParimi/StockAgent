# SA-011 — implementation receipt

**Story:** [SA-011](../stories/SA-011.md), turn durable errors into a deterministic operations
backlog (audit F21). **Phase:** implementation, 11 Oct 2026, from about 14:44 IST, a new
conversation opened with "continue". **Status after this phase:** `review_required`. The fresh
review happens in a new conversation. **The first review and the re-review requested changes;
rework 2 (12 Oct) is the next section, then rework 1, then the first implementation's
record.**

**Baseline:** `b9cc851`, plus uncommitted planning notes. Two kinds of uncommitted edits sit on
top of it and are not part of this story:

- the b9cc851 push note in STATE and HANDOFF;
- a peer session's product-results review (stockagent-main-43). It is read-only analysis written
  as new files, plus edits to STATE, HANDOFF, the PI README, three story cards, the KT and its
  PDF.

The two sessions agreed their writes by message. The peer finished its edits before this phase
touched the KT. The diff digest below takes that into account. Nothing was committed, pushed,
deployed or configured, and no production state was read.

## Rework 2 — 12 Oct 2026 (implementation, after the re-review's `changes_requested`)

**Phase:** implementation (rework 2), a new conversation opened with "continue" on 12 Oct 2026,
from about 07:30 IST. It is neither of the reviewing conversations. **Status after this phase:**
`review_required`; a fresh re-review happens in another new conversation. All 34 listed peer
sessions were idle at the start.

- **Input:** the re-review's input, preserved as
  [SA-011-manifest-review2.json](SA-011-manifest-review2.json) (`158479b4…`). `kt_manifest.py
  verify` gave 0 mismatches before any edit. Those bytes were snapshotted to the ignored
  `analysis_data/sa011/rework2/base/`, and `rw2_diff_digest.py` re-proves the snapshot against
  that manifest's blob ids.
- **Findings addressed:** [the re-review](SA-011-review.md) RR-M1 is fixed; the optional RR-I1
  and RR-I4 are taken. RR-I2 and RR-I3 need no change, as the re-review says.
- Nothing was committed, pushed, deployed or configured, and no production state was read.
- **Superseded statements in the sections below:** rework 1's "the comparison uses `fixed_at` as
  it will be stored (to the second)": times are now stored as precisely as they were logged.
  "Naming `last_seen`": a refusal now names it in IST. "96 tests": see Tests below.

### In one example (RR-M1)

1. A fix is deployed on Monday 5 Oct at 08:00 IST. The warning is back at 10:00 IST, and the
   registry reads that row.
2. On Wednesday the owner runs `prod_errors.py --triage <fp> --status fixed --fixed-at
   2026-10-05T08:00`, the deploy time as the app shows it.
3. **Now the API answers 422:** "fixed_at '2026-10-05T08:00' has no UTC offset, so it could be
   IST or UTC: give 2026-10-05T08:00+05:30 for IST or 2026-10-05T08:00Z for UTC". Nothing about
   the issue changes, not even a task sent in the same request.
4. The owner sends `2026-10-05T08:00+05:30`. That is refused too, as rework 1 intended: "this
   issue was last seen at 2026-10-05T10:00:00…+05:30, after fixed_at 2026-10-05T08:00:00+05:30:
   … that fix did not hold."
5. Before this rework, step 2 was accepted. The fix was stored at 13:30 IST, after the
   recurrence, and a week later the issue read `fixed, verified`.

### Changes, by finding

- **RR-M1 (medium): a fix time without an offset.**
  - `triage` reads `fixed_at` with a parser of its own. A time with no UTC offset, or a date
    alone, is refused (`TriageError`, so 422). The message shows the form to give, built from
    the time sent: `<time>+05:30` for IST or `<time>Z` for UTC. A value that is not an ISO time
    is refused with an example built from now, in IST.
  - **Refusal rather than reading the time as IST,** as the re-review recommends: a machine-key
    caller may mean UTC, and either guess files some fixes at the wrong time. The default (no
    `fixed_at`: now) is unchanged.
  - `parse_ts` is unchanged for stored times and archive rows. `log_store` writes `ts` in UTC
    with its offset, and the registry stores only times with offsets.
  - The rule is in the API field's description, the script's `--fixed-at` help and usage line,
    KT section 10, guide 12-J and CODEBASE.
- **RR-I1 (info, taken): a recurrence in the same second as the fix.**
  - Stored times keep the precision they were logged: microseconds when present, and a
    whole-second time prints as before. Triage compares the fix time with the stored
    `last_seen`; ingestion compares it with the occurrence's own time. Both now see the same
    precision. So a recurrence 0.4 s or 1 µs after the fix is after it in every read order:
    refused when read first, reopened when marked first.
  - **Tried first and rejected: comparing occurrences at whole seconds.** That made the read
    orders agree. But a warning logged in the same second as a default-now mark then counted as
    before the fix. The first reviewer's trace caught it: its lifecycle test logs, marks and
    logs again within one second, and it failed.
  - Stored strings: a UTC ISO time with or without a fraction still sorts in time order (`+`
    sorts before `.`). So the cursor's `max` and retention's sort by `last_seen` are unaffected.
    No production registry exists yet, so no stored value changes format.
- **RR-I4 (info, taken): IST where the owner reads.**
  - A refusal names its times in IST, exactly, in the form `fixed_at` accepts
    (`2026-10-06T08:00:00+05:30`).
  - The digest prints first seen as an IST date, last seen as an IST date and minute, and a
    fixed issue's fix time: `first 2026-10-05, last 2026-10-06 02:30 IST; … status fixed since
    2026-10-06 03:00 IST`. Around IST midnight the UTC date was a day behind.
  - The JSON API keeps UTC ISO times with their offset.

### Tests

- **Story file:** `tests/unit/ops/test_error_backlog_sa011.py`, 96 → **111 tests**, all pass.
  Changed: the HTTP backdated refusal, the read-order test and the future-time test now assert
  their refusal's IST times, written as literals or derived from the scenario's own times. New:
  - RR-M1: one instant in 4 notations (`+05:30`, `.000+05:30`, `Z`, `+00:00`) stores the same
    fix. 3 bare forms (a time, a time with seconds, a date) are refused, show the form and write
    nothing, not even the task. 2 more rows in the HTTP refusal table. The re-review's case
    through HTTP: the bare time and the bare date are refused with the form; the same time with
    `+05:30` is refused naming last seen; nothing is recorded; a later fix sent in `Z` is
    accepted and verified;
  - RR-I1: a recurrence 0.4 s, 1 µs and 1 s after the fix never verifies, in all 3 read orders:
    read first it is refused, marked first it reopens. A warning logged 100 ms after a
    default-now mark reopens the issue;
  - RR-I4: the digest's IST first, last and fix-time text around IST midnight, as literals.
- **The re-reviewed revision fails them:** with its module swapped in memory
  (`SA011_RW2=base`), **11 tests fail**: RR-M1 4 (the 3 bare forms and the HTTP case), RR-I1 2 (0.4 s and 1 µs; the 1 s case passes there, as it should), RR-I4 5 (the HTTP backdated refusal, the read-order test for both prior statuses, the future-time test and the digest).
- **Mutants:** `analysis_data/sa011/rework2/rw2_mutants.py` (plugin `rw2_plugin.py`; no repo
  file written): **12 of 12 caught**. Each reverts or weakens one rework-2 change: bare
  times read as UTC, or as IST; a date alone let through; the refusal without the form;
  whole-second storage; whole-second occurrence comparison; UTC in either refusal; UTC dates in
  the digest; no fix time in the digest; `_ist_iso` in UTC. Rework 1's mutants, rerun on this
  revision: **16 of 16 caught**.
- **Both reviewers' traces, unchanged:** `analysis_data/sa011/review/test_rv_trace.py` → **3
  passed**; `analysis_data/sa011/rereview1/test_rr_trace.py` → **2 passed** (the bare IST time →
  422).
- **The re-reviewer's probe:** `rr_probe.py` → **23 of 24** (was 21). The one failure is RR-I3,
  the agreed residual. The same-second recurrence ends `open`, never verified, in both orders.
- **Full suite:** `python -u -m pytest -q -p no:cacheprovider -o console_output_style=count` →
  **4429 passed, 12 skipped, 0 failed** (5 min 50 s, about 07:56–08:03 IST, on the final bytes). Runtime data (`data/`, `logs/`,
  `outputs/`, paths and bytes, the first reviewer's `rv_tree.py`): 798 files, d9fa2376 before and after.
- **Docs:** KT PDF rebuilt (source `b4445b0a…`, 40 pages); `check_kt_docs` errors `[]`.

Windows 11, Python 3.13.11, pytest 9.0.3, in the `.stockai` venv, through `tests/hermetic.py`.

### Documentation

- KT section 10: the lifecycle bullet (a fix time carries its offset, why, and the form; the
  refusal names last seen in IST; times kept as precisely as logged, so the read order does not
  matter even within one second) and the access bullet (the digest's times are IST).
- Guide 12-J: a mark with an offset and the same time without one; IST in the expected results.
- CODEBASE (the module row). The API field's description and the script's help. ARCHITECTURE and
  PRODUCT_MAP summarise the refusals and point to KT section 10; they needed no change.

### Manifest and digests

- **Review input:** [SA-011-manifest.json](SA-011-manifest.json), regenerated, the same 13
  paths. SHA-256 **`0323f2a893f76e18b09058fbfb2ddeea51e1ea2205afa93ce7f8efce704d59e1`**; `kt_manifest.py verify` gives 0 mismatches.
- **Rework diff** (re-review input → this revision): **`ad35960cf507d2264dd66fe5d8ad85e7b83b7e83dd2d4a08fceca0e496d50a0b`**, 36,162
  bytes; 7 of the 12 text files changed (`config.yaml`, `checks.py`, ARCHITECTURE, PRODUCT_MAP
  and `server.py` unchanged), and the PDF. Recipe: `analysis_data/sa011/rework2/rw2_diff_digest.py`.
- **Cumulative diff** (b9cc851; the KT from the peer's blob `0155b79a`), by the first reviewer's
  `rv_digest.py` recipe: **`c8965571f011cef84ec50698228976848e76053a3624e8c0a1b87bf486418c9c`**, 145,148 bytes over 12 files. That
  script overwrites `analysis_data/sa011/review/rv.diff`; it was restored afterwards
  (`b669cf36…`).

### Self-review (same conversation; not the fresh review)

None is critical, high or medium.

- **I11 (info).** The API's JSON times (`first_seen`, `last_seen`, `status_at`, `regressed_at`,
  `generated_at`, `coverage`) now carry microseconds when logged with them. Only
  `scripts/prod_errors.py --json` reads them, and it prints them as they are.
- **I12 (info).** `fromisoformat` also accepts lenient forms with an offset, such as a space for
  `T` or `+0530`. They are unambiguous, so they are accepted.
- **I13 (info).** An occurrence at exactly the fix time, to the microsecond, counts as before the
  fix, in every read order.
- The earlier I8–I10 stand. I7, registering the watchdog entry, stays the owner's decision at
  rollout.

### Next

A **fresh re-review** in a new conversation, by REVIEW.md, of these bytes (`kt_manifest.py verify
SA-011-manifest.json`). The production check in "Rollout" below is unchanged.

## Rework 1 — 12 Oct 2026 (implementation, after the first review's `changes_requested`)

**Phase:** implementation (rework 1), a new conversation opened with "continue" on 12 Oct 2026,
from about 06:28 IST. It is not the reviewing conversation. **Status after this phase:**
`review_required`; a fresh re-review happens in another new conversation. All 32 listed peer
sessions were idle at the start.

- **Input:** the first review's input, preserved as
  [SA-011-manifest-review1.json](SA-011-manifest-review1.json) (`f4343eae…`). `kt_manifest.py
  verify` gave 0 mismatches before any edit. Those bytes were snapshotted to the ignored
  `analysis_data/sa011/rework1/base/`, and `rw_diff_digest.py` re-proves the snapshot against that
  manifest's blob ids.
- **Findings addressed:** [the review](SA-011-review.md) M1, L1, L2, L3 and L4 are fixed; L5 is
  decided and implemented; the optional I1 is taken. I2 and I3 needed no change.
- Nothing was committed, pushed, deployed or configured, and no production state was read.
- **Superseded statements in the first implementation's sections below:** "an `open` or
  `acknowledged` issue regresses after a gap of at least 7 days" (an acknowledged one now needs
  35); "the row's own run id and ticker never split a cause" (it did for the ticker: L2, now
  fixed); "422 for … a bad `fixed_at`" (now also a future one, or one before `last_seen`); "66
  tests" and "23 mutants" (see Tests below). The sections are kept as the record of the first
  implementation.

### In one example (M1)

1. A fix for the malformed miss-factor warning is deployed on Monday at 08:00.
2. The warning comes back at 20:00, and the owner's Tuesday read records it.
3. On Wednesday the owner marks the issue `fixed` "from Monday 08:00". **Now the API answers
   422:** "this issue was last seen at <Monday 20:00>, after fixed_at <Monday 08:00>: an
   occurrence after the fix is already recorded, so that fix did not hold. Leave the issue open,
   or give the time a later fix took effect." Nothing about the issue changes, not even a task
   sent in the same request.
4. Had the owner not read on Tuesday, the mark is accepted, and the Monday-evening row reopens the
   issue as `regressed` at the next read.
   - Either way the issue never reads `fixed`, `verified`, and no digest line claims the fix.
   - Before this rework, step 3 was accepted and the issue read `fixed, verified` a week later.

### Changes, by finding

- **M1 (medium): a fix time the evidence already contradicts.**
  - `triage` refuses a `fixed_at` earlier than the issue's `last_seen`, naming `last_seen`. The
    comparison uses `fixed_at` as it will be stored (to the second), so the refusal and the later
    classification agree. It applies when the status becomes `fixed` and when an already-fixed
    issue's `fixed_at` is moved.
  - The whole request is refused inside its transaction (rollback), so no field is written.
  - **Refusal rather than "reopen at once":** a 200 that turns a request for `fixed` into `open`
    would surprise the owner. Also, the registry keeps no per-occurrence times, so an immediate
    reopen could only date the regression at `last_seen`, not at the first occurrence after the
    fix.
  - **Defence in depth:** `classify` never reports `verified` while `last_seen` is after
    `fixed_at`. It reports `verification: recurred`, which needs attention, stays in the active
    list and is protected from pruning. Ingestion and triage never store that state; only a
    hand-edited row could.
  - **Order-independence, as tested:** the same rows give the same evidence (count, first and
    last seen) and the same verdict whether they are read before the mark, after it, or split
    around it. The verdict is: never `fixed`, never verified, and no `[fixed, …]` digest line.
    What still differs, by design: read first, the refused mark leaves the prior triage (for
    example `acknowledged` with its task); read after, the recurrence reopens the issue as `open`
    and `regressed`, still with its task.
- **L1 (low):** a `fixed_at` more than 5 minutes ahead of the server's clock is refused (422).
  The 5 minutes allow for a client clock slightly ahead.
- **L2 (low, grouping):** the row's own ticker column is replaced by a stand-in symbol, which the
  symbol rules then mask exactly as they mask any ticker. A `$`, `.NS` or `.BO` on the column
  value is stripped first. So `$MARUTI.NS: possibly delisted …` reads `<sym>: …` inside a run
  and outside one.
  - Local corpus copy, by the reviewer's `rv_split.py`: **0 causes split** (was 4 causes in 8
    issues), 530 issues (was 535). This is local reproduction, not production evidence.
  - Residual, unchanged: a ticker the symbol rules cannot recognise outside a run (2 letters,
    digit-first, or a keep-list word) still reads as its own text there.
  - The run-id column keeps `<id>`. No WARNING+ call site interpolates a run id (grep), so it
    cannot split a cause.
- **L3 (low, privacy):** masked now:
  - any `Authorization:` header value, whatever its scheme (`Authorization: <secret>`);
  - a standalone `Basic <base64>` credential, when the base64 has a digit, `+`, `/` or padding,
    so "basic validation failed" keeps its words;
  - a percent-encoded address (`name%40example.com` → `<email>`).
- **L4 (low, docs):** guide 12-J now takes two digests minutes apart with no new warning, and
  adds a backdated mark that must be refused.
- **L5 (low, design), decided (a delegated technical call):** an acknowledged issue regresses only
  after `error_backlog.ack_quiet_days` = **35** quiet days, longer than the monthly jobs' cadence
  (the 1st of the month at 02:00 and 09:00 IST). An open issue still regresses after 7.
  - Example: the Saturday 10:00 job's acknowledged warning, a few minutes later each week, stays
    acknowledged with its task for 8 weeks. Before, it reopened whenever the gap reached 7 days:
    3 times in 4 weeks in the review's R5. The monthly forecast's acknowledged warning stays
    acknowledged month to month. After 35 quiet days it reopens as `regressed`.
  - An acknowledged issue that spikes still needs attention.
  - Rejected: keeping 7 days and telling the owner to use `wontfix`. That hides an issue the
    owner still means to fix, and the reopen depended on a minute of job timing. Also rejected: a
    rule that learns each issue's cadence, which is an adaptive modifier with new stored state
    (AGENTS.md).
- **I1 (info, taken):** `ops/` is in the SPA catch-all's API namespaces. An unknown `/ops/` path,
  or a GET on the POST-only triage path, is a JSON 404, not `index.html`.
- **Fingerprints:** L2 and L3 change the templates, and so the fingerprints, of rows with a
  ticker column and of messages with an `Authorization:`, `Basic` or `%40` value. Nothing is
  deployed, so no production issue is re-keyed. The golden-template test is unchanged.

### Tests

- **Story file:** `tests/unit/ops/test_error_backlog_sa011.py`, 66 → **96 tests**, all pass. One
  test was replaced: "acknowledged regresses after 14 days" became "open regresses after a quiet
  week". New:
  - M1: read order × prior status (4: a recurrence never verifies; with none, every order
    verifies), a refused mark changes nothing, a contradicted fix reads `recurred`, and the 422
    through HTTP names `last_seen`;
  - L1: a future fix time (unit, and a 422 through HTTP), within the 5-minute tolerance accepted;
  - L2: 7 message shapes × 2 column forms, inside a run, outside one and for another ticker; and
    the real `SQLiteLogHandler` under the real `run_context`: one issue, count 2;
  - L3: three more secrets (a Basic header, a digit-free Token header, a bare Basic credential
    with two digits) and a `%40` address in the leak fixtures; ordinary words after "basic"
    kept;
  - L5: weekly and monthly acknowledged cadences stay owned; more than 35 quiet days regresses;
    an acknowledged spike needs attention;
  - I1: unknown `/ops/` paths through the real `server.app` are 404 JSON.
- **The reviewed revision fails them:** with the review1 module and `server.py` swapped in memory
  (`SA011_RW=base`), **23 of the new tests fail** (M1 5, L1 2, L2 9, L3 3, L5 3, I1 1). The
  positive control, every read order verifies a fix with no recurrence, passes on both.
- **Mutants:** `analysis_data/sa011/rework1/rw_mutants.py` (plugin `rw_plugin.py`; no repo file
  written): **16 of 16 caught**. Each reverts or weakens one rework fix. The first
  implementation's 23 mutants: 22 caught as written. M18's anchor line was replaced by the L2
  change, so it fails at configure rather than being caught; its re-anchored equivalent RW16 is
  caught.
- **The reviewer's trace, unchanged:** `analysis_data/sa011/review/test_rv_trace.py` → **3
  passed** (R1 through HTTP → 422; the I1 paths → 404 JSON).
- **The review's probes rerun:** `analysis_data/sa011/rework1/rw_probe.py` (the reviewer's
  `rv_probe.py` stops at R1's refusal) → 16 of 16. Worst pathological normalisation 0.45 s.
- **Focused neighbours:** `tests/unit/ops` and `tests/unit/test_spa_catchall.py` → 256 passed.
- **Full suite:** `python -u -m pytest -q -p no:cacheprovider -o console_output_style=count` → **4414 passed, 12 skipped, 0 failed** (8 min 18 s, about 06:54–07:03 IST, on the final bytes). Runtime data (`data/`, `logs/`, `outputs/`, paths and bytes, the reviewer's `rv_tree.py`): 798 files, `d9fa2376…` before and after.
- **Docs:** KT PDF rebuilt (source `65c2dd68…`, 40 pages); `check_kt_docs` errors `[]`.

Windows 11, Python 3.13.11, pytest 9.0.3, in the `.stockai` venv, through `tests/hermetic.py`.

### Documentation

- KT: section 3's `error_backlog.*` row (35 for an acknowledged issue); section 10's grouping
  (credentials, `%40`, the row's ticker) and lifecycle (acknowledged cadence; refused fix times).
- Guide 12-J (L4 and the backdated mark); CODEBASE (`ack_quiet_days` row, module row);
  ARCHITECTURE and PRODUCT_MAP (refused fix times); `config.yaml` (`ack_quiet_days: 35`).

### Manifest and digests

- **Review input:** [SA-011-manifest.json](SA-011-manifest.json), regenerated, the same 13
  paths. SHA-256 **`158479b48f00ac51f7f2227b69b15b2e2a061a7d135312a92431d311337ca4a3`; `kt_manifest.py verify` gives 0 mismatches**.
- **Rework diff** (review1 input → this revision): **`13164cffd3433cf2d4068e074b3345a8cf56a61fcbba13cc913f7351dce90336`**, 46,098 bytes; 9 of the 12
  text files changed (`checks.py`, `prod_errors.py`, `ops_api.py` unchanged). Recipe:
  `analysis_data/sa011/rework1/rw_diff_digest.py`.
- **Cumulative diff** (b9cc851; the KT from the peer's blob `0155b79a`), by the reviewer's
  `rv_digest.py` recipe: **`36b27f3aeb933f6ffa0a6d8478a3b63befe1dcda25204f7b243439cfc61c0729`**, 133,594 bytes over 12 files.

### Self-review (same conversation; not the fresh review)

None is critical, high or medium.

- **I8 (info).** A row stamped later than the server's clock (clock skew) blocks a `fixed` mark
  until the clock passes it: the default `fixed_at` is now, and a later one is refused beyond 5
  minutes. Not seen locally; the owner can leave it open.
- **I9 (info).** An occurrence in the 5 minutes between now and a slightly-future `fixed_at` counts
  as before the fix.
- **I10 (info).** `recurred` is a new `verification` value in the API's JSON. Only
  `scripts/prod_errors.py --json` reads that field, and it prints it as it is.
- The implementer's L1 and I1–I7 stand. I7, registering the watchdog entry, stays the owner's
  decision at rollout.

### Next

A **fresh re-review** in a new conversation, by REVIEW.md, of these bytes (`kt_manifest.py verify
SA-011-manifest.json`). The production check in "Rollout" below is unchanged.

## First implementation (11 Oct)

The sections below record the first implementation as it was reviewed.

## In one example

The audit's F21 example is the malformed miss-factor warning: 821 rows over 57 days. The
implementation's end-to-end test drives that case through HTTP.

1. Three rows like `[feedback] malformed miss factor for TICK0X: weight 0.5 out of range` arrive,
   for three tickers and three numbers.
2. `GET /ops/errors` shows **one** issue. Its count is 3, its state `new`, and it needs
   attention.
3. The owner marks it `acknowledged`, with assignee `owner` and task `SA-016`. Then the owner
   marks it `fixed`, with the time the fix took effect.
4. A fourth row arrives after that time. The same issue (same fingerprint) now reads `open` and
   `regressed`, with `regressions: 1` and count 4. It keeps its task.
5. The machine key can read the registry. A member account gets 403, and an anonymous caller
   gets 401.

## What changed

- **`core/ops/error_backlog.py` (new).** Turns `telemetry.db` `app_logs` rows into issues:
  - **Normalisation, with no model anywhere.** These parts become placeholders:
    - the pre-E1 `<IST ts> LEVEL [logger] ` prefix;
    - timestamps; UUIDs, hex and prefixed ids such as Atlas user ids (`u_3f9a12c0`) and run ids;
    - numbers, keeping a unit suffix such as `1d`;
    - file paths; URL userinfo, paths and queries;
    - quoted values; secrets (bearer tokens, `key=`, `password=` and the like, JWTs, long
      tokens);
    - symbols: `MARUTI.NS`, `^NSEI`, and bare upper-case tickers outside a fixed keep-list of
      structural words such as `FAILED`, `SKIPPED`, `NOT` and `HTTP`.
  - **What stays.** A number after `HTTP`, `status_code` or `Errno` is the cause, so it stays,
    and so does a URL's host. Lists of one placeholder collapse (`WELCORP, INFY` → `<sym>`).
  - **Tracebacks** are reduced to their head plus the last exception's type and message. Frames
    and line numbers are dropped.
  - **Fingerprint** = sha256(source, logger, template), first 16 hex characters. Only the
    template is stored.
- **Severity.** It is the record's own `app_logs.level`. Rows below WARNING are skipped. The
  offline `railway_occurrences()` reads the app's level from the console format, Python's
  default format or uvicorn's format inside a Railway JSON line. It counts Railway's `error`
  envelope only as a statistic. A line with no app level is `unparsed`, not an error.
- **Lifecycle.**
  - Activity is derived at read time: `new` within 2 days, `ongoing` within 7, then `quiet`.
    `regressed` lasts 2 days after a return.
  - `spiking` is a flag: today's or yesterday's IST count exceeds the issue's own trailing
    14-day mean + 3 sd and is at least 10. An issue needs at least 3 baseline days before it can
    spike.
  - Triage: `open | acknowledged | fixed | wontfix`, with assignee (64), task (64) and note
    (500).
  - A `fixed` issue reopens on any occurrence after `fixed_at`. An `open` or `acknowledged`
    issue regresses (and reopens) after a gap of at least 7 days. `wontfix` counts and never
    reopens.
  - **Fix verification against measured evidence:** `pending` within 7 days of the fix;
    afterwards `verified` only if the backlog's archive coverage (the newest `app_logs` row it
    has read) passes `fixed_at + 7 days`; otherwise `unobserved`.
- **Store.** Two tables in `telemetry.db`, `error_issues` and `error_backlog_cursor`, on the
  module's own connection (never log_store's lock).
  - **Refresh** reads `app_logs` rows with `id > cursor` in batches of 2,000. Each batch is one
    `BEGIN IMMEDIATE` transaction holding the cursor and its issues, so two workers never count a
    row twice. A read takes at most 20,000 rows; `caught_up` says whether it reached the end.
  - A pre-E1 archive without `run_id`/`ticker` columns and a missing table are both handled.
  - A process-wide re-entrant lock serialises store operations, because the routes share one
    connection in a thread pool.
- **Retention** never touches `app_logs`.
  - Per issue: 30 days of daily counts, and the last 20 run ids and tickers.
  - An issue is *protected* while it is acknowledged, its fix awaits verification, or it needs
    attention. An unprotected issue unseen for 90 days is pruned.
  - Over 2,000 issues, the stalest unprotected *quiet* issues go. An active one (protected, or
    seen within 7 days) never goes, even if the cap is exceeded.
- **Digest.** Deterministic plain text: the same bytes for the same registry, clock and coverage,
  whatever the input order. It has sections "Needs attention", "Fixed" and "Ongoing (top 10)".
- **`services/api/routes/ops_api.py` (new), registered in `server.py`.** Every route is
  `require_owner` (owner session or machine key). Errors return 503 with the exception type
  only.
  - `GET /ops/errors?include=attention|active|all&limit=` returns the ranked issues.
  - `GET /ops/errors/digest` returns the plain-text digest.
  - `POST /ops/errors/{16-hex}` triages an issue. It answers 404 for an unknown fingerprint and
    422 for an invalid status, oversize text, a bad `fixed_at`, or `fixed_at` without `fixed`.
- **`core/ops/watchdog/checks.py`.** A new `error_backlog` check: pending while an issue is
  untriaged and new, regressed or spiking. Its detail names counts, loggers and fingerprints,
  never a template. **No `milestones.yaml` entry uses it, so nothing is sent.** A test pins
  that, and enabling the check is the owner's rollout decision.
- **`scripts/prod_errors.py` (new).**
  - Remote: prints the digest, the JSON or a triage, with `STOCKAGENT_TOKEN` or `SCHEDULER_KEY`
    only. No Railway CLI.
  - Offline: `--db` (a read-only copy of `telemetry.db`, in-memory registry) or
    `--railway-json` (an export, by the app's level).
- **`config.yaml`.** A documented `error_backlog:` section holding the windows and bounds above.

**Dead letters (SA-006 routed input).** The outbox drainer already logs one WARNING per
dead-lettered row. It names the channel and kind and gives the classified, redacted reason, so
the backlog consumes dead letters through `app_logs`. A second direct source from `atlas.db`
would double-count every dead letter under two fingerprints. The integration test drives the
real `drain_once` with six dead rows (two accounts, email and push) through a real
`SQLiteLogHandler`. It gets exactly two issues: `(email/brief)` × 4, whose template ends `check
SMTP_PASSWORD`, and `(push/brief)` × 2. Neither the payload nor the user id appears.

**"Pending verification milestones reconcile against measured evidence."** This is read as the
backlog's fix lifecycle above: a fix claim closes only on measured archive coverage, and reopens
on a recurrence. SA-038 already judged and retired the lapsed `manual_confirmation` milestones.
The one left (`ipo_verdicts_visible_gate`) is a judgement gate, not a verification. The fresh
review should confirm or reject this reading.

## Invariant tests

`tests/unit/ops/test_error_backlog_sa011.py`, **66 tests**, each stated from outside the code.

- **One cause, one issue (15).**
  - 8 parametrised pairs: timestamps and retries; `$MARUTI.NS`/`$INFY.BO` with `period=1d`/`5d`;
    Atlas user ids; UUIDs, durations and hex; outbox row ids and attempts; dated and undated
    paths; ticker lists of different lengths; quoted user text.
  - The row's own run id and ticker never split a cause, and the pre-E1 prefix and the E1 form
    are one issue.
  - 4 traceback variants (moved lines, another caller, a deeper stack, a chained exception), and
    a traceback cut by the 4,000-character cap.
- **Causes stay apart (9).**
  - 7 pairs: HTTP 401/429, `status_code` 401/402, Errno 101/111; email vs push dead letters,
    and permanent vs retries-exhausted; `FAILED` vs `SKIPPED`, `NOT resolved` vs `resolved`.
  - Other exception types or loggers.
  - The URL test: same host, different paths → one issue; another host → another.
- **Stability (1).** One golden template and its fingerprint recipe. Changing the normaliser
  re-opens every production issue as new, so the change has to be on purpose.
- **Nothing private (2).** Ten secrets and payloads: a bearer JWT, an OpenRouter key, `api_key=`,
  `password=`, an email, a push URL with a token, quoted user text, a user id, a Resend key and
  an unlabelled low-digit base64 key. None appears in the **registry database file's bytes,
  WAL included**, the digest, or the public JSON.
- **Severity (3).** Railway `error` envelopes over INFO, uvicorn, default-format and bare
  traceback lines give no occurrence, and the statistics count them. The app's level wins in both
  directions. Archive INFO rows are skipped, and the word "ERROR" in a WARNING message does not
  raise its level.
- **Lifecycle (10).**
  - A 5,000-row flood is one issue, with bounded ids, days and digest.
  - new, then ongoing, then quiet.
  - An acknowledged issue regresses after 14 days and not after 6.
  - A fixed issue reopens on a later occurrence only, not on a late-ingested earlier one.
  - Verification is pending, verified, unobserved, or unobserved with no coverage.
  - A spike against its own baseline; no spike at its normal level, below the minimum, or on a
    first-day burst.
  - wontfix.
- **Ingestion (5).**
  - Idempotent, with `app_logs` byte-identical afterwards.
  - Batch size and read cap do not change the result (7 capped reads equal 1).
  - Two writer connections in threads never double-count.
  - **Four concurrent reads through the shared connection.**
  - A pre-E1 schema, and a missing table.
- **Retention (3).** Only inactive issues are pruned. The cap drops the stalest quiet issues and
  never an attention or ongoing issue, even when the cap is 1. Pruning inside refresh keeps the
  raw rows.
- **Determinism (1).** The digest is the same bytes over 5 shuffles and another batch size.
- **Real capture (2).** Real tracebacks from two call sites, through the real handler, are one
  issue. The outbox dead letters, as above.
- **API (13).** A member gets 403 and an anonymous caller 401 on all three routes, with no log
  text in the body (6). The end-to-end assign, fix and regress through HTTP, with the machine
  key (1). 6 refused triage requests.
- **Watchdog (2).** The check names no template, and no registry entry enables it.

**Mutations.** 23 in-memory mutants, loaded into `sys.modules` by
`analysis_data/sa011/mutant_plugin.py`; no repo file is written. **All 23 are caught.** They are:

- envelope severity; level in the fingerprint; fixed never reopens; verified by time alone;
- prune acknowledged; cursor ignored; raw message kept; member can read;
- acknowledged never regresses; digest in input order; cap drops active; protection by age only;
- no symbol rule; no traceback split; no token rule; no URL rule; no spike baseline;
- no code keep; prefix not stripped; run id kept; deferred `BEGIN`; no process lock;
- status words swallowed.

Two survived earlier drafts, which led to changes:

- the `sk-` key rule was redundant with the token and id rules, and was deleted;
- the URL and token rules were then covered by new fixtures. Those fixtures exposed a real bug:
  the path rule ate the URL rule's output and a `key=` rule split URLs. Both were fixed.

One more survived after the in-process lock was added. The deferred-`BEGIN` mutant passed,
because the lock serialised the two "writer" threads. The two-writer test now calls the unwrapped
`refresh`, which models two worker processes that each have their own lock. That mutant is
caught again.

## Local measurement (local reproduction, not production evidence)

`analysis_data/sa011/measure_corpus.py` prints aggregates only, never a message or template.

- **`data/telemetry.db`, 67,462 rows, 2 Jul to 27 Sep.** Most of these are local runs, including
  test-run rows that pre-SA-005 suites wrote.
  - **535 fingerprints**, 20 of them seen once. The run is deterministic: two runs give the same
    fingerprints and the same digest.
  - **0 templates** contain `@`, a run of 4 or more digits, a URL path or an `sk-` key.
  - Across the E1 prefix boundary: 135 legacy-only fingerprints, 178 E1-only and 217 both. Only
    1 E1-only fingerprint has a legacy-only twin of the same masked shape.
  - `atlas_store` went from 301 fingerprints to 9 once prefixed user ids were normalised.
  - About 7.5 to 15 s for all rows locally.
- **`analysis_data/telemetry.db`, 3,056 rows, 2 to 29 Jul, pre-E1 schema** (an older local copy;
  its origin is not recorded). **211 fingerprints**, 0 detectable leaks by the same checks.

## Commands and environment

Windows 11, Python 3.13.11, pytest 9.0.3, FastAPI 0.136.1, pydantic 2.13.3, in the `.stockai`
venv. Every run passes through `tests/hermetic.py`.

- New file: `python -m pytest tests/unit/ops/test_error_backlog_sa011.py -q -p no:cacheprovider`
  → **66 passed**.
- Focused neighbours: `tests/unit/ops`, error capture, data-health record, `require_owner`, API
  lockdown, the SA-006 delivery invariants, job outcomes → **341 passed**.
- Mutations: `python analysis_data/sa011/mutants.py` (23 mutants) → 23 caught.
- Full suite: `python -u -m pytest -q -p no:cacheprovider -o console_output_style=count`.
  - A first run on an intermediate draft gave 4379 passed, 12 skipped and 2 failed. Both
    failures were in the new file: an earlier test in the process leaves a `SQLiteLogHandler` on
    the root logger, so the fixture double-captured. The fixture now swaps in exactly one handler
    for the test.
  - On the final code: **4384 passed, 12 skipped, 0 failed** (6 min 27 s). After that, only
    the two-writer test changed (above).
  - On the final bytes of the manifest: **4384 passed, 12 skipped, 0 failed** (6 min 27 s).
- Runtime data: `analysis_data/sa011/tree_digest.py` over `data/`, `logs/` and `outputs/`
  (paths and bytes) gives `798 46d6c300…` before and after every full run.
- Docs: KT PDF rebuilt (source `c9a8e239…`, 40 pages); `check_kt_docs` errors `[]`.

## Documentation

- **KT (`docs/TECHNICAL_DESIGN.md`):**
  - §3: a persistent-records row (`app_logs`, `error_issues`) and a configuration row
    (`error_backlog.*`);
  - §9: the daily-review limits no longer list the backlog as planned;
  - §10: new subsection "Operations backlog";
  - §11: the SA-011 bullet is removed;
  - §13: the KT-session row.
  - The roadmap row stays `Open` until acceptance.
  - The module is named in backticks, not linked: `check_kt_docs` checks links at the header's
    revision (`954305a`). The header bump at commit can add the links.
- **Other documents:**
  - ARCHITECTURE: an operations-backlog bullet;
  - CODEBASE: `ops_api.py` and `error_backlog.py` rows, and `error_backlog.*` config rows;
  - PRODUCT_MAP: 14 routers and 89 endpoints, the ops row, the `error_backlog` config section,
    and a §17 bullet;
  - TEAM_TESTING_GUIDE: 12-A now points at the backlog, and new case **12-J** covers the digest,
    triage, regression, verification, member 403 and no message sent.
- `analysis_data/sa011/diff_digest.py` proves that ARCHITECTURE, CODEBASE, PRODUCT_MAP and
  TEAM_TESTING_GUIDE differ from `b9cc851` only by this story's splices.

## Manifest and digest

- **Review input:** [SA-011-manifest.json](SA-011-manifest.json), 13 files. The SHA-256
  of its LF bytes is **`f4343eaec750e7cef8b93c9531b77dcb06f4044d67c621fa932a763edd473cfb`**. `kt_manifest.py verify` gives 0 mismatches.
  - Excluded: STATE, HANDOFF, this receipt, the peer's files, and `.claude/settings.local.json`,
    which is the owner's.
- **Diff digest:** **`b669cf365c762f9ec710a6b4df0c2096b94b2013a7da4a62f438101dc364f94f`**, 114,636 bytes over 12 files.
  - **To rebuild it:** take every manifest path except the PDF, sorted. For a path tracked at
    `b9cc851`, run `git diff --no-color --no-ext-diff b9cc851 -- PATH`. For a new file, run
    `git diff --no-color --no-ext-diff --no-index -- /dev/null PATH`.
  - **Except the KT,** which also holds the peer's edits. Diff it from the peer's version, blob
    **`0155b79a`** (stored with `git hash-object -w` in this checkout). Its canonical source is
    `87607728…`, the peer's recorded PDF source. Rebuild it at
    `analysis_data/sa011/kt_peer_base.md` and run `git diff --no-index` from it.
  - Concatenate the outputs. `analysis_data/sa011/diff_digest.py 0155b79ac52b234e77d7ee6dd2b98f37bf737dd3` does exactly this.

## Self-review

None is critical, high or medium.

- **L1 (low, privacy residual).** Leak protection is pattern-based. Free text that a log call
  interpolates *without* quotes stays in the template. An example is a call site that logs a
  user's sentence bare.
  - The registry is owner-only, nothing is broadcast, and the local corpora show 0 detectable
    leaks.
  - A reviewer could grep call sites that log request bodies. Not fixed here.
- **I1 (info). Over-merging** is limited to one logger. A bare upper-case word outside the
  keep-list becomes `<sym>`, so two code words in the same position merge. The keep-list was
  chosen from the frequent upper-case words in the local corpus.
- **I2 (info). Fingerprint stability.** Any later normaliser change re-keys issues; they reappear
  as new and lose their triage. The golden test makes that a deliberate act.
- **I3 (info). Catch-up after deploy.** Each read folds at most 20,000 rows, so a large
  production archive needs several owner reads (`caught_up: false` until then). `new` comes from
  the rows' own timestamps, so old causes do not flood "needs attention".
- **I4 (info). Dead-letter counts** are log lines. An interrupted-send recovery logs one line per
  batch, not per row. A row whose WARNING failed to reach the archive is missing from the
  backlog, but it is still in `GET /delivery/outbox`.
- **I5 (info). A read writes derived state.** `GET /ops/errors` folds new rows into the registry
  first. The first read after a deploy **creates two tables in production `telemetry.db`**. The
  change is additive, and the nightly backup carries them.
- **I6 (info). Railway's JSON export shape** was not checked against a real export. No production
  read happened in this phase. The parser accepts `level`, `severity` or `attributes.level`, and
  `message` or `msg`.
- **I7 (info, owner decision).** Enabling the `error_backlog` watchdog entry would broadcast
  through `alert_audience()`. That audience is every push-subscribed account, which now includes
  the test member account. Keep it unregistered, or route ops notices owner-only first.
- **Not addressed (scope).** SA-038's I3: the unused `atlas_cutover_*` checks remain.

## Rollout (needs the owner's authorization; nothing here authorizes it)

Commit and deploy only on the owner's word, in a job-free window.

**Production check, read-only, after deploy:**

1. With an owner session, run `python scripts/prod_errors.py --base <app URL>` until the digest's
   refresh is caught up.
2. Confirm that the malformed miss-factor warning is one issue with a count, and that the digest
   shows no address, token or URL path.
3. Confirm that a member session gets 403 and that no new watchdog or push notice appears.
4. Capture one `railway logs --json` export and run `--railway-json` on it. That checks I6 and
   shows how many `error`-envelope lines are INFO.

**Rollback:** revert the commit. The two derived tables can stay or be dropped
(`DROP TABLE error_issues; DROP TABLE error_backlog_cursor;`). `app_logs` is untouched either
way.

## Next

A fresh-session hard review by [REVIEW.md](../REVIEW.md), of these bytes (`kt_manifest.py verify
SA-011-manifest.json`).
