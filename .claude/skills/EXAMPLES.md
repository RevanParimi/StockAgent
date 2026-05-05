# EXAMPLES.md

Sanity-check that the bundle is actually triggering the right skills. Try these prompts in Claude Code; the skills loaded should match the "Expected" column.

If a request loads the wrong skills (or none), the description in the relevant `SKILL.md` needs sharpening. Edit the description, not the body.

## Routine work

| Prompt | Expected skills |
|---|---|
| "Refactor `signals/momentum.py` to extract the EMA calc into a util" | software-engineer |
| "Add a unit test for the FII flow parser" | software-engineer |
| "Why is the options-chain endpoint timing out in prod?" | support-engineer, devops-engineer |
| "Design the schema for storing tick-level OI data" | system-design-engineer, market-domain |
| "Write the system prompt for the earnings-summary agent" | ai-engineer, market-domain |
| "Build a backtest harness for the OI-buildup signal" | signal-engineering, software-engineer |
| "Should we use Postgres or TimescaleDB for tick data?" | system-design-engineer |
| "The momentum signal is underperforming live vs backtest — investigate" | support-engineer, signal-engineering |
| "Set up canary deploys for the inference service" | devops-engineer |

## Decisions (meta skill should fire)

| Prompt | Expected behavior |
|---|---|
| "We're going with Claude Opus for the rationale generator" | meta updates `PROJECT.md → llm_provider`, logs decision, then proceeds |
| "Decided to drop commodities from v1 scope" | meta updates `PROJECT.md → asset scope`, moves item to descoped, logs decision |
| "From now on, every prompt change needs an eval before merge" | meta appends rule to `ai-engineer/SKILL.md`, logs decision |
| "What's still TBD?" | meta greps for `<TBD>` across the bundle and lists open items |
| "Show me what we've decided so far" | meta reads the Key decisions log from `PROJECT.md` |

## Cross-role requests (multiple skills should compose)

| Prompt | Expected skills |
|---|---|
| "Add a new agent that summarizes RBI policy decisions and integrates with the signal aggregator" | ai-engineer, market-domain, signal-engineering, software-engineer |
| "Production incident: the signal scores are off for Bank Nifty after today's expiry" | support-engineer, signal-engineering, market-domain |
| "Architect the recommendation pipeline end-to-end" | system-design-engineer, ai-engineer, signal-engineering, market-domain |

## Things that should NOT trigger any domain skill

| Prompt | Expected skills |
|---|---|
| "Fix this off-by-one in the date parser" | software-engineer only |
| "Why is CI taking 20 minutes?" | devops-engineer only |
| "Should we split the auth service from the user service?" | system-design-engineer only |

If domain skills load on these, the description trigger keywords are too broad — tighten them.
