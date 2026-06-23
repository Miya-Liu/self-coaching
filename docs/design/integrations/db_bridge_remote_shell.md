# db_bridge Remote Shell — Integration Guide

How the `auto-upgrade` coaching system triggers model tuning on the AReaL GPU
host via the `db_bridge` remote shell runner.

## Overview

The AReaL training host and the le-agent/coaching host cannot reach each other
over SSH, but they share a Supabase (Postgres) database. The `db_bridge` remote
shell module uses this shared database as a command queue:

```
┌─────────────────────┐       ┌────────────────┐       ┌─────────────────────┐
│  Coaching host      │       │   Supabase DB  │       │   AReaL GPU host    │
│  (auto-upgrade)     │       │                │       │                     │
│                     │       │  areal_remote  │       │  run_shell_runner   │
│  insert PENDING ──────────>│  _commands     │<────────  polls & claims    │
│                     │       │                │       │                     │
│  poll status   <──────────-│  status/logs   │────────>  executes in tmux  │
│                     │       │                │       │                     │
└─────────────────────┘       └────────────────┘       └─────────────────────┘
```

## Prerequisites

| Requirement | Details |
|-------------|---------|
| Supabase instance | Self-hosted at `http://82.157.184.89:54321` |
| Schema applied | `schema.sql` creates `areal_remote_commands` table + RPCs |
| Runner active | `run_shell_runner` running on AReaL host with `AREAL_REMOTE_SHELL_ENABLED=true` |
| Credentials | `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` in `.env` |
| User ID | `BRIDGE_USER_ID` set (or pass `X-Bridge-User-Id` header) |

## Quick Start

### 1. Send a command (from this repo's Windows machine)

```powershell
cd services\LoRA\db_bridge
uv run python scripts/send_command.py "echo hello" --timeout 30
```

### 2. Send a training command

```powershell
uv run python scripts/send_command.py "python gsm8k_rl.py" `
    --cwd /dfs/share-groups/letrain/zhoujie/AReaL-main `
    --timeout 3600 `
    --tmux-id train-lora-run1
```

### 3. Multi-step pipeline (same tmux session)

Use the same `--tmux-id` for sequential steps that share shell state:

```powershell
uv run python scripts/send_command.py "cd /workspace && source venv/bin/activate" --tmux-id my-pipeline
uv run python scripts/send_command.py "python prepare_data.py" --tmux-id my-pipeline
uv run python scripts/send_command.py "python train.py --config lora.yaml" --tmux-id my-pipeline --timeout 3600
```

### 4. Probe connectivity (dry run, no side effects)

```powershell
uv run python scripts/probe_connectivity.py
```

## Command Lifecycle

```
PENDING → CLAIMED → RUNNING → SUCCEEDED / FAILED / TIMED_OUT / CANCELLED
```

| Status | Meaning |
|--------|---------|
| `PENDING` | Waiting for runner to pick up |
| `CLAIMED` | Runner claimed the row, about to start |
| `RUNNING` | Executing in tmux, heartbeating logs |
| `SUCCEEDED` | Exit code 0 |
| `FAILED` | Non-zero exit code |
| `TIMED_OUT` | Exceeded `timeout_seconds`, session killed |
| `CANCELLED` | Backend requested cancellation |
| `STALE` | Runner lease expired (crash/disconnect) |

## Programmatic Usage (Python)

To integrate from the coaching pipeline code:

```python
import httpx
import uuid
import os

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
USER_ID = os.environ["BRIDGE_USER_ID"]

async def send_training_command(
    command: str,
    *,
    cwd: str = "/dfs/share-groups/letrain/zhoujie/AReaL-main",
    tmux_id: str = "training",
    timeout_seconds: int = 3600,
) -> str:
    """Enqueue a shell command on the AReaL host. Returns the command ID."""
    cmd_id = str(uuid.uuid4())
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{SUPABASE_URL}/rest/v1/areal_remote_commands",
            headers=headers,
            json={
                "id": cmd_id,
                "user_id": USER_ID,
                "tmux_id": tmux_id,
                "command": command,
                "cwd": cwd,
                "timeout_seconds": timeout_seconds,
                "status": "PENDING",
            },
        )
        resp.raise_for_status()
    return cmd_id


async def poll_command_status(cmd_id: str) -> dict:
    """Poll a command row. Returns the full row dict."""
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
    }
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{SUPABASE_URL}/rest/v1/areal_remote_commands",
            headers=headers,
            params={"id": f"eq.{cmd_id}", "select": "*"},
        )
        resp.raise_for_status()
        rows = resp.json()
        return rows[0] if rows else {}
```

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Database as transport | Hosts can't reach each other over SSH; shared Supabase is the only common channel |
| tmux for execution | Named sessions, log capture, decisive termination; not for sandboxing |
| Sequential per `tmux_id` | Same tmux_id = same remote terminal, commands inherit shell state |
| Different `tmux_id` = parallel | Independent jobs run concurrently (up to `MAX_CONCURRENCY=4`) |
| Feature-flagged | `AREAL_REMOTE_SHELL_ENABLED=false` by default; runner refuses to claim |
| Bounded logs | Only last 64KB of stdout/stderr captured per command |

## Environment Variables

Set in `services/lora/db_bridge/.env`:

| Variable | Required | Purpose |
|----------|----------|---------|
| `SUPABASE_URL` | ✓ | Shared Supabase instance URL |
| `SUPABASE_SERVICE_ROLE_KEY` | ✓ | Service role JWT (bypasses RLS) |
| `BRIDGE_USER_ID` | ✓ | Your user UUID for command ownership |

The runner on the AReaL host reads its own `.env.areal` with additional config
(poll interval, lease, timeouts, concurrency). See
`services/lora/db_bridge/README.md` for the full variable table.

## Verified Connectivity (2026-06-16)

| Check | Result |
|-------|--------|
| TCP to `82.157.184.89:54321` | ✅ |
| PostgREST REST API | ✅ HTTP 200 |
| `areal_remote_commands` table | ✅ accessible |
| `areal_shell_claim_next` RPC | ✅ callable |
| Insert → runner claims → executes → returns stdout | ✅ |
| Remote host | `root@workspace`, cwd `/dfs/share-groups/letrain/zhoujie/AReaL-main` |

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/probe_connectivity.py` | Test network + DB + RPC reachability (safe, cleans up) |
| `scripts/send_command.py` | Send a command and poll until completion with live log output |

## Security Notes

- The runner executes **arbitrary shell code** as root on the AReaL host.
- Only enable on trusted hosts where callers are authorized.
- `SUPABASE_SERVICE_ROLE_KEY` bypasses row-level security — keep it out of git.
- The `.env` file is gitignored.
- Logs may contain secrets; treat `stdout_tail`/`stderr_tail` as user-private.

## Related Docs

- [db_bridge README](../../../services/lora/db_bridge/README.md) — full module documentation
- [AERL integration](aerl.md) — HTTP-based training client (alternative path)
- [AReaL CLI training request](areal_cli_training_request.md) — `TRAINING_COMPLETE` marker for coaching host
- [architecture.md](../architecture.md) — overall system design
