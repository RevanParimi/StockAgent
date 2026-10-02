# FIX-003 review receipt — a bank's income statement reads as complete

## Fresh-session review: ACCEPTED (2026-10-02)

- **What was reviewed:** [FIX-003](../stories/FIX-003.md), as described in the
  [implementation receipt](FIX-003-implementation.md).
  - In `services/data/fetchers/fundamentals.py`, a statement with both `Interest Income` and
    `Net Interest Income` rows, and none of `Operating Income`, `EBIT` or `Gross Profit`, is
    now **bank-format**.
  - Its net interest income takes the operating line's place, and its margin is `None`, not
    0.0. The prompt says "Operating margin: not reported", and the reason names the format.
  - The change adds 55 tests, edits KT §4, guide case 02-H and the SA-045 card, and rebuilds the
    PDF.
- **Context:** a fresh-session review in a new conversation, 2 Oct 2026, about 06:12–06:30 IST.
  - It is not the conversation that implemented FIX-003, and it did not read that chat.
  - It read the card, the receipt, the diff and all of `fundamentals.py`.
  - It traced the consumers: `bundle_builder._fetch_fundamentals`, `data_health.assess_health`,
    `decision_gate.gate_from_health_row`, and the 11 legacy `builder.py` callers, which use only
    the text. It also checked the `src/backend` re-export shim, which nothing imports, and
    `get_peer_margins`, which has no caller.
  - It read the banking prompts and the implementer's ignored probe output, which is public
    yfinance data.
- **Nothing** was committed, pushed, deployed or configured, and no production state was read.

### Review input verified

- `kt_manifest.py verify FIX-003-manifest.json`: 6 files and 0 mismatches at the start. The
  manifest's LF SHA-256 is `ee46239f…`, as recorded.
- The full diff was rebuilt with the reviewer's own script (`analysis_data/fix003/review/rebuild_diff.py`)
  by the receipt's recipe. It gives `57e84772…`, 32,922 bytes, over 5 text files. The PDF blob was
  `5bb57d77…` at the start.
- `data/`, `logs/` and `outputs/` held 800 files with digest `76c155f8…` before and after the
  full suite. That is the implementer's digest too.

### Contract checked

- **The changed keys reach no other code.**
  - `get_financials` is called only by `get_fundamentals_result` and `get_peer_margins`, per a
    grep over every `.py` file.
  - `quarterly_ebitda_cr` and `ebitda_margin_pct` are `None` only for a bank. A bank never
    takes `_format_fundamentals`' standard branch, and `get_peer_margins` skips a `None`.
  - No code parses the rendered "EBITDA Margin" text.
- **The gate keys on status alone.**
  - `assess_health` lists an essential section as unusable when its status is neither live
    nor `n/a`. A reason on an `ok` section changes nothing.
  - SA-002 already returns `ok` with a reason, for example when shareholding fields are
    absent.
- **No cache sits before the fundamentals section** in the bundle builder. So the first analysis
  after a deploy reads the new shape.
- **The configuration:**
  - the freshness bound is 200 days (`config.yaml:657`);
  - the essential sections are the same for every sector (`config.yaml:649`). So the
    automobile orchestrator in the new gate test is a fair proxy, and probe Q3 repeats the
    test through the banking sector.
- **Production's blocker was fundamentals alone.** The SA-003 decision record has YESBANK's
  1 Oct forecast at "8 live, 1 fallback, dimensions 6/6": fundamentals was its only unusable
  essential section.
- **Not applicable:**
  - issue-time availability, horizon and idempotency: the statement is read at analysis
    time, the structured dict is never persisted, and no schema changes;
  - prompt changes reach bank-format statements only, which probe Q2 checks.

### Independent adversarial examples

Probes are in `analysis_data/fix003/review/test_fix003_review.py` (ignored). They use the SA-002
`market` fixture under the suite's hermetic guard. Each loads `df34176`'s `fundamentals.py` as a
separate module for comparison. **6 of 6 passed.**

