# Runbook

From **repository root**. Bash required.

Install: [deploy-skill-pack.md](deploy-skill-pack.md). Design: [architecture.md](../design/architecture.md).

## One-time setup

```bash
bash scripts/install-skill-pack.sh . --with-mock
```

Optional AERL: copy `modes/self-coaching/self-tuning/services/example.env` → `.env`, then `bash scripts/preflight.sh`.

## Training pipelines (SFT / GRPO)

```bash
bash scripts/run-pipeline.sh sft logs/exp-01-sft.log
bash scripts/run-pipeline.sh grpo logs/exp-01-grpo.log
```

Summaries → `experience/`; full train output → `logs/<id>.log` only.

## Mock loop demo

One command (~30–60s):

```bash
bash scripts/mock-self-coaching-demo.sh                    # Git Bash / Linux
python scripts/mock_self_coaching_demo.py                  # Windows / cross-platform
```

Optional env: copy [scenarios/demo.env.example](../../scenarios/demo.env.example) → `scenarios/demo.env`.

Expected: `completeness: PASS` (C01–C18). Env knobs: [self-coaching-demo-pipeline-plan.md §10](../project/self-coaching-demo-pipeline-plan.md#10-configuration-environment).

## Pipeline self-play (live)

Integrates the **Self-Questioning Pipeline Service** as the real self-play backend. The loop only needs a **proceed signal** (`proceed: true`) — generated data stays in the remote store (Supabase); nothing is exported to local `staging.jsonl`.

**Docs:** [self-play-pipeline-implementation.md](../project/self-play-pipeline-implementation.md) · API: `services/SELF_QUESTIONING_SERVICE_API.md`

### Env profile

Copy [scenarios/demo.pipeline.env.example](../../scenarios/demo.pipeline.env.example) → `scenarios/demo.pipeline.env` and load before running the coach clock or loop:

```bash
# Git Bash — export vars from file (manual) or use your runner's dotenv loader
export $(grep -v '^#' scenarios/demo.pipeline.env | xargs)
```

Key variables:

| Variable | Purpose |
|----------|---------|
| `ORCHESTRATOR_SELFPLAY_BACKEND=pipeline` | Use pipeline instead of mock self-play |
| `PIPELINE_SERVICE_URL` | Base URL (e.g. `http://10.110.158.146:8001`) |
| `PIPELINE_POLL_INTERVAL_S` / `PIPELINE_POLL_TIMEOUT_S` | Job poll budget |
| `PIPELINE_DRY_RUN=1` | Safe smoke — no real GPU/LLM work |

### Connectivity smoke (dry_run)

```bash
PIPELINE_DRY_RUN=1 python scripts/pipeline_self_play_smoke.py
```

Expected: `pipeline_self_play_smoke: PASS` with `proceed: true` for batch and suite.

### Opt-in integration tests

```bash
PIPELINE_INTEGRATION_TESTS=1 pytest tests/integration/test_pipeline_service_availability.py -v
```

### Coach clock with pipeline backend

```bash
# After loading demo.pipeline.env (and PIPELINE_DRY_RUN=1 for safe test)
python modes/coach/clock.py run --root mock-services/ci-clock-pipeline --json
```

Check summary: `batch_self_play_proceed: true`. Mock clock smoke (`scripts/clock_loop_smoke.py`) remains the default CI gate and uses in-process mocks.

### Proceed gating

- **E-path (C06):** if sparse self-play returns `proceed: false`, learn is skipped (`status: held`).
- **T-path (C07):** if batch self-play returns `proceed: false`, training is skipped (`held: true`).

### C06 prerequisite (pipeline backend)

Mock sparse self-play seeds from a local failure trajectory. The pipeline reads **eval messages from Supabase** on the pipeline host (stage 1). Ensure eval failures are ingested there before expecting meaningful non-dry runs.

## CLI training (live, db_bridge)

Triggers **real training CLI** on the AReaL GPU host via Supabase command queue (`run_shell_runner`). v1 scope: dispatch fixed config + collect status/logs — loop-buffer dataset upload is deferred.

**Docs:** [cli-training-implementation.md](../project/cli-training-implementation.md) · [db_bridge_remote_shell.md](../design/integrations/db_bridge_remote_shell.md) · AReaL marker: [areal_cli_training_request.md](../design/integrations/areal_cli_training_request.md)

### Env profile

Copy [scenarios/demo.cli-train.env.example](../../scenarios/demo.cli-train.env.example) → `scenarios/demo.cli-train.env` and merge Supabase credentials from `services/LoRA/db_bridge/.env`:

| Variable | Purpose |
|----------|---------|
| `ORCHESTRATOR_TRAIN_BACKEND=cli` | Use db_bridge remote shell (not mock or HTTP aerl) |
| `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` / `BRIDGE_USER_ID` | Shared DB transport |
| `CLI_TRAIN_CWD` | Working directory on AReaL host |
| `CLI_TRAIN_SCRIPT` / `CLI_TRAIN_CONFIG` | Remote entry script + YAML config |
| `CLI_TRAIN_TIMEOUT` | Per-command timeout (seconds); long GRPO may need 3600+ |

### Quick probe (recommended first)

Short echo command — validates Supabase insert, runner claim, stdout capture (~1–2 min):

```bash
python scripts/cli_train_smoke.py --env-file scenarios/demo.cli-train.env --probe
```

Expected: `cli_train_smoke: PASS (probe)` and JSON with `candidate: integration-probe` or `smoke-probe`.

### Full training smoke (long-running)

```bash
python scripts/cli_train_smoke.py --env-file scenarios/demo.cli-train.env --pipeline grpo
```

Expect multi-minute to multi-hour runtime depending on config. Monitor `stdout_tail` growth via `send_command.py` or Supabase row poll.

### Reading `stdout_tail` / failures

| Symptom | Likely cause | Action |
|---------|--------------|--------|
| Row stays `PENDING` | `run_shell_runner` down or `AREAL_REMOTE_SHELL_ENABLED=false` | Start runner on AReaL host |
| `TIMED_OUT` | Training exceeded `CLI_TRAIN_TIMEOUT` | Increase timeout; check GPU load |
| `FAILED` + stderr | Bad config path, missing deps | Read `stderr_tail` on row; fix remote command |
| `SUCCEEDED` but synthetic `candidate` | No `TRAINING_COMPLETE` marker in stdout | Forward [areal_cli_training_request.md](../design/integrations/areal_cli_training_request.md) to AReaL team |
| Poll timeout on coaching host | Network or runner stuck in `RUNNING` | Check `log_bytes` increasing; verify tmux session on GPU host |

Full logs beyond 64 KB: remote file `training_<run_id>.log` (from `tee` in dispatched command).

### Opt-in integration tests

```bash
CLI_TRAIN_INTEGRATION_TESTS=1 \
  CLI_TRAIN_ENV_FILE=scenarios/demo.cli-train.env \
  pytest tests/integration/test_cli_train_live.py -v
```

### Loop client with CLI backend

```bash
export ORCHESTRATOR_TRAIN_BACKEND=cli
# ... Supabase + CLI_TRAIN_* vars from demo.cli-train.env
python -c "
from pathlib import Path
import sys
sys.path.insert(0, 'modes/self-coaching')
from loop_env import build_loop_client
c = build_loop_client(Path('mock-services/ci-cli-train'))
print(c.health())
"
```

T-path with real train + holdout remains deferred until dataset handoff (CT-D01).
