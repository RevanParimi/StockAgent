# CLEAN-004 receipt — remove three things no decision reads

Autopilot phase `1119-2203-p5` on the code-server, a `continue` from about 22:03 IST on Thu
19 Nov 2026, outside a push window. `main` was `f756d67`, 24 commits ahead of `origin/main`
(`3f26ae5`); the tree was clean. PR-015 waits for a push window, PR-038 and PR-033 are blocked
on the owner's word, so CLEAN-004 was the first ready story.

**Lane: light.** Reason: no buy, sell, size or grade reads any of the three (the proof is under
each item); the one setting changed, `rl.control_lane_enabled`, feeds only the monthly learning
scorecard. **Accepted without a fresh-session review** (AGENTS.md step 4). Profit-path step:
none directly; it runs because the owner decided it on 15 Nov ("removing the live prompting
anyways including UI"; "remove if it's no use"). It saves about 425 model calls a month (9.7%)
and code that let a laptop's tests run numbers production never computes.

Nothing in production was read or changed. Nothing was pushed.

## Commits

| Item | Commit | Files | Lines |
|---|---|---|---|
| 1 The Prompt Lab (live prompt editing) | `4a1df8d` | 20 | +31 / −1,181 |
| 2a The control lane switched off | `631731d` | 4 | +11 / −19 |
| 2b The control lane deleted | `e81af2f` | 24 | +56 / −640 |
| 3 The C++ indicator copy | `d0d413e` | 11 | +75 / −470 |
| B-8 leftovers, with these records | the records commit | 6 code and document files | +1 / −277 |

The last commit's base is `d0d413e`. Its six non-record files (`.dockerignore`, `.gitignore`,
`docs/PRODUCT_MAP.md`, `docs/README.md`, `scripts/aud098_thesis_tier_bench.py`,
`scripts/ci/broad_except_baseline.txt`) have the diff digest `997322a58d1a4595` (sha256 of
`git diff --binary d0d413e -- <those six>`, first 16). The records in it are STATE, HANDOFF,
HANDOFF-archive, BACKLOG and this receipt.

## Item 1 — the Prompt Lab

**Proof of non-use** (`git grep` over the tree, archives and dated plans aside):

- **Routes:** `services/api/routes/prompts.py`, six routes under `/ui/prompts`, mounted only by
  `services/api/server.py` (one import, one `include_router`). The only callers were the screen
  `prompt-lab.jsx` and the scheduler job below.
- **Job:** `prompt_daily_deploy` (`scheduler.py`, `_prompt_deploy_job`), which imported
  `run_scheduled_deploy` from the routes file. Neither `config/milestones.yaml` nor the
  watchdog's registry names it, so no registry edit and no owner approval were needed.
- **Production** (15 Nov evidence note, section 3): last run 14 Nov `skipped`, 0 files; the
  GitHub push is not configured; git history holds no commit made by it.
- **Screen:** `prompt-lab.jsx`; in `index.html` its `<script>` tag, the `OPERATOR_SCREENS`
  entry, the render line, the nav chip and the "Open prompt lab" button; in `home.jsx` the menu
  entry and a comment; in `sw.js` the cache entry and the unused `/prompts` network prefix (no
  route has had that prefix). The service worker's version goes from `v9` to `v10`, as each
  change of its file list has done, so phones drop the old cache.
- **Config:** `GITHUB_REPO` and `GITHUB_BRANCH` were read only by the routes file; CODEBASE now
  lists only `GITHUB_TOKEN`, which the watchdog reads. `tests/hermetic.py` still blanks all three
  names in tests (harmless).
- **Tests:** `test_prompt_file_encoding.py` deleted (it tested the writer); the two `/ui/prompts`
  tests in `test_api_auth_lockdown.py` removed; "Prompt Lab" dropped from the operator labels in
  `tests/frontend/no_invented_figures.test.mjs` and `prompt-lab.jsx` from the operator set in
  `test_ui_no_invented_figures_pr001.py`; `scripts/ui_responsive_audit.mjs` no longer visits it;
  three grandfathered broad-except lines of the deleted file removed from the baseline.
- **Left alone:** `data/prompt_changes.json` and `data/prompt_deploy_status.json` on the
  production volume (nothing writes them now). `prompt_enhancer` is a different feature and
  stays.

