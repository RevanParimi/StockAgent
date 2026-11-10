# PR-001 — fresh-session reviews

**The re-review of rework 1 (15 Oct) ACCEPTED the reworked revision; it is the next section. The
first review's record (14 Oct, changes requested) follows it.**

## Re-review of rework 1 — 15 Oct 2026 (fresh session)

**Story:** [PR-001](../stories/PR-001.md) · **Phase:** fresh-session re-review of rework 1 (a new
conversation opened with "continue", 15 Oct about 16:20–17:20 IST; it neither implemented nor
reviewed PR-001 before; peers stockagent-main-7f, -e3, -06, -d9, -25, -fb, -f9 and
splitfamilia-a9 idle) · **Verdict: ACCEPTED** for the reviewed revision. The required M1 and L1
and the recommended L2 and I1 are fixed. One medium finding is pre-existing and outside the card
(U1). Production has since confirmed it, and the owner routed it to FIX-010. One low and three
infos are follow-ups.

**Reviewed revision:** the uncommitted working tree on `4c85eec`, pinned by
[`PR-001-manifest.json`](PR-001-manifest.json):
`1c7ea9458356d4940cc5ee4c936be7ad457e16e4c6c82e1f33d25c2f42eb06e3`, 23 files. Rework diff
`0d8c3604a4205978780c13999cccce72c5b15dafc833251a2353c2c83fa3a27b` (56,667 bytes, 13 paths).
Cumulative diff `973ee2d5ee000f1e03b1c989e8ca2ab4112894bac34b5439557e9b3d2f2c2904` (271,308
bytes): the implementer's figure. It was not rebuilt here, because the first review verified
everything outside the rework.

Nothing was committed, pushed or deployed. No production state was read, no production variable
changed and no notification was sent. The re-review changed no reviewed file.

### In one example

Sixteen stocks were analysed every weekday for six weeks, nearly always with the same verdict.
Twelve real changes happened, two of them in TIINDIA.

- **The member's Portfolio page:**
  - "The 10 most recent changes in the analysed stocks";
  - ten cards, newest first: TIINDIA NEUTRAL → STRONG SELL on 9 Oct, down to MRF on 25 Sep,
    with TIINDIA's earlier change on 28 Sep;
  - the two oldest changes (MARUTI, HEROMOTOCO) left out;
  - then "Latest forecast misses": APOLLOTYRE (8 Oct), EICHERMOT (6 Oct).
  - No card repeats a verdict.
- **How it was checked.** The rows went through the real writer, `ScoreStore.save`, with its own
  timestamps and pruning. The real server, with sign-in, served them, and Chromium read the page.
  The expected cards come from the re-reviewer's own oracle, not from the changed code.

**But (U1, pre-existing).** In the current code nothing calls `ScoreStore.save`; its last caller
went on 21 Apr 2026 (`ce1eeb5`). So in production this section can only list changes saved before
then. Home's watchlist can also say "Not analysed" for a stock analysed every day. This was code
inspection; the review read no production state. The owner's read-only probe then measured it:
production's score history holds 0 rows, against 1,082 logged analyses (see "U1 routed").

### Contract checked

- The first review's required changes for rework 1 (in its section below).
- The card's intended result ("the section says nothing rather than something false") and its
  acceptance criteria.
- The rework's documented contract:
  - KT section 10 and the PDF;
  - the CODEBASE `/ui/learnings` row;
  - UI_SPEC: `PORTFOLIO_LEARNINGS.items`, the Learn layout, `LearningsSection`;
  - guide 11-J;
  - PRODUCT_MAP.

The design decisions D7–D11 are sound: no date window, every change listed, misses in `{items}`,
the full-list wording and no universe-ticker guard. The KT once overstates D10's reason (I1).

### Independent checks

**Input and digest.**

- `kt_manifest.py verify PR-001-manifest.json`: 0 mismatches, `1c7ea945…`, before and after
  the re-review.
- The rework diff was rebuilt by the re-reviewer's own
  `analysis_data/pr001/rereview1/rr_digest.py`: `0d8c3604…`, 56,667 bytes, 13 paths.
  - Bases for the 21 review-1 paths: copied from the implementer's snapshot only when each
    SHA-256 equals `PR-001-manifest-review1.json`.
  - Bases for `learn.jsx` and `scripts/ci/broad_except_baseline.txt`: `git show 4c85eec`.
  - The PDF changed and is excluded, as in the recipe.
