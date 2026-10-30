# FIX-018 review receipt — the switch gate sets aside a decision whose result can never be known

## Fresh review: ACCEPTED (2026-10-29)

**Phase:** fresh-session review, a new conversation opened with "continue" (29 Oct, about
22:35–23:15 IST, session `stockagent-main-f2` [16b4d4]). FIX-018 was implemented in
`stockagent-main-49` [cd5405]. This conversation did not read that chat or any earlier one. The
peers `-5d`, `-4f`, `-8a`, `-49` and `-f0` were idle at the start and before the bookkeeping
(ListAgents).

**Verdict: ACCEPTED** for the reviewed revision below.

- Every acceptance criterion on the card holds.
- The four hard-review questions are answered below. Two answers rest on my own cases through the
  real stored scorecard and on the NSE client's code.
- No finding is critical, high or medium. Two low items are test gaps (T1, T2), routed to
  FIX-019's card as one test each; neither changes behaviour. Three notes are informational
  (I1–I3).

**Nothing was committed, pushed, deployed or configured.** No production state was read, no model
was called, no message was sent and no network call was made. NSE, Yahoo and the registry were
faked in every case, and the NSE rows measured were the ones FIX-016 rework 3 saved on 29 Oct.
Tracked files changed by this review: STATE, HANDOFF, this receipt and the FIX-019 card (a
routed-input note). The reviewer's scripts and
outputs are in the ignored `analysis_data/fix018_review/`.

### In one example (RV1, through the real stored scorecard)

16 decisions have passed 30 sessions, each a sale by the evidence rule. S0–S8 then fell 2% (right,
+2 each) and S9–S14 rose 1% (wrong, −1 each). S15 rose 5% (wrong, −5).

- **Account A: NSE's list for S15 is empty every Sunday.** S15 is set aside (1 of 16, under 10%).
  By hand the other 15 are right on 9 (60%) with a mean of (18 − 6) / 15 = +0.80. The first
  Sunday's stored row passes and names S15. The second Sunday recommends the switch, and the
  rendered line reads "Set aside, as its result can never be known: S15, decided 2026-08-20:
  NSE's list of its corporate actions is empty …".
- **Account B: S15's list fails to load on the first Sunday only.** S15 stays in, with no result.
  The first week is stored as a fail, with nothing set aside. On the second Sunday S15 is graded:
  16 judged, 9 right (56%), (18 − 6 − 5) / 16 = +0.4375 (stored as 0.44). That look passes, but
  nothing is recommended, because the stored week before failed. The third Sunday recommends.

So a failed read never sets a decision aside, and it cannot help the evidence rule that week.

### Review input verified

- **Manifest:** [FIX-018-manifest.json](FIX-018-manifest.json), 10 files, review input
  `c2e15877fd2a604f53990803348a1a57e9950aeed727fd264b5b079621680534`.
  `scripts/docs/kt_manifest.py verify` gives 0 mismatches at the start and at the end.
- **Diff:** `6769cab1ec58afd0212d76cde704bb9f4a1e8a6a0c95180c634fb159c70a76f4`, 130,281 bytes,
  9 paths, against HEAD `466a907`. It was rebuilt at the start and at the end by
  `analysis_data/fix018_review/rv_digest.py`, the implementer's recipe writing into the review
  folder. Both match the receipt.
- **No drift:** no reviewed path changed during the review.

### Contract checked

