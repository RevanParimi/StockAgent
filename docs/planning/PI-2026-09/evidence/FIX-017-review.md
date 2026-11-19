# FIX-017 — fresh review receipt

**Story:** [FIX-017](../stories/FIX-017.md): the holding sync reads every NSE corporate-action
row it is given, under NSE's code. Implementation receipt:
[FIX-017-implementation.md](FIX-017-implementation.md).

**Review context: fresh session.** Autopilot session `1119-2135-p4` on the code-server, a new
conversation opened with "continue", Thursday 19 Nov 2026 from about 21:35 IST, outside a push
window. The implementing session (`1119-1710-p3`) had ended at 21:35 IST. `main` = `23cf041`,
`origin/main` = `3f26ae5` after a fetch. Production was not read. NSE's public corporate-action
lists were read (public data, no account, no production state). No model was called; nothing
was pushed, deployed, run or sent.

**Lane:** decision path, confirmed. The sync sets the adjusted quantity and average price that
the price-path stop and the targets read, and the grading reads the same record.

**Verdict: ACCEPTED** for `b425f8c`. Every acceptance criterion is met, and the card's three
hard-review questions hold for every row NSE lists today. Two low findings, both latent or older
than this story, go to BACKLOG (B-23, B-24); one wording nit joins B-22. Merged into `main` as
`9c582e0`, whose code is byte-identical to `b425f8c`.

## Review input, verified

| Check | Result |
| --- | --- |
| Branch | `story/FIX-017` = `b425f8c`, one commit on `a09bde8` (`git merge-base main story/FIX-017`) |
| Diff digest | `git diff a09bde8 b425f8c \| sha256sum` = `77549aaf2d3aac58…` = the implementation receipt |
| Files | the receipt's 8 paths, +509 / −103 |
| Where it ran | a detached worktree of `b425f8c` in the scratchpad |
| Merge | `git merge-tree main story/FIX-017`: clean (`23cf041` holds records only). `9c582e0` against `b425f8c`: only `docs/planning/` differs. Against `story/PR-015`: the same three KT conflicts as before the merge, no new one |

## Contract checked

I traced a holding from `pipeline.run_post_review_pipeline` through `sync_corp_actions`
(`nse_symbol(symbol, today)`, the fetch, `action_record`, `_read_ratios`, `sync_reading`), the
locked second phase (`apply_actions_to_holding` on a fresh load, the dividend credit and its
`DIV` ledger row) to the holding's `adj_qty`, `adj_avg_price` and `dividends_received`, which
`unrealised_pnl_pct` and the advisor read. The grading reads the same record
(`results.corp_actions_fn`: `action_record(read_corp_actions(nse_symbol(symbol)))`), and so does
PR-005's purchase record (`cases._corp_record`, now under `nse_symbol` too).

- **One reading.** The sync applies only the record's bonus and split ratios, so the sync's
  ratio for a row is the product of the grading's. A row the record does not read is never a
  share-count change for the sync.
- **NSE's code.** `nse_symbol` is called inside the per-holding `try`, so a registry error skips
  that holding with a warning, as a failed fetch does. The review day is the date passed; in
  production it is today, as for the grading.
- **Idempotency.** Keys are unchanged for single-ratio rows. A step is applied once per ex-date
  and kind, checked against the fresh holding's applied actions in the locked phase, so a
  reworded row or a second sync applies nothing.
- **Order.** Steps are sorted before dividends and the sort by ex-date is stable, so a dividend
  ex the same day as a split would be credited on the split shares. NSE lists no such pair today
  (below).

## Adversarial examples, worked independently

