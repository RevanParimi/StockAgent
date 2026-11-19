# PR-005 — fresh review receipt

**Story:** [PR-005](../stories/PR-005.md): an investment case for every position.
Implementation receipt: [PR-005-implementation.md](PR-005-implementation.md).

**Review context: fresh session.** Autopilot session `1119-0715-p1` on the code-server, a new
conversation opened with "continue", Thursday 19 Nov 2026 from about 07:15 IST, outside a push
window. The implementing session (`1118-0904-p6`) had ended at 05:18 IST. `main` = `origin/main`
= `3f26ae5` after a fetch. Production was not read. No model was called; nothing was pushed,
deployed, run or sent.

**Lane:** decision path, confirmed. The case's invalidation price is what the evidence exit rule
sells on, and PR-015 switches that rule on.

**Verdict: CHANGES REQUESTED** for `4407b13`. One medium finding (M1) leaves an acceptance
requirement of the card unmet: a case written after the buy can store its invalidation price
outside the buy day's price basis, so the evidence rule loses the sale the shelf rule makes today.
Four low findings (L1 to L4) are cheap and are asked for in the same phase. The at-purchase paths
(a SWITCH buy, a deployment buy, a manual add dated today) are correct as reviewed.

## Review input, verified

| Check | Result |
| --- | --- |
| Branch | `story/PR-005` = `4407b13`, one commit on `f5eefa3` (`git merge-base main story/PR-005`) |
| Diff digest | `git diff f5eefa3 4407b13 \| sha256sum` = `ef61b3609e06b9cb…` = the implementation receipt |
| Files | the receipt's 18 paths, +2206 / −45 |
| Where it ran | a detached worktree of `4407b13` in the scratchpad; pytest's `pythonpath` puts the worktree first |
| Merge | `git merge-tree main story/PR-005`: clean. Against `story/PR-015`: one conflict, `docs/TECHNICAL_DESIGN.md` (both edit KT section 6) |

## Contract checked

The card's intended result, its acceptance criteria, both routed inputs (RR-L1 and T1; the owner's
decision of 24 Oct on the invalidation price), its hard-review questions and the receipt's eight
decisions. I traced a buy from `execute_advice` through `write_for_trades`, `write_for_buy`,
`read_inputs`/`build_bundle`, `check_model_case`, `purchase_invalidation`
(`level_in_basis`, the window) and `CaseStore.append`, and the stored case back through
`EvidenceReader.read`, `exit_evidence`, `level_after_buy` and `case_broken_reasons`; the manual add
route; `review_pillars` in the pipeline; `backfill` and its script; `GET /portfolio/cases`.

- **At purchase.** Every input is filtered by the buy session's 15:30 clock (analysis `run_at`,
  idea `decision_time`, dossier guidance by date, events by `published_at`). The level goes
  through the dive-to-buy part of `level_in_basis` with RR-L1's refusals; T1 is pinned. The window
  matches the card (above the stop, at or below `entry × (1 − 1.5 × ATR%)`), with the stop as the
  advisor computes it (mid bucket; the pipeline passes no market cap). One version 1 per holding:
  the store's version check runs under a file lock, so a re-run, a retry or a concurrent writer
  writes none. A failure never undoes a trade.
- **After the buy.** `level_after_buy` divides only by the holding's applied bonuses and splits
  after the buy; the sync never applies an action ex on the buy day (`corp_actions`: `ex <= buy`
  is skipped), so a buy-day split cannot be applied twice.
- **Pillars.** A challenge is recorded beside the evidence and never sells; only
  `CASE_EVENT_SOURCES` reach `case_broken`. Each event is read once.
- **Access.** `GET /portfolio/cases` builds the store from the signed-in user's id only; a symbol
  outside `[A-Z0-9&_.-]{1,20}` is a 422, so no path leaves the user's folder.
- **The model's words** move no money: prices and dates are code's. The figure check is exact
  (no rounding, no conversion) and per cited input, except L1.

