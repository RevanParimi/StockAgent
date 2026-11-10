# PR-001 — implementation receipt

**Story:** [PR-001](../stories/PR-001.md) · **Phase:** implementation, with same-conversation
self-review only · **Date:** 2026-10-13 about 22:38 IST to 2026-10-14 about 01:00 IST ·
**Baseline:** `4c85eec` plus the accepted, uncommitted FIX-009 work (its code, tests and docs),
the FIX-008 push note in STATE and HANDOFF, and the owner's `docs/README.md` probe line; none of
those is PR-001's · **Status after this phase:** `review_required`

**The fresh review requested changes (14 Oct). Rework 1 (15 Oct) is the next section; the first
implementation's record follows it.**

## Rework 1 — 15 Oct 2026 (implementation, after the review's `changes_requested`)

**Phase:** implementation (rework 1), a new conversation opened with "continue" on 15 Oct 2026,
from about 10:35 IST to about 14:45 IST. It is not the reviewing conversation. Same-conversation
self-review only. **Status after this phase:** `review_required`; a fresh re-review happens in
another new conversation. The seven listed peer sessions were idle at the start.

- **Input:** the review's input, preserved as
  [PR-001-manifest-review1.json](PR-001-manifest-review1.json) (`a4b459b7…`). `kt_manifest.py
  verify` gave 0 mismatches before any edit. Those 21 files, plus `learn.jsx` from `4c85eec`
  (not in the first input), were snapshotted to the ignored `analysis_data/pr001/rework1/base/`,
  each proved by its blob id (`rw_base_snapshot.py`; `rw_digest.py` re-proves them).
- **Findings addressed:** [the review](PR-001-review.md) M1 and L1 are fixed; the recommended
  L2 and I1 are taken. L3 is the owner's rollout note and needs no code.
- Nothing was committed, pushed, deployed or configured, no production state was read and no
  notification was sent.
- **Superseded statements in the sections below:** "`/ui/learnings` returns `{items}` only, dated
  verdict changes (kind turned-bullish|…|neutral) and forecast misses": the items are now only
  real changes, newest first, then misses (see M1). "25 tests" and "9 browser tests": see Tests
  below. "Learn progress 0" stands; Learn no longer claims any progress.

### In one example (M1)

The test member opens Portfolio on 14 Oct. MARUTI went SELL → BUY on 9 Oct and TATAMOTORS
BUY → SELL on 10 Oct. BOSCHLTD went NEUTRAL → BUY on 13 Oct. Eight other stocks were analysed
twice in July with the same NEUTRAL verdict.

| | Before this rework | Now |
|---|---|---|
| Heading | "Recent verdict changes · **10 changes** in the analysed stocks" | "Recent verdict changes · **3 changes** in the analysed stocks" |
| Cards | MARUTI, TATAMOTORS and eight "M&M: NEUTRAL → NEUTRAL · 2026-07-02"-style cards | BOSCHLTD (13 Oct), TATAMOTORS (10 Oct), MARUTI (9 Oct) |
| BOSCHLTD's change | missing: the list kept the first ten stocks in a fixed order | first |
| A forecast miss | after all of them, counted as a "change" | under "Latest forecast misses", not counted |
| Sixteen real changes | "10 changes" | "The 10 most recent changes in the analysed stocks", the newest ten |

### Changes, by finding

