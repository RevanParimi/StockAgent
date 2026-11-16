# CLEAN-003 — production counts behind the keep-or-remove decisions (15 Nov 2026)

**Kind of evidence.** Sections 1 to 7 are **measured in production**: one read-only probe, run at
the owner's request ("we need logs from prod") on Sunday 15 Nov 2026 at 20:15 IST, against the
deployment of commit `1913017`. Section 8 is **code inspection** of the same commit. Nothing here
measures profit; section 9 says what these counts cannot show.

**How.** `analysis_data/clean003/prod_probe.py` (ignored folder; it may not exist in another
checkout), run inside the container with `railway ssh`. It opens `data/telemetry.db` with
`immutable=1`, reads a few JSON files as text and writes nothing. It prints counts, rates and code
labels only. The model-call rows carried a stock symbol in their label; the saved output was
re-aggregated by label prefix and holds no symbol.

## 1. The backup analysis (legacy worker pool)

| Measure | Value |
|---|---|
| Engagements recorded (`data/rl/fallback_events.jsonl`) | **21**, every one dated October 2026 |
| By path | automobile 4, banking 5, IT 4, renewables 4, generic 4 |
| Analyses with a data-health row, last 60 days | 1,361 |
| Of those, runs where the main call scored no dimension | 22 |
| Completed analyses by month (run summaries) | Aug 72, Sep 714, Oct 596, Nov (to the 15th) 329 |
| Settings | `unified_analyst.fallback_legacy` on; `decision_gate.mode` `record` |

The backup ran in about 1.5% of analyses, in October only, and not once in November.

## 2. Do the sector data calls return data? (last 60 days, by path)

"Usable" counts the statuses `ok` and `cache_hit`.

| Path | Analyses | Sector news search usable | Policy page read usable | Commodities | All dimensions scored |
|---|---|---|---|---|---|
| automobile | 368 | 367 (99.7%) | 357 (97.0%), 11 unverified | 368 (100%) | 348 (94.6%) |
| banking | 238 | 238 (100%) | 224 (94.1%), 14 unverified | not fetched | 228 (95.8%) |
| IT | 191 | 191 (100%) | 179 (93.7%), 12 unverified | not fetched | 181 (94.8%) |
| renewables | 182 | 182 (100%) | 170 (93.4%), 12 unverified | not fetched | 174 (95.6%) |
| generic | 382 | 382 (100%) | 376 (98.4%), 6 unverified | not fetched | 375 (98.2%) |

Company news, macro context, fundamentals, technicals, flows and peers were usable in 92% to 100%
of runs on every path. The lowest is banking fundamentals: 218 of 238, with the other 20 served
from a fallback source. **The calls work.** Whether they pick better stocks is not shown here.

## 3. Live prompt editing (Prompt Lab)

| Measure | Value |
|---|---|
| Pending-edits file in production | absent |
| Last midnight `prompt_daily_deploy` run | 14 Nov, status `skipped`, 0 files |
| GitHub deploy configured in production | **no** (token or repository not set) |
| Commits made by it in git history (`prompt-lab (scheduler|manual): ...`) | **none** |

## 4. The daily second AI call (control lane), from the stored monthly scorecards

Share of next-session direction calls that were right, pooled over all stocks.

| Month | Product's forecast | Bare model | Product minus bare | "Same as yesterday" baseline |
|---|---|---|---|---|
| Jun 2026 | 41.0% (n 39) | 40.0% (n 10) | +1.0 | 86.8% |
| Jul 2026 | 43.0% (n 335) | 43.0% (n 293) | 0.0 | 74.6% |
| Aug 2026 | 24.7% (n 259) | 40.6% (n 251) | **−15.9** | 64.7% |
| Sep 2026 | 27.4% (n 361) | 37.5% (n 363) | **−10.0** | 70.6% |
| Oct 2026 | 31.8% (n 371) | 43.8% (n 363) | **−12.0** | 76.8% |

For three months running the product's daily direction forecast was less often right than a bare
model given the same information. Both were far below the simplest guess, "the direction will be
the same as yesterday's" (`core/intelligence/rl/eval/baselines.py` `persistence_accuracy`). These
are the product's own scorecard figures; the probe read them and did not recompute them.

