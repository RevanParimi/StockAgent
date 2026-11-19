# PR-037 — implementation receipt

**Story:** [PR-037](../stories/PR-037.md): enough analysed ideas to hold 25 to 30 stocks. Owner
request of 17 Nov 2026 ("it is our fault if we think there are no good stocks to buy"; "at
least 20-30 investments ... with analysis"). Profit-path step: **invest**.

**Lane: decision path.** Reason: it changes which stocks can be bought (the card; AGENTS.md step
4): how the week's analyst calls are shared decides which companies are analysed, and the shelf's
size and sector cap decide which BUY ideas the autopilot may buy. **Status after this phase:
`review_required`.** The next fresh conversation performs the hard review from `REVIEW.md`; this
phase's self-review does not count as it.

## Phase

- **Implementation** (autopilot `1118-0807-p3`, code-server, Wed 18 Nov 2026 from about 08:07
  IST, outside a push window). Baseline `3a59155` (`main`, six commits ahead of `origin/main`
  `6e1962f`). Committed **`d6e5777` on `story/PR-037`**, which only a fresh review's acceptance
  merges into `main`. Production was not read; nothing pushed, deployed, run or sent.

## What changed (`3a59155..d6e5777`)

| Setting (`config.yaml`) | Was | Now | PR-035's read (18 Nov) |
|---|---|---|---|
| `discovery.shelf_size` | 20 | **45** | measured need: 20 of 20 full, 4.5 ideas at or above the floor turned away a week |
| `discovery.max_ideas_per_sector` | 3 | **6** | measured need: 3 sectors at the cap; 6 × 3.2% = 19.2% within PR-036's 30% sector cap |
| `discovery.deep_dive_count` | 20 | **45** | measured yield; the split is provisional (new companies and IPO slots not told apart) |
| `discovery.new_dive_floor` | (none) | **15** | new; a third of 45, provisional; `base.py` fallback 0 = off |
| `discovery.max_candidates` | 40 | **60** | still provisional: no screen file was read |
| `discovery.shortlist_size` | 80 | **120** | still provisional: no screen file was read |
| `discovery.min_conviction` | 0.55 | 0.55 | unchanged: the bar does not move |

**The budget split** (card step 1). `budget_split()` in `core/discovery/__init__.py`: the
re-dives may take the week's calls less this week's IPO candidates less the floor, never below
0 (45 − 2 − 15 = **28**). `run_deep_dives(..., redive_room, tally)` in `deep_dive.py` counts
that room in calls made: a re-dive the deep dive skips by its existing rules (the idea of a
stock still held, managed and not sold; no close; not a company) takes none of it. A re-dive past
the room is held back and offered after the screen's ranks, in its order, with the calls they
leave (`hygiene.redive_late`); one that gets no call is named in `hygiene.redive_deferred` and is
due again the next Saturday, oldest first within its group (`ShelfStore.redive_due`, unchanged),
unbuyable until then if its dive is older than 30 days, as before. The floor is a minimum: when
fewer re-dives are due, new companies take the rest. The run's result gains `budget` (calls, IPO,
floor, room, made, re-dive calls). Direct callers that pass no room keep today's order.

