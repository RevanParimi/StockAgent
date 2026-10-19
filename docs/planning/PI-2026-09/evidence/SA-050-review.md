# SA-050 — fresh-session review receipt

**Story:** [SA-050](../stories/SA-050.md): one sizing rule for every autopilot buy.
**Context:** a **fresh-session review**, 18 Oct 2026, about 17:05–17:40 IST. Session
stockagent-main-68, a new conversation opened with "continue"; all 18 peers were idle. It is
not the implementing conversation (stockagent-main-e7).
**Reviewed:** the uncommitted working tree on `85e447b1a4e60ac8b3cd4feb530962ca2c0cc5d4`.
- Input [SA-050-manifest.json](SA-050-manifest.json) `d2c13ba8…`: 25 files, **0 mismatches**
  at the start and at the end (`kt_manifest.py verify`, and the reviewer's own
  `git hash-object` pass).
- Diff rebuilt by the reviewer (`analysis_data/sa050_review/rev_digest.py`): it takes the paths
  from `git status`, not from the implementer's list, and gives **`c4b58a22…`, 118,037 bytes, 24
  paths**, the receipt's digest. No changed path is missing from the manifest.

**Verdict: ACCEPTED.** No critical, high or medium finding. Four low findings: R3 is a
wording edit at commit, and R1, R2 and R4 are routed to later stories' cards. Nothing was
committed, pushed or deployed, no production state was read and no message was sent.

## In one example

The reviewer's own trace RT1, through the real pipeline:

- **The day.** ACMESOLAR (₹2,27,000) and BETA (₹1,70,000) both breach their stops on one day,
  in a ₹10 L portfolio. The only shelf idea, NEWPHARMA at ₹530, is the best destination for
  both.
- **Before SA-050.** The first switch bought 428 shares and the second 320 more, so NEWPHARMA
  became 39.6% of equity.
- **Now.** The first switch buys 188 shares (₹99,640), stopped by the 10% position cap. The
  second has ₹360 of room, so it buys nothing. Its SELL in the ledger says why:

  ```text
  exit_full; buy leg skipped: NEWPHARMA: the 10% position cap leaves room for less than one share at ₹530; ₹1,70,000 stays in cash
  ```

- **One gap (R2).** The `switch_buy_skipped` alert does not fire for that second leg, because
  the pipeline counts the first leg's BUY of NEWPHARMA as "bought".

## Contract checked

| Card requirement | Evidence | Result |
|---|---|---|
| The ₹2.27 L switch buys at most the 10% position, with a `capped` note | story test; RT1, leg 1 | met: 188 shares, the note |
| A buy that would breach the sector cap is cut, or skipped under one share, with the reason | story tests; RT3 (20 sector-bound buys, 283 skipped legs, each SELL with its reason) | met |
| ADD keeps today's behaviour when no cap binds | characterization test; RT3 | met, with R1's one-share float edge (low) |
| Property: no autopilot buy over either cap; cash at or above the floor | story property test (300 runs); RT3 (400 runs, exact arithmetic) | met |
| The 11 Oct weights 13.4% and 5.6%; WELCORP may ADD, FEDERALBNK may not | story test; RT2 through `run_post_review_pipeline` and the weekly review | met |
| The WELCORP switch 34% above its band is not bought; the reason and the cash recorded | story test (33.6%) | met |
| Property: no new position above `entry_high` or at or below `invalidation_level` | story property test; RT3 | met |
| A switch through `run_post_review_pipeline`, with the transaction and the note | story test (record and enforce); RT1 | met |
| Hard review: no buy path bypasses the rule | the reviewer's grep, below | met |
| Docs and human tests describe the behaviour | KT section 6, AUTOPILOT_GUIDE, guide 07-F/I/J, README, CODEBASE, PRODUCT_MAP | met, with R3's wording edit for 07-J |

**Every buy path.** The grep for `side="BUY"` outside tests finds four places:

- `core/portfolio/autopilot.py:277` and `:322`: the SWITCH and ADD legs. Both go through
  `sizing.size_buy`, and the SWITCH leg also passes `sizing.entry_check`.
- `services/api/routes/portfolio_api.py:161`: the manual add, out of scope by the card.
- `scripts/seed_autopilot.py:80`: the operator's one-time seed (L3).

`services/data/fetchers/nse_market.py:122` labels NSE bulk deals and is not a trade. The
pipeline is the only caller of `execute_advice` (`core/portfolio/pipeline.py:307`), and it
passes `shelf_index`. Nothing else changes `cash_deployable` downward.

**Data flow traced** (RT2, the 11 Oct shape):

