# SPDX-License-Identifier: MIT
"""Build remote training shell commands from environment configuration."""

from __future__ import annotations

import os
import re
import uuid
from dataclasses import dataclass

DEFAULT_SCRIPT = "customized_areal/tpfc/scripts/train_tpfc_tree_search.py"
DEFAULT_CONFIG = (
    "customized_areal/tpfc/configs/config_tpfc_Qwen3-5L-9B_tree_search_self_play.yaml"
)
DEFAULT_CWD = "/dfs/share-groups/letrain/zhoujie/AReaL-main"
DEFAULT_TMUX_PREFIX = "train-"


def _normalize_key(value: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", value.upper()).strip("_")


def resolve_train_cwd() -> str:
    return os.environ.get("CLI_TRAIN_CWD", DEFAULT_CWD)


def resolve_train_script() -> str:
    return os.environ.get("CLI_TRAIN_SCRIPT", DEFAULT_SCRIPT)


def resolve_tmux_prefix() -> str:
    return os.environ.get("CLI_TRAIN_TMUX_PREFIX", DEFAULT_TMUX_PREFIX)


def resolve_command_timeout_seconds() -> int:
    return int(os.environ.get("CLI_TRAIN_TIMEOUT", os.environ.get("AERL_TIMEOUT_S", "3600")))


def resolve_config_path(*, pipeline: str, base_model: str) -> str:
    """Resolve remote config YAML path from env (v1: fixed map, ignores dataset)."""
    specific = os.environ.get(
        f"CLI_TRAIN_CONFIG_{_normalize_key(pipeline)}_{_normalize_key(base_model)}"
    )
    if specific:
        return specific
    pipeline_key = f"CLI_TRAIN_CONFIG_{_normalize_key(pipeline)}"
    if os.environ.get(pipeline_key):
        return os.environ[pipeline_key]
    return os.environ.get("CLI_TRAIN_CONFIG", DEFAULT_CONFIG)


def new_run_id() -> str:
    return f"cli-train-{uuid.uuid4().hex[:12]}"


def new_tmux_id(*, run_id: str, prefix: str | None = None) -> str:
    resolved_prefix = prefix if prefix is not None else resolve_tmux_prefix()
    slug = run_id.removeprefix("cli-train-")
    return f"{resolved_prefix}{slug}"


def log_file_name(run_id: str) -> str:
    return f"training_{run_id}.log"


@dataclass(frozen=True)
class TrainCommandSpec:
    run_id: str
    command: str
    cwd: str
    tmux_id: str
    config_path: str
    log_file: str
    timeout_seconds: int


def build_train_command_spec(
    *,
    pipeline: str = "sft",
    base_model: str = "mock-base",
    run_id: str | None = None,
) -> TrainCommandSpec:
    """Build the remote shell command for a training run."""
    resolved_run_id = run_id or new_run_id()
    script = resolve_train_script()
    config_path = resolve_config_path(pipeline=pipeline, base_model=base_model)
    log_file = log_file_name(resolved_run_id)
    command = (
        f"uv run {script} --config {config_path} "
        f"2>&1 | tee {log_file}"
    )
    return TrainCommandSpec(
        run_id=resolved_run_id,
        command=command,
        cwd=resolve_train_cwd(),
        tmux_id=new_tmux_id(run_id=resolved_run_id),
        config_path=config_path,
        log_file=log_file,
        timeout_seconds=resolve_command_timeout_seconds(),
    )
