# AReaL Team Request — CLI Training Output Marker

> **Pass to:** AReaL / training pipeline owners  
> **Tracker:** [cli-training-implementation.md](../../project/cli-training-implementation.md) (CT-T10)  
> **Consumer:** `services/adapters/cli_train_output.py` on the coaching host

**Status:** Requested (2026-06-16) — not yet implemented on AReaL host

---

## Context

The self-coaching loop triggers training on the AReaL GPU host via **db_bridge remote shell** (Supabase command queue → `run_shell_runner` → tmux). The coaching host cannot SSH to the GPU box; it only sees:

- Row `status` (`SUCCEEDED` / `FAILED` / `TIMED_OUT`, …)
- Bounded `stdout_tail` / `stderr_tail` (last 64 KB per stream)

We need a **single deterministic line** in stdout so the adapter can resolve `candidate_model_id` after training without parsing unstructured logs.

---

## Request

Please add one **marker line** to the training entrypoint when a run finishes successfully:

```
TRAINING_COMPLETE checkpoint=<absolute-or-relative-path> model_id=<stable-id> metrics=<json-object>
```

### Example (success)

```
TRAINING_COMPLETE checkpoint=/dfs/share-groups/letrain/zhoujie/output/lora-adapter-20260616 model_id=ckpt-grpo-abc123 metrics={"train_loss":0.89,"reward_mean":0.42}
```

### Fields

| Field | Required | Purpose |
|-------|----------|---------|
| `checkpoint` | **Yes** | Filesystem path (or URI) to the trained adapter/checkpoint on the AReaL host |
| `model_id` | Recommended | Stable id for registry / eval routing (may equal checkpoint path if no separate id) |
| `metrics` | Optional | JSON object with scalar summary metrics for loop artifacts (`training.json`) |

### Placement

- Print on the **last line** of successful runs (or anywhere in stdout — parser scans from the bottom).
- Print only when training **completed successfully** (exit code 0).
- On failure, **do not** print this line; rely on non-zero exit + stderr.

### Entry script (current integration)

Coaching host dispatches:

```bash
uv run customized_areal/tpfc/scripts/train_tpfc_tree_search.py \
  --config customized_areal/tpfc/configs/config_tpfc_Qwen3-5L-9B_tree_search_self_questioning.yaml \
  2>&1 | tee training_<run_id>.log
```

**Suggested change location:** end of `train_tpfc_tree_search.py` (or shared helper used by that script).

---

## Fallback behavior (until marker ships)

If the marker is missing but exit code is 0, the coaching adapter synthesizes:

`candidate_model_id = cli-train-<pipeline>-<run_suffix>`

That is enough for **connectivity smoke** but **not** for real holdout eval or checkpoint promotion. Please treat the marker as required for production T-path.

---

## Also helpful (non-blocking)

| Item | Why |
|------|-----|
| Confirm **output directory** in config YAML vs runtime path | Adapter can document default checkpoint location |
| Confirm **write permissions** on output dir from `run_shell_runner` (root) | Avoid silent train success with empty checkpoint |
| Sample **failure stderr** shape | Improve `TrainerCLIError` messages in coaching logs |

---

## Verification

After the marker is added, from the coaching Windows machine:

```powershell
cd services\LoRA\db_bridge
uv run python scripts/send_command.py `
  "echo TRAINING_COMPLETE checkpoint=/tmp/smoke model_id=smoke-test metrics={}"
```

Then run full training smoke:

```powershell
cd <repo-root>
python scripts/cli_train_smoke.py --env-file scenarios/demo.cli-train.env --probe
```

Expected adapter result: `candidate` / `candidate_model_id` parse from the marker, not a synthetic fallback.

---

## Contact / references

- Remote shell ops: [db_bridge_remote_shell.md](db_bridge_remote_shell.md)
- Integration design: [cli-training-integration-plan.md](../../project/cli-training-integration-plan.md)
- Parser implementation: `services/adapters/cli_train_output.py`
