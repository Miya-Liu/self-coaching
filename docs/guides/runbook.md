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

## Pipeline self-questioning (live)

Integrates the **Self-Questioning Pipeline Service** as the real self-questioning backend. The loop only needs a **proceed signal** (`proceed: true`) — generated data stays in the remote store (Supabase); nothing is exported to local `staging.jsonl`.

**Docs:** [self-questioning-pipeline-implementation.md](../project/self-questioning-pipeline-implementation.md) · API: `services/SELF_QUESTIONING_SERVICE_API.md`

### Env profile

Copy [scenarios/demo.pipeline.env.example](../../scenarios/demo.pipeline.env.example) → `scenarios/demo.pipeline.env` and load before running the coach clock or loop:

```bash
# Git Bash — export vars from file (manual) or use your runner's dotenv loader
export $(grep -v '^#' scenarios/demo.pipeline.env | xargs)
```

Key variables:

| Variable | Purpose |
|----------|---------|
| `ORCHESTRATOR_SELF_QUESTIONING_BACKEND=pipeline` | Use pipeline instead of mock self-questioning |
| `PIPELINE_SERVICE_URL` | Base URL (e.g. `http://10.110.158.146:8001`) |
| `PIPELINE_POLL_INTERVAL_S` / `PIPELINE_POLL_TIMEOUT_S` | Job poll budget |
| `PIPELINE_DRY_RUN=1` | Safe smoke — no real GPU/LLM work |

### Connectivity smoke (dry_run)

```bash
PIPELINE_DRY_RUN=1 python scripts/pipeline_self_questioning_smoke.py
```

Expected: `pipeline_self_questioning_smoke: PASS` with `proceed: true` for batch and suite.

### Opt-in integration tests

```bash
PIPELINE_INTEGRATION_TESTS=1 pytest tests/integration/test_pipeline_service_availability.py -v
```

### Coach clock with pipeline backend

```bash
# After loading demo.pipeline.env (and PIPELINE_DRY_RUN=1 for safe test)
python modes/coach/clock.py run --root mock-services/ci-clock-pipeline --json
```

Check summary: `batch_self_questioning_proceed: true`. Mock clock smoke (`scripts/clock_loop_smoke.py`) remains the default CI gate and uses in-process mocks.

### Proceed gating

- **E-path (C06):** if sparse self-questioning returns `proceed: false`, learn is skipped (`status: held`).
- **T-path (C07):** if batch self-questioning returns `proceed: false`, training is skipped (`held: true`).

### C06 prerequisite (pipeline backend)

Mock sparse self-questioning seeds from a local failure trajectory. The pipeline reads **eval messages from Supabase** on the pipeline host (stage 1). Ensure eval failures are ingested there before expecting meaningful non-dry runs.

## CLI training (live, db_bridge)

Triggers **real training CLI** on the AReaL GPU host via Supabase command queue (`run_shell_runner`). v1 scope: dispatch fixed config + collect status/logs — loop-buffer dataset upload is deferred.

**Docs:** [cli-training-implementation.md](../project/cli-training-implementation.md) · [db_bridge_remote_shell.md](../design/integrations/db_bridge_remote_shell.md) · AReaL marker: [areal_cli_training_request.md](../design/integrations/areal_cli_training_request.md)

### Env profile

Copy [scenarios/demo.cli-train.env.example](../../scenarios/demo.cli-train.env.example) → `scenarios/demo.cli-train.env` and merge Supabase credentials from `services/lora/db_bridge/.env`:

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

## Live integration validation (Track 1)

End-to-end coach clock tick with **live** pipeline self-questioning, CLI train (db_bridge), and AgentEvals holdout. Entry point: `scripts/evolution_loop_clock_smoke.py`.

**Env profile:** copy [scenarios/demo.live.env.example](../../scenarios/demo.live.env.example) → `scenarios/demo.live.env` (gitignored). Use `ORCHESTRATOR_SELF_QUESTIONING_BACKEND=pipeline` (legacy `ORCHESTRATOR_SELFPLAY_BACKEND` is still accepted).

### Prerequisites

| Service | Typical URL | Verify |
|---------|-------------|--------|
| Pipeline | `http://10.110.158.146:8001` | `curl …/health` → `{"status":"ok"}` |
| Supabase | your `SUPABASE_URL` | REST root → HTTP 200 with service role key |
| AgentEvals | `http://10.110.158.144:8080` | `curl …/health` → ok |
| AReaL runner | GPU host | `run_shell_runner` active — required for CLI train |

Key timeouts in `demo.live.env`:

