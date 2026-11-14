# CLEAN-002 — Shorten what every conversation reads

Priority: **P2** · Scope: **owner decision** of 2026-11-14 ("yes" to R6 of the
[profit-path review](../../../audit/2026-11-14-profit-path-architecture-review.md)) · Estimate:
**2 points** · Lane: **light** (documents only)

Status lives in [STATE.json](../STATE.json), not this card. No dependency. **Order:** after
[FIX-017](FIX-017.md).

## Why

Each conversation starts by reading the handoff and the state file. On 14 Nov `HANDOFF.md` was
549 KB in 7,505 lines, of which the "START HERE — resume checklist" section alone ran from line 741
to line 7404. `STATE.json` was 978 KB: about 669 KB of tasks and 271 KB of history, 211 KB of it
from before 31 Oct. Most of it is the record of finished work.

## Intended result

- **`HANDOFF.md` holds only what the next conversation needs:** the current handoff, the standing
  rules from the resume checklist (devices, pushes, documents, STATE splicing, owner setup), open
  items, and the last 14 days.
- **Everything else moves, word for word, to `HANDOFF-archive.md`** beside it. Nothing is rewritten
  or dropped.
- **STATE history older than 14 days moves to `STATE-history-archive.json`.** Tasks stay where they
  are: their receipts and production notes are still read by pending checks.
- AGENTS.md's "continue" steps name the archive files as "read only when a card points there".

## Acceptance criteria

- Every line of the old `HANDOFF.md` is in the new file or the archive, once (a script compares
  them); the same for STATE's history entries.
- `STATE.json` parses, and its tasks, pending checks and top-level fields are unchanged.
- Links into moved sections resolve; `scripts/docs/check_kt_docs.py` reports no error.
- A standing rule that contradicts AGENTS.md as changed on 14 Nov (the two review lanes, the backlog
  list) is corrected in the kept part, and the receipt lists each correction.

## Handoff

Receipt `evidence/CLEAN-002.md` with both files' sizes before and after. Accepted in its own
conversation when the checks above pass.
