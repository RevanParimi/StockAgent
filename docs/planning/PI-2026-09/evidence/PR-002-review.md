# PR-002 — review receipt

**Phase:** fresh-session review (a new conversation opened with "continue", 16 Oct 2026, about
18:45–19:20 IST, session stockagent-main-43; all 15 peers idle). It is neither the
implementing conversation (stockagent-main-a9) nor a self-review.
**Verdict: ACCEPTED.** One medium finding (F1) and two low findings (F2, F3) are follow-ups
with named owners. No critical or high finding, and every acceptance criterion is met.

**Reviewed revision:** the committed code `b400747` (parent `b67f972`) and the docs commit
`4027d4a`, pinned by review input [PR-002-manifest.json](PR-002-manifest.json)
`98df10d051f35a77d903f3bb3001bbc4eff94c2b1dad8d1f9956d5d0927afc9a` (15 files).
`kt_manifest.py verify` gives 0 mismatches against `4027d4a` and against the working tree,
at the start and at the end of the review. The code diff is `git diff b67f972 b400747`:
9 files, 107,058 bytes, SHA-256
`015a5155bfc0eae2982e5efdec14178e968670f4e34de3ce393954b24183c9ce`
(`git diff --no-color --no-ext-diff b67f972 b400747`, saved to the ignored
`analysis_data/pr002/review/code.diff`).

Nothing was committed, pushed, deployed or configured. No production state was read, no
message was sent and no reviewed file was changed. The review wrote this receipt, STATE and
HANDOFF, follow-up notes on the SA-051 and PR-010 cards, and its own probes under the
ignored `analysis_data/pr002/review/`.

## In one example

The owner's account holds ₹10,00,000 in cash for four weeks while the Nifty rises from 100
to 110. The scorecard says "RED FLAG: Behind the Nifty … +0.0% against +10.0%", which is
right.

Now say that, in the middle of those four weeks, the owner adds 1,000 shares through
"Add holding" with a buy date a year back. Bought at ₹50, they are worth ₹150 on the day of
the add. The add records ₹50,000 of capital, but ₹1,50,000 of stock arrives. The scorecard
counts the ₹1,00,000 gap as the portfolio's gain in those four weeks: +9.5% against
+9.8%, and the flag reads clear. Valued at ₹1,50,000 on the day it arrived, the window is
0.0% against +9.3%, and the flag fires as before (finding F1).

## Contract checked

The card's hard-review question is "can the scorecard flatter the portfolio?". Each part was
traced in the code, then checked with a fixture whose expected figures were worked out by
hand.

| Question | Result |
|---|---|
| Exited stocks stay in every denominator | Yes. Closed trades count every full exit. "Sold too early" counts every advisor sale, held or not. Matured sales with no grade are counted as missing, never dropped (mutant `exited_dropped` re-run: 6 failures). |
| Horizons count exchange sessions | Yes, through the auditor's own `trading_days_after`. Grades are looked up only for sales whose horizon ended by the week's end. |
| Money-weighted, cash drag included | Yes for cash. The same flows are on both sides, so idle cash counts against the portfolio. **Not for an added holding** (F1). |
| Missing data cannot silence a flag | Yes. The bounds rule covers ungraded sales and unknown purchase dates (mutant `skip_missing_flag` re-run: 4 failures). A missing Nifty close and a week with no valuation read "unavailable". |
| The join between a sale and its grade | Exact. The autopilot writes `advice_ref` = `date|symbol|rationale_hash` from the same advice record the auditor keys its `ref` on. Probe B runs the real writers end to end. |
| Issue-time | Transactions and value points after the week are dropped before anything is computed. The auditor runs nightly at 23:45 IST, so a sale that matured on Friday has its grade by Sunday 18:00. |
| Authorization | `GET /portfolio/scorecard` takes the user from the session and reads only that user's file. The scorecard opens only the user's own auditor file (mutant `default_user_audit` re-run: 1 failure). `POST /delivery/run-weekly` is owner-only (unchanged). |
| Duplicates and retries | The week is checked and appended under one file lock. A weekday run covers the finished week before. Only an owner's manual run with a future date makes a provisional row, and that row is never stored. |
| Bounded math | A zero or negative cost or base gives "unknown" or "unavailable". An empty population gives "not enough". The holding-period bounds use infinity and print only finite values. |
| Browser sink | The weekly screen renders the row's sentences as React text, with no raw-HTML sink. Exercised in Chromium (`npm run test:frontend`). |
| Compatibility | A review stored before the change has no `scorecard` key, and both the text and the screen render it as before. A stale `scoreboard` key is ignored. |

