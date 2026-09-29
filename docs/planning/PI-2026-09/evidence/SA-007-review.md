# SA-007 review receipt — make backups independently recoverable

## Fresh-session review: ACCEPTED (2026-09-29)

- **Story:** [SA-007](../stories/SA-007.md). Audit finding F17.
- **Context:** a fresh-session review in a new conversation, 2026-09-29 about 07:05–07:35 IST. It is
  not the implementing conversation, and it read only the story, the receipt, the diff, the code
  and the relevant docs.
- **SA-039:** no check was due. P2 is at 17:00 IST today.
- **Peers:** 24 other sessions, all idle at the start and before the bookkeeping.
- **Nothing** was committed, pushed, deployed, configured or sent. No bucket was created, and no
  production state was read.
- **Verdict: accepted.** Every acceptance criterion is met. There are two low findings, both
  reproduced, and both routed with a fix to planned stories: F1 to [SA-034](../stories/SA-034.md)
  and F2 to [SA-036](../stories/SA-036.md). None is critical, high or medium.

### Review input verified

- **Manifest:** [SA-007-manifest.json](SA-007-manifest.json). The SHA-256 of its LF bytes is
  `7c1d43d9fcecd34abe025adb84f1426ae276a68c7d9a1c24e5c54c0471a5d1ca`, as the receipt states.
  `kt_manifest.py verify` gave 18 files and 0 mismatches before the review edits.
- **Completeness:** `git diff --name-only cdec78f` plus the untracked files lists exactly the 18
  manifest paths and the 3 excluded bookkeeping files. There is no unlisted change.
- **Diff:** rebuilt with the reviewer's own script (`analysis_data/sa007/review/rev_diff.py`,
  ignored), independent of `sa007_diff.py`. It gave 17 text files, 135,591 bytes and SHA-256
  `2e0a5656a9914c71848d9be41c5ecfd7f4a51ed2087a332b198c3f9bdf8ee383`, the receipt's digest. The
  PDF blob is `799e9596…`, as stated.
- **Baseline:** `cdec78f` is HEAD. The tree held only the listed changes.

### Contract checked

- **Snapshots.** `_is_sqlite` detects a database by its 16-byte header, so every database goes
  through `sqlite3`'s backup API in one step (`pages=-1`). `-wal`, `-shm` and `-journal` files are
  skipped. Other files are read until one read sees no size or mtime change.
- **Manifest.** Each file has its size and SHA-256. Each database also has `integrity_check`, a
  schema digest and every table's row count, and each ledger its row count. The sidecar holds the
  zip's own size and SHA-256.
- **Drill.** The drill checks the sidecar, the zip, the member set, name safety, each restored
  file's checksum, SQLite facts and ledger rows, then continuity. It restores only into an empty
  directory outside `data/`, and it never raises.
- **Job order:** build, drill, rotate, off-site (only if the drill passed), email, status, then
  raise if the drill failed.
- **Off-site.** The archive is encrypted with AES-256-GCM, and the header is the associated data.
  The ciphertext goes first; its size must read back, then the manifest follows and is read back
  too. Retention deletes a manifest before its ciphertext.
- **Fetch.** It checks the name, downloads the manifest, checks the ciphertext's size and SHA-256
  against it, decrypts, then drills.
- **Watchdog.** `backup_recoverable` is a standing invariant, so the engine sends one warning each
  morning while the check is `pending`, and one `resolved` notice when it clears.
- **Configuration.** `core.config.settings` is a shim that star-imports
  `backend.shared.config.settings.base`, with no `__all__`, so the new `BACKUP_*` variables reach
  `config_from_settings`. Measured: with `BACKUP_OFFSITE_TARGET=dir`, `BACKUP_OFFSITE_KEEP=5` and a
  fake key in the environment, the config read `dir`, `5` and "key set", and its `repr` did not
  show the key.

### Independent adversarial examples

The reviewer's own fixtures are in `analysis_data/sa007/review/probe_sa007.py` (ignored). They
ran under `tests.hermetic` as a plugin. Each probe asserts the contract as the reviewer derived it
from the story, so a failing probe is a finding.

