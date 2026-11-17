# CLEAN-002 — Shorten what every conversation reads

Priority: **P2** · Scope: **owner decision** of 2026-11-14 ("yes" to R6 of the
[profit-path review](../../../audit/2026-11-14-profit-path-architecture-review.md)), moved up and
tightened by the owner on 2026-11-17 · Estimate: **3 points** (2 before the tightening) · Lane:
**light** (documents only)

Status lives in [STATE.json](../STATE.json), not this card. No dependency. **Order:** right after
[PR-035](PR-035.md) (owner, 17 Nov 2026; it was after FIX-017).

## Why

Each conversation starts by reading the handoff and the state file. On 14 Nov `HANDOFF.md` was
549 KB in 7,505 lines, of which the "START HERE — resume checklist" section alone ran from line 741
to line 7404. `STATE.json` was 978 KB: about 669 KB of tasks and 271 KB of history, 211 KB of it
from before 31 Oct. Most of it is the record of finished work.

**Measured again on 17 Nov 2026**, in the owner's review of what a `continue` costs:

- Ten recent `continue` conversations stood at 92,000 to 258,000 tokens of context before their
  first repository edit (median about 127,000). About 49,000 are there before anything is read.
- `HANDOFF.md`'s current section alone was 72 KB: 23 dated entries for 11 to 17 Nov. Keeping "the
  last 14 days", as this card first said, would keep more than that.
- `STATE.json` was 1,074 KB, 89% of it finished work (660 KB of done tasks, 294 KB of history).
  `next_phase` was one sentence of 8.6 KB, and 7 of the 12 rows in `pending_production_checks`
  had already passed (15 KB of 21 KB).
- **The cause:** each phase writes the same event in four places: the assistant's own note, the
  handoff, STATE (history and `next_phase`) and the receipt. The assistant's note (181 KB, outside
  the repository) was cut to the current state the same day. This card does the repository's part.

## Intended result

- **One place for each fact.** The receipt holds the detail of a phase: tests, manifest, digests,
  findings. `HANDOFF.md` says what is true now and what comes next. `STATE.json` holds status
  fields and one line of history for each event. AGENTS.md's step 5 says which file holds what, in
  place of "update STATE.json, HANDOFF.md and the receipt together".
- **The current handoff is one screen, at most 8 KB:** what the next conversation does, what is
  uncommitted or held, what is being watched and from which date, and what waits for the owner. A
  dated entry moves to the archive when its story is accepted. There is no "last 14 days".
- **The standing rules** from the resume checklist (devices, pushes, documents, STATE splicing,
  owner setup) stay, directly under the current handoff.
- **Everything else moves, word for word, to `HANDOFF-archive.md`** beside it. Nothing is rewritten
  or dropped.
- **STATE history older than 14 days moves to `STATE-history-archive.json`,** and so do the rows
  of `pending_production_checks` whose status is `passed`. Tasks stay where they are: their
  receipts and production notes are still read by pending checks. [PR-033](PR-033.md) and
  [PR-034](PR-034.md) read that list: read their cards before moving a row, and keep what they
  need to find.
- **`next_phase` is at most 600 characters:** the next conversation's first step and a pointer to
  the handoff.
- AGENTS.md's "continue" steps name the archive files as "read only when a card points there".

## Acceptance criteria

- Every line of the old `HANDOFF.md` is in the new file or the archive, once (a script compares
  them); the same for STATE's history entries and for the moved rows of
  `pending_production_checks`.
- `STATE.json` parses. Its tasks are unchanged. Its pending checks are unchanged except that the
  passed rows have moved. Its top-level fields are unchanged except `next_phase`, whose old text is
  in the archive.
- The current handoff section is at most 8 KB and `next_phase` at most 600 characters.
- AGENTS.md's step 5 names which file holds what, and the first lines of the current handoff say
  the same, so a conversation that reads only the handoff still follows it.
- Links into moved sections resolve; `scripts/docs/check_kt_docs.py` reports no error.
- A standing rule that contradicts AGENTS.md as changed on 14 Nov (the two review lanes, the backlog
  list) or on 17 Nov (the PDF is not built with a story) is corrected in the kept part, and the
  receipt lists each correction.

## Handoff

Receipt `evidence/CLEAN-002.md` with both files' sizes before and after. Accepted in its own
conversation when the checks above pass.

**One measure for the conversation after this one:** its context size before its first repository
edit, to set beside the 17 Nov figures. The script that produced those figures is
`analysis_data/review_20261117/session_cost.py` (on the laptop only). Without it, read the same
number from the conversation's log: the context tokens at its first Edit or Write.