| Variable | Recommended | Purpose |
|----------|-------------|---------|
| `PIPELINE_POLL_TIMEOUT_S` | `3600` | Real C07 batch (10–60+ min) |
| `PIPELINE_PREFLIGHT_TIMEOUT_S` | `30` | Health + dry_run preflight only |
| `CLI_TRAIN_TIMEOUT` | `3600` | Remote training |
| `AGENTEVALS_TIMEOUT_S` | `600` | Holdout suite |
| `LOOP_HOLDOUT_TIMEOUT_S` | `300` | Holdout gate in loop |

### Step 1 — Preflight (~30s)

```bash
python scripts/evolution_loop_clock_smoke.py --env-file scenarios/demo.live.env --phase preflight
```

All three services must report ok before a long run.

### Step 2 — CLI probe (before full live)

Validates db_bridge insert → runner claim → stdout capture. **Do not skip** if `ORCHESTRATOR_TRAIN_BACKEND=cli`:

```bash
python scripts/evolution_loop_clock_smoke.py --env-file scenarios/demo.live.env --phase preflight --probe-cli
```

Alternative:

```bash
python scripts/remote_shell.py --env-file scenarios/demo.live.env -- echo hello
python scripts/cli_train_smoke.py --env-file scenarios/demo.live.env --probe
```

If probe fails: start `run_shell_runner` on the AReaL host (`AREAL_REMOTE_SHELL_ENABLED=true`).

### Step 3 — Dry run (optional, ~1–5 min)

Integrated tick with `PIPELINE_DRY_RUN=1` and **mock train** (train backend temporarily mock). Can pass C06/C07 golden subset when pipeline cooperates:

```bash
python scripts/evolution_loop_clock_smoke.py --env-file scenarios/demo.live.env --dry-run
```

`promoted=false` on holdout ties (0.0 vs 0.0) is normal — not required for dry-run PASS.

### Step 4 — Full live tick (30–90+ min)

```bash
python scripts/evolution_loop_clock_smoke.py --env-file scenarios/demo.live.env
```

Flow: E-path (fixtures + C06 pipeline) → buffer → T-path (C07 pipeline → CLI train → AgentEvals holdout → promote/reject).

Success criteria for Track 1: script exits 0; golden rows **C06, C07, C12, C18** pass. `promoted=true` is **not** required (holdout gate may reject).

### Step 5 — Write golden (on full live PASS only)

```bash
python scripts/evolution_loop_clock_smoke.py --env-file scenarios/demo.live.env --write-golden
```

Updates `tests/fixtures/golden/completeness_report_evolution_loop_live.json`.

### Triage

| Symptom | Likely cause | Action |
|---------|--------------|--------|
| C07 `proceed=false` / timeout | Poll budget or pipeline failure | Read `t_path_last.json` → `batch_fill.error`; increase `PIPELINE_POLL_TIMEOUT_S`; check pipeline logs |
| CLI probe timeout | Runner down / row stuck PENDING | Start runner; `scripts/remote_shell.py -- echo hello` |
| CLI `TIMED_OUT` | Exceeded `CLI_TRAIN_TIMEOUT` | Increase timeout; cancel-on-timeout should have requested remote cancel |
| CLI `FAILED` | Bad remote config/script | Read `stdout_tail` / `stderr_tail` in row or `t_path_last.json` |
| Missing holdout `run_id` | AgentEvals down or suite mismatch | Check `AGENTEVALS_*` and local service |
| `promoted=false`, no errors | Holdout gate | Expected when candidate ≤ baseline; see `gate_reasons` |

**Note:** Pipeline poll timeout logs a warning but does **not** cancel the remote job (no cancel API yet). CLI train uses `request_cancel` on client poll timeout.

### Artifacts

Under `mock-services/ci-evolution-loop/.self-coaching/loop/`:

| File | Contents |
|------|----------|
| `e_path_last.json` | C06, learn, sigma |
| `t_path_last.json` | C07, train, holdout, promote |
| `completeness_report.json` | C01–C18 audit |
| `clock_summary.md` | Human summary |
| `state.json` | generation, tasks processed |

### Opt-in pytest

```bash
EVOLUTION_LOOP_INTEGRATION_TESTS=1 EVOLUTION_LOOP_ENV_FILE=scenarios/demo.live.env \
  pytest tests/integration/test_evolution_loop_live.py -k preflight -v

EVOLUTION_LOOP_INTEGRATION_TESTS=1 EVOLUTION_LOOP_INTEGRATION_TICK=1 \
  pytest tests/integration/test_evolution_loop_live.py -k full_tick -v
```
