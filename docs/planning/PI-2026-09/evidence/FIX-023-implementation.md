# FIX-023 — implementation receipt

**Story:** [FIX-023](../stories/FIX-023.md): deployment buys only on a regime read from live inputs,
as of the review session (SA-049 review M1 and L3), and never at a close from before the idea's
latest dive (SA-049 re-review RR-L1, RR-T1).

**Phase:** implementation, 2 Nov 2026, about 16:10–18:05 IST. Session `stockagent-main-79`
[5ee8a5], a new conversation opened with "continue". The 19 peers were idle at the start and
before the bookkeeping (ListAgents). This phase includes a same-conversation self-review, which is
not the fresh review.

**Baseline:** HEAD `c5165a1` (SA-049's docs commit on `f064010`), working tree clean. `origin/main`
is `f47d246`: SA-049's two commits wait for session -15's push waiter (20:10 IST window), which
pushes commits only and is unaffected by this working tree.

**Status after this phase:** `review_required`. Nothing is committed, pushed, deployed or
configured. No production state was read and no message was sent. Network use was one read-only
probe of public Yahoo data from this machine (`analysis_data/fix023/live_probe.py`, ignored). No
test reaches the network (`tests/hermetic.py`).

## In one example

- **Before:** Friday 30 Oct, Yahoo's `^INDIAVIX` answers nothing and the Nifty fell 3.0% in 5
  sessions. The detector read VIX 17.0 (the fallback), so the label was RISK_OFF; the daily review
  recorded it, and deployment bought 2 × 83 shares toward 50% in a market a live VIX of 30 calls
  MACRO_CRISIS. And Monday's 16:30 run, reviewing Friday, read Monday's VIX and Nifty.
- **Now:** the VIX has no value. With the Nifty at −3.0% the label could be anything from NORMAL
  (VIX below 14) to MACRO_CRISIS (above 22), so the review records Friday without a label (the
  sticky state keeps its label and calm streak), and the run says "market regime unavailable for
  2026-10-30: India VIX did not answer; no new positions". Friday's label is read from Friday's
  bars (the overseas inputs from the sessions before Friday).
- **RR-L1:** Tuesday's run reviews Monday, but NEWX has no Monday bar and its close comes from
  Friday, while NEWX was first dived on Saturday. Record mode bought 83 × ₹1,000 dated Monday. Now
  neither mode buys: "close of 2026-10-30 is before the deep dive of 2026-10-31".

## What changed

- **`core/intelligence/regime/detector.py`:**
  - `_closes(ticker, period, last_day)`: Yahoo's daily closes up to `last_day` by each bar's own
    exchange date (the index is tz-aware: Asia/Kolkata, America/New_York, Europe/London); None
    on an error, no dated close, or none in the 7 days up to `last_day`; non-numeric closes
    dropped.
  - `_get_vix`, `_get_fii_proxy`, `_get_sector_rsi` read up to the session; `_get_5d_pct` and
    `_get_last_session_pct` take the session and read up to the day before it. Each returns None
    when it does not answer (VIX_FALLBACK, FII_PROXY_FALLBACK and RSI_FALLBACK are no longer
    returned).
  - `detect`: the label is still classified with the neutral values in place of missing ones
    (the learning loop's label, unchanged); `_label_bounds` classifies each missing input at its
    mildest and its severest; when the two severities differ, `unavailable` = "<names> did not
    answer" and `floor_label` = the mildest. `dark_inputs` lists every missing input. The
    narrative prints "n/a" and "Not answered: …".
- **`src/backend/shared/schemas/feedback.py`:** `RegimeSnapshot.vix_value`, `fii_proxy_5d_pct`,
  `sector_rsi` may be None (defaults unchanged); new `dark_inputs`, `unavailable`, `floor_label`.
- **`core/intelligence/regime/state.py`:** `severity` public (was `_severity`).
  `record_unavailable_day(today, why, floor_label)`: no state or the sticky layer off → None,
  nothing written; the day already established → no-op; else keep the state, entering only a
  severer `floor_label`, and write `_last_update` with `_unavailable`. `update_sticky_regime`
  treats a marked day as not yet updated (the first established detection applies and clears the
  mark). `label_recorded_for` gives None for a marked day; `unrecorded_reason` says why.
  `_read_marker` replaces `_read_last_update`'s body (same silent read; now marked `swallow-ok`).
- **`core/intelligence/rl/workflows/daily_review.py`:** a detector exception sets
  `RegimeSnapshot(vix/fii/rsi None, unavailable="the regime detector failed")`; an unavailable
  snapshot goes to `record_unavailable_day`, else `update_sticky_regime` as before; the sticky
  label is the returned state's (the raw label when None). The RSI amplifier gets the neutral 50
  when the RSI is missing (no amplifier, as before). The summary gains `regime_dark_inputs` and
  `regime_unavailable`.
- **`core/portfolio/deployment.py`:** `regime_gap(on)` (a seam); `target(..., gap=)`: the closed
  reason is "<gap>; no new positions". New outcome `before_dive`.
- **`core/discovery/shelf.py`:** `close_before_dive(bar, idea)`.
- **`core/portfolio/autopilot.py`:** `_deploy_check` returns `before_dive` before SA-003's
  freshness check; a SWITCH leg is skipped with the reason on its SELL; both in either gate mode.
- **`core/portfolio/exit_shadow.py`:** `switch_buy_lands` is False for such a close.
- **`scripts/ci/broad_except_baseline.txt`:** one entry fewer (`_read_last_update`), via
  `check_broad_except.py --update` (148).
- **Tests:** new `tests/unit/test_regime_inputs_fix023.py` (22). Updated: `test_regime.py` (the
  global fetchers' stubs take the session and answer a live 0.0%; the three fallback tests now
  assert no value), `test_global_stress.py` (stub signatures; the all-missing case also asserts
  `unavailable` and the floor), `test_deploy_idle_cash_sa049.py` (the no-regime reason names the
  day; its state file in tmp).

## Decisions (implementer's, recorded for the review)

- **F23-D1, "established" means the severity is fixed.** The sticky layer is severity-based and
  deployment's targets differ by severity, so a day counts when every value the missing inputs
  could take gives the same severity (the classifier is monotone in VIX and the Nifty's fall, and
  escalation in the number of signals). So a missing input that cannot matter does not close the
  day: VIX 30 and Nifty −3% are MACRO_CRISIS whatever Brent did; one missing global signal with
  none firing cannot reach 2. Closing the day on any missing input would also have stopped a live
  crisis being entered.
- **F23-D2, the sector RSI never closes the day.** It only chooses among the calm labels, which
  share one target (80%). Limit in the KT: a different target per calm label would need it. In
  practice a missing RSI means the Nifty is missing too (the RSI falls back to `^NSEI`).
- **F23-D3, a dark day never moves the hysteresis on a guess.** It is not a calm day and does not
  break a calm streak, so a crisis survives any run of dark days (before, three fallback NORMALs
  exited it). It enters only a severer label the live inputs establish (`floor_label`: VIX 30 with
  the Nifty dark is at least RISK_OFF), so a crisis exit that reads the sticky label is not delayed
  by a dark Nifty. The first established detection of the day replaces the mark (the review runs
  per ticker; a transient miss on the first ticker does not lose the day). With no state file, a
  dark day writes nothing.
- **F23-D4, the learning loop.** Its label (the paper lane, the monthly forecast, a review with no
  state) is classified as before, with the neutral values; the main lane's multipliers on a dark
  day come from the kept sticky label instead of a guess; the reported values are None and the
  summary names the missing inputs. Recorded in the KT (section 5) and RL_DESIGN sections 13 and
  27.1.
- **F23-D5, L3: the label's session.** Indian inputs on or before the session; Brent, USD/INR and
  the S&P 500 strictly before it, because their bar for that date closes after India's close
  (S&P 02:30 IST next day; Brent and USD/INR trade on). The monthly forecast (`as_of` today, 09:00
  IST) is unchanged for the Indian inputs; its overseas inputs drop today's partial bar. A review
  of a session more than about 16 sessions back finds the Nifty missing (RL_DESIGN limit).
- **F23-D6, 7 days.** An input whose newest close is more than 7 days before its cut has not
  answered (covers weekends and NSE holiday runs; refuses a ticker Yahoo stopped updating).
- **F23-D7, RR-L1's rule.** In either gate mode, a buy that opens a position (deployment, a SWITCH
  leg, and the shadow's `switch_buy_lands`, which mirrors the executor) refuses a close whose bar
  is before the idea's `last_dived` (a watchlist idea's `dived` is its analysis day). An undated
  bar is refused too: it cannot be shown to be on or after the dive. An idea with no dive date
  passes this check (the band check still applies). ADD does not open a position and is unchanged.

## Live probe (public Yahoo, 2 Nov 16:50 IST, read-only)

`analysis_data/fix023/live_probe.txt`: all six inputs answered for 30 Oct and 2 Nov; the indexes
are tz-aware (`^INDIAVIX`, `^NSEI` Asia/Kolkata; `BZ=F`, `^GSPC` America/New_York; `INR=X`
Europe/London). At 16:50 Monday Yahoo already held Monday's Indian bars: for 30 Oct the VIX bar
read is 30 Oct and the S&P bar 29 Oct; for 2 Nov, 2 Nov and 30 Oct. Labels RISK_ON both days,
nothing missing. How often an input goes dark in production is not measured.

## Tests

Commands from the repository root, Windows, `.stockai` venv (Python 3.13), plain `pytest` with
`tests/hermetic.py` (`-p no:cacheprovider`).

- **Story file** `tests/unit/test_regime_inputs_fix023.py`: **22 passed**. Yahoo is faked by
  ticker and dated bar (a DatetimeIndex, bars after the session included); the daily review's
  step 0 runs for real (no envelope, so it stops after the sticky update); the state file and the
  executor are real.
  - **Acceptance (RV2's shapes):** a live crisis (control) recorded MACRO_CRISIS and nothing
    bought; India VIX dark: no value, NORMAL kept and marked, nothing bought, the reason names the
    VIX; VIX and Nifty dark: the reason names three inputs; a detector exception: "the regime
    detector failed"; a live VIX of exactly 17.0 with the Nifty −3.0% is RISK_OFF and buys 2 × 83
    to 43.8% (hand-worked).
  - **Hysteresis:** a crisis entered on Wednesday survives three dark days with calm streak 0, and
    Tuesday's live NORMAL is calm day 1; a dark day with VIX 30 and the Nifty dark enters RISK_OFF;
    the first established detection of a day replaces the mark once; sticky off or no state writes
    nothing.
  - **Severity:** three cases (MACRO_CRISIS with every global input missing; NORMAL with one
    missing and none firing; S&P firing with Brent missing is unavailable).
  - **L3:** Friday's label reads Friday's VIX 15 and a flat Nifty (NORMAL) while Yahoo holds
    Monday's VIX 30 and Nifty 23,000 (Monday's label: MACRO_CRISIS, −4.1667%); the S&P's Friday
    −3.0% is read by Monday's label, not Friday's; Brent's 5 sessions likewise (+8.75% / +10%);
    the 7-day bound at 8 and 7 days; a NaN close skipped.
  - **RR-L1:** RR3's shape through the real pipeline in record and enforce: nothing bought,
    outcome `before_dive` naming both dates, counted in the reasons; a carried-forward bar on the
    dive's day still buys in record mode with SA-003's note; a SWITCH leg is skipped with the
    reason on the SELL (cash ₹10,00,000) and the shadow agrees; the rule's own cases (watchlist
    "analysis", undated bar, the dive's day, no idea, no dive date).
  - **RR-T1:** a watchlist BUY analysed Saturday is not offered on Friday's review ("−1 days old")
    and is offered on Monday's with its band from the 31 Oct close (₹485–510).
- **Reviewer cases, for reference:** `analysis_data/sa049_review/test_rv_sa049.py -k rv2` — RV2b
  now fails at its defect line (Friday's label is RISK_OFF from Friday's bars, not Monday's
  MACRO_CRISIS); the two RV2 cases fail one line earlier than their defect, because the VIX is now
  None, not 17.0 (their buy shapes are pinned by the story file). `analysis_data/sa049_rereview1/
  test_rr_sa049.py`: RR3 fails at its defect line in both modes (no buy; outcome `before_dive`).
- **Mutants** (`analysis_data/fix023/mutants.py`, each in place, restored and checked by sha256):
  **23 of 23 caught**, re-run on the final bytes (`mutants.txt`): no session cut; overseas read up to the session; never
  unavailable; bounds ignoring missing globals; a VIX midpoint; no age bound; no NaN filter; the
  floor as the neutral label; a dark day counted calm; no floor entry; the mark ignored by
  `label_recorded_for`; the mark never replaced; a dark update overriding an established day; the
  exception path as NORMAL; the review ignoring `unavailable`; the dive rule never, or inclusive;
  an undated bar allowed; no dive check in deployment, the SWITCH leg or the shadow; the gap
  ignored; the watchlist's lower bound removed (RR-T1's survivor, now caught by a tracked case).
