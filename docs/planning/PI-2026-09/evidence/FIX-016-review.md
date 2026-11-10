# FIX-016 review receipt — the evidence exit's inputs and its switch gate

## Fresh re-review of rework 3: ACCEPTED (2026-10-29)

**Phase:** fresh-session re-review of rework 3, a new conversation opened with "continue" (29 Oct,
about 17:43–18:15 IST, session `stockagent-main-4f` [48a88a]). It shares its short name with
re-review 1's session of 25 Oct, but it is a different conversation and did not read that one.
FIX-016 was implemented in `stockagent-main-a6`, reviewed in `-f7`, reworked in `-e2`,
re-reviewed in `-4f` (25 Oct), reworked in `-1f`, re-reviewed in `-f0` and reworked in `-8a`. This
conversation read none of those chats. The peers `-5d`, `-8a` and `-f0` were idle at the start
and before the bookkeeping (ListAgents).

**Verdict: ACCEPTED** for the reviewed revision below.
- **RR2-F1 is fixed.** Each NSE row is read in full or not at all. On the 3,215 rows NSE lists for
  the 202 configured symbols, every row read as a ratio is a standard equity bonus or face-value
  split, and my own parser gives the same 110 ratios. Every row read as neutral is a dividend, a
  meeting, a vote, a buy back, interest, a redemption or a registrar change. None of 49 wordings of
  my own, run through the real price path, gives a graded result other than the true one.
- **RR2-M1 is fixed.** Grading reads NSE's list under the code the close is read under. With the
  shipped registry, CANARABANK is graded across CANBK's split, and NSE is asked only for CANBK.
- **RR2-L1 is done:** the KT states the limit for undated rows.
- **The card's criteria still hold.** The verdict, event, benchmark and money-check criteria have
  held since the first review, the code behind them is untouched, and PR-009's 39 tests pass.

One low finding is routed:
- **T1, a test gap.** No test pins that a bonus may use only a bonus's words. FIX-018 adds the
  table row.

**Nothing was committed, pushed, deployed or configured.** No production state was read, no model
was called, no message was sent and no network call was made: the NSE rows checked were the ones
rework 3 saved, cross-checked against re-review 2's own read of the same lists. Tracked files
changed by this re-review: STATE, HANDOFF, this receipt and the FIX-018 card (a routed-input note).
The reviewer's scripts and outputs are in the ignored `analysis_data/fix016_rereview3/`.

### In one example (W2, through the real scorecard)

The evidence rule sells 15 stocks at ₹100. Afterwards, 8 fall 2% (right, +2 each) and 7 rise 5%
(wrong, −5 each). That is −19/15, about −1.27% a decision, which fails, as it must.

One of the 7, T14, issues a 1:1 equity bonus three sessions after its decision. NSE's row reads
"Capitalisation Issue 1:1", a wording that no NSE list holds and no rule names.

- **By hand:** T14 is worth ₹105 a share in the old shares, so the sale was wrong. Its raw close
  is ₹52.50.
- **Rework 2** read the row as neutral (it names no known kind). The grade would be a −47.5%
  "fall", the sale right with +47.5, and the population would pass at 9 of 15 and +2.23.
- **Rework 3:** the row has words of no known kind, so T14 has no result at either horizon, named
  "corporate action of no known kind ('Capitalisation Issue 1:1')". The gate fails, right on
  8 of 15, and the next week recommends nothing.

### Review input verified

- **Manifest:** [FIX-016-manifest.json](FIX-016-manifest.json), sha256 `28039abf…e403`, 13 files.
  `scripts/docs/kt_manifest.py verify` gives 0 mismatches at the start and at the end.
- **Kept input:** `FIX-016-manifest-review3.json` is `5bdb5496…2aff`. The digest script checks
  rework 3's input copy byte for byte against it.
- **Rework diff:** `657ff368107be963e742c7aa98dd27f9bf1bdaa23b3fa24fd946cf5171a8175f`, 76,211 bytes.
- **FIX-016's own diff:** `a44537ff7dc8d71c710f5b0559ae243123383efc41893a023ce050226dbc4b0c`,
  235,103 bytes.
- **Cumulative diff against HEAD `8cb626c`:**
  `9b4fdecdd7597bf3f582e3bc18a6fce8deb57ae8a84909f143c859ce075e262c`, 236,583 bytes, 12 paths.
- **How they were rebuilt:** by `analysis_data/fix016_rereview3/rr3_digest.py`, rework 3's
  recipe writing into this folder, at the start and at the end. All three match the rework
  receipt.
- **No drift:** no reviewed path changed after rework 3's bookkeeping. The owner-decision edits of
  16:05–16:16 IST touched only STATE, HANDOFF, the PI README and the new cards. No re-review edit
  touched a reviewed path.

### Contract checked

| Contract | Result | How it was checked |
|---|---|---|
| RR2-F1: a row is a ratio only when the record reads an equity bonus or face-value split in full | **Holds** | `corp_actions._read_ratio` (`corp_actions.py:128-145`): `parse_action` must read a bonus or split, the row must not name both, and every word must be in the kind's own words or the neutral ones (beside a named change, only the clause). Scan of rework 3's 3,215 saved rows (`scan.py`): the 110 ratios are 64 "Bonus N:N" rows (3 beside a dividend or a meeting) and 46 face-value splits, all in NSE's standard shapes. My own parser (the colon pair for a bonus; the two rupee amounts for a split) agrees on all 110. |
| RR2-F1: no row that changes the share count or the basis reads as neutral | **Holds** | `action_record` (`:225-248`): neutral only when the row has words and all are in `_NEUTRAL_WORDS`. In the scan the 3,011 dated neutral rows fall into 97 shapes (sorted words, numbers dropped), each read by eye: dividends in every spelling, meetings, e-voting, buy backs, interest and redemption, one registrar change. 13 rows are unparsed and 27 are of no known kind, the same rows the KT names. |
| A corporate action is not a result (the hard review's question) | **Holds** | W1: 49 wordings of my own, each between a decision's closes on a stock flat in real terms. Through the real price path, each is graded at 0 or has no result, for a sale and for a keep. The 6 standard ratios and the 6 neutral wordings are graded. On re-review 2's input (rework 2's `corp_actions.py` and `results.py`), 17 of the 49 wordings fail, as do W2 and W3: 20 failed, 31 passed. |
| Q3 and Q5 pinned; re-review 2's cases flip | **Holds** | Re-review 2's cases: Q3, Q3 gate (misspelt), Q5, Q5 gate and Q6 fail at their defect assertions (`:151`, `:182`, `:211`, `:238`, `:279`); Q1, Q2 ×2, the Q3 gate control and Q4 pass. Re-review 1's RR1, RR2 (demerger) and RR3 fail at their defect values; 9 pass. |
| RR2-M1: NSE's list under the code the close is read under | **Holds** | `results.corp_actions_fn` (`results.py:1160-1177`) → `fetch_corp_actions(nse_symbol(symbol))`. W3 uses the shipped `config/instruments.yaml`: CANARABANK is sold at ₹100 and stays flat, and CANBK lists a 10-to-2 split three sessions later. It is graded 0 at both horizons, ×5, and NSE is asked once, for CANBK. The story's `_Market` now answers only NSE's codes (tightened, not relaxed). |
| The holding sync is unchanged (FIX-017) | **Holds** | The rework diff touches no line of `parse_action`, `apply_actions_to_holding` or `sync_corp_actions`. PR-009's `test_nse_rows_become_a_record_and_the_sync_applies_exactly_as_before` passes. |
| PR-009's invariants; the gate | **Hold** | `exit_shadow.py` changed only in a docstring. `level_in_basis` reads `unparsed`, which is now wider, so the level is unused more often (fail safe). A row of no known kind between dive and buy is ignored by the level, as it was when such a row read as neutral. The KT states this limit (PR-005). `gate_look`, `decision_benchmark` and `first_disagreements` are untouched. |
| Documentation | **Describes the reviewed behaviour** | KT section 6: "Each row is read in full or not at all", the causes, the preference-share example and the limits. Its measured counts agree with the scan (3,011 + 110 + 50 + 8 + 27 + 9 = 3,215; 14 empty lists). Guide 09-H's step: ₹110 × 0.925 = ₹101.75, and × 22 = ₹2,238.50. The CODEBASE rows. PDF: 59 pages, cover digest `ee857f747b86` = the KT's LF SHA-256. `check_kt_docs`: errors `[]`. |

**Rulings on the rework's decisions:**

- **RW3-D1 (fail closed) is upheld.** The measured cost is 27 rows of no known kind and 13 unread
  share-count rows. All are from 2008 to 2021, except TVSMOTOR's 2025 NCRPS bonus, which is rightly
  unread. Under the owner's RW2-D6 decision, FIX-018 turns these lasting gaps into set-asides within
  a cap.
- **RW3-D2 (measured words, no misspellings) is upheld.** Every neutral shape in the 202 lists is
  genuinely neutral to the equity basis.
- **RW3-D3 and RW3-D4 are upheld.** Under RW3-D4, "Rights Issue 1:5 And Bonus 1:1" keeps its
  bonus of 2 for PR-009's level, and the day has no result in grading.
