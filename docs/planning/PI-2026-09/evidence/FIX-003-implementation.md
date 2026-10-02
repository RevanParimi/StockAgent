# FIX-003 implementation receipt — a bank's income statement reads as complete

- **Story:** [FIX-003](../stories/FIX-003.md), routed on 1 Oct by the
  [SA-003 enforce decision](SA-003-enforce-decision-2026-10-01.md) (NO-GO).
- **Context:** implemented on 2 Oct 2026, about 01:25–02:00 IST, in a **new conversation** opened
  with "continue". A same-conversation self-review was done. It is not the fresh review, which
  needs another new conversation. STATE: `review_required`.
- **Baseline:** `df34176` (the KT bump after FIX-002's commit). The working tree also carried the
  uncommitted FIX-002 push record in STATE and HANDOFF, which this phase keeps.
- **Nothing** was committed, pushed, deployed or configured, and no production state was read.
  One read-only probe of public yfinance data was run locally (below); it wrote only to ignored
  `analysis_data/fix003/`.

## What it does, in one example

On 1 Oct YES Bank's fundamentals came back with the June quarter's figures: revenue
₹4,655.98 Cr, dated 30 Jun 2026.

- **Before:** a bank's statement has no "Operating Income", "EBIT" or "Gross Profit" row.
  `get_financials` substituted zeros for the operating line and listed `operating_income` in
  `missing_rows`. So the section read `fallback`, the gate abstained, and the prompt showed
  "EBITDA Margin: 0.0%". The same happened on every analysis of YESBANK, IDFCFIRSTB, RBLBANK and
  FEDERALBNK: 17 of 78 analyses from 28 Sep to 1 Oct.
- **After:** the statement has both interest rows and no operating row, so it is read as a
  **bank-format** statement. The section reads `ok`, and its reason says "bank-format statement
  (interest income and net interest income, no operating-income row): operating margin not
  reported". The prompt shows net interest income per quarter (₹2,785.48 Cr for June) where
  EBITDA stood. The margin line says "Operating margin: not reported (bank-format statement, no
  operating-income line)". No zero is shown.

## The change

One code file: **`services/data/fetchers/fundamentals.py`**.

- New `_is_bank_format(index)`: true when the statement has both `Interest Income` and
  `Net Interest Income`, and none of `Operating Income`, `EBIT` or `Gross Profit`. It uses the
  same membership test as `get_row`, so a statement with any row the operating line is read
  from stays standard.
- `get_financials`:
  - for a bank-format statement, the second line is `Net Interest Income` (label
    `net_interest_income`), not the operating line. SA-002's M2 rule applies to it unchanged: a
    blank newest quarter is named in `missing_values`, and `as_of` is the newest quarter with
    every figure;
  - revenue is read and required exactly as before;
  - new keys, additive: `statement_format` (`"bank"` or `"standard"`) and, for a bank,
    `quarterly_net_interest_income_cr`. For a bank `quarterly_ebitda_cr` and
    `ebitda_margin_pct` are `None`, not zeros. A standard statement's keys and values are
    unchanged.
- `get_fundamentals_result`: the status rules are unchanged. The reason gains the bank-format
  note first, so it appears with `ok`, `stale` and `fallback` alike.
- `_format_fundamentals`: a bank-format statement shows "Net interest income (quarterly)" and the
  "not reported" margin line. A standard statement's text is byte-identical (tested exactly).
- `get_peer_margins` leaves a bank out instead of returning its missing margin. It has no caller
  today; before, it would have returned the substituted 0.0.

## Acceptance criteria