- **M1 (medium): the learnings list counted re-confirmations and dropped newer changes**
  (`services/api/routes/ui_data.py`, `src/frontend/prototypes/portfolio.jsx`).
  - `_verdict_changes(history)`: a change is a run whose verdict differs from the run before it,
    compared trimmed and case-folded. A pair with a missing verdict is skipped: it proves
    nothing.
  - `get_learnings` reads every kept run of each analysed stock
    (`settings.SCORE_HISTORY_MAX_ROWS`, 90), not just the last two, so a change followed by
    same-verdict re-runs still shows, dated by the run that made it. Each change has its own id
    (the row id), so two changes of one stock are two cards.
  - All changes are sorted newest first (run time, then row id), then cut to
    `_LEARNINGS_MAX_CHANGES` (10). The latest forecast misses follow, newest first, cut to
    `_LEARNINGS_MAX_MISSES` (5). The shape stays `{items}`.
  - If the score history cannot be read, the route sends `{"items": []}`, not the stocks read
    before the failure: a partial list would misstate the newest changes.
  - Portfolio: the heading counts only the change cards. "N change(s) in the analysed stocks"
    below the cap, "The 10 most recent changes in the analysed stocks" at it
    (`LEARNINGS_MAX_CHANGES` mirrors the server's cap; a test pins them equal), and "No verdict
    changes in the analysed stocks" when only misses came. Misses are listed after the changes
    under "Latest forecast misses". `demo-fixtures.js` gains one sample miss, so demo mode and the
    layout audit show that heading.
- **L1 (low): Learn showed MARUTI and claims about the member** (`learn.jsx`).
  - "Continue where you left off" is now "Learning paths".
  - The "Recommended next" block is removed with its `RecCard` component. Its reason ("Picked
    because you finished 'Reading a verdict'") was false, one card named MARUTI, and neither card's
    button did anything.
  - The hero shows "0/28 steps" without "· 0%". Nothing records progress, and a percentage on a
    member screen is held to the "every % came from an API" rule.
  - The path drawer's button reads "Start from step 1" at step 0, not "Continue from step 1".
  - The browser suite now visits Learn in both member scenarios.
- **L2 (low, test gap): unformatted figures** (`tests/unit/test_ui_no_invented_figures_pr001.py`).
  Five guard patterns: an index name followed by a level of four or more digits; an ungrouped
  4–6 digit level with decimals; a bare number of four or more digits as an element's text; a
  whole-number move (with `+` or a Unicode minus anywhere, or a hyphen-minus or no sign when a
  word follows); `₹` with three or more digits, or two with paise. The review's four probes and
  eight more each fail the guard; 14 style and copy lines pass it (`translate(-50%)`,
  `top:'-10%'`, keyframes, gradient stops, `calc(100% - 20px)`, "₹4-6Cr/MW", "Nifty 500"). The
  current customer-facing files hold none of the new forms.
- **I1 (info): "0 agents · automobile"** (`agents-page.jsx`). The count line shows only once the
  agents are known, like the counts above it.
- **Also: the broad-except guard.** Moving the per-change record into `_verdict_change_record`
  moved its old silent `except Exception:` (the agent-score parse) out of `get_learnings`, so the
  guard saw one new handler and one stale baseline entry; both fail it. The handler now catches
  `ValueError` (what `json.loads` raises on bad text), and `check_broad_except.py --update`
  removed the stale line `services/api/routes/ui_data.py | get_learnings | #0` from
  `scripts/ci/broad_except_baseline.txt`, the only change to that file (154 grandfathered
  handlers become 153).

### Design decisions (delegated, recorded)

- **D7. No date window.** "Recent" is the newest ten changes, each dated. A window (say 30 days)
  would make the count depend on the server clock and hide true, dated changes when there are
  few; the cap already keeps the list to the newest.
- **D8. Every change is listed,** including several of one stock. A stock that flips BUY →
  NEUTRAL → BUY shows both moves: each is a real change, and the instability is worth seeing.
- **D9. Misses stay in `{items}`,** after the changes, with their own cap, rather than a new key.
  The shape is what the reviewer's trace asserts, and the page tells them apart by `kind`.
- **D10. The full-list heading.** At the cap the page cannot know whether there were more, so it
  says "The 10 most recent changes", which is true either way.
- **D11. No universe-ticker guard.** Input placeholders ("e.g. TVSMOTORS") and teaching copy
  ("Is it cheap vs Tata, M&M, Bajaj?") name tickers legitimately. Learn's ticker is caught by the
  browser suite, which now visits Learn with every API down.

### Tests

- **`tests/unit/test_ui_no_invented_figures_pr001.py`: 44 tests (was 25).** Seven new
  learnings tests. Each derives its expected list from the fixture's own (stock, time, verdict)
  table, not from the code:
  - the review's probe: three changes, BOSCHLTD first, no unchanged pair (BOSCHLTD is the
    fourteenth stock in the universe);
  - one change in each of the 16 stocks, the newest in the last: the cap keeps the newest ten
    and drops the six oldest;
  - a change followed by two same-verdict re-runs, and a stock that flips three times: four
    cards, dated by their runs, each with its own id;
  - a missing verdict and a case or space difference are not changes;
  - 12 changes and 7 misses: ten changes, then five misses newest first;
  - a read failure on the sixth stock: nothing, not a partial list;
  - the page's cap equals the server's.

  Plus 12 new probes for the guard and 14 new style lines it must pass.
- **`tests/frontend/no_invented_figures.test.mjs`: 10 tests (was 9).** Learn joins the member
  views of the APIs-down and APIs-up tests (no ticker, company, percentage, "you finished",
  "left off", "Recommended next"; "Learning paths" shown); the APIs-down test also checks that
  the Agents page shows no agent count. A new test answers `/ui/learnings` four ways (three
  changes and two misses; ten changes; one; misses only). The heading's number must equal the
  change cards above "Latest forecast misses", no miss may sit among the changes, and a full list
  must say "The 10 most recent changes".
- **On the review-1 code** (`rw_swap_plugin.py`, `RW1_SWAP=base`, blob-checked): 7 of the 43
  tests that run without the browser fail: the six new learnings tests and the cap check. The
  browser suite on the review-1 screens (`rw_fe_mutants.py base`): 3 of 10 fail (APIs down:
  Learn's MARUTI; APIs up: Learn's "0%"; the heading test).
- **Mutants, each caught.** Server R1–R14 (`rw_swap_plugin.py`, `run_swaps.sh`;
  `swap_results.txt`): an unchanged re-run counted; a raw comparison; a missing verdict counted;
  cap before sorting; oldest first; only the newest pair; the old 3-run lookback; misses first;
  misses sharing the ten slots; misses unsorted; a partial list after a failed read; dated by the
  run before; one id per stock and kind; a cap of 9. R13 first survived (the flip fixture made
  two different kinds); the fixture now flips back to the same kind. Frontend G1–G8
  (`rw_fe_mutants.py`; `fe_results.txt`): the heading counts misses; no full-list wording; misses
  mixed in without a heading; "Continue where you left off" back; the percentage back; "0
  agents"; a ticker in Learn's copy; "No verdict changes" at one change.
- **The reviewer's trace** (`analysis_data/pr001/review/test_rv_trace.py`, unchanged; real
  `server.app` under uvicorn, real sign-in, Chromium): 7 passed (2 min 10 s). Its M1 probe now
  records 3 items, 3 real changes, "BOSCHLTD: NEUTRAL → BUY · 2026-10-13" first, the page line
  "3 changes in the analysed stocks", no unchanged pair, and BOSCHLTD's change in the API and on
  the page. With every API down its own regexes find nothing on any screen, Learn included
  (`member_down_hits.json` is `{}`). The stale-cache observation is unchanged (review L3).
