#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Mock AERL trainer — async training runs and pipeline argv endpoint.

Phase 3 mock platform. Compatible with services/adapters/aerl_client.py and
modes/self-coaching/self-tuning/pipelines/_lib.sh (POST /v1/pipelines/{id}/run).

CLI:
  python mock_aerl.py serve --data-dir ./demo-stack --port 8004
  python mock_aerl.py run --data-dir ./demo-stack --pipeline sft --base-model mock-base
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
PIPELINES = frozenset({"sft", "grpo"})


def _now() -> str:
    return _dt.datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _iso_now() -> str:
    return _dt.datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def stable_id(prefix: str, payload: object) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return f"{prefix}-{hashlib.sha1(raw).hexdigest()[:10]}"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def write_json(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


class MockAERLEngine:
    """Deterministic mock AERL trainer with async runs and registry drafts."""

    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir).resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.registry = AgentRegistry(self.data_dir)
        self._runs_dir = self.data_dir / "aerl" / "runs"
        self._logs_dir = self.data_dir / "aerl" / "logs"
        self._runs_dir.mkdir(parents=True, exist_ok=True)
        self._logs_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _run_path(self, run_id: str) -> Path:
        return self._runs_dir / f"{run_id}.json"

    def _save_run(self, run: dict[str, Any]) -> None:
        self._run_path(str(run["id"])).write_text(
            json.dumps(run, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def _load_run(self, run_id: str) -> dict[str, Any]:
        path = self._run_path(run_id)
        if not path.is_file():
            raise KeyError(f"training run not found: {run_id}")
        return json.loads(path.read_text(encoding="utf-8"))

    def _metric_from_records(self, n_records: int) -> float:
        return max(0.01, 1.0 - min(n_records, 10) * 0.05)

    def _resolve_dataset(self, dataset_refs: list[str] | None, coaching_root: Path | None) -> tuple[Path | None, int]:
        refs = dataset_refs or []
        if not refs and coaching_root is not None:
            candidate = coaching_root / ".self-coaching" / "curated" / "train.jsonl"
            if candidate.is_file():
                refs = [str(candidate)]
        dataset_path: Path | None = None
        n_records = 0
        for ref in refs:
            path = Path(ref)
            if path.is_file():
                dataset_path = path
                n_records = len(read_jsonl(path))
                break
        return dataset_path, n_records

    def create_training_run(self, body: dict[str, Any]) -> dict[str, Any]:
        pipeline_id = str(body.get("pipeline_id") or body.get("pipeline") or "sft")
        if pipeline_id not in PIPELINES:
            raise ValueError(f"unsupported pipeline: {pipeline_id}")
        base_model = str(body.get("base_model") or "mock-base")
        agent_id = str(body.get("agent_id") or "example-agent")
        coaching_root = body.get("coaching_root")
        root = Path(coaching_root) if coaching_root else None
        dataset_refs = body.get("dataset_refs")
        if dataset_refs is None and body.get("dataset"):
            dataset_refs = [str(body["dataset"])]
        if isinstance(dataset_refs, str):
            dataset_refs = [dataset_refs]
        dataset_path, n_records = self._resolve_dataset(
            list(dataset_refs) if dataset_refs else None,
            root,
        )

        run_id = f"train-{uuid.uuid4().hex[:12]}"
        created_at = _iso_now()
        run = {
            "id": run_id,
            "pipeline_id": pipeline_id,
            "status": "queued",
            "created_at": created_at,
            "updated_at": created_at,
            "base_model": base_model,
            "agent_id": agent_id,
            "dataset_refs": [str(dataset_path)] if dataset_path else list(dataset_refs or []),
            "coaching_root": str(root) if root else None,
            "metrics": None,
            "candidate_model_id": None,
            "log_file": None,
            "registry_version_id": None,
        }
        self._save_run(run)

        def _finish() -> None:
            time.sleep(0.05)
            metric = self._metric_from_records(n_records)
            candidate = f"mock-{pipeline_id}-candidate-{run_id[-6:]}"
            log_file = self._logs_dir / f"{run_id}.log"
            log_file.write_text(
                "mock AERL training started\n"
                f"pipeline={pipeline_id}\nbase_model={base_model}\n"
                f"records={n_records}\nmetric.val_loss={metric:.4f}\n"
                "mock AERL training complete\n",
                encoding="utf-8",
            )
            registry_version_id: str | None = None
            try:
                self.registry.ensure_agent(agent_id)
                version = self.registry.create_version(
                    agent_id,
                    components={"model_id": candidate},
                    artifacts={"training_run_id": run_id},
                    source="mock_aerl",
                )
                registry_version_id = str(version["version_id"])
            except Exception:
                registry_version_id = None

            if root is not None:
                manifests = root / ".self-coaching" / "manifests"
                manifests.mkdir(parents=True, exist_ok=True)
                manifest = {
                    "run_id": run_id,
                    "timestamp": _now(),
                    "pipeline_id": pipeline_id,
                    "dataset_refs": run["dataset_refs"],
                    "base_model": base_model,
                    "candidate": candidate,
                    "candidate_model_id": candidate,
                    "method": pipeline_id,
                    "hyperparameters": {"epochs": 1, "learning_rate": 1e-5},
                    "log_file": str(log_file),
                    "metrics": {"val_loss": metric},
                    "rollback_target": base_model,
                    "eval_run_id": None,
                    "registry_version_id": registry_version_id,
                }
                write_json(manifests / "training_run_manifest.json", manifest)

            finished = self._load_run(run_id)
            finished["status"] = "succeeded"
            finished["updated_at"] = _iso_now()
            finished["finished_at"] = finished["updated_at"]
            finished["metrics"] = {"val_loss": metric}
            finished["candidate_model_id"] = candidate
            finished["log_file"] = str(log_file)
            finished["registry_version_id"] = registry_version_id
            self._save_run(finished)

        threading.Thread(target=_finish, daemon=True).start()
        return {
            "id": run_id,
            "pipeline_id": pipeline_id,
            "status": "queued",
            "created_at": created_at,
            "updated_at": created_at,
        }

    def get_training_run(self, run_id: str) -> dict[str, Any]:
        run = self._load_run(run_id)
        return {
            "id": run["id"],
            "pipeline_id": run["pipeline_id"],
            "status": run["status"],
            "created_at": run["created_at"],
            "updated_at": run.get("updated_at"),
            "finished_at": run.get("finished_at"),
            "base_model": run.get("base_model"),
            "agent_id": run.get("agent_id"),
            "dataset_refs": run.get("dataset_refs") or [],
            "metrics": run.get("metrics"),
            "candidate_model_id": run.get("candidate_model_id"),
            "log_file": run.get("log_file"),
            "registry_version_id": run.get("registry_version_id"),
        }

    def run_pipeline_argv(self, pipeline_id: str, argv: list[str]) -> str:
        if pipeline_id not in PIPELINES:
            raise ValueError(f"unsupported pipeline: {pipeline_id}")
        digest = hashlib.sha1(json.dumps(argv, sort_keys=True).encode()).hexdigest()[:8]
        metric = 0.42 + (len(argv) % 5) * 0.02
        return (
            f"mock AERL pipeline={pipeline_id}\n"
            f"argv={json.dumps(argv)}\n"
            f"run_token={digest}\n"
            f"metric.val_loss={metric:.4f}\n"
            "mock AERL pipeline complete\n"
        )


def train_via_http(
    base_url: str,
    *,
    coaching_root: Path,
    pipeline: str = "sft",
    dataset: str | None = None,
    base_model: str = "mock-base",
    agent_id: str | None = None,
    poll_timeout_s: float = 60.0,
    poll_interval_s: float = 0.1,
) -> dict[str, Any]:
    """Call mock AERL /v1/training/runs and return coaching-compatible train result."""
    body: dict[str, Any] = {
        "pipeline_id": pipeline,
        "base_model": base_model,
        "coaching_root": str(coaching_root),
        "agent_id": agent_id or "example-agent",
    }
    if dataset:
        body["dataset_refs"] = [dataset]
    created = _http_json("POST", f"{base_url.rstrip('/')}/v1/training/runs", body)
    run_id = str(created.get("id") or "")
    if not run_id:
        raise RuntimeError(f"AERL create run missing id: {created}")

    deadline = time.time() + poll_timeout_s
    detail: dict[str, Any] = created
    while time.time() < deadline:
        detail = _http_json("GET", f"{base_url.rstrip('/')}/v1/training/runs/{run_id}")
        status = str(detail.get("status", "")).lower()
        if status in {"succeeded", "failed", "cancelled", "canceled"}:
            break
        time.sleep(poll_interval_s)
    else:
        raise TimeoutError(f"AERL run {run_id} did not complete within {poll_timeout_s}s")

    if str(detail.get("status", "")).lower() != "succeeded":
        raise RuntimeError(f"AERL run {run_id} ended with status={detail.get('status')!r}")

    candidate = str(detail.get("candidate_model_id") or "")
    manifest_path = coaching_root / ".self-coaching" / "manifests" / "training_run_manifest.json"
    return {
        "status": "trained",
        "run_id": run_id,
        "candidate": candidate,
        "candidate_model_id": candidate,
        "manifest": str(manifest_path) if manifest_path.is_file() else None,
        "log_file": detail.get("log_file"),
        "registry_version_id": detail.get("registry_version_id"),
        "_train_backend": "aerl",
    }


def _http_json(method: str, url: str, payload: dict[str, Any] | None = None) -> Any:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        try:
            err_body = json.loads(exc.read().decode("utf-8"))
        except Exception:
            err_body = exc.reason
        raise RuntimeError(f"{method} {url} failed: HTTP {exc.code}: {err_body}") from exc


class _AERLHandler(http.server.BaseHTTPRequestHandler):
    server_version = "MockAERL/" + VERSION

    @property
    def engine(self) -> MockAERLEngine:
        return self.server.engine  # type: ignore[attr-defined]

    def _json(self, code: int, obj: object) -> None:
        body = json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _text(self, code: int, text: str) -> None:
        body = text.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
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
            self._json(200, {"status": "ok", "version": VERSION, "data_dir": str(self.engine.data_dir)})
            return
        m = re.fullmatch(r"/v1/training/runs/([^/]+)", path)
        if m:
            try:
                result = self.engine.get_training_run(m.group(1))
            except KeyError as exc:
                self._json(404, {"error": str(exc)})
                return
            self._json(200, result)
            return
        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        path = urllib.parse.urlparse(self.path).path
        if path == "/v1/training/runs":
            try:
                result = self.engine.create_training_run(self._body())
            except ValueError as exc:
                self._json(400, {"error": str(exc)})
                return
            self._json(202, result)
            return
        m = re.fullmatch(r"/v1/pipelines/([^/]+)/run", path)
        if m:
            data = self._body()
            argv = data.get("argv") or []
            if not isinstance(argv, list):
                self._json(400, {"error": "argv must be a list"})
                return
            try:
                log = self.engine.run_pipeline_argv(m.group(1), [str(a) for a in argv])
            except ValueError as exc:
                self._json(400, {"error": str(exc)})
                return
            self._text(200, log)
            return
        self._json(404, {"error": "not found"})

    def log_message(self, fmt: str, *args: object) -> None:
        sys.stderr.write("[mock-aerl] " + fmt % args + "\n")


def serve(data_dir: Path, port: int, host: str = "127.0.0.1") -> None:
    engine = MockAERLEngine(data_dir)
    server = http.server.ThreadingHTTPServer((host, port), _AERLHandler)
    server.engine = engine  # type: ignore[attr-defined]
    print(json.dumps({"status": "serving", "url": f"http://{host}:{port}", "data_dir": str(data_dir)}, indent=2))
    server.serve_forever()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Mock AERL trainer service")
    parser.add_argument("--version", action="version", version=VERSION)
    sub = parser.add_subparsers(dest="cmd", required=True)

    def add_data(p: argparse.ArgumentParser) -> None:
        p.add_argument("--data-dir", default="./mock-aerl-data")

    p_run = sub.add_parser("run")
    add_data(p_run)
    p_run.add_argument("--pipeline", default="sft")
    p_run.add_argument("--base-model", default="mock-base")
    p_run.add_argument("--agent-id", default="example-agent")
    p_run.add_argument("--coaching-root")

    p_serve = sub.add_parser("serve")
    add_data(p_serve)
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8004)

    args = parser.parse_args(argv)
    engine = MockAERLEngine(args.data_dir)
    if args.cmd == "run":
        body: dict[str, Any] = {
            "pipeline_id": args.pipeline,
            "base_model": args.base_model,
            "agent_id": args.agent_id,
        }
        if args.coaching_root:
            body["coaching_root"] = args.coaching_root
        created = engine.create_training_run(body)
        run_id = str(created["id"])
        deadline = time.time() + 30
        while time.time() < deadline:
            detail = engine.get_training_run(run_id)
            if str(detail.get("status", "")).lower() == "succeeded":
                print(json.dumps(detail, indent=2, sort_keys=True))
                return 0
            time.sleep(0.05)
        raise SystemExit(f"run {run_id} did not finish")
    if args.cmd == "serve":
        serve(Path(args.data_dir), args.port, args.host)
        return 0
    raise SystemExit(f"unknown command {args.cmd}")


if __name__ == "__main__":
    raise SystemExit(main())
