# FIX-028 — implementation receipt

**Story:** [FIX-028](../stories/FIX-028.md): a sold stock leaves the daily review.

**Phase:** implementation, 11 Nov 2026, about 00:15–01:20 IST. Session `stockagent-main-63`
[5106fb], a new conversation opened with "continue". `origin/main` was at `02f3ad7`, the same as
HEAD: nothing had arrived from the other device. Four peer sessions were idle. This phase includes
a same-conversation self-review, which is not the fresh review.

**Baseline:** HEAD `02f3ad7`. The working tree already held FIX-027's fresh-review documents,
uncommitted and waiting for the owner's word (its receipt, the FIX-031 card, a FIX-015 note, STATE,
HANDOFF); none of FIX-028's files is among them, so every changed file below differs from HEAD by
FIX-028 alone. FIX-027's three commit-time edits (KT section 6 "Not covered", a KT section 12 row,
guide 06-N's status line) are **not** applied yet; they go on top at commit time.

**Status after this phase:** `review_required`. Nothing is committed, pushed, deployed or configured.
No production state was read (the card's measurement is prepared, not run), no network was used, no
LLM was called and no message was sent. No test reaches the network (`tests/hermetic.py`).

## In one example

The list holds 25 original entries and 15 stocks the autopilot bought: 40, the cap.

- **Before:** the autopilot sells OLD; its entry stays `enabled`, origin `held`, so the 16:30 review
  and the monthly forecast keep paying for it, and nothing ever evicts it. The same run's SWITCH buy
  of NEW is promoted while OLD still fills its place, gets `cap_full`, which the executor ignored:
  NEW is held with no daily review and no forecast, and only a log line says so.
- **Now:** once the run's trades are saved, OLD's entry is disabled (sector and history kept) and
  NEW is promoted into its place. Had the cap still kept NEW out (a deployment buy with no sale that
  day), NEW's digest row would carry `not_reviewed`: "no daily review or forecast: managed-ticker
  cap 40 reached", the digest's text and the morning brief repeat it, and every run tries again.
  Bought back later, OLD's entry is re-enabled under its old sector.

## What changed

- **`core/portfolio/promotion.py`:** `release_unheld(current)`: under the list's lock, reads every
  portfolio on disk (`store.list_user_ids`, straight from each `portfolio.json`) plus the portfolio
  just saved; each enabled `held` entry no portfolio holds is disabled, or, while a user's own
  watchlist lists the stock (any source but `autopilot`), becomes a `watchlist` entry (weekly).
  Original entries are never touched. Any unreadable portfolio: nothing released, nothing
  quarantined. No managed file: nothing done, nothing written (not even the lock).
  `without_daily_review(symbols)`: the held stocks the list waits for (no entry; a disabled `held`
  or `watchlist` entry; an enabled `watchlist` entry). `promote_symbol` and `demote_symbol` now hold
  the lock.
- **`services/api/log_buffer.py`:** `managed_tickers_lock()` (one `FileLock` per file, re-entrant
  for its holder); `read_managed_tickers()` (never seeds the file, unlike `load_managed_tickers`);
  `save_managed_tickers` writes through a temporary file and a rename (a torn file would have been
  replaced by the five-ticker seed on the next read).
- **`core/portfolio/autopilot.py`:** the SWITCH-leg and deployment promotions moved out of the buy
  loops into `_follow_holdings(portfolio, txns)`, called by `execute_advice` after the save, under
  the portfolio's lock, on a run with no trade too: the release first, then the positions the run
  opened (as before, a disabled original entry included), then the holdings the list waits for.
  A `cap_full`, `invalid_sector` or failed promotion goes into `report["not_reviewed"]`.
- **`core/portfolio/pipeline.py`, `digest.py`, `digest_text.py`, `core/delivery/brief.py`:** the
  digest row gains `not_reviewed`; the text appends it; the brief lists such a holding under its
  flags whatever its verdict (a stock bought today is `NO_DATA`).

## Decisions (F28-D1 to D9)

| # | Decision | Why | Card |
|---|---|---|---|
| D1 | A state rule, not an event: after every autopilot run the list follows what the portfolios hold. | An event rule ("demote on this sale") never clears the stocks sold before the deploy, which are what fill the cap, and loses a demotion when a run stops between the save and the demotion. The state rule clears both on the next run. | Intended result 1 |
| D2 | In the executor, after the save, under the portfolio's lock; the release before any promotion, and the buy-time promotions moved after the save. | A SWITCH's sale frees its place before its buy asks for one (test `a_sales_room_is_free_before_the_same_runs_buy`). After the save, a stopped run cannot release a stock still held. A deployment trial that is thrown away no longer leaves a promotion behind (before, `_deploy_idle_cash` promoted on the trial copy). | Hard review 2 |
| D3 | "No portfolio holds it" reads every `portfolio.json` on disk, not only the active users, and the portfolio just saved; any unreadable file stops the release for that run. | Conservative: a ghost portfolio's holding keeps its stock reviewed; a guess ("unreadable = holds nothing") would stop a held stock's reviews. Read raw, because `PortfolioStore.load` quarantines a corrupt file and answers "empty". | Never on a guess |
| D4 | A TRIM that sells the last share (`trim_to_zero`) releases, like an exit. | The card's "a TRIM does not" is a TRIM that leaves shares; with none left, no portfolio holds the stock. | Acceptance 1 |
| D5 | A stock on a user's own watchlist stays enabled but becomes a `watchlist` entry (weekly). The autopilot's own `autopilot_exit` item does not count. | Left `held`, it could never be evicted, which is the cap problem the card names. As a watchlist entry it is what the user's own watchlist add makes it. The scheduled 16:30 job does not read cadence (AUTOPILOT_GUIDE section 12), so it is still reviewed daily; the change is that the cap may evict it. | Intended result 1 |
| D6 | Retried every run: the positions the run opened, and each holding the list waits for (no entry, a disabled held or watchlist entry, a watchlist entry). Not an original entry the owner disabled by hand, unless the run bought the stock. | A `cap_full` stays visible and is cured as soon as room frees, and a held stock some other path left disabled (an API delete in another account) is healed. Retrying every disabled entry would undo the owner's own switch-off (TATAMOTORS was disabled by hand on 1 Oct). A buy re-enabling one is today's behaviour, kept. | Intended result 2 |
| D7 | `not_reviewed` on the digest row, in its text and in the brief's flags (any verdict), every run until the holding has an entry. | "Where the owner reads it." A one-day note would scroll away while the holding stays unreviewed. | Acceptance 3 |
| D8 | One `FileLock` for promotion's reads and writes, and an atomic save for every writer. The owner's dashboard routes were not given the lock. | The pipeline thread and the API's handlers write the same file; the release decides from the portfolios while it holds the lock a later promotion needs, so any order converges. The dashboard's POST holds a yfinance call between its read and save; giving it the lock would hold the lock across a network call. Routed (below). | Hard review 2 |
| D9 | FIX-025's `sold` flag stays (F25-D13, D14). | A sold original entry, or a sold stock a user watches, stays managed and enabled after its sale, and a run whose release did not happen leaves one so; without the flag `run_deep_dives` would skip each for good. Pinned by FIX-025's `test_each_flag_passes_only_its_own_skip`. | Hard review 3 |

## The card's hard-review questions

- **Does anything read a sold stock's daily review after the sale?** Code inspection: no grade does.
  The auditor's advice, alert and switch lanes grade from closes (`core/audit/outcomes.py`,
  `close_on`); the exit shadow's grades too (`exit_shadow.grade_disagreements`, a benchmark close
  reader). The advisor reads a stock's forecasts and feedback only while it is held
  (`pipeline.py`, `VerdictStore(holding.symbol)`). A watchlist buy candidate never qualifies from the
  autopilot's own exit item. The RL scorecard and learning evidence read the feedback logs that
  exist: the sold stock's entries stay, and its series ends at the sale, by design. Not measured in
  production.