| # | Fixture | Expected (by the contract) | Observed |
|---|---|---|---|
| P1 | Status written by Sunday's 23:30 IST run, confirmed off-site. Monday: no run (for example, a restart at 23:30). Tuesday 06:30 IST watchdog: the status is 31 h old | `pending`: last night has no confirmed copy | **`satisfied`**: "…passed its restore drill; its encrypted copy is confirmed off-site" (**F1**) |
| P1b | The same, with a normal 7-hour-old status | `satisfied` | `satisfied` |
| P2 | A volume with a healthy `transactions.jsonl` and a malformed `atlas.db` (index root page header broken; `integrity_check` itself raises "malformed") | The ledgers are still archived, and the bad database is named | **The baseline module archived both files. The new job raises `DatabaseError: database disk image is malformed` from `sqlite_facts` (`backup.py:119`, via `:213`). `data/backups/` is empty: no archive, no off-site copy and no status** (**F2**) |
| P3 | The original defect, against the **baseline** module (`git show cdec78f:services/data/backup.py`): `chat_sessions.db` in WAL mode, autocheckpoint off, 5 rows committed, connection left open | The baseline loses the rows, and the new code keeps them | Baseline zip: `chat_sessions.db`, `-shm`, `-wal`; restored alone, `no such table: msgs`. New zip: `chat_sessions.db` and `MANIFEST.json`; 5 rows |
| P4 | Three nights with a `dir` target. After night 1, row 1 of `transactions.jsonl` is rewritten (same row count) | Reported | Watchdog states `satisfied`, `pending`, `satisfied`. A rewrite is reported on one morning only (see D4) |
| P5 | A writer thread commits 50-row batches to a WAL `users.db` throughout the build | A consistent snapshot, and a clean drill | 7,550 rows in the snapshot (5,000 plus whole batches), drill clean |
| P6 | Upgrade night: last night's archive is `stockagent-backup-20260928-1800.zip` with no manifest | It sorts first; continuity is not checked; the drill passes | As expected: "not checked: … has no readable manifest"; the new UTC name sorts last |
| P7 | A newer ciphertext with no manifest (an interrupted upload) beside a confirmed copy | `fetch` takes the newest **confirmed** copy | As expected, and it drills clean |
| P8 | A remote manifest with its `encrypted` block removed | `fetch` refuses it | `OffsiteError` |

**Traced by reading the code:**

- **Secrets.** No log line or status field carries the configuration. Every off-site reason
  passes through `scrub`, and the drill's messages carry only archive-relative paths.
- **Email.** `channels.send_email` never raises, so the status is always written after an upload.
- **Timing.** The 23:45 `audit_nightly` job may overlap a slow backup. APScheduler runs them in
  separate threads, and each file read is change-checked.
- **Python 3.11.** A tokenizer scan found no 3.12-only f-string syntax in the 7 new or changed
  Python files.

### Rulings on the implementer's decisions

- **D1 (standard-library SigV4): upheld.** The test's expected signatures are AWS's published
  constants, not computed. The canonical request, the query encoding (`/` becomes `%2F`,
  continuation tokens included) and the header normalization follow the specification.
- **D2 (ciphertext only off-site): upheld.**
  - Each archive gets a random 96-bit nonce, and the header is authenticated.
  - Decryption writes to `.part` and deletes it unless the tag verifies.
  - Not a finding: the remote manifest is not authenticated. Someone who can write to the bucket
    could rename an older copy as a newer one. The same person could delete every copy, so this
    is outside the threat model.
- **D3 (only a drill-passing archive leaves): upheld** for the off-site copy. The same count-based
  eviction applies to the local rotation, where D3 does not reach (I1).
- **D4 (continuity breaks are warnings): upheld.** Blocking would skip one night and protect
  nothing. P4 measures the cost: a rewrite is reported on one morning, then the history survives
  only in older off-site copies, for `BACKUP_OFFSITE_KEEP` nights (30 by default). The KT now says
  so.
- **D5 ("confirmed" = HEAD at size, plus the signed payload hash): upheld.** Off-site recovery
  stays unverified until the recorded `fetch` drill against a real bucket.
- **D6 (a missed night is reported the next morning): partly upheld.** It holds for a night on
  which the job ran and the upload failed, and the implementer's test proves that. It does not
  hold for a night on which the job never ran (F1).
- **D7 (the email copy is unchanged): upheld** as the owner's decision. LEGAL and the KT record the
  plaintext gap.
- **D8, D9 and D10: upheld.** P6 confirms the name ordering on the upgrade night.

### Findings

