# FIX-011 — fresh review receipt

**Story:** [FIX-011](../stories/FIX-011.md): NSE's per-symbol meta API is gone; restore the
surveillance and suspension guards and an industry source.

**Review context:** a **fresh-session review**, 1 Nov 2026, about 19:43–20:40 IST, session
`stockagent-main-e7` [4cb8e3], a new conversation opened with "continue". The implementation
(session `stockagent-main-3c` [f7fa15]) was not read; only its receipt, the card, the diff and
the code were. The 14 peers (`-5d`, `-f2`, `-4f`, `-8a`, `-5c`, `-49`, `-f0`, `-39`, `-23`,
`-e0`, `-b4`, `-6e`, `-3c`, `-6b`) were idle at the start and before the bookkeeping.

**Verdict: ACCEPTED.** No critical, high or medium finding; every acceptance criterion is met.
Three low findings and one low test gap are follow-ups with owners (below). Nothing was
committed, pushed, deployed or configured. No production state was read and no message was sent.
Network use: read-only fetches of NSE's public archive and report APIs from this machine.

## Reviewed input

- **Baseline:** HEAD `2e14e04` (SA-048's docs commit on `30bf8fc`), nothing staged.
- **Manifest** [FIX-011-manifest.json](FIX-011-manifest.json) `509d392125eafc397752eece05f153abee6100c3099d9135e3fb56e248bc6874`
  (24 files): `kt_manifest.py verify` gives 0 mismatches against the working tree, at the
  start and at the end.
- **Diff** `e8bc2ad9dca6bc7a9fe23853accfd36778f132e423c718f281e418a1c0d3bd78` (94,571 B, 23
  paths), rebuilt by `analysis_data/fix011_review/rv_digest.py` with the implementer's recipe
  (every manifest path but the PDF, sorted, against the index; the new story file against
  `/dev/null`), at the start and at the end: identical.

## Contract checked

- **The gate.** `surveillance_list(session)` walks trading days from the screen's session
  back 7 days. The cached report serves only its own day; other days are fetched, at most 5.
  A report after the session is never used. `apply_guards` reads it once a run: any GSM,
  long-term ASM or short-term ASM stage rejects (`surveillance_asm_gsm`), a status other than
  "A" rejects (`suspended`), an unlisted stock is kept with `surveillance:<SYMBOL>`, and no
  report gives the one check `surveillance`.
- **Visibility.** `_one_check_per_dark_source` collapses a source dark for every checked
  symbol into one check. The weekly result's `dark_checks` keeps run-wide checks only. The
  scheduler's log line prints it. The watchdog's `discovery_guard_sources` reads the persisted
  screens (`shortlist_size` > 0) and is pending when a source has been dark in every screen
  over 7 days or more. Pledge is not judged while its guard is off (`config.yaml`
  `pledge_guard: true`, so it is judged).
- **The sector.** `infer_sector`: the ticker map, else `sector_from_classification` (Yahoo
  industry table, then four Yahoo sectors), else `generic`. The dive asks Yahoo once.
  `holding_sector`: managed record first, then the idea's own key. A re-dive never writes
  `sector`. `promote_symbol` keeps an existing managed record.

### Independent checks

**NSE's real files** (`rv_probe.py`, `rv_coverage.py`, `rv_published.py`; raw files in
`analysis_data/fix011_review/raw/`):

- I fetched `REG1_IND291026.csv` and `REG1_IND301026.csv` myself and read them with the
  `csv` module, by column position, after asserting the header names. `parse_surveillance`
  agrees on every row of both files: 0 differences over 3,216 and 3,217 securities.
- 29 Oct: GSM 74, long-term ASM 143, short-term ASM 47, 16 not active. These are the KT's
  figures. Values seen: GSM 100/0/1/2/3/4, LT 100/1–4, ST 100/1/2, Status A/S, no duplicate
  symbols, no BOM.
- **Coverage.** Of the 2,372 EQ symbols in the 30 Oct universe (the app's `fetch_day` and
  `build_universe`), the 30 Oct report does not list 277. By the app's `instrument_kind`, 276
  of them are funds, which the screen drops as non-companies. One is a company (ABCOTS). 104
  universe stocks are under a measure. So `surveillance:<SYMBOL>` stays rare, as the receipt
  says.
