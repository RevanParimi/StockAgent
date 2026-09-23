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
| 1 | Learning containment first; security, honest health, action gating, scheduler counts, clean CI; dependency lock, provider-credit alerts, job outcomes, milestone hygiene, off-site backup | 35 | Contained learner leaves stored weights untouched and decisions on defaults; browser exploit fixture inert; no-data action/update blocked; counts reconcile; clean Python-3.11 CI baseline |
| 2 | Delivery, instrument/store identity, benchmark correctness, incident registry; silent-degradation watchdog, deploy hygiene | 24 | Mock transport/recovery tests, real verification tracked separately, reviewed migration manifest, correct provider arguments |
| 3 | Learning target, immutable issuance, correct dark grading, atomic bounded updates | 18 | Independent numeric/time fixtures; old outcome cannot be regraded with today's decision; crash/retry invariants pass |
| 4 | Identifiable credit, historical lineage, complete monthly and weekly/fortnightly cohorts | 18 | Hand-reconciled forecast/outcome IDs and denominators; exited calls retained; wrong-roster history excluded explicitly |
| 5 | Effective samples, calibration, prospective experiments, lesson probation, honest evidence UI | 19 | Reviewed experiment protocol and deterministic end-to-end experiment; sufficient market evidence may still be pending |
| 6 | Actual call accounting, sector consolidation, justified fallback retirement, runtime recovery, current docs | 16 | Cost counts reconcile, routing equivalence, owner-loss recovery test, accepted operator documentation |
| Stretch | Packaging/client build, Atlas projections, comprehensive public-read policy | 11 | Separate capacity/product decision; not selected automatically by “continue” |

The 36 planned stories total 130 points; three stretch stories total 11. Six planned stories (SA-033–SA-038) were added on 2026-09-23 from the [production assurance review](../../audit/2026-09-23-production-assurance-review.md), and SA-007 moved to Sprint 1. Later that day the owner split SA-003's learning containment out as SA-039 (P0, 3 points, first in order), and SA-003 went from 5 points to 4. Sprint 1 is heavy at 35 points, so re-estimate after it. Dependencies, not numbering alone, determine readiness. Security/privacy issues newly discovered during any story take priority over this provisional order. Production incidents may justify resequencing, recorded in STATE.json with the reason.

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
| [SA-022](stories/SA-022.md) | 5 | P1 | 5 | Run prospective adapted and frozen-policy experiments | SA-016, SA-018, SA-020 |
| [SA-023](stories/SA-023.md) | 5 | P2 | 3 | Put learned lessons on measurable probation | SA-022 |
| [SA-024](stories/SA-024.md) | 5 | P2 | 3 | Show verifiable learning evidence and honest unavailable states | SA-019, SA-020, SA-022 |
| [SA-025](stories/SA-025.md) | 6 | P2 | 3 | Count actual provider calls and fallback cost | SA-011 |
| [SA-026](stories/SA-026.md) | 6 | P2 | 5 | Consolidate sector definitions with equivalence checks | SA-003, SA-009, SA-010 |
| [SA-027](stories/SA-027.md) | 6 | P2 | 3 | Retire redundant fallback only when measured replacements work | SA-025, SA-026 |
| [SA-028](stories/SA-028.md) | stretch | P2 | 5 | Repair packaging and compile the browser client | SA-001, SA-005 |
| [SA-029](stories/SA-029.md) | 6 | P1 | 3 | Verify readiness and recover background ownership | SA-004, SA-007 |
| [SA-030](stories/SA-030.md) | stretch | P2 | 3 | Reconcile or retire stale Atlas projections | SA-009, SA-013 |
| [SA-031](stories/SA-031.md) | 6 | P2 | 2 | Verify final architecture and operator-documentation consistency | SA-024, SA-027, SA-029 |
| [SA-032](stories/SA-032.md) | stretch | P2 | 3 | Define and enforce the public-read and demo-data policy | SA-001, SA-024 |
| [SA-033](stories/SA-033.md) | 1 | P1 | 3 | Lock reproducible runtime dependencies | — |
| [SA-034](stories/SA-034.md) | 2 | P1 | 5 | Detect silent degradation in the watchdog | SA-036 |
| [SA-035](stories/SA-035.md) | 1 | P1 | 3 | Surface LLM and search provider credit exhaustion | — |
| [SA-036](stories/SA-036.md) | 1 | P1 | 3 | Record durable outcomes for every critical job | — |
| [SA-037](stories/SA-037.md) | 2 | P2 | 3 | Keep deploys from dropping scheduled jobs | SA-036 |
| [SA-038](stories/SA-038.md) | 1 | P1 | 2 | Judge and retire lapsed production-verification milestones | — |
| [SA-039](stories/SA-039.md) | 1 | P0 | 3 | Contain adaptive learning: observe-only, live weights back to defaults | — |

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