**Documents:** PRODUCT_MAP (router table, frontend list, operator screens, job table), KT section
9 (job table) and section 10 (operator tools), CODEBASE (auth note, the route table, the GitHub
settings, the file list), ARCHITECTURE, docs/README, UI_SPEC, the testing guide (11-H's member
expectation). **Counts set to measured values:** the scheduler has 25 possible job IDs (KT said
26 before this change, PRODUCT_MAP, ARCHITECTURE, docs/README and CODEBASE said 24); the API has
87 HTTP endpoints and 1 WebSocket across 14 routers (PRODUCT_MAP said 86 across 13; counted from
the route decorators and `include_router` lines). PRODUCT_MAP's per-router rows were not
re-counted.

**Suite** on the working tree committed as `4a1df8d`: 6,971 passed / 12 skipped / 1 xfailed /
0 failed, rc 0, 6m29s (ended about 22:13 IST); 7 fewer than 6,978, the deleted tests. `check_broad_except.py` OK (145),
`check_kt_docs.py` `errors: []`.

## Item 2 — the daily second AI call (the control lane)

**Proof of non-use:** `run_control_lane_step` had one caller, `daily_review.py` step 10, gated by
`RL_CONTROL_LANE_ENABLED`; its output, `<TICKER>_<YYYY-MM>_control_log.json`, is read only by
`core/intelligence/rl/eval/scorecard.py` (the monthly learning scorecard). No advisor, deep dive,
exit rule, sizing or grading code imports either module. `preopen_check.py` only named it in a
docstring.

**2a, switch off (`631731d`):** `rl.control_lane_enabled: false`; the KT checker's expected value
and KT section 1's configuration row follow. The daily-review test now asserts that the review
makes no control call and writes no control log; with the switch set back to `true` it fails
(1 failed, 4 passed), so it tests the switch. Suite: 6,971 passed / 12 skipped / 1 xfailed / 0
failed, rc 0, 6m33s (ended about 22:20 IST).

