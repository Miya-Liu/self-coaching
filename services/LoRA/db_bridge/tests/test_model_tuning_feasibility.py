"""Feasibility test: triggering model tuning via db_bridge remote shell.

Validates the full lifecycle of dispatching a CLI model-tuning command through
the ``areal_remote_commands`` queue and having the shell runner execute it on
the AReaL host. Uses in-memory fakes (no live DB or tmux needed).

Scenarios:
  1. Single training command → SUCCEEDED with stdout captured.
  2. Multi-step pipeline (same tmux_id) → sequential execution in one session.
  3. Long-running training with periodic heartbeat/log streaming.
  4. Training failure → FAILED with exit code and stderr captured.
  5. Cancel mid-training → CANCELLED with session terminated.
  6. Timeout on hung training → TIMED_OUT.
"""

from __future__ import annotations

import asyncio
import uuid

from db_bridge.config import RemoteShellConfig
from db_bridge.remote_shell import RemoteShellDB, RemoteShellRunner
from db_bridge.shell_executor import CaptureResult, LaunchSpec, ShellExecutor

from _fakes import FakeSupabaseClient

USER = "00000000-0000-0000-0000-000000000001"
SHELL_TABLE = "areal_remote_commands"


def _config(**overrides: str) -> RemoteShellConfig:
    env = {
        "SUPABASE_URL": "https://example.supabase.co",
        "SUPABASE_SERVICE_ROLE_KEY": "test-key",
        "AREAL_REMOTE_SHELL_ENABLED": "true",
        "AREAL_REMOTE_SHELL_RUNNER_ID": "tuning-runner-1",
        "AREAL_REMOTE_SHELL_POLL_INTERVAL": "0.01",
        "AREAL_REMOTE_SHELL_LEASE_SECONDS": "60",
        **overrides,
    }
    return RemoteShellConfig.from_env(env)


def _db(client=None):
    fake = client or FakeSupabaseClient()
    return RemoteShellDB(_config(), client=fake), fake


def _enqueue(
    fake: FakeSupabaseClient,
    command: str,
    *,
    tmux_id: str = "train-lora",
    timeout: int = 300,
    cwd: str | None = "/workspace/areal",
) -> str:
    cmd_id = str(uuid.uuid4())
    fake.tables.setdefault(SHELL_TABLE, {})[cmd_id] = {
        "id": cmd_id,
        "user_id": USER,
        "tmux_id": tmux_id,
        "agent_run_id": None,
        "command": command,
        "cwd": cwd,
        "timeout_seconds": timeout,
        "status": "PENDING",
        "exit_code": None,
        "stdout_tail": "",
        "stderr_tail": "",
        "log_bytes": 0,
        "runner_id": None,
        "lease_epoch": None,
        "cancel_requested_at": None,
        "started_at": None,
        "finished_at": None,
        "metadata": {},
        "created_at": next(fake.seq),
    }
    return cmd_id


def _row(fake, cmd_id):
    return fake.tables[SHELL_TABLE][cmd_id]


class TrainingExecutor(ShellExecutor):
    """Fake executor that simulates model training CLI output."""

    def __init__(self):
        self.launched: list[LaunchSpec] = []
        self.terminated: list[str] = []
        self.scripts: dict[str, list[CaptureResult]] = {}

    async def launch(self, spec: LaunchSpec) -> None:
        self.launched.append(spec)

    async def poll(self, session: str, *, max_log_bytes: int) -> CaptureResult:
        seq = self.scripts.get(session)
        if seq:
            return seq.pop(0)
        return CaptureResult(b"", b"", 0, None)

    async def terminate(self, session: str) -> None:
        self.terminated.append(session)


# ---------------------------------------------------------------------------
# Scenario 1: Single training CLI command succeeds
# ---------------------------------------------------------------------------


