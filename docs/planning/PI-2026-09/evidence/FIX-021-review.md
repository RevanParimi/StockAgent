# FIX-021 review receipt — a Google redirect link is not an article's identity

## Fresh review: ACCEPTED (2026-10-31)

**Phase:** fresh-session review, a new conversation opened with "continue" (31 Oct, about
09:37–09:55 IST, session `stockagent-main-b4` [3d6058]). FIX-021 was implemented in
`stockagent-main-39` [a379a3]. This conversation did not read that chat or any earlier one. The
peers `-5d`, `-f2`, `-4f`, `-8a`, `-49`, `-f0`, `-39`, `-e0`, `-6e` and `-6b` were idle at the
start and before the bookkeeping (ListAgents).

**Verdict: ACCEPTED** for the reviewed revision below.

- Every acceptance criterion on the card holds. The card's four hard-review questions are
  answered below from my own cases, written without the code's helpers. The cases follow a stored
  news event into the exit's evidence, check the host rule against a separately written parser
  and check chat's fusion with a counting invariant over random variant lists.
- No finding is critical, high or medium. There are two low findings:
  - L1, docs: the chat architecture page does not describe the new merge. Fixed by a commit-time
    edit with exact text.
  - T1, a test gap: the story file does not pin a third chat variant. The shipped code is right
    and my RV3 pins it. Routed to PR-012's card.
- Two notes are informational. I1: the host rule and the owner's probe both match google.com
  only. I2: the card's `/resolve` trigger is likely to fire.

**Nothing was committed, pushed, deployed or configured.** No production state was read, no
Serper endpoint or model was called and no message was sent. Every test fakes Serper at
`requests.post`. Tracked files changed by this review: STATE, HANDOFF, this receipt and PR-012's
card (a routed-input note). The reviewer's scripts and outputs are in the ignored
`analysis_data/fix021_review/`.

### In one example (RV1: four runs, a recall, the exit's watch list)

MARUTI is held. Serper's company search returns five articles a run, and only ranks 1–3 come
with their own address. "Maruti Suzuki recalls 12,000 cars over airbag fault" is classified
negative and high.

| Run | The recall's rank | Its link | Reviewed code | HEAD |
|---|---:|---|---|---|
| 22 Oct 08:15 | 5 | `google.com/goto?url=…0014` | dropped, counted | sent to the model as a new article |
| 22 Oct 18:30 | 4 | `google.com/goto?url=…0023` | dropped, counted | sent again (a new id) |
| 23 Oct 08:15 | 1 | its own address | stored once, published 22 Oct | sent a third time |
| 23 Oct 18:30 | 4 | `google.com/goto?url=…0043` | dropped, counted | sent a fourth time |

- **Reviewed code:** the model sees the recall once, and one event is stored under its own
  address. On 23 Oct the holding's evidence lists it once on the watch list, and not among the
  selling events (a news event cannot sell). Each run line in `runs.jsonl` reads
  `news_results` 5, `news_redirect_links` 2. There is one `/news` request a run and no other
  Serper path.
