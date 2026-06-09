#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Cross-platform self-coaching loop demo (Windows, macOS, Linux).

Usage:
  python scripts/mock_self_coaching_demo.py
  python scripts/mock_self_coaching_demo.py --with-http
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEMO_DIR = REPO_ROOT / "mock-services" / "demo-loop"
SCENARIO = REPO_ROOT / "scenarios" / "full_loop.json"

REQUIRED_ARTIFACTS = (
    ".self-coaching/loop/state.json",
    ".self-coaching/loop/support.jsonl",
    ".self-coaching/loop/tuning_buffer.jsonl",
    ".self-coaching/loop/demo_summary.md",
    "agents/demo-agent/meta.json",
)


def _python() -> str:
    return sys.executable


def _run(cmd: list[str], *, env: dict[str, str] | None = None) -> None:
    subprocess.run(cmd, check=True, cwd=REPO_ROOT, env=env)


def _wait_for_health(url: str, label: str) -> None:
    for _ in range(40):
        try:
            with urllib.request.urlopen(f"{url.rstrip('/')}/health", timeout=2) as resp:
                if resp.status == 200:
                    return
        except (urllib.error.URLError, TimeoutError):
            pass
        time.sleep(0.25)
    raise RuntimeError(f"{label} not healthy at {url}")


def _start_http_stack(demo_dir: Path, agent_id: str) -> list[subprocess.Popen[bytes]]:
    ae_port = os.environ.get("MOCK_AGENTEVALS_PORT", "38180")
    learning_port = os.environ.get("MOCK_SELF_LEARNING_PORT", "38766")
    self_play_port = os.environ.get("MOCK_SELF_PLAY_PORT", "38767")
    aerl_port = os.environ.get("MOCK_AERL_PORT", "38004")

    agentevals_url = f"http://127.0.0.1:{ae_port}"
    learning_url = f"http://127.0.0.1:{learning_port}"
    self_play_url = f"http://127.0.0.1:{self_play_port}"
    aerl_url = f"http://127.0.0.1:{aerl_port}"

    _run(
        [
            _python(),
            str(REPO_ROOT / "mock-services" / "mock_agentevals.py"),
            "init",
            "--data-dir",
            str(demo_dir),
            "--agent-id",
            agent_id,
        ]
    )

    procs: list[subprocess.Popen[bytes]] = []
    specs = [
        (REPO_ROOT / "mock-services" / "mock_agentevals.py", ["serve", "--data-dir", str(demo_dir), "--host", "127.0.0.1", "--port", ae_port], {}),
        (REPO_ROOT / "mock-services" / "mock_self_learning.py", ["serve", "--data-dir", str(demo_dir), "--host", "127.0.0.1", "--port", learning_port], {}),
        (
            REPO_ROOT / "mock-services" / "mock_self_play.py",
            ["serve", "--data-dir", str(demo_dir), "--host", "127.0.0.1", "--port", self_play_port],
            {"MOCK_AGENTEVALS_URL": agentevals_url},
        ),
        (REPO_ROOT / "mock-services" / "mock_aerl.py", ["serve", "--data-dir", str(demo_dir), "--host", "127.0.0.1", "--port", aerl_port], {}),
    ]
    for script, args, extra_env in specs:
        env = os.environ.copy()
        env.update(extra_env)
        procs.append(
            subprocess.Popen(
                [_python(), str(script), *args],
                cwd=REPO_ROOT,
                env=env,
            )
        )

    _wait_for_health(agentevals_url, "AgentEvals")
    _wait_for_health(learning_url, "Self-Learning")
    _wait_for_health(self_play_url, "Self-Play")
    _wait_for_health(aerl_url, "AERL")

    os.environ["MOCK_SELF_LEARNING_URL"] = learning_url
    os.environ["MOCK_SELF_PLAY_URL"] = self_play_url
    os.environ["MOCK_AERL_URL"] = aerl_url
    os.environ["TRAINER_BASE_URL"] = aerl_url
    return procs


def _stop_procs(procs: list[subprocess.Popen[bytes]]) -> None:
    for proc in procs:
        proc.terminate()
    for proc in procs:
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def run_demo(*, with_http: bool = False) -> int:
    procs: list[subprocess.Popen[bytes]] = []
    try:
        print(f"==> Prepare demo coaching root at {DEMO_DIR}")
        if DEMO_DIR.exists():
            shutil.rmtree(DEMO_DIR)
        DEMO_DIR.mkdir(parents=True)

        agent_id = os.environ.get("LOOP_AGENT_ID", "demo-agent")
        os.environ["AGENT_ID"] = agent_id
        os.environ["LOOP_AGENT_ID"] = agent_id
        os.environ.setdefault("LOOP_SIGMA_MIN", "3")
        os.environ.setdefault("LOOP_SIGMA_PLAY", "0")
        os.environ.setdefault("LOOP_BATCH_SIZE", "4")
        os.environ.setdefault("LOOP_TAU_FAIL", "0.75")
        os.environ.setdefault("LOOP_IDLE_AFTER", "0")

        if with_http:
            print("==> Start split mock stack (--with-http)")
            procs = _start_http_stack(DEMO_DIR, agent_id)
        else:
            print("==> Module transport (in-process mocks)")
            for key in (
                "MOCK_SELF_LEARNING_URL",
                "MOCK_SELF_PLAY_URL",
                "MOCK_AERL_URL",
                "MOCK_AGENTEVALS_URL",
                "AGENTEVALS_BASE_URL",
            ):
                os.environ.pop(key, None)

        print("==> Run self-coaching loop (scenarios/full_loop.json)")
        _run(
            [
                _python(),
                str(REPO_ROOT / "mock-services" / "self_coaching_loop.py"),
                "run",
                "--root",
                str(DEMO_DIR),
                "--scenario",
                str(SCENARIO),
            ]
        )

        for rel in REQUIRED_ARTIFACTS:
            path = DEMO_DIR / rel
            if not path.is_file():
                raise FileNotFoundError(f"missing artifact {path}")

        print("==> Completeness audit (C01–C18)")
        if str(REPO_ROOT / "tools") not in sys.path:
            sys.path.insert(0, str(REPO_ROOT / "tools"))
        from loop_completeness import build_context, run_audit, write_report  # noqa: E402

        scenario = json.loads(SCENARIO.read_text(encoding="utf-8"))
        report = run_audit(build_context(DEMO_DIR, scenario))
        write_report(DEMO_DIR, report)

        status = report.get("status")
        print(f"completeness: {status}")
        if status != "PASS":
            for item in report.get("failures", []):
                print(f"  FAIL: {item}", file=sys.stderr)
            return 1

        state = json.loads((DEMO_DIR / ".self-coaching" / "loop" / "state.json").read_text(encoding="utf-8"))
        versions_dir = DEMO_DIR / "agents" / "demo-agent" / "versions"
        version_count = len(list(versions_dir.glob("*.json"))) if versions_dir.is_dir() else 0
        print(f"generation: {state.get('generation')}")
        print(f"registry versions: {version_count}")
        print("mock-self-coaching-demo: PASS")
        return 0
    finally:
        if procs:
            _stop_procs(procs)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Self-coaching mock loop demo (cross-platform)")
    parser.add_argument("--with-http", action="store_true", help="Use split HTTP mock stack")
    args = parser.parse_args(argv)
    return run_demo(with_http=args.with_http)


if __name__ == "__main__":
    raise SystemExit(main())