**Example** (the card's): 45 ideas, 12 dived more than 30 days ago, 1 sold since its dive: 13
re-dives, 2 IPO candidates, 30 new companies, 45 calls. With 35 due: 28 re-dives, 2 IPO, 15 new;
the 7 least overdue wait and are the first re-dives a week later. With only 5 new companies:
28 + 2 + 5, then those 7 take 7 of the 10 calls left.

**Found while building, and fixed before the commit** [code]: a split by position
(`due[:room]`, as PR-004 split re-dives from IPO slots) would let held stocks' ideas, which
`run_deep_dives` skips, fill the room without a call, pushing real re-dives behind the screen.
With 25 to 30 holdings on a 45-idea shelf that is the common case, not an edge. Hence the room
counted in calls (test `test_a_held_stocks_idea_takes_no_room`).

| File | Change |
|---|---|
| `config.yaml` | The six values, a comment block with the reason, the cost and the rollback |
| `src/backend/shared/config/settings/base.py` | `DISCOVERY_NEW_DIVE_FLOOR` (fallback 0) |
| `core/discovery/__init__.py` | `budget_split()`; all due re-dives passed with the room; `hygiene.redive_late`/`redive_deferred` from the tally; `budget` in the result |
| `core/discovery/deep_dive.py` | `redive_room` and `tally`; a held-back re-dive returns after the last candidate; past the budget a re-dive is only examined, to report it |
| `tests/unit/test_idea_supply_pr037.py` | New, 11 tests (below) |
| `tests/unit/test_discovery_settings.py` | The pinned values, changed on purpose to 120/60/45/15/45/6 |
| `tests/unit/test_idea_supply_pr004.py` | `_cycle_env` keeps PR-004's split (floor 0), since its budgets (2 to 20) predate the floor; one stub accepts the new arguments |
| `tests/unit/test_scheduler_discovery_job.py`, `test_operator_notices_owner_only_fix008.py` | Three `run_deep_dives` stubs accept the new keyword arguments; nothing else |
| `docs/TECHNICAL_DESIGN.md` | Section 8: the shelf's purpose (25 to 30), step 4, step 5 (the split, its example, the cost), step 6 (45, 6), new step 7 (paper reviews, outside the budget), the screen's 120 and 60; section 11: the supply in the repository, its deploy and catch-up run planned |
| `docs/PRODUCT_MAP.md`, `CODEBASE.md` | The deep dive, shelf and settings rows |
| `docs/TEAM_TESTING_GUIDE.md` | New case 06-Q; 06-E reads the settings in force (45/6/45; 20/3/20 before the deploy); 06-K pins the floor at 0 it was written for |

Diff `3a59155..d6e5777`: `git diff 3a59155..d6e5777 | sha256sum` = `d24636e5197168de…`, 13
files, +529/−47. File digests at `d6e5777` (`git show d6e5777:<path> | sha256sum`, first 12):
`config.yaml` `e64919c35798`; `core/discovery/__init__.py` `b15f00b599a8`;
`core/discovery/deep_dive.py` `d0f8850e1419`; `base.py` `61f69d824be4`;
`test_idea_supply_pr037.py` `23df1cfd586a`; `test_idea_supply_pr004.py` `c1df0efebd92`;
`test_discovery_settings.py` `c2e49a74c2dd`; `test_scheduler_discovery_job.py` `6696dbbc0199`;
`test_operator_notices_owner_only_fix008.py` `83b1ccc5ba7d`; `TECHNICAL_DESIGN.md`
`36e27e8eb4c2`; `PRODUCT_MAP.md` `5b660566d802`; `TEAM_TESTING_GUIDE.md` `898329f3a25d`;
`CODEBASE.md` `86d0f8162402`.

## BACKLOG B-14, read before the invariant [code; inference from PR-035's counts]

PR-035 counted 23 to 31 "deep dives" on the last four Saturdays against a budget of 20: every
`score_history` row on Saturday from 12:25 IST, one per ticker. The deep dives are not the only
analyses that Saturday job makes. After the shelf it runs `run_paper_reviews`: every active idea's
weekly paper review is `run_daily_review(paper=True)`, which runs the analysis again
(`_run_todays_agent_scores` → `orchestrator.analyse`) unless the forecast's direction was right
and its error under 0.5%, and a new month's paper envelope is one more (`generate_forecast`).
Every analysis writes one `score_history` row (`BaseOrchestrator._record_score_history`, "the
one writer"). So the count was deep dives (at most 20, `run_deep_dives`'s bound) plus paper
re-runs of shelf ideas not dived that day: 29 on 14 Nov fits 20 dives and 9 paper re-runs of a
20-idea shelf. The deep-dive budget holds [code]; the invariant below is about it. The paper
reviews are a second, shelf-sized cost: at 45 ideas up to 45 more analyses a Saturday, and once
a month 45 envelopes. **Not yet read in production**: the check row `PR-037-W2` reads `budget.made`
and `paper.reviewed` from the run's own log line; B-14 closes when they add up to the
`score_history` count. Consequence for PR-035's numbers: its 38% yield of new dives stands (the
paper re-runs were counted as re-dives); its 46% of all dives and "38% of dives were re-dives"
are inflated by them.

## The cost, before the deploy (card step 3)

Unit costs are PR-035's read of 18 Nov (56 days): an analysis on Saturday from 12:25 IST, deep
dives and paper re-runs together, a mean **$0.0108**; a daily review a mean **$0.0156**. A month
is 52/12 = 4.33 Saturdays and 21 sessions. [inference: count × measured mean]

| | Today (20 dives, shelf 20, 40 reviews) | New (45 dives, shelf 45, 60 reviews) |
|---|---|---|
| Deep dives a week | 20 × 0.0108 = $0.22 | 45 × 0.0108 = $0.49 |
| Paper reviews a week, at most | 20 → $0.22 | 45 → $0.49 |
| Paper envelopes a month | 20 → $0.22 | 45 → $0.49 |
| **Saturday job, a month** | about **$2.1** | about **$4.7** |
| Daily reviews a month (PR-036's cap) | 40 × 21 × 0.0156 = $13.1 | 60 × 21 × 0.0156 = $19.7 |
| **Model cost a month, these jobs** | about **$15** | about **$24** |

At today's load (21 reviews a day) the daily reviews cost about $7 a month; they grow with the
holdings, not with this card. Run time [inference: PR-035's medians, 1.0 min a dive and 0.9 a
review, sequential]: 45 dives about 45 minutes and up to 45 paper reviews about 40, so Saturday's
12:30 job ends about 14:00-14:30 IST, well before the 17:45 IPO refresh (KT section 9).

## The shelf after two Saturdays (acceptance) [inference from PR-035's measured yield]

Assumptions: 38% of new dives end as an actionable BUY at 0.55 or more (PR-035, 113 dives over 8
Saturdays); about one idea a week leaves by a failed re-dive or by age (PR-035's "dropped"
column); today 20 active ideas, 4 of them held; the five unnamed ideas (B-13) are re-dived first,
which the room covers. The unknown is how many companies the screen's 60 offers past the dive
memo's 30 days, since no screen file was read.

| Run | New dives (screen allowing) | New BUY ideas | Active ideas after |
|---|---|---|---|
| Catch-up run after the deploy (about 8 re-dives due) | about 30 to 35 | about 11 to 13 | about 30 to 32 |
| First Saturday | about 15 to 30 (the memo now holds the catch-up's) | about 6 to 11 | about 35 to 42 |
| Second Saturday | about 15 to 30 | about 6 to 11 | **about 40 to 45** (the cap) |

Without the catch-up run the shelf is about one Saturday behind: about 35 to 42 after two.
PR-035's dates follow: 20 holdings about 5 sessions after the catch-up run and 25 about 10, at
5 new a day (PR-036), if the deposit is made.

## Tests

- **New `tests/unit/test_idea_supply_pr037.py`, 11 tests.** Shipped values read from
  `config.yaml` with a YAML parser, not through the settings module, and expected call lists
  worked out by hand from each fixture: the shipped values; the split of 45 (28; 30 without IPO
  candidates; never below 0); the card's Saturday (13 + 2 + 30, `budget` exact); a heavy week
  (28 + 2 + 15, the 7 least overdue deferred and named, and the first re-dives a week later);
  a short screen (the 7 take what is left, 42 calls); held ideas take no room; the docstring
  example at budgets 4, 6 and 2 (deferred, late, deferred) with a held idea and one without a
  close taking no room; no room keeps today's order; and a **120-trial property** over random
  budgets (0-50), floors (0-20), IPO candidates (0-2), shelves of up to 45 ideas (fresh, older
  than 30 days, never gated, sold, held, without a close), screens of up to 70 with funds,
  managed and recently dived stocks, random analyst failures, convictions and verdicts. It
  checks, against eligibility the fixture decides when it builds each symbol: calls never pass
  the budget and repeat no symbol; new companies get min(floor, eligible, budget − IPO calls);
  re-dives get min(eligible, room); no call unused while an eligible candidate waits; a re-dive
  past the room only once every eligible new company and IPO was called; every due re-dive
  reported once in its order, a deferred one never called; at most 45 ideas and 6 a sector key
  at the shipped values; a new idea only from its own answered dive, a BUY or STRONG BUY at
  0.55 or more; a re-dive that turns a stock down (below 0.55, or HOLD/SELL) removes it.
- **Mutants**, each applied alone to the code and run against the new file: no floor; the
  floor ignoring IPO candidates; the room ignored; a skipped re-dive using the room (the
  by-position defect); a call past the budget; late re-dives reported as deferred; late
  re-dives never reported; `hygiene.redive` unfiltered. **8 of 8 caught.**
- **Focused:** the new file 11 passed (10 s); with the ten files that run the cycle or
  `run_deep_dives` (`test_idea_supply_pr004`, `test_deployment_follows_money_fix025`,
  `test_discovery_cycle_ipo`, `test_scheduler_discovery_job`, `test_sector_naming_fix026`,
  `test_generic_evidence_fix030`, `test_surveillance_sector_fix011`,
  `test_operator_notices_owner_only_fix008`, `test_discovery_deep_dive`,
  `test_discovery_settings`), 339 passed before the new file was added.
- **Full suite** on `d6e5777`, in the checkout (its tree is the commit's; only the records file
  `STATE.json` differed, which no test reads for these values), without `-n`:
  `.stockai/bin/python -m pytest -q -p no:cacheprovider` → **6,820 passed / 12 skipped / 1
  xfailed / 0 failed**, return code 0, 5m49s (about 08:26-08:32 IST). PR-036's run counted
  6,809 passed; the 11 new tests make the difference.
- **Guards:** `scripts/docs/check_kt_docs.py` errors `[]`; `scripts/ci/check_broad_except.py` OK
  (148 grandfathered).

Environment: code-server, Python 3.13.5 (`.stockai`), `tests/hermetic.py` blocks every transport;
no `.env` read.

## Self-review (not the fresh review)

- The bound: `run_deep_dives` still adds a symbol to `attempted` before each call and stops
  calling once `len(attempted)` reaches the limit; held-back entries are examined again but
  never called past it. A failed call counts, in the budget and in the room.
- A due re-dive is never lost: one past the room is offered after the screen, and one not called
  this week stays due (`redive_due` reads the idea's dive date, which only a dive changes).
- Order: within the room, re-dives keep `redive_due`'s order (sold first, then unverified, then
  older than 30 days, each oldest first); the late ones keep it too.
- What a reviewer may weigh: (1) the floor's value (15) is provisional, as the card says; (2)
  `hygiene.redive` now names the re-dives offered within the room, called or skipped by rule, and
  no longer the deferred ones; (3) past the budget the loop now runs to the end of the list to
  report re-dives (a few dataframe filters, no call); (4) a held stock's idea is still listed under
  `hygiene.redive` while it takes no dive, as before (FIX-025).
- Not changed: the screen's signals and weights, the analyst's prompt, the 0.55 floor, sizing
  (the card's out of scope), and `redive_due`.

## Acceptance criteria

| Criterion | State |
|---|---|
| Settings and the budget split in place with tests as above; full suite and guards pass | Met (above) |
| A fresh-session review accepts it | **Met:** accepted 18 Nov 2026, [PR-037-review.md](PR-037-review.md) |
| The receipt states the weekly and monthly cost at the new settings, measured unit cost × count | Met (above) |
| The shelf's expected size after two Saturdays from the measured yield | Met (above, an inference with its assumptions) |
| KT section 8, PRODUCT_MAP and the testing guide describe the wider path | Met; the PDF is not regenerated with a story (AGENTS.md, owner's rule of 17 Nov) |
| Rollout at the owner's word: push before a Saturday run, then one catch-up run; a dated check row | Row `PR-037-W2` added; the push and the run wait for the owner's word (below) |

## Rollout, at the owner's word (given 19 Nov about 07:25 IST)

1. After the fresh review accepts `story/PR-037`, it stays on its branch until the owner's word,
   as PR-015's did: merging it into `main` would ship it with the next push. On the word, a
   session in a push window merges it, runs the full suite on the exact commit, pushes, and checks
   the deploy and `/health`.
2. **The catch-up run**, at the owner's word: `POST /discovery/run` (the Saturday job's entry
   point), on a weekday after the deploy, between 09:30 and 14:00 IST so it ends before the 16:30
   review. Its dives keep their day, so they are first offered at the review of the next
   session's close (a Thursday run, at Monday's run).
3. `PR-037-W2`: after the second Saturday run, read-only (STATE).

## Rollout, Thu 19 Nov: merged into `main`; the push waits for Fri 20 Nov 00:10

Autopilot `1119-0734-p1`, code-server, from about 07:34 IST (outside a push window), at the
owner's word of 19 Nov about 07:25 IST ("go ahead on pr 37"; STATE card `owner_word`).

1. **Merge** [code]: `git diff 3a59155..d6e5777 | sha256sum` printed `d24636e5…`, the reviewed
   digest. `story/PR-037` merged with `--no-ff` into `main` (`013c80f`) as **`ab18c77`**, with no
   conflict. Twelve of the thirteen files are byte-identical to `d6e5777`;
   `docs/TECHNICAL_DESIGN.md` auto-merged with `main`'s section 1 edits since `3a59155` and
   carries exactly the reviewed added and removed lines (compared line for line).
2. **Full suite on `ab18c77`** (a detached worktree, `.stockai/bin/python -m pytest -q`):
   **6,822 passed, 12 skipped, 1 xfailed, 0 failed** in 7 min 55 s (07:35–07:43 IST); the
   worktree stayed clean.
3. **The merges after it** [code, `git merge-tree`]: `story/PR-015` onto the new `main` still has
   the one known conflict, section 1's table (`main`'s "Idle cash" row against PR-015's "Idle
   cash" and "Exit rule" rows; keep both), and no new one. `story/PR-005` merges cleanly.
4. **Next:** the runner pushes the waiting commits from Fri 20 Nov 00:10 IST, after the full suite
   passes on the tip; the session after it checks the deploy and `/health`. After the deploy is
   SUCCESS, the first `continue` on a weekday 09:30–14:00 IST makes the catch-up run (step 2,
   first chance Fri 20 Nov) before its own phase. `PR-037-W2` keeps Tue 1 Dec if both happen by
   Fri 20 Nov; a later deploy moves it by as many weeks.