**The receipt's decisions.** Agreed: 1 (a filing is not narrowed to pillars until PR-013
measures it), 3, 4, 5, 6, 7, 8, and the manual add's `as_of` at the time it is written (the
member decides then; nothing after that time is cited). Decision 2 (a case without a price is not
replaced by the shelf's level) is right for a level the window or RR-L1 refused, and wrong for a
read that failed: see L4.

## Findings

| # | Severity | Where | What |
| --- | --- | --- | --- |
| M1 | Medium, decision path, latent | `core/portfolio/cases.py` `backfill` (`entry_price=h.adj_avg_price`) and `purchase_invalidation` (a dive after the buy day) | A case written after the buy can store its price outside the buy day's basis |
| L1 | Low, words only | `cases._FIGURE_RE` | "₹1.5 lakh crore" and "₹1.5 lakh" read as the same figure |
| L2 | Low, rollback | `core/portfolio/pipeline.py` (the `CaseStore` given to `EvidenceReader`; `review_pillars`) | `advisor.case_write: false` leaves stored prices selling and pillar versions being written |
| L3 | Low, tests | `test_investment_case_pr005.py` | Four issue-time edges are right in the code but unpinned |
| L4 | Low, decision path | `exit_shadow.exit_evidence` (decision 2) with `purchase_invalidation` | NSE's list unread at the buy removes the price trigger for the holding's life |

**M1.** Two ways, both reproduced (RV1, RV2 below):

- **The backfill's entry is in today's basis.** `backfill` passes `adj_avg_price`, which the sync
  divides by every bonus or split after the buy, as the buy day's entry; the level is in the buy
  day's rupees. Example: bought 23 Oct at ₹212, level ₹200 (dived 17 Oct), ATR 2%, stop 12%: the
  window is (₹186.56, ₹205.64] and ₹200 is inside. A 1:1 bonus goes ex 2 Nov (cost ₹106). The
  backfill on 13 Nov sets the window from ₹106 (stop ₹93.28, noise line ₹102.82), refuses ₹200 as
  "above the noise line", and records `entry_price` 106. With no price, and the shelf's level not
  used (decision 2), a close of ₹99 on 13 Nov sells nothing. The shelf rule that runs today reads
  ₹200 ÷ 2 = ₹100 and sells there (RV0).
- **A dive after the buy is stored unconverted.** `_idea_before(…, as_of=now)` picks the newest
  dive, which for a backfill or a manual add dated in the past can be after the buy.
  `purchase_invalidation` then calls `level_in_basis` with `on` = the buy day and no applied
  actions, so the dive's own rupees come back unchanged and are stored as "the buy day's rupees".
  `level_after_buy` divides them again. Example: re-dived 7 Nov after the bonus at ₹100 (₹200 in
  the buy day's rupees). The case stores ₹100; on 13 Nov the level reads ₹50, not ₹100, and the
  close of ₹99 sells nothing.

The card asks that the price be "stored in the buy day's price basis" and "never the dive's raw
level", with the window measured from the entry (the owner's decision of 24 Oct). The error is
always downward, so it never sells by mistake; it removes the evidence rule's only price trigger.
**What it costs:** a ₹3,20,000 position (PR-036's size) whose level is 5.7% below cost then falls
to the 12% stop instead: about 6.3%, **about ₹20,000 per holding affected**. Latent: it needs the
backfill (at the owner's word) or a past-dated manual add, and a bonus or split between the buy
and the case, or a re-dive after the buy.

**Asked for (the implementer chooses how):** the backfill's entry in the buy day's rupees
(`adj_avg_price` times the ratios of the share-count actions the holding applied after the buy);
a dive after the buy day either converted back to the buy day's basis (times the applied ratios
in (buy, dive], and refused on any basis change, registry break or unread row in that span) or
refused with a gap that says so; the same rule for the expectation's price target. RV1 and RV2
then pass.

**L1.** Only the first unit word after a figure is read, so a fact "AUM of ₹1.5 lakh" passes
against "AUM of ₹1.5 lakh crore" (10⁷ apart). This is the card's question "can a number be
laundered through units?". Pillar words move no money, but the portfolio screen will show them
(PR-010). Read "lakh crore" (and "thousand crore") as their own units (RV3).

**L2.** The card's rollback is "stop writing cases; stored cases stay as history". With
`case_write: false` the pipeline still hands the case store to the evidence rule, so a stored
case's price keeps deciding sales, and `review_pillars` keeps appending versions. Rolling back
should return the evidence rule to the shelf's level and stop the pillar versions (or a second
setting does it); the KT's rollback line then says which.

**L3.** Four of my 12 mutants survived the story's tests while the code is right at each edge:
an analysis run exactly at `as_of` (`>=` to `>`); an idea dived on the buy day, decided at
exactly the 15:30 clock (`>=` to `>`; real once PR-037's weekday catch-up run dives on a buying
day); a pillar event published exactly at the review close (`<` to `<=`); the evidence reader
without `before=` (a version written after the close read for that day). REVIEW.md asks for
issue-time invariants: pin each. (A fifth survivor, a buy-day action applied after the buy, is
equivalent: the sync never applies one.)

**L4.** `fetch_corp_actions` returns `[]` on any failure, so a failed NSE read at about 16:45 on
the buy day gives the case no price ("NSE's list … is empty or was not read"), for the life of
the holding: the backfill skips a holding with a case, and decision 2 stops the shelf's level.
The shelf rule re-reads NSE every review day and recovers the next day. Ask: for a gap that is a
failed or short read (not a window or RR-L1 refusal), the evidence rule falls back to the shelf's
level as PR-009 reads it, or the case's price is retried on a later review day as a new version.

## Reviewer cases and mutants

`analysis_data/pr005_review/test_rv_pr005.py` (ignored; sha256 `bfcd8c51051d3494…`), copied
into `tests/unit/` of the worktree: **4 passed, 3 strict xfail**. Each expected value is worked by
hand in the file's docstrings.

- RV0, controls that pass: the backfill without a bonus uses ₹200 and ₹199 breaks the case; the
  shelf rule sells at ₹99 after the bonus; a deployment buy written by `write_for_trades` at the
  15:30 clock is read back by `EvidenceReader` through the `CaseStore` on 13 Nov (₹199 breaks,
  ₹200.50 does not); crore against rupees is caught.
- RV1 (M1, backfill entry): xfail — "level 200.00 not used: above the noise line 102.82 …
  below the entry 106.00".
- RV2 (M1, dive after the buy): xfail — the level reads 50.0.
- RV3 (L1): xfail — `ungrounded("AUM of Rs 1.5 lakh", "AUM of Rs 1.5 lakh crore") == []`.

When M1 and L1 are fixed the three turn into strict XPASS failures; the next reviewer removes the
marks. Mutants (script in the session's scratchpad, 12 single-line changes run against
`test_investment_case_pr005.py` and `test_exit_evidence_pr009.py`): 7 caught (both window edges,
the no-price fallback, a case for an ADD, the `written` label, RR-L1 at purchase, the news
challenge), 5 survived (L3).

## Commands and results

- `pytest -q tests/unit/test_investment_case_pr005.py tests/unit/test_exit_evidence_pr009.py
  tests/unit/test_exit_fix016.py`: 209 passed (13 s).
- Related suites, the 40 test files that name `exit_shadow`, `execute_advice`, `portfolio_api`,
  `run_post_review_pipeline` or `cases`: 2,011 passed (1 min 53 s).
- `scripts/ci/check_broad_except.py`: OK (148 grandfathered). `scripts/docs/check_kt_docs.py`:
  errors `[]`.
- **Not run:** the full suite on `4407b13` (the verdict asks for a new revision; the implementer
  ran it: 6,852 passed); a browser check (no screen changed); production (not read).

## Acceptance checklist

| Criterion | Verdict |
| --- | --- |
| A fixture case holds only bundle figures; an invented number stores the deterministic case | Met, except L1 |
| No input dated after the case's creation (FIX-004) | Met; L3's edges unpinned |
| Each buy path writes one version 1; a re-run writes none | Met |
| A contradicting event challenges the matching pillar and cites it; news never sells | Met |
| A backfilled case is `after_purchase` | Met |
| A member reads only their own cases | Met |
| Routed: the price in the buy day's basis, never the dive's raw level; the window from the entry | **Not met for a case written after the buy (M1)** |
| Routed: RR-L1 fixtures each side; T1 pinned; converted once | Met |
| Living documents (KT 3, 4, 6, 11; CODEBASE; AUTOPILOT_GUIDE; guide case 07-U) | Met for what was built; the fix updates KT section 6's backfill and rollback lines |

## Decision and follow-up state

**Changes requested.** PR-005 returns to implementation on `story/PR-005`: M1 (required), with
L1 to L4 in the same phase (a phase that leaves one out records it as a BACKLOG entry with its
trigger). It stays decision path, so the new revision needs another fresh review. Nothing merges
into `main` and the backfill does not run until then. After PR-015 merges, `story/PR-005` meets
one documents conflict in KT section 6: keep both texts.

## Second fresh review, 19 Nov: `bc82a06` accepted

**Review context: fresh session.** Autopilot session `1119-0826-p6` on the code-server, a new
conversation opened with "continue": started 08:26 IST, held by usage limits, working from about
09:57 IST, outside a push window. The fix phase (`1119-0805-p4`) had ended. `main` = `508c391`,
`origin/main` = `3f26ae5` after a fetch. Production was not read. No model was called; nothing
was pushed, deployed, run or sent.

**Lane:** decision path, confirmed (the case's invalidation price is what the evidence exit rule
sells on).

**Verdict: ACCEPTED** for `bc82a06`. M1 and L1 to L4 are resolved as asked. No critical, high or
medium finding. Two low findings go to BACKLOG (B-16, B-17).

### Review input, verified

| Check | Result |
| --- | --- |
| Branch | `story/PR-005` = `bc82a06`, parent `4407b13`; `git merge-base main story/PR-005` = `f5eefa3` |
| Fix digest | `git diff 4407b13 bc82a06 \| sha256sum` = `fe95cfb800bd2ba7…` = the implementation receipt; 11 files, +637 / −65 |
| Story digest | `git diff f5eefa3 bc82a06 \| sha256sum` = `5f7816f502ad50c3…` |
| Where it ran | a detached worktree of `bc82a06` in the session's scratchpad |
| Merge | `git merge-tree main story/PR-005`: clean |

### Contract checked: the first review's asks

- **M1, the backfill's entry.** `buy_day_entry` multiplies the adjusted cost by the ratio of each
  bonus or split the holding applied after the buy. The sync divides the cost by exactly those
  (`apply_actions_to_holding`: `buy < ex <= today`), so the product undoes them. RV1 passes. With
  an ADD the merge keeps the first buy date and averages in today's rupees, so the entry is the
  holding's blended cost in the buy day's rupees, the cost the stop is measured from (RV6).
- **M1, a dive after the buy.** `level_at_buy` multiplies the level back by each bonus or split ex
  in (buy, dive], from the holding's applied actions and NSE's list, keyed. I checked that the
  union cannot count one action twice: NSE's parsed rows (`ActionRecord.actions`) are the same
  `parse_action` objects the sync applies (`_read_ratio` only filters), with the same key
  (`symbol|ex|desc[:40]`), and `setdefault` keeps the holding's own. A row NSE lists in (buy, dive]
  that the holding has not applied yet is applied by the next sync, which runs before that day's
  evidence; a row the sync applied but `_read_ratio` refuses is in `unparsed`, so both
  `level_at_buy` and `level_after_buy` leave the price unused. RV2 passes. The expectation's
  target goes through the same function.
- **L1.** "lakh crore", "lakh Cr", "lacs crores" and "thousand crore" are units of their own.
  RV3 passes. A hyphen between the words is not read (N2).
- **L2.** With `advisor.case_write: false` the pipeline builds no case store: `EvidenceReader`
  gets `cases=None` and reads the shelf idea's level; the retry and the pillar review do not run;
  `write_for_buy` returns before writing for a SWITCH, a deployment buy and a manual add.
  `GET /portfolio/cases` only reads.
- **L3.** The four issue-time edges are pinned in the story's tests.
- **L4.** `read_gap` is set for an empty, failed or short NSE list and for an unknown ATR, never
  for a refusal by the window or the basis rules. `retry_invalidation` runs after the review's
  trades, from the case's own level, dive day, buy day and entry, with the ATR to the buy day;
  a result that settles is a new version, read from the next review day (`EvidenceReader`'s
  `before=`). A retry keeps `written`, `as_of`, the pillars and the business conditions, and
  names the change.

The card's hard-review question "can the case be written after the fact and look original?" now
holds for prices too: a backfilled price equals the price a case written at purchase holds, and
`written: after_purchase` still says when it was written.

### Reviewer cases, worked by hand

`analysis_data/pr005_review/test_rv2_pr005.py` (ignored; sha256 `d11fc47f93d1b25e…`), copied into
`tests/unit/` of the worktree: **303 passed, 1 strict xfail**. The first review's file
`test_rv_pr005.py` with RV1 to RV3's marks removed (sha256 `f6de436cfa8ffaaf…`): **7 passed**.

- **RV4 (L4 with a bonus):** a deployment buy on 23 Oct at ₹212 with NSE's list unread; a 1:1
  bonus ex 26 Oct, applied by that day's sync. The retry on 26 Oct stores ₹200 (not ₹100) with the
  window ₹186.56 / ₹205.64; on 27 Oct the case reads ₹100, as the shelf rule does; ₹99 breaks the
  case, ₹101 does not.
- **RV5 (backfill, a re-dive between two actions):** a 1:1 bonus ex 2 Nov, a re-dive on 7 Nov at
  ₹100, a ×5 split ex 10 Nov, cost ₹21.20. Entry ₹212, price ₹200 (×2 for the bonus only), ₹20
  on 13 Nov, the shelf rule's ₹100 ÷ 5; ₹19.90 breaks, ₹20.10 does not.
- **RV6 (an ADD, observation):** 10 at ₹212, a 1:1 bonus, 20 more at ₹100: cost ₹103, ₹206 in
  the buy day's rupees; stop ₹181.28, noise line ₹199.82; ₹200 is not used (noise side).
- **RV7 (property, 300 seeds):** random bonuses and splits from 1 Sep to 13 Nov, a dive before or
  after the buy: the case's level on 13 Nov equals the dive's level divided by every ratio ex
  after the dive (worked independently of the code), and equals PR-009's shelf reading.
- **RV8 (N2):** strict xfail: "₹1.5 lakh" passes against "₹1.5 lakh-crore".

### Mutants

16 single-line changes to the fix (script in the session's scratchpad), each run against the
story's own `test_investment_case_pr005.py` and `test_exit_evidence_pr009.py`: **13 caught**
(the buy-day action in the entry; coverage to the dive; the dive-day check; the registry check;
the level not put back; the backfill's applied actions; a short read appended; a failed read never
retried; an unknown ATR not a read gap; the retry's ATR to the retry day; the retry not called;
the rollback keeping the store; two-word units off). **3 survived:** the retry's entry taken from
today's cost and the retry without the applied actions (N1; RV4 catches the first); an applied
demerger ignored when a later dive is put back, which is equivalent, since `level_after_buy`
leaves the price unused for any applied demerger after the buy.

### Findings

| # | Severity | Where | What | Disposition |
| --- | --- | --- | --- | --- |
| N1 | Low, tests | `core/portfolio/cases.py:978-979` (`retry_invalidation`) | The retry's entry (`case.entry_price`) and applied actions are right but unpinned: a mutant that works the retry from today's cost, M1's own error, passes the story's tests | BACKLOG B-16 |
| N2 | Low, words only | `core/portfolio/cases.py:100` (`_FIGURE_RE`) | "₹1.5 lakh-crore" is read as "1.5 lakh", so a fact "₹1.5 lakh" passes against it; "trillion" and "k" are not units either | BACKLOG B-17 |

**N1, what it would cost:** nothing today; the code is right. A later edit that took the entry
from the holding's cost would refuse ₹200 after a bonus, as M1 did: about ₹20,000 on a
₹3,20,000 holding whose case waited on a retry. RV4 is the test to copy.

**N2:** pillar words move no money; PR-010 will show them on the portfolio screen.

### Commands and results

- `pytest -q tests/unit/test_investment_case_pr005.py tests/unit/test_exit_evidence_pr009.py
  tests/unit/test_exit_fix016.py`: 234 passed (9.0 s).
- Reviewer cases: as above.
- **Full suite on `bc82a06`** (the worktree, without `-n`): 6,877 passed / 12 skipped / 1 xfailed / 0 failed
  (6m08s, about 10:07-10:13 IST; `node_modules` linked, so the two browser files ran).
- **Merged into `main` as `40d04d5`** (`git merge --no-ff`, no conflict): each of the 18 files
  carries exactly the reviewed added and removed lines; 5 also hold `main`'s own later edits.
  **Full suite on `40d04d5`** (a detached worktree): 6,890 passed / 12 skipped / 1 xfailed / 0
  failed (6m12s, about 10:13-10:20 IST).
- `scripts/ci/check_broad_except.py`: OK (148 grandfathered). `scripts/docs/check_kt_docs.py`:
  errors `[]`.
- **Not run:** a browser check (no screen changed); production (not read); the model (stubbed).

### Acceptance checklist

| Criterion | Verdict |
| --- | --- |
| A fixture case holds only bundle figures; an invented number stores the deterministic case | Met (N2 is a low gap in units) |
| No input dated after the case's creation (FIX-004) | Met; L3's edges pinned |
| Each buy path writes one version 1; a re-run writes none | Met |
| A contradicting event challenges the matching pillar and cites it; news never sells | Met |
| A backfilled case is `after_purchase` | Met |
| A member reads only their own cases | Met |
| Routed: the price in the buy day's basis, never the dive's raw level; the window from the entry | Met, also for a case written after the buy (RV1, RV2, RV4, RV5, RV7) |
| Routed: RR-L1 fixtures each side; T1 pinned; converted once | Met |
| Rollback: stop writing cases; stored cases stay as history | Met (L2) |
| Living documents (KT 3, 4, 6, 11; CODEBASE; AUTOPILOT_GUIDE; guide case 07-U) | Met; KT section 12's row reads Done with the records commit |

### Decision and follow-up state

**Accepted.** PR-005 is `done`, merged into `main` as `40d04d5`. Not pushed (outside a window): it
ships with the next push, from Fri 20 Nov 00:10. Production verification:
`pending_deployment`; after the deploy, `PR-005-W1` reads the first cases written at purchase.
The backfill runs once at the owner's word after the deploy (the implementation receipt,
"Rollout and rollback").

**For PR-015's merge tonight** (`git merge-tree main story/PR-015` on `40d04d5`): three conflicts,
all in `docs/TECHNICAL_DESIGN.md`. Section 1's table: keep `main`'s "Idle cash" row and PR-015's
"Exit rule" row. Section 4's company-events paragraph: PR-015's sentence on the evidence rule,
then `main`'s "The investment case reads it to challenge a holding's pillars (section 6)" and
"**Planned:** PR-007, PR-008". Section 11: `main`'s "Own a stock for a reason" bullet (PR-005 is
built) and PR-015's "Sell on evidence" bullet.
