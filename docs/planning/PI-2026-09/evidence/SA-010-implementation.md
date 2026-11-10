# SA-010 implementation receipt — sector benchmarks reach the technical-data calls

- **Story:** [SA-010](../stories/SA-010.md), audit finding F20.
- **Context:** implemented on 5 Oct 2026, about 20:55–21:45 IST, in a **new conversation** opened
  with "continue". A same-conversation self-review was done. It is not the fresh review, which
  needs another new conversation. STATE: `review_required`.
- **Baseline:** `5772536` (the KT bump after FIX-003's commit). The working tree also carried the
  uncommitted FIX-003 push record and the FIX-002/FIX-003 production checks in STATE and HANDOFF,
  which this phase keeps.
- **Nothing** was committed, pushed, deployed or configured, and no production state was read.
  Two local checks used data already on disk or public: a count of the `^CNXAUTO` lines in the
  ignored 2 Oct review log, and one read-only probe of public Yahoo data (below). Both wrote only
  to ignored `analysis_data/`.

## What it does, in one example

HDFCBANK, analysed by the banking graph:

- **Before:** the bundle passed only the ticker. `get_technical_result` called
  `get_peer_correlation(ticker)`, whose default index was `^CNXAUTO`. Yahoo had no data for it
  (the 2 Oct review logged "possibly delisted" for it 18 times, 3 lines each). So the code
  substituted correlation 0.0 and beta 1.0, and the prompt read "Nifty Auto Correlation: 0.0 |
  Beta: 1.0". The banking prompt asks for beta against Nifty Bank. The stored prompts were not
  read; the text follows from the code and the logged failures.
- **After:** the bundle passes `banking_bfsi`, and the call asks Yahoo for
  `["HDFCBANK.NS", "^NSEBANK"]`. The prompt reads "Nifty Bank Correlation: … | Beta: …", the
  section's provenance says `benchmark: ^NSEBANK`, and the run logs
  `[technicals] HDFCBANK sector=banking_bfsi benchmark=^NSEBANK (Nifty Bank): correlation …`.
- **For an automobile stock today:** Yahoo has no data for `^CNXAUTO` (probe, 5 Oct). The prompt
  reads "Nifty Auto Correlation: unavailable | Beta: unavailable (benchmark ^CNXAUTO returned no
  price data)", and the section's reason says the same. No 0.0 or 1.0 is shown.

## The change

Five code files, 3 test files and 6 documents (manifest below).

- **`src/backend/shared/config/settings/base.py`:** `NIFTY_AUTO_TICKER` is removed (its only user
  was the old default argument). New `SECTOR_BENCHMARKS`, as (symbol, prompt label):
  - `automobile` `^CNXAUTO` "Nifty Auto";
  - `banking_bfsi` `^NSEBANK` "Nifty Bank";
  - `it_sector` `^CNXIT` "Nifty IT";
  - `renewable_energy` `^CNXENERGY` "Nifty Energy";
  - `generic` `^NSEI` "Nifty 50 (broad market)".

  The four sector symbols are the ones the regime detector and the technical prompts already
  name.
- **`core/intelligence/algorithms/indicators/fetcher.py`:**
  - `sector_benchmark(sector)` returns the sector's entry. Anything else (`generic`, `""`, an
    unregistered name, a misspelling) gets the `generic` entry. It never returns another
    sector's index.
  - `get_peer_correlation(ticker, index_ticker, period_days=252)`: **the index has no default.**
    - It pairs returns over the sessions both series have a close for (`dropna`, then
      `pct_change`).
    - Measured: `{"benchmark", "correlation", "beta", "sessions"}`.
    - Not measured: `correlation` and `beta` are `None`, and `unavailable` says why. The causes
      are no data for either symbol, fewer than 30 paired returns (`MIN_CORRELATION_SESSIONS`,
      the old threshold), a flat series, a non-finite result, or a failed download.
    - The SA-002 key `default: True`, with its 0.0 / 1.0, is gone.
  - `get_technical_result(ticker, *, sector)` and `get_technical_context(ticker, *, sector)`:
    `sector` is a **required keyword**.
    - The reason names an unmeasured correlation ("Nifty Auto correlation unavailable: …").
    - The provenance carries `benchmark`.
    - One INFO line `[technicals] <ticker> sector=<sector> benchmark=<index> (<label>): …` per
      call.
    - The status rules are unchanged.
  - `_format_technicals`: the line is `"{label} Correlation: {c} | Beta: {b}"`, or
    `"{label} Correlation: unavailable | Beta: unavailable ({why})"`. For automobile with data it
    is byte-identical to the old line.
