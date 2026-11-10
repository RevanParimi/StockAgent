# PR-009 review receipt — exit on evidence, not on a price-path miss

## Fresh re-review of rework 1: ACCEPTED (2026-10-24)

**Phase:** fresh-session re-review, a new conversation opened with "continue" (24 Oct, about
08:50–09:35 IST, session `stockagent-main-87` [f3d972]). The implementation was session
`stockagent-main-af`, review 1 `stockagent-main-da`, rework 1 `stockagent-main-c4`. This
conversation is none of them and did not read them. At the start, peers `-c4`, `-da` and
`depth-eval-resume-engine-b9` were idle; `-cb` was busy with the untracked `docs/START_HERE.md`,
which is not PR-009's.

**Verdict: ACCEPTED** for the reviewed revision (below). Both high findings are resolved:

- **F1:** the invalidation level is compared in the review day's price basis, or not used. An
  independent random-history test (RR1, 6,000 cases) found no used level that differed from the
  true-basis level, except one shared corner (I1) that never arises with NSE's list as measured.
- **F2:** each holding is one decision, on its first disagreeing day. An independent oracle over
  400 random portfolios (RR2) agrees with `first_disagreements`, the scorecard block and the gate.

L1 is done and L2 is routed to PR-007's card, as asked. Three new **low** items remain; none
blocks:

- **RR-L1:** a demerger (or another basis change without a share-count ratio) between the dive
  and the buy leaves the level in the old basis. It is rare, and the entry rule reads the same
  unadjusted level. Routed to [PR-005](../stories/PR-005.md), before any switch to `evidence`, plus
  a KT section 6 limit at commit time.
- **RR-L2:** the KT says NSE's reach "has not been measured". This review measured it, so the
  text changes at commit time (exact wording below).
- **T1:** the story file does not pin a split or bonus that goes ex on the buy day. The code
  handles that case correctly. Routed to PR-005's acceptance criteria.

**Nothing was committed, pushed, deployed or configured.** No production state was read, no model
was called and no message was sent. **One network read was made:** NSE's public corporate-actions
list for 12 listed symbols (one call each, through the production fetcher, without credentials) to
measure the list's reach. The tracked files this review changed are STATE, HANDOFF, this receipt
and the routed note on `stories/PR-005.md`. The reviewer's scripts and outputs are in the ignored
`analysis_data/pr009_rereview/`.

### In one example (F1, through the real sync and pipeline)

FFF is dived on 1 Sep at about ₹1,000, and its shelf idea sets the invalidation level at ₹900. A
10→2 face-value split goes ex on 15 Sep (×5 shares). FFF is bought on 30 Sep at ₹200, after the
split, so the sync applies nothing. NSE's list read on the review day holds the split and a 2025
dividend (RR3, both modes).

| Close on 23 Oct | Reviewed code (review 1) | Now (worked by hand) |
|---|---|---|
| ₹185 (−7.5% from cost) | fires: 185 ≤ 900 | level **900 / 5 = ₹180.00**; nothing fires |
| ₹180 | fires | at the level: `case_broken`, sold only under `evidence` |
| ₹150, NSE's list holding only the split | fires | the list starts after the dive, so the level is unused and the gap says why; the stop fires anyway (−25%) |

### NSE's reach, measured (the rework's open limit)

The sync asks NSE for a symbol's actions without dates (`nse.actions(symbol=…)`, whose docstring
says "forthcoming"). On 24 Oct at 09:00 IST, through the production fetcher
(`analysis_data/pr009_rereview/nse_reach_probe.py`, public data):

- **7 of 12 returned exactly 20 rows:** MARUTI, RELIANCE, HDFCBANK, INFY, BAJFINANCE, TMPV and
  WELCORP. Their earliest rows fall between 2005 and 2018, and their latest in 2026.
- **3 returned fewer rows:** LICI 7 (from Aug 2022), JIOFIN 2 (from Aug 2025) and NYKAA 1 (its
  2022 bonus).
- **2 returned nothing:** TATAMOTORS and ETERNAL.

So, by inference from that shape, the list holds the symbol's latest 20 actions of any kind (or
all of them, when there are fewer). For a listed company with any action before the dive, it
reaches back past the dive, and the level is then used and adjusted. It stays unused for a stock
whose earliest listed action is after the dive (JIOFIN dived before Aug 2025) or that has none.
That is conservative, and 07-L's count shows it. The probe also met a real 4:1 bonus and a ₹2→₹1
face-value split on the same ex-date (BAJFINANCE, 16 Jun 2025). They are two keys, both counted:
÷5 then ÷2.

### Review input verified

- **Manifest:** [PR-009-manifest.json](PR-009-manifest.json), sha256 `0c6057e9…ef2256`, 19 files.
  `scripts/docs/kt_manifest.py verify` gives 0 mismatches at the start and at the end.
