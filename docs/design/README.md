# Design documentation

## Naming

| Layer | Name | Path |
|-------|------|------|
| Repository | self-coaching | this repo |
| Deploy mode | **self-coaching** | `modes/self-coaching/` |
| Deploy mode | **coach** | `modes/coach/` |
| Submodule | self-learning / self-play / self-evaluation / self-tuning | under `modes/self-coaching/` |

## Glossary

**“Mode” is overloaded** — use the matching term:

| Term | Meaning |
|------|---------|
| **Deploy mode** | self-coaching (host evolves itself) vs coach (supervises external agents) |
| **Loop execution mode** | autonomous / scheduler / manual — who starts each evolution tick |
| **Service mode** | `LOOP_SERVICE_MODE` — mock-module vs mock-http vs live backends |
| **Worktree autonomy** | iterate inside worktree without merge approval |

**Milestone families** (do not conflate): [roadmap](../project/roadmap.md) M0–M5 (deploy) · [migration](../project/mock-to-real-migration.md) M0–M6 (loop adapters) · [integration plan](../project/integration-plan.md) Phase 0–5 (adapter work).

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
