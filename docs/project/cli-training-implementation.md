# CLI Training (db_bridge) — Implementation Tracker

> **Authoritative tracker** for integrating real AReaL training via the **db_bridge remote shell** (migration **M4**, production path). Design: [cli-training-integration-plan.md](cli-training-integration-plan.md). Operational guide: [../design/integrations/db_bridge_remote_shell.md](../design/integrations/db_bridge_remote_shell.md). Migration rules: [mock-to-real-migration.md](mock-to-real-migration.md).

**Status:** Sprints 0–3 complete (2026-06-16) — trigger + status/results; dataset handoff deferred (CT-D01+)  
**Scope (narrow):** **Trigger the tuning pipeline on the AReaL GPU host and collect terminal status + bounded logs.** Success = adapter returns `{ status, run_id, cmd_id, terminal_status, stdout_tail, … }` after the remote command finishes. Registry promotion, holdout gate, and loop-buffer dataset handoff are **out of scope** until a later phase.

**Related:** [progress.md](progress.md) · [self-tuning-trainer-api-plan.md](self-tuning-trainer-api-plan.md) (HTTP mock path; CI only) · [self-questioning-pipeline-implementation.md](self-questioning-pipeline-implementation.md) (independent M3 track)

---

## 1. Goal

Wire `client.train()` to dispatch a **fixed CLI command** on the AReaL host through Supabase (`areal_remote_commands`), poll until a terminal status, and return a normalized result dict. Mock and HTTP (`aerl`) backends stay unchanged for CI.

| Principle | Rule |
|-----------|------|
| **CT-R1** | Adapter parity — extend `services/adapters/`; do not delete `AERLTrainAdapter` or mock trainer |
| **CT-R2** | Explicit backend — `ORCHESTRATOR_TRAIN_BACKEND=mock\|aerl\|cli` |
| **CT-R3** | Mock CI unchanged — R5 (`LOOP_SERVICE_MODE=mock-module`) stays green every PR |
| **CT-R4** | **Trigger + status first** — fixed remote config YAML; no per-run dataset upload in v1 |
| **CT-R5** | Same `train()` contract — loop callers unchanged; adapter owns transport + polling |
| **CT-R6** | Bounded observability — rely on `stdout_tail` / `stderr_tail` (64 KB); full logs on remote host via `tee` |

### In scope (v1)

- Insert `PENDING` row → poll → `SUCCEEDED` / `FAILED` / `TIMED_OUT` / `CANCELLED` / `STALE`
- Build command from env-based config map (fixed YAML on remote host)
- Parse optional `TRAINING_COMPLETE` marker from stdout (best-effort `candidate` + `metrics`)
- Manual smoke: `scripts/cli_train_smoke.py` and existing `send_command.py`
- Unit tests with in-memory fakes (no live DB in default CI)

### Out of scope (deferred)

| Item | Tracker | When |
|------|---------|------|
| Loop-buffer `train.jsonl` → remote dataset staging | CT-D01 | After v1 smoke passes |
| Dynamic config generation per run | CT-D02 | After dataset handoff design |
| Full T-path E2E (train + holdout + promote) | M4.4 live | After M1 eval + v1 train smoke |
| Checkpoint promotion / model activation on GPU host | CT-D03 | Deployment infra TBD |
| HTTP trainer production path | `aerl` backend | Fallback only; not primary |

---

## 2. Remote command contract (frozen for v1)

**Entry script (on AReaL host):**

```bash
uv run customized_areal/tpfc/scripts/train_tpfc_tree_search.py \
  --config <config_path_on_remote> \
  2>&1 | tee training_<run_id>.log
```

**Working directory:** `CLI_TRAIN_CWD` (default `/dfs/share-groups/letrain/zhoujie/AReaL-main`)

**Config selection:** env map `(pipeline, base_model) → config path` — v1 uses one known YAML (self-questioning tree search). The `dataset` argument from the loop is **ignored** until CT-D01.

**Success marker (AReaL host — optional but recommended):**

```
TRAINING_COMPLETE checkpoint=<path> model_id=<id> metrics=<json>
```

If absent, adapter still returns `status: trained` on `SUCCEEDED` with synthetic `candidate` (`cli-train-<run_id>`).

### Command row lifecycle

```
PENDING → CLAIMED → RUNNING → SUCCEEDED | FAILED | TIMED_OUT | CANCELLED | STALE
```

| Terminal status | Adapter `status` field | Notes |
|-----------------|------------------------|-------|
| `SUCCEEDED` | `trained` | Parse stdout for checkpoint/metrics |
| `FAILED` | raise `TrainerCLIError` | Include `stderr_tail`, `exit_code` |
| `TIMED_OUT` | raise `TrainerTimeoutError` | Remote tmux session killed |
| `CANCELLED` / `STALE` | raise `TrainerCLIError` | Surface `error_message` if present |
| (poll budget exceeded) | raise `TrainerTimeoutError` | Row may still be `RUNNING` on host |

