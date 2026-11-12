# FIX-029 — implementation receipt

**Story:** [FIX-029](../stories/FIX-029.md): every door to a buy reads the same facts: the day's
regime, the sale and the verdict.

**Phase:** implementation, 11 Nov 2026, about 16:30–18:15 IST. Session `stockagent-main-3b`
[950de1], a new conversation opened with "continue". `origin/main` was at `581eb90`, the same as
HEAD: nothing had arrived from the other device. Six peer sessions were idle. This phase includes a
same-conversation self-review, which is not the fresh review.

**Baseline:** HEAD `581eb90`. The working tree held only the uncommitted push record of FIX-028's
review docs in STATE and HANDOFF (bookkeeping, outside the manifest).

**Status after this phase:** `review_required`. Nothing is committed, pushed, deployed or configured.
No production state was read (the card's measurement is prepared, not run), no network was used, no
LLM was called and no message was sent. No test reaches the network (`tests/hermetic.py`).

## In one example

Y breaches its stop on Wednesday 4 Nov's run (reviewing Tuesday). The shelf holds X (pharma, 0.80,
dived Sat 31 Oct) and Z (fmcg, 0.75, same dive). Tuesday's run sold X.

- **Before:** the advisor's candidates still held X, so the SWITCH named X and bought it back a day
  after selling it, paying costs on both sides, on the analysis the sale had overruled.
- **Now:** the list reads this portfolio's ledger: X is "sold on 2026-11-03, after its deep dive of
  2026-10-31; waits for a new deep dive", so the SWITCH takes Z, the next-best idea (the real
  pipeline, `test_m2_the_pipeline_passes_the_ledger_so_a_real_switch_skips_the_sold_stock`). A
  SWITCH made by hand into X is refused at the buy leg with the same words, and the money stays in
  cash.

## What changed

- **M1, the day's regime (`core/portfolio/advisor.py` `build_signals`):** a holding whose own review
  wrote no entry for the day (an older one, or none at all) reads `label_recorded_for(day)`: a
  recorded label replaces the older one, and clears the older entry's "unavailable" reason; none
  recorded keeps the older label and holds ADD with the reason, as before.