- **Elsewhere:**
  - focused run (story file with the browser wrapper, chat-Markdown boundary, auth lockdown,
    `require_owner`): 70 passed (3 min 9 s);
  - `npm run test:frontend`: 27 of 27 (chat 14, Logs 3, PR-001 10);
  - layout audit in fixture mode (`audit_server.py` in a scratch folder with a copy of
    `data/predictions`): exit 0, no overflow across 10 screens and 10 inner tabs at 4 widths,
    both behaviour guards pass. The Portfolio shot shows "3 changes in the analysed stocks", three
    cards, then "Latest forecast misses" with the sample miss;
  - `check_kt_docs`: errors `[]`; broad-except guard: OK (153 grandfathered);
  - full suite **4552 passed, 12 skipped, 0 failed** (10 min 6 s, 14:29–14:40 IST; 4,564 collected, the review's 4,545 plus 19 new); runtime data under `data/`, `logs/`, `outputs/`, `config/` unchanged (801 files, `e715a34c…`, the review's fingerprint).
- **Interruptions, recorded.** The first focused run was cut by the machine sleeping from 11:44
  to 14:12 IST (Windows Kernel-Power events 42 and 107): the browser wrapper's 15-minute wall-clock
  timeout ran out across the sleep. The rerun above passed. The layout audit's first attempt
  stopped on RL Monitor's "Predictions vs actual" tab because the scratch folder had no
  predictions; with the copy it passed.

### Documentation

- KT section 10 (and the PDF): the learnings contract as current design, with the example
  above, and Learn claiming no progress. PDF rebuilt; its source digest `cd034e1e…` equals the
  KT's SHA-256.
- CODEBASE `/ui/learnings` row; UI_SPEC (`PORTFOLIO_LEARNINGS.items`, `LEARN_PATHS`, the Learn
  layout without "Recommended next" and `RecCard`, `LearningsSection`, line references);
  guide 11-J (count the cards, misses under their own heading, Learn); PRODUCT_MAP's
  `ui_data.py` line count.

### Manifest and digest

- **Review input:** [PR-001-manifest.json](PR-001-manifest.json), `1c7ea9458356d4940cc5ee4c936be7ad457e16e4c6c82e1f33d25c2f42eb06e3`, 23 files (the 21
  before plus `learn.jsx` and `scripts/ci/broad_except_baseline.txt`).
- **Rework diff:** `0d8c3604a4205978780c13999cccce72c5b15dafc833251a2353c2c83fa3a27b` (56,667 bytes, 13 paths), from `rework1/base/` to the working
  tree, PDF excluded (`analysis_data/pr001/rework1/rw_digest.py`, writes `rework.diff`). The two
  added paths' bases are `4c85eec`'s bytes, proved by blob id.
