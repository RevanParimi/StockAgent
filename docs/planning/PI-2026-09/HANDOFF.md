# Current handoff - 2026-10-16 (updated about 12:25 IST)

## Also 11 Oct (about 13:00–15:30 IST): product results review and new tasks (separate conversation)

At the owner's request ("the stockagent product needs deeper analysis …"), a separate conversation
(`stockagent-main-43`) reviewed trading results, explanations, models, breadth, the UI, the
central intelligence and the morning brief. **Docs only:** nothing committed, pushed, deployed or
configured, and no production state read. It did not touch SA-011 (in progress in another
session), `active_task` or `next_task`.

- **Review:** [docs/audit/2026-10-11-product-results-review.md](../../audit/2026-10-11-product-results-review.md).
  Main findings:
  - **Sales lose because the exit rule sells on weakness.** `thesis_break` fires after one day's
    price-path miss. In the July snapshot it caused all 9 sales, held 4 to 17 days. Of the 8
    measurable, 6 sold stocks beat the Nifty over the next 20 sessions (median +3.0 points).
  - **Reasons are code-like** because the narrator gets only rule codes.
  - **The portfolio shrank to 2 holdings** because new positions open only through a SWITCH.
  - **The brief repeats** because freshness is judged by fetch date, not publish date.
  - **The portfolio page shows a score × 10,000 as rupees**, and the home hero is hard-coded.
- **Found on the way, privacy:** `GET /ui/logs` and `/ui/logs/stream` need no sign-in. This is
  code inspection; the routes were not called. Routed as [FIX-007](stories/FIX-007.md), first
  in the new block.
- **New tasks** (cards in `stories/`):
  - FIX-007;
  - PR-001 to PR-012: invented figures, weekly scorecard, fresh news, idea supply, investment
    case, company-event feed, explanations, the brief's company lane, exit-on-evidence shadow,
    four-screen UI, new data, model bench.
- **Moved forward:** SA-048 to SA-051. **SA-049 is amended** with the owner's breadth floor:
  `portfolio.min_holdings: 10`, `max_holdings: 15`, `min_invested_inr: 1000000`, configurable
  and per portfolio (7 points after the 12 Oct decisions below). SA-046 and SA-051 gain
  one-schema and one-module notes.
