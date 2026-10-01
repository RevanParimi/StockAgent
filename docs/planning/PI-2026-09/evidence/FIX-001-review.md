# FIX-001 review receipt — use a one-bar price download instead of discarding it

## Fresh-session review: ACCEPTED (2026-10-01)

- **What was reviewed:** [FIX-001](../stories/FIX-001.md), as described in the
  [implementation receipt](FIX-001-implementation.md).
  - `daily_review._fetch_session_close._extract` and `close_verifier._fetch_yfinance_close`
    take `df["Close"]` without `squeeze()`, so a one-bar download is a Series, not a scalar.
  - The change adds 10 tests, edits KT §4 and §8 and guide case 05-G, and rebuilds the PDF.
- **Context:** a fresh-session review in a new conversation, 1 Oct 2026, about 15:10–15:35 IST.
  - It is not the conversation that implemented FIX-001, and it did not read that chat.
  - It read the card, the receipt and the diff. It also read all of `_fetch_session_close`,
    `close_verifier.py`, `pricing.close_on` and `session_close`, `grade_ipo_lane`, and
    `get_price_history`. It read the `session_close` consumers in the portfolio pipeline and
    autopilot too.
- **Pending production checks:** none due. SA-039 P3 passed this morning.
- **Peers:** the StockAgent sessions were idle at the start and before the bookkeeping. The one
  busy session belongs to another project.
- **Nothing** was committed, pushed, deployed, configured or sent. No production state was read.
- **Verdict: accepted.** There is no critical, high or medium finding, and no defect in the change.
  - **L1, low.** `close_on` drops the bar's date. That predates FIX-001, and FIX-001 adds one
    route to it. It is routed to SA-012.
  - **I1, information.** KT §8 claimed more than the evidence showed. It was fixed by a review
    edit.
  - **I2, information.** This is an inference that explains the receipt's open limitation. No
    action is needed.

### Review input verified

- **Manifest:** [FIX-001-manifest.json](FIX-001-manifest.json).
  - The SHA-256 of its LF bytes is
    `b0d12caf51d4ed74be5ffb3ce8871b22ef982e9313840fa5dda9f2ca89168a4f`, as the receipt states. The
    committed copy in `3deade8` has the same digest.
  - `kt_manifest.py verify` gave 8 files and 0 mismatches at the start. It gave the same after
    the mutations, because each mutated source was restored and checked by SHA-256.
- **Diff:** rebuilt by the receipt's recipe against `290b3f7`, with the reviewer's own loop.
  - It gave 7 text files, 16,938 bytes and SHA-256
    `3dc30945141d22be231a94b53b5b04db6db8b165a254b22dffeedc174489dd1b`, the receipt's digest.
  - The PDF's blob is `1318d25e…`, as pinned.
- **Completeness:** HEAD is `3deade8`, one commit after `290b3f7`. `git status` lists exactly:
  - 7 of the manifest paths (6 modified, plus the new test file);
  - the 2 excluded bookkeeping files.

  The eighth manifest path is the card. It was committed in `3deade8` with the manifest's blob.

### Contract checked

- **Which close is selected, by frame shape.**

  | Frame | Before | Now |
  |---|---|---|
  | Two or more bars, one `Close` column under yfinance's (Price, Ticker) levels | `squeeze()` gives a Series | `iloc[:, 0]` gives the same Series |
  | Two or more bars, flat columns | `squeeze()` does nothing | the same Series |
  | One bar, either shape | a scalar, so `.dropna()` raised: **the defect** | a one-row Series |

  - The date rules after that line are unchanged: the session's own bar, else the newest
    earlier bar, dated its own session.
  - A frame with several tickers changes in `close_verifier`. It used to fail, and it now takes
    the first column. Nothing reaches this, because `get_price_history` downloads one symbol.
- **NaN.** `daily_review` still drops NaN rows before it selects a bar. `close_verifier` still
  drops nothing, so a NaN last row is rejected by `_sanitize`.
- **The NSE cross-check** is unchanged. A one-bar close now goes through it like any other.
- **Consumers.**
  - `close_on` serves the audit's `price_fn` for every lane and the portfolio API's
    `price_lookup`.
  - `session_close` serves holdings, shelf candidates and autopilot switch buys. Every caller
    checks `fresh_for(session)`.
  - The daily review's own close.
  - `get_verified_close` sets the forecast's base close, through `_fetch_yfinance_close`.
- **The money path.** Autopilot can now price a listing-day switch candidate from Yahoo. NSE
  could already price one, as it priced ELEVATE and ARMEE on 30 Sep. The close is the session's
  own and is fresh, so this is correct pricing, not a policy change. The SA-008 identity check is
  unchanged.

### Independent adversarial examples

