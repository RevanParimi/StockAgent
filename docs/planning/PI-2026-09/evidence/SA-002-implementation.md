# SA-002 implementation receipt — data-health records describe usable evidence

> **ACCEPTED on 2026-09-26 by a fresh-session re-review** of review input `c88edda5…` (full diff
> `dc7e850b…`, rework diff `56544c46…`). SA-002 is `done`; it is not committed or deployed, and
> `production_verification` is `pending_deployment`. See [the review](SA-002-review.md).

- **Story:** [SA-002](../stories/SA-002.md). Audit finding F07 in the
  [September audit](../../../audit/2026-09-10-repository-production-review.md);
  historical card B6 and §15.1 of the
  [Three Loops spec](../../../superpowers/specs/2026-08-24-three-loops-pi-design.md).
- **Phase:** implementation, one conversation, 2026-09-26 about 10:24–11:20 IST.
  This includes a same-conversation self-review, which is **not** the fresh-session review.
  STATE: `review_required`.
- **Baseline:** HEAD `103f2b8171c0d6365525f9450d41091306ebf22c`, plus the
  accepted and still uncommitted SA-001 worktree (review input `2ded4b43…`). At
  the start, `kt_manifest.py verify SA-001-manifest.json` showed mismatches only
  in the four docs the SA-001 review edited. No SA-039 production check was due
  (P1 is Mon 28 Sep 17:00 IST).
- **Review input:** [SA-002-manifest.json](SA-002-manifest.json), regenerated
  by the rework below. The first review's input is preserved, byte for byte,
  as [SA-002-manifest-review1.json](SA-002-manifest-review1.json) (`4d8968fd…`).
  The digests, and how to diff against the baseline and against the first
  review's input, are in "Rework" and "Manifest and digest" below.
- **Rework:** a new conversation on 2026-09-26, about 20:50–21:30 IST, after
  the fresh review [requested changes](SA-002-review.md). Scope: exactly M1, M2
  and I1. STATE: `review_required` again; a fresh re-review signs off.

## Rework after the fresh review (2026-09-26)

- **Context.** This is a new conversation. It is neither the implementing one
  nor the reviewing one. No SA-039 production check was due (P1 is Mon 28 Sep
  17:00 IST). STATE was set to `in_progress` before any edit.
- **Starting point.** `kt_manifest.py verify SA-002-manifest.json` showed
  exactly the five expected mismatches: the review's status wording in
  `CODEBASE.md`, ARCHITECTURE, TEAM_TESTING_GUIDE, the KT and the PDF. No code
  or test file had changed since the review.

### M1: the tests no longer depend on the weekday

**Example.** Run the suite on Monday 28 Sep. The fake "fresh" price series is
asked to end on Sunday 27 Sep. With pandas 3.0.2,
`bdate_range(end=<Sat or Sun>, periods=300)` returns 299 dates, and
`periods=1` returns none. The fixture then raised inside the fake download, so
the healthy technicals read `empty` and five tests failed. They had passed on
the Saturday the suite was written.

