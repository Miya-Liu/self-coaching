---
name: self-tuning
description: "Use when routing curated self-coaching data into SFT or GRPO training runs — via db_bridge CLI on the AReaL GPU host (production), HTTP mock trainer (CI), or legacy pipeline scripts — with manifests, eval gates, and rollback."
version: 0.3.2
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [self-coaching, sft, rl, grpo, lora, model-training, aerl, cli-train, db-bridge, self-tuning]
    related_skills: [self-coaching, self-questioning, self-evaluation, self-learning, huggingface-hub, weights-and-biases]
required_environment_variables:
  - name: ORCHESTRATOR_TRAIN_BACKEND
    required_for: loop-train
    optional: true
    rationale: "mock (default) | aerl (HTTP mock trainer) | cli (production — db_bridge remote shell to AReaL GPU host)."
  - name: SUPABASE_URL
    required_for: cli-train
    optional: true
    rationale: "Shared Supabase URL for areal_remote_commands queue (CLI path)."
  - name: SUPABASE_SERVICE_ROLE_KEY
    required_for: cli-train
    optional: true
    rationale: "Service-role key for insert/poll on areal_remote_commands. Never commit."
  - name: BRIDGE_USER_ID
    required_for: cli-train
    optional: true
    rationale: "User UUID for command row ownership on the remote shell queue."
  - name: CLI_TRAIN_CWD
    required_for: cli-train
    optional: true
    rationale: "Working directory on AReaL host (default /dfs/share-groups/letrain/zhoujie/AReaL-main)."
  - name: CLI_TRAIN_SCRIPT
    required_for: cli-train
    optional: true
    rationale: "Remote entry script relative to CLI_TRAIN_CWD (default train_tpfc_tree_search.py path)."
  - name: CLI_TRAIN_CONFIG
    required_for: cli-train
    optional: true
    rationale: "Remote YAML config path for v1 fixed-config training."
  - name: CLI_TRAIN_TIMEOUT
    required_for: cli-train
    optional: true
    rationale: "Per-command timeout seconds on GPU host. Long GRPO may need 3600+."
  - name: TRAINER_BASE_URL
    required_for: aerl-http-train
    optional: true
    rationale: "HTTP trainer for ORCHESTRATOR_TRAIN_BACKEND=aerl (mock-http CI). Not used for cli."
  - name: LOOP_HOLDOUT_TIMEOUT_S
    required_for: loop-train-holdout
    optional: true
    rationale: "Holdout eval wait budget after train. Default 5s mock; 300–600 live."
---

# Self-Coaching: Self-Tuning (Model Training)

## Overview

Training is the most expensive self-coaching path. Use it only when skills, prompts, tools, and eval fixes are insufficient, or when the explicit goal is **model** improvement.

In this repository the self-tuning **module** is wired into the coaching loop on the **T-path**: after the tuning buffer `B` reaches batch size `β`, the loop calls `client.train()` and then runs a **holdout eval gate** before optional promotion.

| Backend | When | Transport | What you get |
|---------|------|-----------|------------|
| **mock** (default) | Local dev, CI | In-process `mock_aerl` | Instant fake `candidate_model_id` |
| **aerl** | mock-http CI | HTTP `TRAINER_BASE_URL` | Mock trainer lifecycle (M4) |
| **cli** | **Production** | Supabase → `run_shell_runner` on AReaL GPU host | Real training CLI + status/logs in DB row |

**Production path (2026-06):** Real GPU training uses **`ORCHESTRATOR_TRAIN_BACKEND=cli`** and `CLITrainAdapter` — not HTTP to the GPU box. The coaching host and AReaL host share **Supabase only** (no SSH).

**Implementation references:**

- Tracker: `docs/project/cli-training-implementation.md`
- Design: `docs/project/cli-training-integration-plan.md`
- Ops: `docs/design/integrations/db_bridge_remote_shell.md`
- AReaL stdout marker (external): `docs/design/integrations/areal_cli_training_request.md`

