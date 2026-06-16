#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Smoke test: CLITrainAdapter against live Supabase + run_shell_runner.

Usage:
  python scripts/cli_train_smoke.py --env-file scenarios/demo.cli-train.env --probe
  python scripts/cli_train_smoke.py --env-file scenarios/demo.cli-train.env --pipeline grpo
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SC_ROOT = REPO_ROOT / "modes" / "self-coaching"
if str(SC_ROOT) not in sys.path:
    sys.path.insert(0, str(SC_ROOT))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from loop_env import load_env_file  # noqa: E402

from services.adapters.cli_train_adapter import CLITrainAdapter  # noqa: E402
from services.adapters.cli_train_commands import resolve_train_cwd  # noqa: E402
from services.adapters.cli_train_errors import (  # noqa: E402
    CLITrainError,
    TrainerCLIError,
    TrainerTimeoutError,
    TransportError,
)
from services.adapters.cli_train_transport import CLITrainTransport  # noqa: E402


def _probe_command() -> str:
    return (
        "echo TRAINING_COMPLETE checkpoint=/tmp/cli-train-smoke "
        "model_id=smoke-probe metrics={}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="CLI train adapter smoke test")
    parser.add_argument(
        "--env-file",
        type=Path,
        default=None,
        help="Optional dotenv file (e.g. scenarios/demo.cli-train.env)",
    )
    parser.add_argument("--pipeline", default="grpo", help="Training pipeline id")
    parser.add_argument("--base-model", default="qwen3-8b", help="Base model label for config map")
    parser.add_argument(
        "--probe",
        action="store_true",
        help="Run a short echo command instead of full remote training",
    )
    args = parser.parse_args()

    if args.env_file is not None:
        load_env_file(args.env_file)

    if args.probe:
        try:
            transport = CLITrainTransport.from_env()
            row = transport.send_and_wait(
                _probe_command(),
                cwd=resolve_train_cwd(),
                tmux_id="cli-train-smoke-probe",
                timeout_seconds=120,
            )
            transport.close()
        except (TransportError, TrainerTimeoutError, TrainerCLIError) as exc:
            print(f"cli_train_smoke: FAIL probe — {exc}", file=sys.stderr)
            return 1
        print(json.dumps(row, indent=2, sort_keys=True, default=str))
        if row.get("status") != "SUCCEEDED":
            print("cli_train_smoke: FAIL probe did not succeed", file=sys.stderr)
            return 1
        print("cli_train_smoke: PASS (probe)")
        return 0

    adapter = CLITrainAdapter()
    try:
        result = adapter.train(pipeline=args.pipeline, base_model=args.base_model)
    except (CLITrainError, TransportError) as exc:
        print(f"cli_train_smoke: FAIL — {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    if result.get("status") != "trained":
        print("cli_train_smoke: FAIL training did not return trained status", file=sys.stderr)
        return 1
    print("cli_train_smoke: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
