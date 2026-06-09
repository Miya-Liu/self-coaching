# Runbook

From the **repository root** (directory containing `modes/`, `scripts/`, `services/`). Bash required; **uv** only for external autoresearch training.

**Self-coaching mode (T1):** [deploy-skill-pack.md](deploy-skill-pack.md) or `bash scripts/install-skill-pack.sh . --with-mock`. **Coach mode:** [deploy-overview.md#coach-mode](deploy-overview.md#coach-mode). Design: [architecture.md](../design/architecture.md).

## One-time: dependencies and data

1. `bash scripts/install-skill-pack.sh .` (or `init-experience.sh` + `doctor.sh`).
2. **Autoresearch worktrees:** set `AUTORESEARCH_ROOT` ([upstream/README.md](../../upstream/README.md)), install [uv](https://docs.astral.sh/uv/), then `bash scripts/preflight.sh`.
3. If needed: `uv --directory "$AUTORESEARCH_ROOT" run prepare.py`.

## Per experiment: worktree

See `modes/self-coaching/SKILL.md` — `git worktree add` into `worktrees/<id>/` under the coaching root.

## Run training (log to file)

```bash
bash scripts/run-once.sh "worktrees/<id>" "logs/<id>.log"
```

## Training pipelines (SFT / GRPO, AERL)

1. Copy `modes/self-coaching/self-tuning/services/example.env` to `modes/self-coaching/self-tuning/services/.env`; set `TRAINER_BASE_URL` (default `http://localhost:8004` in `registry.yaml`).
2. Implement `POST /v1/pipelines/{sft|grpo}/run` on your trainer, or `PIPELINE_MODE=local` + `AERL_ROOT` (see `modes/self-coaching/self-tuning/pipelines/_lib.sh`).
3. `bash scripts/run-pipeline.sh grpo logs/exp-01-grpo.log`

## Experience logs

Summaries in `experience/`; full train output in `logs/<id>.log` only.

## Merge after approval

See `modes/self-coaching/SKILL.md` (`git checkout main`, `git merge`, optional `worktree remove`).

## Self-coaching demo (mock loop)

Deterministic **task-stream loop** on mocks: failures → E-path (`g++`, skill draft) → successes → T-path (train + holdout promote). Completeness audit **C01–C18** including semantic promote gate **C18**. Plan: [self-coaching-demo-pipeline-plan.md](../project/self-coaching-demo-pipeline-plan.md).

### One command (~30–60s, module transport)

**Linux / macOS / Git Bash:**

```bash
bash scripts/mock-self-coaching-demo.sh
```

**Windows (PowerShell — no bash required):**

```powershell
python scripts/mock_self_coaching_demo.py
```

Or:

```powershell
.\scripts\mock-self-coaching-demo.ps1
```

Prints `completeness: PASS` and exits **0** when the loop and audit succeed. Idempotent: recreates `mock-services/demo-loop/` each run.

Optional split-stack fidelity (HTTP mocks on high ports): add `--with-http` (bash or Python) or `-WithHttp` (PowerShell script).

### Verbose (same flow, step by step)

```bash
DEMO_ROOT=mock-services/demo-loop
SCENARIO=scenarios/full_loop.json
rm -rf "${DEMO_ROOT}"

python mock-services/self_coaching_loop.py run \
  --root "${DEMO_ROOT}" \
  --scenario "${SCENARIO}"

python tools/loop_completeness.py \
  --root "${DEMO_ROOT}" \
  --expect-json "${SCENARIO}" \
  --json
```

### Expected artifacts

Under `${DEMO_ROOT}/`:

| Path | Meaning |
|------|---------|
| `.self-coaching/loop/state.json` | Generation, task/buffer counters |
| `.self-coaching/loop/support.jsonl` | Failed trajectories (Σ) |
| `.self-coaching/loop/tuning_buffer.jsonl` | Success buffer (B) |
| `.self-coaching/loop/completeness_report.json` | C01–C18 audit (`status`: PASS/FAIL) |
| `.self-coaching/loop/demo_summary.md` | Human-readable run summary |
| `.self-coaching/loop/runs/t_path/` | Holdout gate: `current_eval.json`, `candidate_eval.json`, `decision.json` |
| `agents/demo-agent/versions/*.json` | Registry lineage |

### Environment (demo defaults)

See [self-coaching-demo-pipeline-plan.md §10](../project/self-coaching-demo-pipeline-plan.md#10-configuration-environment):

| Variable | Default | Meaning |
|----------|---------|---------|
| `LOOP_AGENT_ID` | `demo-agent` | Registry agent |
| `LOOP_TAU_FAIL` | `0.75` | Online failure threshold (τ_fail) |
| `LOOP_SIGMA_MIN` | `3` | Min failures to trigger E-path |
| `LOOP_SIGMA_PLAY` | `0` | Max \|Σ\| for sparse self-play (C06) in full_loop |
| `LOOP_BATCH_SIZE` | `4` | T-path batch size (β) |
| `LOOP_IDLE_AFTER` | `0` | Tasks before free-time window |
| `AGENTEVALS_SUITE_ID_HOLDOUT` | `tool-use-holdout` | Promotion holdout suite |

Override for sparse/dense scenarios: `scenarios/sparse_failures.json`, `scenarios/dense_failures.json`.
