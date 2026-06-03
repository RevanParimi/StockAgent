#!/usr/bin/env python3
"""
new-product.py — scaffold an autonomous agent-team repo from the PROJECT_TEMPLATE design.

Usage:
    python new-product.py                 # interactive (asks the questions)
    python new-product.py --config x.json # non-interactive, reads answers from JSON
    python new-product.py --emit-config    # write a blank answers file you can fill + reuse

What it does:
    - asks ONLY the things a human must decide (the "dots")
    - generates CLAUDE.md, docs/*, .claude/agents/* with paths already wired
    - trims the agent bench to the roles you select
    - inits git with a first commit (unless --no-git)

It does NOT write product code. That's the agent team's job once you open Claude Code.
"""
import argparse, json, os, subprocess, sys, textwrap
from pathlib import Path

# ----- PLAIN-LANGUAGE questions. No jargon. A non-technical person can answer all of these. -----
# The scrum-master agent translates these into thesis/design-law/objective-subjective/milestones,
# and asks back — in everyday words — for anything it can't figure out.
QUESTIONS = [
    ("product_name",  "What should we call it? (short name, becomes the folder)", "my-product"),
    ("what",          "In a sentence or two, what are you making?", ""),
    ("who_for",       "Who is it for, and what do they do with it?", ""),
    ("matters_most",  "What's the ONE thing it has to get right? (if it fails at this, the whole thing is pointless)", ""),
    ("annoys_you",    "What about existing apps/tools like this annoys you, or what would you do differently?", ""),
    ("you_judge",     "What parts will YOU want to look at yourself and judge by feel? (e.g. 'does it look nice', 'does it feel fast') — or say 'not sure'", ""),
    ("tech_pref",     "Any tech preference? (a language, framework, or 'you decide')", "you decide"),
]

CORE_AGENTS = ["scrum-master", "builder", "qa-adversary", "integrator"]
BENCH = {
    "frontend-engineer":   ("Builds user-facing UI: components, layout, client state, accessibility.", "a milestone produces a user-facing interface.", "Build accessible, responsive UI. Verify objectively: components render, state transitions fire, inputs validate, a11y checks pass. The LOOK/FEEL is the human's call.", "opus"),
    "backend-engineer":    ("Builds APIs, services, core business logic, auth flows.", "a milestone adds server endpoints or core service logic.", "Build endpoints/services with clear contracts. Verify objectively: correct status codes, schema-valid responses, business rules enforced, error paths handled.", "opus"),
    "data-engineer":       ("Builds schemas, pipelines, migrations, and data validation.", "a milestone touches storage, ETL, or data correctness.", "Build schemas/pipelines. Verify objectively: migrations apply+rollback, constraints hold, transforms correct on fixtures, no data loss, idempotency where required.", "opus"),
    "network-engineer":    ("Owns networking, connectivity, latency/throughput, deployment topology.", "a milestone depends on real network behavior or infra wiring.", "Wire/verify connectivity. Verify objectively: routes reachable, ports/policies correct, latency/throughput within budget, failover behaves.", "sonnet"),
    "security-reviewer":   ("Reviews authn/z, secrets, input validation, dependency CVEs, threat surface.", "a milestone handles credentials, user data, payments, or external input.", "Audit + harden. Verify objectively: no secrets in code, inputs validated, authz on every path, deps free of known CVEs. You may BLOCK on a real vulnerability — an objective fail.", "opus"),
    "performance-engineer":("Profiles and optimizes: load, latency budgets, resource ceilings.", "a milestone has a measurable performance acceptance criterion.", "Profile + optimize against a NUMERIC budget in the story. Verify objectively: p95 latency, throughput, memory/CPU ceilings met under representative load.", "sonnet"),
    "business-analyst":    ("Turns vague vision into concrete stories, success metrics, prioritization.", "the backlog is unclear, scope is contested, or value/priority needs deciding.", "Sharpen the backlog: crisp user stories with TESTABLE criteria, success metrics, priority tied to the thesis. You don't write code; you hand the scrum-master a clearer map.", "opus"),
    "devops-engineer":     ("Owns CI, build pipelines, containerization, release automation.", "a milestone needs reproducible builds, deployment, or automation.", "Build CI/release. Verify objectively: pipeline green from clean checkout, build reproducible, container starts + passes healthcheck, rollback works.", "sonnet"),
    "docs-writer":         ("Writes user/dev docs, API references, onboarding guides.", "a milestone ships something others must consume or operate.", "Write docs matching shipped behavior. Verify objectively: every documented command/endpoint exists and works as written (test the examples). Prose QUALITY is the human's call.", "sonnet"),
}