1. **Every row NSE lists today.** I read NSE's lists for the 202 configured tickers under
   `nse_symbol`'s codes (19 Nov about 21:40 IST: 3,310 rows, no failed read) and put each row
   through the sync before (`a09bde8`'s `parse_action`) and after (`sync_reading`), for a holding
   of 100 shares at ₹1,000 bought on 2 Jan 2000. All rows read alike except nine, each the
   intended way and each checked by hand:

   | Ticker, ex | NSE's row | Before | Now |
   |---|---|---|---|
   | BAJFINANCE 8 Sep 2016 | Bonus 1:1/Face Value Split (Sub-Division) - From Rs 10/- … To Rs 2/- … | ×2 | ×10 |
   | JSWSTEEL 4 Jan 2017 | Fv Splt Frm Rs 10 To Re 1 | ×1 | ×10 |
   | KNRCON 13 Dec 2016 | Fv Splt Frm Rs 10 To Rs 2 | ×1 | ×5 |
   | M&M 29 Mar 2010 | Fv Split Rs.10 To Rs.5 | ×1 | ×2 |
   | SBIN 20 Nov 2014 | Face Value Split Rs.10/- To Re.1/- Per Share | ×1 | ×10 |
   | SUZLON 21 Jan 2008 | Fv Split Rs.10/- To Rs.2/ | ×1 | ×5 |
   | ZEEL 3 Mar 2014 | Bonus Preference Shares 21:1 | ×22 | ×1, named |
   | DRREDDY 17 Mar 2011 | Scheme Of Arrangement - Bonus Debentures 6:1 | ×7 | ×1, named |
   | TVSMOTOR 25 Aug 2025 | Scheme Of Arrangement - Bonus Ncrps 4:1 | ×5 | ×1, named |

   No dividend credit changed. No ticker lists a dividend and a share-count step on one day. The
   sync names 7 rows for that holding: the three above, BHARTIARTL 2009 ("Agm/Div-Rs.2/Fv
   Rs10tors5"), BLUEDART 2014 and BRITANNIA 2019 and 2021 (bonus debentures with no "n:m" ratio).
   No row gives two ratios of one kind on one day. Raw lists and the comparison:
   `analysis_data/fix017_review/` (this device only).
2. **The aliases.** NSE lists nothing under CANARABANK, TVSMOTORS or LTIM today (0 rows each)
   and 20 rows each under CANBK, TVSMOTOR and LTM, which the sync now asks for. ZOMATO's code
   ETERNAL lists nothing (KT's FIX-018 note). TATAMOTORS and HEXAWARE, quarantined, are asked
   under TMPV and HEXT, as the grading already did.
3. **Canara Bank by hand.** 100 shares at ₹500 bought 10 Jan 2024; the 1:5 split ex 15 May
   2024; a ₹16.10 dividend ex 13 Jun 2024. By hand: 500 shares at ₹100, ₹8,050 of dividends,
   0% on the price at ₹100. The test gives the same through the real fetch with an NSE stub that
   answers only CANBK.
4. **A bonus of other securities beside a scheme.** Hypothetical wordings put through
   `action_record`: "Scheme Of Arrangement - Bonus 4:1 Ncrps" reads ×5; "… Issue Of Debentures
   As Bonus 6:1" ×7; "… Bonus 1:1 Redeemable Preference Shares" ×2; "Rights 1:5 And Bonus 1:1
   Debentures" ×2. Without the scheme, rights or demerger word the same rows are refused. Finding
   R1.

## Tests and the original defect

- The table test's expectations are worked from the rows, not from the code: quantity, average
  price, dividends and the gap line for each, and the holding's worth at the ex-day's fair close
  unchanged. The agreement test is implementation-shaped by intent (it pins sync = grading).
- **Reviewer mutants, 9 of 9 caught** by the FIX-017, FIX-016 and corporate-action suites: the
  sync asking under the app's code; the sync applying `parse_action` as before; no once-per-day
  check; short split words unread; PR-005's record under the app's code; two ratios applying the
  first; a bonus-and-split row as its bonus alone; no "earlier reading" line; a consolidation read
  as a split. Each was put back after its run; the worktree was clean at the end.
- Mocked boundaries: the NSE client is a stub in every new test (`_make_nse_client` or `fetch=`);
  the symbol resolver's learned cache is emptied, and the registry is the repository's own file.
  No test reaches the network.

## Findings

| # | Severity | Where | What | Disposition |
|---|---|---|---|---|
| R1 | low; latent and older than this story | `core/portfolio/corp_actions.py:168-169` (`_read_ratios`, beside a change) | Beside a scheme, rights issue or demerger only the words stating the ratio are checked, so a bonus of preference shares, debentures or NCRPS named outside them ("Scheme Of Arrangement - Bonus 4:1 Ncrps") is read as an equity bonus: 100 shares at ₹1,000 become 500 at ₹200, a 400% gain at an unchanged price. None of the 3,310 rows has that shape (NSE's scheme bonuses name the security between "bonus" and the ratio, or give no ratio), and before FIX-017 the sync applied every such row anyway. The self-review's answer to hard-review question 1 ("only when every word is …") does not hold beside a change, and KT section 6 ("every word is known") does not say so either | [BACKLOG](../BACKLOG.md) B-23 |
| R2 | low; older than this story, not changed by it | `corp_actions.parse_action` (the dividend reader) | A row naming two dividend amounts credits only the first, and a row naming a ratio and a dividend credits none. 68 of the 3,310 rows name two amounts, most of them "Dividend … & Special Dividend …": TCS 16 Jan 2026 (Rs 11 and Rs 46: 20 shares are credited ₹220 of ₹1,140), ABBOTINDIA 24 Jul 2026 (Rs 525 and Rs 131), THERMAX 3 Jul 2026 (Rs 14 and Rs 6). HINDPETRO 2017, ICICIBANK 2017 and NIACL 2018 name a bonus and a dividend. Cash and the P&L the stops read are understated by the missing amount | [BACKLOG](../BACKLOG.md) B-24 |
| N1 | nit | `corp_actions.sync_reading` | If NSE adds a second ratio for a day after the sync applied the first, the line says "neither is applied" though the first was; the holding keeps it, as it should | Joined to B-22 (same trigger) |

None found against the card's contract: no ratio NSE does not state for equity shares in rows of
the shapes NSE uses today, no unread row moving a quantity or cost, and the sync and the grading
reading every row alike.

## Commands and results

```
git diff a09bde8 b425f8c | sha256sum                       # 77549aaf2d3aac58…
git worktree add --detach <scratchpad>/wt-fix017 b425f8c
.stockai/bin/python -m pytest -q tests/unit/test_corp_sync_fix017.py \
    tests/unit/test_portfolio_corp_actions.py tests/unit/test_exit_fix016.py \
    tests/unit/test_investment_case_pr005.py tests/unit/test_exit_evidence_pr009.py \
    tests/unit/test_exit_fix018.py tests/unit/test_registry_fix019.py \
    tests/unit/test_corporate_events_fetcher.py           # in the worktree: 342 passed (78 s)
<scratchpad>/fetch_lists.py, <scratchpad>/compare.py     # NSE's lists; before against after
<scratchpad>/mutants.py                                  # 9 of 9 caught
.stockai/bin/python -m pytest -q                         # 6,978 passed, 12 skipped, 1 xfailed
.stockai/bin/python scripts/docs/check_kt_docs.py
.stockai/bin/python scripts/ci/check_broad_except.py
```

Python 3.13.5 (`.stockai`), code-server. **Full suite** on `9c582e0` with this phase's records
in the working tree (the records commit's tree but for this line; its code is `b425f8c`'s):
**6,978 passed, 12 skipped, 1 xfailed, 0 failed** (6 min 53 s, Thu 19 Nov about 22:00 IST), as
the implementation receipt. `check_kt_docs.py`: no errors. `check_broad_except.py`: OK (148
grandfathered).

**Not exercised:** production (no read; no holding's applied actions seen since 29 Oct's probe);
a live review run; NSE's client itself (stubbed in tests, real only in the read above).

## Acceptance checklist

- A table test of every NSE subject quoted, plus plain bonus, split and dividend rows, worked by
  hand: **met** (`test_every_row_has_the_effect_worked_by_hand`, 11 rows).
- A Canara Bank holding through the real sync, with a fixture answering only NSE's code: **met**.
- Idempotent by key; a row applied under the old reading not applied twice; what happens to such
  holdings: **met** (four tests and the receipt's "Idempotency").
- KT section on corporate actions (section 6, "Corporate-action sync"), CODEBASE row, guide case
  08-I, the full suite: **met**. Guide 08-I's label now reads accepted; found on the way,
  case 07-U's PR-005 label still read "awaiting another fresh review" after its merge
  (`40d04d5`) and now reads accepted.

## Production verification

`pending_deployment`: it ships with the next push (the runner's, from Fri 20 Nov 00:10 IST).
`FIX-017-W1` (STATE `pending_production_checks`) reads the first 16:30 review after the deploy.
On 29 Oct no production holding had a bonus or split applied and none was an alias, so no
existing holding is expected to change; a holding bought since, with a listed bonus or split after
its buy, would be adjusted on that first review.

## Decision

**ACCEPTED** for `b425f8c`, merged as `9c582e0`. FIX-017 is `done`; its production verification
is separate. Follow-ups: BACKLOG B-23 and B-24, and N1 in B-22.
