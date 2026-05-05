---
name: meta
description: Use when the user makes a decision, changes direction, picks a tool, defines scope, or otherwise produces information that should be persisted in the skill bundle. Triggers include phrases like "we're using X," "decided to go with Y," "let's switch to," "update the skills," "log this decision," "from now on," "we picked," "we chose," "going with," "scope changed," "no longer using," "TBD on X is now Z." Also triggers when the user asks "what's still TBD," "show open decisions," or "what have we decided so far." This skill edits PROJECT.md and individual SKILL.md files; it does not write application code.
---

# Meta — Self-Update Engine

Your job is to keep the skill bundle in sync with the project as it actually exists. When the user makes a decision in conversation, you persist it before continuing with their main request.

## When this skill is active

You will see decision-language in the user's message. Your behavior changes:

1. **Catch the decision.** Identify what was decided and which file it belongs in.
2. **Edit before answering.** Update `PROJECT.md` (or the relevant `SKILL.md`) in the same turn, before continuing with whatever else the user asked.
3. **Confirm in one line.** "Updated PROJECT.md: output_mode = recommendation." Not a paragraph.
4. **Then handle the rest of the request.** The decision capture is overhead, not the main event.

## Where decisions live

**`PROJECT.md`** — the default destination. Project-level facts: tool name, output mode, asset scope, tech stack, data sources, scale, compliance posture, current sprint. Most decisions land here.

**Individual `SKILL.md` files** — only when the decision is purely about how a specific role operates. Examples:
- "Always run `pnpm test` before claiming done" → `software-engineer/SKILL.md`
- "Eval threshold for production prompts is 90% on the regression set" → `ai-engineer/SKILL.md`
- "All deploys go through canary first" → `devops-engineer/SKILL.md`

When in doubt, prefer `PROJECT.md`. Skill files should describe role behavior, not project facts.

## Editing rules

- **Replace `<TBD>` with the decided value.** Don't leave the placeholder behind.
- **Update the "Last updated" date** at the top of `PROJECT.md` to today.
- **Append to the "Key decisions log"** with format `YYYY-MM-DD — decision — short rationale`. One line per decision.
- **If the decision contradicts something previously logged**, don't delete the old entry. Add a new one and note "supersedes <date>" so history is preserved.
- **If a decision moves an item out of "Open questions,"** delete it from that list.

## Decision-language patterns to catch

These phrasings should trigger an edit:

- "we're using X" / "we'll use X" / "going with X"
- "decided on X" / "let's go with X" / "we picked X"
- "switch to X" / "moving from X to Y" / "no longer using X"
- "scope is X" / "scope now includes X" / "drop X from scope"
- "from now on, do X" / "going forward, X"
- "the answer to <TBD field> is X"

These should trigger a *read* of the bundle, not an edit:

- "what's still TBD" → grep for `<TBD>` and list
- "what have we decided" → show the Key decisions log
- "what's our stack" → read tech stack section of PROJECT.md

## When you're not sure it's a decision

If the user is thinking out loud or weighing options ("we might use Postgres, but Mongo is also on the table"), do not edit. Ask once: "Is that a decision to log, or still under discussion?"

If they say "we're considering X," that's discussion, not decision. No edit.

If they say "let's go with X," that's a decision. Edit.

## Output discipline

After an edit, the confirmation line is brief and structured:

> Updated PROJECT.md → tech_stack.primary_database: Postgres
> Logged decision: 2026-05-05 — Postgres for primary store — relational queries dominate, ops familiarity

Then continue with the user's main request. Don't lecture about the update. Don't list everything you didn't change.

## Boundaries

- You don't edit application code. That's the software-engineer skill.
- You don't make decisions on the user's behalf. If they ask "should we use Postgres or Mongo," that's a system-design question, not a meta question. Hand off.
- You don't delete decisions from the log. History is preserved even when superseded.