1. The pipeline prices both holdings.
2. `sizing.weights` gives equity ₹9,98,725.40, so FEDERALBNK is 13.42% and WELCORP 5.55%.
3. `build_signals` and `decide` (with a bullish, accurate forecast injected after the real
   weights): WELCORP ADD; FEDERALBNK HOLD with `POSITION_LARGE` and no
   `SECTOR_CONCENTRATION_HIGH`.
4. `execute_advice` buys 5 WELCORP (`add_tranche`), and cash ends at ₹7,96,095.
5. The ledger and `portfolio.json` agree.
6. `build_weekly_review` gives banking 13.4%, capital_goods 6.9% and cash 79.7%, and flags
   nothing.

The old modules (RV_SWAP=base) give WELCORP HOLD.

**Other checks:**

- Idempotency: a rerun of the same day adds no trade and does not append the skip reason
  twice (RT1).
- The SELL's note is changed before `append_transactions`, so the persisted ledger carries it.
  `txn_id` does not depend on the note.
- Missing data: a holding without a close is valued at cost and not advised. Closes are
  `dropna`'d upstream, so a NaN cannot reach the caps.
- One active shelf idea per symbol (`core/discovery/shelf.py:78`), so the band lookup is
  unambiguous.
- SWITCH fires only after EXIT (`advisor.decide`), so a refused buy leg leaves a plain exit
  and cash, never a sale made only for the switch.

## Rulings on the implementer's decisions

- **D2 accepted:** `advisor.max_sector_pct`. One key next to `max_position_pct` serves the
  note, the weekly flag and the cap. No code or environment variable reads the old key; it
  survives only in historical plans and the card.
- **D3, D4, D5, D6, D9, D11, D12, D13, D14 accepted.**
- **D7 / L1 accepted:** an ADD skipped by the rule is only logged, like every other ADD skip
  before SA-050. SA-049's card already requires "every non-buy says why".
- **D8 accepted:** the band applies to buys that open a position, as the card says.
- **D10 accepted:** "underweight" is about current exposure, so market shares are the right
  quantity. The story test pins it.
- **L2–L5 stand as documented.** PR-004's card does re-dive ideas older than 30 days, as L4
  says.

## Findings