| Contract | Result | How it was checked |
|---|---|---|
| Two kinds of "no result" (card 1) | **Holds** | `horizon_in_basis` (`exit_shadow.py:475-576`) returns a kind with each gap. Lasting: an empty list, a list starting after the close, a bonus or split between the bar and the review day, an unread row or two ratios by the horizon's bar, a change by the bar or the review day. Temporary: a failed read, a list of undated rows, an undated, early or missing close, a Yahoo-only close with a later action. `grade_disagreements` (`:639-667`) marks a registry break as lasting and any exception as temporary. I read each branch against the card's lists. RV2 adds the boundary the story leaves open: a row or a demerger ex on the horizon's bar itself is lasting, whether NSE's close or only Yahoo's answers. |
| Set aside at both horizons; the rest judged (card 2) | **Holds** | `gate_look` (`:762-781`): a decision past 30 sessions with a lasting gap at either horizon leaves the population, and every check runs on the rest. RV4: a temporary gap at 10 beside a lasting one at 30 is set aside and does not fail the week, as the card requires. |
| The cap (card 3) | **Holds** | `:822-829`: more than 2, or more than 10% of the decisions past 30 sessions, turns only a pass into `cannot_judge`. The checks are whole-number comparisons, so 2 of 20 is allowed and 2 of 17 or 19 is not. The story's table and its 2,000-population exact-fraction oracle pass. The mutants (below) fail on a count of 2 made inclusive and on "cannot judge" replacing "not enough". |
| Named (card 4) | **Holds** | The look stores `set_aside` (date, symbol, reason). The reason is the first lasting horizon's own (`_lasting_reason`). `scorecard_text` names each one. RV1 reads it back from the stored row and from `render_scorecard_text`. |
| Temporary gaps fail as before (card 5) | **Holds** | A judged decision with no result is not right, and it makes its horizon's mean unknown (`:768-815`). RV1 account B is a stored failing week. |
| The fetch tells a failure from an empty list (card 6) | **Holds** | `read_corp_actions` (`corporate_events.py:58-73`) returns `[]` only for a `[]` or `{"data": []}` answer, and raises otherwise. The installed `nse` package (`.stockai/Lib/site-packages/nse/NSE.py:233-245`) raises `ConnectionError` on any non-2xx status and `TimeoutError` on a read timeout, so a failed request is never an empty list. Client creation sits outside the `try`, so its failure propagates. `results.corp_actions_fn` (`results.py:1160-1183`) records a failed read as `None` (temporary) and reads each list once. |
| The sync is unchanged | **Holds** | `fetch_corp_actions` wraps the strict read and returns `[]` on any failure, which is the old behaviour for every answer shape (traced shape by shape). `sync_corp_actions` is untouched. `ActionRecord.rows` is read only by `horizon_in_basis`, and only the weekly scorecard's `corp_actions_fn` feeds grading (grep of `{core,services,src,scripts}`). The sync's `[]`-for-both record never reaches the lasting check. |
| Constants fixed with the date (card 7) | **Holds** | `GATE_MAX_SET_ASIDE = 2` and `GATE_MAX_SET_ASIDE_PCT = 10.0`, with the comment "fixed 29 Oct 2026, before any shadow row existed". No shadow row exists in production: PR-009 is unpushed. |
| The look's consumers | **Unaffected** | `matured` now counts the set-aside decisions too, and `judged` is the old count. Only `scorecard_text` and `previous_week_look` (status only) read the look (grep), so no reader is misled. |
| Regression: PR-009's and FIX-016's story files | **Pass** | 203 passed (FIX-018 37, FIX-016 127, PR-009 39), plus the fetcher's file: 208 passed. The receipt's changed contracts in FIX-016's file were read one by one. None relaxes an assertion: each lasting case reads "not yet" or is set aside instead of "fails", and none passes. |
| Documentation | **Describes the reviewed behaviour** | KT section 6: the two kinds, the order the checks run in, the set-aside rule, the cap table (each row checked by hand), why, and the limits. Section 7's row, guide 07-L and 09-H (09-H by hand: 2 of 18 → 200 > 180 → cannot judge; the money version less one demerged decision → 14 judged, "not yet"), and the CODEBASE rows. `check_kt_docs`: errors `[]`. It checks the PDF's text and its recorded source hash, so the 60-page PDF matches the KT. |

### The card's hard-review questions

1. **Can what the evidence rule did or read decide which decisions are set aside?** Only through
   which holding-days become decisions. Classification reads the symbol, the row's close bar and
   review day, the horizon quote, NSE's list and the registry. `evidence_sold` sets only the sign
   and `right` (`exit_shadow.py:620-672`). The story's swap test agrees, over 300 random grades.
   The rule may still sell on a scheme or demerger filing, the very event that later sets the
   decision aside. The KT states that limit, and only the cap bounds it.
2. **Is the cap the only route by which a missing result can help?** Yes. Within the cap, a
   set-aside decision is as if absent for every check, which is the card's "judges the rest". That
   includes the one-stock share. RV5: stock X is 5 of 16 (31%), which fails; with one X decision
   set aside, X is 4 of 15 and the look passes, at 1 set aside of 16. Beyond the cap only a pass
   changes, to "cannot judge". A temporary gap never helps (the oracle's invariant, and RV1
   account B).
3. **Can a temporary gap be taken for a lasting one?** Not by the code I traced. A failed request,
   a timeout, a client that cannot be made, or an answer of no known shape is a failed read. The
   close is checked before the list. RV3: under an unusable registry, CANARABANK's NSE code falls
   back to the app code, for which NSE's list is empty. That would be lasting on its own, but the
   close is not found under that code either, so the gap is temporary (the shipped registry grades
   it, as the control). What remains is the owner's rule itself: an answered empty list is
   lasting, and the KT states that NSE could list a row later.