---

## 3. Adapter return shape (v1)

Minimum contract for loop / smoke callers:

```json
{
  "status": "trained",
  "run_id": "cli-train-a1b2c3",
  "cmd_id": "<uuid>",
  "candidate": "/output/lora-adapter",
  "candidate_model_id": "/output/lora-adapter",
  "terminal_status": "SUCCEEDED",
  "exit_code": 0,
  "stdout_tail": "...",
  "stderr_tail": "",
  "log_file": "training_cli-train-a1b2c3.log",
  "metrics": null,
  "_train_backend": "cli"
}
```

On failure, raise `TrainerCLIError` / `TrainerTimeoutError` — do not return `status: trained`.

---

## 4. Architecture

```
Coach / loop_driver / smoke script
        │
        ├─ ORCHESTRATOR_TRAIN_BACKEND=mock
        │       → inner ModuleClient.train() / mock_aerl
        │
        ├─ ORCHESTRATOR_TRAIN_BACKEND=aerl
        │       → AERLTrainAdapter → HTTP TrainerClient
        │
        └─ ORCHESTRATOR_TRAIN_BACKEND=cli
                → CLITrainAdapter (services/adapters/)
                        → CLITrainTransport (Supabase REST insert + poll)
                                → areal_remote_commands
                        → cli_train_commands (env config map)
                        → cli_train_output (stdout marker parser)
                ← run_shell_runner on AReaL host (already deployed)
```

**Transport:** Supabase PostgREST — same pattern as `services/lora/db_bridge/scripts/send_command.py`.

---

## 5. Environment profile

```env
# Backend switch
ORCHESTRATOR_TRAIN_BACKEND=cli

# Shared Supabase (coaching host — services/lora/db_bridge/.env)
SUPABASE_URL=http://82.157.184.89:54321
SUPABASE_SERVICE_ROLE_KEY=...
BRIDGE_USER_ID=...

# CLI train adapter
CLI_TRAIN_CWD=/dfs/share-groups/letrain/zhoujie/AReaL-main
CLI_TRAIN_TIMEOUT=3600
CLI_TRAIN_POLL_INTERVAL=5
CLI_TRAIN_TMUX_PREFIX=train-

# Fixed remote config (v1 — override per deployment)
CLI_TRAIN_SCRIPT=customized_areal/tpfc/scripts/train_tpfc_tree_search.py
CLI_TRAIN_CONFIG=customized_areal/tpfc/configs/config_tpfc_Qwen3-5L-9B_tree_search_self_questioning.yaml

# Reuse AERL poll budget naming for long jobs
AERL_TIMEOUT_S=3600
```

**Live smoke profile** (train only; other backends stay mock):

```env
LOOP_SERVICE_MODE=live
ORCHESTRATOR_TRAIN_BACKEND=cli
ORCHESTRATOR_EVAL_BACKEND=mock
ORCHESTRATOR_LEARN_BACKEND=mock
# … Supabase + CLI_TRAIN_* vars above
```

Template: `scenarios/demo.cli-train.env.example` (Sprint 2).

---

## 6. Sprint plan

Calendar assumes ~3–4 working days per sprint. Adjust dates when each sprint starts.

### Sprint 0 — Transport foundation

**Target:** Reusable Supabase insert/poll module; no loop changes.

| ID | Task | Owner | Status |
|----|------|-------|--------|
| CT-T01 | `services/adapters/cli_train_errors.py` — `TrainerCLIError`, `TrainerTimeoutError`, `TransportError` | — | done |
| CT-T02 | `services/adapters/cli_train_transport.py` — `send`, `poll`, `send_and_wait` (extract from `send_command.py`) | — | done |
| CT-T03 | `tests/test_cli_train_transport.py` — offline tests with mocked httpx | — | done |
| CT-T04 | Refactor `send_command.py` to call `CLITrainTransport` (optional thin wrapper) | — | done |
| CT-T05 | Confirm infra checklist: runner up, `probe_connectivity.py` PASS, `send_command.py "hostname"` PASS | — | done (2026-06-16) |

**Sprint 0 exit criteria:**

- [x] Remote shell round-trip verified (`send_command.py`, `probe_connectivity.py`)
- [x] `CLITrainTransport` unit-tested offline
- [x] `send_and_wait` returns full terminal row dict
- [x] R5 mock-module demo still green (no loop changes yet)

---

### Sprint 1 — Adapter: trigger + collect status

**Target:** `CLITrainAdapter.train()` builds command, dispatches, polls, returns v1 result shape.

