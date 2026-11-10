# PR-003 — review receipt

**Phase:** fresh-session review (a new conversation opened with "continue", 18 Oct 2026, about
11:30–12:30 IST, session stockagent-main-d3; all 16 peers idle). It is neither the
implementing conversation (stockagent-main-9a) nor a self-review.
**Verdict: ACCEPTED.** Two low findings (R1, R2) and one low test gap (T1) are follow-ups
with named owners. No critical, high or medium finding, and every acceptance criterion is met.

**Reviewed revision:** the uncommitted working tree on `86a3a60`, pinned by review input
[PR-003-manifest.json](PR-003-manifest.json)
`78f2a9eb1e83ed11b51e71a88ec8c8fe33d18a2c5376e231f2c74dd028d074c7` (20 files).
`kt_manifest.py verify` gives 0 mismatches against the working tree at the start and at the
end of the review. The diff, rebuilt by the reviewer's own script
(`analysis_data/pr003/review/rv_digest.py`: `git diff 86a3a60 -- PATH` per tracked manifest
path, `git diff --no-index /dev/null PATH` for the new test file, sorted, PDF excluded), is
111,286 bytes, SHA-256 `8030c1dc4e6a10cd35853f28f6435f41d7e1e8920a30b259cf298fc4d781e6e4`:
the implementer's digest. Its code-and-tests part is 97,577 bytes, SHA-256
`af6fd295f2eda9f34577d0e3a1b9450dde9f082bba3e45c63d78ff1e42b5e7b6`.

Nothing was committed, pushed, deployed or configured. No production state was read, no
message was sent and no reviewed file was changed. The review wrote this receipt, STATE and
HANDOFF, a follow-up note on the PR-008 card, and its own probes under the ignored
`analysis_data/pr003/review/`.

## In one example

Monday's brief shows "Govt plans to cut excise duty on petrol and diesel". Tuesday is an NSE
holiday. On Tuesday night the cut is announced, and on Wednesday Google returns "Govt cuts
excise duty on petrol and diesel" from another outlet, with no figure in the summary.
Wednesday's brief drops it as a repeat: once "plan" (a stopword) and the plural are set
aside, the two headlines name the same five things, and the newer one carries no new figure.
The same holds for the owner and for a member. A real development stays hidden for up to five
briefs (finding R1). This is the implementer's known limit L1, met here without a changed
verb at all.

Everything else in the same week came out as worked out by hand. The week-old SEBI article
that Google ranks every morning, and an item dated only "LIVE", never appear. Before PR-003,
those two led every brief of the week.

## Contract checked

The card's two hard-review questions:

- **Can a material new development be suppressed as a repeat?** Yes, in one class only: a
  follow-up whose summary keeps the same entities and figures and changes only the action
  ("approves" → "withdraws", "plans to cut" → "cuts"). Ruled in R1. Every other realistic
  follow-up in the review's and the implementer's sets is shown: new entities, a new figure,
  a recovery, a cut after a hold.
- **Time zones: UTC publish dates against an IST brief date.** Traced with the server clock
  at UTC, as in production. A story published Wednesday 01:00 IST (Tuesday 19:30 UTC) and
  fetched at Wednesday 07:30 IST as "6 hours ago" is stored as Wednesday. A story published
  Tuesday 21:00 IST and fetched at Wednesday 07:30 IST as "10 hours ago" is stored as Tuesday.
  Feed files are named by the server's UTC date; the one extra file before the floor covers
  00:00–05:30 IST. The macro jobs run 07:30–15:00 IST, all within one UTC date.

Also checked in the code and by probes:

- **Issue-time information.** The brief reads feed files up to its own day only; the daily
  review reads files fetched by the reviewed day only (an article first fetched Thursday is
  absent from Wednesday's review). US figures use the last session before the brief's day,
  and nothing dated after it is used.
- **Duplicate and retry behaviour.** History is the last 5 briefs dated strictly before the
  day, so a same-day rerun shows the same items. Market figures are fetched once per run
  (7 Yahoo reads per morning for two users, not 14).
- **Missing data.** An unreadable or future date is stored as `""` with the raw string kept,
  and no reader treats it as recent. A failed figure is named "unavailable" with no number;
  a market closed that day is simply absent.
- **Privacy.** Each user's repeat history is read from that user's own store. Market rows are
  market-wide and carry no user data. In the trace, the member is shown a story the owner had
  already seen in a brief written before PR-003, and the owner is not.
- **Compatibility.** A brief stored before PR-003 counts as shown through its headline
  (owner, Monday). An old brief renders with no "Before the open" in the text, HTML and Inbox.
  Feed entries written before the deploy keep their old dates (the implementer's L3,
  transitional).
- **Consumers of the brief JSON.** Narration reads only each item's headline, chat's
  `get_portfolio_brief` and `GET /delivery/brief/latest` render through
  `render_brief_text`/`enrich_brief_for_api`, and the Inbox reads the server's sentences. The
  new item keys (`published_date`, `story_key`) reach no prompt.

### Independent adversarial trace (reviewer's own)

`analysis_data/pr003/review/test_rv_trace.py`, 20 tests, with the suite's hermetic boundary
(`conftest.py`). The week runs Mon 19 to Fri 23 Oct 2026. Tue 20 is an NSE holiday (Dussehra),
so there is no brief, but the weekday macro fetches still run.

- **Inputs.** Each of 15 articles has a true IST publish time and a window in which Google
  returns it. At each real fetch time (07:30, 09:00, 12:00, 15:00 IST), the **real** Serper
  reader (`requests.post` stubbed) receives the age Google would show: minutes, hours, whole
  days, then an absolute date after a week. The **real** cache writer stores it in a file
  named by the server's UTC date. Only the LLM tagging step is replaced (severity and summary
  given).
- **Users.** The **real** `run_morning_brief` runs at 08:50 IST for two users. The owner's
  store holds Friday 16 Oct's brief in the pre-PR-003 shape ("Crude oil jumps 5% as Iran
  tensions escalate", no story key); the member has no brief.
- **Markets.** Yahoo frames in each exchange's zone hold only the bars that exist at 08:50 IST
  that morning. Tokyo trades on Monday 19; Hong Kong is closed then (Chung Yeung substitute);
  USD/INR carries a Sunday quote 0.5 above trend; Nasdaq's fetch fails on Thursday. The
  Tokyo/Hong Kong in-progress bar is assumed present (L4, still pending in production).

Hand-worked results (all matched on the first run of the reviewed code):

| Brief | Owner shows | Member shows | Owner `overnight_filter` (since, candidates, undated, stale, repeats, shown) |
|---|---|---|---|
| Mon 19 | plan to cut excise; RBI ₹50,000 cr liquidity; GST Council cuts | crude "further" (owner: repeat of Friday's old brief); plan to cut excise; RBI liquidity | 16 Oct, 7, 1, 1, 1, 3 |
| Wed 21 | Fed holds, signals pause; Nikkei record (Tue, a holiday) | Fed; Nikkei; GST Council (Monday's, which the member's cap had cut) | 19 Oct, 11, 1, 2, 6, 2 |
| Thu 22 | rupee opens at 94.80 | same | 21 Oct, 11, 1, 7, 2, 1 |
| Fri 23 | rupee opens at 95.10 (new figure); Infosys guidance (Thu 14:00, after Thursday's brief) | same | 22 Oct, 12, 1, 7, 2, 2 |

- **Never shown:** the SEBI article from 14 Oct (stored as 15 Oct from "4 days ago"); the
  "LIVE" item; Sunday's FPI story (cut by Monday's cap, then stale); another outlet's "Fed
  holds rates steady and signals a pause in its easing cycle"; and the excise cut (R1).
- **Same URL, three spellings, four days.** The RBI liquidity story, fetched Monday to
  Thursday (plain, then `m.` host, then `utm_source`), appears in Monday's brief only, for
  both users.
- **Before the open:**
  - Monday: "S&P 500 5,960.00 (+0.17%), as of Fri 16 Oct", "Nikkei 225 39,285.00 (+0.11%),
    as of Mon 19 Oct" and "USD/INR 94.38 (+0.06%), as of Mon 19 Oct" (against Friday; the
    Sunday quote is ignored). Hang Seng is absent, and no "Unavailable" line appears.
  - Wednesday: US figures as of Tue 20 and Asian figures as of Wed 21.
  - Thursday: "Unavailable: Nasdaq Composite." and no Nasdaq number anywhere.
  - Text, HTML (escaped) and the API's lines are identical sentences for both users.