- **When the report is published, and for which day** (I1). The archive's Last-Modified
  for the files dated 26–30 Oct falls on the evening of that date: 18:27 to 20:20 IST, and
  00:41 IST the next day for 29 Oct. NSE's live ASM/GSM lists (`asmTime` 30-Oct-2026) match
  the **29 Oct** file (LT 142 of 143, ST 47 of 47; GSM 74 of 77, the 3 others absent from the
  file). Against the **30 Oct** file they differ by 11 LT and 13 ST symbols: DCMSRIND left
  ST-ASM and SAKUMA entered it.
  - So the file dated D lists the measures in force from the next session. This is an
    inference from the match, not from an NSE statement.
  - The Saturday screen therefore gates on Monday's measures, the right list for a buy. A
    screen of session D runs after D's evening, so it does not look ahead.

**Reviewer cases** `analysis_data/fix011_review/test_rv_fix011.py`: **8 passed + 1 strict
xfail** (L1). The folder's `conftest.py` imports `tests/hermetic.py`'s hooks.

- **RV1:** every security in both real files goes through the archive fake, the cache and
  `apply_guards`, and gets exactly the gates the position-oracle calls for. The 29 Oct screen
  rejects DCMSRIND and passes SAKUMA; the 30 Oct screen does the reverse. A2Z Infra is
  rejected and AURIGROW is `suspended` on both days.
- **RV2, the card's first hard-review question end to end:** the real `run_screen`
  persists its screens, and the real watchdog reads them from disk.
  - The archive is down from 26 Oct and the 23 Oct report is cached. The 30 Oct screen makes
    5 requests, then gates on the cache: A2Z Infra is rejected.
  - On 6 Nov it passes, with one `surveillance` check and no per-symbol ones. The watchdog is
    still satisfied.
  - After the 13 Nov screen the watchdog is pending, with the implementer's exact sentence
    (dark 6 Nov to 13 Nov).
- **RV3 (positive control):** a new stock outside the ticker map, dived as `chemicals`, held
  through `holding_sector` and promoted. Its managed record, the UI's `_sector_for_ticker` and
  the scheduler's `_sector_lookup` all say `chemicals`.
- **RV4:** the brief's earnings line for that holding. The case states the correct result as
  a strict xfail: the line is lost (L1). The control shows the HEAD-era key (`generic`) found
  it.
- **RV5:** a status other than "A" or "S" is rejected as `suspended` (F11-D3).

**Reviewer mutants, in memory** (`rv_mutplug.py`, `run_mutants.sh`; `rv_mutants.txt`): no
file was edited.

| Mutant | Story file | Reviewer cases |
|---|---|---|
| `status_only_s`: only "S" rejects | missed | caught (RV5) |
| `older_cache_serves_first`: an older cached report stops the search before the session's own report is fetched | missed | caught (RV1) |
| `age_eight_days`: 8 days instead of 7 | missed | missed |
| `summary_drops_runwide`: `dark_checks` loses `surveillance` | caught | — |
| `watchdog_any_dark_screen`: a dark run need not be unbroken | caught | — |
| `duplicate_last_row_wins` | missed | missed: NSE's files have no duplicate symbol, so the path is unexercised |
| `empty_classification_refetched` | missed | missed: an extra Yahoo call when Yahoo knew nothing; same key |

The implementer's 33 mutants were not re-run. Their tally is in `analysis_data/fix011/mutants.txt`.

## Hard-review questions

- **Can a stock under ASM/GSM reach the shelf when the source is down?**
  - For 7 days after the last report fetched, no: the cached report gates (RV2).
  - After that, yes, and visibly: one `surveillance` check in the screen and in `dark_checks`.
    The watchdog warns once two screens a week apart were dark, so up to about two weeks after
    the last report.
  - Independent of the source, IPO candidates and re-dives never meet the gate (routed to
    SA-049 by the implementation). So does a user's own watchlist BUY, which `buy_candidates`
    offers to the autopilot. A buy-time check, if SA-049 chooses one, covers all three.
- **Does a new sector key move an existing holding's forecasts to a different store?**
  - No. A managed stock's record wins in `holding_sector`, the deep dive skips managed stocks,
    a re-dive never writes `sector`, and `TICKER_SECTOR` is unchanged. The implementer's pins
    are confirmed by RV3.
  - A new stock outside the map is consistent for every managed-class reader. Two readers that
    resolve through the ticker map are not (L1).
  - The graph-sector readers (`generic/<TICKER>` for any key without a native graph) are the
    documented SA-009 split: KT section 3, SA-026's routed input. FIX-011 adds more stocks to
    that class but changes nothing about it.

