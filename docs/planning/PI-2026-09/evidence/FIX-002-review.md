# FIX-002 review receipt — a scheduled ticker resolves to itself, never through an LLM

## Fresh-session review: ACCEPTED (2026-10-01)

- **What was reviewed:** [FIX-002](../stories/FIX-002.md), as described in the
  [implementation receipt](FIX-002-implementation.md).
  - `BaseSectorOrchestrator._resolve_ticker`'s exact-match short cut now also accepts a ticker
    in the managed list or the instrument registry (`_tracked_tickers`).
  - It reads `log_buffer.managed_symbols()` and `instruments.recorded_tickers()`. Both are new
    and read-only.
  - The change adds 20 tests, edits KT §4, AGENTIC_DESIGN and guide case 02-G, and rebuilds the
    PDF.
- **Context:** a fresh-session review in a new conversation, 1 Oct 2026, about 21:20–21:50 IST.
  - It is not the conversation that implemented FIX-002, and it did not read that chat.
  - It read the card, the receipt and the diff, and all of `_resolve_ticker`, `_managed_tickers`,
    `_company_name_for`, `_yf_info`, `set_aggregator_weights` and `_resolve_weights_for`. It
    also read `analyse()`, `analyse_async()`, `load_registry`, `load_managed_tickers` and the
    company-name cache.
  - It traced the consumers: `generate_forecast._run_orchestrator_analysis` and
    `regenerate_envelope` (the containment route and its CLI), the daily review, the analyse,
    stream and UI routes, and the discovery deep dive.
- **Pending production checks:** none due. FIX-001's check is the 23:45 audit tonight.
- **Peers:** the StockAgent sessions were idle at the start and before the bookkeeping. The one
  busy session belongs to another project.
- **Nothing** was committed, pushed, deployed, configured or sent. No production state was read.
- **Verdict: accepted.** There is no critical or high finding, and no defect in the change.
  - **M1, medium (predates FIX-002, outside its card).** The weekly discovery deep dive still
    sends its candidate symbols to the LLM. A renamed candidate can mint a shelf idea, which is
    a SWITCH destination, from another company's analysis. It is routed to SA-026 as a card note.
  - **L1, low (predates FIX-002, which adds one caller).** `load_registry` raises on a registry
    file that is not valid UTF-8, despite its "never raises" contract. It is routed to SA-031.
  - **I1, information.** The fix also restores the forecast's injected weights. Before it, a
    renamed run loaded the other company's learned weights. No action is needed.

### Review input verified

- **Manifest:** [FIX-002-manifest.json](FIX-002-manifest.json).
  - The SHA-256 of its LF bytes is
    `98ed116a1975cf81f6ca0e4e2790a44e3959142ca49657f9260ae92d2250cca8`, as the receipt states.
  - `kt_manifest.py verify` gave 8 files and 0 mismatches at the start, before any review edit.
- **Diff:** rebuilt by the receipt's recipe against `da66fee`, with the reviewer's own loop.
  - It gave 7 text files, 31,829 bytes and SHA-256
    `bc726da87998ed846dc909f5241ac350fc0608bd97fa90abed02e0a9042c0385`, the receipt's digest.
  - The PDF's blob is `a99a6350…`, as pinned.
- **Completeness:** HEAD is `da66fee`, the baseline. `git status` lists exactly:
  - the 8 manifest paths: 7 modified, plus the new test file;
  - the 2 excluded bookkeeping files, STATE.json and HANDOFF.md;
  - the untracked implementation receipt and the manifest itself.

### Contract checked

- **The short cut, in order.**
  1. The input is trimmed and uppercased.
  2. It resolves to itself if it is in the sector's static `TICKERS` (unchanged, cached on the
     instance), **or** in `_tracked_tickers()`: every managed-list `sym`, any sector, enabled
     or not, trimmed and uppercased, plus every registry record, valid or invalid.
  3. Otherwise the LLM path runs, unchanged, with the Serper fallback.
- **The company name** comes from `_company_name_for`: the curated override, else the learned
  cache, else yfinance for the registry's symbol or `{TICKER}.NS`, else the ticker. The learned
  cache is written only from yfinance (`learn_company_name` has one caller), so no name ever
  comes from the LLM.
- **Reads, never writes.** `managed_symbols()` never seeds or repairs the list, unlike
  `load_managed_tickers`. `recorded_tickers()` uses `load_registry`'s mtime memo.