- **Cumulative diff:** `973ee2d5ee000f1e03b1c989e8ca2ab4112894bac34b5439557e9b3d2f2c2904` (271,308 bytes, 22 paths): the implementer's recipe
  (`analysis_data/pr001/diff_digest.py`: base `analysis_data/pr001/base`, each file checked
  against `4c85eec` or FIX-009's manifest) plus the two added paths against `4c85eec`. Same
  script, writes `cumulative.diff`.

### Self-review

No critical, high or medium finding.

- **I5 (info, pre-existing).** A card's date is `run_at`'s first ten characters, the UTC date, as
  in every other `/ui` route and the chat context. It differs from the IST date only for a run
  between 00:00 and 05:30 IST; scheduled analyses run in IST daytime (16:30 review, 09:00 on the
  1st). Not changed here, to keep one convention; SA-024 if wanted.
- **I6 (info, pre-existing).** `agentSnapshot` is always empty: `get_history` does not select
  `agent_scores`, and the stored values are per-agent objects that the snapshot code would not
  sort. The card shows nothing for an empty snapshot. Carried over, except that its silent
  `except Exception` is narrowed to `ValueError` ("Also" under Changes); PR-007 (explanations) owns what
  a card says about agents.
- **I7 (info, rollout).** On the first open after the deploy, a device still running the old
  cached `portfolio.jsx` counts any misses into "N changes" once, as before; the server already
  sends only real changes. The review's L3 note covers it: close and reopen.

### Next

A fresh re-review in a new conversation ("continue"). Then PR-002. The owner's FIX-008 deploy
confirmation and rollout checks are unchanged.

## First implementation (13–14 Oct)

## How this phase came about

A new conversation opened with "continue". FIX-009 was accepted, and STATE's `next_task` was
PR-001, the first planned `todo` story whose dependencies are `done` (it has none). No production
state was read, nothing was committed, pushed or deployed, no production variable was changed and
no notification was sent. The five peer sessions were idle.

## What changed

**In one example.** A member, Ravi, opens the app at 09:00 IST.

| On screen | Before | After |
|---|---|---|
| Hero greeting | "Good afternoon, Aditi." at any hour | "Good morning, Ravi.": his display name and the IST part of the day, whatever the phone's zone |
| Hero market line | "Auto sector +1.24% today." (fixed text) | "Nifty 50 −0.42% on 12 Oct." from `/ui/bootstrap`'s `NIFTY50`; left out when the fetch failed |
| Index box | "Nifty Auto 22,847" (fixed) over a mock one-month series | the Nifty 50's level, its change over the range and "as of 12 Oct", from `/ui/nifty-ranges`; "Unavailable right now" when it fails |
| Buttons and headings | "Run on MARUTI", "Pick a slice of the auto sector", "Run analysis on MARUTI" | removed |
| This month | eight fixed "How agents are voting" bars when none came; the server put an agent's weight in place of a missing vote | only agents with real scores; no card when there are none |
| `/ui/bootstrap` fails | the sample watchlist, tickers, drivers, suggestions and portfolio | each screen says what is unavailable; no ticker, figure or name appears |
| A price fetch failed / a stock never analysed | ₹0.00 and +0.00%; score 0.50, NEUTRAL | "—"; "Not analysed" |
| Portfolio "Lessons" | "Missed gain +₹18,420" and "Avoided loss +₹6,180" (score change × 10,000), "Realized loss" fixed at 0, "agent agreement 62%", templated lessons, a pattern strip | "Recent verdict changes": dated records such as "MARUTI: SELL → BUY · Score moved +0.41 → now BUY" |
| Operator tools | every member saw Prompt Lab, Analytics, Logs, RL Monitor, agent tuning and the Tweaks panel | only the owner's session; a member sent to an operator screen lands on Home |

**Server** (`services/api/routes/ui_data.py`).

- `/ui/learnings` returns `{items}`: dated verdict changes and forecast misses. Removed:
  `summary` (`missedGain`, `avoidedLoss`, `realizedLoss`, `accuracyVsAgent`, `actionsReviewed`),
  `patterns`, and per item `costValue`, `lesson` and `action`. `cost` is now `detail`. The kinds
  name the verdict move (`turned-bullish`, `turned-bearish`, `bullish`, `bearish`, `neutral`,
  `forecast-miss`). The forecast-miss filter now drops data gaps and outside shocks, as it was
  meant to; it compared against `"MissType.data_gap"`, but `MissType` is a `Literal`, so it never
  matched.
- `/ui/bootstrap` adds `NIFTY50`: the last `^NSEI` close, its change on the close before and that
  close's exchange date, or `null`. It no longer:
  - fills `NIFTY_AUTO_HISTORY` with a random series when the fetch fails (`_fallback_sparkline`
    deleted);
  - pads `drivers` to four with generic sentences;
  - shows an agent's configured weight as its vote;
  - reports a failed sector index as a 0.00% day (`pct` is `null`, and the pulse ignores it);
  - says "Market closed" when there is simply no data ("No recent data");
  - invents a month one-liner ("No analyses this month yet.").
  Chat seeds are questions, not claims.
- `/ui/nifty-ranges` serves the Nifty 50 (it served the Nifty Auto) by calendar span, so "1
  year" covers a year (it covered about 180 trading days), with `value`, `asOf`, `from` and
  `change`; all `null` when the fetch fails (it sent a 0.0 change).
- `/ui/market/summary` follows the same rules (its month one-liner, its Auto change).

**Frontend** (`src/frontend/prototypes`).

- `demo-fixtures.js` (new) holds every sample value and defines them only when
  `window.saDemoMode` (`?demo=1`, set in `index.html`). In demo mode `data.jsx` copies them onto
  `window`, makes no market API call, and `App` shows a "Sample data — the market figures and
  portfolio here are not live" strip.
- `data.jsx` keeps the static catalogues (agent tasks, Learn content), starts every market global
  empty, and records `window.__apiState` (`loading`, `ready`, `failed`, `demo`). A failed request
  never falls back to a sample. Learn progress is 0 (nothing records it).
- `home.jsx`: the hero (signed-in first name, IST greeting, dated Nifty 50 line, a real "Updated
  … IST" badge), `NiftyBox` from `/ui/nifty-ranges`, "unavailable" panes, no fixed vote bars,
  dashes and "Not analysed" in the watchlist and drawers, no MARUTI buttons, neutral search hint,
  initials from the display name, no permanent unread dot. The watchlist follows a bootstrap that
  lands after the pane opens.
- `portfolio.jsx`: "Your portfolio is unavailable right now" with Try again, instead of the mock
  fallback; the learnings section rebuilt as "Recent verdict changes"; `minWidth: 0` on the two
  grid columns (see the audit below).
- `agents-page.jsx`: a member sees the agents read-only: no plug toggles, task toggles, weight
  slider or save badge, and no counts while the agents are unknown. The page reads `/ui/agents`
  itself when bootstrap has not filled `AGENTS`.
- `index.html`: the signed-in account (`saUser`, `saSetUser`, `useSaUser`, `saIsOwner`) from
  `/auth/me` and the login answer. The operator chips, screens and Tweaks panel render only for
  role `owner`; while the role is unknown, none do.
- `auth.jsx`: the name placeholder is "Your name" (it was "Aditi Sharma").
- `sw.js` v9, so devices drop the cached old screens; `demo-fixtures.js` joins the shell.
- `scripts/ui_responsive_audit.mjs` opens the app with `?demo=1` (`--live` to skip).
  `package.json`'s `test:frontend` runs the new browser suite.

## Design decisions (delegated, recorded)

- **D1. One explicit sample switch: `?demo=1`.** The portfolio page already used it, and
  AUTOPILOT_GUIDE documents it. It now covers every screen. Demo mode skips the market API, so
  the audit's screenshots are the same run to run. A second switch (`?fixtures=1`) was
  rejected: two names for one mode. Anyone can open it; it shows samples under the strip. Revisit
  with SA-032's demo-data policy.
- **D2. Learnings name the verdict move, not a user action.** "Missed buy", "Good call" and
  "Avoided loss" claimed things no trade record supports; the Mistakes/Wins filter went with
  them. The section stays, shown only when the API sent items, and says nothing false.
- **D3. The same rule applied to stand-ins outside the card's table**, each small: the random
  sparkline, padded drivers, weights as votes, the 0.00% sector and ₹0.00 price, the default
  0.50/NEUTRAL, the invented month one-liner, "Market closed", chat seeds that state verdicts,
  Learn progress, the unread dot, the placeholder name, the 1-year span and the never-matching
  forecast-miss filter. The card's intent is "every number a user sees is real, dated, or
  plainly marked unavailable".
- **D4. Operator gating fails closed.** No owner tools until `/auth/me` says `owner`; a member
  sent to an operator screen gets Home; the Agents page stays for members, read-only (the card
  hides its tuning controls, not the page). Server guards are unchanged.
- **D5. The account helpers live in `index.html`.** Navigations are network-first, but the
  service worker serves scripts from its cache first, so the first open after a deploy runs the
  new `index.html` with the previous `.jsx` files. Checked (`analysis_data/pr001/
  stale_jsx_check.mjs`): with the helpers in `hooks.jsx` that page was blank (`ReferenceError:
  useSaUser is not defined`); inline, it renders.
- **D6. The audit runs on the samples, and its first run exposed an overflow.** In demo mode the
  Portfolio page was 658 px wide at 360 px, on the base as well: a grid item's `min-width` is
  `auto`, so the holdings table's `minWidth: 640` widened the column. The earlier audit ran on
  live data and never met it. `minWidth: 0` on both columns fixes it; the demo strip moved from a
  fixed pill (it covered the logo at 360 px) into the page flow.

## Invariant tests

**`tests/unit/test_ui_no_invented_figures_pr001.py`, 25 tests.** The real router; a real
`ScoreStore` on a temporary file; a fake `yfinance` module returning dated NSE bars (Asia/Kolkata
index) or raising. Expected values are computed in the test from the fixture series.

- `/ui/learnings` (2): no key shaped like money (`gain|loss|realized|rupee|inr|cost`), no
  `lesson`, `action`, `rate` or summary; no "₹" and none of the old template phrases; kinds and
  "Score moved" deltas from the fixture history; a data gap is not a forecast miss; an empty store
  sends `{"items": []}`.
- `/ui/bootstrap` (3): `NIFTY50` equals the last close, its change on the previous close and that
  close's date; with prices down and no analyses, `MARKET_TODAY` and `MARKET_MONTH` hold no
  number at all, `NIFTY50` is null, no series, no drivers, no votes, sector moves null, and no
  chat seed names a ticker or a verdict; month votes are the analyses' scores (no weight stand-in).
- `/ui/nifty-ranges` (8): each range's points, value, date, start and change from the calendar
  window (1Y has at least 250 trading days); a failed fetch sends no value; an unknown range is
  1M; the pulse ignores unfetched sectors.
- Static guard (12): no customer-facing prototype file (every `.jsx`, `.js` and `.html` except
  `demo-fixtures.js` and the owner-only screens) holds "Aditi", "Run on MARUTI", a decimal
  percentage, a comma-grouped figure, an `_`-separated numeric literal or a market field set to a
  number; one probe per pattern proves it bites; CSS is left alone; the fixture module defines
  nothing without the flag, and loads after it, before the app.
- The browser suite's wrapper (1).

**`tests/frontend/no_invented_figures.test.mjs`, 9 tests,** the real `index.html` in Chromium,
every API answered from the test's own plan (an unplanned path gets 503), no network:

- every market API failing: across Home's four tabs, the chat seeds, Portfolio, Agents, Inbox
  and Settings, the visible text holds no percentage, rupee figure, index level, sample ticker or
  company (read from `demo-fixtures.js` itself) and no "Aditi"; each pane says it is unavailable;
- APIs answering: every percentage, rupee figure and index level on screen is one the API sent,
  formatted independently in the page; the hero's dated line and the box's date; dashes and "Not
  analysed" for a failed price and an unanalysed stock; a null sector renders;
- a bootstrap that lands four seconds after the watchlist opens still fills it; a missing month
  section reads "unavailable", not "Loading";
- the greeting at 09:00, 13:00 and 19:30 IST on browsers set to New York, Los Angeles and Tokyo;
  initials; no name → "Good morning.";
- a member: only "Sign out" in the pill, no RL Monitor tab, no operator entries in the phone
  menu, no Tweaks panel (opened by its host message), no slider, plug button or toggles, and
  Home after a jump to Logs; the owner: all of them;
- an old server's learnings payload (summary, patterns, lesson, `costValue`) shows none of its
  money, rate or advice;
- `?demo=1`: the strip and the fixture figures, and no `/ui/bootstrap`, `/ui/nifty-ranges` or
  `/ui/learnings` call; without it the fixtures are not even defined.

**On the base.**

- The 13 server tests fail on base `ui_data.py` (`PR001_SWAP=base`), 13 of 13.
- The browser suite on the base frontend (`SA_FRONTEND_ROOT=analysis_data/pr001/base_frontend/…`)
  fails 7 of its 8 behaviour tests. The owner-access test passes there, as it should: the base showed
  everything to everyone. Without the null-sector row, the base fails the figures test on its
  own "+1.24%" (`browser_on_base_nonull.txt`).
- The static guard finds 107 hits in the base files (data.jsx 101, home.jsx 5, auth.jsx 1).

**Mutants**, each caught: server M1–M15 (`analysis_data/pr001/mutants.py`, swap plugin
`PR001_SWAP`, `run_swaps.sh`): the rupee field, the summary, a templated lesson, today's date for
the Nifty, the first bar as "previous close", ranges by bar count, a random series, padded
drivers, weight votes, a 0.00% sector, a verdict chat seed, data gaps as misses, "Market closed",
an unguarded pulse, a 0.0 range change. Frontend F1–F16 (`fe_mutants.py`, each on a copy of the
screens): device clock, a silent fallback to the samples, a fixed index box, chips, menu entries,
slider and Tweaks for everyone, a legacy summary rendered, ₹0.00 for a failed price, a member
reaching Logs, RL Monitor for everyone, a fallback name, a fixed portfolio figure, agent counts
while unknown, a watchlist frozen at mount, "Loading" forever. All 16 were run again on the final revision (14 Oct 00:31–00:56 IST, `fe_mutant_results.txt`; the first round, before the self-review edits, is `fe_mutant_results_round1.txt`).

## Commands and environment

Windows 11, `.stockai` Python 3.13, Node 24.21.0, Playwright Chromium; tests hermetic
(`tests/hermetic.py`); `.env` unused.

- `.stockai/Scripts/python.exe -m pytest tests/unit/test_ui_no_invented_figures_pr001.py
  tests/unit/test_chat_markdown_boundary.py tests/unit/test_api_auth_lockdown.py
  tests/unit/test_m0_require_owner.py -q -p no:cacheprovider`: 51 passed.
- `npm run test:frontend`: 26 passed (chat 14, Logs 3, PR-001 9).
- `node scripts/ui_responsive_audit.mjs --base http://127.0.0.1:8011` (fixture mode): no overflow
  across 10 screens and 10 inner tabs at 360, 390, 768 and 1280 px; both behaviour guards pass.
  `--live`: the same. The server was `analysis_data/pr001/audit_server.py`: an API-only worker in
  a scratch folder (its own `users.db` with the audit's dev owner, `seed_fixture_ui.py
  --with-alerts`, a read-only copy of the local `data/predictions` so RL Monitor has tabs), `.env`
  off, non-loopback connections refused, `yfinance` stubbed. The checkout's `data/` was not
  written. The first fixture-mode run exited 2 on RL Monitor's tabs (no RL data in the scratch
  folder) and showed the Portfolio overflow (D6).
- `python scripts/ci/check_broad_except.py`: OK (154 grandfathered).
- Full suite (`python -u -m pytest tests -q -p no:cacheprovider -o console_output_style=count
  -rfE`): **4533 passed, 12 skipped, 0 failed (7 min 50 s, 14 Oct 00:19–00:27 IST)**. An earlier run on the revision before the last self-review edits crossed
  midnight: 4528 passed, 12 skipped, 5 failed, all in `test_question_researcher.py`, from its
  import-time date (routed to SA-031 as I5; the file passes alone, 17 tests).
- Runtime data (`analysis_data/pr001/data_fingerprint.py`, path, size and mtime under `data/`,
  `logs/`, `outputs/`, `config/`): 801 files, `e715a34c…`, before and after.
- KT: `build_kt_pdf.py` (source `ff97abc089b6e4ffaec0602bb3ca796ae7f7016e4abe4afc315552a747fa5c07`,
  398,690 bytes); `check_kt_docs.py` errors `[]`.

## Documentation

- [KT](../../../TECHNICAL_DESIGN.md) section 10: the interface paragraph rewritten as current
  design (real figures or "unavailable", the dated hero line and index box, no stand-ins, the
  learnings contract, demo mode, owner-only operator tools with the server guards as the real
  protection). Section 11: the "Show only what is real" bullet keeps only PR-010. Section 12:
  PR-001 listed with the current design; its roadmap row stays `Open` until the commit. PDF
  rebuilt; the header revision is bumped with the commit. (`demo-fixtures.js` is named, not
  linked, until it exists at the KT's revision.)
- [PRODUCT_MAP](../../../PRODUCT_MAP.md) 14.1–14.3: the module list, the real-figures and
  owner-only rules, the audit's modes, the browser suites; `ui_data.py` line count.
- [CODEBASE](../../../../CODEBASE.md): the prototypes tree note; the `/ui/*` rows for bootstrap,
  nifty-ranges and learnings; the Auth cells of `PUT /ui/agents/weights`, `/ui/agents/tasks` and
  `/ui/categories/{key}/tickers` corrected to "owner or machine key" (they said "None").
- [Testing guide](../../../TEAM_TESTING_GUIDE.md): cases **11-H** (member vs owner tools),
  **11-I** (greeting, dated Nifty 50, dashes, no fixed values) and **11-J** (verdict changes and
  demo mode); HT-11's related PI list.
- [UI_SPEC](../../../../src/frontend/prototypes/UI_SPEC.md): load order, bootstrap flow, demo
  mode, the data table, Home, Agents and Portfolio entries.
- [AUTOPILOT_GUIDE](../../../AUTOPILOT_GUIDE.md) section 11: an unreachable portfolio API reads
  "unavailable"; only `?demo=1` shows samples.
- [TEST_DOCUMENTATION](../../../../tests/TEST_DOCUMENTATION.md): the browser suites.
- [SA-031](../stories/SA-031.md): routed input I5 (bookkeeping, outside the manifest).
- ARCHITECTURE: no change (its frontend line is still accurate).

## Manifest and digest

- **Review input:** [PR-001-manifest.json](PR-001-manifest.json), 21 files. The SHA-256 of
  its LF bytes is **`a4b459b71ca64d6866a8a3639e0c27f683628eaa80182d59f03e046b190d24b1`**, and `kt_manifest.py verify` gives 0 mismatches.
  - Code (11): `ui_data.py`; `index.html`, `data.jsx`, `demo-fixtures.js` (new), `home.jsx`,
    `portfolio.jsx`, `agents-page.jsx`, `auth.jsx`, `sw.js`; `ui_responsive_audit.mjs`,
    `package.json`.
  - Tests (2, new): the Python file and the browser suite.
  - Docs (8): CODEBASE, PRODUCT_MAP, the guide, the KT and its PDF, AUTOPILOT_GUIDE, UI_SPEC,
    TEST_DOCUMENTATION.
  - Excluded: STATE, HANDOFF, this receipt and the SA-031 card's routed block (bookkeeping; the
    card already carried FIX-009's uncommitted review routing); the owner's `docs/README.md`;
    FIX-009's own files.
- **Diff digest:** **`ac0b7e75655d618b953209f314004c61eae197d95c7c786b49d69f08c38a7178`**, 237,159 bytes over 20 paths (every manifest
  path except the PDF), by `analysis_data/pr001/diff_digest.py`:
  - **The base** is `analysis_data/pr001/base/`, checked file by file: CODEBASE, PRODUCT_MAP, the
    guide and the KT must equal the SHA-256 in `FIX-009-manifest.json` (FIX-009's accepted,
    uncommitted bytes); every other modified path must equal `4c85eec`'s blob.
  - Modified paths: `git diff --no-index --no-color base/PATH PATH`, header names rewritten to
    `a/PATH`; new paths: against `/dev/null`; sorted, concatenated.
- **FIX-009's manifest** now mismatches on exactly five files, CODEBASE, PRODUCT_MAP, the guide,
  the KT and the PDF, because PR-001's edits are layered on its accepted bytes. Its code and
  tests are untouched. When the owner commits, the docs commit carries both stories, as earlier
  docs commits did.
- **Base snapshot incident.** Mid-phase I re-ran `base_snapshot.py` by mistake, which copied edited
  code over the snapshot. `restore_base.py` rebuilt it: code from `4c85eec`, docs unchanged,
  every file checked against the first run's SHA-256; the script now refuses to overwrite.

## Self-review

No critical, high or medium finding. The card's hard-review items:

- **Literals that look like market data.** The static guard scans every customer-facing file;
  the browser suite reads the screens' visible text for percentages, rupees, index levels,
  tickers and company names.
- **`window.*` mock reads.** None outside demo mode: the samples are defined only under the flag,
  and every remaining reader handles an empty or null global.
- **Hiding a chip is not the only protection.** `PUT /ui/agents/weights`, `/ui/agents/tasks` and
  `/ui/categories/{key}/tickers` take `require_owner`, as do the prompt, logs and managed-ticker
  writes (unchanged; `test_api_auth_lockdown.py`, `test_m0_require_owner.py`). The read routes
  stay public, as before (SA-032).

Low and infos, most relevant first:

- **L1 (low, transient, rollout).** On a device that already has the app, the first open after
  the deploy runs the cached previous `.jsx` with the new server, once: the old screens (with
  their samples and "Aditi") show, and by code reading, not reproduced, the old Portfolio page
  breaks if `/ui/learnings` has items (it reads `summary`) and the old Home breaks if a sector
  fetch failed (`pct` null). The next open is fully new (service worker v9). Rollout: open the
  app, close it, open it again before checking. The new page itself renders on that first open
  (D5).
- **I1 (info).** `?demo=1` is open to anyone; it shows only samples, under the strip, and the
  Inbox, Settings and operator screens stay live in it. Policy: SA-032.
- **I2 (info).** If `/auth/me` fails on a network error, the owner sees no operator tools until
  the next load (fail closed).
- **I3 (info).** `/ui/learnings` covers the analysed universe (`_ALL_TICKERS`), not the member's
  holdings; the heading says "in the analysed stocks". A personal scorecard is PR-002.
- **I4 (info, out of scope, routed by plan).** Internal words and operator hints on member
  screens ("9 agents running", "verify your API keys in Railway Variables", verdict and agent
  breakdown), the always-green pulse dot, "Mock money" in the empty portfolio, the auto-sector
  Learn course: PR-007 and PR-010. The operator screens' own demo fallbacks: SA-032.
- **I5 (info, routed to SA-031).** The midnight flake in `test_question_researcher.py`.

## Production check (after an owner-authorized deploy, read-only)

Guide cases 11-H, 11-I and 11-J on a phone and a desktop, as the test member and as the owner,
after opening the app twice (L1). Read-only API checks: `GET /ui/learnings` has only `items`;
`GET /ui/bootstrap`'s `NIFTY50.asOf` is the last NSE trading day; `GET /ui/nifty-ranges?range=1Y`
starts about a year back.

Rollback is a revert. This receipt does not authorize deploying, pushing, changing production
variables or sending notifications.

## Next

A fresh-session review in a new conversation ("continue"), by [REVIEW.md](../REVIEW.md). Then
PR-002.
