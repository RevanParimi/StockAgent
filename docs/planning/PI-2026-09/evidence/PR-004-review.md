# PR-004 — review receipt

**The re-review of rework 1 (20 Oct, evening) accepted PR-004. Its section comes first; the
first review's record follows it.**

## Re-review of rework 1 — 20 Oct 2026 (accepted)

**Phase:** a **fresh-session re-review**: a new conversation opened with "continue", 20 Oct
about 18:56–19:45 IST, session stockagent-main-53. It is neither the implementing conversation
(stockagent-main-71), the first review (stockagent-main-95) nor the rework (stockagent-main-3c,
idle from 18:55). Peers -48, -95 and -3c were idle throughout.
**Verdict: ACCEPTED.** Every first-review finding is resolved or ruled. One low finding (RR-L1)
corrects a premise in the rework's receipt and adds a case to FIX-011; both are commit-time
edits below. Nothing was committed, pushed, deployed or configured. No production state was
read, no message was sent and no reviewed file was changed.

**Reviewed revision:** the uncommitted working tree on
`25fae38ecdc1a85b99b4a2c6d759fc2d11dfbdaf`, pinned by
[PR-004-manifest.json](PR-004-manifest.json)
`aec91b8f5cba9d131378e6468d1e3ab0dde891578949ae436af6cd6db1bc24b9`. That is 33 files: the
first review's 31, plus `services/api/log_buffer.py` and the card.

### In one example

**R1, the home page.** A member adds HEROMOTOCO on the home page, which saves it with no
sector. It is managed under `automobile`. The portfolio holds MARUTI and M&M at 28% of ₹10 L,
and HEROMOTOCO's fresh BUY at ₹5,000 is the SWITCH destination.
- The candidate is now `automobile`, the managed record's sector.
- The 30% cap leaves ₹20,000: 4 shares, not 20 (38%).
- The holding and the managed record agree, so the advisor reads the forecasts the daily
  review writes. The first review's RV1 and RV1c now pass without their marks.