| Probe | Example | Result |
|---|---|---|
| Q1 | **Every probed listing, by its real row set.** These are the 14 listings yfinance returned on 2 Oct, each with every row name (23–30 rows), the probe's newest figures and its own quarter count. | The 8 lenders go from `fallback` (the original code, with "EBITDA Margin: 0.0%") to `ok`. HDFCBANK is the exception: it reads `stale`, because its newest yfinance quarter is 30 Jun 2025. Each lender shows its net interest income and no EBITDA. The 6 non-lenders give the original code's text, status, `as_of` and reason exactly. |
| Q2 | **2,000 random statements:** random rows from 11 names, 1–6 quarters, random NaN cells, newest quarter 10–400 days old. | All 905 non-bank shapes equal the original code in text, status, `as_of` and reason. All 1,095 bank shapes match the reviewer's own rule, which is `fallback` only when revenue is absent or the newest revenue or net interest income is blank, and otherwise the freshness bound. All 1,095 read `fallback` under the original code. |
| Q3 | **The gate through the banking sector's own orchestrator** (`banking_bfsi`, 6 dimensions), with YES Bank's real row set | Under the original code: fundamentals `fallback`, `essential_unusable {fundamentals: fallback}`, and the gate abstains. This is production's 1 Oct row. Under the new code: fundamentals `ok`, `essential_unusable {}`, and the gate is `actionable`. |
| Q4 | A bank's statement also lists an `Operating Income` row with no figures | It reads standard and stays `fallback`, with the reason "no figure for: operating_income". See I1. |
| Q5 | RBL Bank's rows with one older net-interest-income quarter blank | `ok`, dated by the newest quarter. The reason names the format and "net_interest_income \<quarter\>". The blank cell renders as before SA-002. |

### Tests

- **The new tests are honest.**
  - The shape table's expected statuses are written by hand, and a vacuity guard ties each row's
    flag to its rows.
  - The exact-text expectations are derived by hand from the fixture's figures.
  - The bank fixtures carry yfinance's `Operating Expense` and `Operating Revenue` rows, as the
    real banks do, and neither is an operating-income row.
  - Every provider is patched by the SA-002 fixture. The full suite passed under SA-005's
    hermetic guard, which fails any outbound connection.
- **The original defect.** With `df34176`'s `fundamentals.py` loaded in memory in place of the
  module, **28 of the 55 fail**: every bank case. That matches the receipt.
- **Reviewer mutations** (in memory, by `swap_plugin.py`; no checkout file edited): **9 of 9
  caught.**

  | Mutation | Failed |
  |---|---|
  | RM1 net interest income alone marks a bank | 3 |
  | RM2 gross profit no longer an operating row | 3 |
  | RM3 the blank-cell rule skips the second line | 3 |
  | RM4 a bank's structured margin computed | 2 |
  | RM5 the reason stops naming the format | 21 |
  | RM6 the bank line labelled "EBITDA" | 26 |
  | RM7 decided by the ticker, not the shape | 22 |
  | RM8 the bank line read from interest income | 5 |
  | RM9 a bank without revenue let through | 3 |

### Findings