- **Review 1's input, rebuilt independently:** HEAD's blob of each path, plus review 1's own
  `analysis_data/pr009_review/review.diff` (`9ef8fdba…`) applied with `git apply` into the
  re-reviewer's own folder. All 17 rebuilt files match manifest `5afb4aa1…` and the implementer's
  `review_input/` copy.
- **Rework diff:** `4afc909a086e2ae33486fa9a3b48694055ae494b4cad429d242d4761fd383342`, 91,569
  bytes, 18 paths. Recomputed from the rebuilt input
  (`analysis_data/pr009_rereview/rr_digest.py`); the bytes equal the receipt's.
- **Cumulative diff:** `86aac81bbb5c6163718bd770dcf2567501c57e196c2e204839169d4076e16495`, 163,305
  bytes, against HEAD `d7c1411`. Recomputed at the start and at the end.
- Outside the manifest, the working tree holds only bookkeeping (STATE, HANDOFF, the receipts and
  the manifest), this review's routed note on `stories/PR-005.md`, the owner's `docs/README.md`
  line and peer `-cb`'s untracked `docs/START_HERE.md`. No review edit touched a reviewed path.
- At the end, the second rebuild (into a fresh folder, because OneDrive refuses to delete the
  first) gave the same 17 matches and the same two digests.

### Contract checked

| Contract | Result | How it was checked |
|---|---|---|
| F1: the level in the close's basis, or unused | **Holds** | `exit_shadow.py:161-221`. After the buy, the holding's applied actions (`buy < ex ≤ day`), which are exactly what `corp_actions.py:167` applies. From the dive to the buy, NSE's list (`dive < ex ≤ buy`), counted only if its earliest row is on or before the dive. A share-count action on the dive day, or an unparseable split or bonus row from the dive day on, gives a gap. The two windows meet at the buy day without overlap, so neither double-counts the other. RR1 (6,000 random histories, NSE rows in NSE's own wording, the list cut to its latest K rows, the holding built by the real `apply_actions_to_holding`): every used level equals the level at the dive divided by every true share-count ratio after the dive, except I1. Liveness: with the full list reaching the dive and nothing ambiguous, the level is used, 238 of 238. |
| F1 end to end | **Holds** | RR3 (above) and the story's R1 invariant. The pipeline keeps the sync's `records` (`pipeline.py:192-197`) and passes them to the reader (`:268`). The reader normalises the symbol (`exit_shadow.py:272`). The sync applies byte for byte as before, and the record is built from the same rows (`corp_actions.py:203-216`). |
| F1: never fires on an unestablished basis | **Holds for bonuses and splits; RR-L1 for other basis changes** | RR1's second property: a close 0.1% above the true-basis level never fires, and a close 0.1% below a used level always does. A demerger row is not a share-count kind, so it is ignored (RR4). |
| F2: one decision per holding | **Holds** | `exit_shadow.py:339-356`: rows sorted by day, keyed by (symbol, buy date), first kept. Grading (`:372`), the block (`:479`) and the gate's population all use it. RR2 (400 random portfolios of up to 6 stocks, each held up to 3 times, rows shuffled) against an oracle that groups by holding: the same decisions, `repeat_days`, matured count and top-stock count. An ADD keeps `buy_date` (`autopilot.py:184-191`), so a holding's identity is stable. |
| F2: the gate counts decisions | **Holds** | The story's R2 gate test through the real weekly scorecard reads "not yet (4 of the 15 decisions …)" both Sundays. Review 1's own repro now fails on its defect line (`not_enough`, 4 matured). |
| L1: a carried-forward close | **Holds** | `exit_shadow.py:375-395`: the Nifty is read from the row's `price_bar_date` (a later bar date is ignored). The stock's return starts from the same close, and the horizons are counted from the review day (D14). The story's hand fixture (−4.0 against −3.02) was re-derived. |
| Stops, `shadow` default, issue-time evidence, one row per day | **Unchanged and still hold** | The rework does not touch `decide`, the stops, the event or score readers, the store's once-only append or `config.yaml`. The story's property test and the shadow/legacy byte identity pass. |
| Documentation | **Describes the reviewed behaviour, except RR-L2** | KT section 6 ("The invalidation level's price basis", "Decisions", grading, the gate table, "When it can first pass", the limits) and section 7's scorecard row; CODEBASE (`exit_shadow.py`, the new `corp_actions.py` row); guide 07-K (e), 07-L (buy dates, levels, the gap count) and 09-H (decisions, 3 later days, the four five-day stocks); PR-007's routed L2 note. D4′'s arithmetic was re-derived: 8 + 6 + 1 = 15 weeks at two a week, 14 + 6 + 1 = 21 at one. `check_kt_docs` gives exactly the one expected error. The PDF's source digest `3f51e3dd…` equals the manifest's KT. |

