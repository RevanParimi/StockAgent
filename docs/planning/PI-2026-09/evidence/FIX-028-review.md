# FIX-028 — fresh review receipt

**Story:** [FIX-028](../stories/FIX-028.md): a sold stock leaves the daily review.

**Context:** fresh-session review, 11 Nov 2026, about 11:34–12:40 IST. Session `stockagent-main-38`
[906bed], a new conversation opened with "continue". It is not the implementing session
(`stockagent-main-63`). After a fetch, `origin/main` was `1eb1b29`, the same as HEAD: nothing had
arrived from the other device. Peers -17, -22, -63, -77 and -09 were idle.

**Verdict: ACCEPTED** for code `245e29e` and the FIX-028 documents in `1eb1b29`. No finding is above
low in FIX-028's own change; one medium, pre-existing finding and two low ones go to a new card,
[FIX-032](../stories/FIX-032.md). Nothing was committed, pushed, deployed or configured. Production
was read once, read-only: Railway's deployment list (below). No production data, log or
environment was read, no LLM or network call was made from a test, and no message was sent.

## Reviewed input

- **Code `245e29e`:** the manifest's 9 code and test files. `kt_manifest.py verify
  FIX-028-manifest.json --rev 245e29e`: no mismatch among them (the 6 documents differ by the
  commit-time status edits, as STATE records). Their diff from `02f3ad7`: 56,297 B, SHA-256
  `38afcb5d709856835cb261c03f6c9c62a78a315d72789b3d43398a5f66f085b7`. The same files are unchanged
  from `245e29e` to HEAD and in the working tree
  (`analysis_data/fix028_review/rv_digest.py`).
- **Documents `1eb1b29`:** the 5 Markdown files' diff from `02f3ad7`: 33,789 B, SHA-256
  `e1e31f7b22904684a0777ec0e23e386c9eb24ae033ff57a05ad52ebf3b167e15`. It also holds FIX-027's three
  commit-time edits, read here only as text. The PDF is checked by `check_kt_docs` (its source
  digest `b4d9bff2…` equals the KT's).
- **Production:** Railway `8c88aa72` (the push of `02f3ad7..1eb1b29` at about 07:37 IST) shows
  SUCCESS in the deployment list read at 12:06 IST. Production runs `245e29e`; the first run of the
  new rule is the 16:30 review of 11 Nov.

## The contract, and how it was checked

**1. The release never disables a stock some portfolio holds, and changes nothing else (RV1).**
300 random states, seeded: up to three portfolios on disk with symbols spelt in any case and with
padding, watchlist items of every source, a just-saved portfolio stored outside the data folder,
entries of every origin, with and without an `enabled` key, and a duplicate entry. This file's
own oracle says what each entry must become: an enabled `held` entry whose symbol no portfolio
holds is disabled, or becomes `watchlist`/`weekly` when a non-autopilot watchlist item lists it;
every other entry and field is unchanged, and an unchanged list is not rewritten. **300 of 300
pass.**

**2. After any autopilot run, every holding is reviewed or named (RV2).** 150 random states
through the real `execute_advice` (a run with no trade), the cap at or near the enabled count. Each
of the portfolio's holdings without an original entry ends with an enabled `held`, daily entry, or
is named in `not_reviewed` with "managed-ticker cap N reached", and then the list really holds N
enabled entries, none of them evictable. A `held` entry of a stock any portfolio holds never loses
`enabled`, original entries never change, and the run never takes the list past the larger of the
cap and its starting count. **150 of 150 pass.** The first run failed 11 seeds, all on the fixture:
an empty `[]` file, which `load_managed_tickers` replaces with the five-ticker seed on the next
promotion (pre-existing; production's list is never empty). The fixture now writes at least one
entry.

**3. The lock excludes another process (RV3).** Production runs two workers (KT section 2). A child
process takes the same lock file with plain `filelock`; `promote_symbol` waits and writes nothing
until the child lets go, then lands. **Pass.** The implementer's test covers two threads; with
`filelock` 3.29's default `thread_local=True`, threads in one process exclude each other too.

**4. The story's tests fail for the original defect.** The story file, run against `02f3ad7` in a
detached worktree: 17 failed, 6 passed. The 6 are the cases where nothing must change (a TRIM that
leaves shares, another portfolio's holding, an original entry, an unreadable portfolio, no managed
file, an original entry disabled by hand). The acceptance tests fail on their assertions: BACK stays
`enabled: true` after its exit, and at the cap OLD stays enabled while NEW is refused. Expected
results in the story file are worked by hand in each docstring, not read from the code.

**5. An adversarial trace (RV4).** u holds BACK and KEEP; v, autopilot off, watches BACK through
`POST /portfolio/watchlist` (source `user`). u exits BACK on Monday: the entry becomes `watchlist`,
`weekly`, enabled (D5). Then:

- v removes BACK through `DELETE /portfolio/watchlist/BACK`: the route demotes it (RV4a, pass);
- v removes BACK on the home page (`PUT /ui/watchlist`, Atlas on as in `config.yaml`): v's watchlist
  is empty, yet after u's Tuesday run BACK is still enabled. The release follows only `held`
  entries. Finding RV4b.

**6. Consumers of the managed list** (code inspection). The 16:30 job's cohort
(`scheduler.py` 790), the scheduler API, the events feed and the start-up self-heal read enabled
entries only; the news fetcher reads every entry, for company names only; the pre-open check reads
the sector configs, not the list. The deep dive's skip reads enabled entries only
(`deep_dive.py` 110), so a released stock is dived again with no flag; FIX-025's `sold` flag is
still needed for a sold stock that stays managed (an original entry, or one a user watches): D9
holds. The auditor's lanes and the exit shadow grade from closes; no metric counts a holding's
missing reviews. A re-bought stock has no current month's envelope until the next self-heal or the
1st, as any new buy.

**7. Locks and order** (code inspection). Only `execute_advice` takes the list's lock while holding
a portfolio's; the API's add, CSV import and shelf promotion take the list's lock after letting the
portfolio's go; the release reads the other portfolio files without their locks. No path takes the
two the other way round. With Atlas on, the home page's watchlist is `Portfolio.watchlist`, so the
release sees a home-page watch (source `user`).

**8. The card's hard-review questions.** (1) Nothing grades from a sold stock's reviews (item 6).
(2) The managed file is safe to write from the executor with another portfolio's run in the same
job: portfolios run in turn, the release reads them under the list's lock, the save is atomic, and
the lock holds across processes (RV3). The owner's dashboard routes take no lock (routed to SA-026
by the implementer; agreed). (3) The `sold` flag stays (item 6).

## Findings

| # | Severity | Where | Trigger → observed / expected | Impact | Disposition |
|---|---|---|---|---|---|
| RV5 | **Medium, pre-existing** (confirmed: strict xfail) | `services/api/routes/ui_data.py` `update_watchlist` (1195-1221): the `_ALL_TICKERS` filter, then `current - desired` removed | v watches BACK (added through the API) and adds MARUTI on the home page. **Observed:** v's watchlist is MARUTI only. **Expected:** BACK kept; the home page cannot show or edit it. | Every home-page save silently drops the account's watchlist stocks outside the 16 built-in names: its own API additions, its shelf promotions (watchlist buy candidates) and the autopilot's notes. Their managed entries stay enabled. Frequency not measured. | [FIX-032](../stories/FIX-032.md) |
| RV4b | Low (confirmed: strict xfail) | `core/portfolio/promotion.py` `release_unheld` follows `held` entries only; `PortfolioStore.remove_watchlist` (the home page's removal) does not demote | After D5 keeps BACK as a watchlist entry for v's watch, v removes it on the home page. **Observed:** enabled after the next run. **Expected** (card: "not on a user's own watchlist … is demoted"): disabled. | Cost only: reviewed every weekday until the cap evicts it (it is evictable, its old `promoted_at` first). The API's delete route demotes. | FIX-032; commit-time doc edits below |
| RV6 | Low (confirmed: strict xfail) | `promotion._portfolios_now` reads `store.list_user_ids`, which needs a live `portfolio.json` | v's file was quarantined (`portfolio.json.corrupt-*`, not restored); v held BACK; u exits BACK. **Observed:** BACK disabled. **Expected** (the docs: "a portfolio file that cannot be read releases nothing"): enabled. | Needs a corrupt file, which already raises a critical alert. After a restore, an autopilot account's next run re-promotes; an account with the autopilot off is not healed. | FIX-032 |
| I-1 | Info | `core/delivery/brief.py` `_VERDICT_PLAIN`; `portfolio.jsx` 669; a same-day re-run | The brief's line reads "NEWCO  NO_DATA — …"; the page skips `NO_DATA` rows, and a re-run rewrites the digest without `not_reviewed`, as with `top_up_skipped`. | Wording and visibility only. | PR-007 routed input (added) |
| I-2 | Info, decision (D6) | `autopilot._follow_holdings` | A `held` entry the owner disabled by hand, for a stock still held, is re-enabled on the next run; only original entries stay off. | Intended: a holding needs its review. The docs say it as "a disabled held entry" is promoted. | None |
| I-3 | Info | `core/discovery/deep_dive.py` 135 (comment) | "a stock the autopilot bought stays managed after its sale" | Comment only; KT section 8 is current. | FIX-032 housekeeping |
| D-1 | Low, docs | TEAM_TESTING_GUIDE 07-P; KT section 6; AUTOPILOT_GUIDE section 12 | 07-P's B adds BACK "on the home page", which accepts only its 16 names, and (b) expects any removal to disable BACK, which holds only for the API's delete route. KT and the guide say a user's watch is "added on the home page or promoted from the shelf". | A tester following 07-P on the home page sees BACK stay enabled. | Commit-time edits below |

No other finding. The implementer's routed findings (the dashboard routes take no lock; the delete
routes look only at the user's own portfolio) are confirmed by reading and stay with SA-026.

## Commands and results

Environment: `.stockai/Scripts/python.exe` (Python 3.13), Windows, repository root, hermetic
(`tests/hermetic.py`). Reviewer files in `analysis_data/fix028_review/` (ignored).

| Command | Result |
|---|---|
| `scripts/docs/kt_manifest.py verify …/FIX-028-manifest.json --rev 245e29e` (and HEAD, working tree) | 9 code and test files match at all three; the 6 documents differ at `245e29e` (not yet committed there) and the KT, guide and PDF at HEAD (commit-time status edits) |
| `analysis_data/fix028_review/rv_digest.py` | as under "Reviewed input" |
| Story file against `02f3ad7` (detached worktree in the scratchpad, removed) | 17 failed, 6 passed (item 4) |
| `pytest -q -p no:cacheprovider analysis_data/fix028_review/test_rv_fix028.py` | **452 passed, 3 xfailed** (strict); with `--runxfail` the three fail at their last assertion: RV4b `True is False`, RV5 `['MARUTI'] == ['BACK', 'MARUTI']`, RV6 `False is True` |
| Focused: the 20 test files naming promotion, the managed list, the autopilot, the digest, the brief, FIX-025's end-to-end file and FIX-002's resolution | **372 passed** (2m03s) |
| `scripts/ci/check_broad_except.py` | OK (148 grandfathered) |
| `scripts/docs/check_kt_docs.py` | `errors: []`; header `245e29e`, edition 2026-11-11; PDF 68 pages, source `b4d9bff2…` |
| Full suite `pytest tests -q -p no:cacheprovider` | **6,279 passed, 12 skipped, 1 xfailed, 1 failed**, pytest rc 1, 24m21s (11:43–12:08 IST; `analysis_data/fix028_review/full_suite.txt`). Git status changed only by this review's own documents. The failure is `test_delivery_sa006_invariants.py::test_real_push_refused_connection_is_retried_and_shown_once`: it expects a connect to a non-listening loopback port to be refused, and got `ConnectTimeout` after 20 s. It fails 3 of 3 runs alone. `loopback_probe.py` shows the cause is this laptop today: a connect to any closed loopback port, bound or not, times out after 8 s instead of being refused. FIX-028 changes no delivery code, and the file passed in the implementer's run at 01:10 IST. Environmental, not routed; re-run where loopback refuses |
| `railway deployment list` (read-only) | `8c88aa72` SUCCESS (created 07:37:47 IST) |

**Not exercised:** a browser run of the home page (RV5 was reproduced through the route
function); a real two-worker deployment (RV3 used two local processes); mutants (the implementer's
19 of 19 stand; RV1 and RV2 test the invariants directly); the production list's size (the card's
measurement is still not run).

## Acceptance checklist

| Criterion | Verdict |
|---|---|
| By the real executor and promotion: a full exit demotes; a TRIM, another portfolio's holding, a user's own watchlist and a `manual` entry do not; a re-buy re-enables under the same sector | Met (story tests; RV1, RV2) |
| The daily review skips a demoted stock and reviews a re-bought one | Met (the story's cohort helper reads the list the 16:30 job reads) |
| A `cap_full` buy is visible in the digest | Met (row, text and brief; RV2 for the cap invariant). The page and a same-day re-run do not show it: I-1 |
| Docs: KT section 8, AUTOPILOT_GUIDE, guide cases | Met, with D-1's corrections at commit time |
| Card's measure first | Not run (owner's word; the probe and command are in the implementation receipt). Production already runs the rule; the probe can still read the count before the 16:30 run of 11 Nov |

## Production verification (pending)

Status `pending_observation`. Production runs `245e29e` since the deploy of about 07:40 IST on 11
Nov (Railway `8c88aa72` SUCCESS). After the 16:30 run of 11 Nov, read-only: guide 07-P's production
line (the probe's counts by origin; the digests' `not_reviewed` rows). No benefit is shown by this
review: the saving is the number of released entries times a review's cost, which only that count
gives.

## Commit-time edits

The KT, AUTOPILOT_GUIDE, the testing guide and the PDF are in FIX-028's reviewed manifest, so they
were not edited during this review. At the next docs commit, with the owner's word:

1. **KT section 1** (production paragraph): production runs `245e29e` (FIX-028, committed before
   its fresh review and accepted on 11 Nov), deployed at about 07:40 IST on 11 November 2026 (the
   deployment list showed it SUCCESS; `/health` was not read). Drop "not yet deployed".
2. **KT section 6**, "The managed list follows the holdings": replace "(added on the home page or
   promoted from the shelf, not the autopilot's own exit entry)" with "(added by the user or
   promoted from the shelf, not the autopilot's own exit entry)", and after "which the cap may
   evict." add: "It is not released again when the watch ends: the API's delete route demotes it,
   a removal on the home page does not. **Planned:** FIX-032, which also keeps a home-page save
   from dropping the watchlist stocks the home page does not list, and stops the release while an
   account's portfolio is quarantined."
3. **KT section 12:** FIX-028 `Done`; a new row: `[FIX-032](planning/PI-2026-09/stories/FIX-032.md)
   | A home-page watchlist save keeps what it does not show, and a removal there leaves the daily
   review | Open | 6 Portfolio; 10 Interface | FIX-028`.
4. **AUTOPILOT_GUIDE section 12**, "The list follows the holdings": "(added on the home page or
   promoted from the shelf; …)" → "(added by the user, through the API or the home page's own list,
   or promoted from the shelf; …)", and after "weekly, and evictable at the cap." add: "When the
   watch ends through `DELETE /portfolio/watchlist/{symbol}` the entry is disabled; a removal on the
   home page leaves it enabled (FIX-032)." In "Never on a guess", after "(nothing is released, and
   the file is not quarantined)" add: "; an account whose file is already quarantined is not read,
   so its stocks can be released (FIX-032)".
5. **TEAM_TESTING_GUIDE 07-P:** "B holds nothing and has BACK on its watchlist, added on the home
   page" → "…added through `POST /portfolio/watchlist`"; (b) "then remove BACK from B's watchlist"
   → "then remove BACK from B's watchlist through `DELETE /portfolio/watchlist/BACK`"; expected
   result (b) gains "(A removal on the home page leaves it enabled: FIX-032.)". Status line:
   "**FIX-028: committed as `245e29e` before its fresh review; deployed 11 Nov 2026; accepted on
   2026-11-11 (fresh review).**"
6. **PDF:** regenerate from the KT; `check_kt_docs` `errors: []`.

**Applied** at the owner's word ("commit and push", 11 Nov about 14:00 IST) in the docs commit after
`1eb1b29`. Edit 2 was placed as a "Not covered … **Planned:** FIX-032" sentence at the end of the
paragraph, in the KT's usual form, rather than mid-paragraph; edit 1 says "pushed at about 07:37 IST",
since the deployment list gives no SUCCESS time.

## Follow-up state

- FIX-028 `done`; production `pending_observation` (above).
- New [FIX-032](../stories/FIX-032.md) (P2, 2 points, after FIX-031, before PR-005): RV5, RV4b,
  RV6, I-3. Routing delegated by the owner (2026-10-13). Not a precondition for switch-on.
- PR-007's card has I-1 as routed input.
- `active_task` null; `next_task` FIX-029 (implementation, a new conversation). The Saturday 14 Nov
  watch for SA-044 and FIX-030 still applies.
