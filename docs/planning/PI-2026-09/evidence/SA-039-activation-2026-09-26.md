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

## Still to verify (read-only)

1. **Mon 28 Sep, after the 16:30 review.** The logs show `learning_mode=observe` on review start
   and `Complete —` lines, and `[WeightAdapter] Proposal (not applied)` instead of `Weights →`.
2. **The same evening.** For every reviewed ticker, `/ui/rl/summary` still shows the version above,
   and `/ui/rl/weights` has a `latest_observation` dated 2026-09-28. No ssh or volume read is needed.
3. **Tue 29 Sep, after the review.** The versions are still unchanged, which is the card's "two
   reviews" check.
4. **Thu 1 Oct, after the 09:00 monthly forecast.** The new envelopes carry `learning_mode: observe`.
   October is the first fully contained cohort.

**Rollback:** delete the Railway variable (or set it to `adapt`) and redeploy. The stored weights
resume unchanged.
