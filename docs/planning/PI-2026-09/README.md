# PI-2026-09 — trustworthy decisions and measurable adaptation

The [September 10 audit](../../audit/2026-09-10-repository-production-review.md) found real adaptation but no demonstrated benefit, compromised evaluation semantics and concrete operational/security defects. This PI repairs the decision/evaluation contract before adding intelligence complexity.

**Start/resume:** [HANDOFF.md](HANDOFF.md) → [STATE.json](STATE.json) → selected story. On September 15 the user explicitly requested [DOC-001](stories/DOC-001.md), current-code KT plus a separate human testing guide, ahead of SA-001. After DOC-001 acceptance, the first remediation implementation is SA-039 (learning containment, promoted by the owner on 2026-09-23), then SA-001. No remediation is claimed complete by the documentation refresh.

## Scope and outcomes

1. Recommendations and adaptive updates require identifiable, fresh essential evidence. Unsafe chat rendering is closed and tested.
2. Every eligible suggestion has a frozen issuance record and a correctly timed outcome. Updates are idempotent and mathematically bounded.
3. Weekly, fortnightly and monthly reports compare equivalent completed cohorts, include unfavorable/missing cases and expose uncertainty and baselines.
4. Adaptation and lesson promotion require predeclared prospective evidence. A valid result of this PI can be **no demonstrated benefit**; the engineering plan cannot guarantee stock-picking improvement.
5. Delivery, backup, scheduler and incident handling have observable outcomes and recovery checks. Consolidation removes measured duplication rather than introducing a new platform.

“Fortnightly” means a declared 10-trading-session comparison, displayed with actual calendar dates. Weekly reporting must similarly define its exchange-session boundaries. These are evaluation cohorts, distinct from a two-calendar-week development sprint and from each forecast's holding horizon.

## Sprint sequence

Planning assumption: six two-week sprints, one story implementation and a separate review conversation at a time. Start dates and team capacity are not known; these are relative sprints, not promised calendar deadlines. Estimates are relative, provisional points; re-estimate after Sprint 1. Do not expand a story just to meet a point budget.

| Sprint | Objective | Planned points | Exit evidence |
|---|---|---:|---|
| 1 | Learning containment first; security, honest health, action gating, scheduler counts, clean CI; dependency lock, provider-credit alerts, job outcomes, source health, outside witness, milestone hygiene, off-site backup | 41 | Contained learner leaves stored weights untouched and decisions on defaults; browser exploit fixture inert; no-data action/update blocked; counts reconcile; clean Python-3.11 CI baseline |
| 2 | Delivery, instrument/store identity, benchmark correctness, incident registry; silent-degradation watchdog, deploy hygiene, read-only ops status; same-industry peers; one sizing rule for every autopilot buy; the portfolio against the Nifty | 35 | Mock transport/recovery tests, real verification tracked separately, reviewed migration manifest, correct provider arguments; no stock valued against another sector's peers |
| 3 | Learning target, immutable issuance, correct dark grading, atomic bounded updates; sector lenses; trading costs and tax in paper P&L; idle cash put to work in normal markets | 31 | Independent numeric/time fixtures; old outcome cannot be regraded with today's decision; crash/retry invariants pass; every managed ticker resolves to one lens with frozen store keys |
| 4 | Identifiable credit, historical lineage, complete monthly and weekly/fortnightly cohorts; computed factors, text reader and pooled shadow learner (all shadow) | 29 | Hand-reconciled forecast/outcome IDs and denominators; exited calls retained; wrong-roster history excluded explicitly; factors reproducible and cutoff-safe; the shadow learns beside the defaults while stored weights stay untouched |
| 5 | Effective samples, calibration, prospective experiments with the observe-exit gates, lesson probation, honest evidence UI; factor-engine decision and shadow comparison | 24 | Reviewed experiment protocol and deterministic end-to-end experiment; engine-vs-analyst paired report; sufficient market evidence may still be pending |
| 6 | Actual call accounting, retirement of the sector packages and fallback after the engine switch, runtime recovery, current docs | 11 | Cost counts reconcile, owner-loss recovery test, accepted operator documentation |
| Stretch | Packaging/client build, Atlas projections, comprehensive public-read policy | 11 | Separate capacity/product decision; not selected automatically by “continue” |

