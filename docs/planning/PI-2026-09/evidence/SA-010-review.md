# SA-010 review receipt — sector benchmarks reach the technical-data calls

## Fresh-session review: ACCEPTED (2026-10-05)

- **What was reviewed:** [SA-010](../stories/SA-010.md), as described in the
  [implementation receipt](SA-010-implementation.md).
  - `settings.SECTOR_BENCHMARKS` names each sector's index, and `fetcher.sector_benchmark` gives
    any other sector the broad market, `^NSEI`.
  - `get_peer_correlation` has no default index. It pairs returns over common sessions, and an
    unmeasured correlation is `None` with the reason, not 0.0 / 1.0.
  - The bundle and the legacy builders pass the run's sector.
  - The change adds 45 tests, edits KT §4, guide case 02-B and the SA-026, SA-040 and SA-045
    cards, and rebuilds the PDF.
- **Context:** a fresh-session review in a new conversation, 5 Oct 2026, from about 22:32 IST.
  - It is not the conversation that implemented SA-010, and it did not read that chat.
  - It read the card, the receipt, REVIEW.md and the whole diff.
  - It traced every caller of the changed functions, the five orchestrators' sector keys, the
    legacy agents' sector strings, the data-health row writer, the decision gate's provenance
    reads and the logging setup.
- **Nothing** was committed, pushed, deployed or configured, and no production state was read.
  No probe made a network call: each one replaced `yfinance.download` with a fake.

### Review input verified

- `kt_manifest.py verify SA-010-manifest.json`: 14 files and 0 mismatches at the start. The
  manifest's LF SHA-256 is `911cc91e…`, as recorded.
- The reviewer's own script (`analysis_data/sa010/review/rv_digest.py`) checked the input:
  - it re-hashed every path with `git hash-object`, and all 14 blobs match;
  - it rebuilt the full diff by the receipt's recipe: `64bf34d6…`, 62,942 bytes, over 13 text
    files. The PDF blob was `2e63d954…` at the start.
- `git status` showed the 14 manifest paths, STATE, HANDOFF, the receipt and the manifest, and
  nothing else. The checkout was at `5772536`.
- `data/`, `logs/` and `outputs/` held 800 files with digest `76c155f8…` before the full suite and
  after it. That is the implementer's digest too.

### Contract checked

- **Every caller.** A grep over every file outside `analysis_data/` shows:
  - `get_technical_result` and `get_technical_context` are called only by
    `bundle_builder._fetch_technicals` and by `builder._build_pattern_analysis` and
    `_build_technical`;
  - `get_peer_correlation` is called only by `get_technical_result`;
  - `NIFTY_AUTO_TICKER` has no remaining reader. `ui_data.py` uses its own `^CNXAUTO` literals,
    a display path routed to SA-026.
- **Nothing reads the old output.** No code parses "Nifty Auto Correlation", the old reason "neutral
  0.0 / beta 1.0", or the removed `default` key.
- **The sector keys match.** The five orchestrators' `SECTOR_NAME` values are `automobile`,
  `banking_bfsi`, `it_sector`, `renewable_energy` and `generic`. They are exactly the keys of
  `SECTOR_BENCHMARKS`. `_run_unified` passes `self.SECTOR_NAME` (`base_orchestrator.py:578`).
- **The legacy pool.**
  - Each sector's technical or pattern agent comes from its registry, which passes the full key
    (`_S = "banking_bfsi"` and so on). The generic orchestrator passes `"generic"`.
  - The automobile orchestrator's `PatternAnalysisAgent` declares `""`, which `ContextBuilder`
    maps to automobile, as its MF-herding line already does (`builder.py:191`).
  - The agent classes that declare the short names `"bfsi"`, `"it"` and `"re"` are all
    non-technical (see I1).
- **The persisted result.** The data-health row stores each section's provenance as given
  (`data_health.py:204-209`, then `json.dumps`), so `benchmark` reaches the row. The decision gate
  reads the technicals' `status` and `symbol` (`base_orchestrator.py:681-682`) and has no key
  whitelist. Status rules did not change, so no gate outcome changes.
- **The log line reaches production.** `LOG_LEVEL` defaults to INFO, and `configure_logging` sets
  the root level. Earlier production checks read INFO lines (for example
  `[WeightAdapter] Proposal (not applied)`).
