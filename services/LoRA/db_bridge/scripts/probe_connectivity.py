#!/usr/bin/env python3
"""Probe script: test whether the db_bridge Supabase instance is reachable
and the remote shell interface can accept commands.

This script performs real network calls to validate:
  1. TCP connectivity to the Supabase host
  2. REST API reachability (PostgREST health)
  3. areal_remote_commands table accessibility
  4. areal_shell_claim_next RPC availability
  5. Insert a test command row and verify it's readable

Usage:
    Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY, then:
        uv run python scripts/probe_connectivity.py

    Or pass them as arguments:
        uv run python scripts/probe_connectivity.py \
            --url http://82.157.184.89:54321 \
            --key <service-role-key>
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import socket
import sys
import time
import uuid
from urllib.parse import urlparse

# Add parent so we can import db_bridge
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def log(level: str, msg: str) -> None:
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] {level:5s} | {msg}")


def log_ok(msg: str) -> None:
    log("OK", msg)


def log_fail(msg: str) -> None:
    log("FAIL", msg)


def log_info(msg: str) -> None:
    log("INFO", msg)


def log_warn(msg: str) -> None:
    log("WARN", msg)


# ---------------------------------------------------------------------------
# Step 1: TCP connectivity
# ---------------------------------------------------------------------------


def probe_tcp(host: str, port: int, timeout: float = 5.0) -> bool:
    log_info(f"Testing TCP connectivity to {host}:{port} ...")
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
        sock.close()
        log_ok(f"TCP connection to {host}:{port} succeeded")
        return True
    except OSError as exc:
        log_fail(f"TCP connection to {host}:{port} failed: {exc}")
        return False


# ---------------------------------------------------------------------------
# Step 2-5: Supabase REST API + RPC tests
# ---------------------------------------------------------------------------


async def probe_supabase(url: str, key: str) -> dict[str, bool]:
    """Run all Supabase-level probes. Returns a results dict."""
    import httpx

    results: dict[str, bool] = {}
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    rest_url = f"{url}/rest/v1"

    async with httpx.AsyncClient(timeout=10.0) as client:
        # --- Step 2: REST API health ---
        log_info(f"Testing REST API at {rest_url} ...")
        try:
            resp = await client.get(f"{rest_url}/", headers=headers)
            log_ok(f"REST API responded: HTTP {resp.status_code}")
            results["rest_api_reachable"] = resp.status_code < 500
        except httpx.HTTPError as exc:
            log_fail(f"REST API unreachable: {exc}")
            results["rest_api_reachable"] = False

        # --- Step 3: areal_remote_commands table accessible ---
        log_info("Testing areal_remote_commands table access ...")
        try:
            resp = await client.get(
                f"{rest_url}/areal_remote_commands",
                headers={**headers, "Prefer": "count=exact"},
                params={"select": "id", "limit": "1"},
            )
            if resp.status_code in (200, 206):
                log_ok(
                    f"Table areal_remote_commands accessible (HTTP {resp.status_code})"
                )
                results["table_accessible"] = True
            elif resp.status_code == 404:
                log_fail(
                    "Table areal_remote_commands not found (404). "
                    "Run schema.sql first."
                )
                results["table_accessible"] = False
            else:
                body = resp.text[:200]
                log_fail(
                    f"Table access returned HTTP {resp.status_code}: {body}"
                )
                results["table_accessible"] = False
        except httpx.HTTPError as exc:
            log_fail(f"Table access failed: {exc}")
            results["table_accessible"] = False

        # --- Step 4: areal_shell_claim_next RPC exists ---
        log_info("Testing areal_shell_claim_next RPC ...")
        try:
            resp = await client.post(
                f"{rest_url}/rpc/areal_shell_claim_next",
                headers=headers,
                json={"p_runner_id": "probe-test", "p_lease_seconds": 10},
            )
            if resp.status_code in (200, 204):
                log_ok(
                    f"RPC areal_shell_claim_next callable (HTTP {resp.status_code}, "
                    f"result={resp.text[:100]})"
                )
                results["rpc_claim_available"] = True
            elif resp.status_code == 404:
                log_fail(
                    "RPC areal_shell_claim_next not found (404). "
                    "Run schema.sql to create the function."
                )
                results["rpc_claim_available"] = False
            else:
                log_warn(
                    f"RPC returned HTTP {resp.status_code}: {resp.text[:200]}"
                )
                results["rpc_claim_available"] = resp.status_code < 500
        except httpx.HTTPError as exc:
            log_fail(f"RPC call failed: {exc}")
            results["rpc_claim_available"] = False

        # --- Step 5: Insert a probe command and read it back ---
        log_info("Testing insert + read of a probe command ...")
        probe_id = str(uuid.uuid4())
        probe_user = "00000000-0000-0000-0000-000000000099"
        try:
            insert_body = {
                "id": probe_id,
                "user_id": probe_user,
                "tmux_id": "probe-test",
                "command": "echo probe-connectivity-test",
                "cwd": "/tmp",
                "timeout_seconds": 10,
                "status": "PENDING",
            }
            resp = await client.post(
                f"{rest_url}/areal_remote_commands",
                headers=headers,
                json=insert_body,
            )
            if resp.status_code in (200, 201):
                log_ok(f"Inserted probe command id={probe_id}")
            else:
                log_fail(
                    f"Insert failed HTTP {resp.status_code}: {resp.text[:200]}"
                )
                results["insert_and_read"] = False
                return results

            # Read it back
            resp = await client.get(
                f"{rest_url}/areal_remote_commands",
                headers=headers,
                params={"id": f"eq.{probe_id}", "select": "id,status,command"},
            )
            if resp.status_code == 200:
                rows = resp.json()
                if rows and rows[0]["id"] == probe_id:
                    log_ok(
                        f"Read back probe row: status={rows[0]['status']}, "
                        f"command={rows[0]['command']}"
                    )
                    results["insert_and_read"] = True
                else:
                    log_fail("Read back returned empty or mismatched row")
                    results["insert_and_read"] = False
            else:
                log_fail(f"Read back failed HTTP {resp.status_code}")
                results["insert_and_read"] = False

            # Cleanup: delete probe row
            resp = await client.delete(
                f"{rest_url}/areal_remote_commands",
                headers=headers,
                params={"id": f"eq.{probe_id}"},
            )
            if resp.status_code in (200, 204):
                log_info("Cleaned up probe row")
            else:
                log_warn(f"Cleanup returned HTTP {resp.status_code} (non-fatal)")

        except httpx.HTTPError as exc:
            log_fail(f"Insert/read probe failed: {exc}")
            results["insert_and_read"] = False

    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main() -> int:
    parser = argparse.ArgumentParser(
        description="Probe db_bridge Supabase connectivity for remote shell"
    )
    parser.add_argument(
        "--url",
        default=os.environ.get("SUPABASE_URL", "http://82.157.184.89:54321"),
        help="Supabase URL (default: from SUPABASE_URL env or .env.areal.example)",
    )
    parser.add_argument(
        "--key",
        default=os.environ.get("SUPABASE_SERVICE_ROLE_KEY"),
        help="Supabase service role key (default: from SUPABASE_SERVICE_ROLE_KEY env)",
    )
    args = parser.parse_args()

    print("=" * 70)
    print("  db_bridge Remote Shell — Connectivity Probe")
    print("=" * 70)
    print()

    url = args.url
    key = args.key

    if not key:
        log_fail(
            "No SUPABASE_SERVICE_ROLE_KEY provided. Set it via --key or env var."
        )
        print()
        print("Usage:")
        print("  set SUPABASE_SERVICE_ROLE_KEY=<your-key>")
        print("  uv run python scripts/probe_connectivity.py")
        print()
        print("Or: uv run python scripts/probe_connectivity.py --key <your-key>")
        return 1

    parsed = urlparse(url)
    host = parsed.hostname or "localhost"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)

    log_info(f"Target: {url}")
    log_info(f"Key: {key[:8]}...{key[-4:]}" if len(key) > 12 else f"Key: ***")
    print()

    # Step 1: TCP
    tcp_ok = probe_tcp(host, port)
    if not tcp_ok:
        log_fail("Cannot reach Supabase host. Check network/firewall.")
        return 1
    print()

    # Steps 2-5: Supabase REST
    results = await probe_supabase(url, key)
    print()

    # Summary
    print("=" * 70)
    print("  RESULTS")
    print("=" * 70)
    all_checks = {"tcp_reachable": tcp_ok, **results}
    all_pass = True
    for check, passed in all_checks.items():
        status = "PASS" if passed else "FAIL"
        icon = "✓" if passed else "✗"
        print(f"  {icon} {check:30s} {status}")
        if not passed:
            all_pass = False
    print()

    if all_pass:
        log_ok(
            "All checks passed. The db_bridge remote shell interface is accessible "
            "and ready to receive model tuning commands."
        )
        return 0
    else:
        log_fail(
            "Some checks failed. Review the output above to identify the issue."
        )
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
