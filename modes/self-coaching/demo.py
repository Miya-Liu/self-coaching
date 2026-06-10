#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Cross-platform self-coaching loop demo (Windows, macOS, Linux).

Usage:
  python -m self_coaching.demo
  python -m self_coaching.demo --env-file scenarios/demo.env
  python -m self_coaching.demo --with-http
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


def _package_root() -> Path:
    return Path(__file__).resolve().parent


def _repo_root() -> Path:
    """Repo checkout root (editable install) or install prefix with bundled data."""
    here = _package_root()
    for candidate in (here.parents[1], here.parents[2], here.parent):
        if (candidate / "mock-services").is_dir():
            return candidate
        if (candidate / "assets" / "mock-services").is_dir():
            return candidate
    try:
        import mock_services  # type: ignore[import-not-found]

        return Path(mock_services.__file__).resolve().parent.parent
    except ImportError:
        pass
    raise FileNotFoundError(
        "Could not locate repo root (mock-services/). "
        "Install with: pip install -e .  or  "
        "bash scripts/install-skill-pack.sh --hermes --with-mock"
    )


def _resolve_asset_root(name: str) -> Path:
    root = _repo_root()
    candidates = [
        root / name,
        root / "assets" / name,
    ]
    for path in candidates:
        if path.exists():
            return path
    raise FileNotFoundError(
        f"Could not find {name} in {candidates}. "
        "Run from a repo checkout or: pip install -e ."
    )


def _resolve_sc_root() -> Path:
    root = _repo_root()
    candidates = [
        _package_root(),
        root / "modes" / "self-coaching",
        root / "assets" / "modes" / "self-coaching",
    ]
    for path in candidates:
        if path.is_dir() and (path / "loop_env.py").is_file():
            return path
    raise FileNotFoundError(
        f"Could not locate self-coaching runtime in {candidates}. "
        "Install with: pip install -e ."
    )


REPO_ROOT = _repo_root()
MOCK_SERVICES = _resolve_asset_root("mock-services")
SCENARIOS_DIR = _resolve_asset_root("scenarios")
TOOLS_DIR = _resolve_asset_root("tools")
SC_ROOT = _resolve_sc_root()

if str(SC_ROOT) not in sys.path:
    sys.path.insert(0, str(SC_ROOT))

from loop_env import configure_demo_env, format_service_profile  # noqa: E402

DEMO_DIR = MOCK_SERVICES / "demo-loop"
SCENARIO = SCENARIOS_DIR / "full_loop.json"

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

    agentevals_url = os.environ.get("MOCK_AGENTEVALS_URL", f"http://127.0.0.1:{ae_port}")
    learning_url = os.environ.get("MOCK_SELF_LEARNING_URL", f"http://127.0.0.1:{learning_port}")
    self_play_url = os.environ.get("MOCK_SELF_PLAY_URL", f"http://127.0.0.1:{self_play_port}")
    aerl_url = os.environ.get("MOCK_AERL_URL", os.environ.get("TRAINER_BASE_URL", f"http://127.0.0.1:{aerl_port}"))

    _run(
        [
            _python(),
            str(MOCK_SERVICES / "mock_agentevals.py"),
            "init",
            "--data-dir",
            str(demo_dir),
            "--agent-id",
            agent_id,
        ]
    )

    procs: list[subprocess.Popen[bytes]] = []
    specs = [
        (MOCK_SERVICES / "mock_agentevals.py", ["serve", "--data-dir", str(demo_dir), "--host", "127.0.0.1", "--port", ae_port], {}),
        (MOCK_SERVICES / "mock_self_learning.py", ["serve", "--data-dir", str(demo_dir), "--host", "127.0.0.1", "--port", learning_port], {}),
        (
            MOCK_SERVICES / "mock_self_play.py",
            ["serve", "--data-dir", str(demo_dir), "--host", "127.0.0.1", "--port", self_play_port],
            {"MOCK_AGENTEVALS_URL": agentevals_url},
        ),
        (MOCK_SERVICES / "mock_aerl.py", ["serve", "--data-dir", str(demo_dir), "--host", "127.0.0.1", "--port", aerl_port], {}),
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


def run_demo(
    *,
    env_file: Path | None = None,
    with_http: bool = False,
) -> int:
    profile = configure_demo_env(
        env_file=env_file,
        with_http=with_http,
    )
    print("==> Service profile")
    print(format_service_profile(profile))

    procs: list[subprocess.Popen[bytes]] = []
    try:
        print(f"==> Prepare demo coaching root at {DEMO_DIR}")
        if DEMO_DIR.exists():
            shutil.rmtree(DEMO_DIR)
        DEMO_DIR.mkdir(parents=True)

        agent_id = profile.agent_id

        if profile.mode == "live":
            print("==> Live service mode (no local mock stack)")
        elif profile.mode == "mock-http" and profile.auto_start_mock_stack:
            print("==> Start split mock stack (mock-http)")
            procs = _start_http_stack(DEMO_DIR, agent_id)
        elif profile.mode == "mock-http":
            print("==> Mock HTTP mode (using URLs from env; stack not auto-started)")
        else:
            print("==> Module transport (in-process mocks)")

        print("==> Run self-coaching loop (scenarios/full_loop.json)")
        _run(
            [
                _python(),
                str(MOCK_SERVICES / "self_coaching_loop.py"),
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
        if str(TOOLS_DIR) not in sys.path:
            sys.path.insert(0, str(TOOLS_DIR))
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
        versions_glob = list((DEMO_DIR / "agents").rglob("versions/*.json"))
        version_count = len(versions_glob)
        print(f"generation: {state.get('generation')}")
        print(f"registry versions: {version_count}")
        print("mock-self-coaching-demo: PASS")
        return 0
    finally:
        if procs:
            _stop_procs(procs)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Self-coaching mock loop demo (cross-platform)")
    parser.add_argument(
        "--env-file",
        type=Path,
        default=None,
        help="Dotenv service profile (default: scenarios/demo.env if it exists)",
    )
    parser.add_argument(
        "--with-http",
        action="store_true",
        help="Shorthand for LOOP_SERVICE_MODE=mock-http (overrides env file mode)",
    )
    args = parser.parse_args(argv)

    env_file = args.env_file
    if env_file is None:
        default_env = SCENARIOS_DIR / "demo.env"
        if default_env.is_file():
            env_file = default_env
            print(f"==> Using default env file: {env_file}")

    return run_demo(env_file=env_file, with_http=args.with_http)


if __name__ == "__main__":
    raise SystemExit(main())