- **STATE order after SA-011, confirmed by the owner on 12 Oct** ("ya continue on the new
  order"), with PR-011 moved up: FIX-007, PR-001, PR-002, PR-003, SA-050, SA-051, PR-004,
  PR-006, **PR-011**, PR-009, SA-048, SA-049, PR-005, PR-007, PR-008, PR-010, PR-012. The
  remaining SA stories follow as before. So **after SA-011 is accepted, "continue" selects
  FIX-007.**

**12 Oct (about 00:35–01:00 IST, same conversation): production baseline and owner decisions.**
Docs only; nothing committed, pushed, deployed or configured.

- **Baseline.** The owner ran the read-only probe
  (`analysis_data/review_20261011/portfolio_results_probe.py`) on 11 Oct. The sanitized
  figures are in review section 11:
  - 2 holdings and 81% cash. Since 10 Jul the portfolio is −0.5% against the Nifty's −8.2%: the
    cash, by accident, in a falling market.
  - 8 sales since 1 Aug, 4 wins. Expectancy is −2.2% per trade: winners were cut at +7.5% on
    average, losers ran to −11.9%.
  - Auditor exits: right at 10 sessions (7 of 10), wrong at 30 (6 of 7 sold stocks then beat the
    Nifty).
  - Shelf ideas beat the Nifty 13 times in 21 at 30 sessions; the held stocks lagged.
  - The brief repeated 32 of 57 items.
- **Defects confirmed** (code plus data):
  - weights are measured against the holdings, not equity, so ADD is locked;
  - a SWITCH ignores the entry band (WELCORP was bought 34% above it);
  - the shelf holds a liquid ETF (LIQUID1) and 7 ideas shelved before the gate existed.
- **Owner decisions:**
  - (1) The order above is confirmed.
  - (2) "Do as per recommendation but I need more data and so as the stocks." SA-049 D1:
    ₹2 L of paper capital through a new dated, owner-only DEPOSIT action, made at rollout. D2:
    `portfolio.target_holdings: 12`, about ₹83,000 each, between 10 and 15. SA-049 is now 7
    points. PR-011 becomes P1 and moves after PR-006.
- **Cards amended:**
  - SA-050 (3 points): equity denominator and one entry rule;
  - PR-004: only companies, cap by real industry, re-dive the pre-gate ideas;
  - PR-009: grade at 10 and 30 sessions; the gate needs both, with at least 15 matured
    disagreements at 30 sessions over at least 8 weeks;
  - PR-002: the red flag reads 30 sessions;
  - SA-049 and PR-011 as above.
- **The KT and PDF were deliberately NOT edited.** SA-011's review manifest covers them; the
  implementing stories carry these facts into the KT as current design.
- **Owner action, weekly until PR-002 ships:** re-run the same probe each Sunday evening with
  the usual `railway ssh` pipe, and paste it into a fresh conversation for comparison with
  section 11.

## START HERE — resume checklist, in order

**FIX-010 is ACCEPTED** by the fresh re-review of rework 1 (16 Oct, about 11:35–12:25 IST, session
stockagent-main-88, a new conversation opened with "continue"; peers idle). Receipt:
[review, "Re-review of rework 1"](evidence/FIX-010-review.md). STATE: `active_task: null`, FIX-010
`done`, **`next_task: PR-002`**, meaning its implementation in a new conversation ("continue"). No
production state was read and no notification was sent. **Committed at the owner's word**
("ya commit and push", about 13:20 IST): `4686150` (code), `3df1f6e` (docs: RR1's wording,
KT section 12's FIX-010 row `Done`, guide 11-K's status line, receipts), then the KT bump to
`3df1f6e` (edition 2026-10-16; section 1 states the owner's backfill); the push follows.
- **In one example.** On a Monday at 09:00 IST, Home's "Market pulse · today" reads "Last
  analysis 2 days ago" with the stale dot when Friday's 16:30 review was the last analysis of a
  shared stock. After a Saturday on which discovery shelved a stock it had just analysed, it reads
  "Last analysis 1 day ago". Before the rework it read "Updated recently", always.
- **What was accepted:** the uncommitted working tree on `c31136b` (input
  [FIX-010-manifest.json](evidence/FIX-010-manifest.json) `89787068…`, 19 files, 0 mismatches
  before and after; rework diff `279ccf94…` rebuilt by the re-reviewer), together with the
  committed `ec3f336`.
- **One low finding, RR1 (docs).** The KT's section 10 and guide 11-K promise "2 days ago" on
  every Monday. Saturday's discovery makes it "1 day ago" whenever it shelves a stock. The code
  is right. The fix is a wording change in FIX-010's commit; the receipt gives the exact text.
  Info items I9 and I10 need no change.
- **Checked:**
  - the review's story set, 170 passed;
  - the first review's trace, 13 of 13;
  - the re-reviewer's own 17 cases: Monday with and without a Saturday shelf dive, the label
    boundaries, and a backfill apply → remove → apply with live rows;
  - the old code fails 14 of 14 of those label cases, and the old backfill leaves 8 rows for 6
    analyses;
  - mutant X1 is caught;
  - in a real browser, an expired session drops the list; the old frontend fails that case;
  - `npm run test:frontend` 30/30, `check_kt_docs` `[]`, full suite 4597 passed, 12 skipped, 0 failed.
- **For the owner, at your word:**
  - Commit the rework. With it go RR1's wording, KT section 12's FIX-010 row `Open` → `Done`,
    the KT header bump, the PDF rebuild and guide 11-K's status line.
  - Push in a job-free window, never 16:25–17:15 IST.
  - After the deploy, close and reopen the app once, then run guide 11-K.
  - Unchanged: after today's 16:30 review, re-run
    `analysis_data/pr001/rereview1/score_history_probe.py` (rows above 1,082, `last_run_at`
    today). KT section 1's "Score history" row is updated with the next docs commit.
- **Next:** PR-002, the weekly results scorecard, in a new conversation.

**FIX-010 REWORK 1 is IMPLEMENTED** (16 Oct, about 09:20–11:00 IST, session stockagent-main-5f, a
new conversation opened with "continue"; ten peers idle). Receipt:
[implementation, "Rework 1"](evidence/FIX-010-implementation.md). STATE: `active_task: null`,
FIX-010 `review_required`, **`next_task: FIX-010`**, meaning its fresh **re-review** in a new
conversation, then PR-002. Nothing was committed, pushed or deployed; no production state was read
and no notification was sent. The rework is uncommitted on `c31136b`.
- **In one example.** On Monday at 09:00 IST, after Friday's 16:30 review, Home's "Market pulse ·
  today" now reads "Last analysis 2 days ago" with the stale dot, not "Updated recently". Runs
  2.5 hours old read "Updated 2h ago".
- **What changed:**
  - **M1:** `_freshness_label` reads a naive `run_at` as UTC; an unreadable time reads "Analysis
    time unknown", stale; its broad `except` left the guard's baseline.
  - **L1:** the gate test runs both exits with enforce.
  - **L2:** sign-out (`saClearToken`, also on expiry and account deletion) drops the verdict
    changes, and an answer that arrives after a sign-out is discarded.
  - **L3:** guide 11-K rewritten (a managed stock outside the 16; the owner's held stock analysed
    on request first; the owner's own check; time labels; an account switch).
  - **I5:** the backfill copies nothing from a minute before a stock's first live row on.
- **Checked:** 13 new Python tests and 2 browser tests, all failing on the reviewed code or the
  matching variant; the reviewer's trace 13 of 13; the review's story set 170 passed;
  `npm run test:frontend` 30/30; `check_kt_docs` `[]` (PDF rebuilt); full suite **4597 passed,
  12 skipped, 0 failed**. Review input [FIX-010-manifest.json](evidence/FIX-010-manifest.json)
  `89787068…` (19 files; the first input stays as `FIX-010-manifest-review1.json`); rework diff
  `279ccf94…` (38,024 bytes, 11 paths, `git diff c31136b`). Tooling in the ignored
  `analysis_data/fix010/rework1/` (`rw_swap_plugin.py`, `fe_variants.py`, `rw_digest.py`).
- **Next, in order:** FIX-010's fresh re-review in a new conversation ("continue"); then PR-002.
  Unchanged: after today's 16:30 review, the owner re-runs
  `analysis_data/pr001/rereview1/score_history_probe.py` (rows above 1,082, `last_run_at` today);
  KT section 1's "Score history" row is updated with the next docs commit.
- **For the owner:** nothing to do now. After the re-review accepts it, the fix needs a commit
  and deploy at your word; then close and reopen the app once.

**FIX-010's fresh review: CHANGES REQUESTED** (16 Oct, about 08:30–09:05 IST, session
stockagent-main-0d, a new conversation opened with "continue"; peers idle). Receipt:
[review](evidence/FIX-010-review.md). STATE: `active_task: null`, FIX-010 `changes_requested`,
**`next_task: FIX-010`**, meaning **rework 1** in a new conversation, then a fresh re-review in
another, then PR-002. Production verification stays `pending_observation`: the code is live, and
the probe after today's 16:30 review still checks the writer. Nothing was committed, pushed or
deployed; no production state was read.
- **In one example.** On Monday at 09:00 IST, the newest analyses are Friday's. Home's "Market
  pulse · today" reads "Updated recently", with no stale dot. The truth is "Last analysis 2 days
  ago", stale. The label never states an age: runs 5.5 hours old also read "Updated recently",
  not "Updated 5h ago".
- **Must fix, M1 (medium).** `_freshness_label` (`services/api/routes/ui_data.py:633-647`)
  subtracts the writer's naive UTC `run_at` from an aware "now". The `TypeError` falls through to
  a fixed "Updated recently", not stale. FIX-010 made this code reachable (it never met a real
  row before). Fix: read a naive `run_at` as UTC. Test through the writer's rows for under 6 h,
  6–24 h and over 24 h, and stale over 12 h. The reviewer's variant X2 shows the trace passing
  with that one line.
- **Recommended in the same rework:**
  - L1: an async-exit test with enforce (mutant X1 survives the story file; the reviewer's
    `analysis_data/fix010/review/test_rv_async_gate.py` catches it);
  - L2: clear the learnings list on sign-out or before the re-fetch (a failed re-fetch keeps the
    previous viewer's list);
  - L3: guide 11-K (the 16:30 review analyses managed tickers only, so the owner's held stock
    needs an analysis on request first).
  - Optional: I5, the backfill's per-stock cut-off (reproduced; production's run is unaffected).
- **What holds:** the writer at both exits after the gate; every entry point, through both
  registries; every store reader classified; the privacy rule for the owner, two members and an
  anonymous caller through the real server with Atlas on; the watchlist row; the dated empty
  case; the backfill, including screens on backfilled rows only (today's production state).
- **Checked:** input `900c8f27` at `445d7fa` (guide after its five commit-time status lines),
  preserved as `FIX-010-manifest-review1.json`; code diff `77cac0bd` (`9db8ba7..ec3f336`); story
  tests 134 passed; reviewer's trace 9 of 12 (M1 twice, I5); `npm run test:frontend` 28/28;
  `check_kt_docs` `[]`; full suite 4584 passed, 12 skipped, 0 failed. Reviewer tooling in the ignored
  `analysis_data/fix010/review/` (`rv_verify.py`, `test_rv_trace.py`, `test_rv_async_gate.py`,
  `rv_swap_plugin.py` with `RV_SWAP=base|X1|X2`, `conftest.py` for the hermetic boundary).
- **For the owner:** nothing new today. The after-16:30 probe stays as planned. The M1 fix needs
  a deploy at your word after its re-review.

**Backfill APPLIED** (owner, 16 Oct 08:23:59 IST, production, counts only). It inserted 1,082 rows (83 stocks, 26 Aug to 15 Oct) and skipped nothing. No live row existed yet, so there is no double copy (I5). The backup is `scores.db.bak-20261016T025359Z`, and `SCORE_BACKFILL=remove` undoes it. The probe at 08:25 IST confirmed it: `score_history` holds 1,082 rows (83 stocks, 26 Aug 11:03 to 15 Oct 11:16 UTC), exactly the run log. No live row exists yet. FIX-010 production verification is now `pending_observation`. **Next check:** after today's 16:30 review, re-run `analysis_data/pr001/rereview1/score_history_probe.py`; rows should be above 1,082, with `last_run_at` today. Then update KT section 1's "Score history" row with the next docs commit. Uncommitted.

**PUSHED** `4c85eec..c31136b` at 21:48:34 IST on 15 Oct, at the owner's word, in the job-free window before the 23:00 jobs. Railway redeploys on push; `railway deployment list` (read-only) showed `c31136b` SUCCESS at about 21:54 IST, and the 13 Oct deployment of `4c85eec` (FIX-008) SUCCESS. The owner checks `/health`, closes and reopens the app once, then runs the checks in the block below. This push note is uncommitted; it goes with the next commit.

**Backfill dry run** (owner, 16 Oct about 08:20 IST, production, counts only): it would insert 1,082 rows (83 stocks, 26 Aug to 15 Oct). Nothing was skipped, and no live row exists yet. **For FIX-010's review (I5):** the cut-off is per stock, at the first live row. An analysis logs its `run_summaries` row a few milliseconds before its score row, so a run made after the deploy but before the backfill would be copied once more, with the same verdict. That means no false change, but one extra row. Applying before the first post-deploy analysis avoids it.

**FIX-010 was IMPLEMENTED and, with PR-001 and FIX-009, COMMITTED** (push at the owner's word follows; its note is added after) (15 Oct, about
20:30–21:47 IST, in the same conversation as PR-001's re-review). The owner said: "ya go ahead on
you suggestions and commit and push at the end". Receipt:
[implementation](evidence/FIX-010-implementation.md). STATE: `active_task: null`, FIX-010
`review_required`, and **`next_task: FIX-010`**, meaning its fresh **review** in a new
conversation, of the committed code. No notification was sent, no production variable changed,
and the backfill was not run.
- **In one example.** The member holds DIXON, and the owner holds BEL; neither is managed or on
  the shelf. The 16:30 analysis turns DIXON from BUY to SELL. Now:
  - the row is written;
  - Home shows DIXON's score and verdict, and Portfolio lists "DIXON: BUY → SELL";
  - the chat's current verdicts include DIXON;
  - none of those screens names BEL to the member.
- **What changed:**
  - **The write:** every analysis writes its score-history row at the orchestrator's single exit
    (both paths), after the decision gate. A failed write is a warning.
  - **Who sees which stock:** lists read from the store name only shared stocks (the built-in
    universe, the managed list and active shelf ideas) plus the viewer's own holdings and
    watchlist. That covers Portfolio, search, the chat, Home's market panes, the market summary
    and the analytics sector comparison. An anonymous request owns nothing.
  - **A crash avoided:** Home's "This month" votes read the writer's per-agent objects. They made
    `/ui/bootstrap` fail (reproduced on the old code).
  - **Watchlist:** a watched stock outside the 16 autos shows its analysis.
  - **Portfolio:** the empty case is dated, and a sign-in re-fetches the list.
  - **Backfill:** a dry-run-by-default script copies past runs from `run_summaries`.
- **Checked:** 32 new tests (expected values from the fixtures; rows by the real writer); on the old code 28 fail, and mutants M1–M11 are caught; the browser suite 11/11 (incl. sign-in re-fetch); `npm run test:frontend` 28/28; full suite **4584 passed, 12 skipped, 0 failed**.
- **Commits:** `a16b617` FIX-009, `9db8ba7` PR-001 (its accepted bytes), `ec3f336` FIX-010; `445d7fa` docs; then the KT bump that records them.
- **For the owner:**
  1. **Confirm the deploy:** `railway deployment list` and `/health`, then the checks below.
     After the deploy, close and reopen the app once (PR-001 L3).
  2. **Backfill (your call):**
     - Dry run first:
       `railway ssh "cd /app && echo $(gzip -9c scripts/backfill_score_history.py | base64 -w0) | base64 -d | python -c 'import sys,zlib;exec(zlib.decompress(sys.stdin.buffer.read(),31))'"`.
     - To write, the same command with `SCORE_BACKFILL=apply` placed before `python`.
     - With it, Portfolio shows the last 30 days' changes the next morning. Without it, Home fills
       after Friday's 16:30 review.
  3. **After Friday's 16:30 review:** re-run the probe
     (`analysis_data/pr001/rereview1/score_history_probe.py`). Rows should be above 0, and the
     last run should be that day.
- **Next, in order:**
  1. FIX-010's fresh review in a new conversation ("continue").
  2. Then PR-002.
  3. The FIX-008 deploy confirmation and the FIX-007, SA-011 and FIX-008 rollout checks still
     stand, now with this deploy.

**FIX-010 was ADDED** (15 Oct, about 18:10 IST, same conversation as PR-001's re-review,
planning only). The owner ran the read-only probe and chose "ya add the score-history fix before
PR-002". Card: [FIX-010](stories/FIX-010.md) (P0, 3 points, no dependencies), placed directly
before PR-002. STATE: `active_task: null`, **`next_task: FIX-010`** (implementation, not
started). Nothing was committed, pushed or deployed and no notification was sent. The KT was not
edited; the implementation adds its section 12 row.
- **Measured in production** (15 Oct, 12:38 UTC, counts only):
  - the score history holds **0 rows**;
  - 1,082 analyses with a verdict were logged elsewhere (`run_summaries`): 83 stocks, from 26 Aug
    to today;
  - in the last 30 days, 747 analyses of 64 stocks, with **173 verdict changes**.
  - So every member screen that reads analysis results shows none. This is recorded in the PR-001
    review receipt, section "U1 routed".
- **In one example.** The member holds WELCORP, and the 16:30 analysis turns it from BUY to SELL.
  - Today, Home says "Not analysed" (a made-up 0.50 NEUTRAL before PR-001), and Portfolio shows
    no change.
  - After FIX-010, Home shows WELCORP's dated score, and Portfolio lists "WELCORP: BUY → SELL".
  - A stock that only the owner asked the chat about never appears on the member's screens.
- **What the card asks for:**
  - every analysis saves its score row again, at the one exit that already logs `run_summaries`;
  - screens that list stocks from the store name only the viewer's holdings and watchlist, the
    managed tickers and shelf ideas. Without this, restoring the write would put every analysed
    stock into every account's chat context;
  - watchlist rows outside the 16 automobile stocks read the store;
  - the empty case is dated;
  - an optional backfill from `run_summaries`.
- **For the owner, at rollout (later):** whether to run the backfill.
  - With it: the morning after the deploy, Portfolio shows the newest of the last 30 days'
    changes and Home shows scores.
  - Without it: Home fills after the next 16:30 review, and a change shows only after a stock's
    next differing analysis.
  - Nothing else to decide now.
  - PR-001 and FIX-009 can be committed whenever you say; shipping PR-001 first is fine.
- **Next, in order:**
  1. FIX-010's implementation in a new conversation ("continue"), then its fresh review in
     another.
  2. Then PR-002. The FIX-008 deploy confirmation and rollout checks below still stand.

**PR-001's fresh re-review: ACCEPTED** (15 Oct, about 16:20–17:20 IST, a new conversation opened
with "continue"). Receipt: [review](evidence/PR-001-review.md), section "Re-review of rework 1".
STATE: `active_task: null`, PR-001 `done`, production verification `pending_deployment`, and
**`next_task: PR-002`** (not started). Nothing was committed, pushed or deployed, no production
state was read and no notification was sent. The re-review changed no reviewed file.
- **In one example.** Sixteen stocks were analysed every weekday for six weeks, nearly always
  with the same verdict, and twelve real changes happened.
  - Portfolio reads "The 10 most recent changes in the analysed stocks", newest first, with the
    two oldest left out, then "Latest forecast misses".
  - No card repeats a verdict.
  - The rows went through the real writer, server and browser. The expected cards come from the
    re-reviewer's own oracle.
- **Checked:**
  - input `1c7ea945`; rework diff `0d8c3604`, rebuilt with the re-reviewer's own script;
  - the re-reviewer's probe: rows written through the real `ScoreStore.save`; twelve random
    histories, a deep history and misses all match its oracle. On the review-1 code all 14 fail;
  - mutants S1–S7: each is caught by the probe or the story's tests;
  - the first reviewer's trace passes unchanged (7), Learn included;
  - `npm run test:frontend` 27/27; the layout audit passes;
  - full suite **4552 passed, 12 skipped, 0 failed**.
- **Findings:** no critical or high; the rework's M1, L1, L2 and I1 are fixed.
  - **U1 (medium, pre-existing, outside PR-001): nothing writes the score history.**
    - `ScoreStore.save` has had no caller since 21 Apr 2026: `ce1eeb5` removed it from the old
      scheduler. Analyses are logged only in `run_summaries`.
    - This is code inspection; production was not read.
    - If production's store is empty or old:
      - Portfolio's "Recent verdict changes" can list only changes from before 21 Apr, or none.
        With only forecast misses, it says "No verdict changes in the analysed stocks".
      - Home's watchlist says "Not analysed" for a stock analysed every day, and always for a
        stock outside the 16 autos.
      - Guide 11-J's change cards cannot appear.
  - L1 (low, test gap): the story's tests do not pin three rules of the change list: same-day
    order, same-second ties and the 90-run lookback. The code is correct. Routed to SA-031, with
    fixtures.
  - I1–I3 (info):
    - a KT sentence to soften (routed to SA-031);
    - forecast misses can be partial when one stock's feedback log is unreadable;
    - two SQLite side files left by the probe's local dry run: `data/telemetry.db-wal` (0 bytes)
      and `-shm`. My delete was blocked; they are safe to delete.
- **For the owner:**
  1. **Decide U1's route.** Recommended: a small FIX card before PR-002. It would save each
     analysis's score row again (or read changes from `run_summaries`) and decide what Portfolio
     says when only misses exist.
     - Example: a stock flips BUY → SELL in the 16:30 analysis. With the fix, the next Portfolio
       visit shows it. Without it, Portfolio never does, and Home keeps calling the stock "Not
       analysed".
  2. **Run the read-only probe** and paste the output. It prints counts and dates only:
     `railway ssh "cd /app && echo $(gzip -9c analysis_data/pr001/rereview1/score_history_probe.py | base64 -w0) | base64 -d | python -c 'import sys,zlib;exec(zlib.decompress(sys.stdin.buffer.read(),31))'"`
  3. Commit and push only at your word, in a job-free window. PR-001 and FIX-009 ship together.
     - With the commit: KT section 12's PR-001 and FIX-009 rows go from `Open` to `Done`, with the
       KT header bump, a PDF rebuild and guide 10-H's status line.
     - After the deploy: close and reopen the app once (L3), then run guide 11-I.
- **Next, in order:**
  1. PR-002 in a new conversation ("continue"), unless you route U1 first.
  2. The FIX-008 deploy confirmation and rollout checks below still stand.

**PR-001 rework 1 was IMPLEMENTED** (15 Oct, about 10:35–14:45 IST, a new conversation opened
with "continue"). Receipt: [implementation](evidence/PR-001-implementation.md), section "Rework 1".
STATE: `active_task: null`, PR-001 `review_required`, and **`next_task: PR-001`**, meaning its
fresh **re-review**. Nothing was committed, pushed or deployed, no production state was read and
no notification was sent.
- **In one example (M1).** MARUTI turned BUY on 9 Oct, TATAMOTORS SELL on 10 Oct and BOSCHLTD
  BUY on 13 Oct; eight other stocks were re-analysed in July with the same verdict.
  - Before: "Recent verdict changes · 10 changes", with eight "NEUTRAL → NEUTRAL" cards and no
    BOSCHLTD.
  - Now: "3 changes in the analysed stocks", BOSCHLTD first. Forecast misses are listed under
    "Latest forecast misses" and not counted. A full list reads "The 10 most recent changes".
- **What changed:**
  - `ui_data.py`: a change is a verdict that differs from the run before it; every kept run is
    read; all changes are sorted newest first, then cut to 10; misses follow, newest first, at
    most 5; a failed read sends nothing rather than a partial list.
  - `portfolio.jsx`: the heading counts the change cards only.
  - `learn.jsx` (L1): no "Continue where you left off", no "Recommended next" (MARUTI and a false
    reason), no progress percentage.
  - The guard catches unformatted figures (L2). The Agents page shows no "0 agents" (I1).
  - The moved agent-score parse catches `ValueError`, not every exception, and the broad-except
    baseline loses its now-stale `get_learnings` line (154 to 153).
- **Design calls (delegated, in the receipt, D7–D11):** no date window; every change listed,
  several per stock included; misses stay in `{items}`; the full-list wording; no
  universe-ticker guard.
- **Tests:** story file 44 tests (was 25) and browser suite 10 (was 9); the review-1 code fails 7 and the review-1 screens 3; server mutants R1-R14 and frontend mutants G1-G8 all caught; the reviewer's own trace passes unchanged (its M1 probe now shows 3 changes, BOSCHLTD first); npm run test:frontend 27/27; layout audit (fixture mode) passes; full suite 4552 passed, 12 skipped, 0 failed; runtime data unchanged.
- **For the re-review:** input `PR-001-manifest.json` (`1c7ea945…`, 23 files); rework diff
  `0d8c3604…` (56,667 bytes) from `analysis_data/pr001/rework1/base/`; cumulative diff
  `973ee2d5…` (271,308 bytes); both from `rework1/rw_digest.py`. Also there:
  `rw_swap_plugin.py` + `run_swaps.sh` (`RW1_SWAP=base|R1..R14`), `rw_fe_mutants.py` (`base`, G1–G8).
- **For the owner:** nothing to decide. The review's rollout note (L3) stands: on a device that
  already has the app, the first open after the deploy can be blank or old; close and reopen it.
- **Next, in order:**
  1. PR-001's fresh re-review in a new conversation ("continue").
  2. Then PR-002. The FIX-008 deploy confirmation and rollout checks below still stand.

**PR-001's fresh review: CHANGES REQUESTED** (14 Oct, about 12:00–13:25 IST, a new conversation
opened with "continue"). Receipt: [review](evidence/PR-001-review.md). STATE: `active_task: null`,
PR-001 `changes_requested`, and **`next_task: PR-001`**, meaning **rework 1**. Nothing was
committed, pushed or deployed, no production state was read and no notification was sent. The
review changed no reviewed file. The review input is preserved as
`evidence/PR-001-manifest-review1.json` (`a4b459b7…`).
- **In one example (M1, must fix).** MARUTI and TATAMOTORS changed verdict this month and BOSCHLTD
  turned BUY yesterday. Eight other stocks were re-analysed in July with no change.
  - The Portfolio page says "Recent verdict changes · **10 changes**". It lists the two changes
    and eight "NEUTRAL → NEUTRAL" cards from 2 July.
  - Yesterday's BOSCHLTD change is missing, because the list keeps the first ten stocks in a
    fixed order.
  - Reproduced through the real server and browser.
- **L1 (low, must fix).** With every market API down, the Learn page still shows "MARUTI". It
  also tells the member "Picked because you finished 'Reading a verdict'" while every path now
  shows 0% done.
- **Recommended in the same rework:** L2, the guard misses `Nifty Auto 22847`, `+1%` and
  `₹18420`; I1, "0 agents · automobile" while the agents are unavailable.
- **Everything else the card asks for works** in the reviewer's own trace. It uses the real app
  with sign-in, the real `/ui` routes and Chromium, and compares against figures computed from the
  fixture market:
  - "Good morning, Ravi." at 09:00 IST on a Los Angeles device;
  - "Nifty 50 -0.03% on 13 Oct." and a dated index box;
  - "—" for failed prices and "Not analysed" for unanalysed stocks;
  - no invented figure with the APIs down;
  - operator tools for the owner only, and member writes refused with 403.

  The same trace fails on the original code.
- **Test results:**
  - the implementer's tests and `npm run test:frontend` (26) pass;
  - base `ui_data.py` fails 13 of 13 server tests;
  - reviewer mutants X1–X6 are all caught;
  - full suite 4533 passed, 12 skipped, 0 failed (17 min 34 s).
- **For the owner:** nothing to decide.
  - Rollout note, firmer than before (L3): the first open after the deploy can be a **blank page**
    on a device that already has the app. Close it and open it again before checking.
- **Next, in order:**
  1. PR-001 rework 1 in a new conversation ("continue"): M1 and L1, plus L2 and I1 if small. Then
     a fresh re-review in another.
  2. The FIX-008 deploy confirmation and rollout checks below still stand.

**PR-001 was IMPLEMENTED** (13 Oct about 22:38 IST to 14 Oct about 01:00 IST, a new conversation
opened with "continue"). Receipt: [implementation](evidence/PR-001-implementation.md). STATE:
`active_task: null`, PR-001 `review_required`, and **`next_task: PR-001`**, meaning its fresh
**review**. This phase committed, pushed and deployed nothing, read no production state and sent
no notification.
- **In one example.** The test member opens the app at 09:00 IST.
  - Before: "Good afternoon, Aditi. Auto sector +1.24% today.", a fixed "Nifty Auto 22,847", a "Run
    on MARUTI" button, the Prompt Lab, Analytics, Logs and RL Monitor chips, and on Portfolio
    "Missed gain +₹18,420", which is a score change × 10,000.
  - Now: "Good morning, <the member's name>." and "Nifty 50 −0.42% on 12 Oct." from the server;
    the Nifty box shows its level and "as of" date; Portfolio lists dated verdict changes with no
    rupee figure; no operator chip, menu entry, tuning control or Tweaks panel. If a request
    fails, the screen says the data is unavailable instead of showing samples.
- **What changed:**
  - `ui_data.py`: `/ui/learnings` sends dated verdict changes only; `/ui/bootstrap` adds a dated
    `NIFTY50` and drops every stand-in (random series, padded drivers, weights as votes, a 0.00%
    failed sector); `/ui/nifty-ranges` is the Nifty 50 by calendar span with value and date.
  - Frontend: samples only under `?demo=1` (`demo-fixtures.js`, a "Sample data" strip); the hero,
    Nifty box, unavailable states, watchlist dashes; Portfolio unavailable instead of mock;
    Agents read-only for members; operator tools only for the owner's `/auth/me` role (the
    server guards are unchanged); `sw.js` v9; the layout audit runs on `?demo=1`.
- **Design calls (delegated, in the receipt, D1–D6):** one sample switch (`?demo=1`); learnings
  name the verdict move, not a user action; the same rule applied to the other stand-ins; gating
  fails closed; the account helpers sit in `index.html` so the first open after a deploy (cached
  old `.jsx`) still renders; a pre-existing Portfolio overflow at 360 px fixed (the audit met it
  once it ran on the samples).
- **Tests:** 34 new (25 Python incl. the browser wrapper, 9 browser). The base fails 13 of 13
  server tests and 7 of the 8 browser behaviour tests; server mutants 15/15 and frontend mutants
  16/16 are caught; the layout audit passes in fixture and live mode. Full suite **4533 passed, 12 skipped, 0 failed (7 min 50 s)**;
  runtime data unchanged.
- **For the review:** input `PR-001-manifest.json` (`a4b459b7…`, 21 files); diff
  `ac0b7e75…` (237,159 bytes) from the snapshot `analysis_data/pr001/base/`
  (`diff_digest.py` checks each base file against `4c85eec` or FIX-009's manifest). Also there:
  `swap_plugin.py` + `run_swaps.sh` (`PR001_SWAP=base|M1..M15`), `fe_mutants.py` (F1–F16),
  `base_frontend/`, `stale_jsx_check.mjs`, `overflow_probe.mjs`, `audit_server.py`.
- **For the owner:** nothing to decide. Rollout note (L1): on a device that already has the app,
  the first open after the deploy may still show the old screens; open it again. FIX-009's four
  docs now also carry PR-001's edits (layered; its code and tests untouched), so the next docs
  commit carries both.
- **Next, in order:**
  1. PR-001's fresh review in a new conversation ("continue").
  2. Then PR-002. The FIX-008 deploy confirmation and rollout checks below still stand.

**FIX-009 was ACCEPTED** by its fresh review (13 Oct, about 16:34–16:56 IST, a new conversation
opened with "continue"). Receipt: [review](evidence/FIX-009-review.md). STATE: `active_task: null`,
FIX-009 `done`, production verification `pending_deployment`, and **`next_task: PR-001`** (not
started). Nothing was committed, pushed or deployed, no production state was read and no
notification was sent. The review changed no reviewed file.
- **In one example.** The owner watches QOWNWAT. Members A and B both hold QBOTHHLD. Member B also
  holds the shelf idea QSHELFHD and has no push subscription. The Sunday 18:00 index check finds
  that all of them changed.
  - The owner hears about QOWNWAT and the shelf's ideas.
  - Member A hears about its own stocks and the shelf's.
  - Member B gets one email with QBOTHHLD and QSHELFHD, the shelf idea once.
  - Nobody is told about another account's own stock.
- **Checked:**
  - input `11c2c620` and diff `57e5467f`, rebuilt with the reviewer's own commands;
  - on a blob-checked copy of the base, 17 of the 40 related tests fail, 11 of the 15 new ones on
    behaviour;
  - the reviewer's own trace passes. It runs from the scheduler's Sunday job with Atlas's real
    outbox and drainer, three accounts and each Inbox over HTTP. It fails on the base;
  - full suite **4508 passed, 12 skipped, 0 failed (6 min 56 s)**; runtime data unchanged; the PDF
    matches its source.
- **Findings:** no critical, high or medium.
  - L1 (low, test gap): no test pins that the accounts read after an unreadable one still get
    their own notices. A `break` in place of `continue` passes all 40 tests, because the failing
    member is read last. The code is correct. Routed to SA-031, with the fixture.
  - I1 (info): with Atlas on, an account with no push subscription now gets its own index notice
    by email; its push row is dead-lettered with a warning, as a brief to it is today. Both
    production accounts have push on.
  - I2 (info): guide 10-H gets its status line with the commit.
- **For the owner:** nothing to decide. FIX-009 ships in a later commit and deploy, at the owner's
  word, in a job-free window (not Sunday 17:50–18:30 IST). With the commit: KT section 12's FIX-009
  row `Open` to `Done`, the KT header bump, a PDF rebuild and the 10-H status line. After the
  deploy: guide 10-H at the next index change to a held or watched stock.
- **Next, in order:**
  1. PR-001 in a new conversation ("continue"), then its fresh review in another.
  2. The FIX-008 deploy confirmation and rollout checks below still stand.

**FIX-009 was IMPLEMENTED** (13 Oct, about 15:32–16:30 IST, a new conversation opened with
"continue"). Receipt: [implementation](evidence/FIX-009-implementation.md). STATE:
`active_task: null`, FIX-009 `review_required`, and **`next_task: FIX-009`**, meaning its fresh
**review**. This phase committed, pushed and deployed nothing, read no production state and sent
no notification.
- **In one example.** The owner watches BBB, the test member holds DDD, and the discovery shelf
  lists EEE. The Sunday index check finds that all three changed.
  - Before: both accounts were told about BBB, DDD and EEE.
  - Now: the owner hears about BBB and EEE, the member about DDD and EEE. An account's own stocks
    come in one notice, the shelf idea in another.
- **What changed:** `core/delivery/index_watch.py` (and one docstring in `alerts.py`).
  - A change to a shelf idea goes to everyone, by `emit_alerts_broadcast`, as a shelf add does.
  - Any other change goes only to the accounts that hold or watch the stock, by
    `emit_alerts(..., user_id=)`, one bundle per account.
  - An account whose portfolio cannot be read misses its own changes that run, with a warning;
    they are never sent to anyone else.
- **Design call (delegated, recorded in the receipt).** A shelf idea that an account also holds
  reaches it once. An account with no push subscription is outside the shelf's audience, so it
  gets that idea in its own notice instead of not at all.
- **Tests:** 15 new. On base `4c85eec` 11 of them fail on behaviour; 11 of 11 mutants are caught.
  Full suite **4508 passed, 12 skipped, 0 failed (14 min 12 s)**; runtime data unchanged.
- **For the review:** input `FIX-009-manifest.json` (`11c2c620…`, 11 files); diff
  `57e5467f…` from `4c85eec` (`analysis_data/fix009/diff_digest.py`). Also in the ignored
  folder: `swap_plugin.py` with `run_swaps.sh` (`FIX009_SWAP=base|M1..M11`), `base_snapshot.py`,
  `mutants.py`.
- **For the owner:** nothing to decide. FIX-008 is already pushed (15:29), so FIX-009 ships in a
  later commit and deploy, after its review is accepted and at the owner's word. KT section 12's
  FIX-009 row stays `Open` until that commit.
- **Next, in order:**
  1. FIX-009's fresh review in a new conversation ("continue").
  2. Then PR-001.

**Committed 13 Oct about 14:40 IST, at the owner's word ("go ahead commit and push"). Pushed
`33ae170..4c85eec` at 15:29:02 IST; deploy confirmation pending.** Railway redeploys at about 15:37.
- `1acb17b` FIX-008 code, config and tests (the reviewed bytes); `e85da94` the docs, evidence, the
  FIX-009 card, STATE and HANDOFF; then the KT bump to `e85da94` (section 12's FIX-008 row `Done`;
  section 1 says production runs the inspected code once this afternoon's deploy is confirmed;
  PDF rebuilt; deep-dive headers; guide 10-G and 12-K status lines).
- `docs/README.md` (the owner's own probe line) is left uncommitted.
- **Why the push waited:** at 14:37 an 8-minute redeploy would have reached the 14:55–15:05
  window (15:00 intraday macro news).
- **Rollout order:** SA-011's 09:07 deploy is not yet confirmed and its first backlog read not
  triaged. After this deploy the 06:30 watchdog warns the owner once a day (counts and the top
  three issues) until the backlog is triaged; nothing reaches the member.
- **After the deploy:** the owner confirms `railway deployment list` and `/health`, runs
  FIX-007's and SA-011's rollout checks and FIX-008's (review receipt), and triages the backlog
  (`GET /ops/errors` or `scripts/prod_errors.py`). Then KT section 1 goes back to "Production
  runs the inspected code".

**FIX-008 was ACCEPTED** by its fresh review (13 Oct, about 12:37–13:10 IST, a new conversation
opened with "continue"). Receipt: [review](evidence/FIX-008-review.md). STATE: `active_task: null`,
FIX-008 `done`, production verification `pending_deployment`, and **`next_task: FIX-009`** (not
started; see L2). Nothing was committed, pushed, deployed or configured, no production state was read and
no notification was sent.
- **In one example.** A member-named portfolio file is found corrupt at 02:10, and the 06:30
  watchdog runs on the next three mornings.
  - The quarantine notice reaches the owner's two devices once each and the owner's mailbox once.
    The member gets nothing, and no outbox row is queued for the member.
  - The archived error becomes a backlog issue. The owner gets one warning each morning until it is
    triaged, then one "resolved", then silence. The member is refused (403) on both the read and
    the triage.
- **Checked:**
  - input `a7a7b58e` and diff `48b3521d`, rebuilt;
  - the implementer's tests on a true copy of `33ae170`: 19 of 22 fail, on behaviour;
  - own trace with Atlas's real outbox and drainer, the real log archive, the scheduler's job and
    the HTTP Inbox: passes here, fails on the base;
  - full suite **4493 passed, 12 skipped, 0 failed (10 min 5 s)**; runtime data unchanged; the PDF matches its source.
- **Findings:** no critical, high or medium.
  - L1 (low, docs): guide 10-G said the member's Alerts tab shows no operator notice at all. By the
    owner's I1 decision, copies from before the deploy stay. Fixed in 10-G.
  - **L2 (low, privacy, pre-existing, outside this card): routed as [FIX-009](stories/FIX-009.md).** Example: only the
    owner watches BBB. When BBB leaves the NIFTY 50, the test member's phone is told too, because
    the index-watch notice is built from every account's holdings and watchlist and sent to all.
    The owner delegated the call (about 14:15 IST, "do whichever is recommended"). FIX-009 (P2,
    1 point) makes each account hear only about its own holdings and watchlist, plus shelf ideas.
    It is ordered next, before PR-001, under the privacy-first rule, so FIX-008 and FIX-009 can
    ship in one deploy with one rollout check. Today the only member is the owner's test account.
    KT not edited: FIX-009's implementation adds its section 12 row, as FIX-008 did.
  - L3 (low, test gap): no test pins the Inbox's per-account limit. Routed to SA-031, with I2 (a
    stale Auth column in CODEBASE). I1 and I3 are infos.
- **For the owner:**
  1. Rollout, unchanged: confirm SA-011's and FIX-007's deploy and their checks, and triage
     SA-011's first backlog read. Then commit and deploy FIX-008 (with FIX-009 once it is
     accepted, if the owner prefers one deploy) at the owner's word, in a job-free window. With the commit: KT section 12's FIX-008 row `Open` to `Done`, the KT
     header bump and a PDF rebuild. The production checks are in the review receipt.
- **Next, in order:**
  1. FIX-009 in a new conversation ("continue"), then its fresh review in another.
  2. Then PR-001. The open items below still stand.

**FIX-008 was IMPLEMENTED** (13 Oct, about 08:25–09:20 IST, a new conversation opened with
"continue"). Receipt: [implementation](evidence/FIX-008-implementation.md). STATE:
`active_task: null`, FIX-008 `review_required`, and **`next_task: FIX-008`**, meaning its fresh
**review**. This phase committed, pushed and deployed nothing, read no production state and sent
no notification.
- **In one example.** The 06:30 watchdog finds the backup not confirmed off-site.
  - Before: the owner's devices and the test member's phone each got a push, each account an
    email, and the member's Inbox listed it.
  - Now: the owner's devices and the owner's mailbox, once. The member gets nothing. A discovery
    shelf add still reaches both.
- **What changed:**
  - `emit_owner_alerts()` for the seven operator callers. Its audience is the `users.db`
    accounts with role `owner`, else the default user; a failed lookup also narrows to the
    default user.
  - The market callers are unchanged.
  - The Inbox (`GET /delivery/alerts`) lists only the caller's records. This is a recorded
    scope decision: without it the member still reads operator notices there.
  - `config/milestones.yaml` gains `error_backlog_triaged`. The Edit tool worked for this
    addition; the earlier registry allow rules are no longer in `.claude/settings.local.json`.
- **Tests:** 22 new. On base `33ae170` 18 fail; 12 of 12 mutants and 4 of 4 guard plants are
  caught. Neighbours 502 passed. Full suite **4493 passed, 12 skipped, 0 failed** (10 min
  28 s) on the manifest's code and test bytes; runtime data unchanged. The KT wording and PDF
  changed during the run (no test reads them), and `check_kt_docs` ran after.
- **For the review:** input `FIX-008-manifest.json` (`a7a7b58e…`, 24 files); diff
  `48b3521d…` from `33ae170` (`analysis_data/fix008/diff_digest.py`). Also in the ignored
  folder: `swap_plugin.py` with `run_swaps.sh` (`FIX008_SWAP=base|M1..M12`), `guard_probe.py`,
  `base_snapshot.py`.
- **Owner decisions (13 Oct about 12:35 IST, "yup i agree"):**
  - I1: leave the old copies in the test member's Inbox. Only that pre-fix account has them, and
    they drop off its 20-item Alerts tab as new notices arrive. No production data change.
  - The `milestones.yaml` allow rules stay off. The owner approves each registry deletion when
    one is due (next: `ipo_verdicts_visible_gate`, by 31 Dec), shown the entry, the evidence and
    the exact edit.
- **For the owner:** rollout. SA-011 deployed first (pushed 09:07), and its first backlog read
  is triaged before FIX-008 deploys.
- **Next, in order:**
  1. FIX-008's fresh review in a new conversation ("continue").
  2. Then PR-001.

**Committed 13 Oct about 08:15 IST, at the owner's word ("commit and push"). Pushed b9cc851..33ae170 at 09:07:07 IST 13 Oct; deploy confirmation pending (owner: railway deployment list + /health, then the FIX-007 and SA-011 rollout checks).** The push
was made by peer session `stockagent-main-3d` at the owner's word.
- `0bd6419` SA-011 code and tests; `672bc1d` FIX-007 code and tests; `dd7a158` the docs,
  evidence, cards, STATE and HANDOFF; then the KT bump to `dd7a158` (section 12 rows
  SA-011 and FIX-007 `Done`; section 1 says production runs `954305a` until this deploy is
  confirmed; PDF rebuilt; deep-dive headers; guide 11-G and 12-J status lines).
- `docs/README.md` (the owner's own probe line) is left uncommitted.
- **Pushed after the window:** 08:00 IST was inside the blocked 07:25–09:05 window, so the push
  waited until 09:07:07 IST. Railway redeploys at about 09:15.
- **After the deploy:** the owner confirms `railway deployment list` and `/health`, then runs
  FIX-007's three checks (review receipt) and SA-011's rollout check. Then KT section 1 is
  updated to "Production runs the inspected code".

**FIX-007 was ACCEPTED** by its fresh review (12 Oct about 23:17 IST to 13 Oct about 00:20 IST,
a new conversation opened with "continue"). Receipt: [review](evidence/FIX-007-review.md).
STATE: `active_task: null`, FIX-007 `done`, production verification `pending_deployment`, and
**`next_task: FIX-008`** (not started). Nothing was committed, pushed, deployed or configured,
and no production state was read.
- **In one example.** A member is signed in on the app.
  - On the Logs screen, its request carries the member's session and gets 403. The screen says
    "Server logs are visible to the owner account only.", with no key prompt and no retry. The
    server never reads the log buffer.
  - The same member typing `/ui/logs` into the address bar gets 401, because a typed URL sends no
    session. The guide expected 403 there; the review corrected it (L1).
- **Checked:**
  - input `ff6001e7` at the start; diff `910503e2` rebuilt from a base proved by blob ids;
  - own trace through a real uvicorn server and real Chromium, 93 passed. 70 fail on the ungated
    routes, and all six wrong-gate mutants are caught;
  - 13 path spellings and a CORS preflight leak nothing, and markup in a log line stays text on
    the owner's screen;
  - the implementer's tests: 42 + 3 pass, and on the original code 33 and 3 fail;
  - full suite **4471 passed, 12 skipped, 0 failed**; runtime data unchanged; PDF matches its
    source.
- **Findings:** no critical, high or medium.
  - L1 (low, docs): guide 11-G and the implementation receipt's rollout step 3 expected 403 for a
    member's direct visit; it is 401. Fixed in the guide.
  - L2 (low, test gap): no test leaves the Logs screen; mutant F4 (no abort on leaving) passes
    all of the implementer's tests. Routed to [SA-031](stories/SA-031.md).
  - I1: CODEBASE's "(FIX-007)" tag removed. I2–I4 are infos with no action.
- **Owner checks at rollout (corrected), read-only after the deploy:**
  1. Without a session, `GET <app URL>/ui/logs?limit=1` returns 401. A 200 means `AUTH_REQUIRED`
     is off; the 10 Sep audit recorded it on.
  2. The owner's Logs screen shows lines arriving (`live`), after one reload.
  3. The test member: the screen shows the owner-only message and no key prompt. An
     address-bar visit gets 401, like anyone's.
- **Still uncommitted:** FIX-007's and SA-011's files and the planning docs. Commit, push and
  deploy only on the owner's word, in a job-free window (safest 00:10–06:20 IST). With the
  commit:
  - set KT section 12's rows for SA-011 and FIX-007 from `Open` to `Done`;
  - bump the KT header's revision and rebuild the PDF.
- **Next, in order:**
  1. **FIX-008** (operator notices to the owner only, then register the backlog's watchdog
     entry) in a new conversation ("continue"). It depends on SA-011, which is done.
  2. Then PR-001. The open items listed below still stand.

**Before that: FIX-007 was IMPLEMENTED** (12 Oct, about 14:06–15:00 IST, a new conversation opened with
"continue"). Receipt: [implementation](evidence/FIX-007-implementation.md). STATE:
`active_task: null`, FIX-007 `review_required`, and **`next_task: FIX-007`**, meaning its fresh
**review**. Nothing was committed, pushed, deployed or configured, and no production state was
read.
- **In one example.** A member signed in on the app opens `/ui/logs?limit=1000`.
  - Before: 200 with up to 1,000 recent log lines, user ids included, and `/ui/logs/stream`
    kept sending new ones.
  - Now: 403 `{"detail": "Owner only."}`; without a session, 401. The check runs before the
    handler, so the buffer is never read and a refused stream never subscribes.
  - The owner's Logs screen still shows live lines. It now reads the stream with `fetch`, which
    sends the session header (`EventSource` cannot). A member there sees "Server logs are
    visible to the owner account only." and no API-key prompt, and the screen stops retrying.
- **Tests:**
  - 42 server tests through the real app; 33 fail on the ungated code, and all 6 wrong-gate
    mutants are caught;
  - 3 browser tests; all 3 fail on the old screen, and 3 screen mutants are caught;
    `npm run test:frontend` 17 passed;
  - full suite **4471 passed, 12 skipped, 0 failed** on the second run. The first run had one
    Windows rename flake in an IPO store test (23 of 23 alone; the class is on SA-031's card).
    Runtime data unchanged.
- **For the review:** input `FIX-007-manifest.json` (`ff6001e7…`, 13 files); diff `910503e2…`
  from the worktree just before FIX-007. `analysis_data/fix007/base_snapshot.py` rebuilds that
  base and proves it by SA-011's blob ids, and `diff_digest.py` makes the diff. Also in the
  ignored folder: `swap_plugin.py` (`FIX007_SWAP=base|M1..M6`, `PYTHONPATH` that folder,
  `-p swap_plugin`) and `fe_variants.sh` with `SA_FRONTEND_ROOT`.
- **Owner checks at rollout:**
  - I1: with `AUTH_REQUIRED` off, every anonymous request acts as the owner, logs included.
    Production's value was not read. After the deploy, an anonymous `GET /ui/logs?limit=1` must
    return 401; a 200 means `AUTH_REQUIRED` is off.
  - I2: reload the Logs screen once after the deploy; the first visit may run the cached old
    screen.
- **Still uncommitted:** FIX-007's files and SA-011's. Commit, push and deploy only on the
  owner's word, in a job-free window (safest 00:10–06:20 IST). With the commit, set KT section
  12's rows `Open` → `Done` (SA-011; FIX-007 once accepted), bump the KT header's revision and
  rebuild the PDF.
- **Next, in order:**
  1. **FIX-007's fresh review** in a new conversation ("continue").
  2. Then **FIX-008**, added 12 Oct about 23:10 IST (block below), then PR-001. The open items
     listed below still stand.

**Also 12 Oct (about 23:10–23:30 IST): FIX-008 added** at the owner's request, in the SA-011
re-review conversation, as a follow-up question. Planning only. FIX-007's review input
(`ff6001e7`) is untouched: the KT, PDF, guide, CODEBASE and PRODUCT_MAP were not edited.
- **Owner decision on SA-011's I7** (registering the backlog's watchdog entry): option 3.
  Register it only after operator notices reach the owner alone.
- **Why, in one example.** The 06:30 watchdog finds the backup not confirmed off-site.
  - Today the owner and the test member each get a push, and the shared mailbox gets two
    identical emails.
  - A ledger-drift notice names a user's id and also reaches the member.
  - This is code inspection: `alert_audience()` is every push-subscribed account plus the
    default user, and seven operator callers broadcast to it.
- **Card:** [FIX-008](stories/FIX-008.md), P1, 2 points, depends on SA-011.
  - It sends operator notices to the owner only, one email per notice; market notices stay
    with everyone.
  - Then it registers `error_backlog` in `config/milestones.yaml` and changes SA-011's
    pinning test.
  - It is placed directly after FIX-007, before PR-001, under the privacy-first rule. The
    product order is otherwise unchanged. PI README row 2.
- **Rollout order:** deploy SA-011 and triage its first read before FIX-008's deploy.
  Otherwise the first 06:30 run announces every recent issue at once.

**Before that: SA-011 was ACCEPTED** by its fresh re-review of rework 2 (12 Oct, about
08:06–08:35 IST, a new conversation opened with "continue"). Receipt: [review, section "Re-review of rework 2"](evidence/SA-011-review.md).
STATE: `active_task: null`, SA-011 `done`, production verification `pending_deployment`, and
**`next_task: FIX-007`** (not started). Nothing was committed, pushed, deployed or configured,
and no production state was read.
- **In one example.** A fix takes effect at 08:00 IST and the warning is back at 10:00 IST.
  - The owner types `2026-10-05T08:00`, or any of 8 other notations without an offset: a space,
    the hour alone, `20261005T0800`, a week date, a fraction, padding, a lower-case `t`, a date
    alone. Each gets 422 with the form (`2026-10-05T08:00+05:30` for IST), and nothing is
    written, not even a task sent with it.
  - With `+05:30`, `+0530` or `Z`, the mark is refused: "last seen at …10:00:00+05:30 … that
    fix did not hold".
  - A recurrence in the same second as the fix gives the same result in both read orders, with
    the real log writer's timestamps. The digest shows IST.
- **Checked:**
  - input `0323f2a8` at the start and the end; rework diff `ad35960c` rebuilt independently and
    read in full;
  - own HTTP trace 4 of 4 (all fail on the re-reviewed module); 11 story tests fail there, the
    receipt's 11;
  - 9 own mutants: 6 caught by the story file, 3 only by the reviewer's trace or probe;
  - full suite **4429 passed, 12 skipped, 0 failed**; runtime data unchanged; PDF matches its
    source.
- **Follow-ups:**
  - RR2-I1, a story-test gap at equality edges, is routed to [SA-031](stories/SA-031.md).
  - RR2-I2 and RR2-I3 are infos with no change.
  - RR-I2: watch after rollout. I7 (registering the watchdog entry) is the owner's decision.
- **SA-011's files are uncommitted,** together with the peer's product-results docs (the
  review, 13 cards, card and STATE edits). Commit, push and deploy only on the owner's word, in a
  job-free window (safest 00:10–06:20 IST). With the commit, set KT section 12's SA-011 row
  from `Open` to `Done`, bump the KT header's revision and rebuild the PDF. The review left the
  KT unchanged so that the reviewed bytes stay as they are. After the deploy, run the read-only
  production check in the [implementation receipt's "Rollout"](evidence/SA-011-implementation.md).
- **Next, in order:**
  1. **FIX-007** (server logs readable only by the owner) in a new conversation ("continue").
  2. Then PR-001. The open items listed below still stand.

**Before that: SA-011 rework 2 was IMPLEMENTED** (12 Oct, about 07:30–08:05 IST, a new conversation
opened with "continue"). Receipt: [implementation, section "Rework 2"](evidence/SA-011-implementation.md).
STATE: `active_task: null`, SA-011 `review_required`, and **`next_task: SA-011`**, meaning its
fresh **re-review**. Nothing was committed, pushed, deployed or configured, and no production
state was read.
- **In one example (RR-M1).** A fix is deployed Monday 5 Oct at 08:00 IST and the warning is back
  at 10:00 IST. On Wednesday the owner runs `--fixed-at 2026-10-05T08:00`, with no offset.
  - Now the API answers 422: the time "has no UTC offset, so it could be IST or UTC: give
    2026-10-05T08:00+05:30 for IST or 2026-10-05T08:00Z for UTC". Nothing about the issue
    changes.
  - With `+05:30` the mark is refused, naming the 10:00 IST recurrence: that fix did not hold.
  - Before, the bare time was read as 08:00 UTC (13:30 IST), and a week later the issue read
    `fixed, verified`.
- **Also taken:** RR-I1, stored times keep the precision they were logged, so a recurrence in the
  same second as the fix is judged the same whatever the read order; RR-I4, refusals and the
  digest name times in IST. Comparing at whole seconds was tried first and rejected: it hid a
  warning logged in the same second as a default-now mark (the first reviewer's trace caught it).
- **Tests:** story file 111 passed; 11 fail on the re-reviewed revision;
  mutants 12 of 12 (rework 2) and 16 of 16 (rework 1) caught; both reviewers'
  trace files pass unchanged; the re-reviewer's probe 23 of 24 (RR-I3, agreed); full suite
  **4429 passed, 12 skipped, 0 failed**; runtime data unchanged.
- **For the re-review:** input `SA-011-manifest.json` (`0323f2a8…`, 13 files); rework
  diff `ad35960c…` from the snapshot `analysis_data/sa011/rework2/base/` (=
  `SA-011-manifest-review2.json`), recipe `rework2/rw2_diff_digest.py`; cumulative
  `c8965571…` by `review/rv_digest.py` (restore `review/rv.diff` from
  `analysis_data/sa011/sa011.diff` afterwards). In-memory swap: `PYTHONPATH=analysis_data/sa011/rework2`,
  `-p rw2_plugin`, `SA011_RW2=base` or a mutant id.
- **Next, in order:**
  1. A fresh re-review in a new conversation ("continue").
  2. After acceptance, FIX-007 and then PR-001. The open items listed below still stand.

**Before that: SA-011's re-review requested changes again** (12 Oct, about 07:07–07:30 IST, a new conversation
opened with "continue"). Receipt: [review, section "Re-review of rework 1"](evidence/SA-011-review.md).
STATE: `active_task: null`, SA-011 `changes_requested`, and **`next_task: SA-011`**, meaning
rework 2. Nothing was committed, pushed, deployed or configured, no production state was read, and
no living document was edited.
- **Every finding of the first review is fixed.** M1, L1 to L5 and I1 hold on the reviewer's own
  examples, and 22 of the new tests fail on the reviewed module.
- **In one example (RR-M1, medium).** A fix is deployed Monday at 08:00 IST and the warning is
  back at 10:00 IST. On Wednesday the owner runs `--fixed-at 2026-10-05T08:00`: the deploy time
  as the app shows it, with no offset.
  - The server reads that as 08:00 UTC, which is 13:30 IST. The 10:00 recurrence then counts as
    before the fix, and a week later the issue reads `fixed, verified`. This was reproduced
    through the real app, in both read orders.
  - With `2026-10-05T08:00+05:30` the same mark is refused, as it should be.
- **Rework 2, in a new conversation ("continue"):**
  1. Refuse a `fixed_at` that has no offset, a date alone included. The 422 shows the expected
     form. Document the rule in the API field, the script's `--fixed-at` help, KT section 10 and
     guide 12-J, and add tests through HTTP.
  2. Optional: RR-I1, a recurrence in the same second as `fixed_at`; RR-I4, IST times in the
     refusal and in the digest's first/last dates.
  3. The input is preserved as `evidence/SA-011-manifest-review2.json` (`158479b4…`).
     Regenerate `SA-011-manifest.json`, record a rework-2 diff and rerun the full suite. Both
     reviewers' trace files should pass unchanged:
     `analysis_data/sa011/review/test_rv_trace.py` and
     `analysis_data/sa011/rereview1/test_rr_trace.py`.
- **Tests here:** story file 96 passed; full suite **4414 passed, 12 skipped, 0 failed**; runtime data unchanged.
- **Next, in order:**
  1. Rework 2.
  2. A fresh re-review in another new conversation.
  3. After acceptance, FIX-007 and then PR-001. The open items listed below still stand.

**Before that: SA-011 rework 1 is IMPLEMENTED** (12 Oct, about 06:28–07:10 IST, a new conversation opened with
"continue"). Receipt: [implementation, section "Rework 1"](evidence/SA-011-implementation.md).
STATE: `active_task: null`, SA-011 `review_required`, and **`next_task: SA-011`**, meaning its
fresh **re-review**. Nothing was committed, pushed, deployed or configured, and no production
state was read.
- **In one example (M1).** A fix is deployed Monday 08:00; the warning is back at 20:00 and the
  owner's Tuesday read records it. On Wednesday the owner marks it `fixed` "from Monday 08:00".
  - Now the API answers 422, naming when the issue was last seen: that fix did not hold. Nothing
    about the issue changes.
  - Had nobody read on Tuesday, the mark is accepted and the Monday-evening row reopens the issue
    as `regressed`. Either way it never reads `fixed, verified`.
- **The other findings:**
  - L1: a `fixed_at` more than 5 minutes in the future is refused;
  - L2: a row's ticker column is masked as any ticker is (local corpus: 0 split causes, was 4);
  - L3: any `Authorization:` value, a bare `Basic` credential and `%40` addresses are masked;
  - L4: guide 12-J reworded;
  - L5, decided: an acknowledged issue regresses only after 35 quiet days
    (`error_backlog.ack_quiet_days`), so a weekly or monthly job's known warning stays with its
    owner; a spike still needs attention;
  - I1: `ops/` is an API namespace (unknown `/ops/` paths are a JSON 404).
- **Tests:** story file 96 passed (66 before); 23 of the new tests fail on the reviewed revision;
  16 of 16 rework mutants caught; the reviewer's `test_rv_trace.py` passes unchanged (3 of 3);
  full suite **4414 passed, 12 skipped, 0 failed**; `data/`, `logs/` and `outputs/` unchanged.
- **Input for the re-review:** `SA-011-manifest.json`, regenerated, 13 files, `158479b4…`.
  Rework diff from the review1 input `13164cff…`; cumulative diff `36b27f3a…` (receipt).
- **Next, in order:**
  1. A **fresh re-review of SA-011** in a new conversation ("continue"), by REVIEW.md.
  2. After acceptance, FIX-007, then PR-001. The open items listed below still stand.

**Before that: SA-011's fresh review requested changes** (12 Oct, about 01:00–01:25 IST, a new conversation
opened with "continue"). Receipt: [review](evidence/SA-011-review.md). STATE: `active_task: null`,
SA-011 `changes_requested`, and **`next_task: SA-011`**, meaning rework 1. Nothing was committed,
pushed, deployed or configured, no production state was read, and no living document was edited.
- **In one example (M1, medium).**
  1. A fix for the miss-factor warning is deployed on Monday at 08:00.
  2. The warning comes back at 20:00, and the owner's Tuesday read records it.
  3. On Wednesday the owner marks the issue `fixed` "from Monday 08:00".
  4. A week later it reads **`fixed, verified`** and leaves the list. Had the owner not read on
     Tuesday, the same row would have reopened it as `regressed`.
  - Reproduced through the real app: the triage response itself says `verified`.
  - This fails the criterion "pending verification reconciles against measured evidence". The
    review confirmed the implementer's reading of that criterion.
- **What held.** These were checked through `server.app`, with real signup and invite and the
  real log handler:
  - input `f4343eae` verified, and diff `b669cf36` rebuilt by the reviewer's own script;
  - no model; nothing sent; `app_logs` only read;
  - owner-only access: a member gets 403, anonymous gets 401;
  - one issue per cause, with a regression that keeps its task;
  - 0 of 535 local templates hit the leak detectors;
  - story tests 66 passed; full suite **4384 passed, 12 skipped, 0 failed**; `data/`, `logs/`
    and `outputs/` unchanged.
- **Also for the rework:**
  - L1: refuse a future `fixed_at`;
  - L2: a row's ticker column splits one cause into two issues (local: 4 causes, 8 issues);
  - L3: a Basic credential and a `%40` address stay unmasked;
  - L4: guide 12-J's day-apart determinism step;
  - L5: decide whether acknowledged periodic warnings reopen;
  - I1 (optional): add `ops/` to the catch-all's API namespaces.
  - L2 and L3 change fingerprints, so fix them before the first deploy.
- **Next, in order:**
  1. **Rework 1 of SA-011** in a new conversation ("continue"). The input is preserved as
     `evidence/SA-011-manifest-review1.json`. Regenerate `SA-011-manifest.json`, record a rework
     diff, and rerun the full suite. The reviewer's
     `analysis_data/sa011/review/test_rv_trace.py` should pass unchanged.
  2. A **fresh re-review** in another new conversation.
  3. After acceptance, FIX-007, then PR-001. The open items listed below still stand.
  - `docs/README.md` has a new `railway ssh` line (01:00:16 IST, the owner's). It is not
    SA-011's and was not touched.

**Before that: SA-011 was IMPLEMENTED** (11 Oct, about 14:44–16:00 IST, a new conversation opened with
"continue"). Receipt: [implementation](evidence/SA-011-implementation.md); card:
[SA-011](stories/SA-011.md). STATE: `active_task: null`, SA-011 `review_required`, and
**`next_task: SA-011`**, meaning its fresh review. Nothing was committed, pushed, deployed or
configured, and no production state was read. The peer session `stockagent-main-43` (block
above) ran at the same time; the two agreed their writes by message.
- **In one example.** Three `malformed miss factor` warnings for three tickers are **one**
  issue at `GET /ops/errors`, with count 3 and state `new`.
  - The owner marks it `acknowledged` with task SA-016, then `fixed`.
  - A fourth warning reopens the same issue as `regressed`; it keeps its task.
  - A member gets 403. Nothing is emailed or pushed.
- **What it is:**
  - `core/ops/error_backlog.py` groups `app_logs` WARNING+ rows by a deterministic fingerprint,
    with no model;
  - the severity is the row's own level, never Railway's stderr envelope;
  - each issue has a lifecycle and triage. A fix is verified only by measured archive coverage,
    and a recurrence reopens it;
  - retention is bounded, and `app_logs` is never changed;
  - the digest is deterministic;
  - `/ops/errors` is owner-only, plus a watchdog check `error_backlog` that **no registry entry
    uses yet**;
  - `scripts/prod_errors.py` reads it with app credentials only.
- **Tests:**
  - 66 new invariant tests and 23 in-memory mutants, all caught;
  - focused neighbours 341 passed;
  - full suite **4384 passed, 12 skipped, 0 failed (6 min 27 s, final bytes)**;
  - `data/`, `logs/` and `outputs/` unchanged.
  - Review input `f4343eae…`, diff `b669cf36…`. The KT diff is taken from the peer's KT
    version, blob `0155b79a`.
- **Self-review:** none critical, high or medium. L1 (low): leak protection is pattern-based,
  so unquoted free text in a log line stays in its template. I1–I7 are info; I7 is an owner
  decision, below.
- **Next, in order:**
  1. **Fresh review of SA-011** in a new conversation ("continue"), by REVIEW.md, of these
     uncommitted bytes (`kt_manifest.py verify SA-011-manifest.json`). It should confirm the
     reading of "pending verification milestones reconcile against measured evidence" (receipt).
  2. After acceptance, commit and deploy only on the owner's word, in a job-free window. The
     production check (read-only) is in the receipt. The first owner read creates two derived
     tables in production `telemetry.db`.
  3. **Owner decision (I7), at rollout:** whether to register the `error_backlog` watchdog entry.
     It would broadcast to every push-subscribed account, which now includes the test member.
  4. After SA-011 is accepted, the next ready task in STATE order is **FIX-007**, then PR-001
     (the peer's block above).
  5. Still open: FIX-004's production checks (the 17 Oct scan; IDFCFIRSTB before 24 Oct; change
     1 only if STARHEALTH is held on 26 or 27 Oct); SA-038's Sunday 11 Oct heartbeat. The b9cc851
     push note is still uncommitted and goes with the next commit.

**Before that: FIX-005 was ACCEPTED by its fresh-session review** (11 Oct, from about 08:23 IST, a new
conversation opened with "continue"). Receipt: [review](evidence/FIX-005-review.md). STATE:
`active_task: null`, FIX-005 `done` with `production_verification: pending_deployment`, and
**`next_task: SA-011`** (not started). The verdict covers the **committed `954305a`**: input
`82d6c89c…` and diff `e28f1e61…`, checked with the reviewer's own script, 0 mismatches. Nothing
was committed, pushed, deployed or configured in this phase, and no production state was read.
- **In one example.** The reviewer's trace drives the real HTTP stack with Atlas on, as in
  `config.yaml`.
  - The owner signs up (id `primary`), and the real brief job writes the owner's brief.
  - A member joins by invite, with no portfolio, and asks chat "show my brief". The answer is
    "No brief yet", with nothing of the owner's and no folder created. That holds also when the
    model's tool arguments or the request body say `"user_id": "primary"`.
  - Once both have briefs, each account's chat answer equals its own
    `GET /delivery/brief/latest` text.
  - The baseline `04ee080` fails all 3 trace tests: a member gets `primary`'s brief.
- **What the review checked:**
  - where the identity comes from: the session, the passthrough, or 401;
  - that the owner made by signup is `primary`;
  - that no other chat path reads personal data: the tools, the context builder, the
    pre-router, and history keyed by user. The memo cache lives for one turn;
  - the reviewer's own mutations (table in the receipt), and the committed KT and PDF pairs at
    `954305a` and `304dcff`;
  - full suite **4318 passed, 12 skipped, 0 failed** (9 min 45 s), with `data/`, `logs/` and
    `outputs/` unchanged (800 files, `88a644fc…`).
- **Findings.** None is critical, high or medium.
  - **L1 (low, tests).** No test pins that the identity comes only from the session. Mutants
    that take `user_id` from the model's tool arguments or from the request body pass all 54 of
    the implementer's tests. The code is correct. Routed to the SA-031 card, with the fixture.
  - **L2 (low, owner decision).** The implementer's L1, confirmed: with Atlas on (as in
    `config.yaml`) and `AUTH_REQUIRED` on, an anonymous `GET /ui/watchlist` reads the default
    user's watchlist (`ui_data.py:1043`). **Routed by the owner as FIX-006, to be done last**
    (item 3 below).
  - **I1 (info, production data).** A brief a member received before the deploy stays in that
    member's own chat history until a startup sweep at least 7 days later. Added to the
    production check. I2 is info.
- **Review edits (docs only):** guide 11-F's status; the SA-031 card; the review receipt; STATE;
  HANDOFF. The KT, its PDF, CHAT_ARCHITECTURE and PRODUCT_MAP were not edited.
- **Next, in order:**
  1. **COMMITTED as `6266772` and PUSHED `304dcff..6266772` at 08:57:41 IST** at the owner's
     word ("go ahead commit and push"). It holds this review's 5 files; STATE and HANDOFF also
     carry the 08:16 push note. It is docs only, so the redeploy runs the same code as
     `954305a`. origin was checked as `304dcff` first. requirements and the Dockerfile are
     unchanged. On a Sunday, no job runs between 08:00 and the 17:45 IPO refresh.
     `.claude/settings.local.json` was not included. This push note is uncommitted and goes
     with the next commit.
  2. **DEPLOYED, confirmed by the owner** (about 11:00 IST, read-only): `dda41574` SUCCESS at
     08:57:41 IST (the `6266772` push; the code is `954305a`'s), `77feeddb` REMOVED, `/health`
     good. **FIX-005 production VERIFIED** (about 11:10 IST, the owner's read-only checks):
     - the owner's chat "show my brief" returns the owner's own 9 Oct brief;
     - a member account, signed up with an invite for this check, is told there is no brief
       yet (no holdings) and sees none of the owner's data. I1: nothing to purge.
     - Heads-up: with Atlas on, the brief job runs for every account, so this member also gets
       a morning brief from Monday's 08:50 run.
     - KT section 1 says production runs the inspected code and gains a "Chat brief scope" row,
       verified 2026-10-11. PDF rebuilt (source `5ea85416…`, 37 pages; `check_kt_docs` errors
       `[]`).
  3. **L2 is routed as [FIX-006](stories/FIX-006.md)** at the owner's word ("put that L2 for
     last"): `todo`, P2, placed last in STATE. Select it only when every other planned story is
     done.
     - **COMMITTED as `b9cc851` and PUSHED `6266772..b9cc851` at 11:12:41 IST** at the owner's
       word ("commit the docs and push them"). It holds items 2 and 3: the KT, PDF, STATE,
       HANDOFF and the FIX-006 card. It is docs only, and origin was checked as `6266772`
       first. Deploy confirmation is the owner's. This push note is uncommitted and goes with
       the next commit.
  4. Still open: FIX-004's production checks (the 17 Oct scan; IDFCFIRSTB before 24 Oct;
     change 1 only if STARHEALTH is held on 26 or 27 Oct); SA-038's Sunday 11 Oct heartbeat.
  5. **SA-011**, the first ready planned story in STATE order (its dependencies SA-002 and SA-004
     are done), in its own implementation conversation ("continue").

**Before that: FIX-005 was IMPLEMENTED** (11 Oct, about 07:47–08:10 IST,
in the same conversation as the deep-dive rewrite, at the owner's word). Receipt:
[implementation](evidence/FIX-005-implementation.md); card: [FIX-005](stories/FIX-005.md). STATE:
`active_task: null`, FIX-005 `review_required`, `next_task: FIX-005` (meaning its review). No
production state was read.
- **The defect.** Chat's `get_portfolio_brief` built `PortfolioStore()` with no user id, so every
  signed-in caller got the default `primary` user's brief or digest (holdings, values, verdicts).
- **The fix** (`services/api/routes/ui_data.py`). Both chat routes pass `user["user_id"]` through
  `_execute_chat_tool` and `_dispatch_chat_tool`. The tool opens `PortfolioStore(user_id)`, the
  store `GET /portfolio` opens. It refuses a missing or invalid id (never the default user; the
  default argument is `None`), and returns "No brief yet" without creating a folder for a user
  who has none.
- **Tests:** 51 new invariant tests, in `tests/unit/api/test_chat_brief_user_scope_fix005.py`:
  - no account sees another's marker, at 4 layers;
  - 7 invalid ids are refused, and no folder is created;
  - both real chat routes, with a stubbed model that calls the tool.
  - Also: `test_chat_brief_tool.py` now names the default user. Focused chat set: 106 passed.
    All 6 in-memory mutants are caught (the old behaviour fails 45).
  - Full suite: **4318 passed, 12 skipped, 0 failed** on the second run. The first run had 1
    failure, the known Windows rename flake in `test_store_migration_sa009` (it passes alone,
    3 of 3). `data/`, `logs/` and `outputs/` were unchanged (800 files, `0f244752`).
  - Review input `82d6c89c…`; diff `e28f1e61…` (27,443 bytes); baseline `04ee080`.
- **Docs:** CHAT_ARCHITECTURE sections 2, 4 and 9; KT sections 10 and 12 (PDF rebuilt);
  PRODUCT_MAP section 16; guide 11-F; the card.
- **Self-review:** none critical, high or medium. **L1 (low, related, not fixed):** with Atlas and
  `AUTH_REQUIRED` both on, an anonymous `GET /ui/watchlist` reads the default user's watchlist.
  The owner should route it. I1–I3 are info.
- **Next, in order:**
  1. **COMMITTED as `954305a`** at the owner's word ("later commit and push them"), before the
     review: a recorded deviation, as for FIX-004 change 1. `verify --rev 954305a` gives 0
     mismatches. Then the KT bump: header `954305a`, edition 2026-10-11, the five deep-dive
     headers, guide 11-F; PDF source `971daaec…`; `check_kt_docs` errors `[]`. **PUSHED
     `ae855a4..304dcff` at 08:16:32 IST** at the owner's word ("its okay push now"). The owner
     waived the 07:30–09:00 slot, in which only the daily 08:00 IPO refresh runs on a Sunday.
     origin was checked as `ae855a4` first. requirements and the Dockerfile are unchanged.
     **Deploy confirmation is the owner's:** `railway deployment list` should show the new
     deployment SUCCESS, and `/health` should be 200. FIX-005 `production_verification` is
     `pending_deployment`. This push note is uncommitted and goes with the next commit.
  2. **Fresh review of FIX-005** in a new conversation ("continue"), by REVIEW.md, of the
     committed bytes (`kt_manifest.py verify FIX-005-manifest.json --rev <commit>`).
  3. Then SA-011, as below.

**Before that: FIX-004 change 1 was ACCEPTED by its fresh-session review** (10 Oct, from about 20:14 IST, a new
conversation opened with "continue"). Receipt: [review, section "Change 1 fresh-session
review"](evidence/FIX-004-review.md). STATE: `active_task: null`, FIX-004 `done`,
`change_1: accepted` with `production_verification: pending_observation`, and `next_task: SA-011`
(not started). The verdict covers the **committed `61c85d6`**: input `146c7507…` and diff
`2ebe6299…`, checked with the reviewer's own script, 0 mismatches. It was already deployed.
Nothing was committed, pushed, deployed or configured in this phase, and no production state was
read.
- **In one example.** The reviewer's own trace runs the real brief job from 19 to 28 Oct, with
  results on Tue 27 Oct.
  - Between the briefs, the real writer adds a row from the Saturday 24 Oct scan and one from the
    Monday 16:30 curator. The 26 Oct brief shows the Saturday row, and the 27 Oct brief the
    Monday one.
  - The pre-FIX-004 row dated 27 Oct is in no delivered text, HTML or saved brief.
- **What the review checked:**
  - every guidance writer, by code: the curator stamps the review date at 16:30; the Saturday
    scan stamps event dates on or before its run; the research loop writes no guidance;
    `distill_dossier` only withdraws items;
  - every consumer: the saved brief (the API and the chat tool), and the text and HTML delivery;
  - the reviewer's own mutations: every one that changes behaviour is caught. One, R2 (the
    results date passed instead of the brief's date), survives the implementer's tests and is
    caught only by the reviewer's trace (I1);
  - the committed KT and PDF pairs at `61c85d6` and `47d49c9`;
  - focused 204 passed; full suite **4267 passed, 12 skipped, 0 failed**, with `data/`, `logs/` and `outputs/` unchanged.
- **Decisions.** C1 ("before the brief's date", not "on or before") is upheld: the window keeps
  the meeting day, and with "on or before" the 27 Oct row shows on the meeting's morning. C2 and
  C3 are upheld.
- **Findings.** None is critical, high or medium. L1 (low; a brief triggered by hand after 16:30
  omits that day's new guidance) is accepted with C1. I1 is routed to the SA-031 card. I2 (the
  implementation receipt names the research loop as a guidance writer) and I3 (replays use
  stored dates; already routed to SA-013) are info.
- **Review edits (docs only):** guide 04-H's status; the FIX-004, SA-046 and SA-031 cards; the
  review receipt; STATE; HANDOFF. **The KT, the PDF and RL_DESIGN were not edited.** A peer
  session (`stockagent-main-e5`) restructured the living docs at the owner's request (block
  below). Its KT body carries no review status, so it needs no edit for this verdict.
- **COMMITTED at the owner's word** ("ya go ahead and commit", about 20:51 IST 10 Oct), in two
  docs-only commits. **Not pushed.**
  - **`b325ad2`:** the design-doc restructure (its 10 files);
  - **the next commit** ("docs: record FIX-004 change 1's fresh-review acceptance"): this
    review's 7 files. Its STATE and HANDOFF also carry the restructure's note and the earlier
    push and deploy note.
  - `.claude/settings.local.json` was not included.
- **Next, in order:**
  1. **PUSHED `47d49c9..ae855a4` at 20:56:48 IST** at the owner's word, between the 19:00 and
     23:00 jobs. It is docs only, so the redeploy runs the same code. **Deploy confirmation is
     the owner's:** `railway deployment list` shows the new deployment SUCCESS, and `/health` is
     200. The old local side branches (`chore/repo-hygiene-cleanup`, from 19 Aug, and
     `feat/externalize-tunable-config-yaml`, from 20 Jun) were not pushed. The owner then had
     them **deleted** "to avoid confusion"; they were never on GitHub. A backup bundle, with
     restore steps, is in the ignored `analysis_data/branch_backups/`. This push note is
     uncommitted and goes with the next commit.
  2. FIX-004's production check (the owner, read-only): rerun the count probe after the 17 Oct
     10:00 IST scan, and sample IDFCFIRSTB's digest before 24 Oct. For change 1, only if
     STARHEALTH is held on 26 or 27 Oct: that brief's watch line is not the 27 Oct row.
  3. Still open: SA-038's Sunday 11 Oct heartbeat check.
  4. **SA-011**, the first ready planned story in STATE order (its dependencies SA-002 and SA-004
     are done), in its own implementation conversation ("continue"). SA-008 change 1 stays
     `todo`: it is gated, and not urgent.

**Also 10 Oct: the design documents were restructured at the owner's request** (docs only, a
separate conversation; committed as `b325ad2`, not pushed). The owner asked that design documents be updated as a whole,
as proper design documents, not by appending per-story change notes.
- **KT and ARCHITECTURE rewritten whole.** Sections 1–10 keep their headings and anchors.
  Measured production state now lives in one dated table (KT section 1). Planned work is in
  section 11. The roadmap is one table in section 12, with Status Done or Open. Commits, reviews
  and deploys stay in STATE and the receipts, never in the design docs.
- **Stale lines corrected in that table:** SA-006 and SA-007 change 1 are deployed; the TMPV
  swap and TATAELXSI's regeneration are done; the SA-009 quarantine was applied on 1 Oct; and
  IPO-lane rows are graded.
- **Story tags removed** from CODEBASE.md, RL_DESIGN (FIX-004 wording only; the rule text is
  unchanged), CHAT_ARCHITECTURE, PRODUCT_MAP, AGENTIC_DESIGN and LEGAL_AND_COMPLIANCE.
  docs/README.md and KT section 12 now state the rule.
- **Checks:** KT header still `61c85d6`; PDF rebuilt (source `96fcf08a…`, 37 pages);
  `check_kt_docs` errors `[]`. No code, test or config changed.
- **Changed files (10):** the KT, its PDF, ARCHITECTURE, CODEBASE.md, RL_DESIGN,
  CHAT_ARCHITECTURE, PRODUCT_MAP, AGENTIC_DESIGN, LEGAL_AND_COMPLIANCE and docs/README.md.
  Committed as `b325ad2` at the owner's word, before the review bookkeeping above.
- **For every later story:** edit the affected section as current design, set the story's
  Status in KT section 12, and put only measured production facts in section 1's table.
- **Then the five deep-dives were rewritten whole** (docs only, a further conversation, 10 Oct
  evening to about 07:45 IST 11 Oct; uncommitted when recorded). RL_DESIGN, AUTOPILOT_GUIDE,
  AGENTIC_DESIGN, CHAT_ARCHITECTURE and PRODUCT_MAP each open with Edition 2026-10-10, Code
  inspected `61c85d6` and a scope line. The Status and Historical banners are gone; still-true
  deltas are folded into the body, and stale ones dropped.
  - **Verified by tracing** every claim against the code at `61c85d6` (the working tree's code is
    identical to it). RL_DESIGN keeps sections 23–27, which CODEBASE and AGENTIC_DESIGN cite, and
    reorders 1–22. PRODUCT_MAP keeps all 22 headings that docs/README.md links; its counts were
    recounted from `git ls-files` (28 config sections, 17 fetchers, 13 routers with 86 endpoints
    and 1 WebSocket, 24 job IDs, 333 test files). docs/README.md's index rows now match.
  - **KT corrections** (header still `61c85d6`): section 3 no longer files the pre-open check
    under `managed`; section 5 says observe mode never writes *adapted* weights (a missing weight
    file is still created at v0); section 10 names chat's `get_portfolio_brief` exception and
    says the chat prompt does not forbid HTML. PDF rebuilt (source `bb210c0e…`, 37 pages).
  - **Checks:** `check_kt_docs` errors `[]`; relative links, heading anchors and a blank line
    before every list checked on all 7 rewritten files. No code, test or config changed.
  - **New findings, documented and not fixed:**
    1. Chat's `get_portfolio_brief` builds `PortfolioStore()` with no user id, so every signed-in
       caller gets the default `primary` user's brief or digest. A cross-user exposure with no
       story yet: **owner decision** (CHAT_ARCHITECTURE section 9).
    2. On a shock morning the pre-open check scans the four native sectors' built-in `TICKERS`
       lists, not the managed list (RL_DESIGN 27.3).
    3. Nothing writes the in-process macro cache, `miss_events` or `correction_counter`: the
       bundle's macro search never hits cache, the recency-weighted miss ranking is inert, and
       the archive rule's effectiveness test always passes.
    4. The Monte Carlo path ignores `path_shape`; forecasts and re-forecasts use the raw regime.
    5. The control lane is scored on the error-direction label.
    6. Promotion re-enables a disabled (retired) managed entry with no registry check; the
       scheduled review ignores the watchlist cadence.
    7. `/ui/chat` skips the pre-router and the scrubber, and both chat routes answer failures
       with a canned demo reply.
  - **Changed files:** the five deep-dives, docs/README.md, the KT, its PDF, STATE.json and
    HANDOFF.md. They go with the earlier push note above in one commit.

**Previous: FIX-004 change 1 was IMPLEMENTED and awaited its fresh-session review** (10 Oct, about
15:28–15:55 IST, a new conversation opened with "continue"). Receipt:
[implementation, section "Change 1"](evidence/FIX-004-implementation.md). STATE:
`active_task: null`, FIX-004 `done` (deployed `0fa598ec`), `change_1: review_required`,
`next_task: FIX-004` (meaning change 1's review). Review input:
[FIX-004-change1-manifest.json](evidence/FIX-004-change1-manifest.json) **`146c7507…`** (11
files); diff **`2ebe6299…`** (28,835 bytes), baseline `0ebd29b`. No production state was read.
- **COMMITTED BEFORE ITS FRESH REVIEW, at the owner's word** ("go ahead commit and push", about
  18:25 IST 10 Oct). This is a recorded deviation from REVIEW.md's order. Status stays
  `review_required`. The fresh review reviews the committed bytes: `kt_manifest.py verify
  FIX-004-change1-manifest.json --rev <commit>` must give 0 mismatches. Any requested change
  lands as a follow-up commit. Committed as **`61c85d6`** (15 files; `verify --rev 61c85d6`
  gives 0 mismatches), then the KT bump to it (KT §5, PDF source `1fde0ed9…`, guide 04-H).
  Verify against `61c85d6`: later revisions differ in exactly those 3 docs. **PUSHED
  `0ebd29b..47d49c9` at 18:28:06 IST** (17:55–18:55 window). **DEPLOYED:** the owner reported
  about 20:10 IST that `railway deployment list` and `/health` are good (deployment id not
  recorded). This push and deploy note is uncommitted and goes with the next commit.
- **In one example.** A held stock has results on Tue 27 Oct. Its dossier holds open guidance
  dated 15 Sep and a pre-FIX-004 item dated 27 Oct (STARHEALTH's shape). Before, the briefs of
  Mon 26 and Tue 27 Oct, the two in the 3-day earnings window, showed the 27 Oct item as the
  watch line. Now both show the 15 Sep item.
- **Decision for the review (C1).** The scope said "on or before the brief's date". The code uses
  **before** it:
  - the brief goes out Mon–Fri at 08:50, before any weekday dossier writer (the curator at
    16:30; event ingestion and research on Saturdays);
  - the window includes the meeting day, so "on or before" would still show the 27 Oct row on
    the 27 Oct morning;
  - the cost: a brief triggered by hand after 16:30 leaves out that day's new guidance until
    the next day.
- **Design.** The dossier gains `open_guidance(as_of)`, which the digest (last 5) and the brief
  (last 1, as of the day before) both use. The digest's behaviour is unchanged.
- **Tests:**
  - 51 new brief tests: a hand-written table, the review's L1 repro, a 36-date sweep, and an
    end-to-end build and render;
  - 2 for the review's I1 (7 known open items: the newest 5 listed);
  - all 12 in-memory swaps are caught: the baseline and 11 mutants, including the literal
    "on or before" (7 failures) and the review's G1;
  - full suite **4267 passed, 12 skipped, 0 failed**, with `data/`, `logs/` and `outputs/`
    unchanged; `check_kt_docs` errors `[]`.
- **Self-review:** none critical, high or medium. L1 is the hand-triggered brief above. L2: the
  rule rests on the schedule. I1: a morning reader of the digest, such as the chat tool, still
  shows an old row on its own day, as reviewed. I2: the other raw readers are unchanged.
- **Docs:** KT §5 and the PDF, RL_DESIGN §23.1, guide 04-H, and the FIX-004 and SA-046 cards.
- **Next, in order:**
  1. **Fresh review of change 1** in a new conversation ("continue"), by REVIEW.md, of the
     committed `61c85d6`. The owner had it committed and pushed first, so it can be live before
     **Mon 26 Oct** (the first brief in STARHEALTH's window). If the review asks for changes,
     they land as a follow-up commit.
  2. FIX-004's production check (owner, read-only): rerun the count probe after the 17 Oct
     10:00 IST scan, and sample IDFCFIRSTB's digest before 24 Oct.
  3. Still open: SA-038's Sunday 11 Oct heartbeat check.

**Previous: FIX-004 was ACCEPTED by its fresh-session review** (10 Oct, about 14:36–15:05 IST, a new
conversation opened with "continue"). Receipt: [review](evidence/FIX-004-review.md). STATE:
`active_task: null`, FIX-004 `done`, deployed as `0fa598ec`, `production_verification: pending_observation`,
`change_1: todo`. The verdict covers review input **`2f4cf482…`** and diff **`5550aab9…`**
(worktree on `5ea49fe`, uncommitted), plus documentation-only review edits. Nothing was
committed, pushed, deployed or configured, and no production state was read.
- **In one example.** The reviewer's own trace takes a board meeting on 24 Oct through the
  weekly scans. The 10 and 17 Oct scans skip it, and the 24 Oct scan stores it under 24 Oct.
  On 23 Oct the agents' digest, the context bundle, the chat tool and the daily curator's
  prompt show no 24 Oct row, even from a dossier that holds one, as old dossiers do.
- **What the review checked:**
  - the input, with the reviewer's own script, at the start and before the edits: 0 mismatches;
  - every writer of a dossier date and every caller of the digest, by code;
  - the old code fails the new tests (52, 4 and 51 failures, as the receipt says). Two of the
    reviewer's variants are caught. One survives (I1), and three behave the same as the real
    code in production;
  - daily and weekly scan sweeps over 22 events: each digested once, on or after its date;
  - focused 80 passed; full suite **4214 passed, 12 skipped, 0 failed**, with `data/`, `logs/`
    and `outputs/` unchanged; `check_kt_docs` errors `[]`.
- **Findings.** None is critical, high or medium.
  - **L1 (low):** the morning brief's earnings-watch line (`core/delivery/brief.py:346`) shows
    the newest open guidance with no date check. Only rows stored before the fix are affected:
    STARHEALTH's one guidance item dated 27 Oct. It reaches the 22–26 Oct briefs only if
    STARHEALTH is held. Routed to **FIX-004 change 1**.
  - I1–I4 are info; see the receipt.
- **Review edits (docs only):** KT §5 (the status, plus one L1 sentence) and the PDF (source
  `2dcad25f…`); guide 04-H; the FIX-004 card (its "Fresh review" section defines change 1) and
  the SA-046 card. `verify FIX-004-manifest.json` now mismatches exactly those 5 files.
- **Next, in order:**
  1. **DONE (`ff95a51`, then the KT bump to it).** ~~At the owner's word, commit FIX-004.~~ Include the 11 manifest paths, the four FIX-004
     receipts (probe, implementation, manifest, review), the SA-038 review's L2 note, STATE and
     HANDOFF. Never include `.claude/settings.local.json`. Then bump the KT to that commit.
  2. **PUSHED `5ea49fe..0ebd29b` at 15:10:49 IST** at the owner's word ("dont worry commi and
     push now"), inside the 15:05–16:25 IST window. **DEPLOYED:** the owner's read-only
     `railway deployment list` shows **`0fa598ec` SUCCESS**, created 15:10:50 IST, and
     `406ad444` REMOVED. `/health` is the owner's check. FIX-004's
     `production_verification` is now `pending_observation` (step 3). This push note and the STATE entry are not committed yet; they go with the
     next commit. ~~Push only on the owner's word, in a job-free window~~ (safest 00:10–06:20 IST). The
     10 Oct 10:00 IST scan ran on the old code. Each Saturday scan before the deploy can add
     more future-dated rows.
  3. **After the deploy** (read-only, by the owner): rerun the count probe after the first
     Saturday scan on the new code, and sample IDFCFIRSTB's digest before 24 Oct (STATE
     `after_deploy`).
  4. **IMPLEMENTED 10 Oct (above); awaits its review.** ~~Then FIX-004 change 1~~, in a new conversation ("continue"): apply the date rule in
     `_earnings_watch`, then its own fresh review. It is worth landing before about 22 Oct. The
     owner may drop it.
  5. Still open: SA-038's Sunday 11 Oct heartbeat check. SA-010 was verified on 10 Oct (below).

**Previous: FIX-004 was IMPLEMENTED and awaited its fresh-session review** (8 Oct, about
15:33–17:35 IST, a new conversation opened with "continue"). Receipt:
[implementation](evidence/FIX-004-implementation.md). STATE: `active_task: null`, FIX-004
`review_required`, `next_task: FIX-004` (its review). Review input:
[FIX-004-manifest.json](evidence/FIX-004-manifest.json) **`2f4cf482…`** (11 files); diff **`5550aab9…`** (36,266 bytes). Baseline `5ea49fe`.
Nothing is committed, pushed, deployed or configured, and no production state was read.
- **In one example.** On 7 Oct, 3 of the 5 "Recent observations" in IDFCFIRSTB's digest were
  dated 24 Oct, a board meeting that had not happened. After FIX-004 the weekly scan skips an
  event until its date, and the digest lists only rows dated today or earlier: IDFCFIRSTB's five
  newest real notes.
- **The rule chosen** (the card asked for a choice and its reasons):
  - write time: skip an event dated after the run. It is not digested and not watermarked, and
    the first scan on or after its date picks it up;
  - read time: the digest leaves out observations and open guidance dated after its date. Stored
    rows are not rewritten.
  - Why: the ingestion prompt says the event "just happened"; the live NSE feed already shows
    upcoming meetings; future meetings no longer take the 3-event scan cap. The reasons are in
    the receipt and the card.
- **Tests:**
  - a new file of 53 tests: the event-date table against a pinned run date, an all-fields
    invariant, the cap, one meeting from scan to digest, and 45 digest dates;
  - focused 80 passed; the baseline code and 7 mutants are all caught;
  - full suite **4214 passed, 12 skipped, 0 failed** (`data/`, `logs/` and `outputs/` unchanged);
  - `check_kt_docs` errors `[]`.
- **Self-review findings** (not the fresh review): none critical or high.
  - L1: the old future rows come back on their date (24 and 27 Oct). No migration is authorised.
  - L2: a skipped meeting relies on a later weekly scan and on NSE's first-5 list (unmeasured).
  - L3: rows carry event dates, not learned dates. Routed to SA-013.
  - I1–I3 are info.
- **Docs:** KT §5 and the PDF (source `ae47071f…`), RL_DESIGN §23.1 and §26, guide case 04-H,
  and the FIX-004, SA-046 and SA-013 cards.
- **Next, in order:**
  1. **FIX-004's fresh review, in a new conversation** ("continue"). Re-verify the manifest,
     reconstruct one board-meeting event from scan to digest, and check every dossier date
     writer (the receipt's table).
  2. After acceptance, at the owner's word: commit the code, tests, docs, receipts (with the
     7 Oct probe receipt and the SA-038 L2 note), STATE and HANDOFF; then bump the KT. Push only
     on the owner's word, in a job-free window. Unless a deploy lands before it, the Sat 10 Oct
     10:00 IST scan runs on the old code and may add more future-dated rows.
  3. After a deploy, the owner reruns the count probe (read-only) after the first weekly scan on
     the new code.
  4. Still open: SA-038's Sunday 11 Oct heartbeat check. ~~SA-010's 16:30 log check (owner-run).~~
     **SA-010 VERIFIED, 10 Oct:** the owner counted the `406ad444` logs, read-only. The 7, 8 and 9 Oct
     runs are whole; 6 Oct is only partly in the window.
     - Every `^CNXAUTO` and `^CNXENERGY` line says unavailable. No `^NSEBANK`, `^CNXIT` or
       `^NSEI` line does.
     - yfinance's `CNXAUTO` lines are 10, 8 and 10 a day, against 54 before SA-010.
     - Every line pairs each sector with its own index on all three days, and others get
       `^NSEI`.
     - Stocks with two lines: 1 on 7 Oct, 1 on 8 Oct, 6 on 9 Oct.
     - Every second line falls inside the 16:30 review, under 2 minutes after the first and
       with the same sector. That fits the legacy fallback of review I2. 9 Oct had 6 such
       pairs; 7 and 8 Oct had 1 each.
     - The 9 Oct gap is explained: ACMESOLAR runs as `generic` in production, so it is measured
       against Nifty 50 by design. Whether it belongs in renewable is a question for SA-026.
     - Not observed: the data-health page's record of the index. STATE has the verified note.
     - The full counts are in STATE, under SA-010 `production_verification`.

**Previous: SA-038 was ACCEPTED by its fresh-session review** (6 Oct, about 11:14–11:40 IST, a new
conversation opened with "continue"). Receipt: [review](evidence/SA-038-review.md). STATE:
`active_task: null`, SA-038 `done`, `production_verification: pending_deployment`,
`next_task: FIX-004`. The review itself committed, pushed, deployed and configured nothing, and
it read no production state.
- **Committed at the owner's word** ("ya go ahead now", about 11:55 IST):
  - `378479a` is SA-038: 18 files, never `.claude/settings.local.json`.
    `verify SA-038-manifest.json --rev 378479a` mismatches only the 4 review-edited docs, so
    the registry and test bytes are committed as reviewed.
  - `70fce66` closes **IPO-0a**: `ipo_p0_live_window_check` is deleted, with its evidence in
    the message, and the I2 test edits are in. Registry readers 207 passed; re-adding the
    entry fails 2 of 5 tests. Guide 12-I and the IPO plan are updated.
  - The KT bump follows: it declares `70fce66`, edition 2026-10-06, PDF source `77a16c4e…`,
    `check_kt_docs` errors `[]`.
  - **PUSHED** `a502cf7..5ea49fe` at 12:05:15 IST, at the owner's word. **The deploy is not
    yet confirmed.** The live deployment before the push was `8b97dab8`. Claude's polling of
    `railway deployment list` after the push was blocked by the auto-mode classifier.
  - **DEPLOYED.** The owner's read-only `railway deployment list` shows **`406ad444` SUCCESS**,
    created 12:05:15 IST, and `8b97dab8` REMOVED. `/health` returned ok at 20:01 IST (owner). SA-038's
    `production_verification` is now `pending_observation`: the 7 Oct 06:30 watchdog mail should
    carry no "LAPSED" critical for the 8 retired ids.
  - **7 Oct 06:30: met.** The owner pasted the mail. Its only item is SA-007's weekly backup
    reminder, which is expected: the off-site setup is deferred to the end of the PI. No
    "LAPSED" critical appeared. Still to observe: the Sunday 11 Oct heartbeat lists only
    `ipo_verdicts_visible_gate` and the invariants.
- **In one example.** The A1 entry asked whether A1 (deployed 25 Aug) stopped other sectors'
  tickers from being written under `automobile/`. SA-009's production inventory of 30 Sep says it
  did not: there were 16 such copies, and they were still gaining feedback rows. SA-009's fix and
  its 1 Oct quarantine stopped the writes, and the 6 Oct probe saw none. So the entry stays
  deleted, but as "superseded by SA-009", not "verified" (M1).
- **What the review checked:**
  - the review input `e3a251d5…` and diff `22196d37…`, re-verified with the reviewer's own script:
    0 mismatches, both at the start and before the edits;
  - each of the 9 entries against its evidence class and the deleted entries' own acceptance
    text;
  - the engine, the runner and `registry_is_current`, by code;
  - 7 of 7 of the reviewer's own registry variants caught; the baseline registry fails 4 of 5;
  - focused tests 207 passed; full suite **4161 passed, 12 skipped, 0 failed**, with `data/`
    unchanged; `check_kt_docs` errors `[]`.
- **Findings.** None is critical or high.
  - **M1 (medium):** A1 was recorded as verified; fixed in the documentation, as above.
  - **L1:** E1's acceptance (e) was never judged. Judged by code in the review; a note is on the
    SA-031 card.
  - **L2:** the F3 share among research rows was not counted. Added to FIX-004's count probe.
  - **L3:** KT §1 still said SA-039's verification was pending; fixed.
  - **I1–I4** are info; see the receipt.
- **Review edits (docs only):** KT §1, §10 and §12, and the PDF (source `3bb23a99…`); guide 12-I;
  the SA-031, SA-046 and FIX-004 cards; a pointer to M1 in the implementation receipt.
  `verify SA-038-manifest.json` now mismatches exactly the KT, the PDF, the guide and SA-046.
- **Next, in order:**
  1. **DONE (`378479a`).** ~~At the owner's word, commit SA-038.~~ Include the 10 manifest paths, the SA-038 receipts
     and manifest, the FIX-004, SA-031 and IPO-plan edits, STATE and HANDOFF. Never include
     `.claude/settings.local.json`. Then bump the KT as usual.
  2. **DONE (`70fce66`).** ~~A separate commit deletes `ipo_p0_live_window_check`~~ (IPO-0a, the owner's decision), with
     its measured evidence. The same commit must edit
     `tests/unit/ops/test_milestones_judged_sa038.py`, or the suite goes red (review I2):
     - add the id to `RETIRED`;
     - delete the IPO assert in test 3 (line 94);
     - delete the two IPO asserts in test 5 (lines 108 and 116).
     Run that file and `tests/unit/ops`. The registry edit still relies on the owner's allow rule.
  3. **PUSHED 12:05:15 IST; DEPLOYED as `406ad444` (SUCCESS).** ~~Push in the 12:05–14:55 IST window.~~ **The four allow rules were removed** at the owner's word (settings.local.json restored, about 12:15 IST). Afterwards the owner removes the
     four allow rules. SA-038's production check, read-only, after the deploy: the next 06:30
     watchdog run sends no critical for any deleted id, and the Sunday heartbeat lists only the
     IPO milestone(s) and the invariants.
  4. **SA-010's read-only production check** of today's 16:30 review, which ran on `406ad444`.
     **The owner runs it.** Claude's read-only `railway logs 406ad444 --json` fetch was denied
     by the auto-mode classifier (Production Reads) at about 22:28 IST, and preparing a log
     counter was denied with it. Neither was retried. What to look for is STATE SA-010
     `production_verification.after_deploy`.
  5. **FIX-004: the count probe RAN** (the owner, 7 Oct 11:43 IST, deploy `406ad444`). The
     result is in the [probe receipt](evidence/FIX-004-probe-2026-10-06.md).
     - **Measured:** 2 of 25 dossiers have future dates. IDFCFIRSTB has 3 observations
       dated 24 Oct, all 3 in its digest's newest 5. STARHEALTH has 1 guidance item dated
       27 Oct. Each has 2 watermark keys on that date.
     - **Reading:** this is a pattern, and event ingestion explains every row. The card now
       says the read-time rule covers "Open guidance" as well as "Recent observations".
     - **SA-038 L2 is closed:** 12 of 17 research rows carry a source (71%), and none of the
       406 other rows does. No fix is needed.
     - **DONE 8 Oct (above): FIX-004's implementation, in a new conversation**, then its fresh review. Then
       the normal STATE queue resumes. FIX-004 stays `todo` until the implementation starts.
       The Sat 10 Oct 10:00 IST scan runs before any FIX-004 deploy and may add more rows.

**Previous: SA-038's implementation — the pre-review record.** SA-038 was `review_required` (`active_task: null`, `next_task: SA-038`). It was implemented on
5–6 Oct in one new conversation: started about 23:44 IST, resumed 07:54 IST, and finished about
11:00 IST after the owner's probe. Receipt: [implementation](evidence/SA-038-implementation.md).
Review input: [SA-038-manifest.json](evidence/SA-038-manifest.json) **`e3a251d5…`** (10 files);
diff **`22196d37…`** (34,650 bytes). Baseline `a502cf7`. Nothing is committed, pushed or
deployed.
- **In one example.** The 2 Oct 06:30 mail said "F3 provenance checkpoint … LAPSED", a
  `critical`, although nothing was broken. The probe shows that 1,021 of 1,041 lessons written
  since F3 carry their dated headlines, so the entry is deleted with that count recorded. After
  SA-038, the real watchdog is run on 7 Oct from production's state, with every check forced to
  `pending`. It sends no critical.
- **The registry** (`config/milestones.yaml`): **7 entries deleted**, each with its evidence or a
  recorded decision.
  - Atlas: the flag is true.
  - F3: 98% of post-F3 lessons carry evidence; 13 sourced research observations.
  - Hard-bind: not judged, because it would grade a defective target. Folded into SA-012 and
    SA-014.
  - A1(b): no `automobile/` copy of another sector's ticker.
  - B1: 888 `run_summaries` rows since 26 Aug, never reset over the last 20 deploys.
  - B2: met on 26 Aug; the B6 half is on SA-002's pending check.
  - E1: met on 26 Aug; (c) not applicable.
  - **Kept open:** `ipo_p0_live_window_check`, re-dated to 2026-10-31 with the measured evidence.
    The ledger is capturing again (54 rows over 15 issues since 24 Sep). Closing it means closing
    IPO-0a, which is the **owner's call** (the IPO plan is paused).
  - No milestone is past its deadline.
- **SA-039 backstop, done.** P3 had passed on 1 Oct, so STATE now reads `verified`, with a note
  naming SA-038 as the recorder.
- **Found by the probe:** a dossier observation is dated **2026-10-24**, in the future. Event
  ingestion stamps board-meeting dates (`event_ingestor.py:111`, `:239`). Finding F1, medium,
  routed to the SA-046 card. The owner may promote it to a FIX story.
- **Also from the probe:** SA-009's restart check is met (recorded in STATE). Its scorecard check
  remains.
- **Tests.**
  - 5 new tests over the real registry. The baseline fails 4, and all 7 mutants are caught.
  - Registry readers: 207 passed.
  - Full suite on the final tree: **4161 passed, 12 skipped, 0 failed**, with `data/` unchanged.
    The first run's single failure was the known Windows rename flake.
- **Docs.** KT §10 (PDF source `8f89c401…`; `check_kt_docs` errors `[]`); guide 12-I, plus a fix
  to section 12's split table; notes on the SA-002, SA-012, SA-014 and SA-046 cards; the SA-039
  activation record.
- **The registry edit needed the owner's permission.** The auto-mode classifier blocked it as
  "audit tampering". The owner added four narrow allow rules to their own
  `.claude/settings.local.json`. That file is excluded from SA-038's manifest and commit. The
  owner may remove the rules after the review; the reviewer edits no registry entry.
- **Owner decisions, taken 2026-10-06 (about 11:05 IST, "yup i agree"):**
  - **IPO-0a: close it.** Delete `ipo_p0_live_window_check` after SA-038 is accepted, as a separate
    small commit with the measured evidence, before its lead window opens on 28 Oct. The missing
    history cross-check is IPO-0e's. This is recorded under IPO-0a in the IPO plan. Afterwards the
    owner removes the four allow rules.
  - **F1 becomes [FIX-004](stories/FIX-004.md)** (P1, 1 point): never date dossier knowledge after
    the day it was learned. Its first step is an owner-run read-only count probe.
  - **Commit SA-038 once accepted,** without `.claude/settings.local.json`, and push in the
    12:05–14:55 IST window.
- **Next, in order:**
  1. **SA-038's fresh-session review,** in a new conversation (opener `continue`). Verify the
     manifest and rebuild the diff with the receipt's recipe. Recheck each judgement against its
     evidence class. The F3 dossier limit and the post-hoc denominator (I5) deserve a hard look.
     The FIX-004 card, the IPO-plan note and these STATE/HANDOFF edits were made after the
     manifest. None of them is a manifest file, so the review input is unchanged.
  2. **SA-010's read-only production check at the 6 Oct 16:30 review** (below, item 3 of the
     SA-010 list). It can run in any conversation; it is read-only.
  3. **After acceptance, at the owner's word:** commit SA-038, then the IPO entry deletion as a
     separate commit, then push at midday.
  4. **FIX-004:** the owner's count probe, then implementation in a new conversation, then its
     fresh review. Then the normal STATE queue resumes.

**Previous: SA-010 was ACCEPTED by its fresh-session review** (5 Oct, about 22:32–23:10 IST, a new
conversation opened with "continue"). Receipt: [review](evidence/SA-010-review.md). STATE:
`active_task: null`, SA-010 `done`, `production_verification: pending_observation`,
`next_task: SA-038`. **Committed as `7efeafd`** at the owner's word (about 23:30 IST, "lets
proceed"), with the KT bump after it. **Pushed and deployed** at 00:10–00:16 IST on 6 Oct
(Railway `8b97dab8`). The review itself committed, pushed, deployed and
configured nothing, read no production state, and made no network call.
- **In one example.** On the baseline code, loaded in memory, HDFCBANK asked Yahoo for
  `^CNXAUTO`. With that index dead, it printed "Nifty Auto Correlation: 0.0 | Beta: 1.0". With
  SA-010 the same input asks for `^NSEBANK` and prints "Nifty Bank Correlation: 0.8384 | Beta:
  1.0597". A dead `^CNXAUTO` now reads "unavailable" with its cause.
- **What the review checked:**
  - review input `911cc91e…` and diff `64bf34d6…` (62,942 bytes), rebuilt with the reviewer's own
    script, with all 14 blobs re-hashed;
  - full suite **4156 passed, 12 skipped, 0 failed**, with `data/` unchanged; focused 548 passed;
  - with the original code in memory, 41 of the 45 new tests fail. The bundle and orchestrator
    tests fail on the defect itself;
  - reviewer mutations: 6 of 8 caught;
  - 5 reviewer probes, 0 failures:
    - 300 yfinance-shaped frames match a plain-Python oracle;
    - the automobile text is byte-identical to the baseline on 60 seeds;
    - edge shapes and 8 sector keys behave as specified;
  - D1–D8 upheld. Broad-except OK, and `check_kt_docs` errors `[]`.
- **Findings.** None is critical, high or medium.
  - **L1 (low, tests).** Two behaviours are unpinned: the `[technicals]` line on the unavailable
    path, and `benchmark` on an empty history. Routed to the SA-031 card.
  - **I1 (info).** A legacy agent declaring `"bfsi"`, `"it"` or `"re"` would get `^NSEI`. None of
    the technical agents does. Routed to the SA-026 card.
  - **I2 (info).** A legacy-fallback run logs a second `[technicals]` line. Written into guide
    02-B and the production check.
  - **I3 (info).** A single-level frame would be reported as "no price data". No action.
- **Review edits (docs only):** KT §4 status (3 places), guide 02-B, the SA-026 and SA-031 cards,
  and the PDF (source `4f10be99…`). `verify SA-010-manifest.json` now mismatches exactly the KT,
  the PDF, the guide and SA-026.
- **Next, in order:**
  1. **DONE: committed and bumped.** `7efeafd` holds the 14 manifest paths, the SA-031 card, the
     three SA-010 evidence files, STATE and HANDOFF. `verify SA-010-manifest.json --rev 7efeafd`
     mismatches only the 4 review-edited docs, so every reviewed code and test byte is committed
     as reviewed. The KT bump declares `7efeafd` (edition 2026-10-05) and says "committed as
     `7efeafd`" in KT §4 and guide 02-B. PDF source `5fc21698…`, and `check_kt_docs` errors `[]`.
     - **PUSHED and DEPLOYED.** At 23:34 the 22:55–00:05 window was open (23:30 backup, 23:45
       audit, 00:00 prompt publish). The owner said "lets proceed" and declined waiting up, so a
       timed job pushed `5772536..a502cf7` at 00:10:07 IST 6 Oct. It was guarded on `origin/main`
       still being `5772536`. Railway `8b97dab8` reached SUCCESS at about 00:16, and `/health`
       returned 200.
     - Boot log: 124 lines, 0 tracebacks, 0 error or warning lines, 24 jobs, and the self-heal
       completed.
     - It was a full build again: 10 patch changes against `f4be41ef`, including langgraph
       1.2.12 → 1.2.13. pandas, numpy, yfinance, openai and nse are unchanged (for SA-033).
     - Raw logs are in the ignored `analysis_data/sa010/deploy/`. This record is uncommitted; it
       rides with the next commit.
  2. **DONE: FIX-002's containment.** The owner re-forecast TATAELXSI at about 23:35 IST, before
     the push, on deploy `f4be41ef`.
     - Run `eac980a4` resolved TATAELXSI to "Tata Elxsi Limited", and 29 days were regenerated.
     - `reforecast_count` is 1 of the month's 2. The Tata Motors-based envelope is archived as
       `archived_envelopes/2026-10_v1.json`, and there was no error line.
     - Inferred from code, not read: its technicals carry the old `^CNXAUTO` 0.0 / 1.0 line, like
       the other October envelopes. It ran inside the 23:30 backup window, so 6 Oct's backup is
       the first that surely holds it.
  3. **Next: SA-010's read-only production check at the 6 Oct 16:30 review** (STATE
     `after_deploy`; `production_verification: pending_observation`).
     - There is one `[technicals]` line per analysis, plus one for a legacy-fallback run.
     - Banking `^NSEBANK`, IT `^CNXIT` and generic `^NSEI`, each with a correlation.
     - Automobile and renewable energy read "unavailable".
     - `^CNXAUTO` ERROR lines fall from 54 to about 9, and about 12 `^CNXENERGY` lines appear.
  4. **SA-038**, by the owner's decision of 2 Oct: started, see above.
  5. **For SA-026, later:** choose an index with data for automobile and renewable energy (D1).

**Previous: SA-010's implementation** (5 Oct, about 20:55–21:50 IST, a new conversation opened
with "continue"; baseline `5772536`). Receipt: [implementation](evidence/SA-010-implementation.md).
Review input: [SA-010-manifest.json](evidence/SA-010-manifest.json). Its record before the review:
- **What was not done:** nothing was committed, pushed, deployed or configured, and no production
  state was read.
- **Local checks only:** a count of `^CNXAUTO` lines in the ignored 2 Oct review log, and one
  read-only probe of public Yahoo data.
- **In one example.** On 2 Oct every analysis asked Yahoo for the automobile index `^CNXAUTO`,
  banks and IT included. Yahoo had no data, so by the code each prompt read "Nifty Auto
  Correlation: 0.0 | Beta: 1.0". Now HDFCBANK asks for `^NSEBANK` and reads "Nifty Bank
  Correlation: … | Beta: …".
  - An index with no data now reads "unavailable" and gives the cause. It is never 0.0 / 1.0.
  - The 5 Oct probe found no Yahoo data for `^CNXAUTO` or `^CNXENERGY`. So automobile and
    renewable-energy stocks now say "unavailable".
  - With data, the automobile text is byte-identical to before.
- **The change:**
  - `settings.SECTOR_BENCHMARKS` holds automobile `^CNXAUTO`, banking `^NSEBANK`, IT `^CNXIT`,
    renewable energy `^CNXENERGY`, and generic `^NSEI` "Nifty 50 (broad market)". Any other or
    empty sector gets generic.
  - `get_peer_correlation` has no default index, and pairs returns over common sessions.
  - `get_technical_result` and `get_technical_context` require `sector`.
  - The bundle and the legacy builders pass the sector. The provenance names the `benchmark`, and
    one `[technicals]` log line is written per call.
- **What was checked:**
  - 45 new tests (`tests/unit/shared/test_sector_benchmark_sa010.py`). With the original modules
    loaded in memory, 41 of them fail. The 4 that pass are paths that were already right.
  - Mutations: 9 of 9 caught.
  - Automobile equivalence: 10 of 10 seeds identical, and the text byte-identical.
  - Focused set: 548 passed. Full suite: **4156 passed, 12 skipped, 0 failed**,
    with `data/` unchanged.
  - Review input `911cc91e…`; diff `64bf34d6…` (62,942 bytes).
  - Broad-except OK. `check_kt_docs` errors `[]`. PDF rebuilt.
- **Decisions for the reviewer (D1–D8 in the receipt):**
  - D1: no proxy index for the two dead ones; that is routed to SA-026.
  - D2: the generic policy is Nifty 50, labelled as the broad market.
  - D3: the technicals status stays the stock's own. Otherwise automobile and renewable energy
    would abstain.
  - D5: in the legacy pool only, an empty agent sector means automobile.
- **Next, in order:**
  1. **SA-010's fresh review,** in a new conversation (opener `continue`).
  2. After acceptance: commit, KT bump (the KT now links `fetcher.py`) and push at the owner's
     word, in a job-free window.
     - Then the read-only production check at the next 16:30 review: one `[technicals]` line per
       ticker; banking `^NSEBANK`, IT `^CNXIT` and generic `^NSEI`, each with a correlation.
     - yfinance's `^CNXAUTO` ERROR lines should fall from 54 to about 9, with about 12
       `^CNXENERGY` lines appearing.
  3. **Still open from FIX-002:** the owner-run containment re-forecast of TATAELXSI. The command
     is in FIX-002's step 3.
  4. **Then SA-038, by the owner's decision** (2 Oct). It goes straight after SA-010's review.
  5. **For SA-026, later:** choose an index with data for automobile and renewable energy. The
     probe saw Nifty Auto ETFs listed, but none was evaluated.

**Previous: FIX-003 — accepted, committed, deployed and verified** (2 Oct). The block below is its
record as of the 2 Oct 16:30 check.

**FIX-003 was ACCEPTED by its fresh-session review** (2 Oct, about 06:12–06:30 IST, a new
conversation opened with "continue"). Receipt: [review](evidence/FIX-003-review.md). STATE:
`active_task: null`, FIX-003 `done`, `production_verification: pending_deployment`,
`next_task: SA-010`. **Committed as `110288e`** at the owner's word ("commit and push", about
06:58 IST), with the KT bump after it. The review itself committed, pushed, deployed and
configured nothing, and read no production state.
- **In one example.** On 1 Oct YES Bank's June quarter was on file, but its statement has no
  operating-income line, so the gate abstained and the prompt said "EBITDA Margin: 0.0%". The
  review ran YES Bank's real yfinance rows through the banking sector's own orchestrator. With
  the original code it reproduced production's row: `essential fundamentals=fallback`, so the
  gate abstained. With FIX-003, fundamentals read `ok` and the gate is `actionable`.
- **What the review checked:**
  - review input `ee46239f…` and diff `57e84772…`, rebuilt with the reviewer's own script;
  - full suite **4111 passed, 12 skipped, 0 failed**, with `data/` unchanged; focused 327 passed;
  - with the original code loaded in memory, 28 of the 55 new tests fail; reviewer mutations
    9 of 9 caught;
  - 6 reviewer probes passed:
    - on the real row sets of the 14 listings the implementer probed, the 8 lenders go from
      `fallback` to `ok` (HDFCBANK reads `stale`, because its newest yfinance quarter is a year
      old), and the 6 others read exactly as before;
    - 2,000 random statements: every non-bank shape is identical to the original code, and every
      bank shape matches the reviewer's own rule;
  - broad-except OK, and `check_kt_docs` errors `[]`.
- **Findings.** None is critical, high or medium.
  - **L1 (low), fixed in review.** Guide 02-H asked the tester to match the section's revenue with
    the bank's published results. yfinance's "Total Revenue" for YES Bank (₹4,655.98 Cr) is below
    its own interest income (₹8,054.49 Cr), so it cannot match a filing's total income. 02-H now
    compares net interest income only, and KT §4 says why in one sentence.
  - **I1 (info).** A bank whose statement also lists an operating row with no figures stays
    `fallback`, by the card's row-presence rule. None of the 8 lenders does today. If a bank
    still shows `fundamentals:fallback` after the deploy, look there first.
- **Review edits (docs only):** KT §4 (the status and the revenue sentence), guide 02-H, the PDF
  (source `8c60e10e…`). `verify FIX-003-manifest.json` now mismatches exactly the KT, the PDF and
  the guide.
- **Next, in order:**
  1. **DONE: committed and bumped.** `110288e` holds the 6 manifest paths, the 3 evidence files
     (implementation, manifest, review), STATE and HANDOFF (with FIX-002's push record).
     `verify FIX-003-manifest.json --rev 110288e` mismatches only the 3 review-edited docs, so
     every reviewed code and test byte is committed as reviewed. The KT bump declares `110288e`
     and says "committed as `110288e`" in KT §4 and guide 02-H. PDF rebuilt (source
     `cf990cb4…`), and `check_kt_docs` errors `[]`.
     **PUSHED and DEPLOYED:** `df34176..5772536` at 07:00:38 IST, in the 06:30–07:25 gap (the
     06:30 watchdog had run; `macro_daily_news` is at 07:30). Railway `f4be41ef` SUCCESS at
     about 07:06.
     - It was a **full build**: the pip layer re-ran although `requirements.txt` did not change.
       Against the 29 Sep full build `26b442f4` there are 13 minor or patch changes: fastapi
       0.141.1 → 0.142.2, transformers 5.17.0 → 5.18.0, torch 2.14.0 → 2.14.1, cryptography
       50.0.1 → 50.0.2, and 9 transitive packages. None is in pandas, numpy, yfinance, nse,
       openai, pydantic, APScheduler or langgraph. This is for SA-033's pinning.
     - Boot log: 124 lines, 0 tracebacks, 0 error or warning lines, 24 jobs. The self-heal
       completed at 07:06:07 with 0 envelopes. `/health` 200.
     - Raw logs are in the ignored `analysis_data/fix003/deploy/`. This push record is
       uncommitted; it rides with the next commit.
  2. **DONE: FIX-003's and FIX-002's production checks PASSED** (read-only, about 17:30 IST).
     They used the `f4be41ef` logs of the 16:30–16:53 review, which graded 1 Oct: 1,146 lines,
     and no fetch was capped. STATE `production_verification`: both `verified`.
     - **FIX-003:** YESBANK, IDFCFIRSTB, RBLBANK and FEDERALBNK read `banking_bfsi ok`,
       fallback 0, dimensions 6/6, with no essential section unusable. None of the 18 analysed
       tickers has one. The analysis gate would abstain on 1 of 18: STARHEALTH, with 2 of 8
       dimensions. The 1 Oct forecast abstained on 6 of 20, 4 of them the banks.
       - The stored reason text and the prompt were not read. That the banks took the
         bank-format path is inferred from their `ok` status, which only that path gives these
         statements.
     - **FIX-002:** all 18 analysed tickers resolved to themselves, with 0 `Serper fallback` and
       0 `ticker_resolution` lines. TATAELXSI is "Tata Elxsi Limited", and HAPPSTMNDS is
       "Happiest Minds Technologies Limited" (1 Oct: "Happy Smile Digital Ltd").
       - WELCORP and TMPV were not analysed: they had no 1 Oct row, because neither had a
         September envelope.
     - **Seen, expected, and it matters for the next SA-003 decision.** The review gate says
       "provenance unknown" on 17 of 18 rows.
       - Why: 1 Oct is not in the October envelopes, so the review grades it from September's,
         which predate SA-003. RBLBANK's September envelope was re-forecast on 28 Sep and
         carries `abstain`.
       - Under `enforce`, those gradings would be skipped. The rows the next decision counts
         must come from envelopes issued after the fixes.
     - **Errors:** all 54 ERROR lines are the known `^CNXAUTO` yfinance failure (SA-010).
     - Raw log: the ignored `analysis_data/fix003/deploy/review_20261002.log`.
  3. **Still open from FIX-002 (below):** the owner-run containment re-forecast of TATAELXSI (the
     command is in FIX-002's step 3).
  4. **Then SA-010's implementation,** in a new conversation (opener `Continue`).
  5. **Then SA-038, by the owner's decision** (2 Oct, about 16:30 IST: "keep as per
     recommendation"). It goes straight after SA-010's review, ahead of its place in STATE.
     - **Why:** the 06:30 ops alert "F3 provenance checkpoint … LAPSED, deadline 2026-09-04".
       That entry is a date-only `manual_confirmation` reminder in `config/milestones.yaml`. It
       re-sends a critical every 7 days until the entry is removed. It is not a production
       failure.
     - **Until then,** weekly "LAPSED" alerts for the old entries are expected.
     - **What it needs:** F3, B1 and A1(b) each need one read-only volume probe, which the owner
       runs.

**Previous: FIX-003's implementation** (2 Oct, about 01:25–02:00 IST, a new conversation;
baseline `df34176`). Receipt: [implementation](evidence/FIX-003-implementation.md). Review input
[FIX-003-manifest.json](evidence/FIX-003-manifest.json) `ee46239f…`; diff `57e84772…` (32,922
bytes). Its record before the review:
- **In one example.** On 1 Oct YES Bank's June-quarter figures were on file (revenue
  ₹4,655.98 Cr), but a bank's statement has no operating-income line. The fetcher substituted
  zeros, so fundamentals read `fallback`, the gate abstained, and the prompt said "EBITDA
  Margin: 0.0%". Now a statement with interest income and net interest income and no operating
  row is read as **bank-format**: it reads `ok`, the reason names the format, and the prompt
  shows net interest income (₹2,785.48 Cr) and "Operating margin: not reported".
- **The change:** one code file, `services/data/fetchers/fundamentals.py`. The shape decides,
  never the ticker: PAYTM reports EBIT and stays standard. Revenue, freshness and SA-002's
  blank-quarter rule still apply, with net interest income in the operating line's place.
- **What was checked:**
  - 55 new tests (`tests/unit/shared/test_bank_statement_fix003.py`): a hand-written table of 15
    statement shapes × 3 tickers, the exact prompt text (bank and standard), and the gate end to
    end for the 4 banks, with a counterpart that still abstains;
  - with the original code put back, 28 of the 55 fail (every bank case); mutations 12 of 12
    caught;
  - focused 327 passed; full suite **4111 passed, 12 skipped, 0 failed** (6 min 11 s), with
    `data/`, `logs/` and `outputs/` unchanged;
  - broad-except OK, `check_kt_docs` errors `[]`, PDF rebuilt.
- **Decisions for the reviewer (D1–D6 in the receipt):** the card's shape rule as written (a
  read-only probe of 14 listings supports it); the prompt states operating margin is not
  reported and shows net interest income, labelled; net interest income is held to SA-002's
  blank-quarter rule; lenders such as BAJFINANCE count by shape; `get_peer_margins` leaves a
  bank out; the KT's "Current gap" now cites the 1 Oct measurement.
