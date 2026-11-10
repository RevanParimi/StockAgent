# FIX-021 — implementation receipt

**Story:** [FIX-021](../stories/FIX-021.md): a Google redirect link is not an article's identity.

**Phase:** implementation, 31 Oct 2026, about 08:48–09:30 IST. Session `stockagent-main-39`
[a379a3], a new conversation opened with "continue". The peers `-5d`, `-f2`, `-4f`, `-8a`, `-49`,
`-f0`, `-e0`, `-6e` and `-6b` were idle at the start and before the bookkeeping (ListAgents). This
phase includes a same-conversation self-review, which is not the fresh review.

**Baseline:** HEAD `48db226`. The working tree held FIX-019, accepted and uncommitted (reviewed
manifest `9f3de76f`, 8 files), its receipts and STATE/HANDOFF records, the 30 Oct deploy record,
and session `-6b`'s FIX-021 card. All are kept.

**Status after this phase:** `review_required`. FIX-021 itself is not committed, pushed, deployed
or configured. No production state was read, no model or Serper endpoint was called and no message
was sent. Every test fakes Serper at `requests.post`.

**After the phase, the same conversation** (about 09:35 IST, at the owner's "we need to commit
and push unless it requires review"): FIX-019, already accepted, was committed (`4aa4c83` code,
then its docs commit), and FIX-021's review input was re-recorded on that base before any review
began (section "Review input"). FIX-021 waits for its fresh review.

## In one example

- **Before:** on the 08:15 run "Maruti Suzuki wins export order" is Serper's result 2, with its
  own link, and is stored as `news:<hash of that link>`. On the 18:30 run it is result 4, which
  Serper now gives as `https://www.google.com/goto?...`. That is a new id, so the feed pays a
  classifier call and stores the article a second time.
- **Now:** the fetcher reads the 18:30 link as no link. The feed drops the article (it has no
  address to cite) and counts it in `news_redirect_links`. The article stays stored once, under its
  own address. In the other order (result 4 first, result 2 later) it is stored once, on the later
  run.

## What changed

- **`services/data/fetchers/news.py`:**
  - `is_google_link(link)`: true when the link's host is google.com or a subdomain of it. Only
    the host is read (`urlsplit(...).hostname`, so case, port, a trailing dot and user info are
    handled, and a link without a scheme is read as `//host/...`).
  - `_serper_row(item, *fields)`: both Serper parsers (`search_serper` for `/search`,
    `search_serper_news_status` for `/news`) build their rows with it. A Google link becomes "" and
    the row carries `redirect: True`; the redirect itself is not kept. Rows are otherwise
    unchanged (same keys, same order).
- **`core/events/feed.py`:** the run record has two new counts: `news_results` (articles Serper
  returned this run) and `news_redirect_links` (those with a redirect link, dropped). The run's
  summary log line shows both. `news_items` already drops a row without a URL, so no feed logic
  changed. Module docstring step 2 says so.
- **`core/events/sources.py`:** docstring only: redirect links arrive without a URL.
- **`services/background/macro_news_fetcher.py`:** `_serper_news` leaves out a headline whose
  link is a redirect and logs how many it left out per query (F21-D3).
