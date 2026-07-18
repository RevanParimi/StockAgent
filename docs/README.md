# docs/ — Documentation Index

Two kinds of documents live here. Know which kind you're reading.

## Living documents (kept current — update these when the system changes)

| Document | What it covers | Audience |
|---|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | **Start here.** Current-state system map: the three loops, runtime topology, all 16 scheduled jobs, data volume layout, LLM tiers, security posture | Everyone |
| [../README.md](../README.md) | Product-level tour: what it does, sectors, verdicts, portfolio features, FAQ | Users / evaluators |
| [../CODEBASE.md](../CODEBASE.md) | Module map, API endpoint census, sector registry, configuration reference | Developers |
| [RL_DESIGN.md](RL_DESIGN.md) | The self-learning loop in full: memory files, daily review steps 0–9, formulas, LLM contracts, Knowledge Layer, Living Envelope | RL developers |
| [AUTOPILOT_GUIDE.md](AUTOPILOT_GUIDE.md) | Compass money path: advisor rule cascade, executor invariants, ledgers | Portfolio developers |
| [CHAT_ARCHITECTURE.md](CHAT_ARCHITECTURE.md) | Agentic streaming tool-loop behind `/ui/chat/stream` | Chat developers |
| [AGENTIC_DESIGN.md](AGENTIC_DESIGN.md) | Agent taxonomy, per-dimension metrics and data sources, static-vs-LLM boundaries | Prompt/agent developers |
| [TECHNICAL_DESIGN.md](TECHNICAL_DESIGN.md) | Deep implementation reference: fetchers, context builders, settings, sector engines | Developers (encyclopedic) |

Each living deep-dive carries a **Status** banner under its title stating when
it was last verified and which sections have drifted; trust the banner over the
body text where they disagree.

## Audit program (append-only working artifacts)

| Document | What it is |
|---|---|
| [audit/CHARTER.md](audit/CHARTER.md) | The audit program's scope, protocol, and hotspot ranking |
| [audit/LEDGER.md](audit/LEDGER.md) | Every finding (`AUD-###`) with evidence, severity, and fix status — the "why is the code like this" record |
| [audit/MAP.md](audit/MAP.md) | System reality map: LIVE / DARK / DEAD census of every module at audit time |

## Frozen history (do **not** update)

- `superpowers/plans/` — implementation plans as approved, one per feature/wave.
- `superpowers/specs/` — design specs as approved.

These are provenance: they record what was *intended* at the time, and the
audit ledger records what was later found and changed. Editing them
retroactively would destroy that trail. When a plan and reality disagree, the
plan is the historical artifact — [ARCHITECTURE.md](ARCHITECTURE.md) and the
code are the truth.
