# CLEAN-006 — Merge the four sector prompts into the one path, with their knowledge kept as lenses

Priority: **P2** · Scope: **paused**, owner decision of 2026-11-15 ("keep 8 weeks, then merge"
approved with "go ahead with the recommendations") · Estimate: **8 points, to be split when
promoted** (shadow, switch, retire) · Lane: **decision path** (it changes the analysis that sets
conviction for four sectors; fresh-session review)

Status lives in [STATE.json](../STATE.json), not this card. Depends on [PR-017](PR-017.md),
[PR-032](PR-032.md) and [CLEAN-005](CLEAN-005.md).

**It starts when** the rule below says merge and the owner promotes it. "continue" never selects
it.

**New conversation? Read first:** [EDGE-ROADMAP.md](../EDGE-ROADMAP.md) sections 1 to 3 and 6;
[CLEAN-003](CLEAN-003.md), "The decisions"; [PR-032](PR-032.md), "The design"; the evidence note
[CLEAN-003-production-counts-2026-11-15.md](../evidence/CLEAN-003-production-counts-2026-11-15.md).

## The rule that starts or closes this card (written 15 Nov 2026)

At `PR-014-R2` (8 weeks after the switch-on of 16 Nov 2026), read PR-017's results by path.

- **The four sector prompts stay** only if BUY ideas from the sector paths beat BUY ideas from the
  general path by 2 points or more of mean excess return at 30 sessions, with 30 or more ideas on
  each side. This card is then closed with that table and a note; nothing is merged.
- **Otherwise they are merged** by this card.
- **Too few ideas to judge:** look again each month. With PR-032 live and still no proof by the
  third look, merge.

Until then nothing about the five prompts changes, so the book's first weeks are measured on one
unchanged method.

## What exists today

Every stock runs one analysis call on one data bundle. Five things still differ by path
(automobile, banking, IT, renewables, general):

| What differs | Where | Sizes on 15 Nov |
|---|---|---|
| The prompt | `src/backend/sectors/<path>/prompts/unified.py` | 226, 169, 207, 178 and 108 lines |
| The score dimensions | `src/backend/shared/pipeline/unified_analyst.py` `SECTOR_SPECS`, `DIMENSIONS` | 9, 6, 8, 6 and 8 dimensions |
| The default weight table | each sector's settings; `get_sector_weights` | one per path |
| The search words | `services/data/context/bundle_builder.py` `_SECTOR_BUNDLE_CFG` | one row per path |
| Extra data | commodities table (automobile only); mutual-fund lists (four sectors, `services/data/fetchers/mf_herding.py`) | — |

Measured on 15 Nov 2026: the sector paths cost no extra call, and their data calls return data in
93% to 100% of runs. Whether they pick better stocks was not measured; that is the rule above.

## What merging means

1. **Four more lens files** in PR-032's format (`config/lenses/`): each sector's search words
   copied from `_SECTOR_BUNDLE_CFG`, and its `kpis` and `macro_drivers` taken from that sector's
   prompt and from CLEAN-005's receipt (the list of what the old per-analyst prompts asked for).
   The automobile lens keeps the commodities table as a lens field.
2. **Every stock runs the general prompt with its lens.** The four sector `unified.py` files are
   no longer read.
3. **Shadow first, on deep dives only.** For four weeks each weekly deep dive and re-dive of a
   stock in the four sectors is analysed both ways and both results are recorded; only the sector
   path's result acts. That is a few extra calls a week. Held stocks' daily analyses are not
   doubled.
4. **Switch one sector at a time**, when the two results give the same verdict in 85% or more of
   that sector's shadow pairs, or the owner accepts the difference after seeing the pairs.
5. **Retire** the four prompts, their dimension sets and weight tables, the four rows of
   `_SECTOR_BUNDLE_CFG` and the fund lists, after four clean weeks. The rest of [SA-027](SA-027.md)
   (paused) covers the same files; close what this card retires there.

## What must not change

- **Sector keys and the 30% sector cap** (FIX-026, `core/discovery/sector_naming.py`). A stock's
  key is not its prompt; the keys stay.
- **Store directories** (`<sector>/<TICKER>`, SA-009). No history moves.
- **Open positions' records.** A held stock's stored scores are keyed by its old dimension names.
  List every reader of those names (the daily review's re-scoring, the forecast rows'
  `predicted_agent_scores`, the weight tables, the dossier) before the switch. If the 30-day price
  forecast has been removed by then ([CLEAN-003](CLEAN-003.md)), most of those readers are gone.

## Acceptance criteria (for the split stories to inherit)

- An invariant test: after a sector's switch, a stock of that sector is analysed with the general
  prompt and that sector's lens, and its sector key and store directory are unchanged.
- The shadow pairs are recorded with both verdicts, both convictions and the lens used, and never
  act twice.
- Rollback is one setting per sector.
- PR-017's report keeps the by-path split through the switch, so before and after can be compared.
- Living documents: KT, `docs/TECHNICAL_DESIGN.md` and its PDF, `docs/PRODUCT_MAP.md`, the testing
  guide, the lenses design.

## Not in this card

The factor engine (SA-045 to SA-047, paused). The rest of SA-026: one resolver for routing, store
keys, benchmarks and peer rules.

## Handoff

When promoted: record the split in STATE first. Receipts `evidence/CLEAN-006-*.md`.
