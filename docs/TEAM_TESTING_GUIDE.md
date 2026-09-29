# StockAgent — Team Human Testing Guide

**Edition:** 2026-09-15 · **Purpose:** distribute functional testing duties

**Execution status:** all cases below are **NOT RUN**; no team acceptance is claimed.

This is separate from the [technical KT document](TECHNICAL_DESIGN.md) and its
[PDF](StockAgent-Three-Loops.pdf). It tells teammates what to check as users and
operators. No model training, prompt engineering, code review or automated-test
writing is required. Modules are independent assignment units; names and team
size can be decided later.

## 1. How the team should work

Engineering provides a test account, a prepared test dataset, known expected
results and access to the relevant screens. Where no screen exists, engineering
provides a sanitized report/export or demonstrates the operation; the tester
does not need to write a query or inspect source code.

Use the test environment for creating holdings, reruns, missing-data scenarios,
notifications and recovery drills. In production, observe existing runs and
records. A button labelled Run, Backfill, Promote, Edit Prompt or Send can
change state, call a paid provider or deliver a real message.

For each case:

1. Record the build/revision, environment, date, test case and fixture ID.
2. Follow the user journey and compare with the provided source records.
3. Record **PASS**, **FAIL**, **BLOCKED** or **NOT RUN**. A missing test account,
   missing report or unavailable scenario is BLOCKED, never PASS.
4. Attach a redacted screenshot/export, expected versus actual result and
   simple reproduction steps. Use synthetic names; remove user identities,
   tokens, balances from real accounts and private chat contents.
5. Retest the failed case and affected downstream case when a fix arrives.

**Important distinction:** some expected results below are intended acceptance
behavior with a known PI gap. They are marked **PI target**. Until the related
fix is accepted, record the observed failure or missing capability; do not
mark the case passed merely because the current defect is already known.

## 2. Assignable duties at a glance

| Duty | Main question | Main place to work | Suggested cadence |
|---|---|---|---|
| HT-01 Scheduled jobs and self-review operations | Did expected work run for the right date and produce complete outputs? | Scheduler status export, daily feedback/digest, watchdog notices | Each release; five consecutive expected sessions for initial operational acceptance |
| HT-02 Research and data quality | Is the right stock analyzed using usable, dated evidence? | Research report, quote/source snapshot, health export | Each release and data-provider change |
| HT-03 Three-loop end-to-end flow | Does one example connect research → learning → portfolio without broken links? | Report, envelope, feedback, advice, transactions, digest | Each cross-module release |
| HT-04 Learning state and evidence | Can we explain what changed and avoid unsupported improvement claims? | RL Monitor, weight/lesson exports, learning evidence report | After learning changes; monthly evidence review |
| HT-05 IPO information and outcomes | Are issue facts, demand and measured outcomes represented honestly? | Brief IPO section, prepared calendar/history/snapshot report | Around issue opening, closing and listing; each IPO change |
| HT-06 Discovery and paper tracking | Are research ideas kept distinct from purchases and live performance? | Discovery shelf, watchlist, paper report | Weekly cycle and discovery changes |
| HT-07 ADD/HOLD/TRIM/EXIT/SWITCH | Do position actions match the scenario and virtual execution rules? | Portfolio advice, reasons and transactions | Each portfolio/risk-rule change |
| HT-08 Profit/loss and balances | Do cash, holdings and profit reconcile? | Portfolio, transactions, performance and digest | Each portfolio release; sampled regular reconciliation |
| HT-09 Prediction/advice marksheets | Are wins/losses, horizons and denominators correct and understandable? | RL rows, weekly/monthly reports, advice auditor export | Weekly/monthly and evaluation changes |
| HT-10 Briefs, alerts and delivery | Did the intended person receive the right information once? | Inbox, email, push and sanitized delivery status | Each channel/template change; sampled scheduled delivery |
| HT-11 User access, chat and screens | Does each user see the appropriate information and truthful states? | Login, portfolio, chat, RL Monitor, mobile/PWA | Each UI/auth release |
| HT-12 Monitoring and recovery | Can the team detect failure and recover actual data? | Watchdog, backup/restore demonstration, cost report | Each operational change; scheduled recovery exercise |