- **M3, the analysis before the close (`services/data/stores/score_store.py`,
  `core/discovery/candidates.py`):** `ScoreStore.get_latest_before(ticker, before)` answers the
  newest analysis run strictly before `before` (an aware time is compared in UTC, as `run_at` is
  stored). `watchlist_idea` takes `analysis_before(symbol, at)` in place of `latest_analysis(symbol)`
  and asks for the one before the review session's 15:30 IST close; a record from after the close is
  still refused (FIX-024's check stays as a second line).
- **M2, M4, one sale rule (`core/discovery/shelf.py`):** `ledger_sales(transactions)` gives a
  portfolio's exits (a SELL that left no shares), each on the day it was decided (`sale_day`): `last`
  by anyone, `by_autopilot` by the autopilot. `resale_wait(idea, sale, autopilot_exit)`: an exit on
  or after the idea's deep dive (a watchlist idea: its analysis's IST day) waits for a new one; from
  the watchlist, after an autopilot exit, only an analysis on or after `saturday_after(exit)` counts
  (the owner's Option A). `Sales.wait(idea)` applies it. `autopilot_sales()` now reads its exits
  through `ledger_sales`.
- **L1, the verdict (`shelf.py`):** `verdict_wait(idea)`: an idea whose verdict is not BUY or STRONG
  BUY is not bought; one with no verdict stored waits for its re-dive. `apply_redives` drops a
  re-dive that is no longer a BUY, with the reason; `apply_deep_dives` does not shelve a new dive that
  is not a BUY (`not_buy`, F29-D7); `redive_due` counts an idea with no verdict as unverified.
- **The list (`candidates.buy_candidates`):** takes `sales` (this portfolio's `Sales`); an unheld
  shelf idea that `Sales.wait` or `verdict_wait` refuses is not offered, and a watchlist candidate
  that `Sales.wait` refuses is not offered. A held stock is left to each door's own "already held"
  check. `core/portfolio/pipeline.py` passes `ledger_sales(store.load_transactions(limit=2000))`.
- **The doors (`core/portfolio/autopilot.py`):** `execute_advice` builds the run's `Sales` once, from
  the ledger and this run's own exits. A SWITCH's buy leg refuses a destination that `Sales.wait` or
  `verdict_wait` refuses, noting it on the SELL. Deployment's `_deploy_check` reads the same two
  (outcomes `sold` and the new `verdict`); `_last_sales` is gone. `deployment.OUTCOME_WORDS`:
  `sold` "sold since the idea was decided", `verdict` "not rated a BUY by the analysis".

## Decisions (F29-D1 to D10)

| # | Decision | Why |
|---|---|---|
| D1 | M1 covers a holding with no entries at all, not only an older one. | It read a made-up NORMAL. ADD cannot fire there in production (no 7-day accuracy), but the crisis exit and the narrative now read the day's recorded label. Two fixtures that force accuracy with no entries (FIX-027's `_signals`, SA-050's 11 Oct test) now state the day's regime as established. |
| D2 | With no label recorded for the day, the older label stays; the market state's kept label is not read. | The card's "None still holds the ADD, as now". The kept label can be a later day's on a re-run of a past session (look-ahead). Limit below. |
| D3 | An older BUY counts for its close when a newer analysis says SELL; the SELL counts from the next close. | Issue time: the trade is booked at that close, and refusing it on what was learnt after the price would favour the record with hindsight. FIX-031's I-1 decided the same. So the page can show a newer verdict than the one a buy was made on. |
| D4 | The rule is one function each (`resale_wait`, `verdict_wait`), applied by the list and read again by both doors against the ledger. | Advice made by hand, or from a list built with no ledger, bypasses the list (the reviewer's RV5, RV6). The doors also see this run's own exits. |
| D5 | An exit is a SELL that left no shares, by anyone; a hand sale blocks as deployment did. A held stock is left to the doors. | Deployment's old reader counted every SELL, a trim too; for a stock not held the latest SELL is its exit, so nothing changes there. Leaving held stocks in the list keeps the switch rows' `already_held`. |
| D6 | "The Saturday after" is the first Saturday strictly after the exit's decided day, and binds the autopilot's exits only. | A dive on the sale's own day counts as before it (`sold_since_dive`), so a Saturday sale waits for the next Saturday. After a hand sale the user decided; any later analysis counts. |
| D7 | `apply_deep_dives` does not shelve a new dive that is not a BUY (`not_buy`). | Beyond the card's list. Otherwise a NEUTRAL idea takes a shelf slot, a sector place and paper grading while nothing may buy it, and its re-dive drops it. For the review to rule on. |
| D8 | An idea with no verdict stored is not offered and is re-dived first. | The card. Ideas have stored their verdict since the shelf began (9 Jul, `fa2e77c`), so none is expected in production; not read. |
| D9 | The deployment outcome words change: `sold`, and a new `verdict`. | The record names why. |
| D10 | `get_latest_before` compares the stored text. | `save` writes naive UTC ISO. A stamp with another offset would sort wrongly; the list still refuses any record after the close by its own time, so a wrong sort can hide an earlier analysis but never admit a later one. |

## The card's hard-review questions

1. **Does taking a sold stock off the list change the exit shadow's `switch_lands` or the switch
   evaluation rows?** The rows, yes: a sold idea is no longer a candidate, so it has no row (it had
   "taken" or a decline), and the next-best idea may be taken (`test_m2_rv5b…`: rows `[("Z",
   "taken")]`). The shadow's legacy verdict then names that idea or a plain EXIT, and `switch_lands`
   asks about the destination named; its own logic is unchanged. A held stock stays in the list, so
   its `already_held` row is unchanged (`test_m2_a_held_stock_is_left…`). Code inspection and tests.
2. **With ideas of no stored verdict on the production shelf, can L1's rule empty the list on its
   first day?** Only if no active idea has a BUY verdict. A verdict has been stored with every idea
   since the shelf began; in the local verdict log (1,541 analyses, 17 Jul to 27 Sep, before FIX-013)
   all 1,364 at or above 0.55 were BUYs. Ideas with none are re-dived first. The production shelf is
   not read (the probe's `L1_active_by_verdict`).
3. **Can M1's recorded label reach any reader that assumed the holding's own entry?**
   `AdvisorSignals.regime_label` has two readers: `decide` (ADD and the crisis exit) and the narrator
   (the narrative and its cache key). Both now read the day's label, as intended. The feedback log and
   the advice record are unchanged (`AdviceRecord` carries no label). Code inspection (grep).
4. **With M3 fixed, can a watchlist idea carry a band or thesis from an analysis older than the one
   the owner sees on the page? Does an older BUY still count when a newer analysis says SELL?** Yes to
   both, for the close before the newer analysis (D3; `test_m3_an_older_buy_counts…`: Tuesday's close
   carries Monday's case; Wednesday's close reads Tuesday's SELL and offers nothing).

## Found on the way

- FIX-028's story fixture stamped its sale with the real clock (`_now_iso` not pinned), so the sale
  read as decided on 11 Nov, after its 18 Jul re-dive, once the SWITCH leg read the ledger. The
  fixture now pins the run after the sale's session (Tue 14 Jul, 17:00 IST).
- Shelf-idea fixtures in 11 test files had no verdict (the schema's default `""`); each now shelves a
  BUY, as a real dive does (`analysis_data/fix029/fixture_verdicts*.py`, and SA-048's costs test by
  hand after the first full suite).
- **Limit, not changed:** on a dark day, a holding with no entry of its own keeps its older label for
  the crisis exit, while the market state's kept label may be severer (a crisis entered after the
  holding's last entry). ADD is held either way. Reading the kept label needs a guard against a state
  written for a later day (D2).

## Measure first (the card) — prepared, not run

Not run: no production read in this phase. Probe
[`analysis_data/fix029/doors_probe.py`](../../../../analysis_data/fix029/doors_probe.py) (ignored
folder; read-only, counts only, no symbols, user ids or values; the score database opened
`immutable=1`; dry-run locally on the stale `data/`, which changed nothing). It prints the card's four
counts (M3 old against new offers over the last 10 weekdays, M4's population, M2's SWITCH re-buys,
L1's verdicts) and how many active ideas the new rule would leave out today. Owner's command, from
Git Bash in the repository root:

```
railway ssh "cd /app && echo $(gzip -9c analysis_data/fix029/doors_probe.py | base64 -w0) | base64 -d | python -c 'import sys,zlib;exec(zlib.decompress(sys.stdin.buffer.read(),31))'"
```

## Rollout

**Deploying changes production with the deployment switch off**, because a SWITCH, ADD, discovery
and the daily review are live:

- a SWITCH never buys a stock sold since its idea was decided, nor an idea not rated BUY; it takes
  the next-best idea or, with none, stays a plain EXIT;
- a holding with no review entry of its own reads the day's recorded label (an ADD on a recorded
  RISK_OFF or MACRO_CRISIS day stops; one held by an older crisis label goes ahead);
- Saturday's discovery shelves only BUY dives, and a re-dive that is no longer a BUY drops its idea;
- **a watchlist stock in the daily review becomes a SWITCH destination** where it almost never was
  (M3 failed safe): from the deploy, a SWITCH may buy the user's own watchlist BUYs.

First look, read-only: the probe before the deploy; after it, the run log's "not offered" reasons
(`sold …`, `its deep dive rates it …`) and the digests' deployment outcomes. **No benefit is shown
here.** These are contracts; how often each case happens is the probe's.

## Tests and commands

Environment: `.stockai/Scripts/python.exe` (Python 3.13), Windows, from the repository root.

- **Story file** [`tests/unit/test_every_door_fix029.py`](../../../../tests/unit/test_every_door_fix029.py),
  27 tests, figures worked by hand in docstrings:
  - M1: 104 shapes (an own entry of the day, an older one or none, each label; the day recorded with
    each label, unrecorded or recorded unavailable) against the card's invariants, ADD and the crisis
    exit; today's calm label frees an older crisis label; an older dark day cleared by today's
    record; RV3 through the real daily review.
  - M3: the real score store: RV12 (offered on every run, each reading the day before's 16:35
    analysis); an older BUY counts for its close and a later SELL from the next; the bound strictly
    before the close.
  - The sale: `saturday_after` against a day count; the rule against an oracle over 21 × 22 × 22 × 2
    shapes (decided day, autopilot exit, hand exit, shelf or watchlist); `ledger_sales` (the stamp's
    day, a trim, a hand sale, the later exit).
  - M2: RV5 (a hand-made SWITCH refused at the leg, ₹1,00,000 in cash); RV5b (real list, decide and
    executor: Z, 70 shares); the real pipeline with and without the sale in the ledger; a hand sale;
    the first run that may use the new dive; a held stock left to the doors.
  - M4: RV4 (the list and the deployment door); an analysis on or after the Saturday; a hand sale.
  - L1: RV6 (deployment, both verdicts, the counted reason); the list and a SWITCH leg; RV7; a new
    NEUTRAL dive not shelved; no verdict re-dived first.
- **The reviewer's FIX-025 cases with their strict xfails removed** (the card's acceptance), in a copy
  built by `analysis_data/fix029/make_rv_copy.py`: **76 passed, 1 xfailed** (RV9, routed to PR-007,
  still strict xfail). RV3, RV4, RV5, RV5b, RV6, RV7 and RV12 pass. Adaptations, all listed in the
  script: the reader's new name and bound (A1); RV12's fake answers the analysis of the day before the
  session, which is what the bounded reader returns (A2); RV5b gives `decide` the list built with the
  ledger, the input every door now reads (A3).
- **Reworked older tests:** the reader's rename in 4 files (`retarget_tests.py`); BUY verdicts in 11
  files' fixtures; FIX-028's sale stamp; PR-004's "no analysis" reason now names the close; FIX-025's
  D4 test reads `shelf.ledger_sales(...).last` for the removed `_last_sales`; FIX-027's `_signals` and
  SA-050's 11 Oct test, which write no feedback entry, state the day's regime as established (D1).
- **Neighbouring tests**, run while reworking the fixtures: the 6 files of FIX-023 to FIX-028 and SA-049, then the 36 files that name the discovery, the advisor, the autopilot, the pipeline or the score store (`tests/unit` and `tests/contract`), each to 0 failed after the fixture changes above. The full suite below is the evidence.
- **Mutants** (`analysis_data/fix029/mutants.py`, in place, each file restored and its sha256 checked;
  the story file and 9 neighbouring tests): **30 of 30 caught.** First pass 29 of 30 (`mutants.txt`): the regime (no entries, the label not applied, only a severer one, an own entry overruled), the bound (at the close, an aware time as text, the newest of all), the Saturday (a Saturday itself, Sunday, on the Saturday), the exits (a trim, a hand sale as the autopilot's, the dive's own day), the list (no sales, held stocks, a watchlist candidate, the pipeline passing none), the doors (the SWITCH leg, deployment's sale, this run's own exits), the verdict (NEUTRAL, none stored, a new dive, a re-dive, the re-dive queue, the list, deployment). **M03 (an older dark day's reason kept once today is recorded) survived:** no test had an older entry that was itself unavailable. `test_m1_an_older_dark_day_does_not_hold_a_day_another_review_recorded` added; re-run, caught (`mutants2.txt`).
- **Full suite**, run 1 (17:19–17:41 IST): 6,306 passed / 12 skipped / 1 xfailed / **1 failed**, pytest rc 1, git status unchanged (`analysis_data/fix029/run1/`). The failure: SA-048's `test_a_switch_spends_the_sale_net_of_its_costs_and_pays_the_buy_costs`, one more shelf-idea fixture with no verdict, which the SWITCH leg now refuses. Its fixture now shelves a BUY. In the same step the watchlist loop's guard was made explicit (`if idea is None or why`), no change under `watchlist_idea`'s contract. The touched files then: 239 passed, 1 xfailed. Run 2, on the final bytes: **6,307 passed / 12 skipped / 1 xfailed / 0 failed**, pytest exit code 0, 21m49s (17:46:12–18:08:01 IST), `git status --porcelain` identical before and after (`analysis_data/fix029/full_suite.txt`, `status_*.txt`, `full_suite_rc.txt`). 6,280 at HEAD plus the 27 new tests.
- `check_broad_except`: OK (148 grandfathered). `check_kt_docs`: `errors: []`, header `linked_sources_changed_since_revision: []`.

## Documentation

- `docs/TECHNICAL_DESIGN.md` section 6: Advisor precedence (the day's recorded label, with the
  example), Cash deployment "Which ideas" (the newest analysis before the close, the one sale rule,
  Option A, the week bound for either list, the verdict), the "Planned: FIX-029" markers gone; section
  8: re-dives (no verdict, a re-dive that is no longer a BUY, `not_buy`), the buy candidates (verdict;
  `get_latest_before`; Option A).
- `docs/AUTOPILOT_GUIDE.md`: the signal table's regime row, the buy candidates, a new "After a sale"
  block, deployment's candidate step and outcomes, the test table's new row.
- `docs/TEAM_TESTING_GUIDE.md`: cases 07-G (e)-(i) and 07-O (a SWITCH into a sold stock), their status
  lines, HT-07's Related PI.
- `docs/PRODUCT_MAP.md` (buy candidates row), `docs/RL_DESIGN.md` (27.1: the advisor reads
  `label_recorded_for` with no entry of its own).
- Cards: PR-013's routed line (which doors the week bound covers); FIX-031 item 4 (built here).
- `docs/StockAgent-Three-Loops.pdf` regenerated: 69 pages, source `21f4fa4ace1ee9b2e8242b748f05257e33262fd044fd07c6e534773bea63c0f3`, 633,825 bytes.

**Commit-time edits still to make:** KT header (Code inspected, edition); KT
section 1 (the inspected code adds FIX-029, not yet deployed); KT section 12 FIX-029 Done; guide 07-G
and 07-O status lines; the PDF.

## Review input

- Manifest: [FIX-029-manifest.json](FIX-029-manifest.json), SHA-256 `55c547584e492137254ea031ef0e545e23f06232bea0e89fc28e3fbfe628d539`, 31 files (`scripts/docs/kt_manifest.py verify`: 0 mismatches).
- Diff against HEAD `581eb90`, the PDF excluded: SHA-256 `3bc38e520461ceb443c1d0b9cde123c5386efc4e959fb061f6e9154eb0bbe5aa`, 154,159 bytes, 30 paths, via `analysis_data/fix029/digest.py` (a temporary index, so the new test file is in the diff and the real index is untouched). Base tree `50535bd8`, end tree `acbbd174080745a716d9c955d6f6712c49e2d679` (taken before this receipt's last figures and the STATE/HANDOFF splice).
- Outside the manifest: STATE, HANDOFF, this receipt and the manifest itself (bookkeeping), and the uncommitted 11 Nov push record in STATE and HANDOFF.
- On another device, recompute from the recipe: `git diff 581eb90 -- <the manifest's paths but the PDF>` over the working tree, sorted paths, `core.autocrlf=false`.

## What a fresh review should press on

1. D4: is there a buy path that reads neither the list nor the doors' check? By grep, the autopilot
   opens a position only in the SWITCH leg and deployment (`_buy_into_holding`); a top-up is of a
   stock already held, and `POST /portfolio/holdings` is the user's own trade. IPO ideas reach the list
   through the shelf.
2. D3 against the owner's view: a buy booked on Monday's BUY while the page shows Tuesday's SELL.
3. D7: shelving only BUY dives, beyond the card.
4. The rollout's last bullet: watchlist BUYs become SWITCH destinations with the switch off.

Next: a fresh review in a new conversation (REVIEW.md).