This skill also includes legacy **pipeline shell helpers** under `self-tuning/pipelines/` (`run-pipeline.sh`, SFT/GRPO YAML) for operator-style runs against an HTTP trainer.

## Runtime module — how the coaching loop uses self-tuning

The loop does **not** train on every tick. Training runs on the **T-path** when:

1. **C07** (self-questioning batch) has filled buffer `B` to size `β` (`LOOP_BATCH_SIZE`), and
2. Orchestrator policy allows the T-path tick.

| ID | Step | Trigger | Module call | Next step |
|----|------|---------|-------------|-----------|
| **C07** | Buffer fill | `\|B\| < β` while idle | `generate_batch` (self-questioning) | — |
| **T-train** | Train | `\|B\| ≥ β` | `client.train(pipeline, dataset, base_model)` | Holdout gate |
| **T-gate** | Holdout | After train | AgentEvals holdout on prod vs candidate | Promote or reject |
| **T-consume** | Buffer | On promote | Mark buffer rows consumed | — |

Code path: `modes/self-coaching/t_path.py` → `client.train()` → adapter (`CLITrainAdapter` | `AERLTrainAdapter` | mock).

Factory resolution (`modes/self-coaching/loop_env.py` → `build_loop_client()`):

1. `ORCHESTRATOR_TRAIN_BACKEND=cli` → `CLITrainAdapter` (Supabase remote shell)
2. `ORCHESTRATOR_TRAIN_BACKEND=aerl` → `AERLTrainAdapter` (HTTP `TrainerClient`)
3. `mock` (default) → inner `ModuleClient.train()` / `mock_aerl`

In `LOOP_SERVICE_MODE=live`, backend auto-infers when unset:

- `TRAINER_BASE_URL` set → `aerl`
- Else Supabase creds (`SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` + `BRIDGE_USER_ID`) → `cli`

### Train success contract (what the agent should check)

After `train()` returns, check **`status == "trained"`** and record **`candidate`** / **`candidate_model_id`** for the registry and holdout eval.

**CLI backend** — success shape:

```json
{
  "status": "trained",
  "run_id": "cli-train-a1b2c3d4e5f6",
  "cmd_id": "<supabase-row-uuid>",
  "candidate": "/output/lora-adapter",
  "candidate_model_id": "/output/lora-adapter",
  "terminal_status": "SUCCEEDED",
  "exit_code": 0,
  "stdout_tail": "…",
  "stderr_tail": "",
  "log_file": "training_cli-train-a1b2c3d4e5f6.log",
  "metrics": { "train_loss": 0.89 },
  "config_path": "customized_areal/tpfc/configs/…yaml",
  "_train_backend": "cli"
}
```

**v1 CLI limitation:** `dataset` from the loop (`train.jsonl` on the coaching host) is **not uploaded** to the GPU host yet. Training uses a **fixed remote config YAML** (`CLI_TRAIN_CONFIG`). Do not assume per-run dataset paths in the dispatched command until dataset handoff (CT-D01) ships.

**Stdout marker:** For real checkpoint ids, the AReaL training script should print:

```text
TRAINING_COMPLETE checkpoint=<path> model_id=<id> metrics={"train_loss":0.89}
```

Without this line, CLI may still return `status: trained` on exit 0 but with a **synthetic** `candidate` (`cli-train-<pipeline>-<suffix>`). Forward `areal_cli_training_request.md` to the AReaL team if promotion/eval needs a real path.

**Failures** (adapter raises — do not treat as trained):

| Error | Meaning |
|-------|---------|
| `TrainerCLIError` | Remote command `FAILED`, `CANCELLED`, or `STALE` — read `stderr_tail` / `error_message` on row |
| `TrainerTimeoutError` | Remote `TIMED_OUT` or coaching host poll budget exceeded |
| `TransportError` | Supabase insert/poll HTTP failure |

Loop artifacts after T-path: `.self-coaching/loop/runs/t_path/training.json`, `t_path_last.json`.

### Agent decision guide