**2b, delete (`e81af2f`):** `core/intelligence/rl/agents/control_lane.py`, its prompt
`core/config/prompts/shared/control_lane.py`, step 10 of `daily_review.py`, "control lane" in
`_GATED_REVIEW_SKIPS` and the paper-lane docstring, the settings `RL_CONTROL_LANE_ENABLED` and
`CONTROL_LANE_MODEL` and their two `config.yaml` keys, the KT checker's key,
`tests/unit/intelligence/rl/test_control_lane.py` (7 tests), and the stubs in seven test files
(`test_daily_review_dossier`, `test_lesson_evidence`, `test_macro_fallback_context`,
`test_news_availability_telemetry`, `test_shock_path`, `test_paper_lane_isolation`,
`test_llm_telemetry_coverage`, whose failure test now uses the pre-open check's call). The
variables step 10 used (`final_entry`, `market_context`, `actual_close`) are still used earlier
in the review. Suite: 6,963 passed / 12 skipped / 1 xfailed / 0 failed, rc 0, 7m (ended about
22:28 IST); the 8 fewer are the 7 deleted control-lane tests and the telemetry test of the same
call.

**Kept:** the stored control logs, `ControlLog` and `ControlPrediction`, the store's
`load_control_log` and `save_control_log` (the scorecard's tests seed logs with it), and the
scorecard's control line. Past months stay readable; later months show n 0. That line leaves with
the learning reports (CLEAN-003, candidate 2).

**In production:** with 2b in the same push, no environment variable can turn the lane back on,
because the setting no longer exists. The last prediction made before the deploy stays unscored
and is left out of November's scorecard.

**Documents:** KT (configuration row; the gated review's skip list), RL_DESIGN (step list, paper
lane, file tree, gated-review skips, schemas, configuration, model callers, limits, section 25 in
the past tense with the August–October result), PRODUCT_MAP (models, step table, agents table,
schemas row, reading order "steps 0–9"), AGENTIC_DESIGN (tree, tiers, table), CODEBASE (tree,
tiers, settings, files), README (the controls paragraph), docs/README ("steps 0–9"), the schema
docstring.

## Item 3 — the C++ copy of the chart indicators

**Proof of non-use:** `stockindicators` was imported only by `fetcher.py` (behind `_USE_CPP`) and
by the skipped parity tests. Production cannot import it (15 Nov evidence note, section 6; the
Dockerfile builds no extension). The code-server has no `.pyd` or `.so` either
(`git ls-files` and the directory listing show `fetcher.py` and `__init__.py` only). `fetcher.py`
also put its own folder on `sys.path` only so the `.pyd` could be imported; nothing imports a
module from that folder by its bare name, so that line went too, with the `sys` and `Path`
imports it alone used.

**Removed:** `core/intelligence/algorithms/cpp/` (`CMakeLists.txt`, `build_ext.ps1`,
`src/indicators.cpp`), the guard and the three branches in `fetcher.py`, the 7 C++ parity tests
and the 3 fallback tests of `tests/contract/test_phase1_indicators.py`, the Dockerfile's and
`docker-compose.yml`'s comments, the `cpp/build/` ignore entry. Documents: PRODUCT_MAP (numeric
sub-engines row now names the Python indicators; the size line), docs/README.

**Acceptance — same numbers with and without the module:** four tests replace the removed ones.
`test_same_numbers_with_and_without_a_compiled_module` imports a fresh copy of `fetcher.py`
once with `stockindicators` unimportable (as in production) and once with a stand-in of that name
whose every answer is wrong on purpose (as on the owner's laptop); RSI, MACD and Bollinger must be
equal. `test_numbers_match_the_frozen_python_reference` compares them with
`tests/fixtures/yfinance_fetcher_pure.py`, an independent frozen copy kept for this. Run against the
old `fetcher.py` (a copy outside the tree), the first test's comparison fails: RSI −1.0 with the
module present, 61.8206 without. Suite: 6,964 passed / 5 skipped / 1 xfailed / 0 failed, rc 0,
6m43s (ended about 22:36 IST); 7 fewer skips (the parity tests) and one more pass (3 fallback
tests out, 4 in).

**For the owner:** the untracked
`core/intelligence/algorithms/indicators/stockindicators.cp313-win_amd64.pyd` on the laptop can be
deleted by hand; nothing reads it now.

## Routed input — BACKLOG B-8

Folded in, each with the same proof:

- **`scripts/aud098_thesis_tier_bench.py`**, an offline bench from the AUD-098 audit: no import,
  test, job or planned card names it; the PRODUCT_MAP bench list and two baseline lines followed.
- **Stale ignore entries:** `.gitignore` `typescript/node_modules/` and `frontend/node_modules/`
  (neither folder exists; the plain `node_modules/` line still covers any depth) and
  `.dockerignore` `src/frontend/web/dist` (no such folder). `cpp/build/` went with item 3.
- **The pasted `railway ssh` line** at the top of `docs/README.md`, with its blank line.

**Left in B-8:** `scripts/model_bench.py` and `scripts/reasoning_bench.py`, because PR-012 names
them as its starting points and extends `reasoning_bench.py`; the rest of B-8 as it was.

## Final suite

On the working tree committed as the records commit (B-8 and every record in place): 6,964
passed / 5 skipped / 1 xfailed / 0 failed, rc 0, 7m07s (22:38:57-22:46:04 IST). Then only this
section of the receipt changed, and `check_kt_docs.py` (`errors: []`) and `check_broad_except.py`
(OK, 143) ran again. Against FIX-017's last full suite (6,978 passed / 12 skipped): 14 fewer
passes and 7 fewer skips, all deleted tests: item 1's 7 (the five cases of the encoding test, two
lockdown tests), item 2's 8, item 3's 7 skipped parity tests and 3 fallback tests out, 4 new in.

## Production check

`CLEAN-004-W1`, after the first deploy that carries these commits and that day's 16:30 review:
read-only, the scheduler's job list has no `prompt_daily_deploy`; no control log file changed
after the deploy; the LLM telemetry shows no `control_lane` call after the deploy; `/health` 200.

## Decisions taken in this phase

- Four code commits (item 2 in two, as the card says) and the B-8 leftovers with the records,
  so the light story's records travel with its last code (AGENTS.md step 4).
- Kept `model_bench.py` and `reasoning_bench.py` (PR-012 extends them); folded in only the third
  bench.
- Bumped the service worker to `v10` and removed its dead `/prompts` prefix.
- Set the job and endpoint counts to measured values instead of subtracting from stale ones.
- Kept `save_control_log` and the control-log schemas: the scorecard reads the stored logs.
- Did not regenerate `docs/StockAgent-Three-Loops.pdf` (AGENTS.md, owner 17 Nov), though the card
  asks for it.
