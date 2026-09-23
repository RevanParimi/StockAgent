# DOC-001 — Fresh-session hard review

Date: **2026-09-22**. Phase: **fresh-session review** under [REVIEW.md](../REVIEW.md).
Review context: **fresh session**, separate conversation from the 2026-09-15
implementation. No same-conversation self-review is reused as the gate.

**Verdict: `changes_requested`.** Two high findings block acceptance at the
reviewed revision. The document's *technical substance* was verified against
source and is accurate everywhere it was probed; the blockers are artifact
provenance, a stale binary deliverable and unmaintained sections, not wrong
engineering.

## Reviewed revision and digest verification

| Item | Recorded | Observed |
|---|---|---|
| Implementation baseline | `9a805878ed19c0cda7833d5b897ac05ee407436d` | Declared in the receipt, manifest and KT header |
| Reviewed revision | — | **`d105a44a06d430304a724f34ac3dc329a4ca0d87`** (HEAD, clean worktree) |
| Review-input manifest SHA-256 | `90c005c46417db97d6e3f6feba2431aae66a8ad93037e852e9823ad7936125c0` | **`1b622788284870638aabbeac1c00e54743365fc2d86de9ef229533869dd025bc`** on disk |
| Reviewed-payload rollup (new) | — | `79d387cb8d3bab6b9f7f7d92a8fad918569b7df8bdbc7a69af5c6cda14b41b5b` |

Manifest payload re-verification (20 files): **15 match, 5 drift, 0 missing.**

Drift classification, by replaying every revision from `042c05f^..HEAD` under
both LF and CRLF:

| File | Status |
|---|---|
| `docs/ARCHITECTURE.md` | Matched at `042c05f`; changed at `3f1f29d` (23→24 job IDs). Legitimate per-story maintenance. |
| `docs/PRODUCT_MAP.md` | Matched at `042c05f`; changed at `3f1f29d` (23→24 job IDs). Legitimate. |
| `docs/README.md` | Matched at `042c05f`; changed at `3f1f29d` (23→24 job IDs). Legitimate. |
| `docs/TEAM_TESTING_GUIDE.md` | Matched through `3f1f29d`; cases 05-F (`548045f`) and 05-G (`ed1b900`) added. Legitimate. |
| `docs/TECHNICAL_DESIGN.md` | **Never matched at any revision** — see F1. |

The `90c005c4…` digest is reproducible only by re-expanding the manifest's LF
bytes to CRLF. The receipt's instruction "recompute the digest from the
manifest's exact bytes" therefore cannot be followed as written; it silently
assumed the pre-commit Windows worktree encoding.

## Findings

| # | Severity | Location | Finding | Disposition |
|---|---|---|---|---|
| F1 | **High** | `evidence/DOC-001-manifest.json`, `STATE.json` | Recorded digest for the primary deliverable exists in no revision | Blocks acceptance |
| F2 | **High** | `docs/StockAgent-Three-Loops.pdf` | Deliverable PDF contradicts its source; misstates the job inventory | Blocks acceptance; rebuild blocked on tooling |
| F3 | Medium | `docs/TECHNICAL_DESIGN.md:3,5` | Header declares a baseline the body no longer describes | Fix with F2 |
| F4 | Medium | `docs/TECHNICAL_DESIGN.md` §10, §11 | Shipped delivery work (`590bc9f`) undocumented; §11 stale vs §8 | Fix with F2 |
| F5 | Medium | `tests/unit/test_atlas_outbox.py:204,217` | Two tests depend on an ambient credential; receipt's test claim no longer reproduces | Route to SA-005/SA-006 |
| F6 | Low | `STATE.json` | `updated_at: 2026-09-15` while history carries 09-19 and 09-21 | Corrected by this phase |

### F1 (High) — the reviewed artifact cannot be reconstituted

The manifest records `docs/TECHNICAL_DESIGN.md` = `15dc554239971a1ad8fefd820b8f1e2ae364cd71e4fd7691e13609b66a95f5d7`.
Hashing that path at **every one of 846 revisions** (`git log --all`), under both
LF and CRLF, yields **30 distinct digests and no match**. The committed value at
`042c05f` — the commit that introduced the manifest — is `b90b3202b216…`; at HEAD
it is `c07205ce6d15…`.

