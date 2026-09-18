# DOC-001 — Implementation and validation receipt

Date: **2026-09-15**. Phase: **documentation implementation and self-review**.
Fresh-session hard review: **pending**. No SA remediation is accepted here.

## Scope and source baseline

The user requested two separate deliverables: current-code KT Markdown/PDF
including all planned PI changes, and assignable non-code-intensive human
testing duties. DOC-001 was explicitly resequenced before SA-001. SA-031
remains a final consistency check, with SA-024/SA-027/SA-029 unresolved.

Inspected HEAD: `9a805878ed19c0cda7833d5b897ac05ee407436d`. No application source,
configuration or Docker changes were made. The checkout already contained
audit banners in ARCHITECTURE/README and untracked AGENTS.md, the PDF, the
September audit and planning files. Their provenance was retained. The user's
PDF bytes were archived before regeneration, at SHA-256
`1fc2402b6bdda4ac088630e1f1caf8d10f89799409dd9e0eff559ab3df4f66d9`.

## Deliverables and source trace

| Deliverable | What was established |
|---|---|
| Technical KT + generated PDF | Current topology, imports, configuration, stores, research/learning/portfolio flow, IPO collection/history/ranking, P/L, six report families, scheduler inventory and all 32 SA story targets. |
| Architecture overview | Replaced stale file-lock, observe-only binding and scheduler-count claims with current source behavior. |
| Team testing guide | 12 assignment units, synthetic examples, evidence template, expected results and explicit PI targets; all human cases remain NOT RUN. |
| Per-story maintenance | Root instructions, REVIEW, PI README, evidence guidance and SA-031 now require incremental documentation rather than waiting for Sprint 6. |
| Specialist references | PRODUCT_MAP and RL_DESIGN carry explicit current-source precedence; their entire historical bodies were not revalidated. |

Code traced directly: server lifespan/TCP singleton; scheduler builder and
daily-review harvest/post-review hook; central graph routing; bundle health
and aggregation/binding; forecast generation, feedback label and fresh-verdict
grading, weight adaptation and prediction persistence; advisor cascade,
executor ordering/deduplication, digest and performance API; IPO cache,
snapshot/history/outcome/report/tracker; discovery; weekly scoreboard,
monthly/evidence reports and audit rules; watchdog, delivery and UI read paths.

The KT explicitly distinguishes forecast-error direction from realized price
direction, research verdict from position action, advice from transaction,
weekly heuristic from matured audit, and retrospective replay from prospective
learning benefit. Existing code and September PI targets are not conflated.

## Local tests

Command from repository root:

```text
python scripts/docs/run_kt_checks.py --dependency-path analysis_data/audit_20260910/test_dependencies
```

- Python **3.13.11**, Windows; pytest **9.0.3**, pytest-asyncio **1.3.0**.
- **323 passed, 0 failed, 0 errors, 0 skipped**, 114.08 seconds reported by
  pytest (114.03 seconds in JUnit). The script contains the exact 30-file list.
- Coverage includes router equivalence, data health, hard-bind behavior,
  scheduler IPO/delivery/portfolio hooks, daily-review early exit, IPO
  calendar/history/report/signals/velocity/tracker, portfolio/API/transparency/
  stops/reconciliation, discovery, audit rules/outcomes, monthly/evidence
  reports, executor sells/adds/switches, outbox and watchdog engine/runner.
- Each attempt uses an isolated tracked-source copy without `.env` or runtime
  data. Credentials are not inherited; dotenv is disabled; real transports and
  test subprocesses are blocked. In-process TestClient and the Windows asyncio
  local socket pair are allowed. This is not a kernel-level network sandbox.
- The local dependency directory reused isolated cryptography, nse and parquet
  dependencies from the prior audit. Another checkout must provide required
  dependencies; do not assume ignored directories are portable.

Harness development had an initial bootstrap failure from replacing the
Popen class with a function, then a 303-pass/20-failure run because the guard
also blocked Windows asyncio self-pipes and in-process TestClient. Correcting
those harness boundaries produced the full 323-pass result without changing
application source or allowing external provider/delivery transports.

