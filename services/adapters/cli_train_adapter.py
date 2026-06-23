# SPDX-License-Identifier: MIT
"""CLI train adapter: trigger remote training via db_bridge and collect results."""

from __future__ import annotations

from typing import Any

from .cli_train_commands import TrainCommandSpec, build_train_command_spec
from .cli_train_errors import TrainerCLIError, TrainerTimeoutError
from .cli_train_output import parse_training_marker, resolve_candidate
from .cli_train_transport import CLITrainTransport


def map_cli_train_result(
    row: dict[str, Any],
    *,
    spec: TrainCommandSpec,
    marker: dict[str, Any],
    pipeline: str,
) -> dict[str, Any]:
    """Map a terminal command row to the loop train() result shape."""
    candidate = resolve_candidate(marker, run_id=spec.run_id, pipeline=pipeline)
    stdout = row.get("stdout_tail") or ""
    stderr = row.get("stderr_tail") or ""
    return {
        "status": "trained",
        "run_id": spec.run_id,
        "cmd_id": str(row.get("id") or ""),
        "candidate": candidate,
        "candidate_model_id": candidate,
        "terminal_status": str(row.get("status") or ""),
        "exit_code": row.get("exit_code"),
        "stdout_tail": stdout,
        "stderr_tail": stderr,
        "log_file": spec.log_file,
        "metrics": marker.get("metrics"),
        "config_path": spec.config_path,
        "_train_backend": "cli",
    }


def _raise_for_terminal_status(row: dict[str, Any], *, cmd_id: str) -> None:
    status = str(row.get("status") or "")
    if status == "SUCCEEDED":
        return
    if status == "TIMED_OUT":
        raise TrainerTimeoutError(
            f"remote training command {cmd_id} timed out",
            cmd_id=cmd_id,
            body=row,
        )
    stderr = row.get("stderr_tail") or ""
    error_message = row.get("error_message") or ""
    detail = stderr.strip() or str(error_message).strip() or f"terminal status={status!r}"
    raise TrainerCLIError(
        f"remote training command {cmd_id} failed: {detail}",
        terminal_status=status or None,
        exit_code=row.get("exit_code"),
        body=row,
    )


class CLITrainAdapter:
    """train() backed by db_bridge remote shell commands."""

    def __init__(self, transport: CLITrainTransport | None = None):
        self._transport = transport

    def _transport_or_env(self) -> CLITrainTransport:
        if self._transport is not None:
            return self._transport
        return CLITrainTransport.from_env()

    def health(self) -> dict[str, Any]:
        """Report CLI train adapter availability (no remote probe)."""
        return {
            "status": "ok",
            "backend": "cli",
            "transport": "db_bridge_remote_shell",
        }

    def train(
        self,
        *,
        pipeline: str = "sft",
        dataset: str | None = None,
        base_model: str = "mock-base",
        coaching_root: str | None = None,
        agent_id: str | None = None,
    ) -> dict[str, Any]:
        """Dispatch training CLI to AReaL host, poll to completion, return result."""
        del coaching_root, agent_id  # v1: fixed remote config; dataset ignored (CT-D01)
        del dataset

        spec = build_train_command_spec(pipeline=pipeline, base_model=base_model)
        transport = self._transport_or_env()
        try:
            row = transport.send_and_wait(
                spec.command,
                cwd=spec.cwd,
                tmux_id=spec.tmux_id,
                timeout_seconds=spec.timeout_seconds,
            )
        except TrainerTimeoutError as exc:
            if exc.cmd_id:
                try:
                    transport.request_cancel(exc.cmd_id)
                except Exception:
                    pass
            raise
        cmd_id = str(row.get("id") or "")
        _raise_for_terminal_status(row, cmd_id=cmd_id or spec.run_id)

        marker = parse_training_marker(row.get("stdout_tail") or "")
        return map_cli_train_result(row, spec=spec, marker=marker, pipeline=pipeline)