- **Is the managed file safe to write from the executor, with another portfolio's run in the same
  job?** The job runs portfolios one after another. The follow-up takes the portfolio's lock, then
  the list's; no path takes them the other way round (`promote_symbol` and `demote_symbol` take only
  the list's; the API's add holding saves under the portfolio's lock, lets it go, then promotes).
  The portfolios are read under the list's lock, so a buy saved before a concurrent promotion is seen,
  and a promotion after a release re-enables its stock (tests: `portfolios_are_read_under_the_lists_lock`,
  `a_promotion_waits_for_the_lists_lock`). The save is atomic (`a_save_that_fails_leaves_the_old_list_whole`).
  Not covered: the dashboard's routes (D8).
- **The `sold` flag: still needed?** Yes (D9).

## Found on the way

- **The owner's dashboard routes take no lock** and **the API's delete routes look only at the
  user's own portfolio** (user A's delete disables X while user B holds it; B's next autopilot run
  heals it, a manual portfolio is not healed). Both pre-existing, low, one owner today. Routed to
  SA-026 (card section "Routed input — 2026-11-11"); KT section 6 and AUTOPILOT_GUIDE section 12
  say so.
- **The scheduler API reviews five fixed tickers when no entry is enabled**
  (`scheduler_api._resolve_tickers` falls back to `SCHEDULER_TICKERS`). Production keeps original
  entries enabled, so a release cannot empty the list there. Noted only.
