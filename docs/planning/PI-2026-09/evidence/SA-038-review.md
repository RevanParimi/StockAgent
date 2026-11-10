# SA-038 review receipt — judging the lapsed production-verification milestones

## Fresh-session review: ACCEPTED (2026-10-06)

- **What was reviewed:** [SA-038](../stories/SA-038.md), as described in the
  [implementation receipt](SA-038-implementation.md).
  - Seven entries are deleted from `config/milestones.yaml`, and `ipo_p0_live_window_check` is
    re-dated to 2026-10-31 with a dated reason. The registry header now says how an entry is
    retired.
  - Five new tests over the real registry.
  - KT §10, guide case 12-I, notes on the SA-002, SA-012, SA-014 and SA-046 cards, and the SA-039
    activation record. The PDF is rebuilt.
- **Context:** a fresh-session review in a new conversation, 6 Oct 2026, from about 11:14 IST.
  - It is not the conversation that implemented SA-038, and it did not read that chat.
  - It read the card, the receipt, REVIEW.md, the audit's §1.1, the whole diff and every deleted
    entry's own acceptance text. It traced the watchdog engine, the runner, the registry loader,
    the `registry_is_current` check, the research loop's provenance path, the dossier merge and
    distillation, event ingestion, and SA-009's recorded production inventory.
- **Nothing** was committed, pushed, deployed or configured. No production state was read, and no
  test or probe made a network call. The owner's probe output was read only as the saved,
  count-only copy in ignored `analysis_data/sa038/probe_20261006.txt`.

### Review input verified

- The reviewer's own script (`analysis_data/sa038/review/rv_verify.py`, not the implementer's
  `diff_digest.py` or `kt_manifest.py`) checked the input:
  - the manifest's LF SHA-256 is **`e3a251d5…`**, as recorded;
  - every one of the 10 paths matches both its git blob id (computed and from `git hash-object`)
    and its SHA-256: **0 mismatches**;
  - the diff rebuilt by the receipt's recipe is **`22196d37…`**, 34,650 bytes, as recorded.
- Files changed outside the manifest, and why that is fine:
  - STATE, HANDOFF and the implementation receipt are excluded by design.
  - `.claude/settings.local.json` is the owner's own allow rules. It is excluded from the manifest
    and from the commit.
  - The FIX-004 card and the IPO plan note were written after the manifest, on the owner's
    decisions of about 11:05 IST. Both were read: they match those decisions and change no code.

### Contract checked

- **The card's criteria.**
  - Each lapsed entry is judged with a sanitized evidence note, then removed, or re-dated with a
    stated reason.
  - B6 is carried to SA-002. Hard-bind is folded into SA-012 and SA-014.
  - `ipo_p0_live_window_check` stays open.
  - No lapsed entry is left without a dated reason.
  - SA-038 cannot be accepted while SA-039's verification is `pending_observation` with no dated
    reason.
- **The engine, by code** (`core/ops/watchdog/engine.py:103-205`).
  - A pending entry past its deadline fires `critical` every 7 days (`_LAPSED_REPEAT_DAYS`).
  - A deadline-only entry is silent until `deadline - today <= lead_days`. So the re-dated IPO
    entry (31 Oct, 3 lead days) is silent until 28 Oct, then warns daily, as KT §10 and guide 12-I
    say.
  - Only registry entries are walked. A deleted entry gets no notice, and its state is dropped
    (receipt I1).
  - `registry_is_current` compares the deployed file with origin/main
    (`checks.py:206-231`). Every push redeploys, so the registry edit cannot leave it pending.
- **Each judgement, against its evidence class:**