| Situation | Action |
|-----------|--------|
| `\|B\| < β` | **Do not train** — wait for C07 self-questioning or lower `LOOP_BATCH_SIZE` in test |
| C07 `proceed: false` | **Hold** — train skipped (`held: true`); fix self-questioning first |
| `train()` → `status: trained` | Continue → holdout eval on `candidate_version_id` |
| Holdout gate **promote** | `registry.activate`; buffer consumed |
| Holdout gate **reject** | Buffer preserved; record `gate_reasons` in `t_path_last.json` |
| `TrainerCLIError` / timeout | **Do not promote** — inspect `stdout_tail`/`stderr_tail`, runner health, `CLI_TRAIN_TIMEOUT` |
| Synthetic `candidate` after real train | Request AReaL team add `TRAINING_COMPLETE` marker |
| User asks to train outside loop | Use smoke script or adapter directly (see below) |

### Configuration (CLI production backend)

Copy env template and merge Supabase credentials:

```bash
cp scenarios/demo.cli-train.env.example scenarios/demo.cli-train.env
# Merge SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, BRIDGE_USER_ID from services/lora/db_bridge/.env
```

| Variable | Role |
|----------|------|
| `ORCHESTRATOR_TRAIN_BACKEND=cli` | Select db_bridge remote shell adapter |
| `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` / `BRIDGE_USER_ID` | Command queue transport |
| `CLI_TRAIN_CWD` | Remote working directory on AReaL host |
| `CLI_TRAIN_SCRIPT` | Entry script (default `train_tpfc_tree_search.py`) |
| `CLI_TRAIN_CONFIG` | Remote YAML config (v1: fixed per deployment) |
| `CLI_TRAIN_CONFIG_<PIPELINE>_<MODEL>` | Optional per-pipeline override (env key, normalized) |
| `CLI_TRAIN_TIMEOUT` | Remote command timeout (seconds) |
| `CLI_TRAIN_POLL_INTERVAL` | Status poll interval from coaching host |
| `AERL_TIMEOUT_S` | Alias poll budget for long jobs |

**AReaL host prerequisite:** `run_shell_runner` with `AREAL_REMOTE_SHELL_ENABLED=true` and `tmux` installed.

### Smoke and health (CLI)

```bash
# Quick probe (~1–2 min) — echo TRAINING_COMPLETE, no GPU training
python scripts/cli_train_smoke.py --env-file scenarios/demo.cli-train.env --probe

# Full remote training (long-running)
python scripts/cli_train_smoke.py --env-file scenarios/demo.cli-train.env --pipeline grpo

# Raw transport round-trip
cd services/lora/db_bridge
uv run python scripts/send_command.py "hostname" --timeout 30

# Opt-in integration tests
CLI_TRAIN_INTEGRATION_TESTS=1 \
  CLI_TRAIN_ENV_FILE=scenarios/demo.cli-train.env \
  pytest tests/integration/test_cli_train_live.py -v
```

**Loop client health** with CLI backend:

```bash
export ORCHESTRATOR_TRAIN_BACKEND=cli
# … load demo.cli-train.env
python -c "
from pathlib import Path
import sys
sys.path.insert(0, 'modes/self-coaching')
from loop_env import build_loop_client
print(build_loop_client(Path('mock-services/ci-cli-train')).health())
"
# Expect: train_backend: cli, cli_train: {status: ok, …}
```

### Direct adapter use (outside loop)

When the user or orchestrator needs a one-off training dispatch:

```python
from services.adapters.cli_train_adapter import CLITrainAdapter

adapter = CLITrainAdapter()  # reads SUPABASE_* + BRIDGE_USER_ID from env
result = adapter.train(pipeline="grpo", base_model="qwen3-8b")
# result["status"] == "trained" → record result["candidate"], result["run_id"]
```

For HTTP mock trainer (CI / split-stack):

```bash
export ORCHESTRATOR_TRAIN_BACKEND=aerl
export TRAINER_BASE_URL=http://127.0.0.1:38004
# build_loop_client() → AERLTrainAdapter
```

## When to Use

Use training when:

- the weakness repeats across many tasks;
- curated examples are high-quality, licensed, deduplicated, and privacy-checked;
- an eval pipeline can compare candidate vs baseline;
- deployment, canary, and rollback are defined;
- cheaper improvements (skill patches, tools, prompts) are insufficient.

Do not train when fewer examples, clearer instructions, a skill patch, or a tool would solve the problem.

## Folder Map

The category root (`SKILL_ROOT`) is wherever the `self-coaching` skill is installed:

```text
$SKILL_ROOT/
  scripts/
    preflight.sh
    run-pipeline.sh          # legacy HTTP pipeline runner
    hook-experiment.sh
    hook-inject-errors.sh
    hook-inject-learnings.sh
    init-experience.sh
  experience/
    EXPERIMENT_LOG.md
    ERROR.md
    LEARNINGS.md
    RUN_SUMMARY.json
  self-tuning/
    services/example.env     # HTTP trainer credentials (aerl path)
    pipelines/registry.yaml
    pipelines/_lib.sh
    pipelines/sft/
    pipelines/grpo/
```

**Monorepo operators** also use repo-root scripts:

```text
scripts/cli_train_smoke.py       # CLI adapter smoke (production path)
scripts/mock_self_coaching_demo.py   # full loop on mocks (R5)
services/adapters/cli_train_adapter.py
services/lora/db_bridge/           # remote shell runner (AReaL host)
```

Copy `self-tuning/services/example.env` → `.env` only for **HTTP aerl** mode. CLI credentials live in `services/lora/db_bridge/.env` or `scenarios/demo.cli-train.env`. Never commit secrets.

## Preflight and Environment

### CLI path (production)

1. Confirm `run_shell_runner` active on AReaL host.
2. Run probe: `python scripts/cli_train_smoke.py --env-file scenarios/demo.cli-train.env --probe`
3. Expect `cli_train_smoke: PASS (probe)` and parsed `candidate` from marker.

### HTTP path (legacy / mock-http)

```bash
bash "$SKILL_ROOT/scripts/preflight.sh"
```

Checks `self-tuning/services/.env` and optional `AERL_ROOT` for local source mode.

HTTP contract (mock trainer / `aerl` backend):

```text
POST {TRAINER_BASE_URL}/v1/training/runs
GET  {TRAINER_BASE_URL}/v1/training/runs/{id}
```

```bash
cp "$SKILL_ROOT/self-tuning/services/example.env" \
   "$SKILL_ROOT/self-tuning/services/.env"
```

### Running a named pipeline (legacy shell)

```bash
bash "$SKILL_ROOT/scripts/run-pipeline.sh" \
  sft "$SKILL_ROOT/logs/sft-001.log" \
  dataset.path=.self-coaching/curated/train.jsonl

bash "$SKILL_ROOT/scripts/run-pipeline.sh" \
  grpo "$SKILL_ROOT/logs/grpo-001.log" \
  scheduler.type=local
```

Pipeline IDs: `self-tuning/pipelines/registry.yaml`. Default mode is HTTP via `TRAINER_BASE_URL`. For production GPU training in this repo, prefer **`ORCHESTRATOR_TRAIN_BACKEND=cli`** instead of extending HTTP to the GPU host.

## Mock loop (end-to-end validation)

Before live training, validate the gated loop on mocks:

```bash
LOOP_SERVICE_MODE=mock-module python scripts/mock_self_coaching_demo.py
# or: bash tests/test_mock_self_coaching_demo.sh
```

Expected: `completeness: PASS` (C01–C18). This uses `ORCHESTRATOR_TRAIN_BACKEND=mock` — no Supabase or GPU.

## SFT / GRPO procedure (data + gates)

1. Collect curated demonstrations (self-questioning buffer, manual curation).
2. Redact secrets; verify license/consent.
3. Convert to target chat/tool-call format.
4. Split by task family, not random transcript chunks.
5. Run training via **loop T-path** (`cli` / `aerl` / `mock`) or legacy `run-pipeline.sh`.
6. Evaluate against fixed regression and held-out suites (**self-evaluation**).
7. Inspect top failures manually.
8. Version dataset, config, model, logs, and eval report together.