- **Fix, in `tests/unit/shared/test_data_health_contract.py`:**
  - `_bars` rolls its end date back to the last session
    (`pd.offsets.BDay().rollback`) before it builds 300 bars. A fixture date on
    a weekend now means what a market can produce: the newest bar is the Friday
    before.
  - The healthy-integration expectation (the review's line 568) uses a plain
    Python `_last_session`, a formulation independent of pandas.
  - `Market.today` makes the "fresh" default (yesterday) explicit, so a test
    can move it.
- **Guard: `TestFixturesHoldOnEveryWeekday`,** 14 tests over a fixed week (Mon
  21 to Sun 27 Sep 2026), not over the day the suite runs:
  - `_bars` holds 300 unique, increasing weekday bars that end on
    `_last_session(end)`, for each of the 7 end dates;
  - technicals and valuation run as if on each of those 7 days. Fresh bars
    read `ok`, with `as_of` the last session before that day, and 30-day-old
    bars read `stale`.
  - Only `fetch_result.date` is pinned. That is the one clock
    `is_stale` reads; valuation's own `today` only shapes search-query text.
    Nothing process-wide is replaced (the review discarded a global shim for
    that reason).
- **Evidence: the whole file, as if run on 7 consecutive days.**
  `analysis_data/sa002/rework/sweep.py` copies the file with `TODAY` set to each
  day, pins the same clock, and runs it with the shared `tests/conftest.py` and
  the network guard.

  | Run day | This rework | The reviewed `_bars` body reinstated |
  |---|---|---|
  | Sun 27 Sep | 155 passed | 9 failed: technicals, valuation, healthy integration, plus the guard |
  | Mon 28 Sep | 155 passed | 11 failed: the same set, plus the guard |
  | Tue 29 Sep | 155 passed | 7 failed: the 30-day technicals and valuation cases, plus the guard |
  | Wed 30 Sep – Sat 3 Oct | 155 passed each | 5 failed each: **the guard only** |

  The control reproduces the review's weekday table: the original tests fail
  only on Sundays, Mondays and Tuesdays. The new guard fails on **every** run
  day, so it would have caught M1 on the day the suite was written. 0 connections
  were blocked in all 14 runs.

### M2: a listed quarter without figures is not verified

**Example (the review's R2).** yfinance lists the quarter ended 27 Aug, but
its revenue and operating income are NaN.

- **Before:** fundamentals `ok`, `as_of` 2026-08-27, no reason. The prompt shows
  `₹nanCr`.
- **Now:** `fallback`, `as_of` 2026-05-28, reason "newest quarter 2026-08-27 has
  no figure for: revenue, operating_income; newest fully reported quarter
  2026-05-28". The prompt text is byte-identical. The row reads `degraded`,
  with `essential_unusable == {fundamentals: fallback}`.

The rules, in `services/data/fetchers/fundamentals.py`:

- `_is_reported(value)`: a figure is a finite number. NaN, `None` (which
  `_safe_float` renders as 0.0) and ±infinity are not figures.
- `get_financials` adds the key `missing_values`, mapping each *present* row to
  the quarter ends where it has no figure. Absent rows stay in
  `missing_rows`, as before. `as_of` is now the newest quarter in which every
  present row has a figure, or `None` if no quarter does. For every statement
  without blanks it is unchanged.
- `get_fundamentals_result`:
  - absent rows, or a blank *newest* listed quarter, give `fallback`, naming
    both;
  - otherwise the freshness bound can give `stale`;
  - otherwise `ok`. A blank *older* quarter is named in the reason and does
    not change the status, as the review specified.
- **Tests:**
  - 8 parametrized producer cases: the newest quarter entirely NaN, revenue
    NaN, operating income NaN, revenue `None`, revenue infinite, the newest
    two NaN, no quarter with figures, and only an older quarter NaN.
    - Each asserts the status and the `as_of` implied by the fixture.
    - Each also asserts that every blank quarter the section reads is named in
      the reason. Only the newest `FINANCIALS_LOOKBACK_QUARTERS` (4) are read.
  - 1 end-to-end case: bundle, record, report payload and DB row.
- **Mutations** (`analysis_data/sa002/rework/pinday.py`, applied at runtime; no
  source edited):

  | Mutation | Caught by |
  |---|---|
  | The reviewed behaviour (no `missing_values`; `as_of` the newest listed quarter) | 9 tests: all 8 cases and the end-to-end case |
  | `missing_values` dropped, `as_of` fix kept | the same 9 |
  | Only NaN counts as missing (`None` becomes 0.0, infinity passes) | 2 tests: the `None` and infinite cases |

- **Byte identity.** `analysis_data/sa002/rework/characterize_nan.py` renders 13
  statements through the HEAD `fundamentals.py` (`git show 103f2b8:…`, loaded
  as its own module) and through the worktree. Result: 13 of 13 texts are
  identical. The 13 cover the healthy statement, a revenue row absent, the
  eight blank cases above, the previous or oldest quarter blank, and no
  statement.
  - The implementation's 24-case `characterize.py` output is byte-identical
    to both its `before.json` (HEAD) and its `after.json`.

### I1: the rollout note

The rework found I1 already applied when it began. This receipt's "Rollout"
section and HANDOFF step 3 both say Serper's 2,500 "budget" is a reporting
constant that nothing enforces, citing the owner's 37,747 credits. Git history
cannot say who made that edit, because this receipt is untracked and HANDOFF is
uncommitted. The rework checked by grep that no KT, ARCHITECTURE,
TEAM_TESTING_GUIDE, `CODEBASE.md` or `config.yaml` text repeats the claim. It
made no further edit.

### Noted for the re-reviewer

- **An older blank quarter keeps `ok`, as the review specified.** The growth
  figure derived from it still renders `nan`. QoQ uses the previous quarter
  and YoY the oldest one read (the characterization's q1 and q3 cases). The
  reason names the quarter. Routed to [SA-045](../stories/SA-045.md) as a
  note: a Growth factor must read `missing_values`. If the re-reviewer counts
  the previous quarter as core, the change is one condition.
- **The review's T1 now reads `stale`, not `ok`.** T1 was a series asked to
  end on Sunday 20 Sep, run on Saturday 26 Sep. The newest bar such a series
  can hold is Friday 18 Sep, 8 days old, which is over the 7-day bound. The
  bound is measured from the newest bar, as KT §4 says.
- **`get_peer_margins`** would pass on a NaN margin for a peer with a blank
  newest quarter. By grep, nothing outside `fundamentals.py` calls it, so no
  action was taken.

### Commands and results (rework)

Environment: Windows 11, Python 3.13.11 (`.stockai` venv), pandas 3.0.2,
`RL_LEARNING_MODE=adapt`. Every pytest run used `-p nonet` (ignored
`analysis_data/sa002/nonet.py`). All numbers below are from the final bytes.

```text
kt_manifest.py verify SA-002-manifest.json (start)   -> 19 files, 5 mismatches (the review's doc edits)
pytest -p nonet tests/unit/shared/test_data_health_contract.py
                                                     -> 155 passed (132 before + 23 new); blocked 0
pytest -p nonet <the review's 11 focused files>      -> 289 passed (266 + 23); blocked 0
rework/sweep.py                                      -> 7 of 7 run days: 155 passed; blocked 0
rework/sweep.py old_bars                             -> Sun 9, Mon 11, Tue 7, Wed-Sat 5 failed (table above)
SA002_MUTATE=m2_reviewed | m2_status | m2_nan_only   -> 9 | 9 | 2 failed, rest passed
rework/characterize_nan.py                           -> identical: 13 of 13
characterize.py (the implementation's 24 cases)      -> byte-identical to before.json and after.json
pytest -p nonet tests/unit                           -> 3323 passed, 5 skipped, 0 failed (3 min 45 s); nonet blocked 194
                                                        (the pre-existing set, SA-005 T2); data/ clean
build_kt_pdf.py; check_kt_docs.py                    -> errors [], source 0979ad97..., 21 pages
```

- The full suite was also run once before a final variable rename in
  `get_financials` (`blank` to `qs` inside one comprehension). That run gave
  3323 passed and 5 skipped, with 194 connections blocked, and `data/` stayed
  clean. Every figure above was rerun after the rename.
- Not exercised: Linux or Python 3.11 (the Docker image), and any production
  data. How often a production statement has a blank newest quarter is still
  **not measured**.

### Files changed by the rework

- Code: `services/data/fetchers/fundamentals.py`.
- Tests: `tests/unit/shared/test_data_health_contract.py`, from 132 to 155 tests.
- Docs:
  - KT §1, §4 (the status line, plus a wider `fallback` meaning), §11 and §12;
  - the PDF, rebuilt;
  - ARCHITECTURE;
  - TEAM_TESTING_GUIDE 02-F, which gains the blank-quarter expectation;
  - `CODEBASE.md`.
- Bookkeeping, outside the manifest: STATE, HANDOFF, this receipt, the
  [SA-002](../stories/SA-002.md) box, the [SA-045](../stories/SA-045.md) note,
  and the preserved first-review manifest.

### Manifest and digests (rework)

- **Review input:** [SA-002-manifest.json](SA-002-manifest.json), the same 19
  paths. SHA-256 of its LF bytes: **`c88edda536f862096fd6fa0df8faffc6ee1bcd3ce3ffd1fc0887f109b8d7dd27`**. `kt_manifest.py verify`:
  0 mismatches.
- **Full SA-002 diff** against the pre-SA-002 bytes: **`dc7e850b62bb705e70aabe0addb9c52d73362dd6444632875f6cd65577023c2c`**
  (153,274 bytes, 18 text files; the PDF is pinned by blob). Rebuild
  it with `analysis_data/sa002/sa002_diff.py`, as below.
- **Rework-only diff,** covering the two code and test files, from the first
  review's input to now: **`56544c46183f1c1d1b12f4c9df95e6522c02ab2353841919df4eb106e0ee60b2`**
  (17,437 bytes).
  - Rebuild it with `analysis_data/sa002/rework/rework_diff.py`.
  - The old side is the first review's blobs, `2a9acfb1…` (`fundamentals.py`)
    and `996149d5…` (the contract test file).
  - Those blobs were never stored at review time. `rework/store_review1_blobs.py`
    rebuilt them by reversing this rework's edits. Both reproduce the pinned
    ids exactly, and both were written with `git hash-object -w`, in this
    checkout only.
  - To view the delta: `git cat-file -p 2a9acfb1… > old`, then
    `git diff --no-index old services/data/fetchers/fundamentals.py`.
- The docs' rework delta is status wording plus the sentences listed above. The
  review had already edited those files after the first manifest pinned them,
  so no stored blob marks the rework's starting point for them.

## What it does, in one example

TATAMOTORS' price source answers HTTP 404, while news, macro, flows and Tavily
all answer. The analyst still scores 9 of 9 dimensions.

| | Before (B2, contract v1) | After (SA-002, contract v2) |
|---|---|---|
| `technicals` | `ok` (text: "Technical data unavailable for TATAMOTORS: Insufficient price data…") | `empty`, reason "Insufficient price data… (0 bars)" |
| `fundamentals` | `ok` (text: "Financial data unavailable: No financial data available…") | `empty` |
| `peers_valuation` | `ok` (text: headers plus Serper snippets) | `fallback`, reason "price history unavailable; Serper fallback found results; valuation ratios unavailable; …" |
| row `health` | `ok`, live 10 | `degraded`, `essential_unusable` names all three |
| analyst prompt | — | byte-identical to before |

This reproduces the 2026-08-26 production rows (`health=ok, live=10, dims 9/9`)
on the pre-SA-002 code: see "Characterization" below. Nothing branches on the
row yet, so no verdict, advice or learning changes; that is SA-003.

## The contract

- **`services/data/context/fetch_result.py` (new, 112 lines).** `FetchResult(text,
  status, source, as_of, reason)` and the status vocabulary. B2's `ok`,
  `cache_hit`, `empty`, `n/a` and `failed:<Type>` are kept. SA-002 adds `stale`,
  `fallback` and `unverified`. `LIVE_STATUSES` is `{ok, cache_hit}`. The module
  also holds the freshness bounds: `observability.data_health_price_max_age_days`
  (7) and `…_fundamentals_max_age_days` (200).
- **Producers state their status from structured data, not text.** Every
  `*_context()` string function now returns `*_result().text`, so its callers
  (the legacy `ContextBuilder`, RL agents) are unchanged.

| Section | Producer | Status decided from |
|---|---|---|
| technicals (essential) | `get_technical_result` | `compute_technicals`' `error` gives `empty`; newest bar more than 7 days old gives `stale`; a neutral index correlation is named in the reason (`get_peer_correlation` gains an additive `default: True`) |
| fundamentals (essential) | `get_fundamentals_result` | `get_financials` `error` gives `empty`, or `failed:<Type>` via the new additive `error_type`; an absent revenue or operating-income row (zeros substituted, new additive `missing_rows`) gives `fallback`; newest quarter (new `as_of`) more than 200 days old gives `stale`. Shareholding and company-info fields shown as 0.0 are named in the reason (additive `missing_fields`) |
| peers_valuation (essential) | `get_valuation_result` | own price history and own ratios tracked as fetched. Both verified gives `ok` or `stale`; neither verified and no Serper fallback found anything gives `empty`; otherwise `fallback`. The Serper fallbacks now go through `fetch_news_result`, so "found nothing" is structural. A peer P/E fallback is named in the reason |
| company_news, sector_policy_news | `fetch_news_result` | article count: 0 gives `empty` (the "[No results for: …]" case); `as_of` is the newest dated article |
| macro_context | `get_macro_result` + news | a core indicator (INR/USD, WTI, steel, aluminium) without a value gives `empty`, and the section text stays `unavailable`, exactly as when `get_macro_context` raised `TypeError`. A macro-cache hit gives `cache_hit`. The RBI settings fallback (additive `fallback: True`), missing rubber and macro news with no results are named in the reason |
| policy_deep_dive | `fetch_tavily_result` | live: result count. Cache: a new `<hash>.meta.json` sidecar records `results` and `fetched_at`, so a cached "no results" stays `empty` for the month; an entry with no sidecar (written before SA-002) is `unverified` but still served, with no extra Tavily call |
| commodities | `get_raw_materials_result` | `n/a` outside automobile; `empty` when no raw-material price came back |
| flows_sentiment | `_fetch_flows_sentiment` | `empty` when none of bulk deals, FII/DII and MF herding came back; missing parts are named |
| dossier | `_fetch_dossier` | disabled or no dossier stored yet gives `n/a` (was `empty`); an empty digest gives `empty` |

- **`bundle_builder._safe`** takes a `FetchResult`'s status as stated and
  records `section_provenance[name] = {source, as_of, reason}`. **Plain text is
  now `unverified`, not `ok`.** B2's blank and exact-marker rules are kept:
  `""`, whitespace and `"unavailable"` are `empty`, and `"not_applicable"` is
  `n/a`. `provenance=` is a keyword-only optional parameter, so existing
  `_safe(sections, status, name, fetcher)` callers still work.
  `SectorDataBundle.section_provenance` is additive. **`has_real_data` is
  unchanged**, as B6 required.
- **`data_health` contract v2.** Rows carry `contract_version: 2`,
  `section_provenance`, `stale`/`fallback`/`unverified` counts,
  `essential_sections`, `essential_unusable` and `health_reasons`. Every section
  lands in exactly one counter. `assess_health`:
  - `hollow`: thresholds unchanged (no dimension scored, or no verified section);
  - `degraded`: a missing dimension, or any section that applies and is not
    verified and fresh;
  - otherwise `ok`.

  Essential sections come from `observability.data_health_essential_sections`,
  default `[fundamentals, technicals, peers_valuation]`.
- **Telemetry.** Seven nullable columns are added to `telemetry.db.data_health`,
  both in the schema for new databases and through `_migrate` for existing ones.
  `data_health_count(health, contract_version)` gains a contract filter, where 1
  means the v1 rows (NULL). A new `data_health_rows(limit)` is exposed through
  `data_health.recent_health_rows`. `normalize_health_row` reads JSONL or DB
  rows. A v1 row keeps its fields and `health` as written, and is labelled
  `provenance_known: False`, with `section_provenance` source `unknown`,
  `essential_unusable`/`health_reasons` None and a `health_basis` explaining what
  v1 meant. A malformed version is treated as unknown, never raised.
- **Orchestrator** passes `section_provenance` to `record_data_health`. The
  WARNING log line now also names stale, fallback, unverified and the essential
  unusable sections.

## Acceptance criteria

| Criterion | Result | Evidence |
|---|---|---|
| Provider no-data messages never become healthy merely because they are nonempty | Met | `TestNoDataTextIsNeverHealthy` (news, Tavily live and cached, legacy cache, technicals, macro, flows) asserts that the text is nonempty and the status not live. `TestEssentialProducers` covers each essential producer's no-data case. Mutations M3, M4, M5, M8 are caught |
| A 9-dimension result with only one live source cannot report fully healthy | Met | `test_nine_of_nine_with_one_live_section_is_never_ok`: 10 choices of the live section × 5 kinds of dead section = 50 cases, all not `ok`. The integration TATAMOTORS run reads `degraded` with 9/9 dimensions. Mutation M1 (the B2 rule) is caught |
| Existing telemetry readers accept legacy rows and explicitly label unknown provenance | Met | `test_a_pre_sa002_database_migrates_and_both_contracts_read_back` builds the B2 schema with a B2 TATAMOTORS row, lets the store migrate it, writes a v2 row, and reads both. The v1 row keeps `health: ok`, labelled v1 with unknown provenance; `data_health_count` counts both, and filters by contract. A v1 JSONL line is also normalized. Mutation M6 is caught |
| Parameterized empty / exception / provider error text / stale cache / synthetic / verified cases | Met | `test_technicals` (verified, 404, stale), `test_fundamentals` (verified, empty, exception, stale, synthetic zeros), `test_valuation` (verified, stale, two synthetic fallbacks, error text only), plus the Tavily cached-empty and legacy-entry cases |
| Integration: bundle → health row → watchdog/UI meaning, no provider calls | Met | `TestBundleToRecordToReaders` runs the real producers under patched providers, through `BaseSectorOrchestrator._run_unified`, to the JSONL line, the telemetry row (normalized), `data_health_count` and the `FinalReport.model_dump()` payload the analyse and stream routes return. The healthy counterpart reads `ok`, with every section typed (no `untyped` provenance), which shows the rule can say `ok` |

No watchdog check or UI screen reads the row today: the grep found none, and
`FinalReport.data_health` reaches the API payload unrendered. "Watchdog/UI
meaning" is therefore tested at the readers they would use (`data_health_count`,
`recent_health_rows`) and at the API payload.

## Tests — commands, environment, results

Environment: Windows 11, Python 3.13.11 (`.stockai` venv), `RL_LEARNING_MODE=adapt`
(the local `.env` resolves `observe`; SA-005 note). All runs below used a pytest
plugin, `-p nonet` (copy in ignored `analysis_data/sa002/nonet.py`). It fails
every non-loopback `socket.connect`/`getaddrinfo` and reports what it blocked.
The new test file also carries its own autouse guard.

```text
PYTHONPATH=<dir of nonet.py> RL_LEARNING_MODE=adapt \
  .stockai/Scripts/python.exe -m pytest -q -p no:cacheprovider -p nonet \
  tests/unit/shared/test_data_health_contract.py
  -> 132 passed; nonet blocked 0

  ... tests/unit/shared/test_data_health_record.py tests/unit/test_bundle_builder.py \
      tests/unit/test_bundle_builder_sectors.py tests/unit/intelligence/rl/test_tavily_cache.py \
      tests/test_tavily_fetcher.py tests/unit/test_news_search_recency.py \
      tests/unit/test_orchestrator_unified_branch.py tests/unit/shared/test_error_capture_context.py \
      tests/unit/test_unified_e2e_parity.py tests/unit/test_unified_e2e_parity_sectors.py
  -> 134 passed; nonet blocked 0

  ... -m pytest tests/unit -q -p no:cacheprovider -p nonet
  -> 3300 passed, 5 skipped, 0 failed (4 min 18 s)
```

The full-suite runs, the first and a second with per-test attribution, both gave
3300 passed, 5 skipped. **The guard blocked 194 attempts, all from tests
SA-002 did not touch:**

- `openrouter.ai`: 120, from four RL review test files;
- `www.nseindia.com`: 68, the known T1 harness;
- `google.serper.dev`: 6, from `TestSalesDemandAgent::test_run_calls_llm` in
  two files.

The same files on the pre-SA-002 code (`git archive 103f2b8`) make the same
OpenRouter and NSE attempts file for file. The 6 Serper attempts appear in both
trees once `SERPER_API_KEY` is set (tested with a dummy value, all blocked):
they depend on the `.env` key, not on SA-002. The SA-002 tests themselves
attempted 0. The attribution is routed to [SA-005](../stories/SA-005.md) T2.
In an unguarded run with real keys those are real calls.

**Existing tests changed** (the contract changed, so the expectations did too):

- `test_data_health_record.py::TestSectionStatus._build` now supplies typed `ok`
  results. With plain `"live text"` the sections would, correctly, be `unverified`.
- `test_macro_cache_hit_is_recorded_by_the_branch_that_knows` asserts on the
  returned `FetchResult` instead of B2's `status_out` side channel, which was
  removed.
- `test_macro_miss_leaves_the_status_to_the_classifier` is replaced by
  `test_macro_miss_with_news_is_ok`, and `test_untyped_text_is_unverified_not_ok`
  is new.
- `test_bundle_builder_sectors.py`: 23 patches retargeted from `*_context` to
  the typed `*_result` producer, each returning a fixture `FetchResult`. Every
  query, peer and call-count assertion is unchanged. Two assertions now also
  check the status (`n/a`, `cache_hit`).

**Mutation check (tests fail when the defect returns).** Each defect was
reintroduced alone, the two health test files were run, and the source was then
restored byte-for-byte (hash-checked). 12 of 12 were caught:

- M1: the B2 health rule;
- M2: the B2 text classifier (untyped text reads `ok`);
- M3: technicals no-data reads `ok`;
- M4: news no-results reads `ok`;
- M5: a cached empty Tavily entry reads `cache_hit`;
- M6: legacy rows not labelled;
- M7: substituted zeros read `ok`;
- M8: a valuation snippet fallback reads `ok`;
- M9: a stale statement is ignored;
- M10: stale price bars are ignored;
- M11: an exception inside `get_financials` reads `empty`;
- M12: essential sections are not singled out.

The script is `analysis_data/sa002/mutate.py` (ignored).

**Characterization (the prompt text is unchanged).** Both scripts are in ignored
`analysis_data/sa002/` with their outputs; they may be absent in another checkout.

- `characterize.py` runs 24 producer cases under fixed fixtures. It was captured
  before any code change and again after the producers were refactored: 24 of 24
  identical, including `get_macro_context` still raising on a missing INR value.
- `bundle_characterize.py` runs 5 whole-bundle scenarios: auto healthy, auto
  TATAMOTORS 404, renewable healthy, BFSI with search dead, IT with everything
  dead. It ran on the HEAD code, exported with `git archive 103f2b8` into a
  scratch directory, and on the worktree. `to_prompt_text()` and `has_real_data`
  are identical in all 5. The HEAD run also reproduces the defect: in the
  TATAMOTORS scenario every section read `ok`, and with every provider dead B2
  still recorded 7 sections `ok`.

## Incident during this phase (provider calls from a test run)

Before the sector tests' patches were retargeted, one run of the existing test
files reached real providers through the new `*_result` functions, using the
local `.env` keys. That run did not load the network guard.

- The local usage counters moved by **+2 Serper** and **+10 Tavily** successful
  calls; public yfinance calls were also made.
- Eight Tavily month-cache pairs were written under `data/tavily_cache/2026-09/`.
  They were new files, deleted in the same session.
- No production system, variable or job was touched. The owner's serper.dev
  dashboard showed 37,747 credits left the same day, so the 2 Serper calls are
  negligible. The Tavily calls came from the local key's monthly allowance.

Every later run used the guard. Routed to [SA-005](../stories/SA-005.md) as T2:
a suite-wide guard in `tests/conftest.py`.

## Design decisions for the reviewer

1. **`degraded` covers any applicable section that is not verified.** This is
   what B2's own `derive_health` docstring promised ("a section that failed or
   came back empty") and never computed. Essential sections are listed
   separately in `essential_unusable`, so SA-003 can tell ordinary degraded
   enrichment from missing price or fundamental data (audit F08).
2. **`hollow` thresholds unchanged,** but `live` now counts only verified
   sections. A run in which nothing verified came back (for example, everything
   `stale`) is now `hollow`. Under B2 its apology sentences counted as live.
3. **Untyped text is `unverified`.** No real producer returns plain text any
   more; the healthy integration test asserts that no section's provenance is
   `untyped`.
4. **A missing dossier is `n/a`,** because nothing was lost. The reason is still
   recorded, so a lost dossier store would show in `section_provenance`.
5. **Legacy Tavily entries are `unverified` and served.** Refetching them would
   spend quota. They expire at the month rollover (1 Oct).
6. **Macro with a missing core value is `empty`** instead of `failed:TypeError`.
   The prompt text is identical (`unavailable`), and still no news is fetched.
7. **Freshness bounds.** 7 calendar days for a price bar covers weekends and
   holiday runs, and still catches a frozen or delisted series. 200 days for a
   quarter covers roughly 60 days of reporting lag plus the ~90 days a quarter
   stays newest. Both are config keys.
8. **Sub-field substitutes do not change a section's status.** These are
   shareholding and company-info zeros, a neutral correlation, the RBI settings
   value, missing rubber and missing peer P/E. They are named in `reason`, and
   routed to SA-045 so the factors never read them as values.
9. **The prompt text is byte-identical by construction and by
   characterization.** SA-002 changes only what the record says.

## Documentation

- [KT](../../../TECHNICAL_DESIGN.md):
  - §1 status line;
  - a new §4 "Data health (SA-002 …)" paragraph with the TATAMOTORS example,
    labelled newer than the header revision. `fetch_result.py` is named, not
    linked, because it is absent at header revision `4c4728a`; link it when the
    header is bumped at commit, as SA-001 does for `chat-markdown.js`;
  - the §4 "Current gap" paragraph, the §11 data-health row and the §12 status
    line.
- The [PDF](../../../StockAgent-Three-Loops.pdf) is rebuilt (source SHA-256
  `c5938bef…`).
- [ARCHITECTURE](../../../ARCHITECTURE.md): a runtime paragraph and the
  current/planned row.
- [TEAM_TESTING_GUIDE](../../../TEAM_TESTING_GUIDE.md): the new case **02-F**
  (dead price source vs normal run vs a v1 row), NOT RUN.
- `CODEBASE.md`: the data-health paragraph and the module table (a new
  `fetch_result.py` row).
- `config.yaml`: the new `observability` keys, with rationale comments.
- Routed notes:
  - [SA-003](../stories/SA-003.md): gate on the record, not `has_real_data`;
    what is and is not provided;
  - [SA-005](../stories/SA-005.md): T2, the network guard;
  - [SA-044](../stories/SA-044.md): F1, the automobile peer P/E fallback query;
  - [SA-045](../stories/SA-045.md): F3, substitute zeros and defaults as factor
    inputs.
- `check_kt_docs`: see "Checks" below.

## Limitations and what was not done

- Nothing gates on the record; that is SA-003. `has_real_data` still counts
  apology text as real, by B6's instruction.
- Section-level freshness exists only for price bars and quarterly statements.
  - News is recency-bounded by its query (`tbs`), with no bound on `as_of`.
  - Tavily content is up to a month old by design.
  - Macro and raw materials record no `as_of`.
  - NSE flows are cached per calendar day.
- `api_calls` is still an upper-bound estimate (SA-025).
- Peer selection is unchanged (SA-044). Price identity, such as a renamed or
  demerged symbol, is SA-008.
- Tested on Windows with Python 3.13.11 only. Linux / Python 3.11 (the Docker
  image) parity is not claimed.
- Not measured in production.

## Rollout, rollback and production verification

- **Additive.** New JSONL fields. Seven nullable columns are added on the first
  boot after deploy (`ALTER TABLE … ADD COLUMN`, duplicate-column safe, retried
  on the next boot). Old rows are untouched. There is no data migration.
- **Expect more `degraded` rows.** That is the point, but read them before
  anyone gates on them.
  - Serper is not a likely cause. The app's 2,500 "budget" is a reporting
    constant that nothing enforces, and the owner's serper.dev dashboard showed
    37,747 credits left on 2026-09-26 (recorded on SA-035). News reads `empty`
    only when searches genuinely return nothing or fail.
  - Tavily entries written in September before the deploy read `unverified`
    until 1 Oct.
  - Degraded rows also log one WARNING each, archived to `app_logs`; no watchdog
    check counts them.
- **Rollback.** `observability.data_health_enabled: false` stops the rows. A
  code revert restores B2 semantics; the added columns stay NULL and harmless.
- **Read-only verification after an authorized deploy,** across one complete
  scheduled cohort:
  - rows carry `contract_version: 2`;
  - `health` and `essential_unusable` agree with the correlated source log lines
    (`[yfinance] No price data for …`, `[news] Serper search failed …`);
  - B2's acceptance (c) still holds (`dimensions_scored` matches the
    `[SignalAggregator] N/M dimensions excluded` warning);
  - not every row is `ok`.

  This also settles the lapsed `b2_data_health_prod_verify` milestone ("DO NOT
  CLOSE AS HEALTHY … until B6"); that judgement is SA-038's.
- This phase deployed nothing, pushed nothing, changed no production variable,
  triggered no job and sent no message.

## Manifest and digest

This section describes the **first** review input, as the fresh review
verified it. The rework's manifest and digests are in "Manifest and digests
(rework)" above. The file named below is now preserved as
[SA-002-manifest-review1.json](SA-002-manifest-review1.json).

- **Review input:** [SA-002-manifest.json](SA-002-manifest.json), 19 files.
  SHA-256 of its LF bytes:
  **`4d8968fdf6bf7971429e63f16c296ec174f0e0f050a7a102e69d3ebd611b0f79`**.
  `kt_manifest.py verify` on the worktree: 0 mismatches.
- **Diff digest:** the text diff of those files is 18 files; the PDF is pinned
  by blob. Its SHA-256 is
  **`f605966c50478145fca417c5d99cb5fe1dbe0e6952962f8e298358a049a2b15e`**
  (142,538 bytes). Rebuild it with `python analysis_data/sa002/sa002_diff.py
  OUT.diff`. The old side is each file's pre-SA-002 blob (manifest
  `pre_sa002_blobs`) or `103f2b8:<path>`, and CRLF is normalized to LF.
- **Files:**
  - Code:
    - `services/data/context/fetch_result.py` (new)
    - `services/data/context/bundle_builder.py`
    - `services/data/stores/data_health.py`
    - `services/data/stores/log_store.py`
    - `services/data/fetchers/news.py`
    - `services/data/fetchers/fundamentals.py`
    - `services/data/fetchers/macro.py`
    - `services/clients/tavily_fetcher.py`
    - `core/intelligence/algorithms/indicators/fetcher.py`
    - `src/backend/shared/pipeline/base_orchestrator.py`
    - `config.yaml`
  - Tests:
    - `tests/unit/shared/test_data_health_contract.py` (new, 132 tests)
    - `tests/unit/shared/test_data_health_record.py`
    - `tests/unit/test_bundle_builder_sectors.py`
  - Docs: `docs/TECHNICAL_DESIGN.md`, `docs/StockAgent-Three-Loops.pdf`,
    `docs/ARCHITECTURE.md`, `docs/TEAM_TESTING_GUIDE.md` and `CODEBASE.md`.
  - Excluded bookkeeping: STATE, HANDOFF, this receipt, the manifest, and the
    routed notes on SA-003, SA-005, SA-044 and SA-045.
- **Shared with SA-001's uncommitted work.** Six files hold both stories'
  changes: the KT, the PDF, ARCHITECTURE, TEAM_TESTING_GUIDE, CODEBASE.md and
  config.yaml (config.yaml is not in SA-001's manifest). Their pre-SA-002 bytes
  were stored with `git hash-object -w` before any edit, and their blob ids are
  in the manifest. To see SA-002's own change to one of them, run
  `git cat-file -p <blob> > old` and then `git diff --no-index old <path>`.
  (`cat-file` hangs on the PDF in this checkout; compare its blob id.)
- **Commit consequence for SA-001.** SA-001's commit check (`verify
  SA-001-manifest.json --rev <commit>` shows mismatches only in the KT, the PDF,
  ARCHITECTURE and TEAM_TESTING_GUIDE) will now also show `CODEBASE.md`, because
  of SA-002's edit, if both stories are committed together. That mismatch is
  exactly the `CODEBASE.md` hunk in SA-002's diff. Committing SA-001 alone first
  would need SA-002's hunks held back in the five shared docs.