| Entry | Receipt | Review |
|---|---|---|
| `atlas_c11_cutover` | Deleted; code | Upheld. `config.yaml:811` has `enabled: true` at `a502cf7`, and `atlas_cutover_pending` returns `satisfied` once the flag resolves true (`checks.py:105-119`). |
| `f3_checkpoint` | Deleted; probe | Upheld, with **L2**. Lessons: 1,021 of 1,041 post-F3 lessons carry evidence, all 2,005 items well formed. Dossier: the literal check ("populated on real rows") is met by 13 well-formed rows. Only the research loop sets `source`, and its rows carry a `[research]` or `[research-partial]` prefix (`question_researcher.py:300`, `:306`). The share among those rows was not counted. |
| `hard_bind_observation` | Deleted, not judged; decision | Upheld. The card and the audit both say to fold it. The SA-012 and SA-014 notes name both cuts (2026-07-17 and 2026-08-03). |
| `a1_routing_prod_verify` | Deleted; "Verified" | Deletion upheld; **the label is corrected (M1)**. |
| `b1_run_history_prod_verify` | Deleted; probe | Upheld. The oldest of 888 rows is the first writer (26 Aug, 16:33 IST), and the JSONL agrees. Every deploy since then would have reset the count if `data/` did not back the path. |
| `b2_data_health_prod_verify` | Deleted; B6 half to SA-002 | Upheld. All four acceptances were measured on 26 Aug and are recorded in the deleted entry. The open half is SA-002's `production_verification`. |
| `e1_error_capture_prod_verify` | Deleted; (c) not applicable | Upheld, with **L1**: acceptance (e) was never judged. |
| `ipo_p0_live_window_check` | Kept; re-dated 2026-10-31 | Upheld. The reason is dated and measured, and closing the entry is IPO-0a's, which the owner has since decided. |
| `ipo_verdicts_visible_gate` | Unchanged | In date. |

- **SA-039 backstop.** STATE now reads `verified`, with `verified_ist` 2026-10-01 10:25 and a note
  naming SA-038 as the recorder. The P1-P3 results in `pending_production_checks` support it. The
  card's acceptance condition is met.

### Independent adversarial examples

1. **A1(b), traced across stories.** The deleted A1 entry asked one thing in (b): after A1's
   deploy on 25 Aug, does a *new* `automobile/<TICKER>` store appear for a ticker of another
   sector?
   - The three-loops spec's production inventory (24 Aug) counted 13 duplicate stores.
   - SA-009's production inventory of 30 Sep (`974e6043`, in STATE) counted 16 wrong-roster
     `automobile/` copies. Compared with the 10 Sep audit, they had "gained feedback and graded
     days (150 conflicting)". SA-009 inferred that the writer was the old self-heal backfill on
     each restart.
   - So the bleed went on after A1. It stopped only with SA-009: its writer fix was deployed on
     30 Sep, and its quarantine moved the 16 copies on 1 Oct 00:10. The 6 Oct probe then saw
     none, across 5 restarts and 3 reviews.
   - The counts are not strictly comparable: the spec counted duplicate *weight stores*, SA-009
     counted stores. But the later writes into the copies are recorded either way. See M1.
2. **E1, every acceptance.** The deleted entry lists five acceptances, (a) to (e). The 26 Aug
   result closed (a), (b) and (d), and said (c) would not close. (e), "run one script under
   `railway ssh` and confirm it produces `app_logs` rows", appears nowhere: not in the 26 Aug
   result, not in the audit's §1.1, and not in the receipt. See L1.
3. **A future re-date, and the owner's next commit.** Mutant 04 sets the IPO deadline to 6 Oct,
   a day already past at the first run. Tests 1, 2 and 5 fail. Separately: when the owner's
   decided IPO deletion lands, tests 3 and 5 go red unless they are edited in the same commit
   (I2).

### Tests

- **Do the tests fail on the original defect?** The reviewer wrote its own plugin
  (`analysis_data/sa038/review/rv_swap_plugin.py`). It replaces the registry bytes that
  `tests/hermetic.py` seeds into each test's sandbox, so the tracked file is never touched. It also
  wrote its own variants (`rv_mutants.py`), different from the implementer's where it could:

| Variant | Result |
|---|---|
| Control: the final registry | 5 pass |
| Baseline registry (`a502cf7`) | 4 fail (1, 2, 3, 5); test 4 passes, because every old milestone had a deadline |
| `f3_checkpoint` re-added, still lapsed | 3 fail (1, 2, 3) |
| The same entry under a **new** id | 2 fail (1, 2). So the lapse is caught, not only the id list |
| IPO deadline set to 2026-10-06 | 3 fail (1, 2, 5) |
| Re-date `was` date after the re-date | 1 fails (5) |
| Re-date with no reason | 1 fails (5) |
| IPO deadline removed | 2 fail (4, 5) |

  All 7 variants are caught. The expected results come from the engine's rules, not from the
  tests' own output. Test 2's "no notice names a deleted id" check is real: alert kinds are
  `watchdog_<id>_<level>` (`runner.py:66`).