- **HEAD** (`RV_HEAD=1` compiles HEAD's parsers, `feed._one_symbol`, `_rrf_fuse` and the macro
  fetcher's `_serper_news` into the live modules): the model sees the recall 4 times.

### Review input verified

- **Manifest:** [FIX-021-manifest.json](FIX-021-manifest.json), 9 files, review input
  `086378d89302411b32969caca05d7000d4d5f05e9a7f5d93b46b2dace2ae02b8`. Every file's working-tree
  blob equals the manifest's, at the start and at the end.
- **Diff:** `d5c07e7fe2867429eeb875a705395832abbb89e868726478ba514ccf779d7508`, 41,345 bytes,
  8 paths, against HEAD `0fdaee6` (FIX-019's docs commit on `4aa4c83`). Nothing is staged. It
  was rebuilt at the start and at the end by `analysis_data/fix021_review/rv_digest.py`, the
  implementer's recipe writing into the review folder. Both match the receipt.
- **No drift:** no reviewed path changed during the review.

### Contract checked

| Contract | Result | How it was checked |
|---|---|---|
| A Google link is no link, at every Serper parse | **Holds** | Three places call Serper (grep of `serper.dev`): `search_serper`, `search_serper_news_status` and the macro fetcher's `_serper_news`. All three apply the rule. RV2 compares `is_google_link` with my own parser over 1,200 link shapes: 20 hosts × 5 prefixes × 6 suffixes, padded and not. They agree on every one. The 9 Google hosts include `user:pw@www.google.com` and `www.google.com.:8443`. The 11 others include `google.com@evil.example`, `google.com.evil.example`, `notgoogle.com` and `google.co.in`. A host that does not parse is not a redirect. Both parsers blank and mark exactly the oracle's rows and leave the others' links byte-equal. |
| One article, ranked high in one run and low in another, is one event and one classifier item | **Holds** | The story's two-run test in both orders, and RV1's four runs over two days. Expected values are by hand. |
| No caller turns "" into something worse | **Holds** | Every non-test read of a result's `link` (grep): the feed (`normalize_url` → None → dropped), IPO GMP (empty domain skipped), chat's two lines (no ` \| `), chat's fusion (title key), and chat's horoscope filter (title still read). The analyst context, the daily review's news context, macro and sector `/search` callers and ticker resolution read title, snippet and date only. RV4: the analyst text still carries a redirected result's title and snippet. The `redirect` key is never persisted or shown. |
| Chat lists one article once | **Holds** | RV3: 400 seeded trials of 1–3 variant lists over 8 articles in 6 titles (so two outlets share a title), random redirects below rank 3 and random case and spacing. Each link appears exactly once. The count is distinct links plus titles seen only without a link. No link-less entry has a title some variant showed with a link. On HEAD it fails (9 listed where 7 are expected). |
| Counted, not silent | **Holds** | RV1 reads `runs.jsonl` back. The summary log line carries both counts (story test). Only the feed and its tests read the record's keys. |
| No production data change, no `/resolve`, no new Serper call | **Holds** | The receipt states the 5 rows of 30 Oct and later ones stay. The diff has no data step. RV1 records one `/news` request a run. |
| KT, guide and PDF | **Hold** | KT section 4 step 5, Delivery, IPO and section 12 match the code. Guide 02-N is new. `check_kt_docs` gives errors `[]`, and the PDF footer digest `ae2e1e79` is the reviewed KT's. The chat page is L1. |

### The card's hard-review questions

- **Is the redirect test exact?** Yes. It reads the host only, google.com or any subdomain
  (RV2, against an independent parser). A publisher URL that merely contains "google" in its
  path, query, fragment, user info or a longer host keeps its link. It applies on every Serper
  path, macro headlines included. `google.co.in` is not matched (I1).
- **Does any caller turn "" into something worse?** No (table above). The empty string never
  becomes a shared key: the feed drops the row, chat keys it by its own title (skipped with no
  title, as before), and the macro fetcher leaves it out before the cache.
- **Is the invariant test independent of the code's helper?** Yes. The story's responses are
  literal JSON behind a fake `requests.post`, and so are mine. My parser oracle and chat invariant
  are written without the code's functions. On HEAD's code, 4 of my 6 cases fail; the 2 that pass
  check no regression (the oracle against the worktree helper, and the analyst text).
- **Are the stored redirect rows stated, with no rewrite?** Yes: 5 from 30 Oct plus any until
  the deploy, each able to recur once under its own address. No data step exists.

### Rulings on the implementer's decisions

- **F21-D1, host rule, google.com and subdomains:** upheld. Serper's notice names google.com,
  and so did the owner's probe. I1 records what neither would see.
- **F21-D2, the `redirect` marker:** upheld. It is the only way to count without keeping the
  redirect, and no consumer persists it.
- **F21-D3, macro headlines left out before the reviewer call:** upheld. `fetch_and_review` and
  the cache (`add_entries`, keyed by URL) would drop a URL-less entry anyway. Extra refinement
  calls are bounded by `_MAX_ITERATIONS`.
- **F21-D4, chat merges by title only when one side has no link:** upheld. The card's premise
  (title fallback alone) was wrong, and the implementer measured that. RV3 covers the three-list
  case the story file does not (T1).
- **F21-D5, `news_results` beside `news_redirect_links`:** upheld. Without it the card's trigger
  cannot be computed.
- **F21-D6, no `/resolve`:** upheld per the card. I2 says when it is likely to be revisited.
- **F21-D7, FIX-019's reviewed bytes kept:** moot after FIX-019's commit. The input was
  re-recorded on that base before this review, and I verified it.

### Findings

| ID | Severity | Location | Evidence | Disposition |
|---|---|---|---|---|
| L1 | low (docs, confirmed) | `docs/CHAT_ARCHITECTURE.md:122-124` ("News fusion") | The page says `search_market_news` merges its variants by reciprocal rank fusion. FIX-021 changes that merge: a link-less result joins the same-title result, and a result seen only without a link is shown with its source and no link. The page is a living design doc for chat's tools. It is not in the reviewed manifest, and the receipt does not mention it. Behaviour is unaffected. | **Commit-time edit** in the docs commit (exact text below). |
| T1 | low (test gap, confirmed) | `tests/unit/test_serper_redirect_fix021.py` (chat tests use 2 variants) | Reviewer mutant `rrf_forget_merged_link` removes `key_of_link.setdefault(link, key)` (`ui_data.py:2601`). Then an article seen first without a link, then with it, then with it again (3 variants, or a re-fuse with `more`) is listed twice. The story file passes the mutant (14 passed). RV3 fails it. The shipped code is right. | Routed to [PR-012](../stories/PR-012.md) (routed-input note): add a 3-list case to the story file when chat's news search is next touched. RV3 holds the reproduction. |
| I1 | info (inference) | `services/data/fetchers/news.py` `is_google_link`; `analysis_data/serper_goto_2026-10-31/events_link_probe.py:43` | Both match google.com and its subdomains only. The feed searches with `gl=in`. If Serper ever gave `google.co.in/goto` links, neither the rule nor the probe would see them. Serper's notice names google.com/goto. | None in code. After the deploy, the production check also counts hosts on any other Google domain (STATE, below). |
| I2 | info (inference from code + Serper's notice) | `config.yaml` `events.news_articles_per_query: 5` | Serper resolves only ranks 1–3. A feed search that returns 5 articles therefore drops 2 (40%), and only searches returning 3 or fewer drop none. The card's revisit trigger (more than a quarter over five trading days) is likely to fire. Before 30 Oct, ranks 4–5 were stored. Now they are stored only if they later rank in the top 3. | None now. Guide 02-N's five-day read decides. Expect `/resolve` to come back to the owner. |

### Commands, environment and results

Windows 11, the project's `.stockai` virtual environment (Python 3.13), with `tests/hermetic.py`
active for every test: no network, no `.env` and no checkout data. The reviewer's folder has
its own `conftest.py` importing the same hooks. From the repository root:

- `.stockai/Scripts/python.exe analysis_data/fix021_review/rv_digest.py`: manifest `086378d8…`,
  0 blob mismatches, nothing staged, diff `d5c07e7f…`, 41,345 bytes, 8 paths, HEAD `0fdaee6`.
  Run at the start and at the end.
- `.stockai/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/unit/test_serper_redirect_fix021.py tests/unit/test_company_events_pr006.py tests/unit/intelligence/chat/test_rrf_fusion.py tests/test_macro_news_fetcher.py tests/test_rss_feed.py tests/unit/test_overnight_freshness_pr003.py tests/unit/test_ipo_gmp.py tests/unit/test_news_search_recency.py tests/unit/test_news_context_window.py`:
  **271 passed, 1 xfailed** (18.7 s). The story file alone: 14 passed.
- `.stockai/Scripts/python.exe -m pytest -q -p no:cacheprovider analysis_data/fix021_review/test_rv_fix021.py`:
  **6 passed** (RV1 four runs into the exit's evidence; RV2 the oracle, and both parsers;
  RV3 chat; RV4 the analyst text). With `RV_HEAD=1`: **4 failed, 2 passed**. RV1 sends the recall
  4 times, both parsers keep `https://google.com`, and RV3 lists 9 where 7 are expected. The
  oracle and RV4 pass, as no-regression checks should.
- Reviewer mutants (`-p rv_mutplug`, in memory, no file edited), `analysis_data/fix021_review/rv_mutants.txt`:
  `rrf_forget_merged_link` passes the story file (T1) and is caught by RV3.
  `rrf_no_title_join` is caught by both. The implementer's 20 mutants were not re-run. Their list
  was read against the code, and my cases cover the rule, the feed and chat independently.
- `.stockai/Scripts/python.exe -m pytest -q -rs -x -p no:cacheprovider` (all of `tests`):
  **5,904 passed, 12 skipped, 1 xfailed, 0 failed** (13m01s, 09:39–09:52 IST). `git status`
  afterwards listed only this review's files and the reviewed input: no runtime data changed.
- `scripts/ci/check_broad_except.py`: OK (151 grandfathered). `scripts/docs/check_kt_docs.py`:
  errors `[]`, PDF 61 pages, source digest `ae2e1e79…` = the reviewed KT.

**Not exercised:** production and Serper itself. The real shape of a goto link and the
`google.co.in` question (I1) were not observed. There was no browser and no model call.

### Acceptance checklist

- Idempotency invariant, hermetic, independent, both orders → **met** (story test; RV1 over four
  runs).
- Parser tests for `/search` and `/news`: www and bare host blanked; publisher links containing
  "google" unchanged → **met** (story; RV2 with 1,200 shapes).
- IPO: a google.com result never counts; one real site plus redirects is fewer than
  `ipo.gmp_min_sources` → **met** (story's two GMP tests).
- Chat: one article with its link in one variant and a redirect in another appears once →
  **met** (story, both orders; RV3. T1 is a test gap only).
- The macro headline never shows a redirect → **met** (story fetcher test; chat's macro fallback
  test).
- `news_redirect_links` counts the dropped articles → **met** (story; RV1 through `runs.jsonl`).
- KT section 4 step 5, section 12, the PDF and the guide case → **met** (02-N; L1 is the chat
  page).
- The story file, the changed files and the full suite pass → **met** (14; 271 + 1 xfailed;
  full suite above).

**Production verification:** `pending_deployment`. The commit and the push each need the
owner's word, in a job-free window (safest 00:10–06:20 IST), and never on the 1st before the 09:00
monthly forecast. 1 November is a Sunday, but the monthly forecast still runs at 09:00. After the
deploy:

- re-run the owner's probe: no news event fetched after the deploy has a `source_url` on
  google.com, and none is on any other Google domain such as `google.co.in` (I1). For that, also
  count hosts whose labels include `google` other than google.com;
- guide 02-N's five trading days: `news_results` and `news_redirect_links` on every run line,
  and their ratio against the card's quarter (I2).

**Commit-time edits** (with the commit, at the owner's word; none is made by this review):

- **Code commit:** exactly the 9 reviewed files. `kt_manifest.py verify FIX-021-manifest.json
  --rev HEAD` must give 0 mismatches (`086378d8`).
- **Docs commit**, holding:
  - the KT header (`Code inspected` = that code commit; edition = the commit's date);
  - KT section 1's production paragraph, carried from the FIX-019 deploy: replace "Production
    runs `53e3f0e` (PR-009, FIX-016 and FIX-018), deployed at about 09:20 IST on 30 October 2026
    (the deployment list showed it SUCCESS and `/health` answered 200). The inspected code adds
    FIX-019's instrument-registry records (section 4)." with "Production runs `4aa4c83`
    (FIX-019), deployed at about 09:31 IST on 31 October 2026 (the deployment list showed it
    SUCCESS and `/health` answered 200). The inspected code adds FIX-021's reading of Google
    redirect links (section 4)." The sentences after it stay;
  - KT section 12's FIX-021 row: `Open` → `Done`;
  - guide 02-N status: "FIX-021: implemented 2026-10-31; fresh review pending." → "FIX-021:
    accepted 2026-10-31, committed as `<code commit>`; production verification pending.";
  - **L1**, `docs/CHAT_ARCHITECTURE.md` "News fusion" bullet, after "with a filter for horoscope
    results." add: "Serper gives a result's own link only in a search's top 3, and a link below
    that is a Google redirect, which the fetcher reads as no link. A result without a link joins
    the result of the same title, and the merged result keeps the link. A result seen only
    without one is shown with its source and no link.";
  - the PDF, rebuilt; `check_kt_docs` errors `[]`;
  - this receipt, STATE, HANDOFF and PR-012's routed note; with them the uncommitted FIX-019
    push and deploy record.

**Next:** FIX-021 is `done`, with production `pending_deployment`. `active_task` is null.
`next_task` is **SA-048** (ready, no dependency), its implementation in a new conversation.