- **Failure modes.**
  - A missing managed list gives an empty set, quietly.
  - An unreadable one, or one that is not a list, gives an empty set and a warning. Managed
    tickers then go back to the LLM for that run. A UTF-8 BOM counts as unreadable. That
    matches `load_managed_tickers`, which treats a BOM as malformed and re-seeds the file.
  - An unusable registry names no ticker.
  - **L1:** a registry that is not UTF-8 raises.
- **Consumers.** `query.ticker` drives everything downstream: `set_run_ticker`, the weights,
  the NSE prefetch, the agents, the aggregator and the decision gate's identity.
  - The forecast and the containment's `regenerate_envelope` call
    `set_aggregator_weights(W, ticker)` and then `analyse(ticker)`. When resolution renamed the
    ticker, `analyse` discarded W and loaded the other company's learned weights (**I1**). Now
    W is used.
  - The envelope is saved under the scheduled ticker in both cases.
- **The containment runbook.** `run_schedule.py reforecast` calls
  `regenerate_envelope(trigger="manual")`. That returns `None`, printed as `[SKIP]`, with no side
  effects when `RL_REFORECAST_ENABLED` is off or `reforecast_count` has reached
  `RL_REFORECAST_MAX_PER_MONTH` (default 2). Otherwise it archives the superseded envelope first,
  keeps rows dated on or before today byte-identical, and prints the archive name. The receipt's
  description is accurate.
  - It must run **after** the deploy. Before it, the re-forecast's own analysis would go
    through the old resolver again.

### Independent adversarial examples

The probes are `rev/test_fix002_review.py` in the session scratchpad; they are not tracked.
- They ran under `tests.conftest`, so the hermetic guard applied: no network, and an empty
  working directory per test.
- They were written without the implementer's helpers. The expected results were worked out by
  hand.

**10 of 10 passed.**

| Probe | Example | Result |
|---|---|---|
| R1 | **Production's scheduled set:** the SA-039 26 Sep baseline's 20 tickers, with TATAMOTORS disabled and TMPV added (1 Oct), plus the shipped registry. Each is resolved in all 5 orchestrator classes. The LLM answers TATAMOTORS to anything | All 21 resolve to themselves in all 5 classes, with 0 LLM and 0 Serper calls. SA-008's identity is `resolved`, `{TICKER}.NS` for all 20 scheduled tickers, and `unresolved`, `TMPV.NS` for TATAMOTORS. So every scheduled ticker is priced from its own listing, and none depended on the LLM to correct its code |
| R2 | **The 1 Oct forecast through the real `analyse()`, sync and async.** The IT orchestrator gets `set_aggregator_weights(W, "TATAELXSI")` and then `analyse("TATAELXSI")`. The probe stops it at the first data fetch, the NSE prefetch, and reads what that fetch receives | **Now:** ticker TATAELXSI, weights W pinned to TATAELXSI, learned weights not loaded, 0 LLM calls, name from yfinance for `TATAELXSI.NS`. **With the original defect restored in memory:** ticker TATAMOTORS, TATAMOTORS's learned weights loaded, 1 LLM call. That is the defect as measured, plus I1 |
| R3 | The managed list is a directory, has a UTF-8 BOM, is cut off mid-write, or holds `"  tataelxsi "` | Nothing raises, and TCS still resolves through the static list. The padded symbol resolves to TATAELXSI with no LLM call. The other three give the documented fallback: one LLM call and a `managed_tickers` warning |
| R3b | The registry file holds a byte that is not valid UTF-8 | `_resolve_ticker` raises `UnicodeDecodeError`, raised by `load_registry` itself. **This is L1** |

### Tests

- **The 20 new tests.**
  - The invariant's fixture is a hand-written managed list of 14 tickers across five sectors.
    The expected result is the identity map, and the expected names are the fixture's own.
  - The fake LLM answers TATAMOTORS and records each call. Every test asserts that no call was
    made, as well as checking the ticker. This matters because the resolver's except-branch
    returns the input when the LLM raises.
  - Serper and yfinance are faked and recorded, and the hermetic guard backs that up. No
    fixture is unrealistically successful: the missing, malformed, not-a-list and
    unusable-registry cases are each covered.
