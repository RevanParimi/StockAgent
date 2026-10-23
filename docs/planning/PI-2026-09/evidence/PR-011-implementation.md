# PR-011 — implementation receipt

**Story:** [PR-011](../stories/PR-011.md): new data, namely promoter and insider trades, pledges and
shareholding changes.
**Phase:** implementation, 23 Oct 2026, about 12:20–15:35 IST. Session stockagent-main-74, a new
conversation opened with "continue"; peers -48, -46, -a6, -a4, -7e, -1c, -3c, -a8, -53, -2c,
-62, -bb, -95 and -f8 were idle at the start and before bookkeeping (ListAgents). The laptop
was in standby 12:57–13:09 and 14:17–15:00 IST (Kernel-Power 506/507).
**Baseline:** `16e31b5` (FIX-013 rework 1's docs commit). The working tree held only the
uncommitted planning bookkeeping (FIX-013's push note in STATE and HANDOFF) and the owner's
`docs/README.md` line, which this phase does not touch.
**Status after this phase:** `review_required`. Nothing was committed, pushed or deployed. No
production state was read and no message was sent. NSE's public disclosure endpoints and
archive were read from this machine (below). No search credit was spent and no model was
called. After the phase, at 15:42 IST, the owner ran the read-only production probe from the
production container: 8 of 8 checks passed (PR-011-P1, below).

## Rework 1 (23 Oct 2026, about 17:30–18:30 IST)

**Context.** Session `stockagent-main-b1`, a new conversation opened with "continue". All 17
peers were idle at the start and before bookkeeping (ListAgents). It answers the fresh review's
CHANGES REQUESTED ([review receipt](PR-011-review.md), session `stockagent-main-5b`). It includes
a same-conversation self-review, which is not the fresh re-review. **Status after:**
`review_required`. Nothing was committed, pushed, deployed or configured. No production state was
read, no model was called and no message was sent. NSE's public insider list and archive were
read from this laptop: one list call and 6 XBRLs for the fixtures, then one real discovery
refresh, 357 XBRLs and 17 shareholding lists (below).

**Input.** The review's input: manifest `2b264207…` (33 files), diff `939890c3…`, on HEAD
`16e31b5`. Both were verified unchanged at the start (`analysis_data/pr011_review/rdigest.py`
and `kt_manifest.py verify`, 0 mismatches). The rework is the working tree on top of it.

### In one example (F1)

On 8 Oct at 17:27:52 NSE disseminated NAUKRI's filing 3962, a revision. Its XBRL holds one trade:
a director sold 5,00,000 shares in the market for ₹68,04,78,416 on 18 to 20 Aug.

- **Reviewed code:** Saturday's discovery gave NAUKRI `insider_buying` −68.0 for the 28 days to
  23 Oct, the lowest value, so NAUKRI ranked last on the signal. A feed run would have stored a
  negative, high event dated 8 Oct, read as a new ₹68 crore sale.
- **Now:** the trade's last day, 20 Aug, is before the window's first day, 25 Sep, so NAUKRI
  scores 0. The event is neutral and low, and its sentence ends "It revises an earlier filing,
  so these trades may have been reported before and are not read as new trading."
- **Another case, PATINTLOG:** filing 3886 (1 Oct 17:11:45) and its revision 3893 (18:23:57; no
  `prevAppId`; NSE's remark says only the filing date was corrected) hold the same two promoter
  trades. Discovery now counts them once. On NSE's live list PATINTLOG moves from −₹4,37,681
  (+₹71,214 twice, less a director's ₹5,80,109 sale in filing 3892) to −₹5,08,895. The feed
  stores 3886 as positive and low, and 3893 as neutral and low with the sentence above.

### Changes

| Finding | Change |
|---|---|
| **F1** (required), discovery | `core/discovery/insider.py`. The cache keeps each filing's trades (no names) and whether NSE lists it as a revision, not one net per filing. `counted_trades()`: filings in dissemination order; an original's trades are added; each trade of a revision replaces the closest earlier trade of the same company with the same action and share count; an unmatched trade is new. Only trades whose last day is in the window count. `refresh_insider_trades()` stores each company's net (`net_inr`). A filing whose promoter or director market trade has no day is unreadable. A cache line without trades is read again; a cache without `net_inr` is never used. |
| **F1**, feed | `core/events/disclosures.py`: `is_revision()` (NSE's `typeOfSubmission` or the XBRL's `RevisedFilling`). `insider_event()` makes a revision neutral and low, and appends the revision sentence in place of the 75% or "no reason" note. The feed calls it unchanged. The module text has a "Revisions" paragraph. |
| **F1**, docs | KT section 4: the revision rule, a PATINTLOG and NAUKRI example, a limit (a revision leaves the corrected filing's event as it was). KT section 8: the each-trade-once and trade-day rules with the live examples, the 75% rule, two limits. Guide 02-L: a revision is its own neutral, low event, and apart from it nothing appears twice. Guide 06-I: check a revised company's `net_inr` and a promoter sale above 75%. CODEBASE: the two module rows. PDF rebuilt. |
| **F2** (recommended) | `insider.py`: `_nets()` reads the latest promoter share (NSE's shareholding list, `quarters_from_list`, as the feed) for each company with a counted promoter-group market sale. `symbol_net()`: above 75% those sales count nothing; directors' trades still count; with no figure from NSE the sale counts, as the event does. A failed read makes the run incomplete and is named ("promoter holding unread for <SYMBOL>"). |
| **L1** (optional, done) | `core/discovery/guards.py`: a pledge row whose quarter ended more than 200 days before the window's latest session, or has no quarter, is unknown: kept and recorded as `promoter_pledge:<SYMBOL>`. KT section 8 and guide 06-I. |
| **I1** (optional, done) | `usable_insider_trades()`: a cache whose window ends after the screen day is not used ("filings read up to 2026-10-23, after 2026-10-22"). |
| Tests and fixtures | `tests/unit/test_disclosures_pr011.py`: 28 new tests (80 → 108), one existing test extended (the shareholding call and `promoter_holding`). Seven new fixtures recorded from NSE on 23 Oct: the list rows of PATINTLOG 3886/3893, HTEL 3762/3945/3922 and NAUKRI 3962, and their XBRLs (`analysis_data/pr011_rework1/fetch_revisions.py`, `make_fixtures.py`). |

### Decisions (delegated, recorded)

- **D16 — how a revision is matched.** NSE gives a revision its own `appId`. In the review's
  window (26 Sep–23 Oct) 2 of 6 revisions named an earlier filing (`prevAppId`), and neither id
  was on the list. So a revision is linked to the trades it restates, not to a filing id. The
  live revisions corrected a value (360ONE: "total amount of securities sold corrected"), a day
  (NAUKRI 3963: "the correct date of revocation"), a person's category (SARLAPOLY), added a trade
  (HTEL) or restated unchanged trades (PATINTLOG, NAUKRI 3962). So the match needs only the same
  action and share count. Among several, the trade that agrees on most of person group, market,
  value and days is replaced, then the latest. An original is never deduplicated: KARURVYSYA's
  filing has three persons with identical trades, and SARLAPOLY filed two originals of the same
  sale. `prevAppId` is not used.
- **D17 — the window is the trade's last day.** A trade counts when its last trade day (else its
  first) falls from `window_from` to `window_to`, both included. Measured on NSE's live list (28
  days to 23 Oct): 31 companies' nets changed. 1 changed by the revision rule (PATINTLOG), 30 by
  the window (NAUKRI among them). Of the 70 left-out promoter or director trades, 62 were made
  1–3 days before the window started and filed inside it (the normal disclosure lag). 8 were made
  7–36 days before. So a trade now counts for 28 days after it was made, not after it was filed,
  as the review's rule requires. For example, AARTIPHARM's promoter group sold ₹106.4 crore on
  21–22 Sep and NSE disseminated the filing on 25 Sep: it counted in windows ending up to 20 Oct,
  and not on 23 Oct (the old rule kept it until 23 Oct).
- **D18 — the feed stores a revision as a revision.** Not storing a revision whose trades match a
  stored event would need the trades in every event's facts, and often the original is not in the
  store (NAUKRI's was filed in August). A labelled event is visible: the reader sees that NSE
  revised the filing. The store is append-only, so the corrected filing's event stays as it was
  (a KT limit). A revision's note replaces the 75% and "no reason" notes: the trades are not new.
- **D19 — the 75% rule in discovery, per trade.** The promoter share comes from the same list and
  test as the event (`quarters_from_list`, latest quarter, more than 75.0%). It is read each run,
  only for companies with a counted promoter-group market sale: 17 on 23 Oct, none above 75%. The
  event is per filing: a filing with a promoter sale and a director sale above 75% is neutral as an
  event, while discovery still counts the director's sale. No figure means the sale counts, as in
  the event. A failed read leaves the run incomplete and is retried, as a failed document is.
- **D20 — a stale pledge row is unknown.** A quarter's pattern is due within 21 days of its end,
  so the latest due quarter is at most about 112 days old; 200 days allows one late quarter. On 23
  Oct (NSE's market list recorded at 12:35), 79 of 1,558 rows were more than 200 days old (10 from
  before 2015), and 35 of them showed more than 25% pledged. Those were rejected before; a
  shortlisted one is now kept and named as unknown.
- **D21 — the cache's format.** A filing line without trades is read again, and a cache without a
  net per company is refused (otherwise every score would be 0, a neutral rank). No production
  cache exists: PR-011 is not deployed.
- **D22 — no new production probe.** The only new call is the shareholding list from the
  discovery run. PR-011-P1 already proved that endpoint from the production container (MARUTI,
  200, 22 quarters).

### Invariant tests (expected values worked by hand)

| Test | Fixture | Expected |
|---|---|---|
| `test_an_identical_revision_without_prev_app_id_counts_once` | PATINTLOG 3886 + 3893, recorded | +₹36,62,165 − ₹35,90,951 = +₹71,214 = **0.0071214** crore once (0.0142428 if summed); last day 29 Sep in 25 Sep–23 Oct |
| `test_a_revision_that_repeats_four_trades_and_adds_one_counts_five` | HTEL 3762 + 3945 + 3922, recorded | six trades, not ten; net **0.8585** (the promoter's ₹85,85,000; designated persons count nothing). As promoter-group trades: + ₹49,20,025 = **1.3505025**; window from 26 Sep: **1.349488** |
| `test_a_revision_of_an_august_trade_is_not_in_a_window_ending_23_october` | NAUKRI 3962, recorded | **0.0**, not −68.0478416; a window from 20 Aug holds it, from 21 Aug not; no shareholding call for a director's sale |
| `test_three_identical_trades_in_one_filing_count_three_times_and_a_revision_keeps_three` | KARURVYSYA 4038 (+ a revision row) | **−0.230769** both ways (not −0.461538, not −0.076923) |
| `test_a_revision_that_corrects_a_value_day_or_category_counts_the_corrected_trade_once` | PATINTLOG with 3893 edited | value ₹36,62,000: **0.0071049**; day: **0.0071214**; category "Immediate relative": **0.0** |
| `test_a_revision_replaces_each_matching_trade_once_and_adds_the_rest`, `…_closest_earlier_trade_then_the_latest` | hand-made | 2 + a 3-trade revision = **3**; SARLAPOLY's figures: values {10,00,000; 10,00,003} remain; a tie replaces the later; dissemination order, not id |
| `test_a_revision_event_is_neutral_low_and_says_it_revises_an_earlier_filing`, `test_the_list_or_the_xbrl_marks_a_revision` | NAUKRI 3962; KARURVYSYA | neutral, low, the exact sentence; the same trades as an original: negative, high; either flag marks a revision |
| `test_a_feed_run_stores_a_revision_as_a_revision_not_as_new_trading` | PATINTLOG, a feed run at 18:30 on 1 Oct | 3886 positive, low; 3893 neutral, low, sentence + note; one positive event; the next run fetches nothing |
| `test_a_promoter_sale_above_the_75_percent_cap_counts_nothing_in_discovery` | KARURVYSYA + its list row | 78.2 and 75.01: **0.0**; 75.0, 58.72, no figure: **−0.230769**; BUYERCO 4.5 unchanged |
| `test_above_the_cap_only_promoter_group_sales_are_left_out` | hand-made: promoter sale ₹30 lakh, director sale ₹10 lakh, promoter purchase ₹20 lakh | above 75%: **+₹10 lakh** (the promoter sale left out); at 75.0 or unknown: **−₹20 lakh** |
| `test_a_failed_promoter_share_read_leaves_the_signal_unavailable`, `test_no_promoter_share_is_read_while_filings_are_unread` | KARURVYSYA | unavailable, named, no `net_inr`; the next run completes without re-reading documents |
| `test_a_market_trade_without_a_day_makes_its_filing_unreadable`, `test_a_cache_read_after_the_screen_day_is_not_used`, `test_a_cache_line_without_trades_is_read_again_and_never_used_as_zeros` | BUYERCO; KARURVYSYA | "1 of 3 filings unreadable"; "filings read up to 2026-10-23, after 2026-10-22"; "cache has no net per company", 3 re-read |
| `test_a_pledge_row_more_than_200_days_old_is_unknown_not_used` | MARUTI's pledge row, quarters changed | window to 23 Oct: 30 Jun and 6 Apr (200 days) reject at 99%; 31 Mar, 5 Apr, no quarter, Dec 2014 are unknown |

**Mutants.** `analysis_data/pr011_rework1/rw_swap_plugin.py` (`PR011_RW_SWAP`, in memory, the same
mechanism as the implementation's): **29 of 29 caught**, base 108 passed. The first run of 28 left
R06 (the match ignores the share count) alive. HTEL's recorded filing 3762, an unrelated
promoter purchase, was then added to the HTEL test, and R06 is caught. The implementation's 32
mutants rerun on the rework: 31 caught; M21's line was rewritten, so it no longer applies, and R29
is the same mutant on the new line (caught).

**The reviewer's repro** (`analysis_data/pr011_review/test_review_repro.py`, which asserts the
defects): 3 of its 4 tests now fail, each on its defect line, with the CONTRACT value
(BUYERCO 4.5; the revision not positive; neutral and low). The fixture check passes.

### Live check on NSE's list (local, read-only)

`analysis_data/pr011_rework1/live_refresh.py`: the real `refresh_insider_trades` for the 28 days
to 23 Oct, 17:56–17:58 IST, into the ignored folder (not `data/`). 357 filings for 179 companies,
7 revisions, all read in 125.5 s, 0 unreadable. 17 promoter shares read, none above 75%, none
unknown. `complete` true. Companies with a non-zero net: 68 (84 before). NAUKRI −68.05 → 0;
PATINTLOG −0.0438 → −0.0509; HTEL 0.8585 both. The cause split is in D17
(`live_breakdown.py`).

### Self-review (same conversation; not the fresh re-review)

- **Hard-review Q1 for revisions.** A revision is never new trading: neutral and low in the feed,
  and in discovery its trades replace what they restate. The window is the trade's day, and the
  list stays on dissemination, so no trade disclosed after the screen day is read.
- **Q2.** Discovery is no more confident than the event about a sale above 75%.
- **Unavailable is never neutral.** A failed promoter-share read and an undated trade both make
  the signal unavailable and named; an old cache is refused, not read as zeros.
- **Not done:** the feed does not revise the stored event of the filing a revision corrects
  (KT limit). A revision that drops a trade or changes a share count is not detected (KT limit;
  none whose original was listed did so in the review's window).

### Commands and environment (rework 1)

Windows 11, the `.stockai` venv (Python 3.13), hermetic boundary on (SA-005).

| Command (repository root) | Result |
|---|---|
| `pytest -q -p no:cacheprovider tests/unit/test_disclosures_pr011.py` | **108 passed** |
| the story file + the 10 other changed test files (the review's set) | **386 passed** in 45 s |
| `analysis_data/pr011_rework1/run_rw_mutants.py` | **29 of 29 caught**, base 108 passed |
| `analysis_data/pr011_rework1/run_orig_mutants.py` | 31 caught, M21 not applicable (R29) |
| `pytest -q -rfEs -p no:cacheprovider tests` (CI's command) | **5,672 passed, 12 skipped, 1 xfailed, 0 failed** in 14 min 29 s (the implementation's 5,644 plus these 28); `find data -newer suite_marker`: no file |
| `scripts/ci/check_broad_except.py` | **OK (151 grandfathered)** |
| `scripts/docs/build_kt_pdf.py`, then `check_kt_docs.py` | 54 pages, source `6e9645ae…`; **errors `[]`** |
| `analysis_data/pr011_rework1/rw_write_manifest.py`, `kt_manifest.py verify` | 40 files, `0e1ba470…`, **mismatches `[]`** |
| `analysis_data/pr011_rework1/rw_digest.py` | review input rebuilt, 32 files match; rework `145b5337…`; cumulative `c9f16799…` |

### Manifest and digests (the re-review's input)

- **Manifest:** [PR-011-manifest.json](PR-011-manifest.json), rewritten: sha256
  `0e1ba470e2821acce98a18983e4e0f1f723ebcadf84be3075bc5c8a21c092615`, 40 files (the review's 33
  and the 7 new fixtures). The review's input manifest is kept as
  `analysis_data/pr011_rework1/review_input_manifest.json` (`2b264207…`).
- **Rework diff:** sha256 `145b5337a877a437f2bdb08a05e24d39350d3db67ef8c0e15c5815352a12bd89`,
  138,494 bytes, 14 paths. Recipe (`rw_digest.py`): the review's input is rebuilt under
  `analysis_data/pr011_rework1/review_input/` from HEAD `16e31b5` plus
  `analysis_data/pr011/pr011.diff` (`939890c3…`), and every rebuilt file must match the review
  manifest's hash. Then, for each path of the new manifest except the PDF, sorted: `git diff
  --no-index review_input/PATH PATH`, or `/dev/null PATH` for a new file.
- **Cumulative diff:** sha256 `c9f16799fb2e688d88a6f07f4d99533f18f1cab3ad76525b6684137b993a1ca8`,
  328,750 bytes, 39 paths, the implementation's recipe against HEAD `16e31b5`.

Raw outputs (ignored, `analysis_data/pr011_rework1/`): `state_start.py`, `fetch_revisions.py` and
`raw/`, `make_fixtures.py`, `rw_swap_plugin.py`, `run_rw_mutants.py`, `mutants_out_R01-R28.txt`,
`mutants_out.txt` (base + R29), `mutants_all.txt`, `run_orig_mutants.py`, `orig_mutants_out.txt`,
`live_refresh.py`, `live_cache.json`, `live_refresh_out.json`, `live_breakdown.py`,
`live_breakdown_out.json`, `full_suite.txt`, `review_input_manifest.json`, `review_input/`,
`rw_write_manifest.py`, `rw_digest.py`, `rework1.diff`, `cumulative.diff`.

**Commit-time edits** (unchanged from the implementation): the KT header "Code inspected" bump,
section 12's PR-011 row Done, PDF rebuild; guide 02-L and 06-I status lines.

## In one example

At 08:15 on Fri 23 Oct KARURVYSYA is held, MARUTI watched and VINCOFE a shelf idea.

- **Before:** the feed reads NSE announcements, board meetings and news. Insider trades,
  substantial acquisitions, pledges and shareholding changes are not seen. In discovery,
  `insider_buying` (0.10) and `mf_holding` (0.05) are dark, and the pledge guard is always
  "degraded".
- **After:**
  1. NSE's insider list for KARURVYSYA, 16–23 Oct, has one filing, disseminated 22 Oct
     19:29:01 (appId 4038). Its XBRL shows three promoter-group members, each selling 2,000
     shares for ₹7,69,230 in the market on 21 Oct. One event: `insider`, negative, low (₹23.1
     lakh is under ₹1 crore), "The promoter group sold 6,000 shares worth ₹23.1 lakh in the
     market on 21 Oct 2026. Filed with NSE on 22 Oct 2026. The filing gives no reason for the
     sale." `published_at` 2026-10-22T19:29:01+05:30, `occurred_from` 2026-10-21.
  2. VINCOFE's Regulation 31 row: a promoter released a pledge on 2.86% of the company on 8
     Oct, filed 22 Oct 20:49:10. One `pledge` event, positive, medium.
  3. MARUTI's shareholding list gives 30 Sep (58.72% promoter) and 30 Jun (58.65%). Both
     quarters' XBRLs are read once and kept: FII 12.82% → 12.42%, DII 25.18% → 25.41%, mutual
     funds 15.33% → 14.77%. No category moved a point, so no `ownership` event. At 18:30
     nothing is fetched again.
  4. No disclosure reaches the model.
  5. On Saturday the discovery run lists the 28 days' insider filings (351 on 23 Oct), reads
     each XBRL once, and the screen ranks `insider_buying` only when all were read. The 80
     shortlisted stocks' pledge rows are read; more than 25% of the promoter holding pledged
     rejects the stock (A2Z Infra had 99.68%).

These are the story's tests `test_a_feed_run_stores_each_disclosure_once_without_the_model`,
`test_the_next_run_fetches_no_document_again_and_stores_nothing`, the insider cache tests and
`test_the_pledge_guard_rejects_heavy_pledges_and_degrades_the_unknown`, on the recorded payloads.

## Data sources: what was measured

Public NSE endpoints, read from this machine on 23 Oct 2026 between about 12:40 and 13:20 IST
through the `nse` client's `_req` (nse 2.1.3 locally; production pins `<4.0`), so NSE's
process-wide throttle applied. Raw output is in `analysis_data/pr011/` (ignored):
`nse_probe.py`, `nse_probe_pit.py`, `pit_weeks.py`, `pit_page.py`, `pit_js.py`,
`nse_probe2.py`, `gg_windows.py`, `pledge_check.py`, `pledge_unknown.py`, `fetch_xml.py` and
their `*_out.json`/`raw/` files.

| Source | Endpoint | Measured |
|---|---|---|
| Insider trades (old) | `corporates-pit` | Rows per fortnight in 2026: 190, 290, 489, 416, 554 to early April; 65, 62 in April; **0 from 4 May to 22 Oct**. Not used. |
| Insider trades | `corporates-pit-gg` | Found in NSE's own page code (`corporate-filings.js`: the insider-trading tab calls `/api/corporates-pit-gg?index=equities` with `symbol`, `from_date`, `to_date`). Market-wide: 351 filings for 177 companies in 25 Sep–22 Oct, 31 in 15–22 Oct (results-season trading window), 949 in June. Rows carry filing metadata only (`appId`, `broadcastDateTime`, `regulation`, `typeOfSubmission`, `xmlFileName`, `ixbrl`). The trades are in the XBRL (5–11 KB): each person's category, transaction type, mode, shares, value and trade days. |
| SAST Regulation 29 | `corporate-sast-reg29` | MARUTI 5 rows (LIC crossing 5% in June 2026), TATASTEEL 17; market-wide 512 in 28 days; the date filter works with a symbol. |
| SAST Regulation 31 | `corporate-pledgedata-sast3132` | 73 events in 28 days market-wide; fields recorded below. |
| Pledge, latest quarter | `corporate-pledgedata` | Market-wide 1,558 rows, **no symbol field** (company name only); 471 with promoter pledges, 181 above 25% of the promoter holding. `percPromoterShares` = pledged ÷ promoter holding (checked by arithmetic on 8 rows: A2Z Infra 99.68 = 99.68). Per symbol: 1 row for MARUTI, M&M, BAJAJ-AUTO, TVSMOTOR, TCS (each its own company); 0 for NIFTYBEES, LIQUIDBEES and an unknown symbol. 8 companies' latest row was for 31 Mar 2025. |
| Shareholding | `corporate-share-holdings-master` | MARUTI 22 quarters, TATASTEEL 29: promoter % (`pr_and_prgrp`), public %, quarter end, `broadcastDate`, and the full pattern's XBRL (~0.6 MB). In the XBRL each category is one context with one `CategoryOfShareholdersAxis` member; its `ShareholdingAsAPercentageOfTotalNumberOfShares` is a fraction (0.5872 = 58.72%, equal to the list's promoter figure). |

Reg 31 fields, read on two rows: `preeventHolding(Perc)` is the promoter's holding,
`encumbHolding(Perc)` what was encumbered before, `eventDetailsHolding(Perc)` the event,
`postEventHolding(Perc)` what is encumbered after (release of 2.86% from 2.86% leaves 0.00%).

**Fixtures** (`tests/fixtures/company_events/`, built once by `analysis_data/pr011/make_fixtures.py`):
`nse_disclosures_20261023.json` (recorded list rows: two insider filings, MARUTI's two SAST
rows, two Reg 31 events, MARUTI's three latest quarters, MARUTI's and A2Z Infra's pledge
rows), `pit_karurvysya_20261022.xml` and `pit_reliance_20260522.xml` (recorded insider XBRLs),
`shp_maruti_20260930.xml` and `shp_maruti_20260630.xml` (recorded shareholding XBRLs, trimmed to
the contexts the parser reads plus three distractors: a scheme's detail row, the FPI
category-one row and the public total; values unchanged). Person names are replaced by
"Person X", "Promoter X", "Lender X", including the one name inside RELIANCE's free-text
block; every other field is as NSE sent it. Derived inputs are built inside the tests and say
so (a SAST row re-timed into the feed's window, promoter % set to 52.1/50.6, a buyer XBRL
made from KARURVYSYA's).

## What changed

| Area | Change |
|---|---|
| Event schema (`src/backend/shared/schemas/events.py`) | Categories `insider`, `pledge`, `ownership` (`DISCLOSURE_CATEGORIES`) and sources `nse_insider`, `nse_sast`, `nse_pledge`, `nse_shareholding`; fields `occurred_from`, `occurred_to` (the disclosed thing's days) and `facts` (its figures). `CLASSIFIER_CATEGORIES` is the original nine. Stored lines without the new fields still load. |
| Classifier (`core/events/classify.py`) | Validates against `CLASSIFIER_CATEGORIES`: a model answer of `insider`, `pledge` or `ownership` is invalid. Prompt unchanged. |
| Fetcher (`services/data/fetchers/nse_disclosures.py`, new) | The five endpoints as raw rows through `_req`, DD-MM-YYYY windows, `fetch_company_disclosures` (one failing endpoint keeps the others, 0.5 s pauses), `fetch_document` (NSE archive host only, 5 MB cap), `pledge_snapshots` (one client for a list of symbols). Never raises. |
| Rules (`core/events/disclosures.py`, new) | `parse_pit_xml` (a document with a DTD or entity is refused before parsing), `person_group`, `market_net`, `insider_event`, `insider_rows`, `sast_events`, `pledge_events`, `pledged_share_of_promoter`, `parse_shareholding_xbrl`, `quarters_from_list`, `ownership_event`. Pure. |
| Feed (`core/events/feed.py`) | Step 5: per stock, the enabled disclosure endpoints in the filing window; new insider filings' XBRLs (at most 10 per stock per run, newest first); SAST and Reg 31 rows; the latest quarter against the one before, each quarter's XBRL read once. Insider filings wait when the shareholding list fails. Run record: `disclosure_sources`, `disclosures_stored` by kind, `disclosures_failed`, `documents_fetched/_failed/_unreadable/_over_cap`, `ownership_mismatch`; `partial` on any disclosure failure. |
| Store (`core/events/store.py`) | `load_ownership` / `save_ownership`: `data/events/ownership/<SYMBOL>.json`, the latest 8 quarters' FII, DII and MF figures. |
| Discovery signal (`core/discovery/insider.py`, new; `signals.py`, `screen.py`, `__init__.py`) | `refresh_insider_trades` in the Saturday cycle after bulk/block; `usable_insider_trades` (complete, at most 10% unreadable, at most 7 days old) with its reason; `net_by_symbol` in ₹ crore. `sig_insider_buying` reads it; `sig_mf_holding` and its slot are deleted; the screen names the reason in `degraded_checks`; the cycle's result carries `insider_trades` counts. |
| Pledge guard (`core/discovery/guards.py`) | Per shortlisted symbol, one row read: more than `max_promoter_pledge_pct` rejects (`promoter_pledge_high`); no row, several rows or a failed call degrades the symbol; no client or `discovery.pledge_guard` off records `promoter_pledge`. |
| Config (`config.yaml`, `base.py`) | `events.disclosures.{insider,sast,pledge,ownership}: true` (fallbacks false), `events.ownership_move_points: 1.0`, `events.max_documents_per_symbol: 10`; `discovery.pledge_guard: true` (fallback false), `insider_window_days: 28`, `insider_max_documents: 600`; `mf_holding` removed from the weights and the fallback. |

## Design decisions (delegated, recorded)

Optional technical calls under the owner's standing delegation; each is open to the review.

- **D1 — the new insider endpoint.** `corporates-pit` is stale (no row since early May 2026),
  so the feed and the signal read `corporates-pit-gg` and its XBRLs. The old endpoint is not a
  fallback: its silence would read as "nobody traded".
- **D2 — rules, not the model.** Disclosures are structured, so the model adds cost and
  risk, not knowledge. The model may not answer the three disclosure categories (the
  classifier rejects them as invalid).
- **D3 — "when we could have known" is NSE's dissemination time** (`broadcastDateTime`,
  `timestamp`, `broadcastdate`, `broadcastDate`), not the company's filing date, the
  intimation date or the trade. The trade, event or quarter-end days go to `occurred_*`. A
  time more than 10 minutes after the fetch waits, as PR-006 does for announcements.
- **D4 — insider direction.** Only the promoter group's and directors' open-market trades carry
  a direction, by the rupee net. Employees ("Designated Person"), relatives, and off-market modes
  are neutral and low. Thresholds ₹10 crore high, ₹1 crore medium. Categories are grouped by
  the filing's own words: "relative" or "other than" means not the promoter group.
- **D5 — the float rule (the card's hard-review question).** The filing never says why a
  promoter sold. When the latest pattern shows promoters above 75%, the 25% minimum public
  shareholding rule is a plausible reason, so the sale is neutral (at most medium) and the
  sentence names the rule. Otherwise the sentence says the filing gives no reason. When the
  shareholding list cannot be read, the stock's insider filings wait for the next run rather
  than take a guessed label, since a stored event is never relabelled. Exactly 75.0% is not
  above the cap.
- **D6 — names.** No person is named in an insider or pledge event (the data is public, but the
  category is what a reader needs). A SAST acquirer is named: the holder is the news, and is
  usually an institution.
- **D7 — SAST direction** belongs to promoters only; a fund crossing 5% is neutral.
  Reg 29(1) (crossing 5%) is at least medium.
- **D8 — pledge events in both directions.** The card says "an event when it rises". Releases
  are stored too, positive and at most medium, because a reader asking "what happened to my
  stock's pledges" needs both. Invocation is negative and high.
- **D9 — ownership from NSE's XBRL, not Yahoo.** Yahoo has no quarter history, so it cannot
  give a quarter-on-quarter change. Each quarter's XBRL is read once and its figures kept. When
  its promoter figure disagrees with NSE's list by more than half a point, its FII, DII and MF
  figures are not used, and the promoter move alone can still make the event. Direction is
  positive only when every moved category rose; a falling promoter share says the pattern does
  not tell a sale from dilution. Only the latest quarter against the one before is compared.
- **D10 — `mf_holding` deleted, weights not re-tuned.** Its source (monthly scheme portfolios)
  is not part of this story. Per the card it is deleted rather than left dark. The other
  weights are unchanged and sum to 0.95; the screen already renormalises. The settings test
  that asserted "sum to one" now asserts relative weights (a contract change, stated in the
  test).
- **D11 — insider_buying is all or nothing.** It is used only when every listed filing was
  read, at most a tenth unreadable, and the list at most 7 days old. A partial read would rank a
  missed buyer as "nobody traded", which is the neutral score the card forbids. The value is in
  ₹ crore, not scaled by company size (limit below). The cap of 600 documents a run bounds the
  first run.
- **D12 — the pledge guard asks per shortlisted symbol.** The market list has no symbol, and
  matching names is a new identity problem. A symbol answering more than one row is
  ambiguous and degraded, never read. A missing row degrades the symbol and does not pass it.
- **D13 — what ships on.** Every source, the signal and the guard ship enabled, each with its
  own switch. The card's "proof before wiring" is kept by a **pre-push production probe**
  (`analysis_data/pr011/prod_probe.py`, below). A source that fails there is switched off
  before the push, and for insider trades the `insider_buying` weight is deleted.
- **D14 — the KT names the three new files in code text, not links**, as PR-006 did:
  `check_kt_docs` requires a linked file to exist at the declared revision. With that,
  `check_kt_docs` gives `[]` now.
- **D15 — PR-006's fixture switches disclosures off.** Its scope is announcements and news; with
  disclosures on, its fake client would take every disclosure path (and its 0.5 s pauses). The
  disclosure paths are covered here.

## Invariant tests

`tests/unit/test_disclosures_pr011.py`, 80 tests. The expected values are worked by hand from
the recorded payloads and the card, not read back from the code. Transports are blocked by
`tests/hermetic.py`; NSE is a fake client whose `_req` answers from the fixtures and filters
by dissemination day as NSE does, behind the real fetchers.

| Invariant | Tests (examples) |
|---|---|
| Dissemination, not the trade, dates an event (the card's first hard-review question) | `test_an_insider_event_is_dated_by_nse_dissemination_not_by_the_trade` (sold 21 Oct, `published_at` 22 Oct 19:29:01, `occurred_from` 21 Oct); `test_a_since_read_finds_the_filing_on_its_dissemination_day`; SAST and Reg 31 recorded rows; `test_insider_rows_keep_this_code_and_leave_future_rows_for_later` (10 min 1 s ahead waits, exactly 10 min kept) |
| A float-rule sale is not labelled negative (the second question) | `test_a_promoter_sale_above_the_75_percent_cap_is_not_called_negative` (78.2% neutral with the rule's sentence; 75.0%, 74.9% and unknown negative with "no reason"); `test_a_large_sale_above_the_cap_is_at_most_medium`; `test_without_the_shareholding_list_insider_filings_wait` |
| Only promoter and director market trades carry direction | `test_only_promoter_and_director_market_trades_carry_a_direction` (+₹3 cr, −₹1 cr, employee −₹5 cr → +₹2 cr, positive, medium); `test_off_market_moves_and_employee_trades_are_neutral_and_low` (a ₹50 cr gift moves 0 in the net); `test_insider_materiality_is_the_open_market_net` (₹10 cr and ₹1 cr boundaries); `test_person_groups_follow_the_filing_category` (13 categories) |
| The card's ownership fixture | `test_the_card_fixture_promoter_52_1_to_50_6_gives_one_ownership_event` (exact sentence, dated 21 Oct 10:01:23, occurred 30 Sep, FII/DII/MF unavailable); `test_the_recorded_quarters_moved_under_a_point_and_give_no_event` (MARUTI's real quarters); `test_the_one_point_boundary` (1.00 and 1.01 make an event, 0.99 does not); `test_mixed_moves_are_neutral_and_three_points_is_high` |
| Malformed and empty input | not-XBRL, empty, HTML, truncated and entity-bearing documents read as None; odd endpoint answers (`{"error": …}`, a string, non-dict rows, a timeout) give rows and an error, never raise; the shareholding parser reads category totals, not a scheme's row |
| Unavailable is never neutral | feed: a failed document or endpoint stores nothing, is named, makes the run `partial`, and the next run stores it; discovery: `test_ranking_with_insider_buying_unavailable_is_not_neutral` (composite 1, .75, .5, .25: momentum alone; a neutral 0.5 would give .875, .6875, .5, .3125), capped, failed, stale and unreadable caches are unavailable with a named reason |
| Signal present, absent, deleted | `test_ranking_with_insider_buying_present` (DDD's ₹4.5 crore of promoter buying: AAA .875, BBB .6875, CCC .5, DDD .4375, worked by hand); the absent case above; `test_mf_holding_is_deleted_from_config_and_ranking` (config.yaml, settings, the signal slots, `dark_signals`, `signal_ranks`) |
| Once only, and no other company's item | two runs store each disclosure once and fetch no document twice; the shareholding XBRLs are cached; a document naming another company is never stored; the model is never called |
| The pledge guard | 0.00% passes, 99.68% rejected, 25.00% passes and 25.01% rejected; no row, two rows and a failed call degrade; guard off or no client is one degraded check |
| The classifier cannot write disclosure categories | a model answer of `insider`, `pledge` or `ownership` is invalid; `deal` is still the model's |
| The document fetcher only reads NSE's archive | other hosts, `http://`, `None`, a number and `file://` are refused without a call |

**Mutants** (`analysis_data/pr011/run_mutants.py`, in memory through
`analysis_data/pr011/swap_plugin.py`: one exact-once replacement in the real module, with names
rebound in modules that imported them; no file written). **32 of 32 caught** on the final
sources (`mutants_out.txt`; base 80 passed). The first run on earlier sources caught 29 of 30:
M05 (an off-market gift counted in the rupee net) survived and the test was strengthened
(self-review). M31 and M32 were added with the last two code changes. The mutants cover:
the dissemination date (M01); the 75% rule's boundary and its removal (M02, M03); who and which
trades count in the net (M04, M05); materiality boundaries and caps (M06, M07, M10);
relatives (M08); SAST direction and window (M09, M14); the ownership boundary, mixed moves and
the fraction (M11–M13); the DTD check (M15); the feed's dedup, cache, foreign check, mismatch
check, failure naming and deferral (M16–M20, M32); the signal's completeness, staleness,
neutrality and unreadable share (M21–M24); the pledge guard's boundary, unknown and
several-row cases (M25, M26, M31); the archive-only fetch and the DD-MM-YYYY window (M27,
M28); the classifier's categories (M29); and the screen's reason (M30).

**Existing tests changed** (a contract moved; no assertion was relaxed except as stated):

- `test_discovery_screen.py`: the fake `compute_signals` takes the insider cache; the dark set
  loses `mf_holding`; the insider reason is now asserted in `degraded_checks`.
- `test_discovery_signals.py`: six slots; `insider_buying` is None without a cache.
- `test_discovery_settings.py`: the weights' set is six and they sum to 0.95, not 1 (D10).
- `test_discovery_universe_guards.py`: the pledge fetch is faked (NSE unavailable), so the
  hermetic boundary is never reached; the same `promoter_pledge` assertion.
- `test_discovery_api.py`, `test_scheduler_discovery_job.py`: a sample `dark_signals` value
  `mf_holding` became `insider_buying` (the slot no longer exists).
- `test_discovery_cycle_ipo.py`, `test_scheduler_discovery_job.py`, `test_idea_supply_pr004.py`,
  `test_operator_notices_owner_only_fix008.py`: their cycle fakes every stage, so they fake
  the new insider refresh too (`analysis_data/pr011/patch_cycle_tests.py`); the PR-004 screen
  fake takes the fourth argument.
- `test_company_events_pr006.py`: its fixture switches the four disclosure sources off (D15).

## Production probe (acceptance criterion 4)

**PASSED in production: 8 of 8 checks** (`PR-011-P1`). The owner ran the probe from the
production container on 23 Oct at 15:42:30 IST, after this phase's bookkeeping, and saved the
output; the raw copy is `analysis_data/pr011/prod_probe_2026-10-23_1542IST.txt` (ignored).
Sanitized result:

| Check | Production, 15:42 IST | Local dry run, 13:19 IST |
|---|---|---|
| Insider list, 7 days (`corporates-pit-gg`) | HTTP 200, 19 rows, fields present, 0.4 s | 200, 19 |
| Insider list, 28 days | 200, 351 rows, fields present, 0.6 s | 200, 351 |
| SAST Reg 29, 7 days | 200, 35 rows, fields present, 0.3 s | 200, 33 |
| SAST Reg 31, 7 days | 200, 12 rows, fields present, 0.4 s | 200, 12 |
| Pledge snapshot, MARUTI | 200, 1 row, fields present, 1.2 s | 200, 1 |
| Shareholding list, MARUTI | 200, 22 quarters, fields present, 0.4 s | 200, 22 |
| Insider XBRL (archive) | 10,821 bytes, fact names present, 0.1 s | 10,821 |
| Shareholding XBRL (archive) | 605,702 bytes, fact names present, 0.6 s | 605,702 |

So every source answers from the cloud host as it does from this laptop; the two SAST
filings more in production arrived between the runs. No source is switched off, and D13
stands: everything ships enabled. The probe read public NSE data only, with no application
data, logs or environment.

The probe: `analysis_data/pr011/prod_probe.py`. It makes read-only calls to NSE's public
endpoints and prints only counts, field presence, sizes and timings: no rows, names, logs or
environment. It uses only `services/data/fetchers/nse_client.py`, which was already deployed,
so it ran before the push. The command, from Git Bash in the repository:

```
railway ssh "cd /app && echo $(gzip -9c analysis_data/pr011/prod_probe.py | base64 -w0) | base64 -d | python -c 'import sys,zlib;exec(zlib.decompress(sys.stdin.buffer.read(),31))'"
```

**Local dry run** (this machine, 23 Oct 13:19 IST, `prod_probe_local_dryrun.json`): every
source answered 200 with its fields present. Insider list 7 days 19 rows, 28 days 351; SAST
Reg 29 7 days 33; Reg 31 7 days 12; MARUTI's pledge row 1; MARUTI's shareholding list 22
quarters. The insider XBRL (10,821 bytes) and the shareholding XBRL (605,702 bytes) both
carried their fact names.

**Pass rule, before the push (met):** each source answers HTTP 200 with `fields_present`
true, and both documents have `has_marker` true. A source that fails stays out: set its `events.disclosures.*` (or
`discovery.pledge_guard`) to false. If the insider list or its XBRL fails, also delete
`insider_buying` from `discovery.signal_weights` and the fallback, and its slot. Then this
receipt's D13 changes, and the change gets a review. September's lesson (the IPO ladder broke
in production) is why the probe comes first.

## Documentation

Each change is written as current design.

- **KT** (`docs/TECHNICAL_DESIGN.md`):
  - section 4 "Company events": the intro names the disclosure events; steps 2 and 4–5 mention
    them; the record gains `occurred_from`, `occurred_to`, `facts`; a new "Disclosures" part
    (the four sources in a table, when we could have known, the direction rules, documents,
    failures and the KARURVYSYA/MARUTI example); four new limits;
  - section 8 "Discovery": new "Screen signals", "Insider buying" and "Promoter pledge"
    paragraphs, with the 22–23 Oct counts; two new limits;
  - section 9: `company_events_am`/`_pm` read disclosures; `discovery_weekly` reads insider
    trades first;
  - sections 2 and 3: the `core/events` row says disclosures, the `data/events/` row names
    `ownership/<SYMBOL>.json`.
  - New files are in code text, not linked (D14). Section 12's PR-011 row stays `Open` (set
    at commit); the header's "Code inspected" is bumped at commit.
- **PDF** rebuilt: 53 pages, source SHA-256 `c56f18af…`; `check_kt_docs` errors `[]`.
- **CODEBASE:** the fetchers, discovery and events tree lines; the `discovery.*` table (pledge
  limit, `pledge_guard`, weights without `mf_holding`, `insider_window_days`,
  `insider_max_documents`, `insider_trades.json`); the `events.*` table (four switches, the
  move threshold, the document cap); key-file rows for `disclosures.py`, `nse_disclosures.py`,
  `insider.py`, the feed, the schema and the screen; the `data/events/` row.
- **Human testing guide:** 02-L (five trading days of disclosure events against NSE's pages,
  and a prepared above-75% sale) and 06-I (the Saturday run's insider counts, the screen's
  `dark_signals` and reason, the pledge guard), each "PR-011: implemented 2026-10-23
  (uncommitted); fresh review pending". HT-02 and HT-06 "Related PI" name PR-011.
- No change: ARCHITECTURE and AUTOPILOT_GUIDE (neither describes the event feed or the
  screen's signals), PRODUCT_MAP (no new route or job), `docs/README.md`, other story cards.

## Self-review (same conversation; it does not replace the fresh review)

- **Found by the mutants and fixed:** M05 (an off-market gift counted in the rupee net)
  survived the first run. The event did not change, but the discovery signal would have; the
  test now asserts the net.
- **Found by reading again and fixed:** without the shareholding list, a promoter sale above the
  75% cap would have been stored for good as "negative, no reason". Insider filings now wait
  (D5). The pledge guard would read the first of several rows; several rows now degrade (D12),
  after a probe showed NSE answers 0 rows for a non-company and 1 for a company.
- **Found by the existing suite and fixed:** PR-006's fixture ran the new disclosure path with
  its fake client (no `_req`), so every stock in every run took four failing calls and their
  0.5 s pauses, and named a disclosure failure (D15). That first run was stopped after about 20
  minutes; the laptop was also in standby for 12 of them (12:57–13:09 IST), so its slowness
  was not measured. The cycle tests reached NSE through the
  new stage and were failed by the hermetic boundary; they now fake it.
- **Checked:** every broad `except` logs (`check_broad_except` OK; the three new files scanned
  directly, `[]`); a document is parsed only after a DTD/entity check; a document URL must be
  NSE's archive; a symbol names a file only after `valid_symbol`; no user id is written; no
  person's name is stored for insider or pledge events; line endings unchanged
  (`base.py` stays CRLF in the working tree, the rest LF).

## Limits and follow-ups

- **Run time:** each stock now makes four more NSE calls with 0.5 s pauses (about 2 s), so a
  60-stock run is about 2 minutes longer, and its first run reads about 120 shareholding XBRLs
  (about 0.6 MB each, once). Not measured in production. The Saturday discovery run's first
  insider refresh reads up to 600 small documents (a few minutes).
- **Insider buying is in rupees**, not scaled by company size (KT section 8 limit).
- **The instrument is not read.** A filing's `TypeOfInstrument` (equity, or futures and options
  in older filings) is not parsed, so a director's derivatives trade would count in the net at
  its notional value. Every filing recorded here was equity; the reviewer may ask for an
  equity-only net.
- **An unreadable insider document** is fetched again each run while its filing is in the
  7-day window; it is counted in `documents_unreadable`.
- **A revised shareholding pattern** for a quarter already compared is not compared again.
- **The 75% test** uses the latest quarter, up to three months old; PSU timelines for the
  public-shareholding rule differ and are not modelled.
- **No reader yet:** the brief (PR-008), the investment case (PR-005) and the exit rule
  (PR-009) are to read these events; only `GET /events/{symbol}` shows them now.
- **No mutual-fund signal** in discovery (D10). A scheme-portfolio source would be its own
  story.

## For the owner

- **The production probe passed** (8 of 8, 23 Oct 15:42 IST; above), so nothing is switched
  off. The push still waits for the fresh review and the owner's word.
- **After the push:** for a week, guide 02-L. Each morning, read the disclosure events of a few
  held stocks against NSE's corporate-filings page. On the first Saturday, guide 06-I.
- **Push windows:** the jobs are unchanged (08:15, 18:30, Saturday 12:30), but the feed runs
  are a few minutes longer. Avoid 08:10–08:40 and 18:25–18:55.
- **Rollback:** `events.disclosures.<source>: false` for an event source;
  `discovery.pledge_guard: false`; deleting `insider_buying`'s weight. All are config, so a
  push is needed (every push redeploys).

## Commands and environment

Windows 11, the `.stockai` venv (Python 3.13), the vendored Playwright Chromium for the PDF.
Hermetic boundary on (SA-005).

| Command (repository root) | Result |
|---|---|
| `.stockai/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/unit/test_disclosures_pr011.py` | **80 passed** |
| `.stockai/Scripts/python.exe analysis_data/pr011/run_mutants.py` | **32 of 32 caught**, base 80 passed |
| the 20 test files that import a changed module (`analysis_data/pr011/affected.txt`) plus `test_discovery_api.py`, `test_discovery_settings.py`, `test_discovery_fetchers.py` | **627 passed** in 2 min 32 s |
| `.stockai/Scripts/python.exe -m pytest -q -rfEs -p no:cacheprovider tests` (CI's command) | **5,644 passed, 12 skipped, 1 xfailed, 0 failed** in 15 min 19 s (FIX-013's 5,564 plus these 80) |
| `.stockai/Scripts/python.exe scripts/ci/check_broad_except.py` | **OK (151 grandfathered)**; the three new files through `scan_source`: `[]` |
| `python scripts/docs/build_kt_pdf.py`, then `check_kt_docs.py` | 53 pages, source `c56f18af…`; **errors `[]`** |
| `find data -newer analysis_data/pr011/suite_marker` after the suite | no file: the checkout's runtime data is unchanged |
| `.stockai/Scripts/python.exe analysis_data/pr011/prod_probe.py` (local dry run) | 8 of 8 checks answered (above) |

Raw outputs (ignored, `analysis_data/pr011/`): the NSE probes and their outputs, `raw/`,
`make_fixtures.py`, `swap_plugin.py`, `run_mutants.py`, `mutants_out.txt`, `mutants_run.log`
(the first run), `patch_cycle_tests.py`, `edit_codebase*.py`, `edit_guide.py`, `digest.py` and
`pr011.diff`, `write_manifest.py`, `state_start.py`, `state_end.py`, `handoff_end.py`,
`full_suite.txt`, `prod_probe.py` and `prod_probe_local_dryrun.json`.

## Manifest and digest

- **Review input:** [PR-011-manifest.json](PR-011-manifest.json), 33 files, written by
  `analysis_data/pr011/write_manifest.py`. SHA-256 of its LF bytes: **`2b264207fb61f5d354b98acb68034c70876c0e82a72e24c2ea8dd71317c09c09`**;
  `kt_manifest.py verify` gives 0 mismatches.
  - Code (13): `config.yaml`, `core/discovery/__init__.py`, `guards.py`, `insider.py` (new),
    `screen.py`, `signals.py`, `core/events/classify.py`, `disclosures.py` (new), `feed.py`,
    `store.py`, `services/data/fetchers/nse_disclosures.py` (new),
    `src/backend/shared/config/settings/base.py`, `src/backend/shared/schemas/events.py`.
  - Tests (16): `tests/unit/test_disclosures_pr011.py` (new), the five new fixtures, and the ten
    changed test files listed above.
  - Docs (4): the KT and its PDF, CODEBASE, the testing guide.
  - Excluded: STATE, HANDOFF and this receipt (bookkeeping); the owner's line in
    `docs/README.md`.
- **Diff digest:** **`939890c3065256de7c91b21eb689b693b1062942420ec6470cd857765d47eccd`**, 228,612 bytes over 32 paths (every manifest path except the
  PDF), by `analysis_data/pr011/digest.py`. It checks that HEAD is `16e31b5`, then for each
  path, sorted: `git diff HEAD -- PATH` for the 23 tracked paths, `git diff --no-index /dev/null
  PATH` for the 9 new files.
