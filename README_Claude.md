# new-product — agent-team repo generator (plain-language, anti-drift)

Scaffold a complete autonomous Claude Code agent-team repo by describing your idea in
**plain words**. The scrum-master agent translates that into the technical plan — and is
built to ASK rather than assume, so it never quietly drifts on something you didn't mean.

No dependencies. Pure Python 3. Windows PowerShell, macOS, Linux.

## What it asks YOU (plain, no jargon)
- What should we call it?
- What are you making?
- Who is it for?
- The ONE thing it must get right?
- What annoys you about existing tools / what you'd do differently?
- What will you judge yourself, by feel? (or "not sure")
- Any tech preference? (or "you decide")

## Two things that make it safe to trust

**1. Your answers are always saved.** Whether you type them live or use a file, the
generator writes `docs/answers.json` into the repo. Interactive mode no longer throws your
words away — it plays them back one at a time first, you fix any by number, then it saves.
Nothing vanishes with the chat.

**2. The agent asks instead of assuming.** Because people trust AI and won't review walls of
text, the burden is on the agent not to drift. Baked into every agent:
- ASK, DON'T ASSUME — if unsure and it matters, it asks; it never silently picks a meaning.
- ONE question at a time, in plain everyday words tailored to how you talk.
- Confirms understanding in small one-sentence yes/no checks ("the main thing this must nail
  is X — right?"), never by handing you a big document to approve.
- Marks each translated decision as (confident) or (confirmed-with-human) in DECISIONS, so
  anything it guessed must be confirmed, not assumed.

## Run it
Interactive (answer live; it plays back + saves):
    python new-product.py

Reuse a file:
    python new-product.py --emit-config      # writes answers.json
    # edit answers.json in plain words
    python new-product.py --config answers.json

Options: --out DIR, --no-git

## After generating
    cd <product>
    claude --dangerously-skip-permissions    # if data is non-sensitive
    # paste the prompt from KICKOFF.md

The scrum-master translates your idea, asks you (in plain words, one at a time) anything it's
unsure about, then the team builds — pinging you only when there's something to look at.

## Hard placement rules (handled for you)
- CLAUDE.md at repo root; agents in .claude/agents/ exactly.

## Honest note
The tool removes the setup toil, the jargon, and the risk of silent drift. The one thing it
can't do is know what you want — so answer "the one thing it must get right" carefully. After
that, if the agent is ever unsure, it will ask you rather than guess.
