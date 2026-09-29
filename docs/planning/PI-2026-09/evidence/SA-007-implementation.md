# SA-007 implementation receipt — make backups independently recoverable

- **Story:** [SA-007](../stories/SA-007.md). Audit finding F17 in the
  [September audit](../../../audit/2026-09-10-repository-production-review.md).
- **Phase:** implementation, one conversation, 2026-09-29 about 03:20–04:10 IST. It includes a
  same-conversation self-review, which is **not** the fresh-session review.
- **Baseline:** `cdec78f3b8b6a488b5586b5419dfbe8292d9bf26` (record-only HANDOFF commit), clean tree.
  Local `main` is 1 ahead of `origin/main`. Production runs deploy `00b94de9` (`acf72d2`), which
  has none of SA-007.
- **SA-039 checks:** none was due. P2 is Tue 29 Sep 17:00 IST.
- **Peers:** 21 other sessions; every StockAgent session was idle at the start and before bookkeeping.
- **Nothing** was committed, pushed, deployed, configured or sent. No bucket was created.
- **Review input:** [SA-007-manifest.json](SA-007-manifest.json). Its SHA-256 and the diff digest
  are under "Manifest and digests".

## What it does, in one example

On a night with the owner's bucket configured, the job at 23:30 IST builds
`stockagent-backup-20260929-180000.zip`. The name is a UTC stamp. Its `MANIFEST.json` says, for
example, that `users.db` passed `integrity_check`, has a given schema digest and holds `users: 2,
sessions: 0`. It says `portfolio/primary/transactions.jsonl` is 1,200 bytes with SHA-256 `ab12…`
and 3 rows. The sidecar `…zip.manifest.json` records the zip's own size and SHA-256.

The job then restores the zip into a temporary directory and recomputes all of it. Last night's
archive held `transactions.jsonl` at 1,100 bytes, so tonight's copy must begin with those same
1,100 bytes. It passes. The zip is encrypted (AES-256-GCM) and uploaded, then its manifest. Both
read back at their uploaded sizes, so the copy is confirmed, and `backup_status.json` says so. The
watchdog's `backup_recoverable` check is satisfied next morning.

On a night with **no bucket**, everything up to the drill still runs. The status then reads
`not configured: BACKUP_OFFSITE_TARGET is unset`, and next morning the watchdog warns: "No
off-site copy has ever been confirmed … Every backup sits on the volume it protects."

## A defect found in the existing code (local reproduction)

`SQLITE_NAMES = {"telemetry.db", "scores.db"}` routed only two databases through SQLite's backup
API. `users.db`, `atlas.db` and `chat_sessions.db` are opened in WAL mode (`user_store.py:93`,
`atlas_store.py:270`, `chat_session_store.py:62`). They were zipped as raw files, and so were their
`-wal` and `-shm` side files, each copied at a different moment. Reproduced locally (Python 3.13,
SQLite through the stdlib):

| Step | Result |
|---|---|
| New WAL database; `CREATE TABLE users`; 2 rows committed; connection left open | main file 4,096 bytes with the SQLite header; `-wal` 12,392 bytes |
| Raw copy of the main file, opened alone | `no such table: users` |
| Backup-API snapshot of the same database | 2 rows |

Now every file with the SQLite header goes through the backup API, and side files are never copied.
`test_wal_database_rows_survive_the_archive` asserts the premise (the raw copy loses the table),
then the fix. Both the pre-SA-007 detection and raw side-file copying fail it (mutations 1–2).

## The contract

**Archive** ([backup.py](../../../../services/data/backup.py)):

- It holds every file under `data/` except the caches (`market_cache`, `tavily_cache`, `nse`,
  `macro_news`, `eval`) and `backups/`.
- Credential-shaped names are excluded and logged by path, never content: `.env`, `.env.*`,
  `*.env`, `*.pem`, `*.key`, `*.p12`, `*.pfx`, `id_rsa*`, `id_ed25519*`, `*secret*` and
  `*credential*`. The dev data copy has none.
- A non-SQLite file is read until a read sees no size or mtime change, at most 3 tries. The last
  try is kept and flagged `unstable`.
- It is built as `.part`, then renamed. The sidecar is written atomically afterwards.

**Drill** (`services/data/restore.py`, `verify_archive`; never raises):

- The destination must not overlap a protected directory (the live `data/` by default) and must
  be empty or absent. Otherwise the drill refuses and writes nothing.
