# CLI-based Training Integration Plan (db_bridge remote shell)

> **Supersedes:** The HTTP API approach in `self-tuning-trainer-api-plan.md` (M4.4 staging) is archived. The team's AReaL training service is CLI-driven, not HTTP-driven. This plan uses the **db_bridge remote shell** as the transport to dispatch training commands to the GPU host.

**Status:** Draft (2026-06-16)  
**Connectivity verified:** 2026-06-16 — full round-trip insert → claim → execute → stdout confirmed.  
**Implementation tracker:** [cli-training-implementation.md](cli-training-implementation.md) — sprint tasks, exit criteria, progress log (authoritative for delivery).

**Related:**
- [self-tuning-trainer-api-plan.md](self-tuning-trainer-api-plan.md) — archived HTTP API approach (M4.0–M4.3 mock layer still useful for CI)
- [../design/integrations/db_bridge_remote_shell.md](../design/integrations/db_bridge_remote_shell.md) — operational guide
- [../design/integrations/aerl.md](../design/integrations/aerl.md) — AERL design overview

---

## 1. Problem statement

The existing M4 plan assumes a **trainer HTTP service** (`POST /v1/training/runs`) running on the GPU host. In practice:

- The AReaL training code is **CLI-based** (shell scripts, `python train.py`, config files).
- The GPU host and this coaching host **cannot reach each other over SSH or HTTP** — they only share a Supabase database.
- The `db_bridge` module already solves this: it relays arbitrary shell commands through the database to a runner on the GPU host.

**Decision:** Use `db_bridge.run_shell_runner` as the primary training dispatch mechanism. The mock HTTP layer (M4.1–M4.3) remains for CI/unit tests; production training goes through CLI.

---

## 2. Architecture

```
┌──────────────────────────┐        ┌────────────────┐        ┌───────────────────────────┐
│  Coaching host            │        │  Supabase DB   │        │  AReaL GPU host           │
│  (this repo)              │        │                │        │                           │
│                           │        │ areal_remote   │        │  run_shell_runner         │
│  CLITrainAdapter          │        │ _commands      │        │  (polls PENDING rows)     │
│    insert PENDING ──────────────> │                │ <──────── claims + executes        │
│    poll status    <──────────────  │ status/logs   │ ────────>  in tmux session         │
│                           │        │                │        │                           │
│  Loop / Orchestrator      │        └────────────────┘        │  AReaL-main/              │
│    train() → adapter      │                                  │    gsm8k_rl.py            │
│    → candidate_model_id   │                                  │    run_all.sh             │
└──────────────────────────┘                                   │    customized_areal/      │
                                                               └───────────────────────────┘
```

### Key differences from HTTP plan

| Aspect | HTTP plan (archived) | CLI plan (this) |
|--------|---------------------|-----------------|
| Transport | HTTP `POST /v1/training/runs` | Supabase row insert → shell runner |
| Training trigger | JSON body to trainer service | Shell command string |
| Status polling | `GET /v1/training/runs/{id}` | Poll row `status` column |
| Logs | `GET /metrics` endpoint | `stdout_tail` / `stderr_tail` on row |
| Checkpoint resolution | `GET /v1/checkpoints/{id}` | Parse stdout or known output paths |
| Multi-step | Single API call | Sequential commands (same `tmux_id`) |

---

## 3. Design principles

| ID | Principle |
|----|-----------|
| **CLI-R1** | **Same `train()` contract.** Loop and orchestrator keep calling `adapter.train(pipeline, dataset, base_model)`. Adapter translates to CLI. |
| **CLI-R2** | **Commands are explicit.** The adapter builds the full shell command string from parameters — no implicit env on the remote host beyond what's in the tmux session. |
| **CLI-R3** | **Sequential steps share state.** Multi-step pipelines (data prep → train → upload) use the same `tmux_id` so each step inherits the previous shell state. |
| **CLI-R4** | **Bounded observability.** Training logs are bounded (64KB tail). For full logs, training scripts should write to a file on the remote host. |
| **CLI-R5** | **Timeout-safe.** Long training jobs get generous timeouts (up to 3600s default, configurable per command). |
| **CLI-R6** | **Mock parity for CI.** Unit tests use the in-memory fake (no DB, no tmux). The mock HTTP layer from M4.1 still works for integration tests. |

---

## 4. Adapter design — `CLITrainAdapter`

New module: `services/adapters/cli_train_adapter.py`

### 4.1 Interface (same as `AERLTrainAdapter`)

```python
class CLITrainAdapter:
    """train() backed by db_bridge remote shell commands."""

    def train(
        self,
        *,
        pipeline: str = "sft",
        dataset: str | None = None,
        base_model: str = "qwen3-8b",
        coaching_root: str | None = None,
        agent_id: str | None = None,
    ) -> dict[str, Any]:
        """Dispatch training CLI to AReaL host, poll to completion, return result."""
        ...
```

