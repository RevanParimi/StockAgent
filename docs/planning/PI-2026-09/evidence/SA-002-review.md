# SA-002 review receipt — data-health records describe usable evidence

This file holds two fresh-session reviews. The **re-review** (below, first) accepted the reworked
revision. The **first review**, further down, requested changes.

## Re-review: ACCEPTED (2026-09-26, fresh session)

- **Story:** [SA-002](../stories/SA-002.md). Implementation receipt, including its "Rework"
  section: [SA-002-implementation.md](SA-002-implementation.md).
- **Review context:** a **fresh-session re-review**, in a new conversation on 2026-09-26, about
  21:57–22:25 IST. It is not the implementing, first-review or rework conversation, and it did not
  read them. No SA-039 production check was due (P1 is Mon 28 Sep 17:00 IST).
- **Reviewed input:**
  - `kt_manifest.py verify SA-002-manifest.json` on the worktree: 19 files, **0 mismatches**.
    The review input SHA-256 is `c88edda536f862096fd6fa0df8faffc6ee1bcd3ce3ffd1fc0887f109b8d7dd27`,
    which matches STATE. The first review's manifest is intact (`4d8968fd…`).
  - **Between the two inputs, the only code or test files that changed are `fundamentals.py` and
    the contract test file.** The five docs changed too (the first review's status wording, plus
    the rework's prose). The other 12 files have identical blob ids.
  - `rework/rework_diff.py` rebuilt the rework-only diff, **`56544c46183f1c1d1b12f4c9df95e6522c02ab2353841919df4eb106e0ee60b2`**
    (17,437 bytes). `sa002_diff.py` rebuilt the full diff, **`dc7e850b62bb705e70aabe0addb9c52d73362dd6444632875f6cd65577023c2c`**
    (153,274 bytes, 18 text files).
  - The rework diff's old side is the blobs `2a9acfb1…` and `996149d5…`, and both exist in the
    object database. A blob id is the hash of its content, so those are the first review's bytes,
    whoever stored them.
  - Baseline: HEAD `103f2b8`, plus the accepted, uncommitted SA-001 worktree.
- **Verdict: `accepted`**, for the worktree revision pinned by `c88edda5…`. M1, M2 and I1 are
  resolved. There is no critical, high or medium finding, and every acceptance criterion is met.
  Two new low findings are routed.

### The first review's findings, re-checked

| ID | Result | Evidence |
|---|---|---|
| M1 | **Resolved** | `_bars` rolls a weekend end back to Friday before it builds 300 bars. The expected dates come from `_last_session`, a plain-Python formulation, not from pandas. The guard, `TestFixturesHoldOnEveryWeekday`, runs over a fixed week, so it does not depend on the run day. The reviewer reran the sweep: all 7 run days (Sun 27 Sep – Sat 3 Oct) pass 155 of 155. With the old `_bars` put back, the control fails 9 on Sun, 11 on Mon, 7 on Tue and 5 on each of Wed–Sat, and the guard fails every day. Only one clock decides a status, `fetch_result.is_stale`, and the guard pins it. `fetcher.py`'s other `date.today()` calls only set the download window, which the fake ignores, or query text. The real-clock run (a Saturday) passes too |
| M2 | **Resolved** | The reviewer's own fixtures, R4–R11 below: the first review's code reads `ok` for every blank newest quarter, and the reworked code reads `fallback`, dated by the newest complete quarter. The prompt text is byte-identical to HEAD |
| I1 | **Resolved** | The receipt's "Rollout" section and HANDOFF say that `SERPER_MONTHLY_LIMIT` is a reporting constant and that Serper is not a likely cause of empty rows. No KT, ARCHITECTURE, guide or `CODEBASE.md` text repeats the old claim |

### Independent adversarial examples (M2)

The reviewer wrote these fixtures. They do not use the contract file's `_statement` helper;
they build yfinance-shaped frames directly. Each fixture ran through three versions of
`fundamentals.py`:

- HEAD `103f2b8`;
- the first review's blob `2a9acfb1`, as a control;
- the worktree.

`yfinance.Ticker` was replaced, a socket guard was on, and `is_stale`'s clock was pinned to
2026-09-26. The expectations come from what each fixture means. The script is untracked
(scratchpad).

| # | Fixture | Expected (by meaning) | Worktree | First review's code |
|---|---|---|---|---|
| R4 | yfinance's shape for an announced quarter. There are 5 columns, and every row is NaN in the newest (30 Jun 2026). The oldest column is sparse and outside the 4-quarter lookback | `fallback`, `as_of` 31 Mar; 30 Jun named; the column outside the lookback not named | As expected | `ok`, `as_of` 30 Jun |
| R5 | "Operating Income" absent, so "EBIT" is the row used, and its newest cell is NaN | `fallback`, naming `operating_income` | As expected | `ok` |
| R6 | A nullable `Float64` frame with `pd.NA` as the newest revenue | `fallback` | As expected. The prompt shows `₹0.0Cr`, exactly as HEAD does | `ok` |
| R7 | The previous quarter's revenue is NaN | `ok` (the first review's split), with 31 Mar named | As expected; QoQ renders `nan` | `ok`, nothing named |
| R8 | The newest complete quarter is 269 days old, and an older quarter is blank | `stale`, and the reason names both | As expected | `stale`, blank not named |
| R10 | A healthy statement | `ok`, no reason | As expected | `ok` |
| R11 | Revenue blank in all 4 quarters read; operating income present | `fallback`, `as_of` None, "no quarter fully reported" | As expected | `ok` |
| R9 | Revenue grows exactly 10% every quarter | (a question about what the figure means) | "YoY" is 33.1% (**N1**) | the same |