These cadences are proposed human testing practice, not new cron jobs or
automatic application approval gates. Rare monthly/yearly jobs can first be
demonstrated in a controlled test environment; production observation remains
pending until the relevant scheduled window occurs.

## 3. HT-01 — Scheduled jobs and self-review operations

**Duty:** own the question “Did it really run successfully?” Do not assess
whether the investment call was good; HT-09 covers that.

**Inputs:** enabled-job list, IST schedule, expected ticker list, run-result
export and dated output records. These can be supplied by the operations owner.
Current read surface: `GET /scheduler/status`; see KT section 9 for the clock.

| Case | Tester action | Expected result |
|---|---|---|
| 01-A | Compare a normal 16:30 review's expected tickers with feedback records and the resulting digest. | Review date is the previous exchange trading session. In `last_runs.daily_review`, each enabled ticker appears once in `by_ticker` as completed, degraded, data_gated, skipped or failed; the five counts add up to `required`; disabled tickers appear only in `excluded`. `produced` equals the number of tickers with a feedback entry dated the session, and exactly those tickers are completed or degraded. **SA-004 (accepted 2026-09-27, committed as `241c393`, deployed 2026-09-27 as `b3fb00dd`)** repairs misleading success counts. |
| 01-B | Inspect a prepared missing-envelope or provider-failure run. | Missing output is visible: `status` is `partial` (or `failed` when nothing was produced), `missing` names the ticker and reason (for example `skipped: no_envelope`), and the partial- or zero-output alert names it too. A review that raised leaves `pipeline_ok` false. A green overall status does not hide the failed ticker. **SA-002/SA-004.** |
| 01-C | Observe a prepared weekend/holiday case and a configured disabled job. | Documented calendar/gate behavior matches the run record; disabled or legitimately skipped work is not called successful output. |
| 01-D | Compare the monthly job, daily learning review, nightly advice audit and watchdog outputs. | Four different functions have identifiable dates/results. A watchdog notice is not a completed financial review. |
| 01-E | Observe an engineer-run restart/owner-loss scenario in test. | One effective background owner; missing/repeated work is detected and recovery is demonstrated. **PI target: SA-029.** |
| 01-F | Rerun the same session: in an isolated test copy, run the daily-review job twice for one review date (as the day after a weekday holiday does), with one ticker failing on the second run only. | `runs` is 2 and `attempted` is twice `required`; `produced` does not grow. The ticker that failed on the second run stays completed, marked `from_earlier_run`, because its feedback entry from the first run stands. **SA-004 (accepted 2026-09-27, committed as `241c393`, deployed 2026-09-27 as `b3fb00dd`).** |

**Deliverable:** one job-results table: job, scheduled time, actual start/end,
review date, expected/produced/skipped/failed counts, output evidence and result.
Related PI: SA-004, SA-011, SA-029.

## 4. HT-02 — Research and data quality

**Duty:** check the stock, evidence and explanation that a user receives.
Inputs: one native-sector example, one generic-sector example, source-date
snapshots, a fresh case, a stale case and an unresolved-security case.

