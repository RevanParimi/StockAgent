# PR-004 — implementation receipt

**Story:** [PR-004](../stories/PR-004.md): enough researched ideas to fill 10+ positions.
**Phase:** implementation, 20 Oct 2026, about 04:15–05:41 IST. Session
stockagent-main-71, a new conversation opened with "continue" at 23:04 IST on 19 Oct; all 21
peers were idle at the start and at bookkeeping. **Baseline:**
`25fae38ecdc1a85b99b4a2c6d759fc2d11dfbdaf` (HEAD, clean for every payload path).
**Status after this phase:** `review_required`. Nothing was committed, pushed or deployed. No
production state was read, and no message was sent. Public NSE and Yahoo endpoints were read
once each from this machine to choose data sources (below).

## Rework 1 (20 Oct 2026, about 18:04–18:55 IST)

**Context.** Session stockagent-main-3c, a new conversation opened with "continue"; peers
stockagent-main-48 and -95 idle throughout. It answers the fresh review's CHANGES REQUESTED
([review receipt](PR-004-review.md)). It includes a same-conversation self-review, which is not
the fresh re-review. **Status after:** `review_required`. Nothing was committed, pushed or
deployed, no production state was read, and no message was sent.

**Input.** The reviewed input [PR-004-manifest-review1.json](PR-004-manifest-review1.json)
(`215be4b9…`) verified with 0 mismatches at the start. Its 31 files were copied to the ignored
`analysis_data/pr004/rework1/base/` and checked by blob id (`base_snapshot.py`).

### In one example (R1)

A member adds HEROMOTOCO on the home page, which saves it with no sector. It is a managed
ticker under `automobile`. The portfolio holds MARUTI and M&M at 28% of ₹10 L. A holding
EXITs and HEROMOTOCO's fresh BUY at 0.80 becomes the SWITCH destination at ₹5,000.

- **Reviewed code:** the candidate was `generic`. The sector cap did not count the two
  automobile holdings: 20 shares, automobile 38%. The holding was `generic` while its managed
  record stayed `automobile`, so the advisor read `predictions/generic/HEROMOTOCO` and the
  daily review wrote `predictions/automobile/HEROMOTOCO`.
- **Now:** the candidate is `automobile`, the managed record's sector. The cap allows 4
  shares and automobile ends at 30%. The holding and the managed record agree, so the advisor
  reads the forecasts the daily review writes.

### Changes

| Finding | Change |
|---|---|
| **R1** (high, must fix) | `candidates.holding_sector`: a managed stock's managed-record sector, enabled or not; else the item's own sector when it is a well-formed key (lowercased, promotion's `is_valid_sector`); else the deep dive's `infer_sector`. It runs only after every other check has passed. The managed file is read through the new read-only `log_buffer.managed_sectors()`, which reads a record as the scheduler does (`sector`, default `automobile`) and never seeds a missing file. A fresh shelf idea whose stock is managed under another sector is offered as a copy under the managed sector (RW-D1). |
| **R2** (low, recommended) | `run_deep_dives` returns every answered call, an abstained one included, in either gate mode, so the cycle's `record_dives` remembers it for 30 days. `ShelfStore.apply_deep_dives` refuses a dive that is not actionable under the enforced gate (summary `gated`). In `record` mode it keeps it, as before (RW-D2). |
| R3 (info, optional) | **Not taken** (RW-D3). |
| R4 (info) | The Documentation section's PDF hash now reads `b8b8e93b…` (review-1 input), with the correction noted. |
| R5 (low, docs) | Rollback sentence in the card's "Rollout and rollback" and in "For the owner" item 4: config does not undo the company rule, the fail-closed listing or the call-counting budget. A listing failure needs a code revert or a hand-placed `listing.json`. |
| T1 (test note) | The pipeline harness `_review_day` takes `watch_sector` and `managed`. With `managed` it writes the sandbox's managed file and runs the real `promote_symbol`. |

### Decisions (delegated, recorded)

- **RW-D1. Shelf ideas follow the same rule.** The invariant is that a candidate carries the
  key its forecasts are written under. A shelf idea can break it too. Example: the deep dive
  shelves S as `generic`; the user then adds S on the portfolio screen under `pharma`, and
  promotion creates a `pharma` record. A SWITCH would have held S as `generic`, the same
  split as R1. Now it is offered under `pharma`. The shelf's own record is unchanged (a copy
  is offered). *Revisit with* SA-026's one sector key.
- **RW-D2. Where SA-003's shelf rule lives.** Two options:
  - A (chosen): the dive returns every answer and the shelf refuses a non-actionable dive
    under `enforce`. There is one memo writer (the cycle). The rule now sits where an idea is
    minted, so a later add path cannot bypass it.
  - B: keep the filter in `run_deep_dives` and have it write the memo itself. That splits memo
    writes across two places.

  With A, SA-003's `test_deep_dive_gate` now applies the dive to a real shelf: under `enforce`
  an abstain is returned and not shelved, and the gate-log rows are unchanged. Two visible
  effects, both only under `enforce`: the weekly line's `deep_dives` counts abstained dives (they
  were calls, and the budget already counted them), and `shelf.gated` names them. Production
  runs `record`, so nothing changes there until enforce.
- **RW-D3. R3 not taken.** With `deep_dive_count` 20 and `ipo_max_deep_dives` 2, re-dives
  have at least 18 slots. In steady state about 5 are due a week (L6), and the first Saturday
  has 3. A memo'd IPO's reserved slot never delays a re-dive, so the fix has no production
  effect, and it would change the reviewer's RV3 and RV4 room model. *Revisit if* the weekly
  line's `hygiene.redive_deferred` is ever non-empty.
