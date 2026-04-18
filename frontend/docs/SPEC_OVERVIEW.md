# StockAgent Frontend — Master Specification

## What This Is
Production-grade React frontend for StockAgent — an AI-powered multi-agent stock analysis
system for Indian automobile stocks (NSE/BSE).

## Quick Links
- [Backend Context & API](./SPEC_BACKEND.md)
- [Tech Stack](./SPEC_TECHSTACK.md)
- [Design System](./SPEC_DESIGN.md)
- [Phase 1 — Landing + Auth](./SPEC_PHASE1.md) ✅ COMPLETE
- [Phase 2 — Dashboard + Watchlist](./SPEC_PHASE2.md)
- [Phase 3 — Analyze (Flagship)](./SPEC_PHASE3.md)
- [Phase 4 — History + Polish](./SPEC_PHASE4.md)
- [3D & Interactive Effects](./SPEC_3D_EFFECTS.md)
- [Mock Data](./SPEC_MOCKDATA.md)
- [Rules & Constraints](./SPEC_RULES.md)

## Current Status
| Phase | Status | Commit |
|-------|--------|--------|
| Phase 1 — Landing + Auth | ✅ Done | e7ba984 |
| Phase 2 — Dashboard + Watchlist | ✅ Done | ae90074 |
| Phase 3 — Analyze | ✅ Done | — |
| Phase 4 — History + Polish | ✅ Done | — |

## Run
```bash
cd frontend
npm run dev   # → http://localhost:5173
```

## Backend URLs
- Python FastAPI:    http://localhost:8000
- TypeScript proxy:  http://localhost:3000
- C# Scheduler:      http://localhost:5000
