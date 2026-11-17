# CLEAN-002 receipt — shorten what every conversation reads

Autopilot phase `1117-2317-p2` on the code-server, a `continue` from about 23:17 IST on Tue
17 Nov 2026. `main` was `8f47a0d`, one ahead of `origin/main` (`d2f45cd`); the tree was clean.
PR-035 is `blocked` on the owner's word, so CLEAN-002 was the first ready story.

**Lane: light.** Reason: documents and one documentation checker; nothing reads them in
production, and no buy, sell, size or grade changes. **Accepted without a fresh-session review**
(AGENTS.md step 4). Profit-path step: none; it runs because the owner decided it (14 Nov, R6 of the
profit-path review; moved up and tightened on 17 Nov).

Nothing in production was read or changed.

## Sizes, before and after

| File | Before (`8f47a0d`) | After |
|---|---|---|
| `HANDOFF.md` | 593,530 B, 8,058 lines | 9,419 B, 128 lines |
| its current section (first `#` section) | about 72 KB on 17 Nov | 5,094 B (limit 8,192 B) |
| `HANDOFF-archive.md` (new) | — | 589,245 B |
| `STATE.json` | 1,069,016 B | 821,624 B |
| `STATE-history-archive.json` (new) | — | 250,220 B |
| STATE `next_phase` | 471 characters | 363 characters (limit 600) |
| STATE `history` | 316 entries | 69 + this phase's 1 |
| STATE `pending_production_checks` | 12 rows, 7 of them passed | 5 rows, none passed |

## What moved, and where

- **HANDOFF.md** keeps: a new current section (which file holds what, now, what waits for the
  owner, the dated watches), PR-035's dated entry word for word (its story is not accepted), and
  the standing rules that opened "START HERE — resume checklist, in order" (old lines 1273–1314)
  under a new heading "START HERE — standing rules", with one corrected line and one added bullet
  (below).
- **HANDOFF-archive.md** holds, word for word and in the old order (newest first), every other
  line: the old first heading, the 17 Nov to 9 Nov entries, the "START HERE" heading and its dated
  entries from November back to September, and the September sections. A short note opens the file
  and says where future entries go.
- **STATE-history-archive.json** holds, word for word: the 247 history entries dated before
  3 Nov 2026 (older than 14 days), newest first as in STATE; the 7 passed rows of
  `pending_production_checks` (FIX-030-M1, FIX-032-P1, PR-011-P1, SA-039-P1 to P3, PR-003-P1); and
  the replaced `next_phase` text. A `moves` list records this move.
- **Tasks stay in STATE**, unchanged apart from CLEAN-002's own entry.
- **PR-033 and PR-034** read `pending_production_checks`. Their cards were read first: both need
  the open (waiting, needs-eyes) rows, which stay. PR-033's card now says where the passed rows
  went, in case a story's outcome needs its earlier pass.

## Corrections to the kept rules

The card asks for each kept rule that contradicts AGENTS.md as changed on 14 Nov (the two review
lanes, the backlog list) or on 17 Nov (the PDF is not built with a story). **None of the kept rules
did.** Two edits were made for facts that had changed:

1. Old line 1284, "`analysis_data/` (ignored), laptop only" became "only on the device that wrote
   it": since 17 Nov the code-server holds PR-035's probe and this card's scripts.
2. Added: a bullet "The code-server" saying that its sessions commit after the checks pass and
   push `main` without asking only in the overnight window, under the owner's standing
   instructions kept outside the repository, so another device fetches before writing STATE or
   HANDOFF.

## Other changes

- **AGENTS.md** step 1 names the two archive files as "read only when a story points there"; step 5
  says which file holds what (receipt: the detail; HANDOFF's current section: now and next, at most
  8 KB, a dated entry archived at acceptance; STATE: status and one line of history, `next_phase`
  at most 600 characters, older history and passed checks archived). The first lines of the new
  HANDOFF say the same.
- **`scripts/docs/check_kt_docs.py`** also checks the links in `HANDOFF-archive.md`, so links into
  moved sections stay checked.
