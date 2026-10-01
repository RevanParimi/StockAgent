# FIX-002 implementation receipt — a scheduled ticker resolves to itself, never through an LLM

- **Story:** [FIX-002](../stories/FIX-002.md), routed on 1 Oct by SA-039 P3 and the
  [SA-003 enforce decision](SA-003-enforce-decision-2026-10-01.md).
- **Context:** implemented on 1 Oct 2026, about 19:10–20:00 IST, in a **new conversation** opened
  with "continue". A same-conversation self-review was done. It is not the fresh review, which
  needs another new conversation. STATE: `review_required`.
- **Baseline:** `da66fee` (the KT bump after FIX-001's commit). The working tree also carried the
  uncommitted FIX-001 push record in STATE and HANDOFF, which this phase keeps.
- **Nothing** was committed, pushed, deployed or configured, and no production state was read.

## What it does, in one example

At 09:16 on 1 Oct the monthly forecast asked the IT orchestrator for TATAELXSI (Tata Elxsi).

- **Before:** the resolver's short cut knew only the IT sector's built-in list (TCS, INFY, WIPRO,
  HCLTECH, TECHM, LTIM, COFORGE). TATAELXSI was not in it, so an LLM was asked which company it
  was. It answered TATAMOTORS. The run analysed Tata Motors (SELL), and TATAELXSI's October
  envelope was saved from that analysis.
- **After:** TATAELXSI is in the managed list, so it resolves to TATAELXSI with no LLM or web
  search. Its name comes from the curated or learned name, else yfinance for its own listing,
  else the ticker.

## The change

- **`src/backend/shared/pipeline/base_orchestrator.py`**
  - New `_tracked_tickers()`: every managed-list symbol (any sector, enabled or not) and every
    instrument-registry record. It is read on each resolution, not cached, so a ticker the owner
    adds is known at once. The forecast, the review, the analyse, stream and UI routes and the
    deep dive build a fresh orchestrator per run; `Scheduler.run_now`, a manual override, reuses
    one across its tickers. The read does not depend on either.
  - `_resolve_ticker`: the short cut now accepts a ticker in `_managed_tickers()` (the static
    `TICKERS`, unchanged) **or** in `_tracked_tickers()`. The rest of the method is unchanged:
    the same `StockQuery` with `_company_name_for`, and free text still goes to the LLM.
  - `_managed_tickers`' docstring now says it is the static setting.
- **`services/api/log_buffer.py`:** new `managed_symbols()`. It is read-only. Unlike
  `load_managed_tickers`, it never seeds a missing file, so resolving a ticker cannot write the
  managed list. A missing file gives an empty set quietly. A file that exists but cannot be read
  as a list gives an empty set and a **warning**, because managed tickers then go back to the LLM.
- **`src/backend/shared/data/instruments.py`:** new `recorded_tickers()`, the registry's records,
  valid or not. Unlike `is_registered`, an unusable registry names no ticker. It still
  quarantines every ticker through SA-008, but it is no evidence that free text is a ticker.

## Acceptance criteria

| Criterion | Result | Evidence |
|---|---|---|
| A managed ticker resolves to itself in every sector orchestrator; no LLM or web-search call | Met | The invariant test, for all 5 real orchestrator classes |
| Its company name never comes from the LLM | Met | Curated first, then yfinance for the registry symbol (CANARABANK asks `CANBK.NS`), then the ticker; M9 |
| Free text is unchanged | Met | "tata elxsi" makes 1 LLM call and takes its answer; an unverified answer still takes the Serper fallback |
| SA-008 is unchanged | Met | TATAMOTORS (disabled, and asked of `it_sector`) resolves to itself and its identity stays `unresolved` on TMPV.NS; SA-008's own tests pass unchanged |
| Independent invariant | Met | Below |

**The invariant test** (`test_every_managed_ticker_resolves_to_itself_in_every_sector`):

- **Fixture:** a hand-written managed list of 14 tickers across five sectors, shaped like
  production's. It holds the measured cases (TATAELXSI, TVSMOTOR, HAPPSTMNDS), a disabled
  TATAMOTORS, tickers with punctuation (M&M, BAJAJ-AUTO), and PAYTM in a sector with no graph.
- **Expected:** every ticker maps to itself. The expected names are the fixture's curated names.
  Neither is computed by the changed code.
- **The LLM** answers TATAMOTORS to any prompt, as production's did, and records each call.
  The resolver's own except-branch returns the input on any LLM error, so an LLM that only
  raised could not be told apart by the returned ticker. Every test therefore asserts that no
  call was recorded, as well as checking the ticker. Serper and yfinance are recorded the same
  way.
- **Not vacuous:** the test asserts that TATAELXSI, TVSMOTOR and PAYTM are outside each
  orchestrator's static list.
- **Isolation:** the suite reads an empty registry by default (`tests/conftest.py`), so this test
  exercises the managed list alone. The registry has its own tests.

## Decisions for the reviewer

- **D1. Every sector's orchestrator honours every managed ticker,** whatever sector the entry
  names. The card asks for "a ticker in the production managed list … returns that ticker" in
  every orchestrator. Routing a ticker to the right sector is the scheduler's job, which passes
  the entry's sector. A user who asks the IT graph about MARUTI gets MARUTI analysed by the IT
  graph, as already happens for the static lists.
- **D2. Read the list on every resolution, not once per instance.** It costs one small file read
  per run. A per-instance copy would mostly work today, because most callers build a fresh
  orchestrator, but it would go stale silently in any caller that keeps one, such as
  `Scheduler.run_now` (M6).
- **D3. Disabled entries count.** A disabled ticker is still the company it names. TATAMOTORS is
  the example: SA-008's gate, not an LLM, decides what it may do.
- **D4. An unusable registry adds nothing** (`recorded_tickers`, not `is_registered`). With
  `is_registered`, any free text would be taken as a ticker whenever the registry file broke
  (M8).
- **D5. The managed list's own `name` field is not used** for the company name. The card names
  `_company_name_for`'s order, and that is kept. The news fetcher already reads the list's names.
- **D6. Narrow scope.** The fix adds a check to the existing short cut. SA-026 holds the long-term
  fix: one sector definition from which the managed list, the static lists and the short cut
  all read.

## Checks

- **Environment:** Windows, the project venv `.stockai` (Python 3.13), the SA-005 hermetic guard
  (no network, an empty working directory per test).
- **New tests:** `tests/unit/shared/test_managed_ticker_resolution_fix002.py`, 20 tests (12
  functions; the invariant and the never-written test have 5 cases each).
- **Mutations** (`mutate_fix002.py` in the session scratchpad; each source is restored and checked
  by SHA-256): **10 of 10 caught** on the final bytes.

  | Mutation | Caught by |
  |---|---|
  | M1 the original defect: the short cut checks the static `TICKERS` only | the invariant |
  | M2 the registry dropped | company-name order (CANARABANK) |
  | M3 the managed list dropped | the invariant |
  | M4 invalid registry records dropped | the registry test (BROKENCO) |
  | M5 enabled entries only | the invariant (disabled TATAMOTORS: LLM called) |
  | M6 the managed list cached on the instance | the added-while-running test |
  | M7 a missing managed list seeded (`load_managed_tickers`) | the never-written test |
  | M8 an unusable registry names every ticker (`is_registered`) | the unusable-registry test |
  | M9 the company name not from `_company_name_for` | the invariant |
  | M10 an unreadable managed list logged at debug, not warning | the never-written test |

- **Focused:** `python -m pytest -q -p no:cacheprovider` over the new file,
  `tests/unit/test_ticker_resolution_shortcircuit.py`, `tests/unit/shared/test_instrument_identity_sa008.py`,
  `tests/unit/shared/test_decision_gate_sa003.py`, `tests/unit/test_company_name_cache.py`,
  `tests/integration/test_orchestrator.py` and `tests/unit/shared/test_error_capture_context.py`:
  **162 passed**. The older short-cut, SA-008 and SA-003 tests are unchanged.
- **Full suite:** `python -m pytest tests -q -p no:cacheprovider` gave **4055 passed, 12 skipped,
  1 failed** (12 min 34 s; 4036 + the 20 new = 4056). `data/`, `logs/` and `outputs/` were
  unchanged: 800 files, the same digest before and after.
  - **The one failure is the known Windows flake,** not FIX-002:
    `test_store_migration_sa009.py::test_rollback_refuses_a_quarantined_store_whose_bytes_changed`
    raised `PermissionError: [WinError 5] Access is denied` from `os.replace` in SA-009's
    `_write_lineage`. The SA-009 change 1 review recorded the same flake (I2) and routed it to
    SA-031. FIX-002 does not touch that module.
  - **Reruns:** the test alone passed 3 of 3. The whole file failed once more, then passed 3 of 3
    (22 passed each).
- **Guards:** `scripts/ci/check_broad_except.py` OK (154 grandfathered; no new broad except).
  `check_kt_docs` errors `[]` (420 links, PDF 34 pages, source
  `6ac7ccb4…`).

## Documentation

- **KT §4:** step 1 of the research flow, and a new "Ticker resolution (FIX-002)" paragraph after
  the owner's TMPV decision: the example, the new rule, what stays with SA-008, and the
  containment still to do.
- **Guide 02-G** (new): a managed list with TATAELXSI, TVSMOTOR and a disabled TATAMOTORS; each
  resolves to itself with no `Serper fallback` line or `ticker_resolution` row; free text still
  makes one call.
- **AGENTIC_DESIGN.md:** the `_resolve_ticker` row of the decision table.
- **The PDF** was rebuilt.
- **The landing commit needs a KT bump.** The header declares `0493f7c`, and
  `base_orchestrator.py` and `instruments.py`, both linked from the KT, change after it.

## Rollout

- After the fresh review: commit, KT bump, and push in a job-free window. No configuration
  changes.
- **Production check (read-only):** the next scheduled forecast or review logs
  `Resolved: X -> ticker='X'` for every managed ticker, with no `Serper fallback` line and no
  `ticker_resolution` LLM call for them. No data-health line names a ticker other than the
  scheduled one. The 16:30 review re-runs each enabled ticker's analysis, so it is the first
  full check.
- **Containment (needs the owner's authorisation after the deploy):** regenerate TATAELXSI's
  October envelope, so the rest of October is graded against its own analysis.
  - **Suggested route:** the manual re-forecast, in a job-free window:
    `python -m services.scheduler.run_schedule reforecast --ticker TATAELXSI --sector it_sector
    --reason "FIX-002 containment: the 1 Oct envelope was built from a TATAMOTORS analysis"`.
    It archives the superseded envelope first and prints the archive name. It replaces only the
    days after today; days already graded stay byte-identical.
  - **Before running it (read-only):** check that `reforecast_count` is below the cap
    (`RL_REFORECAST_MAX_PER_MONTH`, default 2) and that `RL_REFORECAST_ENABLED` is on. Otherwise
    it prints `[SKIP]` and changes nothing.
  - **Record:** the archive name it prints and the new run's id from the log.
  - The alternative, `POST /scheduler/forecast?ticker=TATAELXSI`, rebuilds the whole month's
    envelope. It was not traced here.
- **Until then:** TATAELXSI's October reviews grade Tata Elxsi's closes against the Tata Motors
  analysis. SA-003's gate rows mark each one, and SA-039's `observe` keeps the stored weights
  unchanged.

## Open limitations

- **Discovery's deep dive** (`core/discovery/deep_dive.py`) analyses candidate symbols that no list
  holds, so they still go to the LLM, which can rename them. That is outside the card, whose
  subject is scheduled tickers. SA-026's single sector definition is the place for it.
- **A torn read.** `save_managed_tickers` writes the file in place (pre-existing). A resolution
  that reads it mid-write gets an empty set, and that one run goes back to the LLM. It is now
  logged as a warning.
- **TVSMOTOR now resolves to itself,** priced from `TVSMOTOR.NS` by the default identity. Before,
  the LLM turned it into TVSMOTORS (the registry alias of the same listing), whose fundamentals
  asked `TVSMOTORS.NS` and came back empty (SA-045 holds that fetcher defect).

## Manifest and digests

- **Review input:** [FIX-002-manifest.json](FIX-002-manifest.json). The SHA-256 of its LF bytes is
  **`98ed116a1975cf81f6ca0e4e2790a44e3959142ca49657f9260ae92d2250cca8`**, and `kt_manifest.py verify`
  gives 8 files and 0 mismatches.
  - It lists the 8 files changed since `da66fee`: 3 code files, 1 new test file, and 4 documents
    including the PDF.
- **Excluded:** STATE.json, HANDOFF.md and this receipt. The FIX-002 card is unchanged.
- **Full diff** against `da66fee`:
  **`bc726da87998ed846dc909f5241ac350fc0608bd97fa90abed02e0a9042c0385`**, 31,829 bytes over 7 text
  files. The PDF is pinned by its blob, `a99a6350…`.
  - **To rebuild it:** take every manifest path except the PDF, sorted.
  - For a path tracked at `da66fee`, use `git diff --no-color --no-ext-diff da66fee -- PATH`.
  - For a new file, use `git diff --no-color --no-ext-diff --no-index -- /dev/null PATH`.
  - Concatenate the outputs.
