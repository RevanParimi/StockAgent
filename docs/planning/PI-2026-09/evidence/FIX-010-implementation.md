# FIX-010 — implementation receipt

**Story:** [FIX-010](../stories/FIX-010.md) · **Phase:** implementation, with same-conversation
self-review only · **Date:** 2026-10-15, about 20:30–21:47 IST · **Status after this phase:**
`review_required`

**How this phase came about.** The phase ran in the same conversation as PR-001's re-review and
FIX-010's planning. The owner asked for it: "ya go ahead on you suggestions and commit and push
at the end". That instruction overrides the one-phase-per-conversation rule for this story. The
fresh review still happens in a new conversation, after the commit and push, as for FIX-005 and
FIX-004 change 1. Peers were idle.

**Baseline:** `4c85eec` plus the accepted, uncommitted PR-001 work (manifest `1c7ea945`) and
FIX-009 work (manifest `11c2c620`). FIX-010 layers on five PR-001 files and five docs:
`ui_data.py`, `portfolio.jsx`, PR-001's two test files, and CODEBASE, PRODUCT_MAP, the guide, the
KT and UI_SPEC. Their pre-FIX-010 bytes were snapshotted to the ignored
`analysis_data/fix010/base/` before any edit, each checked against PR-001's manifest or `HEAD`.

## In one example

The member holds DIXON, the owner holds BEL, and neither is managed or on the shelf.

**Before.** The 16:30 analysis turns DIXON from BUY to SELL. Nothing records it in the score
history. Home calls DIXON "Not analysed", Portfolio shows no change, and the chat finds no saved
analysis.

**Now.** The analysis writes DIXON's row.
- Home shows DIXON's score and verdict, and Portfolio lists "DIXON: BUY → SELL".
- The chat's current verdicts include DIXON.
- None of these screens names BEL to the member. If restoring the write had been the only change:
  - the chat's context, search, Home's market panes, the market summary and the sector comparison
    would have named BEL;
  - so would a stock someone else had only asked the chat about.

## What changed

- **The write** (`src/backend/shared/pipeline/base_orchestrator.py`).
  - `_record_score_history(report)` runs at both exits, `analyse` and `analyse_async`, right after
    `log_run_summary`. That is after the decision gate, so the row holds the verdict the run
    returns (`INSUFFICIENT DATA` when enforce withholds one).
  - A failed write (`sqlite3.Error`, `OSError`, or a report that will not serialize, `ValueError`
    or `TypeError`) is a warning. It never fails the analysis.
- **Who sees which stock** (`services/api/routes/ui_data.py`).
  - Shared stocks, from `_shared_symbols()`:
    - the built-in universe;
    - the managed list, which `GET /ui/tickers/managed` already serves to everyone;
    - the shelf's active ideas.
  - The viewer's own stocks, from `_own_symbols(user_id)`: holdings and watchlist, plus the global
    watchlist when Atlas is off. It reads only an existing portfolio, like the chat's brief
    (FIX-005), so the read never creates an account's folder. No user id means an anonymous
    request while sign-in is required: it owns nothing and never stands in for the default user.
  - Both reads fail closed: an unreadable list adds nothing.
  - `_only_visible(rows, symbols)` filters store rows. It is applied to:
    - `/ui/learnings`, now with the session (`get_current_user_optional`), which walks the visible
      stocks instead of the 16 built-in ones and returns `{items, since}`;
    - `/ui/search`'s thesis-text match, with the session;
    - the chat's `_ctx_current_verdicts` and `_ctx_recent_history`, with the caller's
      `user_id`, through `_build_chat_context` and the history tool;
    - `/ui/bootstrap`'s market panes (pulse, one-liners, drivers, "This month" votes) and
      `/ui/market/summary`, shared stocks only;
    - `services/api/routes/analytics.py`: `/analytics/sector-comparison` and the score index
      behind the RL export and Power BI feed, shared stocks only.
- **Agent scores.** The writer stores `{raw, weight, weighted}` per agent. Home's "This month"
  votes did `float(value)` on each value, so the writer's rows made `/ui/bootstrap` raise
  `TypeError` (reproduced on the base code). `_agent_score()` now reads `raw`, and takes a plain
  number as it is. The suggestions' "why" line uses it too.
- **The watchlist.** A watched stock outside the built-in universe shows its score history row,
  with no price fetched ("—"). A stock with no row is still "Not analysed".
- **The empty case.** `since` is the date of the oldest kept run among the listed stocks.
  Portfolio reads "No verdict changes since 16 Sept", or "No verdict changes recorded yet" with
  no date (`portfolio.jsx`, `fmtLearningsSince`).
- **The backfill** (`scripts/backfill_score_history.py`, new). It copies `run_summaries` runs into
  `score_history`:
  - **Rows:** naive-UTC `run_at`, as the writer writes; agent scores as `{raw}`; thesis empty; a
    `{"backfill": "run_summaries", "run_id": …}` marker.
  - **Skips:** runs with no verdict or score, and anything at or after a stock's first live row.
    A second apply adds nothing, and each stock keeps at most 90 rows.
  - **Modes:** dry run by default; `apply` and `remove` take an SQLite backup first. The mode comes
    from `SCORE_BACKFILL`, because the production pipe passes no arguments.
  - **Output:** counts only.