The 48 planned stories total 171 points; three stretch stories total 11. Six planned stories (SA-033–SA-038) were added on 2026-09-23 from the [production assurance review](../../audit/2026-09-23-production-assurance-review.md), and SA-007 moved to Sprint 1. Later that day the owner split SA-003's learning containment out as SA-039 (P0, 3 points, first in order), and SA-003 went from 5 points to 4. On 2026-09-24 the owner adopted the [production observability design](../../superpowers/specs/2026-09-24-production-observability-design.md). It adds SA-040 (source health), SA-041 (read-only ops status) and SA-042 (an outside witness on Healthchecks.io, alerting by Telegram), widens SA-034 (5 → 6 points) and SA-036 (3 → 4), and amends SA-035. The design keeps to this PI's small-service rule: no Prometheus, OpenTelemetry SDK or Arize. The one outside service is a free witness, justified by a measured nine-week email outage that nothing detected. On 2026-09-26 the owner adopted a rule for leaving SA-039's `observe` mode. SA-043 (Sprint 3, 3 points) runs a shadow learner that starts from the default weights and records paired default/shadow decisions. SA-022 is amended with predeclared gates: at least 100 effective disagreements over at least 3 months and 3 sectors, with the shadow right on at least 60%, wins that are consistent and robust to dropping the best sector, and sane weights. Promotion resumes from the shadow's weights, never the stored pre-fix weights. Later that day the owner adopted the [one-engine design](../../superpowers/specs/2026-09-26-one-engine-sector-lenses-design.md), which retires the per-sector graphs. Sector knowledge becomes lens YAML. Five computed factors and one LLM reader (with a computed Catalyst) replace five scoring schemes. The LLM explains but does not decide, and learning uses six pooled factor weights. It adds SA-044 (peer fix), SA-045 (factors), SA-046 (reader) and SA-047 (decide, shadow and switch on non-inferiority). SA-026 becomes the lens story (Sprint 6 → 3), SA-043 moves to Sprint 4 on the factors, and SA-027 retires the packages after the switch. On 2026-09-27, after reviewing the live portfolio screen (81% cash, 2 holdings, a flat total return with nothing to compare it with), the owner added SA-048 (costs and tax in paper P&L), SA-049 (put idle cash to work in normal markets; hold cash on purpose only in a crisis), SA-050 (one sizing rule for every autopilot buy) and SA-051 (the portfolio against the Nifty, with honest labels). Sprint 1 is heavy at 41 points, so re-estimate after it. Dependencies, not numbering alone, determine readiness. Security/privacy issues newly discovered during any story take priority over this provisional order. Production incidents may justify resequencing, recorded in STATE.json with the reason.

## Product results track (added 2026-10-11)