- Every other worktree change is accounted for:
  - FIX-009's files (its manifest mismatches exactly the five layered docs);
  - the owner's `docs/README.md` line;
  - bookkeeping.

**The re-reviewer's own probe** (`analysis_data/pr001/rereview1/test_rr_probe.py`, 16 tests).
The real writer, `ScoreStore.save`, writes every row. It sets its own `utcnow()` timestamps, with
and without microseconds, and prunes to 90 rows per stock; only the clock is faked. The expected
lists come from the probe's own `oracle()`, written from the contract.

- **Twelve random histories** for all 16 stocks, written in shuffled order, so row ids do not
  follow time. Each has up to 40 runs per stock: mostly re-confirmations, 12% flips, same-second
  runs in different stocks, and spellings that differ only in case or spaces. `/ui/learnings`
  equals the oracle in all twelve.
- **Deep history:** 95 runs of one stock.
  - The change at run 3 is pruned and not listed.
  - The change at run 11, the 85th newest run, is listed and dated by its own run.
- **Misses:** seven model misses in two stocks, plus a data gap. Five misses follow the change,
  newest first; the data gap is left out.
- **Portfolio in Chromium.** The real `services.api.server.app` runs under uvicorn with sign-in on
  and a temp users.db and score store. The first reviewer's generic driver (`rv_browser.mjs`)
  reads the page. The result is the example above: the cards and their order equal the oracle,
  and there are no page errors.
- **Observation:** when one stock's feedback log cannot be read, the misses read before it stay
  and later ones are lost (I2).

**Does it bite?** In-memory swaps of `ui_data.py` (`rr_swap_plugin.py`, `RR_SWAP=…`;
`run_swaps.sh`; `swap_results.txt`):

| Swap | Re-reviewer's probe (14 non-browser) | Implementer's story file (43 non-browser) |
|---|---|---|
| base: the review-1 `ui_data.py`, SHA-256 checked | 14 fail | 7 fail |
| S1: sorted by the card's date only | 9 fail | **0 fail** |
| S2: a same-second tie goes to the older row | 10 fail | **0 fail** |
| S3: only the newest 30 runs read | 1 fails | **0 fail** |
| S4: no trim | 12 fail | 1 fails |
| S5: misses oldest first | 1 fails | 1 fails |
| S6: a pair with a missing verdict counted | **0 fail** | 1 fails |
| S7: dated by the older run | 13 fail | 4 fail |

Each mutation is caught by at least one of the two test sets. S1–S3 pass the story's own tests
(L1). S6 passes the probe only because its random verdicts are never empty.

**The first reviewer's trace, unchanged** (`analysis_data/pr001/review/test_rv_trace.py`: the
real server, real sign-in, Chromium): 7 passed (2 min 34 s).

- Its M1 probe now shows 3 items, all real changes, "BOSCHLTD: NEUTRAL → BUY · 2026-10-13" first.
  The page line reads "3 changes in the analysed stocks", with no unchanged pair.
- With every API down, `member_down_hits.json` is `{}`: no invented figure, ticker, company or
  name on any member screen, Learn included.