### 4.2 Internal flow

```
train(pipeline="grpo", dataset="/data/train.jsonl", base_model="qwen3-8b")
  │
  ├─ 1. Build command string:
  │     "python -m areal.train --pipeline grpo --base-model qwen3-8b --data /data/train.jsonl"
  │
  ├─ 2. Insert row into areal_remote_commands:
  │     { user_id, tmux_id="train-{run_id}", command, cwd, timeout_seconds, status="PENDING" }
  │
  ├─ 3. Poll row until terminal status:
  │     SUCCEEDED → parse stdout for checkpoint path
  │     FAILED    → raise TrainerError with stderr
  │     TIMED_OUT → raise TimeoutError
  │
  └─ 4. Return normalized result:
        { status: "trained", candidate: "<checkpoint-path>", run_id, metrics, log }
```

### 4.3 Command templates

| Pipeline | Command template |
|----------|-----------------|
| `sft` | `python -m areal.train --pipeline sft --base-model {base_model} --data {dataset} --method lora` |
| `grpo` | `python -m areal.train --pipeline grpo --base-model {base_model} --data {dataset} --group-size 8 --kl-coef 0.02` |
| Custom script | `bash {script_path} {args}` |

Templates are configurable via env vars or a YAML config file.

### 4.4 Output parsing

The adapter expects training scripts to print a **marker line** on success:

```
TRAINING_COMPLETE checkpoint=/output/lora-adapter model_id=ckpt-grpo-abc123
```

If no marker is found, the adapter falls back to:
1. Known output directory pattern (e.g., `/output/{pipeline}-{run_id}/`)
2. Exit code 0 = success with a generated candidate ID

---

## 5. Configuration

### 5.1 Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `SUPABASE_URL` | required | Shared Supabase instance |
| `SUPABASE_SERVICE_ROLE_KEY` | required | Service role JWT |
| `BRIDGE_USER_ID` | required | User UUID for command ownership |
| `CLI_TRAIN_CWD` | `/dfs/share-groups/letrain/zhoujie/AReaL-main` | Default working directory on AReaL host |
| `CLI_TRAIN_TIMEOUT` | `3600` | Default timeout (seconds) |
| `CLI_TRAIN_POLL_INTERVAL` | `5` | Poll interval for status checks (seconds) |
| `CLI_TRAIN_TMUX_PREFIX` | `train-` | tmux_id prefix for training sessions |
| `CLI_TRAIN_COMMAND_TEMPLATE` | (see §4.3) | Customizable command template |
| `ORCHESTRATOR_TRAIN_BACKEND` | `mock` | Set to `cli` for remote shell dispatch |

### 5.2 Backend selection

| `ORCHESTRATOR_TRAIN_BACKEND` | Backend | Behavior |
|------------------------------|---------|----------|
| `mock` (default) | In-process `mock_aerl` | Deterministic, fast, no network |
| `aerl` | HTTP TrainingClient | M4 mock HTTP or future real HTTP |
| `cli` | **CLITrainAdapter** | db_bridge remote shell to AReaL host |

---

## 6. Remote host requirements

The AReaL GPU host must have:

| Requirement | Status (verified 2026-06-16) |
|-------------|-----|
| `run_shell_runner` active with `AREAL_REMOTE_SHELL_ENABLED=true` | ✅ |
| `tmux` installed | ✅ |
| Python + training dependencies in PATH | ✅ (`/dfs/share-groups/letrain/zhoujie/le-agent-dev_new/db_bridge/.venv/bin/python`) |
| AReaL training code | ✅ (`/dfs/share-groups/letrain/zhoujie/AReaL-main/`) |
| Write access to output directory | TBD — verify output paths |

---

## 7. Multi-step pipeline support

For complex training workflows, the adapter dispatches multiple commands sequentially using the same `tmux_id`:

```python
steps = [
    "source /workspace/venv/bin/activate",
    "python prepare_data.py --input {dataset} --output /tmp/prepared.jsonl",
    "python -m areal.train --data /tmp/prepared.jsonl --pipeline {pipeline}",
    "python upload_checkpoint.py --path /output/adapter --dest s3://models/",
]
for step in steps:
    send_and_wait(step, tmux_id=f"pipeline-{run_id}")
```

Same `tmux_id` guarantees:
- Sequential execution (next step waits for previous to complete)
- Shared shell state (env vars, working directory from `cd`)
- Single tmux session on the remote host

---

## 8. Error handling

| Scenario | Adapter behavior |
|----------|-----------------|
| Command exits non-zero | Raise `TrainerCLIError` with `stderr_tail` |
| Timeout exceeded | Raise `TrainerTimeoutError`; tmux session killed remotely |
| Supabase unreachable | Raise `TransportError` on insert/poll failure |
| Runner not active | Row stays PENDING; adapter times out after `CLI_TRAIN_TIMEOUT + 60s` |
| Partial stdout (long training) | Intermediate logs available via `stdout_tail` during polling |