**Rulings on the rework's decisions:**

- **D12 is upheld.** For a dive after the buy it trusts the holding's record, so the level shares
  the stops' basis (I1).
- **D13 is upheld.** It is the rule review 1 asked for.
- **D14 is upheld.**
- **D4′ is upheld** as arithmetic.

### The re-reviewer's own cases

`analysis_data/pr009_rereview/test_rr_pr009.py` uses its own generator and oracle, the hermetic
hooks (`conftest.py`) and, for RR3, the story's pipeline world re-pointed through the real sync.
**6 passed.**

- **RR1:** the random-history safety and liveness properties above. The generator is biased
  toward the boundaries: a dive on the buy day, and rows within a few days of the dive.
- **RR1b:** a close just above the true-basis level never fires, and just below a used level
  always does.
- **RR2:** decisions against the oracle, in any row order.
- **RR3:** the split between the dive and the buy, in both modes (table above).
- **RR4 (RR-L1, asserts today's behaviour):** a demerger ex between the dive and the buy. The level
  stays ₹455 and fires at ₹455, 3.2% below the ₹470 cost, with the 12% stop far away.

### Findings

| ID | Severity | Location | Trigger | Observed | Expected | Disposition |
|---|---|---|---|---|---|---|
| F1 | (high, review 1) | — | — | Resolved: RR1, RR3, the story's R1 invariant; review 1's R1 repro fails on its defect line | — | **Resolved**, with RR-L1 and I1 |
| F2 | (high, review 1) | — | — | Resolved: RR2, the story's R2 tests; review 1's R2-gate repro fails on its defect line | — | **Resolved** |
| L1 | (low, review 1) | — | — | Done (D14) | — | **Resolved** |
| L2 | (low, review 1) | `stories/PR-007.md` | — | Routed input present, with a fixture for each reason, before any switch | — | **Routed** (PR-007) |
| **RR-L1** | Low (confirmed by reproduction, RR4; rare in practice) | `core/portfolio/exit_shadow.py:68,187-190` (`SHARE_COUNT_KINDS`) | A demerger, capital reduction or rights issue goes ex between the dive and the buy | The price falls by the value that left, and the level does not. Dived at ₹500 with the level ₹455, a demerger takes the price to ₹470 and the entry rule allows the buy there. A 3.2% fall to ₹455 fires `case_broken`, with the 12% stop far away. In `shadow` that is one false decision; in `evidence` a sale. | The test does not run on a basis it cannot establish: a basis-changing row without a share-count ratio, in NSE's list or the instrument registry, from the dive day on gives a named gap | **Follow-up: [PR-005](../stories/PR-005.md)** (its case brings its own invalidation price through the same rule), routed input added, **before any switch to `evidence`**. KT section 6 limit at commit time (text below). In the probe's 12 lists of up to 20 rows, two demerger rows appear (RELIANCE, TMPV). After the buy, a registered demerger triggers the identity hold. |
| **RR-L2** | Low (docs) | `docs/TECHNICAL_DESIGN.md:1221-1225` | — | "how far back that list reaches has not been measured. If it holds only recent and forthcoming actions, the level is unused for most holdings" | The measured shape (above) | **Commit-time edit** (text below) |
| **T1** | Low (test gap; the code is correct) | `tests/unit/test_exit_evidence_pr009.py` | The re-reviewer's mutant `listed_window_from_dive_day` (`dive < ex < buy`: a split ex on the buy day left out) | Survives the story file (39 passed); RR1 catches it | The story file pins a split or bonus ex on the buy day: the buy is at the post-split close, the sync does not apply it, and the level must be divided | **Follow-up in [PR-005](../stories/PR-005.md)**'s routed input (the same function and test file) |
| I1 | Info (found by RR1) | `core/portfolio/exit_shadow.py:191-212` | A dive after the buy; an unparseable split or bonus row from the dive day on that NSE's list read that day does not show (the fetch failed, or the list was cut to 8 rows or fewer) | The level follows the holding's record, which lacks the action. That is the basis the stops use (the sync logs "manual review needed") | — | None. 58 of 6,000 cases; none with a list of 20 rows or the full list |
| I2 | Info (measured) | `core/portfolio/corp_actions.py:148` | A company with no corporate action ever, or none before the dive | An empty list reads as "not reached", so the level is unused | — | None: conservative. Guide 07-L's gap count will show how often. |

### Mutants

The re-reviewer's own 18 mutants (`analysis_data/pr009_rereview/rr_mutants.py`, in memory, applied
after collection; none edits a file) cover 12 on the basis rule and 6 on the first-day rule:

- **On the story file:** 16 of 18 caught (`run_story_under_mutants.py`; control 39 passed).
  - `listed_future_counted` is **equivalent**: the list is only read up to the buy day, so its
    `≤ day` filter cannot change a result.
  - `listed_window_from_dive_day` survives: test gap T1.