async def test_single_lora_training_command_succeeds():
    """Simulate: python -m areal.train --config lora.yaml → exit 0."""
    db, fake = _db()
    cmd_id = _enqueue(
        fake,
        "python -m areal.train --config lora.yaml --base-model qwen3-8b",
    )

    cmd = await db.claim_next("tuning-runner-1", 60)
    assert cmd is not None
    assert cmd.id == cmd_id
    assert cmd.command == "python -m areal.train --config lora.yaml --base-model qwen3-8b"
    assert cmd.cwd == "/workspace/areal"

    session = _config().session_name("train-lora")
    ex = TrainingExecutor()
    ex.scripts[session] = [
        # Simulated training output over multiple polls
        CaptureResult(b"Loading model qwen3-8b...\n", b"", 28, None),
        CaptureResult(
            b"Loading model qwen3-8b...\nEpoch 1/3 loss=2.31\n", b"", 50, None
        ),
        CaptureResult(
            b"Epoch 1/3 loss=2.31\nEpoch 2/3 loss=1.45\nEpoch 3/3 loss=0.89\n"
            b"Training complete. Adapter saved to /output/lora-adapter\n",
            b"",
            120,
            0,  # exit code 0 = success
        ),
    ]

    runner = RemoteShellRunner(db, ex, _config())
    await runner.execute_command(cmd)

    row = _row(fake, cmd_id)
    assert row["status"] == "SUCCEEDED"
    assert row["exit_code"] == 0
    assert "Training complete" in row["stdout_tail"]
    assert "lora-adapter" in row["stdout_tail"]
    assert row["started_at"] is not None
    assert row["finished_at"] is not None
    # Verify the executor received the right launch parameters
    assert len(ex.launched) == 1
    assert ex.launched[0].cwd == "/workspace/areal"
    assert "areal.train" in ex.launched[0].command


# ---------------------------------------------------------------------------
# Scenario 2: Multi-step pipeline (same tmux_id → sequential)
# ---------------------------------------------------------------------------


async def test_multi_step_training_pipeline_sequential():
    """Simulate a 3-step pipeline: download data → train → upload adapter."""
    db, fake = _db()
    tmux_id = "pipeline-run-42"

    step1_id = _enqueue(fake, "python download_data.py --dataset rl-v3", tmux_id=tmux_id)
    step2_id = _enqueue(
        fake,
        "python -m areal.train --config lora.yaml --dataset /data/rl-v3",
        tmux_id=tmux_id,
    )
    step3_id = _enqueue(
        fake, "python upload_adapter.py --path /output/adapter", tmux_id=tmux_id
    )

    session = _config().session_name(tmux_id)
    ex = TrainingExecutor()

    # Step 1: only step1 is claimable (same tmux_id serialization)
    cmd = await db.claim_next("tuning-runner-1", 60)
    assert cmd is not None and cmd.id == step1_id
    ex.scripts[session] = [CaptureResult(b"Downloaded 1.2GB\n", b"", 17, 0)]
    await RemoteShellRunner(db, ex, _config()).execute_command(cmd)
    assert _row(fake, step1_id)["status"] == "SUCCEEDED"

    # Step 2: now claimable since step1 is terminal
    cmd = await db.claim_next("tuning-runner-1", 60)
    assert cmd is not None and cmd.id == step2_id
    ex.scripts[session] = [CaptureResult(b"Training done loss=0.5\n", b"", 23, 0)]
    await RemoteShellRunner(db, ex, _config()).execute_command(cmd)
    assert _row(fake, step2_id)["status"] == "SUCCEEDED"

    # Step 3: upload
    cmd = await db.claim_next("tuning-runner-1", 60)
    assert cmd is not None and cmd.id == step3_id
    ex.scripts[session] = [CaptureResult(b"Uploaded to s3://models/adapter\n", b"", 31, 0)]
    await RemoteShellRunner(db, ex, _config()).execute_command(cmd)
    assert _row(fake, step3_id)["status"] == "SUCCEEDED"

    # All 3 steps used the same tmux session
    assert all(spec.session == session for spec in ex.launched)


# ---------------------------------------------------------------------------
# Scenario 3: Long-running training with heartbeat log streaming
# ---------------------------------------------------------------------------


async def test_heartbeat_streams_training_logs():
    """Runner heartbeats intermediate training logs back to the DB row."""
    db, fake = _db()
    cmd_id = _enqueue(fake, "python train.py --epochs 100", timeout=600)

    cmd = await db.claim_next("tuning-runner-1", 60)
    session = _config().session_name("train-lora")
    ex = TrainingExecutor()
    # Simulate 3 heartbeat cycles before completion
    ex.scripts[session] = [
        CaptureResult(b"Epoch 1/100 loss=3.2\n", b"", 21, None),
        CaptureResult(b"Epoch 1/100 loss=3.2\nEpoch 50/100 loss=1.1\n", b"", 44, None),
        CaptureResult(
            b"Epoch 50/100 loss=1.1\nEpoch 100/100 loss=0.3\nDone.\n",
            b"",
            55,
            0,
        ),
    ]

    runner = RemoteShellRunner(db, ex, _config())
    await runner.execute_command(cmd)

    row = _row(fake, cmd_id)
    assert row["status"] == "SUCCEEDED"
    # The final stdout_tail should contain the last streamed output
    assert "Epoch 100/100" in row["stdout_tail"]
    assert row["log_bytes"] == 55