| Case | Tester action | Expected result |
|---|---|---|
| 02-A | Search the same prepared company by name and symbol. | Same economic security, exchange and business sector. Generic analysis does not relabel the company as automobile. |
| 02-B | Compare report price/date and benchmark with the supplied source snapshot. | Correct symbol, price type, as-of date and sector benchmark; dates are visible. **PI target: SA-010** for benchmark coupling. |
| 02-C | Engineering prepares, in a test environment with `DECISION_GATE_MODE=enforce`, four reports for one stock: its price source returns nothing; only 1 of its dimensions is scored; an unknown symbol; and a normal run. Open each. Then repeat the first with the checked-in `record` mode. | Enforce: the first three read **INSUFFICIENT DATA**, and each report's `decision_gate` says `abstain` with its reasons (the unusable essential sections, "dimensions scored 1/9", and so on) and keeps the verdict it withheld. The normal run keeps its verdict and reads `actionable`. Record: the first report keeps its verdict and still says `abstain`; engineering shows the matching row in `decision_gate.jsonl`. **PI target: SA-003** (accepted 2026-09-27; committed as `167f08b`, production verification pending). The screen does not yet explain the reasons; it shows the verdict text only. |
| 02-D | Inspect a reorganized/delisted/unresolved security example. | No silent substitution with a different company/security; explicit unresolved handling. **PI target: SA-008.** |
| 02-E | Compare a displayed research score and verdict using engineering's field explanation. | Bound composite/category and model narrative score are identified correctly; an unrelated numeric field is not used to recompute the verdict. |
| 02-F | Engineering prepares, in a test environment, one run whose price source returns nothing while news answers, and one normal run, and exports both data-health rows plus one row recorded before the change. | The failed-price run is **not** `ok`: it reads `degraded`, and technicals, fundamentals and peers valuation are named as unusable with a reason each. The normal run reads `ok`. The older row is labelled version 1 with unknown provenance, not presented as verified. If a run's newest listed quarter has no figures yet, its fundamentals read `fallback`, naming that quarter, and are not dated by it. **PI target: SA-002** (accepted 2026-09-26 after a rework; committed as `8413b59`, production verification pending). The decision gate that acts on these statuses is case 02-C. |

**Deliverable:** source-versus-report comparison with screenshots and data dates.
Related PI: SA-002, SA-003, SA-008, SA-010, SA-026, SA-027.

## 5. HT-03 — Three-loop end-to-end flow

**Duty:** follow one example across team boundaries. This catches cases where
individual screens work but the overall product loses or changes a record.

Engineering supplies a prepared ticker, dated forecast and test holding. Use
one successful journey and one missing-data journey. No real-market outcome
needs to be invented and no production job needs to be rerun.

| Case | Tester action | Expected result |
|---|---|---|
| 03-A | Match report → forecast → observed outcome → feedback → next weight/lesson state. | The symbol and dates remain traceable. Revisions are identified and old issue-time facts stay distinguishable. **PI target: SA-013/SA-017.** |
| 03-B | Continue from feedback to position advice, optional virtual transaction and digest. | Advice refers to the intended holding/date. If no transaction occurs, its gate/reason is explainable; advice is not counted as a trade. |
| 03-C | Follow the prepared missing-essential-data case downstream, in a test environment, once with `DECISION_GATE_MODE=enforce` and once with the checked-in `record`. Engineering also supplies a review day whose close is the previous day's bar, and a test holding whose envelope points up. | Enforce: no envelope is built for the stock; the review on the stale close ends `data_gated`, naming the stage and the source run, and the weight file, lessons and feedback log are unchanged; the holding's advice is HOLD with the note `DATA_GATE` (not ADD) and no buy is recorded. A stop-breach EXIT on the same holding still executes. Record: the same journey buys (the defect the gate stops), and every stage says what enforcement would have withheld. **PI target: SA-003** (accepted 2026-09-27; committed as `167f08b`, production verification pending). |
| 03-D | Inspect results after engineering repeats the same prepared processing date. | No duplicate money movement or adaptive effect; the repeated operation is visible. Portfolio and learning deduplication are tested separately. **PI target: SA-015** for adaptive updates. |

**Deliverable:** a single trace sheet with identifiers and timestamps for each
stage, plus the first stage at which any mismatch appears. Related PI:
SA-003, SA-009, SA-013–SA-017. HT-01 checks execution; HT-03 checks continuity.

## 6. HT-04 — Learning state and evidence

**Duty:** determine whether changes are visible and claims are supported,
without reviewing learning algorithms.
Inputs: before/after weight and lesson reports, dated feedback, and a matched
learning-evidence report supplied by engineering.