- **Mocked boundaries.** Test 2 replaces `run_check` (every check `pending`), `_run_preps`,
  `_broadcast` and `_send_email` (which raises). No real SMTP, push or HTTP call is possible, and
  the hermetic guard blocks the network as well.
- **Focused:** `tests/unit/ops`, `tests/unit/test_delivery_alerts.py` and
  `tests/unit/shared/test_instrument_identity_sa008.py` gave **207 passed**. The new file alone
  gave 5 passed.
- **Full suite:** `python -m pytest tests -q -p no:cacheprovider` gave **4161 passed, 12 skipped,
  0 failed** (9 min 42 s). `data/`, `logs/` and `outputs/` were unchanged: 798 files, and the
  reviewer's own fingerprint (`rv_tree.py`) read `dec323a4…` before and after.

### Findings

| ID | Severity | Location | Finding | Disposition |
|---|---|---|---|---|
| M1 | Medium (evidence record) | [implementation receipt](SA-038-implementation.md), judgements table, `a1_routing_prod_verify` row ("Deleted. Verified.") and "A1(b): met" | A1(b) asked whether A1 stopped the bleed. By SA-009's recorded 30 Sep inventory, it did not: copies of other sectors' tickers kept receiving writes (and grew from 13 to 16) until SA-009's writer fix and the 1 Oct quarantine. The 6 Oct probe measures SA-009's fix, not A1's. The deletion is right, but "Verified" credits A1 with a fix it did not make, in the one story whose job is honest judgement records. | **Fixed in review (documentation).** Corrected judgement: *deleted as superseded by SA-009, which stopped the bleed; A1(b) itself was not met.* It is recorded here, in STATE (SA-038 `review_note`) and in HANDOFF, with a pointer added at the top of the receipt's judgements. No signal is lost: SA-009's own `production_verification` keeps the scorecard check. |
| L1 | Low (judgement record) | Deleted E1 entry, acceptance (e) (`a502cf7:config/milestones.yaml`); receipt E1 row | (e), "a standalone script's warnings reach `app_logs` in production", was neither measured nor decided. | **Judged in review, by code; production unmeasured.** All five entry points call `configure_logging` (`core/audit/cli.py:57`, `scripts/atlas_etl.py:419`, `scripts/ipo_backfill.py:362`, `scripts/seed_autopilot.py:104`, `services/scheduler/run_schedule.py:66`), and `test_error_capture_context.py:452` pins a script entry point archiving its warnings. Production runs one uvicorn process that hosts the scheduler (`Dockerfile:48`, `server.py:67`), and (b) measured that path. Standalone scripts run only by hand. A note is on the [SA-031](../stories/SA-031.md) card. |
| L2 | Low (evidence limit) | Receipt, F3 dossier half | The share of research rows that carry a `source` was not counted; 13 of 391 is the count of sourced rows in the capped, distilled buffer. | **Routed:** the [FIX-004](../stories/FIX-004.md) count probe reads the same dossier files. It now also counts `[research` rows with and without `source`. If most research rows are unsourced, open a fix; do not restore the milestone. **Result, 7 Oct (measured):** 12 of 17 post-F3 research rows (71%) carry a source, and none of the 406 others does. No fix is needed, and the milestone stays retired ([probe receipt](FIX-004-probe-2026-10-06.md)). |
| L3 | Low (documentation) | `docs/TECHNICAL_DESIGN.md:25` | After SA-038 recorded SA-039 as `verified`, KT §1 still said "verification after the next reviews is pending". | **Fixed in review.** |
| I1 | Info | Receipt, "No August rows remain, inferred from the capped buffer" | The weekly distillation also removes observations (`dossier_curator.py:250-252`), and 114 pre-F3 rows remain while the average dossier holds about 21 of 30. So the cap alone does not explain it. No judgement depends on August rows. | No action. |
| I2 | Info (forward) | `tests/unit/ops/test_milestones_judged_sa038.py:94`, `:108`, `:116` | The owner decided to delete `ipo_p0_live_window_check` in a separate commit. That commit must also add the id to `RETIRED`, delete line 94, and delete the two IPO asserts in test 5 (lines 108 and 116). Its loop then guards future re-dates. Otherwise the suite goes red. | Recipe recorded in HANDOFF. |
| I3 | Info | Same file, line 43 | `REDATED_RE` accepts only `by SA-NNN`. A FIX or IPO story that re-dates an entry fails test 5 loudly. | No action. |
| I4 | Info (older documentation drift) | `docs/TECHNICAL_DESIGN.md:25`, KT §12 status paragraph | KT §1 said "no quarantine has run in production" for SA-009, but one ran on 1 Oct. The §12 paragraph stopped at SA-009 and called every other story `todo`, which has been wrong since SA-010. | **Fixed in review**, alongside SA-038's own status. |