- The stale-cache observation is unchanged (the first review's L3).

**Code inspection.**

- `learn.jsx` has no "left off", "Recommended next", `RecCard`, ticker or percentage. The drawer
  reads "Start from step 1" at step 0.
- `agents-page.jsx` shows its count line only when agents exist.
- `portfolio.jsx`:
  - the heading counts `kind !== 'forecast-miss'` items;
  - the misses come under their own heading;
  - `LEARNINGS_MAX_CHANGES` equals the server's `_LEARNINGS_MAX_CHANGES`, pinned by a test.
- The narrowed `except ValueError` covers `json.loads` on bad text. `agent_scores` is never
  selected by `get_history`, so that branch is dead today (the implementer's I6).
- The guard's five new patterns are reasonable. The current files hold none of the new forms (the
  static guard test passes).

### Findings

| ID | Severity | Where | Finding | Disposition |
|---|---|---|---|---|
| U1 | **medium**, pre-existing; outside PR-001's display-only scope | `services/data/stores/score_store.py:99` (`ScoreStore.save`, no caller: a grep of `core/`, `services/`, `src/` and `scripts/` finds only its docstring); removed from `services/scheduler/python/scheduler.py` in `ce1eeb5` (2026-04-21); `docs/AGENTIC_DESIGN.md:98` still says an analysis records "the score history row" | **Nothing writes the score history.** Analyses are logged only in `run_summaries` (`telemetry.db`). Every reader of the score store therefore sees rows from before 21 Apr, or none: `/ui/learnings`, bootstrap and watchlist scores, trending, search, the chat context and chat's cached-analysis tool. In this checkout's local data (stale, not production), `score_history` has 0 rows while `run_summaries` holds 246 analysis runs with a verdict (5 stocks, 25 Aug–27 Sep, 2 verdict changes in 30 days). Consequences, if production's store is empty or old (inference; production not read): (a) Portfolio's "Recent verdict changes" lists only pre-April changes, or nothing; when only forecast misses exist it says "No verdict changes in the analysed stocks", though analyses changed verdicts; (b) Home's watchlist says "Not analysed" for a stock analysed every day, and always for a stock outside the 16 autos (`ui_data.py:1099-1102`); (c) guide 11-J's change cards cannot appear, so PR-001's production check cannot show them. | **Routed to [FIX-010](../stories/FIX-010.md)** by the owner, after the probe below measured production (see "U1 routed"). |
| L1 | low, test gap | `tests/unit/test_ui_no_invented_figures_pr001.py` | Three rules of the change list are not pinned: same-day order across stocks (S1), same-second ties (S2), and the 90-run lookback (S3). All three mutations pass the 43 non-browser tests. The code is correct today; the re-reviewer's probe catches each. | Routed to SA-031, with fixtures |
| I1 | info, docs | `docs/TECHNICAL_DESIGN.md` section 10 | "A full list reads 'The 10 most recent changes', because older ones were left out" is not true when exactly ten exist. D10 says "true either way". | SA-031: "may have been left out" |
| I2 | info | `ui_data.get_learnings`, the feedback-log loop | A failed feedback-log read on one stock keeps the misses read before it and drops the rest. So "Latest forecast misses" can omit a newer miss. Misses are not counted, and the documented all-or-nothing rule covers the score history only. | No action now; revisit with U1's card |
| I3 | info, this review's own side effect | `data/telemetry.db-wal` (0 bytes), `data/telemetry.db-shm` (32 KB) | The probe's local dry run opened the WAL-mode `telemetry.db` read-only, and SQLite created these two side files. The database itself is untouched (mtime 11 Oct). The re-reviewer's delete was blocked by the permission classifier. Every other runtime file is unchanged. | The owner may delete both. The probe now uses `immutable=1` for local runs. |
| — | carried | the implementation receipt's I5–I7 and the first review's L3 | Unchanged: the UTC card date, the always-empty agent snapshot, and the first open after a deploy counting misses once or going blank | As routed before (SA-024, PR-007, rollout note) |

No critical or high finding.

### Read-only probe for the owner (U1)

`analysis_data/pr001/rereview1/score_history_probe.py` prints counts and dates only:

- `score_history` rows, stocks, first and last run, and rows since 22 Apr;
- analysis runs with a verdict in `run_summaries`, with the last-30-day verdict changes;
- this month's automobile feedback-log count.

It opens both databases `mode=ro` and reads no feedback-log content. From Git Bash in the repo:

```
railway ssh "cd /app && echo $(gzip -9c analysis_data/pr001/rereview1/score_history_probe.py | base64 -w0) | base64 -d | python -c 'import sys,zlib;exec(zlib.decompress(sys.stdin.buffer.read(),31))'"
```

### U1 routed (15 Oct, about 18:10 IST, same conversation, planning only)

The owner ran the probe and pasted its output. **Measured production evidence**, read-only, 15 Oct
2026 at 12:38 UTC:

| Measure | Value |
|---|---|
| `score_history` rows | **0** (none ever; no first or last run) |
| Analyses with a verdict in `run_summaries` | 1,082, across 83 stocks, from 26 Aug to 15 Oct 11:16 UTC |
| The last 30 days | 747 analyses of 64 stocks, with **173 verdict changes** |
| Automobile feedback logs this month | 4 |

This turns U1's consequences from inference into fact for production. After PR-001's deploy, Home
will say "Not analysed" for every stock. Before it, Home shows a made-up 0.50 NEUTRAL. Portfolio
lists no verdict change, although 173 happened in 30 days.

The owner chose: "ya add the score-history fix before PR-002". The card is
[FIX-010](../stories/FIX-010.md) (P0, 3 points), placed directly before PR-002. `next_task` is
FIX-010. It covers four things:

- **The write:** every analysis saves its row again, from the orchestrator exit that logs
  `run_summaries`.
- **Who sees which stocks:** screens that list stocks out of the store name only the viewer's
  holdings and watchlist, the managed tickers and shelf ideas. Once the store is written, the
  chat's "current verdicts" context would otherwise name every analysed stock to every account.
- **Watchlist and empty case:** watchlist rows outside the 16 automobile stocks read the store,
  and the empty case is dated.
- **Optional backfill:** a copy from `run_summaries`, run only at the owner's word.

PR-001's acceptance stands: its code and documentation are correct for what the store holds.
Shipping PR-001 before FIX-010 replaces a made-up figure with "Not analysed", which is less
misleading. The owner decides when to commit.

### Commands and environment

Windows 11, `.stockai` Python 3.13, Node with Playwright Chromium, the suite's hermetic boundary
(`tests/hermetic.py`, also through `analysis_data/pr001/rereview1/conftest.py`); `.env` unused.

- `.stockai/Scripts/python.exe scripts/docs/kt_manifest.py verify docs/planning/PI-2026-09/evidence/PR-001-manifest.json`:
  0 mismatches. `analysis_data/pr001/rereview1/rr_digest.py`: `0d8c3604…`, 56,667 bytes.
- `RR_OUT=<scratch> PYTHONPATH=. pytest analysis_data/pr001/rereview1/test_rr_probe.py -p no:cacheprovider --rootdir analysis_data/pr001/rereview1`:
  16 passed (15 API-level in 76 s, then the Chromium test in 32 s).
- `bash analysis_data/pr001/rereview1/run_swaps.sh`: the table above.
- `RV_OUT=<scratch> PYTHONPATH=. pytest analysis_data/pr001/review/test_rv_trace.py -p no:cacheprovider --rootdir analysis_data/pr001/review`:
  7 passed.
- `npm run test:frontend`: 27 of 27 passed (chat 14, Logs 3, PR-001 10).
- `node scripts/ui_responsive_audit.mjs --base http://127.0.0.1:8017`, fixture mode, against
  `analysis_data/pr001/audit_server.py` in a scratch folder holding a copy of `data/predictions`:
  exit 0. No overflow across 10 screens and 10 inner tabs at 4 widths; both behaviour guards
  pass. The Portfolio shot shows three sample changes, then "Latest forecast misses".
- `scripts/docs/check_kt_docs.py`: errors `[]`; the PDF's source digest `cd034e1e…` equals the
  KT's SHA-256 (42 pages).
- `scripts/ci/check_broad_except.py`: OK (153 grandfathered).
- Full suite (`python -u -m pytest tests -q -p no:cacheprovider -o console_output_style=count -rfE`):
  **4552 passed, 12 skipped, 0 failed** (19 min 33 s, 16:33–16:52 IST, slowed by the parallel
  swap runs).
- Runtime data (`analysis_data/pr001/review/rv_fingerprint.py`): 801 files, `e715a34c…` before.
  After: the same 801 files and digest, plus the two side files of I3.

**Not exercised:** production data and the live Yahoo feed, a real phone, a real service-worker
update, and the probe in production.

### Acceptance checklist

| Criterion | Result |
|---|---|
| `/ui/learnings`: no rupee field from a score, no templated lesson | Met (unchanged by the rework; the story file's test passes) |
| With bootstrap failing, no figure, ticker or name not from an API (browser test) | Met on every member screen, **Learn included** (first reviewer's trace: `{}`; implementer's suite visits Learn in both member scenarios) |
| The hero shows the signed-in name; "Ravi" never sees "Aditi" | Met (first reviewer's trace, unchanged) |
| A member sees no operator chip, tuning control or Tweaks; the owner does | Met (first reviewer's trace, unchanged) |
| A guard fails on a hard-coded index value, % move, "Aditi" or "Run on MARUTI" outside the fixture module | Met, now including the unformatted forms (L2 fixed: 12 probes caught, 14 style lines pass) |
| Layout audit passes in fixture mode | Met (re-reviewer's run, exit 0) |
| Review M1: only real changes, newest first, cap after sorting, heading count = the cards, misses apart | Met (re-reviewer's oracle on twelve random histories and a production-like history in Chromium) |
| Docs: KT section 10 + PDF, CODEBASE, UI_SPEC, guide 11-J, PRODUCT_MAP | Present and accurate for the code; one overstated reason (I1). Guide 11-J cannot show change cards in production until U1 is fixed. |

**Decision: accepted.** PR-001 is `done` for the reviewed revision. Production verification is
`pending_deployment`. After an owner-authorized deploy, close and reopen the app once (first
review's L3), then run guide 11-I. Guide 11-J's change cards depend on U1. Commit and push only
at the owner's word. With the commit, KT section 12's PR-001 row (and FIX-009's) goes from `Open`
to `Done`, with the KT header bump and a PDF rebuild. `next_task` was PR-002. The owner then routed
U1 ahead of it, so it is FIX-010 (see "U1 routed").

## First review — 14 Oct 2026 (changes requested)

**Story:** [PR-001](../stories/PR-001.md) · **Phase:** fresh-session review (a new conversation
opened with "continue", 14 Oct about 12:00–13:30 IST; peers stockagent-main-e3, -06, -25, -fb,
-f9 and splitfamilia-a9 idle) · **Verdict: CHANGES REQUESTED** (one medium and one low finding
must be fixed; two lows are recommended in the same rework)

**Reviewed revision:** the uncommitted working tree on `4c85eec`, pinned by review input
[`PR-001-manifest.json`](PR-001-manifest.json), preserved as
[`PR-001-manifest-review1.json`](PR-001-manifest-review1.json):
`a4b459b71ca64d6866a8a3639e0c27f683628eaa80182d59f03e046b190d24b1`, 21 files. Diff
`ac0b7e75655d618b953209f314004c61eae197d95c7c786b49d69f08c38a7178`, 237,159 bytes.

Nothing was committed, pushed or deployed. No production state was read, no production variable
changed and no notification sent. The review changed no reviewed file.

## In one example (M1, the finding that must be fixed)

The test member opens Portfolio on 14 Oct. Two stocks really changed verdict this month: MARUTI
went SELL → BUY on 9 Oct and TATAMOTORS BUY → SELL on 10 Oct. BOSCHLTD went NEUTRAL → BUY
yesterday, 13 Oct. Eight other stocks were analysed twice in July with the same NEUTRAL verdict.

- **What the page says:** "Recent verdict changes · **10 changes** in the analysed stocks".
  It lists MARUTI, TATAMOTORS and eight "M&M: NEUTRAL → NEUTRAL · 2026-07-02"-style cards.
- **What is true:** three changes. Yesterday's BOSCHLTD change is missing: the API never
  sends it.

Reproduced through the real server and Chromium (`test_probe_recent_verdict_changes_on_production_like_history`
in `analysis_data/pr001/review/test_rv_trace.py`; result `probe_verdict_changes.json`).

## Review input and digest

- `kt_manifest.py verify PR-001-manifest.json`: 0 mismatches. All 21 git blob ids recomputed with
  `git hash-object` match the manifest.
- **Diff rebuilt independently** (`analysis_data/pr001/review/rv_digest.py`): `ac0b7e75…`,
  237,159 bytes, 20 paths. Bases:
  - the 13 code, test and doc paths that exist at `4c85eec`: `git show 4c85eec:PATH`;
  - CODEBASE, PRODUCT_MAP, the guide and the KT: the implementer's snapshot copy, accepted only
    because each SHA-256 equals FIX-009's manifest (FIX-009's accepted, uncommitted bytes);
  - three new files against `/dev/null`.
- Every other worktree change belongs to FIX-009 (its manifest now mismatches on exactly the five
  layered docs), the owner's `docs/README.md` line or the bookkeeping files.

## Contract checked

From the card:

- every number a member sees is real, dated or plainly unavailable;
- `/ui/learnings` has no rupee figure derived from a score and no templated lesson;
- "until then the section says nothing rather than something false";
- the hero greets the signed-in name and dates its Nifty 50 line;
- operator tools are for the owner only, with the server guards unchanged.

Also checked against the story's own documented contract: KT section 10, CODEBASE `/ui/*` rows,
guide 11-H to 11-J, UI_SPEC and PRODUCT_MAP 14.

## Independent checks

**Reviewer's own trace through the real server**
(`analysis_data/pr001/review/test_rv_trace.py` + `rv_browser.mjs`, 7 tests).

- **Setup.**
  - `services.api.server.app` runs under uvicorn in a thread, with `AUTH_REQUIRED` on and Atlas
    on.
  - Its `cwd` is a temp folder, with a temp `users.db` (owner "Meera Iyer", member "Ravi Menon")
    and a temp score store.
  - Chromium loads the real `index.html` and screens from that server. No API request is
    intercepted; only the CDN libraries come from `node_modules`.
  - Two boundaries are faked: a `yfinance` module with irregular dated NSE bars (the Energy index
    and most stock prices fail, as can happen in production), and, for one scenario, an ASGI
    wrapper that answers 503 for `/ui/`, `/portfolio`, `/discovery` and `/history`.
  - Expected values are computed in the test from the fixture series.
- **Member, signing in through the real form, device in Los Angeles at 09:00 IST.**
  - The greeting reads "Good morning, Ravi."; the line under it is "Nifty 50 -0.03% on 13 Oct.",
    the fixture's last two closes.
  - The index box shows "24,133.5", its 1-month change and "over 1 month · as of 13 Oct"; 1Y
    shows the 365-day change.
  - Energy shows "—".
  - Every percentage, rupee figure and index level on the four Home tabs is a fixture value.
  - Watchlist, written through the real `PUT /ui/watchlist`:
    - MARUTI shows its fixture price and change;
    - EICHERMOT (analysed, price failed) shows "— —" with its real 0.52 NEUTRAL;
    - BAJAJ-AUTO and HEROMOTOCO show "Not analysed".
  - Portfolio lists MARUTI SELL → BUY and TATAMOTORS BUY → SELL, with no money line.
  - Operator tools: the pill holds only "Sign out", and no operator label appears on any screen.
    A Tweaks activation message opens nothing. The Agents page and an opened agent's drawer have
    no slider and no plug control.
- **Owner, by stored session, at 19:00 IST.**
  - "Good evening, Meera."
  - All four operator chips and the Tweaks panel appear.
  - The drawer has the slider and the plug.
- **Member on a 390 px phone.** The ☰ menu and the bottom bar have no operator entry.
- **Member with every market API down.**
  - Home, chat, Agents, Portfolio, Inbox and Settings show no percentage, rupee figure, index
    level, analysed-universe ticker, company name or "Aditi".
  - Each pane says what is unavailable.
  - **Learn is the exception:** it shows "MARUTI" (L1).
- **Member writes refused by the real server.**
  - `PUT /ui/agents/weights`, `/ui/agents/tasks` and `/ui/categories/auto/tickers`: 403.
  - `PUT /ui/tickers/managed`: 403 or 422.
  - `GET /ui/logs`: 403.
  - No weights file was written.
- **On the true base** (`RV_SWAP=base` = `4c85eec`'s `ui_data.py`, blob-checked; screens from
  `git archive 4c85eec`), five of these tests fail on behaviour:
  - "Good afternoon, Aditi." for both accounts;
  - a member's menu offers Prompt Lab;
  - with the APIs down, Home shows "+1.24%", "2,400" and more;
  - `/ui/learnings` has `summary` and `patterns`.

  The owner test fails there only on the fixed greeting.

**The implementer's tests.**

- Focused run: 51 passed (their 25, chat-Markdown boundary, auth lockdown, require_owner).
- `npm run test:frontend`: 26 of 26 passed (chat 14, Logs 3, PR-001 9).
- Base `ui_data.py` loaded by the reviewer's own swap plugin (`rv_swap_plugin.py`, `RV_SWAP=base`):
  13 of the 13 server tests fail.
- Reviewer mutants X1–X6, each caught:
  - X1: the hero dated by the previous bar;
  - X2: the box's value is the first close;
  - X3: a learning dated by the older run;
  - X4: the Nifty line built from the Nifty Auto;
  - X5: a failed sector back to a flat day;
  - X6: ranges by bar count.

  Results in `impl_tests_vs_swaps.txt`.
- **No test has an unchanged pair or more than ten analysed stocks**, which is why M1 passes them.

**Code inspection.**

- `/auth/me` and the login answer both carry `role` (`user_store._row_to_user`).
- The app cannot leave the sign-in screen without a token, so an `AUTH_REQUIRED=false` passthrough
  never reaches the role check.
- `OPERATOR_SCREENS` routes a member to Home however `screen` is set.
- Every sample global in Home, Portfolio and Agents is read only under `saDemoMode`.
- `/ui/learnings` and `/ui/market/summary` have no other reader.
- The service worker drops its v8 caches on activation.

**Stale-cache check (the receipt's L1).** The first open after the deploy runs the new
`index.html` with the cached old `.jsx` files and the new server. Reproduced: with one sector
fetch failing, the old Home throws `TypeError: Cannot read properties of null (reading 'toFixed')`
and the app unmounts, leaving a blank page (`test_observe_stale_cache_first_open`). The next open
is fully new.

## Findings

| ID | Severity | Where | Finding | Disposition |
|---|---|---|---|---|
| M1 | **medium** (the card's intended result for the learnings section; documented contract) | `services/api/routes/ui_data.py:1311-1383` (`get_learnings`: one item for every stock with two runs, in `_ALL_TICKERS` order, then `items[:10]`; `_kind_from_verdict_change` at 1281 gives an unchanged verdict the kind `bullish`/`bearish`/`neutral`); `src/frontend/prototypes/portfolio.jsx:800-802` ("Recent verdict changes" · "{items.length} changes") | The section the card rebuilt to "say nothing rather than something false" states a false count and drops real changes. Unchanged verdicts are listed and counted as changes. The list is not recent-first, and the cap keeps the first ten tickers in a fixed order, so a newer change in a later ticker never reaches the page. Forecast misses come after all of them, so they rarely reach it either, and they too are counted as "changes". The KT §10 ("returns dated verdict changes and forecast misses only"), the CODEBASE row, UI_SPEC and guide 11-J describe changes only. Production analyses most tracked stocks daily with mostly unchanged verdicts, so the page would mostly list re-confirmations (inference from the code and the schedule; production not read). | **Fix in rework 1** (see below) |
| L1 | low (AC2: no ticker that did not come from an API) | `src/frontend/prototypes/learn.jsx:59` "Continue where you left off", `:76` "Picked because you finished 'Reading a verdict'", `:80-81` "See the 9 agents stream live for MARUTI. 12 seconds, real signals." and a "Run a demo analysis" button with no action | With every market API down, Learn still shows the ticker MARUTI. It also states things about the member that are false: PR-001 correctly set every path's progress to 0, so "you finished 'Reading a verdict'" and "Continue where you left off" (at 0/28 steps) now contradict the page itself. The implementer's browser suite visits every member screen except Learn. | **Fix in rework 1:** reword or remove the "Recommended next" block and the "Continue" heading; add Learn to the browser suite's member views. PR-010 later removes the page. |
| L2 | low (test gap, AC5) | `tests/unit/test_ui_no_invented_figures_pr001.py:310-319` (`GUARDS`) | The guard catches comma-grouped and decimal forms only. These pass it: `Nifty Auto 22847`, `24850.10`, `Auto sector +1% today.`, `₹18420` (probes in `analysis_data/pr001/review/rv_guard_probe.py`). The current files hold none of them (reviewer's own sweep). | **Recommended in rework 1** (patterns for an index name followed by a number, `₹` followed by digits, and a whole-number move in text, keeping the style exclusions); otherwise SA-031 |
| L3 | low (rollout; confirms the receipt's L1 with a reproduction) | `sw.js` and the old cached `home.jsx` | The first open after the deploy can be a **blank page**, not just the old screens, when any sector fetch fails. It happens once per device. | Rollout note for the owner: after the deploy, open the app, and if it is blank or old, close and reopen it before any check. No code change. |
| I1 | info | `src/frontend/prototypes/agents-page.jsx:197` | "0 agents · automobile" while the agents are unavailable: a count about nothing. The receipt says counts are hidden while unknown. | Optional in rework 1; otherwise SA-024 |
| I2 | info, pre-existing | Home "Sectors today", watchlist change column | On a non-trading day these show the last session's move under "today", undated. The hero line and the index box are dated. | SA-024 (honest states) / PR-010 |
| I3 | info, concurs with the receipt's I4 | chat overlay | "9 agents online · live" shows even when every market API is down. | Already routed to PR-007 / PR-010 |

No critical or high finding.

## Required changes for rework 1

1. **M1.** `/ui/learnings` and the Portfolio section must not call anything a change that is not
   one.
   - **Verdict changes:** only records where the newest verdict differs from the previous one.
   - **Forecast misses:** kept under their own label; do not count them as verdict changes.
   - **Order and cap:** newest first by date, cap after sorting.
   - **Heading:** its count equals what it names.
   - **Tests** with independently derived expected values, at least:
     - an unchanged pair is not listed or counted;
     - a change in a ticker after the tenth in `_ALL_TICKERS` order is shown when it is the
       newest;
     - the heading's number equals the change records shown;
     - fixture: the reviewer's probe.
   - **Docs:** align KT §10 (and the PDF), CODEBASE, UI_SPEC and guide 11-J.
2. **L1.** No ticker and no false claim about the member on Learn. Add Learn to the member views
   of `tests/frontend/no_invented_figures.test.mjs`.
3. **Recommended:** L2 (guard patterns plus probes that prove they bite), I1.

Keep the rework bounded to these. Re-run the implementer's suites, the reviewer's trace
(`analysis_data/pr001/review/test_rv_trace.py`, which must pass unchanged except the M1 probe,
which then shows three changes and BOSCHLTD), the layout audit in fixture mode and the full suite.
Write a new manifest. Then a fresh re-review in another conversation.

## Commands and environment

Windows 11, `.stockai` Python 3.13, Node 24.21.0, Playwright Chromium; the suite's hermetic
boundary (`tests/hermetic.py`, also via `analysis_data/pr001/review/conftest.py`); `.env` unused.

- `.stockai/Scripts/python.exe scripts/docs/kt_manifest.py verify docs/planning/PI-2026-09/evidence/PR-001-manifest.json`:
  0 mismatches; `analysis_data/pr001/review/rv_digest.py`: `ac0b7e75…`, 237,159 bytes.
- `pytest tests/unit/test_ui_no_invented_figures_pr001.py tests/unit/test_chat_markdown_boundary.py tests/unit/test_api_auth_lockdown.py tests/unit/test_m0_require_owner.py -q -p no:cacheprovider`:
  51 passed (3 min 16 s).
- `RV_SWAP=base|X1..X6 PYTHONPATH=analysis_data/pr001/review pytest tests/unit/test_ui_no_invented_figures_pr001.py -p rv_swap_plugin -k "not guard and not fixture_module and not browser_suite and not customer_facing"`:
  base 13 failed of 13; X1 1, X2 5, X3 1, X4 1, X5 1, X6 5 failed.
- `RV_OUT=<scratch> pytest analysis_data/pr001/review/test_rv_trace.py -p no:cacheprovider --rootdir analysis_data/pr001/review`:
  7 passed (the stale-cache and M1 tests record observations). On the base (`RV_SWAP=base`,
  `RV_FRONTEND_DIR=<git archive 4c85eec>`): 5 of the 6 behaviour tests fail, on behaviour.
- `npm run test:frontend`: 26 passed.
- `scripts/docs/check_kt_docs.py`: errors `[]`; the PDF's source digest `ff97abc0…` equals the
  KT's SHA-256 (42 pages).
- `scripts/ci/check_broad_except.py`: OK (154 grandfathered).
- `node scripts/ui_responsive_audit.mjs --base http://127.0.0.1:8013` (fixture mode) against
  `analysis_data/pr001/audit_server.py` in a scratch folder: exit 0, no overflow across 10 screens and 10 inner tabs at 4 widths, both behaviour guards pass (13:15-13:21 IST). A first attempt while the full suite ran exited 2 (`window.__auditNav` not yet defined after `networkidle` under load); the rerun on an idle machine passed.
- Full suite (`python -u -m pytest tests -q -p no:cacheprovider -o console_output_style=count -rfE`):
  **4533 passed, 12 skipped, 0 failed** (17 min 34 s, 14 Oct 12:56-13:14 IST, slowed by the reviewer's parallel browser runs).
- Runtime data (`analysis_data/pr001/review/rv_fingerprint.py`: path, size and mtime under
  `data/`, `logs/`, `outputs/`, `config/`): 801 files, `e715a34c…` before and after.

**Not exercised:** a real phone, a real service-worker update (simulated by serving the old `.jsx`
files), production data and the live Yahoo feed.

## Acceptance checklist

| Criterion | Result |
|---|---|
| `/ui/learnings`: no rupee field from a score, no templated lesson | Met. M1 is about the count and selection, not money. |
| With bootstrap failing, no figure, ticker or name not from an API (browser test) | Met on Home, chat, Agents, Portfolio, Inbox and Settings. **Not met on Learn** (L1). |
| The hero shows the signed-in name; "Ravi" never sees "Aditi" | Met (real sign-in; IST greeting on a Los Angeles device) |
| A member sees no operator chip, tuning control or Tweaks; the owner does (browser, both) | Met (real server, desktop and phone) |
| A guard fails on a hard-coded index value, % move, "Aditi" or "Run on MARUTI" outside the fixture module | Met for the formatted forms. Unformatted forms slip through (L2). |
| Layout audit passes in fixture mode | Met (reviewer run, exit 0) |
| Docs: KT §10, PRODUCT_MAP, guide | Present and accurate except the learnings contract (M1) |

**Decision: changes requested.** PR-001 goes back to implementation (rework 1), then a fresh
re-review. Production verification stays `not_started`.
