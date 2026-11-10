# FIX-013 review receipt — cheaper current models for the fast and reasoning LLM tiers

## Fresh re-review of rework 1: ACCEPTED (2026-10-23)

**Phase:** fresh-session re-review, a new conversation opened with "continue" (23 Oct, about
11:41–12:05 IST, session `stockagent-main-f8`). FIX-013 was implemented in session
`stockagent-main-62`, reviewed in `stockagent-main-7e`, and reworked in `stockagent-main-48`. This
conversation is none of them. All peer sessions were idle at the start.

**Verdict: ACCEPTED.** The reviewed revision is `560d18f` plus rework 1, which is uncommitted on
`HEAD` `8c5afed`. Every acceptance criterion is met. Production verification is separate and still
pending. The first review's required finding (R-AC6) and its M1, L1, I1 and L2 are all resolved.
Three low findings remain, all in the documentation:

- the human production check misdescribes one log line (RR-L1);
- the check cannot see one silent analyst failure (RR-L2);
- the KT's story table has no FIX-013 row (RR-L3).

They go in as commit-time edits, with the exact text below. The production steps in STATE now
include RR-L2's check.

**Nothing was committed, pushed, deployed or configured.** No production state was read, no LLM or
outside endpoint was called, and no message was sent. The only tracked files this review changed
are STATE, HANDOFF and this receipt.

### In one example (L2, traced end to end)

A weekday at 08:45 IST, after an overnight sell-off: Nikkei −3.1%, Hang Seng −2.8%. The model rates
it severity 0.85, risk-off. MARUTI's forecast for today is UP and TATAMOTORS' is DOWN. The fast
model's 33 real hosts come from the saved public listing. BaseTen is the one host without JSON
mode, and the test makes it serve first. Its reply puts a sentence before the JSON.

- **The reviewed revision `560d18f`:** BaseTen serves the request, so the strict parse fails. The
  morning is recorded as "neutral, no shock", and telemetry records a success. MARUTI's
  contradicted forecast is not redone (RR3).
- **Rework 1:** the request carries `provider.require_parameters`. That leaves 32 of the 33 hosts
  eligible, never BaseTen. The night is rated 0.85 risk-off. MARUTI is re-forecast once, with the
  trigger `preopen_shock`, and TATAMOTORS is left alone. Telemetry records one successful row
  (RR2).
- **Only BaseTen up:** OpenRouter refuses the request. Telemetry records a failure, and the log
  shows "LLM shock rating failed". Nothing is re-forecast (RR4).

### Review input verified

- **Manifest:** [FIX-013-manifest.json](FIX-013-manifest.json), sha256 `d16cfe2c…`, 18 files, 0
  blob mismatches. Checked with `scripts/docs/kt_manifest.py verify` and with this review's own
  `analysis_data/fix013_rereview/rr_digest.py`. `HEAD` `8c5afed` changes none of the 18 paths
  since `560d18f`. Exactly the 8 rework paths differ from `560d18f`.
- **Rework diff:** 25,079 bytes, sha256 `3d6d3a005e7377584e462023113fc5d622705f4b67fa81c4300cd6892a45293f`.
- **Cumulative diff** (baseline `0a798e1`; the card against `/dev/null`): 47,653 bytes, sha256
  `4645aa6e3fe17d3c8239ff2e00fdbf0fa74fd02c668b010ab850d8e15078f5cd`.
- **How:** both diffs were recomputed independently, at the start and at the end. The script
  writes its own `rr_*.diff` files and leaves the implementer's files alone. Both digests match
  the implementation receipt.

### Contract checked

