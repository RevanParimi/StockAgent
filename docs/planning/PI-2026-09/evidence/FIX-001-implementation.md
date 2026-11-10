# FIX-001 implementation receipt — use a one-bar price download instead of discarding it

- **Story:** [FIX-001](../stories/FIX-001.md). It is a user-requested task: the owner said "The small
  price-lookup fix - go ahead as well" (1 Oct 2026, about 00:36 IST).
- **Source:** the diagnosis of the 30 Sep ops alert "audit_nightly completed 25/27", recorded as a
  note on the [SA-040](../stories/SA-040.md) card.
- **Context:** implemented on 1 Oct, about 00:40–01:00 IST, in the **same conversation** as three
  other phases: SA-009 change 1's fresh review, its commit and push, and the SA-008/SA-009
  production rollout. That was at the owner's request, and it is a recorded
  one-phase-per-conversation deviation, as for SA-007 change 1 and SA-009 change 1. A
  same-conversation self-review was done. It is not the fresh review, which is a new
  conversation. STATE: `review_required`.
- **Baseline:** `290b3f7` (the clean tree after the rollout records were committed).
- **Nothing** was pushed, deployed or configured in this phase.

## What it does, in one example

SWASTIKAIN listed on 30 Sep, and its IPO verdict's listing-day row matured that day. At 23:45 the
nightly audit asked `close_on("SWASTIKAIN", 30 Sep)` for the exit close.

- **Before:** yfinance's 7-day download held one bar, the listing day's. `df["Close"].squeeze()`
  turned that one-bar column into a `numpy.float64`, `.dropna()` raised, and the code logged
  "yf.download() failed". The `.BO` fallback failed the same way, and the 1-year history said
  "possibly delisted". The NSE cross-check found nothing, so the row was `skipped_unpriceable`.
  ELEVATE and ARMEE went the same way until NSE supplied their closes.
- **After:** the one bar is read like any other, so `close_on` returns the listing-day close,
  cross-checked against NSE as usual. The listing-day row is the only IPO row that can carry a
  right/wrong mark, and it is exactly the one-bar case.

## The change

- **`core/intelligence/rl/workflows/daily_review.py`,** in `_fetch_session_close._extract`: take
  `df["Close"]` without `squeeze()`. The next lines were already there: the first column when the
  columns have two levels, then `dropna()`.
  - With two or more bars, this is the same path as before. `squeeze()` on an N-by-1 column gave
    the same Series that `iloc[:, 0]` gives now.
  - `_fetch_actual_close`, `close_on`, `session_close` and the audit's `_default_price_fn` all use
    this function.
- **`services/data/fetchers/close_verifier.py`,** in `_fetch_yfinance_close`: the same change.
  - It deliberately adds no `dropna()`: a NaN last row stays a failure (the RISHABH rule in
    `_sanitize`). The previous day's close is not passed off as the latest.
- **Not changed:** the indicator fetcher's `squeeze()` calls. They work on year-long histories, and
  one bar gives no indicators either way.

## Measured evidence

- **Production, read-only.** This is from the Railway log of deploy `14d13162`, read at the owner's
  request on 30 Sep at about 23:48 IST, and filtered.
  - The 30 Sep audit gave `ipo: graded 2, skipped_unpriceable 2`. Every other lane had 0 skipped.
  - There were 6 lines "yf.download() failed for <SYM>: 'numpy.float64' object has no attribute
    'dropna'", for ELEVATE, ARMEE, SWASTIKAIN ×2 and ADROITIND ×2. The ×2 is `close_on`'s one
    retry.
  - "Could not fetch actual close … (source=none)" appeared for SWASTIKAIN and ADROITIND.
  - The same warning appears once on 29 Sep, under deploy `f2e23722`, before SA-008.
  - The line dates from `513b358` (1 May).
- **Local reproduction.** pandas gives a `float64` for a one-row `(Price, Ticker)` frame's `Close`
  after `squeeze()`, and `.dropna()` then raises this exact message. With two rows it gives a
  Series.

## Acceptance criteria

| Criterion | Result |
|---|---|
| A one-bar download gives the session's close, dated that session | Met (tests 1–3) |
| A lone earlier bar is carried forward visibly | Met (test 4: dated Thursday, `fresh_for(FRI)` false) |
| A lone NaN bar is no close | Met (test 5) |
| The BSE fallback reads a one-bar frame | Met (test 6, which also shows the `.NS` → `.BO` order) |
| `close_on` prices a listing day without a retry | Met (test 8) |
| `close_verifier` reads a one-bar history; a NaN last row stays a failure | Met (tests 9, 10) |
| Two or more bars behave as before | Met (test 7, the 14 SA-003 tests, the full suite) |
| Tests fail for the original defect | Met (M1: 6 of 10 fail) |
| KT §4 and §8 and guide 05-G describe it | Met |

## Decisions for the reviewer

