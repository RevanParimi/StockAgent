# PR-018 receipt — the monthly conviction check, with its rule for trusting conviction

**Status: accepted, 27 Nov 2026** (light lane, without a fresh-session review).

Autopilot `1127-2012-p2` on the code-server, Sonnet at xhigh, Fri 27 Nov 2026 from about 20:12 IST.
Nothing in production was read, changed, deployed, run or sent.

**Lane: light** (the card and STATE): a report on the `dive` rows PR-017 grades. No code that buys,
sells or sizes reads it, and no grade and no ledger figure changes; the Opus check looked for such a
path, and for a way another account or a model prompt could see the new fields, and found none.
Profit-path step: **measure** (the owner can see whether a higher conviction did better before any
sizing follows it).

Base revision `5d83226`; committed to `main` with these records. Diff digest `5c22061654a93867` (sha256,
first 16, of `git diff --binary 5d83226 <commit>` over every path except STATE and HANDOFF with
their archives, BACKLOG and this receipt).

## What was built

| Path | What it does |
|---|---|
| `core/audit/ideas.py` | the check, pure: the four groups, the table, the looks and the rule, and the line's words |
| `core/portfolio/results.py` | on a week whose Sunday is the 1st to the 7th, the default user's row gains `conviction_check` and a "Conviction check" line; each look is stored in that row with the dives it read |
| `core/audit/report.py` | the audit report's idea block carries the same table; the older shelf calibration line now says it reads shelf ideas |
| `tests/unit/test_conviction_check_pr018.py` (new) | 57 tests, every expected figure worked by hand |
| KT section 7 (the check; the scorecard table), guide 09-M, EDGE-ROADMAP section 7 | current design |
| `docs/architecture-map/model.json`, `TREES.md` | regenerated (line counts and one import); no curated change, so the page is not rebuilt |

`conviction_calibration` and `calibration_spread` are unchanged for their callers (card, item 2).

## Decisions (taken as recommended, CLAUDE.md section 2)

- **D1. The groups.** "Rejected, under 0.55" is any recorded verdict under 0.55. The three groups
  above hold **BUY dives only**: sizing by conviction applies to buys. A dive at 0.55 or more not
  rated a BUY is in no group and is counted. A boundary goes to the higher group, and the line says
  "0.55 to under 0.65".
- **D2. What a look is.** A monthly check at which each compared group holds 30 or more dives no
  other look has read. It uses up every unread dive. A month without that many is no look: it neither
  counts nor breaks the run. A failed look restarts the run. This reading keeps "n of 30 each" and
  "no row in two looks" together and can still happen. Disjoint calendar months could hardly ever
  reach 30 in the top group.
- **D3. Looks are stored, never recomputed.** Each lives in that week's scorecard row with the dives
  it read, so a grade written late cannot change a look already shown. A stored pass stays.
