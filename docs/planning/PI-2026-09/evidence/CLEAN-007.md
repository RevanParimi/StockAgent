# CLEAN-007 receipt — the nightly backup stops emailing the archive

Owner request, 17 Nov 2026 ("lets remove the backup email completely, it is consuming my email
storage a lot, we dont need to worry about backups anymore until we need them in future").
Session `stockagent-main-bf` [8282a6], a new conversation the owner opened with the request,
Tuesday from about 06:59 IST. `origin/main` and `main` were `62d36ce` after a pull; the peer `-35`
had just pushed FIX-032 and was idle from about 07:06, its records of that push uncommitted in
the tree and left as they were.

**Lane: light.** Reason: operations. The backup's email is read by no buy, sell, size or grade,
by no ledger arithmetic, and by no rule on who can read an account's data. **Accepted without a
fresh-session review** (AGENTS.md step 4). Profit-path step: none; it ran because the owner asked.

Nothing is committed, pushed or deployed. Production was not read or changed.

## What changed

| File | Change |
|---|---|
| `services/data/backup.py` | `run_backup_job` sends no email: the `send_email` call with the archive attached, `EMAIL_MAX_BYTES`, and the `emailed` field of the summary and of `backup_status.json` are removed. The docstring says the archive is never emailed |
| `services/scheduler/python/scheduler.py` | The job's comment says nothing is emailed; its log line drops `emailed=` |
| `core/delivery/channels.py` | One comment: the backup is no longer a direct sender |
| `tests/unit/test_backup.py` | The two tests that asserted the email are replaced by `test_nightly_job_sends_no_email_on_either_transport` (SMTP and Resend) |
| `tests/unit/test_backup_recovery.py` | The `no_email` fixture now fails the test on any send, where it used to swallow one |
| `tests/unit/test_backup_offsite.py`, `tests/unit/ops/test_watchdog_backup.py`, `tests/unit/test_scheduler_delivery_jobs.py` | The patches that muted the email are gone; the scheduler test's summary has no `emailed` |

Unchanged: the archive and its manifest, the restore drill, the rotation to seven local copies,
the off-site step (`services/data/offsite.py`), the status file's other fields, and the
watchdog's `backup_recoverable` check, which never read `emailed`.

**Left in place, by choice:** the `attachments` parameter of `send_email` and
`send_email_result`. No caller passes one now. Removing it would edit the function that sends the
morning brief, for no effect today; it can go with the next change to that file.

Code diff against `62d36ce` (`git diff HEAD -- core services tests`): sha256 `a164c087175d9bcc…`,
8 files, +78/−52. File digests (sha256, first 12):

| File | sha256 |
|---|---|
| `core/delivery/channels.py` | `f75b45b5a282` |
| `services/data/backup.py` | `3ff202175afc` |
| `services/scheduler/python/scheduler.py` | `0a0533299587` |
| `tests/unit/ops/test_watchdog_backup.py` | `85350a86ed23` |
| `tests/unit/test_backup.py` | `abafef7ef76c` |
| `tests/unit/test_backup_offsite.py` | `b7592609183d` |
| `tests/unit/test_backup_recovery.py` | `eb49e185fc55` |
| `tests/unit/test_scheduler_delivery_jobs.py` | `9e7d31188b4c` |

## What the owner gives up

With SA-007's bucket not set up, the mail was the only copy outside the Railway volume (and on
16 Nov it had already failed to go out, BACKLOG B-7). From the first night on the new code, **no
copy of the paper book exists outside the volume**: if the volume were deleted, the ledger and
its seven archives would go together. The owner accepted this in the request. The weekly watchdog
line "No off-site copy has ever been confirmed" continues, because it is true. Removing that line
is an edit to `config/milestones.yaml`, which the owner approves separately.

## Tests

- **The invariant** (`tests/unit/test_backup.py::test_nightly_job_sends_no_email_on_either_transport`,
  once per transport): email is switched on and fully configured, and fake SMTP and Resend
  transports record every send. A probe mail first proves the fakes do record. Then the nightly
  job runs: nothing is opened or posted, the archive exists and its drill passed, and neither the
  summary nor the status file has an `emailed` field.
- **On the code before the story** (`62d36ce`, a detached worktree, removed afterwards): 5 failed,
  27 passed. The invariant fails on both transports, and the three nightly-job tests in
  `test_backup_recovery.py` fail because the old job sends a mail into the fixture that now
  refuses one.
- **Focused:** the backup, off-site, recovery, watchdog, scheduler-job and delivery-channel files:
  141 passed.
- **Full suite:** 6,749 passed / 12 skipped / 1 xfailed / 0 failed, return code 0, 26m17s
  (07:12-07:38 IST), on the working tree over `62d36ce`. The eight code and test files had the
  same sha256 before and after the run. The count equals the last run's 6,749 tests (6,748 passed
  and one flake): two tests were removed and one test with two cases was added.