- **The original defect, reproduced.** A plugin set `_tracked_tickers` to return an empty set in
  memory, with no source file touched. With it, **11 of the 20 tests fail**, including the
  invariant in all 5 classes and the measured TATAELXSI case. The 9 that pass cover free text,
  the Serper fallback, read-only behaviour and the shipped registry, which the defect does not
  change.
- **The implementer's mutations** (10 of 10 caught) were not re-run. The reviewer's own run of
  the defect and probe R2's counterfactual cover M1. Probe R1 covers M3 and M5 against the
  production set.

### Findings

| ID | Severity | Location | Evidence | Disposition |
|---|---|---|---|---|
| M1 | Medium (predates FIX-002; outside its card, whose subject is scheduled tickers; inferred from code, not measured) | `core/discovery/deep_dive.py:125-126` | The weekly discovery job (Saturday 12:30 IST) deep-dives candidate symbols that are not managed: `get_orchestrator(sector).analyse(cand.symbol)`. Unless a candidate is in the registry, it still goes to the LLM, which can rename it, as it renamed 3 managed tickers in 3 days. The shelf idea is saved under the candidate's symbol from the renamed analysis. Active shelf ideas are the portfolio pipeline's SWITCH destinations (`core/portfolio/pipeline.py:197`). SA-003's gate checks the analysed ticker's identity, not whether it is the one asked for | Routed to [SA-026](../stories/SA-026.md) as a card note (deep_dive.py is already among its starting points): a symbol the caller already holds, such as a discovery candidate, resolves to itself. The receipt named it as an open limitation; the card did not record it until now. Not blocking: FIX-002's criteria are met |
| L1 | Low (predates FIX-002, which adds one caller outside a try) | `src/backend/shared/data/instruments.py:353` | `load_registry` promises never to raise, but catches only `(OSError, RegistryError)`. A file that is not valid UTF-8 raises `UnicodeDecodeError`, a `ValueError` (probe R3b). `_resolve_ticker` now calls it before any try, and `analyse()` does not catch it, so every analysis would fail loudly. Nothing would be mis-analysed silently. The registry ships in the image from git, and the suite reads the shipped file, so a bad byte would fail locally first | Routed to [SA-031](../stories/SA-031.md): catch `ValueError` beside `OSError` and treat the file as unusable. FIX-002's `_tracked_tickers` docstring ("never raise") then holds |
| I1 | Info (traced in code; reproduced by probe R2) | `base_orchestrator.py:152-155, 238`; `generate_forecast.py:317-318` | Before FIX-002, a renamed run also lost the forecast's injected weights, because `analyse` reloads weights when the ticker changes. So TATAELXSI's 1 Oct envelope was also built with TATAMOTORS's learned weights. FIX-002 removes both effects for managed tickers | None. The containment re-forecast rebuilds the rest of October with TATAELXSI's own weights |

No defect in the change was found.

### Decisions

- **D1 upheld.** Routing a ticker to a sector is the scheduler's job. A user who asks the IT
  graph about MARUTI already got MARUTI analysed by it when MARUTI was in a static list.
- **D2 upheld.** The added-while-running test and probe R2 both pass. A per-instance copy would
  go stale in `Scheduler.run_now`, which reuses one orchestrator. The cost is one small file read
  per run, and the registry is memoised by mtime.
- **D3 upheld.** In probe R1 and in the tests, TATAMOTORS (disabled) resolves to itself and stays
  `unresolved`. SA-008's gate, not an LLM, decides what it may do.
- **D4 upheld.** With `is_registered`, an unusable registry would make any text a ticker.
- **D5 upheld.** The card names `_company_name_for`'s order.
- **D6 upheld.** The change is a narrow guard; SA-026 holds the single sector definition.

### Commands and results

Environment: Windows 11, `.stockai` venv (Python 3.13), repository root.

