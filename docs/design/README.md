# Design documentation

## Naming

| Layer | Name | Path |
|-------|------|------|
| Repository | self-coaching | this repo |
| Deploy mode | **self-coaching** | `modes/self-coaching/` |
| Deploy mode | **coach** | `modes/coach/` |
| Submodule | self-learning / self-questioning / self-evaluation / self-tuning | under `modes/self-coaching/` |

## Glossary

**“Mode” is overloaded** — use the matching term:

| Term | Meaning |
|------|---------|
| **Deploy mode** | self-coaching (host evolves itself) vs coach (supervises external agents) |
| **Loop execution mode** | autonomous / scheduler / manual — who starts each evolution tick |
| **Service mode** | `LOOP_SERVICE_MODE` — mock-module vs mock-http vs live backends |
| **Worktree autonomy** | iterate inside worktree without merge approval |

**Milestone families** (do not conflate):

| Family | Prefix | Range | Document |
|--------|--------|-------|----------|
| Deploy roadmap | **R0–R5** | deploy targets | [roadmap.md](../project/roadmap.md) |
| Mock→live migration | **Mig0–Mig6** | loop adapters | [mock-to-real-migration.md](../project/mock-to-real-migration.md) |
| Adapter integration | **Int0–Int5** | adapter work | [integration-plan.md](../project/integration-plan.md) |

> Legacy docs may still use bare "M0–M5" (roadmap), "M0–M6" (migration), or "Phase 0–5" (integration). When ambiguous, check which document you are reading.

**Service terminology:**

| Term | Canonical name | Notes |
|------|----------------|-------|
| Self-Questioning | `self-questioning` | Challenge-data generation from failures (upstream pipeline: "Self-Questioning Pipeline Service") |
| AERL | on-hold | Training platform — not yet deployed; code kept for future integration |
| Trainer | `trainer` / `self-tuning` | Functional concept for model training (env: `TRAINER_BASE_URL`) |
| `LOOP_SERVICE_MODE` | transport selector | Selects mock-module / mock-http / live — not a "mode" in the deploy-mode sense |

## Index

| Doc | Topic |
|-----|--------|
| [architecture.md](architecture.md) | Gates, components, shared core |
| [self_coaching_mode.md](self_coaching_mode.md) | Host self-evolution |
| [coach_mode.md](coach_mode.md) | External agent supervision |
| [pipelines.md](pipelines.md) | Evolution engine stages |
| [evaluators.md](evaluators.md) | Metrics and promotion |
| [integrations/](integrations/) | External adapters |

Start with **[architecture.md](architecture.md)**.