- Errors set `ok=False`. They are: missing or unreadable sidecar or `MANIFEST.json`; unknown
  format; archive size or SHA-256 mismatch; not a zip; file count, duplicate, unexpected or missing
  member; an unsafe member name (`..`, absolute, empty part; on Windows also `:` and `\`); a
  per-file checksum mismatch after restore; `integrity_check` not ok; a schema digest or any table
  row count differing from the manifest; a ledger row count differing from the manifest.
- Warnings leave `ok=True` but set `clean=False`. They are: a ledger that disappeared, shrank or was
  rewritten since the previous archive (byte-prefix SHA-256); ledger rows that are not JSON
  objects; a torn last row; an `unstable` file.

**Job** (`run_backup_job`):

1. Build, then drill against the newest earlier local archive.
2. Rotate to 7 local copies. The newest is never deleted, and orphan sidecars and `.part` files go.
3. Push off-site **only if the drill passed**.
4. Email as before.
5. Write the status, then raise `BackupError` if the drill failed.

**Off-site** (`services/data/offsite.py`, `push` never raises):

- `BACKUP_OFFSITE_TARGET` empty means "not configured".
- Any target needs a valid 32-byte `BACKUP_ENCRYPTION_KEY`; there is no plaintext upload.
- `dir` is refused when it is, contains or sits inside `data/`.
- `s3` needs a bare `https://` endpoint, a bucket and both keys. Missing keys are reported by
  variable name.
- Upload order is ciphertext, `HEAD` (size must match), manifest, `HEAD`. Only then is the copy
  confirmed.
- Retention keeps the newest `keep` confirmed copies; `keep <= 0` keeps all. It deletes a copy's
  manifest before its ciphertext, deletes ciphertext without a manifest once a newer copy is
  confirmed, and never touches names outside `stockagent-backup-<stamp>.zip…`.
- The remote manifest carries archive-level fields and the ciphertext's size and SHA-256, and no
  file paths.

**Visibility.** The watchdog check `backup_recoverable` (a daily invariant in
[milestones.yaml](../../../../config/milestones.yaml)) reports, in this order:

- `pending` if no status exists yet, or the last run is more than 36 h old;
- `pending` if the drill failed;
- `pending` if no copy was ever confirmed;
- `pending` if **last night's** copy was not confirmed, even when an older copy is under 36 h old;
- `pending` if the drill flagged anything;
- `satisfied` otherwise.

An unreadable status raises, and the watchdog turns that into `unknown`, which also notifies.

**Secrets.** `OffsiteConfig` hides the key and secrets from `repr`. `scrub()` masks the encryption
key, the secret key and the access-key id in every reason and log line. The status and summary
carry only scrubbed reasons.

## Decisions for the reviewer

- **D1. S3 signing from the standard library, no SDK.** `sigv4_authorization` is about 20 lines
  (`hashlib`/`hmac`), and transport uses `requests`, already declared. boto3 would add about
  15 MB and a new pin before SA-033's lock. It reproduces all three of AWS's published S3 examples:
  GET Object `f0e8bdb8…`, PUT Object `98ad7217…` and ListObjects `34b48302…`. The test does not
  compute the expected signatures.
- **D2. No plaintext off-site, ever.** `users.db` holds emails and password hashes, and chat holds
  private text. A third-party bucket gets ciphertext only.
  - Format SABK1: `b"SABK" 0x01`, a 12-byte random nonce, the ciphertext and a 16-byte tag. The
    17-byte header is the associated data.
  - `cryptography` was already installed through pywebpush (49.0.0 locally). It is now declared
    `>=41.0.0`, because SA-007 imports it directly.
  - Losing the key loses every off-site copy. The KT runbook says to keep a second copy outside
    Railway.
- **D3. Only a drill-passing archive leaves the volume.** Retention counts copies, so shipping
  unverified archives for 30 nights could evict every good copy. A failed drill raises, so the
  job-error alert fires, and the watchdog names the failure.
- **D4. Continuity breaks are warnings, not errors.** Example: a repair script rewrites row 3 of
  `transactions.jsonl` on Monday.
  - Monday night's archive is a faithful copy of the live data, and the older off-site copies still
    hold the original history.
  - Blocking the upload would protect nothing. Tuesday compares with Monday's archive and passes, so
    blocking only skips one night.
  - The warning is recorded, and the watchdog reports it until a clean night.
  - The same reasoning covers a pre-existing unparseable or torn ledger row. Otherwise one old bad
    row would stop every off-site copy indefinitely.
- **D5. What "confirmed" means.** Each object must be read back by `HEAD` at its uploaded size.
  Content integrity comes from the signed `x-amz-content-sha256`, which S3-compatible services
  check against the body (test: a flipped byte in transit gets `400 XAmzContentSHA256Mismatch`, and
  no copy). The job does not download the copy back each night, to save egress. Proving off-site
  recovery is the recorded `fetch` drill (below).
- **D6. The first missed night is reported the next morning.** There is no 36-hour grace for a
  missing copy (test: last copy 31 h old and last night unconfirmed means `pending`). The 36-hour
  threshold applies only to "the job has not run".
- **D7. The email copy is unchanged.** It is plaintext, a direct send, sent when under 20 MB, and
  it no longer counts as off-site. Retiring it, or encrypting it, is left to the owner: it is the
  owner's own mailbox, but multi-user PII (see
  [LEGAL_AND_COMPLIANCE.md](../../../LEGAL_AND_COMPLIANCE.md)).