| ID | Severity | Location | Evidence | Disposition |
|---|---|---|---|---|
| L1 | Low (documentation; confirmed from the implementer's probe data) | `docs/TEAM_TESTING_GUIDE.md`, case 02-H | The case asked the tester to check that the section's revenue matches the bank's published results. yfinance's "Total Revenue" for YES Bank's June quarter is ₹4,655.98 Cr, below its own interest income row of ₹8,054.49 Cr. A filing's total income includes all interest earned, so the two cannot match. A tester following 02-H would record a false failure. The receipt lists this as a limitation; the guide did not follow it. | **Fixed in review.** 02-H now compares net interest income with the published figure and says why revenue is not compared. KT §4 states the same in one sentence. |
| I1 | Info (probe Q4) | `services/data/fetchers/fundamentals.py:67-70` | A bank whose yfinance statement lists an `Operating Income`, `EBIT` or `Gross Profit` row with no figures reads as standard and stays `fallback`. This is the card's row-presence rule, and it is the same test `get_row` uses. None of the 8 lenders probed on 2 Oct lists such a row. | No action. If a bank still shows `fundamentals:fallback` after the deploy, look here first. |

No critical, high or medium finding.

### Decisions

D1–D6 are upheld.

- **D1:** Q1 applied the rule to the probe's full row lists, not the summary.
- **D2:** the banking prompts ask for net interest income growth, QoQ and YoY
  (`banking_bfsi/prompts/fundamentals.py:35`, `unified.py:70`), and none asks for EBITDA.
- **D4:** BAJFINANCE reads as bank-format in Q1.
- **D5:** `get_peer_margins` has no caller.
- **D6:** the KT's numbers match the decision record. The banks' rows are 4 + 4 + 5 + 4 = 17,
  and the resolution rows are TVSMOTOR and TATAELXSI, so 25 of 78.

### Commands and results

Environment: Windows, the project venv `.stockai` (Python 3.13), with SA-005's hermetic guard.

| Check | Command | Result |
|---|---|---|
| Manifest | `python scripts/docs/kt_manifest.py verify docs/planning/PI-2026-09/evidence/FIX-003-manifest.json` | 6 files, 0 mismatches, `ee46239f…` |
| Diff | the receipt's recipe, by `rebuild_diff.py` | `57e84772…`, 32,922 bytes |
| Full suite | `python -m pytest tests -q -p no:cacheprovider --basetemp=<scratchpad>/bt_full` | **4111 passed, 12 skipped, 0 failed** (5 min 32 s, about 06:15–06:21 IST); `data/`, `logs/` and `outputs/` unchanged |
| Focused | the receipt's 6 files | 327 passed |
| The original defect | the new test file with `-p swap_plugin`, `FIX003_SRC=baseline` | 28 failed, 27 passed |
| Mutations | the same, `FIX003_SRC=RM1`…`RM9` | 9 of 9 caught |
| Probes | `python -m pytest -q -s -p no:cacheprovider -c pyproject.toml --rootdir . -p tests.conftest analysis_data/fix003/review/test_fix003_review.py` | 6 passed |
| Broad-except guard | `python scripts/ci/check_broad_except.py` | OK (154 grandfathered) |
| KT check | `python scripts/docs/check_kt_docs.py` (with `PYTHONPATH=analysis_data/kt_docs_deps`) | Before the edits: errors `[]`, 34 pages, source `283b1e88…`, the manifest's KT. After the edits and the rebuild: errors `[]`, 429 links, 34 pages, source `8c60e10e…` |

**Not exercised:**
- No real yfinance call. The row sets are the implementer's 2 Oct probe.
- Insurers and other financial formats were not probed, as the receipt says.
- One probe run that overlapped the full suite failed at session start, with a missing
  `stockagent-drill-*` temp directory. It looks like an artifact of two pytest sessions sharing
  `%TEMP%`. Every later run, made with nothing running in parallel, passed.

### Review edits (documentation only)

- **KT §4:**
  - the status now reads "accepted by its fresh review on 2026-10-02, not yet committed";
  - one sentence says a bank's revenue is yfinance's "Total Revenue", not the filing's total
    income (L1).
- **Guide 02-H:** the comparison (L1) and the status.
- **The PDF** was rebuilt: source `8c60e10e…`, 34 pages, blob `5d2320ad…`.
- `verify FIX-003-manifest.json` now mismatches exactly the KT, the PDF and the guide. No code
  or test byte changed.

### Acceptance and what remains

| Criterion | Result |
|---|---|
| A bank-shaped statement is complete: `ok`, or `stale` by age, and the reason names the format | Met (shape rows 1, 2 and 7 under 3 tickers; Q1 on 8 real lenders; Q2) |
| No invented zero; one option chosen and recorded | Met (no "EBITDA" and the "not reported" line in every bank case; the structured margin is `None`; D2) |
| A non-bank without an operating row, a bank without revenue, and a blank newest quarter stay `fallback` | Met (rows 3–6 and 8–10; Q2's oracle) |
| The gate follows | Met (the 4 banks end to end; Q3 through `banking_bfsi`, from abstain to actionable) |
| Shape, not sector: PAYTM stays standard | Met (row 11; Q1 on PAYTM's real rows; RM7 caught) |
| Deterministic fixtures, blocked transports, an independent shape table | Met |
| KT §4 and guide 02-H describe it; the PDF matches its source | Met, with the review edits |

- **Production verification:** `pending_deployment`. After commit, push and deploy (read-only):
  - the next scheduled review's health lines for YESBANK, IDFCFIRSTB, RBLBANK and FEDERALBNK
    show no `essential unusable=fundamentals:fallback`;
  - their fundamentals sections give the reason "bank-format statement";
  - their prompts then show net interest income, not "EBITDA Margin: 0.0%", so the banks'
    fundamentals scores may move. SA-039's `observe` keeps the weights unchanged.
  - The October envelopes keep the gate they were issued with. The next SA-003 decision counts
    only rows issued after the deploy.

## Verdict

**ACCEPTED.**
- The reviewed revision is the uncommitted working tree on `df34176`, pinned by review input
  `ee46239f…` and diff `57e84772…`, plus the documentation-only review edits above.
- FIX-003 is `done`, and its `production_verification` is `pending_deployment`.
- **Next:**
  1. commit, a KT bump and a push, at the owner's word, in a job-free window. The KT links
     `fundamentals.py`, so the bump must declare the new commit;
  2. then SA-010's implementation, in a new conversation.