- The prompt text is byte-identical to HEAD in 8 of 8 cases. 0 connections were blocked.
- **The rework's own M2 tests are not implementation-shaped.** The 8 parametrized cases take the
  expected `as_of` from the fixture's quarter index. The end-to-end case reaches the DB row and the
  report payload.
- **No other code sees the change.** `get_financials` has exactly two callers, both in
  `fundamentals.py`. `get_peer_margins` has no caller elsewhere. So the new meaning of `as_of`
  and the new `missing_values` key reach nothing else. `_format_fundamentals` is unchanged and
  reads neither key, so byte identity holds by construction as well as by test.

### New findings

| ID | Severity | Location | Trigger → observed / expected | Impact | Disposition |
|---|---|---|---|---|---|
| N1 | Low; predates SA-002 | `services/data/fetchers/fundamentals.py:125-128` (`rev_yoy`), with the lookback of 4 at `:86` | Revenue grows 10% every quarter (R9). Observed: "Revenue YoY: +33.1%". Expected: +46.4%, the same quarter a year earlier. `revenues[-1]` is only three quarters back | The analyst's prompt labels a nine-month change as year-over-year. SA-045's Growth factor lists "Revenue YoY" as an input | Routed to [SA-045](../stories/SA-045.md) as a note. It is outside SA-002's scope, which keeps the prompt text byte-identical by design |
| T3 | Low (test infrastructure); predates SA-002 | `tests/unit/test_ops_alerts.py::test_llm_failure_streak_alerts_once`; `tests/unit/test_delivery_api.py::test_push_subscribe_caps_store_size` | Both failed in the full guarded run. Alone, the ops-alerts file passed 5 of 5, and the delivery file failed 2 of 5 with WinError 5 on its `tmp → json` rename. `ops_alerts._save_state` swallows a failed atomic write, so one lost rename resets the streak and the alert never fires | Red full runs on Windows, unrelated to the change under review. The first review's flake is more frequent than "passes alone" suggested | Routed to [SA-005](../stories/SA-005.md), added to its existing flake note |

**Considered and accepted:**

- **An older blank quarter keeps `ok` (R7).** This is the first review's split, and the rework
  asked the re-reviewer to decide it. The newest quarter's revenue and margin are reported. The
  growth figure built on the blank quarter shows `nan`, not an invented number, and the reason
  names the quarter. SA-045 already has the note that a Growth factor must read `missing_values`.
  The re-reviewer does not count the previous quarter as core, so there is no change.
- **The first review's T1 now reads `stale`.** On Sat 26 Sep, the newest bar that series can hold
  is Fri 18 Sep, 8 days old. That is over the 7-day bound, measured from the newest bar as KT §4
  says. It is correct.
