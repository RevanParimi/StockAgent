# Hard-review protocol

A passing test suite does not establish a correct financial target or absence of leakage. Review the story's invariant and data flow before trusting its test count.

## Implementation receipt

The implementer records the story ID, baseline revision, changed files (including relevant untracked files), diff digest, acceptance results, exact test commands/environment and open limitations in `evidence/SA-NNN-implementation.md`. Record how the digest was computed so a fresh reviewer can verify the same input. Never include secrets, user data or raw production payloads. Update STATE.json and HANDOFF.md together.

## Documentation is part of each story

Update affected sections of [the current KT](../../TECHNICAL_DESIGN.md), the
architecture overview and [human testing cases](../../TEAM_TESTING_GUIDE.md)
in the same implementation phase as the behavior change. Use KT section 12
as the initial mapping, and adjust it when a story's actual scope changes.
Do not regenerate `docs/StockAgent-Three-Loops.pdf` with a story: it is built only when
the owner asks for it or at the PI's end (AGENTS.md, owner's rule of 17 Nov 2026).
Record the documentation paths, checks and remaining planned behavior in the
receipt. If a story has no reader-visible documentation impact, record that
reason explicitly. SA-031 checks final consistency; it does not postpone
normal documentation until the end of the PI.

## Which stories get a fresh-session review

Since 14 Nov 2026 (the owner's rule, AGENTS.md step 4): stories on the **decision path** (what is bought, sold or sized, how a forecast or an exit is graded, the ledger's money arithmetic) and stories that change who can read or change an account's data. **Light** stories (reports, screens, briefs, documents, operations, housekeeping, and rollout stories that change one authorized setting) are accepted in their implementing conversation when the full suite and the project guards pass; their receipt names the lane and the reason. In doubt, the story is on the decision path.

## Fresh-session review

1. Read the selected story, implementation receipt and actual current diff. Verify revision/digest; investigate drift before signing off. Avoid reading a whole unrelated chat or every historical report.
2. Independently trace at least one adversarial example from input to persisted result and all consequential consumers. Check correctness, authorization, data freshness, financial horizon, issue-time availability, duplicate/retry behavior, bounded math, missing-data policy and compatibility where relevant.
3. Check that tests would fail for the original defect and use expected results derived independently of the changed algorithm. Inspect mocked boundaries for hidden real API/SMTP/push calls and unrealistic success fixtures.
4. Run focused tests and required project checks once. Broaden only for changes/failures/unresolved concerns. Security browser sinks require actual browser execution; persistence changes require failure/concurrency checks; pure prose does not need invented unit tests.
   Verify that the affected living documentation and human test cases describe
   the reviewed behavior and that the PDF matches its source when changed.
5. Record findings with severity, exact file/line, trigger, observed/expected result, impact and a reproducible fixture. Distinguish confirmed bugs, inference and product decisions. Do not manufacture findings to appear rigorous.
6. Verdict: `changes_requested` for any unresolved critical/high or unmet acceptance criterion; `accepted` only for the reviewed revision with the relevant tests passing. Document medium/low items as explicit follow-ups, not hidden waivers: a story link for a medium or higher finding on the decision path, otherwise one entry in [BACKLOG.md](BACKLOG.md) with the trigger that would promote it.

If the reviewer changes behavior, record the findings, return to implementation and retest. A later fresh review signs off the new revision. Same-conversation self-review is useful but does not satisfy this gate. This process provides separate-context agent review; it does not claim independent human or professional financial certification.

## Review receipt

Write `evidence/SA-NNN-review.md` with:

- Story, reviewed baseline and diff/revision digest; review context explicitly identified as fresh-session or self-review.
- Contract checked and independent adversarial examples.
- Findings table with severity/location/evidence/disposition, including “none found” when justified.
- Commands, environment and results; what was not exercised.
- Acceptance checklist verdict and remaining production/future-cohort verification.
- Final accepted/changes-requested decision and exact follow-up state.

## Production and evidence gate

The user authorized read-only production inspection. Neither a story nor a passing review independently authorizes a deployment, config change, notification, policy activation or production migration. Prepare a concrete reviewed diff/runbook first and use existing conversation authorization if later provided. Do not repeatedly request permission already granted. For irreversible operations, include backups and a verified dry-run manifest.

Retain historical rollout constraints: avoid the 16:25–17:15 IST review window for behavior deployments; change one adaptive policy flag per observation window; never auto-patch production based on an LLM note. Check current operating conditions before using an old schedule as fact.

Mark `production_verification.status` independently (`not_applicable`, `pending_deployment`, `pending_observation`, `verified`, or `failed`; initial `not_started`). Give dated evidence and revision for verified results. A story's code can be done while rollout is pending; the PI outcome must still show the gap. Prospective learning experiments require future matured cohorts even after implementation acceptance.