- **Docs:** KT §4 "Bank statements (FIX-003)" and "Current gap"; guide 02-H (new); an SA-045
  routed-input note; the PDF. The landing commit needs a KT bump (the KT now links
  `fundamentals.py`).
- **Next, in order:**
  1. **DONE: FIX-003's fresh review** (accepted 2 Oct, about 06:30 IST; the block above).
  2. **Still open from FIX-002 (below):** the read-only check at the 2 Oct 16:30 review, and the
     owner-run containment re-forecast of TATAELXSI (the command is in FIX-002's step 3). Neither
     depends on FIX-003.
  3. After FIX-003 is accepted: commit, KT bump and push at the owner's word, in a job-free
     window. Production check (read-only): the next review's health lines for the four banks
     show no `essential unusable=fundamentals:fallback`. Their October envelopes keep the gate
     they were issued with; the next SA-003 decision needs the 1 Nov forecast or an
     owner-authorised regeneration of those four envelopes.
  4. Then SA-010.

**Previous: FIX-002** (accepted, committed, pushed and deployed; its production checks above
are still open):

**FIX-002 was ACCEPTED by its fresh-session review (1 Oct, about 21:20–21:50 IST, a new
conversation) and is COMMITTED as `656ed71`** at the owner's word ("ya commit and push FIX-002",
about 00:30 IST 2 Oct), with the KT bump after it. `verify FIX-002-manifest.json --rev 656ed71`
mismatches only the 3 review-edited docs, so every reviewed code and test byte is committed as
reviewed. STATE: `active_task: null`, FIX-002 `done`, `next_task: FIX-003`. Receipts:
[implementation](evidence/FIX-002-implementation.md) and [review](evidence/FIX-002-review.md).
- **In one example.** At 09:16 on 1 Oct the monthly forecast asked the IT orchestrator for
  TATAELXSI. Its short cut knew only the IT built-in list, so an LLM was asked and answered
  TATAMOTORS. The run analysed Tata Motors, and it also used Tata Motors' learned weights in
  place of the ones the forecast passed in. Now TATAELXSI is found in the managed list and
  resolves to itself, with no LLM call, and keeps its own weights.