- **On the re-reviewer's cases:** 17 of 18 caught. The survivor is the equivalent mutant.

A first run applied the mutants before the hermetic boundary's session start. Three of them then
"failed" at startup without any test failing. The runners now count a mutant as caught only when a
test fails, and the figures above come from that corrected run. The implementer's 31 rework
mutants were not re-run; their record (31 of 31) is in the implementation receipt.

Review 1's repro (`analysis_data/pr009_review/test_review_repro.py`, which asserts the defects):
R1 and R2-gate now fail on their defect lines (`evidence_triggers == []`; `not_enough`,
4 matured). R2-pipeline (its five rows are kept, as the contract says) and R3 pass.

### Commands and environment

Windows 11, the `.stockai` venv (Python 3.13), with the hermetic boundary on (SA-005).

| Command (repository root) | Result |
|---|---|
| `.stockai/Scripts/python.exe analysis_data/pr009_rereview/rr_digest.py` (start and end) | HEAD `d7c1411`; manifest `0c6057e9…`; review 1's input rebuilt, 17 files, mismatches `[]`; rework `4afc909a…` 91,569 B; cumulative `86aac81b…` 163,305 B |
| `scripts/docs/kt_manifest.py verify docs/planning/PI-2026-09/evidence/PR-009-manifest.json` | 19 files, mismatches `[]` (start and end) |
| `pytest -q -p no:cacheprovider` on the story file and 13 related files (advisor, advisor switch, portfolio pipeline, autopilot pipeline, SA-003 gate, PR-002 scorecard, PR-004 idea supply, SA-050 sizing, SA-051 Nifty, Atlas import boundary, scheduler hook, corp actions, corporate-events fetcher) | **918 passed** in 60.5 s |
| `pytest -q -rfEs -p no:cacheprovider -o console_output_style=count tests` (CI's command) | **5,711 passed, 12 skipped, 1 xfailed, 0 failed** in 9 min 41 s; no `data/` file newer than the start marker |
| `pytest analysis_data/pr009_rereview/test_rr_pr009.py` (hermetic conftest) | **6 passed** (RR1: 4,202 used, 1,798 gapped, 58 I1 cases; liveness 238 of 238) |
| `analysis_data/pr009_rereview/rr_mutants.py` / `run_story_under_mutants.py` | 17 of 18 / 16 of 18 caught (above) |
| `pytest analysis_data/pr009_review/test_review_repro.py` (review 1's repro) | 2 failed (each on its defect line), 2 passed |
| `analysis_data/pr009_rereview/nse_reach_probe.py` (12 symbols, public NSE, 24 Oct 09:00 IST) | as above; outputs `nse_reach_probe_2026-10-24*.txt` |
| `scripts/ci/check_broad_except.py` | OK (151 grandfathered) |
| `scripts/docs/check_kt_docs.py` | exactly the one expected error (`exit_shadow.py` absent at the header's `ffa012b`); PDF source `3f51e3dd…` = the manifest's KT |

**Not exercised:**

- production: nothing read;
- the `evidence` mode's narration (L2, routed);
- the implementer's 31 rework mutants (not re-run).

### Acceptance checklist

| Criterion | Verdict |
|---|---|
| The ₹500 example: legacy EXIT, evidence HOLD, both recorded with reasons | Met (unchanged; now with NSE's list and the buy date) |
| The gate fixture: passing at 30 but failing at 10 recommends nothing, nor the reverse | Met |
| Each `case_broken` path on its own fixture and not one unit short; only stops within the minimum hold | Met |
| Property: stops fire exactly as under the legacy rule | Met |
| In `shadow`, decisions and transactions byte-identical to `legacy` | Met |
| Grading uses only prices after the decision; unmatured is pending | Met (L1: the Nifty from the close's own session) |
| One shadow row per holding per review date | Met |
| The gate counts 15 matured disagreements (review 1's F2) | **Met:** 15 decisions, one per holding |
| Hard review: no stale or misattributed input fires `case_broken` | **Met for events, analyses and bonuses and splits**; RR-L1 (other basis changes) routed before any switch |
| Living docs and human test cases | Met, with RR-L2's commit-time edit |

### Commit-time edits (with PR-009's commit, after this acceptance)

The implementation's, unchanged:

- the KT header "Code inspected" bump and section 12's PR-009 row Done;
- the PDF;
- guide 07-K, 07-L and 09-H status lines (accepted 2026-10-24, the commit).

This review's: in KT section 6 "Limits", **replace** the bullet beginning "For a holding dived
before its buy" with these two bullets:

```
- For a holding dived before its buy, the invalidation test needs NSE's list to
  reach back to the dive day. The sync asks NSE for the symbol's actions
  without dates, and NSE returns its latest 20 actions of any kind, which for
  a large company reaches back years (12 symbols read in October 2026). The
  level is unused when the stock's earliest listed action is after the dive,
  or it has none, and each row's `gaps` says so.
- The level follows bonuses and splits only. A demerger, a capital reduction
  or a rights issue that goes ex between the dive and the buy lowers the price
  but not the level, so the test fires early: dived at ₹500 with the level
  ₹455, a demerger takes the price to ₹470, the stock is bought there, and a
  3.2% fall to ₹455 is at the level. The entry rule reads the same unadjusted
  level; after the buy, the identity hold covers a registered demerger.
  **Planned:** PR-005.
```

Then rebuild the PDF and re-run `check_kt_docs`.

### Decision and state

**ACCEPTED.**

- **STATE:** PR-009 `done`, `active_task` null. **`next_task` SA-048** (Charge realistic trading
  costs and tax in paper P&L), the first ready story in STATE order, which this conversation did
  not start. FIX-015's dependency is now done; it stays queued after FIX-014.
- **`production_verification`:** `pending_deployment`.
- **Commit and push only at the owner's word**, in a job-free window, with the commit-time edits
  above. Deploy in `shadow` (shipped).
- **After the deploy:** guide 07-L on the first five review days, including the gap count, and the
  first "Exit rule test" line the Sunday after.
- **Before any switch to `evidence`:** FIX-015, PR-007's L2 and PR-005's RR-L1/T1.

## Fresh review: CHANGES REQUESTED (2026-10-23)

**Phase:** fresh-session review, a new conversation opened with "continue" (23 Oct, about
21:50–22:15 IST, session `stockagent-main-da`). PR-009 was implemented in session
`stockagent-main-af`; this conversation is not that one and did not read it. No peer session was
running at the start or before the bookkeeping (ListAgents).

**Verdict: CHANGES REQUESTED.** Two high findings are unresolved, both reproduced through the real
pipeline:

- **F1:** after a bonus or split, the evidence rule compares the new close with an invalidation
  level still in the old rupees, so it sells a stock that fell 2%.
- **F2:** one continuing disagreement is counted once per review day. The predeclared gate can
  then recommend the switch on 4 decisions, where the card asks for 15.

The gate is meant to be fixed before any shadow row exists, so F2 has to be settled before the
deploy. Every other part of the contract held:

- the stops are the same code under both rules;
- `shadow` is the default and its advice and trades equal `legacy`'s;
- events and analyses are taken as of the review day, for the right symbol;
- grading reads no price after the horizon, and an unmatured horizon is pending;
- one row per holding per day;
- the `shock_reforecast` finding is correct.

**Nothing was committed, pushed, deployed or configured.** No production state was read, no model
was called, no message was sent and no network call was made. The only tracked files this review
changed are STATE, HANDOFF and this receipt. The reviewer's scripts and outputs are in the ignored
`analysis_data/pr009_review/`.

### In one example (F1)

EEE is dived on 22 Sep at about ₹500, and its shelf idea sets the invalidation level at ₹455. The
autopilot buys 10 shares at ₹500 on 23 Sep. On 21 Oct a 1:1 bonus goes ex. The corp-action sync
runs before the advisor, as it must: the holding becomes 20 shares at ₹250. On 23 Oct EEE closes
at ₹245, which is ₹490 in the old shares, down 2%. Nothing about the company changed.

- **The stop rule** judges −2% against ₹250 and does nothing. That is correct.
- **The evidence rule** compares ₹245 with ₹455 and fires `case_broken`: "close 245.00 at or below
  the invalidation level 455.00 (shelf idea dived 2026-09-22, promoted)".
- **In `shadow`,** the shipped mode, the row is a disagreement, and it repeats every review day
  for as long as EEE trades below ₹455, which may be for as long as it is held.
- **In `evidence`,** the autopilot sells EEE (repro R1).

The level is a rupee price taken from the dive's close (`deep_dive.entry_levels`). Only active
ideas are re-dived (`shelf.py:248`, `redive_due`), so a bought idea keeps its old-rupee level
forever. The sync adjusts only the holding (`corp_actions.py:122-124`). In today's basis the level
is ₹227.50.

### In one example (F2)

BBB has been held 20 sessions, and its 22 Oct analysis is an actionable SELL. The price-path rule
holds it. The real pipeline runs in `shadow` on 26, 27, 28, 29 and 30 Oct and writes five rows:
legacy HOLD, evidence EXIT, `disagree: true` (repro R2). Under the evidence rule BBB would have
been sold on 26 Oct, so there is no BBB left to decide about on 27–30 Oct. Each of the five rows is
still graded and counted as a separate disagreement.

The gate, through the real weekly scorecard:

- **Input:** four stocks, each sold by the evidence rule and kept by the price-path rule for five
  consecutive days, the four episodes three weeks apart from June to August. Two of the stocks
  then trailed the Nifty and two beat it.
- **What the gate reads:** 20 matured disagreements over 67 days, right on 10 at both horizons,
  each stock 25%. It passes.
- **The next Sunday:** "Switch gate: passed two weeks running, so the evidence rule may replace
  the price-path rule. The owner decides."
- **What it actually was:** 4 decisions, 2 right, where the card asks for at least 15
  disagreements.

The count is also lopsided. In `shadow` the price-path rule's sale executes, so a "legacy sells,
evidence keeps" disagreement is written once. An "evidence sells, legacy keeps" disagreement
repeats for as long as the reason stands, which can be weeks with a standing SELL (D9: "whatever its
age"). So the tally weights the evidence rule's sales by how long they lasted. It is not a count
of decisions.

### Review input verified

- **Manifest:** [PR-009-manifest.json](PR-009-manifest.json), sha256 `5afb4aa1…df370c`, 17 files.
  `scripts/docs/kt_manifest.py verify` gives 0 mismatches at the start and at the end.
- **Diff:** sha256 `9ef8fdbae5415cfbf9e7be7b68b2a98d17a61ba3c9f65fe7c96fa9e6aa5c4e5d`, 116,287
  bytes, 16 paths, HEAD `d7c1411`.
  - It matches the implementation receipt.
  - It was recomputed independently by `analysis_data/pr009_review/rdigest.py` (same recipe, own
    code) at the start and at the end.
  - Outside the manifest, the working tree changes only STATE, HANDOFF, the receipt, the manifest
    and the owner's `docs/README.md` line.
- No review edit touched a reviewed path.

### Contract checked

| Contract | Result | How it was checked |
|---|---|---|
| Stops untouched (hard review Q1) | **Holds** | `advisor.py:514-535`. `stop_breach`, `shock_reforecast`, `crisis_regime_bearish` and the trailing stop are one code path under both rules. Only the line between them branches on `exit_rule`. The 4,000-case property test passes, and the minimum hold gates `case_broken` alone (`case_broken_fires`). |
| A stale or misattributed event (hard review Q2) | **Holds for events and analyses; fails for the invalidation price (F1)** | `exit_shadow.py:95-110`: symbol equality, an IST day after `trading_days_ago(on, 5)` and on or before `on`, undated never. `:113-127`: score history by ticker, IST day ≤ `on`, gate actionable or degraded. R3 runs the real `ScoreStore.save` and `EventStore.append_new`: the SELL and the event are read, and an abstained later BUY is skipped. The level's **price basis** is not checked (F1). |
| Matured rows only, exited stocks kept (hard review Q3) | **Holds; the counting unit fails (F2)** | `gate_look`: the population is the keys whose 30-session grade is not pending, and a missing grade is not right. Rows are never removed. But every day of a continuing disagreement is a key (F2). |
| `shadow` by default (hard review Q4) | **Holds** | `config.yaml` `advisor.exit_rule: shadow`. An unknown value reads as `shadow`, and `decide` refuses an unknown rule. In `pipeline.py:302-318` the acting call passes `exit_rule="legacy"` (evidence ignored), and the second call's record never reaches `rec`, the ledger, the narrator or the autopilot. |
| Grading uses only prices after the decision | **Holds** | `grade_disagreements`: a horizon after `as_of` is pending and reads nothing. The stock's close is read on the horizon's trading day only, through `pricing.close_on`, which does not walk back on a trading day. The Nifty is read on the decision and horizon days. The hand fixtures (−4 and +10 points) were re-derived by hand. |
| One row per holding per review day | **Holds** | `store.py:275-294`: the check and the append share one lock, and a stored row wins. Three pipeline runs give four rows. |
| `shock_reforecast` never fires (found on the way) | **Confirmed** | All three writers put a sentence in `reason` and the key in `trigger`: `daily_review.py:1474-1506`, `preopen_check.py:279-283`, `run_schedule.py:439-440`. `build_signals` reads `.reason` (`advisor.py:221`). The schema comment (`feedback.py:96`) says the opposite. That is a fact for FIX-015's card. |
| Tests derive their expectations independently | **Yes** | The ₹500 example, the event window (16 Oct in, 15 Oct out), ₹455.00 against ₹455.01, 9 against 10 sessions, the gate boundaries (14/15, 55/56 days, 5 of 16 against 5 of 17, 6/7 of 20) and the scorecard line are all hand values. The pipeline test runs the real pipeline, store and autopilot, and only prices, signals and the stores are stubbed. No hidden transport: the hermetic boundary is on, and the evidence readers are stubbed or pointed at temporary stores. |
| Documentation | **Describes the implemented behaviour** | KT sections 3, 4, 6, 7, 11 and 12; CODEBASE; guide 07-K, 07-L and 09-H; the PI README and the FIX-015 card. `check_kt_docs` gives exactly one error, the expected one: the KT links `exit_shadow.py`, absent at the header's `ffa012b`. The commit-time bump clears it. The PDF's source digest matches the Markdown. After the rework, section 6 and 09-H must state the counting unit (F2) and the level's price basis (F1). |

**Rulings on the implementer's decisions:**

- D1, D2 ("at or below", the entry rule's meaning), D5, D7, D10 and D11 are **upheld**.
- **D3 is upheld for which idea supplies the level.** The level's price basis is F1.
- **D4 (the span of the counted disagreements) is upheld.** Its "about 14–15 weeks" estimate must
  be re-stated once F2 changes what is counted.
- **D6 is upheld as the definition of a disagreeing row.** F2 adds which rows count.
- **D8 is upheld.** Its weekly re-fetch grows with every repeated row, which is one more reason
  for F2.
- **D9 is upheld.** With F2 fixed, a standing SELL counts once.

### Findings

| ID | Severity | Location | Trigger | Observed | Expected | Disposition |
|---|---|---|---|---|---|---|
| **F1** | **High** (confirmed: R1, through the real corp-action sync, pipeline, autopilot and store) | `core/portfolio/exit_shadow.py:130-147` (`invalidation_for`) and `core/portfolio/advisor.py:456-457`; the basis is changed at `core/portfolio/corp_actions.py:122-124` | A bonus or split goes ex after the shelf idea's dive, for a held stock with a stored level | `case_broken` fires on ₹245 ≤ ₹455 for a stock down 2% (₹490 in old shares). In `shadow` it is a false disagreement, written again every day. In `evidence` the autopilot sells. | The close and the level are in the same price basis. The ₹455 level is ₹227.50 after a 1:1 bonus, so nothing fires. This is the corp-action invariant (sync "before any advisor rule"), and REVIEW.md lists price identity as needing an invariant test. | **Required in rework 1** |
| **F2** | **High** (confirmed: R2, through the real pipeline and the real weekly scorecard) | `core/portfolio/exit_shadow.py:246-343` (`grade_disagreements`, `gate_look`); the row has no holding identity (`schemas/portfolio.py` `ExitShadowRow`) | A disagreement that lasts more than one review day: a standing SELL, an event inside its 5-session window, F1, or a price-path EXIT the autopilot does not execute (a portfolio without autopilot) | Each day is a separate disagreement in the count, the tally, the 30% share and the span. 4 decisions pass the gate and recommend the switch two weeks running. | The card: "at least **15** matured disagreements", "graded … after the decision date". A decision is the day the two rules part ways on a holding. After it they no longer hold the same position, so later rows are not new decisions. | **Required in rework 1** |
| **L1** | Low (code inspection) | `core/portfolio/pipeline.py:272` with `exit_shadow.py:275-276` | The review's close is a carried-forward bar (`quote.fresh_for(session)` false) | The row keeps that close, with no bar date. Grading pairs it with the review day's Nifty close, so the two returns start on different days. | The row records `price_bar_date` (the signals already have it). A stale start is graded from its own day, or is not graded. | Optional in rework 1; otherwise a KT section 6 limit |
| **L2** | Low (code inspection; affects `evidence` mode only) | `core/portfolio/narrator.py:29`; the reasons are not in `AdviceRecord` | A `case_broken` sale under `evidence` | The alert and narrative say "a material negative company event, an actionable SELL research verdict, or the price at its invalidation level", without saying which one. The specific reason is only in `exit_shadow.jsonl`. | The owner's sale reason names the event, the verdict or the level ("plain reasons", product track) | Optional in rework 1. Otherwise a follow-up for [PR-007](../stories/PR-007.md) (explanations), owner the PR-007 implementer, before any switch to `evidence` |

Checked, and **not** findings:

- The corp-action effect on **grading** is the auditor's own convention: the stored close against
  a later `auto_adjust` close (`core/audit/outcomes.py:127`). It is shared, not new.
- **A failed evidence read** leaves the evidence rule unable to fire, the stops still protect, and
  the row names the gap (`no evidence assembled`). That is what the rule would do in production, so
  grading it is faithful.
- **`ScoreStore()`** in the reader creates its table if missing. In production the database exists.

### Rework 1: what must be true at the re-review

1. **F1, required.**
   - The invalidation test compares the review day's close with a level in the **same price
     basis**. For example, divide the level by the ratio of every bonus or split that went ex after
     the dive and on or before the review day.
   - A holding's `applied_actions` hold only actions after its buy. A split between the dive and the
     buy needs the symbol's own actions, or the test is skipped with a named gap. It must never
     fire on a basis it cannot establish. The rule is the implementer's call; record it as a
     decision.
   - Pin R1 as an invariant test through the real sync: no `case_broken`, the level read as
     ₹227.50.
2. **F2, required.**
   - **The rule to implement:** each holding (symbol and buy date) contributes at most one graded
     disagreement, on the first review day the two rules part ways. Later rows of the same holding
     stay in the file, marked or shown as continuations, and are not graded or counted in the
     total, the tally, the 30% share or the span.
   - **Holding identity:** the row needs one, for example `buy_date`. No production row exists
     yet, so the schema can change now.
   - **Tests to pin:**
     - R2's five-day run is one disagreement;
     - R2's four-episode gate reads "not yet" (4 of the 15);
     - a stock bought again later can contribute a second decision;
     - a holding whose first disagreement was the price-path rule's sale is not counted again.
   - **Docs to update:**
     - KT section 6 (grading, the gate table) and the scorecard line say "decisions", not
       "holding-days";
     - D4's first-pass estimate is re-stated;
     - guide 09-H counts decisions, and a case shows a repeated day not counting.
3. **L1, L2: optional.**
4. **Evidence for the re-review:**
   - hand-worked expected values;
   - mutants for both new rules (the basis adjustment, the first-day rule);
   - the story file, the changed test files and the full suite;
   - `check_broad_except`, `check_kt_docs`, and the PDF if the KT changes;
   - a regenerated manifest, a rework diff against this review's input `9ef8fdba`, and the
     cumulative diff against `d7c1411`.

### Commands and environment

Windows 11, the `.stockai` venv (Python 3.13), with the hermetic boundary on (SA-005). The
reviewer's repro folder imports the same hooks through its own `conftest.py`.

| Command (repository root) | Result |
|---|---|
| `.stockai/Scripts/python.exe analysis_data/pr009_review/rdigest.py` | `9ef8fdba…` 116,287 B, 16 paths; HEAD `d7c1411`; outside the manifest only bookkeeping and the owner's README line (start and end) |
| `.stockai/Scripts/python.exe scripts/docs/kt_manifest.py verify docs/planning/PI-2026-09/evidence/PR-009-manifest.json` | 17 files, mismatches `[]` (start and end) |
| `pytest -q -p no:cacheprovider` on the story file and 11 related files (advisor, advisor switch, portfolio pipeline, autopilot pipeline, SA-003 portfolio gate, PR-002 scorecard, PR-004 idea supply, SA-050 sizing, SA-051 Nifty, Atlas import boundary, scheduler portfolio hook) | **883 passed** in 106.6 s |
| `pytest -q -p no:cacheprovider analysis_data/pr009_review/test_review_repro.py` | **4 passed**: R1, R2 (pipeline), R2 (gate) and R3 (positive control). R1 and R2 assert today's defective result, and a `CONTRACT` comment gives the expected one. |
| `scripts/ci/check_broad_except.py` | OK (151 grandfathered) |
| `scripts/docs/check_kt_docs.py` | exactly the one expected error (`exit_shadow.py` absent at `ffa012b`); the PDF digest matches the Markdown |

**Not exercised:**

- the full suite: the implementation's 5,698-passed run covers these exact bytes, and the rework
  reruns it;
- the implementer's 36 mutants (not re-run);
- production: nothing was read, and no live corp-action or score-history data was examined;
- the `evidence` mode's narration (L2 is code inspection).

### Acceptance checklist

| Criterion | Verdict |
|---|---|
| The ₹500 example: legacy EXIT, evidence HOLD, both recorded with reasons | Met (the path ends at ₹470; ₹478 is inside the 1% flat band, as the KT says) |
| The gate fixture: passing at 30 but failing at 10 recommends nothing, nor the reverse | Met |
| Each `case_broken` path on its own fixture and not one unit short; only stops within the minimum hold | Met |
| Property: stops fire exactly as under the legacy rule | Met |
| In `shadow`, decisions and transactions byte-identical to `legacy` | Met (and re-read in the pipeline) |
| Grading uses only prices after the decision; unmatured is pending | Met |
| One shadow row per holding per review date | Met |
| The gate counts 15 matured disagreements (card, switch gate) | **Not met in substance** (F2: 4 decisions pass) |
| Hard review: no stale or misattributed input fires `case_broken` | Events and analyses yes; **the invalidation price no** (F1) |
| Living docs and human test cases | Describe the implemented behaviour; they need F1's basis rule and F2's counting unit after the rework |

### Decision and state

**CHANGES REQUESTED.**

- **STATE:** PR-009 `changes_requested`, `active_task` null, `next_task` PR-009 (**rework 1**, in
  a new conversation). Then a fresh re-review in another new conversation.
- **`production_verification`** stays `not_started`.
- **Do not push PR-009** until a re-review accepts it and the owner gives the word.
- **FIX-015's card stands as written.** Its own implementation can note that the `reason`/`trigger`
  comment in `feedback.py:96` is inverted.