- **D8. Retention edge values.**
  - Locally, `keep=0` used to delete every archive, including tonight's. Now the newest always
    stays.
  - Off-site, `keep <= 0` keeps all copies. The failure mode of a mistyped variable is then growth,
    not loss. This matches `core/portfolio/retention.py` ("None cap = keep-all").
- **D9. Archive names are a UTC stamp with seconds** (`YYYYMMDD-HHMMSS`), where they were the
  container's local time to the minute. They still sort after the old names, and `ARCHIVE_RE`
  accepts both.
- **D10. Not done: a single snapshot across files.** Each file is internally consistent. A
  cross-file transaction, such as `portfolio.json` with `transactions.jsonl`, is not captured
  atomically. The job runs at 23:30, after trading jobs; a volume-level snapshot is outside this
  3-point story.

## Tests

New files, all hermetic (no socket, no `.env`, per-test sandbox cwd):

- `tests/unit/test_backup_recovery.py`, 27 tests. It covers snapshot consistency (a WAL-only row),
  manifest counts taken from the fixture, credential exclusion, an interrupted build, a re-read
  during an append, and the drill:
  - it restores and reads records back;
  - a corrupt archive fails, and so does a truncated one;
  - a missing sidecar fails, and so does an archive without an inner manifest;
  - a member swapped under a valid sidecar fails, and so does a row count disagreeing with the
    manifest;
  - traversal and unlisted members fail, and nothing escapes the destination;
  - the drill refuses `data/`, a directory inside it or its parent, and a non-empty destination.

  It also covers continuity (append clean; rewritten, truncated or deleted flagged; torn and
  unparseable rows flagged), local retention, and the job: missing off-site recorded, continuity
  against the previous archive, and a failed drill that raises and sends nothing off-site.
- `tests/unit/test_backup_offsite.py`, 28 tests:
  - AWS's three published SigV4 vectors;
  - encryption round trip, plus six tamper cases: ciphertext byte, nonce, tag, short file, wrong
    format and wrong key; each leaves no output;
  - key validation that never echoes the value;
  - end-to-end recovery from the off-site copy alone, after deleting the volume;
  - a directory target overlapping `data/` refused (3 cases), and unconfigured or keyless pushes
    refused;
  - a ciphertext that no longer matches its manifest rejected, and non-archive names rejected;
  - the remote retention boundary, `keep=0` keeping all, and the manifest deleted before the
    ciphertext;
  - S3 through an in-memory bucket: the manifest uploaded last, ListObjectsV2 paging (6 keys in
    pages of 2), an interrupted upload never confirmed and cleaned up later, a size mismatch after
    PUT, a body corrupted in transit, and endpoint and credential validation;
  - secrets absent from reasons, logs, status, archive and `repr`;
  - the CLI `drill` and `fetch`, including refusing a non-empty destination.
- `tests/unit/ops/test_watchdog_backup.py`, 10 tests: registry entry, all six states, unreadable
  status is `unknown`, and a job → status → watchdog run end to end, including a misconfigured
  second night.

**Mutations** (`analysis_data/sa007/mutate.py`, ignored). Each re-introduces one defect, runs the
named tests and restores the file, verified by SHA-256: **15/15 caught.**