| ID | Task | Owner | Status |
|----|------|-------|--------|
| CT-T06 | `services/adapters/cli_train_commands.py` — env-based script + config map, `build_train_command()` | — | done |
| CT-T07 | `services/adapters/cli_train_output.py` — parse `TRAINING_COMPLETE` marker + fallbacks | — | done |
| CT-T08 | `services/adapters/cli_train_adapter.py` — `train()` implements CT-R5 contract | — | done |
| CT-T09 | `tests/test_cli_train_adapter.py` — command build, marker parse, error paths (fakes) | — | done |
| CT-T10 | AReaL host: add `TRAINING_COMPLETE` line to training script | AReaL | **requested** — [areal_cli_training_request.md](../design/integrations/areal_cli_training_request.md) · agent skill updated |

**Sprint 1 exit criteria:**

- [x] `CLITrainAdapter.train()` callable from Python with env creds
- [x] Unit tests pass in CI (no network)
- [x] Adapter raises on `FAILED` / `TIMED_OUT`; returns dict on `SUCCEEDED`
- [x] R5 mock-module demo still green

---

### Sprint 2 — Loop wiring + smoke

**Target:** `ORCHESTRATOR_TRAIN_BACKEND=cli` selectable; manual smoke script proves end-to-end.

| ID | Task | Owner | Status |
|----|------|-------|--------|
| CT-T11 | `LoopConfig` — document `train_backend` includes `cli` | — | done |
| CT-T12 | `loop_env.py` — `_build_train_adapter()` returns `CLITrainAdapter` when `cli` | — | done |
| CT-T13 | `composite_client.py` — `use_train` includes `cli` backend | — | done |
| CT-T14 | `scenarios/demo.cli-train.env.example` — staging profile template | — | done |
| CT-T15 | `scripts/cli_train_smoke.py` — calls adapter directly, prints result / exit code | — | done |
| CT-T16 | Manual smoke: real training command with fixed config (long timeout) | — | not started |

**Sprint 2 exit criteria:**

- [x] `ORCHESTRATOR_TRAIN_BACKEND=cli` builds composite client with CLI adapter
- [x] `ORCHESTRATOR_TRAIN_BACKEND=mock` unchanged (default)
- [ ] `cli_train_smoke.py` completes with `status: trained` on staging (manual)
- [x] R5 mock-module demo still green

---

### Sprint 3 — Hardening + docs

**Target:** Opt-in live test, runbook, progress sync. No full T-path yet.

| ID | Task | Owner | Status |
|----|------|-------|--------|
| CT-T17 | `tests/integration/test_cli_train_live.py` — opt-in Supabase round-trip (`echo` or `--help`) | — | done |
| CT-T18 | `tests/test_loop_env.py` — `build_loop_client` with `train_backend=cli` | — | done |
| CT-T19 | `docs/design/integrations/aerl.md` — reference CLI production path | — | done |
| CT-T20 | `docs/guides/runbook.md` — CLI train smoke subsection | — | done |
| CT-T21 | Update [progress.md](progress.md) M4 CLI row when Sprint 2 closes | — | done |

**Sprint 3 exit criteria:**

- [x] Opt-in live integration test documented and runnable
- [x] Runbook covers: env setup, smoke, reading `stdout_tail`, common failures
- [x] R5 mock-module demo still green

---

### Deferred backlog (post–Sprint 3)

| ID | Task | Depends on | Status |
|----|------|------------|--------|
| CT-D01 | Dataset handoff: coaching `train.jsonl` → remote readable path | v1 smoke | deferred |
| CT-D02 | Multi-step adapter (stage config + train, same `tmux_id`) | CT-D01 | deferred |
| CT-D03 | Checkpoint promotion on GPU host | deployment infra | deferred |
| CT-D04 | `test_loop_t_path` opt-in live with `cli` backend | M1 + CT-D01 | deferred |
| CT-D05 | `full_loop_live_smoke.py` T-path row with real train | CT-D04 | deferred |

---

## 7. File map

| File | Sprint | Purpose |
|------|--------|---------|
| `services/adapters/cli_train_errors.py` | 0 | Exception types |
| `services/adapters/cli_train_transport.py` | 0 | Supabase insert + poll |
| `services/adapters/cli_train_commands.py` | 1 | Command builder + env config map |
| `services/adapters/cli_train_output.py` | 1 | Stdout marker / fallback parser |
| `services/adapters/cli_train_adapter.py` | 1 | `train()` entry point |
| `tests/test_cli_train_transport.py` | 0 | Transport unit tests |
| `tests/test_cli_train_adapter.py` | 1 | Adapter unit tests |
| `tests/integration/test_cli_train_live.py` | 3 | Opt-in live probe |
| `scripts/cli_train_smoke.py` | 2 | Manual E2E smoke |
| `modes/self-coaching/loop_env.py` | 2 | Factory wiring |
| `modes/self-coaching/loop_config.py` | 2 | Backend enum docs |
| `services/adapters/composite_client.py` | 2 | `cli` in `use_train` |
| `scenarios/demo.cli-train.env.example` | 2 | Env template |
| `services/lora/db_bridge/scripts/send_command.py` | 0 | Reference impl / optional refactor |