| Case | Tester action | Expected result |
|---|---|---|
| 04-A | Compare before/after weights with the feedback that caused the update. | Version/date/ticker are identifiable; normalized final weights total approximately 100%, with the supplied allowed bounds respected. **PI target: SA-015.** |
| 04-B | Repeat an identical input in the prepared test scenario. | The same feedback does not increment the adaptive effect again. **PI target: SA-015.** |
| 04-C | Inspect a new lesson and its later status. | Originating evidence is traceable. Proposed, probationary, accepted and retired states are not all called proven improvements. **PI target: SA-023.** |
| 04-D | Open an empty/small-sample learning report. | Insufficient evidence is visible; changing weights or a successful model call is not advertised as demonstrated benefit. **PI target: SA-020–SA-024.** |
| 04-E | Compare adapted and fixed-policy results for engineering's prepared cohort. | Same issue window, stock group, horizon and missing-case policy are stated. A retrospective replay is labelled retrospective. **PI target: SA-018/SA-022.** |
| 04-F | With engineering's prepared store in `observe` learning mode, open RL Monitor → weights for a ticker whose stored weights differ from the defaults, then compare the weight file's version before and after a prepared review. | The page states `observe`; the weights in use are the sector defaults (for example `technical` 0.12 in the generic graph), shown apart from the stored ones. The stored version is unchanged after the review, and a dated observation record shows what the weights would have become. After switching back to `adapt`, the stored weights are in use again, unchanged. **SA-039: accepted 2026-09-25; production runs `observe` since 2026-09-26.** |

**Deliverable:** a state-change/evidence summary. Evaluating statistical methods
remains an engineering/specialist duty; this tester flags missing or misleading
evidence. Related PI: SA-015–SA-018, SA-020–SA-024.

## 7. HT-05 — IPO information and outcomes

**Duty:** check IPO facts, dates and honest treatment of unknown outcomes.
There is no complete dedicated IPO prediction screen in this checkout. Use
the brief's IPO section and engineer-supplied calendar/history/snapshot reports.