| First-review finding | What is now true | How it was checked |
|---|---|---|
| **R-AC6** (required) | `CODEBASE.md:368`: chat runs on the fast tier with reasoning off. After two tries that hit a rate limit or a 5xx, it escalates to the reasoning tier, a different vendor. The LLM intro carries no bench dates. | Matches `ui_data.py:3247-3300`: `_CHAT_RETRIES_PER_MODEL = 2`, `_is_transient_llm_error`, and a non-transient error raises at once. The intro says every call site disables reasoning. All 24 `chat.completions.create` sites pass `JSON_MODE_EXTRA_BODY`; chat does so by `setdefault`, and no chat call site overrides it. The 7 living docs and the KT name neither `glm-5` nor `qwen3.6`, and their tier tables agree. **AC6 is met.** |
| **M1** | Guide 11-L and the receipt's step 2 name the three analyst failure lines. | The strings are exactly what the code logs: `base_orchestrator.py:740` and `unified_analyst.py:382`, `:394`. The wording is refined by RR-L1 and RR-L2. |
| **L1** | glm-5.2 keeps its 17 Jul rate, described as its last measured one. | From the saved listing: the first-party host charges $1.40/$4.40, and its 35 hosts range from $0.03 to $2.31 per M in. qwen3.6-flash's 0.1875/1.125 equals the 22 Oct catalogue. |
| **I1** | The price windows, restraint 3/3, and the bench repriced at the base rate. | The listing's `overrides`: DeepSeek doubles on weekdays 01:00–04:00 and 06:00–10:00 UTC (IST 06:30–09:30 and 11:30–15:30). Alibaba charges double its night rate 00:00–14:00 UTC every day (IST 05:30–19:30). The bench file records 3 × $0.0002802 + 3 × $0.0001683 = $0.0013455 at the peak rate, so the base rate is exactly half: $0.00067. |
| **L2** | `preopen_check.py:75-78` adds the pin. | RW-D1 says this is the only fast-tier call that asks for JSON. That holds: every other JSON caller names the bulk or reasoning tier (RR6). `JSON_MODE_EXTRA_BODY` is unchanged (RR5). For the parameters actually sent (temperature, max_tokens, response_format, reasoning), 32 of 33 hosts are eligible; only BaseTen drops out. All 33 support tools, so chat is unaffected, and all 5 of mimo's hosts support JSON mode. |

### Independent adversarial examples

The cases are in `analysis_data/fix013_rereview/test_rr_fix013.py`, run behind the hermetic
boundary. The fake OpenRouter here does not use the implementer's two-host list. It takes its hosts
and their supported parameters from the saved real listing, and it applies OpenRouter's documented
rule. The real OpenAI SDK sends each request over `httpx.MockTransport`. The expected values were
worked out by hand: 0.85 is at least the 0.7 threshold; UP contradicts risk-off; DOWN does not.

| Case | What it does | Result |
|---|---|---|
| RR1 | Checks the request body the code really sends against the 33 real hosts | Sends exactly temperature, max_tokens, response_format, reasoning and the pin. 32 hosts are eligible; only BaseTen is excluded. |
| RR2 | Runs the morning above end to end, on rework 1 | Rated 0.85 risk-off; only MARUTI is flagged and re-forecast (`preopen_shock`); one successful row |
| RR3 | Runs the same morning on `560d18f`'s file, executed from git | BaseTen serves the request. Rated 0.0 neutral, nothing flagged, no re-forecast, and a **successful** row. This is the original defect. |
| RR4 | Only BaseTen is up | OpenRouter answers 404. A failure row and the warning line are recorded, and nothing is re-forecast. |
| RR5 | Two pre-open runs | `JSON_MODE_EXTRA_BODY` stays `{"reasoning": {"enabled": false}}`, so no other caller gains a `provider` key |
| RR6 | Scans the code for fast-tier JSON calls | Only `preopen_check.py` both names `LLM_MODEL_FAST` and asks for `response_format` |
| RR7 | Gives the analyst's real `_call_llm` and parser a reply that reads as JSON but has no dimension keys, and an empty reply | All 9 dimensions come back neutral with the error `missing_in_unified_response`. The result is not empty, so there is no fallback, and **none of 11-L's three lines is logged** (RR-L2). |

**Result: 8 passed.** I also ran these cases against the implementer's in-memory variants
(`analysis_data/fix013/rework1/rw_swap_plugin.py`, `RW_SWAP`):

| Variant | Cases failing |
|---|---|
| HEAD's file (before the pin) | 4 |
| M1: the pin set to false | 4 |
| M2: reasoning-off dropped | 1 (RR1) |
| M3: `allow_fallbacks` instead of the pin | 4 |
| M4: `response_format` dropped | 3 |

Every variant is caught by fixtures independent of the implementer's.

The implementer's two new tests use the same real-SDK-over-mock-transport boundary.
`record_llm_call`, Serper and the client factory are patched, so no real transport is reachable.
Their expected 0.8 comes from the fixture, not from the code.

### Findings