| ID | Severity | Location | Trigger → observed / expected | Impact | Disposition |
|---|---|---|---|---|---|
| F1 | Low, confirmed (P1) | `core/ops/watchdog/checks.py:358` (`_BACKUP_STALE_HOURS = 36`), used at `:405` | The job never runs one night; the next night succeeds. Observed: the 06:30 check reads `satisfied` both mornings, so the missed night is never reported. Expected: `pending` on the first morning. The job at 23:30 and the watchdog at 06:30 are 7 h apart, so one missed run makes the status 31 h old. | That night has no new copy, off-site or local, so the recovery point silently becomes about 48 h. Nothing is lost. Two nights in a row are reported, and SA-042's outside witness is planned for missed jobs. | **Routed to [SA-034](../stories/SA-034.md)** (its critical-job-ran invariant, or a limit of about 30 h), with a note on the card. The KT §10 visibility paragraph now states the gap. |
| F2 | Low, confirmed (P2) | `services/data/backup.py:209-217` (`_snapshot_sqlite`, `sqlite_facts` and the integrity gate, with no per-file handling) | One malformed SQLite file anywhere under `data/`, including a rebuildable one such as `telemetry.db`. Observed: `create_backup_archive` raises, so no archive, off-site copy or status is written, every night until it is repaired. The baseline archived everything else, including the ledgers. Expected: every other file archived and the bad database named. | While a database is corrupt, the portfolio ledgers get no new backup. The job-error alert fires each night. The watchdog says "the job has stopped" only from the second morning (F1). Earlier archives and off-site copies are kept, because rotation and pruning never run. Under D3 a flagged archive would not go off-site either, so the practical loss is the local archive of the ledgers. | **Routed to [SA-036](../stories/SA-036.md)** (a `partial` backup outcome, with a note on the card). The KT §10 "Limits" now state it. |
| I1 | Info | `services/data/backup.py:256` (`prune_backups`), called at `:319` before the drill result is used | 7 failed-drill nights in a row with no bucket configured (production today) | Every good local archive is deleted. Each of those nights raises a job error and a watchdog warning. | Noted on the SA-036 card: never prune the newest drill-passing archive. |
| I2 | Info, predates SA-007 | KT §1, §10 and §12, ARCHITECTURE, guide 01-F and 10-B/E/F | SA-004 (deploy `b3fb00dd`) and SA-006 (deploy `00b94de9`) are deployed, but these still say "not yet deployed" | Stale status wording | For the next KT bump, or [SA-031](../stories/SA-031.md). This review changed only SA-007's wording. |

### Commands, environment, results

Windows 11, Python 3.13.11 in `.stockai`. Production is Linux, Python 3.11.

| Check | Command | Result |
|---|---|---|
| Manifest | `python scripts/docs/kt_manifest.py verify docs/planning/PI-2026-09/evidence/SA-007-manifest.json` | 18 files, 0 mismatches, `7c1d43d9…` (before the review edits) |
| Diff | `python analysis_data/sa007/review/rev_diff.py <repo> cdec78f <out>` | `2e0a5656…`, 135,591 bytes, 17 text files |
| Focused tests | the receipt's 8 files (3 new, plus watchdog, registry, hermetic, the old backup and scheduler tests) | **136 passed** (31 s) |
| Reviewer probes | `python -m pytest -c pyproject.toml --rootdir . -p tests.hermetic -s analysis_data/sa007/review/probe_sa007.py` | 7 passed, **2 failed as findings** (P1 → F1, P2 → F2) |
| Reviewer mutations | `SA007_MUT=<name> PYTHONPATH=analysis_data/sa007/review python -m pytest -p mut_plugin --basetemp <scratch> <the 3 new test files>`; patched at run time, no file edited | **9 of 9 caught.** R1 no stale limit (1 failing); R2 member names unchecked (1); R3 no isolation guard (5); R4 no credential filter (1); R5 plaintext off-site (4); R6 no continuity (5); R7 retention keeps the oldest (3); R8 status forgets the last confirmed copy (1); R9 no scrubbing (1) |
| Full suite, run 1 | `python -m pytest -q -rfEs -p no:cacheprovider tests` | 3901 passed, 12 skipped, **1 failed** (5 min 14 s): `test_ipo_history.py::test_rewrites_still_work_on_a_fully_parseable_file`, `PermissionError: [WinError 5]` on `os.replace` in `core/ipo/history.py`. It ran alongside the mutation runs. SA-007 does not touch that code, and the file passes 5 of 5 alone (11 tests each). It is the same Windows rename flake already routed to SA-031 for `core/ipo/signals.py`; this review adds `core/ipo/history.py` (`upsert`, a bare `Path.replace`) to that route. |
| Full suite, run 2 (alone) | the same | **3902 passed, 12 skipped, 0 failed** (5 min 03 s), the receipt's count |
| `data/`, `logs/`, `outputs/` | files newer than a marker set before each run | 0 and 0 |
| Broad-except guard | `python scripts/ci/check_broad_except.py` | OK (154 grandfathered) |
| KT check | `python scripts/docs/check_kt_docs.py` | errors `[]`, 28 pages, source `79aa0102…` before the edits; after the edits and `build_kt_pdf.py`: errors `[]`, 28 pages, 385 links, source `9efaf9da…`, PDF blob `529f5590…` |

