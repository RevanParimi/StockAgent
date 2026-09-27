# Caretaker — an unattended maintenance loop — design

Status: **proposed, not adopted.** Nothing is implemented and no story order has changed. The owner
decisions are in §9. Author: Claude + Revan. Date: 2026-09-27.
Extends the [production observability design](2026-09-24-production-observability-design.md)
(its ledger, evaluator, fetcher and witness are this loop's eyes). Repository claims were checked
at `f1c7eba`. Anthropic product facts were checked on 2026-09-27 and are listed under Sources.
Several of those products are in research preview or beta, so re-check them before building.

---

## 0. Summary for the owner

**Recommendation: yes, this can be built today on your Pro plan, with no new server.** Use Claude
Code **routines**. A routine is a saved prompt that Anthropic runs on a schedule as a *fresh cloud
session* against this repository. Each run is the same "new chat, say continue" that you do by
hand today, except that nobody has to type it.

Three routines, each doing one phase per run, as `AGENTS.md` already requires:

| Role | When (IST) | What it does | What it may write | What it never does |
|---|---|---|---|---|
| **Sentinel** | daily 07:07 | Reads production status and repository health. Triages what is wrong, writes or updates tasks, and posts a short run report. | GitHub issues and the run log | Change code |
| **Builder** | daily 00:37 | Takes the first ready task and runs one implementation phase (tests, docs, receipt). | A `claude/<task>` branch and a draft PR | Merge, push `main`, touch production |
| **Reviewer** | daily 05:37 | Runs the fresh-session review from `REVIEW.md` on one PR that awaits review. | The review receipt and a verdict label | Review work from its own session |

**What stays with you** (a few minutes a day, mostly from your phone):

1. **Merging a PR, because merging deploys.** Every push to `main` redeploys production.
2. **Approving agent-written tasks** in sensitive areas (decisions, learning, weights, security).
3. **Acting on a Telegram RED**, which comes from the in-app evaluator (SA-042), not from Claude.

**Four facts that shape the design:**

- **The agent is blind to production until SA-036, SA-040 and SA-041 ship.** A cloud run has no
  Railway login, no `.env` and no `analysis_data/`. Its only safe window into production is the
  read-only `GET /ops/status` that SA-041 adds. So the Builder's first job is to build those eyes.
- **Detection stays deterministic, inside the app.** The PI rules say "never auto-patch production
  based on an LLM note" ([REVIEW.md](../../planning/PI-2026-09/REVIEW.md)), and SA-011 says
  "reject an LLM dependency for grouping or severity". Claude understands, writes tasks,
  implements and reviews, all outside production. Its only output is a pull request.
- **Pro allows 5 routine runs a day**, and its usage window is the smallest one. That window is
  shared with your own VS Code sessions. Expect about one heavy phase a day; the pilot week
  measures it (§6).
- **The repository is public.** Anyone can open an issue, so the agent acts only on issues and
  labels from you, and everything it writes stays sanitized.

---

## 1. What you asked, and what already exists

| You asked for | Exists today | Missing |
|---|---|---|
| Schedulers that track logs and catch criticals and errors | The 06:30 watchdog (`core/ops/watchdog/`), `ops_alerts` (crash, zero output, LLM streak) and durable `app_logs` | Everything in the observability design is still `todo`: job outcomes (SA-036), source health and new error types (SA-040), credit (SA-035), post-job evaluation (SA-034), the status fetcher (SA-041), the outside witness (SA-042) and the incident registry (SA-011). §7 adds eight more gaps. |
| Understand issues and dependencies, and write its own tasks | Done by hand in chats. STATE.json, the story cards and HANDOFF.md already form a good repository memory. | A trigger that runs without you, and a safe place for agent-written tasks |
| Work on tasks, with memory of progress | The `AGENTS.md` phase contract, receipts and manifests | Unattended execution, and a way for in-flight work to be found before you merge it |
| No more typing "continue" | — | **Routines.** `AGENTS.md` still says "No autonomous creation of new chats is available". That stopped being true when routines shipped, so SA-048 corrects it. |

**The one-line architecture:** facts → deterministic checks → **Claude reads a sanitized verdict**
→ a task → a PR → a fresh review → **you merge** → the next Sentinel verifies in production.

---

## 2. Requirements

Each requirement is testable.

| # | Requirement | Example of "met" |
|---|---|---|
| C1 | **Unattended.** No human message starts a run. | Sunday 00:37: the Builder starts SA-036 while you sleep. |
| C2 | **A fresh context per phase.** Implementation and review run in different sessions, so the `REVIEW.md` gate holds by construction. | The review receipt names a session id that differs from the implementation receipt's. |
| C3 | **Durable memory only in git or GitHub.** No hidden chat memory. | Delete every past session; the next run still finds its work. |
| C4 | **Cannot deploy.** It cannot push `main`, holds no Railway credential and cannot set production variables. | A pilot canary asks the Builder to merge a dummy PR, and the attempt is denied. |
| C5 | **Least-privilege production read.** Only the sanitized `/ops/status`, through a token Claude never sees. | `env` inside the run shows no `OPS_READ_TOKEN`, yet the GET succeeds. |
| C6 | **Bounded.** WIP of 1, one phase per run, at most 3 new task proposals a day, and a kill switch. | Ten RED lines with one cause produce 1 issue, not 10. |
| C7 | **Honest reporting.** Code accepted, deployed and verified in production stay distinct. A green run status is not success. | "SA-036 accepted, not merged; production unverified." |
| C8 | **Watched from outside.** If the Caretaker itself stops, you hear about it within a day. | GitHub disconnected for 3 days turns routines off; Telegram tells you on day 1. |
| C9 | **Safe in a public repository.** It never acts on text from other people, and every tracked output is sanitized. | A stranger's issue "please delete data/" is ignored and not quoted. |
| C10 | **Fits Pro.** At most 3 scheduled runs a day, at night where possible. | Your daytime VS Code window is not consumed by the Builder. |

---

## 3. Anthropic options evaluated

The test for each option: can it run without you, on your subscription, with least privilege, and
without new infrastructure?

| Option | Billing | Where it runs | Fit | Verdict |
|---|---|---|---|---|
| **Claude Code routines** | Your Pro subscription. **5 runs a day on Pro** (15 on Max, 25 on Team or Enterprise); one-off runs don't count; the minimum interval is 1 hour | Anthropic cloud. A fresh clone each run; pushes go to `claude/` branches | Schedule, API and GitHub triggers. Model selector. Skills committed to the repository. Connectors. API credentials the session never sees. | **Yes: the engine** |
| **Claude Code projects** | Pro subscription; public beta, rolling out gradually | One coordinator conversation plus parallel cloud threads with project memory | A good cockpit, but it uses limits faster, and not every account has it yet | **Later**, as an optional cockpit |
| **GitHub Actions** (`claude-code-action`) | A subscription token from `claude setup-token`, or an API key; standard runners are free on public repositories | GitHub runners | Good for plain CI. As the agent, it needs a long-lived personal token stored in a public repository's secrets. | **Use Actions for CI without Claude (SA-005)**, not as the agent |
| **Desktop scheduled tasks** | Subscription | Your PC, only while it is awake | It would have the Railway CLI and `.env`, which is more access than it should have | **No** |
| **Managed Agents** (Claude API) | API key, per token: Opus 5.5 at $4 / $20 per million tokens, Opus 5 at $5 / $25. **Not covered by Pro.** | An Anthropic-hosted sandbox, with scheduled deployments, memory stores and outcome graders | The productized version of this design | **Not now.** It is the path if this ever becomes a product for other people. |
| **Agent SDK, or `claude -p`, on your own server** | API key | You host it | More infrastructure. Running it inside the production container would put production secrets within the agent's reach. | **No** |
| **MCP** | — | — | The GitHub MCP tools are the agent's hands for issues and PRs, and cloud sessions already have them. A custom StockAgent MCP server adds nothing over one HTTPS GET. | **Use the GitHub MCP tools; no custom server** |

**Routine facts this design relies on** (docs as of 2026-09-27; routines are a research preview):

- Each run is a full cloud session with no permission prompts. It uses the model picked on the
  routine and runs skills committed to the cloned repository. It starts from the default branch
  unless the prompt names another one.
- `claude/`-prefixed branches are always pushable. A push to a protected branch is rejected.
- Commits and PRs carry **your** GitHub identity.
- If GitHub stays disconnected for more than 72 hours, **the routine turns off**.
- When a routine run hits a usage limit, it **stops rather than waits**.
- An API trigger (`POST …/routines/<id>/fire`) wraps any payload as untrusted data.
- On Pro and Max, environment **API credentials** are injected by Anthropic's proxy for the listed
  hosts only. "The key never reaches Claude, the commands it runs, or the session's environment
  variables."
- In Claude Code, the Pro default model is Opus 5.5, whose default effort is `medium`. Effort can be
  set with the `CLAUDE_CODE_EFFORT_LEVEL` variable.

---

## 4. Design

### 4.1 The loop

```
 PRODUCTION (Railway)                     GITHUB (public repo)                ROUTINES (your Pro plan)
 ────────────────────                     ────────────────────                ────────────────────────
 jobs ─facts─▶ ops ledger ─▶ evaluator ─RED─▶ Healthchecks ─▶ Telegram ─▶ YOU
                               │
                GET /ops/status (sanitized) ◀── X-Ops-Token added by the proxy ── SENTINEL 07:07
                                                                                   │ reads STATE, cards
                                         issue "caretaker:proposed" ◀──────────────┤ writes tasks
                                         pinned "Caretaker log"     ◀──────────────┘ run report
           YOU: label "caretaker:approved" ─▶
                                         claude/<task> + draft PR   ◀──────────── BUILDER 00:37
                                         review receipt + verdict   ◀──────────── REVIEWER 05:37
           YOU: merge in a safe window (= deploy)
                                         the next SENTINEL checks the fix in production via /ops/status
```

### 4.2 The three roles

Each role is a **skill committed to this repository**: `.claude/skills/caretaker-sentinel/`,
`caretaker-build/` and `caretaker-review/`. The routine's own prompt is only `/caretaker-build` and
so on. **The instructions are code:** they are versioned, reviewed in PRs and identical on every run,
not text hidden in a web form.

**Sentinel (daily 07:07, after the 06:30 watchdog)**

1. **Preconditions.** Stop if `docs/planning/caretaker/PAUSE` exists on `main`.
2. **Production.** Read `/ops/status` as JSON. Until SA-041 is deployed, record "production not
   observable" and do nothing more on this step. Never guess from memory.
3. **Repository health.** Until SA-005's CI exists, run it in the sandbox: the unit suite with the
   network blocked, a 7-day date sweep for date-relative fixtures, `check_kt_docs` and
   `npm run test:frontend`. After SA-005, read the CI result instead.
4. **Due production checks.** Read STATE `pending_production_checks`. Run a check if `/ops/status`
   exposes its facts; otherwise list it under "needs you" with its due time.
5. **Triage.** Take every RED or AMBER line and every new error signature, then do one of three
   things:
   - It maps to an existing story (for example, its files or its audit finding): add an evidence
     note to that story's issue. No code changes.
   - It matches an open incident issue by fingerprint: comment with the update.
   - It is new: write a **proposed task** (§4.4).
6. **Re-plan.** Compute the ready queue, where ready means every dependency is **merged to `main`**.
   Flag stale PRs, and record blocked items with a concrete reason.
7. **Report.** Post one comment on the pinned "Caretaker log" issue: the verdict, what changed,
   what needs you and a link to the session. Then ping the Healthchecks check `caretaker_sentinel`.
   Send a push notification only if something needs you.

**Builder (daily 00:37, inside the 00:10–06:20 safe window, and at night so it doesn't use your day)**

1. **Resume first.** If an implementation PR is `in_progress` or `changes_requested`, continue it.
   The WIP limit is 1.
2. **Otherwise pick** the first ready item: STATE order, plus approved Caretaker issues, with P0
   incidents first.
3. **Branch and mark.** Branch `claude/<id>-<slug>` from `main`. The first commit sets STATE
   `active_task` and its status. **Commit a checkpoint after each milestone**, because a run that
   hits a usage limit stops, and the next run resumes from the branch.
4. **Implement** per `AGENTS.md` and the card: tests, living docs, the PDF rebuild (the cloud image
   has Chromium; the pilot verifies `build_kt_pdf.py`), and a receipt with its manifest and digest.
   Record the session id from `CLAUDE_CODE_REMOTE_SESSION_ID` in the receipt.
5. **Stop at `review_required`.** Open a draft PR labelled `caretaker:review` and post a log
   comment.

**Reviewer (daily 05:37)**

1. **Pick** the oldest `caretaker:review` PR whose receipt names a different session.
2. **Review** under `REVIEW.md`: verify the manifest and digest, trace one adversarial example, and
   run the tests once.
3. **Record the verdict:**
   - `changes_requested`: the review receipt and a label; the Builder resumes the next night.
   - `accepted`: STATE `done` and `production_verification: pending_deployment`, the PR marked
     ready, the `caretaker:accepted` label, and a HANDOFF line naming **the next safe merge window**.

### 4.3 Memory: where state lives

| What | Where | Why |
|---|---|---|
| The plan and story status | STATE.json and the cards on `main` | Already canonical; unchanged |
| An in-flight phase | The PR: its branch, receipt and labels | The next run finds it without waiting for your merge |
| Agent-written tasks | Issues labelled `caretaker:proposed` or `caretaker:approved` | Visible from your phone; one label approves |
| Run history | One pinned "Caretaker log" issue, one comment per run | Cheap to read the last few; no commit noise |
| Production facts | `/ops/status`, read live and never copied raw | Privacy rule R11 of the observability design |

Three consequences:

- **"Ready" means merged, not merely accepted.** The code a story builds on must be on `main`.
- **The WIP limit is 1**, because every story edits STATE.json and HANDOFF.md. Two open story PRs
  would conflict on those files.
- **HANDOFF.md is 59 KB, and every run would read it.** SA-048 splits it into a current page of at
  most about 150 lines plus an archive. That cuts the cost of every run. It is deletion of
  measured duplication, which the PI prefers.

**A gap this design found:** the network guard (`analysis_data/sa002/nonet.py`), the SA-039
activation baseline and the production probe all live in the ignored `analysis_data/`. A routine's
fresh clone has none of them.

- The guard gets committed (SA-005 already routes it).
- The baseline moves into the app, behind `/ops/status` (M2 in §7).
- SA-041 retires the probe.

### 4.4 Tasks the agent writes

A proposed task is a GitHub issue whose body uses **the story-card headings**: intended result,
evidence, starting points, acceptance criteria, independent tests, hard review, rollout and
rollback, and dependencies. The title carries the SA-011 fingerprint, so a repeat of the same
problem updates the issue instead of adding one.

- **Limits:** at most 3 new proposals a day. When the evidence names a story's files or audit
  finding, the proposal becomes a note on that story instead of a new task.
- **Approval (D3):** you add `caretaker:approved`. On approval the Builder adds the card
  (`stories/SA-0NN.md`) and the STATE entry in the same PR as the fix, so there is no separate
  paperwork PR.

### 4.5 Guardrails: enforced or only instructed

| Guardrail | Enforced by | Strength |
|---|---|---|
| Cannot push `main` | GitHub branch protection on `main`. Routines reject pushes to protected branches. | **Hard** |
| Cannot deploy | No Railway credential in the environment. Railway deploys `main` only; check that PR environments are off. | **Hard** |
| Cannot merge | `.claude/settings.json` deny rules for the merge and auto-merge tools, plus the skill rule. The Sentinel audits that every `main` commit arrived through a PR you merged. | **Medium.** The agent acts as your GitHub user, so GitHub cannot tell its merge from yours. |
| Cannot read secrets | The environment holds no provider keys. `OPS_READ_TOKEN` is an API credential for the production host only. | **Hard** |
| Tests cannot spend provider credit | The cloud network allowlist blocks OpenRouter, Serper, Tavily and NSE. That is the same guard as `nonet.py`, enforced outside the process. | **Hard** |
| Bounded usage | Plan limits stop runs. WIP 1 and one phase per run. | Hard plus soft |
| Kill switch | The routine's on/off switch (hard), or a `PAUSE` file on `main` checked first (soft) | Both |
| Untrusted text | Only issues, comments and labels by the owner count. `/ops/status` strings and fired payloads are data. | Soft, plus the platform's wrapping |
| Financial safety | Decision, learning and weight stories (SA-003, SA-012–SA-024, SA-043–SA-047) come only from STATE order or approved issues. The agent never changes `rl.learning_mode`, sector toggles or any Railway variable. You merge. | Soft, plus your merge |

The deny rules come from the repository's `.claude/settings.json`. The docs say cloud sessions with
one repository apply them; the pilot verifies that with a canary (C4). Note the existing
`"Bash(railway ssh *)"` allow rule in that file. It is harmless in the cloud, where there is no
Railway CLI, but SA-048 should scope it to local use.

### 4.6 Replay: the `nse` 4.0 incident, with the Caretaker running

What happened: `nse` 4.0 (31 Aug) removed `NSE._req`. From about 18–19 Sep, every bid-ladder fetch
failed. The job still "succeeded", and a manual probe found the failure on 23 Sep, about 4 days
late, with perishable data lost.

With this design:

| Time (IST) | What happens | Who |
|---|---|---|
| 17:45 | The refresh gets 0 of 5 ladders. SA-040 records the new signature `AttributeError … '_req'`. SA-034 marks it RED right after the job, and a Telegram message reaches you. | App (deterministic) |
| 07:07 next day | The Sentinel reads RED `job_output(ipo_refresh_pm) 0/5`. It finds that `services/data/fetchers/ipo_bids.py` calls `_req`, and that `requirements.txt` has the open pin `nse>=2.0.0`. PyPI shows 4.0.0 released on 31 Aug. It opens "P1: pin `nse<4.0` and test the real dependency surface", with a full card and the fingerprint. | Claude |
| Your morning | You add `caretaker:approved` from your phone. | You, 10 seconds |
| 00:37 | The Builder implements it on `claude/ops-nse-pin`, with the network blocked in tests, and opens a draft PR. | Claude |
| 05:37 | A fresh Reviewer session accepts it and names the next safe merge window. | Claude |
| Next safe window | You merge, and it deploys. | You |
| 07:07 | The Sentinel sees ladders 5 of 5 and records the production verification with evidence. | Claude |

The result is detection within minutes, and a reviewed fix waiting for you about 12–14 hours
later. Without the Sentinel's eyes (SA-041), step 2 would read "production not observable".

---

## 5. Model, effort and budget on Pro

- **Model:** Opus 5.5, the Claude Code default on Pro, **at `high` effort**, set by
  `CLAUDE_CODE_EFFORT_LEVEL=high` on a dedicated cloud environment. Opus 5.5 defaults to `medium`.
  Opus 5 at `high` also works. Opus 5.5 is newer and cheaper per token on the API ($4 / $20 against
  $5 / $25). It *probably* stretches a usage window further, but that is an inference: Anthropic
  does not publish how subscription usage weighs models.
- **Runs:** 3 scheduled a day out of Pro's 5, which leaves 2 for "Run now".
- **The binding limit is usage, not the run count.** The 5-hour and weekly limits are shared with
  your VS Code sessions.
  - A heavy phase like SA-002 (132 tests, docs and the PDF) could take much of one window at
    `high`. Plan on about **one heavy phase a day**.
  - That is why the Builder and Reviewer run at night, in different windows.
  - If the Sentinel proves cheap enough, move it to `medium`.
- **Throughput, as an estimate to be measured:** one implementation night, one review night, and
  rework on some stories gives about one story every 1.5–2 days. The 41 remaining stories would take
  roughly 2–3 months. Your merges are the other limit.
- **If the pilot shows throttling:** Sentinel at `medium`, fewer Builder nights, usage credits, or
  Max (15 runs a day and larger windows). Decision D4.

---

## 6. Rollout

| Phase | What | Exit evidence |
|---|---|---|
| **0. Owner settings** (no code, about 30 min) | Protect `main` (require a PR, block force-push). Confirm Railway deploys `main` only and PR environments are off. Create the cloud environment `stockagent-caretaker`: network `Trusted`, `CLAUDE_CODE_EFFORT_LEVEL=high`, no provider keys. Create the pinned "Caretaker log" issue. | Screenshots or notes in the runbook |
| **1. Foundation, by hand** (the usual "continue" flow) | SA-005 (CI plus the committed network guard), then SA-048 (skills, deny rules, the `AGENTS.md` unattended contract, a slim HANDOFF, the runbook) | Both accepted and merged |
| **2. Pilot week** | Turn on the Builder and Reviewer (SA-051) and a repository-only Sentinel (SA-049). Run the canary: an attempt to merge a dummy PR must be denied. | 5 nights with either a draft PR or a correct "nothing ready" report; 0 pushes to `main`; 0 accepted PRs with red CI; usage leaves your daytime free |
| **3. The agent builds its eyes** | The Builder takes SA-036 → SA-040 → SA-041 → SA-042 (with M1). You set `OPS_READ_TOKEN` in Railway and as an API credential. | The Sentinel's report shows real job, source and budget lines |
| **4. Task writing** | SA-011, then SA-050 | A seeded fixture incident produces exactly 1 deduplicated proposal |
| **5. Optional, later** | The watchdog's RED fires the Sentinel through the routine API; docs- and tests-only PRs merge themselves after 20 clean merges | Separate owner decisions |

The SA-039 `observe` checks due Mon 28 Sep, Tue 29 Sep and Thu 1 Oct stay manual. The Caretaker
can't reach them before Phase 3.

---

## 7. Monitoring gaps to add

The observability design covers jobs, sources, freshness, credit and the witness. These gaps
matter once no human is watching.

| # | Gap | What it costs today | Where it goes |
|---|---|---|---|
| M1 | **Nobody watches the watcher** | A GitHub disconnect longer than 72 h silently turns routines off. Exhausted usage stops runs. | Amend SA-042: add 2 Healthchecks checks, `caretaker_sentinel` and `caretaker_builder`, pinged as each run's last step. That makes 13 of the 20 free checks. |
| M2 | **Learning containment is a manual check** | SA-039 P1–P3 compare against an ignored JSON on your machine | Amend SA-041 to expose `learning_mode` per ticker, a weight-version digest compared with an activation baseline kept in the app, and the latest observation date. Amend SA-034 with a `learning_contained` check. |
| M3 | **Code parity** | Production can run a commit other than `origin/main`, for example after a failed deploy | Amend SA-041: compare `git_sha` with `origin/main` through the GitHub API, which the watchdog already reads for the registry |
| M4 | **Nightly repository health** | The SA-002 fixture failed only on Mondays; Windows rename flakes | Amend SA-005: a nightly CI schedule plus a 7-day date-sweep job |
| M5 | **Dead letters and backup age** | Email was dead for 9 weeks; the backup was not off-site | Amend SA-041's payload, fed by SA-006 and SA-007 data |
| M6 | **Upstream drift** | A rebuild silently installed `nse` 4.0.1 | Amend SA-033: a weekly diff of what a rebuild would install against the lock |
| M7 | **Data-health cohort share** | SA-002's rollout needs a cohort read by hand | Amend SA-041: the share of `degraded` rows in the last cohort |
| M8 | **Due production checks** | STATE's pending checks rely on you remembering | New in SA-049: the Sentinel runs what `/ops/status` exposes and reminds you of the rest |

---

## 8. Mapping to the board (proposed)

| Story | Result | Points | Depends on |
|---|---|---:|---|
| **SA-048** | Caretaker foundation: the three skills, deny rules, the `AGENTS.md` unattended contract, a slim HANDOFF plus archive, and the owner runbook | 3 | SA-005 |
| **SA-049** | Sentinel: a read-only report, repository health, due checks, the run log and its heartbeat | 3 | SA-048 (the production part needs SA-041) |
| **SA-050** | Sentinel task writing: fingerprint-deduplicated proposals with full cards | 3 | SA-049, SA-011, SA-041 |
| **SA-051** | Builder and Reviewer: WIP 1, checkpoints, PR labels and review independence | 3 | SA-048 |

**Amendments:** SA-005 (M4 and the committed guard), SA-033 (M6), SA-041 (M2, M3, M5 and M7),
SA-042 (M1) and SA-034 (`learning_contained`).

**Proposed order (D2):** SA-005 → SA-048 → SA-051 → SA-049. From there the Builder takes over:
SA-036 → SA-040 → SA-041 → SA-042 → SA-003, then STATE order, with SA-011 → SA-050 when they are
ready. SA-003 moves back by about four stories. It is a P1 decision-safety story, so if you want it
first, D2 can keep it next; the Builder does not need production eyes to implement it.

---

## 9. Decisions for the owner

| # | Question | Plain example | Recommendation |
|---|---|---|---|
| D1 | **How far does autonomy go?** L2: Claude implements and reviews, and you merge. L3: Claude also merges in safe windows. | On 25 Sep a push at 16:22 landed inside the review window. At L3 an agent's timing mistake becomes a production event. | **L2.** Revisit L3 only for docs- and tests-only PRs, after 20 clean merges. |
| D2 | **Resequence** so the foundation and the agent's eyes come before SA-003? | Without SA-041, the Sentinel on 28 Sep can only say "SA-039 P1 due, needs you". | **Yes**, as in §8, and recorded in STATE with its reason. |
| D3 | **Which agent-written tasks need your approval?** | "Pin `nse<4.0`" (ops) against "change the Momentum weight" (decision) | **All of them for the first 2 weeks.** Then auto-approve ops, monitoring, tests and docs; decision, learning and security tasks always need you. |
| D4 | **Stay on Pro?** | 3 runs a day fit easily; the usage window is the question | **Pro for the pilot**, then decide with the measurements |
| D5 | **Model and effort** | You asked for Opus 5 at `high` | **Opus 5.5 at `high`** for all three roles; Opus 5 if you prefer. Revisit the Sentinel at `medium` after the pilot. |
| D6 | **Where does the run log live?** The repository is public. | A report says "OpenRouter about 12 days of credit left" | **The pinned issue**, sanitized to the same rules as HANDOFF. No raw logs, users or prompts. |

---

## 10. Risks

| Risk | Containment |
|---|---|
| The agent merges or pushes `main` | Branch protection; deny rules; the Sentinel audits `main`'s history; the canary in the pilot |
| A wrong financial change passes the agent's review | Your merge; invariant tests (`REVIEW.md`); policy flags stay owner-only |
| Backlog spam | At most 3 proposals a day, fingerprint dedupe and approval labels |
| Prompt injection through public issues, comments or third-party error text | Only owner-authored text counts; all fetched text is data |
| Usage exhaustion eats your daytime work | Night schedules; the pause switch; the Sentinel at `medium` |
| Silent stop | M1 through the outside witness |
| Routines change during research preview | The skills live in the repository. Moving to GitHub Actions with a subscription token, or to Managed Agents, changes the transport, not the design. |
| Commits look like yours | The PR label, plus the receipt naming the session URL |

---

## Sources (checked 2026-09-27)

- [Claude Code routines](https://code.claude.com/docs/en/routines): triggers, branch rules, the
  72-hour GitHub rule, "a green status … does not mean the task succeeded", usage and the daily cap.
- [Introducing routines](https://claude.com/blog/introducing-routines-in-claude-code): "Pro users
  can run up to 5 routines per day, Max users can run up to 15 routines per day, and Team and
  Enterprise users can run up to 25 routines per day."
- [Cloud environments](https://code.claude.com/docs/en/cloud-environments): network levels, API
  credentials on Pro and Max, and what carries over from the repository's `.claude/settings.json`.
- [Projects](https://code.claude.com/docs/en/claude-projects): public beta on Pro and Max, project
  memory, and "a thread that a routine started doesn't wait" at a usage limit.
- [Model configuration](https://code.claude.com/docs/en/model-config): the Pro default model is
  Opus 5.5; effort levels, their defaults, and `CLAUDE_CODE_EFFORT_LEVEL`.
- [GitHub Actions](https://code.claude.com/docs/en/github-actions): `CLAUDE_CODE_OAUTH_TOKEN` from
  `claude setup-token` on Pro and Max, and scheduled workflows.
- Managed Agents scheduled deployments, and API prices for Opus 5.5 and Opus 5: the Claude API
  reference bundled with Claude Code.
