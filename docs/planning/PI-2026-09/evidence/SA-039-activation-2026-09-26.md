# SA-039 — Production activation record, 2026-09-26

**Story:** [SA-039](../stories/SA-039.md). Code accepted on 2026-09-25 ([review](SA-039-review.md)).
**What changed in production:** the owner set the Railway variable `RL_LEARNING_MODE=observe`
and redeployed. The variable was set by the owner, not by Claude. `config.yaml` still checks in
`adapt`; the variable overrides it (`cfg`: env > yaml, verified in the review).
**`production_verification`:** `pending_observation`. Activation is verified below. The
behaviour check waits for the next reviews.

## Deploys (read-only `railway deployment list`)

| Deploy | Commit | Created (IST) | Status | What it was |
|---|---|---|---|---|
| `82c945da` | `5a27683` | 06:22:30 | removed after SUCCESS | Docs push. The old container ran the 06:30 watchdog first. |
| `786faf7f` | `5a27683` | 06:38:57 | SUCCESS | Redeploy for the new variable |
| `da9df6cf` | `16e7ea7` | 06:39:49 | SUCCESS at 06:41:24 | Push of the deploy-record commit; carries the variable |

## Live check (read-only GETs on the production RL monitor, about 06:42 IST)

- `/ui/rl/weights/{ticker}` for all **20** managed tickers: `learning_mode: observe` with reason
  `rl.learning_mode=observe`, so the value was recognised, not a fail-closed fallback.
- Decisions now use the default tables, while the stored files still hold the learned values.
  Sampled chart weights:

  | Graph | Stored | Live |
  |---|---:|---:|
  | Renewable (`technical`), 2 tickers | 0.0 | 0.10 |
  | Automobile (`pattern_analysis`), 2 tickers | 0.0 and 0.033 | 0.11 |
  | IT (`pattern_analysis`) | 0.0017 | 0.10 |
  | Banking (`pattern_analysis`) | 0.017 | 0.15 |
- Stored `weight_version` ranges **v15–v85** across 19 tickers. The 20th, a metals ticker, has no
  forecast envelope, so its summary is empty; that gap is known and predates SA-039.
- `latest_observation` is empty for every ticker, as expected: no review has run in `observe` yet.
- The per-ticker version list is kept only in ignored
  `analysis_data/sa039_activation_versions_20260926.json`, which other checkouts will not have.

## P1 — Mon 28 Sep review: PASSED (checked 20:19 IST)

Read-only: `railway logs b3fb00dd -n 5000 --json`, counted from 16:00 IST (nothing printed), and
public GETs on `/ui/rl/tickers`, `/ui/rl/summary/{t}` and `/ui/rl/weights/{t}`. The live deploy is
still `b3fb00dd` (`90353f3`, 27 Sep 16:00 IST), which carries the variable. The ignored scripts are
`analysis_data/sa039/p1_probe.py` and `p1_recorded_at.py`; their output is saved next to them.

- **Logs, 16:30–19:06 IST:** 20 review headers, one per managed ticker, all `learning_mode=observe`,
  with no duplicate. 19 `[WeightAdapter] Proposal (not applied)` lines and 19 "adapter proposal vN
  not applied; stored weights stay vM" lines. 19 `Complete —` lines. **0 `Weights → v` lines.**
- **Versions:** all 19 tickers with weights report the same `weight_version` as the 26 Sep
  baseline (v15–v85), in both `/summary` and the observation's `stored_version`. Each observation
  has `applied: false`, and `would_be_version` is one higher, so the adapter proposed a change and
  it was not written. WELCORP (the 20th) still has no weights or envelope: its review started and
  stopped before the adapter, as it did before SA-039.
- **Observations:** 19 new ones, recorded 28 Sep 16:31–16:54 IST, `mode: observe`.
- **Correction to the pass rule.** The check expected `latest_observation.review_date` 2026-09-28.
  The 16:30 job reviews the **previous trading session** (`trading_days_ago(today, 1)` in
  `_daily_review_job`), so Monday's run grades Friday: every header and observation says
  **2026-09-25**, which is correct. The rule was written with the wrong date; the `recorded_at`
  times prove these observations came from today's run. For P2, expect `review_date` 2026-09-28.

## P2 — Tue 29 Sep review: PASSED (checked 17:01 IST)

