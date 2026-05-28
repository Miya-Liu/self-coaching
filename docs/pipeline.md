# Self-Improving Agent Pipeline

Goal: build a simple, feasible pipeline that detects agent performance drops, curates high-signal experience, improves the agent through skill learning or model tuning, validates the candidate, and deploys safely.

The design intentionally treats your existing evaluation, data curation, training, and deployment scripts as black-box commands. That keeps the first version small and useful instead of becoming a full MLOps platform.

**Implementation status:** Milestone 1 orchestrator lives in [`services/orchestrator/`](../services/orchestrator/). See [`roadmap.md`](roadmap.md), [`progress.md`](progress.md), and [`production-deployment.md`](production-deployment.md).

Diagram: `docs/self-improving-agent-pipeline-diagram.html` (optional; not required to run M1)

## Executive summary

The loop is:

1. Production agent runs tasks and stores trajectories.
2. Auto-evaluation periodically checks quality, cost, latency, and safety metrics.
3. A drop detector triggers improvement only when performance crosses a threshold.
4. A curation agent selects failed/high-value trajectories and creates clean train/dev/holdout data.
5. The orchestrator chooses the cheapest improvement path:
   - skill/prompt update first when the failure is procedural or instruction-related;
   - model fine-tuning when there is enough high-quality data and the failure is model-capability-related.
6. Candidate is evaluated on holdout and regression suites.
7. If it passes gates, deploy to canary, monitor, then promote; otherwise reject and keep artifacts for analysis.

## MVP architecture

### Components

- Production Agent
  - The serving agent used by real users or downstream systems.
  - Emits trajectories: prompt, context, tool calls, tool outputs, final answer, evaluator feedback, metadata.

- Trajectory Store
  - Minimal MVP: filesystem or database table.
  - Recommended record format: JSONL with redaction metadata and task tags.
  - Later upgrade: object store + vector index + metadata DB.

- Auto-Evaluation Service
  - Runs scheduled/canary evaluations.
  - Produces a small JSON contract:

```json
{
  "score": 0.78,
  "baseline_score": 0.86,
  "cost_per_task": 0.014,
  "latency_p95_ms": 8200,
  "safety_pass_rate": 0.99,
  "task_scores": {
    "tool_use": 0.72,
    "reasoning": 0.80,
    "format_following": 0.91
  }
}
```

- Drop Detector
  - Triggers only when performance degradation is real, e.g.:
    - score drops by more than 3 percentage points from baseline;
    - score is below an absolute minimum;
    - safety pass rate falls below threshold;
    - one critical task slice regresses.

- Improvement Orchestrator
  - Creates one improvement run directory.
  - Calls your scripts in order.
  - Records config, metrics, artifacts, and decisions.
  - Does not need to be complex; the scaffold is a ~single-file Python orchestrator.

- Curation Agent
  - Pulls failed trajectories and similar successful cases.
  - Removes PII/secrets.
  - Deduplicates near-identical examples.
  - Labels failure reasons.
  - Splits data into train/dev/holdout.

- Skill Learning Path
  - Fastest and cheapest path.
  - Updates agent skills, tool-use instructions, prompt templates, routing rules, or few-shot examples.
  - Good when failures are caused by missing procedure, wrong tool choice, formatting, or outdated runbooks.
  - Can use DSPy/prompt optimization if the agent behavior is expressed as prompt modules.

- Model Training Path
  - More expensive path.
  - Use when failures are capability or style issues that repeat across tasks and there is enough curated data.
  - Start with LoRA/SFT on curated successful trajectories or corrected failures.
  - Add preference optimization later if you have pairwise preferences.

- Candidate Evaluation
  - Must evaluate on data not used for training/skill optimization.
  - Compare against current production baseline.
  - Include regression, safety, cost, and latency gates.

- Deployment
  - Register candidate artifact.
  - Deploy to staging or canary.
  - Promote only after canary metrics pass.
  - Keep rollback pointer to previous production model/skill bundle.

## Why this is simple and efficient

- It is event-driven: training only starts when eval detects a real drop.
- It uses existing scripts: no need to replace your training stack.
- It has two improvement paths: cheap skill learning first, expensive model tuning second.
- It has one common artifact contract: JSON metrics and run folders.
- It keeps safety gates explicit and auditable.

## Recommended phases

### Phase 1: Wire the loop without training

