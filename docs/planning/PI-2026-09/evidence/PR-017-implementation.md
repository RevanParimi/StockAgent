# PR-017 — implementation receipt

**Story:** [PR-017](../stories/PR-017.md): grade every deep dive at the conviction it was issued
with, beside the screen's other candidates. Owner decision of 15 Nov 2026 (edge roadmap, stage 2).
Profit-path step: **measure** (the product's core claim, "our deep dive finds stocks that beat the
Nifty, and the higher its conviction the better", gets a record that cannot be picked apart).

**Lane: decision path.** Reason: the card's own lane; it defines how ideas are graded (AGENTS.md
step 4). It changes no buy, sell or size. **Status after this phase: `review_required`.** The next
fresh conversation performs the hard review from `REVIEW.md`; this phase's self-review does not
count as it.

## Phase

- **Implementation** (autopilot `1120-1454-p6`, code-server, Fri 20 Nov 2026 from about 14:54
  IST, outside a push window). Baseline **`7293fb4`** (`main`, 11 commits ahead of `origin/main`
  `03debc1`, push pending). The code is on **`story/PR-017`**: **`5151455`** (the change),
  **`2ce862f`** (one test strengthened after a planted bug got past it) and **`1b01f80`** (two
  silent `except Exception` handlers narrowed, refused by `test_broad_except_guard` in the full
  suite on `2ce862f`). **Revision for review: `1b01f80`.** Only a fresh review's acceptance
  merges it into `main`.
- Production: nothing read, pushed, deployed, run or sent.

## What the card said exists, checked against the code [code inspection]

1. **Re-dives overwrite the conviction.** Confirmed: `ShelfStore.apply_redives` sets
   `idea.conviction = dive.conviction` (and the verdict and band) in place; `grade_shelf_lane`
   reads `idea["conviction"]` when a horizon matures.