Read-only, as for P1: `railway logs f2e23722 -n 5000 --json` counted from 16:00 IST (nothing
printed), and the same public GETs. The live deploy is `f2e23722` (`e3bb6a3`, 29 Sep 15:07 IST),
which carries the variable. Output is saved next to the scripts, in ignored
`analysis_data/sa039/p2_20260929.json` and `p2_recorded_at_20260929.json`.

- **Logs, 16:30–16:56 IST:** 20 review headers, one per managed ticker, all
  `learning_mode=observe`, all naming review date **2026-09-28** (the previous session, as the
  corrected rule expects), with no duplicate. 19 `Proposal (not applied)` lines, 19 "not
  applied; stored weights stay" lines, 19 `Complete —` lines. **0 `Weights → v` lines.**
- **Versions, the card's two-review check:** all 20 tickers report the same `weight_version` as
  the 26 Sep baseline, two reviews later. Every observation's `stored_version` equals it, and
  `would_be_version` is one higher, so the adapter proposed again and nothing was written.
- **Observations:** 19 new ones, `review_date` 2026-09-28, `mode: observe`, `applied: false`,
  recorded 16:31–16:54 IST. WELCORP again has no weights or envelope, as before SA-039.
- **One traceback, handled and unrelated to the learning mode.** At 16:40:57 the automobile
  orchestrator's LLM ticker resolution returned text that was not JSON (`JSONDecodeError` in
  `_resolve_ticker`). That path falls back to the input ticker and the review went on; it
  predates SA-039. It is reached because some managed tickers are not in their sector's
  `TICKERS` list, so they skip the exact-match short cut. Noted for SA-008, which owns
  ticker identity.

## P3 — Thu 1 Oct monthly forecast: PASSED (checked 10:25 IST)

Read-only. `railway logs 14d13162 -n 5000 --json`, filtered to 08:55–12:00 IST, plus the P1
probe's public GETs. The live deploy is `14d13162` (`2c632e2`, 30 Sep 22:26 IST), with no restart
since, so the 09:00 job made the cohort and no self-heal did. The output is in ignored
`analysis_data/sa039/p3_logs_20261001.json` and `p3_api_20261001.json`.

- **Logs, 09:00:07–09:26:00 IST:** 20 `[generate_forecast] learning_mode=observe` lines and 20
  `Saved envelope … 30 day forecasts` lines, one per enabled ticker, with no duplicate and 0
  tracebacks. No TATAMOTORS envelope was made, as expected: it was disabled at 00:30:43.
- **TMPV:** the 09:00 job regenerated TMPV's 00:32 add-route envelope at 09:25:53. The one now
  stored was made in `observe`, so the rollout note's question is answered.
- **The stored field is inferred from code, not read.** `generate_forecast` logs `mode` and
  writes the same variable to `envelope.learning_mode` (`generate_forecast.py`, the
  `learning_mode()` call and the `PredictionEnvelope(...)` constructor). The envelopes on the
  volume were not read.
- **Versions:** 18 tickers equal the 26 Sep baseline, three reviews later, all in `observe`.
  WELCORP and TMPV are at v0 with no baseline entry, as expected: WELCORP never had weights,
  and TMPV is new.
- **Found while checking; not an SA-039 failure.** The IT orchestrator resolved TATAELXSI to
  TATAMOTORS through its LLM ticker resolution. TATAELXSI's October envelope was therefore built
  on another company's analysis. SA-008's identity gate recorded it, in record mode. The fix is
  routed as [FIX-002](../stories/FIX-002.md); see the
  [SA-003 enforce decision](SA-003-enforce-decision-2026-10-01.md).
- **Ignore the `level` field.** The window's log `level` reads `error` on all 753 lines, which
  is Railway's classification of the stream, not the app's level.

## Still to verify (read-only)

1. ~~Mon 28 Sep, after the 16:30 review.~~ Done: P1 above.
2. ~~The same evening.~~ Done: P1 above.
3. ~~Tue 29 Sep, after the review.~~ Done: P2 above.
4. ~~Thu 1 Oct, after the 09:00 monthly forecast.~~ Done: P3 above. SA-039's observation window
   is complete; the SA-003 enforce decision followed (NO-GO).

**Rollback:** delete the Railway variable (or set it to `adapt`) and redeploy. The stored weights
resume unchanged.