| Case | Tester action | Expected result |
|---|---|---|
| 05-A | Compare a prepared issue's name, price, opening/closing/listing dates and subscription with its source snapshot. | Correct issue identity, units and capture date; issue price is not confused with listing close. |
| 05-B | Inspect an old cache after a failed refresh and an unavailable GMP value. | Cached data is distinguishable from fresh data. Unknown premium is not zero or a confident bullish signal. |
| 05-C | Compare two demand snapshots and a repeated unchanged refresh. | Changes match captured facts; duplicate unchanged input is not presented as new demand growth. |
| 05-D | For issue price 100 and listing close 110, inspect the historical return; also inspect an unreached 252-session horizon. | Listing-close return is +10%; the unreached horizon is absent/unavailable, not 0% or a loss. |
| 05-E | Inspect a small subscription bucket and a post-listing shelf candidate. | Sample limits are disclosed. A ranking/oversubscription/GMP figure is not sold as an established allotment or listing-gain prediction. Lock-in heuristic dates require issue-specific confirmation. |
| 05-F | Ask an engineer for a stored IPO research note (the deep dive's narration) and read it beside the structured findings it was written from. | Every figure in the note appears in the findings; the sources line and the “research view — not advice” framing are present. No lean, band, quadrant, index, score or recommendation to apply appears anywhere in the note. Notes are stored only; none reaches a brief or any other surface. |
| 05-G | Ask an engineer for a graded IPO audit row and the stored verdict row it came from. Check the entry price, the horizon dates and which row carries a right/wrong mark. | Entry price is the issue price the subscriber paid, never a market close. Horizon 1 is the listing day itself and each later horizon is that many trading sessions counted from listing. At most one row per issue is marked right or wrong — the listing-day row of a verdict taken after the book closed, whose lean was strong or weak. Every other row shows a return and no verdict. None of these rows appears in the advice marksheet or any user-facing report. |

**Deliverable:** one IPO lifecycle sheet, from opening through observed outcomes,
with unknown/stale fields marked. Prospect P0/P1/P2 features are existing code;
a validated future IPO model is not a completed September story. Related
cross-cutting PI: SA-002, SA-008, SA-024, SA-025.

## 8. HT-06 — Discovery and paper tracking

**Duty:** validate the transition from a research idea to a watchlist entry.
Current read surfaces: discovery shelf and latest-screen reports.

| Case | Tester action | Expected result |
|---|---|---|
| 06-A | Read a normal weekly screen and a prepared degraded-source screen. | Results have a date and explain available evidence; a missing feed is not silently treated as positive evidence. |
| 06-B | Promote a prepared shelf idea in a test account. | Correct symbol reaches that user's watchlist; this alone does not buy a holding. |
| 06-C | Follow a paper-tracked candidate's report. | Paper results are labelled and separate from the user's actual virtual account and production learning state. |
| 06-D | Inspect a stale/dropped/unresolved candidate. | It is not represented as a current actionable idea; the reason and lifecycle are clear. **PI target: SA-008** for unresolved identity. |

**Deliverable:** screen → shelf → watchlist/paper trace. Related PI:
SA-002, SA-003, SA-008, SA-024.

## 9. HT-07 — Portfolio actions

**Duty:** check ADD, HOLD, TRIM, EXIT and SWITCH using prepared holdings.
Engineering supplies expected rule outcomes. The tester compares visible
action, reason, quantity and resulting transaction; no code inspection needed.

| Case | Tester action | Expected result |
|---|---|---|
| 07-A | Open normal HOLD and eligible ADD scenarios. | Expected advice and reasons appear. An ADD blocked by cash/limits does not create an unexplained transaction. |
| 07-B | Open profit-taking TRIM and stop-breach EXIT scenarios, including both conditions together. | Supplied precedence is respected; a stop EXIT is not softened by a profit/holding-age note. |
| 07-C | Inspect SWITCH with an eligible replacement and with none eligible. | Origin and destination are explicit. Cash/eligibility determines execution; a replacement is not invented. |
| 07-D | Disable virtual autopilot for the prepared account, then observe an advisory run. | Advice can exist without an automatic transaction. Research BUY is not treated as proof of a purchase. |
| 07-E | Inspect the repeated-date and insufficient-cash scenarios. | No duplicate trades or negative-cash purchase; skipped execution remains explainable. |
| 07-F | Inspect a SWITCH whose sale proceeds are larger than 10% of the portfolio. | The new position is at most 10% of the portfolio, and its sector stays within the sector cap. The rest stays in cash with a note saying how much was capped and why. **PI target: SA-050** (today a SWITCH buy spends all the proceeds). |
| 07-G | With idle-cash deployment switched on, open a prepared portfolio that is mostly cash, first in a normal regime and then in `MACRO_CRISIS`. | Normal: new positions are bought from qualifying shelf ideas, at most the configured number per day, each within the caps, and each says why. Crisis: no new positions, and the run records "crisis". Whenever cash stays below the target, the reasons are listed. **PI target: SA-049** (owner decision 2026-09-27). |

**Deliverable:** action matrix with advice, actual transaction (or skip reason)
and before/after holdings. Related PI: SA-003, SA-014, SA-024, SA-049, SA-050. HT-08 separately
reconciles money; HT-09 judges later outcome quality.

## 10. HT-08 — Profit/loss and balances

**Duty:** reconcile figures using a calculator and the virtual ledger.
Use this synthetic fixture, with no fees/corporate actions:

| Stage | Cash | Holding value | Realized P/L | Unrealized P/L | Equity |
|---|---:|---:|---:|---:|---:|
| Capital 2,000; buy 10 units at 100; mark 100 | 1,000 | 1,000 | 0 | 0 | 2,000 |
| Mark remaining 10 at 110 | 1,000 | 1,100 | 0 | 100 | 2,100 |
| Sell 4 at 110; remaining 6 marked 110 | 1,440 | 660 | 40 | 60 | 2,100 |

| Case | Tester action | Expected result |
|---|---|---|
| 08-A | Reconcile each fixture stage against transactions and performance. | Cash + holding value = equity. Realized + unrealized P/L = 100 after partial sale. No double-counted sale profit. |
| 08-B | Compare portfolio, digest and performance dates/scopes. | Differences caused by cash inclusion or valuation date are explained. Digest holding value is not mistaken for total equity. |
| 08-C | Inspect missing-price and missing-history fixtures. | Unknown/stale valuation is visible. Current cost-basis fallback must not be mistaken for a verified market quote; flag misleading presentation. |
| 08-D | Inspect an engineer-prepared split/bonus-adjusted holding. | Adjusted quantity/cost and P/L reconcile to the supplied corporate-action result; the mechanical adjustment does not create profit. |
| 08-E | Compare a complete supplied ledger with its performance summary. | History limits/exclusions are disclosed. Current endpoint limits (2,000 transactions/400 history rows) are not mistaken for unlimited lifetime coverage. |
| 08-F | Recompute one round trip's costs and tax by hand from the configured rates. For example, 509 shares bought at 372.88 and sold at 446.65. | Each charge and the total match to the paisa. Realized P/L shows gross and net of costs. The tax estimate is shown separately, and a year that nets to a loss shows no tax. **PI target: SA-048** (today paper P/L charges nothing). |
| 08-G | Open the portfolio screen for a prepared account with two deposits and some closed trades. | "Capital added" (not "Invested"), "In stocks" and "Cash", with shares adding to 100%. A Nifty line shows what the same deposits would be worth in the index. The closed-trade record shows win rate, average win and loss, and expectancy. Every price shows its date. **PI target: SA-051.** |

**Deliverable:** reconciliation sheet listing source date, cash, quantities,
cost, market value, realized/unrealized P/L and any unexplained difference.
Related PI: SA-003, SA-008, SA-024, SA-048, SA-051; a newly found accounting defect needs an
explicit new finding, not an assumed existing PI fix.

## 11. HT-09 — Prediction and advice marksheets

**Duty:** check whether results are counted and described correctly. A losing
call is not itself a software defect; incorrect labeling, missing cases or
misleading claims are defects.

| Case | Tester action | Expected result |
|---|---|---|
| 09-A | Use issue close 100, predicted 110, actual 105. Compare market direction with forecast error. | +5% market movement and −4.55% forecast error remain separate. **Known gap / PI target: SA-012/SA-014.** |
| 09-B | Use stock return +5%, benchmark +8%, then inspect HOLD's advice-audit result. | Excess is −3 percentage points; HOLD is incorrect under the auditor's relative-return contract, despite positive stock return. |
| 09-C | Count engineering's supplied wins, losses, missing prices and unmatured rows, including exited stocks. | Numerator/denominator reconcile; exited names and unfavorable cases are not silently dropped. **PI target: SA-018/SA-019.** |
| 09-D | Compare weekly, fortnightly and monthly periods. | Calendar/trading-session boundaries and eligible groups are stated. Fortnightly means the planned ten-trading-session cohort, not any arbitrary two calendar weeks. **PI target: SA-019.** |
| 09-E | Compare a forecast revised after issuance with its earlier outcome row. | Earlier evaluation uses the frozen original decision; later information cannot improve its past score. **PI target: SA-013/SA-014.** |
| 09-F | Read each headline accuracy/learning claim. | Report identifies its rule, date, horizon and sample size. The weekly heuristic, monthly replay, advice audit and realized account P/L are not presented as one metric. |

**Deliverable:** hand-counted marksheet with source row IDs, rule, horizon,
numerator, denominator and exclusions. Related PI: SA-012–SA-014, SA-017–SA-024.

## 12. HT-10 — Briefs, alerts and delivery

**Duty:** follow content from stored report to the intended recipient.
Use dedicated test recipients and a prepared delivery-failure scenario.

| Case | Tester action | Expected result |
|---|---|---|
| 10-A | Compare the stored brief/digest with inbox/email/push versions. | Same date, symbol, advice and action reason. A shortened push still opens the intended detail. |
| 10-B | Record queue/provider status and actual test-recipient receipt. | Stored or provider-accepted is not called received/read without corresponding evidence. The owner's outbox view (`GET /delivery/outbox`) shows `accepted`, never `delivered` or `received`, and states that receipt is not observed. **SA-006: deployed 2026-09-28 (`00b94de9`).** |
| 10-C | Observe engineering's failed-transport and retry scenario: one temporary failure (for example the mail server unreachable for a minute) and one permanent one (a wrong mail password on a test deployment). | The temporary failure is retried and arrives once. The permanent one is tried once and becomes a dead letter whose reason names what to fix ("check SMTP_USER and SMTP_PASSWORD"). Both stay visible in the outbox view with their reasons; no duplicate message, and no phone shows the same notification twice. **SA-006: deployed 2026-09-28 (`00b94de9`).** |
| 10-D | Check one portfolio escalation and one watchdog notice on desktop and phone. | Correct recipient/content, readable layout and relevant destination; operational notices are distinguishable from investment advice. |
| 10-E | With two dedicated test accounts on different addresses, ask engineering to send each one scheduled brief. | Each address receives only its own account's brief. Nothing reaches the owner or fallback inbox, including when engineering simulates a failed account lookup. **SA-006: deployed 2026-09-28 (`00b94de9`).** |
| 10-F | Put a test phone with alerts enabled in airplane mode for ten minutes across a scheduled push, then reconnect it. | The notification arrives after reconnecting (pushes are held for up to 12 hours). Record the send and arrival times. **SA-006: deployed 2026-09-28 (`00b94de9`); the effect was not measured before.** |

**Deliverable:** message ID/date, content match, transport state, receipt time
and screenshot. Related PI: SA-006, SA-011, SA-024. A delivered backup email
does not replace HT-12's restore test (12-B), and it does not count as the
off-site copy.

## 13. HT-11 — User access, chat and screens

**Duty:** test as ordinary users and check errors, boundaries and presentation.
Use two synthetic accounts and approved test content.

| Case | Tester action | Expected result |
|---|---|---|
| 11-A | Log in with each account and inspect portfolios/watchlists/private chats. | The user gets only their permitted private records. Shared market intelligence is distinguished from personal data. |
| 11-B | Sign out or use an expired session on a private page/action. | Clear access failure; no private data exposed through stale navigation or a forbidden write. |
| 11-C | In a test account, ask the assistant to repeat, word for word: `<img src=x onerror="document.title='SA001-EXECUTED'">` and `[tap me](javascript:document.title='SA001-EXECUTED')`. Then ask for a short answer with a bold line, a bullet list and a link to https://www.nseindia.com/, and tap the link. | The `<img …>` text is shown as plain text; the browser tab title never changes to `SA001-EXECUTED`; "tap me" is not a working link. Bold, bullets and the link render normally. The NSE link opens in a new tab, and the app tab stays where it was. **SA-001: accepted (code review); committed as `8413b59`, production verification pending.** The model may paraphrase instead of repeating: record that, and rely on engineering's browser test (`npm run test:frontend`) for exact fixtures. |
| 11-D | Observe a disconnected/failed API and a genuinely empty account. | Demo, stale, empty and live data are distinguishable. A populated sample chart does not masquerade as live results. **PI target: SA-024/SA-032.** |
| 11-E | Use mobile/PWA layout, refresh and deep links. | Reports remain readable and return to the expected screen/account without losing date/context. |

**Deliverable:** user-journey screenshots and expected/actual access results.
Related PI: SA-001, SA-024, SA-028 (stretch), SA-032 (stretch).

## 14. HT-12 — Monitoring, cost and recovery

**Duty:** witness recoverability and clear failure reporting. Engineering runs
the drill and supplies sanitized results; the tester does not administer
production or inspect raw databases.

| Case | Tester action | Expected result |
|---|---|---|
| 12-A | Observe a test job failure and its watchdog/operations record. | Failed component, time, impact and next action are clear. A notice alone does not close the issue. **PI target: SA-011.** |
| 12-B | Witness restoring a named backup into an isolated environment; open restored sample records. Engineering runs `python -m services.data.restore fetch --dest <empty folder>` against the off-site bucket, not the volume, and shares the printed result. | Backup date and contents are known; portfolios/predictions can be read and reconciled. The result says `"clean": true` and names the archive; its file and row counts are recorded. `restored/portfolio/<user>/transactions.jsonl` and one prediction envelope open and match the app. An archive merely existing is insufficient. **SA-007: deployed 2026-09-29 (`26b442f4`); needs the owner's bucket first.** |
| 12-C | Compare restored authoritative advice with a secondary projection. | Missing/stale projection is visible; the team can identify which records to trust. **PI target: SA-009/SA-030.** |
| 12-D | Inspect a prepared run-cost report with retry/fallback activity. | Actual provider calls and attempts reconcile to totals, not just bundle sections or successful model calls. **PI target: SA-025.** |
| 12-E | Open the repository's Actions page for the latest push to `main`, then the "Python tests" job log. | Three jobs ran: Python tests, the broad-except and KT guards, and the browser suite, all green. The test log's header line starts `hermetic: .env disabled`, the installed set shows Python 3.11, and no step uses a secret. **SA-005:** measured 2026-09-28, CI run `36453992259`, 3 of 3 jobs green. |
| 12-F | Witness a drill: engineering opens a throwaway pull request whose new test calls a real website and ignores the error. | The Python tests job fails. Its message names the website and the file and line that made the call, and says the test reached outside the sandbox. Close the pull request unmerged. **PI target: SA-005.** |

| 12-G | Read the morning watchdog notices after a deploy with no off-site bucket configured; later, after the owner configures one. | Before: the notice "Nightly backup passed its restore drill and is confirmed off-site" says no off-site copy has been confirmed and gives the reason (`not configured: BACKUP_OFFSITE_TARGET is unset`). It shows no key, password or secret. It comes once a week, not every morning: after the first notice, the next six mornings are silent (SA-007 change 1). The weekly pace covers only that notice. A problem the nightly job itself finds, such as a failed drill, a flagged ledger or a job that has not run for 36 hours, is reported the next morning and every morning until it is fixed. A drill run by hand on a copy (12-H) does not reach the watchdog. After: the next morning's check is satisfied and names the archive. **SA-007: deployed 2026-09-29 (`26b442f4`). Change 1 was accepted by its fresh review the same day and is committed as `8663387`; until it is deployed, the notice comes every morning.** |
| 12-H | Witness engineering flip one byte in a copy of a backup archive, then drill it. | The drill fails with "checksum mismatch — corrupt or truncated"; nothing is written into the data folder. An untouched copy of the same archive drills clean. **SA-007: deployed 2026-09-29 (`26b442f4`).** |

**Deliverable:** witnessed drill result, tested backup/revision/date, record
counts, remaining gaps and cost comparison. Related PI: SA-005, SA-007, SA-009,
SA-011, SA-025, SA-029, SA-030 (stretch).

## 15. Shared result template and final human decision

Copy this for each case; keep private evidence in the team's restricted store.

```text
Duty / case:
Tester:
Build / environment:
Date, time and timezone:
Fixture / record IDs:
Steps performed:
Expected result (current contract or named PI target):
Actual result:
PASS / FAIL / BLOCKED / NOT RUN:
Redacted evidence reference:
Issue severity / related PI story:
Fix revision and retest result:
```

For the final human decision, the product owner collects the duty summaries
and records **READY FOR THE TESTED SCOPE** or **HOLD**, with open issues and
missing evidence. Wrong security identity, unauthorized private access,
incorrect money movement or materially misleading results should be raised
immediately and held for engineering resolution. Cosmetic defects can be
tracked separately with an explicit owner and scope decision.

This is an organizational testing handoff, not a newly built approval button,
broker authorization or proof of investment benefit. Local implementation,
fresh-session engineering review, production observation and future market
evidence remain distinct. Successful human testing of screens does not close
unimplemented PI stories or establish that adaptation improves returns.