| ID | Severity | Location | Evidence | Disposition |
|---|---|---|---|---|
| RR-L1 | Low (wording) | `docs/TEAM_TESTING_GUIDE.md:302` (11-L) | The row says any of the three lines "means that stock was scored again by the older bulk-tier agents". That is true for the first two. But `response truncated` is logged when a cut-off reply is salvaged (`unified_analyst.py:374-387`): the dimensions present are kept, and the missing ones are scored neutral (`_parse_all`, `:495-510`). The result is not empty, so nothing falls back. The case still fails on any of the three lines; only the explanation would mislead a tester. | **Commit-time edit** (exact text below). |
| RR-L2 | Low (production-check gap; pre-existing path; frequency unknown) | Same row; the implementation receipt's step 2 | Two kinds of reply slip past the check (RR7). One reads as JSON but holds no dimension, e.g. `{"analysis": {…}}`. The other is empty content, which is read as `"{}"` (`unified_analyst.py:454`). Either way, all 9 dimensions are scored neutral, and none of the three lines is logged. Only the run's `data_health` row in `telemetry.db` shows it: `dimensions_scored` 0 of 9, and the decision gate records an abstention. That row is written before any fallback (`base_orchestrator.py:606`, `:625-675`), so checking it also catches the three logged cases. glm-5.2 had the same path. The analyst's own prompt was never benched on mimo, so how often this happens is unknown (inference). | **STATE's production steps updated by this review.** Guide 11-L and the receipt's step 2 get the same check at commit (exact text below). |
| RR-L3 | Low (documentation process) | `docs/TECHNICAL_DESIGN.md` section 12, `:2380-2403` | Every PI story has a row in the KT's story table, including the user-requested FIX-010 and FIX-012. FIX-013 has none. The KT's own rule (the next subsection) says each implementation "sets the story's status in the table above". `check_kt_docs` does not enforce this. | **Commit-time edit:** add the row as Done (exact text below), bump the KT header, rebuild the PDF and run `check_kt_docs`. |
| RR-I1 | Info | `config.yaml:66-67`; the implementation receipt's D2 | The comment speaks of the "35 hosts' 2026-10-22 prices". The per-host listing was actually read on 23 Oct, about 09:40 IST; the 22 Oct catalogue has only top-level prices. | No action. |
| RR-I2 | Info | `analysis_data/fix013_review/test_rv_fix013.py:237-238` | The first review's R5 request assertion now fails by design: it pinned the absence of `provider`. Its four parse cases still pass, because the parser is unchanged. | No action (ignored reviewer tooling). |
| RR-I3 | Info | `preopen_check.py:75-78` | L2's trade-off: when none of the 32 eligible hosts is up, the morning's rating fails visibly instead of being served without JSON mode. The outcome is the same as any failure before it: neutral, no re-forecast. | Accepted (RW-D1). |

Still open from the first review:
- **I2**, a watch item: mimo has 5 hosts.
- **I5**, known and unrouted: `test_orchestrator_instantiates_openai` fails when its file runs
  alone.

No critical, high or medium finding.

### Commit-time edits (exact)

1. **`docs/TEAM_TESTING_GUIDE.md`, case 11-L.**
   - **Engineering clause.** Replace "the 16:30 review's unified-analyst calls, and the log lines
     of the pre-open check and of that 16:30 run." with "the 16:30 review's unified-analyst
     calls, the log lines of the pre-open check and of that 16:30 run, and that run's
     `data_health` rows."
   - **Expected result.** Replace "Any of them means that stock was scored again by the older
     bulk-tier agents." with "The first two mean that stock was scored again by the older
     bulk-tier agents; the third means the reply was cut off and its missing dimensions were
     scored neutral. Every `data_health` row from that run also shows `dimensions_scored` equal
     to `dimensions_expected`: a reply that reads as JSON but holds no dimension writes none of
     those lines, and all its dimensions are scored neutral."
   - **Status line.** "**FIX-013: accepted 2026-10-23 (rework 1); committed as `<sha>`;
     production verification pending.**"
2. **`evidence/FIX-013-implementation.md`, "Production verification", step 2's third bullet.**
   Append: "Every `data_health` row from that run also shows `dimensions_scored` equal to
   `dimensions_expected`. A JSON reply without the dimensions logs none of those lines (re-review
   RR-L2)."
3. **`docs/TECHNICAL_DESIGN.md`, section 12.** Add after the FIX-012 row:
   `| [FIX-013](planning/PI-2026-09/stories/FIX-013.md) | Move the fast and reasoning LLM tiers to cheaper current models | Done | 3 Configuration | None |`.
   Then bump the KT edition and "Code inspected", rebuild `docs/StockAgent-Three-Loops.pdf`, and
   confirm that `check_kt_docs` reports errors `[]`.

### Commands and results

Environment: Windows 11, `.stockai` venv (Python 3.13), repository root, `HEAD` `8c5afed` plus the
uncommitted rework.

- **Review input:** `.stockai/Scripts/python.exe analysis_data/fix013_rereview/rr_digest.py` and
  `scripts/docs/kt_manifest.py verify docs/planning/PI-2026-09/evidence/FIX-013-manifest.json`,
  at the start and at the end. Both matched (above).
- **Saved-data checks** (no network): `analysis_data/fix013_rereview/rr_hosts.py` (host
  eligibility) and `rr_prices.py` (prices and bench re-pricing). Both use `-I`.