## Findings

| # | Severity | Location | Evidence | Disposition |
|---|---|---|---|---|
| L1 | low | `core/delivery/brief.py:434-437` `_resolve_sector`, `services/api/routes/portfolio_api.py:62-66` `_resolve_sector` | Both take the sector from `SectorRegistry.resolve`: the ticker map, else `generic`. Since FIX-011, a stock outside the map is shelved, bought and managed under its Yahoo key (`chemicals`). (a) Confirmed by RV4: the brief's earnings watch line reads the dossier under `generic`, where event ingest never wrote it, so the line is empty. Under HEAD the key was `generic` everywhere and the line was found. (b) Inference, by code inspection: a second portfolio's manual add without a sector holds the stock as `generic` while it is managed as `chemicals`, and its advisor reads predictions under `holding.sector` (`core/portfolio/pipeline.py:306`), an empty store. This needs two portfolios; the production probe of 29 Oct found one account. Not money-moving in the one-account path. | Follow-up: SA-026 (`store_key`, one resolver), via a routed note (a commit-time edit; the card is in the reviewed manifest). KT section 8 Limits gains a bullet (commit-time edit). |
| L2 | low (docs) | `docs/TEAM_TESTING_GUIDE.md` 06-J; KT section 8 "Surveillance and suspension" | 06-J compares the screen with "NSE's ASM and GSM stocks for the screen's date". The report the screen reads, dated that day, lists the measures in force from the next session (I1). DCMSRIND was on NSE's 30 Oct list but leaves it in the 30 Oct file, so it passes the 30 Oct screen. A tester following 06-J would record a false failure. The KT does not say which day the report's measures apply. | Commit-time edits (exact text below). |
| L3 | low (docs) | `core/discovery/candidates.py:96` | The `holding_sector` docstring still says `infer_sector` reads "NSE's industry". | Commit-time edit, comment only (exact text below). |
| T1 | low (test gap) | `tests/unit/test_surveillance_sector_fix011.py` | The story file does not pin three of the fetcher's rules: (a) the cache serves only its own day; (b) any status but "A" rejects; (c) the 7-day bound itself. The reviewer cases pin (a) and (b). | Follow-up: SA-049's card (its buy may call `surveillance_list`), via a routed note: add the three cases. |
| I1 | info | the report's day | Measured publication time and the match above. | Recorded; the KT sentence under L2 states it. |

No finding on the money path, data freshness (7-day bound, no report after the session),
look-ahead, retries (bounded at 5, `close_nse` on every path), the missing-data policy
(visible, not silent) or authorization. The change has no authorization surface.

## Commit-time edits (exact text, in the docs commit after the code commit)

The implementation's own list stands: the KT header (the new code commit), section 1 if a
deploy happened, section 12 FIX-011 `Done`, guide 06-J status, the PDF, and STATE/HANDOFF
with the uncommitted SA-048 deploy record. In addition:

1. **KT section 8, "Surveillance and suspension"** (L2/I1). After "…but for 2 long-term ASM and
   3 GSM symbols." insert: "NSE publishes the report dated a session on that session's evening,
   and it lists the measures in force from the next session: the 30 Oct report no longer had
   DCMSRIND under short-term ASM, though NSE's list of 30 Oct did. So a Saturday screen gates
   on the measures of the Monday after."
2. **KT section 8 Limits** (L1), a new bullet after the TIINDIA bullet: "- The morning brief's
   earnings watch-line and a holding added by hand without a sector take the sector from the
   registry's ticker map (`SectorRegistry.resolve`), so a stock outside the map reads
   `generic` there, whatever its managed record says. For a stock shelved under another key (a
   chemicals maker as `chemicals`), the brief's line finds no dossier, and a second
   portfolio's manual add holds it under `generic`, where its predictions are not.
   **Planned:** SA-026's one `store_key`."
3. **Guide 06-J** (L2). Replace "list NSE's ASM and GSM stocks for the screen's date
   (nseindia.com, Reports, Surveillance)" with "list NSE's ASM and GSM stocks in force on the
   trading day after the screen's date (nseindia.com, Reports, Surveillance, read on that day;
   the report the screen reads, dated the screen's date, already lists them)". Replace "No
   stock that NSE listed under ASM or GSM that day is among the candidates" with "No stock on
   that list is among the candidates". Status: "**FIX-011: accepted 2026-11-01.**"
