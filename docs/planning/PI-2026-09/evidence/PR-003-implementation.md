# PR-003 — implementation receipt

**Story:** [PR-003](../stories/PR-003.md): fresh overnight news, with no repeats,
publish-date freshness and global cues. **Phase:** implementation, 17 Oct 2026,
about 16:15–17:30 IST, with a real-data probe and one fix on 18 Oct, about 09:00–10:00 IST.
Session stockagent-main-9a, a new conversation opened with
"continue"; all 16 peers were idle at the start. **Baseline:**
`86a3a60c411805d2749e5e85c23a069f532a945b` (HEAD, clean for every payload path).
**Status after this phase:** `review_required`. Nothing was committed, pushed or
deployed. No production state was read and no message was sent.

## In one example

The brief of Thursday 15 Oct; the previous brief went out on Wednesday.
Google keeps ranking three articles, and the macro feed fetched them all again
this morning:

- a Monday story on SEBI and RBI bond-index derivatives, which Monday's brief
  showed;
- a 5 June GDP article;
- an article whose date Serper gave in a form that cannot be read.

Before this change, all three counted as "the last 24 hours", because they sat
in today's or yesterday's fetch file. The unreadable date was stamped with
*today*. The same RBI/rupee story led 8 briefs running in July.

Now each article must have been **published** on or after Wednesday, by its
IST date. The Monday story and the June article are stale. The undated one is
never shown. A Fed story published on Wednesday but fetched only today is shown.
The brief records why each candidate was dropped:

```json
"overnight_filter": {"since": "2026-10-14", "candidates": 10, "undated": 1,
                     "stale": 7, "repeats": 1, "shown": 1}
```

That is the fixture week's Thursday: 10 entries across three files, and one is
Wednesday's crude story, which Wednesday's brief already showed. On Friday,
another outlet's rewording of the Fed story ("US Fed holds rates steady and
signals two cuts in 2026") is suppressed. "Crude oil falls 4% as US-Iran
ceasefire announced" is shown, though Wednesday showed "Crude oil jumps 5% as
Iran tensions escalate": it names new entities and a new figure.

A new section opens before the news:

```text
BEFORE THE OPEN   (latest level; change on the previous session)
  • S&P 500 5,829.00 (+0.50%), as of Mon 12 Oct
  • Nikkei 225 38,805.00 (-0.50%), as of Tue 13 Oct
  • Brent crude $75.11 (+1.50%), as of Tue 13 Oct
  • US 10-year yield 4.13% (+3 bp), as of Mon 12 Oct
  Unavailable: Nasdaq Composite, USD/INR.
```

(The Tuesday fixture frames: Nasdaq's fetch failed, USD/INR returned one session
and Hang Seng did not trade that day.)

## What changed

- **Fetcher** (`services/background/macro_news_fetcher.py`):
  - `_normalize_serper_date(date_str, now)` returns the **IST** publish date.
  - Relative ages count back from the fetch time: "10 hours ago" at 07:30 IST
    is yesterday, no longer "today". It handles s/min/hr/day/week/month/year,
    "a"/"an", "just now" and "yesterday".
  - An unreadable, future or overflowing date is `""`.
  - NewsAPI's UTC `publishedAt` becomes its IST date (`_newsapi_date`).
  - Each entry keeps the source's own string in `published_raw`.