| Check | Command | Result |
|---|---|---|
| Manifest | `python scripts/docs/kt_manifest.py verify docs/planning/PI-2026-09/evidence/FIX-002-manifest.json` | 8 files, 0 mismatches, `98ed116a…`, at the start |
| Diff | the receipt's recipe, with the reviewer's own loop | `bc726da8…`, 31,829 bytes, 7 text files; PDF blob `a99a6350…` |
| Full suite | `python -m pytest tests -q -p no:cacheprovider --basetemp=<scratchpad>/bt_full` | **4056 passed, 12 skipped, 0 failed** (13 min 48 s, about 21:28–21:42 IST): the implementer's 4055 plus the SA-009 Windows flake, which did not recur. `data/`, `logs/` and `outputs/` were unchanged: 800 files, the same digest before and after |
| Focused | the receipt's 7 files: `python -m pytest -q -p no:cacheprovider tests/unit/shared/test_managed_ticker_resolution_fix002.py tests/unit/test_ticker_resolution_shortcircuit.py tests/unit/shared/test_instrument_identity_sa008.py tests/unit/shared/test_decision_gate_sa003.py tests/unit/test_company_name_cache.py tests/integration/test_orchestrator.py tests/unit/shared/test_error_capture_context.py` | 162 passed |
| The original defect | the same new test file, with `-p fix002_m1_plugin` (in memory: `_tracked_tickers` returns an empty set) | 11 failed, 9 passed |
| Probes | `python -m pytest -q -s -p no:cacheprovider -c pyproject.toml --rootdir . -p tests.conftest <scratchpad>/rev/test_fix002_review.py` | 10 passed |
| Broad-except guard | `python scripts/ci/check_broad_except.py` | OK (154 grandfathered) |
| KT check | `python scripts/docs/check_kt_docs.py` | Before the edits: errors `[]`, 34 pages, source `6ac7ccb4…`, the manifest's KT. After the edits and `build_kt_pdf.py`: errors `[]`, 422 links, 34 pages, source `7fef3482…`, PDF blob `f541a658…` |

**Not exercised:**
- Linux and Python 3.11 (CI runs after a push);
- a real LLM, Serper or yfinance call;
- production's current managed list. Probe R1 uses the measured 26 Sep and 1 Oct sets;
- a managed-list write racing a resolution in production. The torn read is the receipt's open
  limitation, and R3 shows its fallback.

### Review edits (documentation only)

- **The KT:** §4's FIX-002 paragraph now reads "accepted by its fresh review on 2026-10-01, not
  yet committed". Its example also says that the renamed run used Tata Motors' learned weights
  (I1). A sentence on discovery candidates was added (M1). The PDF was rebuilt (source
  `7fef3482…`).
- **Guide 02-G:** the status wording.
- **The [SA-026](../stories/SA-026.md) card:** a routed note for M1.
- **The [SA-031](../stories/SA-031.md) card:** a routed note for L1.
- **Manifest check:** `verify FIX-002-manifest.json` now mismatches exactly the KT, the PDF and
  the guide. No code or test file was changed.

### Acceptance and what remains

| Criterion | Result |
|---|---|
| A managed ticker resolves to itself in every sector orchestrator, with no LLM or web-search call | Met (the invariant in all 5 classes; R1 with production's set; R2 through `analyse()`) |
| Its company name never comes from the LLM | Met (the company-name test; the learned cache has only a yfinance writer; R2) |
| Free text is unchanged | Met (the free-text and Serper tests; the 9 tests that pass under the defect) |
| SA-008 is unchanged | Met (TATAMOTORS resolves to itself and stays `unresolved`; the SA-008 tests are unchanged and pass) |
| An independent invariant, with an LLM that fails the test if called | Met (hand-written identity map; every test asserts that no call was made; 11 tests fail under the defect) |
| KT §4, AGENTIC_DESIGN and guide 02-G describe it; the PDF matches its source | Met, with the review edits |

- **Reviewed revision:** the uncommitted working tree on `da66fee`, pinned by input `98ed116a…`
  and diff `bc726da8…`, plus the documentation-only review edits.
- **Next:**
  - **Commit and push** need the owner's word, in a job-free window (00:10–06:20 IST is safest).
    The landing commit's KT bump declares the FIX-002 commit, because `base_orchestrator.py`
    and `instruments.py` change after `0493f7c`.
  - **Production check (read-only).** After the deploy, the next 16:30 review logs
    `Resolved: X -> ticker='X'` for every managed ticker. It shows no `Serper fallback` line
    and no `ticker_resolution` call for them, and no data-health line names another ticker.
    `production_verification` is `pending_deployment`.
  - **Containment (needs the owner's authorisation, after the deploy):** re-forecast
    TATAELXSI's October envelope with the receipt's command. Check
    `RL_REFORECAST_ENABLED` and `reforecast_count` first, and record the archive name and the
    new run id.
- **Next story:** FIX-003, in a new conversation, then SA-010. SA-008 change 1 stays open. It
  must come before any `successors` record.