### Independent adversarial examples (reviewer probes)

`analysis_data/pr002/review/test_rv_probes.py`, run under the suite's hermetic boundary
(`conftest.py` imports `tests.hermetic`): **4 passed**. Each docstring has the hand figures.

- **A, reference.** ₹10 L of idle cash while the Nifty rises 100 → 110. The real valuation
  writer (`autopilot.record_value_point`) records the points. The window reads 0.0% against
  +10.0%, so the flag fires.
- **A, backdated add (F1).** The same account, plus the real `POST /portfolio/holdings` on
  20 Feb: 1,000 shares with buy date 2025-02-03, priced by the route at ₹50 and worth ₹150.
  `capital_in` steps by ₹50,000 and equity by ₹1,50,000. The window reads +9.52% against
  +9.75%, and the flag reads **clear**. By hand, with the add valued at its arrival, it is
  0.00% against +9.32%, and the flag **fires**. "Since the start" reads +9.52% against
  +9.75% ("level"), where the idle cash alone is 10 points behind.
- **B, the real join.** An EXIT is advised on 12 Jan at ₹90, and the real
  `autopilot.execute_advice` executes it. The real `grade_advice_lane` writes +17.2 points
  at 10 and 30 sessions. On Sunday 8 Mar the scorecard finds 1 sale, graded once, beating
  the Nifty, at each horizon. The trade is −10% on a ₹100 cost.
- **C, the retention prune (F2).** ₹1,000 is invested on 5 Jan at Nifty 100 in a stock that
  tracks it, and both sides make +32%. The real `retention._prune_value_history`, with the
  cap at 2 points (400 in production), keeps the last two. The first kept point's
  `capital_in` then reads as a deposit on 2 Feb at Nifty 120. "Since the start" becomes
  +32% against +10%: 22 points "ahead" for the same history.

## Findings

