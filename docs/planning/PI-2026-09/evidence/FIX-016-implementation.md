# FIX-016 — implementation receipt

**Story:** [FIX-016](../stories/FIX-016.md): fix the evidence exit's inputs and its switch gate
before the shadow starts.

**Phase:** implementation, 24 Oct 2026, about 11:15–12:25 IST. Session `stockagent-main-a6`, a
new conversation opened with "continue". Peer sessions were idle throughout (ListAgents at the
start and before the bookkeeping).

**Baseline:** HEAD `8cb626c` (PR-009's docs commit; `2d290d5` holds PR-009). main is 2 commits
ahead of origin, held by the owner until this story is accepted. The working tree already held
session `stockagent-main-cb`'s uncommitted owner-decision docs (the FIX-016, PR-013 cards; PR-005,
PR-012, SA-049 notes; the PI README; the KT and its PDF; `docs/README.md`; `docs/START_HERE.md`;
STATE; HANDOFF). They are preserved and are not part of this phase's diff (below).

**Status after this phase:** `review_required`. Nothing was committed, pushed, deployed or
configured. No production state was read, no model was called and no message was sent.

## Rework 3 (2026-10-29): each NSE row read in full or not at all, under NSE's code

**Phase:** rework 3 of the fresh re-review's CHANGES REQUESTED
([FIX-016-review](FIX-016-review.md), top section), a new conversation opened with "continue"
(29 Oct, about 10:53–12:15 IST, session `stockagent-main-8a`). Implementation was
`stockagent-main-a6`, the review `-f7`, rework 1 `-e2`, re-review 1 `-4f`, rework 2 `-1f` and
re-review 2 `-f0`; this conversation is none of them. The peers `-5d` and `-f0` were idle at the
start and before the bookkeeping (ListAgents). It includes a same-conversation self-review, which
is not the fresh re-review.

**Status after this phase:** `review_required` (the fresh re-review, in a new conversation).
Nothing was committed, pushed, deployed or configured. No production state was read, no model was
called and no message was sent. One read-only probe read NSE's public corporate-action lists for
all 202 configured symbols (below). PR-009's push stays held until FIX-016 is accepted.

**Input:** the re-review's input, verified unchanged at the start (`kt_manifest.py verify`: 13
files, 0 mismatches, `5bdb5496`), kept as
[FIX-016-manifest-review3.json](FIX-016-manifest-review3.json), and its 13 files copied to the
ignored `analysis_data/fix016_rework3/review_input/` before any edit.

### In one example

The evidence rule keeps KKK at ₹280 on Friday 23 Oct; the price-path rule sold it (cash). On
Wednesday 28 Oct KKK issues 21 bonus preference shares of ₹1 for each equity share, worded as
ZEEL's 2014 row "Bonus Preference Shares 21:1". The equity trades at ₹259, and the number of
equity shares does not change.

- **Before:** the record read a 22-for-1 equity bonus, and the grade multiplied ₹259 by 22: a
  +1,935% keep. One such row let a rule losing 1.27% a decision pass the gate (Q5).
- **Now:** the row names preference shares, and no word list of an equity bonus includes them,
  so the record does not read it as a ratio. The decision has no result at either horizon:
  "NSE lists a split or bonus on 2026-10-28 that could not be read". The gate fails, as it must.

### What changed

