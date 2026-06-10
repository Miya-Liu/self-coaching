#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Mock AgentEvals HTTP service — suites, async runs, RunDetail metrics.

Compatible with services/adapters/agentevals_client.py and the OpenAPI snapshot under
docs/integration/api-snapshots/agentevals-openapi.json.

Mock-only extension: POST /api/suites (register customised suites).

CLI:
  python mock_agentevals.py serve --data-dir ./demo-stack --port 8080
  python mock_agentevals.py init --data-dir ./demo-stack
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import http.server
import json
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any

try:
    from mock_agent_registry import AgentRegistry
except ImportError:  # pragma: no cover
    from .mock_agent_registry import AgentRegistry

VERSION = "0.1.0"
UTC = _dt.timezone.utc

BUILTIN_SUITES: dict[str, dict[str, Any]] = {
    "tool-use-canary": {
        "id": "tool-use-canary",
        "name": "Tool Use Canary",
        "description": "Mock canary suite for scheduled monitoring",
        "tasks_count": 4,
        "metric_statistic": "mean",
        "kind": "benchmark",
        "task_ids": ["task-verify-1", "task-verify-2", "task-verify-3", "task-verify-4"],
    },
    "tool-use-holdout": {
        "id": "tool-use-holdout",
        "name": "Tool Use Holdout",
        "description": "Mock holdout suite for promotion gates",
        "tasks_count": 3,
        "metric_statistic": "mean",
        "kind": "benchmark",
        "task_ids": ["task-hold-1", "task-hold-2", "task-hold-3"],
    },
}

HOLDOUT_SUITE_IDS = frozenset({"tool-use-holdout"})