- **`services/data/context/fetch_result.py`:** `FetchResult.benchmark`, optional. `provenance()`
  adds it when set, as SA-008 did with `symbol`.
- **`services/data/context/bundle_builder.py`:** `_fetch_technicals(query, sector)`, and
  `build_sector_bundle` passes its sector.
- **`services/data/context/builder.py`** (the legacy worker pool, used only when the unified
  analyst fails): `_build_pattern_analysis` and `_build_technical` pass `_benchmark_sector()`.
  That is the agent's own sector, or `automobile` for an empty one (D5).

## Every path that reaches the call

| Path | Sector it carries | Index after SA-010 | Test |
|---|---|---|---|
| Scheduled forecast/review and API analysis → `sector_router` / `SectorRegistry` → orchestrator `_run_unified` → `build_sector_bundle(query, SECTOR_NAME)` → `_fetch_technicals` | the orchestrator's `SECTOR_NAME`; `insurance` and other unregistered sectors route to `generic` | the sector's, `^NSEI` for generic | `TestScheduledAndApiPathsCarryTheSector` (5 sector keys through the real router and `_run_unified`) |
| Legacy pool, automobile orchestrator's `PatternAnalysisAgent` (declares no sector) → `_build_pattern_analysis` | `""` → automobile | `^CNXAUTO` | `TestLegacyWorkerPoolCarriesTheSector` |
| Legacy pool, automobile registry `UniversalAgent("pattern_analysis", sector="automobile")` | automobile | `^CNXAUTO` | same |
| Legacy pool, renewable-energy `technical` → `_build_technical` | renewable_energy | `^CNXENERGY` | same |
| Legacy pool, generic `technical` → `_build_technical` | generic | `^NSEI` | same |
| Legacy pool, banking and IT `pattern_analysis` → `_build_bfsi_…` / `_build_it_pattern_analysis` | (search-only builders) | none: they fetch no index, before or after | same |

`get_technical_context` and `get_technical_result` have no other callers. API routes call neither.
The dashboard's index tiles and the regime detector use their own symbols (open limitations).

## Acceptance criteria

| Criterion | Result | Evidence |
|---|---|---|
| BFSI/IT/renewables do not implicitly call the automobile index | Met | Recorded provider arguments for every sector, through `_fetch_technicals`, the full bundle, the routed orchestrator and the legacy agents. No non-automobile path downloads `^CNXAUTO`. The index and the sector have no default (`TypeError` tests). |
| An unavailable benchmark is missing evidence, not a measured beta=1 / correlation=0 | Met | `correlation`/`beta` are `None` with `unavailable`. The prompt says "unavailable" with the cause, the reason names it, and the provenance names the index. Tested for a dead index, short history, null or flat returns and a failed download. |
| Auto behaviour equivalent with sufficient data | Met | numpy-derived values and the old call window in `test_auto_with_sufficient_data_is_the_measured_value`. The probe ran the original `fetcher.py` beside the new one: correlation and beta identical on 10 of 10 seeds, and the automobile prompt text byte-identical, with the same status and reason. |
| Provider-call arguments for every sector and the generic routing | Met | Each sector, plus `""`, `insurance`, `pharma` and `Automobile` (generic) |
| Unequal sessions, short history, all-null returns, unavailable benchmark | Met | `TestMeasurement`, `TestUnavailableBenchmark` |
| Deterministic fixtures, blocked transports | Met | A fake `yfinance.download` records every call. The closes come from seeded numpy, with no real yfinance call. SA-005's hermetic guard fails any connection. |

**The independent invariants.** The test file writes out the expected index for every sector by
hand. It does not read them from settings. Every expected correlation and beta is computed with
numpy (`np.corrcoef`, and `np.cov` / `np.var` with ddof 1) over the sessions both fixtures share.
It never uses the fetcher's pandas code. The unequal-sessions fixture follows the probe's shape:
the index misses every 9th session and the newest one.

