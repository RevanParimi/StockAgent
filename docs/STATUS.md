---
Last updated: 2026-05-05
Owner of this doc: <TBD>
---

# STATUS.md

Team coordination snapshot. Updated every Friday by the doc owner.
**Rule:** if it's not here, it's not being tracked.

---

## Now — In flight this week

| Item | Owner | Status | Notes |
|------|-------|--------|-------|
| Phase 2 restructure approval | <TBD> | in-progress | RESTRUCTURE_PROPOSAL.md created 2026-04-29; reorganizes project into one-folder-per-sector + shared pipeline; pending team sign-off before BFSI/IT/RE work can proceed |
| Phase 2b: Wire BFSI/IT/Renewable sectors to CLI + API | <TBD> | blocked | Blocked on Phase 2 restructure approval; all three sector graphs are written but not reachable via FastAPI or CLI |
| ContextBuilder extension for new sector agents | <TBD> | blocked | P0 gap (FLOW.md §16.5): BFSI/IT/RE agents receive stub context only; needs routing branches in `tools/context_builder.py` |
| SEBI disclaimer text | <TBD> | in-progress | Required before any public-facing release (PROJECT.md); not yet implemented anywhere in the stack |
| NSE holiday calendar for RL weight adapter | <TBD> | in-progress | `core/intelligence/rl/agents/weight_adapter.py:32` — rolling windows currently exclude weekends only; NSE holidays not modelled |

> **Note to owner:** If you can't identify an owner or status for an item above, fill it in — that's exactly what this file is for.

---

## Next — Planned (next 2–4 weeks)

| Item | Owner | Notes |
|------|-------|-------|
| LangGraph async migration | TBD | `run_agent` nodes call `agent.run()` synchronously; should migrate to `run_async()` for coroutine-clean concurrency under FastAPI (FLOW.md §16.5 P1) |
| Multi-sector API routing | TBD | Add `POST /analyse/{sector}` on FastAPI + `--sector` flag on CLI; TypeScript gateway cron also needs sector param (FLOW.md §16.5 P1) |
| RAG pipeline activation | TBD | Code is written and disabled by default (`RAG_ENABLED=false`); activation requires embedding model choice and ChromaDB seeding; `_rag_retrieve()` also hardcoded for automobile agents only (FLOW.md §16.5 P2) |
| Agent name collision fix | TBD | `fundamentals` and `pattern_analysis` keys exist in all 4 sector registries; fine per-graph today, breaks on any cross-sector join; proposed fix: prefix (`bfsi_fundamentals`, etc.) |
| CI/CD setup + Railway deployment | TBD | Neither configured; Railway is the decided deployment target (PROJECT.md) |

---

## Later — Backlog

Items with no committed timeline. Vague is fine here.

- **Asset scope v2** — F&O, options chain (OI, PCR, IV), commodities, currency; not started
- **Real-time market data** — yfinance is ~15 min delayed; live feed (Zerodha Kite / Upstox) needed for any intraday use case
- **MF holdings integration** — not started
- **SEBI RA registration** — required if tool goes multi-user or public; changes output framing significantly
- **Multi-user scaling** — current design is single-user; SQLite, in-memory cache, and no auth all need revisiting
- **RAG cross-encoder reranking** — `RERANKER_ENABLED=false`; infrastructure exists, not activated
- **Webhook alert hardening** — currently fire-and-forget with no delivery guarantee or retry
- **Intraday regime detection** — `RegimeDetector` exists; not wired to any decision path yet
- **SQLite → Postgres migration** — no driver for this today; revisit when multi-user scale warrants it
