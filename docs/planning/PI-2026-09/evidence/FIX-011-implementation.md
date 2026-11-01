# FIX-011 — implementation receipt

**Story:** [FIX-011](../stories/FIX-011.md): NSE's per-symbol meta API is gone; restore the
surveillance and suspension guards and an industry source.

**Phase:** implementation, 1 Nov 2026, about 16:46–18:00 IST. Session `stockagent-main-3c`
[f7fa15], a new conversation opened with "continue". The 13 peers (`-5d`, `-f2`, `-4f`, `-8a`,
`-5c`, `-49`, `-f0`, `-39`, `-23`, `-e0`, `-b4`, `-6e`, `-6b`) were idle at the start and before
the bookkeeping (ListAgents). This phase includes a same-conversation self-review, which is not
the fresh review.

**Baseline:** HEAD `2e14e04` (SA-048's docs commit on `30bf8fc`). The working tree held the
uncommitted SA-048 push and deploy record in STATE and HANDOFF; it is kept.

**Status after this phase:** `review_required`. Nothing is committed, pushed, deployed or
configured. No production state was read and no message was sent. Network use was read-only
probes of public data from this machine: NSE's archive files and its ASM/GSM report APIs, and
Yahoo Finance (scripts and raw files in `analysis_data/fix011/`, ignored). No test reaches the
network (`tests/hermetic.py`).

## In one example

- **Before:** on 29 Oct A2Z Infra was under long-term ASM, stage I. The screen asked NSE's
  `equity-meta-info` for it, got 404, recorded `surveillance:A2ZINFRA` and passed it, as it did
  every shortlisted stock. A chemicals maker outside the registry's ticker map was keyed
  `generic`.
- **Now:** the screen reads NSE's 29 Oct Surveillance Indicator report once and rejects A2Z Infra
  with `surveillance_asm_gsm`. The chemicals maker, dived now, is keyed `chemicals` (Yahoo:
  "Specialty Chemicals"): the generic graph still runs, and its stores sit under
  `.../chemicals/<SYMBOL>`. A stock already held or shelved keeps the key it has.

## Sources probed (1 Nov, from this machine)

| Source | Answered | Used for |
|---|---|---|
| NSE `equity-meta-info` (the old source) | 404 on 20 Oct (PR-004's probe); not retried | nothing now; `get_symbol_meta` deleted |
| NSE daily-reports index (`/api/daily-reports?key=CM`) | yes | found the file names below |
| `REG1_IND291026.csv`, "Surveillance Indicator New" (and the older `REG_IND`) | 200, 3,216 rows, 63 columns | **the surveillance and suspension source** |
| NSE `reportASM` / `reportGSM` APIs | 200 (30 Oct) | cross-check only: long-term ASM 142 of 143 in both, short-term 47 of 47, GSM 74 of 77 (one day apart) |
| `NSE_CM_security_<date>.csv.gz`, `sec_list_<date>.csv`, `EQUITY_L.csv` | 200 | not used (no surveillance column) |
| `ind_niftytotalmarket_list.csv` (Industry column) | 200, 750 companies | compared, not used: 176 of the registry's 202 tickers, coarse classes |
| Yahoo Finance `.info` sector and industry (`market_classification`) | 193 of 202 registry tickers; 146 of 150 sampled Total Market companies | **the industry source** |

Encoding, read off the file and checked against NSE's APIs: "100" means not under the measure;
any other value is a stage (GSM stage 0 included: 67 stocks, all in NSE's GSM list). `Status`
is "A" (3,200) or "S" (16).

## What changed

- **`services/data/fetchers/surveillance.py`:**
  - `get_symbol_meta` and its per-day cache (`data/market_cache/symbol_meta.json`) are deleted.
  - `parse_surveillance(text)`: `{symbol: {"status", "measures"}}`, where `measures` names GSM,
    LT-ASM and ST-ASM when the value is not "100" or empty; `None` when a needed column is
    missing.
  - `surveillance_list(session, tries=5)`: the newest report dated on or before `session`, at
    most 7 days before it. Trading days are taken newest first: the cached report
    (`data/discovery/surveillance.json`) serves for its own day; other days are fetched, at most
    5, through `nse._req` (the shared throttle). NSE unreachable means only the cache can
    answer. `(None, None)` when nothing qualifies. Never raises.
  - `market_classification` and `float_mcap_cr` are unchanged.
- **`core/discovery/guards.py`:** reads the report once a run, for the window's latest session.
  Under any GSM/LT-ASM/ST-ASM stage: `surveillance_asm_gsm`; status not "A": `suspended`; not in
  the report: kept, `surveillance:<SYMBOL>`; no report: the one check `surveillance`.
  `_one_check_per_dark_source`: a per-symbol source (`GUARD_SOURCES`: surveillance, float_mcap,
  promoter_pledge) that degraded for every symbol reaching the per-symbol gates is recorded
  once, as `<source>`.
- **`core/discovery/__init__.py`:** the weekly result gains `dark_checks`: the screen's run-wide
  checks (not `<guard source>:<SYMBOL>`). **`services/scheduler/python/scheduler.py`:** the
  Discovery log line prints it.
- **`core/ops/watchdog/checks.py`:** check `discovery_guard_sources` reads the persisted screens
  that ran the guards. It is pending when a guard source has been dark in every screen from one
  at least 7 days before the latest (two weekly screens in a row). The pledge source is skipped
  while `discovery.pledge_guard` is off. **`config/milestones.yaml`:** invariant
  `discovery_guard_sources_live` (an addition; nothing deleted).
- **`core/discovery/deep_dive.py`:** `_INDUSTRY_SECTOR_KEYWORDS` (NSE industry substrings) is
  replaced by `_YAHOO_INDUSTRY_SECTOR` (exact Yahoo industry to key) and `_YAHOO_SECTOR_SECTOR`
  (Healthcare, Financial Services, Real Estate, Energy). New `sector_from_classification()`.
  `infer_sector(symbol, classification=None)`: the ticker map, else the classification (fetched
  only when not given), else `generic`. `run_deep_dives` asks Yahoo once a dive and passes the
  answer to both `infer_sector` and the result's `market_sector`/`industry` (before, two calls).
- **`scripts/ci/broad_except_baseline.txt`:** one entry fewer (the deleted `_load_cache`
  swallow), via `check_broad_except.py --update`.
- **Tests:** new `tests/unit/test_surveillance_sector_fix011.py` (48). Updated fakes in 7 files:
  the guards' and pledge tests patch `surveillance_list` instead of `get_symbol_meta`; the deep
  dive's `infer_sector` stubs take the classification argument, and one dive test fakes Yahoo,
  which is now asked before the analyst; the two `get_symbol_meta` fetcher tests are deleted (the
  story file replaces them); the scheduler cycle's screen fakes carry `degraded_checks`, and the
  happy path asserts `dark_checks`.

## Decisions (implementer's, recorded for the review)

- **F11-D1, the report, not the API.** The archive file is the same host as the bhavcopy the
  production listing already reads (inferred to answer from Railway; not verified), one request a
  run, dated, so a replay can take the file of its own day. The ASM/GSM APIs are live-only and
  under `www.nseindia.com/api`, the host whose quote API refused this machine.
- **F11-D2, which columns gate.** GSM, long-term ASM and short-term ASM, at any stage, as the
  guard always intended. Not ESM (on 29 Oct all 228 ESM rows were BE, BZ or SME series, which the
  universe leaves out) and not insolvency (IRP: 56 rows, 2 of them EQ; not an ASM/GSM measure;
  KT limit). The other columns are indicators (pledge, loss-making, P/E, price moves), not
  measures.
- **F11-D3, `status` not "A" rejects as `suspended`.** Only "A" and "S" were seen.
- **F11-D4, age and look-ahead.** At most 7 days before the screen's session and never after it.
  The weekly run fetches once a week, so a fallback longer than 7 days would gate on a list older
  than a week. A replay of a past screen cannot see a later report, from the archive or the cache
  (tested).
- **F11-D5, no report degrades visibly; it does not block.** The card asks for a visible degraded
  state. Failing closed would stop every new idea during an archive outage. The screen records
  one `surveillance` check, the weekly summary lists it, and the watchdog warns after two dark
  weekly screens.
- **F11-D6, one check for every per-symbol source.** The same rule covers `float_mcap` (Yahoo)
  and `promoter_pledge`, so a Yahoo block also reads as one check.
- **F11-D7, Yahoo is the one industry source.** It covers nearly every company and its
  industries separate insurer from bank, defence from capital goods, agrochemicals from
  chemicals. NSE's industry exists only in index lists (750 companies) and is coarse: "Financial
  Services" holds banks and insurers, "Capital Goods" defence makers. PR-004's shelf cap already
  stores Yahoo's classification, so the cap, `infer_sector`, SA-044 and SA-026 read one source.
  The table maps exact industry names and falls back to four Yahoo sectors that name one key
  whatever the industry; every key is a registry sector (tested).
- **F11-D8, the ticker map is untouched.** Adding CEATLTD or TIINDIA to `TICKER_SECTOR` would
  also change `SectorRegistry.resolve` for analyses run outside discovery, moving their stores.
- **F11-D9, nothing is re-keyed.** A managed stock keeps its record's sector (`holding_sector`),
  the deep dive skips managed stocks, and a re-dive never changes an idea's `sector`
  (`apply_redives`, unchanged). So ideas shelved before keep `generic` and their paper-lane
  stores. Re-keying stays SA-026's.
- **F11-D10, the watchdog reads the screens.** They already persist `degraded_checks` with a
  date, so no new state file is written.

## Industry mapping evidence (Yahoo, 1 Nov)

- **In-sample, the registry's 202 tickers** (`analysis_data/fix011/mapping_check.py`; the table
  was written while reading these, so this is not an out-of-sample measure): Yahoo classified
  193; the table agrees with the curated key for 184. The 9 differences: BEL and HAL
  (`defence`; map `capgoods`), MAZDA, INOXWIND and SUZLON (`capgoods`; map `defence`,
  `renewable_energy`), LT (`infra`; map `capgoods`), LODHA (`realestate`; map `infra`),
  SCHAEFFLER (`automobile`; map `capgoods`) and AAVAS (`banking_bfsi`; map `chemicals`, a
  housing-finance company). The map wins for its own tickers. Yahoo has no quote for 9
  registry symbols (ACCCEMENT, APL, BAYER, DEEPAKNITRI, GATI, INOXLEISUR, MAHINDHOTEL, MTAR,
  NIIT); routed to SA-026 with AAVAS.
- **Out-of-sample, 150 Nifty Total Market companies outside the registry** (seeded sample):
  146 classified (no quote: three NSE placeholder symbols, DUMMY…, and BAGMANE). 4 read
  `generic` (Specialty Business Services, Packaging, Textiles, Paper). Against NSE's own coarse
  industry: 118 consistent, 21 different (for example MIDHANI `metals` where NSE says Capital
  Goods; SAGILITY `pharma` where NSE says IT), 3 in an NSE class with no key (Textiles,
  Utilities). Before this story all 150 would have been `generic`.
- **The card's two stocks:** CEATLTD is `automobile` (Auto Parts), so PR-004 RR-L1's case is
  fixed for it. TIINDIA is `capgoods` (Yahoo: Conglomerates; NSE: automobile components), so
  for TIINDIA it is not (KT limit).

## Production data (unchanged)

`data/market_cache/symbol_meta.json` is no longer read and stays on the volume; deleting it
needs the owner's word. The first screen after a deploy writes `data/discovery/surveillance.json`.
Shelf ideas and managed records keep their sectors. The production shelf was not read.

## Tests

Commands from the repository root, Windows, `.stockai` venv (Python 3.13), plain `pytest` with
`tests/hermetic.py` (`-p no:cacheprovider`).

- **Story file** `tests/unit/test_surveillance_sector_fix011.py`: **48 passed**. The report
  fixture is NSE's header (first 19 of 63 columns) with hand-written rows; the NSE client is a
  fake serving named files and answering 404 otherwise.
  - The report: each measure and the status (GSM stage 0 is a stage; IRP and ESM not gated; a
    row without a symbol skipped); a renamed column is no report.
  - The fetcher: newest day on or before the session, then cached and served without a request;
    a report after the session is never used, from archive or cache; a cached report serves a
    6 Nov screen and not a 9 Nov one with NSE down; at most 5 requests a run.
  - The gates: a fixture list rejects the 3 listed and the suspended stock and passes the
    clear, IRP-only, ESM-only and unlisted ones (the last recorded `surveillance:NEWLIST`); no
    report gives one `surveillance` check and passes every stock (the hard-review answer); a
    source answering for no symbol is one check, and one answering for one symbol is not; the
    report is asked for once, for the window's session, and not at all for an empty shortlist
    (no dark check then).
  - **Invariant (independent oracle),** 5 seeds × 150 random rows through the archive file,
    cache and gates: a stock passes iff NSE's GSM, LT-ASM and ST-ASM cells, read by **column
    position** off NSE's header, are all "100" or empty and its status is "A".
  - The weekly summary's `dark_checks`; the watchdog (pending for 23 and 30 Oct; quiet for one
    dark screen, after recovery, for 3 days, for screens without guards, with no screens; pledge
    judged only while its guard is on); the registry entry and its check.
  - Sector: a fixture industry outside the ticker map maps to `defence`, a registry sector;
    every table key is a registry sector and a valid key; 11 classification cases; the ticker
    map wins and Yahoo is asked only when no classification is given.
  - **Characterization of graph routing**, 7 industries through `run_deep_dives`: Auto Parts,
    Banks - Regional, IT Services and Utilities - Renewable route to their native graphs (were
    generic); Specialty Chemicals and Packaged Foods keep the generic graph under `chemicals` and
    `fmcg`; Textile Manufacturing stays `generic`. Yahoo is asked once a dive.
  - **Store paths:** a managed `generic` holding stays `generic`, Yahoo is not asked and its
    `PredictionStore` directory is `<base>/generic/CHEMCO`; a shelf idea's re-dive keeps its
    sector (and so its paper store) while its industry updates; CEATLTD, not managed, is held as
    `automobile`.
- **Mutants** (`analysis_data/fix011/mutants.py`, each in place and restored, sha256 of the 7
  code files checked after): **33 of 33 caught** (`analysis_data/fix011/mutants.txt`, on the final bytes). HEAD's `surveillance.py`, `guards.py`, `deep_dive.py`, `checks.py` and discovery `__init__.py` each fail the story file. So do: GSM stage 0 read as none; ESM gated; a renamed column read anyway; a cached report newer than the session served; no age limit; unbounded requests; an unreachable client ending the search before the cache; a silent dark source; a dark check without asking; an unlisted stock rejected; only GSM gated; suspension ignored; the wall-clock date for the session; no collapse; collapse when any symbol degrades; the summary listing per-symbol checks; the watchdog at more than 7 days, counting per-symbol checks, judging the pledge source with its guard off, or counting screens without guards; the ticker map not first; no sector fallback; insurers as banks; defence as capital goods; Yahoo always asked; Yahoo asked twice a dive; a re-dive re-keying the sector; the managed sector ignored.
- **Neighbouring files** (guards, fetchers, deep dive, PR-011 pledge, PR-004 idea supply, SA-003
  gate, screen, cycle and IPO cycle, discovery API, scheduler job, `tests/unit/ops`, FIX-008
  notices, hermetic boundary, story file): 626 passed and 2 failed on the first run (the
  scheduler fakes lacked `degraded_checks`); after that fix, both scheduler tests pass.
- **Full suite:** **5,973 passed / 12 skipped / 1 xfailed / 0 failed** (18m36s, 17:37–17:56 IST; SA-048's 5,927 plus this story's 48, less the 2 deleted `get_symbol_meta` tests), on the final code and test bytes. No tracked runtime file changed (`git status`). Output: `analysis_data/fix011/full_suite.txt`.
- **Checks:** `check_broad_except` OK (150 grandfathered, one fewer); `check_kt_docs` errors
  `[]`, header `30bf8fc`, 106 linked sources; PDF regenerated, 64 pages.

## Self-review (same conversation; not the fresh review)

Found and fixed before the final runs:

- `surveillance_list` ended its search when the NSE client could not be created, so a cached
  report within 7 days was never read (found writing the 6 Nov test). The first fix let a sixth
  request through; the loop now counts a failed client as the last request and goes on to the
  cache only. Pinned by the mutants `client_failure_aborts` and `tries_unbounded`.
- `apply_guards` recorded `surveillance` as dark for an empty shortlist, when nothing was asked.
  Now the check is recorded only after a request (mutant `dark_without_asking`).
- The deep dive's single Yahoo call was not pinned; the routing test now counts it (mutant
  `dive_asks_yahoo_twice`).