| # | Severity | Location | Trigger → observed / expected | Impact | Disposition |
|---|---|---|---|---|---|
| F1 | **Medium** (confirmed, probe A) | `core/portfolio/results.py:307-320` (`deposits_from_values`), with the writers `services/api/routes/portfolio_api.py:155-157` and `core/portfolio/store.py:492-497` | Trigger: on a cash-accounting account, "Add holding" with a buy date before the add, a typed price, or a CSV import. Observed: the Nifty side is credited the holding's **cost** (`capital_in` += qty × buy-date close or typed price), while the equity series carries its **market value**, so the gap counts as the portfolio's return in the period of the add. Expected (the card: "each deposit buys Nifty units at that day's close"): the holding enters both sides at its value on the day it arrives. Otherwise, the windows it touches should say "could not check". | It can silence "Behind the Nifty" for the 4 weeks after the add (probe A), or fire it falsely after adding a stock that has fallen since purchase. "Since the start" carries the gap for ever. Affects only accounts with valuations, which today is the owner's autopilot account. The form's default (buy date today, no price) is unaffected. Reports only: no decision changes. | **Follow-up, owner [SA-051](../stories/SA-051.md)** (its chart reuses `nifty_equivalent` and the same deposit rule; a note was added to its card). The fix is a contract choice for SA-051: value in-kind additions at the arrival day's close, or mark the windows they touch as could-not-check. Until then the KT should say so (commit-time edit below). |
| F2 | Low (confirmed, probe C; latent) | `core/portfolio/results.py:307-320` with `core/portfolio/retention.py:89-112` (`value_history_cap: 400` in `config.yaml:838`) | Trigger: a user's value history passes 400 points. Observed: the first kept point's `capital_in` becomes the "opening deposit" on that later date, so "since the start" compares the portfolio since inception with the Nifty since the cut. Expected: deposits keep their own dates. | The since-start line only, not a flag. At one point per review day, the owner's account (started July 2026) reaches 400 points around early 2028. | **Follow-up, owner SA-051**, noted with F1. SA-049's dated `DEPOSIT` transactions (never pruned) are a natural source, or retention could keep the first point. |
| F3 | Low (code inspection) | `src/frontend/prototypes/weekly-view.jsx:44-46` | Trigger: a flag with status `not_enough` (for example "the check needs 8"). Observed: the screen shows it with "✓" beside the clear checks. The email says "Checked, too few to judge". Expected: a neutral mark for "too few to judge". | A tick can read as "passed". The sentence itself is honest. | **Follow-up, owner [PR-010](../stories/PR-010.md)** (the screens rework; a note was added to its card), or any earlier story that touches the weekly screen. |
| I1 | Info | `vs_nifty` and the benchmark `^NSEI` | Dividend cash raises the portfolio's equity, while `^NSEI` is a price index. The tilt in the portfolio's favour is about 1.2–1.5% a year, about 0.1 point over 4 weeks, far below the 3-point line. | None now | Shared with the auditor's grades. Revisit if the benchmark changes (SA-012 and SA-051 name the Nifty series). |
| I2 | Info | D3, `expectancy_flag` | The flag reads since-start expectancy, so it stays on until the whole record turns positive. Inference: with the 11 Oct baseline (−2.2% per trade on 8 sales since August), the first Sunday's row will probably show "RED FLAG: Losing money per trade". | Expected, not a defect | Tell the owner before 18 Oct. |
| I3 | Info | `weekly_scorecard` with a future `on` | An owner-only manual run dated in the future emails a provisional row without saying "provisional". It is never stored. | Negligible | None |
| I4 | Info | `PortfolioStore.append_scorecard_once` | A process killed mid-write leaves a partial line. It is skipped on read, and that week's row is appended again on the next run. | Self-healing | None |

Nothing else was found. Exited stocks, horizons, missing grades, the money-weighted cash
case, idempotency and member isolation each held under a hand-built fixture.

## Rulings on the implementer's delegated decisions

- **D1 (executed sales, not raw auditor rows):** accepted. Probe B confirms that the join is
  exact. On the autopilot account every EXIT is executed the same evening, so the population
  equals the auditor's.
- **D3 (since-start expectancy at three week ends):** accepted. The sentence describes it
  exactly ("negative at the end of each of the last 3 weeks"), and the week's own figure is
  on the "Closed trades" line. It lags a real improvement (I2); revisit after PR-009, as
  recorded.
- **D4 (no-cost trades excluded and counted):** accepted. A missing percentage has no
  bound, and the line states the count.
- **D5 (a stored week is frozen):** accepted. It is the card's idempotency rule.
- **D8 (HTML is the Inbox screen):** accepted. The weekly email has no HTML body, and the
  screen renders the same stored sentences.

## Commands and environment

Windows 11, the `.stockai` venv (Python 3.13), Node 24 with the vendored Playwright
Chromium. Hermetic boundary on (SA-005): no `.env`, no network, no checkout data.

