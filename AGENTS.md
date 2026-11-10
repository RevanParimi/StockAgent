# StockAgent repository working instructions

## Continuing the active PI

When the user says **continue** (or asks to work through the audit sprint plan), use repository state rather than assuming hidden chat memory:

1. Read `docs/planning/PI-2026-09/HANDOFF.md` and `docs/planning/PI-2026-09/STATE.json`. Inspect git status and preserve unrelated user changes.
2. Resume the active story if one is in progress, changes-requested or awaiting review. Otherwise select the first planned `todo` story whose dependencies are `done`, ordered by the state file. Treat `next_task` as a checked hint, not permission to ignore dependencies. A blocked task needs a concrete recorded reason; another ready authorized task may proceed. Stretch tasks require explicit promotion.
3. Read only the selected story, required evidence receipt and relevant code/docs. Consult the dated audit for its linked findings; do not load every story or historical chat.
4. Execute **one implementation or fresh-session review phase per conversation**. Implementation includes appropriate tests and self-review, then stops at `review_required`. The next fresh conversation performs the hard review from `REVIEW.md`. Same-conversation self-review cannot be signed off as a fresh review; leave that gate pending and explain the fresh-chat handoff.
5. Before editing, set `active_task` and status. After the phase, update STATE.json, HANDOFF.md and the story's sanitized evidence receipt together. Record exact tests, changed-file manifest and reviewed diff/revision digest. Only accepted tested work becomes `done`; production verification is separate. Select the next ready story after acceptance, but do not start it in the same conversation.

If the user explicitly changes scope or requests a specific task, their instruction wins; record the resequencing and unresolved dependencies. If these plan files are unavailable, report that concrete problem rather than inventing completion history. Outside the owner's unattended loop (below), the user opens a fresh conversation in this same repository for each phase.

## Unattended loop runs

On the owner's dev box, `scripts/devbox/auto_continue.sh` starts each phase as a new non-interactive session whose prompt says it is an unattended loop run. In such a run, follow "Continuing the active PI" above, with these additions:

1. Nobody can answer mid-phase. Do not ask questions or wait for a reply. When the phase needs an owner decision, an authorization or anything only the owner can supply, record it in HANDOFF.md at a safe point and stop.
2. Do not push, deploy, run `railway`, change production variables or flags, trigger jobs, migrate production data or send messages. Commit only when the prompt says the owner allows a local commit, and never push. Production checks that are due are owner actions: list them, and stop if the phase depends on one.
3. End the final message with a briefing of at most 10 lines (task and phase, outcome, tests run, what comes next, what needs the owner). Make the last line exactly one of:
   - `LOOP: NEXT`, when the next phase can start without the owner;
   - `LOOP: STOP | <reason> | <one line>`, where the reason is `decision`, `commit`, `production`, `blocked`, `failed`, `target` or `uncertain`.
4. `NEXT` is only for a phase that ended cleanly, with STATE.json, HANDOFF.md and the receipt updated together. An implementation that reaches `review_required` and a review that requests changes are both `NEXT`. Stop with `commit` when accepted work waits for the owner to commit or push (unless the prompt allowed a local commit and you made it), with `target` once the stop target named in the prompt is accepted, with `failed` when a test or check fails and the phase cannot fix it, and with `uncertain` whenever you are unsure.
5. The briefing reaches the owner's phone through a third-party notification service, so it must hold no secrets, user data, raw logs or production payloads.

## Review and change boundaries

- Update affected living documentation and human testing cases with each implementation story. Regenerate `docs/StockAgent-Three-Loops.pdf` whenever its source `docs/TECHNICAL_DESIGN.md` changes. Keep current code, planned PI behavior and measured production evidence distinct; SA-031 is the final consistency check, not a deferral of documentation to the end.
- Follow `docs/planning/PI-2026-09/REVIEW.md`. Financial targets, issue-time information, price identity/freshness, idempotency and final weight constraints require independent invariant tests, not only implementation-shaped assertions.
- Distinguish code inspection, local reproduction, measured production evidence and inference. Do not equate changed weights, retrospective replay, successful HTTP/LLM calls or code completion with demonstrated learning benefit.
- Keep tasks focused. Prefer correcting contracts and deleting measured duplication to new frameworks, distributed infrastructure or more adaptive modifiers.
- Local implementation, reversible fixes and read-only production inspection are in scope when continuing a selected story. Do not deploy, push, change production variables/flags, trigger jobs, migrate production data, or send email/push messages without applicable explicit authorization. Use prior authorization when present; prepare concrete reviewable changes before asking for missing authorization.
- Never expose `.env`, tokens, private user payloads or raw production logs in tool output/commits. Use isolated deterministic tests without real transports or runtime data. Preserve unrelated files, including the pre-existing untracked PDF.
- Keep raw diagnostics under ignored `analysis_data/`; only sanitized evidence summaries belong in tracked documentation. Do not assume those local diagnostics exist in another checkout.

The dated audit is `docs/audit/2026-09-10-repository-production-review.md`. Historical August specifications are context, not proof of current implementation or permission for production actions.