def _now() -> str:
    return _dt.datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _iso_now() -> str:
    return _dt.datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class MockAgentEvalsEngine:
    """In-process AgentEvals mock backed by JSON files under data_dir."""

    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir).resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.registry = AgentRegistry(self.data_dir)
        self._suites_path = self.data_dir / "agentevals" / "suites.json"
        self._runs_dir = self.data_dir / "agentevals" / "runs"
        self._runs_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._load_suites()

    def _load_suites(self) -> None:
        if self._suites_path.is_file():
            data = json.loads(self._suites_path.read_text(encoding="utf-8"))
            self._custom_suites: dict[str, dict[str, Any]] = data.get("suites", {})
        else:
            self._custom_suites = {}
            self._persist_suites()

    def _persist_suites(self) -> None:
        self._suites_path.parent.mkdir(parents=True, exist_ok=True)
        self._suites_path.write_text(
            json.dumps({"suites": self._custom_suites}, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def _all_suites(self) -> dict[str, dict[str, Any]]:
        merged = dict(BUILTIN_SUITES)
        merged.update(self._custom_suites)
        return merged

    def list_suites(self) -> list[dict[str, Any]]:
        out = []
        for suite in self._all_suites().values():
            out.append({k: suite[k] for k in ("id", "name", "description", "tasks_count", "metric_statistic", "kind", "source_benchmark") if k in suite})
        return out

    def get_suite(self, suite_id: str) -> dict[str, Any]:
        suite = self._all_suites().get(suite_id)
        if not suite:
            raise KeyError(f"suite not found: {suite_id}")
        detail = dict(suite)
        task_ids = detail.get("task_ids") or []
        detail["task_summary"] = [{"id": tid, "name": tid} for tid in task_ids]
        return detail

    def create_suite(self, body: dict[str, Any]) -> dict[str, Any]:
        name = str(body.get("name") or "Custom Suite")
        tasks = body.get("tasks") or body.get("task_ids") or []
        if isinstance(tasks, list) and tasks and isinstance(tasks[0], dict):
            task_ids = [str(t.get("id", f"task-{i}")) for i, t in enumerate(tasks)]
        else:
            task_ids = [str(t) for t in tasks]
        if not task_ids:
            task_ids = ["task-custom-1"]
        suite_id = str(body.get("suite_id") or body.get("id") or "")
        if not suite_id:
            digest = hashlib.sha1(json.dumps({"name": name, "tasks": task_ids}, sort_keys=True).encode()).hexdigest()[:10]
            suite_id = f"custom-{digest}"
        suite = {
            "id": suite_id,
            "name": name,
            "description": str(body.get("description") or "Mock customised suite"),
            "tasks_count": len(task_ids),
            "metric_statistic": "mean",
            "kind": str(body.get("kind") or "customised"),
            "source_benchmark": body.get("source_benchmark"),
            "task_ids": task_ids,
            "source_run_id": body.get("source_run_id"),
        }
        with self._lock:
            self._custom_suites[suite_id] = suite
            self._persist_suites()
        return suite

    def _run_path(self, run_id: str) -> Path:
        return self._runs_dir / f"{run_id}.json"

    def _save_run(self, run: dict[str, Any]) -> None:
        path = self._run_path(str(run["id"]))
        payload = json.dumps(run, indent=2, sort_keys=True) + "\n"
        tmp = path.with_suffix(".json.tmp")
        with self._lock:
            tmp.write_text(payload, encoding="utf-8")
            tmp.replace(path)

    def _load_run(self, run_id: str) -> dict[str, Any]:
        path = self._run_path(run_id)
        if not path.is_file():
            raise KeyError(f"run not found: {run_id}")
        with self._lock:
            text = path.read_text(encoding="utf-8")
        if not text.strip():
            raise KeyError(f"run file empty: {run_id}")
        return json.loads(text)

    def _compute_metrics(self, *, suite_id: str, agent_config: dict[str, Any], num_trials: int) -> dict[str, Any]:
        agent_id = str(agent_config.get("agent_id") or "example-agent")
        version_id = str(agent_config.get("version_id") or "ver-0001")
        self.registry.ensure_agent(agent_id)
        multiplier = self.registry.score_multiplier(agent_id, version_id)
        base = 0.86 * multiplier
        if suite_id in HOLDOUT_SUITE_IDS:
            base *= 0.97
        base = max(0.05, min(1.0, base))
        cost = round(0.04 + 0.01 * num_trials, 4)
        return {
            "overall": round(base, 4),
            "pass_rate": round(base, 4),
            "safety": 1.0,
            "cost_usd": cost,
            "latency_p95_ms": 800 + num_trials * 50,
            "tool_use": round(base * 0.98, 4),
            "privacy": 1.0,
        }

    def create_run(self, body: dict[str, Any]) -> dict[str, Any]:
        suite_id = str(body.get("suite_id", ""))
        if suite_id not in self._all_suites():
            raise KeyError(f"suite not found: {suite_id}")
        agent_config = body.get("agent_config") or {}
        if agent_config.get("agent_id"):
            self.registry.ensure_agent(str(agent_config["agent_id"]))
        num_trials = int(body.get("num_trials") or 1)
        run_id = f"run-{uuid.uuid4().hex[:12]}"
        created_at = _iso_now()
        run = {
            "id": run_id,
            "suite_id": suite_id,
            "status": "queued",
            "created_at": created_at,
            "updated_at": created_at,
            "num_trials": num_trials,
            "agent_config": agent_config,
            "metrics": None,
        }
        self._save_run(run)

        def _finish() -> None:
            time.sleep(0.05)
            metrics = self._compute_metrics(suite_id=suite_id, agent_config=agent_config, num_trials=num_trials)
            finished = self._load_run(run_id)
            finished["status"] = "succeeded"
            finished["updated_at"] = _iso_now()
            finished["metrics"] = metrics
            finished["finished_at"] = finished["updated_at"]
            self._save_run(finished)

        threading.Thread(target=_finish, daemon=True).start()
        return {
            "id": run_id,
            "suite_id": suite_id,
            "status": "queued",
            "created_at": created_at,
            "updated_at": created_at,
        }

    def get_run(self, run_id: str) -> dict[str, Any]:
        run = self._load_run(run_id)
        detail: dict[str, Any] = {
            "id": run["id"],
            "suite_id": run["suite_id"],
            "status": run["status"],
            "created_at": run["created_at"],
            "updated_at": run.get("updated_at"),
            "metrics": run.get("metrics"),
            "num_trials": run.get("num_trials", 1),
            "agent_config": run.get("agent_config") or {},
        }
        if run.get("finished_at"):
            detail["finished_at"] = run["finished_at"]
        return detail

    def list_runs(self, *, suite_id: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for path in sorted(self._runs_dir.glob("*.json")):
            run = json.loads(path.read_text(encoding="utf-8"))
            if suite_id and run.get("suite_id") != suite_id:
                continue
            if status and run.get("status") != status:
                continue
            out.append(
                {
                    "id": run["id"],
                    "suite_id": run["suite_id"],
                    "status": run["status"],
                    "created_at": run["created_at"],
                    "updated_at": run.get("updated_at"),
                }
            )
        return out

    def init_demo(self, agent_id: str = "example-agent") -> dict[str, Any]:
        agent = self.registry.ensure_agent(agent_id)
        return {
            "status": "initialized",
            "data_dir": str(self.data_dir),
            "suites": [s["id"] for s in self.list_suites()],
            "agent": agent,
        }


def _http_json(method: str, url: str, payload: dict[str, Any] | None = None) -> Any:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def evaluate_via_http(
    base_url: str,
    *,
    coaching_root: Path,
    candidate: str,
    baseline: str,
    suite_id: str = "tool-use-canary",
    agent_id: str = "example-agent",
    num_trials: int = 4,
    poll_timeout_s: float = 10.0,
) -> dict[str, Any]:
    """POST /api/runs to a running mock AgentEvals server; write coaching-root artifacts."""
    root_url = base_url.rstrip("/")
    created = _http_json(
        "POST",
        f"{root_url}/api/runs",
        {
            "suite_id": suite_id,
            "num_trials": num_trials,
            "agent_config": {
                "agent_id": agent_id,
                "version_id": candidate,
                "baseline_version_id": baseline,
            },
        },
    )
    run_id = str(created.get("id", ""))
    deadline = time.time() + poll_timeout_s
    detail: dict[str, Any] | None = None
    while time.time() < deadline:
        detail = _http_json("GET", f"{root_url}/api/runs/{run_id}")
        if str(detail.get("status")) in {"succeeded", "failed"}:
            break
        time.sleep(0.05)
    if detail is None:
        raise RuntimeError(f"mock AgentEvals run {run_id} did not return detail")
    if str(detail.get("status")) != "succeeded":
        raise RuntimeError(f"mock AgentEvals run {run_id} ended with {detail.get('status')!r}")

    metrics = detail.get("metrics") or {}
    overall = float(metrics.get("overall", 0.0))
    status = "passed" if overall >= 0.8 else "failed"
    report = {
        "run_id": run_id,
        "timestamp": _now(),
        "candidate": candidate,
        "baseline": baseline,
        "status": status,
        "scores": {
            "overall": overall,
            "tool_use": float(metrics.get("tool_use", overall)),
            "safety": float(metrics.get("safety", 1.0)),
            "privacy": float(metrics.get("privacy", 1.0)),
        },
        "case_count": 1,
        "results": [],
        "regressions": [] if status == "passed" else [{"case_id": "mock", "reason": "score below gate"}],
        "top_failures": [],
        "recommendation": "promote" if status == "passed" else "do_not_promote",
        "cost": {"tokens": 0, "usd": float(metrics.get("cost_usd", 0.0))},
        "latency": {"p50_s": 0.01, "p95_s": float(metrics.get("latency_p95_ms", 800)) / 1000.0},
        "run_detail": detail,
    }
    outdir = coaching_root / ".self-coaching" / "reports" / "eval_runs" / run_id
    outdir.mkdir(parents=True, exist_ok=True)
    outdir.joinpath("report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    outdir.joinpath("summary.md").write_text(
        f"# Mock Eval {run_id}\n\n- candidate: {candidate}\n- baseline: {baseline}\n"
        f"- status: {status}\n- overall: {overall:.2f}\n- recommendation: {report['recommendation']}\n",
        encoding="utf-8",
    )
    return {
        "status": status,
        "run_id": run_id,
        "report": str(outdir / "report.json"),
        "recommendation": report["recommendation"],
        "_eval_backend": "agentevals",
    }


def evaluate_for_coaching_root(
    engine: MockAgentEvalsEngine,
    *,
    candidate: str,
    baseline: str,
    suite_id: str,
    agent_id: str,
    coaching_root: Path | None = None,
) -> dict[str, Any]:
    """Run eval via engine and optionally write coaching-root report artifacts."""
    summary = engine.create_run(
        {
            "suite_id": suite_id,
            "num_trials": 4,
            "agent_config": {
                "agent_id": agent_id,
                "version_id": candidate,
                "baseline_version_id": baseline,
            },
        }
    )
    run_id = str(summary["id"])
    deadline = time.time() + 5.0
    detail: dict[str, Any] | None = None
    while time.time() < deadline:
        detail = engine.get_run(run_id)
        if str(detail.get("status")) == "succeeded":
            break
        time.sleep(0.02)
    if detail is None or str(detail.get("status")) != "succeeded":
        raise RuntimeError(f"mock eval run {run_id} did not succeed in time")

    metrics = detail.get("metrics") or {}
    overall = float(metrics.get("overall", 0.0))
    status = "passed" if overall >= 0.8 else "failed"
    report = {
        "run_id": run_id,
        "timestamp": _now(),
        "candidate": candidate,
        "baseline": baseline,
        "status": status,
        "scores": {
            "overall": overall,
            "tool_use": float(metrics.get("tool_use", overall)),
            "safety": float(metrics.get("safety", 1.0)),
            "privacy": float(metrics.get("privacy", 1.0)),
        },
        "case_count": engine.get_suite(suite_id).get("tasks_count", 1),
        "results": [],
        "regressions": [] if status == "passed" else [{"case_id": "mock", "reason": "score below gate"}],
        "top_failures": [],
        "recommendation": "promote" if status == "passed" else "do_not_promote",
        "cost": {"tokens": 0, "usd": float(metrics.get("cost_usd", 0.0))},
        "latency": {"p50_s": 0.01, "p95_s": float(metrics.get("latency_p95_ms", 800)) / 1000.0},
        "run_detail": detail,
    }

    if coaching_root is not None:
        outdir = coaching_root / ".self-coaching" / "reports" / "eval_runs" / run_id
        outdir.mkdir(parents=True, exist_ok=True)
        outdir.joinpath("report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        outdir.joinpath("summary.md").write_text(
            f"# Mock Eval {run_id}\n\n- candidate: {candidate}\n- baseline: {baseline}\n"
            f"- status: {status}\n- overall: {overall:.2f}\n- recommendation: {report['recommendation']}\n",
            encoding="utf-8",
        )

    return {
        "status": status,
        "run_id": run_id,
        "report": str((coaching_root / ".self-coaching" / "reports" / "eval_runs" / run_id / "report.json")) if coaching_root else run_id,
        "recommendation": report["recommendation"],
        "_eval_backend": "agentevals",
    }


class _AgentEvalsHandler(http.server.BaseHTTPRequestHandler):
    server_version = "MockAgentEvals/" + VERSION

    @property
    def engine(self) -> MockAgentEvalsEngine:
        return self.server.engine  # type: ignore[attr-defined]

    def _json(self, code: int, obj: object) -> None:
        body = json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict[str, Any]:
        n = int(self.headers.get("Content-Length", "0") or "0")
        if not n:
            return {}
        return json.loads(self.rfile.read(n).decode("utf-8"))

    def do_GET(self) -> None:  # noqa: N802
        path = urllib.parse.urlparse(self.path).path
        if path == "/health":
            self._json(200, {"status": "ok", "version": VERSION})
            return
        if path == "/openapi.json":
            self._json(200, {"openapi": "3.1.0", "info": {"title": "Mock AgentEvals", "version": VERSION}})
            return
        if path == "/api/suites":
            self._json(200, self.engine.list_suites())
            return
        m = re.match(r"^/api/suites/([^/]+)$", path)
        if m:
            try:
                self._json(200, self.engine.get_suite(m.group(1)))
            except KeyError as exc:
                self._json(404, {"error": str(exc)})
            return
        if path == "/api/runs":
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            suite_id = qs.get("suite_id", [None])[0]
            status = qs.get("status", [None])[0]
            self._json(200, self.engine.list_runs(suite_id=suite_id, status=status))
            return
        m = re.match(r"^/api/runs/([^/]+)$", path)
        if m:
            try:
                self._json(200, self.engine.get_run(m.group(1)))
            except KeyError as exc:
                self._json(404, {"error": str(exc)})
            return
        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        path = urllib.parse.urlparse(self.path).path
        if path == "/api/suites":
            try:
                self._json(201, self.engine.create_suite(self._body()))
            except (KeyError, ValueError) as exc:
                self._json(400, {"error": str(exc)})
            return
        if path == "/api/runs":
            try:
                self._json(201, self.engine.create_run(self._body()))
            except KeyError as exc:
                self._json(404, {"error": str(exc)})
            return
        self._json(404, {"error": "not found"})

    def log_message(self, fmt: str, *args: object) -> None:
        sys.stderr.write("[mock-agentevals] " + fmt % args + "\n")


def serve(data_dir: Path, port: int, host: str = "127.0.0.1") -> None:
    engine = MockAgentEvalsEngine(data_dir)
    engine.init_demo()
    server = http.server.ThreadingHTTPServer((host, port), _AgentEvalsHandler)
    server.engine = engine  # type: ignore[attr-defined]
    print(json.dumps({"status": "serving", "url": f"http://{host}:{port}", "data_dir": str(data_dir)}, indent=2))
    server.serve_forever()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Mock AgentEvals service")
    parser.add_argument("--version", action="version", version=VERSION)
    sub = parser.add_subparsers(dest="cmd", required=True)

    def add_data(p: argparse.ArgumentParser) -> None:
        p.add_argument("--data-dir", default="./mock-agentevals-data")

    p_init = sub.add_parser("init")
    add_data(p_init)
    p_init.add_argument("--agent-id", default="example-agent")

    p_serve = sub.add_parser("serve")
    add_data(p_serve)
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8080)

    args = parser.parse_args(argv)
    engine = MockAgentEvalsEngine(args.data_dir)
    if args.cmd == "init":
        print(json.dumps(engine.init_demo(args.agent_id), indent=2, sort_keys=True))
        return 0
    if args.cmd == "serve":
        serve(Path(args.data_dir), args.port, args.host)
        return 0
    raise SystemExit(f"unknown command {args.cmd}")


if __name__ == "__main__":
    raise SystemExit(main())
