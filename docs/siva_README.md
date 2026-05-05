# Siva's Working Folder — Banking & BFSI Agent

This folder is the working space for the Banking & Financial Services agent design and team training.

## Files

| File | What it is |
|---|---|
| `TRAINING_PLAN.md` | Complete 8-module team training plan — covers architecture, data, agents, RAG, RL, build milestones |
| `REPO_CONTEXT.md` | What is already built in the repo vs what needs to be built for BFSI |
| `banking_agent_v5.html` | Full interactive architecture diagram — 17 agents, stocks universe, F&O contracts, MF universe, setup costs |

## Quick orientation

- The **Automobile sector** (`core/sectors/automobile/`) is fully built — this is your reference implementation
- The **Banking sector** (`core/sectors/banking/`) has empty stubs — this is what we're building
- All infrastructure (BaseAgent, Orchestrator, RAG, RL, API, frontend) is **reusable as-is**
- The 17-agent BFSI design is documented in `banking_agent_v5.html` and detailed in `TRAINING_PLAN.md`

## Start here

1. Open `banking_agent_v5.html` in a browser — understand the full architecture visually
2. Read `REPO_CONTEXT.md` — understand what's built and reusable
3. Read `TRAINING_PLAN.md` Module 0 — run `python main.py MARUTI` to see the system end-to-end
4. Then follow the training plan module by module
