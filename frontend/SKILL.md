---
name: stockagent-design
description: Use this skill to generate well-branded interfaces and assets for StockAgent — the AI-powered multi-agent stock analysis product for Indian equities. Produces production code or throwaway prototypes/mocks that match the "Bloomberg Terminal meets Apple Vision Pro" dark-cinematic aesthetic: deep near-black backgrounds, electric-cyan primary accent, green/amber/red verdict system, Inter + JetBrains Mono, 16px glassmorphism cards, restrained purposeful motion. Contains essential design guidelines, colors, type, fonts, assets, and UI kit components for prototyping the Dashboard, Analyze (agent stream + verdict reveal), and shared surfaces.
user-invocable: true
---

Read the `README.md` file within this skill, and explore the other available files — `colors_and_type.css` (tokens), `preview/` (design-system cards), `ui_kits/stockagent/` (the Analyze-page UI kit with pixel-faithful recreations of `ScoreGauge`, `VerdictReveal`, `AgentCard`, `StreamProgress`, etc.), and `ui_kits/stockagent/_ref/` (verbatim TSX from the upstream repo for reference).

If creating visual artifacts (slides, mocks, throwaway prototypes, etc), copy assets out and create static HTML files for the user to view. If working on production code, you can copy assets and read the rules here to become an expert in designing with this brand.

If the user invokes this skill without any other guidance, ask them what they want to build or design, ask some questions, and act as an expert designer who outputs HTML artifacts _or_ production code, depending on the need.
