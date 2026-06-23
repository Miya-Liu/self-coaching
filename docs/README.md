# Documentation

Portable skill pack + optional mock runtime for agent self-evolution (learn → play → evaluate → tune), with human approval before merge or promotion.

**Glossary** (overloaded “mode”, milestone families): [design/README.md](design/README.md#glossary)

## Start here

Pick one path — you do not need to read everything.

| I want to… | Read |
|------------|------|
| Install and use the skill pack | [guides/deploy-skill-pack.md](guides/deploy-skill-pack.md) → `modes/self-coaching/SKILL.md` |
| Run day-to-day commands / mock demo | [guides/runbook.md](guides/runbook.md) |
| Understand architecture (10 min) | [design/architecture.md](design/architecture.md) |
| Supervise external agents (coach mode) | [design/coach_mode.md](design/coach_mode.md) |
| See what is done vs planned | [project/progress.md](project/progress.md) |

## Guides

| Doc | Topic |
|-----|--------|
| [guides/deploy-skill-pack.md](guides/deploy-skill-pack.md) | T1 install (Hermes, clone, pack copy) |
| [guides/runbook.md](guides/runbook.md) | Worktrees, training, mock loop demo |
| [guides/deploy-overview.md](guides/deploy-overview.md) | T2 Coaching API + T3 evolution engine (optional) |

## Design

| Doc | Topic |
|-----|--------|
| [design/architecture.md](design/architecture.md) | Gates, components, two deploy modes |
| [design/overall.md](design/overall.md) | Full system diagram (loop + backends + data stores) |
| [design/self_coaching_mode.md](design/self_coaching_mode.md) | Host self-evolution · loop execution modes |
| [design/coach_mode.md](design/coach_mode.md) | Supervise external agents |
| [design/pipelines.md](design/pipelines.md) | Evolution engine stages |
| [design/evaluators.md](design/evaluators.md) | Metrics, drop detection, promotion |
| [design/integrations/](design/integrations/) | AgentEvals, agent API, Coaching API, AERL |

## Project status & plans

**Status (authoritative):** [project/progress.md](project/progress.md) · [project/roadmap.md](project/roadmap.md)

Implementation specs below are long on purpose — read only when building that phase:

| Doc | When to open |
|-----|----------------|
| [project/mock-to-real-migration.md](project/mock-to-real-migration.md) | Wiring mock → live loop adapters |
| [project/integration-plan.md](project/integration-plan.md) | Adapter implementation breakdown |
| [project/self-coaching-demo-pipeline-plan.md](project/self-coaching-demo-pipeline-plan.md) | Loop driver / completeness harness |
| [project/self-learning-review-agent-plan.md](project/self-learning-review-agent-plan.md) | Migration M2 learn/evolve API |
| [project/self-tuning-trainer-api-plan.md](project/self-tuning-trainer-api-plan.md) | Migration M4 trainer API |
| [project/mock-platform-design.md](project/mock-platform-design.md) | Mock Coaching API internals |
| [integration/README.md](integration/README.md) | OpenAPI snapshots, field mapping |
