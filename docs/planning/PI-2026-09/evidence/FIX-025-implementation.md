# FIX-025 — implementation receipt

**Story:** [FIX-025](../stories/FIX-025.md): deployment follows the money and the ideas; a top-up
checks NSE's report too (owner decisions D1–D4 of 4 Nov 2026, plus FIX-024's review items L2, T1, T2
and T3).

**Phase:** implementation, 5 Nov 2026, about 14:30–16:20 IST. Session `stockagent-main-77` [636bf2],
a new conversation opened with "continue". Peers `-31` and `-64` were idle. This phase includes a
same-conversation self-review, which is not the fresh review. The owner's answers to its three
questions went in on 6 Nov, about 08:50–10:20 IST, in the same conversation, before any review.

**Baseline:** HEAD `0f0d7f6` (the pushed FIX-023 and FIX-024), with `-31`'s uncommitted deploy record
in STATE and HANDOFF, kept as it was. Nothing is stacked: every changed file below differs from HEAD.

**Status after this phase:** `review_required`. Nothing is committed, pushed, deployed or configured.
No production state was read, no network was used, and no message was sent. No test reaches the
network (`tests/hermetic.py`).

## In one example

₹50 L in a calm market, all cash, 15 ideas at ₹1,000.

- **Before:** each buy asked for a fixed ₹83,333, so buying stopped at 15 holdings with about ₹12.5 L
  (25%) invested, and ₹37 L sat idle.
- **Now:** each buy asks for 80% ÷ 12 of equity, ₹3,33,333, which is 333 shares. Twelve come to
  ₹39.96 L, ₹4,000 short of the ₹40 L target, so a thirteenth opens: ₹43.29 L (86.6%) invested, and
  two ideas wait.

## What changed

- **`core/portfolio/deployment.py`:**
  - `Breadth` loses `min_invested_inr` and gains `shares` (the regime shares, config then override).
    `position_inr(equity)` is the NORMAL share of equity ÷ `target_holdings`.
  - `target()` is the regime's share, within equity less the cash floor. `Target.notes` is gone.
  - `stop_reason()`: closed, no room, the maximum, target reached, the day's limit, else open.
  - `below_aim()` is the soft minimum's sentence; `run_record()` uses it in place of "holdings floor
    unreachable" and "invested floor unreachable".
- **`core/portfolio/autopilot.py`:**
  - The ADD path reads the run's one report after the cooldown and before sizing. A refusal logs,
    goes to `report["top_ups_skipped"]` and buys nothing.
  - `_deploy_idle_cash` fixes `position_inr` from the equity at the start of the step.
  - `_last_sales` and `_deploy_check` use `shelf.sale_day` and `shelf.sold_since_dive`.
- **`core/discovery/shelf.py`:** `sale_day`, `sold_since_dive`, `autopilot_sales`, `no_longer_held`;
  `redive_due(on, sold)` puts a sold stock's idea first.
- **`core/discovery/deep_dive.py`:** a candidate flagged `sold` is dived though its stock is managed.
- **`core/discovery/__init__.py`:** reads the sales (an unread ledger costs only the priority, and is
  in `errors`), flags those candidates, and records `hygiene["redive_sold"]`. A screen candidate the
  autopilot sold and no portfolio holds is flagged too (`hygiene["sold_candidates"]`, D14).
- **`core/portfolio/advisor.py` (L2):** with no entry of its own for the review day, `build_signals`
  asks `label_recorded_for`, and on None sets `regime_unavailable` from `unrecorded_reason`.
- **`core/portfolio/pipeline.py`:** the report is read before the lock when an ADD is on the day's
  advice too; the skips go to the digest.
- **`core/portfolio/digest.py`, `digest_text.py`, `core/delivery/brief.py`:** the row keeps its ADD
  verdict and gains `top_up_skipped`; its text and the brief's "Add more" line say why.
- **`core/portfolio/results.py`:** the scorecard reads "Aimed for: at least 10 holdings." instead of
  "Floor: 10 holdings." The stored key stays `floor`.
- **`config.yaml`, `settings/base.py`:** `portfolio.min_invested_inr` and
  `PORTFOLIO_MIN_INVESTED_INR` are removed.
- **`core/portfolio/sizing.py`:** the docstring only.
- **Docs:** see below.

## The owner's answers (6 Nov)