- **RW-D4. `infer_sector` can ask NSE.** For a watchlist stock with no sector, not managed and
  not in the registry, `infer_sector` calls NSE's meta API (404 today, so `generic`). It runs
  last, after every other check. The home page reaches it only for CEATLTD and TIINDIA, the two
  of its 16 stocks outside the registry, when they are not managed (re-review RR-L1). A portfolio-screen watchlist add carries a sector and creates the managed
  record. It is kept so the watchlist and the deep dive key a stock alike; FIX-011 fixes
  `infer_sector` for both.

### Tests

The story file has **89 tests (was 69)**. Expected values are hand-worked or come from the
managed file and the scheduler's own reader, not from the changed code.

| Finding | Tests |
|---|---|
| R1 | `test_a_watchlist_candidate_carries_the_sector_its_forecasts_use` (6 cases: the managed record wins over an empty or another item sector; an unmanaged item's own sector, normalized; `infer_sector` when neither, or when the sector is malformed or the managed one empty); `…_read_from_the_managed_file_enabled_or_not` (a disabled record, a record without a sector); `…_never_writes_the_managed_file`; `…_shelf_idea_managed_under_another_sector_…` (RW-D1); `test_a_home_page_watchlist_buy_counts_in_its_real_sector_for_the_cap` (RV1c's portfolio, hand-worked to exactly 4 shares; with the managed file, and without it through the real `infer_sector` and the registry) |
| R1 + T1 | `test_pipeline_holds_a_watchlist_buy_under_the_key_its_forecasts_use`: the real 16:30 pipeline, the real `promote_symbol` and a sandbox managed file. The holding's sector equals the sector the scheduler's `get_active_tickers_with_sector` passes to the daily review, and the two `PredictionStore` directories are one. Cases: the home-page item of an enabled managed ticker; of a disabled (evicted) one; an unmanaged item with its own sector, where promotion creates the record. |
| R2 | `test_cycle_remembers_an_abstained_new_dive_for_the_month` (both modes: not dived again at 7 and 28 days, dived again at 35; the memo row reads `abstain`); `test_every_answer_is_returned_even_an_abstain_under_the_enforced_gate`; `test_under_enforce_the_shelf_mints_only_actionable_ideas` (abstain and no gate refused, degraded and actionable kept, all kept in `record`) |

**Existing tests changed** (a contract moved; no assertion relaxed): SA-003's
`test_deep_dive_gate` (RW-D2) and the story's former
`test_an_abstaining_redive_is_returned_even_when_the_gate_is_enforced`, now
`test_every_answer_is_returned_…` (both dives come back; the shelf refuses the new one). The
`fresh_rules` fixture records `infer_sector` calls and returns `inferred`: for a symbol outside
the registry it would ask NSE, which the hermetic boundary refuses.

**Bite on the reviewed code.** `analysis_data/pr004/rework1/rw_swap_plugin.py` compiles
modules from other bytes in memory (no repository file is written). `RW_SWAP=base` loads
`candidates`, `deep_dive` and `shelf` from the review-1 snapshot, and `log_buffer` from HEAD:
**18 of the story and SA-003 tests fail, 129 pass.** The 18 are the new R1 and R2 cases and
SA-003's enforce-abstain case. The controls pass on the reviewed code: record mode, degraded
and actionable dives, and an unmanaged item with its own sector.

**Mutants** (`run_mutants.py`, in memory): **13 of 13 caught.**

- R1a no managed lookup; R1b item sector first; R1c a fixed `generic` fallback; R1d shelf
  ideas not re-keyed; R1e an unvalidated own sector; R1f enabled records only; R1g no
  `automobile` default; R1h a seeding reader; R1i the watchlist path ignoring the managed map.
- R2a the shelf ungated; R2b the dive dropping an enforced abstain again; R2c the gate in
  `record` too; R2d degraded refused.

R1f's first anchor matched twice: the plugin refused it and no test ran. The runner first
reported that as "survived"; it now says BROKEN, and R1f was re-run and caught.

**The reviewer's trace, unchanged** (`analysis_data/pr004_review/test_rv_trace.py`): **88
passed, 4 failed.** The four are expected:

- the three strict xfails now pass, so they fail as XPASS(strict): R1 in RV1, R1 in RV1c `""`,
  and R2 in RV2 `enforce`;
- `test_rv4_r2_shows_up_in_enforce_mode` asserts that enforced repeats are above 0, and they
  are now 0.

RV3 passes as it was, because R3 was not taken. A copy with the three marks removed and the
frequency check expecting 0 (`make_rv_unmarked.py`, `rv_unmarked/`) gives **92 passed**. For
the re-review: remove the marks and flip that assertion.

### Commands and environment

Windows 11, the `.stockai` venv (Python 3.13). The hermetic boundary was on for every run.