The probes are `rev/test_fix001_review.py` in the session scratchpad; they are not tracked.
- They load `daily_review.py` and `close_verifier.py` from `290b3f7` beside the current code,
  and compare the two through the real functions.
- They ran under `tests.conftest`, so the hermetic guard applied. A separate probe confirmed the
  guard: a DNS lookup failed its test.
- Expected values were worked out by hand from the fixture bars.

**7 of 7 passed.**

| Probe | Example | Result |
|---|---|---|
| A1 | 3,000 random frames with two or more bars through `_fetch_session_close`. They mix both column shapes, naive and IST-dated indexes, 25% NaN, duplicate dates and bars after the session. The `.NS`, `.BO` and 1-year attempts are each empty or not, and NSE gives 4 different answers | **0 differ** between `290b3f7` and now |
| A2 | 2,000 random histories through `_fetch_yfinance_close` | 0 differ. A one-bar history gives `None` at `290b3f7` and 77.7 now |
| A3 | One bar of 123.45 on the session, in each column shape, NSE silent | `290b3f7`: no close (`none`). Now: 123.45, dated the session, `yfinance` |
| A4 | **The card's trace.** A strong, evidenced verdict; issue price 100; the listing-day download holds one bar at 131.2; NSE silent; a flat benchmark. The real `close_on` and `grade_ipo_lane` run on the listing day | `290b3f7`: graded 0, skipped 1, nothing stored. Now: one row, horizon 1, dated the listing day. Entry 100, exit 131.2, return and excess +31.2, `correct` True |
| A5 | The same issue on its 5th session (Tue 10 Mar). Yahoo still holds only the listing bar, and NSE has no row | `290b3f7`: both rows skipped, and retried the next night. Now: the horizon-5 row stores 131.2, the listing day's close, as Tuesday's. `correct` is unset. **This is L1** |

### Tests

- **The 10 new tests.**
  - Their expected closes and dates are the fixture's own bars.
  - Their frames use yfinance's shape, plus one flat frame.
  - They patch `yfinance.download`, `get_price_history` and the NSE session, so no real
    transport is reached, and the suite's hermetic guard backs that up. No fixture is
    unrealistically successful: the empty, NaN and older-bar cases are each covered.
- **The reviewer's mutations** (`rev/mutate_review.py`) were **4 of 4 caught**:
  - R1, `squeeze()` back in `daily_review`, which is the original defect: 6 failing;
  - R2, `squeeze()` back in `close_verifier`: 1 failing;
  - R3, a lone earlier bar dated the session that was asked for: 1 failing;
  - R4, a one-bar frame skipping the NSE cross-check: 1 failing.
- **The implementer's M4** (no `dropna()` in `daily_review`) is equivalent, as the receipt
  says: `_sanitize` rejects the NaN.
- **Optional, not a finding:** A4 could become a repository test. Test 8 and the IPO lane's own
  tests cover the two halves of that trace.

### Findings

| ID | Severity | Location | Evidence | Disposition |
|---|---|---|---|---|
| L1 | Low (predates FIX-001, which adds one route) | `core/portfolio/pricing.py:40-45` (`close_on`), `core/audit/outcomes.py:40-43, 548` | `close_on` returns `_fetch_session_close(...).close` and drops the bar's date. So a close carried forward from an earlier bar is stored as the session's exit close, and no audit lane checks freshness. FIX-001 adds a download that holds only one earlier bar: A5, a provider lag in the days after a listing. If NSE has no row, the row is now stored with the listing-day close, where it was skipped and retried before. If NSE has the session within 1%, `_compare` returns the earlier yfinance close as `agree`, where NSE's own close was used before. Today this reaches only IPO rows at horizons 5 and later. They carry no right/wrong mark and are excluded from the report. The listing-day row is safe, because no bar precedes a listing. Multi-bar frames whose newest bar lags have had the same behaviour since before SA-003 | Routed to [SA-012](../stories/SA-012.md) as a card note: price audit rows through `session_close`, and treat a close that is not fresh as unpriceable, so it is retried. Not blocking: FIX-001's criterion (the carry-forward is dated in `_fetch_session_close`) is met |
| I1 | Info (docs) | KT §8 | The KT said production graded its first IPO rows "on 29 and 30 September". The receipt measures only 30 Sep (`ipo: graded 2, skipped_unpriceable 2`). For 29 Sep it records one warning line and no lane summary | **Fixed in review:** §8 states the 30 Sep measurement only, and adds a sentence on L1 |
| I2 | Info (inference from code; not reproduced against Yahoo) | `core/intelligence/algorithms/indicators/fetcher.py:80-91` | `get_price_history` ends at `date.today()`, and yfinance treats `end` as exclusive. So the 1-year fallback cannot see today's bar, and on a listing day it is empty. That is the likely cause of the "possibly delisted" line, which the receipt left uninvestigated | No action. The 7-day download no longer depends on it |