- **A NaN peer margin in `get_peer_margins`:** nothing outside the module calls it.
- **Encoding:** HEAD's `fundamentals.py` starts with a UTF-8 BOM, and the worktree keeps it.

### Commands, environment, results

Environment: Windows 11, Python 3.13.11 (`.stockai` venv), pandas 3.0.2,
`RL_LEARNING_MODE=adapt`. Every pytest run used `-p nonet` (the ignored
`analysis_data/sa002/nonet.py`) through `PYTHONPATH=analysis_data/sa002`.

```text
kt_manifest.py verify SA-002-manifest.json          -> 19 files, 0 mismatches, c88edda5...
rework/rework_diff.py                               -> 56544c46..., 17437 bytes, 2 files
sa002_diff.py                                       -> dc7e850b..., 153274 bytes, 18 files
git cat-file -t 2a9acfb1... / 996149d5...           -> blob / blob
pytest -p nonet <the first review's 11 focused files>
                                                    -> 289 passed; nonet blocked 0 (Sat 2026-09-26, real clock)
reviewer fixtures (scratch)                         -> 8 of 8 as expected; control (2a9acfb1) fails R4, R5, R6, R11;
                                                       text identical to HEAD 8 of 8; blocked 0
pytest -p nonet tests/unit                          -> 3321 passed, 2 failed, 5 skipped (5 min 47 s);
                                                       nonet blocked 194 (the pre-existing set, SA-005 T2)
   test_ops_alerts.py alone, 5 runs                 -> 8 passed every time
   test_delivery_api.py alone, 5 runs               -> 16 passed 3 times; 1 failed (WinError 5 rename) 2 times
rework/sweep.py                                     -> 7 of 7 run days: 155 passed; blocked 0
rework/sweep.py old_bars                            -> Sun 9, Mon 11, Tue 7, Wed-Sat 5 failed (the guard every day)
check_kt_docs.py (input as reviewed)                -> errors [], source 0979ad97..., 21 pages
build_kt_pdf.py; check_kt_docs.py (after the re-review's status edits)
                                                    -> errors [], source 333895c4..., 21 pages
kt_manifest.py verify SA-002-manifest.json (after)  -> 19 files; mismatches exactly CODEBASE.md, ARCHITECTURE,
                                                       the PDF, TEAM_TESTING_GUIDE and the KT (expected)
```