- A characterization case first failed because the fixture gave Yahoo a made-up sector; "Banks -
  Regional" maps through the sector "Financial Services", so the fixture now uses Yahoo's real
  pairs.

## Documentation

- **KT** (`docs/TECHNICAL_DESIGN.md`, section 8 Discovery): new **Surveillance and suspension**
  and **One check per dark source** paragraphs; **Market sector** rewritten (the source, the key
  table's measured agreement, graph routing, no re-keying); **Limits** rewritten (no report for
  7 days, IPO and re-dive paths, ESM and IRP, Yahoo's taxonomy and TIINDIA, the dead NSE APIs).
  The planned sector-lens bullet names the industry source. Section 12's FIX-011 row stays
  `Open` until acceptance. PDF regenerated.
- **Testing guide:** case 06-J (new) and HT-06's related-PI line.
- **AUTOPILOT_GUIDE.md:** what `infer_sector` reads. **CODEBASE.md:** the guards, deep-dive and
  surveillance rows.
- **Cards:** routed notes on SA-044 and SA-026 (the industry source settled; SA-026 also gets
  the stale registry symbols and AAVAS) and SA-049 (the sector key; ASM after shelving, an owner
  decision for the IPO lane).
- **ARCHITECTURE.md:** unchanged; it does not describe the screen's guards or sector inference.

## Found on the way

- **ASM after shelving (routed to SA-049).** Only the screen's shortlist meets the surveillance
  gate. IPO candidates and re-dives never do, so an idea that comes under ASM or GSM after it is
  shelved, or an IPO idea under short-term ASM, stays on the shelf and is a buy candidate. This
  predates FIX-011. SA-049 spends idle cash on shelf ideas, so it should decide whether a buy or
  the weekly hygiene checks the report too. Many new listings start under short-term ASM, so the
  IPO lane needs the owner's call.
- **The registry's ticker map** (routed to SA-026): 9 symbols Yahoo cannot quote and AAVAS keyed
  `chemicals`.

## Review input

- **Manifest:** [FIX-011-manifest.json](FIX-011-manifest.json) `509d392125eafc397752eece05f153abee6100c3099d9135e3fb56e248bc6874` (24 files),
  `kt_manifest.py verify` 0 mismatches.
- **Diff:** `e8bc2ad9dca6bc7a9fe23853accfd36778f132e423c718f281e418a1c0d3bd78` (94,571 B, 23 paths), from `analysis_data/fix011/digest.py`:
  every manifest path except the PDF, sorted, against the index (= HEAD `2e14e04`, nothing
  staged); the story file against `/dev/null`.

## Commit (after the fresh review accepts it, only at the owner's word)

The manifest's files exactly as reviewed, then a docs commit: KT header (the new code commit) and
section 1's production paragraph if a deploy happened, section 12 FIX-011 `Done`, guide 06-J's
status, the PDF, with this receipt, the review receipt, STATE and HANDOFF (and the uncommitted
SA-048 deploy record). A push deploys it: in a job-free window. The first Saturday discovery run
after the deploy is the first real test.

## For the fresh review (the card's hard-review questions)

- **Can a stock under ASM/GSM reach the shelf when the source is down?** For 7 days after the
  last report it fetched, no: the cached report still gates. After that, yes, visibly: one
  `surveillance` check in the screen, `dark_checks` in the weekly summary and the log line, and
  the watchdog warns once two weekly screens in a row are dark. Independent of the source, an
  IPO candidate or a re-dive never meets the gate (above, routed to SA-049).
- **Does a new sector key move an existing holding's forecasts to a different store?** No. The
  only change is what `infer_sector` returns for a stock outside the ticker map. Its callers are
  the deep dive, which skips managed stocks, and `holding_sector`, which returns the managed
  record's sector first and a shelf idea's stored sector next. A re-dive never writes `sector`.
  `TICKER_SECTOR` and `SectorRegistry.resolve` are unchanged. Pinned: the managed-holding store
  path, the re-dive test and the mutants `managed_sector_ignored` and `redive_rekeys_sector`.

## Production verification (separate, after the deploy)

Guide 06-J on the first Saturday discovery run after the deploy: the log line's `dark_checks`;
the screen's `rejected` against NSE's ASM/GSM lists for that date; `surveillance.json`'s
`as_of`; new shelf ideas' sector keys against their industry. Read-only, counts and fields only.