- **RW3-D5 (today's NSE code) is upheld.** The registry check still covers a new basis. For the
  two unresolved entries, both the close and the list are read under the successor's code
  (TATAMOTORS → TMPV, HEXAWARE → HEXT), so a grade never mixes two listings.
- **RW3-D6 (undated rows stay unread, a KT limit) is upheld.**

### Findings

| ID | Severity | Location | Trigger | Observed | Expected | Disposition |
|---|---|---|---|---|---|---|
| **T1** | Low (test gap; the reviewed code is correct) | `core/portfolio/corp_actions.py:145` (`_RATIO_WORDS[action.kind]`); `tests/unit/test_exit_fix016.py` (the rework 3 table) | A bonus row that also changes the face value without the word "split", such as "Bonus 1:1 And Face Value From Rs 10 To Rs 2" or "Bonus 1:1 (Face Value Rs 10 To Rs 2)". No NSE list holds this wording. | The reviewed code reads both as unparsed: no result, and PR-009's level unused. My mutant `ratio_words_pooled` lets a bonus use a split's words, which reads both as a bonus of 2 alone, a false −80% on a 1:1 bonus with a 10-to-2 split. The mutant survives the story file: 164 passed (`pooled_probe.txt`). | One table row pins it: either wording is unparsed. | **Routed to [FIX-018](../stories/FIX-018.md)** (routed-input note): FIX-018 changes the same record's classes. Not a push blocker. |

**Checked, and not findings:**

- **The saved rows are what NSE listed.** Rework 3's `raw_rows_2026-10-29.json` (10:57–11:08 IST)
  and re-review 2's own probe (09:05 IST) give the same row count for 183 of 183 shared symbols.
  The only 4 differences are the codes rework 3 read under `nse_symbol`:
  - CANARABANK, TATAMOTORS and TVSMOTORS: 0 rows under the app code, 20 under NSE's;
  - HEXAWARE: 20 rows under its own code, 4 under HEXT.
- **Dividends** are still the stated limit from the first review (the raw-close return leaves them
  out). They were not reopened.
- **Undated rows:** 9 on 29 Oct, among them INOXLEISUR's "Merger" and NIIT's
  "Agm/Div-50%/Sch Of Arrang". This is the KT's limit (RW3-D6).
- **Wordings that read in full and are right:** "Sub-Division Of Equity Shares From Rs 10 To Rs 1"
  and "Share Split From Rs 10 To Rs 1" each read as a split of 10, which is right.
- **Wordings that could slip past:** I looked for any built only from known words that changes the
  basis (W1's list and the scan's shapes). I found none. "Redemption" and "Buy Back" leave the
  equity's basis alone; a buy back's tender premium is a market move, not a ratio.

### The reviewer's own cases

`analysis_data/fix016_rereview3/test_rr3_fix016.py`, with its own `conftest.py` importing the
hermetic hooks. Its price model is re-review 2's `Book`, extended: it records the codes NSE is
asked for, and NSE answers only codes it lists. It was written separately from the implementer's
`_Market`. Each share's worth is set in real terms. From a row's ex day, the equity trades at a
stated multiple of that worth: 0.5 for a 1:1 bonus, a fraction for value that leaves, 10 for a
consolidation. NSE's close is raw, and Yahoo's agrees.

**51 passed** on the reviewed tree:

- **W1 (×49):** each wording between a decision's closes: graded at 0 or no result, never another
  number. The standard ratios and the neutral rows must be graded. How rework 3 classes each
  wording is in `wording_classes.txt`.
- **W2:** the gate example above.
- **W3:** the alias, with the shipped registry.

With `RR3_SWAP=input`, which loads re-review 2's input versions of `corp_actions.py` and
`results.py` from rework 3's kept copy, **20 fail**: 17 W1 wordings, among them "Bonus Warrants
1:1", "Capitalisation Issue 1:1", "Transfer Of Undertaking", "Return Of Capital", "Sch Of
Arrangement" and an empty subject, plus W2 and W3. 31 pass.

### Commands and environment

Windows 11, the `.stockai` venv (Python 3.13), with the hermetic boundary on (SA-005).

| Command (repository root) | Result |
|---|---|
| `.stockai/Scripts/python.exe scripts/docs/kt_manifest.py verify docs/planning/PI-2026-09/evidence/FIX-016-manifest.json` | 13 files, mismatches `[]`, `28039abf…` (start and end) |
| `.stockai/Scripts/python.exe analysis_data/fix016_rereview3/rr3_digest.py` | `657ff368…` 76,211 B, `a44537ff…` 235,103 B, `9b4fdecd…` 236,583 B, 12 paths, HEAD `8cb626c` (start and end) |
| `pytest -q -p no:cacheprovider tests/unit/test_exit_fix016.py tests/unit/test_exit_evidence_pr009.py` | **164 passed** in 30 s |
| `pytest -q -p no:cacheprovider --rootdir analysis_data/fix016_rereview3 analysis_data/fix016_rereview3/test_rr3_fix016.py` | **51 passed**; with `RR3_SWAP=input`: 20 failed, 31 passed |
| `pytest … analysis_data/fix016_rereview2/test_rr2_fix016.py` (re-review 2's cases) | 5 failed at their defect assertions (Q3, Q3 gate misspelt, Q5, Q5 gate, Q6), 5 passed |
| `pytest … analysis_data/fix016_rereview/test_rr_fix016.py` (re-review 1's cases) | 3 failed at their defect values (RR1, RR2 demerger, RR3), 9 passed |
| `analysis_data/fix016_rereview3/scan.py` (no network; rework 3's saved rows) | 202 symbols; 183/183 counts equal to re-review 2's probe; 110 ratios, my parser agrees 110/110; 97 neutral shapes; 13 unparsed; 27 of no known kind; 50 named changes |
| `analysis_data/fix016_rework3/rw3_mutants.py new` (the implementer's 18) | 18 of 18 caught, baseline clean (164 passed) |
| `analysis_data/fix016_rereview3/rr3_mutants.py` (2 of mine, through the implementer's in-memory plugin) | baseline 164 passed; `share_count_branch_dropped` caught (24 failed); `ratio_words_pooled` **survived** (164 passed): T1 |
| `pytest tests -q -p no:cacheprovider` (full suite, 17:54-18:09 IST, beside the mutants) | **5,835 passed / 12 skipped / 1 xfailed / 1 failed (14m09s, beside the mutants): the one failure is the known Windows flake test_store_migration_sa009.py::test_a_refused_store_is_retried_and_the_status_never_overstates (PermissionError WinError 5 on os.replace in its own temp folder; outside the review input, unchanged from HEAD); re-run alone 3 of 3 passed, its file 22 passed** |
| `scripts/ci/check_broad_except.py` | OK (151 grandfathered) |
| `scripts/docs/check_kt_docs.py` | errors `[]` |
| `analysis_data/fix016_rereview/pdf_check.py` | 59 pages; cover digest `ee857f747b86` = the KT's LF SHA-256 |

**Not exercised:**

- production: nothing was read;
- NSE: no new read; the rows checked were rework 3's saved rows, cross-checked as above;
- the 81 earlier FIX-016 mutants: their logs show them caught on rework 3's final tree, and the
  code they target is unchanged except the 5 the rework re-pointed;
- Yahoo's handling of an unusual action, which does not matter here: each horizon close in W1–W3
  is NSE's raw close.

### Acceptance checklist

| Criterion | Verdict |
|---|---|
| Verdict: a SELL run before the buy, or 23 sessions old, does not sell; one run after the buy and 22 sessions old sells; a newer BUY over an older SELL does not sell | Met (unchanged since the first review; story file passes) |
| Events: a high-negative `news` event does not sell and is a watch item; the same from `nse_announcement` sells; a rule-typed pledge invocation sells | Met (unchanged) |
| Benchmark: stock −3%, Nifty −5%: plain EXIT right against cash, SWITCH wrong against the Nifty; read from the row, never re-graded | Met (unchanged) |
| Money check: the independent oracle's populations; a missing grade never turns a fail into a pass; "better" only at 70% with a positive mean | Met (unchanged; W2, Q3 and Q5 add corporate-action cases that cannot pass it) |
| Re-review 2's RR2-F1, RR2-M1 and RR2-L1 | Met |
| Hard review: can a corporate action decide the money check? | **No**, for any row the record reads: only a fully read equity ratio is applied, and anything else between the closes is no result |
| PR-009's story file passes, with each changed contract named | Met (rework receipt "Changed contracts") |
| KT sections 6 and 7, guide 07-L and 09-H, `check_kt_docs`, PDF; the story file, changed files and the full suite pass | Met. The full suite's one failure is the known Windows flake in SA-009's migration test (`PermissionError [WinError 5]` on `os.replace` in its own temp folder, recorded in HANDOFF). It lies outside the review input and is unchanged from HEAD, and it passes on re-run. |

### Commit-time edits

These are docs only, made in the commit that carries FIX-016 (the reviewed paths are left as
reviewed):

1. **Guide status lines** 07-L, 07-M and 09-H: "FIX-016: rework 3 implemented 2026-10-29, fresh
   re-review pending; it ships with PR-009." becomes "FIX-016: accepted 2026-10-29; it ships with
   PR-009 and FIX-018."
2. **KT header and section 1:** "Code inspected" and the edition move to the commit. The sentence
   "the owner held its push on 24 October until FIX-016 is accepted, so both go out together"
   becomes: held until FIX-016 and FIX-018 are accepted (owner, 24 and 29 October), so the three
   go out together.
3. **KT section 12:** the FIX-016 row becomes Done. Add Open rows for FIX-017 (re-review 2's
   card), FIX-018 and FIX-019.
4. **Afterwards:** regenerate the PDF, then run `check_kt_docs`.

### Decision and state

**ACCEPTED.**

- **STATE:** FIX-016 is `done`, with a `rereview_3` record and `reviewed_revision`. `active_task`
  is null. **`next_task` is FIX-018** (ready: its only dependency is FIX-016). It is not started:
  the implementation runs in a new conversation.
- **`production_verification`:** `pending_deployment`. The code is uncommitted, and the push waits
  for FIX-018 (owner). After the deploy, observe:
  - each shadow row's `benchmark`, `watch_event_ids` and `research_run_at` (guide 07-L, first five
    trading days);
  - the first Sunday scorecard's gate line with the money check (07-M, 09-H shapes).
- **PR-009's push stays held** until FIX-018 is accepted (owner, 29 Oct). Then PR-009, FIX-016 and
  FIX-018 go out in one push, at the owner's word, in a job-free window.
- **Commit:** FIX-016 is uncommitted on `8cb626c`. Commit only at the owner's word, with the
  commit-time edits above and the owner-decision docs already in the tree. Those are the cards
  FIX-016 to FIX-019 and PR-013, the PR-005, PR-012 and SA-049 notes, the PI README,
  `docs/README.md` and `docs/START_HERE.md`.

## Fresh re-review of rework 2: CHANGES REQUESTED (2026-10-29)

**Phase:** fresh-session re-review of rework 2, a new conversation opened with "continue" (29 Oct,
about 08:57–09:45 IST, session `stockagent-main-f0`). FIX-016 was implemented in
`stockagent-main-a6`, reviewed in `-f7`, reworked in `-e2`, re-reviewed in `-4f` and reworked again
in `-1f`. This conversation is none of them and did not read them. No other session was running
at the start or before the bookkeeping (ListAgents).

**Verdict: CHANGES REQUESTED.** Rework 2 did what re-review 1 asked:
- every demerger, scheme, consolidation, capital reduction and rights row in NSE's standard wording
  is no result;
- a row naming a bonus and a split is no result;
- a basis change the registry records is no result;
- RR1–RR3 are pinned;
- RR-L1 and I1 are done.

One new high finding remains in the same financial target, and one medium:

- **RR2-F1 (high):** NSE's rows are read by keywords, and some of the configured stocks' own rows
  are misread. In the lists of all 202 configured symbols (3,171 rows, read on 25 and 29 Oct), the misread rows fall
  into three groups:
  - **a bonus of preference shares read as a 22-for-1 equity bonus** (ZEEL's "Bonus Preference
    Shares 21:1");
  - **a split not seen at all** (JSWSTEEL's "Fv Splt Frm Rs 10 To Re 1");
  - **a rights issue and a scheme the word list misses** ("Rhs 3:7…", "Scheme Of Arangement").

  One such row between a decision's closes still decides the money check. With ZEEL's wording, a
  rule that loses 1.27% a decision passes at about +121% and is recommended the next week (Q5).
- **RR2-M1 (medium):** grading asks NSE for the app's code, not the registry's. `TVSMOTORS` and
  `CANARABANK` get an empty list, so every decision on them has no result for good. The story's
  fixture answers any code, so "a rename is graded" holds only in the fixture.

The owner held PR-009's push so that the gate, including how a result is measured, is fixed
before any shadow row exists. RR2-F1 is the same defect class as F1 and RR-F1, so it is settled
before the push, not routed. **Nothing was committed, pushed, deployed or configured.** No
production state was read, no model was called and no message was sent. The only network calls
were read-only reads of NSE's public corporate-action lists (below). After the verdict, at the
owner's go-ahead ("go ahead", about 10:42 IST), one read-only production probe checked FIX-017's
trigger: 1 account, 2 holdings (REDINGTON, WELCORP), no registry alias, no bonus or split
applied, and no NSE row after either buy (`analysis_data/fix016_rereview2/prod_holdings_2026-10-29.txt`,
`held_rows_2026-10-29.txt`). It did not inform the verdict. Tracked files changed by this
re-review: STATE, HANDOFF, this receipt, the PI README's queue and the new card
[FIX-017](../stories/FIX-017.md). The reviewer's scripts and outputs are in the ignored
`analysis_data/fix016_rereview2/`.

### In one example (RR2-F1)

The price-path rule sells KKK at ₹280 on Friday 23 Oct as a plain EXIT; the evidence rule keeps
it, so the row's benchmark is `cash`. On Wednesday 28 Oct KKK issues 21 bonus preference shares of
₹1 for each equity share. NSE's row reads "Bonus Preference Shares 21:1", as ZEEL's 2014 row does.
The equity now trades at ₹259, and the holder also owns ₹21 of preference shares. The number of
equity shares is unchanged.

- **By hand:** the stock is flat in real terms, so the keep was right with a result of 0. Read as a
  payout like a dividend (the stated limit), it is −7.5%, and the keep was wrong. Either is
  acceptable, and so is no result.
- **The grade:** `action_record` keeps the row as a bonus of ratio (21 + 1) / 1 = 22, and
  `horizon_in_basis` multiplies ₹259 by 22. The result is **+1,935%**, and the keep is "right".
  The row names neither a split nor a basis change, so nothing else catches it.

**The gate (Q5), through the real scorecard block and the real price lookups:**

- **15 decisions where the evidence rule kept:** 8 then rose 2% (right, +2 each) and 7 fell 5%
  (wrong, −5 each). That is −19/15, about −1.27% a decision, and it fails, as it must.
- **One change:** one of the 7 issues bonus preference shares worth 7.5% of its price three
  sessions after its decision. It is still wrong by hand. Its graded close is 95 × 0.925 × 22,
  so it becomes "right" with about +1,833.
- **The gate then reads** right on 9 of 15 with a mean above +100%: a pass. The next Sunday it
  recommends the switch.

Unlike a demerger's −40, a factor of 22 is not diluted by a larger population: one such row passes
the money check against 100 honest decisions.

### Review input verified

- **Manifest:** [FIX-016-manifest.json](FIX-016-manifest.json), sha256 `5bdb5496…2aff`, 13 files.
  `scripts/docs/kt_manifest.py verify` gives 0 mismatches at the start and at the end.
- **Rework diff:** `44143f54e0534c1afeddbb7f2ec4a68280820d48b782d601fb83d9a213903772`, 78,802
  bytes. The script first checks the rework's input copy byte for byte against
  `FIX-016-manifest-review2.json` (`9b8e7457`).
- **FIX-016's own diff:** `564fc952…6ce7`, 201,380 bytes.
- **Cumulative against HEAD `8cb626c`:** `dd54d84898668c405661bc4cf4f56e448d2f86a89158ebd2246e9e3b0cc375ba`,
  202,860 bytes, 12 paths.
- **How they were rebuilt:** by `analysis_data/fix016_rereview2/rr2_digest.py`, the rework's
  recipe writing into this folder, at the start and at the end. All three match the rework
  receipt.
- **No drift:** no tracked file changed after 26 Oct 17:07 IST, when the rework's bookkeeping
  ended. No re-review edit touched a reviewed path.

### Contract checked

| Contract | Result | How it was checked |
|---|---|---|
| RR-F1 as asked: a change no ratio converts, in NSE's standard wording, between the closes is no result | **Holds** | `horizon_in_basis` (`exit_shadow.py:523-529`): the same windows as the bonus rule (after the close's bar; by the horizon's bar, the review day, or after the bar for Yahoo's alone). RR1–RR3 of re-review 1 now fail on their defect values (no result where they asserted −40, +1.53 and −40); RR4, RR4b and RR5 (×6) pass. My Q2: GRASIM's wording "Scheme Of Arrangement" and "Demerger" give no result through the real price path. The rework's 19 mutants re-run and caught. |
| A corporate action is not a result (the hard review's question) | **Fails for rows the record misreads** (RR2-F1) | Q3, Q5 and the wording table, from NSE's own rows |
| A registry basis change is no result; a rename is graded | **Holds for the change; the rename only in the fixture** (RR2-M1) | `registry_break` over `identity_break`, asked up to the horizon's day (RW2-D5), zero-network (`resolve_identity`). Q6: an alias reads an empty list. |
| A bonus-and-split row is no result, and PR-009's level unused | **Holds** | `action_record` puts it in `unparsed`; `level_in_basis` reads `unparsed` from the dive day on, before and after the buy. |
| I1: any failed destination fetch is a refused buy | **Holds** | The executor skips the buy on any `session_close` error (`autopilot.py:207-213`). The two pipeline tests pass. |
| The benchmark is read from the row; PR-009's invariants | **Hold** | `first_disagreements`, `decision_benchmark` and the money check are untouched. PR-009's 39 tests pass. The rework removed only string rewordings and the market model's old lines: no assertion was relaxed. |
| Documentation | **Describes the implemented behaviour** | KT section 6 ("One price basis", the demerger example, the limits) and section 7. Guide 09-H's demerger step: ₹110 × 0.6 = ₹66, a −34% "fall" without the fix. The CODEBASE rows. PDF 59 pages; its cover digest `7ceed0eedf33` equals the KT's LF SHA-256. `check_kt_docs`: errors `[]`. RR2-F1 and RR2-M1 will change the KT's measured sentence (29 of 354) and its rename claim. |

**Rulings on the rework's decisions:**

- **RW2-D1 is overturned on its evidence.** It said wording the classifier does not know reads as
  neutral, because "NSE's lists hold no unknown basis change today". That rested on 22 lists. The
  configured universe's 202 lists hold such rows (RR2-F1). The trade-off it names is real:
  failing closed can block the gate. But a silent grade across a basis change can pass it, and the
  owner's rule is that a missing grade never helps. Rework 3 re-decides it.
- **RW2-D2 (rights not converted) and RW2-D3 (consolidation not parsed) are upheld.**
- **RW2-D4 is upheld.** The same reasoning extends to a bonus of other securities (RR2-F1).
- **RW2-D5 and RW2-D6 are upheld.** RW2-D6 stays the owner's question, and RR2-F1's fix may make
  it more pressing.

### Findings

| ID | Severity | Location | Trigger | Observed | Expected | Disposition |
|---|---|---|---|---|---|---|
| **RR2-F1** | **High** (confirmed: Q3 and Q5 through the real `results.stock_quote_fn` and `results.corp_actions_fn` → `fetch_corp_actions` → `action_record`, with only `yfinance.download`, NSE's close and NSE's `actions()` faked; every wording measured in NSE's public lists for the configured symbols on 29 Oct) | `core/portfolio/corp_actions.py` `action_record` (`:168-188`), `parse_action` (`_BONUS_RE` `:28`, the split test `:116`), `_changes_share_count` (`:75-77`), `_BASIS_CHANGE_KINDS` (`:37-44`); consumed by `exit_shadow.horizon_in_basis` | A row NSE lists for a configured stock, between a decision's closes, that the record misreads | (a) **A bonus of other securities is read as an equity bonus:** ZEEL 2014 "Bonus Preference Shares 21:1" → ×22, caught by nothing. DRREDDY 2011 "… Bonus Debentures 6:1" → ×7 and TVSMOTOR 2025 "Scheme Of Arrangement - Bonus Ncrps 4:1" → ×5 are caught only by their scheme words. (b) **A split is not seen:** JSWSTEEL 2017 "Fv Splt Frm Rs 10 To Re 1" and KNRCON 2016 "Fv Splt Frm Rs 10 To Rs 2" are neither applied nor unparsed, so the horizon close is a tenth: a −90% "fall" (F1's defect). (c) **A basis change the word list misses:** HINDALCO 2008 "Rhs 3:7@Prem Rs95" (rights); BRITANNIA 2019 and 2021 "Scheme Of Arangement- Bonus - 1 Debenture …" (caught only by "bonus"); NIIT "Sch Of Arrang" (undated). Q3: a demerger worded "Scheme Of Arangement" grades a flat stock at −40, and the RR2 population passes. Q5: one ZEEL-worded row passes a −1.27% rule and recommends it. | A row is a ratio only when the record fully reads an equity bonus or a face-value split. Every other row that names a share, a security, a split, a scheme or a rights issue, and that the record cannot class, is no result between the closes, never neutral. | **Required in rework 3** (below) |
| **RR2-M1** | **Medium** (confirmed: Q6; NSE read on 29 Oct) | `core/portfolio/results.py:1168-1173` `corp_actions_fn` → `fetch_corp_actions(symbol)`; the close asks for `nse_symbol` (`services/data/fetchers/close_verifier.py:112-114`); the story's fixture `tests/unit/test_exit_fix016.py:728-735` answers any code | A decision on a registry alias (`TVSMOTORS` → TVSMOTOR, `CANARABANK` → CANBK, `config/instruments.yaml`) | NSE lists 0 rows for `TVSMOTORS` and `CANARABANK`, and 20 each for `TVSMOTOR` and `CANBK`, including Canara Bank's 1:5 split of 15 May 2024. Every decision on these two stocks has no result, for good, so the money check cannot pass while one is in the population. RR3's "a rename is graded" passes only because the fixture lists rows under the old code. | The list is read under the code the close is read under. A fixture answers only NSE's code. | **Required in rework 3** (one call and a test; it corrects a stated contract) |
| **RR2-L1** | Low (docs) | `action_record` skips a row with no ex-date | NSE lists undated scheme rows: PEL and INOXGREEN "Merger", NIIT "Sch Of Arrang" | Ignored by grading, as an undated bonus is. Whether NSE dates such a row once it goes ex was not measured. | A KT limit sentence, or the implementer's rule | Rework 3 (docs) |
| Routed | — (live, outside FIX-016) | the holding sync: `sync_corp_actions` → `parse_action` → `apply_actions_to_holding` | The same rows, applied to holdings before the stops run | The quantity is ×22, ×5 or ×7 for a bonus of other securities; a bonus-and-split row is its bonus alone (rework 2's find); an "Fv Splt" split is not applied; aliases fetch nothing. The holding shows a false gain or a false −80–90%, and a stop can sell it. | — | **New card [FIX-017](../stories/FIX-017.md)** (P2, after FIX-015; routing delegated) |

**Checked, and not findings:**

- **The 17 configured symbols whose list is empty.** NSE answered `[]` with no error for AAVAS,
  ACCCEMENT, APL, CANARABANK, DEEPAKNITRI, GATI, ICICIPRULI, IDEAFORGE, LTIM, MAHINDHOTEL,
  MCDOWELL-N, MTAR, PVR, STARHEALTH, TATAMOTORS, TVSMOTORS and ZOMATO.
  - Two of them are registry aliases: RR2-M1.
  - TATAMOTORS is quarantined.
  - The rest are app codes NSE does not list under that name, or companies with no action yet.
    They are RR-L1's limit at a measured size: 8% of the configured universe.
  - A decision on them fails safe (no result).
- **The probe's coverage.** 3,171 rows across all 202 configured symbols. The rows with an ex-date
  that could fall between future closes are NSE's future rows. Recent rows use standard wording,
  but the misspelt "Arangement" is from 2019 and 2021, and the NCRPS bonus from August 2025.
- **Rows in NSE's standard wording are classed.** The 202 lists hold 23 rights rows, 13 demerger
  rows and 6 scheme rows the record classes correctly. HINDALCO's 2008 "Rhs" is the one rights row
  it misses.

### Rework 3: what must be true at the next re-review

1. **RR2-F1, required.**
   - **No row is read as a share-count ratio that it does not state for equity shares.** A bonus
     of preference shares, debentures or NCRPS is no result between the closes, never a ratio.
   - **No row that changes the share count or the basis reads as neutral.** That covers NSE's
     short split wording ("Fv Splt Frm …"), "Rhs", "Arangement" and "Sch Of Arrang". The
     implementer decides the shape and records it as a decision.
     - Recommended: **fail closed.** A row is neutral only when it matches a known neutral kind:
       dividend in any of NSE's spellings, a meeting, e-voting, a buy back, an interest payment or
       redemption, or a registrar change. Any other dated row is unparsed, so it is no result
       between the closes and named.
     - The alternative is to add the measured words. If chosen, say why a new wording cannot pass
       the gate.
   - **Grading only.** The holding sync is FIX-017. The record must not change what the sync
     applies.
   - **Pin:** every NSE subject quoted in RR2-F1 as a table test with its expected class; Q3 and
     Q5 as invariant tests through the real price path. Their defect assertions are in
     `analysis_data/fix016_rereview2/test_rr2_fix016.py` and should fail after the fix.
   - **Docs:** KT section 6: what is read, what is no result, and the probe's sentence measured on
     the 202 lists; guide 09-H or 07-M if a step changes.
2. **RR2-M1, required.**
   - Grading reads NSE's list under `symbol_resolver.nse_symbol(symbol)`, the code its close is
     read under.
   - The story's fixture answers only NSE's code. RR3's rename and Q6 then show a rename and an
     alias graded.
   - The KT's empty-list limit names the measured 17 of 202.
3. **RR2-L1:** the KT limit, or the implementer's rule for undated rows.
4. **Evidence for the next re-review:**
   - keep this input as `FIX-016-manifest-review3.json` (`5bdb5496`), and copy its files to an
     ignored folder before changing anything;
   - hand-worked expected values and mutants for the new rules;
   - the story file, PR-009's story file and the full suite;
   - `check_broad_except`, `check_kt_docs`, and the PDF if the KT changes;
   - a regenerated manifest, a rework diff against this input, and the cumulative diff against
     `8cb626c`.

### The reviewer's own cases

`analysis_data/fix016_rereview2/test_rr2_fix016.py`, with its own `conftest.py` importing the
hermetic hooks, and its own price model, written separately from the implementer's `_Market`.
Each share's worth in real terms; from a row's ex day the equity trades at a stated fraction of it.
NSE's close is raw, Yahoo agrees, and NSE's list is a 2012 dividend plus each stock's rows in NSE's
own wording.

**10 passed:**

- **Q1:** BRITANNIA's own row ("Scheme Of Arangement- Bonus - 1 Debenture For 1 Equity Share
  Held") between the closes is no result.
- **Q2 (×2):** a demerger worded "Scheme Of Arrangement" (GRASIM 2017) or "Demerger" is no result.
- **Q3:** the same demerger worded "Scheme Of Arangement" is graded −40 (asserted as observed).
- **Q3 gate (×2):** spelt correctly, the RR2 population fails. Misspelt, it passes at +1.53 on 9
  of 15 and recommends the switch.
- **Q5:** ZEEL's wording gives a bonus of 22 and a +1,935% keep.
- **Q5 gate:** a −1.27% keep population passes, at a mean above +100%, and recommends the switch.
- **Q6:** `TVSMOTORS` through the alias reads an empty list and has no result at both horizons.
- **Q4:** the wording table (printed, 41 subjects). Every quoted NSE row gives the class described
  in RR2-F1. "Return Of Capital" and "Composite Scheme" (not seen in NSE's lists) are also
  neutral.

**NSE's public lists** were read with the rework's own probe
(`analysis_data/fix016_rework2/kinds_probe.py`, the production fetcher, 2 s apart) on 29 Oct,
09:04–09:20 IST. Outputs:

- `britannia_probe_2026-10-29.txt` (BRITANNIA);
- `universe_probe_2026-10-29.txt` (the 187 configured symbols the 25 Oct probe had not read);
- `alias_probe_2026-10-29.txt` (TVSMOTOR, CANBK).

Totals across the 187: 2,406 dividends, 380 neutral, 55 bonuses, 38 splits, 8 demergers, 14 rights
and 5 schemes. Every row is a public corporate-action subject; no private data.

### Commands and environment

Windows 11, the `.stockai` venv (Python 3.13), with the hermetic boundary on (SA-005).

| Command (repository root) | Result |
|---|---|
| `.stockai/Scripts/python.exe scripts/docs/kt_manifest.py verify docs/planning/PI-2026-09/evidence/FIX-016-manifest.json` | 13 files, mismatches `[]`, `5bdb5496…` (start and end) |
| `.stockai/Scripts/python.exe analysis_data/fix016_rereview2/rr2_digest.py` | `44143f54…` 78,802 B, `564fc952…` 201,380 B, `dd54d848…` 202,860 B, 12 paths, HEAD `8cb626c` (start and end) |
| `pytest -q -p no:cacheprovider tests/unit/test_exit_fix016.py tests/unit/test_exit_evidence_pr009.py` | **106 passed** in 76 s |
| `pytest -q -p no:cacheprovider --rootdir analysis_data/fix016_rereview analysis_data/fix016_rereview/test_rr_fix016.py` (re-review 1's cases) | 3 failed (RR1, RR2 demerger, RR3: each grade is now no result where the defect value was asserted), 9 passed |
| `pytest -q -p no:cacheprovider --rootdir analysis_data/fix016_rereview2 analysis_data/fix016_rereview2/test_rr2_fix016.py` | **10 passed** |
| `python analysis_data/fix016_rework2/rw2_mutants.py baseline` + the rework's 19 new mutants | 19 of 19 caught, baseline clean (106 passed) |
| `pytest tests -q -p no:cacheprovider` (full suite, 09:08-09:37 IST, beside the NSE probe and the mutants) | **5,778 passed / 12 skipped / 1 xfailed / 0 failed (28m40s, beside the NSE probe and the mutants)** |
| `scripts/ci/check_broad_except.py` | OK (151 grandfathered) |
| `scripts/docs/check_kt_docs.py` | errors `[]` |
| `analysis_data/fix016_rereview/pdf_check.py` | 59 pages; cover digest `7ceed0eedf33` = the KT's LF SHA-256 |

**Not exercised:**

- production: nothing was read;
- Yahoo's handling of a preference-share bonus, which does not matter here: the horizon close is
  NSE's raw close in Q5;
- the implementer's 62 earlier mutants (their log shows them caught with rework 2's tree).

### Acceptance checklist

| Criterion | Verdict |
|---|---|
| The card's verdict, event, benchmark and money-check criteria | Met (unchanged since the first review) |
| Re-review 1's RR-F1: no result across a change no ratio converts, RR1–RR3 pinned, docs | Met, for NSE's standard wording |
| RR-L1, I1 | Met |
| Hard review: can a corporate action decide the money check? | **Yes, a row the record misreads can** (RR2-F1) |
| A rename keeps the basis and is graded (KT section 6) | **Only in the fixture** (RR2-M1) |
| PR-009's story file passes, with each changed contract named | Met |
| KT sections 6 and 7, guide cases, `check_kt_docs`, PDF; story file and full suite | Met (RR2-F1's and RR2-M1's text aside) |

### Decision and state

**CHANGES REQUESTED.**

- **STATE:** FIX-016 is `changes_requested`, with a `rereview_2` record. `active_task` and
  `next_task` are FIX-016 (**rework 3**, in a new conversation), then a fresh re-review in
  another.
- **New card:** FIX-017 (P2, 2 points, `todo`) is queued after FIX-015. Its KT section 12 row is a
  commit-time edit.
- **`production_verification`** stays `not_started`.
- **PR-009's push stays held** (owner, 24 Oct) until FIX-016 is accepted. Then the two go out in
  one push, at the owner's word, in a job-free window.
- **The guide's status lines** ("fresh re-review pending") are reviewed paths and are left to
  rework 3.

## Fresh re-review of rework 1: CHANGES REQUESTED (2026-10-25)

**Phase:** fresh-session re-review of rework 1, a new conversation opened with "continue" (25 Oct,
about 07:59–08:40 IST, session `stockagent-main-4f`). FIX-016 was implemented in
`stockagent-main-a6`, reviewed in `-f7` and reworked in `-e2`; this conversation is none of them
and did not read them. Every peer session was idle at the start and before the bookkeeping
(ListAgents).

**Verdict: CHANGES REQUESTED.** One new high finding, reproduced through the real price path:

- **RR-F1:** a **demerger** between a decision and its horizon is still graded as a fall. The
  rework's basis rule reads only bonus and split rows, so the part of the company that left reads
  as a loss, and the money check adds it. With one 40% demerger, a rule that loses 1.27% a decision
  passes the gate and is recommended the next week (RR2).

Everything the review asked for is done and works:

- F1 as specified: a bonus or split is allowed for, and an unestablished basis is no result, which
  never helps the evidence rule;
- F2: a SWITCH whose buy the executor would refuse records `cash`;
- F3, I1 and I2.

RR-F1 is the same defect class as F1, in the same financial target. The owner held PR-009's push so
that the gate, including how a result is measured, is fixed before any shadow row exists, and the
fix is small. So it is settled before the push, not routed.

**Nothing was committed, pushed, deployed or configured.** No production state was read, no model
was called, no message was sent and no network call was made. The only tracked files this
re-review changed are STATE, HANDOFF and this receipt. The reviewer's scripts and outputs are in
the ignored `analysis_data/fix016_rereview/`.

### In one example (RR-F1)

BBB is held. On Friday 23 Oct the evidence rule sells it at ₹190 as a plain EXIT, and the
price-path rule keeps it, so the row's benchmark is `cash`. On Wednesday 28 Oct BBB demerges a
business worth 40% of its value. One BBB share now trades at ₹114, and the holder also owns shares
of the new company worth ₹76. Nothing was lost.

- **By hand:** the sale saved nothing, so it was wrong, with a result of 0.
- **The grade:** ₹190 against ₹114 is −40%, so the sale is "right" with **+40**. Had the
  price-path rule sold and the evidence rule kept, the same demerger reads −40 against the
  evidence rule (RR1, through the real pipeline's rows).

**The gate (RR2), through the real scorecard block and the real price lookups:**

- **15 sales by the evidence rule:** 8 then fell 2% (right, +2 each) and 7 rose 5% (wrong, −5
  each). That is (8 × 2 − 7 × 5) / 15 = −1.27% a decision, and it fails, as it must.
- **One change:** one of the 7 wrong sales is in a stock that demerges 40% three sessions later. Its
  graded return is 105 × 0.6 − 100 = −37%, so the sale becomes "right" with +37.
- **The gate then reads** right on 9 of 15 with a mean of (16 + 37 − 30) / 15 = +1.53%: a pass.
  The next Sunday it reads "passed two weeks running" and recommends the switch.

**Where it comes from.** `horizon_in_basis` keeps only bonus and split rows
(`core/portfolio/exit_shadow.py:503-504`). `action_record` marks a row as unparsed only when its
text names a split, bonus or sub-division (`core/portfolio/corp_actions.py:62-64, 146`). A demerger
row is neither applied nor unparsed, so the basis counts as established.

**It happens to large companies.** NSE's public lists, read on 24 Oct by session `-87`'s probe
(`analysis_data/pr009_rereview/nse_reach_probe_2026-10-24*.txt`), hold a demerger row for RELIANCE
and for TMPV: 2 demerger rows against 8 bonus or split rows in the 12 lists read. So a demerger is
less likely than F1's bonus, about a quarter as often in those lists, and it must take about 40% or
more of the price to flip a gate as narrow as RR2's. The consequence is F1's.

**The design already says so.** The instrument registry's own rule is "prices on different bases
are never compared" (`config/instruments.yaml:14-16`), and KT section 6 calls a demerger "the same
trap" as a bonus. A demerger the registry records as a new basis is still graded across the two
bases, although `identity_break` names the break (RR3).

### Review input verified

- **Manifest:** [FIX-016-manifest.json](FIX-016-manifest.json), sha256 `9b8e7457…dc3`, 12 files.
  `scripts/docs/kt_manifest.py verify` gives 0 mismatches at the start and at the end.
- **Rework diff:** `e0efc6bae97dde90f2daafdfe863937b64a324b9f4b0c21ad8b2acfcada983b0`, 108,455
  bytes, 11 paths. The script first checks the review input copy byte for byte against
  `FIX-016-manifest-review1.json` (`72268ff3`).
- **FIX-016's own diff:** `ee7a3f84…2e37`, 168,563 bytes.
- **Cumulative against HEAD `8cb626c`:** `fc0cab4bd5700bfed62a2c8a50e0a0db7c1fdcc6178bfc76802eb7dc1fff0944`,
  170,043 bytes, 11 paths.
- **How they were rebuilt:** by `analysis_data/fix016_rereview/rr_digest.py`, the rework's recipe
  writing into this folder, at the start and at the end. All three match the rework receipt.
- **No drift:** no tracked file changed after 24 Oct 17:50 IST, when the rework's bookkeeping
  ended. No re-review edit touched a reviewed path.

### Contract checked

| Contract | Result | How it was checked |
|---|---|---|
| F1 as asked: a bonus or split between the closes is allowed for | **Holds** | `horizon_in_basis` (`exit_shadow.py:464-531`): ratios ex in (close's bar, horizon's bar], an ex day's own close not converted, one ratio per day and kind. Reviewer world model (RR4, written separately from the implementer's): a flat stock after a 1:1 bonus grades 0, BBB wrong with 0, AAA right with 0. The story file's 10 hand cases. 5 implementer mutants on this rule and 1 on the lookups re-run and caught. |
| An unestablished basis never helps the evidence rule | **Holds for the causes it lists** | It is `ungraded` with `no_basis`, so its result is unknown and `gate_look` fails the money check. RR4b: a Yahoo-only close read after a later bonus is no result. The S15 test; mutant `unknown_graded_raw` caught. |
| A corporate action is not a result (the review's expected outcome) | **Fails for a demerger** (RR-F1) | RR1, RR2, RR3 |
| Information as of the horizon | **Holds for prices** | NSE's list is read at grading, so it holds later actions. A later action is never applied to a raw close, and it makes a Yahoo-only close no result. |
| F2: where a refused SWITCH's money went | **Holds** | `switch_buy_lands` makes the executor's checks before sizing, in the same order (`autopilot.py:207-245`): a close; under `enforce`, the session's own bar and a resolved identity; `sizing.entry_check`. It uses the same `shelf_index` object. RR5: at ₹48.49, ₹48.50, ₹51.00, ₹51.01, ₹45.00 and ₹45.01 it agrees with `entry_check`, and with the hand rule. Mutants `lands_ignored`, `band_not_checked` and `row_not_told` caught. The other causes are the KT limit. |
| F3, I1, I2 | **Done** | The `advisor.py` comment and the KT sentence; `_ist_day` in the reason; the docstring reflowed. |
| The benchmark is read from the row; PR-009's invariants | **Hold** | `first_disagreements` and `level_in_basis` are untouched. PR-009's 39 tests pass with call-site changes only (`_nse`, `_no_actions`), plus two new tally keys. No assertion was relaxed. |
| Documentation | **Describes the implemented behaviour, except RR-F1** | KT section 6 ("One price basis", the bonus example, limits) and section 7. Guide 07-L, 07-M and 09-H, with 09-H's bonus figures re-derived: ₹110 / 2 = ₹55, ×2 = ₹110, +10%, wrong, −3.6%. The CODEBASE row. The PDF has 58 pages, and its cover digest `edd5f1305a60` equals the KT's LF SHA-256. `check_kt_docs`: errors `[]`. |

**Rulings on the rework's decisions:**

- **RW-D1 is upheld.** It also sets the shape of RR-F1's fix: no result, not a bound.
- **RW-D2 and RW-D3 are upheld.**
- **RW-D4 is upheld**, because it fails safe. RR-L1 corrects the KT's wording.
- **RW-D5 is upheld**, and dividends stay a limit.

### Findings

| ID | Severity | Location | Trigger | Observed | Expected | Disposition |
|---|---|---|---|---|---|---|
| **RR-F1** | **High** (confirmed: RR1 through the real pipeline's rows and the real `results.stock_quote_fn` → `pricing.session_close` → `daily_review._fetch_session_close` → `close_verifier`, and `results.corp_actions_fn` → `fetch_corp_actions` → `action_record`; only `yfinance.download`, NSE's close and NSE's `actions()` faked. RR2 through the real scorecard block. RR3 with a registry file. Demerger rows in NSE's lists measured on 24 Oct.) | `core/portfolio/exit_shadow.py:503-504` (only `SHARE_COUNT_KINDS` rows); `core/portfolio/corp_actions.py:62-64, 146` (a demerger row is neither parsed nor unparsed); `exit_shadow.py:464` never asks `identity_break` (`symbol_resolver.py:304`) | A demerger goes ex after the decision close's bar and on or before the horizon close's bar. This holds whether or not the registry records it. | A flat stock grades −40%: the seller right with +40, the keeper wrong with −40. One 40% demerger lets a rule that loses 1.27% a decision pass the gate and be recommended the next week. A registered demerger is graded across two bases. | A corporate action the grade cannot convert is not a result: the decision has no result that week, named, as for an unparsed bonus row. | **Required in rework 2** (below) |
| **RR-L1** | Low (docs) | KT section 6 limits (`docs/TECHNICAL_DESIGN.md`, the "price basis stays unknown" bullet) | NSE's list comes back empty for a stock that has never had an action | The KT says this is "a recent listing that has paid no dividend yet". Session `-87`'s probe read 0 rows for ETERNAL, a large company listed in 2021. The gate's population has no time window, so one such decision keeps the money check failing for as long as the list stays empty. That can be for good. | The bullet names the case plainly, such as a company that has never paid a dividend, and says it keeps the gate from passing while that decision is in the population. ETERNAL is not in the configured universe today. | **Recommended in rework 2** (docs), or a commit-time edit |
| **I1** | Info (code inspection) | `core/portfolio/pipeline.py:274-287` (`switch_lands`) | Any exception other than `PriceUnavailableError` from `session_close` or `symbol_identity_issue` | The pipeline's outer `except` drops that holding's shadow row for the day. The executor treats any exception as a skipped buy. Neither call raises anything else today: `load_registry` and `cross_check_close` never raise, and the Yahoo attempts are wrapped. | — | Optional: catch as the executor does, and record `cash` |

**Checked, and not findings:**

- **`agree` is treated as raw.** Yahoo's auto-adjusted close agrees within 1% of NSE's raw close.
  What is left over is at most a later dividend, which is the stated dividend limit.
- **The process-wide quote cache** is keyed by stock and day. It keeps only a past day's own bar in
  NSE's raw basis, so no Yahoo-only figure outlives a read.
- **Two holdings switching into one destination** get the same answer, from one fetch per run. A
  second buy refused by sizing falls under the stated limit (under one share after sizing).
- **Rights issues** are listed by NSE too (RELIANCE, BAJFINANCE, TMPV in the probe). The price
  falls by the value of the entitlement, usually a few percent for a large company: the dividend
  limit's size. Rework 2 decides whether a rights row is no result or a stated limit.

### Rework 2: what must be true at the next re-review

1. **RR-F1, required.**
   - A decision has **no result**, and the line names why, when either of these lies after the
     decision close's bar and on or before the horizon close's bar. Use the same review-day and
     Yahoo-only windows the bonus rule uses.
     - NSE's list holds a row that changes the price basis and that grading does not convert.
       This covers at least a demerger, the word NSE's lists carry (measured). The implementer
       decides the rest and records it as a decision: a scheme of arrangement, a consolidation
       (a row that names neither split nor sub-division is unparsed today), a capital reduction,
       and a rights issue (no result, or a stated limit beside dividends).
     - The instrument registry records a new price basis (`identity_break(symbol, start, bar)`).
   - Valuing the split-off shares is not required.
   - **Pin RR1, RR2 and RR3** as invariant tests through the real price path. Their defect
     assertions are in `analysis_data/fix016_rereview/test_rr_fix016.py`, and they should fail
     after the fix. RR4, RR4b and RR5 should keep passing.
   - **Docs:**
     - KT section 6's "One price basis" says what it converts (a bonus, a split) and what is no
       result (the new causes);
     - the limits;
     - one line in a guide case (09-H or 07-M);
     - the CODEBASE row, if the helper changes.
2. **RR-L1:** the KT limit's wording, as in the table.
3. **I1:** optional.
4. **Evidence for the next re-review:**
   - keep this input as `FIX-016-manifest-review2.json` (`9b8e7457`), and copy its files to an
     ignored folder before changing anything;
   - hand-worked expected values;
   - mutants for the new causes;
   - the story file, PR-009's story file and the full suite;
   - `check_broad_except`, `check_kt_docs`, and the PDF if the KT changes;
   - a regenerated manifest, a rework diff against this input, and the cumulative diff against
     `8cb626c`.

### The reviewer's own cases

`analysis_data/fix016_rereview/test_rr_fix016.py`, with its own `conftest.py` importing the
hermetic hooks. It reuses PR-009's `_pipeline_world` for the rows and writes its own world model:

- the real value per old share;
- a demerger leaves the parent at a fraction of that value;
- a bonus divides the raw close;
- Yahoo's series is adjusted for later bonuses;
- NSE's list is a 2010 dividend plus each action's row ("Demerger", "Bonus 1:1").

**12 passed:**

- **RR1:** a 40% demerger grades flat BBB at −40 (+40 to the seller) and AAA at −40 against the
  keeper. The parser keeps the row neither as an action nor as unparsed. RR1 asserts today's
  defective values, and its docstring holds the expected ones.
- **RR2:** parametrized. With no demerger it fails at −1.27, right on 8 of 15 (the control). With
  one 40% demerger it passes at +1.53, right on 9 of 15, and the next week it recommends the
  switch.
- **RR3:** a registry file records BBB's demerger into BBBA.NS as a new basis. `identity_break`
  names the break, and the grade is −40%.
- **RR4:** the bonus control in this world: 0 and 0. **RR4b:** a Yahoo-only close after a later
  bonus is no result.
- **RR5:** six band-edge prices: `switch_buy_lands` equals `entry_check` and the hand rule.

### Commands and environment

Windows 11, the `.stockai` venv (Python 3.13), with the hermetic boundary on (SA-005).

| Command (repository root) | Result |
|---|---|
| `.stockai/Scripts/python.exe scripts/docs/kt_manifest.py verify docs/planning/PI-2026-09/evidence/FIX-016-manifest.json` | 12 files, mismatches `[]`, `9b8e7457…` (start and end) |
| `.stockai/Scripts/python.exe analysis_data/fix016_rereview/rr_digest.py` | `e0efc6ba…` 108,455 B, `ee7a3f84…` 168,563 B, `fc0cab4b…` 170,043 B, 11 paths, HEAD `8cb626c` (start and end) |
| `pytest -q -p no:cacheprovider tests/unit/test_exit_fix016.py tests/unit/test_exit_evidence_pr009.py` | **95 passed** in 28.6 s |
| `pytest -q -p no:cacheprovider --rootdir analysis_data/fix016_rereview analysis_data/fix016_rereview/test_rr_fix016.py` | **12 passed** in 8.9 s |
| `pytest -q -p no:cacheprovider --rootdir analysis_data/fix016_rework1/rv_adapted …/test_rv_fix016_adapted.py` | 2 failed (the two defect assertions of the review's RV1 and RV2, as the rework receipt says), 3 passed |
| `python analysis_data/fix016_rework1/rw_mutants.py baseline basis_ignored later_actions_counted stored_close_trusted yahoo_alone_trusted unknown_graded_raw lands_ignored band_not_checked row_not_told list_read_per_horizon` | baseline clean (95 passed); **9 of 9 caught** |
| `pytest tests -q -p no:cacheprovider` (full suite, 08:22–08:34 IST) | **5,767 passed / 12 skipped / 1 xfailed / 0 failed (11m28s)** |
| `scripts/ci/check_broad_except.py` | OK (151 grandfathered) |
| `scripts/docs/check_kt_docs.py` | errors `[]` |
| `analysis_data/fix016_rereview/pdf_check.py` | 58 pages; cover digest `edd5f1305a60` = the KT's LF SHA-256 |

**Not exercised:**

- production: nothing was read;
- a real NSE or Yahoo response. NSE's exact wording for a demerger row was not saved: the 24 Oct
  probe classified a row as a demerger by that word in its text. How Yahoo adjusts its series for
  a demerger does not matter here, because the horizon close is after the ex date in both sources;
- the implementer's other 53 mutants (their log shows 62 of 62).

### Acceptance checklist

| Criterion | Verdict |
|---|---|
| The card's verdict, event, benchmark and money-check criteria | Met (as in the first review; unchanged by the rework) |
| Review F1: one price basis for a bonus or split, an unestablished basis never helps, RV1 and RV2 pinned, docs | Met |
| Review F2 (recommended), F3, I1, I2 | Met |
| Hard review: can a corporate action decide the money check? | **Yes, a demerger can** (RR-F1) |
| PR-009's story file passes, with each changed contract named | Met |
| KT sections 6 and 7, guide cases, `check_kt_docs`, PDF; story file and full suite | Met (RR-F1's text aside) |

### Decision and state

**CHANGES REQUESTED.**

- **STATE:** FIX-016 `changes_requested` with a `rereview_1` record; `active_task` and
  `next_task` FIX-016 (**rework 2**, in a new conversation), then a fresh re-review in another.
- **`production_verification`** stays `not_started`.
- **PR-009's push stays held** (owner, 24 Oct) until FIX-016 is accepted. Then the two go out in
  one push, at the owner's word, in a job-free window.
- **The guide's status lines** ("fresh re-review pending") are reviewed paths and are left to
  rework 2.

## Fresh review: CHANGES REQUESTED (2026-10-24)

**Phase:** fresh-session review, a new conversation opened with "continue" (24 Oct, about
12:58–13:30 IST, session `stockagent-main-f7`). FIX-016 was implemented in session
`stockagent-main-a6`; this conversation is not that one and did not read it. Every peer session was
idle at the start and before the bookkeeping (ListAgents).

**Verdict: CHANGES REQUESTED.** One high finding is unresolved, reproduced through the real price
path:

- **F1:** a bonus or split between a decision and its horizon is graded as a fall of 50% or more.
  The new money check adds that figure into the gate's mean, so one corporate action can decide the
  gate. With one bonus, the card's own failing example (right on 8 of 15, −3.6% a decision) passes
  the gate and is recommended two weeks running.

Every acceptance criterion as the card words it is met, and the four corrections work as specified:

- a verdict the buyer could have seen, or one older than 22 sessions, never sells;
- a news article never sells by any route through `case_broken`;
- the benchmark is fixed in the row on the decision day and read only from there;
- a missing or pending grade never helps the money check.

F1 is in the financial target that the new money check sums. The gate is meant to be fixed before
any shadow row exists, and PR-009's push is held for this story, so F1 has to be settled before the
push.

**Nothing was committed, pushed, deployed or configured.** No production state was read, no model
was called, no message was sent and no network call was made. The only tracked files this review
changed are STATE, HANDOFF and this receipt. The reviewer's scripts and outputs are in the ignored
`analysis_data/fix016_review/`.

### In one example (F1)

BBB is held, and on Friday 23 Oct the evidence rule sells it (an actionable SELL) while the
price-path rule keeps it. It is a plain EXIT, so the row's benchmark is `cash`. The real pipeline
stores the close both rules saw, ₹190. Three sessions later a 1:1 bonus goes ex. The company's
value does not change, and the stock trades at ₹95, which is ₹190 in the old shares.

- **The portfolio** is right: the corp-action sync makes a still-held BBB twice the shares at half
  the cost, so a bonus is not a loss (KT section 6, "Identity hold").
- **The grade** is not. `grade_disagreements` compares the stored ₹190 with the ₹95 close 10 and 30
  sessions on (`exit_shadow.py:469`). The real lookup returns NSE's raw close there, and Yahoo
  agrees after the ex date. The stock's return reads −50%, so the sale was "right" with a result of
  **+50**. In the holding's own basis the return is 0: the sale saved nothing, so it was wrong, with
  a result of 0 (repro RV1).
- **Had the price-path rule sold** and the evidence rule kept it (AAA in the same run), the same
  bonus reads −50 against the evidence rule.

**The gate (RV2), through the real weekly scorecard block and the real price lookup:**

- **The card's example:** 15 plain-EXIT sales by the evidence rule, 8 of which then fell 2% and 7
  rose 10%. That is (8 × 2 − 7 × 10) / 15 = −3.6% a decision, and it fails, as it must.
- **One change:** one of the 7 wrong sales is in a stock that goes ex on a 1:1 bonus 3 sessions
  later. Its true return is +10%. Its graded return is 110 / 2 − 100 = −45%, so the sale becomes
  "right" with +45.
- **The gate now reads** right on 9 of 15 (60%), with a mean of +0.07%: a pass. The next Sunday it
  reads "Switch gate: passed two weeks running (not worse than the price-path rule in count and
  money), so the evidence rule may replace the price-path rule."

**Why the earlier ruling no longer holds.** PR-009's review saw this basis question and ruled it
"not a finding": a convention shared with the auditor. Then the gate only counted hits, so a bonus
flipped one count among 15 or more. FIX-016 adds the results themselves. They are unbounded (D8
says so), and a 1:1 bonus is −50, a 1:5 split −80. Over 15 decisions, one such term moves the mean
by 3 to 5 points, more than the gap the money check is there to catch.

**It happens to large companies.** NSE's public list, read on 24 Oct by session `-87`'s probe,
shows LICI's 1:1 bonus, ex 29 May 2026. How often a holding goes ex within 30 sessions of a decision
is not measured here.

### Review input verified

- **Manifest:** [FIX-016-manifest.json](FIX-016-manifest.json), sha256 `72268ff3…a51`, 10 files.
  `scripts/docs/kt_manifest.py verify` gives 0 mismatches at the start and at the end.
- **FIX-016's own diff:** `dd35017d2820bf8b49cee222c44e8b09ee8ca19ec5f16fdaf30a4b70fbcd1763`,
  105,082 bytes, 9 paths.
- **Cumulative against HEAD `8cb626c`:**
  `c583962ef57aedb44759ae0b623f3739009a6f2ba8b8cbd61a024695a7510001`, 106,562 bytes.
- **How both were rebuilt:** by `analysis_data/fix016_review/rv_digest.py`, the receipt's recipe
  writing into the review folder, at the start and at the end. Both match the implementation
  receipt, and the KT and guide start copies have the SHA-256s the receipt names.
- **No review edit** touched a reviewed path.

### Contract checked

| Contract | Result | How it was checked |
|---|---|---|
| A verdict the buyer saw never sells (hard review Q1) | **Holds** | `exit_shadow.py:140-167`. A run on or before the buy's IST day, or before `trading_days_ago(on, 22)`, is skipped before the newest is chosen, so neither a pre-buy SELL nor a pre-buy BUY reaches the rule. `trading_days_ago` counts sessions strictly before `on`, so a run on that day has exactly 22 sessions in (run day, review day]. An ADD keeps the holding's `buy_date` (`autopilot.py:174-190`), so it never resets the window. The monthly forecast analyses every enabled managed ticker through the orchestrator, which writes the score history (`scheduler.py:995-1023`, `base_orchestrator.py:297-313`). |
| A news article cannot sell another way (Q2) | **Holds for `case_broken`; see F3 for what "filed" means** | The split at `exit_shadow.py:268-269` and the source guard at `advisor.py:466-468` each stop it (the implementer's mutants `news_sells_in_assembly` and `source_guard_removed`, re-run and caught). No stop or other exit trigger reads events. A research verdict can reflect news the analyst read, by design: it is an analysis, not an event. PR-005's card carries the pillar rule. |
| The benchmark is the decision day's (Q3) | **Holds; see F2 for a SWITCH that did not reinvest** | `decision_benchmark` runs when the row is written (`exit_shadow.py:373`). Grading reads `row["benchmark"]` and nothing else, and `first_disagreements` makes the holding's first row the decision. The reviewer re-ran the story's every-mode test. |
| Ungraded or pending decisions cannot help the money check (Q4) | **Holds for missing and pending; a basis artefact helps (F1)** | `gate_look:542-555`. Pending at 30 sessions is outside the population. A missing result at either horizon fails the money check and is not right in the count. The 2,000-population oracle and the missing-result property agree. |
| PR-009's invariants (Q5) | **Hold** | `first_disagreements` and `level_in_basis` are untouched, and events and verdicts are still read as of the review day. PR-009's 39 tests pass with the named helper changes: `_row` gains a benchmark, `_random_case` a source, `_grades` a result. No assertion was relaxed. |
| Tests derive their expectations independently | **Yes** | The −3%/−5% table, the 22/23-session dates (counted by hand against the fixture holidays), the 8-of-15 line and the 11-of-15 label are hand values. The oracle is written from the card in exact fractions. The pipeline tests run the real pipeline, store and autopilot. The hermetic boundary is on. |
| Documentation | **Describes the implemented behaviour** | KT section 6 (rules, example, grading, gate table, "not worse", two limits) and the section 7 line; guide 07-L, 07-M and 09-H, with their figures re-derived by hand (09-H second version (8 × 5 − 8 × 1) / 16 = +2.00; first version fails on 7 of 16 at 10); CODEBASE rows; the config comment. The PDF cover's source digest `3608dff5c85f` equals the KT's manifest SHA-256 (57 pages). `check_kt_docs`: errors `[]`. |

**Rulings on the implementer's decisions:** D1 (the 22-session boundary), D2 (the buy day never
counts), D3, D4 (an allow-list), D6, D7, D9 and D10 are **upheld**.

- **D5 is upheld** for which verdict sets the benchmark; F2 is about a SWITCH whose proceeds never
  left cash.
- **D8 is upheld**, and F1's rework must apply it: a result whose price basis cannot be established
  must never help the evidence rule either.

### Findings

| ID | Severity | Location | Trigger | Observed | Expected | Disposition |
|---|---|---|---|---|---|---|
| **F1** | **High** (confirmed: RV1 through the real pipeline and the real `results.stock_close_fn` → `pricing.close_on` → `daily_review._fetch_session_close`, with only `yfinance.download` and NSE's close faked at the boundary; RV2 through the real scorecard block) | `core/portfolio/exit_shadow.py:469` (`grade_disagreements`: the row's stored close against `stock_close_on(symbol, matured)`); NSE's raw close wins a disagreement at `services/data/fetchers/close_verifier.py:164-177` | A bonus or split goes ex after the decision's bar and on or before a horizon | A flat stock grades −50%: the seller is right with +50, the keeper wrong with −50. The card's −3.6% example passes the gate with one bonus, and "passed two weeks running" follows. | The return is in one price basis, so a flat stock is 0 and the card's example fails. A corporate action is not a result. REVIEW.md lists price identity among the targets that need an invariant test. | **Required in rework 1** |
| **F2** | **Medium** (confirmed: RV3, through the real pipeline and autopilot) | `exit_shadow.py:341-357` (`decision_benchmark`); the row is written at `pipeline.py:351-356`, before the autopilot (`pipeline.py:363` on); the buy leg is skipped at `autopilot.py:207-257` | A SWITCH whose buy leg does not land. The usual cause is the entry band: the advisor proposes a SWITCH without checking it, the executor does (guide 07-I), and a deep dive sets the band at 97–102% of its own close (`deep_dive.py:101-106`) while the idea stays on offer for as long as that dive is fresh. Other causes: no price, a stale close or an unresolved identity under `enforce`, under one share. | The SELL executes, its note says the proceeds stay in cash, cash rises, and the row says `nifty`. | The card's purpose is "the money's real alternative". Here that is cash, so the stock's own return is the yardstick. The grade is otherwise off by the Nifty's move over the horizon, in the same direction for every such sale in a trending market. The evidence rule's own SWITCH in `shadow` never runs, so its buy leg is never tested. | **Recommended in rework 1.** At row time, apply the executor's deterministic entry check (`sizing.entry_check` on the candidate's close) to either rule's SWITCH, and record `cash` when its buy leg would not land. State the remaining causes as a KT section 6 limit. Otherwise, at least that limit. |
| **F3** | Low (code inspection) | KT section 6 (`docs/TECHNICAL_DESIGN.md:1125-1127`) and the comment above `CASE_EVENT_SOURCES` (`core/portfolio/advisor.py:438-441`) | Reading why news cannot sell | The text says a news article cannot sell because the bulk-tier model sets its direction and materiality, which suggests a filing's label is different. The same bulk-tier call types NSE announcements and board-meeting intimations (`core/events/classify.py:198`; KT section 4, step 4). Only disclosures are typed by rules. A routine filing labelled high-negative still sells. | One sentence: an NSE filing's direction and materiality are the bulk-tier model's reading too. A filing can sell because the item itself is a primary source, and PR-012's label-accuracy bench (zero routine items labelled high-negative) measures the label. The owner chose this (card, intended result 2), and PR-012's routed input already knows it. | **Rework 1** (docs), or a commit-time edit |
| **I1** | Info (code inspection) | `advisor.py:474`; guide 07-L | A run between 00:00 and 05:30 IST on the day after the buy | The reason prints `research_run_at[:10]`, a naive-UTC date: "research verdict SELL (2026-10-08)" for a holding bought on 8 Oct, from a run at 00:01 IST on 9 Oct. 07-L asks the tester to check that the run was after the buy day. | The reason shows the IST day the rule used, or 07-L says that `research_run_at` is naive UTC. | Optional |
| **I2** | Info | `core/portfolio/advisor.py:21` | — | One module-docstring line is 124 characters (not reflowed after the edit). No lint enforces a length. | Reflowed | Optional |

Checked, and **not** findings:

- **Dividends** are the same shape at a small size. The raw-close return leaves out a dividend that
  went ex in the window (often 1–2%), so it slightly favours a sale over keeping. Including it with
  F1's fix (total return) is optional.
- **The new `except Exception`** around the Nifty return (`exit_shadow.py:473`) re-raises for a
  `nifty` row and leaves only the Nifty figure empty for a `cash` row. `check_broad_except` passes.
- **"Newest" by `run_at` string** is PR-009's, unchanged.
- **A disabled managed holding** (`enabled: false`) gets no monthly re-analysis. It is covered by
  the new KT limit ("a holding whose monthly re-analysis did not run").

### Rework 1: what must be true at the re-review

1. **F1, required.**
   - **The return between the decision's close and each horizon is in one price basis.** For
     example, multiply the horizon close by the ratio of every bonus or split that went ex after
     the close's bar (`price_bar_date`, else the review day) and on or before the horizon day.
   - **The ratios come from the symbol's own record, read at grading** (`corp_actions.fetch_corp_actions`
     and `action_record`). A stock the acting rule sold has no holding, so its `applied_actions`
     cannot be the only source.
   - **When the basis cannot be established,** the grade must never help the evidence rule. Cases:
     the list was not read that Sunday, or an unparsed bonus or split row falls in the window. One
     rule that satisfies this: the decision has no result that week, which fails the money check as
     a missing close does, and the line names why. The rule is the implementer's call; record it as
     a decision. A re-fetch the next week may resolve it.
   - **Pin RV1 and RV2 as invariant tests** through the real price path:
     - the flat stock grades 0, the seller wrong with a result of 0;
     - the card's example with the bonus still fails at −3.6%.
   - **Docs:**
     - KT section 6's grading paragraph states the basis rule with the bonus example;
     - section 6's limits state what an unestablished basis does;
     - a guide case (09-H or 07-M) has a bonus after a decision.
   - Dividends are optional.
2. **F2, recommended** (as in the table), or at least the KT section 6 limit.
3. **F3:** the KT section 6 sentence and the `advisor.py` comment.
4. **I1, I2:** optional.
5. **Evidence for the re-review:**
   - keep this review's input as `FIX-016-manifest-review1.json` before changing anything;
   - hand-worked expected values;
   - mutants for the basis adjustment and for the unestablished-basis rule;
   - the story file, PR-009's story file and the full suite;
   - `check_broad_except`, `check_kt_docs`, and the PDF if the KT changes;
   - a regenerated manifest, a rework diff against this review's input, and the cumulative diff
     against `8cb626c`.

### The reviewer's own cases

`analysis_data/fix016_review/test_rv_fix016.py`, with its own `conftest.py` importing the
hermetic hooks. It reuses PR-009's `_pipeline_world` and FIX-016's `_switch_world`. Prices come
from a market model in real terms per old share: NSE's close is the raw price, and Yahoo's
auto-adjusted close divides earlier days by every later ratio. **5 passed:**

- **RV1:** a bonus grades the flat BBB at −50 (+50 to the seller) and AAA at −50 against the
  keeper. RV1 asserts today's defective values, and its comment holds the expected ones.
- **RV1 control:** with no action, 0 and 0.
- **RV2:** parametrized. With no bonus it fails at −3.6 (control); with one bonus it passes at
  +0.0667, and the next week recommends the switch.
- **RV3:** a skipped SWITCH buy leg leaves the money in cash, with the row at `nifty`.

### Commands and environment

Windows 11, the `.stockai` venv (Python 3.13), with the hermetic boundary on (SA-005).

| Command (repository root) | Result |
|---|---|
| `.stockai/Scripts/python.exe analysis_data/fix016_review/rv_digest.py` | `dd35017d…` 105,082 B and `c583962e…` 106,562 B, 9 paths, HEAD `8cb626c` (start and end) |
| `.stockai/Scripts/python.exe scripts/docs/kt_manifest.py verify docs/planning/PI-2026-09/evidence/FIX-016-manifest.json` | 10 files, mismatches `[]`, `72268ff3…` (start and end) |
| `pytest -q -p no:cacheprovider tests/unit/test_exit_fix016.py tests/unit/test_exit_evidence_pr009.py` | **76 passed** in 33.5 s |
| `pytest -q -p no:cacheprovider --rootdir analysis_data/fix016_review analysis_data/fix016_review/test_rv_fix016.py` | **5 passed** in 15.9 s |
| `python analysis_data/fix016/mutants.py verdict_no_buy_check news_sells_in_assembly exit_graded_vs_nifty money_check_removed` | 4 of 4 caught (one per correction) |
| `pytest -q -p no:cacheprovider tests` (full suite, 13:11–13:25 IST) | **5,748 passed, 12 skipped, 1 xfailed, 0 failed** in 13 min 12 s (the implementation's count) |
| `scripts/ci/check_broad_except.py` | OK (151 grandfathered) |
| `scripts/docs/check_kt_docs.py` | errors `[]` |

**Not exercised:**

- production: nothing was read, and no live price, corporate-action or score-history data was
  examined;
- the implementer's other 29 mutants (their log shows 33 of 33);
- a real NSE or Yahoo response: the price path is real code, with its two network calls faked.

### Acceptance checklist

| Criterion | Verdict |
|---|---|
| Verdict: a pre-buy SELL, a 23-session SELL and a newer BUY over an older SELL do not sell; a 22-session SELL after the buy sells | Met |
| Events: high-negative news does not sell and is a watch item; the same as `nse_announcement` sells; a rule-typed pledge invocation sells | Met |
| Benchmark: −3%/−5% plain EXIT right vs cash, SWITCH wrong vs the Nifty; read from the row; a later config re-grades nothing | Met |
| Money check: oracle on hand-built populations; the 8-of-15 example fails; 50% with a positive mean passes; a missing grade never helps; "better" only at 70% with a positive mean | Met on the populations built. **Not met in substance** once a corporate action falls in a decision's window (F1: the same example passes). |
| PR-009's story file passes, with each changed contract named | Met |
| KT sections 6 and 7, guide 07-L and 09-H, `check_kt_docs`, PDF; story file, changed files and the full suite | Met (F3 wording aside) |
| Hard review: can ungraded or pending decisions help the money check? | No. But a mis-based result can (F1). |

### Decision and state

**CHANGES REQUESTED.**

- **STATE:** FIX-016 `changes_requested`, `active_task` and `next_task` FIX-016 (**rework 1**, in
  a new conversation). Then a fresh re-review in another new conversation.
- **`production_verification`** stays `not_started`.
- **PR-009's push stays held** (owner, 24 Oct) until FIX-016 is accepted. Then the two go out in
  one push, at the owner's word, in a job-free window.
- **The guide's status lines** ("fresh review pending") are reviewed paths and are left to the
  rework.