- **The PI README**'s start line names the archives.
- **BACKLOG B-9:** `setup_dev.sh --check` says READY when Chromium is on disk but cannot start (found
  by this phase's first suite run; see Checks).

## Checks

- **HANDOFF, every line once** (`analysis_data/clean002/verify_handoff.py`, independent of the
  splitter): the old 8,058 lines = 7,998 in the archive's body, in order with only removals, + 60
  in HANDOFF.md (59 word for word, 1 corrected: old line 1284, the only one listed). Current
  section 5,094 B, under 8 KB.
- **STATE** (`analysis_data/clean002/verify_state.py`), against the copy taken just before the move
  and again at the end against `8f47a0d`: it parses; key order kept; top-level fields unchanged
  except `next_phase` (old text archived) and this phase's `next_task`, `active_task` and
  `updated_at`; no task changed but CLEAN-002; history before = kept + archived, word for word
  (316 = 69 + 247), cut exactly at 3 Nov; pending rows: the kept and moved split is exactly the
  passed split, word for word (12 = 5 + 7); `next_phase` under 600.
- **Both checkers catch a fault:** a line deleted from the archive, a kept line changed, a line
  dropped from HANDOFF.md, and one archived history date changed were each reported; the files were
  then restored byte for byte and passed again.
- `check_kt_docs.py`: `errors: []`, 835 local links checked, `pdf_fresh: false` as intended since 17 Nov. `check_broad_except.py`: OK (148).
- **Full suite** on the commit: 6,749 passed / 12 skipped / 1 xfailed / 0 failed, return code 0, 6m26s (23:34:42-23:41:08 IST), on the working tree over `8f47a0d`; `scripts/docs/check_kt_docs.py`, the one non-document file changed, had the same sha256 (`08042fbdf1a5`) before and after, and the files committed are the files tested. A first run (23:27-23:30) had 2 failures, the two real-browser tests: Chromium could not start on the code-server for lack of system libraries (`libglib-2.0.so.0`). After `sudo npx playwright install-deps chromium` both passed alone (2 passed, 3m12s), then the whole suite above. The setup check's gap is BACKLOG B-9.

## Scripts (ignored `analysis_data/clean002/`, on the code-server)

sha256, first 12: `archive_state.py` `67042a629831`, `split_handoff.py` `c47a1c028e5d`,
`splice.py` `1cc5e402e990`, `verify_state.py` `a2aef7859bbc`, `verify_handoff.py` `96826fb8089b`,
`context_at_first_edit.py` `2d0307e58a56`. On another device, rebuild from this receipt: the line
ranges and the 3 Nov cut are above.

## The card's measure: context before the first repository edit

17 Nov's ten conversations: 92,000 to 258,000 tokens (median about 127,000). Read from each
session's transcript (`context_at_first_edit.py`: input plus cached tokens of the assistant turn
that made the first repository edit):

| Conversation | Read | Context at first edit |
|---|---|---|
| Autopilot phase 1 (PR-035), 17 Nov | the old files | 207,687 |
| This phase (CLEAN-002), 17 Nov | the old files, in parts | 112,622 |
| Autopilot phase 3 (FIX-015), 17 Nov | the new files | 116,069: 41,301 at its first call, 57,200 once AGENTS.md, HANDOFF, STATE's fields and the card were read; the rest was FIX-015's code, read before the story was marked active |

## Changed files

| File | Change | sha256 (first 12) |
|---|---|---|
| `AGENTS.md` | steps 1 and 5 | `f4b2ae635fda` |
| `scripts/docs/check_kt_docs.py` | checks the archive's links too | `08042fbdf1a5` |
| `HANDOFF.md` | rewritten: current section, PR-035's entry, standing rules | `1e6289bac2f8` |
| `HANDOFF-archive.md` | new: the rest of the old HANDOFF.md, word for word | `f78951a01702` |
| `STATE.json` | history, passed checks and `next_phase` moved; CLEAN-002 accepted; `next_task` FIX-015 | `ea13d184203a` |
| `STATE-history-archive.json` | new: 247 history entries, 7 passed checks, the old `next_phase` | `a2b185d75dcf` |
| `README.md` | the start line names the archives | `92500c385d52` |
| `BACKLOG.md` | B-9, the setup check | `e34907bd7164` |
| `stories/PR-033.md` | where the passed rows went | `0cf991e1a161` |
| `evidence/CLEAN-002.md` | new: this receipt | — |