| Criterion | Result | Evidence |
|---|---|---|
| A bank-shaped statement is complete: `ok` (or `stale` by age), not `fallback`; the reason names the bank format | Met | Shape table rows 1, 2 and 7, under 3 tickers; the end-to-end test for the 4 banks |
| No invented zero: no 0.0 operating income, no 0.0% EBITDA margin; one option chosen and recorded | Met | Every bank row asserts no "EBITDA" and the "not reported" line; the exact-text test; D2 |
| A non-bank statement without an operating row stays `fallback` | Met | Shape table row 8 |
| A bank-shaped statement without revenue stays `fallback` | Met | Shape table row 3 |
| A present row with a blank newest quarter stays `fallback` (SA-002 M2) | Met | Rows 4, 5 and 6 (revenue, net interest income, every row) |
| The gate follows: `essential_unusable` empty; gate `actionable` or `degraded`, never `abstain` for fundamentals | Met | `TestTheGateFollows`, 4 banks through the real bundle, health record and gate; the counterpart still abstains |
| Shape, not sector: PAYTM (EBIT + net interest income) stays standard | Met | Row 11; every row runs under YESBANK, PAYTM and TATAMOTORS with the same result |
| Deterministic fixtures, blocked transports, no real yfinance call | Met | The SA-002 `market` fixture patches `yfinance.Ticker`/`download`; its autouse guard and SA-005's hermetic guard fail any connection |

**The independent invariant** (`TestStatementShapes`, 15 shapes × 3 tickers):

| # | Shape | Expected | Bank format |
|---|---|---|---|
| 1 | YES Bank's rows, fresh | `ok` | yes |
| 2 | the same, newest quarter 300 days old | `stale` | yes |
| 3 | bank rows, no revenue row | `fallback` | yes |
| 4 | bank rows, newest revenue blank | `fallback` | yes |
| 5 | bank rows, newest net interest income blank | `fallback` | yes |
| 6 | bank rows, newest quarter listed with every figure blank | `fallback` | yes |
| 7 | bank rows, only an older net interest income blank | `ok` | yes |
| 8 | non-bank: revenue, pre-tax and net income; no operating or interest row | `fallback` | no |
| 9 | interest income without net interest income, no operating row | `fallback` | no |
| 10 | net interest income without interest income, no operating row | `fallback` | no |
| 11 | PAYTM's rows: EBIT beside net interest income | `ok` | no |
| 12 | TCS's rows: both interest rows beside operating rows | `ok` | no |
| 13 | bank rows plus a gross-profit row | `ok` | no |
| 14 | bank rows plus an EBIT row | `ok` | no |
| 15 | revenue and operating income | `ok` | no |

- **Expected values** are what each shape means, written by hand; none is computed by the changed
  code. A guard test checks that each row's "bank format" flag matches its rows, so the table
  cannot drift into vacuity.
- **Fixture rows** are the row names yfinance listed for these companies on 2 Oct. The banks'
  newest-quarter figures are the probe's; the older quarters are made up (each 2% smaller).
- **The exact-text tests** derive their expected lines by hand from the fixture's figures (for
  example, QoQ 4,655.98 / 4,562.86 − 1 = +2.0%).

## Decisions for the reviewer

- **D1. The card's shape rule, unchanged:** both interest rows, and no operating row. The probe
  supports it. All 8 lenders probed match (YESBANK, IDFCFIRSTB, RBLBANK, FEDERALBNK, HDFCBANK,
  SBIN, CANBK, BAJFINANCE). None of the 6 non-lenders does (PAYTM, TCS, TATAELXSI, MARUTI, TMPV,
  OLECTRA). TCS lists both interest rows, but beside its operating rows. No single row is present
  in every lender and absent from every non-lender, so no one "bank row" would do.
- **D2. The prompt says operating margin is not reported (the card's first option),** and the
  quarterly line shows net interest income, labelled, where EBITDA stood. Why:
  - the banking prompts ask for net interest income growth, QoQ and YoY
    (`banking_bfsi/prompts/fundamentals.py` and `unified.py`), and it is the line a bank reports
    instead of an operating line;
  - pre-tax income, the card's example, comes after provisions, so one-off credit costs move it.
    A pre-tax margin would also be a new derived figure that no prompt asks for.
- **D3. Net interest income is held to SA-002's M2 rule,** because the prompt shows it in the
  operating line's place: a blank newest quarter makes the section `fallback`. Interest income is
  only part of the shape test; it is neither shown nor checked for blanks.
- **D4. Lenders count, by shape:** BAJFINANCE, a non-bank lender, reports the same format and is
  read the same way. The card's rule is the statement's shape, not the business's licence.
- **D5. `get_peer_margins` leaves a bank out** rather than report a margin it does not have. No
  caller uses it today.
- **D6. KT "Current gap" refreshed.** It said how often the gate would abstain was "not yet
  measured"; it now cites the 1 Oct decision (25 of 78, 32%; 17 the banks, 2 the resolution
  defect).