- **Daily review** for Wednesday at 16:30 IST: Nikkei record, the excise cut, the Fed and the
  MEDIUM auto-sales item, in that order; nothing older than Tuesday and nothing fetched later.
- **Chat** on Friday at 10:00 IST: only items published Thursday or Friday. The rupee story
  is listed twice, once per URL spelling (I2).
- **Bite.** Run against the 86a3a60 modules (`RV_SWAP=base`, in-memory swap of brief, store,
  cache, fetcher and macro), 17 of the trace's first 18 tests fail. Only the holiday test
  passes on both. The old briefs show the SEBI article and the "LIVE" item every day.
- **R2 probe.** An article published Tuesday 09:00 IST and first returned on Thursday at 07:30
  IST is 46.5 hours old; Google says "1 day ago". It is dated Wednesday and shown on Thursday.
- **First-fetch probe.** A story published Tuesday 21:00 IST and fetched Wednesday ("10 hours
  ago" → Tuesday) and Thursday ("1 day ago" → Wednesday) is stale on Thursday, because
  readers keep the first fetch. Mutant X1 (the last fetch wins) is caught by this probe but
  not by the story tests (T1).

## Findings

| ID | Severity | Location | Evidence | Disposition |
|---|---|---|---|---|
| R1 | Low (accepted limit; product) | `core/delivery/brief.py:240-253` (`_repeats`); stoplist `config.yaml:812-815` | Trace, Wednesday: "Govt cuts excise duty on petrol and diesel" after Monday's "Govt plans to cut excise duty on petrol and diesel" has 0 new salient entities ("plan" is a stopword; "cuts" → "cut") and no figure, so it is a repeat for both users. The implementer's strict xfail is the same class with one changed verb. | **Ruling: acceptable as a documented limit.** It needs the same entities, the same figures and a changed action only. It is bounded to 5 briefs and to HIGH macro items, and the news summaries usually carry a figure or date for an action. A token rule cannot see the change; a fix needs meaning. The KT and guide wording is widened in PR-003's commit (below). Follow-up: a note on [PR-008](../stories/PR-008.md), whose "not shown again" rule for company events must not reuse this rule unchanged ("proposes dividend" → "declares dividend"). |
| R2 | Low (docs; inherent to the source) | `services/background/macro_news_fetcher.py:108-114`; guide 10-I | Google gives ages in whole days after 24 hours, and the fetcher takes the newest date that age allows. Probe: an article 46.5 hours old is "1 day ago", dated the floor day, and shown once on Thursday, though it was published the day before Wednesday's brief. Guide 10-I says no item was published before the previous brief's date. | No code change (delegated technical call, recorded). Dating "N days ago" at its oldest bound would misdate items that chat and the daily review read, and the effect is one appearance: the next morning the first fetch makes it stale, and before PR-003 such an article returned every day. The KT and guide 10-I state the exception, in PR-003's commit. |
| T1 | Low (test gap) | `services/background/macro_news_cache.py:141-157` (`entries_fetched`) | Mutant X1 (iterate the files newest first, so the last fetch wins) passes the story files: 140 passed, 1 xfailed. It re-dates a story by a later "1 day ago" and shows a pre-brief story once more. The reviewer's first-fetch probe catches it. | Routed to [SA-031](../stories/SA-031.md)'s test-gap list (card note). Code correct. |
| I1 | Info | `services/api/routes/ui_data.py:1747-1798` | Chat's `get_macro_news` falls back to one live Serper search, labelled "background feed not yet populated today", whenever nothing was published today or yesterday. Before PR-003 that happened only when today's file was empty. | No change. Rare, with 4 fetches a day; one search per tool call. |
| I2 | Info | `macro_news_cache.py` `entries_fetched` | Readers that span several files keep one entry per **exact** URL; chat lists the same article twice when Google returns it under a `utm_` or `m.` spelling on another day. The brief normalises URLs and is unaffected. | No change. A candidate for SA-031 if chat duplicates are seen. |
| I3 | Info | `core/delivery/brief.py` `_market_lines` | A move under half a basis point, or under 0.005%, that is negative prints as "-0 bp" or "-0.00%". | No change; cosmetic. |
| I4 | Info (inference from code) | `core/delivery/brief.py` `run_morning_brief` → `store.save_brief` | A manual rerun the same day (`POST /delivery/run-brief`) overwrites that day's stored brief. If a fetch since 08:50 added a newer item, the rerun's top 3 differ, and an item the 08:50 email showed drops out of the history. If it was published that morning, it passes the next day's floor and can be shown again. The rerun also re-sends the brief, as before PR-003. | No change: reruns are rare and owner-only. Worth knowing when reading 10-I after a rerun. |

## Rulings on the implementer's delegated decisions

- **D1–D3 (IST publish date, floor = previous brief's date, files floor−1..day):** accepted.
  The date-granularity tolerance of D2 is extended by Google's whole-day ages (R2).
- **D4–D6 (story key, the repeat rule, the last 5 briefs strictly before the day):**
  accepted, with R1 ruled as a documented limit.
- **D7–D9 (newest first, `overnight_filter`, chat and the daily review on the same rule):**
  accepted.
- **D10–D14 (sessions, no GIFT Nifty, one fetch per run, the server writes the sentences,
  narration unchanged):** accepted. D10's live-session premise remains L4, checked on Monday
  19 Oct (`PR-003-P1`); it fails safe (absent, not invented).
- **L2, L3, L5, L6, L7:** accepted as recorded. L7: chat's 1,800-character cut is unchanged.

## Commands and environment

Windows 11, `.stockai` venv (Python 3.13), Node 24 with the vendored Playwright Chromium;
hermetic boundary on (no `.env`, no network, no checkout data).

| Command (repository root) | Result |
|---|---|
| `scripts/docs/kt_manifest.py verify docs/planning/PI-2026-09/evidence/PR-003-manifest.json` (start and end) | 20 files, 0 mismatches; `78f2a9eb…` |
| `.stockai/Scripts/python.exe analysis_data/pr003/review/rv_digest.py` | 19 paths, 111,286 bytes, `8030c1dc…` |
| `pytest -q -p no:cacheprovider tests/unit/test_overnight_freshness_pr003.py tests/unit/test_delivery_brief.py tests/test_macro_news_cache.py tests/test_macro_news_fetcher.py tests/unit/test_brief_earnings_watch_fix004.py tests/unit/intelligence/rl/test_macro_fallback_context.py` | **200 passed, 1 xfailed** (the strict L1 xfail) |
| `pytest -q -p no:cacheprovider --rootdir analysis_data/pr003/review -c NUL analysis_data/pr003/review/test_rv_trace.py` | **20 passed** |
| the same with `RV_SWAP=base` (86a3a60 modules in memory; the first 18 tests) | **17 failed, 1 passed** (the holiday test) |
| X1 with `-p rv_mut_plugin` (`RV_MUT=X1_last_fetch_wins`, `PYTHONPATH=analysis_data/pr003/review`): the story files / the reviewer's trace | story files **140 passed, 1 xfailed** (X1 survives: T1) / trace **4 failed**, 16 passed (caught, including the first-fetch probe) |
| the implementer's mutants re-run (`PR003_MUT=…`, 4 of 33) | unparseable_is_today 4 failed, brief_no_floor 5 failed, repeat_ignores_numbers 2 failed, weekend_bar_kept 1 failed: each caught, with the counts in the implementer's log |
| `npm run test:frontend` | **34/34**, including the 2 new "Before the open" tests (run with the machine idle) |
| `scripts/docs/check_kt_docs.py` | errors `[]`; 45 pages; source `21aa4392…` (the PDF matches its source) |
| `scripts/ci/check_broad_except.py` | OK (152 grandfathered) |
| `pytest -q -rfEs -p no:cacheprovider tests` (CI's command) | **5,007 passed, 12 skipped, 1 xfailed (the known limit), 0 failed** in 18 min 28 s |

Not exercised: real Yahoo or Serper (the live-session premise is `PR-003-P1`), the deployed
service, a real mail client, and an Inbox on a phone. Raw outputs are in the ignored
`analysis_data/pr003/review/`.

## Acceptance checklist

| Criterion | Verdict |
|---|---|
| The same URL fetched on 3 consecutive days appears in at most one brief | Met: the trace's RBI story, 4 days and 3 spellings; the story test's article A |
| An article published 3 days before the brief but fetched today is not shown | Met: the SEBI article and the story test's P. On a Monday, Friday is the previous brief's date, so Friday's news after that brief is shown, as Change 1 says |
| A reworded copy is suppressed; a genuinely new development is shown | Met, with R1 ruled as a documented limit |
| An unparseable date never reaches the overnight section | Met: "LIVE" is stored as `""` and never shown |
| Each market figure has its as-of date; a failed one is absent and named "unavailable" | Met: trace, Monday to Thursday |
| Chat and the daily review keep working, on the same documented rule | Met: trace; CHAT_ARCHITECTURE, RL_DESIGN section 5, AGENTIC_DESIGN section 12 |
| Living docs and the human test case describe the behaviour; the PDF matches its source | Met: KT section 10, guide 10-I, `check_kt_docs` `[]`; R1 and R2 wording at commit |

## Commit-time edits (to apply in PR-003's commit, at the owner's word)

**Applied** at the owner's word ("commit and push", 18 Oct about 15:10 IST): the code is
committed as `b6d2470`, identical by blob to the reviewed input, and these edits are in the
docs commit that follows (PDF source `05f5c16c…`, `check_kt_docs` `[]`).

1. KT section 10, replace the sentence "The known limit: a follow-up that changes one verb of
   an otherwise identical headline ("approves" to "withdraws") reads as a repeat." with:

   > The known limits: a follow-up that changes only the action of an otherwise identical
   > headline, with no new figure, reads as a repeat for up to 5 briefs ("approves" to
   > "withdraws", or "plans to cut" to "cuts"). And after 24 hours Google gives an article's
   > age in whole days, which the fetcher dates at the newest day that age allows, so an
   > article first seen at "1 day ago" can be up to two days old; it is shown once.

2. Guide 10-I, expected result: after "none was published before the previous brief's date
   (IST)" add "(one exception: an article Google first lists as "1 day ago" can be up to two
   days old; it appears once)". After "a notification after an announcement) does." add "A
   follow-up that only changes the action, with the same words and no new figure ("plans to
   cut" then "cuts"), is a known limit: note it if you see one."
3. Guide 10-I status line: "**PR-003: accepted 2026-10-18, committed as `<sha>`; production
   verification pending.**"
4. KT section 12, the PR-003 row `Open` → `Done`; the KT header bump; rebuild the PDF and run
   `check_kt_docs`.

## Production verification (remaining)

`pending_deployment`: the code is accepted, uncommitted. After the deploy:

- `PR-003-P1` (STATE `pending_production_checks`): **passed, 20 Oct 09:57 IST.** The Yahoo
  probe ran locally on public Yahoo data (`analysis_data/pr003/yahoo_probe.py`, the committed
  PR-003 code; no production access) in the first "continue" conversation inside the 07:00–12:00
  window. Monday's run was missed. In the brief dated Tue 20 Oct:
  - Nikkei 225 `ok`, 64,176.09 (−1.14%), "as of Tue 20 Oct" (13:27 JST, afternoon session);
  - Hang Seng `ok`, 23,956.93 (−0.95%), "as of Tue 20 Oct" (12:27 HKT, lunch break). Its
    Monday bar is absent, which is correct: Hong Kong was closed on Mon 19 Oct;
  - USD/INR `ok`, "as of Tue 20 Oct", a weekday.

  So Yahoo returns the in-progress daily bar during both sessions, and L4's premise holds.
  Inference, not measured: at 08:50 IST, Tokyo is in its lunch break (12:20 JST) and Hong Kong
  is in its morning session (11:20 HKT). Both have opened, so the bar exists then too. The
  deployed 08:50 brief itself is checked by the first week's 10-I run. Raw output:
  `analysis_data/pr003/yahoo_probe_20261020_0956.txt`.
- The first week: `overnight_filter` in `GET /delivery/brief/latest`, the Sunday probe's
  repeat count (expected near 0), and guide case 10-I. Fewer items on quiet days is correct.

## Decision

**Accepted** for the reviewed revision (input `78f2a9eb…`, diff `8030c1dc…`). STATE: PR-003
`done`, production verification `pending_deployment`, `active_task: null`,
**`next_task: SA-050`** (ready, no dependencies; not started). Follow-ups: R1 → PR-008 card
note and commit-time wording; R2 → commit-time wording; T1 → SA-031 card note.