2. **Only shelf ideas are graded, and failed ideas leave the record.** Confirmed: the dive memo
   `dives.json` (`record_dives`) is keyed by symbol (a re-dive overwrites the stock's entry) and
   pruned after `DISCOVERY_REDIVE_AFTER_DAYS` (30); it keeps no graph, sector or close. A dive
   that was not shelved is gone after a month. A dropped idea stays in `shelf.json` with status
   `dropped`, so the shelf lane still grades it, at its last conviction. So the card's step 1
   needed `dives.jsonl`.
3. **Screen candidates are never graded.** Confirmed: `screens/<date>_screen.json` is written
   (`screen._persist`) and read only by `load_latest_screen`. Its `screen_date` is the EOD day
   read (Friday for a Saturday run), not the run's day.
4. **The entry is before the dive.** Confirmed: `close_at_add = dive.close`, the latest close in
   the window the dive read.

## What was built [code]

1. **`dives.jsonl`** (`core/discovery/dive_record.py`, `DiveRecord`), append-only in the discovery
   data folder. `run_discovery_cycle` appends one `"row": "dive"` per answered dive (reference
   `dive:<dive day>|<symbol>`, conviction, verdict, graph, sector key, close, composite, gate,
   band, invalidation, Yahoo labels, `kind` new or redive) and one `"row": "run"` (run day, the
   screen file's `screen_date`, the symbols dived), **before** `record_dives` rewrites the memo
   and before the shelf writes the run's events. `dive_rows` returns the first row per reference
   (an at-dive row wins over a seeded one).
   **The seed** (`seed_rows`), on the first write only: the memo's entries (complete, verdict
   included), the shelf events' `added` (`conviction=0.62`) and `redived` (`conviction 0.62 ->
   0.80`) convictions with the IST day of the event, the verdict only where the memo has the
   same stock and day, and the graph and sector of the stock's record in `shelf.json` (else "").
   Run rows only for days the memo still covered (on or after its newest day less 30 days); each
   names the newest screen file within 7 days before it. `python -m core.discovery.dive_record`
   previews the seed without writing. **The record is complete from the first discovery run
   after deploy** (then the seed's covered days, about the 30 days before it).
2. **The bare judge** (`core/discovery/bare_judge.py`): `run_deep_dives` keeps each dive's data
   bundle (`evidence`, from the orchestrator's `_last_bundle`, set in `_run_unified` and reset at
   each run); `run_discovery_cycle` then asks about each **new** dive (re-dives skipped, dive
   order) one JSON-mode call: the analysis's model (`LLM_MODEL_REASONING`), the bundle's sections
   in the analysis's order less `dossier`, under `UNIFIED_BUNDLE_MAX_CHARS` (18,000), plus the
   code, Yahoo sector and industry, the day and the close; the instruction in `SYSTEM` (BUY or
   SKIP to beat the Nifty 50 over three months, a conviction 0 to 1, one sentence). At most
   `discovery.bare_judge_max_per_week` (20) calls with a dive day in the last 7 days, a failed or
   unreadable one counted. `bare_judgements.jsonl`, append-only; decision "" when the answer is
   not BUY/SKIP with a conviction in [0, 1]. `record_llm_call("bare_judge", ...)`.
3. **Three lanes** (`core/audit/idea_lanes.py`, `grade_idea_lanes`, called from `grade_due` after
   the five old lanes, default user only, like the IPO lane):
   - `dive` from `dives.jsonl`; `bare` from `bare_judgements.jsonl` (graph and close from the
     dive); `screen` from every screen file: reference `screen:<run day>|<symbol>`, triggers
     `not_dived` / `dived` (against run rows that read that screen) / `dived_unknown`. The run
     day is the earliest covering run's, else the file's new `run_date` (`ScreenResult.run_date`,
     written by `run_screen` from now on), else the IST day of the file's modification time
     (trigger `run_day:file_time`), and never before the screen's own date.
   - **Entry:** the open of `next_trading_day(call day)` from the EOD panel
     (`executable.panel_fn`, NSE's raw bhavcopy, 550 sessions kept). The dive's close is kept in
     `reference_close`. No bar on that session: `no_entry_price`, no row.
   - **Horizons:** `audit.idea_horizons_td` = 10, 30, 60, 90, 180, `trading_days_after(call
     day, h)`. `audit.horizons_td` stays 10, 30, 60 for the other lanes.
   - **Exit:** the panel's close of the horizon session, put into the entry open's basis by
     `exit_shadow.horizon_in_basis(quote, record, entry_on, entry_on)` (a bonus or split ex after
     the entry session and on or before the horizon bar multiplies it; one ex on the entry day is
     already in the open) and refused on `registry_break`. A missing file within the panel's 7
     retry days, or a TEMPORARY basis gap: `pending`; otherwise `no_exit_price`.
   - **The Nifty:** `BenchmarkSeries.close_on` of the session before the entry open, and of the
     horizon session. Failing: `skipped_unpriceable`, like the other lanes (it feeds the job's
     partial-output alert); `pending` and the no-price counts do not.
   - At most `audit.idea_max_symbol_reads` (200) NSE corporate-action lists read a night
     (`Prices`, shared by the three lanes, dives first); a horizon past it waits (`pending`).
   - Rows: `AuditOutcome` with lane `dive`/`screen`/`bare`, `correct=None`, the conviction and
     verdict as issued, and five new optional fields (`graph`, `reference_close`, `entry_on`,
     `basis`, `composite`). `AuditOutcomeStore.append` leaves those five out of a row where they
     hold their default, so every other lane's line keeps its exact keys and order.
4. **The report** (`core/audit/ideas.py`, pure): per horizon, n, mean and median excess, share
   above zero and "too few to judge" under 30 for BUY dives (BUY or STRONG BUY at a conviction of
   at least `discovery.min_conviction`), rejected dives (every other recorded verdict; abstained
   only counted), screen only (`not_dived`), the bare model's BUYs, and BUY dives by graph; the
   counts of seeded dives without a verdict, abstained dives, BUY dives of unknown graph and
   screen candidates "dived unknown"; first row per (reference, horizon).
   `report.build_report` keeps the idea lanes out of every advice figure (as it does IPO rows)
   and adds `"ideas"` with `coverage`: per horizon, the recorded dives that reached it and how
   many have no grade. `render_section` prints one sentence per horizon.
5. **The scorecard line** "Every deep dive" (`results.py`: `row["idea_record"]` at 30 sessions,
   `as_of` the week's end; `scorecard_lines`).
6. **Backfill:** the dive seed above; the screen lane grades every stored screen file; the bare
   lane cannot be backfilled.

## Decisions taken in this phase

- **The new horizons are a key of their own** (`audit.idea_horizons_td`), not added to
  `audit.horizons_td`: widening that would add 90 and 180-session rows to the advice, alert,
  shelf and switch lanes, which the card does not ask for. Every reader of idea rows takes the
  idea key; the advice report's three-horizon readers are untouched.
- **The Nifty leg starts at the close before the entry open**, because `BenchmarkSeries` holds
  closes only and Yahoo's index opens are not checked here. The excess therefore includes minus
  one overnight Nifty move. Named in the code, the KT and here.
- **The backfill is automatic, on the first write after deploy**, not a command waiting for the
  owner: it only creates a new derived file from files the run already holds, and the memo loses
  a week each Saturday, so waiting costs data. It runs inside the Saturday job, before the memo
  is rewritten. The reviewer should weigh this (below).
- **The bare judge asks about new dives only**, not re-dives, within 20 a week: the budget is 45
  dives a week, and a re-dive's question ("still a BUY?") differs from the bare model's.
- **The bare judge gets the dive's own bundle less the dossier**: that is the same dated evidence
  (news, policy, macro, fundamentals, technicals, commodities, flows, peers); the dossier is the
  product's memory of the stock, part of the method.
- **Same model as the analysis**, so the comparison is of the method.
- **"BUY dives" means BUY or STRONG BUY at the shelf's floor or above**; a BUY under 0.55 is a
  rejected dive (the card: "NEUTRAL, SELL or under 0.55").
- **The scorecard line shows 30 sessions**; the report shows all five.
- **Old screen files take their run day from the file's time**, so they are graded at all; the
  first actionable open of a screen written on a weekday catch-up is then the next day's.
- **A nightly cap of 200 corporate-action reads** (network calls), dives first.
- **B-30** (BACKLOG): a horizon that can never be priced is tried again every night.

## Acceptance criteria

| Criterion | Where | Result |
|---|---|---|
| Conviction on a `dive` row equals that dive's own, whatever re-dives followed (the card's example) | `test_a_dive_keeps_its_own_conviction_whatever_redives_followed`, `test_the_seed_keeps_the_conviction_each_shelf_event_was_written_with`, `test_a_reference_written_twice_is_graded_once_as_first_written` | 0.62 on every horizon of the first dive, 0.80 on the re-dive; seeded the same |
| Entry bar dated after the dive; a dive with no price skipped and counted | `test_the_entry_is_the_open_of_the_first_session_after_the_dive`, `test_a_dive_with_no_entry_price_is_skipped_and_counted`, `test_a_dive_without_a_price_is_counted_in_the_report` | Monday's open for a Saturday dive, Tuesday's for a Monday dive; every row `entry_on > issued_on`; counted in the lane summary and the report's coverage |
| Idempotent per reference and horizon; old `shelf` rows byte-for-byte unchanged | `test_grading_again_writes_nothing`, `test_old_shelf_rows_are_byte_for_byte_unchanged` | Second run: file bytes identical. An old shelf line keeps its bytes; a new shelf row has the 22 old keys in order |
| Every figure carries its n; under 30 "too few to judge" | `test_the_groups_and_their_figures`, `test_thirty_ideas_are_judged_and_twenty_nine_are_too_few`, `test_the_line_names_every_n_and_too_few` | 29 → too few, 30 → judged |
| Corporate actions as FIX-016 | `test_a_bonus_after_the_entry_is_put_in_the_entrys_basis`, `test_a_bonus_on_the_entry_day_is_already_in_the_open`, `test_a_demerger_leaves_the_horizon_ungraded_and_counted` | ₹55 after a 1:1 bonus = ₹110 (+10%); demerger: no row, counted |
| Horizons 10/30/60/90/180; readers of three horizons checked | `test_five_horizons_counted_from_the_dive_day`, `test_the_shipped_horizons_and_caps`, `test_idea_rows_never_move_the_advice_report` | Five rows on the hand-counted days; advice report figures unchanged by idea rows |
| The report: four groups and the graph split | `test_the_groups_and_their_figures`, `test_idea_rows_never_move_the_advice_report` | As worked by hand |
| Bare lane: 20 a week, re-dives not asked, no dossier | `test_the_bare_judge_sees_the_evidence_not_the_method`, `test_at_most_twenty_calls_in_any_seven_days`, `test_an_answer_that_is_not_buy_or_skip_is_kept_and_not_graded`, `test_a_failed_call_counts_against_the_cap_and_never_raises`, `test_no_evidence_no_call` | As stated |
| End to end through `run_discovery_cycle` | `test_the_run_records_every_dive_before_the_memo_and_asks_the_bare_judge` | Seed read the memo before the run rewrote it; run row names screen 2026-07-03; two bare calls, no dossier |
| Living documents: KT section 7, the testing guide | KT §3 (records), §7 ("Every deep dive graded", report-families row, scorecard row), §8 (the dive record and the bare judge); guide 09-K; CODEBASE (tree, module and config rows) | `check_kt_docs.py`: errors [] |

## Tests and checks

- New: `tests/unit/test_idea_lanes_pr017.py`, 29 tests, expected figures worked by hand (calendar
  pinned without holidays). Changed: the lane-set assertions of `test_audit_lanes.py` and
  `test_audit_ipo_lane.py` (now eight lanes).
- **Planted bugs: 12 of 12 caught** at `2ce862f` and again at `1b01f80` (`5151455` caught 11; the twelfth, the record written after
  `record_dives` prunes the memo, passed the end-to-end test, so `2ce862f` adds a memo entry 31
  days old to it). Each run alone against the PR-017 file: the first row per reference turned
  into the last; the entry at the call day's own session; the idea fields written on every row;
  the advice report reading idea rows; the basis counted from the call day; the dossier left in;
  the weekly cap counting 8 days; "too few" at 30; the Nifty from the entry session; re-dives
  asked; the record written after the memo; a BUY under the floor counted as a BUY dive. The
  entry mutant was re-run with its import in place: it fails the entry test alone.
- Focused: `tests/unit/test_idea_lanes_pr017.py tests/unit/audit`: 195 passed. Every test file
  touching the discovery run, the orchestrator, the report or the scorecard (40 files): 1,293
  passed before the new file existed.
- Full suite in a detached worktree: see "Full suite" below.
- `scripts/docs/check_kt_docs.py`: errors [].
- Environment: code-server, Python 3.13.5 (`.stockai`), hermetic suite (no `.env`, no network).

## Review input

- Baseline `7293fb4`, revision `1b01f807f15594ef09d1fd7ecb5dcc90fb637646` (`story/PR-017`,
  three commits: `5151455`, `2ce862f`, `1b01f80`).
- `git diff 7293fb4 1b01f80 | sha256sum` = `c735410fa8eed626ba45214665595dbc3603eb24e88add072c7550113a7b864e`
  (21 files, +2,061 −21).
- Manifest [PR-017-manifest.json](PR-017-manifest.json) (21 files, git blob and SHA-256 per
  file, written from a worktree at `1b01f80`): review-input SHA-256
  `95e5ccc861aa33fdcae4d0be67b6d145aef9c40746e0f9c0d220480d91712df5`;
  `kt_manifest.py verify … --rev 1b01f80`: mismatches [].

## Limits and what the reviewer should look at

- **The Nifty overnight** (decision above): about one session's index move per row, noise of
  about half a point either way, not a bias the size of the horizons' excess.
- **The seed runs in production on the first Saturday after deploy**, writing a new file from
  the memo, the shelf events and the shelf. It reads; it changes none of them. A reviewer who
  thinks it needs the owner's word should say so; the alternative is a command at the owner's word, and
  each Saturday's wait loses the memo's oldest week.
- **Seeded dives before the memo window carry no verdict** (shelf adds before about 21 Oct): in
  no group, counted. PR-038's read found verdicts for some of them in `score_history`; joining it
  was left out (a read of the analyses table by stock and day, matched on the score), and could be
  a follow-up if the counts are large.
- **Screens before the first run row** are graded "dived unknown" and are in no group but their
  own count. Screen files are overwritten when a later run reads the same EOD day; the candidates
  are then the later run's.
- **The bare judge adds up to 20 calls to the Saturday job** (about 4,500 input tokens each, the
  same model as the dives), and the time they take, before the shelf is updated.
- **A horizon that can never be priced is retried nightly** (B-30).
- Adversarial checks suggested: a re-dive on the same day as a first dive; a bonus ex on the
  horizon day itself; a dive on a Friday after the close; a screen file with a run row whose
  `screen_date` matches two files; the cap reached mid-lane; idea rows in the store while
  `evaluate_breaches` runs.

## Production watch (proposed, from the first Saturday after the deploy)

`PR-017-W1`: after the first discovery run: `dives.jsonl` exists with `backfill` rows and the
run's `at_dive` rows and one run row naming the Friday screen; `bare_judgements.jsonl` holds at
most 20 rows, and the run's summary has `bare_judge`; the LLM log has `bare_judge` calls. After
that night's 23:45 audit: the log's lanes include `dive`, `screen` and `bare`, with their counts;
`/audit/report` has `ideas` with five horizons and `coverage`; the seed's preview numbers
(`python -m core.discovery.dive_record` before the run) match what was written.

## Full suite

- `2ce862f`: 1 failed, 6,945 passed, 5 skipped, 1 xfailed (7m34s). The failure was
  `test_broad_except_guard.py::test_real_tree_matches_its_baseline`: two new silent broad
  handlers (`idea_lanes.idea_horizons`, `ideas._floor`). Fixed in `1b01f80`.
- **`1b01f80`: 6,946 passed, 5 skipped, 1 xfailed, 0 failed (7m01s)**, detached worktree, `.stockai` Python 3.13.5, hermetic.