These are existing behavior checks. In particular, tests that expect current
fresh-verdict grading are not independent evidence that its financial target
is correct. The September audit's known invariants remain unresolved. No
full-suite rerun, Linux/Python-3.11 parity, live provider experiment, live
authenticated UI acceptance, production recovery or learning-benefit claim
is made.

## Document and PDF validation

```text
python scripts/docs/build_kt_pdf.py
python scripts/docs/check_kt_docs.py
git diff --check
git diff --name-only -- core services src/backend src/frontend config.yaml Dockerfile
```

The builder runs local Chromium with browser requests blocked. The PDF contains
the source hash in its footer and has searchable text. Local paths are removed
from PDF hyperlinks. Automated checks cover Markdown link targets, 32 PI rows
and their dependencies, 23 possible scheduler IDs and 13 configuration claims.
Original PDF archive bytes are checked independently.

Visual verification uses PyMuPDF 1.28.2 installed only under ignored analysis
data. All pages were rendered to a contact sheet and representative pages
inspected. Final counts and manifest digest are recorded below after checks.

## Read-only production context

Executed Railway CLI with the use-railway skill telemetry:

```text
railway.cmd status --json
railway.cmd deployment list --limit 1 --json
```

Output was allowlisted to deployment status, creation time and commit, rather
than printing raw logs/variables. Latest deployment: **SUCCESS**, created
`2026-08-26T18:50:56.268Z`, commit matching inspected HEAD. This establishes
deployment metadata only. September 10's detailed operational evidence stays
dated; email, off-site recovery, job counts and future outcomes were not
remeasured. No production writes, jobs, notifications, deployment, commit or
push were performed.

## Manifest and handoff

The companion `DOC-001-manifest.json` records SHA-256 hashes of all deliverable
files and helper scripts, including relevant untracked files. It records the
baseline revision. Its own SHA-256 is the review-input digest. STATE.json,
HANDOFF.md, this receipt and the manifest itself are excluded from the payload
hashes to avoid circular bookkeeping; a reviewer must inspect those four files
separately for state/receipt consistency. The exclusions are not a waiver for
unrelated changes.

Self-review does not satisfy the fresh-session gate in REVIEW.md. DOC-001
finishes at `review_required`; after acceptance the first remediation remains
SA-001. Every SA story retains `todo` and its dependencies. Human testing cases
remain NOT RUN; the guide describes future team duties, not results.

## Final validation result

- **323 existing tests passed** across 30 files (114.08 seconds).
- **12 documents / 207 local link targets**, all **32 SA story rows** with
  dependency/title checks, **23 scheduler IDs**, and **13 configuration
  assertions** checked successfully.
- **16-page PDF**, **34,937 extracted text characters**, no HTML table/code
  overflow and no PDF text blocks outside page bounds. All pages rendered;
  contact sheet and representative full-size pages inspected.
- **12 human duties / 57 cases**, all explicitly NOT RUN.
- `git diff --check` passed; the application/config/Docker diff query returned
  no files. There is a Git line-ending normalization notice for the Markdown,
  not a whitespace failure. Raw diagnostics remain ignored.
- Markdown SHA-256:
  `15dc554239971a1ad8fefd820b8f1e2ae364cd71e4fd7691e13609b66a95f5d7`.
- Review-input manifest SHA-256: `90c005c46417db97d6e3f6feba2431aae66a8ad93037e852e9823ad7936125c0`.
- Manifest: [DOC-001-manifest.json](DOC-001-manifest.json), **20 hashed
  payload files**, plus the four explicitly excluded bookkeeping files.

Recompute the digest from the manifest's exact bytes. For each `files` entry,
compute SHA-256 over the referenced file's bytes and compare with its recorded
hash. Also inspect the four bookkeeping exclusions. This is a self-reviewed
worktree content manifest, not a signed-off fresh-session review or commit.