**RW-D1, a shelf idea** (the re-reviewer's RR1, through the real 16:30 pipeline).
1. The deep dive shelved S as `generic`.
2. Earlier, the user had added S on the portfolio screen under `pharma`. Promotion made a
   `pharma` record, since evicted (disabled).
3. A SWITCH buys S as `pharma`. The real `promote_symbol` re-enables the record as it was, and
   the scheduler's reader then passes `pharma` to the daily review. The shelf file still says
   `generic`.
4. When the portfolio already holds a pharma stock larger than the exiting power holding
   (23.1% against 17.5% of ₹13 L), S is no longer in an underweight sector. The run is a plain
   EXIT. The reviewed code's `generic` label would have switched into it.

### Review input and digests

- `kt_manifest.py verify PR-004-manifest.json`: **33 files, 0 mismatches**, at the start and
  again after the full suite and the trace (19:38 IST).
- The rework's base: the 31 files of `analysis_data/pr004/rework1/base/` hash to exactly the
  blob ids of [PR-004-manifest-review1.json](PR-004-manifest-review1.json) (`215be4b9…`, the
  first review's input). This is the re-reviewer's own check (`git hash-object` per file).
- Diffs rebuilt by the re-reviewer's own `analysis_data/pr004_rereview/rr_digest.py`, separate
  from the rework's `rw_digest.py`:
  - **rework:** review-1 bytes to the working tree over the new manifest's paths, PDF
    excluded. **`82fa5b55…`, 52,151 bytes, 11 paths.**
  - **cumulative** against `25fae38`: **`d09d4bbb…`, 205,963 bytes, 32 paths.**

  Both equal the receipt.
- Outside the input: STATE, HANDOFF and the receipts (bookkeeping), PR-003's review receipt
  (the PR-003-P1 result), and the owner's `docs/README.md` line.

### Contract checked

| First-review item | What the re-reviewer found |
|---|---|
| **R1** (high, must fix) | **Resolved.** `holding_sector` takes the managed record's sector (enabled or not), else the item's well-formed sector, else `infer_sector`. Every code writer of the managed file validates the sector: `promote_symbol`'s pattern, and the owner routes' enabled-sector list. So a record always holds a valid key. `managed_sectors()` reads it exactly as `get_active_tickers_with_sector` does (`sector`, default `automobile`), and it never seeds. The advisor reads `VerdictStore(holding.symbol, sector=holding.sector)` (`pipeline.py:269`). RR2 checks the round trip on 400 random cases with the real promotion. |
| **R2** (low, recommended) | **Resolved.** Every answered dive reaches `record_dives`. Under `enforce`, `apply_deep_dives` refuses a non-actionable dive (`gated`). The only other reader of the returned dives is the alert's conviction map, which serves added ideas only, and the weekly line's `deep_dives` count (I1). The memo's only reader is `recently_dived`. The first review's RV4, made strict for **both** modes, finds 0 repeats in 80 random 12-week runs. |
| R3 (info, optional) | **Not taken: RW-D3 accepted.** At most 2 slots, never a re-dive when room ≥ 18. The weekly line's `hygiene.redive_deferred` shows it if it ever happens. RV3 passes as written. |
| R4 (receipt hash) | **Resolved:** `b8b8e93b…` in the receipt's Documentation section. |
| R5 (rollback wording) | **Resolved:** the card says what config does not restore, and that a listing failure needs a code revert or a hand-placed `listing.json`. |
| T1 (harness) | **Resolved:** `_review_day` takes a managed file and the real `promote_symbol`. |
| D4/D9 rulings "with R1" | Now accepted without the condition. |

### Rulings on the rework's decisions

| Decision | Ruling |
|---|---|
| RW-D1 shelf ideas re-keyed by the managed record | **Accepted.** It is the same invariant as R1. The copy never reaches the shelf file: `buy_candidates` has one caller, the pipeline, and nothing persists its output. Promotion from the shelf files the record under the idea's own sector (`shelf.py:419-425`), so only a record made elsewhere re-keys an idea. The visible effect on a SWITCH's sector test (RR1b) is intended, and AUTOPILOT_GUIDE 3.2 says the candidate's sector is what that test counts. |
| RW-D2 SA-003's shelf rule moved to `apply_deep_dives` | **Accepted.** `is_actionable` admits actionable and degraded only. A re-dive goes to `apply_redives` and is dropped with its reason, never `gated` (RR3). SA-003's `test_deep_dive_gate` moved its assertion to the shelf without weakening it. |
| RW-D3 R3 not taken | **Accepted** (above). |
| RW-D4 `infer_sector` may ask NSE | **Accepted, with RR-L1.** It never raises, and `get_symbol_meta` caches per symbol and day. Its premise, "the home page cannot reach it", fails for two of the 16 stocks. |

### Independent checks

1. **The first review's trace, strict.** `make_rr_unmarked.py` builds
   `analysis_data/pr004_rereview/rv_strict/` from the unchanged `test_rv_trace.py`:
   - the three strict xfails are removed;
   - RV4's memo rule (I10) asserts no repeat within 30 days in **either** mode. Before, it
     tolerated enforced abstains;
   - the frequency check expects `{"record": 0, "enforce": 0}`.

   Result: **92 passed** in 6 min 19 s.
2. **The re-reviewer's trace**, `analysis_data/pr004_rereview/rr_trace/test_rr_trace.py`
   (hermetic boundary on; fixture builders borrowed from the story file; expectations
   hand-worked or taken from the scheduler's reader):
   - **RR0:** the swap loads what it says.
   - **RR1a, RR1b:** RW-D1 through the real pipeline and the real `promote_symbol`, as in the
     example above.
   - **RR2:** 400 random cases. Managed files carry sectors, a missing sector key and disabled
     records. Watchlist items carry an empty, padded, upper-case, malformed or different
     sector. The stocks are registry and non-registry ones, plus shelf ideas. For every
     candidate, the real `promote_symbol(candidate.sector)` and then
     `get_active_tickers_with_sector` give the candidate's sector: one store. A watchlist
     candidate is never `generic` when a managed record, the registry or a well-formed item
     sector names one. The managed file is never written by the read.
   - **RR3:** the real Saturday cycle under `enforce`.
     - X (new) abstains, Y (new) is actionable, and OLD (a pre-gate idea re-dived) abstains.
     - `deep_dives` is 3, Y alone is added and alerted, and X is `gated` and remembered.
     - OLD is dropped with "data gate abstain" and is not `gated`.
     - The next Saturday dives nothing.
   - **RR4** (observation): RR-L1.

   Result on the working tree: **7 passed.**
3. **Bite.** `RR_SWAP=base` loads `candidates`, `deep_dive` and `shelf` from the review-1
   snapshot in memory. This is the re-reviewer's own meta-path finder in the trace's conftest;
   no repository file is written. RR1a, RR1b, RR2 and RR3 **fail**, with the reviewed code's
   values: `('generic', 'pharma')`, a SWITCH instead of an EXIT, a broken round trip, and 2
   calls counted for 3. RR0 passes. RR4 calls the rework's signature and was not run on the
   base.
4. **Code reading:**
   - every writer of `managed_tickers.json` (promotion, `/ui/tickers/managed`);
   - every reader of the returned dives and of `dives.json`;
   - every caller of `buy_candidates`;
   - `PUT /ui/watchlist`'s symbol filter (`ui_data.py:1197`);
   - `infer_sector` and `get_symbol_meta`.

### Findings

| # | Severity | Where | Trigger → observed / expected | Impact | Disposition |
|---|---|---|---|---|---|
| RR-L1 | Low (confirmed: RR4; a premise, not a regression) | Receipt RW-D4 (`PR-004-implementation.md:76`) and "For the re-reviewer" (`:209`). Mechanism: `services/api/routes/ui_data.py:203-220` `_ALL_TICKERS`, `core/discovery/deep_dive.py:59-79` `infer_sector`. | The receipt says the home page's 16 stocks are registry automobiles, "keyed `automobile` whether or not they are managed". **Observed:** CEATLTD and TIINDIA, in the extended list, are not in the registry's ticker map. Not managed, a home-page BUY of one is keyed `generic`, because NSE's industry answers 404. **Then:** with MARUTI and M&M at 28%, CEATLTD at ₹3,000 takes the full 10% (33 shares), and automobile exposure is about 38% while the cap counts it as `generic`. Managed, it takes the managed sector and the cap leaves 6 shares. | The store stays one (promotion creates a `generic` record), so the advisor is not blind. It needs one of two named stocks, unmanaged, with a fresh actionable on-request BUY. Same as the reviewed code. It is FIX-011's stated limitation ("every symbol outside the registry's ticker map is `generic`"). | No PR-004 code change. At commit: correct the two receipt sentences and add the case to FIX-011's card (exact text below). |
| I1 | Info | `core/discovery/__init__.py:177`, `scheduler.py:622-628` | Under `enforce`, `deep_dives` now counts abstained answers, so a week in which every dive abstains no longer raises the zero-output alert ("likely a provider/key failure"). | That alert's purpose is a swallowed failure, and abstains are answers; `record` mode always counted them. The gate log and `shelf.gated` name the abstains. Production runs `record`. | None. |
| I2 | Info, pre-existing | `services/api/routes/ui_data.py` `add_managed_ticker` | The owner-only add route files a stock the registry does not know under `automobile` when the generic fallback is off. Since R1, a watchlist BUY of such a stock is capped with the autos. | It keeps one store, and errs toward a smaller buy. | For SA-026 (one sector key); no card note. |

No other finding.

### Acceptance checklist (re-checked)

| Criterion | Verdict |
|---|---|
| 40 candidates in 8 sectors fill 20 by conviction, at most 3 per sector | **Met** (story tests; strict RV4) |
| The deep-dive budget is never exceeded, IPO slots included | **Met** (strict RV4) |
| A watchlist BUY in the window is a candidate; older or abstained is not | **Met** (RV5 through the real score history), now under the right sector (RV1, RR2) |
| An idea older than 30 days is not a buy candidate until re-dived | **Met** (story tests) |
| Old config values reproduce today's shelf exactly | **Met for the shelf logic**; the card now says what config does not restore (R5) |

### Commands and environment

Windows 11, the `.stockai` venv (Python 3.13). The hermetic boundary was on for every pytest
run.

| Command (repository root) | Result |
|---|---|
| `kt_manifest.py verify docs/planning/PI-2026-09/evidence/PR-004-manifest.json` | 33 files, 0 mismatches (start and end) |
| `python analysis_data/pr004_rereview/rr_digest.py` | snapshot 31/31 blobs; rework `82fa5b55…` (52,151 B, 11 paths); cumulative `d09d4bbb…` (205,963 B, 32 paths) |
| `pytest analysis_data/pr004_rereview/rv_strict/test_rv_strict.py` | **92 passed** (6 min 19 s) |
| `pytest analysis_data/pr004_rereview/rr_trace` | **7 passed** |
| `RR_SWAP=base pytest analysis_data/pr004_rereview/rr_trace` (before RR4 was added) | 4 failed (RR1a, RR1b, RR2, RR3), 1 passed (RR0) |
| the story file, SA-003's file and 18 discovery, autopilot, pipeline, promotion and sizing files, plus `tests/unit/pipeline` | **286 passed** |
| `scripts/ci/check_broad_except.py`; `scan_source` on the untracked `candidates.py` | OK (151 grandfathered); `[]` |
| `check_kt_docs.py` | errors `[]`, 49 pages; PDF source `ec058a64…` = the KT's SHA-256 |
| `pytest -q -rfEs -p no:cacheprovider tests` (CI's command) | **5,421 passed, 12 skipped, 1 xfailed, 0 failed** in 20 min 36 s (19:15:56–19:36:40 IST) |

**Not exercised:**
- the live NSE archive and Yahoo;
- the production shelf and managed list (whether CEATLTD and TIINDIA are managed there is
  unknown);
- the rework's mutants (13 of 13 in its receipt; this review's bite check is independent);
- the frontend (no screen changed).

### Commit-time edits (with PR-004's commit, at the owner's word)

1. **FIX-011's card**, a new last bullet under "Effect (code inspection)":
   > - The home page's extended list (`services/api/routes/ui_data.py` `_ALL_TICKERS`) holds
   >   two stocks outside the ticker map, CEATLTD and TIINDIA. A home-page watchlist BUY of
   >   either that is not a managed ticker is keyed `generic` (PR-004's `holding_sector` falls
   >   back to `infer_sector`), so SA-050's cap counts it outside automobile: with MARUTI and
   >   M&M at 28%, CEATLTD at ₹3,000 takes the full 10%, and automobile exposure reaches about
   >   38%. Once a managed record exists its sector wins, so the fix must not re-key an
   >   existing record (this card's hard-review question). PR-004 re-review RR-L1.
2. **The implementation receipt:**
   - in RW-D4, replace "The home page cannot reach it: its 16 stocks are registry
     automobiles." with "The home page reaches it only for CEATLTD and TIINDIA, the two of
     its 16 stocks outside the registry, when they are not managed (re-review RR-L1).";
   - in "For the re-reviewer", replace "The home page's watchlist offers only the 16 registry
     automobiles, which are keyed `automobile` whether or not they are managed." with "Of the
     home page's 16 stocks, 14 are registry automobiles, keyed `automobile` whether or not
     they are managed; CEATLTD and TIINDIA are keyed `automobile` only when managed
     (re-review RR-L1)."
3. **As for every story at commit:**
   - KT: section 12's PR-004 row `Open` → `Done`, the header's code revision and edition,
     section 1's production paragraph, then the PDF and `check_kt_docs`;
   - the AUTOPILOT_GUIDE header;
   - the testing guide's 06-E to 06-H status lines: "accepted 2026-10-20, committed as
     `<sha>`; production verification pending".

### Production and follow-up state

STATE: PR-004 `done`, `active_task: null`, **`next_task: PR-006`**, which is ready (no
dependencies) and not started. Production verification is `pending_deployment`.

After the owner's commit and push, in a job-free window (not 08:30–09:20, 16:25–17:15, or
Saturday 12:25–14:00 IST):
- the first Saturday's "weekly cycle complete" line: `listing`, `hygiene`, `redived`, and at
  most 20 deep dives;
- guide 06-E to 06-H. 06-F's fifth run is the home-page case.

Production runs `record`, so RW-D2 changes nothing there until the gate is enforced.

---

## First review — 20 Oct 2026 (changes requested)

**Story:** [PR-004](../stories/PR-004.md): enough researched ideas to fill 10+ positions.
**Context:** a **fresh-session review**, 20 Oct 2026, from 09:56 IST. Session
stockagent-main-95, a new conversation opened with "continue". It is not the implementing
conversation (stockagent-main-71). The one peer, stockagent-main-48, was idle. The PR-003-P1
Yahoo probe ran first (it passed; see [PR-003's review receipt](PR-003-review.md)).
**Reviewed:** the uncommitted working tree on `25fae38ecdc1a85b99b4a2c6d759fc2d11dfbdaf`.
- Input [PR-004-manifest.json](PR-004-manifest.json) `215be4b9…`: 31 files, **0 mismatches**
  (`kt_manifest.py verify`). It is kept unchanged as
  [PR-004-manifest-review1.json](PR-004-manifest-review1.json), so the rework's new manifest
  does not replace the reviewed one.
- Diff rebuilt by the reviewer (`analysis_data/pr004_review/rev_digest.py`). It takes the paths
  from the manifest and picks `git diff HEAD` or `--no-index` by whether HEAD holds the path.
  Result: **`5c6c392d…`, 179,179 bytes, 30 paths**, the receipt's digest. Every other dirty
  path is bookkeeping (STATE, HANDOFF, the receipt, the PR-003 review receipt's probe result)
  or the owner's `docs/README.md` line.

**Verdict: CHANGES REQUESTED.** One high finding:
- **R1:** a watchlist BUY with no stored sector is bought as `generic`. The holding then reads
  the wrong prediction store, and SA-050's sector cap does not see it.

Also found:
- **R2** (low): under the enforced gate, an abstained new dive is not remembered, so it is
  dived again every Saturday.
- **R5** (low): the rollback note is incomplete.
- **R3, R4:** information only.
- **T1:** a test-harness note.

Everything else holds, including all five acceptance criteria as written and the card's three
hard-review questions. Nothing was committed, pushed or deployed, no production state was read
and no message was sent. No payload file was changed by this review.

## In one example (R1)

The home page saves a watchlist with `PUT /ui/watchlist`. With Atlas on (`config.yaml`
`atlas.enabled: true`), that writes `WatchlistItem(symbol=sym, added=today)`, with no sector
(`services/api/routes/ui_data.py:1216`). Take a member who adds HEROMOTOCO there. It is a
managed ticker, analysed every day under `automobile`.

The portfolio is ₹10 L of equity:
- MARUTI and M&M (both `automobile`) at ₹1.4 L each, 28% together;
- ITCO, ₹2.2 L;
- ₹5 L cash.

On a review day:
1. A holding EXITs. HEROMOTOCO's latest analysis is a fresh, actionable BUY at 0.80.
2. `candidates.watchlist_idea` builds the candidate with `sector = item.sector or "generic"`,
   so `generic` (`core/discovery/candidates.py:127`).
3. **The sector cap.** SA-050 counts holdings whose `sector` equals the buy's
   (`core/portfolio/sizing.py:122`).
   - As `generic`, the buy takes the full 10% position: 20 shares at ₹5,000. Automobile
     reaches **38% against the 30% cap**.
   - Under its real sector, the cap leaves ₹20,000: 4 shares, and automobile stays at 30%.
   - RV1c, hand-worked.
4. **The prediction store.** The autopilot buys it as `generic` and calls
   `promote_symbol(cand, "generic")`. That keeps the existing managed record's `automobile`
   (`core/portfolio/promotion.py:88-109`).
   - From the next day the advisor reads `VerdictStore(sym, sector="generic")`, that is
     `data/predictions/generic/HEROMOTOCO`.
   - The daily review and the monthly forecast write `data/predictions/automobile/HEROMOTOCO`
     (`services/scheduler/python/scheduler.py:778-781, 986-988`;
     `core/intelligence/rl/stores/prediction_store.py:117-120`).
   - So the holding is advised without its own forecasts: confidence 0.5, a flat direction,
     no thesis review, and ADD blocked for "no forecast rows".
   - RV1, through the real 16:30 pipeline with the real `promote_symbol`.

Nothing warns. A shelf idea never has this problem: its `sector` comes from `infer_sector`, and
the managed record is created with that same key.

## Contract checked

| Question | What the reviewer found |
|---|---|
| Card: does the shelf cap use the sizing key (SA-050)? | **No, deliberately** (D3/D4): the cap counts Yahoo's `market_sector`, sizing counts `sector`. Accepted for shelf ideas: their `sector` is `generic` for most screened stocks and is the store key, so changing it belongs to SA-026/FIX-011 (routed, SA-049 card note). R1 is a different case: the true key is known and the new path drops it. |
| Card: can a watchlist stock skip the data gate? | **No.** RV5 writes real `FinalReport`s through `ScoreStore.save` and reads them with `buy_candidates`' default reader. Actionable and degraded qualify. Abstain (record mode) and `INSUFFICIENT DATA` (enforced) do not. The pipeline then still applies SA-003's destination gate and SA-050's band. |
| Card: measured cost, not estimated? | **Yes.** The receipt's table comes from the production run logger (139 runs, median $0.019). The split between dives and paper reviews is labelled as inference. Not re-run here (production). |
| Budget bound, IPO slots included | RV4: 80 random 12-week runs of the real Saturday cycle in both gate modes. Calls never exceed `deep_dive_count`. Every eligible IPO is dived. Re-dives take exactly min(room, due), pre-gate first. A failed call counts. |
| Only companies | RV4: no analyst call for a fund, REIT, InvIT or unlisted symbol in any run. LIQUID1 is dropped in week 0 with its series and ISIN. |
| Sector cap and shelf size | RV4: after every run, no market sector holds more than the cap, and the shelf never exceeds its size. |
| Rotation from the latest dive (D13) | RV4: no active idea has a latest dive older than 60 days. `added` and `close_at_add` never change for an idea (the auditor's start is kept). |
| Re-dive drops (D7) | RV4: every refreshed idea is actionable or degraded and at the floor. In enforce, no new idea is shelved without an actionable or degraded gate. |
| The dive memo (D10) | Holds in record mode: RV4 found 0 repeats. **Not in enforce** (R2): 123 repeats across the enforce-mode runs, and RV2 shows the minimal case. |
| Issue time and freshness | A watchlist band comes from the close on or before the analysis day (IST); a future-dated analysis is refused. A shelf idea older than 30 days is not offered. The idea-quality line counts only grades that matured by the week's Sunday. One grade per ref, as `advice_grades` does. |
| Real score-history shape | `run_at` naive UTC, bare ticker, `report_json` = the full report with `decision_gate.status` (RV5 through the real writer; `ui_data` also reads bare tickers). |
| Old shelf files | Every new field has a default; `source` is never persisted. |

## Rulings on the implementer's decisions

| Decision | Ruling |
|---|---|
| D1 company = `INE…` ISIN, not series RR/IV | **Accepted.** The equity-series preference in `fetch_listing` keeps a company's debenture row from standing for the symbol. |
| D2 fail closed without a listing | **Accepted**, with R5 (rollback wording). |
| D3 the cap counts `market_sector`; D4 `sector` unchanged | **Accepted for shelf ideas.** D4's statement that `sector` "after a buy, keys the holding's prediction store and managed-ticker record" fails for the watchlist path (R1). |
| D5 the budget counts calls | **Accepted** (RV4). |
| D6 re-dive order and room | **Accepted** (RV4), with R3. |
| D7 re-dive drops in either mode | **Accepted** (RV4). |
| D8 buy candidates fail closed | **Accepted.** |
| D9 watchlist BUYs (owner-confirmed) | **Accepted** as rules (RV5), with R1 for the sector they carry. |
| D10 the dive memo | **Accepted**, with R2. |
| D11 idea quality | **Accepted.** |
| D12 events | **Accepted.** |
| D13 rotation from the latest dive | **Accepted** (RV4). |
| L1–L10 | **Accepted** as documented. |

## Findings

| # | Severity | Where | Trigger → observed / expected | Impact | Disposition |
|---|---|---|---|---|---|
| R1 | **High** (confirmed: RV1 and RV1c) | `core/discovery/candidates.py:127` (`sector=item.sector or "generic"`). Reached through `services/api/routes/ui_data.py:1216` (a home-page watchlist item has no sector, Atlas on), `core/portfolio/pipeline.py:318-323` (`sector_lookup` from the candidates) and `core/portfolio/autopilot.py:246-281` (bought under that sector; `promote_symbol` keeps the managed record's own). | A watchlist item with an empty sector whose stock is a managed ticker under a real sector → candidate, SWITCH buy and holding all `generic`; the managed record stays `automobile`. **Expected:** the candidate carries the key its forecasts are written under: the managed record's sector when the stock is managed, else `item.sector`, else the deep dive's `infer_sector`. Never a fixed `generic`. | The bought holding is advised without its forecasts (store split), and SA-050's 30% sector cap and the SWITCH underweight test do not count it with its sector: 38% automobile in RV1c. Reachable through the main screen's watchlist. Silent. Introduced by this story's new buy path; SA-049 will make that path the main way cash is invested. | **Rework 1, must fix.** Test it through the real pipeline with the real `promote_symbol` and a managed-ticker file (RV1 is the shape), plus the sizing case (RV1c). Docs: KT section 8's sentence on what `sector` keys, AUTOPILOT_GUIDE section 3 (the candidate's sector), and guide 06-F (a home-page watchlist stock). |
| R2 | Low (confirmed: RV2, RV4) | `core/discovery/deep_dive.py:185-186` (`if enforced and not redive: continue`) with `core/discovery/__init__.py` `record_dives(dives, ...)` | `decision_gate.mode: enforce`, and a new screen or IPO candidate abstains → it is not returned, so it is not in `dives.json`, and it is dived again the next Saturday while it stays in the screen. **Expected:** D10 and the cycle's own comment ("below the floor, abstained, or outranked") say it is remembered for 30 days. | Only in enforce. Production runs `record` (SA-003's NO-GO of 1 Oct). The budget bound still holds, but repeated abstains crowd out new names. At the 1 Oct decision's 32% abstain rate, that is up to a third of new calls. | **Rework 1, recommended:** remember an enforced abstain too. Test: RV2's enforce case. |
| R3 | Info (RV3) | `core/discovery/__init__.py:96` `room = max(0, DEEP_DIVE_COUNT - len(ipo_cands))`, computed before the memo and company filters | An IPO candidate the memo or the company rule then removes still holds a re-dive slot, and a screen name takes it while a due re-dive waits a week. | At most `ipo_max_deep_dives` (2) slots, and only when due re-dives exceed the room. The first Saturday after a deploy has 3 re-dives and room 18 or more. | Optional in rework 1: count only the IPO candidates that will be dived. |
| R4 | Info (receipt) | `evidence/PR-004-implementation.md`, Documentation: "PDF rebuilt … source SHA-256 `ec3bf7fd…`" | The PDF and `check_kt_docs` give `b8b8e93b…`, as the commands table does; `ec3bf7fd…` is the build before D13. | Bookkeeping only. | Correct in rework 1. |
| R5 | Low (docs) | Receipt "For the owner" item 4 and the card's "Rollout and rollback" section (the KT has no rollback text) | "Rollback: set the old values" restores the sizes, the cap, re-dives and watchlist BUYs. It does not restore three things: the company rule, the fail-closed listing, or the call-counting budget. They are unconditional. If the first listing fetch fails on the server, no deep dive runs that week whatever the config says. | An owner rolling back with config alone would still see zero dives after a listing failure. | Rework 1: one sentence. Config restores the sizes; a listing failure needs a code revert or a hand-placed `listing.json`. The run's `errors` line names it. |
| T1 | Test note | `tests/unit/test_idea_supply_pr004.py` `_review_day` | The pipeline harness stubs `promote_symbol` and gives every watchlist item the sector `pharma`, so neither R1 condition can occur. | This is why R1 passed self-review. | Rework 1: add the sectorless, managed case. |

No other finding. Not counted as findings:
- the per-portfolio EOD-window read when a qualifying watchlist item exists (fine at today's
  few users);
- the Windows `WinError 5` on rapid memo writes (L8). RV4 met it once: the code logged it and
  went on, and Linux renames do not fail this way.

## Rework 1 (next "continue" conversation)

1. **R1:** resolve a watchlist candidate's `sector` from the managed record, else the item,
   else `infer_sector`. Test with the real `promote_symbol` and a managed file. Expected: the
   holding's sector equals the managed one, and automobile is capped at 30% in RV1c's
   portfolio.
2. **R2** (recommended): remember enforced abstains in `dives.json`.
3. **R3** (optional), **R4**, **R5** and **T1** as above.
4. Docs: the KT section 8 sentence, AUTOPILOT_GUIDE section 3, guide 06-F (and the PDF).
5. A new manifest and digest; the fresh re-review then signs off the new revision.

The reviewer's trace (`analysis_data/pr004_review/test_rv_trace.py`) marks R1 (twice) and R2
as strict `xfail`. After the fix they should pass, so the strict marks fail as a reminder:
remove them in the re-review.

## Acceptance checklist

| Criterion | Verdict |
|---|---|
| 40 candidates in 8 sectors fill 20 by conviction, at most 3 per sector | **Met** (story tests; RV4's cap invariant) |
| The deep-dive budget is never exceeded, IPO slots included | **Met** (RV4) |
| A watchlist BUY in the window is a candidate; older or abstained is not | **Met** (RV5, through the real score history). R1 concerns the sector it then carries. |
| An idea older than 30 days is not a buy candidate until re-dived | **Met** (story tests through the real pipeline) |
| Old config values reproduce today's shelf exactly | **Met for the shelf logic** (the characterization test). The company rule and call-counting budget are unconditional by the card's own additions (see R5). |

## Commands and environment

Windows 11, the `.stockai` venv (Python 3.13). The hermetic boundary (SA-005) is on for every
pytest run, the reviewer's trace included (`analysis_data/pr004_review/conftest.py`).

| Command (repository root) | Result |
|---|---|
| `.stockai/Scripts/python.exe scripts/docs/kt_manifest.py verify docs/planning/PI-2026-09/evidence/PR-004-manifest.json` | 31 files, 0 mismatches |
| `.stockai/Scripts/python.exe analysis_data/pr004_review/rev_digest.py` | `5c6c392d…`, 179,179 bytes, 30 paths |
| `.stockai/Scripts/python.exe -m pytest -q -p no:cacheprovider analysis_data/pr004_review/test_rv_trace.py` | **89 passed, 3 xfailed** (strict: R1 in RV1 and RV1c, R2 in RV2). `--runxfail` shows the observed values in the example above. |
| the story file, `test_discovery_cycle_ipo.py`, `test_discovery_deep_dive.py`, `test_discovery_settings.py`, `test_operator_notices_owner_only_fix008.py`, `test_scheduler_discovery_job.py`, `tests/unit/shared/test_decision_gate_sa003.py` | **163 passed** |
| `.stockai/Scripts/python.exe scripts/ci/check_broad_except.py` | OK (151 grandfathered) |
| `.stockai/Scripts/python.exe scripts/docs/check_kt_docs.py` | errors `[]`; PDF source `b8b8e93b…` = the KT's SHA-256 (49 pages) |
| `.stockai/Scripts/python.exe -u -m pytest -q -p no:cacheprovider -o console_output_style=count tests` | **5,400 passed, 12 skipped, 1 xfailed, 1 failed** in 12 min 49 s. The failure is `test_store_migration_sa009.py::test_rollback_never_merges_into_a_live_store_that_reappeared`: `WinError 5` on `os.replace` in `store_migration.py`, which PR-004 does not touch, while this review's trace ran at the same time. Its file re-run alone: **22 passed**. The implementer's final run was 5,401 passed. |
| `kt_manifest.py verify` again at the end | 31 files, 0 mismatches |

**Not exercised:**
- the live NSE archive and Yahoo classification (the implementer probed both on 20 Oct);
- the production shelf and the Saturday job;
- the mutation run (the implementer's 17 of 17; this review's trace is independent of it);
- the frontend (no screen changed).

## Production and follow-up state

STATE: PR-004 `changes_requested`, `active_task: null`, **`next_task: PR-004`** (rework 1 in a
new conversation, then a fresh re-review in another). Production verification `not_started`.
After acceptance and the owner's push, the checks are guide 06-E to 06-H and the first
Saturday's "weekly cycle complete" line (`listing`, `hygiene`, `redived`).
