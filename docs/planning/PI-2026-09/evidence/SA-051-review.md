# SA-051 — fresh-session review receipt

**Story:** [SA-051](../stories/SA-051.md): show the portfolio against the Nifty, with honest
labels, plus PR-002's review follow-ups F1 (an added holding enters at its cost) and F2
(retention moves "since the start").
**Context:** a **fresh-session review**, 19 Oct 2026, about 15:26–16:15 IST. Session
stockagent-main-db, a new conversation opened with "continue". It is not the implementing
conversation (stockagent-main-da). That session wrote the bookkeeping files at 15:24 and was
idle from 15:35, when this review marked itself started; no peer was busy after that.
**Reviewed:** the uncommitted working tree on `bb9969e5b5a9902a5d5e920b3f741a9dffbd1755`.
- Input [SA-051-manifest.json](SA-051-manifest.json) `fb29bbda…`: 18 files, **0 mismatches**
  at the start and at the end (`kt_manifest.py verify`). No payload file changed after
  13:24 IST.
- Diff rebuilt by the reviewer (`analysis_data/sa051_review/rev_digest.py`). It takes the paths
  from the manifest, not from the implementer's list, and chooses `git diff HEAD` or
  `--no-index` by whether HEAD tracks the path. Result: **`fb7c36da…`, 136,285 bytes, 17
  paths**, the receipt's digest. Every other dirty path is bookkeeping (STATE, HANDOFF, the
  receipt, the manifest) or the owner's `docs/README.md` line.

**Verdict: ACCEPTED.** No critical or high finding, and every acceptance criterion is met.
Two low findings:
- **R1** (behaviour): a holding added while the 16:30 run is under way is valued two ways.
  Routed to SA-049, with a KT wording edit at commit.
- **R2** (documentation): `UI_SPEC.md` still describes the old screen and response. Fixed by
  an edit at commit.

Nothing was committed, pushed or deployed, no production state was read and no message was
sent.

## In one example

The reviewer's trace RV3 runs **the real 16:30 pipeline** while the owner adds a holding:

- **The account.** ₹10 L from 30 Jan: ₹9,90,000 in cash and 100 BASE at a flat ₹100.
- **The add.** On Fri 20 Feb, while the pipeline is narrating BASE (16:35), the owner adds
  1,000 ACME through the real route, with a buy date a year back. The route prices them at
  that day's ₹50; they are worth ₹150.
- **The valuation.** The value point is written at 16:40, under the lock, by the real writer.
  It holds ACME (`recorded_at` is after the add), but the pipeline took its closes before the
  add. So the point marks ACME at its ₹50 cost: equity ₹10,50,000.
- **The comparison.** It takes ACME in at ₹150, so ₹1,50,000 of money arrives that day.
  - The week of 16–22 Feb reads **−8.70% against the Nifty's +2.56%**. The truth is 0.0%.
  - That evening the screen says the portfolio is ₹1,50,000 behind (13.0 points); the truth
    is ₹50,000 behind (4.3 points).
  - The next valuation marks ACME at ₹150, so the following week reads +9.52% against +1.90%.
- **A losing stock flatters.** Shares typed in at ₹150 but worth ₹50 make the same week read
  +9.52% against +2.80%: **ahead when the truth is behind**.
- **Control.** The same add at 11:00, before the run loads the portfolio, reads the truth:
  0.0% against +2.56%.

This is finding R1. The receipt's L2 names the mechanism, but calls the result "a small
loss". It is the whole difference between the stock's close and its cost, in either
direction. A weekly scorecard row is stored once, so a week that ends on that valuation keeps
the wrong figure.

## Contract checked

**The card's hard-review questions.**

| Question | What the reviewer found |
|---|---|
| Can the comparison flatter the portfolio? | Only through R1, an add during the run. Otherwise no: RV1 and RV2 below. |
| Deposit dates | Each deposit is dated at the first value point that shows it. RV1 agrees over 300 random histories, including arrivals at every hour of the day. Pruning keeps every date (F2). |
| Holiday walkback | RV4 runs the real `BenchmarkSeries` through `/portfolio/performance`. A deposit on an NSE holiday buys at the session before it (102). A day Yahoo never published also stands on 102, never on the later 110. Line: 10,00,000 / 10,20,000 / 11,20,000 / 12,20,000 / 13,15,686.27. One download; the second page load downloads nothing. |
| Cash drag shown | Yes. Both sides use the same flows over total equity, so idle cash counts against the portfolio. |
| Money-weighted, not just the invested part | Yes. The control test shows HEAD's cost rule reads off-level where the new rule reads level. |