- **What the review checked:**
  - review input `98ed116a…` and diff `bc726da8…` verified;
  - full suite **4056 passed, 12 skipped, 0 failed**, with `data/` unchanged;
  - focused 162 passed;
  - with the original defect put back in memory, 11 of the 20 new tests fail;
  - 10 of 10 independent probes passed. They include production's 21 tickers in all 5
    orchestrators, and the forecast traced through the real `analyse()`;
  - broad-except OK, and `check_kt_docs` errors `[]`.
- **Findings:** none in the change. Two follow-ups predate FIX-002 and are routed as card notes:
  - **M1 → [SA-026](stories/SA-026.md).** The weekly discovery deep dive still sends candidate
    symbols to the LLM. A renamed candidate can mint a shelf idea, a SWITCH destination, from
    another company's analysis;
  - **L1 → [SA-031](stories/SA-031.md).** `load_registry` raises on a registry file that is not
    valid UTF-8.
- **Review edits (docs only):** KT §4 (the status, the weights, and a sentence on discovery),
  guide 02-G's status, the PDF. `verify FIX-002-manifest.json` now mismatches exactly the KT, the
  PDF and the guide.
- **Next, in order:**
  1. **DONE: committed and bumped.** `656ed71` holds the 8 manifest paths, the 3 evidence files,
     STATE, HANDOFF and the SA-026 and SA-031 cards. The KT bump declares `656ed71` (edition
     2026-10-02). It also marks FIX-001 deployed and confirmed by the 1 Oct audit (KT §4 and §8,
     guide 05-G). PDF rebuilt (source `806b5894…`), `check_kt_docs` errors `[]`.
     **PUSHED and DEPLOYED:** `da66fee..df34176` at 00:33:13 IST 2 Oct. Railway `8983ab80`
     SUCCESS at 00:34:32 (cached build). The boot log has 124 lines, 0 tracebacks and 0
     error or warning lines. The scheduler registered 24 jobs, and startup and self-heal
     completed, with no ticker resolved at boot. `/health` 200. This push record is
     uncommitted; it rides with the next commit.
  2. **Production check (read-only), after the deploy:** the next 16:30 review logs
     `Resolved: X -> ticker='X'` for every managed ticker, with no `Serper fallback` line and no
     `ticker_resolution` call for them. Fri 2 Oct is an NSE holiday in the app's calendar, but
     the review still runs at 16:30 (Mon–Fri) and re-runs every ticker's analysis for the 1 Oct
     session. So with a push tonight, 2 Oct 16:30 is the first full check.
  3. **Containment needs the owner's authorisation, after the deploy.** Re-forecast TATAELXSI's
     October envelope with the implementation receipt's "Rollout" command. The owner runs it
     through `railway ssh`, because Claude's `railway ssh` is blocked. It is safe without a
     pre-check: if re-forecasts are off or the monthly cap is reached, it prints `[SKIP]` and
     changes nothing. It anchors on the newest close, so it works on the 2 Oct holiday too. Its
     own log line `Resolved: TATAELXSI -> ticker='TATAELXSI'` is an early production check of
     FIX-002. Record the archive name it prints and the new run id. It sends no email or push.
     The owner runs it from Git Bash in a job-free window and pastes the filtered output:

     ```bash
     railway ssh "cd /app && python -m services.scheduler.run_schedule reforecast --ticker TATAELXSI --sector it_sector --reason 'FIX-002 containment: the 1 Oct envelope was built from a TATAMOTORS analysis' 2>&1 | grep -E 'Resolved:|Run [0-9a-f]+ started|\[OK\]|\[SKIP\]|Archived|reforecast_count|regenerate_envelope|Traceback|Error'"
     ```
  4. **FIX-003's implementation,** in a new conversation (opener `Continue`), then SA-010.
- **FIX-001's production check PASSED** (read-only, 23:47 IST; step 2). The 23:45 audit had no
  `dropna` error. It graded 27 rows, IPO 4, with 0 skipped in every lane, against IPO 2 graded
  and 2 skipped on 30 Sep. It fetched SWASTIKAIN's and ADROITIND's 30 Sep closes (209.95 and
  248.35) from Yahoo; NSE had no row.
- **Seen, outside FIX-001, watch tomorrow:** the 23:30 backup's email copy failed
  (`SMTPServerDisconnected`, `emailed=False`). The backup archive itself was written. Earlier
  nights emailed it. If 2 Oct's 23:30 run fails the same way, look at it under SA-007.

**0. Step 0 is DONE (1 Oct, about 10:20–10:40 IST). SA-039 P3 passed, and the delegated SA-003
enforce decision is NO-GO: the gate stays in `record`.** Nothing in production changed. Check
STATE `pending_production_checks` again only if a new entry appears.

- **P3, in one example.** The 09:00 monthly forecast made 20 October envelopes, one per enabled
  ticker. Every one was made with `learning_mode=observe` (logs, deploy `14d13162`), including
  TMPV's, which the job regenerated at 09:25:53. None was made for the disabled TATAMOTORS.
  18 weight versions still equal the 26 Sep baseline. The stored field is inferred from code,
  not read from the volume. See the [activation record](evidence/SA-039-activation-2026-09-26.md),
  P3. SA-039's observation window is complete (P1 28 Sep and P2 29 Sep passed earlier).
- **The SA-003 decision, in one example.** YES Bank's June-quarter results are on file, but a
  bank's statement has no "operating income" line. The fetcher fills it with zero and marks
  fundamentals `fallback`, so the gate abstains on every bank analysis. Under `enforce`, four
  banks would get no October forecast and no learning, on fine data. The rules' measures:
  - **(a) met:** 25 of 78 analyses (28 Sep–1 Oct) would abstain, 32%. The 4 banks alone are 22%;
  - **(b) met:** 3 of 5 spot-checked abstentions had fine data (the banks);
  - **wait condition (4) not met:** only 3 review days. Because the cause is structural, the
    outcome is NO-GO rather than WAIT;
  - **F1:** 6 of 20 October envelopes abstain. **F2:** 0 `actual_close` rows.

  See the [decision record](evidence/SA-003-enforce-decision-2026-10-01.md). **Re-decide by the
  same rules** after FIX-002 and FIX-003 are deployed and at least 5 review days have rows
  issued after them: the 1 Nov forecast, or an owner-authorised regeneration of the affected
  envelopes.
- **Found at P3: TATAELXSI was analysed as TATAMOTORS.** The IT orchestrator sends managed
  tickers that are missing from its static `TICKERS` list to an LLM. At 09:16 that LLM answered
  TATAMOTORS, and TATAELXSI's October envelope was saved from a Tata Motors analysis.
  SA-008's identity gate recorded it, in record mode. The same path resolved TVSMOTOR to
  TVSMOTORS on 29 Sep, and named HAPPSTMNDS "Happy Smile Digital Ltd" today. SA-039 `observe`
  keeps the stored weights unchanged meanwhile.
- **Two routed fixes were added to the board as `todo`** (STATE, P1, 1 point each). They are
  recommended next after FIX-001's review and before SA-010:
  - [FIX-002](stories/FIX-002.md): a managed ticker resolves to itself, with no LLM call. After
    its deploy, the owner authorises regenerating TATAELXSI's October envelope;
  - [FIX-003](stories/FIX-003.md): a bank-shaped statement reads as complete, with no invented
    zero.
- **Raw diagnostics** are in ignored `analysis_data/sa039/` (`p3_*`, `gate_rows_2026092*`,
  `review_gate_rows.py`). They hold counts, tickers, reasons and run ids only.

**1. SA-007 change 1 is committed as `8663387`** at the owner's word ("ya commit and push",
about 14:37 IST). `verify SA-007-change1-manifest.json --rev 8663387` mismatches only the 3
review-edited docs, so every reviewed code and test byte is committed as reviewed.

- **The KT bump follows it.** It declares `8663387` (`check_kt_docs` errors `[]`, no linked
  source changed since it, PDF 28 pages).