The bytes the implementer validated, hashed and built the PDF from were edited
before `042c05f` committed them, without the manifest being regenerated.

**Impact:** REVIEW.md step 1 ("verify revision/digest; investigate drift before
signing off") cannot be satisfied for the story's central deliverable. A reviewer
cannot confirm that the 323-test run, the link/inventory checks and the visual PDF
inspection were performed against the text now in the repository.

**Reproduction:** `sha256sum docs/TECHNICAL_DESIGN.md` at any revision; compare
with the manifest entry.

### F2 (High) — the PDF deliverable contradicts its own source

`check_kt_docs.py` fails with exactly one error: `PDF source digest does not
match current Markdown`. The PDF footer carries source digest `15dc55423997` and
baseline `9a805878…`; the current Markdown hashes `c07205ce6d15…`.

The divergence is material, not cosmetic. Extracted PDF text contains:

- **"23 possible job IDs"** — the Markdown, `scheduler.py` and three other
  documents all say **24**.
- none of `ipo_deep_dive`, `deep_dive.py`, `narrate.py`, `verdicts.py`,
  `grade_ipo_lane` — the whole of PI Prospect Sprints 2–4, which §8 and §9 of
  the Markdown do document.

DOC-001 names the PDF as a deliverable and AGENTS.md requires regeneration
whenever `TECHNICAL_DESIGN.md` changes. A reader handed the PDF gets a wrong
scheduler inventory.

**Blocker (concrete, recorded):** `node` and `npx` are absent from this machine;
`node_modules/playwright` is vendored but unusable without a Node runtime and a
Chromium download. `scripts/docs/build_kt_pdf.py` cannot run here. This is an
environment blocker, not a disagreement about the fix.

### F3 (Medium) — the KT declares a baseline it no longer describes

`docs/TECHNICAL_DESIGN.md:3` says **Edition 2026-09-15**; line 5 says
**Code inspected: `9a805878…`**. But §8 and §9 document `ipo_deep_dive`,
`deep_dive.py`, `narrate.py` and `grade_ipo_lane`, and I verified each is
**absent at `9a805878`** (`git show 9a805878:services/scheduler/python/scheduler.py | grep -c ipo_deep_dive` → 0;
`git cat-file -e 9a805878:core/ipo/narrate.py` → missing). The body tracks HEAD.

`check_kt_docs.py` enforces the body against the *working tree* (job-ID set
equality, PI rows, config claims) but has **no guard on the header's revision
claim** — which is why this drifted silently through three IPO stories while
every automated check stayed green. The edition line and code-inspected line
should move with the body, and the check script should assert it.

### F4 (Medium) — §10 and §11 were not maintained for shipped work

`590bc9f` shipped 192 lines across `core/delivery/channels.py` and
`core/delivery/outbox.py`: `resolve_recipient()` (line 108), an HTTPS Resend
transport, `EMAIL_TRANSPORT` selection and `outbox.last_error`. The KT mentions
**none** of them (grep for `last_error|resend|resolve_recipient|EMAIL_TRANSPORT`
→ 0 hits) and §10 still presents "September 10 recorded email failures" as the
delivery picture, after the outage was diagnosed and fixed on 2026-09-21.

§11's IPO row likewise still lists current implementation as only "Calendar,
history, snapshots and recent-listing screening" while §8 documents the full
dark P3 model — the two sections now disagree. §13's KT-session table has the
same small gap.

This violates REVIEW.md's "Documentation is part of each story". The omission
belongs to `590bc9f`, not to the 2026-09-15 implementation, but it is present at
the revision under review and DOC-001's acceptance criterion requires current
code and dated production observation to stay distinct and correct.

### F5 (Medium) — the receipt's test result no longer reproduces

Re-running the receipt's exact command yields **324 tests, 2 failures, 0 errors,
188.2 s** against the recorded **323 passed, 0 failed, 114.08 s**.

Both failures are in `tests/unit/test_atlas_outbox.py` and share one cause:

```
test_send_row_caps_push_and_passes_html_to_email  assert (False, "no email on file for user 'u1'") == (True, '')
test_send_row_returns_transport_reason            assert 'Errno 101' in "no email on file for user 'u1'"
```

`outbox.py:142-144` calls `resolve_recipient(row["user_id"])` and returns
`(False, "no email on file…")` **before** reaching the `send_email_result` the
tests monkeypatch. `resolve_recipient` never raises: with no `users.db` row and
no `DELIVERY_EMAIL_TO` it returns `""`.

Minimal reproduction — the tests depend on an ambient credential:

```
DELIVERY_EMAIL_TO="test@example.invalid" pytest tests/unit/test_atlas_outbox.py -q  → 11 passed
DELIVERY_EMAIL_TO=""                     pytest tests/unit/test_atlas_outbox.py -q  → 2 failed, 9 passed
```

They pass in a normal developer run because `.env` supplies the value through
dotenv, which the KT harness deliberately disables. That is the opposite of
isolation: a green suite here depends on a real delivery address being present.
This is direct input to **SA-005** (clean isolated test baseline) and
**SA-006** (delivery transport), and it qualifies the handoff's "2832 passed"
claim for `590bc9f`, which was measured with that credential loaded.

Not a DOC-001 implementation defect — it was introduced after the receipt — but
it means the receipt's headline evidence is no longer reproducible.

## What was verified and found correct

The KT's technical substance held up under every independent trace attempted.
None of these relied on the document's own wording for the expected value.

- **All 24 scheduled jobs.** `check_kt_docs.py` verifies job *IDs* only, so I
  re-derived every `CronTrigger` from the scheduler AST and resolved each
  config-driven field against `config.yaml` and `settings/base.py`.
  **All 24 IDs and all 24 schedules match the KT table**, including the three
  config-indirect ones (`ipo_refresh_am` 08:00, `ipo_refresh_pm` 17:45 from
  `refresh_hour_live`/`refresh_minute_live`; `ipo_deep_dive` 19:00;
  `ops_watchdog` 06:30; `rl_daily_review` from `feedback_cron`).
- **§5's grading defect, reproduced exactly.** With issue close 100, predicted
  110, actual 105: the real move is **+5% UP**, `(105-110)/110 = -4.55%`, and
  with `RL_FLAT_THRESHOLD_PCT = 0.3` (config `rl.flat_threshold_pct`)
  `classify_direction` returns **DOWN**. Confirmed live in the data flow at
  `daily_review.py:554-555`, where it feeds `is_direction_correct` →
  `direction_correct` → WeightAdapter credit. The KT documents a real,
  consequential defect and attributes it correctly to SA-012/013/014.
- **§7 P/L.** The worked example (2,000 → buy 10@100 → mark 110 → sell 4@110)
  is arithmetically exact at every figure, including equity staying 2,100. The
  documented read limits match `portfolio_api.py:328-329` (`limit=400` history,
  `limit=2000` transactions).
- **§8 IPO tracker weights.** 40/20/15/25 match `_SUB_WEIGHTS` in
  `ipo_tracker.py:38-39`, as does the first-cached-close fallback.
- **§6 advisor cascade.** EXIT > TRIM > ADD > HOLD matches `advisor.py:366-374`;
  SWITCH requires EXIT plus shelf ideas (`:378`); the softening applies to TRIM
  and never EXIT (`:386-390`), exactly as the KT states.
- **§8 P3 model and audit lane** accurately describe `deep_dive.py`,
  `narrate.py`, `verdicts.py`, `listing.py` and `grade_ipo_lane`, including the
  dark-until-gate constraint.
- **Harness isolation is real, not a success fixture.** `run_kt_checks.py`
  blocks `socket.connect/connect_ex/sendto/create_connection`, `Popen`,
  `os.system`, `requests`, `httpx` (sync and async), `urllib`, `smtplib`,
  `curl_cffi` and `pywebpush`, and disables dotenv. The only exception is a
  narrow loopback socketpair for Windows asyncio. No hidden real transport.
- **§1 evidence-label table** cleanly separates current code / locally checked /
  production observation / PI target, satisfying the story's first criterion.
- **Archive preserved.** `docs/archive/StockAgent-Three-Loops.original-before-2026-09-15.pdf`
  matches the required `1fc2402b…` byte-for-byte.
- **Testing guide.** 12 duties (HT-01…HT-12), **59** cases, globally marked
  NOT RUN at line 5, non-code-intensive, and explicitly disclaiming any
  implemented runtime approval gate. The 57→59 growth is correct per-story
  maintenance (05-F, 05-G).
- **Incremental documentation discipline is working.** The 23→24 job-count change
  propagated to four documents across the IPO stories — the practice DOC-001
  introduced is being followed.

## Commands, environment and results

```text
.stockai/Scripts/python.exe scripts/docs/check_kt_docs.py
.stockai/Scripts/python.exe scripts/docs/run_kt_checks.py --dependency-path analysis_data/audit_20260910/test_dependencies
.stockai/Scripts/python.exe -m pytest tests/unit/test_atlas_outbox.py -q   (with and without DELIVERY_EMAIL_TO)
git log --all / git show <rev>:<path>   (846-revision digest replay)
```

- Python 3.13.11, Windows, `.stockai` virtualenv. Worktree clean before and
  after; `data/nse/key_registry.json` unchanged (`db6bd9c5…`).
- `check_kt_docs.py`: 12 documents, **224** local links, 32 PI rows with
  dependency/title checks, 24 scheduler IDs, 13 configuration claims, 16 PDF
  pages, 34,937 characters — **1 error** (stale PDF digest, F2).
- `run_kt_checks.py`: **324 tests, 2 failures, 0 errors, 0 skipped, 188.2 s** (F5).

**Not exercised:** no full-suite run, no Linux/Python-3.11 parity, no browser
execution, no live provider or delivery transport, no authenticated UI
acceptance, no production inspection of any kind this session. The PDF was not
re-rendered or re-inspected visually — it cannot be rebuilt here (F2). The
historical bodies of PRODUCT_MAP and RL_DESIGN were not revalidated, consistent
with the implementation receipt's own scope note.

## Acceptance checklist

| Criterion | Verdict |
|---|---|
| Source-linked explanations distinguish code, local test, production, planned | **Partly** — §1's framework is sound, but F3 and F4 break it in practice |
| Concrete walkthroughs for jobs, three loops, IPO, advice vs portfolio, P/L, evaluation | **Met** — §2, §5–§9 verified against source |
| Every PI story maps to functionality and documentation | **Met** — 32 rows, dependencies and titles checked |
| Human testing guidance separate, initially unexecuted, no implied approval gate | **Met** |
| Validate links, inventory, PDF extraction/rendering, relevant tests in isolation | **Not met** — PDF check fails (F2); 2 test failures (F5) |
| Changed-file digest and limitations recorded in the receipt | **Not met** — F1 |

## Decision and follow-up state

**`changes_requested`.** DOC-001 returns to implementation. Required before the
next fresh review:

1. **F1/F3** — regenerate the manifest from committed bytes, state the
   line-ending convention used, and move the KT's edition/code-inspected header
   to the revision the body actually describes. Add a header-revision guard to
   `check_kt_docs.py` so this cannot drift silently again.
2. **F2** — rebuild `docs/StockAgent-Three-Loops.pdf` on a machine with Node
   LTS (`npx playwright install chromium`, then `python scripts/docs/build_kt_pdf.py`)
   until `check_kt_docs.py` is clean. Blocked on this machine.
3. **F4** — document `resolve_recipient`, the Resend transport, `EMAIL_TRANSPORT`
   and `outbox.last_error` in §10; update §11's IPO and delivery rows and §13's
   session table; re-date the September 10 delivery observation against the
   2026-09-21 resolution.
4. **F5** — carry to **SA-005** (isolate the two `test_atlas_outbox.py` tests
   from `DELIVERY_EMAIL_TO`) and note against **SA-006** that `590bc9f`'s green
   suite depended on that ambient credential.

Unchanged by this review: all 32 SA stories remain `todo`; no remediation is
accepted. `production_verification` for DOC-001 stays `not_applicable`
(documentation only). No application source, configuration, deployment, job,
notification, commit or push was performed — this review was read-only apart
from its own bookkeeping.