**Independent invariants (the reviewer's trace, `analysis_data/sa051_review/test_rv_trace.py`):**

- **RV1, 300 random histories.**
  - Cash deposits and arrivals land at random times, before or after 17:00; cash trades are
    mixed in.
  - The Nifty line, the since-start figures and four ranges are checked against an
    exact-arithmetic model written from the card's rule (`fractions`, not `results.py`). Every
    figure agrees to the paisa or 0.01 point.
  - A copy pruned at a random cap keeps the same flows and since-start comparison, arrivals
    included.
  - The first run found one disagreement, an arrival at exactly 17:00:00. The real writer stamps
    microseconds under the lock, so such a tie cannot happen; the model now avoids it.
- **RV2, 150 histories always in the Nifty.**
  - Every deposit is invested in a Nifty tracker at once, and every arriving stock moves with
    the Nifty, at any backdated cost.
  - Every range and the since-start figure read level: the gap is below ₹0.05 per point,
    which is the writer's rounding.
  - Control: HEAD's at-cost rule reads off-level in more than 20 of these histories.
- **RV3, the real pipeline:** R1 above (3 tests, with the control).
- **RV4, the real benchmark through the route:** the walkback above.
- **RV5, real threads:** two store objects (as two processes) on the same lock file.
  - An add in progress blocks the valuation, and the reverse.
  - Add first: the point is recorded after the add, holds it whole (`capital_in` ₹10,50,000;
    ACME ₹1,50,000) and carries the ₹1,50,000 flow.
  - Point first: the add is recorded after the point and is not in it.

**Other checks:**

- **Arrivals.** Only "Add holding" and the CSV import write `manual` BUY rows: a grep of the
  non-test code finds those two, plus the manual delete, which is a SELL. The add route has
  stamped `ts` (the add's own time, not the buy date) since 11 Jul. A manual delete sells to
  cash and leaves `capital_in` alone, so no holding leaves in kind.
- **Same-day points.** `record_value_point` skips a second point for a day, so "the last
  point wins a date" never hides a `recorded_at`.
- **The benchmark preload.** `_pick` reproduces the old per-date choice exactly. The download
  starts 7 days before the first session, so every day in range sees the same window as a
  per-date fetch. The cache holds a range only once its last session has its own bar. A
  failed download marks the range loaded, so nothing falls back to per-date fetches.
- **The screen.**
  - The chart and each range's figure use the same points (`range_points`).
  - A missing Nifty value breaks the dashed line, and a run of one point is not drawn.
  - `fmtSigned` never shows a negative zero.
  - Every share price in the table, the activity card and the agents' card carries a date.
- **Compatibility.** New response fields only, and each history row gains `nifty_value`.
  `vs_nifty`, `build_row` and `weekly_scorecard` keep their signatures. The scorecard's
  arrivals use the same `capital_flows`.

## Rulings on the implementer's decisions

| Decision | Ruling |
|---|---|
| D1 an arrival valued at the close of the first valuation that holds it | **Accepted**, with R1: it is neutral only when that run priced the holding. |
| D2 `recorded_at` under the lock, no guess from the rise in capital | **Accepted**; RV5 confirms the ordering with real threads. |
| D3 unknown flows (unavailable inside or before a busy period; the index's own move before a quiet one) | **Accepted**. With constant units the Nifty side's return is the index's move, whatever the units are. |
| D4 F2 through retention | **Accepted**: RV1's pruned copies, arrivals included. |
| D5 "Capital added" at cost, "Total return" unchanged (L3) | **Accepted** as a product decision. The KT says so; the comparison is the honest figure. |
| D6 the gap in rupees and in points | **Accepted**. The two always agree in sign: points = rupees ÷ the deposits. |
| D7 money-weighted range figures | **Accepted**: RV1's four ranges. |
| D8 shares: cash rounded, stocks 100 minus it | **Accepted**. |
| D9 no comparison or trade card without cash accounting | **Accepted**. |
| D10 the allocation card stays a share of the holdings | **Accepted**. |
| L1, L3–L6 | **Accepted** as documented. Production has no arrivals (the 13:40 probe). |
| L2 an add during the 16:30 run | **Re-stated as R1**: the size and direction of the effect were understated. |

## Findings

| # | Severity | Where | Trigger → observed / expected | Impact | Disposition |
|---|---|---|---|---|---|
| R1 | Low (confirmed, RV3) | `core/portfolio/pipeline.py:241-248` (closes from the portfolio loaded at the start), `:322-323` (the point loads the store again under the lock), `core/portfolio/sizing.py:52` (no close: cost), `core/portfolio/results.py` `capital_flows` (the arrival at that day's close) | An add while the run is under way (or a close that fails for the arrival in its first run) → the point holds it at cost, the flow at the close. The ₹50/₹150 add reads −8.70% for its week (truth 0.0%); a ₹150/₹50 add reads +9.52% (truth 0.0%). | That day's comparison is off by qty × (close − cost), either way, until the next valuation. A weekly row whose week ends on that valuation keeps it, and can fire or clear "Behind the Nifty" wrongly. Rare: the run takes minutes, and production has never had an arrival. | Routed to **SA-049** (card note). Either fix works: price the holdings that arrived during the run before the point, or have the point record which holdings it marked at cost so that `capital_flows` treats the jump to the first close as money in. Test: RV3's shape reads 0.0%. KT section 7's limit sentence corrected **at commit** (text below). |
| R2 | Low (docs) | `src/frontend/prototypes/UI_SPEC.md`: the portfolio section's live-wiring paragraph and layout, the component and props tables (`Stat2 share`, `AlertsCard reviewDate`, `ValueChart`, `TradeRecordCard`, `RangeFigure`, `VsNiftyLine`) and the API table's `GET /portfolio` and `GET /portfolio/performance` rows | The spec still says the hero shows "Cash + Realized P&L stats" and the chart plots `total_equity` only, and it lists the old response fields. | A teammate reading the spec misses the comparison, the new fields and the dates. It was updated by PR-001 and FIX-010, so it is living documentation; the implementation receipt checked ARCHITECTURE and the README but not this file. | **Edit at commit** (list below). |

**Info, no change needed in SA-051:**

- **The hero mixes the last valuation with live figures.** "In stocks" comes from the last
  value point; "Cash" and "Capital added" are live. This was already true of the old hero.
  - Between an add and the next valuation, "Total return" reads the add's cost as a loss.
    The comparison and the shares do not.
  - "Valued as of" now dates the valuation. PR-010 rebuilds this screen, so its card gets a
    one-line note.
- **The closed-trade card counts the owner's own trades,** as PR-002's scorecard does. A
  holding added with an earlier buy date and later sold counts its whole gain since that date.
  That is a real round trip for the owner; the card does not claim it as the autopilot's.

## Commit-time edits (at the owner's word, with the implementer's list)

The implementation receipt's list stands: the KT header, section 12's SA-051 row `Done`, the
PDF rebuild and `check_kt_docs`; the AUTOPILOT_GUIDE header; the guide's 08-G and 08-H status
lines. Add:

- **KT section 7, "Holdings that arrive without cash" (R1).** Replace the "Limit." bullet
  with:

  > - **Limit.** A holding added while the 16:30 pipeline runs, or one whose close fails in
  >   that run, is in that day's valuation at its cost while the comparison values it at the
  >   day's close. Until the next valuation marks it to market, that day reads the
  >   difference, quantity × (close − cost), as a loss or a gain that is not the
  >   portfolio's. A weekly scorecard whose week ends on that valuation keeps it. Example:
  >   1,000 shares bought at ₹50, worth ₹150 and added at 16:35 read ₹1,00,000 behind that
  >   day. **Planned:** SA-049.

  Then rebuild the PDF, as the header edit already requires.
- **The implementation receipt's L2** gets a pointer to R1. It now calls the effect "a small
  loss".
- **`src/frontend/prototypes/UI_SPEC.md` (R2).** Make each of these describe the current
  screen:
  - the "Live-wired" and "Cash/day-change/range-chart" paragraphs and the layout's hero
    lines: Capital added, In stocks and Cash with shares, Valued as of, the comparison
    sentence, `ValueChart` with the dashed Nifty line and the range figure;
  - the component tree (`TradeRecordCard` under the holdings);
  - the props tables (`Stat2` `share`, `AlertsCard` `reviewDate`, the four new components);
  - the API rows: `GET /portfolio` gains `last_close_date`, and `GET /portfolio/performance`
    gains `in_stocks_pct`, `cash_pct`, `history[].nifty_value`, `benchmark`, `vs_nifty`,
    `ranges`, `range_points` and `closed_trades`, and reads every row and point.
- **Found while making these edits (part of R2):** AUTOPILOT_GUIDE section 9 still said
  "there is no benchmark" and listed the Nifty comparison as planned, and section 16
  listed it under planned work. Both now describe the current design.

## Commands and environment

Windows 11, the repository's `.stockai` venv (Python 3.13), Node 24 with the vendored
Playwright Chromium. The hermetic boundary (SA-005) is on for every pytest run: no `.env`, no
network, no checkout data.

| Command (repository root) | Result |
|---|---|
| `scripts/docs/kt_manifest.py verify docs/planning/PI-2026-09/evidence/SA-051-manifest.json` | 18 files, 0 mismatches (start and end) |
| `.stockai/Scripts/python.exe analysis_data/sa051_review/rev_digest.py` | `fb7c36da…`, 136,285 bytes, 17 paths |
| `.stockai/Scripts/python.exe -m pytest -q -p no:cacheprovider analysis_data/sa051_review/test_rv_trace.py` | **457 passed** |
| the story file, `test_weekly_scorecard_pr002.py`, `tests/unit/audit/`, `test_atlas_retention.py`, `test_portfolio_api.py`, `test_autopilot_*.py`, `test_portfolio_*.py`, `test_seed_autopilot.py`, `test_broad_except_guard.py`, `tests/unit/pipeline`, `test_ui_no_invented_figures_pr001.py` | **1,088 passed** in 4 min 28 s |
| `npm run test:frontend` | **39/39** |
| `PYTHONPATH="analysis_data/kt_docs_deps;.;src" python scripts/docs/check_kt_docs.py` | errors `[]`; PDF source `7a430a02…` = the KT's SHA-256 (47 pages) |
| `python scripts/ci/check_broad_except.py` | OK (151 grandfathered) |
| `.stockai/Scripts/python.exe -u -m pytest -q -p no:cacheprovider -o console_output_style=count tests` | **5,332 passed, 12 skipped, 1 xfailed (the known PR-003 limit), 0 failed in 19 min 28 s** |

Raw outputs (ignored): `analysis_data/sa051_review/full_suite.txt`, `npm_frontend.txt`, and the
helper scripts (`rev_digest.py`, `splice_start.py`, `debug_seed.py`, the trace and its
`conftest.py`).

**Not exercised:**

- No production read in this phase. The implementer's 13:40 probe stands: one cash account,
  67 points, no arrivals.
- No real Yahoo or NSE call: the benchmark ran through a patched `yfinance.download`.
- The race in R1 was driven through the real pipeline with its network and LLM seams
  patched, not timed in a live run.
- The mutant runs were not repeated. The reviewer's own controls take their place: HEAD's
  cost rule fails RV2, and the 11:00 add reads the truth in RV3.

## Production and follow-up state

- **SA-051:** `done` for this revision. Production verification **`pending_deployment`**.
- **After the deploy:**
  - value points carry `recorded_at` from the first 16:30 run;
  - open the portfolio screen: the labels, the comparison and the trade card;
  - in a test copy, run guide 08-G and 08-H;
  - the first Sunday's scorecard shows "You vs the Nifty" as before. Production has no
    arrivals, so no figure changes.
- **Follow-ups:**
  - R1 → SA-049 card note (routed input, 19 Oct);
  - the hero note (info) → PR-010 card note;
  - R2 and the R1 KT wording → commit-time edits.
- **Commit and push only at the owner's word,** in a job-free window: not 08:30–09:20 or
  16:25–17:15 IST.
- **Next:** PR-004, ready. Not started in this conversation.