| Command (repository root) | Result |
|---|---|
| `kt_manifest.py verify …/PR-004-manifest-review1.json` (start) | 31 files, 0 mismatches |
| `pytest tests/unit/test_idea_supply_pr004.py tests/unit/shared/test_decision_gate_sa003.py` | **147 passed** (89 + 58) |
| the same with `RW_SWAP=base` and `-p rw_swap_plugin` (`PYTHONPATH=analysis_data/pr004/rework1`) | 18 failed, 129 passed (above) |
| `python analysis_data/pr004/rework1/run_mutants.py` | 13 of 13 caught (`mutants_out.txt`, `mutants_out_r1f.txt`) |
| `pytest analysis_data/pr004_review/test_rv_trace.py`; `pytest analysis_data/pr004/rework1/rv_unmarked` | 88 passed, 4 failed (above); 92 passed |
| the 27 discovery, shelf, promotion, autopilot, pipeline and sizing test files, SA-003's file and `tests/unit/pipeline` | **327 passed** |
| `pytest -q -rfEs -p no:cacheprovider tests` (CI's command), 18:36:36–18:48:21 IST | **5,421 passed, 12 skipped, 1 xfailed, 0 failed** in 11 min 39 s |
| `scripts/ci/check_broad_except.py`; `scan_source` on the untracked `candidates.py` | OK (151 grandfathered); `[]` |
| `build_kt_pdf.py`, then `check_kt_docs.py` | 49 pages, source `ec058a64…`; errors `[]` |

### Documentation (current design)

- **KT section 8:**
  - step 5: the memo keeps every answered dive, an abstain too, and a failed call is retried;
  - step 6: under `enforce` only actionable or degraded dives become ideas;
  - the market-sector paragraph: what `sector` keys and who writes under the managed
    record's sector;
  - a new paragraph after the buy candidates on the sector each candidate carries, with the
    HEROMOTOCO example.
- **PDF:** rebuilt, source `ec058a64…`.
- **AUTOPILOT_GUIDE:**
  - 3.1: the review writes under the managed entry's sector, and promotion keeps an existing
    entry's sector. The old sentence said promotion files the entry under the holding's
    sector, which fails for an existing entry: R1's mechanism;
  - 3.2: the sector a candidate carries, with the example.
- **Testing guide 06-F:** a fifth run for the home-page stock (sector `automobile`, the 30%
  cap note, its own forecasts the next day). The status lines of 06-E to 06-H now read
  "implemented 2026-10-20 and reworked the same day; fresh re-review pending".
- **CODEBASE:** the rows for `candidates.py` (`holding_sector`), `shelf.py` (the enforce
  rule) and `log_buffer.py` (the managed-file readers).
- **The card:** its rollback sentence (R5).
- Not changed: PRODUCT_MAP (its row stays at that level), ARCHITECTURE.

### Manifest and digests

- **Review input:** [PR-004-manifest.json](PR-004-manifest.json), **33 files**. Review 1's 31,
  plus `services/api/log_buffer.py` and the card `stories/PR-004.md`. SHA-256 of its LF bytes
  is **`aec91b8f5cba9d131378e6468d1e3ab0dde891578949ae436af6cd6db1bc24b9`**, with 0
  mismatches. Excluded: STATE, HANDOFF, this receipt, the review receipt, PR-003's review
  receipt (its probe result) and the owner's `docs/README.md` line.
- **Rework diff:** **`82fa5b55491a2f4c0a77bb4c3631cb2e8f2d3306d72f8214bfdc19eebdea0195`**,
  52,151 bytes over 11 paths (`rw_digest.py`). For a changed review-1 path it diffs the
  snapshot against the working tree (headers relabelled `a/PATH b/PATH`). For the two new
  paths it uses `git diff HEAD`.
- **Cumulative diff** against `25fae38`: **`d09d4bbb41d4213581d3f222013b58821fc46f1ebe03738e5f642c4e4ad9c9f8`**,
  205,963 bytes over 32 paths (the PDF excluded). The reviewer's own
  `analysis_data/pr004_review/rev_digest.py`, run on the new manifest, gives the same digest.
  That run overwrote its `rev.diff`; it was restored from `analysis_data/pr004/pr004.diff`
  (`5c6c392d…`, review 1's diff).

### Self-review (same conversation)

- **Found and fixed:**
  - the mutant runner reported a broken anchor as "survived";
  - a "kept, as today" change-note in `apply_deep_dives`' docstring, reworded as design;
  - the guide's reference to the sizing rule pointed at section 7 instead of section 6.
- **Checked:**
  - no new network path in the suite: `infer_sector` runs only for an unmanaged, sectorless
    item, and the tests stub it or hit the registry;
  - reading the managed file never writes it;
  - an old `shelf.json` and `dives.json` load unchanged;
  - `record` mode is unchanged end to end. The characterization test and RV4's record seeds
    still pass.

### For the re-reviewer

- Worth a hard look:
  - RW-D1 (shelf ideas re-keyed by the managed record);
  - RW-D2 (the SA-003 rule moved from the dive to the shelf, and `deep_dives` now counting
    enforced abstains);
  - RW-D3 (R3 not taken);
  - RW-D4 (`infer_sector`'s NSE call on a rare path).
- After a deploy, production runs `record`, so RW-D2 changes nothing there. R1 decides the
  sector of every watchlist buy of a managed stock. Of the home page's 16
  stocks, 14 are registry automobiles, keyed `automobile` whether or not they are managed;
  CEATLTD and TIINDIA are keyed `automobile` only when managed (re-review RR-L1).

## In one example

The production shelf of 11 Oct (product review section 11): 9 active ideas, 7 shelved before
the data gate existed, LIQUID1 (a liquid ETF) abstained, AUROPHARMA verified, 5 of 9 tagged
`generic`.

- **Before (the next Saturday at HEAD):** 10 deep dives on new screen names; the 7 pre-gate
  ideas and LIQUID1 stay; the shelf can hold 10, all in one sector.
- **After (the first Saturday after a deploy):**
  - LIQUID1 is dropped: "not a company: NSE lists it as fund (series EQ, ISIN INF174KA1LV5)".
  - The 7 pre-gate ideas are re-dived first. Each is refreshed in place (new conviction, band
    and gate, `added` kept) or dropped with the reason, for example "re-dive 2026-10-24: data
    gate abstain".
  - The other 13 analyst calls go to IPO slots and new screen names, never to an ETF.
  - The shelf grows towards 20, at most 3 per market sector ("Healthcare", "Industrials", …).
- **Each 16:30 review after that:** the autopilot may buy a shelf idea only if its latest
  dive is at most 30 days old, or the user's own watchlist stock whose latest analysis is a
  fresh, actionable BUY.

## What changed

| Area | Change |
|---|---|
| Config (`config.yaml`, settings) | `deep_dive_count` 10 → 20, `shelf_size` 10 → 20; new `max_ideas_per_sector: 3`, `redive_after_days: 30`, `watchlist_buys: true`. The settings fallbacks (0, 0, false) keep the old behaviour when a key is absent. |
| Instrument listing (`services/data/fetchers/bhavcopy.py`) | `fetch_listing`, `refresh_listing`, `load_listing`: series and ISIN per symbol from NSE's archive UDiFF bhavcopy, cached in `data/discovery/listing.json`; a failed fetch keeps the last good listing. |
| Only companies (`core/discovery/universe.py`) | `instrument_kind` (company `INE…`, fund `INF…`, trust = series RR/IV, other, unknown) and `companies_only`. |
| Screen (`core/discovery/screen.py`) | Ranks companies only when a listing exists; without one it keeps EQ symbols and records the degraded check `instrument_listing`. |
| Deep dive (`core/discovery/deep_dive.py`) | Budget counts analyst calls, a failed call included. No call for a non-company or an unknown symbol, or at all without a listing. Candidates flagged `redive` bypass the shelved skip, take their close from the EOD window, and come back even when an enforced gate abstains. `entry_levels` is shared with watchlist candidates. Each result carries Yahoo's `market_sector` and `industry`. |
| Shelf (`core/discovery/shelf.py`) | Per-market-sector cap with in-sector replacement; `apply_redives`; `redive_due`; `drop_non_companies`; `backfill_classification`; `_enforce_sector_cap` after every mutation path; the dive memo (`record_dives`, `recently_dived`); `cap_key`, `last_dived`, `dive_is_fresh`. |
| Cycle (`core/discovery/__init__.py`) | Listing refresh, shelf upkeep and the re-dive queue before the screen; re-dives first in the budget, IPO slots kept; the memo filters screen and IPO candidates; the summary gains `listing`, `hygiene` and `redived`. |
| Buy candidates (`core/discovery/candidates.py`, new) | `buy_candidates`: fresh shelf ideas plus the user's own watchlist BUYs, with the reason for every exclusion. |
| Pipeline (`core/portfolio/pipeline.py`) | The 16:30 review offers `buy_candidates` to the advisor and the autopilot instead of every active shelf idea; if the list cannot be built, none is offered. |
| Scorecard (`core/portfolio/results.py`) | `idea_quality` and the "Idea quality" line (shelf ideas against the Nifty at 10 and 30 sessions). |
| Schemas (`src/backend/shared/schemas/discovery.py`) | `DeepDiveResult.market_sector`, `industry`; `ShelfIdea.market_sector`, `industry`, `dived`, `source`. All default, so old `shelf.json` files load unchanged. |
| Surveillance fetcher | `market_classification` (Yahoo sector and industry). |

## Data sources: what was measured

Public endpoints, read from this machine on 20 Oct; raw output in `analysis_data/pr004/`
(ignored).

- **NSE `equity-meta-info`** (what `get_symbol_meta` reads): **404** for LIQUID1, CASHIETF,
  NIFTYBEES, MARKSANS, STYLAMIND and EMBASSY (`meta_probe.py`). This machine's meta cache (82
  entries, 11 Jul) is all `degraded`. NSE's `quote-equity` answered **403** (`quote_probe.py`).
- **Yahoo `.info`:** `quoteType` is "EQUITY" for LIQUID1, CASHIETF and NIFTYBEES, so it cannot
  tell a fund from a company. EMBASSY reads "MUTUALFUND". Companies carry `sector` and
  `industry` (MARKSANS "Healthcare" / "Drug Manufacturers - General"); the funds carry neither.
- **NSE archive UDiFF bhavcopy of 16 Oct** (`udiff_probe.py`): 3,675 rows. `FinInstrmTp` is
  `STK` for every row. Series EQ holds 2,337 `INE` and 353 `INF` ISINs: LIQUID1
  `INF174KA1LV5`, CASHIETF `INF109K1A021`, GOLDBEES `INF204KB17I5`. EMBASSY is series RR,
  INDIGRID series IV. AUROPHARMA, MARKSANS, DEEPINDS, ALIVUS, DYCL are EQ with `INE` ISINs.

So the ISIN is the only structural field that separates a company from a fund, and the NSE
industry the card names is unavailable.

## Design decisions (delegated, recorded)

- **D1. Only companies, by ISIN and series.** A symbol is a company when its ISIN begins
  `INE` and its series is not RR or IV. Never by name. Example: LIQUID1 (EQ, `INF…`) is a
  fund; a company called "Liquid…" with an `INE` ISIN is a company.
  *Revisit if* NSE lists a company's shares under a non-`INE` ISIN.
- **D2. Fail closed.** No listing at all: no deep dive that week, and the run's errors say
  why (the screen still runs and records `instrument_listing`). A symbol the listing does not
  know is never dived. Without the cache's first fill, the owner sees zero dives and the ops
  zero-output alert, not a fund on the shelf.
- **D3. The cap counts Yahoo's market sector.** The card asks for the NSE industry; that
  source is gone (above). Yahoo's sector (about 11 values) is the level the sizing cap works
  at: 30% of equity is about 3.6 holdings of ₹83,000, so 3 ideas per sector matches what can
  be bought. Its finer `industry` would let 6+ healthcare ideas in. An idea with no market
  sector is not capped: lumping unknowns together is the `generic` label again.
  *Revisit when* FIX-011 or SA-026 settles one sector key.
- **D4. `sector` stays as it was.** It picks the analysis graph and, after a buy, keys the
  holding's prediction store (`VerdictStore(symbol, sector=…)`) and managed-ticker record.
  So the card's hard-review question, "does the cap use the sizing key?", is answered **no,
  deliberately**: SA-050 counts `sector`, which is `generic` for most screened stocks. Routed
  to SA-049 (card note) and FIX-011.
- **D5. The budget counts calls.** Before, it counted results: a failed call, or an abstain
  skipped under `enforce`, made another call. Now `deep_dive_count` bounds every call. With no
  failed call and no enforced abstain, a call always yields a result, so the two counts give
  the same sequence of calls.
- **D6. Re-dive order and room.** Ideas with no gate first, then dives older than 30 days,
  oldest first. Re-dives get `deep_dive_count − IPO candidates` slots. An idea that rotates
  this run (its latest dive older than `stale_days`) is not re-dived. A re-dive keeps `added`
  and `close_at_add` (the auditor's shelf grades keep their start), resets the band from
  today's close, and restarts the rotation clock (D13).
- **D7. When a re-dive drops an idea.** Not actionable (abstain, or no gate) or below the
  0.55 floor, in either gate mode. `degraded` stays, as `is_actionable` allows elsewhere. A new
  idea keeps today's rule (in `record` an abstained new dive is still shelved): the card asks
  for the drop on re-dive only.
- **D8. Buy candidates fail closed.** If the list cannot be built, the review offers none
  (a warning names the account), rather than every shelf idea.
- **D9. Watchlist BUYs** (the card: "owner to confirm at implementation"; implemented on, as
  the card recommends; **the owner confirmed on 20 Oct: "do as per recommendation"**;
  `discovery.watchlist_buys` turns it off):
  - only `source` "user" or "discovery". A stock the autopilot sold onto the watchlist
    (`autopilot_exit`) does not qualify: the exit rule just sold it;
  - an actionable gate in **either** mode. In `record` an unverified shelf idea can still be a
    destination; an unverified watchlist stock is not a candidate at all;
  - verdict BUY or STRONG BUY, conviction at least 0.55, NSE lists it as a company;
  - at most 30 days old. The card says "within `stale_days`" (60); the stricter of that and
    the shelf's 30-day rule applies, so both kinds of idea age alike;
  - the band and invalidation come from the close on the analysis day (IST), as a deep dive
    sets them;
  - a held stock, or one active on the shelf, is not offered from the watchlist;
  - when only autopilot exits are left on the watchlist, the score
    history, the EOD window and the listing are not read at all.
- **D10. The dive memo.** Found by the fill test: week 2 spent 5 of 20 calls re-diving week 1's
  rejects. Momentum keeps strong names in the screen for weeks, so they would take the top of
  every Saturday's budget. A screen or IPO candidate dived in the last 30 days and not on the
  shelf is now skipped. Limit L4.
- **D11. Idea quality** is a line, not a flag: since the start, for 10 and 30 sessions, the
  count that beat the Nifty and the median gap; grades that matured after the week's Sunday
  are left out; one grade per ref. A stored row from before PR-004 renders without it.
- **D12. Events.** Cap replacements and every re-dive or non-company drop write `dropped`
  with the reason; a refreshed idea writes `redived`. The brief reads only `added` and
  `promoted`, so it is unaffected.
- **D13. Rotation counts from the latest deep dive** (delegated by the owner on 20 Oct: "do as
  per recommendation, i trust your technical expertise"). `rotate_stale` and the re-dive
  queue's rotation filter read the latest dive (`dived`, else `source_screen_date`, else
  `added`) instead of `added`. The 60-day rotation stood in for "this idea may have gone
  stale"; the monthly re-dive now checks that directly. So an idea that keeps passing it
  stays, one that fails is dropped with the reason (D7), and one that cannot be re-dived
  (held, no close, deferred by the budget) ages out 60 days after its last dive. Example:
  REDINGTON, shelved 5 Sep and re-dived on 24 Oct, would otherwise rotate out on 7 Nov, 14
  days after a passing check; now it stays until its next re-dive decides, and rotates only
  if no re-dive passes before 24 Dec.
  - Without re-dives nothing changes: every idea's `dived` and `source_screen_date` equal
    `added` (a new add sets both to the cycle date; the July and production shelves show the
    same), so rotation is HEAD's (`test_without_redives_rotation_is_todays`).
  - The auditor's shelf ref (`shelf:added|symbol`) is unchanged, so grades still count from
    the day the idea was shelved.
  - An undatable idea now rotates (age taken as very large); before, its bad date would have
    raised inside `rotate_stale`.

## Invariant tests

`tests/unit/test_idea_supply_pr004.py`, 69 tests. Fixtures are hand-built; the analyst is a
stub; transports are fakes or blocked by `tests/hermetic.py`.

| Card criterion or question | Test |
|---|---|
| 40 candidates in 8 sectors fill 20 by conviction, at most 3 per sector | `test_forty_dives_in_eight_sectors_…` (oracle: the 20 strongest of each sector's 3 strongest, by sorting); `test_cycle_fills_the_shelf_to_twenty_…` (two real Saturdays: 20 calls each, week 2 dives exactly the other 20, the end shelf equals the oracle) |
| The budget is never exceeded, IPO slots included | `test_property_the_budget_bounds_every_call` (300 random lists with re-dives, IPOs, repeats, managed, shelved, funds, missing closes, failures and gates in both modes: calls = the first `max_n` eligible); `test_a_failed_call_counts_…`; `test_cycle_redives_…_keeps_the_ipo_slots` |
| A fresh watchlist BUY is a candidate; an older or abstained one is not | `test_a_fresh_actionable_watchlist_buy_…`, six excluded cases, the 30-day boundary, autopilot exits (alone, and beside the user's own pick), funds, held and shelved stocks; through the real 16:30 pipeline in both modes, and never in `record` for an unqualified one |
| An idea older than 30 days is not a candidate until re-dived | `test_a_shelf_idea_older_than_thirty_days_…`; through the real pipeline: EXIT, then a SWITCH after the re-dive |
| Old values reproduce today's shelf exactly | `test_old_values_reproduce_todays_shelf_exactly`: HEAD's `apply_deep_dives` transcribed as an oracle, 40 random 12-week histories, ideas, summaries and events identical; the cycle sends exactly IPO + screen; every active idea is offered |
| No sector exceeds the cap after any sequence | `test_property_no_sector_ever_exceeds_the_cap`: 60 random 25-step sequences of adds, re-dives that name sectors, backfills, drops and rotations |
| Only companies | the kind table on the 16 Oct rows; names never count; the listing fetch (NCD row sharing a ticker, weekend walk-back, fallback to the last good listing); the screen never ranks a fund; no analyst call for a fund, trust, unknown symbol or an IPO REIT; LIQUID1 dropped by the cycle |
| Re-dives | queue order on 9 dated ideas; refresh in place; drop on abstain, no gate, or below the floor; a re-dive that names a full sector drops the weakest |
| Rotation (D13) | REDINGTON's dates: not rotated 63 days after shelving when re-dived at 49; rotated 61 days after the re-dive; a never-re-dived idea rotates at 61 days as before; re-dives off: 20 random weeks match HEAD's rule |
| Idea quality | hand-worked counts and medians, a grade after the week left out, a duplicate counted once, another lane ignored; no grades; an old row |

**Mutation check** (`analysis_data/pr004/mutants.py`): 17 of 17 mutants killed, every file
restored byte for byte (`sha256sum -c`): no sector cap, budget counting results, no company
check, stale ideas buyable, watchlist skipping the gate, abstained re-dive kept, no memo, idea
quality past the week, autopilot exits qualifying, re-dives taking the IPO slots, pre-gate not
first, the screen keeping funds, no cap after backfill, non-companies kept, and the score
history read when only autopilot exits are left, rotation from `added`, and the re-dive
queue filtered by `added`.

**Existing tests changed** (the contracts changed; no assertion relaxed):
`test_discovery_cycle_ipo.py`, `test_scheduler_discovery_job.py` and
`test_operator_notices_owner_only_fix008.py` patch the new `refresh_listing` stage (a network
stage the sandbox refuses); `test_discovery_deep_dive.py` gives its candidates a listing and a
classification and now proves the failing analyst was really called (without a listing it
would have passed without reaching it); SA-003's `test_deep_dive_gate`
(`tests/unit/shared/test_decision_gate_sa003.py`) gets the same listing and classification;
`test_discovery_settings.py` asserts 20, 20, 3, 30 and true.

## Commands and environment

Windows 11, the `.stockai` venv (Python 3.13), Node with the vendored Playwright Chromium.
Hermetic boundary on (SA-005).

| Command (repository root) | Result |
|---|---|
| `.stockai/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/unit/test_idea_supply_pr004.py` | **69 passed** |
| `.stockai/Scripts/python.exe -m pytest -q -rfEs -p no:cacheprovider tests` (CI's command), first run | 5,394 passed, 12 skipped, 1 xfailed, **3 failed**: SA-003's `test_deep_dive_gate` (no listing, so no dive; fixed by giving it one) |
| the same, second run | **5,399 passed, 12 skipped, 1 xfailed, 0 failed** in 13 min 25 s |
| the story file after `test_only_autopilot_exits_left_reads_nothing` was strengthened during that run (M15) | **67 passed**; M15 then killed |
| the same, final run after D13 (rotation), on the final code | **5,401 passed, 12 skipped, 1 xfailed, 0 failed** in 12 min 2 s |
| `.stockai/Scripts/python.exe analysis_data/pr004/mutants.py` | **17 of 17 killed** (M1–M14 in one run, M15 after its test was strengthened, M16–M17 with D13); files restored |
| `.stockai/Scripts/python.exe scripts/ci/check_broad_except.py` | **OK (151 grandfathered)** |
| `python scripts/docs/build_kt_pdf.py`, then `check_kt_docs.py` | 49 pages (was 47), source `b8b8e93b…`; errors `[]` |

Raw outputs (ignored, `analysis_data/pr004/`): `full_suite.txt`, `full_suite2.txt`,
`mutants_out.txt`, the three source probes and their outputs, `dive_cost_probe.py`,
`digest.py`, `bookkeeping.py`.

## Documentation

Each change is written as current design.

- **KT** (`docs/TECHNICAL_DESIGN.md`):
  - section 8 "Discovery" rewritten: the weekly run in six steps (rotation from the latest
    dive in step 6, D13), the market sector, a cap
    example, buy candidates, and the limits (NSE meta 404, Yahoo's `quoteType`, the 30-day wait
    of a capped-out idea), with **Planned:** FIX-011;
  - section 6 "Cash deployment": the ideas come from section 8's buy candidates;
  - section 7: the scorecard table gains "Idea quality";
  - section 11 "Portfolio economics": SA-049's sizing must count real sectors;
  - section 12: a FIX-011 row; PR-004 stays `Open` until the fresh review accepts it.
  - `candidates.py` is named in code text, not linked: `check_kt_docs` requires a linked file
    to exist at the declared revision `84eefda`. The link and the header are commit-time edits.
- **PDF** rebuilt: 49 pages, source SHA-256 `b8b8e93b…` (the review-1 input; this line first
  said `ec3bf7fd…`, the build before D13, corrected in rework 1 as R4); `check_kt_docs` `[]`.
  Rework 1 rebuilt it again (its section above).
- **AUTOPILOT_GUIDE**: section 3 (buy candidates, with an example; SWITCH judges the top 5
  candidates), section 4 (a watchlist stock needs an actionable analysis in either mode),
  section 7 (cash deployment). Its header is a commit-time edit.
- **CODEBASE** (three new settings rows, the two changed values, the `stale_days` row (D13), rows for `universe.py`,
  `candidates.py`, `shelf.py`, `deep_dive.py`, `bhavcopy.py`, `surveillance.py`) and
  **PRODUCT_MAP** (the funnel line, Universe, Deep dive, Shelf, a Buy candidates row).
- **Human testing guide** (HT-06): new cases 06-E (the first Saturday after deploy), 06-F
  (watchlist BUYs, four runs), 06-G (a stale shelf idea, then re-dived), 06-H (the Idea quality
  line). Status: "PR-004: implemented 2026-10-20; fresh review pending."
- **Planning:** new card FIX-011; PI README order (FIX-011 at 15, before SA-049) with its
  reason; card notes on SA-049 (buy from `buy_candidates`; one sector key for the shelf and
  sizing caps), SA-044 and SA-026 (their NSE industry source is gone).
- No change needed: ARCHITECTURE (no discovery detail), the frontend (the weekly view renders
  any labelled line), `docs/README.md`.

## Manifest and digest

- **Review input:** [PR-004-manifest.json](PR-004-manifest.json), 31 files. The SHA-256 of
  its LF bytes is **`215be4b9339179838faabdd73a2c7689a27318fbb8d9d3e99344a34e5ce8eba9`**;
  `kt_manifest.py verify` gives 0 mismatches.
  - Code (13): `config.yaml`, `core/discovery/__init__.py`, `candidates.py` (new),
    `deep_dive.py`, `screen.py`, `shelf.py`, `universe.py`, `core/portfolio/pipeline.py`,
    `core/portfolio/results.py`, `services/data/fetchers/bhavcopy.py`,
    `services/data/fetchers/surveillance.py`, `src/backend/shared/config/settings/base.py`,
    `src/backend/shared/schemas/discovery.py`.
  - Tests (7): `tests/unit/test_idea_supply_pr004.py` (new), `test_discovery_cycle_ipo.py`,
    `test_discovery_deep_dive.py`, `test_discovery_settings.py`,
    `test_operator_notices_owner_only_fix008.py`, `test_scheduler_discovery_job.py`,
    `tests/unit/shared/test_decision_gate_sa003.py`.
  - Docs (11): the KT and its PDF, AUTOPILOT_GUIDE, PRODUCT_MAP, the testing guide, CODEBASE,
    the PI README, FIX-011 (new), SA-026, SA-044, SA-049.
  - Excluded: STATE, HANDOFF, this receipt (bookkeeping), and the owner's own line in
    `docs/README.md`.
- **Diff digest:** **`5c6c392d3fb6013da3bf7556a06e7f1c5dbed4acc45c7b073f8e8d60508e8866`**,
  179,179 bytes over 30 paths (every manifest path except the PDF), by
  `analysis_data/pr004/digest.py`. It checks that HEAD is `25fae38` and that no changed path
  lies outside the manifest and the bookkeeping, runs `git diff --no-color --no-ext-diff HEAD --
  PATH` for the 27 modified paths and `git diff --no-index /dev/null PATH` for the 3 new files,
  then sorts by path and concatenates.

## Self-review

Same-conversation self-review; it does not replace the fresh review. Found and fixed:

- **Week 2 re-dived week 1's rejects** (5 of 20 calls in the fill test). Added the dive memo
  (D10).
- **A wrong rationale in the KT draft.** It said re-keying `sector` to pharma would run the
  multi-call legacy graph. Every native graph is on the one-call path and pharma routes to
  `generic` anyway. The real reason is the prediction-store and managed-ticker keys (D4).
- **A test that would pass without reaching the analyst.** The deep-dive failure test had no
  listing, so after this change it returned `[]` before any call. It now gets a listing and
  asserts the call was made.
- **An overclaim.** "The guards have tested nothing since July" rested on this machine's July
  cache, not production. Reworded everywhere to the 20 Oct probe.
- **Readers loaded for nothing.** With only autopilot exits on the watchlist, the review read
  the score history and a 90-session EOD window every day. It now returns first. M15 at first
  survived (the test passed its own reader); the test now refuses all three default readers.
- **SA-003's deep-dive gate test** called `run_deep_dives` without a listing; it now has one.
- **Windows rename contention** in three high-churn tests (L8).

Checked and left as is:

- An old `shelf.json` loads: every new field has a default.
- The brief reads only `added` and `promoted` events; `redived` and the new `dropped` reasons
  do not reach it.
- The auditor's shelf ref (`added|symbol`) is unchanged, so a re-dive never re-grades an
  idea; only the rotation clock moves (D13).
- No broad `except` swallows silently (guard OK, 151 grandfathered, none added).

## Measured cost per deep dive (production, read-only)

The owner ran `analysis_data/pr004/dive_cost_probe.py` through `railway ssh` on 20 Oct (about
05:50 IST, deployed `25fae38`) and pasted the output; it is kept in
`analysis_data/pr004/dive_cost_probe_out_20261020.txt` (ignored). The probe prints counts,
costs and the shared shelf only.

| Saturday | Runs | Total | Median | Max | Median tokens | From that week's screen |
|---|---:|---:|---:|---:|---:|---:|
| 29 Aug | 16 | $0.3026 | $0.0192 | $0.0210 | 9,926 | 9 |
| 5 Sep | 17 | $0.3217 | $0.0185 | $0.0237 | 9,522 | 10 |
| 12 Sep | 17 | $0.3281 | $0.0192 | $0.0214 | 9,649 | 9 |
| 19 Sep | 17 | $0.3307 | $0.0198 | $0.0214 | 10,169 | 11 |
| 26 Sep | 17 | $0.3135 | $0.0187 | $0.0217 | 9,762 | 9 |
| 3 Oct | 24 | $0.4582 | $0.0187 | $0.0219 | 9,724 | 8 |
| 10 Oct | 17 | $0.3163 | $0.0185 | $0.0219 | 9,655 | 10 |
| 17 Oct | 14 | $0.2624 | $0.0193 | $0.0217 | 10,031 | 9 |
| **All** | **139** | **$2.6335** | **$0.0190** (mean $0.0189) | | | |

- **Measured:** one analysis run in the Saturday discovery window costs a median **$0.019**
  (mean $0.0189, highest $0.0237, about 9,700 tokens), as the run logger recorded it.
- **What the runs are.** The window holds more runs than the 10-dive budget, and only 8 to 11
  a week were symbols from that week's screen. After the dives, the same job's paper lane
  reviews every active shelf idea, and each review re-runs the analyst once
  (`daily_review._run_todays_agent_scores`), plus a new paper envelope once a month
  (`paper_lane.ensure_paper_envelope`). With 6 to 10 shelf ideas that accounts for the rest:
  code inspection and inference, since the probe does not label a run. Every run is the same
  one-call analysis, so the per-run cost is the cost of a deep dive.
- **Projection at 20 dives a week:** 86.7 dives a month × $0.019 = **$1.65 a month** for the dives.
  A 20-idea shelf also means up to 20 paper reviews a week, another **$1.65**, plus up to 20
  envelopes a month (about $0.38). The whole Saturday job would go from **$1.43 a month**
  today (8 Saturdays, $2.63) to about **$3.70 a month**. Small next to the 16:30 reviews, but
  watch the provider credit for the first weeks (SA-035 is not live).

**The production shelf on 20 Oct** (6 active ideas, nothing deployed yet):

| Idea | Added | Gate | Latest dive | After a deploy |
|---|---|---|---|---|
| REDINGTON | 5 Sep | none | 45 days | not a buy candidate; re-dived first on Saturday |
| DEEPINDS | 5 Sep | none | 45 days | the same |
| MARKSANS | 12 Sep | none | 38 days | the same |
| AUROPHARMA | 10 Oct | actionable | 10 days | candidate |
| LIQUID1 | 10 Oct | abstain | 10 days | candidate until Saturday drops it (see L10) |
| SAMBHV | 17 Oct | actionable | 3 days | candidate |

So the first Saturday spends 3 calls on re-dives, drops LIQUID1, and has up to 2 IPO slots and
15 or more calls for new ideas. No idea has a market sector yet: the backfill names them that
day. `listing.json` and `dives.json` do not exist yet; the first run writes them.

## Limits and follow-ups

- **L1. The paper lane grows with the shelf.** Up to 20 review runs a week as well as 20 dives
  (above). Measured per run; the split between dives and reviews is inferred from the code.
- **L2. NSE's meta API is gone** (404), so the screen's ASM/GSM and suspension gates test
  nothing and `infer_sector` never sees an industry. Routed: new card
  [FIX-011](../stories/FIX-011.md), ordered before SA-049; notes on SA-044 and SA-026.
- **L3. Sizing still counts `sector`.** A fourth `generic` holding of about ₹83,000 hits the
  30% "sector" cap. Routed: SA-049 card note (D4).
- **L4. A capped-out idea waits 30 days** for its next dive, even when its sector frees a place
  sooner (D10).
- **L5. An idea with no Yahoo sector is not capped** until a re-dive or backfill names one;
  then the cap drops the weakest.
- **L6. Re-dives cost budget.** In steady state each idea is re-dived once, at 30 days, before
  rotating at 60, so about 5 of 20 calls a week. The first Saturday after deploy spends up to
  18 on re-dives if the shelf is old; the number of pre-gate ideas in production today is
  what the probe reports.
- **L7. A held shelf idea is not re-dived** (managed symbols are skipped). It is held, so it
  is not a buy candidate anyway.
- **L8. Windows file contention in tests.** Thousands of rapid `os.replace` saves on one file
  raised WinError 5 twice. The two property tests and the characterization test use an
  in-memory store (the real class with `load`/`save` in memory); persistence code is unchanged.

- **L9. A strong idea can stay for months** (D13). Its place is turned over only by a failed
  re-dive, the sector cap, or a stronger newcomer when the shelf is full. The paper lane keeps
  reviewing it weekly (about $0.019 a week each).
- **L10. LIQUID1 until the first Saturday.** After a deploy it stays on the shelf, 10 days old
  with an abstained gate, until Saturday's run drops it. In `record` mode it can be a SWITCH
  destination, exactly as today at HEAD (SA-050's entry band still applies). Removing it
  sooner is the shelf's drop action in production: the owner's call.

## For the owner

1. **Watchlist BUYs: confirmed on 20 Oct** ("do as per recommendation"). They stay on.
2. **Cost: measured** (above): about $0.019 a run; the Saturday job goes from about $1.43 to
   $3.70 a month.
3. **Optional, production:** drop LIQUID1 from the shelf now instead of waiting for the first
   Saturday after the deploy (L10).
4. **After acceptance:** commit and push in a job-free window (not 08:30–09:20, 16:25–17:15,
   or Saturday 12:25–14:00 IST). The new values take effect at the next Saturday 12:30 run.
   Rollback: set `shelf_size: 10`, `deep_dive_count: 10`, `max_ideas_per_sector: 0`,
   `redive_after_days: 0`, `watchlist_buys: false`. Config restores the sizes, the cap,
   re-dives and watchlist BUYs. It does not undo the company rule, the fail-closed listing or
   the call-counting budget: if the listing cannot be fetched, no deep dive runs whatever the
   config says, and that needs a code revert or a hand-placed `data/discovery/listing.json`
   (the run's `errors` line names it). (Rework 1, R5.)
