# Documentation

**Self-coaching** helps agents evolve through **self-learning**, **self-play**, **self-evaluation**, and **self-tuning**, with gates and human approval. Two modes — **skill** (host evolves itself) and **coach** (supervise external agents) — share the same evolution engine and integrations.

Naming: [design/README.md](design/README.md#canonical-naming). Start: [design/architecture.md](design/architecture.md).

## Design

| Doc | Topic |
|-----|--------|
| [design/architecture.md](design/architecture.md) | Purpose, gates, data flow, two modes |
| [design/skill_mode.md](design/skill_mode.md) | mode: skill |
| [design/coach_mode.md](design/coach_mode.md) | mode: coach |
| [design/pipelines.md](design/pipelines.md) | Evolution engine + submodules |
| [design/evaluators.md](design/evaluators.md) | Metrics and promotion |
| [design/integrations/](design/integrations/) | AgentEvals, agent API, AERL |

## Guides

| Doc | Topic |
|-----|--------|
| [guides/deploy-skill-pack.md](guides/deploy-skill-pack.md) | T1 — `modes/skill/` |
| [guides/deploy-overview.md](guides/deploy-overview.md) | T1 / T2 / T3 |
| [guides/runbook.md](guides/runbook.md) | Day-to-day commands |

## Project

| Doc | Topic |
|-----|--------|
| [project/roadmap.md](project/roadmap.md) | Milestones |
| [project/integration-plan.md](project/integration-plan.md) | Adapters (AgentEvals, agent API) |
| [project/progress.md](project/progress.md) | Status |
