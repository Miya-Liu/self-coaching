# Architecture

## Role

**Self-coaching** is a **portable, agent-agnostic** package (not tied to one IDE): the **policy** in `modes/skill/SKILL.md` and **Experience** on disk are the contract. A **subject agent** evolves skills and optionally a **model** in a **git** repo by passing a **Loading Gate**, using a **Data Pool** and **Local Model**, running an experiment loop behind a **Deploy Gate** (worktree + approval), and writing **Results** to `experience/` while full train output goes to `logs/`.

The same **submodules** and **evolution engine** deploy in two **modes** ? only executor, subject, and coaching-root layout differ:

| Mode | Executor | Subject | Path |
|------|----------|---------|------|
| **skill** | Host agent | Host agent | `modes/skill/` |
| **coach** | Coach service / scheduler | External agents | `modes/coach/` + T2/T3 |

Detail: [skill_mode.md](skill_mode.md), [coach_mode.md](coach_mode.md). Naming: [README.md](README.md#canonical-naming).

The canonical end-to-end sequence is the Mermaid block in root `README.md` (Loading Gate, Performance, Data Pool, Local Model, Deploy Gate, Trainer, Results).

## Repository layout

```text
self-coaching/
??? modes/
?   ??? skill/                    # mode: skill (T1)
?   ?   ??? SKILL.md              # umbrella (name: self-coaching)
?   ?   ??? self-learning/
?   ?   ??? self-play/
?   ?   ??? self-evaluation/
?   ?   ??? self-tuning/
?   ?   ??? adapters/
?   ??? coach/                    # mode: coach (shell, planned)
??? configs/
??? services/
?   ??? orchestrator/             # evolution engine (T3)
?   ??? adapters/
??? scripts/
??? mock-services/                # Coaching API (T2)
??? docs/
??? experience/
```

## Components

1. **Policy** ? `modes/skill/SKILL.md` (worktree workflow, when to train/stop, merge gate, Experience paths).
2. **Submodules** ? `self-learning`, `self-play`, `self-evaluation`, `self-tuning` under `modes/skill/`.
3. **Evolution engine** ? `services/orchestrator/` (T3): `record-eval`, `check-drop`, `run`; calls `SelfCoachingClient` and adapters.
4. **Target repo** ? default: external [autoresearch](https://github.com/karpathy/autoresearch) clone (`AUTORESEARCH_ROOT`); `main` is integration line.
5. **Experiment line** ? `worktrees/<id>/`, branch `experiment/<id>`.
6. **Execution logs** ? `logs/<id>.log` (full train stdout/stderr; parse in small chunks).
7. **AERL pipelines** ? `modes/skill/self-tuning/pipelines/` + `services/.env` (`TRAINER_BASE_URL`, optional `AERL_ROOT`).
8. **Experience** ? `experience/EXPERIMENT_LOG.md`, `ERROR.md`, `LEARNINGS.md`; optional `RUN_SUMMARY.json`.
9. **Coaching root** ? `{root}/experience/` + `{root}/.self-coaching/` (metrics, curated data, eval reports).
10. **Hooks** ? `scripts/hook-*.sh` + `references/hooks-setup.md` (skill mode).
11. **Coach shell** (planned) ? `modes/coach/` supervision registry, scheduler, optional LLM proxy.

## Shared core (both modes)

```text
                    ???????????????????????????????????????
                    ?  Evolution engine (T3)              ?
                    ?  services/orchestrator              ?
                    ???????????????????????????????????????
                                      ?
              ?????????????????????????????????????????????????
              ?                       ?                       ?
     Submodules (modes/skill/*)  Coaching API (T2)      Adapters
              ?                       ?              (integrations/)
              ?????????????????????????????????????????????????
                                      ?
              ?????????????????????????????????????????????????
              ?                                               ?
         mode: skill                                    mode: coach
```

| Submodule | Purpose | T2 HTTP |
|-----------|---------|---------|
| **self-learning** | Memory, skills, eval cases | `POST /learning/events` |
| **self-play** | Tasks, trajectories | `POST /self-play/generate` |
| **self-evaluation** | Benchmarks, gates | `POST /eval/runs` |
| **self-tuning** | SFT/GRPO (AERL) | `POST /training/runs` |

**Rule:** one evolution engine, one `SelfCoachingClient`, many adapters (AgentEvals, production agent API, AERL) ? see [integrations/](integrations/).

## Data flow

Sequence diagram in root `README.md`. Participants: **Human, Agent, Loading Gate, Performance, Data Pool, Local Model, Deploy Gate, Trainer, Results**.

```mermaid
sequenceDiagram
    autonumber
    participant U as Human
    participant A as Agent
    participant G as Loading Gate
    participant B as Performance
    participant C as Data Pool
    participant M as Local Model
    participant D as Deploy Gate
    participant T as Trainer
    participant X as Results

    U->>A: Enable self-coaching
    A->>G: Ensure Opening Gate
    G->>B: Review performance
    B->>G: Needs improvement
    G->>C: Load training data
    C->>M: Load model checkpoint
    G->>A: Experiment Ready
    A->>D: Create experiment + worktree
    loop Experiment iterations
        A->>T: Edit in worktree; run train
        T->>A: Results / errors
    end
    A->>U: Request authorization
    alt Approve
        A->>M: Replace local model
        A->>C: Update data
    end
```

## Conceptual to concrete mapping

| Concept | Meaning | Default pack |
|---------|---------|----------------|
| Loading Gate | Preconditions to train (deps, data/cache, checkpoints). | `uv sync`, `prepare.py`, checkpoint paths. |
| Performance | Metric improved vs baseline / best. | Parse `logs/<id>.log`; guardrails in `SKILL.md`. |
| Data Pool | Training/val sources: caches, dialogue-derived corpora, **self-play** outputs. | `~/.cache/autoresearch/` + curated paths. |
| Local Model | Admin-selected checkpoint before run. | Not mutated on `main` until merge approval. |
| Deploy Gate | Experiment isolation + promotion policy. | `experiment/<id>`, `worktrees/<id>/`; human decision to merge. |
| Trainer | Executes experiment run. | `run-once.sh` or AERL `run-pipeline.sh` / `self-tuning/pipelines/`. |
| Trainer feedback | Outcomes/errors to agent; raw log on disk. | Agent reads summary; full output in `logs/<id>.log`. |
| Results | Agent-resolved outcomes and learnings. | `experience/*.md`; `.self-coaching/` artifacts. |

## Evolution engine loop (coach + optional skill automation)

Observe ? evaluate ([evaluators.md](evaluators.md)) ? drop detect ? route (**self-learning** / **self-tuning**) ? candidate eval ? deploy gate. Detail: [pipelines.md](pipelines.md).

## Control boundaries

| Boundary | Location |
|----------|----------|
| Trainer integration line | `AUTORESEARCH_ROOT` on `main` |
| Experiment line | `worktrees/<experiment_id>`, `experiment/<id>` |
| Execution logs | `logs/<id>.log` |
| Experience | `experience/*.md` |
| Coaching artifacts | `.self-coaching/` under coaching root |

## Merge gate

- The agent may run experiment iterations autonomously **inside** the Deploy Gate (worktree only).
- The agent may not **replace local model** or **update data** on the integration path without explicit **human** authorization (merge into `AUTORESEARCH_ROOT` `main`, or swap promoted weights).
- Coach-mode production deploy (agent API activate/rollback) uses the same gate ? [coach_mode.md](coach_mode.md).

## Combined deployments

- **coach** supervises production external agents (scheduled eval, central improvement runs).
- **skill** installs `modes/skill/` in dev workspaces for local iteration before coach promotes.

Same submodules, `SKILL_PACK_VERSION`, OpenAPI contract, and evolution engine.

## Related

- [skill_mode.md](skill_mode.md) ? [coach_mode.md](coach_mode.md)
- [pipelines.md](pipelines.md) ? [evaluators.md](evaluators.md) ? [integrations/](integrations/)