| ID | Severity | Location | Trigger → observed / expected | Disposition |
|---|---|---|---|---|
| R1 | low (confirmed) | `core/portfolio/sizing.py:132-134` | A request that is a whole number of shares. An ADD of 144 shares at ₹6,358.80 asks for ₹2,28,916.80 = 36 shares. `36 × 6,358.80` exceeds the budget by float rounding, so the guard buys 35; HEAD bought 36. Over a 200,000-holding grid (`float_guard_exact.py`), HEAD's floor already buys one share short of exact arithmetic in 2.11% of ADDs; SA-050 makes it 2.32%. Never over a cap, the floor or the request. | Accepted as low; follow-up on [SA-049](../stories/SA-049.md), which reuses `size_buy`: compare in paisa, add a test |
| R2 | low (confirmed) | `core/portfolio/pipeline.py:385` | Two exits on one day with the same destination (RT1). The second leg is skipped by the position cap; its SELL's note says why, but no `switch_buy_skipped` alert fires, because `bought` matches any BUY of the symbol. Before SA-050 the second leg bought more, so this case could not arise. KT section 6 and AUTOPILOT_GUIDE section 6 say the alert repeats the reason whenever the buy does not land. | Follow-up on [SA-049](../stories/SA-049.md) (match the BUY to its SELL by `advice_ref`); doc wording at commit (below) |
| R3 | low (docs) | `docs/TEAM_TESTING_GUIDE.md`, case 07-J | The tester opens the weekly review after the run that buys WELCORP's 5 shares. The case expects capital_goods 5.6% and cash 81.0% (the pre-trade shape); after the buy they are 6.9% and 79.7% (RT2), so a correct build would be recorded as a failure. | Wording at commit (below) |
| R4 | low (confirmed; how common is inference) | `core/portfolio/advisor.py:525`, `narrator.py:41` | A portfolio with no cash on record (only the autopilot seed sets cash). Equity is then the holdings alone, so a manual portfolio of five equal stocks gets `POSITION_LARGE` on every holding, with "so the autopilot will not add to it" (RT4); HEAD gave none. Verdicts are unchanged: ADD was blocked the same way before. Production was not read, so how many such portfolios exist is unknown. | Follow-up on [PR-007](../stories/PR-007.md) (the note's wording without cash) |

**Info, no change needed:**

- I1: the SWITCH destination is the top-conviction qualified idea, chosen before the band is
  read. If it is above its band, the next in-band idea is not tried, and the proceeds stay in
  cash for SA-049, as the card says.
- I2: `size_buy` has no guard against a non-finite mark. A NaN would make `min()` keep the
  request. Unreachable today, because closes are `dropna`'d in `_fetch_session_close`.

## Commit-time edits (at the owner's word, with the implementer's list)

The receipt's own list still applies:

- KT: header, the `core/portfolio/sizing.py` link in "Sizing every buy", section 12's SA-050
  row `Done`, then the PDF rebuild and `check_kt_docs`;
- the AUTOPILOT_GUIDE header;
- the guide's three status lines.

Add:

- **R3, guide 07-J's result:** "… The weekly allocation, read after this run, shows banking
  13.4%, the other sector 6.9% (after the 5-share ADD) and cash 79.7%, and flags nothing."
- **R2, KT section 6 ("Execution and persistence") and AUTOPILOT_GUIDE section 6:** after
  "the `switch_buy_skipped` alert repeats that reason", add "(when another switch that day
  bought the same stock, only the SELL's note says why)".
- **Status lines:** "SA-050: accepted 2026-10-18, committed as `<sha>`; production
  verification pending".

## Commands and environment

Windows 11, the repository's `.stockai` venv (Python 3.13), Node with the vendored Playwright
Chromium. Hermetic boundary on (SA-005): no `.env`, no network, no checkout data.

| Command (repository root) | Result |
|---|---|
| `python analysis_data/sa050_review/rev_digest.py` | diff `c4b58a22…`, 118,037 bytes, 24 paths; manifest 25 files, 0 mismatches |
| `python scripts/docs/kt_manifest.py verify docs/planning/PI-2026-09/evidence/SA-050-manifest.json` | 0 mismatches, input `d2c13ba8…` (start and end) |
| `PYTHONPATH="src;." pytest -q -p no:cacheprovider` the story file and the 15 affected files | **180 passed** (172 plus 8 in `test_autopilot_executor_sells.py`) |
| `pytest -q -p no:cacheprovider --rootdir analysis_data/sa050_review -c NUL analysis_data/sa050_review/test_rv_trace.py` | **6 passed** (RT1 ×3, RT2, RT3, RT4) |
| the same with `RV_SWAP=base` (advisor, autopilot, pipeline, weekly from `85e447b`, in memory) | RT1, RT2, RT3 and RT4 **fail** on the old code; the rerun and the silent-alert probe pass on both |
| `python analysis_data/sa050_review/float_guard_freq.py`, `float_guard_exact.py` | R1's rates: 0.21% of ADDs newly one share short; 2.11% at HEAD, 2.32% now |
| `npm run test:frontend` | **35/35** |
| the new browser test with `SA_FRONTEND_ROOT` = the prototypes with HEAD's `weekly-view.jsx` (blob-identical copy in `analysis_data/sa050/fe_base`) | **fails** (no cash row), as the receipt says |
| `python scripts/docs/check_kt_docs.py` | errors `[]`; the PDF (46 pages) embeds source `5912d699…`, the KT's own digest |
| `python scripts/ci/check_broad_except.py` | OK (151 grandfathered) |
| `pytest -q -rfEs -p no:cacheprovider tests` (CI's command) | **5,037 passed, 12 skipped, 1 xfailed (the known PR-003 limit, `test_known_limit_a_one_verb_reversal_is_shown`), 0 failed** in 11 min 51 s |

The six edited existing test files change fixtures only. The single changed assertion is the
renamed settings key in `test_portfolio_settings.py`.

**Not exercised:**

- the implementer's 21 mutants were not re-run: they edit sources and cannot overlap the
  suite. The reviewer's own traces fail on the old modules instead;
- production: not read, and how many portfolios have no cash (R4) is unknown;
- a real Yahoo or NSE price, or a real shelf file.

Raw outputs (ignored): `analysis_data/sa050_review/` (`review.diff`, `full_suite.txt`,
`npm_frontend.txt`, the trace and probe scripts, `conftest.py`).

## Production and follow-up state

- **Code status:** `done` for the reviewed revision. Production verification is `not_started`
  until the owner's commit and push.
- **Rollout (at the owner's word):** commit with the edits above, and push in a job-free
  window, not 08:30–09:20 or 16:25–17:15 IST. No migration and no new production setting.
- **First week after the deploy:**
  - read the transactions' notes and any `switch_buy_skipped` alert;
  - run guide 07-F, 07-I and 07-J;
  - expect FEDERALBNK's advice to carry `POSITION_LARGE`, and a bullish, healthy WELCORP to
    ADD about ₹13,900 at a time.
- **Follow-ups:** R1 and R2 on SA-049's card, R4 on PR-007's card, R3 and R2's wording at
  commit.
- **Next:** SA-051 (ready, no dependencies), in a new conversation.