- **Neighbours** (`tests/unit/intelligence/`, the SA-049, PR-004, FIX-016 and PR-009 files, the
  story file): **1,567 passed**, 0 failed.
- **Full suite:** first run 6,044 passed / 12 skipped / 1 xfailed / **1 failed**
  (`test_broad_except_guard.py::test_real_tree_matches_its_baseline`: the moved handler, fixed as
  above). Final run, on the final code and test bytes: **6,045 passed / 12 skipped / 1 xfailed / 0 failed** (25m58s, 17:28–17:54 IST; SA-049's 6,023 plus this story's 22). Output: `analysis_data/fix023/full_suite2.txt`. No tracked runtime file
  changed (`git status` before and after).
- **Checks:** `check_broad_except` OK (148 grandfathered, one fewer); `check_kt_docs` errors
  `[]`, header `f064010`, 110 linked sources, none changed since; PDF regenerated, 66 pages.

## Self-review (same conversation; not the fresh review)

- The broad-except ratchet caught the moved silent read (`_read_marker`); marked `swallow-ok` with
  its reason and the baseline shrunk, rather than adding an entry.
- The global fetchers' old test stubs returned None as "neutral"; under this story None is a
  missing input, so the stubs now answer a live 0.0% and the docstring says why.
- Checked every consumer of the snapshot's values for None: the daily review's log line and
  summary, the conviction amplifier (neutral 50), the narrative, the forecast (label only), the
  brief (reads the state file's label only).
- Hard-review routes checked: the detector's exception path (recorded unavailable); the sticky
  layer off (nothing written, so no label: deployment opens nothing, SA-049's RV5); a corrupt
  state file (no label; a dark day writes nothing); `update_sticky_regime`'s own exception
  (nothing written for the day, so no label); a later dark call cannot undo an established day.

## Documentation

- **KT** (`docs/TECHNICAL_DESIGN.md`): section 6 Cash deployment, the regime paragraph rewritten
  as the rule ("A label counts only when live inputs establish it", two limits) and the
  candidates' list gains the close-and-dive rule (the RR-L1 limit sentence removed); section 5
  "What adaptation means here" gains the regime modifier's paragraph. Section 12's FIX-023 row
  stays `Open` until acceptance; section 11's planned rollout line is unchanged. PDF regenerated.
- **RL_DESIGN.md:** section 13 (signals as of the session, missing signals, "established", the
  overseas cut; the old "reads the latest values" limit replaced) and 27.1 (unavailable days).
- **AUTOPILOT_GUIDE.md:** deployment's target and candidates steps, the `before_dive` outcome, the
  story file's row. **CODEBASE.md:** the state, detector, deployment and shelf rows.
- **Testing guide:** case 07-G gains the dark-input case, the before-dive case, a production count
  and the status line "FIX-023: implemented 2026-11-02, review pending; not deployed."

## Review input

- **Manifest:** [FIX-023-manifest.json](FIX-023-manifest.json) `211735f44ef80af3f9404f067cd95714a628274f0c07fc10dee0a6e883b9e099` (19 files),
  `kt_manifest.py verify` 0 mismatches.
- **Diff:** `672f6c606645c6284a9a5828bed8478a5f9877c1981ab0a08031d297824b0867` (115,078 B, 18 paths), from `analysis_data/fix023/digest.py`: every manifest path except the PDF,
  sorted, against the index (= HEAD `c5165a1`, nothing staged); the story file against
  `/dev/null`.

## Commit (after the fresh review accepts it, only at the owner's word)

The manifest's files exactly as reviewed, then a docs commit: the KT header (the new code commit),
section 1's production paragraph as it then stands, section 12 FIX-023 `Done`, guide 07-G's
status, the PDF, with this receipt, the review receipt, STATE and HANDOFF (and any uncommitted
SA-049 deploy record). A push deploys it: in a job-free window. Deployment stays off until the
owner's rollout (SA-049 step 4).

## For the fresh review (the card's hard-review questions)

- **Can a fallback reach the label by another route?** The detector no longer returns a fallback
  value; a missing input's neutral value is used only for the learning loop's label, which is
  trusted as the day's regime only when its severity is established. The exception path records
  the day unavailable. The sticky layer off writes nothing, so `label_recorded_for` is None. A
  corrupt or missing state file gives None, and a dark day writes nothing to it. A later dark
  call cannot override an established day; an established one replaces a dark mark once.
  Pinned by the story file and the mutants above.
- **Does the paper lane, or the learning loop's regime multiplier, change?** The paper lane's
  raw label: unchanged on a dark day (neutral values), but read as of the reviewed session (L3).
  The main lane's multiplier: on a dark day it comes from the kept sticky label (before: the
  sticky label updated with the guess), and severe labels are no longer exited by dark days.
  Intended and recorded (F23-D3, D4; KT section 5, RL_DESIGN 13 and 27.1).

## Production verification (separate, after the deploy)

Guide 07-G's production line: count the review days whose log says "did not answer" and the
digests' `before_dive` outcomes; confirm the state file carries `_unavailable` only on such days.
Read-only, counts and fields only.
