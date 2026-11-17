# Backlog of small findings

Owner's rule of 14 Nov 2026 (AGENTS.md): a finding that is low, latent or pre-existing, and changes
no buy, sell, size or grade today, is written here as one entry with its trigger. It becomes a card
only when its trigger is seen in production or the owner promotes it. Medium or higher findings on
the decision path still become cards.

Each entry: what, where it was found, and the trigger that promotes it.

## Open

| # | Finding | Found in | Promote when |
|---|---|---|---|
| B-1 | The migration shims in `core/pipeline/` and `core/schemas/` are still in place: 141 import sites, and one contract test patches through the shim path | CLEAN-001 item 6a, skipped ([receipt](evidence/CLEAN-001.md)) | A change needs both import paths edited, or the owner asks for the migration |
| B-2 | `docs/superpowers/plans`, the two scaling documents and `docs/archive/` were not moved under one archive folder: `config/milestones.yaml`, which the production watchdog reads, names a plan in that set | CLEAN-001 item 6b, skipped ([receipt](evidence/CLEAN-001.md)) | The IPO lane's milestone is retired or its plan path changes |
| B-3 | The entry band's top is 2% above the close the deep dive read and stays for up to 30 days, so an idea that rises is refused while one that drifts down is bought | Profit-path review F3, code inspection, not measured | `PR-014-D1`'s rule: more than a third of offered BUY ideas refused "above entry band" |
| B-4 | `ARCHITECTURE.md`, `RL_DESIGN.md`, `PRODUCT_MAP.md` and `AGENTIC_DESIGN.md` still label stories that are off the plan (SA-012 to SA-024, SA-043) or paused (SA-026, SA-045 to SA-047) as "Planned" | PR-014's docs commit, 14 Nov: KT sections 11 and 12 and AUTOPILOT_GUIDE section 16 were updated, these four were not | The owner's decision at `PR-014-R2` on whether either group returns, or a reader acting on one of those pointers |
| B-5 | FIX-032 stops a home-page removal from leaving a `watchlist`-origin managed entry enabled for a stock nobody holds or watches, but it does not clean the ones left before it: such an entry stays in every 16:30 review (the scheduled job ignores the weekly cadence) until the cap evicts it. It costs LLM spend, and discovery skips a managed stock's deep dive while the entry is enabled; no buy, sell, size or grade reads it directly | FIX-032 implementation, 16 Nov (code inspection; count not measured) | `FIX-032-P1`'s probe reads `watchlist_enabled_nobody_holds_or_watches` above 0 |
| B-6 | `POST /portfolio/watchlist` promotes the stock before it saves the watch (`portfolio_api.py:272`, then `:277`). If another user's removal of the same stock lands between the two (the API's delete, or the home page since FIX-032), its demotion sees nobody watching and disables the entry: the adder then watches a stock with no review. Example: w adds BACK while v removes BACK; BACK's entry ends disabled. Fix: save the watch first, as `ShelfStore.promote` does. Fixture: `analysis_data/fix032_review/test_rv_fix032.py::test_rv5_…` (strict xfail). Needs two users acting on one stock within milliseconds | FIX-032 fresh review R1, 16 Nov (local reproduction; frequency not measured) | A stock on a user's own watchlist found with a disabled managed entry (PR-033's sweep or PR-034's report can count it), or a third active account |
| B-8 | Small leftovers, none read by a buy, sell, size or grade. **Code nothing in production imports:** `services/scheduler/run_schedule.py` (624 lines, a hand-run command line), `core/intelligence/rl/stores/store_migration.py` (407, SA-009's one-time move), `services/data/fetchers/ipo_gmp.py` (248, named only in comments), `src/backend/shared/prompts/feedback_agent.py` (227, a second copy that not even a test imports), `core/intelligence/rl/eval/run_eval.py` (136), `core/ipo/report.py` (110), `core/audit/cli.py` (58), `core/config/prompts/shared/orchestrator.py` (57) and `signal_aggregator.py` (3). Three one-off benchmarks that the image still copies: `scripts/aud098_thesis_tier_bench.py`, `scripts/model_bench.py`, `scripts/reasoning_bench.py` (728 lines together). Five re-export files of 2 or 3 lines under `src/backend/shared/` (`clients/tavily_fetcher.py`, `data/fetchers/fundamentals.py`, `macro.py`, `news.py`, `data/stores/score_store.py`), and `core/config/settings/base.py`, one more shim of B-1's kind. **Stale settings:** `.gitignore` names `cpp/build/`, `typescript/node_modules/` and `frontend/node_modules/`, none of which exists at the root; `.dockerignore` names `src/frontend/web/dist`. (`MagicMock/` stays: it guards against a test that writes such a folder.) **Documents:** a pasted `railway ssh` command is line 3 of `docs/README.md`; `docs/archive/` holds a 622 KB PDF that git history also holds (`check_kt_docs.py` pins its hash; see B-2); `docs/RL_DESIGN.md` (81 KB) describes the learner that is off the plan (see B-4). **Interface:** `UI_SPEC.md` (49 KB) sits in the served folder, so the catch-all route in `services/api/server.py` hands it to anyone; `demo-fixtures.js` loads for everyone and is used only with `?demo=1` | Owner's repository review, 17 Nov 2026: an import graph over the 796 tracked Python files, text search, and code inspection. Not checked on production. Whether the owner still runs any of the command lines by hand was not asked | Fold in what touches the same files when [CLEAN-004](stories/CLEAN-004.md), [CLEAN-005](stories/CLEAN-005.md) or [CLEAN-003](stories/CLEAN-003.md) runs; the two interface items are in [PR-040](stories/PR-040.md); or the owner asks |
| B-9 | `scripts/setup_dev.sh --check` says READY when Playwright's Chromium is on disk but cannot start: it checks the file, not a launch, and as a non-root user it installs the browser without its system libraries. On the code-server on 17 Nov the two real-browser tests then failed (`libglib-2.0.so.0` missing) and passed after `sudo npx playwright install-deps chromium`. Fix: check by launching, and install the libraries with `sudo -n` where it works. No buy, sell, size or grade reads it | CLEAN-002's full suite, 17 Nov (local reproduction on the code-server) | A third device or a cloud session hits it, or the setup script is next edited |
| B-10 | The shock exit (`shock_reforecast`, FIX-015) does not reach across a month: the envelope is per month and the daily review re-forecasts only the live cycle. The review of a month's second-to-last session runs on its last session at 16:45, so its two closes are the next month's first two sessions, which read the new month's envelope with no history; the review of the last session runs on the 1st and re-forecasts nothing; a pre-open shock on the last session counts once, not twice. Example: the review of Mon 29 Jun runs Tue 30 Jun 16:45; Wed 1 and Thu 2 Jul hold, though July's path falls too. The stops and the crisis exit still act, and the new month's forecast is drawn fresh at 09:00 on the 1st. Fixture: `analysis_data/fix015/test_review_cases.py::test_month_end_shock_never_reaches_a_decision` | FIX-015 fresh review R1, 18 Nov 2026 (local reproduction; frequency not measured) | `FIX-015-W1` shows an `external_shock` re-forecast of a held stock in a month's last two sessions that did not sell and the stock then fell through its stop, or the owner asks |

## Parked with their cards

Findings already routed into a card stay in that card's "Routed input" section. When the card is
paused or removed, they wait with it:

- [SA-021](stories/SA-021.md) (removed 14 Nov): FIX-031's review finding R2, the calibration report
  pairs a graded session with a confidence revised after its close.
- [SA-026](stories/SA-026.md) (paused 14 Nov): FIX-028's low finding that the owner's dashboard
  routes take no lock. (Its second, the API's delete routes looking only at the user's own
  portfolio, is taken by FIX-032.)

## Closed

- **B-11** (18 Nov 2026, found and fixed the same night): two re-forecast tests took today's date from
  the machine's clock (`date.today()`) while `generate_forecast._review_session_close` reads IST
  (`now_ist()`). The code-server's clock is UTC (its `TZ=IST` is not a zone glibc knows), so from
  00:00 to 05:30 IST the tests asked for yesterday's close, reached the network and failed:
  `test_decision_gate_learning_sa003.py::test_a_reforecast_row_names_the_run_that_issued_it` and
  `test_learning_mode_sa039.py::test_reforecast_uses_sector_defaults_in_observe` (full suite at
  00:12 IST: 2 failed / 6,789 passed). That window is the push window, and the autopilot's push
  runs the suite in it. Both now take `now_ist().date()`; they pass with the zone unset, UTC and
  Asia/Kolkata. Found in FIX-015's fresh review; no product code changed.

- **B-7** (17 Nov 2026): the owner asked for the backup email to be removed completely, because
  the nightly archive (19.5 MB on 16 Nov) was filling the mailbox. [CLEAN-007](stories/CLEAN-007.md)
  removed the send, so the failed 16 Nov mail has nothing left to repair. What B-7 warned of
  stands and the owner accepted it: with SA-007's bucket not set up, no copy of the paper book
  exists outside the Railway volume.
