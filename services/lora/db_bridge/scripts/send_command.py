#!/usr/bin/env python3
"""Send a real command via db_bridge remote shell and poll until completion.

Inserts a command into `areal_remote_commands`, then polls the row until it
reaches a terminal status, printing live log tails along the way.

Usage:
    uv run python scripts/send_command.py "echo hello from AReaL"
    uv run python scripts/send_command.py "nvidia-smi" --cwd /root
    uv run python scripts/send_command.py "ls -la" --tmux-id test-session --timeout 30
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
import uuid
from pathlib import Path

DB_BRIDGE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = DB_BRIDGE_ROOT.parents[2]
for path in (REPO_ROOT, DB_BRIDGE_ROOT):
    text = str(path)
    if text not in sys.path:
        sys.path.insert(0, text)


def _load_env(path: str) -> None:
    """Load a .env file into os.environ (simple key=value parser)."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            if key and not key.startswith("#"):
                os.environ.setdefault(key, value)


def _print_progress(row: dict, *, last_stdout: str, last_stderr: str) -> tuple[str, str]:
    stdout = row.get("stdout_tail") or ""
    stderr = row.get("stderr_tail") or ""
    status = row.get("status", "?")
    ts = time.strftime("%H:%M:%S")

    if stdout != last_stdout:
        new_lines = stdout[len(last_stdout) :]
        if new_lines.strip():
            print(f"[{ts}] [stdout] {new_lines.rstrip()}")
        last_stdout = stdout

    if stderr != last_stderr:
        new_lines = stderr[len(last_stderr) :]
        if new_lines.strip():
            print(f"[{ts}] [stderr] {new_lines.rstrip()}")
        last_stderr = stderr

    from services.adapters.cli_train_transport import TERMINAL_STATUSES

    if status not in TERMINAL_STATUSES:
        print(f"[{ts}] status={status} log_bytes={row.get('log_bytes', 0)}")

    return last_stdout, last_stderr


async def main() -> int:
    parser = argparse.ArgumentParser(description="Send a command via db_bridge remote shell")
    parser.add_argument("command", help="Shell command to execute on the AReaL host")
    parser.add_argument("--cwd", default=None, help="Working directory on remote host")
    parser.add_argument("--tmux-id", default=None, help="tmux session ID (default: random)")
    parser.add_argument("--timeout", type=int, default=60, help="Command timeout in seconds")
    parser.add_argument("--poll-interval", type=float, default=2.0, help="Poll interval (seconds)")
    parser.add_argument("--user-id", default=None, help="User UUID (default: from BRIDGE_USER_ID)")
    args = parser.parse_args()

    _load_env(str(DB_BRIDGE_ROOT / ".env"))

    from services.adapters.cli_train_errors import TransportError, TrainerTimeoutError
    from services.adapters.cli_train_transport import CLITrainTransport

    user_id = args.user_id or os.environ.get("BRIDGE_USER_ID")
    if user_id:
        os.environ["BRIDGE_USER_ID"] = user_id

    try:
        transport = CLITrainTransport.from_env(
            poll_interval_s=args.poll_interval,
            poll_timeout_s=float(args.timeout),
        )
    except TransportError as exc:
        print(f"ERROR: {exc}")
        return 1

    tmux_id = args.tmux_id or f"cmd-{uuid.uuid4().hex[:8]}"
    cmd_id = str(uuid.uuid4())

    print(f"{'='*70}")
    print("  Sending command to AReaL host via db_bridge")
    print(f"{'='*70}")
    print(f"  Command : {args.command}")
    print(f"  CWD     : {args.cwd or '(default)'}")
    print(f"  tmux_id : {tmux_id}")
    print(f"  Timeout : {args.timeout}s")
    print(f"  cmd_id  : {cmd_id}")
    print(f"{'='*70}")
    print()

    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] Enqueued command (status=PENDING)")

    last_stdout = ""
    last_stderr = ""

    def on_poll(row: dict) -> None:
        nonlocal last_stdout, last_stderr
        last_stdout, last_stderr = _print_progress(
            row,
            last_stdout=last_stdout,
            last_stderr=last_stderr,
        )

    try:
        row = await asyncio.to_thread(
            transport.send_and_wait,
            args.command,
            cwd=args.cwd,
            tmux_id=tmux_id,
            timeout_seconds=args.timeout,
            cmd_id=cmd_id,
            on_poll=on_poll,
        )
    except TransportError as exc:
        print(f"ERROR: Transport failed: {exc}")
        if exc.body:
            print(str(exc.body)[:500])
        return 1
    except TrainerTimeoutError as exc:
        print(f"ERROR: Polling timed out waiting for command to complete.")
        if exc.body:
            print(f"  Last status: {exc.body.get('status')}")
        return 1
    finally:
        transport.close()

    print()
    print(f"{'='*70}")
    print("  COMMAND COMPLETED")
    print(f"{'='*70}")
    print(f"  Status     : {row.get('status')}")
    print(f"  Exit code  : {row.get('exit_code')}")
    print(f"  Log bytes  : {row.get('log_bytes', 0)}")
    if row.get("error_message"):
        print(f"  Error      : {row['error_message']}")
    print(f"  Started    : {row.get('started_at', '?')}")
    print(f"  Finished   : {row.get('finished_at', '?')}")
    print()

    stdout = row.get("stdout_tail") or ""
    stderr = row.get("stderr_tail") or ""
    if stdout.strip():
        print("--- stdout ---")
        print(stdout.rstrip())
        print()
    if stderr.strip():
        print("--- stderr ---")
        print(stderr.rstrip())
        print()

    return 0 if row.get("status") == "SUCCEEDED" else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