- **The reviewer's cases:** `.stockai/Scripts/python.exe -m pytest -q -p tests.hermetic -p
  no:cacheprovider analysis_data/fix013_rereview/test_rr_fix013.py`. Result: **8 passed**. The
  variant runs add `-p rw_swap_plugin`, with `RW_SWAP` set and `PYTHONPATH` pointing at the
  implementer's folder (table above).
- **The receipt's six targeted files:** **77 passed, 1 failed** (the known I5), the same as the
  receipt.
- **The first review's cases:** 17 passed, 1 failed. The failure is R5's request assertion
  (RR-I2), as the implementation receipt predicted.
- **Guards:** `scripts/ci/check_broad_except.py` OK (151 grandfathered); `scripts/docs/check_kt_docs.py`
  errors `[]`.
- **Full suite:** `.stockai/Scripts/python.exe -m pytest -q -p no:cacheprovider`, run 11:51–12:01
  IST on the review input. Result: **5,564 passed, 12 skipped, 1 xfailed, 0 failed** (618.9 s).
  The suite changed nothing under `data/`.

**Not exercised:**
- no live call, so neither the pin through OpenRouter nor the analyst prompt on mimo was tried;
- no production log, telemetry or Railway variable was read;
- no browser.

### Acceptance

| Criterion | Result |
|---|---|
| `config.yaml` names the new fast and reasoning models and leaves bulk unchanged; the `base.py` and `ui_data.py` fallbacks name the same models | **Met.** Unchanged since the first review; R1 of its cases passes on the rework. |
| Each new model has optional reasoning, parses `json_object` 6 of 6 with reasoning off, and holds restraint | **Met** (first review). Restraint is now stated as 3/3. |
| The fast model has no fabricated source, skipped tool or broken answer, is faster, and serves the pre-open JSON check | **Met.** The pre-open call can no longer be served by the host without JSON mode (RR1–RR4). |
| The reasoning model comes from a different vendor than the fast model | **Met** (first review, R2 and R4) |
| Every tier model has a cost rate; reasoning is priced at its own rate, checked by hand-worked values; previous tiers keep their rates | **Met.** glm-5.2's kept rate is now described truthfully. |
| The living docs that name the tiers describe the current models | **Met.** R-AC6 is resolved; the sweep found no stale name. |
| Production verification is separate | **Pending.** `560d18f` has been live since 23 Oct 00:10 IST, and rework 1 is not deployed. The steps are below. |

### Verdict and follow-up state

**ACCEPTED** for `560d18f` plus rework 1: input `d16cfe2c…`, rework diff `3d6d3a00…`, cumulative
`4645aa6e…`.

**STATE:**
- FIX-013 is `done` and `active_task` is null.
- **`next_task` is PR-011.** It is ready, since PR-006 is done, and it was not started in this
  conversation.
- Production verification stays `pending_observation`.

**Commit and push** only at the owner's word, in a job-free window, together with the three
commit-time edits. The push deploys L2's pin.

**Owner checks:**
1. Already done: no Railway `LLM_MODEL_*` variable.
2. After today's 16:30 run:
   - the analyst and aggregator rows show `xiaomi/mimo-v2.6-pro`;
   - none of the three analyst lines appears;
   - every `data_health` row from that run has `dimensions_scored` equal to `dimensions_expected`
     (RR-L2);
   - no degraded FeedbackAgent line.
3. Guide 11-L's chat questions.
4. After the push, the first 08:45 run: `preopen_check` shows `success` 1, and there is no "LLM
   shock rating failed" line.

## Fresh-session review: CHANGES REQUESTED (2026-10-23)

**Phase:** fresh-session review, a new conversation opened with "continue" (23 Oct, about
09:18–09:55 IST, session `stockagent-main-7e`). FIX-013 was researched, implemented, committed and
pushed in session `stockagent-main-62`. That session was busy during this review, but it only
touched its own ignored `analysis_data/fix013/` folder. This review is neither the implementing
conversation nor its self-review.

**Verdict: CHANGES REQUESTED.** The model switch itself holds up. The new ids are consistent
everywhere, both models pass the stated gates, the costs are right, and the chat fallback is a
different vendor. But one acceptance criterion is unmet: CODEBASE still names `glm-5.2` as the
chat's escalation model. And the production check, as written, cannot see the one failure that
matters most for the analyst. Both fixes are documentation. A small hardening of the pre-open call
is recommended alongside them.

**Nothing was changed in the reviewed files.** Nothing was committed, pushed, deployed or
configured, and no production state was read. Two public, unauthenticated OpenRouter catalogue
reads were made (below). No LLM was called.

### In one example

A Friday, 16:30 IST. The daily review runs the unified analyst on MARUTI with the new reasoning
model, `xiaomi/mimo-v2.6-pro`.

- **When the reply is JSON** (6 of 6 in the bench, on two other prompt shapes), the analyst scores
  all nine dimensions. Telemetry records one reasoning call, about $0.0058 for 7,440 tokens in and
  2,957 out, against about $0.0204 on glm-5.2.
- **When the reply does not parse**, the analyst returns nothing. The orchestrator logs
  `unified analyst failed -> legacy fallback` and reruns the stock on the nine bulk-tier legacy
  agents. Telemetry still shows one successful-looking `xiaomi/mimo-v2.6-pro` row at $0.0058.
  Guide case 11-L checks "`llm.model_reasoning` for the analyst, with successful calls", so it
  would pass, and FIX-013 could be marked verified while every analysis ran the old path (M1).
  The analyst's own prompt was never benched on the new model, so this is the one consumer with no
  pre-deploy evidence.

### Review input verified

- **Revision:** `560d18f` (FIX-013's commit, pushed 23 Oct 00:10 IST), on `HEAD` `8c5afed`. The
  two later commits (FIX-012's) touch none of FIX-013's 16 paths.
- **Diff:** 34,810 bytes, sha256
  `156a0b84107bd7a55cc13cc3c1b15c12fb6a9632f3e58943a70c8240abc6b78e`. The same as the
  implementation receipt, recomputed at the start and at the end with the implementer's recipe.
  The reviewer's copy is `analysis_data/fix013_review/rv_digest.py`, which writes its own output
  and leaves the implementer's `fix013.diff` alone.
- **Commit contents:** `0a798e1..560d18f` changes exactly the 16 manifest paths plus the three
  bookkeeping files (receipt, STATE, HANDOFF).
- **Working tree:** every path's bytes equal its blob at `560d18f` and at `HEAD`, except that the
  working copy of `base.py` has CRLF line endings. The blob is LF (`eol=lf`), git reports the
  file clean, and the content is identical after normalisation (I4).

### Contract checked

1. **One set of tier ids:**
   - `config.yaml` names fast `deepseek/deepseek-v4.1-flash-1017`, reasoning
     `xiaomi/mimo-v2.6-pro` and bulk `deepseek/deepseek-v4-flash`;
   - `settings` loads the same values under the hermetic boundary (no `.env`, no environment);
   - `base.py`'s fallbacks and `ui_data.py`'s import-failure chat fallbacks name the same ids;
   - `_DEFAULT_COST_RATES` equals `llm.cost_rates`.
2. **Gates from the card, re-read from the saved data:**
   - the saved catalogue (`openrouter_models_2026-10-22.json`, sha256 `5eb4a7f7…`, matching the
     receipt) and today's public endpoints listing both report `reasoning.mandatory: false` for
     both models;
   - both support `tools`, `tool_choice`, `response_format` and `reasoning`;
   - mimo's output limit is 131,072 tokens, far above the analyst's 6,000-token cap.
3. **Bench figures, recounted from the raw files** (`094ff96c…`, `214d8558…`, `50e72143…`):
   - JSON: 6/6 for both. All 12 replies parse with plain `json.loads`, the strictest parser in
     production (the pre-open check's), with no fence and no `<think>`.
   - Verdict and drivers: mimo 3/3 and 3/3; DeepSeek 3/3 and 2/3.
   - The chat bench: 0 fabricated sources, 0 skipped tools and 0 broken answers for both. DeepSeek
     averaged 14.0 s a turn, against 20.6 s for qwen3.6-flash, at $0.00586 against $0.01179.
   - Two of the four chat questions are pre-routed, so only two exercise tool calling.
   - mimo writes fewer tokens than glm-5.2 on both tasks (81 against 93, and 53 against 62), so the
     analyst's 6,000-token cap is not at more risk.
   - Restraint is checked only on the FeedbackAgent task: it is 3/3 per model, not 6/6 (I1).
4. **Prices:** today's top-level list prices are $0.15/$0.60 (DeepSeek V4.1 Flash 1017) and
   $0.435/$0.87 (MiMo-V2.6-Pro), the same as `cost_rates`. DeepSeek's own host doubles its price on
   weekdays 06:30–09:30 and 11:30–15:30 IST, as the receipt says. Alibaba's doubles every day
   05:30–19:30 IST, not in those windows (I1).
5. **Who uses a cost rate:** only pipeline runs (the analyst, the aggregator and the bulk agents)
   store a cost, computed at call time. Chat and pre-open telemetry rows store tokens, not cost. So
   the fast tier's rate, and D3's choice of the base rather than the peak price, change no
   production figure (I3).
6. **The fallback chain:** chat retries the fast tier twice on a 429 or 5xx, then the reasoning tier.
   Reasoning is off on every attempt, and every attempt is recorded under its own model id. A 401
   (the 22 Oct key fault) raises at once and spends no fallback call.
7. **The KT** (`TECHNICAL_DESIGN.md`) names no model, so the PDF correctly stays unchanged.

### Independent adversarial examples

The reviewer's cases are in `analysis_data/fix013_review/test_rv_fix013.py`, run behind the suite's
hermetic boundary (`-p tests.hermetic`). Expected values were worked out by hand from list prices,
not read back from the code.

| Case | What it does | Result |
|---|---|---|
| R1 | Tier ids agree across `config.yaml`, `settings`, `base.py` fallbacks and `ui_data.py` fallbacks; shipped default rates equal config's | pass |
| R2 | AC4's invariant: the fast and reasoning vendors differ (`deepseek` against `xiaomi`) | pass (no tracked test asserts it) |
| R3 | 7,440 in / 2,957 out: mimo $0.00580899, DeepSeek V4.1 $0.0028902, bulk $0.001215214, glm-5.2 rollback $0.020381316; saving against glm-5.2's kept rate 71.5% | pass |
| R4 | A chat call where the fast tier answers 429 twice: calls go fast, fast, reasoning, each with reasoning off; telemetry rows fast ✗, fast ✗, reasoning ✓ with its tokens. A 401 makes one call and raises | pass |
| R5 | Pre-open parse: plain JSON → severity 0.7; `<think>` + JSON → 0.7; **fenced JSON → 0.0 (neutral)**; **prose first → 0.0**. The request sends `json_object` and reasoning off, and pins no provider | pass, which shows L2's consequence |
| R6 | The analyst given a non-JSON reply: returns `{}`, and still logs one `xiaomi/mimo-v2.6-pro` row at $0.00580899. The orchestrator's `legacy fallback` warning exists | pass, which shows M1 |

**Mutants of the cost table** (`analysis_data/fix013_review/rv_mut.py`, in memory only), run against
the tracked `tests/unit/test_llm_cost.py`:

| Mutant | Tracked tests failing |
|---|---|
| M1: drop mimo's rate (AUD-105's defect: priced at the bulk flat rate) | 4 |
| M2: mimo input rate typo, 0.435 → 0.345 | 1 (the hand-worked case) |
| M3: drop DeepSeek V4.1's rate | 2 |
| M4: mimo priced at exactly the bulk flat rate | 2 |
| M5: DeepSeek V4.1 output at the peak price, 1.20 | 1 |

Every mutant is caught. The new AUD-105 test would fail for the original defect (M1, M4), and its
expected values were worked by hand.

### Findings

| ID | Severity | Location | Evidence | Disposition |
|---|---|---|---|---|
| R-AC6 | Low impact; **unmet acceptance criterion** | `CODEBASE.md:368`; `CODEBASE.md:573-574` | The card requires CODEBASE to "describe the current models". The `/ui/chat/stream` row says "BULK-tier default with reasoning disabled, glm-5.2 escalation on failure". Chat runs on the fast tier and escalates to the reasoning tier, now `xiaomi/mimo-v2.6-pro`. The "BULK-tier default" was already wrong at the baseline. README's equivalent claim was fixed, but this one was missed. The section intro, "Models are tiered (2026-06-03 benchmark …; bulk re-benchmarked 2026-07-02)", is out-of-date history in a current-design section. | **Required** in rework 1. Describe the row as current design: the fast tier with reasoning off, the reasoning tier as escalation. Rewrite the intro without bench dates. |
| M1 | Medium | `docs/TEAM_TESTING_GUIDE.md:302` (11-L); `evidence/FIX-013-implementation.md`, "Production verification" step 2; STATE `production_verification.steps` | The analyst's telemetry row is written before its reply is parsed (`unified_analyst.py:356-366`, then `:368-396`). An unparseable reply returns `{}`, and `base_orchestrator.py:735-740` reruns the stock on the bulk-tier legacy pool with a warning. 11-L's "`llm.model_reasoning` for the analyst, with successful calls" therefore passes either way (R6). `scripts/reasoning_bench.py` covers only the FeedbackAgent and aggregator shapes, so the analyst's prompt has no evidence on mimo. | **To fix in rework 1** (docs). 11-L and the receipt's step 2 should also require that the first 16:30 run after the change logs no `unified analyst failed -> legacy fallback`, `[UnifiedAnalyst] run() failed` or `response truncated` line. **This review has already updated** STATE's `production_verification.steps`. |
| L2 | Low (new exposure; frequency inferred) | `core/intelligence/rl/workflows/preopen_check.py:69-74`, `:124` | One of the new fast model's 33 OpenRouter hosts (BaseTen) does not support `response_format`. The old fast tier had one host, and the bulk tier has 15; all of them support it. OpenRouter's documented default (`provider.require_parameters` false) lets such a host serve the request and drop the parameter. The pre-open check parses with plain `json.loads` after a `<think>` strip, so a fenced or prose-first reply silently becomes "neutral, no shock" (R5), seen only as a warning line. Chat sends no `response_format`. All five of mimo's hosts support it. | **Recommended in rework 1:** add `"provider": {"require_parameters": True}` to the pre-open call's `extra_body` (or strip a fence before parsing), with a test. If rework 1 leaves it, route it to [PR-012](../stories/PR-012.md) with the fixture R5. |
| L1 | Low | `config.yaml:63`; implementation receipt D2 (`:180`); `stories/PR-012.md:25` | All three say the retired tiers are "still priced", priced "correctly", or "refreshed to 22 Oct list prices". `z-ai/glm-5.2` keeps its 17 Jul rate, $1.218/$3.828. Its 22 Oct hosts range from $0.45/$1.44 to $2.31/$7.26, with the first party at $1.40/$4.40. The catalogue's top-level $0.0341/$7.00 is just the host with the cheapest input. PR-012's earlier line, that glm cost telemetry is likely overstated, was removed. The rate matters only after a rollback, when run costs could be off by tens of percent. | **To fix in rework 1** (wording): say the rate is glm-5.2's last measured one (17 Jul), or update it to the first-party $1.40/$4.40 in both `config.yaml` and `base.py`. Implementer's choice. |
| I1 | Info | implementation receipt `:79` table, `:122`; `config.yaml:18-19` | Restraint is 3/3 per model (FeedbackAgent task only; Haiku 1/1), not 6/6. Alibaba's host doubles every day 05:30–19:30 IST, not in DeepSeek's weekday windows. `reasoning_bench.py` prices DeepSeek V4.1 at the peak rate, while `model_bench.py` uses the base rate, so the reasoning-bench cost of $0.00135 is the peak price for a run made off-peak. | Correct in rework 1, together with L1. |
| I2 | Info (watch) | the reasoning tier | mimo-v2.6-pro has 5 OpenRouter hosts, and 2 showed a degraded status at about 09:40 IST today. glm-5.2 had 35. The reasoning tier carries the 16:30 review (FeedbackAgent, ThesisReviewer), the analyst, the aggregator and the chat fallback. | No action. Note it for the production watch: any degraded FeedbackAgent lines at 16:30. |
| I3 | Info | `services/clients/llm_client.py:115-152`; `log_store.py:305-336` | Chat and pre-open telemetry store tokens, not cost. The fast rate prices no production figure today. | No action. |
| I4 | Info | `src/backend/shared/config/settings/base.py` working copy | The working copy has CRLF line endings and the blob is LF. Git reports it clean; the committed and deployed bytes are LF. | No action. |
| I5 | Info (known, pre-existing) | `tests/contract/test_phase0_llm_migration.py::TestOrchestratorUsesOpenAI::test_orchestrator_instantiates_openai` | Fails when its file runs alone: 1 failed, 19 passed at `HEAD`, and identically at `0a798e1` in a throwaway worktree. It passes inside the full suite (CI's Linux job on `8c5afed` was green). Not caused by FIX-013. | Unrouted, as the implementation receipt left it. |

No critical or high finding.

### Commands and results

Environment: Windows 11, `.stockai` venv (Python 3.13), repository root, `HEAD` `8c5afed`.

- Review input: `.stockai/Scripts/python.exe analysis_data/fix013_review/rv_digest.py`, at the start
  and at the end. The output matched both times (above).
- Catalogue and endpoints: `analysis_data/fix013_review/rv_catalogue.py` (the saved file);
  `analysis_data/fix013_review/rv_endpoints.py` (public `GET /api/v1/models/{id}/endpoints` and
  `/api/v1/models`, no key, about 09:40 IST; raw JSON saved beside the script). Two more endpoint
  reads, for `deepseek/deepseek-v4-flash` and `qwen/qwen3.6-flash`, gave the L2 comparison.
- The reviewer's cases: `.stockai/Scripts/python.exe -m pytest -q -p tests.hermetic -p
  no:cacheprovider analysis_data/fix013_review/test_rv_fix013.py`. Result: **18 passed**.
- Mutants: `… -p tests.hermetic -p analysis_data.fix013_review.rv_mut --rv-mut=M1..M5
  tests/unit/test_llm_cost.py`. Each one was caught (table above). Control: 8 passed, with the
  hermetic header showing ".env disabled … outbound network blocked".
- The receipt's targeted run: `.stockai/Scripts/python.exe -m pytest -q -rfEs -p no:cacheprovider
  tests/unit/test_llm_cost.py tests/unit/shared/test_config.py
  tests/unit/shared/test_config_loader.py tests/contract/test_phase0_llm_migration.py
  tests/unit/test_chat_llm_hardening.py tests/unit/intelligence/rl/test_preopen_check.py`.
  Result: **75 passed, 1 failed** (I5, the same as the receipt).
- `python scripts/ci/check_broad_except.py`: OK (151 grandfathered). `python
  scripts/docs/check_kt_docs.py`: errors `[]`.
- **Full suite:** not rerun. CI's "Python tests (Linux, 3.11)" passed on `8c5afed`, which contains
  `560d18f`, and the implementer's local full run was 5,561 passed with one known flake. Nothing in
  this review called for broadening.

**Not exercised:**
- No live LLM call: the analyst prompt on mimo, and the pre-open call through BaseTen, are untested;
- no production log, telemetry or Railway variable read;
- no browser.

### Documentation

The seven living docs and the PR-012 card name the new tiers, apart from `CODEBASE.md:368` and
`:573-574` (R-AC6). Guide case 11-L exists, but it needs M1's analyst check. The KT names no model,
so there is no PDF impact. The README now matches the code: bulk does ticker resolution, not fast.

### Acceptance

| Criterion | Result |
|---|---|
| `config.yaml` names the new fast and reasoning models, bulk unchanged; `base.py` and `ui_data.py` fallbacks name the same | **Met** (R1) |
| Each new model: reasoning optional; `json_object` parses 6/6 with reasoning off; restraint holds | **Met.** `mandatory: false` in the saved catalogue and today's; 6/6 by plain `json.loads`; restraint 3/3 (the only task that checks it) |
| Fast model: no fabricated source, skipped tool or broken answer; faster than its predecessor; serves the pre-open JSON check | **Met** on the bench (0/0/0; 14.0 s against 20.6 s; JSON 6/6). The pre-open host exposure is L2 |
| The reasoning model is a different vendor from the fast model | **Met** (R2, R4) |
| Every tier model has a cost rate; reasoning priced at its own rate with hand-worked values; previous tiers keep rates | **Met** (R3, M1–M5). glm-5.2's kept rate is out of date (L1) |
| The living docs that name the tiers describe the current models: CODEBASE, README, AGENTIC_DESIGN, ARCHITECTURE, CHAT_ARCHITECTURE, PRODUCT_MAP, RL_DESIGN | **Not met.** `CODEBASE.md:368` names glm-5.2 as the chat escalation (R-AC6) |
| Production verification separate: telemetry shows the new ids with successful calls for chat, pre-open and the analyst; no Railway `LLM_MODEL_*` override | **Pending.** The code has been live since 23 Oct 00:10 IST. The analyst check as worded cannot see a parse failure (M1) |

## Verdict

**CHANGES REQUESTED** for `560d18f` (diff `156a0b84…`).

**Rework 1**, in a new conversation, is documentation and wording, plus one optional line of code:

1. **Required (R-AC6):** `CODEBASE.md:368` and `:573-574`, as current design.
2. **M1:** guide 11-L's expected result and the implementation receipt's production step 2 add the
   analyst parse check.
3. **L1 and I1:** fix the glm-5.2 rollback wording (or its rate), Alibaba's window in
   `config.yaml:18-19` and in the receipt, and the receipt's restraint column.
4. **Recommended (L2):** `provider.require_parameters` on the pre-open call, or a fence strip, with
   a test. Otherwise route it to PR-012.

A later fresh review signs off rework 1. Its commit and push need the owner's word, in a job-free
window. Since `560d18f` is already live, rework 1 changes production only if L2 is taken.

**Production verification can proceed now, separately.** FIX-013 has been deployed since 23 Oct
00:10 IST. STATE `production_verification` is `pending_observation`, with these owner checks:

1. No Railway variable named `LLM_MODEL_FAST`, `LLM_MODEL_REASONING` or `LLM_MODEL_BULK`.
2. **Today (23 Oct), from 08:45:**
   - the pre-open check logged no `LLM shock rating failed` line;
   - telemetry rows for `preopen_check` and `ui_chat` show `deepseek/deepseek-v4.1-flash-1017`
     with `success` 1.
3. **After today's 16:30 run:**
   - analyst and aggregator rows show `xiaomi/mimo-v2.6-pro`;
   - no `unified analyst failed -> legacy fallback`, `[UnifiedAnalyst] run() failed` or
     `response truncated` line;
   - no degraded FeedbackAgent line.
4. Guide case 11-L's chat questions, on the first trading morning.