---

## 8. Testing strategy

| Layer | Command / file | Network | PR gate |
|-------|----------------|---------|---------|
| Mock regression (R5) | `bash tests/test_mock_self_coaching_demo.sh` | none | **required** |
| Transport unit | `pytest tests/test_cli_train_transport.py` | none | required (Sprint 0+) |
| Adapter unit | `pytest tests/test_cli_train_adapter.py` | none | required (Sprint 1+) |
| db_bridge feasibility | `pytest services/lora/db_bridge/tests/test_model_tuning_feasibility.py` | none | optional |
| Connectivity probe | `uv run python scripts/probe_connectivity.py` | live | manual |
| Send command | `uv run python scripts/send_command.py "hostname"` | live | manual |
| CLI train smoke | `python scripts/cli_train_smoke.py --env-file scenarios/demo.cli-train.env` | live | manual |
| Live integration | `pytest tests/integration/test_cli_train_live.py` | live | opt-in |
| Loop env wiring | `pytest tests/test_loop_env.py -k cli` | none | required (Sprint 2+) |
| Full T-path | `pytest tests/test_loop_t_path.py` | none (mock) | required |

---

## 9. Risks and decisions

| # | Risk / question | Mitigation | Decision |
|---|-----------------|------------|----------|
| Q1 | Checkpoint path unknown | `TRAINING_COMPLETE` marker (CT-T10); fallback synthetic id | **TBD** — start with marker |
| Q2 | 64 KB log tail truncates metrics | `tee training_<run_id>.log` on remote; adapter sets `log_file` | **Accepted for v1** |
| Q3 | Long GRPO exceeds timeout | `CLI_TRAIN_TIMEOUT=3600+`; poll shows `log_bytes` growth | **Configurable** |
| Q4 | Runner down → row stuck PENDING | Adapter times out at `CLI_TRAIN_TIMEOUT + 60s` | **Decided** |
| Q5 | Loop `dataset` ignored in v1 | Document CT-R4; CT-D01 later | **Decided** |
| Q6 | Concurrent training jobs | Unique `tmux_id` per `run_id` | **Decided** |
| Q7 | Shell runs as root on GPU host | Feature flag on runner; trusted host only | **Accepted** |

---

## 10. Verified infrastructure (2026-06-16)

| Component | Status | Details |
|-----------|--------|---------|
| Supabase (self-hosted) | ✅ | `http://82.157.184.89:54321` |
| `areal_remote_commands` table | ✅ | Schema applied |
| `areal_shell_claim_next` RPC | ✅ | Callable |
| `run_shell_runner` on AReaL host | ✅ | Claims within ~2s |
| Command execution (`echo`, `hostname`, `ls`) | ✅ | Full round-trip |
| AReaL training code on host | ✅ | `/dfs/share-groups/letrain/zhoujie/AReaL-main/` |
| Training output write access | ⏳ | Verify before Sprint 2 manual smoke |
| `TRAINING_COMPLETE` marker in script | ⏳ | CT-T10 |

---

## 11. Progress log

| Date | Sprint | Notes |
|------|--------|-------|
| 2026-06-16 | — | Implementation tracker created; scope narrowed to trigger + status/results |
| 2026-06-16 | Sprint 0 | CT-T05 done — connectivity verified via `send_command.py` / `probe_connectivity.py` |
| 2026-06-16 | Sprint 0 | CT-T01–T04 done — `CLITrainTransport`, errors, unit tests, `send_command.py` refactor |
| 2026-06-16 | Sprint 1 | CT-T06–T09 done — command builder, output parser, `CLITrainAdapter`, unit tests |
| 2026-06-16 | Sprint 2 | CT-T11–T15 done — loop wiring, smoke script, env template |
| 2026-06-16 | Sprint 3 | CT-T17–T21 done — live integration test, runbook, aerl.md, progress sync |

---

## 12. How to update this doc

1. Change task **Status** (`not started` → `in progress` → `done`) when work lands.
2. Check sprint **exit criteria** boxes when the sprint closes.
3. Append a row to **§11 Progress log** with date and PR reference.
4. Mirror headline status in [progress.md](progress.md) § Migration M4.

**Task status values:** `not started` · `in progress` · `done` · `blocked` · `deferred` · `cancelled`