- **Cache** (`services/background/macro_news_cache.py`):
  - `published_on(entry)` and `ist_today()`.
  - `entries_fetched(start, end, severities)`: files start..end, one entry per
    URL, the first fetch kept.
  - `entries_published(start, end, severities)`: by IST publish date, reading
    one extra file before `start`, because files are named by the server's
    fetch date.
  - Chat's `get_high_severity` / `get_formatted_context` / `get_for_reviewer`:
    HIGH items published today or yesterday.
  - `get_all_today` (chat's `get_macro_news`): every severity published today
    or yesterday, where it was everything fetched today.
  - `get_for_daily_review`: HIGH+MEDIUM published on the reviewed day or the
    day before, from files fetched by the reviewed day. Its line format is
    unchanged, so the provenance parser is unaffected.
- **Brief** (`core/delivery/brief.py`):
  - `_overnight_items(on, recent)` returns `(items, counts)`. The floor is the
    previous brief's date (`_overnight_since`); undated and future items are
    dropped, then stale ones.
  - It suppresses repeats against the story keys of the user's last 5 briefs
    (`_story_key`, `_repeats`, `_shown_keys`; URL normalised by `_norm_url`;
    figures by `_headline_numbers`).
  - Items are ordered newest first, merged within the brief, then capped.
  - Each shown item stores its `published_date` and `story_key`, and
    `_dedup_overnight` passes the cluster's URLs to the kept item.
  - `build_morning_brief` reads `store.load_recent_briefs(on, 5)` and writes
    `before_the_open`, `overnight` and `overnight_filter`. It takes
    `markets=`, which `run_morning_brief` fetches once per run.
  - Text and HTML gain a "Before the open" section. `enrich_brief_for_api`
    adds `before_the_open_lines` and `before_the_open_unavailable`.
- **Store** (`core/portfolio/store.py`): `load_recent_briefs(before, n)`, the
  last `n` briefs dated strictly before `before`.
- **Markets** (`services/data/fetchers/macro.py`):
  `get_overnight_markets(on, instruments, history, max_age_days)`, one row per
  instrument from Yahoo daily bars. The reader `history(ticker)` is injectable.
- **Settings and config:**
  - `delivery.brief_overnight_max_lookback_days: 4`, `…repeat_lookback_briefs: 5`,
    `…repeat_min_shared: 3`, `…repeat_max_new_share: 0.34`;
  - `delivery.brief_markets`: 7 instruments, each with a session rule and a
    unit;
  - `delivery.brief_market_max_age_days: 4`.
- **Inbox** (`src/frontend/prototypes/brief-view.jsx`): a "Before the open"
  fold renders the server's sentences and the "Unavailable:" line, and does no
  formatting of its own.

## Design decisions (delegated, recorded)

- **D1. Publish date = the IST calendar date, unreadable = empty.** The brief
  date is an IST date (the job runs at 08:50 IST), so 20:00 UTC Tuesday
  (01:30 IST Wednesday) counts as Wednesday. A date that cannot be read is
  stored as `""` with the raw string kept. It is never "today", and every reader
  treats it as not recent. A parsed date later than the fetch is also `""`.
- **D2. Floor = the previous brief's date.** It is a date, not the previous
  brief's send time: most publish dates have only date granularity, so the
  comparison is by date.
  - An item published on the floor day before that brief went out can
    therefore pass. If that brief showed it, the repeat check catches it; if
    not, showing it now is still news to the reader.
  - With no previous brief, the floor is the previous trading day.
  - It is never more than 4 days back (`brief_overnight_max_lookback_days`), so
    a gap in briefs cannot turn week-old news into "overnight".
- **D3. Files read: floor−1 through the brief's day.** Files are named by the
  server's fetch date. The Dockerfile sets no `TZ`, so that is UTC in
  production (an inference from code, not checked in production). The code does
  not rely on it: dates are converted to IST explicitly, and the one extra file
  covers the 00:00–05:30 IST stretch. Nothing fetched after the brief's day is
  read, so a backfilled brief sees only what was known by then.
- **D4. The story key** holds:
  - the normalised URLs: no scheme, fragment or `utm_*` parameters, no leading
    `www.`/`m.`/`amp.`, no trailing slash, the query otherwise kept (PIB-style
    `?NoteId=` URLs stay distinct);
  - the salient entities of the **displayed** headline (the same
    `_salient_tokens` and stoplist as the within-brief merge);
  - the headline's canonical figures.

  The displayed headline is what the reader judges as "the same again". It is
  also all that briefs stored before PR-003 have. URLs of items merged into a
  shown item are remembered too.
- **D5. The repeat rule.** The same URL is always a repeat. A different URL is
  a repeat only when all three hold:
  - it shares ≥ 3 entities with a shown story;
  - ≤ 34% of its own entities are new;
  - it carries no figure that story lacked.

  It is deliberately stricter than the within-brief merge (≥ 2 shared) and
  biased toward showing. The calibration is in
  `analysis_data/pr003/calibrate.py`: the July briefs' real headlines and
  realistic follow-ups. Six of 7 reworded pairs are caught; the miss is an
  acronym against the full name: "Non-Resident Indians" against "NRIs". All 8
  real developments are shown, at 0.50 new or more. The figure rule was added
  in self-review, after "Rupee falls to record low of 96.5" and "…of 97.2"
  scored 0.33.
- **D6. History = the last 5 briefs dated strictly before the brief's day.**
  A rerun the same day therefore shows the same items and does not suppress
  what 08:50 showed. For briefs stored before PR-003, the headline gives the
  entities and figures; there is no URL.
- **D7. Newest first.** Candidates are sorted by publish date (stable), then
  merged and capped at 3. Before, the order was the fetch order.
- **D8. `overnight_filter`** records `since`, `candidates`, `undated`, `stale`,
  `repeats` and `shown`. Candidates minus all the rest are the items merged
  within the brief or cut by the cap. A future-dated item counts as undated.
- **D9. Chat and the daily review use the same rule.** Chat (system context
  and `get_macro_news`): items published today or yesterday (IST). Daily
  review: the reviewed day or the day before. Chat's short-circuit is
  unchanged: it adds no macro context while the server's file for today does
  not exist yet.
- **D10. Market sessions.**
  - S&P 500, Nasdaq Composite and the US 10-year yield (`us_close`) use the
    last bar dated **before** the brief's day: that US session has not closed
    at 08:50 IST.
  - Nikkei 225 and Hang Seng (`asia_live`) are shown only when Yahoo has a bar
    dated the brief's day. Otherwise the market is "closed": absent, but not
    "unavailable", since it is not a failure.
  - Brent (`BZ=F`) and USD/INR (`INR=X`) (`24h`) use the latest bar up to the
    brief's day.

  The change is against the previous bar, and the as-of date is the
  exchange-local bar date. Saturday and Sunday bars are ignored: Yahoo carries
  weekend quotes for USD/INR, which does not trade then (see the 18 Oct probe
  below). A figure older than 4 days, a 10-year yield outside 0–20% (a ×10
  quote), NaN/≤0 closes and fewer than 2 sessions all make the figure
  "unavailable", which carries no number.
- **D11. GIFT Nifty is not shown.** Yahoo has no GIFT Nifty series. I did not
  search further for another free source, so the story's fallback applies:
  not shown.
- **D12. One fetch per run.** The figures are market-wide, so they are fetched
  once per run and passed to every user's brief. If the fetch as a whole
  fails, every configured figure is named unavailable. `brief_markets: []`
  removes the section.
- **D13. The server writes the sentences.** The Inbox renders them
  (`enrich_brief_for_api`), in line with the brief view's rule that the
  server translates.
- **D14. Narration is unchanged.** The headline prompt does not see the
  market figures.

## Invariant tests

`tests/unit/test_overnight_freshness_pr003.py` (new; 61 = 60 passed and 1
strict xfail). Expected values are worked out by hand from the fixtures. They
are not read back from the code.

- **The fixture week** (Mon 12 – Fri 16 Oct 2026). The real
  `run_morning_brief` runs five times over real feed files and a real
  PortfolioStore, with the briefs saved and read back. Only the LLM narration
  and the delivery channel are stubbed; Yahoo comes from fixture frames.
  - Article A is fetched all five days, once with `utm` tags and once on the
    mobile host. It appears in Monday's brief only.
  - The June GDP article, the undated item, the Monday article first fetched
    on Thursday (3 days old), and the reworded copies of A and of the Fed story
    are never shown, in the JSON, the email text or the HTML.
  - The development N (new entities, newer date), the late-fetched Fed story T
    and the crude follow-up Q are each shown once.
  - No shown item was published before the previous brief's date.
  - Each day's `overnight_filter` equals the hand-computed counts.
  - A same-day rebuild shows the same items.
  - The delivered email carries the market line with its as-of dates.
- **Repeats.**
  - 10 realistic follow-ups are shown, among them a cut after a hold, a
    notification after an announcement, a recovery after a record low, a new
    record low (96.5 → 97.2), Sensex 1,100 → 1,450, and "Fed cuts rates" after
    "Fed holds rates".
  - 4 reworded copies are suppressed, among them 6.0% against 6%.
  - The same article under new wording is suppressed by its normalised URL.
  - A brief stored before PR-003 still counts as shown.
  - A story merged into a shown item counts as shown: its second URL is
    suppressed on the next day although 7 of its 10 entities are new.
  - Only the last 5 briefs count, through the real store.
  - **The known limit is a strict xfail:** "Govt withdraws bill …" after "Govt
    approves bill …" (5 of 6 entities shared, same figure) is suppressed.
- **The floor.**
  - A first brief reaches back to the previous trading day.
  - A 10-day gap is capped at 4 days.
  - UTC publish times are judged by their IST date (20:00 UTC passes the
    floor, 18:00 UTC does not).
  - A future-dated item is never shown.
  - An entry filed the day before the floor is found.
  - Over the cap, the newest items are kept.
- **Fetcher.**
  - 9 Serper forms map to their IST dates from a fixed 07:30 IST fetch.
  - 7 unreadable, future or overflowing forms map to `""`.
  - A UTC fetch clock does not move the IST date.
  - NewsAPI times are converted to IST.
  - Through the real Serper reader (with `requests.post` stubbed), an
    unreadable date is stored as `""` with its raw string.
- **Chat and the daily review.** Old, undated and other-severity items are
  left out of `get_high_severity`, `get_formatted_context` and `get_all_today`.
  The daily review drops an old article fetched on the reviewed day and keeps
  a MEDIUM one published the day before.
- **The market line**, from fixture frames for Tuesday 13 Oct.
  - Each figure is its own instrument's close on its as-of date.
  - Tuesday's in-progress US bar is not used, and nor is a bar dated after the
    brief.
  - A NaN bar is skipped; its prev is the bar before.
  - A Sunday USD/INR quote (the shape the 18 Oct probe saw) is neither
    Monday's previous session nor, before Monday's bar exists, the level.
  - Hang Seng with no Tuesday session is "closed".
  - A failed fetch and a single session are "unavailable", with no figure.
  - The text, the HTML (escaped) and the API render the same sentences and the
    "Unavailable:" line, with no 0 and no unused bar's value.
  - Stale and ×10-yield figures are unavailable.
  - A total failure names every figure.
  - An empty list removes the section.

Changed existing tests:

- `tests/unit/test_delivery_brief.py`: an autouse `_before_the_open` stub, so no
  test reaches Yahoo. The `_overnight_items` stubs return `(items, {})`. The
  three collector tests feed `entries_fetched` with publish dates. Their
  assertions are unchanged: the title fallback, summary preferred, the
  within-brief merge.
- `tests/unit/test_brief_earnings_watch_fix004.py`: the same two stubs.
- `tests/test_macro_news_cache.py`: entries seeded in past files now carry
  realistic publish dates. The old fixtures stamped everything with *today*,
  even in a file fetched 10 days earlier. The new rule correctly reads that as
  published after the reviewed day. Every assertion is unchanged.
- `tests/frontend/no_invented_figures.test.mjs`: 2 browser tests.
  - The fold lists the server's sentences and the "Unavailable:" line; a
    closed market is absent; no number appears for a failed figure; and every
    percentage on screen is one the server sent.
  - A brief stored before the change shows no fold.

  Against HEAD's screens (`SA_FRONTEND_ROOT`), the first **fails**; the second
  is a compatibility guard and passes there.

**Bite proof** (`analysis_data/pr003/pr003_mutants.py`, `run_mutants.sh`). Each
run rewrites one fragment of the shipped source in memory and re-executes the
module before collection, then runs the three story and brief test files.
Final bytes: **33 of 33 mutants caught**; the unmutated baseline is 140 passed, 1 xfailed.

| Group | Mutants (each caught) |
|---|---|
| The original defect | unparseable date → today; cache by fetch file; no publish floor; undated → today; no repeat check; daily review by file; chat `get_all_today` by file |
| Dates and zones | Serper without IST; NewsAPI UTC date; future date kept (fetcher, brief); no file before the floor; floor uncapped; floor ignores the previous brief; history includes today's brief |
| Repeat rule | URL only; new share ignored; within-brief threshold (≥ 2) reused; figures ignored; figures not canonical; URL not normalised; cluster URLs forgotten; oldest first |
| Market line | today's US bar used; future bars used; closed Asian market shown; stale shown; yield unchecked; weekend bar kept; NaN kept; failure shown as 0; unavailable not named; total failure empty |

## Commands and environment

Windows 11, the repository's `.stockai` venv (Python 3.13), Node 24 with the
vendored Playwright Chromium. Hermetic boundary on (SA-005): no `.env`, no
network, no checkout data.

| Command (repository root) | Result |
|---|---|
| `.stockai/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/unit/test_overnight_freshness_pr003.py` | **60 passed, 1 xfailed** (strict, the known limit) |
| the same with `tests/unit/test_delivery_brief.py` and `tests/test_macro_news_cache.py` (the mutant baseline) | 140 passed, 1 xfailed |
| `tests/test_macro_news_cache.py tests/test_macro_news_fetcher.py tests/unit/test_delivery_brief.py tests/unit/test_brief_earnings_watch_fix004.py tests/unit/intelligence/rl/test_macro_fallback_context.py` (the existing readers, before the new file) | 140 passed |
| `bash analysis_data/pr003/run_mutants.sh` | baseline 140 passed, 1 xfailed; **33 of 33 caught** (table above) |
| `npm run test:frontend` | **34/34** (was 32; the 2 new brief tests) |
| the 2 new browser tests with `SA_FRONTEND_ROOT` = HEAD's prototypes | the fold test **fails** (no fold), as intended; the guard passes |
| `.stockai/Scripts/python.exe -m pytest -q -rfEs -p no:cacheprovider tests` (CI's command) | **5,007 passed, 12 skipped, 1 xfailed (the known limit), 0 failed** in 12 min 35 s (18 Oct, after the fix; 17 Oct before it: 5,006 passed) |
| `python scripts/ci/check_broad_except.py` | OK (152 grandfathered) |
| `PYTHONPATH="src;." .stockai/Scripts/python.exe analysis_data/pr003/yahoo_probe.py 2026-10-16 2026-10-19` (18 Oct, 09:03 IST; real Yahoo, read-only) | all 7 tickers answer; found the Sunday USD/INR bar (self-review); after the fix Monday's line reads "USD/INR 94.52 (-0.66%), as of Fri 16 Oct" |
| `python scripts/docs/build_kt_pdf.py`, then `check_kt_docs.py` | 45 pages, source `21aa4392…`; errors `[]` |

Raw outputs (ignored): `analysis_data/pr003/full_suite.txt`, `npm_frontend.txt`,
`mutants.log` (final bytes), `mutants_run1.log` (an earlier pass, mid-phase), `mutants_run2.log`
(17 Oct, before the weekend fix), `yahoo_probe_20261018_0905.txt`, `yahoo_probe_20261018_after_fix.txt`,
`calibrate.py`, `fe_base/` (HEAD's screens).

## Documentation

Each change below is written as current design.

- **KT** (`docs/TECHNICAL_DESIGN.md`):
  - section 10, the Delivery paragraphs: publish-date freshness and its floor;
    the story key and repeat rule with its known limit; same-day reruns; the
    `overnight_filter` counts; chat's and the daily review's rule; "Before the
    open" and its session, as-of and unavailable rules; no GIFT Nifty. The
    "Planned" pointer now names only PR-006 and PR-008.
  - section 11: "The brief opens with your stocks" names PR-008 only.
  - section 12's PR-003 row stays `Open` until the fresh review accepts it.

  The new links (`macro_news_fetcher.py`, `macro.py`) exist at the declared
  revision `b400747`.
- **PDF** rebuilt: 45 pages (was 44), source SHA-256 `21aa4392…`.
  `check_kt_docs` reports `[]`.
- **AGENTIC_DESIGN** section 12: the brief and chat read the feed too, and every
  reader judges recency by IST publish date.
- **CHAT_ARCHITECTURE**: the `get_macro_news` row.
- **RL_DESIGN** section 5: the daily review's macro window.
- **PRODUCT_MAP**: the brief row (line count 1,395) and the macro fetcher row.
- **Human testing guide**: new case **10-I** (HT-10), five consecutive briefs:
  - no item twice;
  - none published before the previous brief;
  - a reworded copy does not come back, but a follow-up with new facts does;
  - each figure checked against its public close on its as-of date;
  - "Unavailable:" with no number;
  - a closed Asian market absent;
  - `overnight_filter` read.

  HT-10's related-PI list names PR-003. Status line: "implemented, awaiting its
  fresh review; not deployed".
- No change needed:
  - ARCHITECTURE: it does not describe the brief's sections;
  - AUTOPILOT_GUIDE: no brief content;
  - `tests/TEST_DOCUMENTATION.md`: general, and lists no story files.

## Manifest and digest

- **Review input:** [PR-003-manifest.json](PR-003-manifest.json), 20 files. The SHA-256 of
  its LF bytes is **`78f2a9eb1e83ed11b51e71a88ec8c8fe33d18a2c5376e231f2c74dd028d074c7`**;
  `kt_manifest.py verify` gives 0 mismatches.
  - Code (8): `config.yaml`, `core/delivery/brief.py`, `core/portfolio/store.py`,
    `services/background/macro_news_cache.py`, `services/background/macro_news_fetcher.py`,
    `services/data/fetchers/macro.py`, `src/backend/shared/config/settings/base.py`,
    `src/frontend/prototypes/brief-view.jsx`.
  - Tests (5): `tests/unit/test_overnight_freshness_pr003.py` (new),
    `tests/test_macro_news_cache.py`, `tests/unit/test_delivery_brief.py`,
    `tests/unit/test_brief_earnings_watch_fix004.py`,
    `tests/frontend/no_invented_figures.test.mjs`.
  - Docs (7): the KT and its PDF, AGENTIC_DESIGN, CHAT_ARCHITECTURE, RL_DESIGN, PRODUCT_MAP,
    the testing guide.
  - Excluded: STATE, HANDOFF, this receipt (bookkeeping), and the owner's own line in
    `docs/README.md`.
  - Superseded inputs: `1dc2b97e…` / diff `b4279d46…` (17 Oct, before the weekend fix).
- **Diff digest:** **`8030c1dc4e6a10cd35853f28f6435f41d7e1e8920a30b259cf298fc4d781e6e4`**,
  111,286 bytes over 19 paths (every manifest path except the PDF), by
  `analysis_data/pr003/digest.py`. It checks that HEAD is `86a3a60`, runs
  `git diff --no-color --no-ext-diff HEAD -- PATH` for the 18 modified paths and
  `git diff --no-index /dev/null PATH` for the new test file, then sorts by path and
  concatenates.

## Self-review

Same-conversation self-review; it does not replace the fresh review.

- **Found and fixed:**
  - **A new figure suppressed as a repeat.** "Rupee falls to record low of 96.5
    against the dollar" followed by "…of 97.2…" shared 4 of 6 entities at 0.33
    new, and so read as a repeat: a material development hidden for up to 5
    briefs. Figures are now part of the key, and a candidate with a figure the
    shown story lacked is never a wording repeat. Two tests and two mutants
    cover it.
  - **An overflowing relative age.** "999999 years ago" raised `OverflowError`
    inside the Serper reader, whose broad except would drop the query's whole
    result list. It now returns `""`.
  - **A weekend quote taken as a session**, found by a real-data probe after
    the phase on 18 Oct. The owner asked whether the live-session question
    could be checked. Production logs cannot answer it: the PR-003 code is not
    deployed, and the code logs only failures. So `yahoo_probe.py` read Yahoo
    directly; this is public market data, and no production access was used.
    - All 7 tickers returned bars in the expected zones: New York, Tokyo, Hong
      Kong, London, and Chicago for `^TNX`.
    - `^TNX` is in percent.
    - A brief dated Fri 16 Oct would have shown the US figures as of Thu 15
      and the Asian ones, Brent and USD/INR as of Fri 16.
    - But `INR=X` had a bar dated **Sunday 18 Oct** (94.96 against Friday's
      94.52). Monday's brief would have read "USD/INR 94.96 (+0.46%), as of Sun
      18 Oct". Later Mondays would have measured the live rate against that
      weekend quote.

    Weekend-dated bars are now ignored. After the fix, the probe's Monday
    line reads "USD/INR 94.52 (-0.66%), as of Fri 16 Oct". One test and one
    mutant cover it. Raw probe outputs:
    `analysis_data/pr003/yahoo_probe_20261018_0905.txt` and
    `…_after_fix.txt`.
- **Traced:**
  - one adversarial week, from the feed files through the stored briefs, the
    email text and HTML and the API;
  - the UTC/IST boundary both ways;
  - the same-day rerun;
  - a backfill: no file after the brief's day is read, and nothing dated after
    it is shown;
  - a member and the owner: each store holds its own history; the market rows
    are market-wide and carry no user data.
- **Checked unaffected:**
  - the provenance parser: `get_for_daily_review` keeps its line format;
  - the weekly review, the pre-open check and the scheduler's macro jobs: no
    change;
  - `scripts/seed_fixture_ui.py`: builds no brief;
  - the `/delivery/run-brief` manual trigger: it goes through
    `run_morning_brief`.
- **Compatibility:**
  - briefs stored before the change render as before: no "Before the open",
    and their overnight items lack keys but still count as shown;
  - feed entries written before the change keep their old `published_date`
    (see L3).

## Limits and follow-ups

- **L1 (known limit, strict xfail).** A follow-up that changes one verb of an
  otherwise identical headline, with the same figures, reads as a repeat:
  "Govt withdraws bill to raise FDI cap in insurance to 100%" after "Govt
  approves bill …". Bag-of-words cannot see that change. It is bounded to 5
  briefs and to HIGH macro items, and the same story is usually reported again
  with new wording or figures. A fix would need meaning, not tokens: an LLM
  check, or PR-008's company-event feed. **Reviewer: rule on whether this is
  acceptable.**
- **L2.** A reworded copy that swaps an acronym for its full name
  ("Non-Resident Indians" for "NRIs") is not recognised and is shown once more.
  This errs toward showing.
- **L3 (transitional).** Feed files written before deploy carry the old
  dates: an unreadable date was stamped with the fetch day. For about two days
  the floor's window still reads such files. A stale article stamped with that
  day can pass the date test once, unless the repeat check matches a legacy
  brief's headline. After that, those files fall out of the window.
- **L4 (still inference for the live session).** "Nikkei/Hang Seng when open"
  relies on Yahoo returning that day's in-progress daily bar during the
  session. The 18 Oct probe ran on a Sunday, so this is still unobserved. If
  Yahoo does not return it, both markets read "closed" and are absent, which
  fails safe. The check is STATE's `PR-003-P1`, set at the owner's request for
  Monday 19 Oct: run `analysis_data/pr003/yahoo_probe.py` on a weekday between
  07:00 and 12:00 IST. Tokyo trades 05:30–12:00 IST and Hong Kong 07:00–13:30
  IST, lunch breaks included. Then the brief dated that day should show the
  market "as of" that day. Hong Kong is closed on Monday 19 Oct (the day after
  Chung Yeung), so Monday proves the Nikkei only, and Tuesday 20 Oct the Hang
  Seng. The first week's 10-I run also checks it. At 08:50 IST Tokyo is in its
  lunch break, so its level is the morning close.
- **L5.** Brent is the front-month future (`BZ=F`), dated in New York. The 18
  Oct probe confirmed `^TNX` is quoted in percent (5.10), so the ×10 guard
  stays a guard.
- **L6.** Chat adds no macro context while the server's file for today does
  not exist (before the 07:30 run). That is unchanged.
- **L7.** Chat's `get_portfolio_brief` tool cuts the rendered brief at 1,800
  characters. "Before the open" adds about 400 characters ahead of the
  overnight news, so on a full day the later sections (ideas, IPOs) reach chat
  sooner truncated. The tool's cut is unchanged.

## Rollout (at the owner's word)

- Commit and push only on the owner's word, in a job-free window (not 08:30–09:20
  or 16:25–17:15 IST). The brief needs no data migration and no new setting.
- First week: read `overnight_filter` in `GET /delivery/brief/latest` and the
  Sunday probe's "repeat_prev" count (expected near 0), and run guide case 10-I.
  Fewer overnight items on quiet days is correct.
- Rollback: revert the commit. `delivery.brief_markets: []` removes only the
  market section.

## Next

`next_task: PR-003`, its **fresh review** in a new conversation ("continue"),
then SA-050.