No defect in the change was found.

### Decisions

- **D1 upheld** (A1, A3, A4; R3 is caught). The carry-forward is visible to `session_close`
  callers. It is not visible to `close_on` callers (L1).
- **D2 upheld** (test 10, R2 and the implementer's M3).
- **D3 upheld.** The indicator fetcher's `squeeze()` calls (lines 226, 258, 387–388) work on
  year-long histories.
- **D4 upheld.** The SA-003 test file's diff changes a comment only.

### Commands and results

Environment: Windows 11, `.stockai` venv (Python 3.13.11), repository root.

| Check | Command | Result |
|---|---|---|
| Manifest | `python scripts/docs/kt_manifest.py verify docs/planning/PI-2026-09/evidence/FIX-001-manifest.json` | 8 files, 0 mismatches, `b0d12caf…`, at the start and after the mutations |
| Diff | the receipt's recipe, with the reviewer's own loop | `3dc30945…`, 16,938 bytes, 7 text files; PDF blob `1318d25e…` |
| Full suite | `python -m pytest tests -q -p no:cacheprovider` | **4036 passed, 12 skipped, 0 failed** (7 min 20 s, about 15:12–15:20 IST), the implementer's count. `data/`, `logs/` and `outputs/` were unchanged: 800 files, the same digest before and after |
| Focused | `python -m pytest -q -p no:cacheprovider tests/unit/test_one_bar_close_fix001.py tests/unit/test_session_close_sa003.py tests/unit/audit/test_audit_ipo_lane.py` | 58 passed |
| Probes | `python -m pytest -q -s -p no:cacheprovider -c pyproject.toml --rootdir . -p tests.conftest <scratchpad>/rev/test_fix001_review.py` | 7 passed |
| Mutations | `rev/mutate_review.py` | 4 of 4 caught |
| Broad-except guard | `python scripts/ci/check_broad_except.py` | OK (154 grandfathered) |
| KT check | `python scripts/docs/check_kt_docs.py` | Before the edits: errors `[]`, 419 links, 33 pages, source `a8511517…`, the manifest's KT. After the edits and `build_kt_pdf.py`: errors `[]`, 419 links, 33 pages, source `9e4d782b…`, PDF blob `27d2121c…` |

**Not exercised:**
- Linux and Python 3.11 (CI runs after a push);
- a real Yahoo or NSE response for a listing day;
- any production data.

### Review edits (documentation only)

- **The KT:**
  - §4 and §8 now read "accepted by its fresh review on 2026-10-01, not yet committed";
  - §8 states the 30 Sep measurement only (I1), and says that `close_on` stores a
    carried-forward close as the session's (L1).
  - The PDF was rebuilt (source `9e4d782b…`).
- **Guide 05-G:** the status wording.
- **The [SA-012](../stories/SA-012.md) card:** a routed note for L1.
- **Manifest check:** `verify FIX-001-manifest.json` now mismatches exactly the KT, the PDF and
  the guide. No code or test file was changed.

### Acceptance and what remains

| Criterion | Result |
|---|---|
| A one-bar download for the session gives that close, dated that session | Met (tests 1–3, A3, A4) |
| A lone earlier bar is dated its own session | Met in `_fetch_session_close` (test 4, R3). `close_on` drops the date (L1, routed) |
| A lone NaN bar is no close | Met (test 5) |
| The BSE fallback reads a one-bar frame | Met (test 6) |
| `close_verifier` reads a one-bar history, and a NaN last row stays a failure | Met (tests 9, 10, A2) |
| Two or more bars behave exactly as before | Met (A1: 3,000 cases, A2: 2,000; test 7; the 14 SA-003 tests) |
| Hand-written expectations that fail on the original defect | Met (R1: 6 failing) |
| KT §4 and §8 and guide 05-G describe it | Met, with the review edits |

- **Reviewed revision:** the uncommitted working tree on `3deade8` (baseline `290b3f7`), pinned
  by input `b0d12caf…` and diff `3dc30945…`, plus the documentation-only review edits.
- **Next:**
  - **Commit and push** need the owner's word, in a job-free window. The landing commit's KT
    bump declares the FIX-001 commit, because `daily_review.py` changed after `9c626a5`.
  - **Production check.** After the deploy, the first nightly audit shows no
    `'numpy.float64' object has no attribute 'dropna'` line.
    - The two skipped rows (SWASTIKAIN and ADROITIND, 30 Sep) are retried each night. A retry
      asks for the 30 Sep close, and its download window ends that day, so it holds the one
      listing bar. Each row is graded once Yahoo or NSE has that bar.
    - `production_verification` is `pending_deployment`.
- **Next story:** FIX-002's implementation, in a new conversation. FIX-003 and then SA-010
  follow. SA-008 change 1 stays open. It must come before any `successors` record.