1. Name-based SQLite detection (pre-SA-007).
2. WAL side files copied raw.
3. No credential exclusion.
4. No continuity check.
5. No isolation guard.
6. Row counts not compared.
7. Member checksums not compared.
8. Traversal allowed.
9. Manifest uploaded first.
10. No read-back.
11. Plaintext upload.
12. Prune deletes the newest.
13. Secrets not scrubbed.
14. Drill failure not blocking off-site.
15. A missed night hidden for 36 h.

The first run found a surviving mutant: `_member_target`'s `resolve()` containment check was
unreachable behind the lexical check, since the drill writes only regular files into an empty
directory. That dead guard was deleted and the mutant re-aimed at the lexical check, which it now
kills.

**Commands** (Windows 11, Python 3.13 in `.stockai`; production is Linux/Python 3.11):

```text
python -m pytest -q -p no:cacheprovider tests/unit/test_backup_recovery.py            -> 27 passed
python -m pytest -q -p no:cacheprovider tests/unit/test_backup_offsite.py             -> 28 passed
python -m pytest -q -p no:cacheprovider tests/unit/ops/test_watchdog_backup.py \
  tests/unit/ops/test_watchdog_checks_more.py tests/unit/ops/test_watchdog_registry.py \
  tests/unit/test_hermetic_boundary.py                                                -> 70 passed
python -m pytest -q -p no:cacheprovider tests/unit/test_backup.py \
  tests/unit/test_scheduler_delivery_jobs.py                                          -> 11 passed (pre-existing, unchanged)
python analysis_data/sa007/mutate.py                                                  -> 15/15 killed
python -m pytest -q -rfEs -p no:cacheprovider tests                                   -> 3902 passed, 12 skipped, 0 failed (9 min 32 s)
python scripts/ci/check_broad_except.py                                               -> OK (154 grandfathered)
python scripts/docs/check_kt_docs.py                                                  -> errors [] (28 pages)
```

The full suite is SA-006's 3837 plus exactly the 65 new tests. The checkout's `data/`, `logs/`
and `outputs/` (800 files) have no file modified since 03:15 IST.

**Local rehearsal on real-shaped data** (`analysis_data/sa007/rehearsal.py`, ignored; counts only;
a copy of the dev `data/`, never the checkout's own; dotenv off; no email; a scratch directory as
the "second disk"):

- archive 5.07 MB, 63 files (57 plain, 5 SQLite, 1 ledger), built in 4.7 s;
- drill clean, with 77,540 SQLite rows over 5 databases checked (1.8 s);
- off-site copy confirmed (0.3 s);
- every file deleted from the copy's `data/`, then `fetch` plus drill from the off-site copy alone:
  clean, 63 files (1.8 s).

## Documentation

- [KT](../../../TECHNICAL_DESIGN.md):
  - edition 2026-09-29;
  - section 3, `data/backups/`;
  - section 9, the `data_backup_nightly` row;
  - section 10, the new "Backups and recovery" block: the old defect with an example, the six
    steps, the continuity example, visibility, owner configuration, the restore runbook and limits.
    The direct-send paragraph and the closing recovery sentence were adjusted;
  - section 11, the Operations row.
  - New files are named in code font, not linked. `check_kt_docs.py` requires linked sources to
    exist at the declared revision (`15dcda1`). Link them at the KT bump after a commit.
- [PDF](../../../StockAgent-Three-Loops.pdf) rebuilt: 28 pages, no overflow; source SHA-256
  `79aa0102…`. Text extraction finds the new block on pages 19–21.
- [TEAM_TESTING_GUIDE](../../../TEAM_TESTING_GUIDE.md): 12-B made concrete (a `fetch` against the
  bucket; `clean: true`; records opened), new 12-G (the missing copy is visible, then satisfied)
  and 12-H (a flipped byte fails the drill), and the HT-10 note that email is not the off-site copy.
- [ARCHITECTURE](../../../ARCHITECTURE.md), [PRODUCT_MAP](../../../PRODUCT_MAP.md),
  [CODEBASE.md](../../../../CODEBASE.md) and
  [LEGAL_AND_COMPLIANCE](../../../LEGAL_AND_COMPLIANCE.md) (client-side encryption; the email and
  erasure-retention gaps).

## Rollout and rollback

Local implementation only. Deploying, setting Railway variables and creating a bucket all need the
owner's word. Setting a Railway variable also redeploys, so it belongs in a job-free window
(00:10–06:20 IST).