## 5. Where the model calls go (last 30 days: 4,383 calls, 13.7 million tokens)

| Caller | Calls | Share of calls | Share of tokens | Failed |
|---|---|---|---|---|
| `unified_analyst` (the analysis) | 605 | 13.8% | 36.3% | 0 |
| `aggregation` | 605 | 13.8% | 17.2% | 0 |
| `dossier_curator` | 550 | 12.5% | 12.1% | 21 |
| `FeedbackAgent` (grades the daily forecast, writes lessons) | 465 | 10.6% | 20.0% | 21 |
| `control_lane` (the second AI call) | 425 | 9.7% | 3.7% | 21 |
| `company_events` | 407 | 9.3% | 2.1% | 22 |
| `thesis_reviewer` | 359 | 8.2% | 2.5% | 16 |
| `ipo_extract` | 205 | 4.7% | 1.4% | 34 |
| `ticker_resolution` | 155 | 3.5% | 0.5% | 0 |
| `event_ingestor` | 129 | 2.9% | 1.1% | 0 |
| `question_researcher` | 101 | 2.3% | 0.9% | 0 |
| `macro_reviewer` | 90 | 2.1% | 1.0% | 8 |
| `price_interpolator` | 86 | 2.0% | 0.5% | 0 |
| six smaller callers | 201 | 4.6% | 0.8% | 5 |

`FeedbackAgent`, `control_lane`, `thesis_reviewer` and `price_interpolator` serve the daily price
forecast and the frozen learner: 1,335 calls (30.5%) and 26.7% of tokens.

## 6. The C++ indicator module

Absent in production (`stockindicators` cannot be imported; the Dockerfile does not build it).
Production computes RSI, MACD and Bollinger bands in Python. A compiled copy exists on the owner's
laptop (`core/intelligence/algorithms/indicators/stockindicators.cp313-win_amd64.pyd`, untracked),
so local tests can run code production never runs.

## 7. Shelf ideas by path (the shelf file on 15 Nov)

| Path | Active | Dropped |
|---|---|---|
| a sector path ("native") | 8 | 3 |
| the general path ("generic") | 12 | 33 |

45 of the 56 ideas the shelf file holds came from the general path. Why an idea was dropped was not
read, so this says nothing about which path picks better stocks.

## 8. Code inspection (commit `1913017`)

- **The main analysis reads one prompt per path**, `src/backend/sectors/<path>/prompts/unified.py`
  (`unified_analyst.py` `SECTOR_SPECS`). All five paths are on it (`unified_analyst.sectors`).
- **The Prompt Lab cannot edit those prompts.** Its catalogue (`services/api/routes/prompts.py`
  `_CATALOGUE`) lists only the older per-analyst prompt files, which only the backup analysis reads.
- **A backup analysis cannot become a buy.** Its report carries an abstaining data gate
  (`decision_gate.no_provenance_gate`), and the deep dive mints no idea from an abstained analysis
  (`core/discovery/deep_dive.py`).
- **Model failures already raise an alert**: `core/delivery/ops_alerts.py` `record_llm_result`, one
  alert at 10 consecutive failures.
- **Nothing on the buy or sell path reads the control lane.** `daily_review.py` step 10 writes it;
  `core/intelligence/rl/eval/scorecard.py` (the monthly learning scorecard) reads it.
- **All five paths gather data the same way** (`services/data/context/bundle_builder.py`): one
  analysis call, three web searches and one page extract. Each search returns five results, shown
  to the analyst as title and snippet, from the last month. The page extract is cut to 600
  characters (`data_fetch.tavily_max_content_chars`). A sector path differs in its search wording,
  its prompt and score dimensions, the commodities table (automobile only) and the fund lists.
- **The general path's searches do not name the stock's industry.** Its sector search is "India
  stock market {month} {year} sector news policy demand", and its macro search reads "India generic
  sector macro economy ...", because the path's name is put where a sector's name goes.

## 9. What these counts do not show

- Whether ideas from a sector path beat the Nifty more often than ideas from the general path. That
  is PR-017's split by path.
- Whether the lessons `FeedbackAgent` writes are read by any prompt today. CLEAN-003 step 1 proves
  that before anything is removed.
- Why the product's forecast fell behind the bare model from August.
