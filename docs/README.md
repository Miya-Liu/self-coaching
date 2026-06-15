# Documentation

**Self-coaching** helps agents evolve through **self-learning**, **self-play**, **self-evaluation**, and **self-tuning**, with gates and human approval. Two modes — **self-coaching** (host evolves itself) and **coach** (supervise external agents) — share the same evolution engine and integrations.

Naming: [design/README.md](design/README.md#canonical-naming). Start: [design/architecture.md](design/architecture.md).

## Design

| Doc | Topic |
|-----|--------|
| [design/architecture.md](design/architecture.md) | Purpose, gates, data flow, two modes |
| [design/self_coaching_mode.md](design/self_coaching_mode.md) | mode: self-coaching |
| [design/coach_mode.md](design/coach_mode.md) | mode: coach |
| [design/pipelines.md](design/pipelines.md) | Evolution engine + submodules |
| [design/evaluators.md](design/evaluators.md) | Metrics and promotion |
| [design/integrations/](design/integrations/) | AgentEvals, agent API, AERL |

## Guides

| Doc | Topic |
|-----|--------|
| [guides/install-as-hermes-skill.md](guides/install-as-hermes-skill.md) | Install as a Hermes skill |
| [guides/deploy-skill-pack.md](guides/deploy-skill-pack.md) | T1 — `modes/self-coaching/` |
| [guides/deploy-overview.md](guides/deploy-overview.md) | T1 / T2 / T3 |
| [guides/runbook.md](guides/runbook.md) | Day-to-day commands · [§ Self-coaching demo (mock loop)](guides/runbook.md#self-coaching-demo-mock-loop) |

## Project

| Doc | Topic |
|-----|--------|
| [project/roadmap.md](project/roadmap.md) | Milestones |
| [project/integration-plan.md](project/integration-plan.md) | Adapters (AgentEvals, agent API) |
| [project/progress.md](project/progress.md) | Status |
| [project/self-coaching-demo-pipeline-plan.md](project/self-coaching-demo-pipeline-plan.md) | Self-coaching loop demo (mock) |
| [project/self-learning-review-agent-plan.md](project/self-learning-review-agent-plan.md) | Self-learning review agent API (M2 draft) · [§11 tasks](project/self-learning-review-agent-plan.md#11-implementation-task-lists) |
| [project/self-tuning-trainer-api-plan.md](project/self-tuning-trainer-api-plan.md) | Self-tuning / AERL trainer API (M4 draft) · rollout proxy, reward schema, agent snapshot |
| [project/mock-to-real-migration.md](project/mock-to-real-migration.md) | Mock → live API migration (M0–M6); **M1 PASS** |
| [integration/README.md](integration/README.md) | OpenAPI snapshots, `mapping.md` |
