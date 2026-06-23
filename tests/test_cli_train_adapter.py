# SPDX-License-Identifier: MIT
"""Unit tests for CLI train command builder, output parser, and adapter."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from services.adapters.cli_train_adapter import CLITrainAdapter, map_cli_train_result  # noqa: E402
from services.adapters.cli_train_commands import (  # noqa: E402
    build_train_command_spec,
    log_file_name,
    resolve_config_path,
)
from services.adapters.cli_train_errors import TrainerCLIError, TrainerTimeoutError  # noqa: E402
from services.adapters.cli_train_output import parse_training_marker, resolve_candidate  # noqa: E402


def test_resolve_config_path_specific_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(
        "CLI_TRAIN_CONFIG_GRPO_QWEN3_8B",
        "customized_areal/tpfc/configs/grpo.yaml",
    )
    assert resolve_config_path(pipeline="grpo", base_model="qwen3-8b") == (
        "customized_areal/tpfc/configs/grpo.yaml"
    )


def test_resolve_config_path_default(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("CLI_TRAIN_CONFIG_GRPO_QWEN3_8B", raising=False)
    monkeypatch.setenv("CLI_TRAIN_CONFIG", "configs/default.yaml")
    assert resolve_config_path(pipeline="sft", base_model="qwen3-8b") == "configs/default.yaml"


def test_build_train_command_spec(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CLI_TRAIN_SCRIPT", "scripts/train.py")
    monkeypatch.setenv("CLI_TRAIN_CONFIG", "configs/run.yaml")
    monkeypatch.setenv("CLI_TRAIN_CWD", "/workspace/areal")
    monkeypatch.setenv("CLI_TRAIN_TIMEOUT", "7200")

    spec = build_train_command_spec(
        pipeline="grpo",
        base_model="qwen3-8b",
        run_id="cli-train-abc123",
    )
    assert spec.run_id == "cli-train-abc123"
    assert spec.cwd == "/workspace/areal"
    assert spec.timeout_seconds == 7200
    assert spec.config_path == "configs/run.yaml"
    assert spec.log_file == log_file_name("cli-train-abc123")
    assert "uv run scripts/train.py --config configs/run.yaml" in spec.command
    assert spec.command.endswith("| tee training_cli-train-abc123.log")
    assert spec.tmux_id == "train-abc123"


def test_parse_training_marker_full_line():
    stdout = (
        "Epoch 3/3 loss=0.89\n"
        "TRAINING_COMPLETE checkpoint=/output/lora-adapter "
        'model_id=ckpt-grpo-abc123 metrics={"train_loss":0.89,"reward_mean":0.42}\n'
    )
    marker = parse_training_marker(stdout)
    assert marker["checkpoint"] == "/output/lora-adapter"
    assert marker["model_id"] == "ckpt-grpo-abc123"
    assert marker["metrics"] == {"train_loss": 0.89, "reward_mean": 0.42}


def test_parse_training_marker_missing_returns_empty():
    assert parse_training_marker("training logs only\n") == {}


def test_resolve_candidate_prefers_model_id():
    candidate = resolve_candidate(
        {"model_id": "ckpt-1", "checkpoint": "/output/a"},
        run_id="cli-train-deadbeef",
        pipeline="grpo",
    )
    assert candidate == "ckpt-1"


def test_resolve_candidate_fallback():
    candidate = resolve_candidate({}, run_id="cli-train-deadbeef", pipeline="sft")
    assert candidate == "cli-train-sft-deadbeef"


def test_map_cli_train_result_shape():
    spec = build_train_command_spec(run_id="cli-train-abc123", pipeline="grpo", base_model="x")
    row = {
        "id": "cmd-uuid",
        "status": "SUCCEEDED",
        "exit_code": 0,
        "stdout_tail": "TRAINING_COMPLETE checkpoint=/out model_id=ckpt-1 metrics={}\n",
        "stderr_tail": "",
    }
    marker = parse_training_marker(row["stdout_tail"])
    result = map_cli_train_result(row, spec=spec, marker=marker, pipeline="grpo")
    assert result["status"] == "trained"
    assert result["run_id"] == "cli-train-abc123"
    assert result["cmd_id"] == "cmd-uuid"
    assert result["candidate"] == "ckpt-1"
    assert result["_train_backend"] == "cli"
    assert result["log_file"] == "training_cli-train-abc123.log"


def test_adapter_train_success():
    transport = MagicMock()
    transport.send_and_wait.return_value = {
        "id": "cmd-uuid",
        "status": "SUCCEEDED",
        "exit_code": 0,
        "stdout_tail": (
            "TRAINING_COMPLETE checkpoint=/output/adapter model_id=ckpt-live metrics={}\n"
        ),
        "stderr_tail": "",
    }

    adapter = CLITrainAdapter(transport=transport)
    result = adapter.train(pipeline="grpo", base_model="qwen3-8b", dataset="/local/train.jsonl")

    transport.send_and_wait.assert_called_once()
    call_args = transport.send_and_wait.call_args
    command = call_args.args[0]
    assert "uv run" in command
    assert "--config" in command
    assert "| tee training_cli-train-" in command
    assert call_args.kwargs["cwd"]
    assert str(call_args.kwargs["tmux_id"]).startswith("train-")
    assert result["status"] == "trained"
    assert result["candidate"] == "ckpt-live"
    assert result["terminal_status"] == "SUCCEEDED"
    assert result["run_id"].startswith("cli-train-")


def test_adapter_train_failed_raises():
    transport = MagicMock()
    transport.send_and_wait.return_value = {
        "id": "cmd-uuid",
        "status": "FAILED",
        "exit_code": 1,
        "stdout_tail": "",
        "stderr_tail": "FileNotFoundError: config missing",
    }

    adapter = CLITrainAdapter(transport=transport)
    with pytest.raises(TrainerCLIError, match="FileNotFoundError") as exc:
        adapter.train(pipeline="grpo")
    assert exc.value.terminal_status == "FAILED"
    assert exc.value.exit_code == 1


def test_adapter_train_timed_out_raises():
    transport = MagicMock()
    transport.send_and_wait.return_value = {
        "id": "cmd-uuid",
        "status": "TIMED_OUT",
        "exit_code": None,
        "stdout_tail": "partial\n",
        "stderr_tail": "",
    }

    adapter = CLITrainAdapter(transport=transport)
    with pytest.raises(TrainerTimeoutError, match="timed out"):
        adapter.train(pipeline="grpo")


def test_adapter_poll_timeout_requests_cancel():
    transport = MagicMock()
    transport.send_and_wait.side_effect = TrainerTimeoutError(
        "poll budget exceeded",
        cmd_id="cmd-timeout-1",
    )
    transport.request_cancel.return_value = {"ok": True, "status": "CANCEL_REQUESTED"}

    adapter = CLITrainAdapter(transport=transport)
    with pytest.raises(TrainerTimeoutError, match="poll budget"):
        adapter.train(pipeline="grpo")

    transport.request_cancel.assert_called_once_with("cmd-timeout-1")


def test_adapter_poll_timeout_cancel_failure_still_raises():
    transport = MagicMock()
    transport.send_and_wait.side_effect = TrainerTimeoutError(
        "poll budget exceeded",
        cmd_id="cmd-timeout-2",
    )
    transport.request_cancel.side_effect = RuntimeError("rpc down")

    adapter = CLITrainAdapter(transport=transport)
    with pytest.raises(TrainerTimeoutError, match="poll budget"):
        adapter.train(pipeline="grpo")

    transport.request_cancel.assert_called_once_with("cmd-timeout-2")


def test_adapter_ignores_dataset_in_v1():
    transport = MagicMock()
    transport.send_and_wait.return_value = {
        "id": "cmd-uuid",
        "status": "SUCCEEDED",
        "exit_code": 0,
        "stdout_tail": "",
        "stderr_tail": "",
    }
    adapter = CLITrainAdapter(transport=transport)
    adapter.train(pipeline="sft", dataset="/should/be/ignored.jsonl")
    command = transport.send_and_wait.call_args.args[0]
    assert "/should/be/ignored" not in command