**Preference / RL (GRPO):** use `pipeline=grpo` in `train()` or the `grpo` pipeline id. Monitor reward hacking, verbosity drift, and tool-use regressions on holdout.

## Record Schemas

SFT record:

```json
{"id":"sft-001","source":"eval_failure","messages":[],"tool_trace_summary":[],"ideal_response":"...","capability":["debugging"],"privacy_checked":true,"license":"internal-permitted","use_for":["train"]}
```

Training manifest (loop / adapter):

```json
{
  "run_id": "cli-train-a1b2c3d4e5f6",
  "cmd_id": "uuid",
  "candidate": "/output/lora-adapter",
  "terminal_status": "SUCCEEDED",
  "log_file": "training_cli-train-a1b2c3d4e5f6.log",
  "config_path": "customized_areal/tpfc/configs/….yaml",
  "_train_backend": "cli"
}
```

## Experience Logging

After each run, update:

- `experience/EXPERIMENT_LOG.md` — run id, hypothesis, metrics, decision, log path
- `experience/ERROR.md` — crashes, OOMs, timeouts, transport failures
- `experience/LEARNINGS.md` — reusable process lessons
- `experience/RUN_SUMMARY.json` — machine-readable summary when useful

```bash
bash "$SKILL_ROOT/scripts/hook-inject-errors.sh"
bash "$SKILL_ROOT/scripts/hook-inject-learnings.sh"
```

For loop T-path runs, also read `.self-coaching/loop/t_path_last.json` and `runs/t_path/training.json`.

## Evaluation Gate

Every training run must pass **self-evaluation** holdout before promotion (loop does this automatically on T-path):

```bash
python scripts/run_agent_evals.py \
  --candidate <trained-model-or-endpoint> \
  --baseline <previous-model-or-endpoint> \
  --suite .self-coaching/cases/eval_cases.jsonl \
  --out .self-coaching/reports/eval_runs/<run_id>/report.json
```

Record eval report path in the training manifest. Promote only if target metrics improve and safety/tool-use regressions do not appear.

## Self-coaching loop position

```text
mine failures → hypothesize → self-questioning (C07) → buffer B → train (T-path) → holdout gate → promote/rollback → archive
```

Prefer cheap improvements first. Training should be gated by evidence and eval, not by data volume alone.

## Common Pitfalls

1. **Training before eval exists.** Build or select the eval runner first.
2. **Wrong backend for production.** GPU host needs `cli`, not `TRAINER_BASE_URL` HTTP.
3. **Runner not running.** Rows stuck `PENDING` → check AReaL `run_shell_runner`.
4. **Expecting local dataset on GPU (v1).** CLI uses fixed `CLI_TRAIN_CONFIG`; loop `dataset` ignored until CT-D01.
5. **Synthetic candidate after real train.** Missing `TRAINING_COMPLETE` marker on AReaL host.
6. **Skipping mock validation.** Run mock-module demo before live CLI.
7. **Pasting full logs.** Use `stdout_tail` summary; full logs on remote `training_<run_id>.log`.
8. **Leaking secrets.** Keep Supabase keys out of chat, memory, and git.
9. **No rollback.** Record baseline model/config before training.
10. **Training when C07 `proceed: false`.** Fix self-questioning before expecting buffer fill.

## Verification Checklist

- [ ] Data is privacy-checked, licensed, and deduplicated (when using local datasets).
- [ ] Train/validation/test splits separated by task family.
- [ ] Held-out eval data not in training.
- [ ] **CLI:** probe smoke PASS; Supabase creds configured; runner enabled on AReaL host.
- [ ] **CLI:** `train()` returns `status: trained` and sensible `candidate` (marker or documented fallback).
- [ ] **Loop:** `t_path_last.json` shows holdout gate outcome before promotion.
- [ ] Training manifest records `run_id`, `log_file`, config path, rollback target.
- [ ] Candidate passes evaluation gates.
- [ ] Experience logs summarize outcomes without raw log dumps or secrets.
- [ ] Mock-module demo still PASS after integration changes.