- **`services/api/routes/ui_data.py`:**
  - `_rrf_fuse` (chat's news search): a result without a link joins the result of the same title
    (case and spacing ignored) and the merged entry keeps the result that has the link. Two
    results with one title and different links stay two, as before (F21-D4).
  - Chat's news-search and macro-fallback lines print ` | <link>` only when there is a link, so a
    link-less result shows "Source: Mint", not "Source: Mint | ".
- **`tests/unit/test_serper_redirect_fix021.py` (new, 14 tests):** below.
- **Docs:** KT section 4 event-feed step 5 (the rule and the two counts), the Delivery paragraph
  (macro headlines), the IPO paragraph (GMP sources) and section 12's FIX-021 row (`Open`); the
  PDF regenerated; testing guide case 02-N (new) and HT-02's related-PI line. CODEBASE.md has no
  row for the touched code and is unchanged.

## Callers checked (the card: "do not assume it")

| Caller | What "" does there | Checked by |
|---|---|---|
| Event feed, `news_items` | the row is dropped: no id, no classifier call | invariant test (both orders) |
| IPO GMP, `_numbers_by_domain` | `urlparse("").netloc` is "", skipped | one real site + 3 redirects → `None`; 2 real sites + 1 redirect → 125.0 from 2 sources |
| Chat news search, `_rrf_fuse` and its lines | before this story a link-less copy was keyed by title and the linked copy by link, so it listed twice; now merged | both variant orders; redirect-only result shows no link and no stray bar |
| Chat macro fallback (live `/news`) | the line drops ` \| ` | fallback test |
| Macro headlines (own `/news` call) | left out before review | fetcher test; KT Delivery |
| Analyst news context (`fetch_news_result`), the daily review's `get_news_context`, macro and sector `/search` callers (`macro.py`, automobile settings, `base_orchestrator`) | read title, snippet, date and source only | code inspection (grep of every `link` read) |

No caller turns "" into a crash, an `about:blank` link or a key shared by every link-less article:
the feed drops it, GMP skips it, chat keys a link-less result by its own title (a result with
neither link nor title is skipped, as before), and macro headlines never reach the URL-keyed cache.

## Decisions (implementer's, recorded for the review)

- **F21-D1, google.com and its subdomains, by host.** Serper's notice names `google.com/goto`, and
  the owner's probe counted hosts the same way. A country domain (`google.co.in`) is not matched:
  no such link has been seen. A Google page that is a real article (for example on
  `cloud.google.com`) is also dropped; for company news that loss is small, and the card asks for
  the whole host.
- **F21-D2, the row says `redirect: True`.** The parser blanks the link, so without a marker the
  feed could not tell a redirect from a result that never had a link. The marker carries no URL.
- **F21-D3, macro headlines are left out, not kept without a link.** `fetch_and_review` already
  drops a URL-less entry after the reviewer call (`if url and url not in seen_urls`), and the cache
  tells entries apart by URL. Leaving it out before the reviewer gives the same stored result and
  keeps it out of the reviewer's 15 slots. Expected loss: up to 2 of each query's 5 results.
- **F21-D4, chat merges by title only when one side has no link.** The card expected chat's title
  fallback to be enough. It is not: the linked copy is keyed by its link and the redirect copy by
  its title, so they never met (measured: the `head_ui_data` mutant fails the chat test). Merging
  every same-title pair would also merge two outlets carrying one wire story, which the old code
  kept apart; that change is not asked for.
- **F21-D5, `news_results` beside `news_redirect_links`.** The card's revisit trigger (redirects
  above a quarter of the feed's articles over five trading days) cannot be computed from the old
  record, which counted only the articles kept. Guide case 02-N reads the two counts.
- **F21-D6, no Serper `/resolve`,** per the card.
- **F21-D7, FIX-019's reviewed bytes are kept.** The KT, the guide and the PDF sat in FIX-019's
  uncommitted reviewed manifest. Before any edit, all 8 of its files were copied to
  `analysis_data/fix021/start/` (ignored); `verify_fix019_snapshot.py` shows each copy's blob id
  equals the manifest's (0 mismatches, manifest `9f3de76f` unchanged). FIX-019's code commit
  `4aa4c83` was built from that copy (`kt_manifest.py verify --rev HEAD`: 0 mismatches), and its
  docs commit applied its review's commit-time edits to those bytes. FIX-021's KT and guide lines
  were then put back on top, line for line (the added and removed lines compare equal before and
  after), and the PDF rebuilt.

## Production data (unchanged)

Rows already stored under a redirect link stay: 5 news events fetched on 30 Oct (the owner's
probe), plus any from the runs between that probe and the deploy. No attempt is made to rewrite
them; removing them needs the owner's word. After the deploy, such an article can appear once more,
under its own address, when it next ranks in the top 3: a one-time duplicate per stored redirect.
Macro headlines already cached under a redirect stay in their day's file; chat's macro tool reads
only today's file and the brief a day or two back, so they stop showing within about two days.

## Tests

- **Story file** `tests/unit/test_serper_redirect_fix021.py`, 14 passed. Serper's responses are
  written out by hand; no test calls `is_google_link` or builds a row with the code's helper.
  - The idempotency invariant, both orders: morning (export order at rank 2 with its link, a plant
    visit only as a redirect, one article with no link at all) and evening (export order at rank 4
    as a redirect). Exactly 4 news events, each under its own link; the export order sent to the
    model once; the plant visit and the link-less article never sent; no stored `source_url` on
    google.com; per-run `(news_results, news_redirect_links)` = (5, 1) and (4, 1).
  - Parsers, `/search` and `/news`: 8 redirect shapes (www, bare host, upper case, trailing dot and
    port, `news.google.com`, `//host`, no scheme, padded) become "" with `redirect`; 7 publisher
    links containing "google" (path, query, `googleblog.example.com`, `notgoogle.com`,
    `google.com.evil.example`, `google.com@evil.example`, a Moneycontrol path) are unchanged
    without it. A missing or empty link is left as it was.
  - IPO, chat (both orders; redirect-only; same title with two links stays two), macro headlines,
    chat macro fallback, and a run without a search starts both counts at 0.
- **Mutants** (`analysis_data/fix021/mutants.py`, in place, restored after each; sha256 of the 5
  code files checked after the run): **20 of 20 caught**. HEAD's own `news.py`,
  `macro_news_fetcher.py`, `feed.py` and `ui_data.py` each fail the story file; so do a host
  suffix without the dot, a substring test, no scheme-less parse, no trailing-dot strip, the bare
  host missed, www only, no `redirect` flag, `/search` not blanked, macro blanking instead of
  leaving out, the feed counting nothing, the feed counting link-less rows (survived the first
  run; the morning response then gained a link-less article), chat merging every same-title pair,
  keeping the first (link-less) copy, comparing raw titles, and either stray ` | `.
- **Neighbouring files** (before the story file existed): the PR-006 feed tests, chat (RRF and
  tools), IPO GMP, news recency and window, PR-003 freshness, data-health contract, FIX-002
  resolution, the fetcher integration file, chat brief scope and macro fetcher: 538 passed, 1
  xfailed.
- **Full suite:** 5,904 passed / 12 skipped / 1 xfailed / 0 failed (11m48s, 09:06–09:18 IST; the
  previous 5,890 plus this story's 14), on the final code and test bytes. No tracked runtime file
  changed (`git status`). Output: `analysis_data/fix021/full_suite.txt`.
- **Checks:** `check_broad_except` OK (151 grandfathered); `check_kt_docs` errors `[]` after this
  phase's HANDOFF edit (before it, one error: a broken link in HANDOFF's planned FIX-021 text,
  which that edit replaces); PDF 61 pages. On the re-recorded base: `check_kt_docs` errors `[]`,
  header `4aa4c83`, PDF 61 pages, source `ae2e1e79`. No test reads the KT or the guide, so the
  full suite above still covers the unchanged code and test bytes.

## Review input

- **Manifest:** [FIX-021-manifest.json](FIX-021-manifest.json)
  `086378d89302411b32969caca05d7000d4d5f05e9a7f5d93b46b2dace2ae02b8` (9 files: the 5 code files,
  the story file, the KT, the guide and the PDF), `kt_manifest.py verify` 0 mismatches.
- **Diff:** `d5c07e7fe2867429eeb875a705395832abbb89e868726478ba514ccf779d7508` (41,345 B, 8 paths),
  from `analysis_data/fix021/digest.py`: every path against HEAD, FIX-019's docs commit on
  `4aa4c83`; the story file against `/dev/null`.
- **Superseded before any review:** `8ab98d70` / `d0ae40df` (09:30 IST), whose KT, guide and PDF
  sat on FIX-019's then-uncommitted reviewed bytes. Code and test bytes are the same in both.

## Commit (after the fresh review accepts it, only at the owner's word)

The code and test files exactly as reviewed, then a docs commit (KT header and section 12 Done,
guide 02-N status, PDF). A push deploys it: in a job-free window, never on the 1st before the
09:00 monthly forecast.

## For the fresh review (the card's hard-review questions)

- **Is the redirect test exact?** Host only, google.com or `*.google.com`; 8 redirect shapes and 7
  near-miss publisher links are pinned, and 6 rule mutants are caught. On every Serper path: both
  parsers in `news.py` and the macro fetcher's own `/news` call, which are all the places a Serper
  link is read (grep of `link` reads, table above).
- **Does any caller turn "" into something worse?** No (table above). A pre-change chat line
  showed "Source: X | " for a link-less result; now it shows no bar.
- **Is the invariant test independent of the code's helper?** Yes: the two responses are literal
  JSON behind a fake `requests.post`; the real parser, feed, store and a fake model run.
- **Are the rows already stored under redirect links stated, with no attempt to rewrite them?**
  Yes, above.

## Production verification (separate, after the deploy)

Re-run the owner's probe (`analysis_data/serper_goto_2026-10-31/events_link_probe.py`, read-only,
counts only): no news event fetched after the deploy carries a google.com link. Each
`runs.jsonl` line shows `news_results` and `news_redirect_links`; over five trading days the
second stays at or below a quarter of the first (guide 02-N), or `/resolve` is revisited.
