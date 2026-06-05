# Design documentation

## Purpose

**Self-coaching** helps agents **evolve safely**: observe experience, improve through **self-learning** / **self-play** / **self-evaluation**, optionally **self-tuning**, and promote only after gates and human approval. The same building blocks serve:

- **skill** mode — the host agent coaches itself (`modes/skill/`).
- **coach** mode — a service supervises external agents (`modes/coach/` + evolution engine).

Not a single-product plugin: markdown skills, Bash scripts, optional HTTP (T2) and orchestrator (T3). External integrations (AgentEvals, production agent API, AERL) plug in via adapters — unchanged by naming.

## Canonical naming

| Layer | Name | Path |
|-------|------|------|
| Repository | **self-coaching** | this repo |
| Mode | **skill** | `modes/skill/` |
| Mode | **coach** | `modes/coach/` |
| Submodule | **self-learning** | `modes/skill/self-learning/` |
| Submodule | **self-play** | `modes/skill/self-play/` |
| Submodule | **self-evaluation** | `modes/skill/self-evaluation/` |
| Submodule | **self-tuning** | `modes/skill/self-tuning/` |

Umbrella skill ID: `self-coaching` (`modes/skill/SKILL.md`). Submodule IDs match folder names.

HTTP tags (`POST /learning/events`, etc.) are Coaching API contract names — they map to submodules above.

---

Start with **[architecture.md](architecture.md)** for gates, data flow, and shared core.

## Index

| Doc | Topic |
|-----|--------|
| [architecture.md](architecture.md) | Role, components, gates, mapping, two modes |
| [skill_mode.md](skill_mode.md) | Host self-evolution |
| [coach_mode.md](coach_mode.md) | Supervise external agents |
| [pipelines.md](pipelines.md) | Evolution engine, submodules, improvement paths |
| [evaluators.md](evaluators.md) | EvalMetrics, drop detection, promotion |
| [integrations/](integrations/) | AgentEvals, agent API, Coaching API, AERL |

## Related

| Doc | Topic |
|-----|--------|
| [guides/deploy-overview.md](../guides/deploy-overview.md) | Deploy T1 / T2 / T3 |
| [project/roadmap.md](../project/roadmap.md) | Milestones |
| [project/integration-plan.md](../project/integration-plan.md) | Adapter implementation |