def ask(interactive, cfg, key, prompt, default):
    if not interactive:
        return cfg.get(key, default)
    d = f" [{default}]" if default else ""
    val = input(f"  {prompt}{d}: ").strip()
    return val or default

def w(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).lstrip("\n"), encoding="utf-8")

def core_agent_files(root: Path):
    a = root / ".claude/agents"
    w(a / "scrum-master.md", """
    ---
    name: scrum-master
    description: >
      Use PROACTIVELY at session start and between stories. Keeper of the path and owner of
      staffing. Runs the resume ritual, opens/closes stories, activates bench roles by need.
      Invoke for "where are we", "what's next", "open next story", "is this done". No feature code.
    tools: Read, Write, Edit, Bash, Glob, Grep
    model: opus
    memory: project
    ---
    You are the scrum-master and tech lead. Read CLAUDE.md + docs/PROJECT_CHARTER.md + docs/ROLES.md.
    ON EVERY INVOCATION run the resume ritual: read PROJECT_CHARTER, ROLES, SPRINT_STATE (source of
    truth), BUILD_LOG tail, then state "We are at <milestone>, story <id>, status <status>, last
    event <X>." Only then act; if state can't reconstruct, that's bug #1 — fix the state files.

    FIRST-RUN TRANSLATION (do this once, when SPRINT_STATE says status TRANSLATING_INTAKE):
    The human described the product in plain words in docs/INTAKE.md — they are NOT technical and
    should never be asked for jargon. Your job is to TRANSLATE that intake into the technical fields
    and fill the stubbed docs:
    - thesis (the one sentence that must be true) <- from "what matters most"
    - design law (what keeps it honest) <- from "what annoys you / would do differently"
    - objective vs subjective split <- infer from the product; put anything the human said they want
      to "judge by feel" on the subjective side
    - stack + reason <- from tech preference, or choose sensibly and record why in DECISIONS
    - M1 (the first real capability — the riskiest core of the thesis) + its testable criteria
    - which bench roles to activate, based on what the product needs
    - test + lint commands for the chosen stack
    Write all of this into CLAUDE.md, PROJECT_CHARTER, BACKLOG, ROLES, SPRINT_STATE. Then, ONLY if
    something is genuinely missing or ambiguous, ask the human follow-up questions IN PLAIN, EVERYDAY
    LANGUAGE (no "thesis", "epic", "acceptance criteria" — say "the main thing it must nail", "the
    first piece to build", "how we'll know it works"). Tailor the wording to how the human talks in
    their intake. Ask few, only what you truly can't infer. When done, set status to M0.1 TODO and
    proceed normally.

    HOW TO ASK (critical — the human trusts you and will NOT review walls of text, so the burden is
    on YOU not to drift):
    - ASK, DON'T ASSUME. For each thing you translate, decide: am I confident, or guessing? If there's
      a reasonable chance the human meant something else, it's a GUESS — you must ask, not assume.
      Never silently pick an interpretation on something that matters.
    - ONE QUESTION AT A TIME. Never dump a list of decisions for bulk approval. Ask your single most
      important open question, wait for the answer, then the next. Stay silent on what you're sure of.
    - CONFIRM SMALL, NOT BIG. Before building the core, play back ONLY the single most load-bearing
      thing in one short sentence and get a yes/no — e.g. "Quick check: the main thing this has to
      nail is <X>. Did I get that right?" Do NOT ask them to read the charter or backlog.
    - MARK YOUR CONFIDENCE in DECISIONS: each translated item tagged (confident) or (confirmed-with-
      human). Anything you guessed and did NOT confirm is forbidden — confirm it or ask.
    - If the human gives a vague answer, ask a smaller, more concrete plain-language question rather
      than guessing. Better one more tiny question than one wrong assumption baked into the build.
    Authority: you ALONE open stories (write objectively-testable acceptance criteria before any
    code; no criteria -> block) and close them (only after integrator reports full suite green AND
    you checked vs written criteria; author never self-certifies). STAFFING: before each milestone
    ask "what skills does this need?", activate matching bench roles (record reason in DECISIONS),
    or propose a new role per ROLES.md. Keep dormant what's not needed. Own SPRINT_STATE; update
    before ending any turn. Safety rails: nesting depth 1, stop after 3 failed attempts, active
    story only. Cannot judge feel/taste — route to human via blocked_on_human. After any action:
    append BUILD_LOG, update SPRINT_STATE + memory.
    """)
    w(a / "builder.md", """
    ---
    name: builder
    description: >
      Use PROACTIVELY when an opened story needs generic implementation and no specialist is active.
      Writes the feature AND its test harness, runs to green, hands to qa-adversary. A specialist
      REPLACES builder for stories in their domain.
    tools: Read, Write, Edit, Bash, Glob, Grep
    model: opus
    memory: project
    ---
    You implement the ACTIVE story in SPRINT_STATE — never work ahead or invent scope. Read CLAUDE.md,
    the story's acceptance criteria, and DECISIONS. Obey the design law: outcomes emerge from the real
    mechanism, never hardcoded/faked; if about to map input directly to a scripted output, STOP.
    Loop: implement -> write tests for EACH criterion -> run -> red, fix, rerun until green -> lint ->
    hand to qa-adversary. You do NOT declare done. Safety rails: stop after 3 failed attempts, no
    nested agents. Cannot judge subjective quality. After work: append BUILD_LOG, update memory.
    """)
    w(a / "qa-adversary.md", """
    ---
    name: qa-adversary
    description: >
      Use PROACTIVELY after a builder/specialist reports green, before integration. Assumes the
      implementer is wrong until it can't break the feature. Writes ADDITIONAL breaking tests, logs
      every attempt, sends failures back. Invoke for "QA this", "try to break it".
    tools: Read, Write, Edit, Bash, Glob, Grep
    model: opus
    memory: project
    ---
    Stance: broken until you fail to break it. Test against WRITTEN criteria, never "it ran." Write
    ADDITIONAL tests: boundaries, extremes, degenerate inputs, determinism, and the no-hardcoding trap
    (assert an UNTESTED input combo still produces sane output; scripted code fails this). Log EVERY
    attempt to QA_LOG. Failure -> back to implementer. Loop until you can't break it. Safety rails:
    stop after 3 cycles, no nested agents. Passing for merely "running" is forbidden. Can't judge feel
    — note suspected feel issues for the human, don't block. After: append BUILD_LOG, update memory.
    """)
    w(a / "integrator.md", """
    ---
    name: integrator
    description: >
      Use PROACTIVELY after qa-adversary is satisfied, before the scrum-master closes a story. Reruns
      the ENTIRE suite to catch regressions, reports full-suite status. Invoke for "regression check".
    tools: Read, Bash, Glob, Grep
    model: sonnet
    memory: project
    ---
    Your single concern: new work must not break old. Run the COMPLETE suite. Confirm every
    previously-green criterion still passes AND the new story's tests pass. Report total/passed/failed
    and name any regression precisely. Green -> tell scrum-master ready to close. Regression -> back to
    implementer with the exact failing test. Safety rails: no nested agents, stop after 3 failed runs.
    Don't write features or judge quality. After: append the full-suite result to BUILD_LOG.
    """)