- **The bump also fixes the routed status wording (the earlier review's I2)** in the KT,
  ARCHITECTURE and the guide:
  - SA-004 was deployed as `b3fb00dd` on 27 Sep;
  - SA-005's CI first ran on 28 Sep (`36453992259`, 3 of 3 jobs);
  - SA-006 was deployed as `00b94de9` on 28 Sep.
- **Pushed and deployed.** The push waited out the 14:55–15:05 jobs.
  - **The push:** `cd33fc4..e3bb6a3` at 15:06:23 IST.
  - **The deploy:** Railway `f2e23722` reached SUCCESS by 15:07:26 IST. It was a cached build,
    because `requirements.txt` did not change.
    - Boot log: 124 lines, 0 tracebacks and 0 error or warning lines; the scheduler started
      with 24 jobs.
    - `/health` returns 200 `ok`.
  - **CI:** run `36550251651` on `e3bb6a3` passed 3 of 3 jobs. Python tests on Linux / 3.11
    took 152 s, the guards 15 s and Chromium 60 s.
  - **What production should now show.** Change 1 landed before the first production run of
    `backup_recoverable`, which is Wed 30 Sep 06:30.
    - That morning's "No off-site copy has ever been confirmed" is the first weekly notice.
      **Observed Wed 30 Sep 06:30.** The owner pasted the alert: one warning, reading "…
      repeats weekly until a target is configured". `checks.py` gives that wording only when
      three things hold: the backup ran within 36 h, its restore drill passed with no warnings,
      and no off-site target is set. So the 29 Sep 23:30 backup, the first in production with a
      drill, passed it. That is inferred from the notice; `backup_status.json` was not read.
    - Thu 1 Oct to Tue 6 Oct should be silent for this entry. The Thursday check is read-only.
  - This record (STATE and HANDOFF) is uncommitted. It rides with the next commit.

**2. FIX-001 was ACCEPTED by its fresh-session review** (1 Oct, about 15:10–15:35 IST, a new
conversation). See the [review receipt](evidence/FIX-001-review.md). At the owner's word ("go
ahead commit and push FIX-001 now", about 18:00 IST) it is **committed as `0493f7c`**, with the
KT bump after it (header `0493f7c`, edition 2026-10-01). `verify FIX-001-manifest.json --rev
0493f7c` mismatches only the 3 review-edited docs, so every reviewed code and test byte is
committed as reviewed.
- **Production check: PASSED** (read-only, 1 Oct 23:47 IST, deploy `e7a994a5`). The 23:45 audit
  had no `'numpy.float64' … 'dropna'` line. It graded 27 rows, with 0 skipped in any lane. The IPO
  lane graded 4, against 2 graded and 2 skipped on 30 Sep. The daily review fetched SWASTIKAIN's
  30 Sep close (209.95) and ADROITIND's (248.35) from Yahoo: the `.NS` download was empty, so the
  bar came from the `.BO` or 1-year attempt, and NSE had no row.
  - That the two 30 Sep rows are among the 4 graded is inferred from these lines; the stored rows
    were not read.
  - STATE `production_verification`: `verified`.
- **In one example.** An issue lists at issue price 100, and its listing-day download holds one
  bar, at 131.2. Before the fix, the audit skipped the row. Now it stores exit 131.2, a return of
  +31.2% and `correct` True. The probe ran the real `close_on` and `grade_ipo_lane`.
  - 3,000 random multi-bar frames give the same result as at `290b3f7`.
  - Mutations: 4 of 4 caught.
  - Full suite: 4036 passed, 12 skipped, 0 failed.
- **Findings.** None is critical, high or medium.
  - **L1, low**, routed to [SA-012](stories/SA-012.md). `close_on` drops the bar's date, so a
    carried-forward close is stored as the session's. That predates FIX-001. FIX-001 adds one
    route, which reaches only unmarked IPO rows at horizons 5 and later.
  - **I1** was fixed in review: KT §8 no longer claims IPO grading on 29 Sep.
  - **I2** is an inference and needs no action.
- **Review edits** (documentation only): KT §4 and §8, the PDF, guide 05-G and an SA-012 card
  note. `verify FIX-001-manifest.json` now mismatches exactly the KT, the PDF and the guide.
- **The commits.** `0493f7c` holds the code, the tests, the KT, guide and PDF, the review receipt,
  the SA-012 note, STATE and HANDOFF. The KT bump after it is `da66fee` and declares `0493f7c`.
- **Pushed and deployed.**
  - **The push:** `3deade8..da66fee` at 18:02:56 IST, in the 18:00–18:55 job-free window.
  - **The deploy:** Railway `e7a994a5` reached SUCCESS by 18:04:16 (a cached build).
    - Boot log: 124 lines, 0 tracebacks, 0 error or warning lines, 24 jobs; startup and the
      self-heal completed.
    - `/health` returned 200 at 18:05.
  - **CI on `da66fee`:** not read here, because the `gh` CLI is not installed. The owner reads
    the Actions page.
  - This record is uncommitted. It rides with the next commit.
- **Production check, still to do (FIX-001 `pending_observation`):** tonight's 23:45 nightly
  audit should show no `'numpy.float64' … 'dropna'` line, and should grade the 30 Sep SWASTIKAIN
  and ADROITIND rows if Yahoo or NSE has the bar.

**2c. Done: FIX-002's implementation** (the block at the top). It was planned here as the next
phase, in a new conversation, then FIX-003, then SA-010. Read the
[FIX-002 card](stories/FIX-002.md) first.
- **Pushed and deployed, 1 Oct.** At the owner's word ("go ahead and commit and push"), the
  step 0 records were committed as `3deade8`. That commit also holds FIX-001's card, receipt and
  manifest, because HANDOFF links them; its code, tests and KT/PDF edits are NOT committed.
  - **The push:** `2c632e2..3deade8` (with `290b3f7`) at 11:32:38 IST, after the 09:00 forecast
    and before the 11:55 job.
  - **The deploy:** Railway `ccd6ca78` reached SUCCESS by 11:34:01. Boot log: 124 lines, 0
    tracebacks, 0 error or warning lines, 24 jobs; the self-heal completed without generating
    any envelope. `/health` returned 200 at 11:34.
  - **CI on `3deade8`:** not read here. A clean worktree's `check_kt_docs` passed every link check;
    its only errors were Windows "Filename too long" artifacts of the temp path.
  - FIX-001 stays uncommitted until its review.

**2b. Earlier plan, superseded by step 2: SA-010's implementation**, in a new conversation. Opener: `Continue`. STATE:
`active_task: null`, `next_task: SA-010`, `next_phase: implementation`. **Run step 0 first:** P3 is
due Thu 1 Oct 09:30, then the SA-003 enforce decision.
- **SA-009 change 1 was ACCEPTED** by its fresh review (about 17:50–18:15 IST; the block below).
  At the owner's word ("ya commit and push", about 22:20 IST) it is committed as `9c626a5`, with
  the KT bump after it (header `9c626a5`). **Pushed and deployed:** `e698c68..2c632e2` at
  22:24:37 IST; Railway `14d13162` SUCCESS 22:26:11 (cached build); boot log 125 lines, 0
  tracebacks, 0 error or warning lines, 24 jobs, self-heal complete in 10 s; `/health` 200 at
  22:29. CI on `2c632e2` was not read here: the owner reads the Actions page.
- SA-008 change 1 stays open. It must be accepted before any `successors` record.

**FIX-001 was IMPLEMENTED on 2026-10-01** (about 00:40–01:00 IST, in this conversation at the
owner's word: "The small price-lookup fix - go ahead as well"). It is uncommitted. Its fresh
review accepted it at about 15:35 IST (step 2 above); the bullets below are the pre-review record.
- **In one example.** On a listing day the 7-day download holds one bar. `squeeze()` turned it into
  a number, and `.dropna()` raised, so SWASTIKAIN's and ADROITIND's listing-day closes were
  discarded on 30 Sep. Now the bar is read like any other, dated its session, and cross-checked
  against NSE.
- **The change:** `daily_review._fetch_session_close._extract` and
  `close_verifier._fetch_yfinance_close`. Frames with two or more bars take the same path as
  before. A NaN last row stays a failure.
- **Checks:**
  - 10 new tests, and focused 24 passed;
  - mutations 3 of 4 caught: the original defect fails 6 tests, and M4 is equivalent;
  - full suite **4036 passed, 12 skipped, 0 failed**, `data/` unchanged;
  - `check_kt_docs` errors `[]`.
- **Docs:** KT §4 and §8 (the first production IPO rows; the skipped listing-day rows), guide
  05-G, the PDF, and the [card](stories/FIX-001.md).

**2a. The 30 Sep audit alert ("audit_nightly completed 25/27"), diagnosed from the log.** Only the
IPO lane missed: 2 listing-day rows (SWASTIKAIN, ADROITIND) got no close. The close lookup discards
a one-bar Yahoo table (`squeeze()` turns it into a number, and `.dropna()` fails). The NSE fallback
rescued ELEVATE and ARMEE, but not these two. The bug is pre-existing (1 May; also seen 29 Sep) and
reproduced locally. `close_on` shares it, so a holding on its listing day has the same gap. The
diagnosis and fix are in a note on the [SA-040](stories/SA-040.md) card; the fix waits for the
owner's word. The 23:30 backup that night was clean (drill passed, emailed; off-site unset as
expected).

**3. SA-008 and SA-009 are pushed and deployed** (the owner's word, about 13:00 IST: "ya commit
and push").
- **The commits:** SA-009 is `313e3f6`, with its KT bump `e698c68`. `verify SA-009-manifest.json
  --rev 313e3f6` mismatches exactly the 4 review-edited docs. SA-008 is `02c43f6`, with its bump
  `f443cc7`.
- **The push:** `e3bb6a3..e698c68` at 13:07:23 IST, in the 12:05–14:55 job-free window.
- **The deploy:** Railway `650bb98c` reached SUCCESS at 13:13:09 IST, a cached build, because
  `requirements.txt` did not change.
  - Boot log: 127 lines, 0 tracebacks and 0 error or warning lines. The scheduler started with
    24 jobs.
  - The self-heal skipped all 20 tickers on September's checkpoint, as expected. The new
    per-sector behaviour starts with October's first restart.
  - `/health` returned Railway's edge 404 "Application not found" for about 4½ minutes after
    SUCCESS, then 200 `ok` from 13:17:48.
- **CI:** run `36684772155` on `e698c68` passed 3 of 3 jobs: guards 13 s, Python tests on Linux /
  3.11 154 s, Chromium 112 s.
- **The owner's rollout steps (not done yet; the owner said "go ahead on the rollout recommended"
  at about 22:20 IST).** Claude cannot do them: the dashboard steps need the owner's login, and
  Claude's `railway ssh` was denied by the auto-mode classifier ("Production Reads"). So the
  owner runs each step and pastes the output. Order matters: the dashboard steps first, because
  the plan's digest pins the managed list. At the owner's request Claude wrote a helper the owner
  runs from Git Bash (ignored, local): `bash analysis_data/sa009/rollout/run.sh check` (read-only:
  TATAMOTORS/TMPV entries, learned symbols, inventory summary, plan digest with ITEM/HOLD/FLAG
  lines), then `run.sh apply <digest>` (refuses unless the fresh plan has that digest and the IST
  time is 00:10-06:20 or 12:05-14:55), and `run.sh rollback <migration id>`. It calls only the
  SA-009 modules. Tested locally on the fixture tree with the real wiring: check wrote nothing,
  apply moved the 3 strays, rollback was byte-identical.
  - **First production check (owner, about 23:35 IST, read-only).** The dashboard step was not yet
    done (TATAMOTORS enabled, TMPV absent). SA-008 L2: no managed ticker has a learned symbol, and
    `AUTO_TICKERS` is unset. The plan (`ce3556d0…`) moves 16 stores and holds or flags none:
    every `automobile/<TICKER>` copy of a ticker managed in another sector, each with its owner
    store present. The copies now hold 19–21 files and 150 conflicting graded days, against
    weights and 1–2 envelopes on 10 Sep (the writer is inferred, not verified).
  - **Apply rule given to the owner:** after the dashboard step, re-run `check`. Apply its new
    digest only if it shows `DASHBOARD STEP DONE`, `PLAN items 16 holds 0 flags 0`, and the same
    16 `ITEM` lines with the same file counts. Otherwise paste the output and do not apply.
  - **Second check (owner, about 23:55 IST) was identical:** inventory `974e6043…`, plan
    `ce3556d0…`, the same 16 items and file counts, and the dashboard step still not done. So nothing
    wrote to the 16 copies between the checks, which included the 23:45 audit.
  - **Claude approved plan `ce3556d0…`** (delegated: "go ahead on the rollout recommended"). The
    dashboard step touches none of the 16 stores, so the order can be: apply first, in 00:10–06:20,
    before any dashboard change; then the dashboard step before 09:00; then a final `check`
    (expect `DASHBOARD STEP DONE`, `PLAN items 0`, no `DUP` lines). If the dashboard step comes
    first, the digest changes, apply refuses, and the earlier rule applies to a new check.
  - **APPLIED 1 Oct 00:10:31 IST** (owner, `run.sh apply ce3556d0…`). Migration
    `20260930T184031Z-ce3556d023d3`: 16 of 16 stores `moved`, with unchanged bytes. The inventory after
    (`c1708d20…`) has 168 stores, 0 duplicate tickers, 0 duplicate envelopes or graded days (36
    and 150 conflicting before) and 0 wrong-roster stores. The undo is `run.sh rollback 20260930T184031Z-ce3556d023d3`.
    **The dashboard step as one command** (owner asked, about 00:20 IST): `run.sh dashboard` calls the
    app's own routes on localhost, with the machine key from the container's environment, never
    printed. It toggles TATAMOTORS off only if it is enabled, never calls remove, and adds TMPV
    (automobile) only if absent. It is safe to run twice, and was tested locally against a fake app.
    **Then to do (done, below):** the dashboard step before 09:00, then a final `check` (expect `DASHBOARD STEP
    DONE`, `PLAN items 0`, no `DUP`). Later, a check after October's first restart should show no
    new `automobile/<TICKER>` copy with files.
  - **ROLLOUT COMPLETE (1 Oct 00:30–00:33 IST).**
    - `run.sh dashboard`: TATAMOTORS is disabled (not removed) and TMPV is added (automobile).
      TMPV's October envelope was done at 00:32:06 (weights v0). The log since 00:00 has 0 errors.
    - Final check: `DASHBOARD STEP DONE`; 169 stores; 0 duplicates; 0 wrong-roster stores;
      plan 0 items, 0 holds, 0 flags.
    - **For P3 at 09:30:** no TATAMOTORS October envelope is expected (it is disabled). TMPV's
      envelope came from the add route at 00:32, not the 09:00 job; check that it too says `observe`.
    - **Left to observe:** October's first restart creates no `automobile/<TICKER>` copy with files
      (a later `check`); new feedback logs carry their store's sector; the scorecard lists each
      moved ticker once.
  - **SA-008:**
    - **Disable** TATAMOTORS with the toggle. **Never remove it:** removing deletes its history.
    - Add TMPV: sector `automobile`, name "Tata Motors Passenger Vehicles Ltd". The add starts
      its envelope in the background.
    - Suggested timing: any time now, before Thu 09:00, so the monthly forecast includes TMPV and
      skips TATAMOTORS. The 30 Sep 16:30 review already showed TATAMOTORS' `identity` stage once
      in production.
    - Also a read-only look at the volume's `data/yf_symbol_cache.json` (SA-008 review L2).
  - **SA-009:** run the inventory and the plan read-only on the volume, and paste the summary
    lines, the items and the holds. The commands are in the SA-009 receipt's "Rollout". Before
    approving, check `owner_store_present` on every item (review I4). Apply only by the plan's
    digest, in a job-free window after the 23:30 backup. It is best to wait until change 1 is
    deployed, so the rollback has its fixes. Change 1 is accepted but not yet committed. A plan
    made now keeps its digest after change 1 deploys (review Q6).
- **Production checks after the deploy:**
  - **today's 16:30 review, observed read-only at about 17:33 IST (the `650bb98c` log to 17:01).**
    - It graded 29 Sep for all 20 tickers in `observe`. There were 19 proposals not applied, 0
      `Weights → v` lines and 0 tracebacks.
    - The outcome was 19/20. The missing one is WELCORP with `no_envelope`, which is known and
      pre-existing.
    - SA-008's `identity` lines name only TATAMOTORS, both "would skip (record mode)": once in the
      analysis gate and twice for the review.
    - The yfinance `^CNXAUTO` "possibly delisted" errors are pre-existing: 38 lines in the 29 Sep
      review on `f2e23722`, 40 today. They belong to SA-010's benchmark work.
    - The ERROR and WARNING totals are 67 and 79, against 88 and 87 the day before;
  - still to observe: new October feedback logs carry their store's sector, and October's first
    restart checks each ticker's own store.

**SA-009 change 1 was ACCEPTED on 2026-09-30 by a fresh-session review** (a new conversation,
about 17:50–18:15 IST). Receipt: [SA-009-review.md](evidence/SA-009-review.md), section "Change 1
fresh-session review". No SA-039 check was due. Nothing was committed, pushed, deployed,
configured or sent, and no production state was read.

- **Input verified:** `7f2a4a2a…` (9 files, 0 mismatches, no unlisted change). The diff
  `e3a04386…` was rebuilt with the reviewer's own script.
- **Traced:** `rollback` touches files in only two ways. It removes an empty live directory with
  `rmdir`, and it renames back a store whose bytes equal the record. `PredictionStore` creates
  only the store's own directory on a read.
- **An example the change also fixes (probe Q1).** A rollback crashes after renaming
  `automobile/SUZLON` back, before recording it.
  - Before: every later run said `refused_quarantine_missing` and `partial`.
  - Now: the next run finds the store live with its recorded bytes (`found_live`) and reports
    `rolled_back`.
- **Checks:**
  - reviewer probes 8 of 8;
  - reviewer mutations 4 of 6 caught (RA is L1, RD is telemetry);
  - focused 45 passed;
  - full suite **4026 passed, 12 skipped, 0 failed** (5 min 16 s), `data/` unchanged;
  - broad-except OK, and `check_kt_docs` errors `[]`.
- **C1–C4 upheld.**
- **Findings.** None is critical, high or medium, and there is no code defect.
  - **L1 (low, tests; predates change 1):** no test pins that a store restored with other bytes
    (`rolled_back_changed`) keeps the run `partial`. Routed to [SA-031](stories/SA-031.md): add
    probe Q2 as a test.
  - **I1:** the KT did not state `found_live`. Fixed in KT §3.
  - **I2:** a Windows-only `os.replace` flake in `_write_lineage`. Routed to SA-031.
- **Review edits (docs only):** the status wording in the KT (§1, §3, §11, §12) and guide 04-G;
  the `found_live` sentence in KT §3; the PDF rebuilt; the SA-031 card note. `verify
  SA-009-change1-manifest.json` now mismatches exactly the KT, the PDF and the guide.

**SA-009 change 1 was IMPLEMENTED on 2026-09-30** (this conversation, about 13:15–17:45 IST,
with a pause). It is uncommitted and not reviewed. A same-conversation self-review was done; it is
not the fresh review. The receipt is the "Change 1" section of
[SA-009-implementation.md](evidence/SA-009-implementation.md).

- **What it is, in one example.** A quarantined SUZLON file was changed, and a dashboard read
  recreated an empty `automobile/SUZLON`.
  - **Before:** rollback refused SUZLON. After the file was fixed, a retry skipped SUZLON yet
    reported `rolled_back` (review L1). The empty directory alone would also have blocked it
    (L2).
  - **Now:** every run retries each store not back, after removing an empty live directory with
    `rmdir`. It reports `rolled_back` only when every store is back with its recorded bytes.
  - A store moved back by hand counts only with its recorded bytes (`found_live`).
  - The inventory's summary gains `roster_collisions` (I3).
- **Checks:**
  - 10 new tests pin the review's probes R2, R3, R5 and R8–R10 (L3);
  - focused 45 passed;
  - mutations 11 of 11 caught, including the review's four survivors;
  - full suite **4026 passed, 12 skipped, 0 failed** (4016 + 10), `data/` unchanged;
  - `check_kt_docs` errors `[]`.
- **Also recorded here:** SA-008 and SA-009 now read "deployed 2026-09-30 (`650bb98c`)" in the
  KT, ARCHITECTURE, the guide and CODEBASE.

**SA-009 was ACCEPTED on 2026-09-30 by a fresh-session review** (a new conversation, about
12:25–12:55 IST). Receipt: [SA-009-review.md](evidence/SA-009-review.md). SA-009 is `done`, and
its `production_verification` is `pending_deployment`. No SA-039 check was due. Nothing was
committed, pushed, deployed, configured or sent, and no production state was read.

- **Input verified:** `72923d91…` (14 files, 0 mismatches, no unlisted change). The diff
  `c931b6c7…` was rebuilt with the reviewer's own script.
- **Traced:**
  - the owner rule against every scheduled writer (the scheduler, the self-heal, the pre-open
    check, the event ingest, the RL monitor) and the add route;
  - the readers: the orchestrator's weight read, the fallbacks, the evaluator walks, the backup
    and the universe walk;
  - the fixture's rosters equal the five real graphs'.
- **Checks:**
  - focused 35 passed;
  - full suite **4016 passed, 12 skipped, 0 failed** (12 min 08 s), `data/` unchanged;
  - reviewer probes: 12 passed, with the real wiring. R1 is SUZLON end to end: the plan moves only
    `automobile/SUZLON`, the scorecard and learning-evidence walks list SUZLON once, and a rollback
    is byte-identical;
  - reviewer mutations: 4 of 8 caught, including each of the three pre-SA-009 writers. The 4
    survivors are L3's untested rules, and each is covered by a probe;
  - `check_kt_docs` errors `[]` after the review edits (409 links, PDF 33 pages).
- **D1–D10 upheld.**
- **Findings.** None is critical, high or medium.
  - **L1 (low), in one example.** A quarantined file changes, so `rollback` refuses that store and
    reports `partial`. The operator restores the bytes and retries. The retry skips the store,
    which stays in quarantine, and reports `rolled_back` with exit 0.
  - **L2 (low).** Any read that constructs the quarantined store's `PredictionStore` recreates an
    empty live directory, and `rollback` then refuses. Removing it and retrying works.
  - **L3 (low, tests).** No test pins the holds for a sectorless or conflicting managed entry, the
    declared-sector conflict, or `apply` ignoring the plan file's items. The code is right; the
    reviewer's probes verified it.
  - **All three go to SA-009 change 1**, which is not required before the production apply. Until
    then the rollback caveat is in KT section 3.
  - **I1 → [SA-015](stories/SA-015.md).** The first restart of each month backfills yesterday for
    all 20 tickers, and the 16:30 job grades it again. The adapter runs twice, which is inert in
    `observe`.
  - **I2 → [SA-017](stories/SA-017.md).** The eval harness groups `per_sector` by the log's label.
  - **I3.** The rosters depend on the sector toggles; all four native sectors are enabled.
  - **I4 → rollout step 3.** Check `owner_store_present` on every item before approving.
- **Review edits (docs only):** status wording in the KT (§1, §3, §11, §12), ARCHITECTURE,
  guide 01-G and 04-G; the rollback caveat in KT §3; the PDF rebuilt. Routed notes were added on
  SA-015 and SA-017.

**SA-009 was IMPLEMENTED on 2026-09-30** (this conversation, about 06:46–11:58 IST, with a
pause). It is uncommitted and not reviewed. A same-conversation self-review was done; it is not
the fresh review. No production check was due, and no production state was read.

- **Sequencing.** SA-009 edits files SA-008 also changed, so the owner chose to commit SA-008
  first (step 3). The SA-009 baseline is the clean tree at `f443cc7`.
- **What it is, in one example.** SUZLON is managed as `renewable_energy`. The startup self-heal
  looked for every managed ticker's envelope in `automobile/<TICKER>`. So on each month's first
  deploy it ran the automobile graph into `automobile/SUZLON`: a second store with the automobile
  dimensions, which SUZLON's reviews never read but every evaluator that walks the tree does. The
  audit's 10 Sep capture found 15 such pairs, and all 58 feedback logs said `automobile` (the
  schema default).
- **What changed:**
  - **The owner rule.** A ticker's history belongs to `<managed sector>/<TICKER>`. A ticker
    without a managed entry has no owner, and nothing guesses one.
  - **The writers.** The self-heal uses each managed entry's sector. The store stamps its own
    sector on new logs, weights and ledgers, and leaves old files as they are. The daily review
    rebuilds a missing weight file, live or paper, from its sector's graph.
  - **The inventory.** `python -m core.intelligence.rl.stores.store_inventory` is read-only. Per
    store it gives identity, sector evidence and ownership. `confirmed` needs a dimension roster
    that matches the directory's graph; a directory name alone never confirms. It also lists
    duplicate tickers, envelope ids and graded days, identical or conflicting.
  - **The quarantine.** `python -m core.intelligence.rl.stores.store_migration plan|apply|rollback`.
    `plan` is read-only and ends with a digest. `apply` needs that digest, re-hashes each store
    just before moving it, and moves it by one rename into `data/prediction_quarantine/<id>/`.
    `rollback` restores the tree byte for byte and never merges.
- **Checks:**
  - 35 new tests (35 passed);
  - full suite on the final bytes: 4016 passed, 12 skipped, 0 failed (10 min 41 s; 3981 + the 35 new);
  - mutations: 15 of 15 caught (unmutated 35 passed before and after; sources restored byte-identical by blob id);
  - `check_kt_docs` errors `[]` (PDF 32 pages);
  - local runs: on a July snapshot the plan moves exactly the 13 `automobile/<TICKER>` copies; the
    dev tree was unchanged by the run.
- **Decisions D1–D10 for the reviewer** are in the receipt. The biggest:
  - D1: the owner is the managed sector;
  - D2 and D3: the dimension roster is the evidence, judged against the directory and against the
    owner separately;
  - D5: quarantine moves a store by rename, not copy and delete;
  - D8: the writer fixes are part of this story; without the self-heal fix the next month's
    first deploy would recreate the copies.
- **Routed:** the readers keyed by the graph sector, the `automobile` defaults and the directory
  creation on read go to [SA-026](stories/SA-026.md). Row lineage goes to
  [SA-017](stories/SA-017.md). A caveat for P3's F1 is in step 0.
- **Rollout, after review, commit and push:** first deploy, then the owner runs the inventory and
  plan read-only on the volume. The apply needs the owner's authorisation, by the plan's digest,
  in a job-free window after the nightly backup. Receipt: "Rollout".

**SA-008 was ACCEPTED on 2026-09-30 by a fresh-session review** (a new conversation, about
06:16–06:50 IST). Receipt: [SA-008-review.md](evidence/SA-008-review.md). SA-008 is `done`,
and its `production_verification` is `pending_deployment`. No SA-039 check was due. Nothing was
committed, pushed, deployed, configured or sent, and no production state was read.

- **Input verified:** `9a2edfb2…` (37 files, 0 mismatches, no unlisted change). The diff
  `bb7d0576…` was rebuilt with the reviewer's own script, and 37 of 37 blob ids match.
- **Traced:**
  - TATAMOTORS from the shipped registry through the analysis gate, the forecast stamp, the
    review's `identity` stage, the close fallbacks, the advisor and the autopilot;
  - the Dockerfile copies `config/` into `/app`, and no volume masks it, so production reads the
    real registry and not the fail-closed path;
  - the automobile `TICKERS` default only feeds the LLM lookup's short cut and the preopen
    check's list, so deploying schedules no TMPV run. The owner's add does that.
- **Checks:**
  - focused 500 passed;
  - full suite **3981 passed, 12 skipped, 0 failed** (5 min 14 s), `data/` unchanged;
  - reviewer mutations 4 of 4 caught;
  - reviewer probes 9: 7 passed, and 2 found M1 and L1;
  - `check_kt_docs` errors `[]` before and after the review edits.
- **D1–D9 upheld.**
- **Findings.** None is critical or high.
  - **M1 (medium) and L1 (low), in one example.** They are in the reconciliation tool's
    `apply`, and both go to **SA-008 change 1**.
    - **M1:** a user holds 100 PARENT, which demerged 60/40 into PARENTA and PARENTB, and the
      operator approves the plan. If 50 are sold in the moment between `apply`'s last check and
      its lock, the result is still 100 PARENTA + 100 PARENTB: shares and cost that were never
      held.
    - **L1:** if one user has two such holdings, the second backup overwrites the first, so no
      file holds the portfolio from before the apply. The audit log still has each old holding.
    - **Neither can happen today.** The shipped registry records no `successors`, so `apply`
      applies nothing. Until change 1 is accepted, record no `successors` and run no `apply` in
      production. KT §6 says so.
  - **L2 (low):** the review's close now asks the learned symbol cache first. Before SA-008 it
    used only the overrides dict. A ticker with a learned entry, such as SUZLON → SUZLON.BO, is
    now graded against the same symbol its forecast was priced from. That is right, but the
    receipt did not list it. The rollout adds a read-only look at the volume's cache.
  - **L3 (low, pre-existing):** the fundamentals fetcher never used the dict or the registry.
    TVSMOTORS' fundamentals ask `TVSMOTORS.NS`, while its prices come from `TVSMOTOR.NS`.
    Routed to [SA-045](stories/SA-045.md).
  - **I1 (info):** "different price bases are never compared" holds for grading and holdings. It
    does not hold for the technicals after a future demerger in which the parent keeps its code.
    Change 1's docs will state it.
- **Review edits (docs only):** status wording in the KT (§1, §4, §11, §12), ARCHITECTURE,
  TEAM_TESTING_GUIDE and CODEBASE; M1 and L1 in KT §6; the PDF rebuilt (30 pages, source
  `97953dc0…`).
- **SA-008 change 1** (M1, L1 and I1's wording) is in STATE as `change_1: todo`. It gets its own
  implementation conversation and its own fresh review. It is not urgent under the shipped
  registry, but it must come before any `successors` record.

**SA-008 was IMPLEMENTED on 2026-09-29** (this conversation, about 16:38–17:50 IST, after P2), and
was amended on 30 Sep, about 00:05–00:30, for the owner's decision below. It is uncommitted and not
reviewed. A same-conversation self-review was done; it is not the fresh
review.

- **What it is, in one example.** TATAMOTORS (weights v85) was priced from TMPV.NS through an
  undated `YF_SYMBOL_OVERRIDES` entry. TMPV is the passenger-vehicle company after the 2025
  demerger, while "Tata Motors Limited" now names the commercial-vehicle company. With healthy
  data its analysis was `actionable`.
  - Now `config/instruments.yaml` records each non-trivial ticker's provider symbol, price basis
    and identity status, with dates. Evidence resolves an identity; nothing is needed to
    quarantine one.
  - TATAMOTORS ships `unresolved`, still fetched from TMPV.NS. In `record` (the shipped mode)
    nothing changes, and its gate rows start "identity unresolved: retired by the owner's decision".
  - In `enforce` it reads INSUFFICIENT DATA, builds no envelope, stops its review at stage
    `identity`, and a holding of it is held (note `IDENTITY`).
- **Also:**
  - forecast rows, envelopes and advice keep the instrument they priced;
  - a row is graded only on its own price basis;
  - a holding whose basis changed since purchase (a demerger) is held, exits included, until an
    operator runs `python -m core.portfolio.identity_reconcile plan`, reviews it, and applies it
    with the plan's digest;
  - the close fallbacks and the NSE check price the resolved instrument.
- **Checks:**
  - 70 new tests;
  - 22 of 22 runtime mutations caught;
  - full suite **3981 passed, 12 skipped, 0 failed** (3911 + the 70 new, final bytes), `data/`
    unchanged;
  - `check_kt_docs` errors `[]` (PDF 30 pages).
- **Decisions D1–D9 for the reviewer** are in the receipt. The biggest:
  - D1: it uses SA-003's switch, not a new one;
  - D3: the identity hold also holds EXIT and TRIM, a deliberate departure from SA-003's
    "never blocked", because a demerged parent's price reads as a false 40% loss.
- **Owner decision (29 Sep, delegated: "take whichever is recommended"): option (b).** The
  passenger-vehicle company is tracked as its own ticker, TMPV; TATAMOTORS is retired and stays
  quarantined, with its history kept. TMCV is not added.
  - **The amendment it needed:** TMPV joins the automobile exact-match list, because the LLM
    lookup's prompt lists TATAMOTORS and could rename TMPV back to it; TMPV is added to the
    sector map; the registry's TATAMOTORS reason records the decision.
  - **The owner's step at rollout,** after review, commit and deploy: add TMPV (automobile,
    name "Tata Motors Passenger Vehicles Ltd"), then **disable** TATAMOTORS with the toggle.
    **Never remove it:** removing deletes `data/predictions/automobile/TATAMOTORS` (its v85
    weights, envelopes and feedback). Receipt "Rollout", step 4.
- **Routed:** P2's ticker-resolution traceback goes to [SA-026](stories/SA-026.md).

Six Sprint-1 stories (SA-033, SA-035, SA-036, SA-038, SA-040, SA-042) come later in the STATE
file; taking one before SA-009 needs the owner's word.

**SA-007 change 1 was ACCEPTED on 2026-09-29 by a fresh-session review** (a new conversation,
about 12:33–12:55 IST). Receipt: [SA-007-review.md](evidence/SA-007-review.md), section "Change
1 fresh-session review". SA-007 is `done` again. No SA-039 check was due. Nothing was committed,
pushed, deployed, configured or sent.

- **What it is, in one example.** The owner deferred the off-site bucket to the last task of the
  PI and chose option B (about 12:00 IST).
  - The watchdog reminds "No off-site copy has ever been confirmed" once a week, not every
    morning: Wednesday 06:30, then silence until the next Wednesday.
  - A failed drill, a stopped job, a flagged ledger or a half-done setup still warns daily.
- **Input verified:** `4cda0408…` (8 files, 0 mismatches, no unlisted change). The diff
  `18525515…` was rebuilt with the reviewer's own script, and 8 of 8 blob ids match.
- **Traced:**
  - the engine's daily path is exactly the expression it replaced;
  - `repeat_days` reaches the engine through `run_check` and the runner;
  - the real job writes `target: None` only when `BACKUP_OFFSITE_TARGET` is unset.
- **Reviewer probes, 7 of 7**, through the real nightly job and the real runner:
  - weekly notices on 30 Sep, 7 Oct and 14 Oct;
  - the rollout claim (the deployed code warns Wed 30 Sep; change 1 then keeps Thu–Tue silent);
  - a half-done setup, a flagged ledger and a rollback stay daily;
  - a failed delivery is retried the next day.
- **Decisions C1–C4 upheld.** C4's cost: after any daily notice, a return to the deferred state
  is silent for up to six days. The Sunday heartbeat still lists the state weekly.
- **Findings, both fixed by docs-only review edits:**
  - **L1 (low):** guide 12-G said a drill failed by hand on a test copy would reach the watchdog.
    `restore drill` never writes `backup_status.json`.
  - **I1 (info):** SA-007's "not yet deployed" wording was stale since `26b442f4`.
- **Checks:** focused 202 passed; reviewer mutations 5 of 5 caught; full suite **3911 passed, 12 skipped, 0 failed** (6 min 06 s), `data/` unchanged;
  broad-except OK; `check_kt_docs` errors `[]` (PDF 28 pages, source `70a321ef…`).
- **Review edits (docs only):** KT §1, §10, §11 and §12; the PDF; guide 12-B, 12-G and 12-H;
  ARCHITECTURE; LEGAL. `verify SA-007-change1-manifest.json` now mismatches exactly the KT, the
  PDF and the guide.