- `data/` stayed clean after the full run and after the sweep.
- **Not exercised:**
  - Linux or Python 3.11, the Docker image;
  - production data. How often a production statement has a blank newest quarter is still
    **not measured**;
  - the rework's mutation script. The reviewer's own control (the first review's code) covers M2,
    and the sweep's control covers M1;
  - a real browser: not applicable, because no client code reads the record.

### Documentation

- **Checked.** The KT §4 `fallback` meaning and the older-quarter sentence, TEAM_TESTING_GUIDE
  02-F's blank-quarter expectation, `CODEBASE.md` and ARCHITECTURE describe the reviewed
  behaviour.
- **The re-review changed status wording only:** KT §1, the §4 paragraph header and "Current
  gap", §11 and §12; ARCHITECTURE (two places); 02-F; and `CODEBASE.md`. The PDF is rebuilt.
  - After these edits, `verify SA-002-manifest.json` mismatches exactly those five files: the KT,
    the PDF, ARCHITECTURE, TEAM_TESTING_GUIDE and `CODEBASE.md`. That is expected. No code or
    test file changed.
- **Routed notes:** [SA-045](../stories/SA-045.md) (N1) and [SA-005](../stories/SA-005.md) (T3).
  [SA-003](../stories/SA-003.md)'s routed-input line now says SA-002 is accepted.

### Acceptance checklist

| Criterion | Verdict |
|---|---|
| Provider no-data messages never become healthy merely because they are nonempty | Met (unchanged since the first review) |
| A 9-dimension result with only one live source cannot report fully healthy | Met (unchanged; the first review's X1) |
| Existing telemetry readers accept legacy rows and explicitly label unknown provenance | Met (unchanged) |
| Parameterized empty / exception / error text / stale / synthetic / verified cases | Met, and now deterministic (7 of 7 run days) |
| Integration bundle → row → readers, with no provider calls | Met: 0 blocked, and independent of the weekday |
| Hard review: every essential producer | Structured, not string-guessing. The NaN statement gap is closed (R4–R11) |

### Decision and follow-up state

- **`accepted`** for the worktree revision pinned by review input `c88edda5…` (full diff
  `dc7e850b…`). SA-002 is `done`, which means its code is complete.
- **`production_verification`: `pending_deployment`.** Nothing is committed or deployed. After an
  authorized commit and push, run the read-only checks in the implementation receipt's "Rollout"
  section across one scheduled cohort. Also note whether any row has fundamentals `fallback`
  naming a blank newest quarter; its frequency is the unmeasured question.
- **Commit (the owner's word, in a safe window).** SA-001 and SA-002 are both accepted and
  uncommitted, and they share six files. `verify SA-002-manifest.json --rev <commit>` should
  mismatch only in the five status-edited docs. Bump the KT header revision at commit, and link
  `fetch_result.py` there, as the receipt says.
- **Follow-ups:** N1 → SA-045 and T3 → SA-005, both new. The earlier routes stand: L1 → SA-045,
  the flake and date dependence → SA-005, T2 → SA-005, F1 → SA-044, F3 → SA-045, and the gate
  inputs → SA-003.
- **Next story: [SA-003](../stories/SA-003.md)** (its only dependency, SA-002, is now `done`).
  Implement it in a new conversation; it was not started here.
- This re-review deployed nothing, pushed nothing, committed nothing, changed no production
  variable, triggered no job and sent no message.

## First review: CHANGES REQUESTED (2026-09-26, fresh session)

- **Story:** [SA-002](../stories/SA-002.md). Implementation receipt:
  [SA-002-implementation.md](SA-002-implementation.md).
- **Review context:** a **fresh-session review**, in a new conversation on 2026-09-26, about
  13:20–14:00 IST. It is not the implementing conversation, and it did not read that chat.
  No SA-039 production check was due (P1 is Mon 28 Sep 17:00 IST).
- **Reviewed input:**
  - `kt_manifest.py verify SA-002-manifest.json` on the worktree: 19 files, **0 mismatches**.
    The review input SHA-256 is `4d8968fdf6bf7971429e63f16c296ec174f0e0f050a7a102e69d3ebd611b0f79`,
    which matches STATE.
  - `analysis_data/sa002/sa002_diff.py` rebuilt the diff: **`f605966c50478145fca417c5d99cb5fe1dbe0e6952962f8e298358a049a2b15e`**,
    142,538 bytes, 18 text files. The PDF is pinned by blob.
  - Baseline: HEAD `103f2b8` plus the accepted, uncommitted SA-001 worktree.
- **Verdict: `changes_requested`.**
  - The production code has no critical or high defect.
  - The new invariant suite is not deterministic. It passes on Wednesday to Saturday, but its
    healthy-path and 30-day-stale tests fail on Sundays, Mondays and Tuesdays (M1).
  - The story requires deterministic fixtures, and REVIEW.md accepts only with the relevant tests
    passing.
  - One essential producer reads `ok` for a quarter with no figures (M2). It is fixed in the same
    rework because SA-003 and SA-045 would otherwise inherit it.

### Contract checked

- **Every essential producer decides its status from structured data, not from its sentence.**
  - `technicals`: from `get_technical_result`, using `compute_technicals`' `error` and the last bar
    date.
  - `fundamentals`: from `get_fundamentals_result`, using `get_financials`' `error`, `error_type`,
    `missing_rows` and `as_of`.
  - `peers_valuation`: from `get_valuation_result`, using the price and ratio availability flags
    and whether each Serper fallback found articles.
  - No producer matches on text. `_classify_section` handles only untyped text. It keeps B2's exact
    blank and marker rules, and all other text is `unverified`.
- **The analyst sees nothing but the bundle.**
  - `UnifiedAnalyst` receives only `bundle.to_prompt_text()` (`unified_analyst.py:420`), so the 10
    sections are the whole data surface.
  - The orchestrator's single `_record_data_health` passes `section_provenance`.
- **Nothing branches on the row.**
  - A grep for `HEALTH_*`, `data_health_count`, `recent_health_rows` and `.data_health` finds only
    the store, the orchestrator, `FinalReport` and tests.
  - `src/frontend` never reads `data_health`.
  - `derive_health`'s signature changed; its only caller is `data_health.py`.
- **Compatibility.**
  - Every `*_context()` string function now returns `*_result().text`. The ~40 legacy
    `ContextBuilder` and RL call sites are therefore unchanged.
  - The additive dict keys (`as_of`, `missing_rows`, `error_type`, `missing_fields`, `default`,
    `fallback`) are not serialized whole into any prompt. Their consumers are the formatters and
    `get_peer_margins`, which reads one key.
  - The `telemetry.db` migration only adds nullable columns and is duplicate-safe.
- **Macro equivalence.**
  - The new "core missing" rule (`current` or `change_3m_pct` is None) is wider than the old
    raise, which fired only on a missing `change_3m_pct`, because `current` has no format spec.
  - It is equivalent in practice: `_fetch_latest` returns both as None together, or both set.
- **No new secret sink.**
  - `_safe` now persists `str(exc)` in the row's `reason`.
  - NewsAPI's key travels in the query string. However, `search_newsapi` swallows every exception
    and returns `[]`, so no keyed URL can reach `_safe`. The same exception text was already
    logged before SA-002.
- **The JSONL writer uses `default=str`,** so a non-string `as_of` cannot drop a row.
  `_normalize_date` always returns a string, and its non-ISO outputs are skipped.

### Independent adversarial examples

The reviewer wrote these fixtures. Each expectation comes from what the fixture means. They reuse the
contract file's provider fakes, with all transports patched and the socket guard on; the scratch file
is not tracked.

| # | Fixture | Expected (by meaning) | Observed |
|---|---|---|---|
| R1 | A frozen or delisted symbol. The last bar is 22 days old (a Friday), the newest quarter is 400 days old, ratios answer, and everything else is healthy. Run through `_run_unified` to the JSONL and DB rows | All three essential sections `stale`; the row `degraded` with all three in `essential_unusable`; JSONL and DB agree | As expected |
| R3 | Serper over its monthly budget; NewsAPI also returns nothing | Both news sections `empty`; macro stays `ok`, with "macro news: no results" in its reason; the essentials `ok`; the row `degraded` with `essential_unusable == {}` | As expected |
| R2 | The newest quarter (ended 30 days ago) is listed, but its figures are NaN: yfinance's announced-but-unpopulated column | The fundamentals section is not verified | **`ok`**, with `as_of` 2026-08-27 and no reason. The text reads `₹nanCr`, `Revenue QoQ: +nan%`, `EBITDA Margin: nan%` → **M2** |
| T1 | A healthy price series whose newest requested date is a Sunday (2026-09-20, within the 7-day bound). This is the contract file's default input on any Monday | Technicals `ok` | **`empty`**, "0 bars": the fixture helper raises → **M1** |
| X1 | B2's dimension-only health rule reinstated at runtime (a scratch plugin; no source edited) | The new health tests fail | 100 of 104 `TestHealthDerivation` tests fail. The 4 that pass are the cases where B2 and v2 agree (all ok, `n/a`, the counter partition, the hollow thresholds) |

### Findings

| ID | Severity | Location | Trigger → observed / expected | Impact | Disposition |
|---|---|---|---|---|---|
| **M1** | Medium; **blocking**, as an unmet story evidence requirement | `tests/unit/shared/test_data_health_contract.py`: `_bars` at lines 97–101; the default "fresh" `TODAY - 1 day` at 132 and 137; the 30-day offsets at 216 and 266; `last_business_day` at 568 | With pandas 3.0.2, `pd.bdate_range(end=<Sat or Sun>, periods=300)` returns **299** dates. `_bars` then raises `ValueError` inside the fake `yf.download`, and every producer sees an empty frame. The 1-day default lands on a weekend when the suite runs on Sun or Mon, and the 30-day cases on Mon or Tue. The healthy-path tests (technicals and valuation "verified", and the integration `ok` counterpart) and the 30-day stale cases then fail. Expected: a pass on any date | The invariant suite is red 3 days out of 7. The receipt's "3300 passed" held only because the run was on a Saturday. The next reviewer, and SA-005's CI, would see failures unrelated to the code | **Return to implementation.** Anchor the fixtures to business days: roll `last` back with `pd.offsets.BDay().rollback`, or size the arrays by `len(idx)`, and fix line 568 the same way. Add a guard test that builds the healthy fixture for 7 consecutive end dates |
| **M2** | Medium | `services/data/fetchers/fundamentals.py`: `get_financials` at 85–116 (a present row whose value is NaN is neither `missing_rows` nor substituted); `get_fundamentals_result` at 257–271 | yfinance lists the newest quarter with NaN revenue and operating income. Observed: `ok`, with `as_of` set to that quarter, and the prompt shows `nan`. Expected: not verified (for example `fallback`, naming the NaN quarter), and `as_of` the newest quarter with a finite figure. The prompt text stays byte-identical | An essential section reads usable and fresh without its newest reported figures. SA-003's routed contract ("only `ok`/`cache_hit` usable") would pass it, and SA-045's `missing_rows` key would miss it. How often production statements have a NaN newest quarter is **not measured** (inference) | **Return to implementation** in the same rework. It is bounded to one producer, plus a parametrized case (a NaN newest quarter; a NaN older quarter named in the reason only) |
| I1 | Info (docs) | The implementation receipt's "Rollout" section, and HANDOFF step 3's rollout bullet | The rollout note expects news to read `empty` because "Serper was over its monthly budget in September (2,590 of 2,500)". By code inspection, `SERPER_MONTHLY_LIMIT` (`api_usage.py:53`) feeds only the usage log's `remaining`/`pct_used`, and `news.py` only calls `record_call`. Nothing blocks at 2,500. An owner observation routed to [SA-035](../stories/SA-035.md) the same day, from another session, read 37,747 credits left on the Serper account | An operator could read `empty` news rows as the budget working as designed, rather than as a provider failure | Correct the note in the rework. The R3 fixture (Serper failing for any reason) is unaffected |
| L1 | Low | `fundamentals.py:86-87` | When "Operating Income" and "EBIT" are absent, "Gross Profit" becomes the EBITDA proxy, with no note and an `ok` status | A substitute that looks like a measurement; it overstates the margin. This predates SA-002 | Routed to [SA-045](../stories/SA-045.md) (a note), alongside F3 |

Considered and cleared:

- **Tavily sidecar race.** Two simultaneous live fetches of the *same* query with different outcomes
  could pair one fetch's sidecar with the other's text. Queries include the ticker and company name,
  so this needs the same ticker analysed twice at the same instant. The receipt's sidecar-first
  ordering already makes a crash fail as a cache miss. No action.
- **The macro news miss stays `ok`.** Missing macro news is named in the reason, and macro indicators
  are the core datum. This is a documented design decision.
- **Legacy Tavily entries are `unverified`, so rows read `degraded` until 1 Oct.** This is a
  documented rollout expectation.

### Commands, environment, results

Environment: Windows 11, Python 3.13.11 (`.stockai` venv), pandas 3.0.2, `RL_LEARNING_MODE=adapt`.
Every run used `-p nonet` (the ignored `analysis_data/sa002/nonet.py`) through
`PYTHONPATH=analysis_data/sa002`.

```text
kt_manifest.py verify SA-002-manifest.json            -> 19 files, 0 mismatches, 4d8968fd...
analysis_data/sa002/sa002_diff.py                     -> f605966c..., 142538 bytes, 18 files

pytest -p nonet  test_data_health_contract.py test_data_health_record.py test_bundle_builder.py
   test_bundle_builder_sectors.py test_tavily_cache.py tests/test_tavily_fetcher.py
   test_news_search_recency.py test_orchestrator_unified_branch.py test_error_capture_context.py
   test_unified_e2e_parity.py test_unified_e2e_parity_sectors.py
                                                      -> 266 passed; nonet blocked 0 (Sat 2026-09-26)
pytest -p nonet tests/unit                            -> 3299 passed, 1 failed, 5 skipped (4 min 6 s);
                                                         nonet blocked 194 (the pre-existing set, SA-005 T2)
   the failure: test_delivery_api.py::test_push_subscribe_caps_store_size, PermissionError
   WinError 5 on the store's tmp->json rename; the file alone: 16 passed (a Windows flake,
   unrelated to SA-002; routed to SA-005)
reviewer fixtures (scratch)                           -> R1, R3 pass; R2, T1 fail as described
B2 rule reinstated at runtime (scratch plugin)        -> TestHealthDerivation: 100 failed, 4 passed
check_kt_docs.py (input as reviewed)                  -> errors [], source c5938bef..., 21 pages
check_kt_docs.py (after the review's status edits)    -> errors [], source 5694d413..., 21 pages
```

- **`data/` stayed clean after the full run.** `git status` showed no change to
  `data/nse/key_registry.json` this time.

- **Weekday dependence.** The weekday table comes from `bdate_range` arithmetic on the fixture's
  offsets, and T1 reproduces the Monday input directly on the real clock.
- **A clock shim was tried and discarded.** Replacing `datetime.date` made unrelated producers raise
  `TypeError` on the control days too, so no result from it is used.
- **Not exercised:**
  - Linux or Python 3.11, the Docker image;
  - any production data. The frequency of a NaN newest quarter is unmeasured;
  - a real browser, which is not applicable: no client code reads the record.

### Documentation

- **Checked.** The KT §1, §4, §11 and §12, ARCHITECTURE, CODEBASE.md, `config.yaml`, and the human
  test case 02-F describe the reviewed behaviour, and they label it as unreviewed and undeployed.
- **The review changed status wording only.** It edited those same places to say that the fresh
  review requested changes, and it rebuilt the PDF (`check_kt_docs`: 0 errors).
  - After this review, `kt_manifest.py verify SA-002-manifest.json` therefore shows 5
    mismatches, exactly the status-edited files: `CODEBASE.md`, `docs/ARCHITECTURE.md`,
    `docs/TEAM_TESTING_GUIDE.md`, `docs/TECHNICAL_DESIGN.md` and the PDF (source `5694d413…`).
  - No code or test file changed. The rework regenerates the manifest.
- **Behaviour descriptions stay as they are.** The rework keeps them. If M2's fix adds a status
  reason, the §4 `fallback` sentence ("a core figure was replaced by search snippets or substituted
  zeros") should also name missing (NaN) figures.

### Acceptance checklist

| Criterion | Verdict |
|---|---|
| Provider no-data messages never become healthy merely because they are nonempty | Met (R3, T1's producer path, the implementer's tests) |
| A 9-dimension result with only one live source cannot report fully healthy | Met (50 cases; X1 shows the B2 rule fails them) |
| Existing telemetry readers accept legacy rows and explicitly label unknown provenance | Met (migration test, JSONL v1 line, malformed versions) |
| Parameterized empty / exception / error text / stale / synthetic / verified cases | Present, but **not deterministic** (M1) |
| Integration bundle → row → readers, with no provider calls | Present (0 blocked connections), but its healthy counterpart is weekday-dependent (M1) |
| Hard review: every essential producer | Structured, not string-guessing. One gap: NaN statement values (M2) |

### Decision and follow-up state

- **`changes_requested`.** SA-002 returns to implementation in a **new conversation** for M1 and M2.
  A later fresh review signs off the new revision.
- **Rework scope:**
  - M1: fixture determinism, plus a guard test.
  - M2: NaN statement values in `get_financials` / `get_fundamentals_result`, with the prompt text
    kept byte-identical and re-characterized. Update the KT §4 sentence if the status vocabulary's
    meaning grows.
  - I1: correct the Serper line in the rollout note.
  - Then regenerate the manifest and diff digest, and rerun the focused and full suites under the
    guard.
- **L1** is routed to SA-045 as a note. The full-run rename flake and the date-dependence class are
  routed to SA-005 as a note.
- **`production_verification`** stays `not_started`: nothing was committed or deployed. The owner's
  rollout notes in the implementation receipt still apply after acceptance.
- This review deployed nothing, pushed nothing, changed no production variable, triggered no job
  and sent no message.