- **Freshness and issue time.** The download window is unchanged: from 282 days back to today,
  with today's bar excluded by yfinance's end-exclusive `end`.

### Independent adversarial examples

Scripts are in the ignored `analysis_data/sa010/review/`. The oracle in R1 and R3 is plain Python
arithmetic, with no numpy or pandas.

| Probe | Example | Result |
|---|---|---|
| R1 | **300 random frames shaped like yfinance 1.x output.** Columns are (Price, Ticker) for all 5 fields, tickers in yfinance's sorted order, rows the union of dates. Each frame has 35–319 sessions and random gaps of up to 8% in either series. In half of them the index's newest bar is missing. | Every measured result equals the plain-Python Pearson and beta over the common sessions. Every short one (under 30 paired returns) is `None` with its session count. |
| R2 | **The baseline module (git `5772536`, loaded in memory) beside the new one, on equal sessions.** 60 seeds, 31–399 sessions, an automobile stock through `get_technical_result`. | Text, status and reason are byte-identical on all 60. |
| R3 | **Edge shapes.** Both symbols dead (an empty frame); a dead index column (the 5 Oct probe's shape); a zero close; a single-level frame; exactly 30 paired returns from unequal lengths; a stock suspended for 15 sessions. | Both dead: both symbols named. Dead index: "benchmark ^CNXAUTO returned no price data". Zero close: finite numbers. Single-level frame: unavailable (I3). 30 returns: measured. Suspension: equals the oracle over the common sessions. |
| R4 | **8 sector keys through `get_technical_result`:** the five keys, plus `""`, `insurance` and `bfsi`. | Each makes one paired call with its own index and label. `""`, `insurance` and `bfsi` get `^NSEI` "Nifty 50 (broad market)" (`bfsi`: see I1). |
| R5 | **The original defect, reproduced.** HDFCBANK, with Yahoo answering `^NSEBANK` and not `^CNXAUTO`. MARUTI, with `^CNXAUTO` dead. | Baseline HDFCBANK: asks for `^CNXAUTO` and prints "Nifty Auto Correlation: 0.0 \| Beta: 1.0". New: asks for `^NSEBANK` and prints "Nifty Bank Correlation: 0.8384 \| Beta: 1.0597", with no reason and `benchmark: ^NSEBANK`. Baseline MARUTI: 0.0 / 1.0. New MARUTI: "Nifty Auto Correlation: unavailable \| Beta: unavailable (benchmark ^CNXAUTO returned no price data)", status `ok`, and the reason names it. |

### Tests

- **The new file:** 45 passed.
- **The original code.** The implementer's `swap_plugin.py` was read first; it writes only to the
  system temp directory. With `SA010_SRC=baseline`: **41 failed, 4 passed**, as recorded.
  - The full-bundle and routed-orchestrator tests fail on the baseline because of the defect
    itself: `[['HDFCBANK.NS', '^CNXAUTO']] == [['HDFCBANK.NS', '^NSEBANK']]`. The bundle and
    orchestrator signatures did not change, so this is not just the new keyword.
  - The dead-index tests fail on the baseline with a `TypeError` (the new `sector` keyword). R5
    reproduces that defect directly.
- **Independence.** The expected index table is written out by hand. Expected values come from
  numpy over the fixture's common sessions, never the fetcher's pandas code. R1 adds a plain-Python
  oracle on the real column layout.
- **Mocked boundaries.** The fake `yf.download` records every call. `_nse_ticker`, the symbol
  self-heal and `time.sleep` are patched, and SA-005's hermetic guard is active. The tests' fake
  paired frame has only `Close` columns. R1 and R2 used yfinance's full 5-field layout, and the
  results matched. No real API is reached.
- **Reviewer mutations** (`analysis_data/sa010/review/rv_mut_plugin.py`, in memory, against the new
  file, `test_data_health_contract.py` and `test_instrument_identity_sa008.py`): **8, of which 6
  caught.**

  | Mutation | Result |
  |---|---|
  | RM1 the prompt keeps "Nifty Auto" for every sector | caught (12) |
  | RM2 beta divides by the stock's variance | caught (3) |
  | RM3 an unmeasured benchmark makes the section `fallback` (D3 reversed) | caught (2) |
  | RM4 the `[technicals]` line only when measured | **survived** (L1) |
  | RM5 the empty-history result drops `benchmark` | **survived** (L1) |
  | RM6 gaps padded, as pandas 2.2's `pct_change` default did | caught (2) |
  | RM7 the reason drops the unmeasured correlation | caught (4) |
  | RM8 the window loses its 30-day pad | caught (1) |

### Findings

None is critical, high or medium.

| ID | Severity | Location | Evidence | Disposition |
|---|---|---|---|---|
| L1 | Low (tests) | `tests/unit/shared/test_sector_benchmark_sa010.py` | RM4 and RM5 pass every test. The log test covers only a measured correlation. Yet the production check counts the "unavailable" lines for automobile and renewable energy, and D7 promises one line per call. The code does write that line (R5's run and `fetcher.py:721-726` log before the branch). | Routed: SA-031 card note (two tests). The first production check also observes it directly. |
| I1 | Info (inference from code) | `services/data/context/builder.py:143-148`, `fetcher.py:276-284` | `sector_benchmark` knows only the full keys. Some legacy agent classes declare `"bfsi"`, `"it"` or `"re"` (for example `banking_bfsi/agents/fundamentals.py:17-18`), and `ContextBuilder` maps only `""`. R4: `bfsi` gets `^NSEI`. No technical agent declares a short name today, so no stock is affected. | Routed: SA-026 card note (one sector key per sector in the lens). |
| I2 | Info (production-check wording) | `settings/base.py:870` | `UNIFIED_ANALYST_FALLBACK_LEGACY` defaults to on. A run whose unified analyst fails falls back to the legacy agents. For automobile, renewable energy and generic stocks, that run logs a second `[technicals]` line naming the same index. | Guide 02-B and STATE's `after_deploy` say so. |
| I3 | Info (already a receipt limitation) | `fetcher.py:318` | If yfinance ever returned a single-level frame for a paired download, both symbols would be reported as "returned no price data". That names a shape problem as missing data. It is conservative: nothing is measured. | No action. |

### Decisions

| Decision | Verdict |
|---|---|
| D1 no proxy for `^CNXAUTO` / `^CNXENERGY` | **Upheld.** The card asks for the configured benchmark and a restorable mapping. A proxy is a new data choice that needs its own evidence (SA-026). The honest result until then is "unavailable" (R5). |
| D2 generic policy `^NSEI` "Nifty 50 (broad market)" | **Upheld.** The card requires a deliberate generic policy. The label says what it is, and no sector gets another sector's index (R4). |
| D3 status stays the stock's own | **Upheld.** The reason names the gap, as SA-002 did. Making technicals `fallback` would turn every automobile and renewable-energy gate to abstain because of Yahoo's dead index, which is a gate decision outside this card. RM3 is caught. |
| D4 returns paired over common sessions | **Upheld.** It equals the baseline on equal sessions (R2), matches the oracle on unequal ones (R1, R3), and does not depend on pandas' fill default (RM6 caught). |
| D5 `""` means automobile in `ContextBuilder` only | **Upheld.** It matches `builder.py:191`. `sector_benchmark("")` gives the generic policy. |
| D6 sector and index are required | **Upheld.** There are no other callers, and both `TypeError` tests pass. |
| D7 one INFO line per call | **Upheld.** INFO reaches the production console. The unavailable path is unpinned (L1), and a legacy fallback adds a line (I2). |
| D8 SA-002 `default` key removed | **Upheld.** It has no reader (grep). The SA-045 card is updated. |

### Commands and results

Environment: Windows 11, the project venv `.stockai` (Python 3.13.11, pandas 3.0.2, numpy 2.4.4,
yfinance 1.3.0), with SA-005's hermetic guard.

| Check | Command | Result |
|---|---|---|
| Manifest | `python scripts/docs/kt_manifest.py verify docs/planning/PI-2026-09/evidence/SA-010-manifest.json` | 14 files, 0 mismatches, `911cc91e…` |
| Diff | `python analysis_data/sa010/review/rv_digest.py . <manifest> <out>` | `64bf34d6…`, 62,942 bytes; 14 blobs equal |
| New tests | `python -m pytest tests/unit/shared/test_sector_benchmark_sa010.py -q -p no:cacheprovider` | 45 passed |
| The original defect | the same with `SA010_SRC=baseline PYTHONPATH=analysis_data/sa010 … -p swap_plugin` | 41 failed, 4 passed |
| Mutations | `RV_MUT=RM1…RM8 PYTHONPATH=analysis_data/sa010/review … -p rv_mut_plugin` (3 files) | 6 of 8 caught |
| Probes | `python analysis_data/sa010/review/rv_probes.py .` and `rv_baseline_dead.py .` | R1–R4: 0 failures; R5 as above |
| Focused | the receipt's 14 files (at their real paths) | **548 passed** |
| Full suite | `python -m pytest tests -q -p no:cacheprovider` | **4156 passed, 12 skipped, 0 failed** (6 min 30 s, about 22:53–23:00 IST); `data/`, `logs/` and `outputs/` unchanged (800 files, `76c155f8…`), and the reviewed source bytes equal before and after |
| Broad-except guard | `python scripts/ci/check_broad_except.py` | OK (154 grandfathered) |
| KT check | `python scripts/docs/check_kt_docs.py` (with `PYTHONPATH=analysis_data/kt_docs_deps`) | Before the edits: errors `[]`, 434 links, 35 pages, source `0e10594c…` (the manifest's KT). After the edits and the rebuild: errors `[]`, 436 links, 35 pages, source `4f10be99…`, PDF blob `77ed4b93…` |

Not exercised: a real Yahoo call (the implementer's 5 Oct probe is the only measurement of which
indexes have data), the LLM's reading of an "unavailable" line, and a production run.

### Review edits (documentation only)

- **KT §4:** the heading's status, the "Current gap" sentence and the PI-target row now say
  accepted, not yet committed or deployed. The row links this receipt. The PDF was rebuilt.
- **Guide 02-B:** the status, and I2's sentence about a legacy-fallback run logging a second line.
- **SA-026 card:** the I1 bullet. **SA-031 card:** the L1 section, which is not a manifest file.
- `verify SA-010-manifest.json` now mismatches exactly the KT, the PDF, the guide and the SA-026
  card. No code or test byte changed.

### Acceptance and what remains

| Criterion | Result |
|---|---|
| BFSI/IT/renewables do not implicitly call the automobile index | **Met.** Recorded calls through the bundle, the routed orchestrator and the legacy agents; R4; R5 (baseline asks `^CNXAUTO` for a bank, new asks `^NSEBANK`); RM1 caught. |
| An unavailable benchmark is missing evidence, not beta 1 / correlation 0 | **Met.** `None` with the cause in the prompt, the reason and the log line; R3, R5; RM7 caught. |
| Auto behaviour equivalent with sufficient data | **Met.** R2: 60 of 60 byte-identical against the baseline module. |
| Provider-call arguments for every sector and the generic routing | **Met.** Tests and R4. |
| Unequal sessions, short history, all-null returns, unavailable benchmark | **Met.** Tests; R1 and R3 against a plain-Python oracle. |
| Deterministic fixtures, blocked transports | **Met.** |

- **Verdict: ACCEPTED** for the reviewed input (`911cc91e…`, diff `64bf34d6…`) plus the
  documentation-only edits above. STATE: SA-010 `done`, production verification
  `pending_deployment`.
- **Follow-ups:** L1 is on the SA-031 card and I1 on the SA-026 card. The proxy index for automobile
  and renewable energy stays with SA-026 (D1).
- **To land it, at the owner's word:**
  - commit the manifest paths, the three evidence files, STATE and HANDOFF;
  - then a KT bump: the KT links `fetcher.py`, which changes after the declared `110288e`;
  - push in a job-free window (00:10–06:20 IST is safest). No configuration change.
- **Production check (read-only), at the first 16:30 review after the deploy:**
  - one `[technicals]` line per analysis, plus one for any run that fell back to the legacy agents;
  - banking `^NSEBANK`, IT `^CNXIT` and generic `^NSEI`, each with a correlation;
  - automobile `^CNXAUTO` and renewable energy `^CNXENERGY` "unavailable — benchmark … returned no
    price data" while Yahoo has no data for them;
  - yfinance's `^CNXAUTO` ERROR lines fall from 54 to about 9, and about 12 `^CNXENERGY` lines
    appear;
  - the health rows' technicals provenance names the same index.
- **Next story:** SA-038, by the owner's sequencing of 2 Oct. It has no dependencies, and it starts
  in a new conversation.
