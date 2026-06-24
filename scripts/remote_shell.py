#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Run a one-off shell command on the remote AReaL host via db_bridge transport.

Uses the same Supabase remote-shell channel as CLI training (CLITrainTransport).
Intended for ops: inspect GPU processes, then kill a stale training PID.

Usage:
  # Load credentials (SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY / BRIDGE_USER_ID)
  #   from an env file, then run a command:
  python scripts/remote_shell.py --env-file scenarios/demo.live.env -- nvidia-smi

  # Inspect just the PID/utilization table:
  python scripts/remote_shell.py --env-file scenarios/demo.live.env -- \
    "nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv"

  # Kill a specific PID once you've identified it (explicit, no wildcards):
  python scripts/remote_shell.py --env-file scenarios/demo.live.env -- "kill -TERM 12345"

  # Force kill if TERM did not work:
  python scripts/remote_shell.py --env-file scenarios/demo.live.env -- "kill -KILL 12345"

Notes:
  - The remote `run_shell_runner` must be active on the AReaL host to claim the command.
  - This sends a raw shell command; double-check the PID before killing.
"""
from __future__ import annotations

import argparse
import os
import sys
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
for _entry in (str(REPO_ROOT), str(REPO_ROOT / "modes" / "self-coaching")):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)


def _load_env_file(path: Path) -> None:
    from loop_env import load_env_file

    load_env_file(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a shell command on the remote AReaL host (db_bridge)")
    parser.add_argument("--env-file", type=Path, default=None, help="Env file with Supabase credentials")
    parser.add_argument("--cwd", default=None, help="Remote working directory (default: CLI_TRAIN_CWD)")
    parser.add_argument("--timeout", type=int, default=120, help="Command timeout in seconds (default 120)")
    parser.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        help="Command to run remotely (prefix with -- to stop flag parsing)",
    )
    args = parser.parse_args(argv)

    if args.env_file is not None:
        _load_env_file(args.env_file)

    cmd_parts = [c for c in args.command if c != "--"]
    if not cmd_parts:
        print("ERROR: no command provided. Example: -- nvidia-smi", file=sys.stderr)
        return 2
    command = " ".join(cmd_parts) if len(cmd_parts) > 1 else cmd_parts[0]

    from services.adapters.cli_train_commands import resolve_train_cwd
    from services.adapters.cli_train_transport import CLITrainTransport

    cwd = args.cwd or resolve_train_cwd()
    print(f"==> remote host: {os.environ.get('SUPABASE_URL', '(unset)')}")
    print(f"==> cwd: {cwd}")
    print(f"==> command: {command}")
    print(f"==> timeout: {args.timeout}s (runner must be active to claim)")
    print()

    transport = CLITrainTransport.from_env(poll_timeout_s=float(args.timeout))
    try:
        row = transport.send_and_wait(
            command,
            cwd=cwd,
            tmux_id=f"remote-shell-{uuid.uuid4().hex[:8]}",
            timeout_seconds=args.timeout,
        )
    finally:
        transport.close()

    status = row.get("status")
    exit_code = row.get("exit_code")
    print(f"status: {status} exit_code: {exit_code}")
    stdout = row.get("stdout_tail") or ""
    stderr = row.get("stderr_tail") or ""
    if stdout:
        print("\n--- stdout ---")
        print(stdout)
    if stderr:
        print("\n--- stderr ---", file=sys.stderr)
        print(stderr, file=sys.stderr)

    return 0 if status == "SUCCEEDED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