- **Guards:** `check_kt_docs` `errors: []` (13 documents, 818 local links, 73 PDF pages);
  `check_broad_except` OK (148 grandfathered).

## Documents

- `docs/TECHNICAL_DESIGN.md`: section 1's Backups row (production still tries the mail until the
  deploy); the job table; section 10: the direct senders, the backup steps (the email step is
  gone; a paragraph says what that leaves), the limits; section 11's planned investment track
  and section 12's rows for PR-035 to PR-039 and CLEAN-007 (PR-014's row now reads Done, as
  STATE does). PDF regenerated: 73 pages, source `a08f270e`.
- `docs/LEGAL_AND_COMPLIANCE.md`: where backups live; the unencrypted mail is no longer a gap.
- `docs/TEAM_TESTING_GUIDE.md`: case 12-L (no backup mail; the status file), and section 12's
  note.
- `CODEBASE.md`: the file tree's line for `backup.py`.
- `docs/planning/PI-2026-09/BACKLOG.md`: B-7 closed.

## Committed and deployed, 17 Nov 08:05 IST

Asked when to commit and push, the owner answered "Commit and push now" at about 08:03 IST.

- **Commits:** `73e0c29`, the 8 code and test files; each committed file's sha256 equals the
  bytes the full suite ran on. `7603e81`, documents only: this story's, the investment track's
  cards, and the earlier conversation's records of the FIX-032 deploy and PR-014's acceptance. The
  KT header names `73e0c29`; PDF 73 pages, source `a08f270e`; `check_kt_docs` `errors: []`.
- **Suite evidence for the push:** the 07:12-07:38 run above, on the same code bytes. No test
  reads the documents, so the suite was not run a second time on the committed tree; a second
  run would have ended after the 08:30 analysis job began.
- **Push:** `62d36ce..7603e81` at 08:05:11 IST. Railway deployment `6ea566ab` (commit `7603e81`)
  created 08:05:15, SUCCESS by 08:07:44; the previous `43790aa6` REMOVED; `/health` 200 at
  08:07:48 (one read of the deployment list and one request to `/health`).
- **Not read:** whether the 08:00 IPO refresh had finished before the restart; its second pass
  runs at 17:00.
- **Dated watch `CLEAN-007-W1`** (STATE `pending_production_checks`), from Wed 18 Nov: no
  "StockAgent nightly backup" mail for the night of 17 Nov; the status file names that night's
  archive with its drill passed and no `emailed` field.
- **The push record** (this section, STATE and HANDOFF, KT section 1 with "production runs
  `73e0c29`" and the Backups row, guide 12-L deployed, PDF 73 pages source `6b446816`) is one
  docs-only commit on `7603e81`, made at the owner's word ("go ahead commit and push", about
  08:14 IST). Its push is held to about 09:20 IST, after the morning jobs (08:15 to 09:00): it
  restarts the app and carries nothing production needs. If `origin/main` is still `7603e81`, it
  was not pushed.

## `CLEAN-007-W1` passed, Wed 18 Nov

- **The owner, about 07:05 IST:** no "StockAgent nightly backup" mail arrived for the night of
  17 Nov ("didn't receive mail").
- **Read-only, through `railway ssh` at about 07:15 IST** (the session that ran PR-035's probe;
  field names and counts only): `data/backups/backup_status.json` names
  `stockagent-backup-20261117-180000.zip` (18:00 UTC, the 23:30 IST run of 17 Nov), written at
  that time; its drill `ok` true with no errors and no warnings, continuity checked against the
  archive of 16 Nov; no `emailed` field. `data/backups` holds 7 archives, the newest those of
  15, 16 and 17 Nov.
- **Pass: both.** The row moved word for word, with its result, to
  `STATE-history-archive.json` (`pending_production_checks_passed`).

## The steps as planned before the owner's word

1. **Commit:** the 8 code and test files; then the documents, with the KT header's "Code
   inspected" set to the new commit.
2. **Push** in a job-free window. The mail stops with the first 23:30 run on the new code, so a
   push before 23:30 stops it the same night.
3. **After the deploy:** KT section 1's Backups row drops "production still tries the email
   copy"; testing guide 12-L reads "deployed"; add the dated watch `CLEAN-007-W1` to STATE
   `pending_production_checks`: the morning after, no "StockAgent nightly backup" mail, and
   `backup_status.json` names that night's archive with its drill passed and no `emailed` field.
4. **The mails already received** are not touched by any code. In the mailbox that receives them,
   search `subject:"StockAgent nightly backup"` and delete. (The Gmail account connected to this
   assistant holds none, so they went to another address.)
