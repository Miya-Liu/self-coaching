# Documentation

Index for the self-coaching repository. Start with the **active** T1 path, then use design/project docs when adopting T2/T3.

## Start here (T1 — skill pack)

| Doc | Description |
|-----|-------------|
| [guides/deploy-skill-pack.md](guides/deploy-skill-pack.md) | **Active deploy target** — install, verify, upgrade |
| [guides/runbook.md](guides/runbook.md) | Day-to-day commands (worktrees, training, experience) |
| [design/architecture.md](design/architecture.md) | Control boundaries and data flow |

## Deployment (T1 / T2 / T3)

| Doc | Description |
|-----|-------------|
| [guides/deploy-overview.md](guides/deploy-overview.md) | Index: skill pack, coaching API, orchestrator |
| [guides/deploy-skill-pack.md](guides/deploy-skill-pack.md) | T1 detail |
| [guides/deploy-overview.md#t2--coaching-api](guides/deploy-overview.md#t2--coaching-api) | T2 — HTTP mock / future adapters |
| [guides/deploy-overview.md#t3--self-improving-pipeline](guides/deploy-overview.md#t3--self-improving-pipeline) | T3 — orchestrator CLI |

## Design and pipeline

| Doc | Description |
|-----|-------------|
| [design/pipeline.md](design/pipeline.md) | Self-improving loop (eval → drop → improve → gates → deploy) |
| [design/architecture.md](design/architecture.md) | Repo structure and gates |

## Project tracking

| Doc | Description |
|-----|-------------|
| [project/roadmap.md](project/roadmap.md) | Milestones M0–M4, deploy targets T1–T3 |
| [project/progress.md](project/progress.md) | Component status vs roadmap |
| [project/integration-plan.md](project/integration-plan.md) | Production agent + AgentEvals adapters |
| [project/changelog-skills.md](project/changelog-skills.md) | Skill pack version history |

## Integration (planned artifacts)

| Path | Description |
|------|-------------|
| [integration/README.md](integration/README.md) | OpenAPI snapshots and field mapping (Phase 0) |
| [integration/api-snapshots/](integration/api-snapshots/) | Exported OpenAPI JSON (when captured) |

## Repo root (outside `docs/`)

| Path | Description |
|------|-------------|
| `upstream/README.md` | Clone autoresearch externally (`AUTORESEARCH_ROOT`) |
| `SKILL.md` | Full orchestration policy |
| `DESCRIPTION.md` | Atomic skills index |
| `mock-services/contracts/openapi.yaml` | Coaching HTTP contract |
| `services/orchestrator/` | Improvement orchestrator (M1) |
