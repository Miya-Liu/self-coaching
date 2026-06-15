# self-coaching mode

The **host agent** is both executor and subject: it loads `modes/self-coaching/`, runs experiments locally, and evolves via the gated loop in root [README.md](../../README.md#workflow).

Overview: [architecture.md](architecture.md). Install: [deploy-skill-pack.md](../guides/deploy-skill-pack.md).

## Submodules

| Submodule | Load when |
|-----------|-----------|
| **self-learning** | Corrections → memory / skills / eval cases |
| **self-play** | Generate or curate tasks and trajectories |
| **self-evaluation** | Run evals, interpret reports, promotion gates |
| **self-tuning** | AERL SFT/GRPO after curation |

Load umbrella `SKILL.md` first. Pipeline order: [pipelines.md](pipelines.md).

## Deploy profile

| Aspect | Typical |
|--------|---------|
| Target | T1 — `modes/self-coaching/` |
| Coaching root | Repo or project root |
| Deploy improvements | Merge into host repo after user approval |
| Config | `configs/self-coaching.example.yaml` |

## Loop execution modes

Same **self-evolution tick** in all three; only **who triggers** and **cadence** differ:

| Mode | Driver | Typical use |
|------|--------|-------------|
| **Autonomous** | Host agent 24×7 (or background worker) | Always-on coding agents |
| **Scheduler** | Cron / idle window | Nightly eval + improve; coach default |
| **Manual** | User / admin on demand | “Learn from this session” |

### Self-evolution tick

```text
1. Observe   trajectories, Σ, sessions, eval metrics
2. Gate      σ_min, σ_play, |B| vs β, drop detector
3. Route     hold | self-learning (E) | self-play (P) | self-tuning (T)
4. Record    generation bump, registry, experience artifacts
```

| Route | Trigger (demo) | API surface |
|-------|----------------|-------------|
| Hold | thresholds not met | — |
| Self-learning | \|Σ\| ≥ σ_min | `learn()` / `POST /learning/evolve*` |
| Self-play | sparse Σ or buffer fill | `generate-suite` / `generate` |
| Self-tuning | idle ∧ \|B\| ≥ β | `train()` + holdout gate |

E-path takes precedence over T-path on the same tick. Thresholds and routing detail: [demo plan §3](../project/self-coaching-demo-pipeline-plan.md).

### Config knobs

`LOOP_EXECUTION_MODE`, `LOOP_SIGMA_MIN`, `LOOP_SIGMA_PLAY`, `LOOP_BATCH_SIZE`, `LOOP_IDLE_AFTER` — see [demo.env.example](../../scenarios/demo.env.example). Distinct from `LOOP_SERVICE_MODE` (mock vs live).

## Worktree experiments

Integration line: promoted model/skills after eval gate and user approval. Artifacts: `.self-coaching/` under coaching root.

## Optional automation (scheduler)

```bash
python -m services.orchestrator record-eval --coaching-root . --agent-id my-host ...
python -m services.orchestrator check-drop --metrics-dir ./.self-coaching/metrics
python -m services.orchestrator run --coaching-root . --run-dir ./runs/... --agent-id my-host
```

## Related

[coach_mode.md](coach_mode.md) · [runbook.md](../guides/runbook.md)