- Known and documented already: the scheduled 16:30 review ignores cadence (D5).

## Measure first (the card) — prepared, not run

The card asks for a read-only count of the production list by origin, with the owner's word, to
decide whether FIX-028 goes before switch-on. Not run: no production read in this phase. Probe
[`analysis_data/fix028/managed_probe.py`](../../../../analysis_data/fix028/managed_probe.py) (ignored
folder; counts only, no symbols, user ids or values; dry-run locally on the stale `data/`). It prints
the entries by origin and state, the enabled count against the cap, the holdings per portfolio, the
`held` entries no portfolio holds (what the first run after the deploy would disable, or keep for a
user's watchlist) and the holdings with no enabled entry. Owner's command, from Git Bash in the
repository root:

```
railway ssh "cd /app && echo $(gzip -9c analysis_data/fix028/managed_probe.py | base64 -w0) | base64 -d | python -c 'import sys,zlib;exec(zlib.decompress(sys.stdin.buffer.read(),31))'"
```

If "enabled_after_first_run" plus the 13 or so holdings deployment aims for passes 40, FIX-028 is a
switch-on precondition (the card's rule).

## Rollout

- **Deploying changes production with the switch off.** On the first autopilot run after the deploy
  (the 16:30 review), every `held` entry for a stock no portfolio holds is disabled, or kept as a
  weekly watchlist entry while a user watches it: the stocks the autopilot sold since July. Their
  16:30 reviews and the monthly forecast stop, and their LLM cost with them; how many is the probe's
  `would_be_disabled_on_first_run` (not read). Their history stays; a re-buy re-enables each.
- **A holding without an entry** is named on the digest from that run on; the probe's
  `holdings_without_enabled_entry` says whether any exists today.
- **On the 1st**, the 09:00 monthly forecast runs the enabled list; a deploy before 1 Dec means
  December's forecasts leave out the released stocks.
- **First look, read-only:** after the first 16:30 run following the deploy, the probe again (the
  released count should match its first reading) and the digests' `not_reviewed` rows (guide 07-P).
- **No benefit is shown here.** These are contracts. The saving is the number of released entries
  times a review's cost, which only the production count gives.

## Tests and commands

Environment: `.stockai/Scripts/python.exe` (Python 3.13), Windows, from the repository root.

- **Story file** [`tests/unit/test_sold_stock_leaves_review_fix028.py`](../../../../tests/unit/test_sold_stock_leaves_review_fix028.py), 23 tests, figures worked by hand in docstrings, through the real `execute_advice`, `promote_symbol`, `release_unheld`, `buy_candidates`, `run_post_review_pipeline`, `build_morning_brief`, `get_active_tickers_with_sector` and the scheduler API's `_resolve_tickers`, with a real managed file and real portfolio files:
  - Acceptance 1: a full exit disables, keeping sector, origin and cadence, and the cohort loses it; a TRIM that leaves 8 of 10 keeps it; a last-share TRIM releases; another portfolio's holding keeps it; a user's own watchlist (home page, shelf, the seller's own) keeps it as weekly `watchlist`, another portfolio's `autopilot_exit` item does not; original entries (no origin, `manual`) never change; a stock sold earlier leaves on a run with no trade.
  - Acceptance 2: the re-buy (exit Mon 13 Jul, re-dived Sat 18 Jul as `chemicals`, the real candidates offer it as `pharma`, SWITCH on Mon 20 Jul): enabled, `pharma`, held, daily, in the cohort again.
  - The sale's room before the same run's buy (cap 3).
  - Acceptance 3, through the pipeline: an 80-share deployment buy the cap keeps out, named on the row, in the text and in the brief (verdict `NO_DATA`); named again the next run; promoted, and the note gone, once an original entry is switched off.
  - The retry's four entry shapes (D6), and the just-saved portfolio counting wherever it is stored.
  - Never on a guess: an unreadable portfolio releases nothing and is not quarantined; no managed file writes nothing; the portfolios read under the lock; a promotion waits for the lock (two threads); a failed rename leaves the old list byte for byte.
- **Reworked older tests** (behaviour changed by design): FIX-025's two end-to-end tests (`test_deployment_follows_money_fix025.py`): the in-memory list also stands in for the new reader, and after the exit BACK reads `enabled: false` instead of "nothing demotes it"; the first is renamed `test_d4_end_to_end_bought_sold_and_re_dived`. Their dives still happen (now as unmanaged stocks).
- **Neighbouring tests:** the 92 test files that name the autopilot, promotion, the pipeline, the managed list, the digest, the brief, the deep dive or the candidates (`analysis_data/fix028/focused_files.txt`): 2,644 passed, 1 xfailed, 0 failed, pytest rc 0, 8m01s (`focused_run2.txt`). An earlier, narrower run caught the isolation test's two expectations: the lock created `data/` with no managed file, and the unreadable-list fallback also promoted ADD top-ups. Both were fixed to keep the old behaviour.
- **Mutants** (`analysis_data/fix028/mutants.py`, in place, each file restored and its sha256 checked; the story file, the isolation and promotion files, FIX-025's two end-to-end tests and the brief's file): **19 of 19 caught.** First pass 18 of 19 (`mutants.log`): who holds it, a user's watchlist, the autopilot's exit item, original entries, the release's order, the refused promotion, the digest row, its text, the brief's filter, the no-trade run, an unreadable portfolio, the portfolios read before the lock, an unlocked promotion, an in-place save, the lock with no file, a hand-disabled original entry re-enabled, the run's own buys, a watched stock disabled. **M17 (the just-saved portfolio not counted) survived:** the same run's retry re-enabled the entry, so the end state matched, though the entry was disabled in between and the log said so. Its test now asserts the release itself and the log; re-run, caught (`mutants2.log`).
- **Full suite** (`tests`, hermetic): **6,280 passed / 12 skipped / 1 xfailed / 0 failed**, pytest exit code 0, 19m06s (00:51:43–01:10:49 IST), `git status --porcelain` identical before and after (`analysis_data/fix028/full_suite.txt`, `status_*_suite.txt`). One run; 6,257 before plus the 23 new tests.
- `check_broad_except`: OK (148 grandfathered). `check_kt_docs`: `errors: []` after the PDF rebuild.
- `analysis_data/fix028/crlf_check.py`: every touched file is LF, as at HEAD.

## Documentation

- `docs/TECHNICAL_DESIGN.md` section 6: "The managed list follows the holdings" (the rule, the retry,
  the digest line, the example), and the fresh-verdict example's "every held stock is managed";
  section 8: a sold stock leaves the list, the "Planned: FIX-028" sentence gone.
- `docs/AUTOPILOT_GUIDE.md`: section 1 (the designed exception), the SWITCH paragraph, section 12
  (three new bullets: the list follows the holdings, a capped holding is named, never on a guess;
  the delete routes' limit; a re-enable keeps the sector), section 14's new test row, section 16's
  FIX-028 bullet removed.
- `docs/TEAM_TESTING_GUIDE.md`: new case 07-P; HT-07's Related PI names FIX-028.
- `README.md`: the auto-promotion table's "Release" row.
- `docs/planning/PI-2026-09/stories/SA-026.md`: the routed input.
- `CODEBASE.md`, `docs/ARCHITECTURE.md`: no change; neither describes the managed list's rules
  (CODEBASE's delete-route rows stay true).
- `docs/StockAgent-Three-Loops.pdf` regenerated: 68 pages, source `ee91ea966feae30692e23c727e1a36371a5027d00c3d43cf2b9b3113b248f3a1`, 627,731 bytes; `check_kt_docs` `errors: []`.

**Commit-time edits still to make:** KT header (Code inspected, edition); section 1 (production, and
the inspected code adds FIX-028, not yet deployed); section 12 FIX-028 Done; guide 07-P's status
line; the PDF. FIX-027's three commit-time edits first (its review receipt), if they are not
committed by then.

## Review input

- Manifest: [FIX-028-manifest.json](FIX-028-manifest.json), SHA-256 `5358ec75923e7a59b451467bb9214d6af147701730fdb7b167da21dee8601c85`, 15 files
  (`scripts/docs/kt_manifest.py verify`: 0 mismatches).
- Diff against HEAD `02f3ad7`, the PDF excluded: SHA-256 `6338bdb84ab1a842bae7a5eebd07e83d401bb0d6435e32218387d16be683b6a4`, 77,712 bytes, 14 paths, via
  `analysis_data/fix028/digest.py` (a temporary index, so the new test file is in the diff and the real
  index is untouched). Base tree `5241f3c2`, end tree `289ee1f5e9b04a1d15a533ba325f864175bc66c5` (taken before this
  receipt's last figures and the STATE/HANDOFF splice).
- Outside the manifest: STATE, HANDOFF, this receipt and the manifest itself (bookkeeping), and FIX-027's
  uncommitted review documents (its receipt, the FIX-031 card, the FIX-015 note).
- On another device, recompute from the recipe: `git diff 02f3ad7 -- <the manifest's paths but the PDF>`
  over the working tree, sorted paths, `core.autocrlf=false`.

## What a fresh review should press on

1. D1 and D3: can the release ever disable a stock some portfolio holds (a portfolio outside the
   data folder, a symbol spelled differently, a run that saved and then failed)?
2. D6: the retry against the owner's own switch-offs and the dashboard's edits.
3. D5: a user-watched stock kept as `watchlist`, evictable at the cap while the 16:30 job still
   reviews it daily.
4. The first run after the deploy: how many entries leave at once, and whether anything still reads
   their reviews (the hard-review answer is code inspection only).

Next: a fresh review in a new conversation (REVIEW.md).

## After the phase: committed before the fresh review

At the owner's word ("commit and push now", 11 Nov about 07:25 IST), a recorded deviation as with
FIX-027:

- Code `245e29e`: the 9 code and test files, byte-identical to the manifest
  (`kt_manifest.py verify … --rev 245e29e`: no mismatch among them).
- The docs commit after it: the 6 docs, which differ from the manifest only by the commit-time status
  edits (KT header `245e29e`, edition 2026-11-11; KT section 1 "adds FIX-028 … not yet deployed";
  guide 07-P "committed as `245e29e` before its fresh review; review pending"), and FIX-027's review
  documents with their three commit-time edits. PDF 68 pages, source `b4d9bff2…`; `check_kt_docs`
  `errors: []`.
- The fresh review reviews `245e29e` and that docs commit. The push is recorded in HANDOFF.
