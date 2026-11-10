# FIX-026 — fresh review receipt

**Story:** [FIX-026](../stories/FIX-026.md): the analysis names a new stock's sector from our list; an
empty or unknown sector is flagged. **Implementation receipt:** [FIX-026-implementation](FIX-026-implementation.md).

**Context:** fresh-session review (9 Nov 2026, a new conversation opened with "continue"; the
implementation session's chat was not read). `git pull --ff-only`: already up to date, nothing from the
other device.

**Verdict: ACCEPTED**, for the reviewed input below, with the limits under "Not exercised". No critical
or high finding. One low, one inference-level note and one rollout watch item; none needs a code change
before commit.

## Reviewed input

- Baseline HEAD `412645f`, nothing staged, 29 changed paths in the working tree.
- Manifest [FIX-026-manifest.json](FIX-026-manifest.json) `253620a2`, 25 files: `kt_manifest.py verify`
  reports 0 mismatches against the working tree.
- Stored diff `analysis_data/fix026/fix026.diff` is 195,461 B with SHA-256 `0da6b47a...`, as recorded. I
  did not re-derive it with the implementer's script; the manifest verify is what ties the tree to the
  receipt.
- `docs/TECHNICAL_DESIGN.md` SHA-256 `30df47f0...` equals the PDF source hash the receipt records.

## Contract checked

Read in full: `core/discovery/sector_naming.py`, and the diffs of `deep_dive.py`, `candidates.py`,
`shelf.py`, `unified_analyst.py`, `base_orchestrator.py`, `discovery_api.py`, `core/discovery/__init__.py`;
the buy path in `core/portfolio/pipeline.py`.

- **An answer outside the list is never stored.** `read_answer` accepts only membership in the 22 keys
  (trimmed, lower-cased) or a reasoned `generic`; `decide_key` stores anything else as `generic` with
  source `unnamed`.
- **Nothing buys an unnamed idea.** The only route from the shelf to a buy is `buy_candidates`, which
  runs before the SWITCH legs and the deployment (`core/portfolio/pipeline.py`, `shelf_ideas` is
  reassigned from its result, and `[]` if it raises). It excludes an idea with `unnamed_why`. Promote
  refuses it (409). A watchlist stock needs a configured own key or a ticker-map key.
- **Decided once.** `known_key` order managed, ticker map, earlier key; `apply_redives` renames only an
  idea with no configured key.
- **The graph guess decides nothing stored.** `route` picks the graph; `sector` comes from `decide_key`.
  `graph` in the result follows `route`.
- **No extra paid call.** One `analyse` call per dive; the question is appended to the unified
  analyst's user prompt, and without it the prompt is unchanged.

## Independent adversarial examples

Run by hand against the real `read_answer` / `decide_key` with the real 22-key list:

| Input | Result |
|---|---|
| bank by Yahoo, answer `" IT_Sector "`, `yahoo_fits: true` | key `it_sector`, no problem (see M-1) |
| `{"key": "pharma", "yahoo_fits": "yes"}` | `pharma`, `yahoo_fits` None (strict bool) |
| `{"key": ["pharma"]}` | malformed, stored `generic` unnamed |
| `{"key": "generic"}` no reason | `generic_without_reason`, unnamed |
| bare string `"pharma"` | malformed, unnamed |
| `"Pharma\n"` | `pharma` |

## Findings

| # | Sev | Where | Finding | Disposition |
|---|---|---|---|---|
| M-1 | low (disclosed) | `sector_naming.read_answer` | A valid but wrong key with `yahoo_fits: true` (a bank named `it_sector`) passes: no rule catches it. The week's summary prints Yahoo's labels beside every named key, so a human can. | Accepted limit, as the receipt says. First Saturday's sample (guide 06-M) is the check. SA-026 owns key consolidation. |
| M-2 | note (inference) | `unified_analyst.py`, native graph prompts | Whether the model answers an appended block when a native prompt says "no keys beyond the schema below" cannot be shown by tests; a miss is loud (`no_answer`, unnamed), not silent. | Production observation at the first Saturday. |
| M-3 | watch | rollout | Every legacy `generic` idea is unbuyable until re-dived and takes the first re-dive slots; the watchdog may notify on its first run. | Already in the receipt's Rollout; deploy only in a job-free window, owner's word. |

No finding about financial targets, issue-time information, price identity or sizing: the change touches
none of them. The shelf's cap and SA-050's cap now read the same key.

## Commands and results

Environment: `.stockai/Scripts/python.exe` (Python 3.13), Windows, from the repository root.

- Focused: `tests/unit/test_sector_naming_fix026.py test_idea_supply_pr004.py test_surveillance_sector_fix011.py
  test_discovery_deep_dive.py test_deploy_idle_cash_sa049.py shared/test_decision_gate_sa003.py`:
  **292 passed**, 0 failed (96 s).
- `check_broad_except`: OK (148 grandfathered, unchanged).
- `check_kt_docs`: the one expected error ("KT links core/discovery/sector_naming.py, which is absent at its
  declared revision b065da303cf1"), cleared by the commit-time header bump.

## Not exercised

- The full suite was not re-run; I rely on the implementer's 6,203 passed / 12 skipped / 1 xfailed /
  0 failed (14m07s). The implementer's 33 mutants were not re-run either.
- No real LLM, Yahoo or NSE call; no production state, log or network read. The real-answer sample the card
  asks for does not exist yet.
- No browser (no UI change beyond a 409 on promote).

## Acceptance checklist

- Drug maker named `pharma`, shelved `pharma`, counted by both caps: met (story tests, both caps).
- Each fail-loud case has its named record, summary line and watchdog warning: met (story tests).
- Held stock keeps its key through a differing re-analysis, disagreement recorded: met.
- No fixed Yahoo-to-key table decides a stored key: met (tables, `infer_sector`, `shelf_sector` deleted).
- Docs (KT s8 and s12, guide 06-M, CODEBASE, AUTOPILOT_GUIDE) and PDF source hash: met.

## Decision and follow-up state

FIX-026 is **accepted** for the reviewed revision. Production verification: `pending_deployment`.
Commit-time edits listed in the implementation receipt remain to be done at the owner's word (KT header
and section 1 and 12, guide 06-M status, PDF). Next ready story: **FIX-027**, in a new conversation.