- **Production verification** stays `pending_observation`: tonight's 23:30 backup, then the
  Wed 06:30 watchdog. After change 1 deploys, its own check is a silent watchdog on the morning
  after the first weekly notice.

**SA-007 was ACCEPTED on 2026-09-29 by a fresh-session review** (a new conversation, about
07:05–07:35 IST). Receipt: [SA-007-review.md](evidence/SA-007-review.md). SA-007 is `done`. No
SA-039 check was due. Nothing was committed, pushed, deployed, configured or sent.

- **Input verified:** `7c1d43d9…` (18 files, 0 mismatches, no unlisted change). The diff
  `2e0a5656…` was rebuilt with the reviewer's own script.
- **The original defect, reproduced against the baseline module.** A WAL `chat_sessions.db` with
  5 committed rows still in its `-wal`: the old zip restores to "no such table", and the new one
  holds 5 rows. A writer committing during the build still gives a clean drill.
- **Two low findings, both reproduced and routed. Neither blocks acceptance.**
  - **F1 → [SA-034](stories/SA-034.md), in one example.** Sunday's backup is confirmed. On Monday
    the container restarts at 23:30, so the job never runs and no error fires. At 06:30 on
    Tuesday the status is 31 h old, under the check's 36 h limit, so the watchdog says
    `satisfied`. If Tuesday's run works, the missed night is never reported. Fix: SA-034's
    job-ran invariant, or a limit of about 30 h.
  - **F2 → [SA-036](stories/SA-036.md), in one example.** `atlas.db` is malformed and
    `transactions.jsonl` is healthy. Before SA-007 the zip held both. Now the job raises
    `DatabaseError`, and no archive, off-site copy or status is written until the database is
    repaired. The job-error alert fires each night, and earlier copies are kept. Fix: archive the
    rest and record a `partial` outcome.
  - **I1 (info) → the SA-036 card:** the local rotation ignores the drill. **I2 (info, predates
    SA-007):** SA-004 and SA-006 still read "not yet deployed" in the KT, ARCHITECTURE and the
    guide. For the next KT bump or SA-031.
- **Decisions:** D1–D10 upheld, except D6 in part (F1). D4's cost is now in the KT: a ledger
  rewrite is reported on one morning, then the history survives only in the older off-site
  copies, for 30 nights by default.
- **Checks:**
  - focused 136 passed;
  - reviewer probes: 7 passed, and 2 failed as the findings;
  - reviewer mutations 9 of 9 caught;
  - full suite alone **3902 passed, 12 skipped, 0 failed** (5 min 03 s), `data/` unchanged. An
    earlier run beside the mutations hit a Windows rename flake in `core/ipo/history.py`, which
    passes 5 of 5 alone; it is routed to SA-031 with the `signals.py` one;
  - broad-except OK; `check_kt_docs` errors `[]`.
  - The probes and the mutation plugin are in `analysis_data/sa007/review/` (ignored).
- **Review edits (docs only):** SA-007 status wording in the KT (§1, §10, §11, §12),
  ARCHITECTURE, guide 12-B/G/H and LEGAL. KT §10 now states F1 and F2. The PDF is rebuilt (28
  pages, source `9efaf9da…`). Routed notes are on the SA-034 and SA-036 cards. `verify
  SA-007-manifest.json` now mismatches exactly the KT, the PDF, ARCHITECTURE, the guide and LEGAL.
- **Production verification: `pending_deployment`.** It needs:
  - the owner's commit, push and deploy. A deploy alone makes the watchdog warn every morning
    until a bucket exists;
  - the bucket, key and `BACKUP_*` variables (deferred owner setup);
  - a recorded `restore fetch` from outside Railway.
  The plaintext backup email (D7) is still the owner's decision.
- **Committed at the owner's word** ("ya go ahead commit and push", about 07:37 IST Tue 29 Sep).
  - **`165d152`:** SA-007 and its review bookkeeping. `verify SA-007-manifest.json --rev 165d152`
    mismatches only the 5 review-edited docs, so every reviewed code and test byte is committed as
    reviewed.
  - **The next commit is the KT bump.** It declares `165d152` and links `offsite.py` and
    `restore.py`. The SA-007 status lines now say "committed as `165d152`". It also records
    `implementation_commit` and rebuilds the PDF (28 pages, `check_kt_docs` errors `[]`).
- **Pushed and deployed.** The 07:37 word waited out the morning-job window.
  - **The push:** `acf72d2..cd33fc4` at 12:12:57 IST, carrying `cdec78f`, `165d152` and
    `cd33fc4`.
  - **The deploy:** Railway `26b442f4` reached SUCCESS by 12:19:54 IST.
    - Boot log: 124 lines, 0 tracebacks and 0 error or warning lines; the scheduler started
      with 24 jobs.
    - `/health` returns 200 `ok`.
  - **Packages:** the pip layer reinstalled. Against the 27 Sep full build `0106fc89`, 6
    transitive packages changed:
    - `oauthlib` 3.3.1 → 4.0.0, a major version. It comes through chromadb → kubernetes →
      requests-oauthlib, and no app code imports it. For SA-033's pinning;
    - `coverage`, `filelock`, `peewee`, `platformdirs` and `regex`, minor or patch versions.
    - `cryptography` 50.0.1 and every core package are unchanged.
    - The raw build logs are in the ignored `analysis_data/sa007/deploy/`.
  - **CI:** run `36532524605` passed 3 of 3 jobs. Python tests on Linux / 3.11 took 2 min 50 s,
    so SA-007's tests pass there.
  - **SA-007 `production_verification`: `pending_observation`.**
    - Tonight's 23:30 backup is the first with a manifest and a drill. Its continuity will read
      "not checked" against the old-format archive, and `backup_status.json` will say "not
      configured".
    - At 06:30 on Wed 30 Sep the watchdog should say "No off-site copy has ever been confirmed".
      That is expected. It repeats daily until change 1 lands, then weekly.
    - Off-site recovery stays unverified until the bucket. The owner deferred it to the last task
      of the PI.
  - STATE and HANDOFF record this uncommitted. It rides with change 1's commit.

**SA-007 was implemented on 2026-09-29** (about 03:20–04:10 IST). Receipt:
[SA-007-implementation.md](evidence/SA-007-implementation.md). Review input
**`7c1d43d9…`** (18 files); full diff `2e0a5656…` against `cdec78f`. Nothing was committed,
pushed, deployed, configured or sent. No bucket exists.

- **In one example.** Tonight's archive gets a `MANIFEST.json`, for example `users.db`:
  integrity ok, `users: 2`, `transactions.jsonl`: 1,200 bytes and 3 rows. The job restores it into
  a temporary directory and checks all of it. It also checks that the ledger still begins with
  last night's 1,100 bytes. Only then does it encrypt the archive (AES-256-GCM) and send it
  off-site, ciphertext first and manifest last, each read back at its size. With no bucket
  configured, the watchdog says every morning: "No off-site copy has ever been confirmed".
- **A real defect was fixed.** `users.db`, `atlas.db` and `chat_sessions.db` run in WAL mode and
  were zipped as raw files with their `-wal`/`-shm` files. Rows still in the WAL were lost:
  restored alone, a raw copy of a fresh WAL database has no tables at all. Now every SQLite file
  goes through the backup API.
- **For the reviewer:**
  - D1–D10 are in the receipt. The contested ones are D3 (only a drill-passing archive leaves),
    D4 (continuity breaks are warnings, not errors), D5 (what "confirmed" means) and D7 (the
    email copy is unchanged).
  - The S3 signer is from the standard library, checked against AWS's three published examples.
  - A deploy alone makes the watchdog warn daily until the owner configures a bucket.
- **Checks:**
  - 65 new tests (27 recovery, 28 off-site, 10 watchdog);
  - full suite **3902 passed, 12 skipped, 0 failed** (9 min 32 s), `data/` unchanged;
  - 15 of 15 mutations caught;
  - the broad-except guard OK, and `check_kt_docs` errors `[]` (PDF 28 pages);
  - a local rehearsal on a copy of the dev data: 63 files, 5 databases and 77,540 rows drilled
    clean, then recovered from the off-site copy alone.
- **Docs:** KT §3, §9, §10 ("Backups and recovery": steps, runbook, owner configuration, limits)
  and §11; guide 12-B, new 12-G and 12-H; ARCHITECTURE, PRODUCT_MAP, CODEBASE and LEGAL. New files
  are not linked from the KT until the KT bump after a commit.
- **Production verification: `pending_deployment`.** It needs:
  - acceptance, then the owner's commit, push and deploy;
  - the owner's bucket, key and `BACKUP_*` variables, set in a job-free window (each set
    redeploys). This joins the deferred owner setup list;
  - a recorded `python -m services.data.restore fetch --dest <empty dir>` from outside Railway.

  Also for the owner to decide: retire or encrypt the plaintext backup email.
- **After acceptance:** select the next ready story, but do not start it in the review chat. By
  STATE file order that is **SA-008**. Six Sprint-1 stories (SA-033, SA-035, SA-036, SA-038,
  SA-040, SA-042) come later in the file.

**SA-006 was ACCEPTED by its fresh re-review on 2026-09-28** (this conversation, about
19:40–20:45 IST, after P1). Receipt: [SA-006-review.md](evidence/SA-006-review.md), section
"Re-review". Nothing was committed, pushed, deployed or sent.

- **F1 is fixed, in one example.** A phone's push service stores the morning brief's push, then
  drops the connection. The brief now shows once; the row dead-letters with the reason. A
  refused connection is still retried and shows once.
  - The rule matches urllib3's own "safe to retry" test (`Retry._is_connection_error`).
  - Real-stack tests prove both cases.
- **F2 is fixed:** the owner report carries no user id.
- **D10, D11 and D12 are upheld:**
  - D10: a TLS error is an unknown outcome;
  - D11: one phone's unknown outcome stops the row;
  - D12: no `sw.js` tag for now. It is revisited if guide case 10-C shows a double.
- **Checks:**
  - the input `b8273b2c…` verified, and the diffs `e01c4913…` and `713e1675…` rebuilt;
  - focused tests 124 passed;
  - full suite **3837 passed, 12 skipped, 0 failed** (7 min 12 s), `data/` unchanged;
  - the reviewer's 8 of 8 mutations caught, and 7 of 7 probes as the contract requires;
  - `check_kt_docs` errors `[]`.
  - No findings.
- **Review edits (docs only):** the SA-006 status wording in the KT (§1, §10, §11, §12), ARCHITECTURE
  and guide 10-B/C/E/F; the PDF is rebuilt (26 pages, source `38ddf518…`). So `verify
  SA-006-manifest.json` now mismatches exactly those 4 files.
- **Production verification: `pending_deployment`.**
  - It needs the owner's commit and push.
  - After the deploy, read `GET /delivery/outbox` (machine key) or run the owner probe
    `analysis_data/sa006/prod_probe_outbox.py`.
  - Then human cases 10-B, 10-C, 10-E and 10-F.
  - A real test email or push needs explicit messaging authorization.
- **Committed as `15dcda1`** at the owner's word ("commit and push with revan.datta132@gmail.com",
  about 22:18 IST Mon 28 Sep). The author is `Revan <revan.datta132@gmail.com>`, the same as
  earlier commits.
  - `verify SA-006-manifest.json --rev 15dcda1` mismatches only the 4 review-edited docs, so every
    reviewed code and test byte is committed as reviewed.
  - A follow-up commit bumps the KT to `15dcda1` (§1, §10, §11 and §12 now say "committed"; PDF
    26 pages, `check_kt_docs` errors `[]`) and records the commit in STATE.

**The push hold is lifted** (owner, about 22:18 IST Mon 28 Sep: "commit and push"). The push
carries 5 commits: `7901f35`, `48143ed` (SA-005), `9e65c7a`, `15dcda1` (SA-006) and the KT bump.
It is timed so the deploy lands before the 22:55–00:05 blocked window (23:00 atlas jobs, 23:30
backup). **After the push:**

- check the deploy with `railway deployment list`;
- read the Actions page and record CI's three jobs against SA-005 (human case 12-E);
- do SA-006's first read-only production read (`GET /delivery/outbox` or the owner probe).

**Pushed and deployed.**

- **The push:** `90353f3..acf72d2` at 22:20:54 IST.
- **The deploy:** Railway `00b94de9`, created 22:21:00, SUCCESS by 22:27:46 IST, before the
  22:55 window. The 23:00–23:45 nightly jobs run on the new code; `atlas_retention` at 23:20 is
  the first to keep dead letters for 180 days.
- **After the deploy (read-only):**
  - startup completed, with 0 tracebacks in its first 126 log lines;
  - `/health` returns ok;
  - the RL monitor is still `learning_mode=observe`;
  - `GET /delivery/outbox` without credentials returns 401 (owner-only, as designed).
- **CI's first run passed** (run `36453992259` on `acf72d2`, read via the public GitHub API):
  - Python tests (Linux, 3.11): success, 2 min 30 s;
  - the broad-except and KT guards: success;
  - the Chromium browser suite: success.
  - That is SA-005's human case 12-E, measured. What remains for SA-005 is the witnessed drill
    12-F.
- **SA-005 and SA-006 `production_verification`:** now `pending_observation`.
- **Still to do for SA-006:**
  - the first authenticated outbox read: the owner runs `analysis_data/sa006/prod_probe_outbox.py`
    in the container, or uses a machine-key GET;
  - then one observed retry or dead letter (case 10-C), and cases 10-B, 10-E and 10-F.
- **Local `main` is 1 ahead** after the next commit (this record). It is not pushed, because every
  push redeploys; it goes out with the next push.

**SA-006 rework 1 was done on 2026-09-28** (a new conversation, about 15:38–16:25 IST, baseline
`9e65c7a`). Receipt: [SA-006-implementation.md](evidence/SA-006-implementation.md), section
"Rework 1". No SA-039 check was due. Nothing was committed, pushed, deployed or sent.

- **F1 fixed, in one example.** A push service stores a brief's push, then the connection
  drops before its 201.
  - Before: the drainer retried it, so the phone showed it twice.
  - Now: it is an unknown outcome and dead-letters after one attempt, so the phone shows it once
    and the owner report says why.
  - A push is retried only when its connection was never made: refused, a DNS failure or a
    connect timeout. The check uses exception types, found along `args`, `reason` and
    `__cause__`, never message text.
- **F2 fixed.** The dead letter for an account with no address now reads "permanent: no email on
  file for this account", with no user id.
- **Two new decisions for the re-reviewer:**
  - **D10:** TLS errors count as unknown outcomes, because their type cannot prove that nothing
    was sent.
  - **D11:** one phone's unknown outcome stops the row for all of that account's phones. A phone
    whose service answered 5xx then loses that notification, visibly, as a dead letter.
- **D12, decided by Claude on the owner's delegation:** no notification `tag` in the service
  worker for now.
  - Our own retries can no longer duplicate a push.
  - A tag only merges a copy that is still on screen, so it makes no retry safe.
  - It would change code on every phone, and no automated test covers that code.
  - Revisit if a phone ever shows one notification twice (guide case 10-C).
- **Tests:**
  - 12 new tests. One is the review's R1, kept as a permanent test: the real pywebpush →
    requests → urllib3 stack against a loopback push service. The service stores 1 copy and the
    row dead-letters after 1 attempt; the reviewed code fails this test. Another uses a real
    refused connection, which is retried and ends with 1 copy stored.
  - A 9-case table of exception types, and I5 extended with an account that has no address.
  - Focused: 124 passed. Full suite: **3837 passed, 12 skipped, 0 failed** (11 min 02 s).
    `data/`, `logs/` and `outputs/` were unchanged.
  - 5 of 5 rework mutations were caught, the broad-except guard is OK, and `check_kt_docs`
    errors are `[]` (PDF 26 pages).
- **Docs:** KT §10 (the transient, at-most-once and visibility bullets); the status lines in the
  KT, ARCHITECTURE and the guide, which now say "re-review pending"; and guide case 10-C.

**SA-006's fresh review requested changes on 2026-09-28** (a new conversation, about
15:08–15:35 IST). Receipt: [SA-006-review.md](evidence/SA-006-review.md). The review input
`516d2aec…` was verified (18 files, 0 mismatches) and the diff `79ec6b54…` rebuilt
independently. No SA-039 check was due. The review edited no code or docs, and nothing was
committed, pushed, deployed or sent.

- **F1 (medium; an acceptance criterion is not met), in one example.** A push service receives
  a brief's push, then the connection drops before it answers. The drainer calls that
  transient and sends it again a minute later, so the phone shows the brief twice. This was
  reproduced with the real pywebpush and requests stack against a loopback push service, which
  stored 2 copies. Today only a `ReadTimeout` counts as an unknown outcome.
  - **The fix:** retry a push only when the exception shows the connection was never made
    (`ConnectTimeout`, `NewConnectionError`, `NameResolutionError`). Treat anything else as an
    unknown outcome, which dead-letters.
- **F2 (low).** The dead letter for an account with no address reads "no email on file for
  user 'u_…'". So the owner report shows a user id, although its contract says it shows none.
  The fix is to drop the id.
- **Everything else holds.**
  - 112 focused tests passed.
  - Full suite: 3825 passed, 12 skipped, 0 failed (11 min 26 s), data/logs/outputs unchanged.
  - 10 of 10 reviewer mutations were caught, including the `590bc9f` owner fallback.
  - The broad-except guard is OK, and `check_kt_docs` errors are `[]`.

**SA-006 was implemented on 2026-09-28** (one conversation, about 13:15–15:05 IST, baseline
`9e65c7a`). Receipt: [SA-006-implementation.md](evidence/SA-006-implementation.md). No SA-039
check was due. Nothing was committed, pushed, deployed or sent.

- **What it does, in one example.** A beta account's brief meets a locked `users.db`: before, it
  went to the owner's `DELIVERY_EMAIL_TO`; now it waits a minute and goes to the account's own
  address, once. The owner's brief meets a rejected Gmail password: before, 3 tries and a raw
  error; now one try and a dead letter saying "check SMTP_USER and SMTP_PASSWORD".
- **The contract:** every transport returns a `SendResult`, meaning acceptance, never receipt.
  Transient failures retry on the backoff or the provider's `Retry-After` (capped at 6 h).
  Permanent ones dead-letter at once with a hint. Unknown outcomes (a drop inside the SMTP send,
  a push read timeout, a process killed mid-send) dead-letter and are never re-sent. Resend gets
  a per-row `Idempotency-Key`. Reasons and logs are redacted. `GET /delivery/outbox` (owner)
  shows counts, dead letters and retrying rows, with `delivered` shown as `accepted`. Dead
  letters are kept 180 days (payload cleared at 30). Pushes carry a 12 h TTL (pywebpush's default
  0 lets a push service drop them).
- **Production, read-only:** the live deploy `b3fb00dd` logged 3 outbox enqueues, 0 dead letters
  and 0 send failures from 27 Sep 16:05 to 28 Sep 12:01. The 23 Sep probe had 8 email rows
  accepted and 0 dead since the Pro redeploy. SMTP works; SA-006 does not change transport
  selection. A read-only outbox probe for the owner is `analysis_data/sa006/prod_probe_outbox.py`
  (not yet run in production).
- **Tests:** full suite 3825 passed, 12 skipped, 0 failed (SA-005's 3800 plus 25 new), with
  `data/`, `logs/` and `outputs/` unchanged; 22 new invariant tests at the network boundary
  (fake relay, Resend and push service count what they accepted); 16 of 16 mutations caught,
  including the `590bc9f` owner fallback; broad-except guard OK; `check_kt_docs` errors `[]`;
  PDF rebuilt (26 pages).
- **Found and routed to SA-031:** `scripts/docs/run_kt_checks.py` has not run since SA-005 (it
  does not copy the tracked seed `data/nse/key_registry.json`, exits 4 and then prints a stale
  24 Sep XML); a Windows rename flake in `core/ipo/signals.py`.
- **Nine decisions for the reviewer,** in the receipt (D1 at most once; D3 stored status stays
  `delivered`, reported as `accepted`; D5 dead-letter retention; D6 push TTL; D8 direct senders
  stay direct).
- **Open:** receipt is not observed (no webhooks); direct senders (monthly report, heartbeat,
  backup) have no retry; no dead-letter alert (SA-011); CI never ran.

- **Earlier plan note:** SA-006 was the first planned `todo` story in STATE's order whose
  dependencies are done. SA-005's acceptance also unblocked [SA-012](stories/SA-012.md).

**SA-005 was ACCEPTED on 2026-09-28 by a fresh-session review** (a new conversation, about
07:25–07:55 IST). Receipt: [SA-005-review.md](evidence/SA-005-review.md). SA-005 is `done`. Its
`production_verification` stays `pending_deployment`: CI has never run on GitHub. No SA-039 check
was due. The review committed, pushed and deployed nothing.

- **Input verified:** `ef0e3a31…` (51 files, 0 mismatches). The completeness check found no
  unlisted change, and the diff `7274a199…` was rebuilt with the reviewer's own script. The three
  action pins are the upstream tags' commits (`git ls-remote`).
- **Tests:**
  - owner's checkout (`.env` present): 3800 passed, 12 skipped, 0 failed. `data/`, `logs/` and
    `outputs/` were unchanged (800 files);
  - reviewer's fresh copy (`git archive 7901f35` plus the manifest, run from the long temp path):
    3799 passed, 13 skipped, 0 failed. `git status` was empty afterwards, and `logs/` and
    `outputs/` were never created;
  - reviewer's 6 mutations: all caught. They include the original F22 defect (the old MARUTI
    test fails without local data) and the F5 defect (the old outbox tests fail without
    `DELIVERY_EMAIL_TO`);
  - probes: yfinance's real call path is refused and fails the test (P1); the owner's real `.env`
    does not reach settings (P6);
  - no Python 3.12-only syntax in 730 files (a tokenizer scan, since `ast` feature_version misses
    PEP 701).
- **Findings.** None critical, high or medium.
  - **L1 (low), in one example.** A test that read
    `C:\Users\REVANP~1\…\data\nse\key_registry.json` (the 8.3 spelling of the checkout) got the
    file instead of a refusal. The same holds for `listdir`/`exists`, pyarrow reads, SQLite
    `file:` URIs and a numeric-IP connection on Windows' asyncio loop. The application reaches
    none of these today. The KT and `tests/TEST_DOCUMENTATION.md` now say so; the docstring and
    optional hardening go to [SA-031](stories/SA-031.md).
  - **L2 (low):** fixing one grandfathered broad `except` and adding a new silent one in the same
    function passes the guard. Routed to SA-031, and the KT states it.
  - I1 and I2 are info only.
- **Review edits (documentation only):** KT §13 (two passages) and the SA-005 status wording
  (§1, §10, §12, the §13 heading), the PDF rebuilt (source `f407a930…`), `tests/TEST_DOCUMENTATION.md` rule 4, and the SA-031 card. `verify
  SA-005-manifest.json` now mismatches exactly these four files. The code, test, CI and tooling
  bytes are as reviewed.
- **Committed at the owner's word** ("commit and push now", about 07:58 IST Mon 28 Sep).
  - **`48143ed`:** SA-005 and its review bookkeeping. `verify SA-005-manifest.json --rev 48143ed`
    mismatches only the four review-edited docs, so every reviewed code, test and CI byte is
    committed as reviewed.
  - **The next commit is the KT bump:** it declares `48143ed`, links the five new or changed
    files, changes the status lines to "committed as `48143ed`", records `implementation_commit`
    and rebuilds the PDF (source `abec1a58…`; `check_kt_docs` errors `[]`).
  - **The push was held for the window.** The word came at 07:58, inside the 07:25–09:05
    morning-job window (`ipo_refresh_am` 08:00, `preopen_shock_check` 08:45, `morning_brief`
    08:50, `macro_market_news` 09:00). A push then would have restarted the container about
    08:06, during the IPO refresh. (Superseded: the owner put the push on hold at 08:46 IST; see step 1.) It
    carries `7901f35`, `48143ed` and the KT bump, and it is CI's first run: afterwards, read
    the Actions page and record the three jobs against SA-005 (human case 12-E).

**Earlier: the SA-005 implementation (27–28 Sep).**

- **SA-005 was implemented** in one conversation (27 Sep about 16:25–17:30 IST and 28 Sep about
  06:45–07:45 IST, baseline `7901f35`). Receipt:
  [SA-005-implementation.md](evidence/SA-005-implementation.md). No SA-039 check was due. Nothing
  was committed, pushed or deployed.
  - **What it does, in one example.** Before, the owner's test run loaded `.env`, and yfinance's
    requests went out unseen by the old socket guard. The first run under the new boundary refused
    286 Yahoo requests, 178 OpenRouter attempts and 124 NSE session attempts. The old suite also
    changed 15 files in the local `data/`, including the MARUTI toggle (I3). Now every test runs in
    an empty working directory, with no `.env` and no network, and the final run left `data/`
    byte-identical.
  - **The boundary:** `tests/hermetic.py`, imported first by `tests/conftest.py`. A test that
    reaches the network or the checkout's `data/`, `logs/` or `outputs/` fails, naming the target
    and the application line, even when the application swallowed the error.
  - **CI:** `.github/workflows/ci.yml` (the whole tree on Linux / Python 3.11, the broad-except
    ratchet and `check_kt_docs`, the browser suite; `contents: read`, no secrets),
    `requirements-test.txt`, `scripts/ci/check_broad_except.py` (154 handlers grandfathered, not
    reviewed one by one).
  - **Nine decisions for the reviewer,** in the receipt. For example: D1 one working-directory
    sandbox instead of ~40 path redirects; D3 an obsolete TypeScript-client contract test removed;
    D4 a Windows-only rename retry in three production writers; D6 the guard is a whole-tree
    ratchet.
  - **Tests:** owner's checkout 3800 passed, 12 skipped, 0 failed; a fresh git checkout outside
    OneDrive 3799 passed, 13 skipped, 0 failed; the reverse-order run found one leak, now fixed;
    12 of 12 mutations caught; `check_kt_docs` 0 errors; PDF rebuilt.
  - **Open:** CI has never run (it needs a push, and every push redeploys); no pinned-date run
    (routed to SA-012); child processes are outside the boundary; cached store connections are
    shared between tests.
  - **Routed:** [SA-012](stories/SA-012.md), [SA-018](stories/SA-018.md),
    [SA-029](stories/SA-029.md), [SA-031](stories/SA-031.md).
  - **Local data restored.** The old suite's measurement run changed 15 files in `data/`; they
    were restored from the ignored `analysis_data/sa005/data_before` copy and are identical to it.
  - **Running tests here:** plain `python -m pytest tests`. `-p nonet` and
    `RL_LEARNING_MODE=adapt` are no longer needed in this checkout; a checkout without SA-005
    still needs them.

**Earlier: SA-004 accepted, committed and deployed (27 Sep).**

- **SA-004 was ACCEPTED on 2026-09-27 by a fresh-session review** (a new conversation, about
  15:23–15:50 IST). Receipt: [SA-004-review.md](evidence/SA-004-review.md). SA-004 is `done`. Its
  `production_verification` is `pending_observation`: it was deployed at 16:06 (see below). No SA-039 check was due. The review itself
  committed, pushed and deployed nothing; the commit and push followed at the owner's word (below).
  - **Input verified:** `a5e77a74…` (13 files, 0 mismatches), and the diff `648b7b68…`, rebuilt
    with the reviewer's own script.
    - Payload update 1 (`5d9030e0…`, diff `e16a8e3f…`) arrived during the review, from the
      concurrent planning session (the backlog bullet below).
    - The reviewer rebuilt it too. The code, tests and `CODEBASE.md` are byte-identical, and the
      four doc changes are planning content only. The acceptance covers both inputs.
  - **Traced:**
    - `completed` implies a stored feedback entry, because a failed write raises;
    - the ticker and date pass through unchanged, so `classify` cannot misread a real review;
    - `/scheduler/status` is the only reader of the record;
    - the HTTP task and the paper lane already counted only `completed`;
    - no watchdog check reads review outcomes.
  - **Hard review.** The five counts always add up to `required`. Within the counting, the zero-
    and partial-output alerts fire for every `produced < required`.
  - **F1 (low, reproduced), in one example.** Suppose Friday's record for 1 Oct had a wrong type
    in it, for example `"attempts": [1]`. On Mon 5 Oct, `summarize` raises before the portfolio
    pipeline:
    - the crash pages;
    - that day's advisor → autopilot → digest does not run.

    The only writer writes integers, so this needs a hand edit. Routed to
    [SA-036](stories/SA-036.md): wrap the block and fall back to no merge. I1 and I2 (info) are
    routed there too.
  - **I3 (info, predates SA-004).** `test_api_auth_lockdown.py:82` flips MARUTI's `enabled` flag
    in the checkout's real `data/managed_tickers.json` on every full run. It now holds MARUTI
    enabled, TCS and HDFCBANK disabled. This is local only. Routed to [SA-005](stories/SA-005.md).
  - **The implementer's five decisions:** the review agreed with each.
  - **Tests** (network guard on, `RL_LEARNING_MODE=adapt`):
    - focused: 376 passed;
    - the reviewer's 5 runtime mutations: all caught. The baseline scheduler, which is F09
      itself, fails 30 of 61;
    - pinned Mon 28 Sep and Fri 2 Oct: 71 passed each;
    - the reviewer's probes: 8 passed;
    - full `tests/unit`: 3502 passed, 5 skipped, 1 failed, the known `test_delivery_api` rename
      flake (5 of 5 alone); the guard blocked the pre-existing 194;
    - `check_kt_docs`: 0 errors.
  - **Review edits (documentation only):**
    - status wording in the KT (§1, §5, §9, §11, §12), ARCHITECTURE, 01-A and 01-F, `CODEBASE.md`
      and the SA-034 note;
    - the PDF rebuilt (source `bf3d73d3…`).

    `verify SA-004-manifest.json` now mismatches exactly the KT, the PDF, ARCHITECTURE,
    TEAM_TESTING_GUIDE and `CODEBASE.md`.
  - **Committed at the owner's word** ("commit and push", about 15:55 IST on Sun 27 Sep).
    - **`241c393`:** SA-004 and this review's bookkeeping. It also carries the planning session's
      SA-048…SA-051 cards and PI README, because the docs interleave the two.
    - `verify SA-004-manifest.json --rev 241c393` mismatches only the five status-edited docs, so
      every reviewed code, test and config byte is committed as reviewed.
    - **The next commit is the KT bump.** It declares `241c393`, links `review_outcomes.py`,
      changes the status lines to "committed as `241c393`", records `implementation_commit` in
      STATE and rebuilds the PDF.
  - **Pushed and deployed.** `a61fafe..90353f3` was pushed at 16:00:04 IST, and it also carried
    `0a5bf9e`. On a Sunday nothing runs between 09:05 and the daily `ipo_refresh_pm` at 17:45.
    - Deploy `b3fb00dd` reached SUCCESS at about 16:06 IST. The build was cached, about 6 minutes
      from the push.
    - The boot log (read-only, filtered) shows the scheduler started with 24 jobs registered and
      startup complete at 16:05:52, with 0 error or warning lines. No job fell in the switch.
    - SA-004's `production_verification` is now `pending_observation`.
    - This record is committed locally and rides the next push.
  - **Verify read-only across one scheduled session,** as the receipt's "Rollout" says. The first
    is Mon 28 Sep 16:30, alongside SA-039-P1 and the SA-003 cohort check. In
    `/scheduler/status` → `last_runs.daily_review`:
    - `by_ticker` holds every enabled ticker once;
    - the five counts add up to `required`;
    - `produced` equals the tickers whose `feedback_log.last_date` is 2026-09-25.

    Expect most outcomes to read `degraded` until the 1 Oct envelopes, because the rows were issued
    before the data gate. A skip (for example `no_envelope`) now sends a partial-output alert,
    which is intended. SA-004 is live before Fri 2 Oct, so Mon 5 Oct's record should read
    `runs: 2` for 1 Oct.