- **D1. Read a one-bar frame like any other.** The SA-003 test comment called the discard
  "pre-existing, and conservative". It is not conservative.
  - On a listing day the one bar is the session's own close.
  - When the lone bar is older, the result is dated that bar's session, and SA-003's freshness
    marks it stale.
  - The NSE cross-check still applies.
- **D2. `close_verifier` keeps "NaN last row = failure".** Adding `dropna()` there would return
  yesterday's close as the latest. Mutation M3 shows a test catches that.
- **D3. The indicator fetcher is out of scope** (see "The change").
- **D4. The SA-003 test comment was updated** to point to the new tests. No SA-003 test changed.

## Tests: commands, environment, results

Environment: Windows 11, `.stockai` venv (Python 3.13), repository root.

- **New: `tests/unit/test_one_bar_close_fix001.py`,** 10 tests.
  - The expected closes and dates are the fixture's bars, written by hand.
  - The frames use yfinance's `(Price, Ticker)` shape, plus one flat frame.
  - Nothing reaches a network: yfinance, the history fetcher and the NSE session are patched, and
    `tests/hermetic.py` guards the rest.
- **Focused:** `python -m pytest -q -p no:cacheprovider tests/unit/test_one_bar_close_fix001.py
  tests/unit/test_session_close_sa003.py` gave **24 passed**.
- **Mutations** (`mutate_fix001.py` in the session scratchpad; each source is restored and checked
  by SHA-256): **3 of 4 caught.**
  - M1, `squeeze()` restored in `daily_review` (the original defect): 6 failing;
  - M2, `squeeze()` restored in `close_verifier`: 1 failing;
  - M3, `dropna()` added in `close_verifier`: 1 failing;
  - M4 survived: `dropna()` removed in `daily_review`. It is equivalent for these cases, because
    `cross_check_close` also passes the yfinance close through `_sanitize`, so a NaN is rejected
    there too. That line is unchanged by FIX-001.
- **Full suite:** `python -m pytest tests -q -p no:cacheprovider` gave **4036 passed, 12 skipped,
  0 failed** (10 min 27 s; 4026 + 10). `data/`, `logs/` and `outputs/` were unchanged: 800 files,
  the same digest before and after.
- **Guards:** `scripts/ci/check_broad_except.py` OK (154 grandfathered). `check_kt_docs` errors
  `[]` (417 links, PDF 33 pages, source `a8511517…`).

## Documentation

- **KT §4** (close freshness): a one-bar download is read like any other.
- **KT §8** (IPO lane): the first production IPO rows were graded on 29 and 30 Sep, and two
  listing-day rows were skipped by this defect. It replaces "No production IPO row has been
  graded yet".
- **Guide 05-G:** the listing-day row has its exit close, and the audit log shows no
  `skipped_unpriceable` for it.
- **The PDF** was rebuilt.
- **The landing commit's KT bump:** the header declares `9c626a5`, and `daily_review.py` changes
  after it. So a KT bump follows the commit, as for SA-009.

## Rollout

- After the fresh review, commit and push in a job-free window. There are no configuration
  changes.
- **Production check:** the first nightly audit after the deploy shows no `'numpy.float64' object
  has no attribute 'dropna'` line.
  - The two skipped rows (SWASTIKAIN, ADROITIND, dated 30 Sep) are retried each night. Once
    deployed, they are graded if Yahoo or NSE has the listing-day bar.
  - An issue listed only on a board neither source carries stays unpriceable. That is not this
    defect.
- **Until then**, the "audit_nightly completed N/M" warning can repeat each night.

## Open limitations

- The 1-year history fetch (`get_price_history`) said "possibly delisted" for these new listings.
  It was not investigated; with this fix the 7-day download no longer depends on it.

## Manifest and digests

- **Review input:** [FIX-001-manifest.json](FIX-001-manifest.json). The SHA-256 of its LF bytes is
  **`b0d12caf51d4ed74be5ffb3ce8871b22ef982e9313840fa5dda9f2ca89168a4f`**, and `kt_manifest.py verify`
  gives 8 files and 0 mismatches.
  - It lists the 8 files changed since `290b3f7`: 2 code files, 2 test files (1 new), and 4
    documents including the PDF and the new story card.
- **Excluded:** STATE.json, HANDOFF.md and this receipt.
- **Full diff** against `290b3f7`:
  **`3dc30945141d22be231a94b53b5b04db6db8b165a254b22dffeedc174489dd1b`**, 16,938 bytes over 7 text
  files. The PDF is pinned by its blob, `1318d25e…`.
  - **To rebuild it:** take every manifest path except the PDF, sorted.
  - For a path tracked at `290b3f7`, use `git diff --no-color --no-ext-diff 290b3f7 -- PATH`.
  - For a new file, use `git diff --no-color --no-ext-diff --no-index -- /dev/null PATH`.
  - Concatenate the outputs.
