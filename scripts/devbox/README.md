# Dev box: the unattended "continue" loop

`auto_continue.sh` runs the PI's `continue` phases one after another on the owner's
always-on dev box (the Railway code-server service), so nobody has to type `continue`.

- Each phase is a new, non-interactive Claude Code session, so an implementation and its
  review never share a conversation.
- Each phase ends with a `LOOP: NEXT` or `LOOP: STOP | reason | line` line, as defined in
  [AGENTS.md](../../AGENTS.md) under "Unattended loop runs".
- The loop sends each briefing to the owner's phone and stops whenever the owner is needed.
- It never pushes, deploys or touches production.

## When it stops

| Stop | What to do |
|---|---|
| `decision`, `production`, `blocked` | Open a session from the Claude app, deal with it, then `resume` |
| `commit` | Commit, and push in a safe window (every push to `main` deploys), then `resume` |
| `failed`, `error`, `timeout`, `no LOOP line` | Read the briefing and the log in `~/.autocontinue/logs/`, then `resume` |
| `main moved` | Someone pushed from another machine. Run `git pull` on the box, then `resume` |
| `usage limit` | Nothing. It waits out the usage window by itself, and stops only after 12 waits |
| `target`, `phase cap`, `paused` | The run is complete. Start a new one when you want |

## One-time setup on the box

1. **Notifications.** Install the free **ntfy** app on your phone and subscribe to a
   long random topic name. The name works like a password: anyone who knows it can read
   the briefings. Then, on the box:
   ```bash
   mkdir -p ~/.autocontinue && chmod 700 ~/.autocontinue
   printf 'NTFY_TOPIC=%s\n' 'your-long-random-topic' > ~/.autocontinue/config
   chmod 600 ~/.autocontinue/config
   ```
   A Telegram bot works too: set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` instead.
2. **A push guard, box only.** It is a second lock behind the loop's own ban on `git push`:
   ```bash
   cat > ~/project/StockAgent/.git/hooks/pre-push <<'EOF'
   #!/bin/sh
   [ "${ALLOW_PUSH:-0}" = 1 ] && exit 0
   echo "pre-push: pushes from the dev box need ALLOW_PUSH=1 (a push to main deploys)." >&2
   exit 1
   EOF
   chmod +x ~/project/StockAgent/.git/hooks/pre-push
   ```
   When you decide to push from the box yourself, run `ALLOW_PUSH=1 git push`.
3. **A first, supervised phase.** Watch one phase end to end:
   ```bash
   cd ~/project/StockAgent
   scripts/devbox/auto_continue.sh run --max-phases 1
   ```
   Check that the briefing reached your phone and that STATE.json and HANDOFF.md look right.

## Everyday use

```bash
scripts/devbox/auto_continue.sh start --target FIX-030   # runs in tmux session "loop"
scripts/devbox/auto_continue.sh status                   # running or not, recent log
scripts/devbox/auto_continue.sh pause                    # stop after the current phase
scripts/devbox/auto_continue.sh resume                   # clear the pause and carry on
```

- From your phone, you can ask any Claude app session on the box to run these commands.
- `--target` names the story whose acceptance ends the run. `--max-phases` caps a run (default 6).
- Optional settings in `~/.autocontinue/config`:
  - `LOOP_MODEL` and `LOOP_EFFORT`: default `opus` and `xhigh`, as on the laptop;
  - `PHASE_TIMEOUT`: default `4h`;
  - `LIMIT_WAIT` and `LIMIT_MAX_WAITS`: default 30 minutes and 12 waits;
  - `LOOP_ALLOW_LOCAL_COMMIT=1`: lets a phase commit accepted work locally, so the loop can
    move on to the next story. It still never pushes.

## Morning review

Every briefing the loop sends is also appended to `~/.autocontinue/briefings.md` on the box,
newest at the bottom: the phase, the outcome, the tests run, what comes next and why the loop
stopped.

```bash
scripts/devbox/auto_continue.sh briefings          # only what is new since you last marked it read
scripts/devbox/auto_continue.sh briefings --done   # mark everything as read
```

To go through a night's work with Claude, open a session on the box from the Claude app and
say: *"Read ~/.autocontinue/briefings.md (the unread part) and walk me through each phase
before I approve the commit and push."* That session can also open each phase's receipt and
diff.

## What it cannot see

- **Loop sessions don't appear in the Claude app's session list.** Briefings come by
  notification, and full transcripts stay on the box: run `claude --resume` there, or read
  `~/.autocontinue/logs/`.
- **Don't start Claude app sessions on the box while the loop runs.** They share the same
  checkout. Pause the loop first.
- **Spotting a usage limit relies on the error's wording.** If the wording changes, the loop
  stops with `error` instead of waiting. That is safe, but you would then resume it by hand.
