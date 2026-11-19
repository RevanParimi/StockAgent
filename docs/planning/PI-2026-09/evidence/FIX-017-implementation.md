# FIX-017 — implementation receipt

**Story:** [FIX-017](../stories/FIX-017.md): the holding sync reads every NSE corporate-action row
it is given, under NSE's code. Routed from FIX-016's rework 2 and its fresh re-review (25 and 29
Oct 2026). Profit-path step: **hold** (the quantity and average price the stops and targets read)
and **measure** (the exit rule's grading reads the same rows).

**Lane: decision path.** Reason: it changes a holding's adjusted quantity and average price, the
ledger's arithmetic that the price-path stop sells on, and how the exit rule's grading reads a row
(AGENTS.md step 4). **Status after this phase: `review_required`.** The next fresh conversation
performs the hard review from `REVIEW.md`; this phase's self-review does not count as it.

## Phase

- **Implementation** (autopilot `1119-1710-p3`, code-server, Thu 19 Nov 2026 from about 17:10
  IST, outside a push window). Baseline **`a09bde8`** (`main`, 20 commits ahead of `origin/main`
  `3f26ae5`). The code, tests and living documents are **`b425f8c` on `story/FIX-017`**, which
  only a fresh review's acceptance merges into `main`. Production was not read; nothing pushed, deployed, run or sent.

## What changed

**One reading for the sync and the grading** [code]. Before, the sync applied whatever
`parse_action` found first in each row; the grading read the same rows through
`action_record`, which fails closed (FIX-016 rework 3). Now `sync_corp_actions` applies only
`sync_reading`'s actions: the bonus and split ratios `action_record` reads in full, once per
ex-date and kind, and each row `parse_action` reads as a dividend in rupees. So the two cannot
disagree on a ratio: the sync's ratio for a row is the product of the record's ratios for it.

**The card's four findings**, each against a holding of 100 shares bought at ₹1,000:

| # | NSE's row | Before | Now |
|---|---|---|---|
| 1 | "Bonus 1:1/Face Value Split (Sub-Division) - From Rs 10/- Per Share To Rs 2/- Per Share" (BAJFINANCE 2016) | ×2: 200 at ₹500, −80% at ₹100 | ×2 and ×5: 1,000 at ₹100, 0% |
| 2 | "Bonus Preference Shares 21:1" (ZEEL 2014); "Scheme Of Arrangement - Bonus Ncrps 4:1" (TVSMOTOR 2025); "... Bonus Debentures 6:1" (DRREDDY 2011) | ×22, ×5, ×7 | unchanged, a named gap |
| 3 | "Fv Splt Frm Rs 10 To Re 1" (JSWSTEEL 2017); "Fv Splt Frm Rs 10 To Rs 2" (KNRCON 2016) | not seen: −90%, −80% | ×10 and ×5 |
| 4 | CANARABANK's 1:5 split ex 15 May 2024 | asked NSE for CANARABANK: no row, ₹500 against ₹100, −80% | asked for CANBK: 500 at ₹100 |

**The split reader** [code]. `_SPLIT_RE` reads a split's two face values after the word that
names it (`split`, `splt`, `sub-division`), with no other number between, so a number before the
word is never read ("Dividend Rs 5/Face Value Split From Rs 10 To Rs 2" is ×5, not ×2.5). The
split's words add `fv`, `splt`, `frm`. A split that adds no shares (from Rs 1 to Rs 10) is a
consolidation and is not read.

**A row naming a bonus and a split** (decided: apply both; the card left it to the implementer).
Each ratio is stated in the row, and they multiply in either order (×2 then ×5 or ×5 then ×2),
so holding the symbol with a gap would leave a −90% "fall" for the stop. The record gives two
actions: the bonus keeps the row's key, the split's key adds `|split`. Beside a change no ratio
converts (a rights issue), only the words that state the two ratios are read, as FIX-016 did for
one; the change still leaves grading without a result. A row naming both where either ratio is
missing ("Bonus 1:1/Face Value Split") is not read, never as its other part alone.

**A bonus of preference shares, debentures or NCRPS** (decided: a named gap, not a payout). The
row states a count of other securities, not their rupee value, so no cash credit can be read
from it; the holding is unchanged and named.

**The named data-health line** (decided: a log warning and the sync's result). Each share-count
row after the buy, by the review day, that the sync leaves unapplied is logged each review as
`[corp_actions] data health: <symbol>: NSE lists a split or bonus on <day> that could not be read
('<row>'); the quantity and average price are unchanged`, and returned in the sync result's new
`gaps`. The data-health store (`services/data/stores/data_health.py`) records an analysis's
sections and has no row for a holding, so it was not used.

**Idempotency** (the card asks what happens to holdings applied under the old reading):

- Keys are unchanged for every single-ratio row, so a row applied before is never applied again.
- A bonus or split is also applied once per ex-date and kind, whichever row states it: NSE
  rewording a row ("Bonus 1:1 (Revised)") gives a new key, not a second bonus (×2, not ×4).
- Two ratios of one kind on one day: neither is applied, named (the grading has no result
  across that day either).
- **A row naming a bonus and a split, applied before as its bonus alone (×2):** the bonus's key
  is already applied; the split's new key applies ×5 once: ×10 in all, correct.
- **A bonus of other securities applied before (×22, ×5, ×7):** never reversed. The sync names
  it each review ("applied under an earlier reading, and NSE's row no longer reads as one; the
  quantity and average price keep it until corrected by hand"); the correction is an operator's
  ledger step. On 29 Oct the production probe found no bonus or split applied to any holding,
  and every bonus of other securities in NSE's lists of that day (the rows above, BLUEDART 2014,
  BRITANNIA 2019) is ex in or before August 2025, before any paper holding's buy, so none is
  expected; one listed since would show on the first review after the deploy. [inference: no
  production read in this phase]
- **A short-wording split or an alias's split missed before:** applied on the next review if its
  ex-date is after the buy and by that day.

**Found on the way, fixed** [code]: PR-005's purchase record (`cases._corp_record`) also asked
NSE under the app's code, so an alias's case read an empty list and its invalidation price was
unused. It now asks `nse_symbol(symbol)`, as the grading and the sync do.

| File | Change |
|---|---|
| `core/portfolio/corp_actions.py` | `_NAMES_SPLIT_RE`, `_SPLIT_RE` read after the split's word; `_share_count_parts` and `_read_ratios` (two ratios for a row naming both); `apply_actions_to_holding` once per ex-date and kind; `sync_reading`; the sync fetches `nse_symbol(symbol, today)` and returns `gaps` |
| `core/portfolio/cases.py` | `_corp_record` asks under `nse_symbol` |
| `tests/unit/test_corp_sync_fix017.py` | new, 29 tests (below) |
| `tests/unit/test_exit_fix016.py` | the rows FIX-017 reads now: expectations changed, each by hand (below) |
| `tests/unit/test_exit_fix018.py` | the sync's result gains `gaps` |
| `docs/TECHNICAL_DESIGN.md` | KT section 6: "Corporate-action sync" (the reading, an example, what is named, the limit); the invalidation level and "Each row is read in full" paragraphs; the 29 Oct counts note |
| `CODEBASE.md` | the `corp_actions.py` row |
| `docs/TEAM_TESTING_GUIDE.md` | case 08-I |

## Tests

- **New `tests/unit/test_corp_sync_fix017.py`, 29 tests**, all through the real sync with a
  `PortfolioStore` in a temporary folder:
  - a table of every NSE subject the card quotes plus the plain bonus, split, dividend and a
    meeting, each with its quantity, average price, dividends and gap worked by hand, and the
    holding's worth at the ex-day's fair close unchanged by any ratio (11 cases);
  - for the same 11 rows, the sync's applied ratio equals the product of the grading record's
    ratios, and the sync names a gap exactly where the record holds the row unread;
  - Canara Bank through the real `fetch_corp_actions` with an NSE client stub that answers only
    NSE's own codes: asked once, for CANBK; 500 at ₹100; the dividend after the split credited
    on 500 shares (₹8,050); NSE lists nothing under CANARABANK;
  - PR-005's purchase record asks for CANBK;
  - idempotency: the bonus-and-split row applied as its bonus alone gets its split once (×10),
    and a second sync applies nothing; the preference bonus applied as ×22 is named twice
    (unread, applied earlier) and not reversed; a reworded bonus row is not applied again; two
    bonus ratios on one day apply neither; rows before the buy or after today are neither
    applied nor named.
- **`tests/unit/test_exit_fix016.py`, changed where FIX-017 changes the reading:** the record
  test (the BAJFINANCE row is ×2 and ×5, nothing unparsed); the horizon by hand (₹100 is ₹1,000
  in the old shares across that row); the invalidation level across it (₹455 → ₹45.50, was
  unused); the RR2 table (the four short splits are ×10, ×5, ×2, ×10; BAJFINANCE ×2 and ×5;
  "Splt Frm Rs 10 To Re 1" ×10; the bonus-and-split beside a rights issue: both ratios and the
  rights issue named; five new rows: a reverse split, a split to a higher face value, a bonus
  with no ratio beside a split, a bonus beside a split with no values, and a dividend before a
  split, ×5); the short-split grading test (graded at 0 with "×10 for the split", and
  BHARTIARTL's "Fv Rs10tors5" still no result); the level with the short split (₹45.50) and with
  "Bonus Debentures 6:1" (unused). The random-market test moves the two short splits and the
  BAJFINANCE row (×10) to the rows the record reads, keeps BHARTIARTL's as odd, and lists one
  share-count row a day per stock (two would be two ratios of one kind, no result by design).
- **Focused:** the corporate-action and grading suites (FIX-016, FIX-018, PR-005, PR-009,
  FIX-019, the fetcher, the sync, FIX-017): all passed.
- **Full suite** on the final tree: see "Full suite" below.
- `scripts/docs/check_kt_docs.py`: no errors. `scripts/ci/check_broad_except.py`: OK (148
  grandfathered). `scripts/docs/run_kt_checks.py` was not usable: its copy of the repository
  leaves out `data/`, and `tests/hermetic.py` reads `data/nse/key_registry.json` at import (not
  this change; recent receipts use the full suite instead).

## Self-review (not the fresh review)

The card's hard-review questions, answered from the code:

1. **Can any row change a holding's quantity by a ratio NSE's row does not state for equity
   shares?** Only `action_record`'s ratios reach `apply_actions_to_holding` for a bonus or
   split. Each is read from the row's own numbers, and only when every word is of an equity
   bonus, a face-value split or a neutral part; a preference, debenture or NCRPS bonus, a
   warrant bonus, a reverse split and a split to a higher face value are refused. A second row
   for the same ex-date and kind is not applied again; two different ratios apply neither.
2. **Can a row the sync cannot read still move a stop?** It cannot move the holding's cost or
   quantity, so the stop level is unchanged. The price still moves, so the price-path stop can
   still fire on a fall such a row caused (as before this card). The row is named each review.
   **BACKLOG B-21.**
3. **Do the sync and the exit rule's grading read the same rows the same way?** Yes by
   construction: the sync applies the record's ratios (pinned by the agreement test over every
   row in the table). The grading's `horizon_in_basis` also counts one ratio per ex-date and
   kind and refuses two. The invalidation level (`level_in_basis`, `cases.level_at_buy`) counts
   the record's ratios once per row key, so two listed rows for one bonus would count twice:
   pre-existing, latent. **BACKLOG B-22.**

Other checks: the sync still never raises per symbol (`nse_symbol` is inside the per-holding
`try`); a failed or empty fetch still gives an empty record and nothing applied (FIX-018's test,
plus `gaps: {}`); raw `qty` and `avg_buy_price` are never written; dividends keep their order
by ex-date, so a dividend after a split is credited on the split shares.

## Acceptance criteria

- A table test of every NSE subject quoted, plus the plain bonus, split and dividend rows, each
  worked by hand: `test_every_row_has_the_effect_worked_by_hand`. **Met.**
- A Canara Bank holding through the real sync, with a fixture answering only NSE's code:
  `test_a_canara_bank_holding_is_split_through_the_real_sync`. **Met.**
- Idempotent by action key; a row applied under the old reading not applied twice; what
  happens to such holdings: "Idempotency" above and its four tests. **Met.**
- KT section on corporate actions, CODEBASE row, a guide case (08-I); story file, changed files
  and the full suite: **met** (the full suite below). The PDF is not regenerated (AGENTS.md).

## Full suite

On the tree committed as **`b425f8c`** on `story/FIX-017` (`a09bde8..b425f8c`: 8 files, +509 / −103; `git diff a09bde8 b425f8c | sha256sum` starts `77549aaf2d3aac58`), Python 3.13.5,
`.stockai/bin/python -m pytest -q`: **6,978 passed, 12 skipped, 1 xfailed, 0 failed** (7 min 7 s,
Thu 19 Nov about 21:30 IST). The working tree also held this phase's records (STATE `in_progress`,
BACKLOG, HANDOFF, this receipt), which no test reads for FIX-017.

## Commands

```
.stockai/bin/python -m pytest -q tests/unit/test_corp_sync_fix017.py tests/unit/test_portfolio_corp_actions.py
.stockai/bin/python -m pytest -q tests/unit/test_exit_fix016.py tests/unit/test_investment_case_pr005.py \
    tests/unit/test_exit_evidence_pr009.py tests/unit/test_exit_fix018.py tests/unit/test_registry_fix019.py \
    tests/unit/test_corporate_events_fetcher.py
.stockai/bin/python -m pytest -q
.stockai/bin/python scripts/docs/check_kt_docs.py
.stockai/bin/python scripts/ci/check_broad_except.py
```