4. **`core/discovery/candidates.py:96`** (L3), docstring only: "`infer_sector` (the registry,
   NSE's industry, "generic")." becomes "`infer_sector` (the registry's ticker map, Yahoo's
   classification, "generic")."
5. **Card SA-026**, a routed-input section (L1): "## Routed input — 2026-11-01 FIX-011 review
   (two more registry readers). `core/delivery/brief.py` `_resolve_sector` (the earnings
   watch-line's dossier) and `services/api/routes/portfolio_api.py` `_resolve_sector` (a
   holding or watchlist item added without a sector) read `SectorRegistry.resolve`, not the
   managed record. Since FIX-011, a stock outside the ticker map is managed under its Yahoo
   key, so both disagree for it. One resolver (the managed record, then `store_key`) settles
   them. See the FIX-011 review, L1."
6. **Card SA-049**, appended to the FIX-011 routed section (T1 and the watchlist lane): "-
   **Tests to add with any buy-time check** (FIX-011 review T1): the cache serves only its own
   day; a status other than "A" rejects; the 7-day bound. The user's own watchlist BUYs, which
   `buy_candidates` offers too, never meet the screen's gate either; a buy-time check covers
   them with the IPO lane and re-dives."
7. Regenerate the PDF after edits 1–2.

## Commands, environment, results

Windows, `.stockai` venv (Python 3.13), repository root, plain `pytest -p no:cacheprovider`
under `tests/hermetic.py`.

- `analysis_data/fix011_review/rv_digest.py start|end`: see Reviewed input.
- Reviewer cases: 8 passed, 1 xfailed (strict). Reviewer mutants: see the table.
- **Full suite** `python -m pytest -q -p no:cacheprovider tests`: **5,973 passed / 12
  skipped / 1 xfailed / 0 failed** (19m30s, 19:57–20:17 IST, the reviewer's probes and mutants
  running beside it). This equals the implementer's count. The only new path in `git status`
  afterwards was this receipt, written meanwhile (`status_before_suite.txt`,
  `status_after_suite.txt`). Output: `analysis_data/fix011_review/full_suite.txt`.
- `check_kt_docs`: errors `[]`. Header `30bf8fc`, 106 linked sources, none changed since,
  PDF 64 pages.
- The PDF's footer carries the KT's SHA-256 `d235feb70060`, which is the manifest's KT sha256,
  and the new KT sentences are in its text (`rv_pdf.py`).
- `check_broad_except`: OK (150 grandfathered).

**Not exercised:**

- A real Saturday run against production.
- Yahoo's live classification. I re-read neither the 202-ticker sample nor the 150-company
  sample: the table's agreement figures are the implementer's.
- The graph run on a native graph for a stock outside the map. The characterization test fakes
  the orchestrator.
- The watchdog's notice delivery, which is unchanged code.

## Acceptance checklist

- A fixture ASM/GSM list rejects a listed symbol and passes an unlisted one; a fixture
  suspension rejects: **met** (story file; RV1 on NSE's real files).
- A source that answers for no symbol is one visible degraded state per run, and the weekly
  summary says so: **met** (story file; RV2 through `run_screen`). The watchdog warns after a
  week of dark screens: **met** (RV2 on disk).
- `infer_sector` maps a fixture industry outside the ticker map to a real key; routing is
  characterized; existing holdings' store paths stay consistent: **met**. New holdings: L1,
  routed.
- No test reaches the network: **met** (hermetic; the full suite).
- Docs: KT section 8, guide 06-J, AUTOPILOT_GUIDE, CODEBASE and the cards describe the
  reviewed behavior, except L2/L3 (commit-time edits). The PDF matches its source.

## Production verification (separate)

`pending_deployment`. After a deploy, run guide 06-J (as amended by edit 3) on the first
Saturday discovery run, read-only, counts and fields only.

## Decision

**Accepted** for the reviewed input (manifest `509d3921`, diff `e8bc2ad9`, on HEAD `2e14e04`).

- STATE: FIX-011 `done`, production `pending_deployment`; `active_task` null.
- `next_task`: the next ready story by STATE order (recorded in STATE and HANDOFF), not started
  in this conversation.
- Commit and push only at the owner's word, in a job-free window. The code commit is the
  manifest's 24 files exactly as reviewed (`kt_manifest.py verify --rev HEAD`, 0 mismatches);
  the docs commit carries edits 1–7 with the implementation's own.
