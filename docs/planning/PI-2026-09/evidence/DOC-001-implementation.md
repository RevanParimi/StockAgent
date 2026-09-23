# DOC-001 — Implementation and validation receipt

> **2026-09-23 — changes-requested remediation appended below.** The
> September 15 sections are kept as the dated record. Their Markdown digest
> (`15dc5542…`) and review-input digest (`90c005c4…`) are **superseded**: the
> 2026-09-22 review (F1) showed neither can be reconstituted. Current evidence
> is in [Remediation phase](#remediation-phase--2026-09-23) and the
> regenerated [manifest](DOC-001-manifest.json).

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

## Remediation phase — 2026-09-23

Phase: **implementation after `changes_requested`**. It answers the
[2026-09-22 fresh-session review](DOC-001-review.md), F1–F6. The phase ran in a
new conversation, but the same conversation also self-reviewed it, so it is
**not** a fresh review. DOC-001 returns to `review_required` (after the PDF
rebuild at the end of this section). Base revision:
HEAD `d105a44a06d430304a724f34ac3dc329a4ca0d87`, with no commit made in this
phase.

### Findings addressed

| # | Disposition in this phase |
|---|---|
| F1 | **Fixed.** Manifest regenerated by the new `scripts/docs/kt_manifest.py`. It records git's own blob id plus the SHA-256 of those same blob bytes, and refuses a file whose bytes do not reproduce the blob id. The convention is stated in the manifest itself (`hash_convention`). |
| F2 | **Fixed** later the same day, once the user installed Node (see [PDF rebuild](#pdf-rebuild--2026-09-23-after-node-install)). It was first recorded as blocked because no `node`, `npx` or Playwright browser cache existed. |
| F3 | **Fixed.** KT header moved to Edition 2026-09-23, Code inspected `d105a44a…`, with a line recording the first edition. `check_kt_docs.py` gains `check_header_revision` (see below). |
| F4 | **Fixed.** §10 documents both email transports, `EMAIL_TRANSPORT`, `outbox.last_error` and its migration, and `resolve_recipient()`. It separates the dated Sept 10 and Sept 21 observations and lists three known gaps. §11's IPO and Operations rows now agree with §8/§10; §13 links the review and its sessions cover P3 and outbox states. |
| F5 | **Routed.** Reproduced locally, then recorded on [SA-005](../stories/SA-005.md) (fix the tests' isolation) and [SA-006](../stories/SA-006.md) (qualifies `590bc9f`'s 2832-pass claim). Not fixed here; a test change belongs to SA-005. |
| F6 | Done by the review; `updated_at` moved to 2026-09-23 here. |

Found in this phase, beyond the review's list:

- §8 did not document IPO-0b's size-tiered brief demand lean (`ef34153`).
  Its closing paragraph also said current code had only "collection,
  history, captured signals and heuristic candidate ranking", contradicting
  the P3 row above it. Both are fixed.
- The Resend default shared sender delivers only to the Resend account owner.
  That limits per-account delivery; recorded in §10 and on SA-006.
- HT-10 had no recipient-isolation case. Case **10-E** was added and 10-C
  now expects a stated failure reason: 12 duties, **60** cases, all NOT RUN.
- Some committed blobs contain CRLF (e.g. `docs/ARCHITECTURE.md`: HEAD's blob
  equals its raw CRLF worktree bytes). "LF-normalized equals committed" is
  therefore false in general, which is why the manifest uses git's blob.
- On this OneDrive checkout `git cat-file blob HEAD:docs/StockAgent-Three-Loops.pdf`
  hangs (it logged `mmap failed`). `kt_manifest.py verify --rev` therefore
  compares blob ids via `git rev-parse`, and every git call has a timeout.

### Code inspected to write the new text (d105a44)

`git diff --stat 9a805878..d105a44` outside docs/tests/data: all 16 commits
are IPO work or `590bc9f`. Read directly: `core/delivery/channels.py`
(`resolve_recipient`, `_resolve_transport`, `send_email_result`),
`core/delivery/outbox.py` (`_send_row`, `drain_once`),
`services/data/stores/atlas_store.py` (`_migrate`), the settings in
`src/backend/shared/config/settings/base.py` plus `cfg()` in `loader.py`
(precedence env > config.yaml > fallback), `services/data/stores/user_store.py`
(`data/users.db`), `core/delivery/brief.py` (`_ipo_lean`,
`_ipo_demand_band`), and `config.yaml` delivery/outbox keys.

### Header guard: what it does and does not catch

`check_header_revision` fails when the declared revision is unknown, is not
an ancestor of HEAD, postdates the edition date, or lacks any linked source
file or documented §9 job ID. It reports, but does not fail on, linked sources
changed since the revision.

Tested against inputs where the property is false, not only where it holds:

| Input | Result |
|---|---|
| KT as reviewed at `d105a44` (header `9a805878`) | **10 errors**: 9 `core/ipo/*` links (including `narrate.py`) and job `ipo_deep_dive`, matching the review's own F3 evidence |
| Current KT | 0 errors; 64 linked sources; 0 changed since `d105a44` |
| Edition changed to 2026-09-01 | 1 error, edition predates commit date 2026-09-22 |
| Revision `ffff…` | 1 error, not a known commit |

**Limit:** it cannot see changed behaviour inside a file that already existed
at the declared revision. `590bc9f`'s `channels.py` edits were exactly that
case, and would have produced only the informational list. Moving the revision
forward still requires re-reading those sections.

The PDF builder and checker now both hash the KT over LF-normalized bytes, so
PDF freshness no longer depends on the checkout's line endings.

### Commands and results (Windows, Python 3.13.11, `.stockai`)

```text
.stockai/Scripts/python.exe scripts/docs/check_kt_docs.py
  -> 13 documents, 226 local links, 32 PI rows, 24 job IDs, 13 config claims,
     header OK (d105a44, 64 sources, 0 changed); 1 error: stale PDF digest (F2)
.stockai/Scripts/python.exe scripts/docs/run_kt_checks.py --dependency-path analysis_data/audit_20260910/test_dependencies
  -> 324 tests, 2 failures, 0 errors, 0 skipped, 102.82 s
     failures (JUnit): test_atlas_outbox::test_send_row_caps_push_and_passes_html_to_email,
                       test_atlas_outbox::test_send_row_returns_transport_reason  (= F5, routed)
DELIVERY_EMAIL_TO="test@example.invalid" pytest tests/unit/test_atlas_outbox.py -q  -> 11 passed
DELIVERY_EMAIL_TO=""                     pytest tests/unit/test_atlas_outbox.py -q  -> 2 failed, 9 passed
scripts/docs/kt_manifest.py verify <manifest>             -> 24 files, 0 mismatches
scripts/docs/kt_manifest.py verify <manifest> --rev HEAD  -> exactly the 9 files changed/added here differ
git diff --check                                          -> clean
git diff --name-only -- core services src config.yaml config Dockerfile  -> empty
```

Manifest cross-check before use: for `docs/ARCHITECTURE.md` (CRLF blob),
`docs/RL_DESIGN.md` (LF) and the PDF (binary), the tool's blob id equals
`git rev-parse HEAD:PATH`. A deliberately changed file is flagged by
`verify --rev HEAD`. `data/nse/key_registry.json` was unchanged
(`db6bd9c5…`) before and after the harness run.

### Manifest

- [DOC-001-manifest.json](DOC-001-manifest.json): **24 payload files**. The 20
  earlier ones, plus `kt_manifest.py`, `DOC-001-review.md`, `SA-005.md` and
  `SA-006.md`. The same four bookkeeping exclusions apply.
- Review-input SHA-256 `f2ee40c2…` was superseded by the PDF rebuild; the
  current values are in [PDF rebuild](#pdf-rebuild--2026-09-23-after-node-install).
- The payload is **uncommitted**. Once committed, `kt_manifest.py verify
  <manifest> --rev <commit>` must report 0 mismatches. If it does not, the
  payload changed after this manifest, which is the F1 failure again.

### Not done, and why

- ~~**PDF rebuild (F2):**~~ *done later the same day, see below.* It needed Node LTS, `npx playwright install chromium`,
  then `python scripts/docs/build_kt_pdf.py` and a visual check. DOC-001 cannot
  be accepted while its PDF deliverable contradicts its source. The next
  reviewer should expect F2 to still be open unless the user rebuilds first.
- No test fix for F5 (SA-005 scope). No full suite, no Linux/Python 3.11
  parity, no browser run, no production inspection, no commit, push,
  deployment, job or notification.

### PDF rebuild — 2026-09-23, after Node install

The user installed Node **v24.21.0** (`C:\Program Files\nodejs`, already on
the system PATH). Shells opened before the install lacked it, so this session
prepended it explicitly. Chromium was installed through the vendored
Playwright **1.62.1** CLI (`node node_modules/playwright/cli.js install
chromium`, i.e. Chrome for Testing 151.0.7922.34 into `%LOCALAPPDATA%\ms-playwright`).
Then `python scripts/docs/build_kt_pdf.py`.

Visual inspection (PyMuPDF from the ignored `analysis_data/` dependency
folder): an 18-page contact sheet, plus full-size views of the header, §1 and
§10. It found one real defect, which was fixed before the final build. §1's
"Production observation" row still said Railway reported SUCCESS "at the same
commit". With the header moved to `d105a44`, that implied a production check at
`d105a44` which never happened. The row now names `9a805878` and says no
`d105a44` deployment was inspected. A first rewrite broke the label mid-word
in the narrow column, so the row was shortened and re-rendered clean.

Final results:

```text
python scripts/docs/build_kt_pdf.py   -> html_overflow_elements 0, 184,832 bytes
python scripts/docs/check_kt_docs.py  -> 0 errors: 13 documents, 235 local links, 32 PI rows,
                                         24 job IDs, 13 config claims, 18 PDF pages,
                                         40,489 characters, header OK (d105a44, 64 sources, 0 changed)
PDF text: "24 possible job IDs" x1, "23 possible job IDs" x0; ipo_deep_dive, deep_dive.py,
          narrate.py, verdicts.py, grade_ipo_lane, resolve_recipient, last_error,
          EMAIL_TRANSPORT all present; no empty page
kt_manifest.py verify <manifest>             -> 24 files, 0 mismatches
kt_manifest.py verify <manifest> --rev HEAD  -> 10 differ: the 9 above plus the rebuilt PDF
git diff --check -> clean; application/config/Docker diff -> empty
```

The KT's §1 edit changed no code and no test input, so the 324-test harness
result above still stands; it was not re-run after the rebuild. The Edit tool
wrote `TECHNICAL_DESIGN.md` LF-only. That is harmless under `eol=lf`, and the
digest convention is LF-normalized either way.

**Current digests:**

- **Review-input SHA-256: `7b04fa718dbaf958c71413f21e0d99454b9184801cc530d4d3f1cec2fb03deca`**
  (the manifest's own LF bytes; `sha256sum` reproduces it).
- `docs/TECHNICAL_DESIGN.md`: git blob `8e1dcf7a43cbf0933e42f50687426a39418449da`,
  SHA-256 `8703543d353adfbb2983c90b8e7c496738d746ee52f54aaa7ea563c520b4bd20`
  (also the PDF footer's `Source 8703543d353a`).
- `docs/StockAgent-Three-Loops.pdf`: git blob `dfcdbf4a34c005ec087b74dd5db7a8121ff7df01`,
  SHA-256 `576cf24ad4fe4d753d3c5fdfb4f609e7a74fd86754589b84d885252f9a3c7a26`.

The payload is still **uncommitted**. Commit it before the review; then
`kt_manifest.py verify <manifest> --rev <commit>` must report 0 mismatches.
With F2 closed, every review finding is fixed or routed. DOC-001 stops at
**`review_required`**; the fresh-session review is the next phase, in a new
conversation.

### Payload update — 2026-09-23 (late), after the PDF rebuild

After that rebuild, the user asked to add the production-assurance backlog to every board. The
checker requires every SA story in STATE to have a KT §12 row, so three payload files changed:
`docs/TECHNICAL_DESIGN.md` (six §12 rows for SA-033–SA-038, and §1's "SA-001 through SA-038"),
the rebuilt PDF, and `docs/planning/PI-2026-09/README.md` (backlog rows, sprint totals, SA-007 →
Sprint 1). No KT body text about current code changed.

- `kt_manifest.py verify`, before regenerating, flagged exactly those 3 files. After
  regenerating: 24 files, 0 mismatches.
- `check_kt_docs.py`: 0 errors. 38 PI stories, 18 PDF pages, 248 local links. The new rows were
  checked visually on page 17.
- **Current review-input SHA-256: `d5516ae04325e4e9bd836322f6f7f267bd093528cf318eba9b64bad7bc2ca7c9`** (supersedes `7b04fa71…`).
- `docs/TECHNICAL_DESIGN.md` git blob `f4d41cec0038ca4625b29ddd3315b02a86aeb151`, SHA-256
  `523049917f7b66324a7f169b9ea939693a76d69a047642b62542e3adffe2e084`. PDF git blob
  `75e9787b83e9eb315fb99c504d8c98eb4fa55f17`, SHA-256 `02981885777c299180a73eb4b4e028bb45ecc33b75d9bf55bfebe2a9f1cc9b18`.