None is critical or high.

### Decisions

- **Hard-bind, deleted without a verdict, is a decision recorded as such.** It is not a silenced
  check. The card and the audit both prescribe the fold.
- **The F3 deletion stands.** Lessons are F3's main carrier, and the evidence there is strong and
  measured. The dossier half's literal check is met, the limit is stated in the receipt, and the
  rate question now has an owner (L2). The pre-registered rule was weak, and the receipt says so
  itself (I5). That is the honest way to handle it.
- **M1 is corrected in documentation, not by reopening.** The entry's question, "has the bleed
  stopped?", has a measured yes today. Only the attribution was wrong.

### Commands and results

- Environment: Windows 11, `.stockai` venv (Python 3.13, pytest 9.0.3), with the SA-005 hermetic
  guard active.
- `python analysis_data/sa038/review/rv_verify.py`: 0 mismatches, `e3a251d5…`, `22196d37…`.
- `python -m pytest tests/unit/ops tests/unit/test_delivery_alerts.py
  tests/unit/shared/test_instrument_identity_sa008.py -q -p no:cacheprovider`: 207 passed.
- `bash analysis_data/sa038/review/rv_run_mutants.sh`: the table above.
- `python -m pytest tests -q -p no:cacheprovider`: 4161 passed, 12 skipped, 0 failed.
- `PYTHONPATH=analysis_data/kt_docs_deps python scripts/docs/check_kt_docs.py`: errors `[]` on the
  reviewed KT (source `8f89c401…`), and again after the review edits (PDF rebuilt, source `3bb23a99…`, 443 local links).
- **Not exercised:**
  - the production 06:30 run and the Sunday heartbeat (pending deploy);
  - E1 (e) in production;
  - the research-row share;
  - the real checks behind each entry, because the tests force `pending` on purpose.

### Review edits (documentation only)

- KT: §1 (SA-039 `verified`; SA-009's quarantine applied; an SA-038 sentence), §10 (SA-038
  accepted), and the §12 status paragraph (SA-010 and SA-038). The PDF is rebuilt.
- Guide 12-I status line.
- Cards: [SA-031](../stories/SA-031.md) (L1), [FIX-004](../stories/FIX-004.md) (L2), and
  [SA-046](../stories/SA-046.md) (F1 is now FIX-004).
- The implementation receipt: one pointer to M1 above its judgements table.
- STATE and HANDOFF.
- No code, test or registry byte changed. After these edits, `kt_manifest.py verify
  SA-038-manifest.json` mismatches exactly the KT, the PDF, the guide and SA-046 (checked).

### Acceptance and what remains

- **Verdict: ACCEPTED** for review input `e3a251d5…` (diff `22196d37…`), plus the
  documentation-only review edits above.
- **Production verification: `pending_deployment`.** It is not committed. After an authorized
  deploy:
  - the next 06:30 `ops_watchdog` run sends no `critical` for any of the 7 deleted ids;
  - the Sunday heartbeat lists only the IPO milestones and the invariants.
- **Next, at the owner's word** (decisions of about 11:05 IST):
  1. Commit SA-038 without `.claude/settings.local.json`.
  2. Delete the IPO entry as a separate commit, with the I2 test edits.
  3. Push in the 12:05-14:55 IST window.
  4. Then FIX-004, starting with its owner-run count probe, which now includes L2.