- **What a deploy alone changes:**
  - the job writes manifests and runs the drill;
  - the first night's continuity reads "not checked", because the old archives have no manifest;
  - `backup_status.json` appears;
  - the watchdog starts warning every morning that no off-site copy was ever confirmed. That
    warning is the acceptance criterion working, so deploy it knowingly, or together with the
    bucket.

  The email and 7-copy rotation behave as before, and old archives rotate out after 7 nights.
- **Owner steps:**
  1. Create a private bucket and a key scoped to it. Nothing is provisioned by code.
  2. Generate `BACKUP_ENCRYPTION_KEY` and store a second copy outside Railway.
  3. Set the `BACKUP_*` variables (KT section 10).
  4. After the first confirmed night, run `python -m services.data.restore fetch --dest <empty
     dir>` from a machine outside Railway, and record the result.

  Only that recorded restore moves production verification to `verified`. Until then, off-site
  recovery stays **unverified**.
- **Rollback:**
  - Unset `BACKUP_OFFSITE_TARGET` to stop uploads. The local archive, drill and email continue.
  - Or revert the commit. Pre-SA-007 code ignores the manifests and the status file.
  - Existing local backups are never deleted beyond the 7-copy rotation, the same as before.

## Open limitations and routed follow-ups

- **No real bucket was exercised.** The S3 adapter is proven against AWS's published signatures and
  an in-memory bucket, not against Backblaze B2 or Cloudflare R2. `BACKUP_S3_REGION` must match
  the provider's (default `auto`). This is the first production-verification step.
- **Key rotation is not supported.** Older copies need the key they were written with, so a
  rotation means keeping the old key until those copies age out.
- **Two gaps remain from D7.** The email copy is still plaintext, and an erased account survives in
  off-site copies until retention removes them (30 nightly copies by default). Both are recorded in
  the KT and LEGAL, and both are owner decisions.
- **Owner setup, deferred:** the bucket and key join the owner's end-of-PI setup list, with the
  Railway alerts, the OpenRouter key limit and Healthchecks.io.
- **Not run:** `scripts/docs/run_kt_checks.py`, which is broken since SA-005 and already routed to
  SA-031.

## Manifest and digests

- **Review input:** [SA-007-manifest.json](SA-007-manifest.json), SHA-256 of its LF bytes
  **`7c1d43d9fcecd34abe025adb84f1426ae276a68c7d9a1c24e5c54c0471a5d1ca`**. It lists 18 paths:
  - 8 code and configuration files: `services/data/backup.py`, `services/data/offsite.py` (new),
    `services/data/restore.py` (new), `core/ops/watchdog/checks.py`, `config/milestones.yaml`,
    `services/scheduler/python/scheduler.py`, `src/backend/shared/config/settings/base.py` and
    `requirements.txt`;
  - 3 new test files: `tests/unit/test_backup_recovery.py`, `tests/unit/test_backup_offsite.py`
    and `tests/unit/ops/test_watchdog_backup.py`;
  - 7 documentation files: the KT, the PDF, `docs/TEAM_TESTING_GUIDE.md`, `docs/ARCHITECTURE.md`,
    `docs/PRODUCT_MAP.md`, `docs/LEGAL_AND_COMPLIANCE.md` and `CODEBASE.md`.

  `python scripts/docs/kt_manifest.py verify docs/planning/PI-2026-09/evidence/SA-007-manifest.json`
  gives 0 mismatches. `git status` shows no other change, apart from the excluded files below.
- **Excluded,** because they are written after the manifest: STATE.json, HANDOFF.md and this
  receipt.
- **Full diff** against `cdec78f`:
  **`2e0a5656a9914c71848d9be41c5ecfd7f4a51ed2087a332b198c3f9bdf8ee383`**, 135,591 bytes over 17
  text files. The PDF is pinned by its blob, `799e9596…` (source `79aa0102…`).
- **To rebuild the diff:** take every manifest path except the PDF, sorted.
  - For a path tracked at the baseline, run `git diff --no-color --no-ext-diff cdec78f -- PATH`.
  - For a new file, run `git diff --no-color --no-ext-diff --no-index -- /dev/null PATH`.
  - Concatenate the bytes. The ignored `analysis_data/sa007/sa007_diff.py` does exactly this.
- **After a commit:** `verify --rev <commit>` compares against the commit instead.