> "no position is a hard rule, its all about investments turning inti profits"
> "even the 2L"
> "3 - do as per suggested"

1. **A thirteenth position is fine.** D5 stands. The number of positions is not the aim.
2. **No ₹2 L deposit.** SA-049's rollout loses that step (its receipt keeps the original runbook; its
   card carries the note). The deposit action stays. The docs' worked example is now the ₹10 L book:
   66 shares at ₹1,000, ten buys, ₹8.5 L (85%); in RISK_OFF from all cash, eight buys, 52.8%.
3. **A stock sold after its idea left the shelf.** Nothing had been suggested in writing, and I told
   the owner so. D14 below is my pick under the delegation.

**Asked, not assumed:** `portfolio.max_holdings` (15) stays. The owner agreed it on 4 Nov (card D1,
and the acceptance relies on it), and the answer above was to a different question. Pinned as it
stands by `test_max_holdings_still_binds_when_money_arrives_on_a_full_book`.

## Decisions (F25-D1 to D14)

Each is mine under the owner's delegation for optional technical calls, for the fresh review to rule
on.

| # | Decision | Why | Revisit when |
|---|---|---|---|
| D1 | A position in RISK_OFF is the calm size. | The card's recommendation: RISK_OFF only stops sooner. | The scorecard shows otherwise. |
| D2 | `min_invested_inr` is removed, not kept for reporting. | Nothing reads it, and a dead setting invites the floor back. A leftover override is ignored (tested). | Never expected. |
| D3 | Per-portfolio regime shares: `portfolio.overrides.<user>.deploy_target_invested_pct`, merged by regime, case-insensitive. | The acceptance says "the regime shares changed in config, or per portfolio". The position uses that portfolio's NORMAL share. | — |
| D4 | The soft minimum speaks only in calm regimes. Its reason is the first that applies: target reached; enough ideas waiting behind the limit (the stop's words); only N qualifying ideas; no qualifying idea. N counts today's qualifying ideas, not holdings: "4 holdings, below the 10 aimed for: only 3 qualifying ideas". | RISK_OFF's few holdings are by design. | The owner finds the sentence noisy. |
| D5 | The last position stays whole. | The card: "open while invested is below the target", at most one position past it. **Effect:** whole shares usually leave the twelfth just short, so a thirteenth usually opens and invested ends near 86%, not 80%. Not measured on live prices. | Confirmed by the owner, 6 Nov. |
| D6 | A position's size is fixed from the equity at the start of the step, recalculated each day. | One size a run. **Effect with costs:** ₹12 L buys 80 shares at ₹1,000 on day one; on day two equity is lower by about ₹190 of charges, so 79 (tested). | — |
| D7 | A top-up's order: cooldown, then report, then sizing. | A stock inside its cooldown costs no read and no skip row. | — |
| D8 | The skip reaches the log, the digest and the brief, not the advice ledger. | The advice is written before the executor runs. The card asks for the log and the digest; the brief reads the digest, and "Add more" alone would read as if shares were bought. | PR-007's plain reasons. |
| D9 | The report is read before the lock when an ADD is on the advice. | Otherwise the network read would run under the user's lock. | — |
| D10 | D4 counts the autopilot's own exits, across every active portfolio. A hand sale and a TRIM that leaves shares do not count. | The card says "the autopilot sold". A trimmed stock is still held. | — |
| D11 | Sold ideas go ahead of pre-gate ideas too, oldest dive first. | The card: "first". | — |
| D12 | **Beyond the card:** a sale counts from the IST day it was decided (`sale_day`: the later of its date and, for the autopilot's rows, its stamp). | See "Found on the way" 1. It only makes a re-buy wait. An import keeps its own date. | FIX-027 changes which session a run decides. |
| D13 | **Beyond the card:** a candidate flagged `sold` is dived though its stock is managed. | See "Found on the way" 2. Without it D4 does nothing for its own population. | — |
| D14 | A stock the autopilot sold with no idea left takes its rank in the screen like any other stock, once no portfolio holds it. Not a guaranteed re-analysis, and no place in the queue. | `candidates.py` already said that buying a sold stock back needs a new dive, and the managed skip refused that dive for good, however the idea left: rotated, displaced or dropped. A case older than 60 days has no claim on the budget ahead of what the screen ranks, so this adds no analyst call a rank would not make. | The scorecard shows bought-back stocks outperform. |

KT section 1 and guide 07-G's status also take the deploy of 5 Nov now: they were commit-time edits
in HANDOFF, and no reviewed manifest holds those files any more.

## Found on the way

1. **A day-old round trip (changed, D12).** The 16:30 run dates a sale by the session it reviews. A
   sale decided by Monday's run is dated Friday, so a dive dated the Saturday between read as "after
   the sale", and Tuesday's run could buy the stock back at Monday's close, paying costs twice on an
   analysis older than the sale. Code inspection and a test; not measured.
2. **A stock the autopilot bought can never be re-dived (changed, D13).** A buy promotes the stock to
   the managed list and nothing demotes it on an autopilot sale (`demote_symbol` is called only from
   the API's manual deletes). `run_deep_dives` skips a managed symbol even when flagged `redive`. So
   the card's "Today … waits for its routine re-analysis" does not hold for such a stock: its
   re-dive was a silent no-op, and D4 alone would have moved it to the front of the queue and still
   not analysed it. Reproduced before the fix: with SOLD managed and sold, the cycle's `hygiene.redive` named SOLD, `analyst.calls` was `[]`, `redived.refreshed` was `[]` and its dive date did not move. Pinned end to end by `test_d4_end_to_end_bought_sold_and_re_dived_though_still_managed`: the real executor and promotion buy it, the real executor exits it, nothing demotes it, the real ledger reader finds the sale and the real cycle dives it.
3. **Found, not changed:**
   - A routine re-dive of an idea whose stock is managed and still held takes a slot of the week's
     `due[:room]` and makes no call, so with deployment on, up to 15 such ideas could push real
     re-dives back. Code inspection; not measured. It costs no budget, since `run_deep_dives` counts
     only calls.
   - **A sold stock stays managed (routed: [FIX-028](../stories/FIX-028.md)).** It keeps its daily
     review for good, at LLM cost. `held` entries are never evicted, so sold stocks fill the cap of 40;
     at the cap a new buy's promotion returns `cap_full`, the autopilot ignores that, and the holding
     gets no daily review. Code inspection; the production list's size is not measured.
   - A hand sale still blocks a re-buy until the next dive (`_last_sales`), while D4 does not hurry
     that dive, so it waits for the routine one. Deliberate under D10; it only makes a re-buy wait.
   - `breadth()` raises on a malformed override (`int`, now `float` too), and `deployment.active` runs
     outside the step's guard. The same class as before, from a config typo. Not measured.

## The card's hard-review questions

- **Can the soft minimum still force a buy anywhere?** No. `Target.min_holdings` is read only by
  `below_aim`, and `stop_reason` no longer has a holdings-floor branch. Brute-force grid:
  `test_the_soft_minimum_never_changes_whether_a_position_opens` (4,320 cases).
- **With a large deposit, can a position pass the 10% cap or its sector's cap?** No: `size_buy` still
  takes the smallest limit. `test_property_any_amount_of_money_keeps_every_cap` replays each run's
  ledger from ₹50,000 to ₹5 crore. The caps hold on the equity at each buy; a later buy's charges
  then shrink equity by a few rupees, the first thing that test's first version caught.
- **Can D4 churn?** At most one round trip a week per stock, since a re-buy needs a dive after the
  sale and dives come on Saturdays (`test_d4_churn_is_at_most_one_round_trip_a_week`; a manual
  discovery run could add one). **Is each round trip's cost visible in the scorecard? No.** The
  scorecard's figures are before costs. Each trade's charges are on its ledger row and in the
  portfolio page's cost summary. Routed to [PR-013](../stories/PR-013.md) as one added line.
- **Is a refused ADD ever retried past the check?** No. `_execute_buys` is the only top-up path; the
  run marker stops a same-day re-run; the next day's ADD is checked again. A SWITCH into a stock
  already held has its own check, as before.

## Routed items

- **L2:** done, as the card says. A holding with no entries at all is untouched: with no 7-day
  accuracy, an ADD cannot fire. Six older fixtures dated their newest entry the day before the
  review with no regime recorded, the fault's own shape; their newest entry is now the review day's
  (`test_decision_gate_portfolio_sa003.py`, used by `test_identity_chain_sa008.py` too).
- **T1:** `test_run_advisor_with_no_date_defaults_to_today_and_the_same_rule`.
- **T2:** `test_an_established_day_adds_as_before` pins `rec.notes == []`.
- **T3:** `test_a_real_switch_buys_a_morning_analysis_at_that_days_close` and its evening pair (a real
  stop breach, the real `decide`, the real executor).

## Rollout

- **This changes production with the switch off.** Once deployed, a top-up of a stock under a measure
  stops; every top-up stops on a day with no report from the last 7 days; a holding with no review
  entry on a day with no recorded regime adds nothing; a sold stock's idea goes first on Saturday.
  How often NSE's report is missing is not measured beyond FIX-011's checks.
- **No deposit (owner, 6 Nov).** At ₹10 L the target is ₹8 L and a position ₹66,667. SA-049's rollout
  skips its step 2.
- **Before switch-on:** measure the managed list (FIX-028).
- **Small portfolios:** at ₹1 L a position asks for ₹6,667, so a stock above that is "less than one
  share" and not bought. By design of D2; not measured.
- **No benefit is shown here.** These are contracts. Whether deployment beats cash is for the Nifty
  comparison after switch-on.

## Tests and commands

Environment: `.stockai/Scripts/python.exe` (Python 3.13), Windows, from the repository root.

- **Story file** [`tests/unit/test_deployment_follows_money_fix025.py`](../../../../tests/unit/test_deployment_follows_money_fix025.py), 86 tests, each figure worked by hand in its docstring:
  - The card's table: row 1 (₹12 L, 80 shares, ten buys, 82.5%), row 2 (₹50 L, 333 shares, thirteen buys, 86.6%), through the executor and through the real pipeline; row 3 (₹10.2 L at 86%: nothing); row 4 (6 ideas); row 5 under D3; row 6 under D4.
  - The ₹10 L book with no deposit (66 shares, ten buys over five days, 85.0%; RISK_OFF from all cash, eight buys, 52.8%), and `max_holdings` as it stands (₹40 L arriving on 12 holdings stops at 15 holdings, 37.0%, ₹31,51,000 idle).
  - `stop_reason` over a 4,320-case grid against the definition written in the test; the soft minimum's sentences; a 300-seed property test from ₹50,000 to ₹5 crore, replaying each run's ledger at configured costs.
  - Settings: the removed setting, regime shares in config and per portfolio, the shipped values; a position following the day's equity at configured costs (80 shares, then 79).
  - D3: six refusals in either switch position; a cleared stock unchanged; the cooldown first and untouched; a skip starting no cooldown; one read of the report for ADDs and a SWITCH together; through the pipeline, read before the lock, the digest's row and text; the brief (`test_delivery_brief.py`).
  - D4: the order; an undated dive; a sold stock dived though managed, and no other; each flag passing only its own skip; the budget bound; an unread ledger; `autopilot_sales`; `sale_day`; the end-to-end buy, sale and re-dive; bought by the first run that may use the dive; one round trip a week.
  - D14: the real buy, rotation at 63 days, sale, dive as a new idea, candidate list and second buy, end to end; no call while any portfolio holds it; only the autopilot's sale passes, with a hand sale, a trim and a never-sold stock ranked in the same run; the dive memo's one call a month; its screen rank kept, with a sold idea still first; unread holdings keep it out and cost nothing else.
- **Routed:** `test_analysis_time_fix024.py` (L2's three shapes and the own-entry case, T2, T3 in a morning and an evening), `test_portfolio_api.py` (T1).
- **Mutants** (in place, restored by sha256), **all caught, one after a test was strengthened:**
  - 5 Nov (`analysis_data/fix025/mutants.py`; the story file, FIX-024's, the API's and the brief's): 52 distinct. First pass 45/48 (`mutants.txt`): the survivors were real test gaps, one of them my own assertion swallowed by the advisor's `except`. Then 9/9 (`mutants2.txt`), then the 3 L2 mutants 3/3. One of the 52, `sold_alone_passes_managed`, is now the intended code (D14) and is retired.
  - 6 Nov, D14 (`mutants3.py`): 15 new. First pass 14/14 (`mutants3.txt`). After the fix below, `every_candidate_flagged` **survived**: flagging now runs only when a stock was sold, and no test had a sold stock beside a never-sold managed one. The test was strengthened and it is caught. On the final code 8 were re-run, all caught (`mutants4.txt`); the other 7 ran only in the first pass, their code unchanged since.
  - 6 Nov, 6 of the older mutants on the same cycle code re-run, 6/6 (`mutants5.txt`). The rest of the 52 were not re-run: their code did not change.
- **Full suite** (`tests`, hermetic):
  - 5 Nov: first run 8 failed (7 L2 fixture shapes, 1 `WinError 5` rename flake in `test_cli_round_trip`, which passed alone); second run 6,141 passed / 12 skipped / 1 xfailed / 0 failed.
  - 6 Nov, first run: 6,159 passed / 12 skipped / 1 xfailed / **1 failed**, pytest exit code 1 (24m38s; the job's notification said 0, its last command's): `test_scheduler_discovery_job.py::test_run_discovery_cycle_happy_path`. A real fault of mine: the new flagging read every candidate on every cycle, outside any guard. It now runs only when a stock was sold, as the neighbouring `if recent:` block does.
  - 6 Nov, second run, on the final bytes: **6,161 passed / 12 skipped / 1 xfailed / 0 failed**, pytest exit code 0 (18m23s). `git status` identical before and after each run (`analysis_data/fix025/full_suite*.txt`, `status_*`).
- `check_broad_except`: OK (148, unchanged). `check_kt_docs`: errors `[]`. `kt_manifest.py verify`: 0 mismatches.

Hand-derived figures in older stories' tests were re-derived for the new position size (SA-049 39
edits, FIX-023 6, FIX-024 5, PR-002 3). `test_below_the_holdings_floor_a_position_opens_past_the_target`
was rewritten to its opposite, as the owner's decision requires.

## Documentation

- `docs/TECHNICAL_DESIGN.md`: section 1 (production), 6 (advisor precedence, surveillance at buy time,
  Cash deployment, every buy's checks, the re-buy rule), 8 (re-analysis selection, the managed
  exception and the limit it leaves), 12 (FIX-025's row, Open; SA-049's title loses the floor).
- `docs/AUTOPILOT_GUIDE.md`: section 7's steps, the sizing rule, ADD, the worked example, the
  configuration table, the test list.
- `docs/TEAM_TESTING_GUIDE.md`: 07-G gains the money cases and the sold stock, with new figures; 07-O
  gains the top-up cases; new 06-K for the re-analysis and 06-L for a stock sold with no idea left.
- `CODEBASE.md`, `config.yaml`, `deployment.py`'s docstring, `docs/ARCHITECTURE.md` (the deposit).
- Cards: FIX-025 (the owner's answers), SA-049 (the deposit superseded), new FIX-028; the plan's README.
- `docs/planning/PI-2026-09/stories/PR-013.md`: the routed line.
- `docs/StockAgent-Three-Loops.pdf` regenerated: 68 pages, source `c3fc5717…`.

**Commit-time edits still to make:** KT header (Code inspected, edition); section 1 ("the inspected
code adds FIX-025 … not yet deployed"); section 12 FIX-025 Done; guide 06-K, 06-L, 07-G and 07-O status lines;
the PDF.

## Review input

- Manifest: [FIX-025-manifest.json](FIX-025-manifest.json), SHA-256 `33b944df64f80d8aa511a23edc85b4922b45aad8e231b578bbde675f1facf992`, 33 files
  (`scripts/docs/kt_manifest.py verify`).
- Diff against HEAD `0f0d7f6`, the PDF excluded: SHA-256 `dabc7e343de1bdfe4d7bef12aac0a6afbd57fb892b7d2c59adff63e4c0cb7cf7`, 245,518 bytes, 32 paths, via
  `analysis_data/fix025/digest.py` (a temporary index, so the new test file is in the diff and the real
  index is untouched). End tree `4ac1d13195606d91c0f0487385cb56aea039c799`.
- STATE, HANDOFF and this receipt are bookkeeping, outside the manifest.

## What a fresh review should press on

1. D12 and D13 are beyond the card. Are they right, and is anything else reading a sale's date?
2. D14: does a stock returning as a new idea leave anything keyed by the wrong sector, or reach a
   portfolio that should not buy it? Can its flag let in a stock still held?
3. D4's `below_aim` reasons against the card's examples.
4. Whether a re-dive of a managed stock (D13) leaves any store keyed by the wrong sector.
5. T3's and row 2's pipeline fixtures: do they exercise the real paths they claim?

Next: a fresh review in a new conversation (REVIEW.md).
