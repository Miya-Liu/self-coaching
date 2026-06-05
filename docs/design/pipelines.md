# Pipelines

The **evolution engine** loop and **pipeline stages** (learn → self-play → eval → train). Shared by [self-coaching mode](self_coaching_mode.md) and [coach mode](coach_mode.md).

Evaluators and gates: [evaluators.md](evaluators.md). Adapters: [integrations/](integrations/).

**Implementation:** `services/orchestrator/` (T3, M1 done). Operator commands: [deploy-overview.md](../guides/deploy-overview.md#t3--evolution-engine).

## Evolution engine loop

```text
1. Observe     trajectories, learning events, scheduled eval
2. Evaluate    → EvalMetrics                    [evaluators.md]
3. Drop detect → check-drop
4. Curate      failed / high-value trajectories
5. Improve     skill path OR model path
6. Gate        candidate eval (holdout) → promote | reject
7. Deploy      dry-run | canary | activate      [coach_mode.md]
```

### Executive summary

1. Subject agent runs tasks; trajectories land in coaching root or external store.
2. Auto-evaluation records quality, cost, latency, safety ([evaluators.md](evaluators.md)).
3. Drop detector triggers improvement only on real regression.
4. Curation selects failed / high-value trajectories → train/dev/holdout.
5. Engine routes to cheapest effective path (skill first, then model).
6. Candidate evaluated on holdout + regression suites.
7. Pass gates → deploy; else reject and keep artifacts.

## Pipeline stages

| Stage | Repo | T2 HTTP | Output |
|-------|------|---------|--------|
| **self-learning** | `modes/self-coaching/self-learning/` | `POST /learning/events` | Memory, skill patches, eval cases |
| **self-play** | `modes/self-coaching/self-play/` | `POST /self-play/generate` | Curated candidates, trajectories |
| **self-evaluation** | `modes/self-coaching/self-evaluation/` | `POST /eval/runs` | Reports under `.self-coaching/reports/` |
| **self-tuning** | `modes/self-coaching/self-tuning/` | `POST /training/runs` | Checkpoints, manifests, `logs/` |

Stages are invoked by:

- **Self-coaching mode:** host agent following `modes/self-coaching/SKILL.md` / phase skills, or `bash scripts/mock-run-all.sh`.
- **Coach mode / T3:** `SelfCoachingClient` from `services/orchestrator/run`.

OpenAPI contract: [integrations/coaching_api.md](integrations/coaching_api.md).

## Evolution engine (`services/orchestrator/`)

| Command | Role |
|---------|------|
| `record-eval` | Run eval, append `EvalMetrics` |
| `check-drop` | Compare latest metrics vs thresholds |
| `run` | Full improvement run → `improvement_run_manifest.json`, `decision.json`, `deploy_manifest.json` |

Calls `SelfCoachingClient` (`module` or `http` transport). Eval backend: `mock` | `agentevals`.

## Improvement paths

### Skill learning path

- Updates skills, prompts, tool instructions, few-shot examples.
- Best for procedural failures, wrong tools, format errors, sparse failures.
- Cheapest path — try first when `prefer_skill_first: true`.

### Model training path

- SFT / LoRA / GRPO via AERL pipelines.
- Best for repeated capability failures with enough curated data.
- See [integrations/aerl.md](integrations/aerl.md).

### Routing rule of thumb

| Data volume | Prefer |
|-------------|--------|
| &lt; 100 good examples | Skill / prompt learning |
| 100–1,000 | DSPy / few-shot / small LoRA |
| 1,000+ | Model tuning |

## Data curation policy

Curate for **quality**, not volume.

**Include:** failed trajectories with clear expected behavior; corrections; high-confidence successes; hard negatives; impacted task slices.

**Exclude:** secrets / PII; ambiguous unlabeled tasks; duplicates; holdout leakage; unverified self-judgments.

**Split:** train 70% · dev 15% · holdout 15% · plus frozen regression suite (never trained on).

## Trajectory store

MVP: filesystem JSONL under `.self-coaching/events/` or `run_dir/data/`.

Record: prompt, context, tool calls, outputs, final answer, evaluator feedback, redaction metadata, task tags.

Coach mode: export via production agent API ([integrations/production_agent.md](integrations/production_agent.md)).

## Minimal external script interface

Black-box commands behind the orchestrator:

- CLI flags + environment variables in.
- Artifacts + summary JSON out.
- Exit 0 = success.

Example `pipeline.yaml` hooks (org-specific):

```yaml
commands:
  current_eval: "python scripts/evaluate_agent.py --split canary --out {run_dir}/current_eval.json"
  collect: "python scripts/collect_trajectories.py --since 7d --out {run_dir}/trajectories.jsonl"
  curate: "python scripts/curate_data.py --input {run_dir}/trajectories.jsonl --out-dir {run_dir}/data"
  learn_skills: "python scripts/learn_skills.py --data {run_dir}/data --out-dir {run_dir}/skills"
  train_model: "python scripts/train_model.py --data {run_dir}/data --out-dir {run_dir}/model"
  candidate_eval: "python scripts/evaluate_agent.py --candidate {candidate_ref} --split holdout --out {run_dir}/candidate_eval.json"
  deploy: "python scripts/deploy_candidate.py --candidate {candidate_ref} --canary 0.05"
```

## Implementation phases

| Phase | Focus | Exit criterion |
|-------|-------|----------------|
| 1 | Loop without real training | Drop → improvement run dir + reports |
| 2 | Real skill learning | Target slice improves; holdout holds |
| 3 | Model tuning | Candidate beats baseline + safety gates |
| 4 | Canary deploy | Promote and rollback safely |

Roadmap alignment: [roadmap.md](../project/roadmap.md) M1–M4.

## Why this stays small

- Event-driven: train only after eval detects a real drop.
- Existing stacks plug in via adapters — no MLOps platform required.
- One artifact contract (`EvalMetrics`, run directories).
- Explicit safety and cost gates.

## Related

- [evaluators.md](evaluators.md)
- [architecture.md](architecture.md)
- [integrations/](integrations/)