- **Backlog added at the owner's request (2026-09-27, after SA-004).** The owner reviewed the live
  portfolio screen: ₹9,99,611 equity, 81% cash, 2 holdings, a flat total return with nothing to
  compare it with. Four stories were added; the task order is unchanged, and they follow SA-047:
  - [SA-048](stories/SA-048.md) (S3, 3 points): costs and tax in paper P&L. ACMESOLAR's
    +₹37,551 would be about ₹29,660 in hand.
  - [SA-049](stories/SA-049.md) (S3, 5 points): put idle cash to work in normal markets. **Owner
    decision:** deploy idle cash in a normal market, and hold it only in a crisis ("if it's some
    war"). The regime targets and the per-day limit are proposals the owner confirms; the switch
    ships off. It depends on SA-050 and SA-051.
  - [SA-050](stories/SA-050.md) (S2, 2 points): one sizing rule for every autopilot buy. Today a
    SWITCH buy spends all its proceeds, with no 10% cap.
  - [SA-051](stories/SA-051.md) (S2, 3 points): the portfolio against the Nifty, with honest
    labels ("Invested" is really capital added) and a closed-trade record.

  Totals: 48 planned stories, 171 points (Sprints 1–6: 41 / 35 / 31 / 29 / 24 / 11). If the owner
  wants these sooner, SA-050 and SA-051 have no dependencies and could come next instead of
  SA-005; that resequencing needs the owner's word.
- **SA-004 was implemented on 2026-09-27** (a conversation, about 11:45–12:35 IST, on baseline
  `0a5bf9e`). Receipt: [SA-004-implementation.md](evidence/SA-004-implementation.md). No SA-039
  check was due. Nothing was committed, pushed or deployed.
  - **What it does, in one example.** The 8 Sep production record said `produced=20`,
    `expected=20`, `pipeline_ok=true`, while WELCORP had no envelope and 19 feedback rows existed.
    The same day now reads 19 of 20, `status: partial` and
    `missing: {WELCORP: "skipped: no_envelope"}`. The partial-output alert says
    "completed 19/20 — missing: skipped no_envelope: WELCORP".
  - **Outcomes.** The new `core/intelligence/rl/workflows/review_outcomes.py` gives each enabled
    ticker exactly one outcome:
    - `completed`;
    - `degraded`: completed on an input SA-003's record mode flags;
    - `data_gated`;
    - `skipped`: no envelope, no forecast row, or no close;
    - `failed`: an exception, a malformed result, or a timeout.

    Only completed and degraded (feedback written) are output.
  - **Also:**
    - required and attempted are counted separately;
    - disabled tickers are `excluded`, and a duplicate entry is reviewed once;
    - a second scheduled run of the same session merges: attempts add up, completion does not;
    - job `status` is `ok`, `partial`, `failed` or `empty`;
    - `pipeline_ok` is false for a malformed or raising pipeline, and when a review failed.
  - **Decisions flagged for the reviewer:** 5, in the receipt. For example, `degraded` counts as
    output, and the alerts use the merged cohort, not only this run.
  - **Tests** (network guard on, `RL_LEARNING_MODE=adapt`):
    - new files: 61 passed, including an integration test through the real `run_daily_review`
      that checks the persisted record against the stored feedback rows;
    - focused (36 existing files plus the 2 new): 376 passed;
    - 13 runtime mutations, 13 caught;
    - 7-day sweep: 91 passed each day, after one known `test_ops_alerts` flake on the Tuesday pin;
    - full `tests/unit`: 3503 passed, 5 skipped, 0 failed; the guard blocked the pre-existing 194;
    - `check_kt_docs`: 0 errors, and the PDF is rebuilt.
  - **Docs:** KT §1, §5, §9 (a new "Daily-review outcomes" paragraph), §11 and §12; the PDF;
    ARCHITECTURE; human cases 01-A and 01-B, plus a new 01-F (a rerun of the same session);
    `CODEBASE.md`.
  - **Routed:**
    - [SA-005](stories/SA-005.md): the new job-outcome test isolation, and leaks still open;
    - [SA-015](stories/SA-015.md): see the heads-up below;
    - [SA-034](stories/SA-034.md): no watchdog check reads this record yet;
    - [SA-036](stories/SA-036.md): one outcome contract; the pipeline's own `completed` hides
      per-holding advisor failures.
  - **Heads-up, pre-existing (F10, routed to SA-015).** The Mon–Fri 16:30 cron does not skip a
    weekday holiday, so each weekday holiday reviews a session twice.
    - Fri 2 Oct (NSE holiday) reviews Thu 1 Oct, and Mon 5 Oct reviews Thu 1 Oct again.
    - Each ticker runs a full `run_daily_review` for 1 Oct twice.
    - SA-004 would count that once; it does not stop the second run's learning writes.
  - **At commit:** the KT names `review_outcomes.py` in code formatting. The commit that lands
    SA-004 should link it and bump the KT header past `167f08b`.
- Before SA-005: run every test with the network guard `-p nonet` and `RL_LEARNING_MODE=adapt`
  (see step 4). With SA-005 in the checkout, plain `python -m pytest tests` is enough.
- **SA-003 is committed, pushed and deployed** at the owner's word ("commit and push", about
  09:00 IST on Sun 27 Sep).
  - **Commits.** SA-003 is `167f08b`; the KT bump is `a61fafe`, which declares `167f08b`, links
    `decision_gate.py` and rebuilds the PDF. `check_kt_docs` reports no errors.
    `verify SA-003-manifest.json --rev 167f08b` mismatches only the five status-edited docs. So
    every reviewed code, test and config byte is committed as reviewed.
  - **Push.** `f1c7eba..a61fafe` was pushed at 09:05:01 IST; it also carried `da90ee5`. On a
    Sunday, the time after 09:05 IST is job-free until `weekly_review` at 18:00.
  - **Deploy.** `0106fc89` reached SUCCESS at 09:27:57 IST. The boot log (read-only) shows startup
    complete, the scheduler started with 24 jobs registered, and 0 error or warning lines. No job
    fell in the switch.
  - **The build was a full rebuild, about 22 minutes.**
    - Docker Hub had moved the floating `python:3.11-slim` tag (base digest `da047cb8…` became
      `e41613d4…`). That invalidated every cached layer, so pip re-resolved the unpinned
      requirements.
    - Against the 23 Sep install, 15 packages changed (all minor or patch, for example uvicorn
      0.53→0.54 and opentelemetry 1.44→1.45), and 1 transitive package was added.
    - pandas, yfinance, nse (3.2.1), APScheduler (3.11.3), openai and torch are unchanged.
    - Routed to [SA-033](stories/SA-033.md): pin the base-image digest as well as the packages.
  - It ships `record` (`DECISION_GATE_MODE` is not set), so the deploy changes no outcome and is
    not a policy-flag change. It is live before the 1 Oct 09:00 forecast, so the October envelopes
    will carry `data_gate`.
  - **This record is committed locally** and rides the next push.
  - **Verify read-only across one scheduled cohort,** as the receipt's "Rollout" says. The first
    cohort is Mon 28 Sep, at the 16:30 review; check it alongside SA-039-P1.
    - `data/logs/decision_gate.jsonl` gains rows. Until 1 Oct, every review names
      `stage: forecast_row`, "issued before the data gate existed".
    - Reports carry `decision_gate`.
    - The weight and feedback behaviour is unchanged; SA-039-P1 checks this anyway.

**2. SA-003 was ACCEPTED on 2026-09-27 by a fresh-session review** (a new conversation, about
08:30–09:15 IST). Receipt: [SA-003-review.md](evidence/SA-003-review.md). SA-003 is `done`, and its
`production_verification` is now `pending_observation`, after the deploy in step 1. No SA-039
check was due. The review itself committed, pushed and deployed nothing; the commit and push
followed at the owner's word (step 1).

- **Input verified:**
  - the review input `dbe16714…`: 38 files, 0 mismatches;
  - the diff `a46a6846…`, rebuilt with the reviewer's own script;
  - the PDF blob.
- **Traced:**
  - all 8 non-test `analyse` callers;
  - the one `decide` caller;
  - both autopilot buy paths;
  - every weight and lesson writer;
  - the re-forecast paths.

  Each acts only through the gate, or is display-only and routed.
- **F1 (medium), in one example.** With `enforce` on, TATAMOTORS' 09:00 analysis on 1 Nov
  abstains.
  - No November envelope is built.
  - Nothing scheduled retries it before 1 Dec; only a restart's self-heal does.
  - Until then its reviews return `no_envelope`, and its ADDs stay blocked.

  The KT said "the next scheduled run retries", and the review corrected it. The retry and the log
  text are routed to [SA-036](stories/SA-036.md).
- **F2 (medium, predates SA-003), in one example.** Friday's review: yfinance has Friday's close,
  110. NSE has not listed Friday yet, and its newest row is Thursday's, 100.
  - The verifier returns 100, from Thursday.
  - Before SA-003, Friday was graded against Thursday's close.
  - SA-003 dates it Thursday, so it is not fresh: `record` logs it, and `enforce` skips the day.

  Routed to [SA-012](stories/SA-012.md).
- **The implementer's seven decisions:** the review agreed with each. EXIT and TRIM are never
  blocked (verified).
- **Tests** (network guard on):
  - full `tests/unit`: 3442 passed, 5 skipped, 0 failed; the guard blocked the pre-existing 194;
  - the 4 new files: 119 passed;
  - the reviewer's 5 runtime mutations: all caught (34, 5, 11, 13 and 32 failing);
  - the 7-day sweep: 119 passed each day;
  - the NSE-lag probe: 3 passed;
  - `check_kt_docs`: 0 errors.
- **Review edits (documentation only):**
  - status wording in the KT, ARCHITECTURE, 02-C, 03-C and `CODEBASE.md`;
  - the KT's F1 sentence corrected, and the F2 case named;
  - the PDF rebuilt (source `3735be42…`).

  `verify SA-003-manifest.json` now mismatches exactly those five files. No code, test or config
  changed.

**3. SA-003 was implemented on 2026-09-27** (a new conversation, about 03:40–05:15 IST, on baseline
`da90ee5`). Receipt: [SA-003-implementation.md](evidence/SA-003-implementation.md). No SA-039 check
was due. Nothing was committed, pushed or deployed.

- **What it does, in one example.** TATAMOTORS' price source answers 404, and the aggregator still
  says STRONG BUY on 9 of 9 dimensions.
  - The report now carries a typed `decision_gate`, `abstain`, naming the three unusable essential
    sections and the run id.
  - In `record` (the checked-in mode) nothing else changes, and a row in
    `data/logs/decision_gate.jsonl` says what enforcement would have withheld.
  - In `enforce` the report reads INSUFFICIENT DATA. No envelope is built on it, and the small
    holding's ADD becomes HOLD with no buy.
  - With a live price source, the same chain still buys.
- **Where it acts** (in `enforce`):
  - public analysis;
  - the month-start forecast and re-forecast;
  - the daily review: the graded row, a close from the session's own bar, and the re-run;
  - discovery's shelf;
  - the advisor's ADD and SWITCH destinations;
  - the autopilot's SWITCH buy leg.

  EXIT and TRIM are never blocked.
- **Tests** (network guard on, `RL_LEARNING_MODE=adapt`):
  - new files: 119 passed;
  - focused (32 affected existing files plus the new 4): 570 passed, 2 pre-existing failures that
    need the local Atlas DB (identical on baseline);
  - full `tests/unit`: 3442 passed, 5 skipped, 0 failed; the guard blocked the pre-existing 194;
  - 12 runtime mutations, 12 caught;
  - 7-day sweep (27 Sep – 3 Oct, across the month rollover and the 2 Oct holiday): 119 passed
    each day;
  - `check_kt_docs`: 0 errors.
- **Docs:** KT §1, §3, §4, §5, §6, §11 and §12; the PDF is rebuilt; ARCHITECTURE; human cases
  02-C, 02-F and 03-C; `CODEBASE.md`.
- **Routed:** [SA-004](stories/SA-004.md) (count `data_gated` separately),
  [SA-005](stories/SA-005.md) (the loader reload, the Atlas-dependent pipeline tests, the locking
  flake), [SA-008](stories/SA-008.md) (what the gate gives; TATAMOTORS maps to TMPV, and the gate
  cannot see that), and [SA-024](stories/SA-024.md) (the screens show a score next to INSUFFICIENT
  DATA).
- **At commit:** the KT names `src/backend/shared/pipeline/decision_gate.py` in code formatting.
  The commit that lands SA-003 should link it and bump the KT header past `8413b59`;
  `check_kt_docs.py` fails on a link to a file absent at the header's revision.

**4. SA-001 and SA-002 were committed, pushed and deployed on 2026-09-27.** They are committed as
`8413b59` (about 03:40 IST, at the owner's "commit and push", inside the 00:10–06:20 safe window).

- **Network guard.** Use `-p nonet` for every test run. Without it, a missed patch reaches real
  providers (see the incident in step 8). Check any date-relative fixture on 7 consecutive days;
  see the SA-005 note.
- **Commit and deploy:**
  - Commit checks passed. `verify SA-001-manifest.json --rev 8413b59` (17 files) and
    `verify SA-002-manifest.json --rev 8413b59` (19 files) each mismatch only in the five
    status-edited docs: the KT, the PDF, ARCHITECTURE, TEAM_TESTING_GUIDE and `CODEBASE.md`.
  - `npm run test:frontend`: 14 of 14 passed before the push.
  - The next commit bumps the KT header to `8413b59` (edition 2026-09-27), links
    `chat-markdown.js` and `fetch_result.py`, and changes the status lines to "committed".
  - **Pushed and deployed.** `16e7ea7..f1c7eba` was pushed at 03:41:25 IST; it also carried
    `994a7b6` and `103f2b8`. Deploy `0509de45` reached SUCCESS at about 03:42:48 IST.
    - The boot log (read-only) shows startup complete at 03:42:34 and the scheduler started with
      24 jobs registered. It has no error or warning lines.
    - No job fell in the switch; the next is the 06:30 watchdog.
    - Both stories' `production_verification` is now `pending_observation`.
    - This record is committed locally and rides the next push.
  - **Owner's post-deploy checks:**
    - SA-001: open the app twice, so that sw v8 takes over. Run human case 11-C in an isolated
      test account. Confirm that `marked@12.0.2` and `dompurify@3.4.16` load with status 200 and no
      SRI error.
    - SA-002: read-only, across one scheduled cohort, as in the Rollout section of its receipt.

**5. SA-002 was ACCEPTED on 2026-09-26 by a fresh-session re-review** (a new conversation, about
21:57–22:25 IST). Receipt: [SA-002-review.md](evidence/SA-002-review.md), under "Re-review". SA-002
is `done`, and `production_verification` is `pending_deployment`. No SA-039 check was due.

- **Input verified:**
  - the review input `c88edda5…`: 19 files, 0 mismatches;
  - the full diff `dc7e850b…` and the rework diff `56544c46…` both reproduced;
  - the first review's blobs exist in the object database.
- **M1 resolved, in one example.** Run as if on Monday 28 Sep, the whole contract file now passes.
  The reviewer reran the 7-day sweep: 7 of 7 days pass 155 of 155. With the old fixture put back,
  it fails on every day, through the guard.
- **M2 resolved, in one example.** The reviewer's own fixture uses yfinance's real shape: every row
  is NaN in the newest quarter (30 Jun), and the oldest column is sparse. The first review's code
  says `ok`, as of 30 Jun. The reworked code says `fallback`, as of 31 Mar, and names 30 Jun.
  - The same holds for three more shapes: the EBIT fallback row, a `pd.NA` nullable frame, and no
    quarter reported.
  - The prompt text is byte-identical to HEAD in 8 of 8 cases.
- **Decided:** an older blank quarter keeps `ok`, as the first review specified. The growth figure
  then shows `nan`, and SA-045's note covers it.
- **New findings (both low, both predate SA-002):**
  - **N1 → [SA-045](stories/SA-045.md).** The prompt's "Revenue YoY" compares the newest quarter
    with the one three quarters back. Revenue growing 10% a quarter shows +33.1%, where the true
    year-over-year change is +46.4%.
  - **T3 → [SA-005](stories/SA-005.md).** The full run failed 2 tests on Windows rename flakes.
    `test_delivery_api` fails 2 of 5 runs even alone, and `test_ops_alerts` loses its streak when a
    save fails.
- **Tests:**
  - focused: 289 passed, with 0 connections blocked;
  - full: 3321 passed, 2 failed (the flakes above), 5 skipped; the guard blocked the pre-existing
    194;
  - `check_kt_docs`: 0 errors.
- **Docs:** status wording in the KT (§1, §4, §11, §12), ARCHITECTURE, 02-F and `CODEBASE.md`. The
  PDF is rebuilt (source `333895c4…`). `verify SA-002-manifest.json` now mismatches exactly those
  five files.
- **Rollout (owner, after commit and push):** follow the "Rollout" section of the
  [implementation receipt](evidence/SA-002-implementation.md). It is additive: 7 nullable columns,
  and expect more `degraded` rows. Verify read-only across one scheduled cohort. Rollback is
  `observability.data_health_enabled: false`.
- Nothing was committed, pushed or deployed.

**6. The SA-002 rework was done on 2026-09-26** (a new conversation, about 20:50–21:30 IST).
The rework section is in the [implementation receipt](evidence/SA-002-implementation.md). No
SA-039 check was due.

- **M1, in one example.** Before, running on Monday 28 Sep made the fake "fresh" series end on
  Sunday. pandas 3 then built 299 dates for 300 values, so technicals read `empty` and 5 tests
  failed.
  - Now `_bars` rolls weekend dates back to the last session.
  - 14 guard tests pin a fixed Mon–Sun week and do not depend on the run day.
  - The whole contract file passes as if run on each of 7 days (Sun 27 Sep – Sat 3 Oct).
  - With the old fixture body put back, the original tests fail only on Sun, Mon and Tue, but the
    guard fails on every day.
- **M2, in one example.** Before, yfinance listing the quarter ended 27 Aug with NaN figures made
  fundamentals read `ok`, as of 27 Aug.
  - Now they read `fallback`, as of 28 May (the newest fully reported quarter), and the reason
    names the blank quarter. The row is `degraded`.
  - NaN, `None` and infinity all count as missing. The new key is `get_financials`
    `missing_values`.
  - The prompt text is byte-identical to HEAD in 13 of 13 cases.
  - Three runtime mutations are each caught: 9, 9 and 2 failing tests.
- **I1** had already been corrected in the receipt and in step 8 below before the rework began.
  The rework checked that no doc repeats the claim.
- **Tests:**
  - contract file: 155 passed (132 before + 23 new);
  - focused: 289 passed, with 0 connections blocked;
  - full: 3323 passed, 5 skipped, 0 failed; the guard blocked the pre-existing 194;
  - `check_kt_docs`: 0 errors; the PDF was rebuilt (source `0979ad97…`).
- **Docs:** status wording in the KT (§1, §4, §11, §12), ARCHITECTURE, TEAM_TESTING_GUIDE 02-F and
  `CODEBASE.md`. The KT §4 `fallback` meaning now includes a blank newest quarter, and 02-F gains
  that expectation. Routed: a note on [SA-045](stories/SA-045.md) (the Growth factor must read
  `missing_values`).
- Nothing was committed, pushed or deployed.

**7. The SA-002 fresh review requested changes on 2026-09-26** (a new conversation, about
13:20–14:00 IST). Receipt: [SA-002-review.md](evidence/SA-002-review.md).

- **Input verified:** `4d8968fd…`, 19 files, 0 mismatches; the diff digest `f605966c…` reproduced.
- **The production code has no critical or high defect:**
  - every essential producer decides its status from structured data;
  - the analyst's only input is the bundle, and nothing branches on the row;
  - the migration is additive, and there is no new secret sink.
- **The reviewer's own fixtures:**
  - A frozen symbol reads `stale` on all three essential sections (`degraded`). Correct.
  - Serper over quota reads `degraded`, with no essential section flagged. Correct.
  - With B2's rule put back at runtime, 100 of 104 health tests fail. Correct.
- **Why changes were requested, in one example.** Run the suite on Monday 28 Sep. The fake
  "healthy" price series then ends on Sunday 27 Sep. The test helper cannot build a price frame
  ending on a weekend, so the healthy technicals read `empty`, and 5 tests fail. They passed on
  2026-09-26 only because that was a Saturday.
  - **Second finding:** yfinance lists a quarter ended 30 days ago with no figures in it. The row
    says fundamentals `ok`, as of that quarter, while the prompt shows `₹nanCr`.
- **Tests:**
  - focused: 266 passed, with 0 connections blocked;
  - full: 3299 passed, 1 failed, 5 skipped. The failure is a Windows rename flake in
    `test_delivery_api`, which passes 16 of 16 alone; routed to SA-005. The guard blocked 194
    connections, the pre-existing set;
  - `check_kt_docs`: 0 errors.
- **Routed:** L1 (the Gross Profit EBITDA proxy) to SA-045; the flake and date-dependent fixtures
  to SA-005.
- **Doc edits:** status wording in the KT, ARCHITECTURE, TEAM_TESTING_GUIDE 02-F and CODEBASE.md,
  and the PDF is rebuilt. Nothing was committed, pushed or deployed.

**8. SA-002 was implemented on 2026-09-26** (a conversation from about 10:24 to 11:20 IST). Its
fresh review requested changes (step 7); the rework is step 6, and the re-review accepted it (step 5).

- **What it does, in one example:** TATAMOTORS' price source answers 404, while news, macro and
  flows answer, and the analyst scores 9/9.
  - Before, the data-health row said `ok`, with 10 live sections: every "Technical data
    unavailable for …" sentence counted as data.
  - Now each section producer returns a typed `FetchResult` (status, source, as-of, reason), so
    technicals and fundamentals read `empty`, peers valuation `fallback`, and the row `degraded`,
    with `essential_unusable` naming all three.
  - The analyst's prompt text is byte-identical: 24 producer cases and 5 whole-bundle scenarios
    were compared against the HEAD code.
  - Nothing branches on the row yet; SA-003 gates.
- **Evidence:**
  - 132 new tests;
  - the full unit suite: 3300 passed, 5 skipped, under a network guard;
  - 12 of 12 reintroduced defects caught;
  - `check_kt_docs`: 0 errors; the PDF was rebuilt.
- **Incident (recorded in the receipt).** One intermediate run of the existing sector tests, before
  their patches were retargeted, reached real providers with the local `.env` keys. It made +2
  Serper and +10 Tavily successful calls, plus public yfinance calls. The 8 Tavily cache pairs it
  wrote were deleted. Nothing in production was touched.
- **Found, pre-existing (routed to SA-005 as T2).** With the guard on, the *existing* suite tried
  194 outbound connections: `openrouter.ai` 120 (four RL review test files), NSE 68 and Serper 6.
  The pre-SA-002 code shows the same pattern. **In a normal unguarded run with `.env` keys, these
  are real calls, and the OpenRouter ones likely spend LLM credit on every suite run.** Consider
  running the suite with the guard until SA-005 lands.
- **Other routed notes:** SA-003 (gate on the record, not `has_real_data`), SA-044 (F1: the
  automobile peer P/E fallback query), SA-045 (F3: substitute zeros and defaults as factor inputs).
- **Rollout (owner, after acceptance).** Deploy is additive: 7 nullable DB columns are added on
  boot, and old rows are untouched. Expect more `degraded` rows, which is the point. Tavily cache
  entries from September read `unverified` until 1 Oct.
- **Serper credit, answered (owner, 2026-09-26):** the serper.dev dashboard shows **37,747 credits
  left**. The app's "2,590 of 2,500" was never a limit: `SERPER_MONTHLY_LIMIT` only feeds the usage
  log, and no code enforces it. Recorded on [SA-035](stories/SA-035.md). This closes the open
  "check serper.dev for real remaining credits" item from 23 Sep. IPO-0c's decision (GMP stays
  dark) stands on its own reasons.

  Rollback: `observability.data_health_enabled: false`. Production verification is read-only,
  across one scheduled cohort; see the receipt.
- **Commit interaction.** SA-001 and SA-002 are both uncommitted in one worktree and share six
  files. If they are committed together, SA-001's commit check will also show `CODEBASE.md`, which
  is SA-002's hunk. The receipt explains. Commit and push only at the owner's word, in a safe
  window.

**9. SA-001 was ACCEPTED on 2026-09-26 by a fresh-session review** (a new conversation, about
07:35–07:55 IST). Receipt: [SA-001-review.md](evidence/SA-001-review.md). SA-001 is `done`;
`production_verification` is `pending_deployment`. No SA-039 check was due during the review.

- **What the review checked:**
  - The input was verified first: `2ded4b43…`, 17 files, 0 mismatches, on baseline `103f2b8`.
  - The reviewer re-traced model and tool text to every client sink. There is one HTML sink, the
    bubble; the only URL sink, `sw.js` `openWindow`, takes server constants.
  - The previously executable fixture was re-run on the pre-fix files: 0 of 14 pass, and
    `img-onerror`/`img-split` execute. The reviewed files pass 14 of 14.
  - 20 of the reviewer's own payloads went through at every prefix: 0 executions, and the output is
    stable on re-parse.
  - The live CDN bytes equal all five SRI hashes.
  - Focused pytest: 12 passed. `check_kt_docs`: 0 errors, after the review's status-wording edits
    and the PDF rebuild.
- **Findings:** none critical, high or medium.
  - **L1 (low):** the browser suite skips on machines without Node, and the repo has no CI. Routed
    to [SA-005](stories/SA-005.md). Until then, run `npm run test:frontend` before any push that
    touches `src/frontend/prototypes/`.
  - **I1 (info):** the harness flags an inert partial `href="https://"`. Noted on
    [SA-028](stories/SA-028.md).
- **Uncommitted in the worktree:**
  - the SA-001 implementation (the 17 manifest files, plus its receipt and manifest);
  - the review bookkeeping: the review receipt, STATE, this file, and the notes on SA-005, SA-028
    and SA-002;
  - status wording in the KT, the PDF, ARCHITECTURE and TEAM_TESTING_GUIDE.

  Commit at the owner's word. Before committing, run
  `python scripts/docs/kt_manifest.py verify docs/planning/PI-2026-09/evidence/SA-001-manifest.json --rev <commit>`.
  Expect mismatches only in `TECHNICAL_DESIGN.md`, the PDF, `ARCHITECTURE.md` and
  `TEAM_TESTING_GUIDE.md`. Bump the KT header revision to the commit, and link `chat-markdown.js`
  there. `994a7b6` and `103f2b8` are also still unpushed.
- **What it does, in one example:** the model quotes `Tata Motors <img src=x onerror="…">`. Before,
  the chat bubble created the image and the handler ran, next to the stored login token. Now the
  bubble shows that text literally, and nothing runs. Bold, lists, code, tables and https links
  still render. Links open in a new tab that cannot reach the app.
- **How:** the new `src/frontend/prototypes/chat-markdown.js` has two layers:
  - marked shows raw HTML as text;
  - DOMPurify 3.4.16 keeps Markdown tags and http(s) links only, with no images, styles or events.

  It fails closed to escaped text. index.html pins marked 12.0.2 (the same bytes as before) and
  DOMPurify with SRI, and takes marked off `window` immediately. That covers a pre-fix `sphere.jsx`
  still cached by the service worker, which goes to v8.
- **Evidence:**
  - 14 real-browser tests through the actual `ChatOverlay`, with no network, stable over 3 runs;
  - 9 static pytest guards (the sink inventory, including URL sinks, and the exact pins);
  - full unit suite: 3166 passed, 5 skipped (with `RL_LEARNING_MODE=adapt`);
  - on the pre-fix files the suite records the fixture executing, and five weakened fixes are each
    caught;
  - `check_kt_docs`: 0 errors, and the PDF is rebuilt.
- **Routed:** CSP and bearer-token storage go to [SA-028](stories/SA-028.md) (a routed note). CSP
  needs the compiled client first.
- **Rollout (owner):** commit at the owner's word, and bump the KT header to that commit, linking
  `chat-markdown.js`. Every push redeploys, so push only in a safe window (step 0 rules; read IST
  with plain `date`). This change affects the served client. After the deploy, open the app twice so
  sw v8 takes over, then run human case 11-C in an isolated test account. The fixture only changes
  the tab title if it ever runs. Also confirm that `marked@12.0.2` and `dompurify@3.4.16` load with
  status 200 and no SRI error. `production_verification` stays `pending_deployment` until then.

**2026-09-26, owner-adopted design (no story started): [one engine with sector lenses](../../superpowers/specs/2026-09-26-one-engine-sector-lenses-design.md).**
This is the single reference for both the learning-exit logic (§1) and the analysis redesign.

- **The per-sector graphs go.**
  - Sector knowledge becomes lens YAML (real peers, benchmark, KPIs), resolved from NSE's
    industry field.
  - Code computes five factors: Value, Quality, Growth, Momentum and Risk.
  - One LLM reader returns dated events, and code turns them into Catalyst.
  - Code decides at equal weights; below 4 of 6 factors it gives no verdict. The LLM explains.
  - Learning uses six pooled factor weights.
- **Board:**
  - New stories: SA-044 (peer fix, Sprint 2), SA-045 (factors, Sprint 4), SA-046 (reader,
    Sprint 4) and SA-047 (decide, shadow and switch on non-inferiority, Sprint 5).
  - SA-026 is now the lens story (Sprint 3). SA-043 learns pooled factor weights (Sprint 4).
  - SA-022 and SA-027 now also depend on SA-047.
  - Totals: 44 planned stories, 158 points (Sprints 1–6: 41 / 30 / 23 / 29 / 24 / 11).
- **Found while inspecting (a live defect, fixed by SA-044):** generic-graph stocks are valued
  against car makers (SUNPHARMA → MARUTI, TATAMOTORS, M&M, HEROMOTOCO, BAJAJ-AUTO).
- KT sections 1, 4, 5, 11 and 12, ARCHITECTURE and the PI README are updated; the PDF is rebuilt
  (`check_kt_docs`: 0 errors, 47 stories).