4. **Can "cannot judge" count toward the two-week run?** No. `recommends` needs this week's look
   and the stored week before to be `pass` (`:841-845`). The story's text test pins both
   directions, and RV1 shows that a stored failing week breaks the run the same way.

### Rulings on the implementer's decisions

- **F18-D1 (a strict read, and a never-raising wrapper for the sync): upheld.** An unknown answer
  must not pass as an empty list. The `nse` package's `_req` makes every non-2xx answer raise.
- **F18-D2 (the close first): upheld.** Beyond the receipt's reason, it also keeps a mis-resolved
  NSE code (RV3) from reading as lasting.
- **F18-D3 (a list of undated rows is temporary): upheld.** This is conservative: such a decision
  can only fail its week.
- **F18-D4 (a row or change after a Yahoo-only bar is temporary): upheld.** NSE's raw close may
  answer later, and the card treats the Yahoo bonus the same way.
- **F18-D5 (the card's "any size with 3 set aside" read with its rule 3): upheld.** Rule 3 says
  "cannot judge" replaces only a pass. The three acceptance populations are cannot judge, and the
  KT's table says "17, 27 or 47 graded + 3 set aside". Neither reading lets any population pass.
- **F18-D6 (the first lasting horizon's reason, in full): upheld.**
- **F18-D7 (a missing close is temporary even beside a lasting cause): upheld.** This is the card's
  "Not in this story".

### Findings

| ID | Severity | Location | Evidence | Disposition |
|---|---|---|---|---|
| T1 | low (test gap) | `exit_shadow.py:534` | The reviewed `covers_from > since` is right. A list whose earliest row is ex on the decision's close day covers it, so the decision is graded; RV6 checks it with a dividend ex 1 Sep and a close on 1 Sep (graded, ×1), and ex 2 Sep (lasting). My mutant `late_list_inclusive` (`>=`) survives the three story files (203 passed). Under it, such a decision is set aside. Under FIX-016 this boundary could only fail a week; now it could help the evidence rule. | Routed to [FIX-019](../stories/FIX-019.md) (routed-input note): one test. RV6 catches the mutant. |
| T2 | low (test gap) | `exit_shadow.py:835-838` (`_lasting_reason`) | A decision with a temporary gap at 10 and a lasting one at 30 is named with the lasting reason (RV7). My mutant `lasting_reason_any_kind` survives the story files: the scorecard would name the temporary reason instead. This affects text only. In practice both horizons usually give the same text, because they read one list (RV4: both say "NSE lists a demerger ex …"). | Routed to FIX-019 with T1: one test. RV7 catches the mutant. |
| I1 | info | `corp_actions.action_record` `covers_from`; `exit_shadow.py:534` | NSE's list holds a symbol's latest 20 actions, so its start only moves forward. A decision graded today can later read "the list starts after the decision's close" (lasting) and be set aside in later looks, inside the cap. Measured on rework 3's saved rows (`window_roll.py`): 136 of 202 lists are at 20 rows, and the newest start among them is TCS's 2022-05-25, at about 4 rows a year. So no configured list rolls past a decision made now for about 4 years. | No action in this PI. A one-line KT limit is optional at SA-031. |
| I2 | info | `exit_shadow.tally` / `scorecard_text` | The per-horizon tally counts every graded grade, including those of pending decisions and the graded horizon of a decision set aside for its other one. So "right on 10 of 16" can sit beside a gate judged on 15. This is PR-009's tally, by design, and the line names each decision set aside. | None. |
| I3 | info | `results._rounded` | The stored scorecard row keeps the gate's means to 2 decimals (0.4375 is stored as 0.44). This predates FIX-018, and the gate's status is computed before rounding. | None. |

### Commands, environment and results

Windows 11, the project's `.stockai` virtual environment (Python 3.13.11), `tests/hermetic.py`
active (no network, no `.env`, no checkout data). From the repository root:

- `.stockai/Scripts/python.exe analysis_data/fix018_review/rv_digest.py`: diff `6769cab1…`,
  130,281 bytes, 9 paths, HEAD `466a907`; at the start and at the end.
- `.stockai/Scripts/python.exe scripts/docs/kt_manifest.py verify docs/planning/PI-2026-09/evidence/FIX-018-manifest.json`:
  0 mismatches, `c2e15877…`; at the start and at the end.
- `.stockai/Scripts/python.exe -m pytest tests/unit/test_exit_fix018.py tests/unit/test_exit_fix016.py tests/unit/test_exit_evidence_pr009.py tests/unit/test_corporate_events_fetcher.py -q -p no:cacheprovider`:
  **208 passed** (2m31s).
- `.stockai/Scripts/python.exe -m pytest analysis_data/fix018_review/test_rv_fix018.py -q -p no:cacheprovider`:
  **8 passed** (RV1 stored scorecard, RV2 ×2 boundaries, RV3 alias under an unusable registry,
  RV4 temporary at 10 and lasting at 30, RV5 one-stock share, RV6 the list's first day, RV7 the
  reason named).
- `.stockai/Scripts/python.exe analysis_data/fix018_review/rv_mutants.py`: the implementer's
  in-memory harness with my own 11 mutants, run against the three story files. Baseline clean
  (203 passed); **9 of 11 caught**. Caught: set-aside including decisions short of 30 sessions;
  the 15-minimum, the span or the one-stock share counted over all decisions past 30 sessions;
  "cannot judge" replacing "not enough"; the count cap made inclusive; an unread row or a change
  on the horizon's bar read as temporary; a client that cannot be made read as an empty list.
  Survived: `late_list_inclusive` (T1) and `lasting_reason_any_kind` (T2). With
  `RV_TESTS=reviewer` both are caught by my cases (2 of 2; baseline 8 passed).
- The implementer's 43 mutants were not re-run; their list was read against the code.
- `.stockai/Scripts/python.exe -m pytest tests -q -p no:cacheprovider`: **5,875 passed, 12
  skipped, 1 xfailed, 0 failed** (26m03s, 22:47–23:13 IST, beside the mutant run). `git status`
  afterwards listed only this review's files and the reviewed input: no runtime data changed.
- `scripts/ci/check_broad_except.py`: OK (151 grandfathered). `scripts/docs/check_kt_docs.py`:
  errors `[]`.
- `analysis_data/fix018_review/window_roll.py`: I1's measurement (no network).

**Not exercised:** NSE's real answer for a blocked or expired-cookie request. The `nse` package
raises on any non-2xx status, but whether NSE ever answers 2xx with an empty list in place of an
error was not observed (inference only). There was no production read, and no browser.

### Acceptance checklist

- An independent oracle: the card's table, plus 3 set aside at 20, 30 and 50 → **met** (the
  story's TABLE and its exact-fraction oracle; I checked the table by hand).
- The four invariants → **met** (oracle, swap and repair tests; RV4, RV5).
- Through the real price path: a demerger, an empty list, a failed read, a Yahoo-only close →
  **met** (story tests; RV1 through the stored row).
- The sync is unchanged → **met**.
- Regression: PR-009's and FIX-016's story files, with the changed contracts named → **met**.
- Documentation: KT section 6, guide 07-L and 09-H, `check_kt_docs`, the PDF → **met**.
- The story file, the changed files and the full suite → **met** (208 focused; 5,875 / 12 / 1 /
  0 in full).
- The routed T1 from FIX-016's re-review (the bonus-word rows) → **met**: both rows are in FIX-016's
  table, and the implementer's `ratio_words_pooled` mutant is caught.

**Production verification:** `pending_deployment`. FIX-018 ships with PR-009 and FIX-016 in one
push, at the owner's word, in a job-free window (safest 00:10–06:20 IST). The commit needs the
owner's word too. After the deploy:

- guide 07-L on the first five trading days, including the count of disagreements on a stock
  whose NSE list is empty;
- the first Sunday scorecards' gate line: any "set aside" names, and whether "cannot judge"
  appears.

No prospective result is claimed: no shadow row exists yet.

**Commit-time edits** (with the commit, at the owner's word; none is made by this review):

- **Code commit:** exactly the 10 reviewed files. `kt_manifest.py verify FIX-018-manifest.json
  --rev HEAD` must give 0 mismatches (`c2e15877`).
- **Docs commit**, holding:
  - the KT header (`Code inspected` = that code commit; edition = the commit's date);
  - KT section 1's push sentence: the inspected code (PR-009, FIX-016 and FIX-018) is
    committed, not yet deployed, and pushed together at the owner's word. It no longer waits
    for an acceptance;
  - KT section 12's FIX-018 row: `Open` → `Done`;
  - guide 07-L and 09-H status: "FIX-018: implemented 2026-10-29; fresh review pending." →
    "FIX-018: accepted 2026-10-29; ships with PR-009 and FIX-016.";
  - the PDF, regenerated, with `check_kt_docs` errors `[]`;
  - the receipts and manifest, the FIX-019 card note, STATE and HANDOFF.

**Decision: ACCEPTED.** STATE: FIX-018 `done`, production `pending_deployment`; `active_task`
null; `next_task` **FIX-019** (implementation, in a new conversation): the first planned `todo`
story whose dependencies are done, in STATE order.
