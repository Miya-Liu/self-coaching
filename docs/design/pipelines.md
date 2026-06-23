# Pipelines

Evolution engine loop and pipeline stages. Shared by [self-coaching mode](self_coaching_mode.md) and [coach mode](coach_mode.md).

Evaluators: [evaluators.md](evaluators.md). Adapters: [integrations/](integrations/). Commands: [deploy-overview.md](../guides/deploy-overview.md#t3--evolution-engine).

## Evolution engine loop

```text
1. Observe → 2. Evaluate → 3. Drop detect → 4. Curate
5. Improve (skill OR model) → 6. Holdout gate → 7. Deploy
```

Loop execution modes (who triggers): [self_coaching_mode.md](self_coaching_mode.md#loop-execution-modes).

## Pipeline stages

| Stage | Path | T2 HTTP |
|-------|------|---------|
| self-learning | `modes/self-coaching/self-learning/` | `POST /learning/events` |
| self-questioning | `modes/self-coaching/self-questioning/` | `POST /self-questioning/generate` |
| self-evaluation | `modes/self-coaching/self-evaluation/` | `POST /eval/runs` |
| self-tuning | `modes/self-coaching/self-tuning/` | `POST /training/runs` |

Invoked by host agent (`SKILL.md`) or `services/orchestrator run` via `SelfCoachingClient`.

## Orchestrator CLI

| Command | Role |
|---------|------|
| `record-eval` | Append `EvalMetrics` |
| `check-drop` | Compare vs thresholds (exit 1 = drop) |
| `run` | Full improvement → `decision.json`, `deploy_manifest.json` |

## Improvement paths

| Path | Best for |
|------|----------|
| **Skill** | Procedural failures, wrong tools, sparse failures — try first |
| **Model** | Repeated capability failures with enough curated data (SFT/GRPO via AERL) |

Routing rule of thumb: &lt;100 examples → skill; 100–1k → few-shot/LoRA; 1k+ → model tuning.

## Data curation

Include: failed trajectories with clear expected behavior, corrections, hard negatives. Exclude: secrets, duplicates, holdout leakage. Split: train 70% · dev 15% · holdout 15%.

## Related

[evaluators.md](evaluators.md) · [architecture.md](architecture.md) · [roadmap.md](../project/roadmap.md)
