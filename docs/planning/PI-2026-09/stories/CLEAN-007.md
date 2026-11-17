# CLEAN-007 — The nightly backup stops emailing the archive

Priority: **P1** · Scope: **owner request** of 2026-11-17 ("lets remove the backup email
completely, it is consuming my email storage a lot, we dont need to worry about backups anymore
until we need them in future") · Estimate: **1 point** · Lane: **light** (operations; no buy, sell,
size, grade or account-data path reads it)

Status lives in [STATE.json](../STATE.json), not this card. No dependency. Profit-path step:
**none**; it runs because the owner asked for it.

## Why

Each night at 23:30 the backup job built an archive of `data/` and mailed it to the owner. The
archive was 9 MB in September and 19.5 MB on 16 Nov, so the mail took about 20 MB of mailbox a
night. The owner asked for it to stop.

## What changes

- `services/data/backup.py`: the nightly job no longer sends any email. The size limit for the
  mail, the `emailed` field of `backup_status.json` and of the job's summary are gone.
- `services/scheduler/python/scheduler.py`: the job's comment and log line no longer speak of an
  email.
- Kept, because they cost nothing and send nothing: the archive, its restore drill, the seven
  local copies under `data/backups/`, and the off-site copy for the day a bucket is configured
  (SA-007's deferred setup).
- Kept: attachments in `core/delivery/channels.py`. No caller sends one now; removing the
  parameter would touch the sender of the morning brief for no gain today.

## What the owner gives up

With SA-007's bucket not set up, the mail was the only copy outside the Railway volume. After
this change **no copy exists outside the volume.** Example: if the Railway volume were deleted,
the paper book's ledger and its seven archives would go together. The owner accepted this on
17 Nov. The weekly watchdog line "No off-site copy has ever been confirmed" keeps saying so until
a bucket is configured; removing that line is a registry edit the owner approves separately.

## Acceptance criteria

- With email fully configured and working, the nightly job opens no SMTP connection and posts
  nothing to Resend (both transports tested).
- The archive, the drill, the rotation, the off-site step and the watchdog's
  `backup_recoverable` check behave as before.
- KT section 10, the legal note and the testing guide (case 12-L) say that nothing is emailed and
  what that leaves; BACKLOG B-7 is closed.
- The full suite and the project guards pass.

## Rollout

The email stops with the deploy of this commit: a push at the owner's word, in a job-free window
before 23:30 for it to take effect the same night. The mails already in the mailbox are not
touched by the code; the owner deletes them (Gmail search: `subject:"StockAgent nightly backup"`).