| Command (repository root) | Result |
|---|---|
| `kt_manifest.py verify docs/planning/PI-2026-09/evidence/PR-002-manifest.json [--rev 4027d4a]` | 15 files, 0 mismatches, both, at the start and the end |
| `pytest tests/unit/test_weekly_scorecard_pr002.py tests/unit/test_delivery_weekly.py tests/unit/test_delivery_api.py tests/unit/test_portfolio_api.py tests/unit/test_autopilot_api.py tests/unit/test_m0_idor.py -q -p no:cacheprovider` | **411 passed** |
| reviewer probes `analysis_data/pr002/review/test_rv_probes.py` (`--rootdir` there, `PYTHONPATH=<repo>;<repo>\src`) | **4 passed** (A ×2, B, C) |
| the implementer's mutants, re-run: none, `exited_dropped`, `skip_missing_flag`, `lump_sum_nifty`, `default_user_audit` | baseline 50 passed; 6, 4, 2 and 1 failures, matching the implementation receipt |
| `npm run test:frontend` | **32/32**, including the 2 weekly-screen tests |
| `scripts/docs/check_kt_docs.py` | errors `[]`; PDF 44 pages, source `d1a86e53…`; 91 linked sources, none changed since `b400747` |
| `scripts/ci/check_broad_except.py` | OK (152 grandfathered) |
| `pytest -q -rfEs -p no:cacheprovider tests` (CI's command) | **4,947 passed, 12 skipped, 0 failed** in 13 min 35 s (the implementer's one transient `WinError 5` did not recur); the working tree was unchanged afterwards |

**Not exercised:** production data (the first Sunday is the production check), a real
yfinance Nifty fetch, a real SMTP or push delivery, and cross-process lock contention
(threads were tested). The mutants not listed above were not re-run.

## Acceptance checklist

| Criterion | Verdict |
|---|---|
| Fixture ledger → win rate, averages, expectancy equal hand figures; an open position is never closed | Met (story tests; probe B's −10% trade) |
| "Sold too early" by horizon; unmatured = pending; exited stock stays in the denominator | Met (story tests; probe B with the real writers) |
| Two deposits + hand-built Nifty → hand figure; missing benchmark "unavailable", never flat | Met for cash deposits. An added holding is mis-valued (F1, follow-up) |
| Each red flag fires when crossed, silent one unit below | Met |
| Re-running a week rewrites and appends nothing | Met (also 8 threads → 1 row) |
| A member's scorecard reads only that member's ledger | Met (store and real sign-up endpoint tests) |
| Property test; weekly job end to end with transports blocked | Met |
| KT section 7 as current design; human test case | Met (KT sections 3, 7, 9, 10 and 11; guide 09-G); PDF matches its source |

## Commit-time edits (applied in the acceptance commit)

The owner said "commit and push" (16 Oct, about 20:05 IST). These three edits went into
one docs commit with this receipt, the SA-051 and PR-010 card notes, STATE and HANDOFF.
The PDF was rebuilt (source `ec5ab870…`, 44 pages) and `check_kt_docs` reports `[]`. The
KT keeps "Code inspected: `b400747`", because no code changed. The owner's line in
`docs/README.md` stays uncommitted.

1. **KT section 12:** the PR-002 row `Open` → `Done`.
2. **KT section 7, "You vs the Nifty" row (F1 as current design):** append "A holding added
   with an earlier buy date or a typed price, or imported from a CSV, enters `capital_in`
   at its cost, so its gain before it arrived counts as the portfolio's in that period.
   **Planned:** [SA-051](planning/PI-2026-09/stories/SA-051.md) values it on the day it
   arrives." Then rebuild the PDF and run `check_kt_docs`.
3. **Guide 09-G status line:** "**PR-002: accepted 2026-10-16, committed as `b400747`;
   production verification pending.**"

## Production verification (remaining)

Deployed `4027d4a` (SUCCESS by 18:34:30 IST, 16 Oct; recorded by the implementing session).
`pending_observation`. On Sunday 18 Oct after 18:00 IST, the owner reads the weekly email and
`GET /portfolio/scorecard` and records the first row (week key, flags fired, could-not-check
lines) in the implementation receipt's production section, then runs guide 09-G.

- **Read with F1 in mind:** if a holding was added in the last 4 weeks with an earlier buy
  date, a typed price or a CSV, the "You vs the Nifty" lines include that stock's earlier
  gain or loss.
- **Expect** "Losing money per trade" to be among the red flags (I2).

## Decision

**ACCEPTED** at `b400747` + `4027d4a` (input `98df10d0…`). STATE: PR-002 `done`,
`active_task: null`, **`next_task: PR-003`**, which is ready (no dependencies) and is not
started in this conversation. Follow-ups: F1 and F2 → SA-051 (card note added), F3 → PR-010 (card note added).