- **Committed as `5a27683` and pushed on 2026-09-26 at 06:22:29 IST** (the reflog says "update
  by push" from this checkout). The owner asked to commit and push. The push was not run by
  Claude's commands, most likely through VS Code. It carried `0b3ebb9` too.
  - Deploy `82c945da` reached SUCCESS, and the new container registered its jobs at 06:31:09.
  - The old container ran the 06:30 watchdog first (`evaluated=17 notified=0 levels=[]`), so
    nothing was missed.
  - Documentation only; production still runs `adapt`.
- **`observe` is ACTIVE in production since 2026-09-26, about 06:40 IST.** The owner set the
  Railway variable `RL_LEARNING_MODE=observe`. Deploys `786faf7f` and `da9df6cf` (`16e7ea7`)
  reached SUCCESS. A read-only RL-monitor check shows all 20 tickers in `observe`, using the default
  weights. Record: [SA-039-activation-2026-09-26.md](evidence/SA-039-activation-2026-09-26.md).
  STATE: `production_verification: pending_observation`. Rollback is deleting the variable.
  **Checks still due (read-only):**
  - **Mon 28 Sep after 16:30:** the logs show `learning_mode=observe` and `Proposal (not
    applied)`; `/ui/rl/summary` versions match the baseline in ignored
    `analysis_data/sa039_activation_versions_20260926.json`; `/ui/rl/weights` has a
    `latest_observation` dated 2026-09-28.
  - **Tue 29 Sep:** the versions are still unchanged.
  - **Thu 1 Oct after 09:00:** the new envelopes carry `learning_mode: observe`.
- **Local side effect:** the owner's local environment (probably `.env`) now also resolves
  `observe`, so **7 lesson-emphasis unit tests fail locally**. They assume `adapt`, and SA-001 did
  not cause this. Until SA-005 pins the mode in `tests/conftest.py` (routed note added), run tests
  with `RL_LEARNING_MODE=adapt`, or remove that line from the local `.env`.
- The docs for this (the activation record, STATE, this file, KT sections 1/5/12, ARCHITECTURE,
  04-F, the SA-005 note and the PDF) are committed locally and ride the next push.

**2026-09-26, owner-requested planning (no story started): how learning leaves `observe`.**

- **New [SA-043](stories/SA-043.md)** (Sprint 3, 3 points, after SA-015): a shadow learner.
  - A separate weight file starts from the defaults and learns every night on the corrected
    target. Decisions stay on the defaults.
  - For each issued decision it records the default verdict and the shadow verdict, computed from
    the same agent scores.
- **[SA-022](stories/SA-022.md) is amended** with predeclared gates. They are scored only on
  disagreements between the two verdicts:
  - at least 100 effective disagreements, over at least 3 months and 3 sectors;
  - the shadow right on at least 60% of them;
  - wins consistent month to month and robust to dropping the best sector;
  - sane weights, with no agent collapsing to 0.

  A pass must hold at two consecutive monthly looks, and the owner decides. Promotion resumes from
  the shadow's weights, never the stored pre-fix ones. A reverse tally below 45% returns learning
  to `observe`.
- Totals are now 40 planned stories and 143 points (Sprint 3: 21). KT sections 1, 5 and 12 and the
  PI README are updated; the PDF is rebuilt (`check_kt_docs`: 0 errors). This is uncommitted,
  alongside the SA-039 review bookkeeping below.
- Owner-decided backlog changes are recorded in STATE; nothing changed in the task order, and the
  next story is still SA-001.

**SA-039 was ACCEPTED on 2026-09-25** by a fresh-session review at `4c4728a`, with review input
`1efe361f…` (0 mismatches). Receipt: [SA-039-review.md](evidence/SA-039-review.md). SA-039 is `done`.
STATE has `active_task: null`, `next_task: SA-001` and `next_phase: implementation`.
`production_verification` stays `not_started`, because production still runs `adapt`.

- **Next PI phase: implement [SA-001](stories/SA-001.md)** in a new conversation. It has no
  dependencies. Opener: `Continue — implement SA-001`.
- **Review bookkeeping is uncommitted** in the worktree:
  - the review receipt, STATE, this file and the implementation-receipt banner;
  - routed notes on SA-022 (I2) and SA-026 (L2);
  - post-acceptance docs maintenance: KT §1, §5 and §12 status lines, the L1 paper-lane wording
    and the I1 timing sentence in §5, ARCHITECTURE, TEAM_TESTING_GUIDE 04-F, and the rebuilt PDF
    (`check_kt_docs`: 0 errors).

  Commit at the owner's word. `0b3ebb9` is also still unpushed. Every push redeploys, so push only
  in a safe window (Step 0 rules; read IST with plain `date`).
- **Owner decision: activate `observe`.** Either a one-line `rl.learning_mode: observe` commit or
  the Railway variable `RL_LEARNING_MODE=observe` (checked: the env value overrides the yaml).
  **Timing (review I1):** rows already issued keep their verdicts; the review re-weights only their
  confidence. If activation lands before the **1 Oct 09:00 IST** monthly forecast, October is the
  first clean `observe` cohort. The activation commit should also update the "Production is still
  `adapt`" and status lines in the KT, ARCHITECTURE and 04-F, then rebuild the PDF. Afterwards,
  verify read-only against the [baseline](evidence/SA-039-baseline-2026-09-24.md).
- Findings: L1 is fixed (wording). L2, which predates SA-039, is routed to SA-026: the review
  initialises missing weight memory from the automobile table. I2 is routed to SA-022: observe
  freezes the numeric channels only. Earlier routes stand: T1 → SA-005, F1 → SA-024, F2 → SA-016.

### Previous state (SA-039 implemented and pushed, 2026-09-24/25)

**SA-039 implementation is done and awaits a fresh-session review** (2026-09-24, one conversation).
STATE: `active_task: SA-039`, status `review_required`, `next_phase: review`. Receipt:
[SA-039-implementation.md](evidence/SA-039-implementation.md). Review input: `1efe361f…` from
[SA-039-manifest.json](evidence/SA-039-manifest.json) (18 files) on top of HEAD `3742fff`.

- **Next PI phase: the fresh review of SA-039** in a new conversation. Opener:
  `Continue — fresh review of SA-039`. First step:
  `python scripts/docs/kt_manifest.py verify docs/planning/PI-2026-09/evidence/SA-039-manifest.json --rev 4c4728a`
  (expect 0 mismatches), then follow [REVIEW.md](REVIEW.md). Without `--rev`, the KT and PDF
  mismatch by design, because the next commit bumped the KT header. The receipt lists every decision
  consumer and the test that covers it. It also flags one scope interpretation for the reviewer:
  the untagged lesson micro-adjustment is contained too.
- **Committed and pushed on 2026-09-25 at the owner's word.** **Correction:** the owner asked at
  16:18 IST, not 10:48. `TZ=Asia/Kolkata date` returns UTC in Git Bash, so the push went out at
  about 16:22 IST, inside the blocked review window. Deploy `7ebd06c5` (`309d801`) reached SUCCESS.
  The new container was up at 16:28:56, so the 16:30 review still ran, on the new code in `adapt`
  mode: 19 completions and 19 weight writes, done at 16:54. The 20th ticker (metals) returned
  `no_envelope`; it has no forecast envelope, an existing gap. The job and its portfolio pipeline
  finished at 16:55. Nothing was missed.
  This correction is committed locally and **not pushed**; it rides the next push. Read IST with
  plain `date` from now on.
  `4c4728a` is the SA-039 change exactly as the review input describes it. The next commit bumps
  the KT header's `Code inspected` revision to `4c4728a` (edition 2026-09-25), links
  `learning_mode.py` and rebuilds the PDF. The deploy outcome is recorded in the commit after that.
  The code ships as `adapt`, so the deploy changes no decision.
- **What it does, in one example:** a ticker stores `technical = 0.0` at v41. With
  `rl.learning_mode: observe`, its forecast and analysis use the 0.12 default. After the review the
  file still says 0.0 at v41, and `<TICKER>_weight_observations.json` shows what v42 would have
  been. The code ships as `adapt`, so nothing changes until activation.
- **Activation is a separate owner decision after acceptance:** a one-line config commit, or the
  Railway variable `RL_LEARNING_MODE=observe`. Push only in a safe window (Step 0 rules). Afterwards,
  verify production read-only against the
  [baseline](evidence/SA-039-baseline-2026-09-24.md).
- **R2 done:** the baseline comes from today's 16:30 review logs (deploy `d9c459ae`). Chart weight
  was 0.0 for 9 of 18 logged tickers; 5 of the 6 `technical` tickers were at 0.0, which reproduces
  the 23 Sep figure; all 19 reviews wrote a new version. KT §1 and §5 now cite it. §5 also corrects
  the default: 0.12 generic, 0.10 renewable.
- **Routed self-review follow-ups:**
  - T1: the shared review test harness still constructs a live NSE session. Routed to SA-005, and
    it may explain the `key_registry.json` leak.
  - F1: chat context, `/scheduler/status` and the CLI show stored weights as if live. Routed to
    SA-024.
  - F2: the FeedbackAgent drift summary. Routed to SA-016.
- The Step 1 production checks below are otherwise unchanged. **OpenRouter was recharged**
  (owner, 2026-09-25). IPO-0a is still open.

### Previous state (DOC-001 accepted, earlier on 2026-09-24)

**DOC-001 was ACCEPTED on 2026-09-24** by a second fresh-session review, at `c832145` with review
input `63ff474c…`. The receipt is [DOC-001-review-2026-09-24.md](evidence/DOC-001-review-2026-09-24.md).
DOC-001 is `done`. STATE now has `active_task: null`, `next_task: SA-039` and `next_phase: implementation`.

- **Next PI phase: implement [SA-039](stories/SA-039.md)** in a new conversation. Opener:
  `Continue — implement SA-039`. Read the card's new "Routed input (R2)" section: the
  implementation must also record a sanitized pre-activation weight baseline. That record becomes
  the evidence for KT §5's "5 of 6 tickers" sentence, and §1's production row should name the
  2026-09-23 inspection when §5 is rewritten.
- The low follow-ups are routed, not waived. R3 (the KT harness imports nse 4.0.1, outside the
  `<4.0` pin) is on SA-033, and F5 stays on SA-005/SA-006.
- **Committed locally, not pushed** (at the owner's "commit", 2026-09-24): this conversation's work
  in one commit on top of `c832145`:
  - the review bookkeeping: the review receipt, STATE, this file, the implementation-receipt banner,
    and routed notes on SA-033 and SA-039;
  - the observability backlog (below).

  `origin/main` is still `e8df088`, so both local commits ride the next push. Push only on the
  owner's explicit word, in a safe window (Step 0 rules). The commits are docs-only, but every push
  still redeploys. **Manifest note:** the backlog changes
  three DOC-001 payload files (the KT, the PDF and the PI README) as normal post-acceptance
  maintenance. Verify the accepted input with `kt_manifest.py verify <manifest> --rev c832145`
  (0 mismatches). Against a later HEAD those three files will differ, and that is expected.
- **Step 1 production checks, 24 Sep**, from read-only `railway logs` (no ssh):
  - The build installed **nse 3.2.1**, so the pin works, and the fix has been live since
    23 Sep 22:44 IST (deploy `dfd7a15d`).
  - The **08:00 `ipo_refresh_am` logged no bid-ladder fetch failure**: current=7, 50 s, where the
    23 Sep 17:45 run had 10 `_req` failures. Rows on the volume are not visible from logs, so
    **IPO-0a stays open**; the 06:30 watchdog on 25 Sep or an owner probe confirms them.
  - The 06:30 watchdog raised 1 `warning`. The log doesn't name the check; it is inferred to be
    `ipo_signals_accruing`.
  - **0 OpenRouter 402s** since 23 Sep 13:30. The 23 Sep 16:30 review logged 18 runs costing
    **$0.40**, so a $0.97 balance leaves about 2 days. **Top up before 25 Sep 16:30.**
  - Still due: VARMORA rows after 17:45, and whether the 19:00 `ipo_deep_dive` stores its first
    verdict.

### Production observability — adopted 2026-09-24 (owner decisions D1–D5)

The owner asked for a proper production "fetcher" and a careful tool evaluation. The design is
[2026-09-24-production-observability-design.md](../../superpowers/specs/2026-09-24-production-observability-design.md).

- **Verdict:** no Prometheus, no OpenTelemetry SDK (field names only), no Arize or Langfuse for
  now, and Sentry deferred. Instead:
  - an in-app ops ledger in `telemetry.db`: `job_runs`, `source_health_day`, `error_signatures`
    and `budget_readings`;
  - the watchdog as evaluator, now also run right after each critical job;
  - a read-only `GET /ops/status` with `OPS_READ_TOKEN`, plus a fetcher CLI;
  - Healthchecks.io as the outside witness, alerting by Telegram.
- **Board:** SA-040 (S1, 3 points), SA-041 (S2, 3 points) and SA-042 (S1, 2 points) are added.
  SA-034 goes 5 → 6 points, SA-036 goes 3 → 4, and SA-035 is amended. That makes 39 planned
  stories and 140 points; Sprint 1 is 41 and Sprint 2 is 28. SA-039 is still first. The KT §12
  rows are added and the PDF is rebuilt (`check_kt_docs.py`: 0 errors).
- **Owner actions (settings only, no code). The owner will do these at the end**, so don't press
  for them earlier. Remind when a rollout needs one: the OpenRouter key limit for SA-035, and
  Healthchecks.io for SA-042.
  - Railway: turn on alerts for deploy failed/crashed and volume usage.
  - OpenRouter: set a monthly credit limit on the production key.
  - Healthchecks.io: create the account and connect Telegram, ready for SA-042.
- **Suggested ops order after SA-039:** SA-036 → SA-035 → SA-040 → SA-042 → SA-034 → SA-041.
  STATE's task order is unchanged, so "continue" still follows the existing sequence.

**Pushed 2026-09-24 06:56 IST at the owner's explicit "push it".** `a2c19c9..e8df088` was pushed, and
deploy `d9c459ae` reached SUCCESS at 07:03 IST. The boot log shows 24 jobs registered, no errors,
and the serper counter at 2,590/2,500. The 06:30 watchdog had already finished, and no job was due
before 07:30. Production now runs `e8df088`, which adds no application code over `a2c19c9`. The rest
of Step 0 below is the record of how the push was arranged.

### Step 0 — push the two local commits (done; see above)

Done at the owner's go-ahead, 23:30 IST:

- **`650c01c`** holds the earlier 22-path batch: the production assurance review, SA-033…SA-038,
  routed notes, and the DOC-001 payload `d5516ae0…`. `verify --rev HEAD` reported 0 mismatches.
- **The commit after it** holds the owner's three decisions (Step 2, now resolved). That is the
  SA-039 card, the SA-003 split, the SA-024 routed note, STATE, the PI README, KT §1/§5/§12, the
  rebuilt PDF, the IPO-0c record, this HANDOFF, the DOC-001 receipt ("Payload update 2") and the
  regenerated manifest (**review input `63ff474c…`**). After it, `verify --rev HEAD` must again
  report 0 mismatches.

**The push is still pending.** The owner chose "commit now, push later". At 23:28 IST a push would
have redeployed over `data_backup_nightly` (23:30), and probably over `audit_nightly` (23:45) and
`prompt_daily_deploy` (00:00).

**Every push redeploys production** (no watch-path rule until SA-037), and the in-memory scheduler
loses any job whose time falls inside the roughly 8-minute deploy.

- **Safest window: 00:10–06:20 IST.**
- Otherwise avoid 07:25–09:05, 11:55–12:05, 14:55–15:05, 16:25–17:05, 17:40–17:55, 18:55–19:20
  and 22:55–00:05.
- Push only when the owner says "push". Afterwards, confirm with `railway deployment list --json` that
  the new deploy reached SUCCESS. The two commits change documentation only, with no application code
  or requirements. The deploy still rebuilds and restarts the scheduler.

### Step 1 — time-sensitive production checks (read-only; the owner runs the probe)

| When (IST) | Check | Why |
|---|---|---|
| 24 Sep after 08:00 and 17:45 | VARMORA rows appear in `data/ipo/ipo_signals.jsonl` | First proof that `a2c19c9` fixed capture. VARMORA closes on the 24th. |
| 24 Sep after 19:00 | `ipo_deep_dive` post-close for VARMORA stored a row: `ipo_verdicts.jsonl` exists; note whether `substance` is still null | First stored P3 verdict. The 23 Sep T−1 run stored nothing (`demand=None substance=None`). |
| Until 25 Sep | `railway logs \| grep -i "error code: 402"` | The owner reported an OpenRouter balance of **$0.97**, with a top-up on 25 Sep. The existing streak alert can miss a low-balance pattern (SA-035). |
| After capture is proven | Close `IPO-0a`: delete `ipo_p0_live_window_check` from `config/milestones.yaml`, evidence in the commit message | Not before. |

The probe is `analysis_data/prod_probe_20260923.py`. It is ignored, so it may be missing in another
checkout; it prints counts and IPO fields only. Run it from Git Bash at the repo root:

```bash
railway ssh "cd /app && echo $(gzip -9c analysis_data/prod_probe_20260923.py | base64 -w0) | base64 -d | python -c 'import sys,zlib;exec(zlib.decompress(sys.stdin.buffer.read(),31))'"
```

Claude can run `railway status`, `railway deployment list --json` and `railway logs <id> -n 2000`
(plus `--build`), after prepending `/c/Program Files/nodejs:$HOME/AppData/Roaming/npm` to PATH.
**Claude's `railway ssh` is blocked by the auto-mode classifier.** Volume reads go through the
owner.

### Step 2 — owner decisions: all three resolved 2026-09-23, about 23:30 IST

1. **Learning containment: yes, reset to defaults.** The containment is split out of SA-003 as
   **[SA-039](stories/SA-039.md)** (P0, Sprint 1, 3 points, no dependencies). It is placed first in
   STATE's task order, and SA-003 went from 5 to 4 points. SA-039 resets on the **read side**:
   - Decision consumers (forecast, public analysis, and the review's re-scoring and re-forecast) use
     the sector's configured default table.
   - Lesson emphasis stops.
   - The adapter keeps computing into a diagnostic record, and stored `WeightMemory` is never
     mutated.

   So there is no production data migration, and rollback is exact. Example: stored
   `technical = 0.0` stays 0.0 on disk, while the forecast uses 0.12. The code ships with `adapt` as
   the default. Activation is a separate one-line config commit, pushed only with the owner's
   go-ahead.

   Also found while writing the card, by code inspection: the verdict-shadow field
   `learned_weights_used` is true whenever any weights are passed, defaults included, so it
   overstates learned-weight use. That is routed to SA-024, and SA-039 must not use it as evidence.
2. **IPO-0c: GMP stays dark.** It is closed in the IPO plan with no code change, because `gmp_pct` is
   already a dark froth input. The serper.dev dashboard was **not** read, so the question of real
   account credit stays with SA-035.
3. **Push timing:** commit now, and push only when the owner says so, after 00:10 IST (Step 0).

### Step 3 — then the normal PI sequence

- ✅ **DOC-001 accepted 2026-09-24** (see START HERE). The bullets below are the pre-review record.
- **DOC-001** was `review_required`, with review input
  **`63ff474cec51a5810af84dca279a8fcdaa93239cd65230e6f5cd738b01128dd0`**.
  - Its fresh-session review runs in a **new conversation**. It can run against the local commits
    before the push. Opener: `Continue — fresh-session review of DOC-001`.
  - Receipt: [the 2026-09-23 section](evidence/DOC-001-implementation.md#remediation-phase--2026-09-23).
    F1–F4 are fixed, F5 is routed to SA-005/SA-006, F6 is done, and F2 was fixed by the PDF rebuild.
  - The payload changed twice more. The first change added the SA-033–SA-038 KT rows ("Payload
    update"). The second added SA-039's row and a labelled PI-target paragraph in KT §5 ("Payload
    update 2"). Check that §5 paragraph against `daily_review.py` Step 5.
- **After DOC-001 is accepted:** select the next ready story, but do not start it in the review
  chat. By STATE's order that is **SA-039**, then SA-001.
- **Ready now** (all dependencies done): SA-039 (S1, P0), SA-001 (S1, P0), SA-002 (S1), SA-004 (S1),
  SA-005 (S1), SA-007 (S1), SA-033 (S1), SA-035 (S1), SA-036 (S1), SA-038 (S1), SA-006 (S2), SA-009
  (S2) and SA-010 (S2, P2). There are 39 SA stories in total: 36 planned (130 points) and 3 stretch.
  Sprint 1 is 35 points, and Sprint 2 is 24.
- **IPO (PI Prospect)** stays paused apart from the Step 1 checks. Open items: IPO-0a (Step 1),
  IPO-0d (brief freshness), IPO-0e (P1 spine in production), and IPO-5a/5b (gated). IPO-0c is
  closed as "no". See `docs/superpowers/plans/2026-09-21-ipo-prospect-p3-substance.md`.

### How the owner likes to work (observed this session)

- Explain each decision with a small concrete example (e.g. ₹100 → predicted ₹110 → closed ₹105).
- Welcomes deep research and wants every recommendation turned into board tasks.
- Commits and pushes happen only when the owner says so; each push is asked separately.

### Backlog additions and owner decisions — 2026-09-23 (late)

At the user's request, every recommendation in the
[production assurance review](../../audit/2026-09-23-production-assurance-review.md) is now on a
board. **New stories:** SA-033 (dependency lock), SA-034 (silent-degradation watchdog), SA-035
(LLM/Serper credit exhaustion; OpenRouter was at $0.97, top-up 25 Sep), SA-036 (job outcomes),
SA-037 (deploy/missed-job hygiene), SA-038 (lapsed milestones). **SA-007 moved to Sprint 1** (no
off-site backup). Notes were routed to SA-003, SA-008, SA-010, SA-011, SA-023 and SA-028. The IPO
plan gains `IPO-0d` (brief freshness) and `IPO-0e` (P1 spine in production).

**Decisions that were waiting on the owner** have all been resolved; see Step 2 above. Containment
became SA-039, GMP stays dark, and the push waits for the owner's word after 00:10 IST.

### Production read — 2026-09-23 (read-only; supersedes "no railway access" notes below)

The Railway CLI now works here (Node installed, folder linked to project `carefree-renewal` /
`production` / `StockAgent`). The user ran one read-only probe through `railway ssh`; Claude's own
`railway ssh` is blocked by the auto-mode classifier. The probe is
`analysis_data/prod_probe_20260923.py` (ignored). Run it from Git Bash:
`railway ssh "cd /app && echo $(gzip -9c <probe> | base64 -w0) | base64 -d | python -c 'import sys,zlib;exec(zlib.decompress(sys.stdin.buffer.read(),31))'"`.

- **Deploy:** `b68bc02` is SUCCESS (2026-09-23 07:59 UTC).
- **D6 — closeable.** In the outbox, before 21 Sep there were 77 email rows dead and 77 push
  delivered. Since 21 Sep: 3 email dead, all before the redeploy (last at 07:52 UTC on the 21st);
  **8 email delivered, 0 dead since**, and 11 push delivered (email/push parity). "Delivered" means
  provider-accepted. This is production evidence toward SA-006, **not** its acceptance.
- **IPO live capture is broken in production since ~18–19 Sep.** Cause confirmed from the logs:
  `'NSE' object has no attribute '_req'`. `nse` 4.0 (31 Aug) removed `NSE._req`, and the 21 Sep
  rebuild installed 4.0.1 under the open-ended pin `nse>=2.0.0`. The fix is the pin
  `nse>=2.0.0,<4.0` plus tests of the real dependency. The 19–21 Sep window, on the old 3.2.1
  image, is still unexplained. The 22 Sep brief's category figures were 2–3 days stale (NSE QIB 1.53× shown,
  final 12.68×). VARMORA has no ledger rows, and `ipo_signals_accruing` is warning. **Do not close
  IPO-0a.** Full evidence is under IPO-0a in the plan.
- **P1 spine absent in production** (`data/ipo/ipo_history.jsonl` missing).
- **IPO-0c:** serper counter 2,590 in September (default budget 2,500). Recommend GMP stays dark;
  check serper.dev for real remaining credits.
- **P3:** no `ipo_verdicts.jsonl` yet. That is expected for NSE/SONA, because their T−1 run predates
  the deploy. VARMORA's T−1 run is 23 Sep 19:00 IST, but its demand inputs are dark (no ledger rows).
- **P3 run observed:** `ipo_deep_dive` fired at 19:01 IST for VARMORA (`t_minus_1`, 16 docs, 9
  extracted), with demand and substance both dark, so `written=False` ("every index dark, not
  stored").
- **After the fix deploys:** confirm VARMORA ledger rows land at the 08:00 / 17:45 IST refreshes on
  24 Sep, the day it closes (re-run the probe). Only then revisit IPO-0a.

### IPO stays paused

`ed1b900` (IPO-4c) is pushed and `origin/main` is current, which closes **Sprint 4** of PI "Prospect".
The user chose to **pause IPO work and wait for live production evidence** rather than start `IPO-5a`.
Do not start an `IPO-` task unless the user brings evidence or says so. One encouraging note from the
review: the incremental-documentation discipline DOC-001 introduced **is** being followed — the 23→24
job-count change propagated correctly to four documents, and cases 05-F/05-G were added with their
stories.

After DOC-001 is accepted, `SA-039` is the first remediation story. It was promoted ahead of `SA-001`
by the owner on 2026-09-23 (Step 2). Select it, but do not start it in the acceptance conversation.

### Why IPO is waiting, and what arrives on its own

Everything through Sprint 4 is built and now deployed-on-push; **none of it has been measured in
production.** The first real evidence appears without anyone doing anything:

- **Tonight and each evening after**, the `ipo_deep_dive` job (19:00 IST) should hit its `post_close`
  slot for **NSE** and **SONA**, both `bidding closed — awaiting listing`.
- **2026-09-23** is the first genuine **T−1** candidate: **VARMORA** closes 24 Sep (the 22 Sep brief
  said "closes in 2 days"), so the expensive research slot should fire that evening.

Check `GET /scheduler/status` for the `ipo_deep_dive` last-run outcome, or whether
`data/ipo/ipo_verdicts.jsonl` now exists on the volume. Until a row exists, `IPO-5a` would be surfacing
code written against an imagined row.

### IPO-0a — criterion 1 is MET; one piece of evidence remains

The user supplied the **22 Sep 08:50 IST production brief**. It satisfies the live-observation half in
full — this is the subject the milestone had never had:

| Issue | Heading rendered | Subscription rendered |
|---|---|---|
| NSE | `bidding closed — awaiting listing` | 3.78261× overall (QIB 1.52996×, retail 0.722428×, 39% at cut-off) |
| SONA | `bidding closed — awaiting listing` | 1.45233× overall (QIB 0.459178×, retail 1.28955×, 58% at cut-off) |
| VARMORA | `closes in 2 days` (open) | `data pending` — correct; it opened that morning |

Real × values, not `data pending`, under correct state headings. **Still needed:** the ledger half —
either no `ipo_signals_accruing` `pending` alert since NSE/SONA opened on the 17th (Inbox or
`GET /delivery/alerts`), or a volume read. ⚠ `railway ssh` is NOT available: this machine has no Node,
so the CLI's npm install route is closed too (a standalone binary from Railway's releases would work).
Do not delete the milestone entry on the brief alone.

### ⚠ Open question raised by that brief — worth one look before IPO-5b

Both closed issues rendered **"(NSE only)"**. Per `services/data/fetchers/ipo.py`, `total_x_nse_only`
clears only when the all-exchange **combined** ladder is fetched, and `_enrich_open_issues` fetches a
live ladder only while `issue_state == "open"` — a closed issue inherits via `_carry_forward`. So the
final book recorded in production for NSE and SONA looks like the **NSE-only under-report**.

Against the 21 Sep 14:15 IST scratch fetch in the plan's IPO-0a note (total 3.817×, **QIB 7.81×, retail
1.10×, 14% at cut-off**) the totals are close and the categories are not. Combined-vs-NSE-only would
explain it; so would something wrong. **This is unresolved and was not investigated** — it needs
production data this machine cannot reach.

**Why it matters:** P3's `demand` is computed from exactly those category figures (`qib_x`, `retail_x`,
`cutoff_share`), and `IPO-1` fitted its thresholds on the spine's combined subscription. If production's
final book is habitually NSE-only, `demand` is being computed on a different quantity than it was fitted
on — which would undercut the forward hit-rate `IPO-5b`'s gate depends on. Resolve before `IPO-5b`.

### Also outstanding, user-side

- `IPO-0c` still waits on the production Serper counter (`cat data/logs/api_usage.json`, or the boot log
  `[api_usage] counter intact at boot ... serper=N/2500`). `fetch_gmp()` also has no production caller.
- `docs/StockAgent-Three-Loops.pdf` is stale and cannot be rebuilt here — no Node, no Chromium cache,
  although `node_modules/playwright` is vendored. Install Node LTS, then
  `npx playwright install chromium` and `python scripts/docs/build_kt_pdf.py`. It is the only
  `check_kt_docs.py` error; 24 job IDs, 221 local links and 13 configuration claims are green.

**IPO-4c is done** (2026-09-22): the audit lane. `Lane` gains `"ipo"`; `core/ipo/listing.py` resolves the
listing date and issue price (P1 spine first, NSE cache second); `grade_ipo_lane` in
`core/audit/outcomes.py` grades the newest stored verdict per issue at 1/5/21/63/126/252 trading days
from listing, with `entry_close` = the **issue price**, documented at the schema field rather than left
to be inferred. Three design points the plan's outline did not reach, all now in its step detail:
`is_correct` was **not** taught an IPO word — `core/audit/rules.py` gains `is_ipo_correct` beside
`is_switch_correct`, on the precedent that a different question gets its own answer; **only one row per
issue can carry True/False** (the listing-day horizon, of a post-close verdict, whose lean asserts a
direction), every other horizon carrying the return and no claim; and an issue with no tape yet counts as
`awaiting_listing`, deliberately **not** `skipped_unpriceable`, because the nightly job feeds that
counter to `alert_job_partial_output`. IPO rows are excluded from the rendered audit report and reach no
surface. 37 offline tests; full suite **3126 passed, 5 skipped**. `TEAM_TESTING_GUIDE.md` gained case
**05-G** (12 duties, **59** cases, all still NOT RUN).

⚠ **`IPO-4c` has had implementation and same-conversation self-review only — no fresh-session review.**
That matches how `IPO-3*`/`IPO-4a`/`IPO-4b` were closed under this plan's own "commit per task"
discipline, and it is not the `REVIEW.md` gate. If a fresh review is wanted, the three highest-value
targets are: the horizon off-by-one (horizon 1 must be the listing day, not the day after); the
scoreability rule (nothing outside an evidenced, directional, listing-day row may carry True/False); and
containment (no IPO row may move a number in `build_report`). All three have tests; the question a
reviewer should ask is whether the tests can pass while the property is false.

⚠ **No production IPO row has been graded and none can be yet**, for three reasons that are not code:
the `ipo_deep_dive` job reaches production only on deploy; `data/ipo/ipo_verdicts.jsonl` does not exist
there until it does; and grading additionally needs the issue in the P1 spine, which
`scripts/ipo_backfill.py` rebuilds **manually** from the bhavcopy volume. Until an issue reaches the
spine the NSE cache is the only resolver, and NSE drops issues from `past` after a few months — so a
252-td horizon on an issue that never reached the spine sits in `awaiting_listing` for good. That is a
visible counter in the lane summary, not a silent loss. Wiring the spine to a job is unclaimed work; it
is not in this plan.

**IPO-4b is done** (2026-09-22): `core/ipo/narrate.py` + `core/config/prompts/shared/ipo_narrate.py`.
The note is the `IPO-5a` explainer content, stored on the verdict row and reaching **no surface**.
What the plan put in the prompt, the build put in the code path: the verdict is never passed to the
narrator at all; every number in the prose must appear in the structured findings (rounding yes,
arithmetic no); an advice/verdict vocabulary rejects the note; and a rejected or failed note falls back
to a deterministic template from the same facts. The model is handed source COUNTS, never URLs — the
"Sources:" line and the "research view — not advice" framing are appended in code on both routes.
Cost shape: a note is bought only for a row that will actually be stored, and reused while the facts
digest holds, so an issue costs at most two model calls — T−1 and the close (the note states which).
⚠ This nuances `IPO-4a`'s "post-close costs nothing": that remains true for network and extraction; the
narration adds exactly one call at the close. 45 offline tests.

**IPO-4a is done** (2026-09-22): `core/ipo/deep_dive.py` + the `ipo_deep_dive` job at 19:00 IST.
The design point that was not in the plan's table: the visibility gate counts only `short.evidenced`
rows, which exist only after the book closes, so the sweep has **two slots** — the T−1 research run and
a post-close re-read off the cached dossier + cached extraction (zero network). A verdict with every index
dark is not stored (the capture ledger's "a row asserts a reading was taken"). 32 offline tests. ⚠ The
job reaches prod only on deploy; until then `data/ipo/ipo_verdicts.jsonl` does not exist in production.
The first real T−1 candidate after deploy is whichever mainboard issue closes the day after.
⚠ `docs/StockAgent-Three-Loops.pdf` is stale (was already stale at `5f7238c`; §8/§9 of the KT changed at
`IPO-4a`, §8 again at `IPO-4b`, and §7 + §8 again at `IPO-4c`). No Node/Chromium on this machine —
rebuild with `python scripts/docs/build_kt_pdf.py` where there is. It is the only `check_kt_docs.py`
error; 24 job IDs, 221 local links and 13 configuration claims are green.

**IPO-0a status (2026-09-21 afternoon):** worked, not closeable that day — nothing was in the
`closed — awaiting listing` state until NSE and SONA closed that night. Read the "Progress 2026-09-21"
note under IPO-0a in the plan; it names the two pieces of production evidence the 22 Sep 08:50 brief
provides. Do not delete the milestone entry without both.

**IPO-0b is done** (size-tiered demand lean; see the plan's "Done 2026-09-21" note).

**IPO-1 is done** (2026-09-21 evening): the per-horizon read is in the plan under IPO-1 with the decision — fit the SHORT (post-close listing-day) horizon to QIB/total demand, LONG stays dark, OFS never scored. `ipo_p1_backtest_review` removed from the registry. Sprints 3–5 may now get step detail.

**IPO-0c is blocked on you:** it needs the production Serper counter (`railway ssh` → `cat data/logs/api_usage.json`, or the boot log line `[api_usage] counter intact at boot ... serper=N/2500`). Also found: `fetch_gmp()` has no production caller, so provisioning the key would need a wiring change too — see the plan's IPO-0c progress note.

**Sprint 2 is done** (2026-09-21 evening, `e8abda3` + `c8e54c2`): `core/ipo/research.py` (Tavily dossier, cached per issue) and `core/ipo/extract.py` (per-document extraction, corroboration gate). 60 offline tests over three real captures. Not yet wired to any job — that is `IPO-4a`.

**Sprint 3 is DONE** (`4c26072`, `c60f602`, and `IPO-3c`/`3d`/`3e` on 2026-09-22): `hype.py` (fitted `demand` + unfitted `froth`), `substance.py` (S, never fitted), `verdict.py` (the §3 grid, SHORT from `demand`, LONG hard-wired dark) and `verdicts.py` (the append-only store). The model runs end to end on the recorded dossiers and reaches no job and no surface.

**`ipo_verdicts_visible_gate` is now in `config/milestones.yaml`**, deadline 2026-12-31 or 60 days of forward P2 rows, whichever comes first. It is the gate P3 has to pass before any verdict is shown. ⚠ A milestone reaches prod only on deploy — the `registry_is_current` invariant watches for that.

**Sprint 4 is complete.** `IPO-4a` (the `ipo_deep_dive` job at 19:00 IST) wired Sprints 2–3 to the clock,
`IPO-4b` (the narrator) gave the row its prose, and `IPO-4c` (the audit lane) gave it forward grading.
The model now runs, writes, narrates and will be measured — and still reaches no user.

Still open from Sprint 0: `IPO-0a` closes on the 22 Sep brief; `IPO-0c` still waits on the production Serper counter (see below).

Read that plan's "State of play as of 2026-09-21" section first. Sprints 0–4 are
executable and built; Sprint 5 carries acceptance criteria and a gate column but
no step detail yet.

The Three Loops PI below is **paused, not abandoned** — DOC-001 still awaits its
fresh-session review and all 32 `SA-` stories remain `todo`. `STATE.json` was
deliberately not touched by any IPO task: it describes PI-2026-09, which has zero
IPO scope, and writing an IPO `active_task` into it would misrepresent that PI.

## Resolved since September 19 — the email outage

The September 19 investigation below is superseded on its central question.

- **Cause:** Railway disables outbound SMTP on Free/Trial/Hobby. Production
  logged `[Errno 101] Network is unreachable` on every send since 2026-07-16
  (n=103 over 21 days — card **D6**, spec `2026-08-24-three-loops-pi-design.md` §15.4).
- **Fix:** upgraded to Pro **and redeployed**. The upgrade alone changes nothing
  for an already-running container; the 25-day-old deployment was still under the
  Hobby network policy. Verified 2026-09-21 — a triggered brief reached the inbox.
- **D6 is closeable** after a day of clean logs.
- ⚠ The [September 19 audit](../../audit/2026-09-19-delivery-deployment-review.md)
  advances a Gmail-credential hypothesis that production evidence **disproved**.
  Its §1 and §3 are wrong on cause. Treat it as a record of what was believed on
  the 19th, not as current diagnosis.

### Shipped in `590bc9f` (on `origin/main`, deployed)

- `outbox.last_error`, written on retry and dead-letter, cleared on recovery —
  a failed send now explains itself without container logs. Partially satisfies **SA-006**.
- An HTTPS Resend transport beside SMTP; `EMAIL_TRANSPORT=auto` picks it only
  when `RESEND_API_KEY` is set, so current behaviour is unchanged on Pro+SMTP.
- Per-account recipients via `resolve_recipient()`. ⚠ **Known gap:** a transient
  `users.db` lookup failure falls back to `DELIVERY_EMAIL_TO`, which in multi-user
  beta could route a tester's brief to the owner's inbox. Tighten before beta.
- Tests: 2832 passed, 5 skipped (full `tests/unit`).

## Operational investigation requested September 19

The user temporarily resequenced a read-only review of missing scheduled emails
and Railway deployment state. See the [dated findings](../../audit/2026-09-19-delivery-deployment-review.md).
Public HTTP and remote Git checks are current; private production logs/configuration
could not be refreshed because this machine has no Railway CLI/login/token.
September 10 delivery counts remain historical. Current service inventory, source
branch, scheduler activity and SMTP connectivity still need authenticated inspection.
No application, deployment, variable, job or notification was changed. This is
an operational investigation, not DOC-001 acceptance or SA-006 implementation.
The PI state and unresolved dependencies below are preserved.

## PI handoff retained from September 15

**DOC-001 implementation is complete; fresh-session review is required.**
No remediation code was changed or accepted. All 29 planned SA stories and
three stretch stories remain `todo`.

Next task: [DOC-001](stories/DOC-001.md). Next phase: **fresh-session review**
under [REVIEW.md](REVIEW.md). Read the [implementation receipt](evidence/DOC-001-implementation.md),
verify the [manifest](evidence/DOC-001-manifest.json) and inspect the worktree.
Review-input SHA-256: `90c005c46417db97d6e3f6feba2431aae66a8ad93037e852e9823ad7936125c0`.
Do not sign off this phase using its same-conversation self-review.

## Scope and deliverables

The user explicitly resequenced two tasks ahead of SA-001:

1. Current-code KT Markdown/PDF including all PI targets, clearly separate
   from implemented and production-verified behavior.
2. A separate human testing guide: assignable duties, practical cases,
   expected results and evidence; no code-intensive review or named assignment.

The updated entry points are [Technical KT](../../TECHNICAL_DESIGN.md),
[generated PDF](../../StockAgent-Three-Loops.pdf),
[architecture](../../ARCHITECTURE.md) and
[team testing guide](../../TEAM_TESTING_GUIDE.md).
The guide has 12 duties and 60 cases (05-F added at `IPO-4b`, 05-G at `IPO-4c`, 10-E at the 2026-09-23 DOC-001 remediation), all NOT RUN.

Every future implementation updates its affected living docs/test cases and
regenerates the PDF when its source changes. SA-031 now means the final
consistency check; SA-024/SA-027/SA-029 remain unresolved dependencies. After
DOC-001 acceptance, select SA-001 as the first remediation story, but do not
start it in that review conversation. *(Superseded 2026-09-23: SA-039 now comes first.)*

## Verification and limitations

- HEAD and September 15 Railway deployment metadata match
  `9a805878ed19c0cda7833d5b897ac05ee407436d`; deployment status SUCCESS.
  Only deployment context was refreshed. The [September 10 audit](../../audit/2026-09-10-repository-production-review.md)
  remains the detailed dated production evidence.
- 323 existing tests passed across 30 files, Python 3.13.11 on Windows,
  in an isolated source copy with dotenv disabled and external transports
  blocked. TestClient and a Windows asyncio local socket pair are allowed.
  No full-suite or Linux/Python-3.11 parity claim.
- 16-page PDF: searchable, source-hash matched, rendered and visually checked.
  All 32 SA targets/dependencies/titles, 23 possible scheduler IDs (24 since `IPO-4a`), 13 config
  assertions and local documentation links checked. Receipt has exact results.
- Known grading, timing, health, weight-bound, delivery and recovery gaps
  remain. Neither tests describing existing behavior nor this KT establishes
  learning benefit. Human acceptance and future market evidence remain pending.

## Preserve and continue safely

- Pre-existing user audit banners/provenance were retained. The original PDF
  is preserved byte-for-byte in [the archive](../../archive/README.md); the user
  explicitly requested updating its primary path.
- No application source/configuration change, deployment, production job,
  backfill, notification, commit or push was performed.
- Do not read/expose `.env` or private raw logs. Raw local diagnostics are
  ignored under `analysis_data/kt_20260915/`; audit history under
  `analysis_data/audit_20260910/` may be absent elsewhere.
- Preserve other unrelated worktree changes. Manifest covers the intended
  payload; inspect STATE, HANDOFF and receipt bookkeeping separately.