def bench_agent_file(root: Path, name: str):
    desc, when, body, model = BENCH[name]
    w(root / ".claude/agents" / f"{name}.md", f"""
    ---
    name: {name}
    description: >
      DORMANT bench role — activated by the scrum-master only when a milestone needs it.
      {desc} Activate when: {when}
    tools: Read, Write, Edit, Bash, Glob, Grep
    model: {model}
    memory: project
    ---
    You are the {name}. Activated ONLY for stories in your domain; otherwise dormant. You REPLACE the
    generic builder for those stories and follow the SAME loop and rules. Before work: read CLAUDE.md,
    the active story's acceptance criteria, DECISIONS.
    {body}
    Loop: implement -> write tests for EACH criterion -> run to green -> lint -> hand to qa-adversary.
    You do NOT close your own story. Obey the design law (outcomes emerge, never faked) + safety rails
    (stop after 3 failed attempts, no nested agents, active story only). Cannot judge subjective
    quality — route feel/taste to the human. After work: append BUILD_LOG, update memory.
    """)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--config", help="JSON answers file (non-interactive)")
    p.add_argument("--emit-config", action="store_true", help="write blank answers file and exit")
    p.add_argument("--no-git", action="store_true", help="skip git init")
    p.add_argument("--out", default=".", help="parent dir to create the repo in")
    args = p.parse_args()

    if args.emit_config:
        blank = {k: d for k, _, d in QUESTIONS}
        Path("answers.json").write_text(json.dumps(blank, indent=2))
        print("Wrote answers.json — fill it in (plain words, no tech jargon needed),")
        print("then: python new-product.py --config answers.json")
        return

    interactive = not args.config
    cfg = json.loads(Path(args.config).read_text()) if args.config else {}
    if interactive:
        print("\n=== New product — just describe it in plain words ===")
        print("(No tech knowledge needed. The agent team translates the rest.)")
        print("(Answer one at a time. You'll get to fix anything before we save.)\n")
    ans = {k: ask(interactive, cfg, k, q, d) for k, q, d in QUESTIONS}

    # Interactive: play the answers back ONE field at a time and let the user fix any.
    # No wall of text — just a short list they can correct by number, or press Enter to accept.
    if interactive:
        while True:
            print("\n--- Here's what I heard (press Enter to confirm, or type a number to fix) ---")
            items = list(QUESTIONS)
            for i, (k, q, _) in enumerate(items, 1):
                val = ans[k] or "(blank)"
                print(f"  {i}. {q}\n     -> {val}")
            choice = input("\n  Number to fix, or Enter to confirm: ").strip()
            if not choice:
                break
            if choice.isdigit() and 1 <= int(choice) <= len(items):
                k, q, d = items[int(choice) - 1]
                ans[k] = input(f"  {q}: ").strip() or ans[k]
            else:
                print("  (didn't catch that — type a number or just press Enter)")

    root = Path(args.out) / ans["product_name"]
    if root.exists():
        print(f"ERROR: {root} already exists."); sys.exit(1)

    # Generator ships ALL bench roles present-but-dormant; the scrum-master activates the
    # right ones during translation. No technical choice asked of the human.
    bench = list(BENCH.keys())

    # ---- answers.json : ALWAYS saved (interactive or config) so inputs never vanish ----
    (root / "docs").mkdir(parents=True, exist_ok=True)
    (root / "docs" / "answers.json").write_text(
        json.dumps({k: ans[k] for k, _, _ in QUESTIONS}, indent=2), encoding="utf-8")

    # ---- INTAKE.md : the human's own plain words, untouched ----
    w(root / "docs/INTAKE.md", f"""
    # INTAKE — what the human said, in their own words
    > The scrum-master translates this into the technical plan on first run. Do not edit;
    > it's the source record of the original ask.

    **Name:** {ans['product_name']}

    **What it is:**
    {ans['what'] or '(not given)'}

    **Who it's for / what they do with it:**
    {ans['who_for'] or '(not given)'}

    **The one thing it must get right:**
    {ans['matters_most'] or '(not given)'}

    **What annoys them about existing tools / what they'd do differently:**
    {ans['annoys_you'] or '(not given)'}

    **What the human wants to judge themselves, by feel:**
    {ans['you_judge'] or '(not sure — scrum-master to infer)'}

    **Tech preference:**
    {ans['tech_pref'] or 'you decide'}
    """)

    # ---- CLAUDE.md : stubbed, scrum-master fills the technical fields from INTAKE ----
    w(root / "CLAUDE.md", f"""
    # CLAUDE.md — Project Constitution
    Loaded every session. Keep lean (<120 lines). Detail lives in `/docs`.

    ## What we are building
    {ans['what'] or '<from INTAKE>'}
    Full plain-language ask: `docs/INTAKE.md`. Full vision: `docs/PROJECT_CHARTER.md`.

    ## The thesis (the ONE thing that must be true)
    <<SCRUM-MASTER: fill from INTAKE "the one thing it must get right". One sentence.>>
    Everything else is decoration on top of this. Defend it.

    ## The design law (how we avoid faking it)
    <<SCRUM-MASTER: fill from INTAKE "what they'd do differently". The principle that keeps it honest.>>

    ## Stack
    <<SCRUM-MASTER: choose from INTAKE tech preference (or decide) + one-line reason. Record in DECISIONS.>>

    ## The hard boundary (read twice)
    Every agent may ONLY sign off on what is objectively verifiable (tests/checks).
    <<SCRUM-MASTER: list the objective checks here.>>
    No agent may judge: <<SCRUM-MASTER: list what the human judges by feel, from INTAKE.>>
    Those route to the human ONLY. When a question is subjective, all agents are blind. Stop and flag.

    ## How work flows (the loop)
    Per story: scrum-master writes acceptance criteria -> builder/specialist implements feature +
    test harness -> runs to green -> qa-adversary writes ADDITIONAL breaking tests -> failures
    return -> integrator reruns FULL suite -> scrum-master validates vs written criteria and closes.
    The author never self-certifies.

    ## Session start ritual (MANDATORY before any work)
    1. Read docs/PROJECT_CHARTER.md, docs/ROLES.md.
    2. Read docs/SPRINT_STATE.md — single source of truth.
    3. Read tail of docs/receipts/BUILD_LOG.md.
    4. State: "We are at <milestone>, story <id>, status <status>, last event <X>."
    5. Only then act. If state can't reconstruct, that's bug #1 — fix the state files.

    ## State discipline
    - Chat is volatile; the repo is durable. Anything that must survive = a file.
    - docs/receipts/* are APPEND-ONLY. Never edit history.
    - Settled calls live in docs/receipts/DECISIONS.md. Don't relitigate.
    - After every meaningful action: update SPRINT_STATE + append BUILD_LOG before ending turn.

    ## Agent safety rails (NON-NEGOTIABLE)
    - No agent spawns sub-agents that spawn agents. Max nesting depth = 1.
    - Every agent stops after 3 consecutive failed attempts and reports back.
    - An agent works ONLY the active story in SPRINT_STATE. No working ahead.
    - Prefer the lightest tool. Dormant roles stay dormant until a milestone needs them.

    ## Talking to the human
    The human is NOT technical and trusts the team — they will NOT review walls of text, so the
    burden is on US not to drift. Rules for every agent:
    - ASK, DON'T ASSUME. If you're unsure what the human wants and it matters, ask — never silently
      pick an interpretation. A wrong assumption the human nods through is worse than a small question.
    - Ask in plain everyday words, never jargon, tailored to how the human writes.
    - ONE question at a time. Confirm understanding in small one-sentence yes/no checks, never by
      asking them to review a big document.
    - When unclear, ask a smaller more concrete question rather than guessing.

    ## Roles & staffing
    Defined in `.claude/agents/`. Authority + active/dormant model: `docs/ROLES.md`.

    ## Commands
    - Run tests: <<SCRUM-MASTER: set for chosen stack>>
    - Lint/format check: <<SCRUM-MASTER: set for chosen stack>>
    """)

    w(root / "docs/PROJECT_CHARTER.md", f"""
    # PROJECT CHARTER  (scrum-master completes from docs/INTAKE.md on first run)

    ## Vision
    {ans['what'] or '<from INTAKE>'}
    For: {ans['who_for'] or '<from INTAKE>'}

    ## The thesis (the one thing that must be true)
    > <<SCRUM-MASTER: one sentence from INTAKE "the one thing it must get right".>>

    ## Why existing solutions fall short
    {ans['annoys_you'] or '<from INTAKE>'}

    ## The design law
    <<SCRUM-MASTER: the principle that keeps it honest, derived from the above.>>

    ## The objective / subjective boundary
    - Agents own (objective, verifiable): <<SCRUM-MASTER: list>>
    - Human owns (subjective, judged by feel): {ans['you_judge'] or '<<SCRUM-MASTER: infer>>'}
    Agents build & verify the bones. The human verifies the soul.

    ## Stack decision
    <<SCRUM-MASTER: stack + reason; record in DECISIONS.>>

    ## Definition of "ready for the human"
    A milestone is beta-ready when ALL its objective criteria are green AND the full prior suite
    still passes. The human is pinged ONLY then — never to debug or review code.
    """)

    w(root / "docs/BACKLOG.md", """
    # BACKLOG  (scrum-master completes from docs/INTAKE.md on first run)
    Acceptance criteria MUST be assertions a test/check can verify. Untestable -> human's job.
    Status: TODO · BUILDING · IN_QA · FAILED_QA · INTEGRATING · DONE

    ## EPIC M0 — Project & test scaffold (ALWAYS first)
    **M0.1** Skeleton + test/check runner.
    - AC1: Test command runs and reports cleanly with zero tests.
    - AC2: A deliberately failing check is reported as FAILED (prove the harness detects failure).
    - AC3: Lint/format check passes.

    ## EPIC M1 — <<SCRUM-MASTER: the first real capability — the riskiest heart of the thesis>>
    **M1.1** <<story>>
    - AC1: <<testable assertion>>

    ## EPIC M2+ — <<SCRUM-MASTER: lay out the rest from INTAKE>>

    ## Parked (do NOT build yet)
    <<SCRUM-MASTER: everything that is decoration until the core is proven>>
    """)

    w(root / "docs/SPRINT_STATE.md", f"""
    # SPRINT_STATE.md — LIVE LEDGER (single source of truth)
    > Resume ritual reconstructs the project from THIS file + BUILD_LOG tail.
    > Update BEFORE ending any turn. State-then-stop.

    ## Current position
    - Active epic:   (pre-M0) intake translation
    - Active story:  —
    - Status:        TRANSLATING_INTAKE
    - Owner role:    scrum-master
    - Blocked on human?:  NO

    ## Active roster
    - Core: scrum-master, builder, qa-adversary, integrator
    - Bench available (dormant): {', '.join(bench)}
    - Bench activated: (scrum-master decides during translation)

    ## Last event
    Repo scaffolded from plain-language intake (docs/INTAKE.md). Awaiting scrum-master translation
    into thesis / design law / objective-subjective / stack / milestones.

    ## Next action
    scrum-master: run FIRST-RUN TRANSLATION. Fill the <<...>> stubs in CLAUDE.md, PROJECT_CHARTER,
    BACKLOG, ROLES from docs/INTAKE.md. Ask the human plain follow-ups ONLY for what can't be
    inferred. Then set status M0.1 TODO and proceed.

    ## Milestone board
    - [ ] (translate intake)  <- WE ARE HERE
    - [ ] M0  Scaffold + test harness
    - [ ] M1  <<from INTAKE>>

    ## Ready-for-beta queue
    (empty)

    ## blocked_on_human
    (none)
    """)

    w(root / "docs/ROLES.md", """
    # ROLES — Team, Authority & Self-Staffing
    Core rule: the author never certifies their own work. Building and accepting are separate.

    ## ACTIVE / DORMANT model
    All bench roles ship present-but-DORMANT. The scrum-master activates one only when the active
    milestone needs it (reason recorded in DECISIONS), and proposes a NEW role if none fit.
    Capacity grows from need, never speculation.

    ## PERMANENT CORE (always active)
    - scrum-master — owns path + staffing; translates intake; opens/closes stories; resume ritual.
    - builder — implements active story + its tests; replaced by a specialist in their domain.
    - qa-adversary — tries to break it; tests vs written criteria; logs every attempt.
    - integrator — reruns full suite; guards against regression.

    ## ON-CALL BENCH (dormant until needed)
    frontend-engineer, backend-engineer, data-engineer, network-engineer, security-reviewer,
    performance-engineer, business-analyst, devops-engineer, docs-writer.
    Each .claude/agents/*.md says when it activates. The scrum-master picks per milestone.

    ## Propose a NEW role
    If a milestone needs a skill no role covers: justify in DECISIONS, draft .claude/agents/<role>.md
    (standard frontmatter + authority rules + safety rails), activate for that milestone, dormant after.

    ## The human (NOT an agent)
    Beta-tester / taste-owner, and NOT technical. Pinged only when a milestone is objectively green +
    regression-clean. Judges by feel. Never asked to code, design, review logic, debug, or use jargon.

    ## Escalation
    Any agent hitting a subjective question STOPS and routes to the human via blocked_on_human,
    phrased in plain everyday language.
    """)

    w(root / "docs/receipts/BUILD_LOG.md", """
    # BUILD_LOG.md — APPEND-ONLY. Never edit prior entries.
    Format: [timestamp] <role> — <what happened>
    ---
    [init] generator — Repo scaffolded from plain-language intake. Status: TRANSLATING_INTAKE.
    Next: scrum-master translates docs/INTAKE.md into the technical plan.
    """)
    w(root / "docs/receipts/QA_LOG.md", """
    # QA_LOG.md — APPEND-ONLY. Every adversarial attempt, pass AND fail.
    Format: [timestamp] story <id> — target: <what> — result: PASS/FAIL — note
    ---
    (no QA runs yet)
    """)
    w(root / "docs/receipts/DECISIONS.md", """
    # DECISIONS.md — Settled questions. Do NOT relitigate. APPEND-ONLY.
    Format: [date] DECISION: <what> — RATIONALE: <why> — STATUS: settled
    ---
    [init] DECISION: Core roles always-on, bench activated only by milestone need.
    RATIONALE: More agents -> cost, drift, runaway-loop risk; grow capacity from concrete need.
    STATUS: settled.
    [init] DECISION: Human is non-technical; product defined via plain-language INTAKE, translated
    by the scrum-master. RATIONALE: don't force jargon onto the user. STATUS: settled.
    """)

    core_agent_files(root)
    for b in bench:
        bench_agent_file(root, b)

    w(root / "README.md", f"""
    # {ans['product_name']}
    {ans['what']}

    Built by an autonomous Claude Code agent team. You describe it in plain words
    (docs/INTAKE.md); the team translates and builds. You are the beta-tester / taste-owner.
    Start: open Claude Code here and paste the prompt from KICKOFF.md.
    """)
    w(root / "KICKOFF.md", """
    # Kickoff prompt — paste into Claude Code opened in this folder

    Read CLAUDE.md, then invoke the scrum-master subagent. We just started: SPRINT_STATE says
    status TRANSLATING_INTAKE. Run the FIRST-RUN TRANSLATION — read docs/INTAKE.md (my plain-words
    description) and turn it into the thesis, design law, objective/subjective split, stack, and
    the M1 milestone with testable criteria, filling the <<...>> stubs in the docs. I'm not
    technical, so if you need anything from me, ask in plain everyday language, not jargon. Once
    translated, scaffold the project + test runner (prove it can detect a real failure), then run
    the normal loop and don't ping me until there's something to look at. Obey the safety rails.
    """)
    w(root / ".gitignore", """
    node_modules/
    __pycache__/
    .env
    *.log
    dist/
    build/
    .DS_Store
    """)
    (root / "src").mkdir(exist_ok=True)
    (root / "tests").mkdir(exist_ok=True)
    w(root / "src/.gitkeep", "")
    w(root / "tests/.gitkeep", "")

    if not args.no_git:
        try:
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            ic = subprocess.run(["git", "config", "user.email"], cwd=root, capture_output=True, text=True)
            if not ic.stdout.strip():
                subprocess.run(["git", "config", "user.email", "agent-team@local"], cwd=root)
                subprocess.run(["git", "config", "user.name", "agent-team"], cwd=root)
            subprocess.run(["git", "add", "-A"], cwd=root, check=True)
            subprocess.run(["git", "commit", "-q", "-m", "scaffold: agent team + intake"], cwd=root, check=True)
            git_note = "git initialized with first commit."
        except Exception as e:
            git_note = f"git skipped ({e}). Run 'git init' yourself."
    else:
        git_note = "git skipped (--no-git)."

    print(f"\n[+] Created {root}")
    print(f"[+] {git_note}")
    print(textwrap.dedent(f"""
    Next:
      1. cd {ans['product_name']}
      2. Open Claude Code here (claude --dangerously-skip-permissions if non-sensitive).
      3. Paste the prompt from KICKOFF.md. The scrum-master will translate your plain
         description into the technical plan and ask you (in plain words) only what it needs.
    """))

if __name__ == "__main__":
    main()
