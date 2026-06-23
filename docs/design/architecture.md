# Architecture

## Role

**Self-coaching** is a portable, agent-agnostic package: **policy** in `modes/self-coaching/SKILL.md` + **Experience** on disk. A subject agent evolves skills and optionally a model via gated experiments (worktree isolation, human approval before merge).

| Mode | Executor | Subject | Path |
|------|----------|---------|------|
| **self-coaching** | Host agent | Host agent | `modes/self-coaching/` |
| **coach** | Coach service | External agents | `modes/coach/` + T2/T3 |

Loop **execution mode** (autonomous / scheduler / manual): [self_coaching_mode.md](self_coaching_mode.md#loop-execution-modes). End-to-end sequence diagram: root [README.md](../../README.md#workflow).

## Repository layout

```text
modes/self-coaching/     # T1 skill pack (SKILL.md + 4 submodules)
modes/coach/             # Coach shell (M5)
services/orchestrator/   # T3 evolution engine
services/adapters/       # AgentEvals, AERL, agent API
mock-services/           # T2 Coaching API mock
tools/                   # loop_completeness.py (C01–C18 audit harness)
scenarios/               # loop scenarios + env examples (full_loop.json, …)
scripts/  experience/  docs/
```

## Components

| # | Component | Location |
|---|-----------|----------|
| 1 | Policy | `modes/self-coaching/SKILL.md` |
| 2 | Submodules | self-learning, self-questioning, self-evaluation, self-tuning |
| 3 | Evolution engine | `services/orchestrator/` (`record-eval`, `check-drop`, `run`) |
| 4 | Coaching root | `{root}/experience/` + `{root}/.self-coaching/` |
| 5 | Experiment isolation | `worktrees/<id>/`, branch `experiment/<id>` |
| 6 | Execution logs | `logs/<id>.log` (full train output; not in agent context) |
| 7 | Trainer (optional) | AERL via `self-tuning/pipelines/` or mock loop |

**Rule:** one evolution engine, one `SelfCoachingClient`, many adapters — [integrations/](integrations/).

| Submodule | T2 HTTP |
|-----------|---------|
| self-learning | `POST /learning/events`, `/learning/evolve*` |
| self-questioning | `POST /self-questioning/generate` |
| self-evaluation | `POST /eval/runs` |
| self-tuning | `POST /training/runs` |

## Conceptual mapping

| Concept | Default pack |
|---------|----------------|
| Loading Gate | deps, `prepare.py`, checkpoint paths |
| Performance | metric from `logs/<id>.log` vs best |
| Data Pool | cache + curated / self-questioning data |
| Local Model | admin-chosen checkpoint; unchanged on `main` until approval |
| Deploy Gate | worktree isolation + human merge decision |
| Trainer | AERL pipelines or mock `train()` |
| Results | `experience/*.md`; `.self-coaching/` artifacts |

## Evolution engine (T3)

Observe → evaluate → drop detect → route (skill / model) → candidate eval → deploy gate. Detail: [pipelines.md](pipelines.md), [evaluators.md](evaluators.md).

## Merge gate

- Agent may iterate **inside** a worktree without approval (**worktree autonomy**).
- Replacing weights or merging to integration `main` requires **human** authorization.
- **Worktree autonomy ≠ loop execution autonomous** — see [glossary](README.md#glossary).

## Related

[self_coaching_mode.md](self_coaching_mode.md) · [coach_mode.md](coach_mode.md) · [pipelines.md](pipelines.md)