On 2026-10-11 the owner asked for a deep product review: losing sales, code-like reasons, the
models, a portfolio of only 2 stocks, a jargon-heavy UI and a repetitive morning brief. The
[product results review](../../audit/2026-10-11-product-results-review.md) traced each one to its
mechanism and added the stories below. It also moved SA-048 to SA-051 forward and amended SA-049
with the owner's breadth floor: at least 10 holdings and ₹10 L invested, configurable.
FIX-007, a privacy defect found on the way, is ordered first under the rule that security and
privacy findings take priority. In STATE order the block follows SA-011, so it is selected before
the remaining SA stories. The review explains the trade-off. FIX-008, added on 2026-10-12 at the owner's request, follows FIX-007 under the
same rule: operator notices go to the owner alone, then the backlog's watchdog entry is
registered. FIX-009, added on 2026-10-13 from FIX-008's review (finding L2; the owner delegated the call), follows
FIX-008 under the same rule: an index-change notice tells each account only about stocks it holds or
watches, plus shelf ideas. It is 1 point and can ship in one deploy with FIX-008.
FIX-010, added on 2026-10-15 from PR-001's re-review (finding U1; the owner: "add the score-history fix
before PR-002"), comes directly before PR-002. In production the score history holds no rows
(nothing has written it since April), while 1,082 analyses were logged elsewhere, so member
screens show no real analysis state. Every analysis writes it again, and screens that list
stocks name only the viewer's own, the managed tickers and shelf ideas.
FIX-011, added on 2026-10-20 from PR-004's implementation (found on the way; routing delegated by
the owner on 2026-10-13), comes directly before SA-049. NSE's per-symbol meta API answered 404 when
probed on 2026-10-20, so the screen's surveillance (ASM/GSM) and suspension guards test nothing,
and no stock outside the registry gets a real sector. SA-049 buys shelf ideas with idle
cash, so the guards should work first.
FIX-012, added on 2026-10-22 after the PR-004 and PR-006 push (the owner: "ya go ahead"),
comes first in the remaining queue. CI's Linux suite has failed on every push since 13 Oct:
FIX-007's route guard walks `app.routes`, and FastAPI 0.137.0 and later keep included routers
as wrappers, so the guard finds no route. While CI is red, a new regression cannot be told
apart from the known failure. It is test-only; pinning FastAPI belongs to SA-033.
FIX-014, added on 2026-10-23 from PR-011’s fresh re-review (routing delegated by the owner on
2026-10-13), comes after PR-012. Above 75% promoter holding, discovery drops promoter-group sales
but keeps purchases, so a purchase and a sale through the market score as a purchase. No company
showed this on 23 Oct; it moves ahead if guide case 06-I finds one.
FIX-015, added on 2026-10-23 while implementing PR-009 (routing delegated), comes after FIX-014.
The advisor's `shock_reforecast` exit compares a stored sentence with trigger keys, so it has never
fired. Fixing it must not count a thesis-break re-forecast, or the price-path exit would return
inside the evidence rule. It moves ahead before the owner switches `advisor.exit_rule` to evidence.
FIX-016 and PR-013, added on 2026-10-24 from the owner's walkthrough of PR-009 (the owner: "i go
with the recommendations"), close weaknesses of the evidence exit. FIX-016 comes directly after
PR-009, and PR-009's push waits for it, so the switch gate is still fixed before any shadow row
exists. A SELL verdict counts only when it is fresh and after the buy, a news article never sells
alone, each decision is graded against where the money went (cash or the Nifty), and the gate adds
a money check: "not worse" in count and in money. PR-013 follows PR-005 and reports the average
loss by exit reason, the fall the evidence rule sits through and the decision pace. PR-005 (5 → 6
points: the invalidation price's basis and bounds) and PR-012 (2 → 3 points: label accuracy for
event reading) grew with routed inputs, and SA-049 gained a routed note.
FIX-017, added on 2026-10-29 from FIX-016's fresh re-review of rework 2 (routing delegated),
comes after FIX-015. The live holding sync reads some of NSE's own rows wrongly: a bonus of
preference shares or debentures as an equity bonus, a bonus-and-split row as its bonus alone,
a split in NSE's short wording not at all, and it asks NSE under the app's code, so two
registry aliases get no row. A holding can then show a false gain or a false fall, and a stop
can sell it. It moves ahead if a held stock lists such a row.
FIX-018 and FIX-019, added on 2026-10-29 from the owner's decision on FIX-016's open question
RW2-D6 ("go ahead on your recommendation"). FIX-018 comes directly after FIX-016, and PR-009's
push now waits for both. A decision whose result can never be known, such as a demerger between
its closes or a stock NSE lists nothing for, would otherwise fail the switch gate for good. It is
set aside and named on the scorecard; at most 2 decisions and 10% may be set aside before the
gate says "cannot judge". FIX-019 follows: 14 configured codes got an empty NSE
corporate-action list on 29 Oct, and the stale ones are mapped with evidence.
FIX-020, added on 2026-10-30 from the owner's answer to FIX-019's question Q2 ("do as per
recommendation"; routing delegated), comes after FIX-017. Seven configured codes are not NSE
codes, so the app has never priced them. NIIT, in the enabled IT sector, is one of them. FIX-020
corrects them in the sector list. APL is APL Apollo Tubes, decided the same day under the
owner's delegation, by its configured sector (metals). FIX-020 also moves AAVAS, a
housing-finance company, out of chemicals.
FIX-021, added on 2026-10-31 from Serper's email of 30 Oct (routing delegated), comes directly
before SA-048. Since 30 Oct, Serper returns every link after a search's top 3 as a google.com
redirect, `/news` included: 5 of the 31 news events stored on 30 Oct carry one. A news event is
keyed by its link, so an article at rank 2 one run and rank 4 the next would be stored twice.
FIX-021 drops a redirect link where Serper is read, so the article is skipped and counted. It
goes first because every run until then can store such rows, and they stay.
FIX-022, added on 2026-10-31 from SA-048's fresh review (routing delegated), comes after
FIX-020 at the end of the routed queue. The tax estimate takes a position's average cost where
the law takes each lot's own, so a sale of long-term and short-term shares bought at different
prices can read ₹0 where the law gives ₹4,160. FIX-022 takes each lot at its own cost, makes a
CSV import with a missing rate write nothing, and lets a renamed position keep its buy charges
and dates.

| Order | Story | Priority | Points | Result | Dependencies |
|---:|---|---|---:|---|---|
| 1 | [FIX-007](stories/FIX-007.md) | P1 | 1 | Server logs readable only by the owner | — |
| 2 | [FIX-008](stories/FIX-008.md) | P1 | 2 | Operator notices reach only the owner; then register the backlog's watchdog entry | SA-011 |
| 3 | [FIX-009](stories/FIX-009.md) | P2 | 1 | Index-change notices name only the account's own stocks | — |
| 4 | [PR-001](stories/PR-001.md) | P0 | 3 | Remove invented figures and fixed demo values; hide operator tools from members | — |
| 5 | [FIX-010](stories/FIX-010.md) | P0 | 3 | Every analysis writes the score history again; screens name only the viewer's stocks | — |
| 6 | [PR-002](stories/PR-002.md) | P1 | 3 | A weekly results scorecard with a "sold too early" check | — |
| 7 | [PR-003](stories/PR-003.md) | P1 | 2 | Fresh overnight news: no repeats, published-date freshness, global cues | — |
| 8 | [SA-050](stories/SA-050.md) | P1 | 3 | One sizing and entry rule for every autopilot buy, against the whole portfolio | — |
| 9 | [SA-051](stories/SA-051.md) | P1 | 3 | The portfolio against the Nifty, with honest labels | — |
| 10 | [PR-004](stories/PR-004.md) | P1 | 3 | Enough researched ideas to fill 10+ positions | — |
| 11 | [PR-006](stories/PR-006.md) | P1 | 3 | A daily company-event feed for held, watched and shelf stocks | — |
| 12 | [FIX-012](stories/FIX-012.md) | P1 | 1 | CI is red since 13 Oct: make FIX-007's log-route guard work on any FastAPI | — |
| 13 | [PR-011](stories/PR-011.md) | P1 | 3 | New data: promoter and insider trades, pledges, shareholding changes | PR-006 |
| 14 | [PR-009](stories/PR-009.md) | P1 | 5 | Exit on evidence, not on a price-path miss (shadow, then switch) | PR-002, PR-006 |
| 15 | [FIX-016](stories/FIX-016.md) | P1 | 3 | Fix the evidence exit's inputs and its switch gate before the shadow starts | PR-009 |
| 16 | [FIX-018](stories/FIX-018.md) | P1 | 2 | The switch gate sets aside a decision whose result can never be known: named, and within a cap | FIX-016 |
| 17 | [FIX-019](stories/FIX-019.md) | P2 | 1 | Find out why NSE lists no corporate action for 14 configured codes, and map the stale ones | — |
| 18 | [FIX-021](stories/FIX-021.md) | P2 | 1 | A Google redirect link is not an article's identity: the event feed skips it and counts it | — |
| 19 | [SA-048](stories/SA-048.md) | P1 | 3 | Costs and tax in paper P&L | — |
| 20 | [FIX-011](stories/FIX-011.md) | P1 | 2 | NSE's per-symbol meta API is gone: restore the surveillance and suspension guards and an industry source | — |
| 21 | [SA-049](stories/SA-049.md) | P1 | 7 | Idle cash to work, with the breadth floor (12 target holdings) and the ₹2 L top-up | SA-050, SA-051 |
| 22 | [PR-005](stories/PR-005.md) | P1 | 6 | An investment case for every position | PR-006 |
| 23 | [PR-013](stories/PR-013.md) | P2 | 2 | Show where losses come from and what waiting costs | PR-002, PR-009 |
| 24 | [PR-007](stories/PR-007.md) | P1 | 3 | Plain, fact-grounded buy and sell explanations | PR-005, PR-006 |
| 25 | [PR-008](stories/PR-008.md) | P1 | 3 | "Your stocks overnight" at the top of the brief | PR-003, PR-006 |
| 26 | [PR-010](stories/PR-010.md) | P1 | 5 | Four screens for members; an Operator menu for the owner | PR-001 |
| 27 | [PR-012](stories/PR-012.md) | P2 | 3 | Models chosen by role, benched on our own data; cost rates refreshed | PR-007 |
| 28 | [FIX-014](stories/FIX-014.md) | P2 | 1 | Above the 75% cap, a promoter wash must not score as insider buying | PR-011 |
| 29 | [FIX-015](stories/FIX-015.md) | P2 | 1 | The shock exit reads the re-forecast's trigger, not its sentence | PR-009 |
| 30 | [FIX-017](stories/FIX-017.md) | P2 | 2 | The holding sync reads every NSE corporate-action row it is given, under NSE's code | — |
| 31 | [FIX-020](stories/FIX-020.md) | P2 | 1 | Correct the configured codes NSE does not list, and AAVAS's sector | — |
| 32 | [FIX-022](stories/FIX-022.md) | P2 | 2 | The tax estimate at each lot's own cost, and SA-048's loose ends | — |

The new stories add 41 points. SA-049 grows from 5 to 7 points and SA-050 from 2 to 3. On 2026-10-12 the owner confirmed this order, chose the ₹2 L paper-capital top-up with 12 target holdings, and moved PR-011 up as P1 ("I need more data"); the production baseline is section 11 of the review. The track makes results
visible, makes the portfolio broad enough to learn from, and stops one identified source of
early selling. It cannot promise profit: PR-009 switches only on its predeclared gate, and "no
benefit" is a valid result.

DOC-001 is an additional user-requested documentation task outside those point
totals. Its resequencing does not waive SA-031's unresolved dependencies.
Every implementation now updates its affected living documentation and human
test cases, including regenerating the KT PDF when its source changes.
SA-031 remains the final consistency check, not deferred documentation work.

P0 learning defects need a correct target and issuance contract before a safe replacement can be activated. SA-039, split from SA-003 on 2026-09-23 by owner decision and ordered first, therefore adds reversible observe-only containment. Decisions use the configured default weights, while the learner keeps computing into a diagnostic record and leaves stored weights untouched. SA-012–SA-016 build and review the corrected path. Activating containment in production is a separate, owner-authorized configuration push. This plan does not endorse treating existing learning statistics as valid during that interval or automatically changing production flags.

## Executable backlog

| Story | Sprint | Priority | Points | Result | Dependencies |
|---|---|---|---:|---|---|
| [SA-001](stories/SA-001.md) | 1 | P0 | 3 | Sanitize every chat Markdown rendering boundary | — |
| [SA-002](stories/SA-002.md) | 1 | P1 | 3 | Make data-health records describe usable evidence | — |
| [SA-003](stories/SA-003.md) | 1 | P1 | 4 | Gate recommendations and learning on essential data | SA-002 |
| [SA-004](stories/SA-004.md) | 1 | P1 | 3 | Count daily-review outcomes truthfully | — |
| [SA-005](stories/SA-005.md) | 1 | P1 | 5 | Establish a clean, isolated test and CI baseline | — |
| [SA-006](stories/SA-006.md) | 2 | P1 | 3 | Repair delivery transport and expose dead letters | — |
| [SA-007](stories/SA-007.md) | 1 | P1 | 3 | Make backups independently recoverable | — |
| [SA-008](stories/SA-008.md) | 2 | P1 | 5 | Quarantine unresolved securities with explicit lifecycle records | SA-003 |
| [SA-009](stories/SA-009.md) | 2 | P1 | 3 | Inventory and reconcile prediction-store ownership | — |
| [SA-010](stories/SA-010.md) | 2 | P2 | 2 | Pass sector benchmarks through technical-data calls | — |
| [SA-011](stories/SA-011.md) | 2 | P2 | 3 | Turn durable errors into a deterministic operations backlog | SA-002, SA-004 |
| [SA-012](stories/SA-012.md) | 3 | P1 | 3 | Specify and test the learning target before changing it | SA-005 |
| [SA-013](stories/SA-013.md) | 3 | P1 | 5 | Persist immutable, genuinely prospective forecast identities | SA-012 |
| [SA-014](stories/SA-014.md) | 3 | P1 | 5 | Grade frozen decisions and issue controls before their outcomes | SA-003, SA-013 |
| [SA-015](stories/SA-015.md) | 3 | P1 | 5 | Make adaptive updates idempotent and preserve final weight bounds | SA-014 |
| [SA-016](stories/SA-016.md) | 4 | P1 | 5 | Replace blame-based shared credit with identifiable outcomes | SA-015 |
| [SA-017](stories/SA-017.md) | 4 | P1 | 3 | Attach historical lineage and quarantine incomparable feedback | SA-009, SA-013 |
| [SA-018](stories/SA-018.md) | 4 | P1 | 5 | Build complete, matched monthly evaluation cohorts | SA-014, SA-017 |
| [SA-019](stories/SA-019.md) | 4 | P1 | 5 | Evaluate suggestions across weekly and fortnightly cohorts | SA-018 |
| [SA-020](stories/SA-020.md) | 5 | P1 | 3 | Compute effective samples from trading-session overlap | SA-013 |
| [SA-021](stories/SA-021.md) | 5 | P1 | 5 | Validate calibration and weight recovery with minimum evidence | SA-016, SA-018, SA-020 |
| [SA-022](stories/SA-022.md) | 5 | P1 | 5 | Run prospective adapted and frozen-policy experiments | SA-016, SA-018, SA-020, SA-043, SA-047 |
| [SA-023](stories/SA-023.md) | 5 | P2 | 3 | Put learned lessons on measurable probation | SA-022 |
| [SA-024](stories/SA-024.md) | 5 | P2 | 3 | Show verifiable learning evidence and honest unavailable states | SA-019, SA-020, SA-022 |
| [SA-025](stories/SA-025.md) | 6 | P2 | 3 | Count actual provider calls and fallback cost | SA-011 |
| [SA-026](stories/SA-026.md) | 3 | P1 | 5 | Consolidate sector definitions into sector lenses | SA-003, SA-009, SA-010 |
| [SA-027](stories/SA-027.md) | 6 | P2 | 3 | Retire redundant fallback only when measured replacements work | SA-025, SA-026, SA-047 |
| [SA-028](stories/SA-028.md) | stretch | P2 | 5 | Repair packaging and compile the browser client | SA-001, SA-005 |
| [SA-029](stories/SA-029.md) | 6 | P1 | 3 | Verify readiness and recover background ownership | SA-004, SA-007 |
| [SA-030](stories/SA-030.md) | stretch | P2 | 3 | Reconcile or retire stale Atlas projections | SA-009, SA-013 |
| [SA-031](stories/SA-031.md) | 6 | P2 | 2 | Verify final architecture and operator-documentation consistency | SA-024, SA-027, SA-029 |
| [SA-032](stories/SA-032.md) | stretch | P2 | 3 | Define and enforce the public-read and demo-data policy | SA-001, SA-024 |
| [SA-033](stories/SA-033.md) | 1 | P1 | 3 | Lock reproducible runtime dependencies | — |
| [SA-034](stories/SA-034.md) | 2 | P1 | 6 | Detect silent degradation in the watchdog | SA-036, SA-040 |
| [SA-035](stories/SA-035.md) | 1 | P1 | 3 | Surface LLM and search provider credit exhaustion | — |
| [SA-036](stories/SA-036.md) | 1 | P1 | 4 | Record durable outcomes for every critical job | — |
| [SA-037](stories/SA-037.md) | 2 | P2 | 3 | Keep deploys from dropping scheduled jobs | SA-036 |
| [SA-038](stories/SA-038.md) | 1 | P1 | 2 | Judge and retire lapsed production-verification milestones | — |
| [SA-039](stories/SA-039.md) | 1 | P0 | 3 | Contain adaptive learning: observe-only, live weights back to defaults | — |
| [SA-040](stories/SA-040.md) | 1 | P1 | 3 | Record per-source fetch health and detect new error types | — |
| [SA-041](stories/SA-041.md) | 2 | P1 | 3 | Provide a read-only production status fetcher | SA-036, SA-040 |
| [SA-042](stories/SA-042.md) | 1 | P1 | 2 | Add an outside witness for missed jobs (Healthchecks.io → Telegram) | SA-036 |
| [SA-043](stories/SA-043.md) | 4 | P1 | 3 | Run a shadow learner and record paired decisions in observe mode | SA-015, SA-039, SA-045 |
| [SA-044](stories/SA-044.md) | 2 | P1 | 2 | Compare valuations only with same-industry peers | — |
| [SA-045](stories/SA-045.md) | 4 | P1 | 5 | Compute the five universal factors deterministically | SA-026 |
| [SA-046](stories/SA-046.md) | 4 | P1 | 3 | Read text into dated events and a Catalyst factor | SA-026 |
| [SA-047](stories/SA-047.md) | 5 | P1 | 5 | Decide with the factor engine; switch when it is not worse | SA-045, SA-046, SA-014, SA-020 |
| [SA-048](stories/SA-048.md) | 3 | P1 | 3 | Charge realistic trading costs and tax in paper P&L | — |
| [SA-049](stories/SA-049.md) | 3 | P1 | 7 | Put idle cash to work in normal markets, with the breadth floor | SA-050, SA-051 |
| [SA-050](stories/SA-050.md) | 2 | P1 | 3 | Apply one sizing and entry rule to every autopilot buy | — |
| [SA-051](stories/SA-051.md) | 2 | P1 | 3 | Show the portfolio against the Nifty, with honest labels | — |

Every card has concrete acceptance criteria, independent unit/integration fixtures, hard-review questions and rollout/rollback limits. Use [REVIEW.md](REVIEW.md) for the sign-off gate and [evidence/README.md](evidence/README.md) for durable receipts.

## Acceptance and release gates

- **Implementation complete:** bounded diff, appropriate deterministic checks, exact evidence receipt, no secrets/runtime evidence in tracked files. Status becomes `review_required`.
- **Code accepted:** a fresh conversation reviews the recorded diff, challenges its assumptions and records a verdict. Status becomes `done` only after all blocking findings are fixed and rechecked. This is a separate-context agent review, not an independent human audit.
- **Production verified:** separate state field with deployment revision, observation period and actual results. Local success does not prove rollout, email receipt, disaster recovery or future market efficacy.
- **Learning benefit demonstrated:** matched prospective evidence satisfies the predeclared statistical/economic gate with sufficient effective samples. Neither a finished sprint nor changed weights satisfies this gate. Recheck cohorts over time without selecting thresholds after seeing outcomes.

No blanket rewrite, new distributed service, broker trading integration, automatic LLM patching, automatic production migration or unrequested notification sending belongs in this PI. Use current small-service infrastructure unless a measured constraint warrants more.

## Reconciliation with the August three-loops PI

The [August specification](../../superpowers/specs/2026-08-24-three-loops-pi-design.md) stays historical. Its routing/durable-logging/data-health/error-capture changes are present in the deployed commit; operational acceptance is not inferred merely from code presence. The September audit supersedes its unverified claims about learner correctness, unused fallback cost and automatic ticker succession.

| August card | September disposition |
|---|---|
| A1 Single router | Implemented in baseline; preserve with SA-026 equivalence checks |
| A2 Prediction migration | SA-009 manifest and SA-017 lineage/quarantine |
| A3 Sector profile / A4 profile cutover | SA-026 |
| B1 Durable logging | Implemented; acceptance/retention and severity interpretation in SA-011 |
| B2 Data-health record | Implemented record; semantic and consumer gaps in SA-002/SA-003 |
| B3 Watchdog integrity | SA-004/SA-011/SA-029 |
| B4 Real API accounting | SA-025 |
| B5 Hollow-run gate | SA-003 |
| B6 Returned-data semantics | SA-002 |
| C1 Grading diagnostic | Diagnostic exists; September reward/time findings refine it |
| C2 Grading specification | SA-012, including the previously unfilled specification boundary |
| C3 Dark grading | SA-013/SA-014/SA-015/SA-016 |
| C4 Weight recovery | SA-021; efficacy remains unproven until prospective validation |
| D1 TickerVerdict | SA-003 typed result; SA-030 owns only optional SQL projection completion |
| D2 Legacy retirement | SA-027; use measured fallback evidence |
| D3 Exception CI guard | SA-005 |
| D4 Automobile index | SA-010; latest inspected failures are older, coupling still exists |
| D5 Ticker lifecycle | SA-008; confirm economic identity, do not blindly rename a demerged security |
| D6 Email transport | SA-006; independent recovery handled in SA-007 |
| E1 Error capture | Implemented substantially; remaining malformed-factor issue in SA-016, acceptance in SA-011 |
| E2 Fingerprint / E3 watchdog digest / E4 registry | SA-011 |
| E5 LLM triage note | Deferred, not required for this PI; reconsider after deterministic registry proves useful |

## Continuing in fresh chats

Root [AGENTS.md](../../../AGENTS.md) tells agents how to select and hand off one phase. The state file and receipts are repository memory, not hidden conversational memory. A fresh Codex chat opened in this repository can say **continue** and read the next bounded task. After implementation, the next fresh chat reviews that task; after acceptance, the following chat implements the next ready story.

An agent cannot automatically create a fresh chat or guarantee that an unrelated workspace reads these files. Keep the plan in the checkout used by the next chat; if moving to another machine, include these files in the normal source-control handoff. No commit or push was performed by the audit. Codex's repository instruction behavior is described in [official AGENTS.md documentation](https://learn.chatgpt.com/docs/agent-configuration/agents-md).
