# Backlog of small findings

Owner's rule of 14 Nov 2026 (AGENTS.md): a finding that is low, latent or pre-existing, and changes
no buy, sell, size or grade today, is written here as one entry with its trigger. It becomes a card
only when its trigger is seen in production or the owner promotes it. Medium or higher findings on
the decision path still become cards.

Each entry: what, where it was found, and the trigger that promotes it.

## Open

| # | Finding | Found in | Promote when |
|---|---|---|---|
| B-1 | The migration shims in `core/pipeline/` and `core/schemas/` are still in place: 141 import sites, and one contract test patches through the shim path | CLEAN-001 item 6a, skipped ([receipt](evidence/CLEAN-001.md)) | A change needs both import paths edited, or the owner asks for the migration |
| B-2 | `docs/superpowers/plans`, the two scaling documents and `docs/archive/` were not moved under one archive folder: `config/milestones.yaml`, which the production watchdog reads, names a plan in that set | CLEAN-001 item 6b, skipped ([receipt](evidence/CLEAN-001.md)) | The IPO lane's milestone is retired or its plan path changes |
| B-3 | The entry band's top is 2% above the close the deep dive read and stays for up to 30 days, so an idea that rises is refused while one that drifts down is bought | Profit-path review F3, code inspection, not measured | `PR-014-D1`'s rule: more than a third of offered BUY ideas refused "above entry band" |
| B-4 | `ARCHITECTURE.md`, `RL_DESIGN.md`, `PRODUCT_MAP.md` and `AGENTIC_DESIGN.md` still label stories that are off the plan (SA-012 to SA-024, SA-043) or paused (SA-026, SA-045 to SA-047) as "Planned" | PR-014's docs commit, 14 Nov: KT sections 11 and 12 and AUTOPILOT_GUIDE section 16 were updated, these four were not | The owner's decision at `PR-014-R2` on whether either group returns, or a reader acting on one of those pointers |

## Parked with their cards

Findings already routed into a card stay in that card's "Routed input" section. When the card is
paused or removed, they wait with it:

- [SA-021](stories/SA-021.md) (removed 14 Nov): FIX-031's review finding R2, the calibration report
  pairs a graded session with a confidence revised after its close.
- [SA-026](stories/SA-026.md) (paused 14 Nov): FIX-028's two low findings (the owner's dashboard
  routes take no lock; the API's delete routes look only at the user's own portfolio).

## Closed

None yet.