## Decisions for the reviewer

- **D1. No substitute index for the two that have no data.** `^CNXAUTO` and `^CNXENERGY` answered
  nothing on 5 Oct (probe). The card asks for the configured benchmark to be passed and for the
  prior mapping to be restorable. A proxy (an ETF that tracks Nifty Auto, or another energy index)
  would be a new data choice with its own evidence. It is routed to SA-026, whose lens names the
  benchmark. Until then, automobile and renewable-energy technicals say "unavailable".
- **D2. The generic policy is the broad market, `^NSEI`, labelled "Nifty 50 (broad market)".** It
  applies to `generic` and to any sector without its own entry, including an empty or misspelt
  one. The regime detector already falls back to `^NSEI`, and SA-026's default lens names "market
  benchmark". The generic prompts mention no index, so the label says what it is.
- **D3. The section's status stays the stock's own.** The index is context for the stock's price
  history. A missing correlation is named in the reason, as SA-002 did, and does not make the
  section `fallback`. Otherwise every automobile and renewable-energy analysis would turn the gate
  to `abstain` (technicals is essential) because of Yahoo's dead index. That gate change is beyond
  this card.
- **D4. Returns are paired over common sessions.** With equal sessions this is the old
  calculation exactly. With unequal ones, each return spans the same two sessions for both series.
  It no longer depends on pandas' `pct_change` fill default: pandas 2.2 pads a gap, pandas 3 does
  not, and `requirements.txt` allows `pandas>=2.2`. Under 2.2 the old code paired an index's padded
  zero return with the stock's real one.
- **D5. An empty legacy sector means automobile, inside ContextBuilder only.** The automobile
  orchestrator's 9 agent classes are the only agents that declare no sector. Every other sector's
  agents declare theirs. `ContextBuilder.build` already documents `""` as automobile.
  - Why not give `PatternAnalysisAgent` a sector: that would also turn on its RAG
    prompt-enhancement lazy-load (`base_agent.py`, used when RAG is enabled).
  - `fetcher.sector_benchmark("")` itself gives the generic policy, never automobile.
- **D6. Required arguments instead of defaults.** A caller that forgets the sector or the index
  now fails with `TypeError` rather than silently using an index.
- **D7. An INFO log line per call** carries the ticker, sector, index and outcome, for the
  production check ("correlated fetch logs").
- **D8. Removing the SA-002 key `default`.** Its only reader was `get_technical_result`'s reason,
  and no test asserted it. The SA-045 card's note is updated: a factor must read `unavailable`.

## Checks

- **Environment:** Windows 11, the project venv `.stockai` (Python 3.13.11, pandas 3.0.2,
  yfinance 1.3.0), and the SA-005 hermetic guard.
- **New tests:** `tests/unit/shared/test_sector_benchmark_sa010.py`, **45 tests**: 34 on the call
  arguments and paths, 11 on the measurement and the unavailable index.
  - Command: `python -m pytest tests/unit/shared/test_sector_benchmark_sa010.py -q -p no:cacheprovider`.
- **The original defect:** the HEAD `fetcher.py`, `bundle_builder.py` and `builder.py` were loaded
  in memory (`analysis_data/sa010/swap_plugin.py`, `SA010_SRC=baseline`; no checkout edit).
  **41 of the 45 fail.** The 4 that pass are the paths that were already right: the two
  automobile legacy agents measure against `^CNXAUTO`, and the banking and IT legacy chart
  builders fetch no index.
- **Mutations** (the same plugin, `SA010_SRC=M1…M9`, one at a time on the working-tree source):
  **9 of 9 caught.** Each run's failures:

  | Mutation | Failures |
  |---|---|
  | M1 an unregistered sector falls back to the automobile index | 4 (`""`, `insurance`, `pharma`, `Automobile`) |
  | M2 the bundle stops passing its sector | 16 (the 4 non-automobile sectors × 4 bundle and orchestrator tests) |
  | M3 a missing measurement shown as 0.0 / 1.0 | 6 (short history ×2, null or flat ×3, failed download) |
  | M4 returns not paired over common sessions | 1 (unequal sessions) |
  | M5 the 30-return threshold off by one | 1 (31 closes, 30 returns) |
  | M6 the automobile agents' empty sector not mapped | 1 (the automobile orchestrator's agent) |
  | M7 the prompt prints the missing values | 3 |
  | M8 the provenance stops naming the index on a usable section | 18 |
  | M9 the legacy `technical` builder hard-codes automobile | 2 (renewable energy, generic) |