1. **RR2-F1: the record fails closed** ([corp_actions.py](../../../../core/portfolio/corp_actions.py)
   `_read_ratio`, `_NEUTRAL_WORDS`, `_RATIO_WORDS`, `_SHARE_COUNT_RE`, `action_record`).
   - **A ratio only when read in full.** `parse_action` must read a bonus or split, the row must
     not name both, and every word of the row must be a word of an equity bonus ("bonus",
     "issue", "eq") or a face-value split ("face value split sub division from … to"), or of a
     neutral part. Beside a change no ratio converts (a bonus with a rights issue), only the
     bonus's or split's own words are read: the change already leaves that day without a
     result, and the bonus keeps its ratio for PR-009's level, as before.
   - **A share-count row not read is unparsed.** A row with "bonus", "split", "splt",
     "sub-div", "fv" or "face value" that is not read as a ratio: a bonus of preference shares,
     debentures or NCRPS, a split in short words ("Fv Splt Frm Rs 10 To Re 1", "Fv Split Rs.10
     To Rs.5"), a bonus with a split. No result between the closes, as before for an unparseable
     row; PR-009's level unused.
   - **Neutral only when known to be.** Any other row is neutral only when it has words and
     every one is of a dividend, a meeting, a vote, a buy back, interest or a redemption, or a
     registrar change, in NSE's spellings (with its notes "(Purpose Revised)", "Book Closure
     Dates", "Per Equity Share"). Else it is kept in `basis_changes` as
     "corporate action of no known kind ('<subject>')": no result between the closes, named,
     e.g. "NSE lists a corporate action of no known kind ('Transfer Of Undertaking') ex
     2026-07-31, after the decision's close (2026-07-28), and no ratio puts the horizon close in
     the decision's price basis across it".
   - **Named kinds, in NSE's measured short words:** a scheme also from "Sch" or "Scheme" alone
     ("Scheme Of Arangement", "Agm/Div-50%/Sch Of Arrang", "Composite Scheme"); rights also
     "Rhs"; capital reduction also "Return Of Capital"; a demerger also "De Merger". These only
     name the reason better: failing closed already gave each no result.
   - **The sync is unchanged.** `parse_action`, `apply_actions_to_holding` and what
     `sync_corp_actions` applies are untouched (the rework diff shows no line of them); only the
     record it returns for PR-009's level changes. The sync's own misreadings are FIX-017.
2. **RR2-M1: NSE's list under NSE's code** ([results.py](../../../../core/portfolio/results.py)
   `corp_actions_fn`): grading asks `fetch_corp_actions(symbol_resolver.nse_symbol(symbol))`, the
   code the close is read under, so TVSMOTORS is read as TVSMOTOR and CANARABANK as CANBK. The
   story's market model now answers only NSE's codes, so RR3's rename is graded through the
   registry's code, and both registry aliases are graded (Q6 pinned).
3. **RR2-L1** (KT section 6 limit): a row without an ex-date is not read; NSE listed 9 on 29 Oct
   (interest payments, a nil dividend, INOXLEISUR's "Merger", NIIT's "Agm/Div-50%/Sch Of
   Arrang"); whether NSE dates such a row once it goes ex was not measured; the registry records
   a merger's new basis.
4. **Docs.** KT section 6 ("Each row is read in full or not at all", the causes, a third
   example, the level's gaps, the limits with the 202-list measurement and the empty lists),
   PDF, CODEBASE (`corp_actions.py`, `exit_shadow.py` rows), guide 09-H (a preference-share
   step) and the status lines of 07-L, 07-M and 09-H.

**Changed contracts** (each named for the re-review):

- `ActionRecord.actions` holds only rows read in full; `unparsed` also holds a bonus of other
  securities and a split in short words; `basis_changes` also holds rows of no known kind, as
  `(ex-date, "corporate action of no known kind ('<subject>')")`.
- `basis_change_kind`: wider patterns (scheme, rights, capital reduction, demerger).
- `results.corp_actions_fn` asks NSE under `nse_symbol(symbol)`.
- `level_in_basis` (PR-009, no code change): a share-count row the record does not read, from the
  dive day on, leaves the level unused. ZEEL's row divided it by 22 and JSWSTEEL's short split
  was ignored; a row of no known kind is treated as the named changes are (KT limit, PR-005).
- Tests: `_Market`'s NSE answers only codes in `value`. No assertion was relaxed and no earlier
  expected value changed. Rework 1's "Bonus 1:1 (revised)" case still reads as a bonus because
  "revised" is one of NSE's words (about 100 rows).

### Decisions (delegated, recorded)

- **RW3-D1, fail closed (re-decides RW2-D1, overturned by the re-review).** A row is neutral only
  when every word is known to be neutral, and a ratio only when every word is known. A wording
  never seen can cost a decision its result, which fails the money check (for good under RW2-D6),
  but it can never decide one. Measured cost: of the 3,206 dated rows in the 202 lists, 27 are of
  no known kind and 13 share-count rows are not read; all are from 2008 to 2021 except
  TVSMOTOR's 2025 NCRPS bonus (rightly unread); of the 849 rows dated from 2024, none is of no
  known kind.
- **RW3-D2, the words are measured, misspellings are not added.** Every word in the vocabulary
  occurs in the 202 lists. NSE's notes and joining words ("revised", "purpose", "book closure",
  "dates", "equity", "second", "plus", "including") are added: about 125 rows use them, and they
  say nothing about the basis. Misspellings ("Dividned", "Pr Share", "Annnual", "Meetingdividend")
  are not: the latest is from 2021, and an unknown spelling is exactly what failing closed is
  for.
- **RW3-D3, a row of no known kind goes to `basis_changes`, a share-count row to `unparsed`.** The
  reason then says what is known ("a split or bonus … could not be read" or "a corporate action
  of no known kind ('…')"), and the windows are the same. PR-009's level reads `unparsed`, so any
  split or bonus it cannot read leaves the level unused; a row of no known kind is treated as the
  named changes are (the KT's PR-005 limit).
- **RW3-D4, beside a named change only the clause is read.** "Bonus 1:1/Rights 1:5 @ Premium Rs
  100/-" keeps its bonus ratio and its rights change, as rework 2 pinned; the day has no result
  in grading either way.
- **RW3-D5, the list is read under today's NSE code.** That is the code the close is read under
  for every alias in the registry. For a registry rename (a successor segment), NSE's history
  under the new code is assumed, not measured; the registry check still turns a new basis into
  no result.
- **RW3-D6, undated rows stay unread** (a KT limit, not a rule): an undated row has no day to
  place, and failing closed on it would leave every decision on that stock without a result.

### Invariant tests (expected values worked by hand)

[tests/unit/test_exit_fix016.py](../../../../tests/unit/test_exit_fix016.py), section "Rework 3":
58 new tests, 164 (125 in test_exit_fix016 + PR-009's 39) in the story file with PR-009's. The price path is real code, with
only Yahoo's series, NSE's close and NSE's action list faked.

- **Every quoted row by hand** (`test_rr2_every_row_is_read_in_full_or_refused`, 50 cases): the
  re-review's RR2-F1 rows (ZEEL, DRREDDY, TVSMOTOR, BLUEDART, BRITANNIA bonuses of other
  securities: unparsed, the scheme ones also a scheme; JSWSTEEL, KNRCON, M&M, SBIN, BHARTIARTL
  short splits and BAJFINANCE's bonus-and-split: unparsed; HINDALCO "Rhs": rights; the
  misspelt and short schemes: scheme); two rows of no known kind (INDHOTEL's CCDs, NESTLEIND's
  "Dividned"); four ratios with their values (BRIGADE 1:3 = 4/3, ICICIBANK's revised 1:10 = 1.1,
  NAZARA 4→2 = 2, NESTLEIND 10→1 = 10); 17 neutral rows in every recent shape and some old ones;
  and 9 wordings no list held (return of capital, "De Merger", a transfer of undertaking, a
  dividend in specie, a bonus of warrants, a reverse split, "Splt" without "Fv", a bonus and a
  split beside a rights issue, an empty subject).
- **Q5 pinned:** 15 keeps (8 at +2, 7 at −5: −19/15) fail; with S14's preference bonus (92.5% of
  its worth stays in the equity) S14 has no result, named, the gate fails right on 8 with the
  money check unknown, and the week after recommends nothing (with the defect: +1,833% and a
  pass).
- **Q3 pinned, and the same with wording never seen:** the RR2 population with S14 demerging 40%
  worded "Scheme Of Arangement" or "Transfer Of Undertaking": no result, named by kind or by the
  row's words; the gate fails and recommends nothing.
- **A short split is not a fall:** JSWSTEEL's wording with the raw close at a tenth has no result,
  named; the standard wording of the same split is graded at 0 (×10).
- **Q6 pinned, with the shipped registry:** TVSMOTORS and CANARABANK, each with a 10→2 split three
  sessions after the decision: NSE is asked once, for TVSMOTOR or CANBK, and the sale is graded
  at 0 (×5); NSE's list under the alias is empty.
- **PR-009's level:** ZEEL's and JSWSTEEL's rows between the dive and the buy leave ₹455 unused,
  with the gap.
- **Random markets with random wording** (6 × 25 decisions, seeded): each stock moves in real
  terms after its review day; NSE lists up to three rows, each ex from 5 sessions before to 35
  after, either known (a bonus or split in read words, a dividend, a meeting, a buy back, an
  e-voting) or odd (the re-review's misread rows and wordings no list held), each odd row moving
  the price by an amount only the model knows. Every graded return equals the real-terms move;
  every decision with an odd row between its closes has no result; every one with NSE's horizon
  close and only known rows between is graded (300 grades: 191 graded, 44 of them across a known row between the closes; 109 with no result, 92 of them with an odd row between).

### Checks

| Check | Result |
|---|---|
| Story file + PR-009's file | 164 passed |
| Re-review 2's cases (`analysis_data/fix016_rereview2/test_rr2_fix016.py`) | Q3, Q3 gate (misspelt), Q5, Q5 gate and Q6 fail on their defect assertions, as asked (Q3: the misspelt row is now a scheme; Q5: no 22-for-1 bonus; the gates fail right on 8; Q6: TVSMOTORS's list starts 2012-07-02); Q1, Q2 (×2), the Q3 gate control and the Q4 table pass: 5 failed, 5 passed |
| Re-review 1's cases (`analysis_data/fix016_rereview/test_rr_fix016.py`) | RR1, RR2 (demerger) and RR3 fail on their defect assertions, as after rework 2; 9 pass |
| Mutants, rework 3's own (`analysis_data/fix016_rework3/rw3_mutants.py new`) | 18 of 18 caught on the final tree (each new rule and word list, and the alias code), baseline clean (164 passed); the first run, before the last two table rows, caught 17 (`splt_not_share_count` survived; pinned) |
| Mutants, every earlier FIX-016 mutant (5 of rework 2's re-pointed at the rewritten text) | 81 of 81 caught: 80 in the first run, and the 5 re-pointed (rework 2's demerger, scheme, rights, change-beside-a-ratio and bonus-and-split mutants, rewritten for the new text) re-run on the final tree, including `bonus_and_split_read_as_bonus`, which survived the first run (pinned) |
| Full suite (`tests/`, hermetic) | 5,836 passed / 12 skipped / 1 xfailed / 0 failed on the final tree (15m08s, beside the mutants); the two earlier runs, one and two table rows short, gave 5,834 and 5,835 passed, 0 failed |
| `scripts/ci/check_broad_except.py` | OK (151 grandfathered) |
| `scripts/docs/build_kt_pdf.py`, then `check_kt_docs.py` | 59 pages, source SHA-256 `ee857f74…` (the KT's LF digest; `analysis_data/fix016_rereview/pdf_check.py` matches); errors `[]` |
| `kt_manifest.py write` (13 paths), then `verify` | 13 files, mismatches `[]`, `28039abf…` |

**Review input for the re-review:** [FIX-016-manifest.json](FIX-016-manifest.json) 13 files, mismatches `[]`, `28039abf…`.
`analysis_data/fix016_rework3/rw3_digest.py` (rework 2's recipe, pointed at this input) first
checks the kept input copy byte for byte against `FIX-016-manifest-review3.json` (`5bdb5496`),
then writes: the rework diff against it, `657ff368107be963e742c7aa98dd27f9bf1bdaa23b3fa24fd946cf5171a8175f` (76,211 bytes, 12 paths); FIX-016's own diff, `a44537ff7dc8d71c710f5b0559ae243123383efc41893a023ce050226dbc4b0c` (235,103 bytes); the
cumulative diff against HEAD `8cb626c`, `9b4fdecdd7597bf3f582e3bc18a6fce8deb57ae8a84909f143c859ce075e262c` (236,583 bytes).

### NSE's lists, read on 29 Oct 2026 (public data, read-only)

`analysis_data/fix016_rework3/raw_probe.py` called the production fetcher for every configured
symbol (the sector registry's 202), under `nse_symbol` (4 mapped: TVSMOTORS → TVSMOTOR,
CANARABANK → CANBK, TATAMOTORS → TMPV, HEXAWARE → HEXT), 2 s apart, 10:57–11:08 IST, and saved
each row's subject and ex-date (`raw_rows_2026-10-29.json`, ignored). `measure.py` classed every
row with the re-review's input and with this rework (`measure.txt`):

- 3,215 rows; 9 undated; 14 symbols with an empty list (AAVAS, ACCCEMENT, APL, DEEPAKNITRI, GATI,
  ICICIPRULI, IDEAFORGE, LTIM, MAHINDHOTEL, MCDOWELL-N, MTAR, PVR, STARHEALTH, ZOMATO; 17 under the
  app's codes);
- this rework: 3,011 neutral, 110 ratios, 14 demergers, 27 rights issues, 9 schemes (5 also an
  unread bonus of debentures or NCRPS), 8 more unread share-count rows, 27 of no known kind;
- before: 3,043 neutral, 113 ratios (ZEEL's ×22, DRREDDY's ×7 and TVSMOTOR's ×5 among them), 7
  unparsed (one inside a scheme), 4 schemes, 26 rights issues, 14 demergers;
- 37 rows changed class, every one dated 2008–2021 except TVSMOTOR's August 2025 NCRPS bonus
  (was a ×5 ratio beside its scheme, now unparsed beside it): 27 neutral rows became of no known
  kind, 3 neutral rows unparsed (the short splits and BHARTIARTL's), HINDALCO's "Rhs" a rights
  issue, BRITANNIA's 2021 "Dividend - Rs 12.50 Per Share Pursuant To Scheme" a scheme (its
  words would make it of no known kind anyway), ZEEL's ×22 and DRREDDY's ×7 unparsed, and
  BRITANNIA's 2 misspelt scheme-and-debenture rows, already unparsed, now also a scheme;
- the 849 rows dated from 2024 read the same before and after: 802 neutral, 33 ratios, 8
  demergers, 5 rights issues, 1 NCRPS scheme.

### Self-review (same conversation; not the fresh re-review)

- The vocabulary is a word list, but failing closed makes its gaps cost a result, never decide
  one. A row of known words could still be misread only if `parse_action` reads a wrong ratio
  from words that are all known; the table pins every ratio shape NSE used since 2023.
- `_words` lower-cases after removing the registrar phrase; `[a-z]+` splits "Rs10tors5" into
  "rs" and "tors", so a face-value change inside a dividend row is a share-count row ("fv").
- The first mutant runs left two survivors, each pinned with a wording no list held, and both
  re-run caught on the final tree:
  - "splt" looked redundant on NSE's data (every "Splt" row also says "Fv"). It is kept, so a
    split worded without "Fv" still leaves PR-009's level unused ("Splt Frm Rs 10 To Re 1").
  - Rework 2's bonus-and-split guard matters now only beside a named change, where only the
    bonus's own words are read. Without it, a bonus, a split and a rights issue in one row would
    give its bonus as ×2.
- One shell slip: a `python -` heredoc hung, as on earlier days; it was stopped and nothing ran.

### Not done, and for the owner

- FIX-017 (the live holding sync's misreadings, and its alias fetch) is unchanged and still
  queued after FIX-015. Its trigger was not met at the re-review's probe.
- RW2-D6 stands (the owner's question): a decision whose basis can never be known keeps the money
  check failing for good. Failing closed adds old misspelt rows to the ways that can happen;
  none of the rows dated from 2024 would.

## Rework 2 (2026-10-25): no result across a change no ratio converts

**Phase:** rework 2 of the fresh re-review's CHANGES REQUESTED
([FIX-016-review](FIX-016-review.md), top section), a new conversation opened with "continue"
(25 Oct, about 08:47–09:45 IST, session `stockagent-main-1f`; after a pause in the same
conversation, the bookkeeping was finished on 26 Oct, about 17:10 IST, with the tree, the review
input and STATE/HANDOFF re-checked unchanged). Implementation was
`stockagent-main-a6`, the review `stockagent-main-f7`, rework 1 `stockagent-main-e2` and the
re-review `stockagent-main-4f`; this conversation is none of them. Every peer session was idle at
the start and before the bookkeeping (ListAgents). It includes a same-conversation self-review,
which is not the fresh re-review.

**Status after this phase:** `review_required` (the fresh re-review, in a new conversation).
Nothing was committed, pushed, deployed or configured. No production state was read, no model was
called and no message was sent. One read-only probe read NSE's public corporate-action lists for
22 symbols (below). PR-009's push stays held until FIX-016 is accepted.

**Input:** the re-review's input, verified unchanged at the start (`kt_manifest.py verify`: 12
files, 0 mismatches, `9b8e7457`), kept as
[FIX-016-manifest-review2.json](FIX-016-manifest-review2.json), and its 12 files copied to the
ignored `analysis_data/fix016_rework2/review_input/` before any edit.

### In one example

The evidence rule sells BBB at ₹190 on Friday 23 Oct as a plain EXIT; the price-path rule keeps
it. On Wednesday 28 Oct, 40% of the company's value is demerged into a new listing. BBB is flat in
real terms and trades at ₹114.

- **Before:** the grade compared ₹190 with ₹114: a 40% "fall", so the sale was "right" with a
  result of +40. One such demerger let a rule losing 1.27% a decision pass the gate (RR2).
- **Now:** NSE's row says only "Demerger" and gives no fraction, so no ratio can put ₹114 in the
  old shares. The decision has no result at either horizon, named, and the money check cannot
  pass while it is in the population. The same holds when only the instrument registry records
  the new basis.

### What changed

1. **RR-F1, a change no ratio converts, in NSE's list**
   ([corp_actions.py](../../../../core/portfolio/corp_actions.py) `basis_change_kind`,
   `ActionRecord.basis_changes`, `action_record`;
   [exit_shadow.py](../../../../core/portfolio/exit_shadow.py) `horizon_in_basis`).
   - Each NSE row is classed by its wording: demerger (also "spin off", "hive off"); scheme of
     arrangement (also amalgamation, merger); consolidation; capital reduction; rights issue. The
     record keeps each such row as (ex-date, kind), whatever else the row says.
   - **No result** when one went ex after the decision close's bar and on or before the horizon
     close's bar or the review day, or after the bar when the horizon close is Yahoo's alone. The
     reason names the kind and the day: "NSE lists a demerger ex 2026-10-28, after the decision's
     close (2026-10-23), and no ratio puts the horizon close in the decision's price basis across
     it".
2. **A row naming a bonus and a split** (BAJFINANCE, 2016: "Bonus 1:1/Face Value Split
   (Sub-Division) - From Rs 10/- … To Rs 2/-"). `parse_action` reads its bonus alone (×2 where
   the price fell to a tenth, ×10). `action_record` now keeps such a row as unparsed: no result
   in grading, and PR-009's invalidation level unused with its gap.
3. **RR3, a new basis the registry records** (`exit_shadow.registry_break`, over
   `symbol_resolver.identity_break`, the check forecast grading uses). A graded close is turned
   into no result when the registry gives the symbol two price bases between the decision's
   close and the horizon's day: "the instrument registry says the price basis changed between
   2026-10-23 and 2026-11-06: BBB (BBB.NS) then BBBA (BBBA.NS)". A rename keeps the basis and is
   graded.
4. **Wording.** An empty or unread list now reads "NSE's list of its corporate actions is empty or
   was not read, so one since … cannot be ruled out" (and "… starts …"); the scorecard line says
   "N with no result at H sessions, as a corporate action could not be ruled out or allowed for
   (stocks)".
5. **RR-L1** (KT section 6 limit): an empty NSE list is not only a recent listing (ETERNAL, listed
   in 2021, returned none on 24 and 25 Oct); with no population window, one decision whose basis
   stays unknown keeps the money check failing, for good for an empty list, a demerger or a
   registry basis change.
6. **I1 (optional, done)** ([pipeline.py](../../../../core/portfolio/pipeline.py) `switch_lands`):
   a destination close fetch that fails with any error, not only `PriceUnavailableError`, is
   logged and counted as a refused buy, so the row says `cash`, as the executor skips such a buy.
   Before, such an error dropped that holding's shadow row for the day.

**Changed contracts** (each named for the re-review):

- `ActionRecord` gains `basis_changes: tuple[tuple[str, str], ...] = ()`; its `unparsed` also
  holds the ex-date of a row naming a bonus and a split, which is no longer in `actions`.
- `corp_actions.basis_change_kind(desc) -> str` and `exit_shadow.registry_break(symbol, start,
  until) -> str` are new.
- `horizon_in_basis`: one new no-result cause; the two empty/late-list reasons are reworded.
- `grade_disagreements`: a graded close becomes no result on a registry basis change.
- `scorecard_text`: the no-result clause is reworded.
- The pipeline's `switch_lands` closure: any fetch error is a refused buy (logged).
- `level_in_basis` (PR-009): a row naming a bonus and a split from the dive day on leaves the
  level unused (it was halved). No other PR-009 behaviour changed.
- Tests: rework 1's `_Market` gains demergers (`demerge`), extra NSE rows, an optional Yahoo
  adjustment for demergers, and asks NSE for the registry's code (`nse_symbol`), as the real
  fetcher does. Four exact strings in rework 1's tests follow the rewording. No assertion was
  relaxed.

### Decisions (delegated, recorded)

- **RW2-D1, which kinds are no result.** A demerger, a scheme (arrangement, amalgamation, merger),
  a consolidation, a capital reduction and a rights issue change the price by an amount NSE's row
  does not give. A buy back, a dividend (a stated limit), a meeting or an e-voting row leaves the
  basis alone. Wording the classifier does not know reads as neutral: treating every unknown row
  as a change would let any new wording block the gate for good, and NSE's lists hold no unknown
  basis change today (the probe, below).
- **RW2-D2, a rights issue is not converted.** The theoretical ex-rights price needs the issue
  price, the ratio and the last cum-rights close. NSE's wording varies (partly paid, a premium
  "of", fully and partly paid parts, differential-voting shares), and a wrong ratio is a wrong
  grade, so no result. Rights rows were 14 of 354 in the probe.
- **RW2-D3, a consolidation is not parsed as a ratio.** `parse_action` reads face-value changes
  only from split or sub-division wording, and it also feeds the holding sync. Teaching it
  consolidation would change holdings' adjustments, outside this story; no result is the safe
  side.
- **RW2-D4, a row naming a bonus and a split is unparsed, not two ratios.** The holding sync still
  applies only its bonus (found on the way, below). Two ratios in the record would make grading
  and the level disagree with the holding's own record, so the record refuses the row instead.
- **RW2-D5, the registry is asked up to the horizon's day.** The horizon close is resolved for that
  day (`pricing.session_close`), so that day's instrument is the one priced. An unresolved
  identity is not added: both closes go through the same resolver, and a learned mapping is
  SA-008's quarantine path, not a basis change.
- **RW2-D6, the gate's rule is unchanged.** A decision with no result still counts as not right
  and fails the money check (the owner's "a missing grade never helps", 24 Oct). Excluding a
  decision whose basis can never be known would be an owner decision; the KT states the
  consequence (RR-L1).

### Invariant tests (expected values worked by hand)

[tests/unit/test_exit_fix016.py](../../../../tests/unit/test_exit_fix016.py), section "Rework 2":
11 new tests, 106 in the story file with PR-009's. The price path is real code, with
only Yahoo's series, NSE's close and NSE's action list faked by rework 1's market model, which now
has demergers (from the ex day the stock trades at the kept fraction of its value; NSE's row says
"Demerger").

- **RR1 pinned** through the real pipeline's rows: BBB (sold) and AAA (kept), flat in real terms,
  each demerging 40% on 28 Oct (₹114, ₹288): no result at 10 and 30 sessions for both, with the
  named reason; the scorecard line names AAA and BBB.
- **RR2 pinned:** 8 sales at +2 and 7 at −5 fail at −19/15 (about −1.27%). With S14 demerging 40%
  three sessions after its decision: still right on 8 of 15, S14 no result at both horizons, the
  gate fails with "1 decision with no result … cannot pass", and the week after recommends
  nothing (with the defect: 9 of 15, +1.53%, a pass two weeks running).
- **RR3 pinned**, with NSE's list silent: a registry demerger (BBBA at ₹114, a new basis) is no
  result with the registry's reason; a registry rename (BBBN at ₹190, the same basis) is graded at
  0, the sale wrong.
- **The record by NSE's wording:** 7 subjects from NSE's lists (demerger, scheme, merger, four
  rights wordings) and 6 more (spin off, amalgamation, consolidation, capital reduction twice, a
  bonus beside a rights issue) are each kept as their kind on their own day; 8 neutral subjects
  (buy back twice, meetings, e-voting, dividends) give none; a plain bonus and split keep their
  ratios; the bonus-and-split row is unparsed.
- **The windows by hand** (`horizon_in_basis`): every such kind ex between the closes is no result;
  every neutral row is graded; a demerger ex on the decision's own bar is graded, ex by the review
  day or on the horizon's bar is no result, ex after the horizon's bar is graded from NSE's or an
  agreeing close and no result from Yahoo's alone; a carried-forward horizon close with a demerger
  by the review day is no result.
- **PR-009's level:** the bonus-and-split row between the dive and the buy leaves ₹455 unused, with
  the gap; a plain bonus still halves it to ₹227.50.
- **Random markets** (6 × 25 decisions, seeded): each stock moves in real terms after its review
  day, with a 1:1 bonus, a demerger (keeping half or 80%) or both, ex from 5 sessions before to 35
  after; NSE down on about 30% of days; Yahoo adjusting for demergers in half the markets. Every
  graded return equals the real-terms move; every decision with a demerger between its close and
  its horizon has no result; every one with NSE's horizon close and no such demerger is graded
  (300 grades in all: 212 graded, 45 of them across a bonus and 43 from Yahoo's close alone; 88 with no result, 58 of them with a demerger between).
- **I1 through the pipeline** (×2: a `ConnectionError` and a `ValueError` from ZZZ's close fetch):
  both SWITCH rows are written and say `cash`, and ZZZ is not bought.

### Checks

| Check | Result |
|---|---|
| Story file + PR-009's file | 106 passed |
| The re-review's cases (`analysis_data/fix016_rereview/test_rr_fix016.py`) | RR1, RR2 (demerger) and RR3 fail on their defect assertions, as asked; RR2 control, RR4, RR4b and RR5 (×6) pass: 3 failed, 9 passed |
| Files touching corp actions, the scorecard, the shadow or identity (21 files) | 1,025 passed (run before the I1 change; the full suite covers the final tree) |
| Mutants, rework 2's own (`analysis_data/fix016_rework2/rw2_mutants.py new`) | 19 of 19 caught (each new cause and window, each kind's wording, the neutral rows, the bonus-and-split row, the registry's three, I1, the line's wording) |
| Mutants, every earlier FIX-016 mutant re-run | 62 of 62 caught (the implementer's 33 with rework 1's refresh, rework 1's 29); 81 of 81 with the new, baseline clean |
| Full suite (`tests/`, hermetic) | 5,778 passed / 12 skipped / 1 xfailed / 0 failed (12m49s; 11 more than the re-review's 5,767) |
| `scripts/ci/check_broad_except.py` | OK (151 grandfathered) |
| `scripts/docs/build_kt_pdf.py`, then `check_kt_docs.py` | 59 pages, source SHA-256 `7ceed0ee…` (the KT's LF digest); errors `[]` |
| `kt_manifest.py write` (13 paths), then `verify` | 13 files, mismatches `[]`, `5bdb5496…` |

### NSE's lists, read on 25 Oct 2026 (public data, read-only)

`analysis_data/fix016_rework2/kinds_probe.py` called the production fetcher for 22 symbols (the
24 Oct probe's 12, plus 10 chosen for a known demerger, scheme or rights issue) and classed each
row with this rework's code. Of 354 rows: 262 dividends, 48 neutral (meetings, buy backs,
e-voting), 9 bonuses, 6 splits, and 29 changes no ratio converts: 9 demergers (RELIANCE 2023, TMPV
2025, ITC 2025, SIEMENS 2025, ABFRL 2025, RAYMOND 2024 and 2025, PEL 2022, GMRAIRPORT 2022), 14
rights issues and 6 schemes (one an undated "Merger"). No basis change used wording the classifier
missed. Two old rows a parser would miss: GMRAIRPORT's 2009 "Fv Split Rs.2/- To Re.1/-" (already
unparsed: no result) and BHARTIARTL's 2009 "Agm/Div-Rs.2/Fv Rs10tors5" (a face-value change inside
a dividend row, read as a dividend). ETERNAL returned no rows again.

### Found on the way (not routed)

- **The holding sync reads a bonus-and-split row as its bonus alone.** `parse_action` returns the
  first kind it matches, so `apply_actions_to_holding` would halve the cost basis where the price
  fell to a tenth. The holding would then show about −80% and its stop would fire. NSE's 2016
  BAJFINANCE row has this wording; its 2025 bonus and split came as two rows. It is a Compass
  corp-action defect, outside this story; it needs a story (suggested: parse both ratios, or hold
  the symbol with a named gap).
- A face-value change inside a dividend row (BHARTIARTL 2009's wording) is read as a dividend by
  the sync and by grading. Only old rows use it.

### Self-review (same conversation; not the fresh re-review)

- The classifier is a word list. A basis change in wording it does not know is graded as before
  (RW2-D1); the probe found none in 354 rows, and the record-by-wording test pins every wording
  seen. A new NSE wording would need a line there.
- The registry check first asked up to the horizon close's bar. The close is resolved for the
  horizon's day, so it now asks up to that day (RW2-D5); with NSE answering on the day, the two
  are the same.
- The probe's 22 symbols were not a random sample (6 picked for a demerger), so its 29 of 354 is
  not a rate for the universe; the KT says so.
- Rework 1's `_Market` changed shape; its 19 tests still pass unchanged except the four reworded
  strings.

### For the owner

- **One unknowable decision blocks the gate.** A decision with a demerger between its closes, or a
  stock NSE lists nothing for, never gets a result, and the gate counts every decision ever made.
  **Example:** 40 decisions over a year, one in a stock that demerged: the money check fails every
  week after, whatever the other 39 show. Today's rule ("a missing grade never helps") is yours
  (24 Oct). A choice for later: leave such a decision out of both the count and the money. That
  favours neither rule on average, because whether a stock demerges does not depend on which rule
  sold it, but it does drop a decision whose result nobody can know. No change is made here.
- **The holding sync defect** above needs a story before any held stock lists a bonus and a split
  in one row.

### Changed files (rework 2)

| Path | Change |
|---|---|
| `core/portfolio/corp_actions.py` | `basis_change_kind`, `_bonus_and_split`, `ActionRecord.basis_changes`, `action_record`; docstrings (new to the manifest) |
| `core/portfolio/exit_shadow.py` | `horizon_in_basis` (new cause, reworded list reasons), `registry_break`, `grade_disagreements`, `scorecard_text`; docstrings |
| `core/portfolio/pipeline.py` | `switch_lands`: any failed fetch is a refused buy (I1) |
| `core/portfolio/results.py` | `corp_actions_fn` docstring |
| `tests/unit/test_exit_fix016.py` | section "Rework 2" (11 tests); `_Market` demergers, extra rows, Yahoo option, the registry's NSE code; the I1 pipeline test; 4 strings reworded |
| `docs/TECHNICAL_DESIGN.md`, `docs/StockAgent-Three-Loops.pdf` | section 6: the level's unknown causes, the price basis's causes, a demerger example, the RR-L1 limit; section 7: the scorecard row's wording. PDF 59 pages, source `7ceed0ee…` |
| `docs/TEAM_TESTING_GUIDE.md` | 09-H: a demerger step and its expected line; the line's wording; status notes in 07-L, 07-M, 09-H |
| `CODEBASE.md` | the `corp_actions.py` and `exit_shadow.py` rows |

Not in the manifest (bookkeeping): `docs/planning/PI-2026-09/stories/PR-005.md` (a sentence in
RR-L1's routed input: the two new signals exist; the level does not read them yet), STATE, HANDOFF,
this receipt, `FIX-016-manifest-review2.json` and `FIX-016-manifest.json`. Unchanged from the
re-review's input: `config.yaml`, `core/portfolio/advisor.py`,
`src/backend/shared/schemas/portfolio.py`, `tests/unit/test_exit_evidence_pr009.py`.

Digests (`analysis_data/fix016_rework2/rw2_digest.py`): rework diff against the re-review's input
`44143f54` (78,802 B, 8 of 12 paths changed); FIX-016's diff (the implementer's recipe) `564fc952` (201,380 B); cumulative against HEAD
`8cb626c` `dd54d848` (202,860 B, 12 paths). Input for the fresh re-review: `FIX-016-manifest.json` `5bdb5496` (13 files).

## Rework 1 (2026-10-24): one price basis in grading, and where a refused SWITCH's money went

**Phase:** rework 1 of the fresh review's CHANGES REQUESTED
([FIX-016-review](FIX-016-review.md)), a new conversation opened with "continue" (24 Oct, about
16:35–17:55 IST, session `stockagent-main-e2`). Implementation was `stockagent-main-a6` and the
review `stockagent-main-f7`; this conversation is neither. Every peer session was idle at the
start and before the bookkeeping (ListAgents). It includes a same-conversation self-review, which
is not the fresh re-review.

**Status after this phase:** `review_required` (the fresh re-review, in a new conversation).
Nothing was committed, pushed, deployed or configured. No production state was read, no model was
called and no message was sent. PR-009's push stays held until FIX-016 is accepted.

**Input:** the review's input, verified unchanged at the start (`kt_manifest.py verify`: 10 files,
0 mismatches, `72268ff3`), kept as
[FIX-016-manifest-review1.json](FIX-016-manifest-review1.json), and its 10 files copied to the
ignored `analysis_data/fix016_rework1/review_input/` before any edit.

### In one example

The evidence rule sells BBB at ₹190 on Friday 23 Oct as a plain EXIT; the price-path rule keeps
it. A 1:1 bonus goes ex on Wednesday 28 Oct. The company's value does not change, and the stock
trades at ₹95.

- **Before:** the grade compared ₹190 with ₹95: a 50% "fall", so the sale was "right" with a
  result of +50. One such bonus let the card's failing example (right on 8 of 15, −3.6% a
  decision) pass the gate two weeks running.
- **Now:** ₹95 is ₹190 in the old shares. The return is 0, the sale saved nothing and was wrong,
  with a result of 0, and the card's example still fails at −3.6%. When the price basis cannot be
  established, the decision has no result that week, which fails the money check and names the
  stock.

### What changed

1. **F1, one price basis** ([exit_shadow.py](../../../../core/portfolio/exit_shadow.py)
   `horizon_in_basis`, `grade_disagreements`; [results.py](../../../../core/portfolio/results.py)
   `stock_quote_fn`, `corp_actions_fn`, `build_row`, `weekly_scorecard`).
   - Grading reads the horizon close with its bar and its source (`pricing.session_close`), and the
     symbol's NSE corporate-action list (`corp_actions.fetch_corp_actions` + `action_record`), read
     once per stock per scorecard.
   - The horizon close is multiplied by the ratio of every bonus or split ex after the decision
     close's bar (`price_bar_date`, else the review day) and on or before the horizon close's own
     bar. An ex day's close is already in the new shares, so a ratio ex on the decision's bar is not
     applied and one ex on the horizon's bar is. The same action listed twice counts once.
   - **No result** (status `ungraded`, `no_basis` says why) when the list is empty, was not read
     or starts after the decision's close; a split or bonus row after the close cannot be parsed,
     or one day has two ratios; one went ex after the close's bar and by the review day (the stored
     close may be in either basis); the horizon close is undated or older than the decision's; or
     it is Yahoo's alone (NSE's did not answer) and an action went ex after its bar.
   - The tally counts `no_basis` and names the stocks; the scorecard line says "N with no result at
     H sessions, as a bonus or split could not be ruled out or allowed for (stocks)".
   - A past quote is kept for the process only when it is that day's own bar in NSE's raw basis
     (NSE's, or Yahoo's agreeing with it).
2. **F2, a refused SWITCH buy** ([exit_shadow.py](../../../../core/portfolio/exit_shadow.py)
   `switch_buy_lands`, `decision_benchmark`, `shadow_row`;
   [pipeline.py](../../../../core/portfolio/pipeline.py)). When the row is written, before the
   autopilot runs, the selling rule's SWITCH asks whether its buy would pass the executor's checks
   before sizing: a close for the session; under `enforce`, the session's own bar and a resolved
   identity; a price inside the idea's entry band (`sizing.entry_check`). If not, the row records
   `cash`. The pipeline fetches each destination's close once per run and passes the autopilot the
   same shelf index.
3. **F3** ([advisor.py](../../../../core/portfolio/advisor.py) comment above
   `CASE_EVENT_SOURCES`; KT section 6): an NSE filing's direction and materiality are the same
   bulk-tier model's reading as a news article's; a filing may sell because it is the company's
   primary disclosure; PR-012's label-accuracy bench measures that reading (planned).
4. **I1:** the research-verdict reason prints the run's IST day, the day the freshness rule
   compares with the buy. **I2:** the module docstring reflowed.

**Changed contracts** (each named for the re-review):

- `grade_disagreements(rows, *, as_of, stock_quote_on, bench_close_on, corp_actions, horizons)`:
  `stock_close_on` (a float) is replaced by `stock_quote_on` (a `SessionClose`), and
  `corp_actions(symbol)` (an `ActionRecord`) is new and required. The same for `scorecard_block`.
  Grades gain `basis` and `no_basis`; `tally` gains `no_basis` and `no_basis_symbols`.
- `build_row(..., stock_quote_on=None, corp_actions=None)` and `weekly_scorecard(...,
  stock_quote_on=None, corp_actions=None)` are new; `stock_close_on` now only values arrivals.
  `weekly_scorecard` defaults them to `stock_quote_fn()` and `corp_actions_fn()`.
- `decision_benchmark(..., switch_lands=True)` and `shadow_row(..., switch_lands=None)` are new.
- `case_broken_reasons`: the research reason's date is the run's IST day (it was the naive-UTC
  date).
- PR-009's and FIX-016's test helpers: grading call sites pass `stock_quote_on=_nse(...)` and
  `corp_actions=_no_actions` (new helpers in PR-009's file, beside `_row`: NSE's close dated the
  day asked; a list since 2000 with no bonus or split); one exact tally dict gains the two
  `no_basis` keys; `_switch_world`'s IT idea gains the band ₹48.50–₹51.00 that holds ZZZ's ₹50
  close (without a band the executor refuses the buy, and the row now says so). No assertion was
  relaxed.

### Decisions (delegated, recorded)

- **RW-D1, an unestablished basis is no result, not a bound.** A bonus or split only lowers the raw
  price, so the unadjusted figure is a lower bound for a keep; but a consolidation (a split to a
  higher face value) moves the other way, and NSE's list is the only source. No result fails the
  money check (D8), so it never helps the evidence rule, and a later week's read can resolve a list
  or Yahoo case.
- **RW-D2, the horizon close's own bar and source decide its basis.** The review's suggestion used
  the horizon day. A carried-forward close is in its bar's basis, not the day's; and Yahoo's series
  is adjusted for every action up to the day it is read, so a Yahoo-only close after a later bonus
  is in a later basis (pinned: ₹50 for a ₹100 stock; no result until NSE answers).
- **RW-D3, an action between the decision close's bar and its review day is no result.** The row
  does not store the close's source, so a carried-forward close fetched on an ex day may be in
  either basis. This needs a stale bar on the ex day; it stays no result (KT limit).
- **RW-D4, an empty list is "not read".** `fetch_corp_actions` returns `[]` for NSE's empty answer
  and for a failed fetch alike; a large company's list is never empty (it reaches back years), so
  a stock with no action at all (a recent listing) is the cost (KT limit).
- **RW-D5, F2 at row time, mirroring the executor's checks before sizing.** The alternative,
  writing the rows after the autopilot and reading its outcome, works only for the acting rule; the
  evidence rule's SWITCH in `shadow` is never executed. The remaining causes (the executor's own
  re-fetch failing, under one share after sizing, a ledger duplicate) are a KT section 6 limit; the
  review's RV3 is the first of them and still records `nifty` (by design here).
- **Dividends** stay out of the return (KT limit, as the review allowed).

### Invariant tests (expected values worked by hand)

[tests/unit/test_exit_fix016.py](../../../../tests/unit/test_exit_fix016.py), section "Rework 1":
19 new tests, 95 in the story file with PR-009's. The price path is real code
(`results.stock_quote_fn` → `pricing.session_close` → `daily_review._fetch_session_close` →
`close_verifier`; `results.corp_actions_fn` → `corp_actions.fetch_corp_actions`), with only three
boundaries faked by a market model written from what the actions do: Yahoo's auto-adjusted series,
NSE's raw close with its bar, and NSE's action list.

- **RV1 pinned** through the real pipeline's rows: BBB (sold) and AAA (kept), flat, 1:1 bonus ex
  28 Oct: return 0 at both horizons, BBB wrong with 0, AAA right with 0, basis "×2 for the bonus ex
  2026-10-28"; the control (no bonus) the same with no basis.
- **RV2 pinned:** the card's example with S14's bonus: S14 +10% (₹55 is ₹110), wrong, −10; the gate
  fails at −3.6, right on 8 of 15, and does not recommend the week after.
- **The rule by hand:** 10 basis cases (none, ×2 between, ×2 with "agree", ex on the horizon's bar,
  ex on the close's bar, ex after the horizon's bar, ×2 then ×5 = ×10, a duplicate row, Yahoo with
  nothing after its bar, an unreadable row after the bar) and 10 no-result cases, each with its
  exact reason.
- **Never helps:** 8 sales right at +5 and 8 keeps wrong at −1 pass at +2.00; with S15's list empty
  the gate fails on the money check alone, the count unchanged, and the line names S15. A list read
  that raises is no result.
- **Yahoo alone after a later bonus:** no result while NSE does not answer; graded 0 when it does.
- **Lookups:** one NSE list read per stock per scorecard; a Yahoo-only close is not kept.
- **F2:** `switch_buy_lands` over 14 cases (band edges, invalidation level, no close, no idea, no
  band, stale and unresolved in record mode and under enforce); `decision_benchmark` with a refused
  buy; the row asks only about the selling rule's SWITCH; through the real pipeline and autopilot,
  ZZZ at ₹50 is bought and both rows say `nifty`, at ₹55 (7.8% above the band) the buy is refused,
  AAA's proceeds stay in cash and both rows say `cash`.
- **I1:** a SELL at 00:01 IST on 9 Oct (stored 18:31 on 8 Oct) counts for an 8 Oct buy and the
  reason says 2026-10-09.

**Mutants** ([analysis_data/fix016_rework1/rw_mutants.py](../../../../analysis_data/fix016_rework1/rw_mutants.py),
ignored; the implementer's in-memory harness): **62 of 62 caught**: FIX-016's 33 (`deployment_ignored` re-anchored on its changed line)
and 29 for the rework: 20 on the basis rule (the factor, its direction, both ex-day
boundaries, later actions, every no-result cause, duplicates, a raised list read, the
tally), 2 on the scorecard's lookups (one list read per stock, no Yahoo-only quote kept), 6 on
F2 (the benchmark ignores the check, no band check, no enforce checks, a missing close
lands, the keeping rule asked, the pipeline not passing the check) and 1 on I1. The baseline
(no mutant) passes. In the first run the 2 lookup mutants did not run: the plugin could not
build `results.py`'s dataclass outside `sys.modules`. The plugin now registers its module,
and the re-run caught both.

**The review's repros, adapted** (`analysis_data/fix016_rework1/rv_adapted/`: only the new grading
contract and an NSE action-list fake added): RV1 and RV2's bonus case now fail on their
defect assertions (a flat stock grades 0, not −50; the example stays `fail`, right on 8 of
15). Their controls pass. RV3 passes as written: the executor's own re-fetch of ZZZ fails
after the row's check priced it, so the row still says `nifty` (the KT limit; RW-D5).

### Commands and environment

Windows 11, the `.stockai` venv (Python 3.13), the SA-005 hermetic boundary.

| Command (repository root) | Result |
|---|---|
| `.stockai/Scripts/python.exe scripts/docs/kt_manifest.py verify docs/planning/PI-2026-09/evidence/FIX-016-manifest.json` (start, the review's input) | 10 files, mismatches `[]`, `72268ff3…` |
| `pytest -q -p no:cacheprovider tests/unit/test_exit_fix016.py tests/unit/test_exit_evidence_pr009.py` | **95 passed** (56 + PR-009's 39) |
| `python analysis_data/fix016_rework1/rw_mutants.py` (17:03–17:31 IST) | baseline 95 passed; 60 of 62 caught, 2 not run (harness: a dataclass outside `sys.modules`) |
| the same, `baseline list_read_per_horizon yahoo_quote_kept basis_ignored`, after the plugin fix | baseline clean; 3 of 3 caught: **62 of 62** in all |
| `pytest -q -p no:cacheprovider --rootdir analysis_data/fix016_rework1/rv_adapted analysis_data/fix016_rework1/rv_adapted/test_rv_fix016_adapted.py` | 2 failed (the two defect assertions), 3 passed |
| `pytest tests -q -p no:cacheprovider` (17:34–17:47 IST) | **5,767 passed, 12 skipped, 1 xfailed, 0 failed** in 12 min 38 s (5,748 before, plus the 19 new) |
| `scripts/ci/check_broad_except.py` | OK (151 grandfathered) |
| `scripts/docs/build_kt_pdf.py`, then `scripts/docs/check_kt_docs.py` | 58 pages, source SHA-256 `edd5f130…`; errors `[]` |
| `python analysis_data/fix016_rework1/rw_digest.py` (twice) | the digests below, the same both times |
| `kt_manifest.py write` (12 paths), then `verify` | 12 files, mismatches `[]`, `9b8e7457…` |

### Documentation

- **KT section 6:** the news and filing sentence (F3); the `cash`/`nifty` bullets (a refused SWITCH
  buy); a new "One price basis" paragraph with its no-result causes and "Example: a bonus after a
  decision"; limits for an unknown basis that stays, dividends, and the SWITCH causes the row cannot
  see; the cache limit. **Section 7:** the Exit rule test row names the no-result decisions. PDF
  rebuilt (58 pages; source SHA-256 `edd5f130…`, the KT's manifest entry).
- **CODEBASE.md:** the exit_shadow row (`switch_buy_lands`, `horizon_in_basis`, the scorecard's
  lookups).
- **Testing guide:** 07-L (the reason's IST day; a refused SWITCH's row says `cash`), 07-M (the IT
  idea's band; the close above it gives `cash`), 09-H (a bonus after a decision changes nothing; an
  empty list is no result, named); the three status lines.
- **Commit-time edits after acceptance** (unchanged from the implementation receipt): the KT's Code
  inspected revision and edition, section 1's production paragraph, section 12's FIX-016 row Done,
  the PDF, and the guide status lines (07-L, 07-M, 09-H).

### Manifest and digests

- **The re-review's input:** [FIX-016-manifest.json](FIX-016-manifest.json), regenerated, 12
  files: the review's 10 plus `core/portfolio/pipeline.py` and `core/portfolio/results.py`. The
  SHA-256 of its LF bytes is
  **`9b8e7457ed5b36980e8ca7308d3106e79edafa976c09cdf9692ee13391daddc3`**; `kt_manifest.py verify`
  gives 0 mismatches. The review's input is kept as
  [FIX-016-manifest-review1.json](FIX-016-manifest-review1.json) (`72268ff3`).
- **Rework diff** (every manifest path but the PDF against this review's input copied to
  `analysis_data/fix016_rework1/review_input/`, checked byte for byte against `72268ff3` first; the
  two new paths against HEAD, unchanged when the rework began):
  **`e0efc6bae97dde90f2daafdfe863937b64a324b9f4b0c21ad8b2acfcada983b0`**, 108,455 bytes, 11 paths
  (9 changed; `config.yaml` and the schema are unchanged).
- **FIX-016's own diff** (the implementation's recipe: the KT against
  `analysis_data/fix016/start/`'s copy): `ee7a3f8480aa69abbc6d82d4b9b9a76695fdbf3c745e9a262003ea1972112e37`,
  168,563 bytes, 11 paths.
- **Cumulative against HEAD `8cb626c`:**
  **`fc0cab4bd5700bfed62a2c8a50e0a0db7c1fdcc6178bfc76802eb7dc1fff0944`**, 170,043 bytes, 11 paths
  (the KT also carries session -cb's edits, as before).
- Recipe: `analysis_data/fix016_rework1/rw_digest.py` (ignored); the diffs are beside it.

### Self-review (same conversation; not the fresh re-review)

- **Can a bonus or split still be a result?** Only if NSE's list misses one while its earliest
  row is on or before the decision's close. Session -87's probe found the undated list is the latest
  20 actions of any kind, so every later action is in it. RV1 and RV2 are pinned through the real
  price path, and the mutants on the factor, both ex-day boundaries, later actions and duplicates
  are caught.
- **Can an unestablished basis help the evidence rule?** It is no result: not right in the count,
  and the money check fails at that horizon (D8), so it cannot. Pinned: S15's empty list turns a
  +2.00 pass into a fail; the `unknown_graded_raw` mutant is caught.
- **Is anything after the horizon used?** Prices are not. NSE's list is read at grading, so it
  holds later actions; they are not applied to a raw close and make a Yahoo-only close no result.
- **The F2 check and the executor:** the same shelf index, the same entry rule, the same enforce
  switch, read in the same run; pinned through the real pipeline and autopilot at ₹50 (bought,
  `nifty`) and ₹55 (refused, `cash`).
- **Found and fixed in self-review:** the process-wide quote cache could carry one test's prices
  into another, so the tests' market installs a fresh one; the mutant plugin could not build
  `results.py` (a dataclass needs its module in `sys.modules`), so two mutants first did not run.
- **Not changed:** the shadow row's schema (the close's source is not stored; RW-D3), PR-009's
  invalidation basis, the gate's constants and wording, the stops.

### Limits

- A stock NSE lists no action for, and a decision with a bonus or split between its close's bar and
  its review day, have no result while that lasts; each keeps the money check failing, named.
- The SWITCH causes the row cannot see (the executor's own failed re-fetch, under one share, a ledger
  duplicate) are graded against the Nifty; the SELL's note names them.
- Dividends are not in the return.
- Measured benefit: none. The rule is in shadow, no row exists, and this changes how decisions will
  be judged, not any trade.

### For the owner

A bonus or split no longer counts as a gain or loss when the exit test is graded: a stock that only
went ex on a 1:1 bonus grades as flat, as your holdings already do. When the system cannot tell
whether a bonus happened, that decision counts against the switch for the week, never for it. And a
switch whose buy would be refused (its price above the plan's band) is judged against cash, where
the money actually stays. Next: the fresh re-review in a new conversation; then PR-009 and FIX-016
go out together, at your word, in a job-free window.

## In one example

A stock is added by hand on 8 October although its analysis of 24 September said SELL. On
23 October, ten sessions later:

- **Before:** `case_broken` sells it on that old SELL, against the owner's own choice.
- **Now:** the SELL ran before the buy, so it never counts; the evidence rule HOLDs. A SELL from
  an analysis on 9 October would sell it, until that analysis is 22 sessions old.

And on the gate: right on 8 of 15, where the 8 saved 2% each and the 7 wrong ones cost 10% each.
**Before:** a pass (8 of 15 is more than half). **Now:** (8 × 2 − 7 × 10) / 15 = −3.6% a decision,
so it fails: "its mean result at 10 sessions is -3.60% (needs at least +0.00%)".

## What changed

1. **A fresh verdict** ([exit_shadow.py](../../../../core/portfolio/exit_shadow.py)
   `latest_actionable_verdict`). A research verdict counts only when its analysis ran on a later
   IST day than the buy and at most `RESEARCH_VERDICT_SESSIONS` (22) sessions before the review
   day, beside `CASE_EVENT_SESSIONS`. The newest such actionable run wins, as before.
2. **Only a filed or rule-typed event sells.** `CASE_EVENT_SOURCES`
   ([advisor.py](../../../../core/portfolio/advisor.py)) lists the six sources that may break the
   case: `nse_announcement`, `nse_board_meeting`, `nse_insider`, `nse_sast`, `nse_pledge`,
   `nse_shareholding`. `exit_evidence` splits the high-negative events of the window:
   `negative_events` (those sources) and `watch_events` (news). `case_broken_reasons` also skips
   any event whose `source` is not in the list, so a news event placed in the selling list by
   another route still cannot sell. The shadow row records `watch_event_ids`.
3. **The money's real alternative.** `decision_benchmark` fixes, on the decision day, where the
   selling rule's sale put the money: `nifty` for a SWITCH (or once a portfolio deploys its cash,
   the `deploys_cash` argument, false until SA-049), else `cash`; `""` when the rules agree.
   `ExitShadowRow.benchmark` stores it. `grade_disagreements` reads it from the row: cash is graded
   on the stock's own return, the Nifty on the excess, and each grade carries `return_pct`,
   `excess_pct`, `gap_pct`, `result_pct` (+gap kept, −gap sold) and `nifty_result_pct`. A row
   with no benchmark is ungraded.
4. **A money check in the gate.** `gate_look` fails unless, at 10 and at 30 sessions, the mean
   result is at least `GATE_MIN_MEAN_RESULT_PCT` (0), beside the unchanged 50% count. A decision
   with no result at a horizon fails the money check there. `better` labels a pass that is also
   right on at least `BETTER_RIGHT_PCT` (70%) at both horizons with a positive mean. The scorecard
   line names the mean result (against where the money went, how many against cash and against
   the Nifty, and the mean against the Nifty alone) and reads a pass as "not worse than the
   price-path rule in count and money", adding "better" when it applies. The gate block's comment
   is re-dated 24 Oct 2026; no shadow row exists yet (PR-009 is not deployed).

**Changed contracts** (each named for the fresh review):

- `latest_actionable_verdict(records, symbol, on, bought, sessions=22)`: `bought` is new and
  required. Its only caller is `exit_evidence`.
- `ExitEvidence.watch_events` is new; each event dict gains `"source"`; `case_broken_reasons`
  ignores an event without a selling source.
- `ExitShadowRow.benchmark` (`"" | "cash" | "nifty"`) is new; `evidence.watch_event_ids` is new;
  `shadow_row(..., deploys_cash=False)` is new.
- Grades gain `benchmark`, `return_pct`, `gap_pct`, `result_pct`, `nifty_result_pct`; a row
  without a benchmark is now ungraded (PR-009 graded every row on the Nifty).
- `tally` gains `vs_cash`, `vs_nifty`, `mean_result_pct`, `mean_nifty_result_pct`; the gate look
  gains `mean_result_pct`, `unknown_result`, `better` and the money reasons.
- `scorecard_text`: each horizon names its mean result; a pass names "not worse" (and "better").

Not changed: the pipeline (it passes nothing new; SA-049 will pass `deploys_cash`), the stops,
the minimum holding period, the invalidation level and its price basis, one decision per holding,
the store's write-once rule.

## Design decisions (delegated, recorded)

1. **The 22-session boundary.** A run counts when at most 22 sessions have closed after its IST
   day, up to the review day: on or after `trading_days_ago(on, 22)`. For 23 Oct that is Monday
   21 Sep (22 sessions) in, Friday 18 Sep (23) out, and a Sunday 20 Sep run is out too (23
   sessions closed after it). This is the card's acceptance wording ("22 sessions old sells, 23
   does not"). With the monthly forecast, a month of up to 23 sessions keeps the 1st's verdict to
   the month's last session.
2. **The buy day itself never counts.** The holding stores a buy day, not a time, and an analysis
   on that day could have been seen before buying.
3. **An unreadable buy date lets no verdict count.** No run can be shown to postdate the buy (the
   holding period is unknown then too, so `case_broken` already waits).
4. **An allow-list, not "everything but news".** A source added later sells only when it is put
   in `CASE_EVENT_SOURCES` on purpose; a test fails until every source is placed on one side.
5. **The selling rule's own verdict sets the benchmark.** The rule that sold decides where the
   money went; TRIM is not a sale of the position (as in PR-009's `sells`), so TRIM against EXIT is
   graded against cash.
6. **A row without a benchmark is ungraded, never re-derived.** No production row exists (PR-009
   never deployed), so no stored row lacks it. Re-deriving from the verdicts would let a later
   rule change re-grade stored decisions.
7. **Cash with no Nifty close is still graded** on the stock alone, with no Nifty figure; a Nifty
   decision with no Nifty close is ungraded.
8. **A missing result fails the money check at its horizon.** Results are unbounded (a stock sold
   and then up 150% is −150), so any stand-in value could flatter the rule; failing is the only
   rule under which a missing grade can never help. The count rule is unchanged (a missing grade
   is not right). Consequence: a close that stays missing keeps the gate shut (KT section 6 limit).
9. **Exact sums.** `pct_change` and `excess` round to 4 decimals, so results are summed as
   integers in 1/10,000 of a point: a mean of exactly 0 passes, with no float drift either way.
10. **"Better" needs a pass.** It is a label on a pass (15 decisions, 8 weeks, no stock above 30%,
    count and money), never a pass on its own.

## Invariant tests (expected values worked by hand)

[tests/unit/test_exit_fix016.py](../../../../tests/unit/test_exit_fix016.py), 37 tests, reusing
PR-009's fixture world (`_pipeline_world`, `_world`, the 23 Oct review day). Sessions are counted
by hand (weekdays less 14 Sep, 2 Oct and 20 Oct) and checked against the calendar.

- **Verdict:** a SELL 22 sessions old (21 Sep) sells; 23 (18 Sep) and a Sunday-night run do not;
  00:01 IST Monday does. The card's hand-added example: SELLs of 24 Sep, 7 Oct and 8 Oct (09:30 and
  23:59 IST) never sell a holding bought 8 Oct; 9 Oct 00:01 IST and 15 Oct do. A newer BUY over an
  older SELL does not sell; the reverse does; a BUY from before the buy neither hides a later SELL
  nor counts. An unreadable buy date lets nothing count. Through the real pipeline and autopilot
  under `evidence`: the 24 Sep SELL keeps the stock, a 9 Oct SELL sells it.
- **Events:** every source parametrized: news never sells and is a watch item, the other six sell;
  `CASE_EVENT_SOURCES` equals the schema's sources less news. A news event in the selling list, or
  one with no source, still does not sell. The recorded NSE Reg 31 row (VINCOFE, 22 Oct 20:49 IST)
  turned into an invocation is typed high negative by the rules and sells. Through the pipeline:
  news is watched (`watch_event_ids`), the same text as an NSE announcement sells.
- **Benchmark:** the verdict matrix (11 cases, deployment included). Stock −3%, Nifty −5%, through
  `decide` and `shadow_row`: plain EXIT cash, right, +3; SWITCH Nifty, wrong, −2; the price-path
  rule's EXIT with the evidence rule keeping: cash, wrong, −3; its SWITCH: Nifty, right, +2. The
  same row graded under each benchmark, under every `advisor.exit_rule` setting (identical), with
  a later SWITCH row of the same holding (the first row's cash stands), without a benchmark
  (ungraded) and without a Nifty close (cash graded, Nifty ungraded). Through the pipeline: plain
  EXITs store `cash`, agreements `""`, and with an IT idea on offer both sales store `nifty`.
- **Money check:** the card's 8-of-15 example fails with −3.60 at both horizons and the exact line;
  8 right at +5 and 8 wrong at −1 passes at +2.00 as "not worse", not better; a mean of exactly 0
  passes; one missing 10-session close turns that pass into a fail with its reason; 11 of 15 with a
  positive mean is better, 10 of 15 is not, 11 of 15 at a mean of 0 is not, 11 of 15 losing money
  fails. The gate's constants as the card fixes them.
- **Oracle:** 2,000 random populations (13–21 decisions, some pending, some missing, half leaning
  right) against an oracle written from the card in exact fractions: status and `better` agree on
  every one; then each graded result in turn is made missing: a non-pass never becomes a pass, and
  a pass always becomes a fail. Every branch occurs more than 20 times.

**Existing tests changed** ([test_exit_evidence_pr009.py](../../../../tests/unit/test_exit_evidence_pr009.py);
a contract moved, no assertion was relaxed):

- `_row` gains `benchmark="nifty"` (rows without one are now ungraded); PR-009's grading tests
  keep their Nifty expectations.
- `_random_case`'s event dict gains `"source": "nse_announcement"` (`case_broken_reasons` needs a
  selling source); the property still sees `case_broken` more than 50 times.
- `_grades` gives each graded grade `result_pct: 0.0`, so the money check neither passes nor fails
  a look on its own there.
- The two exact scorecard lines and the tally dicts gain the mean results and the "not worse" and
  "better" wording.

**Mutants.** [analysis_data/fix016/mutants.py](../../../../analysis_data/fix016/mutants.py) with
`mutplug.py` (ignored): 33 one-rule mutants applied in memory after collection (the function's code
object is replaced, so every reference runs it; constants are rebound). Caught = pytest's summary
says " failed". **33 of 33 caught** across the verdict window and buy-day rule, the event split
and source guard, the watch record, each benchmark branch, the result sign, the money check (removed,
missing ignored, strict zero, one horizon only, floor −1) and the `better` label. The 6 constant
mutants were also caught with the constant tripwires deselected (`FIX016_K`), so a behaviour test
catches each of them.

## Commands and environment

- Python 3.13, `.stockai/Scripts/python.exe`; the SA-005 hermetic boundary (no network, no
  checkout data).
- `python -m pytest tests/unit/test_exit_fix016.py tests/unit/test_exit_evidence_pr009.py -q`:
  **76 passed** (37 + PR-009's 39), 32 s.
- Full suite `python -m pytest tests -q`: **5,748 passed, 12 skipped, 1 xfailed, 0 failed** (16 min 12 s, 12:02–12:18 IST; PR-009 ended at 5,711). A first run with `-p no:logging` (my flag, to quiet the output) errored the 53 tests that use the `caplog` fixture, which that flag removes; they never ran. The suite was then re-run whole without the flag (above). Both outputs are in `analysis_data/fix016/` (ignored).
- `python analysis_data/fix016/mutants.py` (33 of 33) and `FIX016_K="not fixture_sessions and not
  gate_is_fixed and not every_event_source_is_decided" python analysis_data/fix016/mutants.py
  verdict_window_23 verdict_window_21 floor_minus_one better_at_60 news_is_a_case_source
  pledge_not_a_case_source` (6 of 6).
- `python scripts/docs/build_kt_pdf.py` (57 pages, source SHA-256 `3608dff5…`) and
  `python scripts/docs/check_kt_docs.py`: errors `[]`.

## Documentation

- **KT section 6** (Two exit rules): the evidence rule's event sources and fresh verdict, with the
  hand-added example; news as a watch item; the row's benchmark; grading against cash or the Nifty
  with the −3%/−5% example; the gate table's money row; "What a pass means: not worse" with the
  8-of-15 example and the `better` label; two new limits (a close that stays missing, a holding
  whose monthly re-analysis did not run). The "Planned, before the shadow starts (FIX-016)"
  paragraph is gone: it is current design now. **KT section 7:** the Exit rule test line.
  PDF rebuilt.
- **CODEBASE.md:** the advisor and exit_shadow rows. **config.yaml:** the `advisor.exit_rule`
  comment.
- **Testing guide:** 07-L (the reasons, the watch ids and the benchmark in the production export),
  09-H (the money version and the wording of a pass), new **07-M** (the corrected inputs in a test
  environment); Related PI lines.
- **Commit-time edits** (not made now, as with PR-009): the KT header's Code inspected revision and
  edition; section 1's production paragraph; section 12's FIX-016 row Done; the guide status lines
  ("accepted …, committed as …").

## Manifest and digests

- **Review input:** [FIX-016-manifest.json](FIX-016-manifest.json), 10 files. The SHA-256 of its
  LF bytes is **`72268ff3eacd20bd07443627cc63a181cf09be75a25a0de6f67a059ac13c4a51`**;
  `kt_manifest.py verify` gives 0 mismatches.
  - Code (4): `config.yaml`, `core/portfolio/advisor.py`, `core/portfolio/exit_shadow.py`,
    `src/backend/shared/schemas/portfolio.py`.
  - Tests (2): `tests/unit/test_exit_evidence_pr009.py`, `tests/unit/test_exit_fix016.py` (new).
  - Docs (4): `CODEBASE.md`, the KT and its PDF, the testing guide.
  - Excluded: STATE, HANDOFF and this receipt (bookkeeping), and session -cb's uncommitted
    owner-decision docs (the FIX-016 and PR-013 cards, the PR-005, PR-012 and SA-049 notes, the PI
    README, `docs/README.md`, `docs/START_HERE.md`). They need their own docs commit before or
    with FIX-016's; the FIX-016 card is this story's input, unchanged here.
- **FIX-016's own diff:** **`dd35017d2820bf8b49cee222c44e8b09ee8ca19ec5f16fdaf30a4b70fbcd1763`**,
  105,082 bytes over 9 paths (every manifest path except the PDF), by
  `analysis_data/fix016/digest.py`. It checks that HEAD is `8cb626c`, then for each path, sorted:
  the KT against `analysis_data/fix016/start/docs/TECHNICAL_DESIGN.md`, the copy saved before the
  first edit (SHA-256 `1423d47b…`; it held session -cb's edits, so its blob `fa22add8` is not
  HEAD's `fac50556`); `git diff HEAD -- PATH` for the 7 other tracked paths (the guide's start copy
  equals HEAD's blob `d58e778b`); `git diff --no-index /dev/null PATH` for the new test file.
- **Cumulative against HEAD:** **`c583962ef57aedb44759ae0b623f3739009a6f2ba8b8cbd61a024695a7510001`**,
  106,562 bytes over the same 9 paths; it also carries session -cb's KT edits (sections 1 and 12;
  its section 6 "Planned (FIX-016)" paragraph, which this phase replaced with current design).
- Both digests were run twice, with the same result. The diffs are `fix016.diff` and
  `cumulative.diff` beside the script (ignored).

## Self-review (same conversation; not the fresh review)

- **Can a verdict the buyer saw before buying still sell?** No: the buy-day and earlier runs are
  filtered before the newest is chosen, so neither a pre-buy SELL nor a pre-buy BUY reaches the
  rule (tests and two mutants).
- **Can a news article reach a sale another way?** Not through `case_broken`: the split and the
  source check in `case_broken_reasons` each stop it (two mutants, each caught alone). The stops,
  `shock_reforecast` and `crisis_regime_bearish` do not read events. PR-005's pillar must keep the
  rule; its card says so.
- **Is the benchmark the decision day's?** It is written once with the row and read from it; the
  holding's first disagreeing row is the decision, so a later SWITCH row changes nothing.
- **Can ungraded or pending decisions help?** Pending ones are outside the population; a missing
  result fails the money check and is not right in the count (oracle property).
- **PR-009's invariants:** its 39 tests pass with the helper changes above; one decision per
  holding, information as of the review day and the level's price basis are untouched code.
- Found and fixed in self-review: guide case 07-M first had the IT idea on offer in the same run
  as the plain-EXIT holding, which would have made that sale a SWITCH too; the idea now has its own
  run. The KT limit first implied the owner can clear a missing close; nothing does.

## Limits and follow-ups

- A close that stays missing (a suspension or delisting) keeps the money check failing every week;
  the line counts them.
- The 22-session window relies on the monthly re-analysis of every managed stock; a holding the
  forecast skipped has no research verdict after 22 sessions.
- `deploys_cash` is not passed by the pipeline yet: SA-049 must pass it from the day deployment is
  on (its routed note says so).
- Measured benefit: none. The rule is in shadow and no row exists; this story changes what will be
  recorded and how it is judged, not any trade.

## For the owner

The evidence exit now ignores research it could have seen when you bought, and verdicts older than
22 sessions. A news headline can no longer sell a stock; a filing with NSE or a rule-typed
disclosure still can. Each decision is judged against where the money really went, cash after a
plain sale and the Nifty after a switch. The switch gate now also checks money: half right but
losing on average fails. A pass means "not worse"; "better" is shown only at 70% right with a
positive average. Next: the fresh review in a new conversation; then PR-009 and FIX-016 go out
together, at your word, in a job-free window.