**Not exercised:**

- a real S3-compatible provider (B2, R2 or AWS);
- Linux and Python 3.11, which CI covers on the next push;
- production-sized data;
- the email send;
- delivery of the watchdog's notifications.

The off-site restore stays unverified until the owner's bucket exists and a `fetch` is recorded
(guide 12-B).

### Review edits (documentation only)

- **KT** (`docs/TECHNICAL_DESIGN.md`):
  - SA-007's status is now "accepted" in §1, the §10 heading, §11 and §12. §1 now reads "every
    other story from SA-008".
  - §10 "Visibility" now states F1, and that a ledger rewrite is reported on one morning.
  - §10 "Limits" now states F2.
- **The PDF** is rebuilt from the edited KT (28 pages, no overflow).
- **ARCHITECTURE, TEAM_TESTING_GUIDE (12-B, 12-G, 12-H) and LEGAL:** SA-007's status wording.
- **Story cards (outside the manifest):** routed-input notes on SA-034 (F1) and SA-036 (F2, I1).

No code, test or configuration byte changed. `verify SA-007-manifest.json` now mismatches exactly
these 5 files: the KT, the PDF, ARCHITECTURE, TEAM_TESTING_GUIDE and LEGAL_AND_COMPLIANCE.

### Acceptance checklist

| Criterion | Verdict |
|---|---|
| Backup artifacts include consistent SQLite snapshots and required JSON/JSONL state | **Met.** Every database, found by its header, goes through the backup API. P3 shows the original defect and its fix, and P5 shows a consistent snapshot while a writer is active. All non-cache files are included. F2 is a failure-handling gap, not a content gap. |
| A restore drill validates schema, row counts, ledger continuity and checksums | **Met.** The tests use fixture-derived expectations, and mutations R2, R3 and R6 are caught. |
| Missing off-site confirmation is visible; secrets are excluded from artifacts and logs | **Met.** The watchdog warns daily when no copy is configured, on a failed upload and on a failed drill. F1 is the one gap, and it is routed. Credential-shaped files are excluded, reasons are scrubbed, and `repr` hides the key (R4, R9). |
| Evidence: interrupted upload, corrupt archive, missing manifest, retention boundary, failed restore | **Met.** Each has a test. The fixtures are temporary, and the drill refuses `data/`. |
| Hard review: snapshot consistency, encryption and access configuration, retention, a recoverable manifest | **Met.** AES-256-GCM with an authenticated header; no plaintext upload; manifest last; retention by confirmed copies; recovery from the off-site copy alone is tested. Nothing is provisioned by code. |
| Documentation updated | **Met.** The KT, PDF, guide, ARCHITECTURE, PRODUCT_MAP, CODEBASE and LEGAL, plus this review's edits. |

### Decision and follow-up state

- **SA-007 is `done`** (code and docs accepted) for the reviewed revision: the uncommitted
  working tree on `cdec78f`, pinned by review input `7c1d43d9…` and diff `2e0a5656…`.
- **Production verification stays `pending_deployment`.** It needs:
  - the owner's commit, push and deploy. A deploy alone makes the watchdog warn every morning
    until a bucket is configured;
  - the owner's bucket, key and `BACKUP_*` variables, set in a job-free window (each set
    redeploys). This is on the deferred owner-setup list;
  - a recorded `python -m services.data.restore fetch --dest <empty dir>` from outside Railway.
- **Owner decision, still open:** retire or encrypt the plaintext backup email (D7).
- **Follow-ups:** F1 → SA-034; F2 and I1 → SA-036; I2 → the next KT bump or SA-031; the
  `core/ipo/history.py` rename flake → SA-031, with the `signals.py` one. The
  implementation's routed notes still stand: the owner setup, and the KT links to `offsite.py` and
  `restore.py` at the KT bump after a commit.
- **Next ready story, by STATE file order: SA-008.** Its dependency, SA-003, is done. It was not
  started in this conversation.
