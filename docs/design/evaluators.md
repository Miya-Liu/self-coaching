# Evaluators

How self-coaching **measures subject agent performance**, detects regressions, and gates promotion. Evaluators feed the **evolution engine** ([pipelines.md](pipelines.md)); both [self-coaching mode](self_coaching_mode.md) and [coach mode](coach_mode.md) use the same contracts.

## Evaluator roles

| Role | Purpose | Primary implementation |
|------|---------|------------------------|
| **Benchmark eval** | Scored suites for drop detection and holdout gates | **AgentEvals** (coach); mock (dev) |
| **Training metric** | Worktree / AERL run quality (`val_bpb`, `val_loss`) | `logs/<id>.log`, pipeline reports |
| **Self-judgment** | Agent critique during self-play / learn | Policy in phase skills — not a promotion gate alone |
| **Regression suite** | Frozen cases never used for training | AgentEvals suite or `.self-coaching/cases/` |

**Rule:** promotion decisions use **benchmark eval** on holdout (or equivalent), not raw training loss alone.

## EvalMetrics contract

Single JSON shape for auto-eval, drop detection, and promotion. Stored as JSONL:

```text
{coaching_root}/.self-coaching/metrics/eval_metrics.jsonl
```

Schema and normalizers: `services/orchestrator/eval_metrics.py`.

### Example record

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

### Key fields

| Field | Use |
|-------|-----|
| `score` | Primary metric for drop detection |
| `baseline_score` | Reference for delta triggers |
| `task_scores` | Per-slice regression checks |
| `safety_pass_rate` | Hard gate |
| `cost_per_task`, `latency_p95_ms` | Cost/latency gates |
| `agent_id`, `model_checkpoint_id`, `skill_bundle_version` | Lineage |
| `split` | `canary` (monitoring) vs `holdout` (promotion) |
| `raw` | Full backend payload (e.g. AgentEvals `RunDetail`) |

## Drop detector

CLI: `python -m services.orchestrator check-drop`

Triggers improvement when degradation is real — not on noise.

**Default thresholds** (`services/orchestrator/config/thresholds.json`):

```yaml
thresholds:
  min_score: 0.80
  max_drop: 0.03
  min_candidate_improvement: 0.01
  min_safety_pass_rate: 0.995
  max_latency_p95_ms: 10000
  max_cost_per_task: 0.05
```

**Trigger if:**

- `score < min_score`, or
- `baseline_score - score >= max_drop`, or
- safety / cost / latency violates hard limits.

Exit code `1` = drop detected (suitable for cron → `run`).

## Promotion gates

After improvement, **candidate eval** on holdout must pass before deploy:

**Promote if:**

- candidate `score` ≥ production `score` + `min_candidate_improvement`;
- candidate `safety_pass_rate` ≥ threshold;
- cost and latency within limits;
- no critical regression suite failure.

Outputs: `candidate_eval.json`, `decision.json` (`promote` | `reject` | `dry_run_only`).

## Eval flow in the evolution engine

```text
record-eval  →  append EvalMetrics (canary)
check-drop   →  compare latest vs thresholds
run          →  improve → candidate_eval (holdout) → decision.json
```

| Step | Evaluator backend | Split |
|------|-------------------|-------|
| `record-eval` | AgentEvals or mock | canary |
| `run` (post-improve) | AgentEvals or mock | holdout |

## Mode-specific notes

| Mode | Typical evaluator setup |
|------|---------------------------|
| **Skill** | Mock for dry runs; AgentEvals optional for parity |
| **Coach** | AgentEvals required for production supervision |

Coach mode: one `eval_metrics.jsonl` per subject coaching root. See [coach_mode.md](coach_mode.md).

## Phase skill

Runtime policy for building and interpreting eval runs: `modes/self-coaching/self-evaluation/SKILL.md`.

## External integrations

| System | Design doc |
|--------|------------|
| AgentEvals | [integrations/agentevals.md](integrations/agentevals.md) |
| Mock Coaching API eval | [integrations/coaching_api.md](integrations/coaching_api.md) |

Field mapping artifacts: [integration/mapping.md](../integration/mapping.md).

## Related

- [pipelines.md](pipelines.md) — when eval triggers improve / train
- [architecture.md](architecture.md) — deploy gate
