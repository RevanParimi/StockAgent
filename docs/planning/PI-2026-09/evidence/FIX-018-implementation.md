# FIX-018 — implementation receipt

**Story:** [FIX-018](../stories/FIX-018.md): the switch gate sets aside a decision whose result can
never be known, named and within a cap.

**Phase:** implementation, 29 Oct 2026, about 20:23–21:50 IST. Session `stockagent-main-49`, a new
conversation opened with "continue". FIX-016's implementation, reviews and reworks were other
conversations. The peers `-5d`, `-4f`, `-8a` and `-f0` were idle at the start and before the
bookkeeping (ListAgents). This phase includes a same-conversation self-review, which is not the
fresh review.

**Baseline:** HEAD `466a907` (FIX-016's docs commit; `aa29f69` holds FIX-016, `2d290d5` PR-009).
`main` is 4 commits ahead of `origin`; the owner holds the push until this story is accepted. The
working tree was clean.

**Status after this phase:** `review_required`. Nothing was committed, pushed, deployed or
configured. No production state was read, no NSE list or model was called and no message was
sent: every test fakes NSE, Yahoo and the registry.

## In one example

The shadow has made 16 decisions past 30 sessions. On 15 the evidence rule was right on 9 at
+2 each and wrong on 6 at −1: (18 − 6) / 15 = +0.80 a decision. The 16th sold a stock that
demerged 40% of its value three sessions later; NSE's row says only "Demerger".

- **Before:** the 16th had no result at either horizon, so the money check failed every week,
  for good, whatever the other 15 showed.
- **Now:** no later read can give it a result, so it is set aside at both horizons. The gate
  judges the 15 (a pass, "not worse"), and the scorecard line ends: "Set aside, as its result can
  never be known: S15, decided 2026-08-20: NSE lists a demerger ex 2026-08-25, after the
  decision's close (2026-08-20), and no ratio puts the horizon close in the decision's price
  basis across it." (the story file's first real-path test). A second such decision makes 2 of 17 (12%), above the 10% cap: "cannot
  judge", which is never a pass.
- **A failed read is not that.** Had NSE's list for the 16th merely failed to load that Sunday,
  it would count as not right with an unknown result, and the week fails, as before.

## What changed

1. **Two kinds of "no result"** ([exit_shadow.py](../../../../core/portfolio/exit_shadow.py)
   `horizon_in_basis`, `grade_disagreements`). `horizon_in_basis` returns
   `(close, note, gap, kind)`; each ungraded grade stores `no_result`: `lasting` or `temporary`.
   - **Lasting:** NSE's list read and empty; a list starting after the decision's close; a bonus
     or split ex between the close's bar and the review day; a share-count row not read as a
     ratio, or two ratios on one day, ex by the horizon close's bar; a change no ratio converts or
     a row of no known kind ex by the horizon's bar or the review day; a registry basis change
     (`registry_break`).
   - **Temporary:** the list could not be read, or holds rows but none dated; no close, an
     undated close, a close from before the decision, no benchmark, any other exception; a
     Yahoo-only close with a bonus, split, unread row or change no ratio converts ex after its bar.
   - **Order:** the first cause found decides. The close's checks (undated, too early) now run
     before the list's, so a decision is lasting only on a close and a list that were both read.
2. **The gate sets aside and caps** (`gate_look`, `scorecard_text`; constants
   `GATE_MAX_SET_ASIDE = 2`, `GATE_MAX_SET_ASIDE_PCT = 10.0`, `CANNOT_JUDGE`, `LASTING`,
   `TEMPORARY`, fixed with this date, before any shadow row exists).
   - A decision past 30 sessions with a lasting gap at 10, at 30 or at both is set aside at both.
     The look stores `matured` (all past 30 sessions), `judged` (the rest) and `set_aside`
     (date, symbol, reason). Every other check runs on the judged decisions.
   - Beyond the cap (more than 2, or more than 10% of `matured`; whole-number comparison, 2 of 20
     allowed), a look that would pass is `cannot_judge`, with the reason. A look that fails or
     has too few keeps that status. `recommends` is unchanged and needs two passes.
   - The not-enough reason adds ", not counting N set aside"; the line names each decision set
     aside with its decision day and reason.
3. **Grading tells a failed read from an empty list**
   ([corporate_events.py](../../../../services/data/fetchers/corporate_events.py),
   [results.py](../../../../core/portfolio/results.py),
   [corp_actions.py](../../../../core/portfolio/corp_actions.py)).
   - New `read_corp_actions(symbol)`: NSE's rows, `[]` only for an empty answer; raises when no
     client, the request fails or the answer is neither a list nor `{"data": [...]}`.
   - `fetch_corp_actions` now wraps it and returns `[]` for any failure, so the holding sync
     receives exactly what it did (FIX-017 changes the sync).
   - `results.corp_actions_fn` reads with `read_corp_actions`; a failed read is `None`, logged
     and kept for that scorecard (one read per stock, failures included).
   - `ActionRecord.rows` (new, default 0): how many rows NSE returned, dated or not, so an empty
     answer is told from a list of undated rows.
4. **T1 routed from FIX-016's re-review 3:** two rows in FIX-016's wording table, "Bonus 1:1 And
   Face Value From Rs 10 To Rs 2" and "Bonus 1:1 (Face Value Rs 10 To Rs 2)", each unread. The
   reviewer's mutant `ratio_words_pooled` now fails the story files.
5. **Docs:** KT section 6 (the two kinds, the set-aside rule, the cap and its table, why; limits:
   the population has no window, an empty list taken as lasting, the evidence rule selling on the
   event that sets a decision aside) and section 7's exit-rule row; PDF (60 pages); CODEBASE rows
   for `corp_actions.py`, `exit_shadow.py`, `corporate_events.py`; guide 07-L (count the
   disagreements on a stock with an empty list) and 09-H (set aside, a failed read, the cap), with
   status lines.

## Decisions (implementer's, recorded for the review)

- **F18-D1, how the fetch tells failure from empty** (the card left it to the implementer): a
  strict `read_corp_actions` that raises, and `fetch_corp_actions` as its never-raising wrapper.
  An answer of no known shape is a failed read: an unknown answer must never be taken for an
  empty list, the only failure-shaped lasting cause.
- **F18-D2, precedence:** the first cause in a fixed order decides, and the close is checked
  first. FIX-016 checked the list before the close's date; that order would have made an empty
  list beside an undated close lasting. Now a temporary cause found first keeps the grade
  temporary (it can only fail the week); a lasting cause is reported only on a close and a list
  that were read.
- **F18-D3:** a list holding rows but none dated is temporary: NSE may date a row later (KT
  limit). Hence `ActionRecord.rows`.
- **F18-D4:** a row not read, or a change no ratio converts, ex after the horizon's bar matters
  only under a Yahoo-only close; that is temporary, like the card's Yahoo-only bonus.
- **F18-D5:** the card's row "any size with 3 set aside: cannot judge" is read with its rule 3:
  "cannot judge" replaces only a pass, so 10 judged with 3 set aside is "not yet" and a failing
  population with 3 set aside fails. The three acceptance populations (20, 30 and 50) are
  "cannot judge".
- **F18-D6:** a set-aside decision's reason is its first lasting grade's, 10 sessions before 30,
  in full (the card's "a demerger ex 12 Nov" is an example of the content). The cap's two bounds
  are reported separately, the count first.
- **F18-D7:** a missing close, a missing benchmark or any exception is temporary even when a
  lasting cause would be found once the close is read. The registry is asked, as before, once a
  horizon close is in basis; where the registry's new code has a close, the decision is set aside
  (the card's "unless the registry records a new basis").

## Changed contracts (FIX-016's and PR-009's story files)

No assertion was relaxed. In `tests/unit/test_exit_fix016.py`:

- the by-hand tables of `horizon_in_basis` (`test_the_price_basis_rule_by_hand`,
  `test_a_change_no_ratio_converts_is_no_result_by_hand`) compare 4-tuples: each existing case
  keeps its close, note and reason and gains its kind, worked by hand; the one reason "is empty or
  was not read" becomes "could not be read" (None) and "is empty" (an empty record); five cases
  are added (a list of undated rows; an unread row between the closes under Yahoo's close, lasting;
  a quote undated or too early beside a lasting cause, temporary, twice; a demerger on the
  horizon's bar under Yahoo's close, lasting);
- `test_a_basis_that_cannot_be_established_is_no_result_and_never_helps`: S15's list now fails to
  load (`_Market.nse_fails`, new) instead of coming back empty, which is now set aside (pinned in
  the new file); every earlier assertion holds, plus `no_result` temporary and nothing set aside;
- `test_rr2_one_demerger_no_longer_passes_a_losing_rule[True]`, `test_rr2_q5_…` and
  `test_rr2_q3_…` (2 cases): the decision with a lasting gap is set aside, so the gate reads
  "not yet" (14 judged of the 15 it needs, "not counting 1 set aside") instead of failing on an
  unknown mean; right still 8 at both horizons, the mean of the 14 −1.00 by hand, nothing
  recommended the week after (each still the defect's opposite: none passes);
- two read spies move from `corp_actions.fetch_corp_actions` to
  `corporate_events.read_corp_actions` (grading's read); the reads they count are unchanged;
- T1's two rows in `OTHER_ROWS`.

PR-009's file is unchanged and passes: its grades carry no `no_result`, and its tally comparison is
untouched (the tally gains no key).

## Tests

- New [tests/unit/test_exit_fix018.py](../../../../tests/unit/test_exit_fix018.py), 37 tests:
  - **the card's table by hand** (12 populations): every row of the card, lasting at 10 only and
    at 30 only, 3 set aside at 20, 30 and 50, a failing and a short population with 3 set aside;
    each status, `matured`, `judged`, reasons, the named decisions and the mean, and the status
    FIX-016's rule gave (fail; not enough for the 13);
  - **an independent oracle** in exact fractions over 2,000 random populations (pass 117, better
    88, fail 794, not enough 1,025, cannot judge 64; 89 passes with one or two set aside): equal
    status and label; no pass above the cap; a set-aside decision weighs exactly as if absent
    except through the cap; a graded horizon made temporary never turns a non-pass into a pass and
    turns a judged pass into a fail;
  - **through FIX-016's real price path:** a demerger between the closes set aside, the 15 pass
    and recommend two weeks running, FIX-016's rule failed them; two set aside of 17 cannot be
    judged and recommend nothing; an empty list set aside, a failed read fails the week, read the
    next week it is graded; a Yahoo-only close fails the week until NSE answers; graded at 10 with
    a lasting gap at 30 set aside at both (its right 10-session grade not counted); a registry
    demerger lasting, a rename graded; a missing close, a missing benchmark or an unread list
    temporary;
  - **random markets** (6 × 25 decisions, 300 grades: 149 graded, 103 lasting, 48 temporary):
    swapping which rule sold leaves every grade's status, kind and reason and the set-aside list
    the same; once NSE's close answers every day and every list is read, each lasting gap is
    unchanged with its reason, and each temporary one is graded (30) or lasting (18), none
    temporary;
  - **the read:** `read_corp_actions` over 11 answers (empty list, empty `data`, rows, a failed
    request, a timeout, `{}`, `{"data": None}`, `None`, a page of HTML, no client): rows or a
    raise; `fetch_corp_actions` `[]` for every failure; the real sync gives the same result and
    record for a failed read and an empty list; `corp_actions_fn` reads each list once, failures
    included, and the two kinds follow.
- Story files: FIX-018 37 + FIX-016 127 + PR-009 39 = **203 passed**; with the fetcher's and the
  sync's own files 225 passed.
- **Mutants** (`analysis_data/fix018/mutants.py`, ignored; FIX-016 rework 3's in-memory harness
  over the three story files): **43 of 43 caught**, baseline clean (203 passed). Set aside:
  temporary taken as lasting, lasting only at 30, only at both, none set aside, set aside but
  still counted (and in `right`). Cap: none, 3, 10% inclusive, 10% of the judged, 10% dropped;
  "cannot judge" replacing a fail, counted as a pass now or the week before, labelled better.
  Naming: the 30's reason, the line without the names, the short reason unnamed. Kinds: each
  cause flipped (empty, unread, undated rows, late list, stored, unread and change after the
  bar, Yahoo, two ratios, registry, exception), the list checked before the close, the kind not
  stored. The read: a failed read as an empty record or not cached, grading through the sync's
  fetch, `rows` not counted, an unknown answer or a `dict` without `data` as empty, the sync's
  fetch raising. T1's `ratio_words_pooled`.
- **Full suite:** 5,875 passed, 12 skipped, 1 xfailed, 0 failed (18m53s, after the mutant run). The
  suite left no runtime data changed (`git status` lists only this phase's files).
- `check_broad_except`: OK (151 grandfathered). `check_kt_docs`: errors `[]`. PDF: 60 pages,
  source SHA-256 `7231fcda` (the KT's LF bytes).

## Review input

- Manifest [FIX-018-manifest.json](FIX-018-manifest.json): 10 files, review input
  `c2e15877fd2a604f53990803348a1a57e9950aeed727fd264b5b079621680534` (`kt_manifest.py verify`:
  0 mismatches). Files: `CODEBASE.md`, `core/portfolio/corp_actions.py`,
  `core/portfolio/exit_shadow.py`, `core/portfolio/results.py`, `docs/StockAgent-Three-Loops.pdf`,
  `docs/TEAM_TESTING_GUIDE.md`, `docs/TECHNICAL_DESIGN.md`,
  `services/data/fetchers/corporate_events.py`, `tests/unit/test_exit_fix016.py`,
  `tests/unit/test_exit_fix018.py` (new).
- Diff: `6769cab1ec58afd0212d76cde704bb9f4a1e8a6a0c95180c634fb159c70a76f4`, 130,281 bytes, 9
  paths (`analysis_data/fix018/digest.py`, ignored: every manifest path but the PDF against HEAD
  `466a907`, the new test file against `/dev/null`).
- Bookkeeping outside the input: this receipt, STATE and HANDOFF.

## For the fresh review (the card's hard-review questions)

- **Can what the evidence rule did or read decide which decisions are set aside?** Classification
  reads only the close, NSE's list, the registry and the dates; the swap test pins it. The rule
  may still sell on a scheme or demerger announcement, the event that sets the decision aside: a
  KT limit, bounded only by the cap.
- **Is the cap the only route by which a missing result can help?** The oracle test's "as if
  absent" invariant: with the cap held, the look equals the look without those decisions;
  beyond it, only a pass changes, to "cannot judge".
- **Can a temporary gap be taken for a lasting one?** A failed read is `None`, never an empty
  record (`failed_read_is_empty` mutant); an unknown answer raises; the close is checked first;
  the repair invariant shows no lasting gap depends on a failed read.
- **Can "cannot judge" count toward the two-week run?** No: `recommends` needs two passes; the
  text test and two mutants pin both directions.
- **Not in this story:** the holding sync's `[]` for both (FIX-017); stale codes (FIX-019); a
  stock whose close stays missing still fails the money check.