## Design decisions (delegated, recorded)

- **D1.** One writer, at the orchestrator's exit. Every entry point ends there: the 16:30 review,
  the monthly forecast, discovery deep dives, `/analyse`, the stream and the chat. Each caller
  could save its own row instead, but a new entry point would then forget.
- **D2.** Restore the documented store; don't point readers at `run_summaries`. That log has no
  thesis, and about a dozen readers expect the score store (AGENTIC_DESIGN step 7 already says
  each analysis records the row). Merging the two stores is out of scope (card).
- **D3. The managed list counts as shared.** Members can already read it.
- **D4. Beyond the card's named readers.** The card listed `/ui/learnings` and two chat readers.
  Restoring the write also activates these list-shaped reads of the store, so each is filtered:
  - Home's market panes;
  - the market summary;
  - search by thesis text;
  - the analytics sector comparison and score index.

  A guard test now fails on any unfiltered list-shaped read, apart from three keyed ones.
- **D5. Anonymous means shared only.** With sign-in required, an anonymous request never stands
  in for the default user, because that would show the owner's holdings (the same class as
  FIX-006).
- **D6.** Forecast misses still come from the built-in universe's feedback logs, which are public,
  as before.
- **D7.** Dating the watchlist score stays with SA-024 (the first PR-001 review's I2). The card's
  example said "dated" and was corrected.
- **D8. The backfill's backup** is a sibling copy made with SQLite's backup API, not the nightly
  archive tooling (SA-007), which has no off-site target yet.

## Tests

- **`tests/unit/test_score_history_fix010.py`, 32 tests (new).** Expected values come from each
  fixture's own table, not from the code.
  - **The write**, through the real orchestrator and aggregator (the SA-003 harness). One analysis
    writes one row with the returned verdict, and each agent's raw score is checked. A second
    analysis adds a second row.
  - The async exit writes its row too. With enforce, the row holds `INSUFFICIENT DATA`, never the
    withheld verdict.
  - A locked database leaves the report and its `run_summaries` call intact, and logs the
    warning.
  - **Guards:**
    - every sector orchestrator inherits both exits, and the registry gives out only those
      classes;
    - the base orchestrator is the only writer;
    - an AST scan finds every `get_all_latest`/`get_by_date_range` call filtered by
      `_only_visible`, apart from three keyed reads.
  - **Who sees which stock**, with Atlas on and off. The rows are written by the real writer: the
    owner holds QOWNHOLD, the member QMEMHOLD; QASKED is only analysed; QMANAGED is managed; QSHELF
    is an active idea and QDROPPED a dropped one. Every one changed verdict. The owner, the member
    and an anonymous caller each see exactly their set on `/ui/learnings`, `/ui/search` and the
    chat's context and history tool. Bootstrap, the market summary and the sector comparison name
    shared stocks only.
  - **"This month" votes** equal the mean raw score of the shared stocks' runs, worked out by hand.
  - A watched stock outside the universe shows its score; one with no analysis is "Not analysed".
  - **The empty case:** `since` is the older of two single runs. With nothing visible it is
    `null`.
  - An unreadable portfolio names only shared stocks.
  - **The backfill:**
    - the dry run's exact counts, and it writes nothing;
    - apply: naive UTC, the agent shape, the marker, the live-row cut-off, the newest 90;
    - a second apply adds nothing, and `remove` restores the table exactly.
- **PR-001's story tests, adjusted to the new contract.** `since` is now in the shape and in
  three empty bodies, and `_rows_since` takes `visible`. 44 pass (43 plus the browser wrapper).
- **The browser suite**, `tests/frontend/no_invented_figures.test.mjs`, has 11 tests (was 10):
  - the misses-only heading reads "No verdict changes since 16 Sept", or "recorded yet" with no
    date;
  - a new test starts signed out: the page loads the shared stocks' changes, and a sign-in
    through the form fetches them again as the member, whose own holding then shows ("2
    changes").
- **Two chat test stubs** (`test_chat_brief_user_scope_fix005.py`, `test_chat_session_memory.py`)
  replace `_build_chat_context` with a one-argument lambda. They now accept the `user_id`
  keyword; nothing else changed.
- **On the base code** (`analysis_data/fix010/swap_plugin.py`, `FIX010_SWAP=base`, SHA-256
  checked): 28 of the 32 new tests fail.
  - The four that pass on the base are the backfill test (a new script, not swapped) and the
    three source-scanning guards. They read the files on disk, which an in-memory swap cannot
    change.
  - That those guards bite is shown separately, with planted violations in a temp tree
    (`analysis_data/fix010/test_guard_probe.py`, 3 passed): an unfiltered
    `get_all_latest()` fails the list guard with its file, line and function; a filtered one
    passes; a second `ScoreStore().save` site fails the writer guard.
  - The market-wide test fails there with `TypeError: float() argument must be a string or a real
    number, not 'dict'`: the crash.
- **Mutants M1–M11**, each caught (`swap_results.txt`, `swap_results_final.txt`):
  - M1/M2: no write from the sync/async exit;
  - M3: a failed write propagates;
  - M4: an anonymous viewer stands in for the default user;
  - M5: dropped shelf ideas count as shared. It survived at first; the fixture now gives QDROPPED
    a change (20 fail);
  - M6: per-agent objects read as numbers;
  - M7: the outside-universe watchlist row is "Not analysed" again;
  - M8: `since` is the newest run. It survived at first; the empty-case fixture now has two runs
    (2 fail);
  - M9: the chat context forgets its caller;
  - M10: search unfiltered;
  - M11: the sector comparison unfiltered.
- **Elsewhere:**
  - `npm run test:frontend`: 28 of 28;
  - `check_kt_docs`: errors `[]`;
  - the broad-except guard: OK (153);
  - the failing files after the first full run, re-run: 91 passed.
- **Full suite:** 4584 passed, 12 skipped, 0 failed (run 2, 21 min 1 s, 21:25–21:46 IST).
  - The first run (20:59–21:23) failed 10: the two stubs (9 tests) and the hot-path guard, which
    requires `exc_info` on the new warning. Both were fixed.
- **Not run:**
  - the layout audit (FIX-010 changes a heading string and a fetch function, not the layout);
  - the backfill against real data;
  - production.

## Documentation

- **KT:**
  - section 1: a dated "Score history" row with the probe's figures;
  - section 3: `scores.db` gets its own persistent-records row;
  - section 10: the learnings paragraph covers the stocks the viewer may see, the `since` empty
    case, and "may have been left out", the SA-031 RR-I1 wording, now fixed;
  - section 10: a new "Score history and who sees which stock" paragraph, with an example;
  - section 12: the intro and a FIX-010 row (`Open`).
- The PDF was rebuilt: 43 pages, source digest `0ced16a2…` = the KT's SHA-256, `check_kt_docs`
  errors `[]`.
- **CODEBASE:** the `/ui/learnings` and `/ui/search` rows ("session optional"), market summary,
  sector comparison, `score_store.py`, `base_orchestrator.py`, `data/scores.db`.
- **Guide:** 11-J (the dated empty case) and a new case, 11-K (the privacy rule and a watched
  stock's analysis).
- **UI_SPEC:** `PORTFOLIO_LEARNINGS` gets `{items[], since}`, the visible-stocks note and the
  heading wording. **PRODUCT_MAP:** `ui_data.py`'s line count.
- `docs/AGENTIC_DESIGN.md` step 7 is unchanged: it already said each analysis records the score
  history row, and now that is true.

## Manifest and digest

- **Review input:** [FIX-010-manifest.json](FIX-010-manifest.json),
  `900c8f27ff08f4ead35c73227f3038fef4860082449119c61c016701467b8027`, 18 files.
- **Diff:** `150bb8b6164d30e608825992d2df3e1df4b9cbcb6ee414cb2466854fc2b95df3` (105,005 bytes, 17 paths, PDF excluded), from
  `analysis_data/fix010/manifest_and_digest.py`.
  - Bases: `analysis_data/fix010/base/` (SHA-256 checked) and `git show HEAD` for `analytics.py`.
  - New files are diffed against `/dev/null`.
- PR-001's manifest (`1c7ea945`) now mismatches on the ten files FIX-010 layered. FIX-009's still
  mismatches on its five layered docs, as before.

## Self-review

No critical, high or medium finding.

- **I1 (info, rollout).** Until the backfill runs (it is optional), production's history starts
  empty. Home fills after the first analyses: Friday's 16:30 review and any chat or `/analyse`
  request. A verdict change shows only once a stock has two runs.
- **I2 (info).** `/ui/learnings` now looks through about 100 stocks: the 16 built-in, the managed
  list, shelf ideas and the viewer's own. That is one indexed query each, on a page opened by
  hand.
- **I3 (info).** Forecast misses still come only from the built-in universe's feedback logs (D6).
  A managed stock's misses outside the universe are not listed, as before.
- **I4 (info).** An analysis that the chat runs for a stock nobody holds is stored, and named only
  when a viewer asks for it by name. The store does not record who asked, so not even the asker's
  own lists show it (the card's privacy case).

## Production check (after an owner-authorized deploy, read-only)

1. After the first 16:30 review following the deploy, re-run
   `analysis_data/pr001/rereview1/score_history_probe.py`. `score_history` rows are above 0, and
   `last_run_at` is that day.
2. **Home:** as the test member, a watched stock that is analysed daily shows a score and
   verdict.
3. Guide 11-K.
4. **Backfill, only at the owner's word.** First the dry run:
   `railway ssh "cd /app && echo $(gzip -9c scripts/backfill_score_history.py | base64 -w0) | base64 -d | python -c 'import sys,zlib;exec(zlib.decompress(sys.stdin.buffer.read(),31))'"`.
   Then the same command with `SCORE_BACKFILL=apply` placed before `python`.