- **Focused:** the new file, `test_data_health_contract.py`, `test_data_health_record.py`,
  `test_decision_gate_sa003.py`, `test_decision_gate_learning_sa003.py`,
  `test_instrument_identity_sa008.py`, `test_bank_statement_fix003.py`, `test_bundle_builder.py`,
  `test_bundle_builder_sectors.py`, `test_unified_analyst.py`, `test_unified_e2e_parity.py`,
  `test_regime.py`, `tests/integration/test_orchestrator.py` and
  `tests/integration/test_data_fetchers.py`: **548 passed** (1 min 42 s).
- **Full suite:** `python -m pytest tests -q -p no:cacheprovider` gave **4156 passed, 12 skipped,
  0 failed** (11 min 6 s; 4111 + the 45 new). It ran on the final source bytes: the SHA-256 of the 5
  code files and the new test file were checked before and after. `data/`, `logs/` and `outputs/` were
  unchanged: 800 files, digest `76c155f8…` before and after. None of the 30 warnings comes from a
  changed module.
- **Guards:** `scripts/ci/check_broad_except.py` OK (154 grandfathered; the one broad except in
  `get_peer_correlation` logs, as before). `check_kt_docs`
  errors `[]` (432 links, 85 linked sources, PDF 35 pages, source `0e10594c…`).

## The probes (read-only)

- **The 2 Oct review log** (the ignored `analysis_data/fix003/deploy/review_20261002.log`) has 36
  lines naming `^CNXAUTO`. With its blank "1 Failed download" lines that makes 54 ERROR lines, 3
  for each of the 18 analyses, all for the window 2025-12-24 → 2026-10-02. That is
  `get_peer_correlation`'s 282 days. The analyses were 3 automobile, 5 banking, 4 IT, 4
  renewable-energy and 2 generic.
- **Yahoo, 5 Oct about 21:00 IST** (`analysis_data/sa010/probe_benchmarks.py`, public data,
  yfinance 1.3.0, window 2025-12-27 → 2026-10-05):

  | Symbol | Answer |
  |---|---|
  | `^CNXAUTO` | no data ("possibly delisted") |
  | `^CNXENERGY` | no data ("possibly delisted") |
  | `^NSEBANK`, `^CNXIT`, `^NSEI` | 188 sessions each, newest 2026-10-01 |
  | `MARUTI.NS`, `HDFCBANK.NS` | 194 rows (193 non-null in a paired download), newest 2026-10-02 |

  - A paired download of `MARUTI.NS` with `^CNXAUTO` gives a `^CNXAUTO` column with 0 values.
  - `HDFCBANK.NS` with `^NSEBANK` gives 188 common sessions, so sessions really are unequal.
  - Yahoo's search lists `^CNXAUTO` as "NIFTY AUTO", and Nifty Auto ETFs (`AUTOBEES.NS`,
    `AUTOIETF.NS`); no proxy was evaluated.
- **Automobile equivalence** (`analysis_data/sa010/probe_auto_equivalence.py`): the original and
  new modules were run on the same fake data.
  - Correlation and beta were identical on 10 of 10 seeds (299 paired returns each).
  - The automobile prompt text was byte-identical, with status `ok` and reason `None` for both.
  - For a bank, the original asked for `^CNXAUTO` and printed "Nifty Auto Correlation"; the new
    code asks for `^NSEBANK`.
  - For a dead `^CNXAUTO`, the original printed "0.0 | Beta: 1.0"; the new code prints
    "unavailable" and the cause.

## Documentation

- **KT §4:** a new "Sector benchmarks (SA-010)" paragraph after FIX-003's example. It covers the
  measured cause, the table, the generic policy, the missing-evidence rule, the provenance and log
  line, and the 5 Oct probe. The "Current gap" sentence and the PI-target row now name SA-010 as
  implemented, with its review pending.