# ---------------------------------------------------------------------------
# Scenario 4: Training failure captured with stderr
# ---------------------------------------------------------------------------


async def test_training_failure_captures_stderr():
    """A training script that exits non-zero reports FAILED with stderr."""
    db, fake = _db()
    cmd_id = _enqueue(
        fake,
        "python -m areal.train --config bad.yaml",
    )

    cmd = await db.claim_next("tuning-runner-1", 60)
    session = _config().session_name("train-lora")
    ex = TrainingExecutor()
    ex.scripts[session] = [
        CaptureResult(
            b"",
            b"FileNotFoundError: bad.yaml not found\nTraceback (most recent call last):\n  ...\n",
            80,
            1,
        ),
    ]

    runner = RemoteShellRunner(db, ex, _config())
    await runner.execute_command(cmd)

    row = _row(fake, cmd_id)
    assert row["status"] == "FAILED"
    assert row["exit_code"] == 1
    assert "FileNotFoundError" in row["stderr_tail"]


# ---------------------------------------------------------------------------
# Scenario 5: Cancel mid-training
# ---------------------------------------------------------------------------


async def test_cancel_training_mid_run():
    """Backend requests cancellation while training is running."""
    db, fake = _db()
    cmd_id = _enqueue(fake, "python train.py --epochs 1000", timeout=3600)

    cmd = await db.claim_next("tuning-runner-1", 60)
    session = _config().session_name("train-lora")

    poll_count = 0

    class CancellingExecutor(ShellExecutor):
        async def launch(self, spec: LaunchSpec) -> None:
            pass

        async def poll(self, session: str, *, max_log_bytes: int) -> CaptureResult:
            nonlocal poll_count
            poll_count += 1
            if poll_count == 2:
                # Simulate backend cancel arriving after 2 polls
                _row(fake, cmd_id)["cancel_requested_at"] = 1.0
            return CaptureResult(b"Epoch 5/1000 loss=2.8\n", b"", 22, None)

        async def terminate(self, session: str) -> None:
            pass

    runner = RemoteShellRunner(db, CancellingExecutor(), _config())
    await runner.execute_command(cmd)

    row = _row(fake, cmd_id)
    assert row["status"] == "CANCELLED"


# ---------------------------------------------------------------------------
# Scenario 6: Timeout on hung training process
# ---------------------------------------------------------------------------


async def test_timeout_on_hung_training():
    """Training exceeds its timeout → TIMED_OUT and session killed."""
    db, fake = _db()
    cmd_id = _enqueue(
        fake,
        "python train.py --config stuck.yaml",
        timeout=1,  # 1 second timeout
    )

    cmd = await db.claim_next("tuning-runner-1", 60)
    session = _config().session_name("train-lora")
    ex = TrainingExecutor()
    # Never completes — always returns "running"
    ex.scripts[session] = []  # empty = always returns running default

    runner = RemoteShellRunner(
        db, ex, _config(AREAL_REMOTE_SHELL_POLL_INTERVAL="0.02")
    )
    await runner.execute_command(cmd)

    row = _row(fake, cmd_id)
    assert row["status"] == "TIMED_OUT"
    assert session in ex.terminated


# ---------------------------------------------------------------------------
# Scenario 7: Parallel independent training jobs (different tmux_ids)
# ---------------------------------------------------------------------------


async def test_parallel_independent_training_jobs():
    """Two independent training jobs (different tmux_ids) can be claimed concurrently."""
    db, fake = _db()
    job_a = _enqueue(fake, "python train.py --model A", tmux_id="train-a")
    job_b = _enqueue(fake, "python train.py --model B", tmux_id="train-b")

    # Both should be claimable since they use different tmux_ids
    cmd_a = await db.claim_next("tuning-runner-1", 60)
    cmd_b = await db.claim_next("tuning-runner-1", 60)

    assert cmd_a is not None and cmd_b is not None
    claimed_ids = {cmd_a.id, cmd_b.id}
    assert claimed_ids == {job_a, job_b}