- **D4. Judged as printed.** The gap is taken from the two means to two places (after the Opus
  check's finding 4: unrounded, a line could read "+4.30 against +2.30, a gap of +1.99: not passed").
- **D5. The 300-dive statement.** "Flat or negative" is a gap under the 2 points; negative is said
  as "higher conviction did worse". No conclusion is printed while the latest look passed.
- **D6. Fixed in code.** The edges and the rule are constants, not settings, and the shelf's floor
  setting does not move them. The owner may change the 2 points before the first look.
- **D7. The default user's scorecard only:** dive grades are kept in that store alone.
- **D8.** Each group says how many stocks its dives are of (Opus finding 1).
- **D9.** The product text names no card ids. This receipt and STATE name PR-029, 024, 025 and 012.

## Acceptance criteria

| Criterion | Test | Result |
|---|---|---|
| The line's figures equal the audit report's for the same rows | `test_the_lines_figures_equal_the_audit_reports_for_the_same_rows` | Four groups, worked by hand, in the line, the report's block and its text |
| A fixture for each outcome: pass, too few, flat | `test_two_passing_looks_in_a_row_pass_the_rule`, `test_29_in_one_group_is_too_few_for_a_look`, `test_a_flat_gap_does_not_pass_and_at_300_dives_is_said_plainly`, and negative and too-few-at-300 | As stated |
| No row counted as two looks | `test_a_dive_a_look_has_read_is_never_read_by_another`, the late-grade, late-built-week, stored-looks and provisional-week tests, and a run through `weekly_scorecard` | Looks' dives are disjoint |
| Living documents: KT section 7, the testing guide | KT section 7, guide 09-M | `check_kt_docs.py`: errors [] |

## The Opus check (Sonnet builds, Opus checks)

A fresh Opus subagent at xhigh reviewed the diff, read-only, on a scratch copy: the new and related
tests, edge probes and 11 planted bugs. **Verdict: safe to commit as is.** No high finding.

| # | Severity | Finding | What was done |
|---|---|---|---|
| 1 | medium | The card's rule counts dives, not stocks (re-dives overlap), and looks never stop, so a conviction with no information can pass by chance over many looks | Each group now shows its stocks. The rule is the card's, so it is unchanged: **the owner's, before the first look** (BACKLOG B-54) |
| 2 | low | BUY groups use the composite's band; the shelf also asks for the model's BUY | Said in the module and KT (B-55) |
| 3 | low | A gap of +1.9 read "flat", and a conclusion could print beside a passing look | Reworded "short of the 2"; no conclusion while the latest look passed |
| 4 | low | Rounding could print figures that did not subtract to the gap | Judged on the printed means (D4) |
| 5 | low | Five planted bugs survived the tests | Tests added; all are caught |
| 6 | nit | A week built late could withdraw a pass | The stored pass is carried |
| 7 | low | Guide 09-M would not render as a table row | Fixed |
| 8, 9 | nit | KT wording; "BUY dives"; "no other look"; labels overlapping at 0.65 | Fixed |
| 10 | nit | The old shelf calibration line beside the new table | It now says it reads shelf ideas |
| 11 | nit | A damaged stored row can blank the whole scorecard | **Not fixed:** only a hand edit causes it; skipping a damaged look would let its dives be counted twice, other blocks behave the same, and the email says the scorecard could not be computed |
| 12 | nit | Nothing records a pass in STATE by itself | Watch row `PR-018-W1` |

Opus did not re-read the code after these fixes; the tests and planted bugs cover them.

## Tests and checks

- `tests/unit/test_conviction_check_pr018.py`: 57 passed.
- **Planted bugs:** before the Opus check, 18 of 19 caught; the float-noise one slipped through,
  its fixture was strengthened, then 19 of 19. After the fixes, a new set of 28 including Opus's
  survivors: 25 caught; three were masked by the stored pass date, direct tests were added, then
  28 of 28.
- Related files (scorecard, audit, idea lanes): 1,472 passed.
- `scripts/docs/check_kt_docs.py`: errors []. Map guard: `model.json` and `TREES.md` match.
- **Full suite through the memory guard**, on the final code (a fingerprint of `core/`, the map
  files and the new test was the same before and after the rerun): main step **7,803 passed,
  5 skipped, 1 xfailed** (peak `anon` 1,180 MB). Browser step 60 passed, 1 failed: **B-53 again**
  (the map's search box, line 435, a 30 s wait), which this change does not touch. **Browser step
  rerun: 61 passed** (13m07s, peak 1,748 MB, no process left).
- Environment: code-server, `.stockai` Python 3.13.5, hermetic suite (no `.env`, no network).

## Limits

- Nothing is observed in production. The rule has had no look.
- "BUY" is the composite's band (B-55), and dives are not stocks (B-54).
- A dive seeded without a verdict is in no group (PR-017's seed).
- Found and left: PR-017's "Every deep dive" line reads "none graded yet" on a member's scorecard,
  where dive grades are never kept (B-56, display only).

## Production watch: `PR-018-W1`

From the first weekly review on a month's first Sunday after the deploy (Sun 6 Dec 2026, 18:00 IST,
if deployed by then; else Sun 3 Jan 2027), each month: the owner's scorecard has the "Conviction
check" line with every group's n and stocks; the audit report's block shows the same figures. If it
says the rule passed, record it in STATE and name **PR-029** ready to promote (the owner promotes).
If it gives the 300-dive flat or negative statement, ask the owner: PR-024, PR-025 or PR-012.
Reading production takes the owner's word in the same conversation; the owner also sees the line.
