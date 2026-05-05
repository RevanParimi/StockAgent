# Stock Market Agent — Skill Bundle

A skill pack for Claude Code, scoped to building an AI-powered investing tool for the Indian stock market.

## Layout

```
.claude/skills/
├── README.md                          (this file)
├── PROJECT.md                         Living source of truth for project state
├── EXAMPLES.md                        Sample requests + expected skill loading
├── meta/SKILL.md                      Self-update: edits PROJECT.md and skills as decisions happen
├── software-engineer/SKILL.md         Code, tests, refactors, reviews
├── ai-engineer/SKILL.md               LLM features, RAG, agents, evals
├── system-design-engineer/SKILL.md    Architecture, scaling, data modeling
├── devops-engineer/SKILL.md           CI/CD, infra, observability
├── support-engineer/SKILL.md          Incidents, debugging, RCA
├── market-domain/SKILL.md             Indian market structure, SEBI, instruments
└── signal-engineering/SKILL.md        Signal taxonomy, combination, backtesting
```

## How skills load

Each `SKILL.md` opens with YAML frontmatter (`name` + `description`). Claude Code reads only the frontmatter at first. When your request matches a description, Claude loads the full body before responding. Multiple skills load together when tasks span roles.

## Self-updating bundle

This bundle updates itself as you work. You don't fill it in upfront.

`PROJECT.md` is the living state file. It tracks output mode, asset scope, tech stack, current sprint, decisions made, decisions pending. Every other skill references it instead of duplicating facts.

The `meta` skill triggers whenever you make a decision in conversation. Phrases like "we're using X," "decided to go with Y," "update the skills," "log this decision" cause Claude to edit `PROJECT.md` (or the relevant `SKILL.md` if it's role-specific) before responding. Edits happen in the same turn as the decision, so the bundle is always current.

Anything not yet decided is marked `<TBD>`. Run `grep -r "<TBD>" .claude/skills/` to see open decisions.

## Install

From your codebase root:

```bash
mkdir -p .claude/skills
cp -r /path/to/this/bundle/* .claude/skills/
```

Claude Code picks them up next session.

## Day-one workflow

1. Open `PROJECT.md`. The fields are mostly `<TBD>`. That's fine.
2. Start working. As you decide things, say so out loud to Claude.
3. The meta skill catches decision-language and updates files automatically.
4. Periodically grep for `<TBD>` to see what's still open.