- **Guide 02-B:** the sector index per stock (HDFCBANK, INFY, TVSMOTOR, STARHEALTH), "unavailable"
  instead of 0.0 / 1.0, and the log and provenance check.
- **Routed notes:**
  - SA-026: the table it absorbs, the two indexes without data, and the regime and dashboard
    copies.
  - SA-040: the change in index noise, with `^CNXENERGY` to seed.
  - SA-045: the new correlation contract.
- **The PDF** was rebuilt (source `0e10594c…`).
- **The landing commit needs a KT bump.** The KT now links `fetcher.py`, which changes after the
  declared `110288e`.
- **Not changed:** `docs/AGENTIC_DESIGN.md` describes the automobile agent's Nifty Auto
  correlation, which is still accurate. `docs/RL_DESIGN.md`'s table is the regime detector's,
  which is unchanged.

## Rollout

- After the fresh review: commit, KT bump and push at the owner's word, in a job-free window
  (00:10–06:20 IST is the safest). Avoid 16:25–17:15. No configuration change.
- **Production check (read-only), at the first 16:30 review after the deploy.** With the 2 Oct mix:
  - one `[technicals]` line per analysed ticker;
  - banking lines name `^NSEBANK`, IT `^CNXIT` and generic `^NSEI`, each with a correlation;
  - automobile lines name `^CNXAUTO` and renewable-energy lines `^CNXENERGY`, each "unavailable —
    benchmark … returned no price data" while Yahoo has no data for them;
  - yfinance's `^CNXAUTO` ERROR lines fall from 54 to about 9 (3 automobile analyses × 3), and
    about 12 `^CNXENERGY` lines appear (4 × 3);
  - the data-health rows' `technicals` provenance names the same index.
- **Rollback:** revert the commit. It restores the old mapping, the automobile index for every
  sector, with its neutral substitute named in the reason. No stored data needs changing. Health
  rows written meanwhile carry one extra provenance key, which no reader requires.

## Open limitations

- **Automobile and renewable-energy stocks have no correlation or beta** until an index with data
  is chosen (D1, SA-026). Their prompts now say so instead of showing a neutral number. The
  automobile unified prompt still asks for "relative strength vs Nifty Auto". The LLM must now
  score without it, and the prompts' "no supporting data → 0.5" rule (SA-045/SA-046) still applies.
- **Other users of the same symbols, outside this card** (routed to SA-026):
  - the regime detector's `REGIME_SECTOR_TICKERS`, which for automobile and renewable energy
    silently uses Nifty 50's RSI;
  - the dashboard's index tiles and its "Nifty Auto" sparkline in `ui_data.py`, which are display
    paths.
- **yfinance's own ERROR lines** for a dead index stay; only which analyses produce them changes
  (SA-040).
- **If Yahoo returned a single-level frame** for a paired download, both symbols would be reported
  as absent, so nothing is measured. That is conservative.
- The 2 Oct "provenance unknown" rows and the SA-003 enforce decision are unaffected. Technicals'
  status rules did not change.

## Manifest and digests

- **Review input:** [SA-010-manifest.json](SA-010-manifest.json). The SHA-256 of its LF bytes is
  **`911cc91e57fc81675eaa0ef1b4f8f8582ff5333b1c86768f1dac947d9daf49ad`**, and `kt_manifest.py verify` gives 14 files and 0 mismatches.
  - It lists the 14 files changed since `5772536`: 5 code files, 3 test files (1 new) and 6
    documents including the PDF.
- **Excluded:** STATE.json, HANDOFF.md and this receipt.
- **Full diff** against `5772536`: **`64bf34d68b59fa809d8378fbb56b1d3540ac85f96015a2a37b265ec789cb3dae`**, 62,942 bytes over 13 text files. The PDF is
  pinned by its blob, `2e63d954…`.
  - **To rebuild it:** take every manifest path except the PDF, sorted.
  - For a path tracked at `5772536`, use `git diff --no-color --no-ext-diff 5772536 -- PATH`.
  - For a new file, use `git diff --no-color --no-ext-diff --no-index -- /dev/null PATH`.
  - Concatenate the outputs; `analysis_data/sa010/diff_digest.py` does exactly this.