Implement:

- evaluation JSON contract;
- drop detector;
- trajectory collection;
- curation command;
- skill-learning command;
- candidate evaluation command;
- dry-run deployment.

Success criterion:

- A fake or real eval drop creates an improvement run and produces a candidate report.

### Phase 2: Add real skill learning

Implement:

- failure clustering;
- skill/runbook patch generation;
- prompt optimization or DSPy optimization;
- regression tests for changed skills.

Success criterion:

- Skill update improves target slice without hurting holdout metrics.

### Phase 3: Add model tuning

Implement:

- curated SFT dataset builder;
- LoRA/SFT training command;
- model artifact registry;
- candidate evaluation against fixed holdout.

Success criterion:

- Candidate model beats production baseline by the required margin and passes safety gates.

### Phase 4: Add canary deployment

Implement:

- deploy to a small traffic slice;
- observe live eval metrics;
- auto-rollback on regressions;
- optional human approval for production promotion.

Success criterion:

- New skill/model bundle can be promoted and rolled back safely.

## Trigger policy

Start with conservative thresholds:

```yaml
thresholds:
  min_score: 0.80
  max_drop: 0.03
  min_candidate_improvement: 0.01
  min_safety_pass_rate: 0.995
  max_latency_p95_ms: 10000
  max_cost_per_task: 0.05
```

Trigger if:

- `score < min_score`, or
- `baseline_score - score >= max_drop`, or
- safety/cost/latency violates hard limits.

Promote candidate if:

- candidate score >= production score + min_candidate_improvement;
- candidate safety pass rate >= threshold;
- candidate cost and latency are within limits;
- no critical regression suite fails.

## Data curation policy

Curate for quality, not volume.

Include:

- failed trajectories with clear expected behavior;
- corrected outputs;
- high-confidence successful trajectories for imitation;
- hard negatives and edge cases;
- representative slices from impacted tasks.

Exclude:

- examples with secrets or unredacted PII;
- ambiguous tasks with no trusted label;
- duplicated conversations;
- examples used in final holdout evaluation;
- low-quality agent self-judgments with no verification.

Recommended split:

- train: 70%;
- dev: 15%;
- holdout: 15%;
- plus a frozen regression suite that is never trained on.

## Skill learning vs model tuning

Use skill learning when:

- the fix is procedural;
- the agent used the wrong tool;
- the prompt needs better constraints;
- output format is wrong;
- domain runbook changed;
- failures are sparse.

Use model tuning when:

- many examples share the same failure pattern;
- the agent lacks stable behavior despite good instructions;
- style, reasoning pattern, or tool-call policy needs to be internalized;
- you have enough curated high-quality examples;
- the improvement justifies training/deployment cost.

Rule of thumb:

- fewer than 100 good examples: prefer skill/prompt learning;
- 100-1,000 good examples: consider DSPy/few-shot/prompt optimization or small LoRA;
- 1,000+ good examples: model tuning becomes more attractive.

## Minimal interfaces

Every external script should follow this convention:

- Inputs through CLI flags and environment variables.
- Output artifacts written to a provided directory.
- Summary metrics written as JSON.
- Exit code 0 means success; non-zero means fail.

Example commands in `pipeline.yaml`:

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

## Implementation checklist

- [ ] Decide where trajectories are stored.
- [ ] Standardize the evaluation JSON schema.
- [ ] Add redaction before data reaches training.
- [ ] Create frozen holdout and regression suites.
- [ ] Configure thresholds in YAML.
- [ ] Run orchestrator in dry-run mode.
- [ ] Connect real evaluation command.
- [ ] Connect real curation command.
- [ ] Connect skill learning command.
- [ ] Connect model training command.
- [ ] Add artifact tracking with W&B/MLflow or filesystem.
- [ ] Add canary deployment and rollback.

## Pitch narrative for teammates

This pipeline gives us a practical self-improvement loop without overbuilding. We keep the agent accountable with continuous evaluation. When performance drops, we do not blindly retrain. We first collect and curate the relevant failures, then choose the cheapest effective fix: update skills/prompts when the problem is procedural, or fine-tune the model when the problem is repeated and data-backed. Every candidate must pass holdout, regression, safety, cost, and latency gates before canary deployment. The first version is just an orchestrator around our existing scripts, so it is feasible to build quickly and extend safely.
