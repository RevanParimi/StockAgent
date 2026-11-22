# FIX-033 — implementation receipt

**Story:** [FIX-033](../stories/FIX-033.md): a deep dive's idea is the company it was asked
about. Origin: [the B-32 read](B-32-read-2026-11-21.md) (21 Nov 2026). Profit-path step:
**invest** (what is bought) and **sell** (the holding bought on another company's case).

**Lane: decision path.** Reason: it changes what is bought (every buy door) and what is sold
(a new EXIT trigger) (AGENTS.md step 4). **Status after this phase: `review_required`.** The next
fresh conversation performs the hard review from `REVIEW.md`; this phase's self-review does not
count as it.

## Phase

- **Implementation** (autopilot `1123-0029-p1`, code-server, Mon 23 Nov 2026 from about 00:30
  IST, inside the push window). Baseline **`2cf3eee`** (`main` = `origin/main`, pushed by the
  runner at 00:29). The code is on **`story/FIX-033`**: **`dcd17f5`** (the change) and
  **`a3a2116`** (self-review: the paper lane, the monthly forecast and the daily review pass the
  exact symbol too; the legacy check reads only tickers and theses, through a store method FIX-010's
  guard names, after the full suite on `dcd17f5` caught the first version). **Revision for review: `a3a2116`.** Only a fresh review's
  acceptance merges it into `main`.
- Production: nothing read, pushed, deployed, run or sent. The records commit on `main` is
  documentation only.

## What the card said, checked against the code [code inspection]

1. **The dive re-resolves its symbol.** Confirmed: `run_deep_dives` called
   `get_orchestrator(route).analyse(cand.symbol, ...)`; `_resolve_ticker` returned a managed or
   tracked symbol as itself and sent anything else to `TICKER_RESOLUTION_PROMPT` (model, then a
   Serper search when the answer did not verify). The dive had already checked the symbol is a
   listed company (`instrument_kind`), so the model call could only change the company.
2. **The result is filed under the symbol asked for.** Confirmed: `DeepDiveResult(symbol=
   cand.symbol, ...)` with no comparison against `report.ticker`.
3. **No buy door could tell.** Confirmed: `ShelfIdea` kept no trace of the report's ticker;
   `buy_candidates`, the SWITCH leg (`_execute_buys`) and `_deploy_check` read `resale_wait`,
   `verdict_wait`, `close_before_dive`, the gate, surveillance and the band, none the identity of
   the analysis. A BUY row kept the thesis (`reason`) and nothing naming the analysis.
4. **The same resolver sat behind the paper lane.** Found in self-review: `paper_lane` calls
   `generate_forecast(idea.symbol, paper=True)`, whose `_run_orchestrator_analysis` called
   `analyse(ticker)`; a shelf symbol nobody manages went to the model the same way. It buys
   nothing, but its envelope and score row would be another company's.

## What was built [code]

1. **The exact symbol** (`src/backend/shared/pipeline/base_orchestrator.py`):
   `analyse(..., exact_symbol=True)` calls `_resolve_ticker(..., exact=True)`. A managed or tracked
   symbol is itself, as before; otherwise the symbol is itself once `_listed` finds it in the
   cached instrument listing (`bhavcopy.load_listing`), or, with no listing cached, once Yahoo
   prices it (`_verify_ticker`); else `UnlistedSymbol` (`no_analysis.py`, a `ValueError`) stops
   the run before any data or model. No model, no web search. `analyse_async` and a plain
   `analyse` (the Analyze box, the stream, the chat) keep the resolver. Callers passing it: the
   deep dive; `generate_forecast._run_orchestrator_analysis` (the monthly forecast, a
   re-forecast, the paper lane); `daily_review._run_todays_agent_scores`.
2. **The dive keeps only an analysis of the stock** (`core/discovery/deep_dive.py`): after the
   call, `plain_symbol(report.ticker)` (upper case, no `NSE:` or `.NS`/`.BO`) must equal the
   candidate; otherwise, or when the report names no symbol, no result (so no idea and no memo
   entry), a warning "DEEPA: the analysis is of DEEPAKNTR, not DEEPA; not shelved", and
   `tally["other_company"]` = {asked: analysed or "?"} (the call counts against the budget).
   `DeepDiveResult.analysed_symbol` carries the report's symbol. The weekly run reports
   `hygiene.other_company`.
3. **Every door** (`core/discovery/shelf.py`): `other_company(symbol, analysed)` and
   `analysis_of_other(idea)`: "" when the analysed symbol is unknown ("") or the idea's own, else
   "the analysis is of DEEPAKNTR, not DEEPA". Read by: `apply_deep_dives` (skipped,
   `other_company` in the summary), `apply_redives` (drops the idea, "re-dive 2026-11-28: …";
   a re-dive of the stock itself stamps a legacy idea), `buy_candidates` (shelf ideas, held or
   not; watchlist ideas, which take the symbol of their score-history row), the SWITCH leg
   (skipped, proceeds kept, said on the SELL) and `_deploy_check` (outcome `other_company`,
   counted "whose analysis is of another company"). `ShelfIdea.analysed_symbol`.
4. **The ledger and the exit** (`core/portfolio/autopilot.py`, `advisor.py`, `pipeline.py`,
   `narrator.py`, `results.py`): each BUY from an idea (SWITCH leg, deployment) writes
   `TransactionRecord.analysed_symbol`. `analysed_elsewhere(ledger)` names each holding a BUY of
   whose open position (since its last sale to zero) names another symbol; the pipeline sets
   `AdvisorSignals.bought_on_other`, and `decide` appends `bought_on_other_analysis` first among
   the EXIT triggers, under either exit rule, never blocked (only SA-008's identity hold comes
   first). `AdviceRecord.bought_on_other` carries "bought on DEEPAKNTR's analysis, not DEEPA's";
   `narrate` tells that sale in fixed words, never by the model ("EXIT — bought on DEEPAKNTR's
   analysis, not DEEPA's Your position: …"), so the SELL row's `reason` and the trades screen
   name both symbols. The scorecard's exit reasons name it first ("another company's analysis").
5. **Ideas shelved before FIX-033** (`shelf.py`, `pipeline.py`, `core/discovery/__init__.py`):
   `history_identity(idea, rows)`: among the score history's analyses of the dive's IST day and
   the next (`score_rows_on`, bounds `_thesis_day_bounds`, read by the new
   `ScoreStore.theses_between`: ticker and `substr(investment_thesis, 1, 800)` only, no report
   JSON), the one symbol whose first 800 thesis characters are the idea's; none or two: "".
   FIX-010's guard of list-shaped score reads names this one caller (a server-side check no
   viewer sees). The daily review reads the shelf through
   `with_history_identity` (copies, nothing written; an unread history fails open per idea), so
   DEEPA's misfiled idea is refused from the first review after the deploy. The weekly run calls
   `ShelfStore.verify_analyses()` before the re-dives (its own try): own symbol stamped; another
   drops the idea ("its deep dive of 2026-11-14 analysed DEEPAKNTR, not DEEPA", an event) and
   removes its dive memo entry, so a later screen can dive DEEPA as itself; unknown stays
   unverified until its next re-dive (`hygiene.analyses`).

## Decisions taken in this phase

- **An unknown analysed symbol ("") is not refused.** Refusing every idea shelved before FIX-033
  would stop the book's buying until re-dives (the B-32 read: 20.8% invested for lack of ideas);
  probe 5 found DEEPA the only misfiled idea of 20. The score-history read covers the legacy ideas
  at once instead.
- **Legacy ideas are read from the score history, not re-dived.** Exact (the dive's thesis is the
  first 800 characters of the row's), free (no model call), and immediate in the daily review.
  Re-diving all legacy ideas would have taken about 20 of Saturday's 45 calls from new companies.
  `redive_due` is unchanged: an idea the history cannot tell is stamped at its normal re-dive.
- **The daily review reads, never writes, the shelf;** the Saturday run writes. No weekday writer
  of `shelf.json` is added.
- **Fail open on an unread score history** (logged): before this, a history error inside the
  shelf read would have emptied the day's candidate list; it now leaves the ideas as loaded.
- **The exit fires under both rules and before the stop**; SA-008's identity hold still comes
  first (its close is not the holding's price basis; an operator reconciles first).
- **The narration is fixed words** for this sale, so the symbols cannot be paraphrased away.
- **A BUY written before FIX-033 is not judged** (no `analysed_symbol`). The B-32 read found
  DEEPA the only one; it was sold on 21 Nov.
- **The resolver seam keeps its old call shape for free text** (`_resolve_ticker(input,
  run_id=…)`), so about 50 existing patches of it still fit; `exact=True` is passed only when
  asked.
- **The paper lane, the monthly forecast and the daily review pass the exact symbol too** (the
  card's item 1: "never asks a model to guess"); a managed symbol was already itself (FIX-002),
  so only the paper lane's behaviour changes.
- **A narrow store read for the legacy check, allowlisted in FIX-010's guard** rather than
  `get_by_date_range` (which reads every report's JSON) or a filter by viewer (there is no
  viewer). The guard now also watches `theses_between`, so a later caller must be filtered or
  named.

## Acceptance criteria

| Criterion | Where | Result |
|---|---|---|
| A dive whose orchestrator returns another ticker shelves nothing, with the reason (DEEPA → DEEPAKNTR) | `test_a_dive_about_another_company_shelves_nothing`, `test_a_report_that_names_no_symbol_is_refused_too`, `test_the_exchange_suffix_is_not_another_company` | No result, no memo entry, `other_company` {"DEEPA": "DEEPAKNTR"}, 2 calls counted, the log line; GOOD shelved stamped GOOD |
| A listed symbol outside the managed list makes no resolver call (transport blocked) | `test_an_exact_listed_symbol_makes_no_model_call`, `test_an_unlisted_exact_symbol_stops_without_a_model`, `test_with_no_listing_cached_yahoo_decides`, `test_analyse_passes_exact_only_when_asked`; control `test_the_defect_free_text_deepa_resolves_to_deepak_nitrite` | 0 model calls, web search refused; the control reproduces DEEPA → DEEPAKNTR with 1 call |
| Every buy door refuses an idea whose analysis is of another symbol (a planted shelf row) | shelf `test_the_shelf_refuses_…`, `test_a_re_dive_about_another_company_drops_the_idea`; list `test_the_candidate_list_leaves_it_out_held_or_not`, `test_the_list_offers_it_exactly_when_…` (8 shapes); watchlist `test_the_watchlist_door_reads_the_rows_own_symbol`; SWITCH `test_a_switch_leg_refuses_it_and_keeps_the_proceeds`; deployment `test_deployment_refuses_it_and_says_why` | Each refuses with "the analysis is of DEEPAKNTR, not DEEPA"; each control (own analysis) buys, its row naming the analysis |
| A holding bought on another symbol's analysis is EXITed at the next review with that reason | `test_analysed_elsewhere_follows_the_open_position`, `…against_an_oracle` (500 ledgers), `test_the_advisor_exits_it_whatever_the_stop_or_forecast_says` (both rules), `test_the_reason_is_told_in_fixed_words_never_by_the_model`, `test_the_next_review_sells_it_with_the_reason_in_the_ledger` (real pipeline) | Control ADD → EXIT; the SELL of 100 at ₹1,050 reads "EXIT — bought on DEEPAKNTR's analysis, not DEEPA's"; GOOD held |
| The misfiled idea now on the shelf | `test_history_identity_…`, `test_the_day_bounds_…`, `test_the_score_history_is_read_between_those_bounds` (real store), `test_reading_the_shelf_stamps_copies_…`, `test_an_unread_history_…`, `test_the_weekly_run_drops_deepa_and_forgets_its_dive`, `test_the_first_review_after_the_deploy_refuses_the_legacy_idea` (real pipeline, with a no-history control) | DEEPA refused from the first review (GOOD 66 shares bought; control buys both); Saturday drops DEEPA, forgets its memo entry, stamps GOOD, leaves ODD unverified |
| Living documents: KT sections 4 and 8; a testing-guide case | KT §4 (step 1, "Ticker resolution"), §6 (the cascade, the buy doors), §7 (the exit-reason order), §8 (steps 3, 4, 5, 6); ARCHITECTURE (identity); CODEBASE (four module rows); guide 06-R, 07-V | `check_kt_docs.py`: errors [] |

## Tests and checks

- New: `tests/unit/test_misfiled_analysis_fix033.py`, 40 tests, expected values worked by hand
  in each docstring.
- Changed fakes (the new contract): the deep-dive analysts in `test_discovery_deep_dive.py`,
  `test_idea_supply_pr004.py`, `test_idea_supply_pr037.py`, `test_sector_naming_fix026.py`,
  `test_no_analysis_clean005.py`, `shared/test_decision_gate_sa003.py` accept `exact_symbol` and
  return a report naming its ticker; two watchlist fakes in `test_idea_supply_pr004.py` answered
  W's row for every symbol and now answer each symbol's own; PR-037's tally gains
  `other_company`; the forecast fakes in `intelligence/rl/test_reforecast.py` and
  `test_learning_mode_sa039.py` accept `exact_symbol`, and `test_no_analysis_clean005.py`'s
  resolver fakes accept `exact`. Guard: `test_score_history_fix010.py` watches
  `theses_between` and names its one caller, `shelf.score_rows_on`.
- **Planted bugs: 21 of 21 caught** (scratch script, each mutant alone against the FIX-033 file):
  the dive keeps a misfiled result; the orchestrator resolves an exact symbol by model; the list,
  the watchlist door, the SWITCH leg, deployment, the shelf add and the re-dive each unchecked;
  the advisor not exiting; a sale not clearing; an ambiguous history accepted; the memo not
  forgotten; the pipeline ignoring the ledger fact or skipping the history read; the model
  narrating the sale; an unknown symbol counted as another; the deployment BUY row unstamped;
  the suffix not normalised; the monthly forecast (and paper lane) or the daily review asking the model; the store cutting 799 characters.
- Focused: the discovery, deep-dive, idea-supply, sector-naming, no-analysis and decision-gate
  files (257 passed); every portfolio, autopilot, advisor, deployment, exit, scorecard and
  discovery file (1,877 passed, then 2 narrator-cache fixes for duck-typed records); on
  `a3a2116`, `tests/unit/intelligence`, `tests/contract`, the no-analysis, paper-runner,
  score-history, resolver and FIX-033 files (1,434 passed, 5 skipped).
- `scripts/ci/check_broad_except.py`: OK. `scripts/docs/check_kt_docs.py`: errors [].
- Environment: code-server, Python 3.13.5 (`.stockai`), hermetic suite (no `.env`, no network).

## Full suite

- `dcd17f5`: 2 failed, 6,958 passed, 5 skipped, 1 xfailed (8m37s). Both were FIX-010's guards
  in `test_score_history_fix010.py`: the legacy check's unfiltered list read of the score
  history (`get_by_date_range`) and the guard's text match for a writer (`shelf.py` named the
  store and calls `.save(`). Fixed in `a3a2116` (the narrow, named read above).
- **`a3a2116`: 6,961 passed, 5 skipped, 1 xfailed, 0 failed (10m51s)**, the checkout at that
  revision (only the uncommitted records differ), `.stockai` Python 3.13.5, hermetic.

## Review input

- Baseline `2cf3eee`, revision `a3a2116eb10f92d5d07635e00e06383e6cf7c451` (`story/FIX-033`, two
  commits: `dcd17f5`, `a3a2116`).
- `git diff 2cf3eee a3a2116 | sha256sum` = `8f92bf60787e18c4600ba45df46c4a8d3ca9ef451ff37476ff79b96d0bb8f2d8`
  (31 files, +1,147 −79).
- Manifest [FIX-033-manifest.json](FIX-033-manifest.json) (31 files, git blob and SHA-256 per
  file): review-input SHA-256 `36ce5e97acb0b888a0556e6e02ced3cccac6c247169c1ea88e00555c80df5c57`;
  `kt_manifest.py verify … --rev a3a2116`: mismatches [].

## Limits and what the reviewer should look at

- **The legacy read matches on the thesis's first 800 characters** within the dive's IST day and
  the next. A thesis edited after the dive, or a score row pruned (90 rows per ticker), leaves an
  idea unverified (bought as before), never misnamed. Two symbols with the same thesis: "".
- **The daily review reads the score history once per dive day of each unverified legacy idea,
  for each portfolio**: a few queries a review until Saturday stamps them.
- **`UnlistedSymbol` in the daily review or the monthly forecast**: a managed symbol never reaches
  it (it is tracked); a shelf idea's symbol was a listed company when dived. A delisting between
  then and a paper review makes that paper review fail, logged, instead of analysing whatever a
  model names.
- **Adversarial checks suggested:** a dive of a symbol whose report ticker is lower case or
  suffixed; a legacy idea re-dived and then read by `verify_analyses` the same Saturday; a holding
  topped up (ADD) after a misfiled buy; a SWITCH out of a misfiled holding into a good idea; the
  identity hold on a misfiled holding; a watchlist row with no ticker key.

## Production watch (proposed, from the first review after the deploy)

`FIX-033-W1`: at the first 16:30 review after the deploy, the digest's buying record shows no
idea bought whose analysis is of another company (and, if any legacy idea's history shows one,
"whose analysis is of another company" in its reasons); every new BUY row carries
`analysed_symbol`. At the first Saturday run after it: the run's summary has `hygiene.analyses`
(DEEPA, if still active, dropped with "its deep dive of 2026-11-14 analysed DEEPAKNTR, not
DEEPA"; most others verified) and `hygiene.other_company` (expected empty); the dive log has no
"ticker_resolution" model call for a dive.
