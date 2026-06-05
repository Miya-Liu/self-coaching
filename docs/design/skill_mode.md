# skill mode

The **host agent** is both **executor** and **subject**: it loads `modes/skill/`, runs experiments locally, and evolves itself using the gated loop in root `README.md` (Loading Gate → Deploy Gate → Experience).

Overview: [architecture.md](architecture.md). Naming: [README.md](README.md#canonical-naming).

## Purpose in this mode

Coach the agent on *how* to learn from real work: encode durable memory and skills (**self-learning**), generate stress data (**self-play**), measure performance (**self-evaluation**), tune when needed (**self-tuning**), and merge only after human approval. Full train logs stay on disk (`logs/`), not in context.

## Submodules

| Submodule | Path | When to load |
|-----------|------|--------------|
| **self-learning** | `self-learning/SKILL.md` | Corrections, bugs, preferences → memory/skills/eval cases |
| **self-play** | `self-play/SKILL.md` | Generate or curate tasks and trajectories |
| **self-evaluation** | `self-evaluation/SKILL.md` | Run evals, interpret reports, promotion gates |
| **self-tuning** | `self-tuning/SKILL.md` | AERL SFT/GRPO after curation and eval discipline |

Load umbrella `modes/skill/SKILL.md` first. Pipeline order and evolution-engine automation: [pipelines.md](pipelines.md).

## Deploy profile

| Aspect | Typical setup |
|--------|----------------|
| Primary target | T1 — `modes/skill/` (+ repo `scripts/` when cloned whole) |
| Coaching root | Repo or project root (`experience/`, `.self-coaching/`) |
| Observation | Hooks, user corrections, local logs, optional orchestrator |
| Deploy improvements | Merge into host repo; user approval in session |
| Config template | `configs/skill.example.yaml` |
| Host adapters | `modes/skill/adapters/` |

## How it runs

### 1. Policy-driven loop

Follow `SKILL.md`: worktree experiments (`AUTORESEARCH_ROOT`), redirect training to `logs/`, write **Experience**, request authorization before merge.

### 2. Hooks (optional)

`references/hooks-setup.md` — experiment command pattern, error/learnings tail. Not required by `SKILL.md`.

### 3. Evolution engine (optional)

Semi-automated eval and improve-on-drop from repo root:

```bash
python -m services.orchestrator record-eval --coaching-root . --agent-id my-host ...
python -m services.orchestrator check-drop --metrics-dir ./.self-coaching/metrics
python -m services.orchestrator run --coaching-root . --run-dir ./runs/... --agent-id my-host
```

`ORCHESTRATOR_TRANSPORT=module` (default); `ORCHESTRATOR_EVAL_BACKEND=mock` or `agentevals`.

## Worktree experiment model

- Integration line: trainer repo `main` (`AUTORESEARCH_ROOT`).
- Experiment line: `worktrees/<id>/`, branch `experiment/<id>`.
- Summaries: `experience/`; full logs: `logs/<id>.log`.

## Guides

- [deploy-skill-pack.md](../guides/deploy-skill-pack.md)
- [runbook.md](../guides/runbook.md)

## Related

- [coach_mode.md](coach_mode.md) — external supervision
- [evaluators.md](evaluators.md) — metrics when automating