## Checks

- **Environment:** Windows, the project venv `.stockai` (Python 3.13), the SA-005 hermetic guard
  (no network, an empty working directory per test).
- **New tests:** `tests/unit/shared/test_bank_statement_fix003.py`, **55 tests** (8 functions: the
  shape table 15 × 3 = 45; the vacuity guard; 4 no-invented-zero tests; the gate for 4 banks; the
  counterpart). It reuses the SA-002 provider fixtures and `_run` from
  `test_data_health_contract.py`.
- **The original defect:** with `df34176`'s `fundamentals.py` put back, **28 of the 55 fail**:
  every bank row of the table (7 × 3), the bank text, structured-result and peer tests, and the
  gate for all 4 banks. The 27 that pass include the exact standard-statement text, so that text
  is unchanged.
- **Mutations** (`mutate_fix003.py` in the session scratchpad; each source restored and checked by
  SHA-256): **12 of 12 caught** on the final bytes.

  | Mutation | Caught by |
  |---|---|
  | M1 the original defect (the baseline file) | the shape table (YES Bank's shape) |
  | M2 decided by the ticker's name, not the shape | the shape table (bank shape under PAYTM) |
  | M3 net interest income alone marks a bank | row 10 |
  | M4 operating rows not checked | row 12 (TCS's shape) |
  | M5 a blank net interest income not checked | row 5 |
  | M6 a bank's absent revenue row ignored | row 3 |
  | M7 a bank's margin shown as 0.0% | row 1's text assertions |
  | M8 the reason does not name the bank format | row 1's reason assertion |
  | M9 peer margins show a bank as 0.0 | the peer-margins test |
  | M10 a bank's structured margin 0.0, not None | the structured-result test |
  | M11 a bank's line read from interest income | row 5 |
  | M12 a bank shape without revenue read as standard | row 3 |

- **Focused:** `python -m pytest -q -p no:cacheprovider` over the new file,
  `tests/unit/shared/test_data_health_contract.py`, `test_data_health_record.py`,
  `test_decision_gate_sa003.py`, `tests/unit/intelligence/rl/test_decision_gate_learning_sa003.py`
  and `tests/integration/test_orchestrator.py`: **327 passed** on the final bytes. The older SA-002 and SA-003 tests are unchanged.
- **Full suite:** `python -m pytest tests -q -p no:cacheprovider` gave **4111 passed, 12 skipped,
  0 failed** (6 min 11 s; 4056 + the 55 new). It ran on the final bytes (`fundamentals.py`
  SHA-256 `153348ea…` before and after). `data/`, `logs/` and `outputs/` were unchanged: 800
  files, digest `76c155f8…` before and after.
  - An earlier full run gave the same count (6 min 30 s). Two cosmetic line wraps in
    `fundamentals.py` (a docstring line and the margin string) landed after it had imported the
    module, so the new tests, the focused set, the mutations and the full suite were all re-run on
    the final bytes. The figures above are from those re-runs.
- **Guards:** `scripts/ci/check_broad_except.py` OK (154 grandfathered; no new broad except).
  `check_kt_docs` errors `[]` (427 links, 84 linked sources, PDF 34 pages, source `283b1e88…`).

## Documentation

- **KT §4:** a new "Bank statements (FIX-003)" paragraph after SA-002's data-health example: the
  measured cause, the shape rule, what stays `fallback`, and the YES Bank example. The
  "Current gap" paragraph now cites the 1 Oct measurement (D6).
- **Guide 02-H** (new): YESBANK, FEDERALBNK and PAYTM after results. The banks read `ok` with
  "bank-format statement", show net interest income and "Operating margin: not reported", and the
  gate does not abstain for fundamentals. PAYTM still shows EBITDA.
- **SA-045 card:** a routed-input note. A Quality factor must treat a bank's margin as not
  applicable, and must not rank a bank's net interest income against another company's operating
  income.
- **The PDF** was rebuilt.
- **The landing commit needs a KT bump.** The KT now links `fundamentals.py`, which changes after
  the declared `656ed71`.

## Rollout

- After the fresh review: commit, KT bump, and push in a job-free window (00:10–06:20 IST is the
  safest). Not on the 1st before the 09:00 monthly forecast. No configuration change.
- **Production check (read-only):** the next scheduled review's health lines for YESBANK,
  IDFCFIRSTB, RBLBANK and FEDERALBNK show no `essential unusable=fundamentals:fallback`.
- **Their October envelopes keep the abstaining gate they were issued with.** The next SA-003
  decision counts only rows issued after this fix. That needs either the 1 Nov forecast, or an
  owner-authorised regeneration of those four envelopes (the manual re-forecast, as in FIX-002's
  rollout, subject to the monthly re-forecast cap).

## Open limitations

- **A non-bank statement that lists both interest rows and no operating row** would be read as
  bank-format. None of the 6 non-lenders probed does; each reports EBIT. Its revenue and
  freshness would still be checked, and the prompt would say the margin is not reported, not
  show zero.
- **A bank's "Total Revenue"** in yfinance is not its gross interest income. YES Bank's is
  ₹4,655.98 Cr against interest income of ₹8,054.49 Cr and net interest income of ₹2,785.48 Cr,
  so it looks like net interest income plus other income (an inference; not checked against the
  bank's filing). It is not comparable with a non-bank's revenue. It is shown as before.
- **Revenue "YoY" still compares with three quarters back** (SA-002 re-review N1, routed to
  SA-045). FIX-003 leaves it unchanged.
- **Insurers and other financial formats were not probed.** They change only if their statement
  has both interest rows and no operating row.

## The probe (read-only, public data)

`analysis_data/fix003/rows_probe.py` (ignored) read `quarterly_income_stmt` for 14 listings on
2 Oct at about 01:30 IST and wrote row names and newest-quarter figures to
`analysis_data/fix003/rows_2026-10-02.json`. Summary (₹ Cr, quarter ended 30 Jun 2026, except
HDFCBANK's newest listed quarter, 30 Jun 2025):

| Listing | Revenue | Operating income / EBIT / gross profit | Interest income | Net interest income |
|---|---|---|---|---|
| YESBANK | 4,655.98 | none | 8,054.49 | 2,785.48 |
| IDFCFIRSTB | 8,283.72 | none | 11,051.09 | 5,974.12 |
| RBLBANK | 2,577.29 | none | 3,840.24 | 1,655.25 |
| FEDERALBNK | 4,405.53 | none | 7,861.58 | 3,324.00 |
| PAYTM | 2,448.00 | 72 / 254 / 753 | no row | −7.00 |
| TCS | 72,275.00 | 17,317 / 18,217 / 28,784 | row present, newest blank | −273.00 |

HDFCBANK, SBIN, CANBK and BAJFINANCE have the bank shape too. TATAELXSI, MARUTI, TMPV and OLECTRA
have the standard shape.

## Manifest and digests

- **Review input:** [FIX-003-manifest.json](FIX-003-manifest.json). The SHA-256 of its LF bytes is
  **`ee46239f5b997ea2e53323eec004f3dff21123163498a5d2f9826c275fa8aaba`**, and `kt_manifest.py verify` gives 6 files and 0 mismatches.
  - It lists the 6 files changed since `df34176`: 1 code file, 1 new test file, and 4 documents
    including the PDF.
- **Excluded:** STATE.json, HANDOFF.md and this receipt. The FIX-003 card is unchanged.
- **Full diff** against `df34176`: **`57e847720b41c39a73557a34aaa8e8303dbd419671be6c97ee8076a0c72ff171`**, 32,922 bytes over 5 text files. The PDF is
  pinned by its blob, `5bb57d77…`.
  - **To rebuild it:** take every manifest path except the PDF, sorted.
  - For a path tracked at `df34176`, use `git diff --no-color --no-ext-diff df34176 -- PATH`.
  - For a new file, use `git diff --no-color --no-ext-diff --no-index -- /dev/null PATH`.
  - Concatenate the outputs.