---

## 9. Observability

| What | How |
|------|-----|
| Training progress | Poll `stdout_tail` field (last 64KB of output) |
| Full logs | Training script writes to `/output/train-{id}.log` on remote host |
| Status timeline | Row timestamps: `created_at`, `started_at`, `finished_at` |
| Metrics | Parse stdout markers or read from training output files |

---

## 10. Implementation tasks

> **Moved to** [cli-training-implementation.md](cli-training-implementation.md) — sprint plan CT-T01–CT-T21, deferred backlog CT-D01–CT-D05. Update task status there, not in this section.

| Sprint | Focus | Status |
|--------|-------|--------|
| Sprint 0 | Transport foundation (`CLITrainTransport`) | in progress (infra verified) |
| Sprint 1 | Adapter: trigger + collect status | not started |
| Sprint 2 | Loop wiring + `cli_train_smoke.py` | not started |
| Sprint 3 | Hardening, opt-in live test, runbook | not started |

---

## 11. Migration from HTTP plan

| M4 piece | Action |
|----------|--------|
| M4.0 spec | Archived — this doc supersedes for production path |
| M4.1 mock HTTP | **Keep** — still useful for CI unit tests |
| M4.2 TrainingClient | **Keep** — HTTP path remains as fallback or future option |
| M4.3 loop env wiring | **Extend** — add `cli` backend alongside `mock` and `aerl` |
| M4.4 staging smoke | **Replace** — use `scripts/send_command.py` probe instead |
| M4.5 R5 regression | **Unchanged** — mock-module path unaffected |

---

## 12. Testing strategy

| Layer | Approach |
|-------|----------|
| Unit (CI) | In-memory fake DB + fake executor (same pattern as `test_remote_shell.py`) |
| Integration (local) | `scripts/probe_connectivity.py` — verifies network + DB + RPC |
| E2E (manual) | `scripts/send_command.py "echo test"` — confirms full round-trip |
| Training smoke (manual) | `scripts/send_command.py "python -m areal.train --dry-run"` |

---

## 13. Security considerations

- Shell commands run as **root** on the AReaL host — no sandboxing.
- `SUPABASE_SERVICE_ROLE_KEY` is gitignored (in `.env`).
- Only `BRIDGE_USER_ID`-scoped rows are visible to the adapter.
- Training scripts should not echo secrets to stdout (captured in DB rows).
- Feature flag `AREAL_REMOTE_SHELL_ENABLED` must be explicitly `true` on the runner.

---

## 14. Open questions

| # | Question | Options | Decision |
|---|----------|---------|----------|
| Q1 | How does the adapter discover the output checkpoint path? | Marker line in stdout vs known path convention | TBD — start with marker line |
| Q2 | Should we support concurrent training jobs? | Different `tmux_id` per job | Yes — use `train-{uuid}` |
| Q3 | How to handle training script version mismatch? | Pin script version in command vs always use HEAD | TBD |
| Q4 | Full log retrieval after training? | Separate command to `cat` the log file | TBD — may not be needed if 64KB tail suffices |
| Q5 | Checkpoint promotion (model activation)? | Separate command or API call after train succeeds | TBD — depends on deployment infra |

---

## 15. Verified infrastructure (2026-06-16)

| Component | Status | Details |
|-----------|--------|---------|
| Supabase (self-hosted) | ✅ | `http://82.157.184.89:54321` |
| `areal_remote_commands` table | ✅ | Schema applied, rows queryable |
| `areal_shell_claim_next` RPC | ✅ | Callable, returns null when empty |
| `run_shell_runner` on AReaL host | ✅ | Active, claims within ~2s |
| Command execution | ✅ | `echo` + `ls` + `hostname` all succeeded |
| AReaL training code | ✅ | Present at `/dfs/share-groups/letrain/zhoujie/AReaL-main/` |
| Remote host | ✅ | `root@workspace`, Python available |

---



## Feasible Plan: Self-Tuning via db_bridge

Here's the situation and my proposed approach:

### What exists today

```
Loop (run_tasks) → T-path triggers → client.train(pipeline, dataset, base_model)
                                              ↓
                              AERLTrainAdapter.train()
                                              ↓
                              TrainingClient → POST /v1/training/runs (HTTP)
                                              ↓
                              wait_for_run() → poll GET until terminal
                                              ↓
                              map_train_result() → { candidate, metrics, ... }
```

The loop never touches the training infra directly — it calls `client.train()` and gets back a `candidate_model_id`. Everything else is adapter-internal.

### What the CLI path needs to do

Same contract, different transport:

```
Loop → client.train(pipeline, dataset, base_model)
                    ↓
       CLITrainAdapter.train()
                    ↓
       1. Build shell command from (pipeline, base_model, config)
       2. Insert row into areal_remote_commands (PENDING)
       3. Poll row status until terminal (SUCCEEDED/FAILED/TIMED_OUT)
       4. Parse stdout_tail for checkpoint/metrics
       5. Return { candidate, metrics, run_id, ... }
```

### The key design question: What does the command look like?

Your real training command is:
```bash
uv run customized_areal/tpfc/scripts/train_tpfc_tree_search.py \
    --config customized_areal/tpfc/configs/config_tpfc_Qwen3-5L-9B_tree_search_self_play.yaml \
    2>&1 | tee training_self_play.log
```

This tells me:
- **The config YAML is the knob** — it controls model, data, hyperparams, output path.
- **The script is fixed** — `train_tpfc_tree_search.py` is the entrypoint.
- **The adapter doesn't need to pass CLI flags per-parameter** — it just points to a config file.

### Proposed architecture (3 layers)

```
┌─ Layer 1: Loop integration (this repo) ──────────────────────────────┐
│                                                                       │
│  CLITrainAdapter.train(pipeline, dataset, base_model)                │
│    → picks config file based on pipeline + base_model                │
│    → calls CLITrainTransport.send_and_wait(command, cwd, timeout)    │
│    → parses result → returns normalized dict                         │
│                                                                       │
├─ Layer 2: Transport (thin Supabase client) ──────────────────────────┤
│                                                                       │
│  CLITrainTransport                                                    │
│    .send(command, cwd, tmux_id, timeout) → cmd_id                    │
│    .poll(cmd_id, interval) → {status, stdout_tail, stderr_tail, ...} │
│    .send_and_wait(command, ...) → terminal row                       │
│                                                                       │
├─ Layer 3: db_bridge runner (AReaL host, already running) ────────────┤
│                                                                       │
│  run_shell_runner polls → claims → executes in tmux → writes result  │
│                                                                       │
└───────────────────────────────────────────────────────────────────────┘
```

### Config strategy — two options

**Option A: Pre-existing configs (simplest, start here)**

The adapter maps `(pipeline, base_model)` → a config file path on the remote host:

```python
CONFIG_MAP = {
    ("grpo", "qwen3-8b"): "customized_areal/tpfc/configs/config_tpfc_Qwen3-5L-9B_tree_search_self_play.yaml",
    ("sft", "qwen3-8b"): "customized_areal/tpfc/configs/config_sft_qwen3_8b.yaml",
}
```

The adapter builds:
```bash
uv run customized_areal/tpfc/scripts/train_tpfc_tree_search.py --config {config_path} 2>&1 | tee training_{run_id}.log
```

**Option B: Dynamic config generation (future)**

For dynamic datasets or hyperparams, the adapter sends a multi-step pipeline:
1. Write a modified config YAML to `/tmp/train-{run_id}.yaml` (via `echo` or `python -c`)
2. Run training with that config
3. Read output

This uses the same `tmux_id` for sequential execution.

### What the adapter returns

The loop expects:
```python
{
    "status": "trained",
    "run_id": "cli-train-{uuid}",
    "candidate": "<checkpoint-path-or-id>",
    "candidate_model_id": "<same>",
    "metrics": {"train_loss": ..., "reward_mean": ...},  # parsed from stdout
    "log_file": "training_self_play.log",  # remote path
    "_train_backend": "cli",
}
```

### Implementation steps (prioritized)

| Priority | Task | Complexity |
|----------|------|------------|
| 1 | `CLITrainTransport` — Supabase insert + poll (thin httpx wrapper) | Small — reuse `send_command.py` logic |
| 2 | `CLITrainAdapter` — implements `train()`, builds command, calls transport | Medium |
| 3 | `loop_env.py` — add `ORCHESTRATOR_TRAIN_BACKEND=cli` wiring | Small |
| 4 | Output parser — extract metrics/checkpoint from training stdout | Medium (depends on what the script prints) |
| 5 | Config map or template — maps pipeline params to remote config paths | Small |
| 6 | Unit tests with fakes | Small — same pattern as existing `test_remote_shell.py` |

### Open questions for you

1. **What does `train_tpfc_tree_search.py` print on success?** Does it output a checkpoint path, final metrics, or just raw training logs? This determines how the adapter resolves `candidate_model_id`.

2. **Is the config file always the same, or do you need to vary it per training run?** (e.g., different dataset path, different base model, different hyperparams per run)

3. **Where does the trained checkpoint end up?** A fixed path like `/output/...`? Or is it in the config YAML?

4. **Do you want to start with Option A (fixed config map) and iterate?** This gets end-to-end working fastest.

These answers determine whether we need the simple "pick a config and run" approach or the more complex "generate config on the fly" path. What do you think?