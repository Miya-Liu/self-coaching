#!/usr/bin/env python3
"""
Mock self-coaching service/CLI for testing the full learning -> self-questioning -> evaluation -> training loop.

This is intentionally deterministic, local-only, and stdlib-only. It simulates service boundaries
without calling real model providers or trainers.

CLI examples:
  python mock_self_coaching.py run-all --root ./demo
  python mock_self_coaching.py learn --root ./demo --event "Agent claimed success without verification"
  python mock_self_coaching.py self-questioning --root ./demo --capability tool_use --n 3
  python mock_self_coaching.py evaluate --root ./demo --candidate candidate-v1 --baseline baseline-v0
  python mock_self_coaching.py train --root ./demo --pipeline sft
  python mock_self_coaching.py serve --root ./demo --port 8765
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import http.server
import json
import os
from pathlib import Path
import random
import re
import sys
import threading
import time
import urllib.parse

VERSION = "0.1.0"
UTC = _dt.timezone.utc
DEFAULT_MAX_BODY_BYTES = 1 << 20  # 1 MiB
IDEMPOTENCY_TTL_S = 86400
IDEMPOTENCY_MAX_ENTRIES = 1000
_IDEMPOTENT_POST_PATHS = frozenset({
    "/learning/events",
    "/self-questioning/generate",
    "/eval/runs",
    "/training/runs",
    "/pipeline/run-all",
})


def now() -> str:
    return _dt.datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def slugify(text: str, limit: int = 48) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    return (s or "item")[:limit]


def stable_id(prefix: str, payload: object) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return f"{prefix}-{hashlib.sha1(raw).hexdigest()[:10]}"


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def write_json(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def paths(root: Path) -> dict[str, Path]:
    base = root / ".self-coaching"
    return {
        "base": base,
        "events": base / "events" / "learning_events.jsonl",
        "self_questioning_candidates": base / "cases" / "self_questioning_candidates.jsonl",
        "eval_cases": base / "cases" / "eval_cases.jsonl",
        "train": base / "curated" / "train.jsonl",
        "validation": base / "curated" / "validation.jsonl",
        "test": base / "curated" / "test.jsonl",
        "reports": base / "reports" / "eval_runs",
        "manifests": base / "manifests",
        "logs": base / "logs",
        "idempotency": base / "idempotency",
        "experience": root / "experience",
    }


def init(root: Path) -> dict:
    p = paths(root)
    for d in [
        p["base"] / "events",
        p["base"] / "cases",
        p["base"] / "curated",
        p["reports"],
        p["manifests"],
        p["logs"],
        p["idempotency"],
        p["experience"],
        root / "logs",
        root / "worktrees",
    ]:
        d.mkdir(parents=True, exist_ok=True)
    for name, title in [
        ("EXPERIMENT_LOG.md", "# Experiment log (mock self-coaching)\n"),
        ("ERROR.md", "# Error log (mock self-coaching)\n"),
        ("LEARNINGS.md", "# Learnings (mock self-coaching)\n"),
    ]:
        fp = p["experience"] / name
        if not fp.exists():
            fp.write_text(title + "\n", encoding="utf-8")
    # Create empty split files so a fresh initialized workspace satisfies the
    # artifact contract before any examples are curated into those splits.
    for split in (p["validation"], p["test"], p["base"] / "curated" / "holdout.jsonl"):
        if not split.exists():
            split.write_text("", encoding="utf-8")
    manifest = {
        "created_at": now(),
        "mock_version": VERSION,
        "layout": ".self-coaching",
        "interfaces": ["cli", "python_module", "http_mock"],
    }
    write_json(p["manifests"] / "mock_service_manifest.json", manifest)
    return {"status": "initialized", "root": str(root), "manifest": str(p["manifests"] / "mock_service_manifest.json")}


def _self_learning_base_url() -> str | None:
    value = os.environ.get("MOCK_SELF_LEARNING_URL", "").strip()
    return value.rstrip("/") if value else None


def learn(root: Path, event: str, source: str = "manual", capability: str = "tool_use") -> dict:
    init(root)
    sl_url = _self_learning_base_url()
    if sl_url:
        try:
            from mock_self_learning import learn_via_http
        except ImportError:
            from .mock_self_learning import learn_via_http
        agent_id = os.environ.get("AGENT_ID", "example-agent")
        return learn_via_http(
            sl_url,
            coaching_root=root,
            event=event,
            source=source,
            capability=capability,
            agent_id=agent_id,
        )
    try:
        from mock_self_learning import MockSelfLearningEngine
    except ImportError:
        from .mock_self_learning import MockSelfLearningEngine
    agent_id = os.environ.get("AGENT_ID", "example-agent")
    return MockSelfLearningEngine(root).record_event(
        coaching_root=root,
        event=event,
        source=source,
        capability=capability,
        agent_id=agent_id,
    )


def _self_questioning_base_url() -> str | None:
    value = os.environ.get("MOCK_SELF_QUESTIONING_URL", "").strip()
    return value.rstrip("/") if value else None


def self_questioning(root: Path, capability: str = "tool_use", n: int = 3) -> dict:
    init(root)
    sp_url = _self_questioning_base_url()
    if sp_url:
        try:
            from mock_self_questioning import self_questioning_via_http
        except ImportError:
            from .mock_self_questioning import self_questioning_via_http
        return self_questioning_via_http(sp_url, coaching_root=root, capability=capability, n=n)
    try:
        from mock_self_questioning import MockSelfQuestioningEngine
    except ImportError:
        from .mock_self_questioning import MockSelfQuestioningEngine
    return MockSelfQuestioningEngine(root).generate_batch(coaching_root=root, capability=capability, n=n)


def negative_eval_marker(text: str) -> bool:
    """True when id is an intentional negative-eval fixture (not hex substring noise)."""
    n = text.lower()
    if "regress" in n or "mock-bad" in n:
        return True
    if n.startswith("bad-") or "-bad-" in n:
        return True
    return bool(re.search(r"^bad[-_]", n))


def _score_case(case: dict, candidate: str) -> dict:
    # Deterministic fake scoring: intentional bad/regress fixtures fail verification cases.
    bad = negative_eval_marker(candidate)
    final_response = "Created and validated config.yaml with evidence." if not bad else "Created the file."
    failures = []
    for check in case.get("deterministic_checks", []):
        if check.get("type") == "contains":
            if check.get("value", "") not in final_response:
                failures.append(f"missing {check.get('value')} in {check.get('field')}")
    passed = not failures
    return {
        "case_id": case["id"],
        "passed": passed,
        "score": 1.0 if passed else 0.0,
        "final_response": final_response,
        "failures": failures,
        "route": "none" if passed else "self-learning",
    }


def _agentevals_base_url() -> str | None:
    for key in ("MOCK_AGENTEVALS_URL", "AGENTEVALS_BASE_URL"):
        value = os.environ.get(key, "").strip()
        if value:
            return value.rstrip("/")
    return None


def evaluate(root: Path, candidate: str = "mock-candidate-v1", baseline: str = "mock-baseline-v0") -> dict:
    init(root)
    ae_url = _agentevals_base_url()
    if ae_url:
        try:
            from mock_agentevals import evaluate_via_http
        except ImportError:
            from .mock_agentevals import evaluate_via_http
        suite_id = os.environ.get("AGENTEVALS_SUITE_ID") or os.environ.get("MOCK_AGENTEVALS_SUITE_ID", "tool-use-canary")
        agent_id = os.environ.get("AGENT_ID", "example-agent")
        return evaluate_via_http(
            ae_url,
            coaching_root=root,
            candidate=candidate,
            baseline=baseline,
            suite_id=suite_id,
            agent_id=agent_id,
        )
    p = paths(root)
    cases = read_jsonl(p["eval_cases"])
    if not cases:
        self_questioning(root, n=3)
        cases = read_jsonl(p["eval_cases"])
    results = [_score_case(c, candidate) for c in cases]
    passed_count = sum(1 for r in results if r["passed"])
    overall = passed_count / max(1, len(results))
    status = "passed" if overall >= 0.8 else "failed"
    run_id = stable_id("eval", {"candidate": candidate, "baseline": baseline, "cases": [c["id"] for c in cases], "t": now()})
    report = {
        "run_id": run_id,
        "timestamp": now(),
        "candidate": candidate,
        "baseline": baseline,
        "status": status,
        "scores": {"overall": overall, "tool_use": overall, "safety": 1.0, "privacy": 1.0},
        "case_count": len(cases),
        "results": results,
        "regressions": [] if status == "passed" else [r for r in results if not r["passed"]],
        "top_failures": [
            {"case_id": r["case_id"], "reason": "; ".join(r["failures"]), "route": r["route"]}
            for r in results if not r["passed"]
        ][:5],
        "recommendation": "promote" if status == "passed" else "do_not_promote",
        "cost": {"tokens": 0, "usd": 0.0},
        "latency": {"p50_s": 0.01, "p95_s": 0.02},
    }
    outdir = p["reports"] / run_id
    write_json(outdir / "report.json", report)
    (outdir / "summary.md").write_text(
        f"# Mock Eval {run_id}\n\n- candidate: {candidate}\n- baseline: {baseline}\n- status: {status}\n- overall: {overall:.2f}\n- recommendation: {report['recommendation']}\n",
        encoding="utf-8",
    )
    return {"status": status, "run_id": run_id, "report": str(outdir / "report.json"), "recommendation": report["recommendation"]}


def _aerl_base_url() -> str | None:
    for key in ("MOCK_AERL_URL", "TRAINER_BASE_URL"):
        value = os.environ.get(key, "").strip()
        if value:
            return value.rstrip("/")
    return None


def train(root: Path, pipeline: str = "sft", dataset: str | None = None, base_model: str = "mock-base") -> dict:
    init(root)
    aerl_url = _aerl_base_url()
    if aerl_url:
        try:
            from mock_aerl import train_via_http
        except ImportError:
            from .mock_aerl import train_via_http
        agent_id = os.environ.get("AGENT_ID", "example-agent")
        return train_via_http(
            aerl_url,
            coaching_root=root,
            pipeline=pipeline,
            dataset=dataset,
            base_model=base_model,
            agent_id=agent_id,
        )
    p = paths(root)
    if pipeline not in {"sft", "grpo"}:
        raise ValueError(f"unsupported mock pipeline: {pipeline}")
    if dataset is None:
        dataset = str(p["train"])
    if not Path(dataset).exists():
        self_questioning(root, n=4)
    records = read_jsonl(Path(dataset))
    run_id = stable_id("train", {"pipeline": pipeline, "dataset": dataset, "base_model": base_model, "t": now()})
    log_file = p["logs"] / f"{run_id}.log"
    metric = max(0.01, 1.0 - min(len(records), 10) * 0.05)
    log_file.write_text(
        "mock training started\n"
        f"pipeline={pipeline}\nbase_model={base_model}\ndataset={dataset}\nrecords={len(records)}\n"
        f"metric.val_loss={metric:.4f}\nmock training complete\n",
        encoding="utf-8",
    )
    manifest = {
        "run_id": run_id,
        "timestamp": now(),
        "pipeline_id": pipeline,
        "dataset_refs": [dataset],
        "base_model": base_model,
        "candidate": f"mock-{pipeline}-candidate-{run_id[-6:]}",
        "method": pipeline,
        "hyperparameters": {"epochs": 1, "learning_rate": 1e-5},
        "log_file": str(log_file),
        "metrics": {"val_loss": metric},
        "rollback_target": base_model,
        "eval_run_id": None,
    }
    write_json(p["manifests"] / "training_run_manifest.json", manifest)
    exp_log = p["experience"] / "EXPERIMENT_LOG.md"
    with exp_log.open("a", encoding="utf-8") as f:
        f.write(f"\n| {run_id} | 1 | mock | {pipeline} dry-run | {dataset} | val_loss | {metric:.4f} | n/a | needs_eval | {log_file} |\n")
    return {"status": "trained", "run_id": run_id, "candidate": manifest["candidate"], "manifest": str(p["manifests"] / "training_run_manifest.json"), "log_file": str(log_file)}


def run_all(root: Path, capability: str = "tool_use", pipeline: str = "sft") -> dict:
    init_result = init(root)
    learning = learn(root, "Mock seed: agent forgot to verify a file write", "run_all", capability)
    play = self_questioning(root, capability, n=5)
    baseline_eval = evaluate(root, "mock-baseline-v0", "mock-baseline-v0")
    training = train(root, pipeline=pipeline)
    candidate_eval = evaluate(root, training["candidate"], "mock-baseline-v0")
    p = paths(root)
    manifest_path = p["manifests"] / "training_run_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["eval_run_id"] = candidate_eval["run_id"]
    write_json(manifest_path, manifest)
    summary = {
        "status": "ok",
        "root": str(root),
        "init": init_result,
        "learning_event_id": learning["id"],
        "self_questioning": play,
        "baseline_eval": baseline_eval,
        "training": training,
        "candidate_eval": candidate_eval,
        "promotion_allowed": candidate_eval["recommendation"] == "promote",
    }
    write_json(p["manifests"] / "mock_pipeline_summary.json", summary)
    return summary


def _max_body_bytes() -> int:
    raw = os.environ.get("MOCK_MAX_BODY_BYTES", "")
    if not raw:
        return DEFAULT_MAX_BODY_BYTES
    return int(raw)


def _service_token() -> str | None:
    token = os.environ.get("MOCK_SERVICE_TOKEN", "").strip()
    return token or None


def _idempotency_key(endpoint: str, key: str) -> str:
    digest = hashlib.sha256(f"{endpoint}\0{key}".encode("utf-8")).hexdigest()
    return digest[:32]


class IdempotencyStore:
    """On-disk cache of prior POST responses keyed by (endpoint, Idempotency-Key)."""

    def __init__(self, directory: Path, *, ttl_s: int = IDEMPOTENCY_TTL_S,
                 max_entries: int = IDEMPOTENCY_MAX_ENTRIES) -> None:
        self.directory = directory
        self.ttl_s = ttl_s
        self.max_entries = max_entries
        self.directory.mkdir(parents=True, exist_ok=True)

    def _path(self, endpoint: str, key: str) -> Path:
        return self.directory / f"{_idempotency_key(endpoint, key)}.json"

    def get(self, endpoint: str, key: str) -> tuple[int, dict] | None:
        path = self._path(endpoint, key)
        if not path.is_file():
            return None
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            path.unlink(missing_ok=True)
            return None
        stored_at = record.get("stored_at", 0)
        if time.time() - stored_at > self.ttl_s:
            path.unlink(missing_ok=True)
            return None
        return int(record["status"]), record["body"]

    def put(self, endpoint: str, key: str, status: int, body: dict) -> None:
        self._evict_expired()
        path = self._path(endpoint, key)
        path.write_text(
            json.dumps({"stored_at": time.time(), "status": status, "body": body},
                       ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
        self._trim()

    def _evict_expired(self) -> None:
        cutoff = time.time() - self.ttl_s
        for path in self.directory.glob("*.json"):
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                path.unlink(missing_ok=True)
                continue
            if record.get("stored_at", 0) < cutoff:
                path.unlink(missing_ok=True)

    def _trim(self) -> None:
        files = sorted(self.directory.glob("*.json"),
                       key=lambda p: p.stat().st_mtime, reverse=True)
        for path in files[self.max_entries:]:
            path.unlink(missing_ok=True)


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "MockSelfCoaching/" + VERSION

    def _json(self, code: int, obj: object) -> None:
        body = json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _auth_ok(self, path: str) -> bool:
        if path == "/health":
            return True
        expected = _service_token()
        if expected is None:
            return True
        auth = self.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return False
        return auth[7:].strip() == expected

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length", "0") or "0")
        if not n:
            return {}
        if n > _max_body_bytes():
            raise ValueError(f"request body exceeds limit of {_max_body_bytes()} bytes")
        return json.loads(self.rfile.read(n).decode("utf-8"))

    @property
    def root(self) -> Path:
        return self.server.root  # type: ignore[attr-defined]

    @property
    def idempotency(self) -> IdempotencyStore:
        return self.server.idempotency  # type: ignore[attr-defined]

    def _handle_post(self, path: str, data: dict) -> tuple[int, dict]:
        if path == "/learning/events":
            return 200, learn(self.root, data.get("event", "mock event"),
                              data.get("source", "http"), data.get("capability", "tool_use"))
        if path == "/self-questioning/generate":
            return 200, self_questioning(self.root, data.get("capability", "tool_use"), int(data.get("n", 3)))
        if path == "/eval/runs":
            return 200, evaluate(self.root, data.get("candidate", "mock-candidate-v1"),
                                data.get("baseline", "mock-baseline-v0"))
        if path == "/training/runs":
            return 200, train(self.root, data.get("pipeline", "sft"), data.get("dataset"),
                             data.get("base_model", "mock-base"))
        if path == "/pipeline/run-all":
            return 200, run_all(self.root, data.get("capability", "tool_use"), data.get("pipeline", "sft"))
        return 404, {"error": "not found"}

    def do_GET(self) -> None:  # noqa: N802
        path = urllib.parse.urlparse(self.path).path
        if not self._auth_ok(path):
            self._json(401, {"error": "unauthorized", "type": "AuthError"})
            return
        if path == "/health":
            self._json(200, {"status": "ok", "version": VERSION, "root": str(self.root)})
            return
        m = re.match(r"^/eval/runs/([^/]+)/report$", path)
        if m:
            report = paths(self.root)["reports"] / m.group(1) / "report.json"
            if report.exists():
                self._json(200, json.loads(report.read_text(encoding="utf-8")))
            else:
                self._json(404, {"error": "report not found"})
            return
        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        path = urllib.parse.urlparse(self.path).path
        if not self._auth_ok(path):
            self._json(401, {"error": "unauthorized", "type": "AuthError"})
            return
        idem_key = self.headers.get("Idempotency-Key", "").strip()
        if idem_key and path in _IDEMPOTENT_POST_PATHS:
            cached = self.idempotency.get(path, idem_key)
            if cached is not None:
                code, body = cached
                self._json(code, body)
                return
        try:
            data = self._body()
        except ValueError as e:
            msg = str(e)
            if "exceeds limit" in msg:
                self._json(413, {"error": msg, "type": "PayloadTooLarge"})
            else:
                self._json(400, {"error": msg, "type": "ValueError"})
            return
        try:
            code, result = self._handle_post(path, data)
            if idem_key and path in _IDEMPOTENT_POST_PATHS and code < 500:
                self.idempotency.put(path, idem_key, code, result)
            self._json(code, result)
        except Exception as e:  # intentionally visible for mock debugging
            self._json(500, {"error": str(e), "type": type(e).__name__})

    def log_message(self, fmt: str, *args: object) -> None:
        sys.stderr.write("[mock-self-coaching] " + fmt % args + "\n")


def serve(root: Path, port: int, host: str = "127.0.0.1") -> None:
    init(root)
    server = http.server.ThreadingHTTPServer((host, port), Handler)
    server.root = root  # type: ignore[attr-defined]
    server.idempotency = IdempotencyStore(paths(root)["idempotency"])  # type: ignore[attr-defined]
    print(json.dumps({"status": "serving", "url": f"http://{host}:{port}", "root": str(root)}, indent=2))
    server.serve_forever()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Mock self-coaching service/CLI")
    parser.add_argument("--version", action="version", version=VERSION)
    sub = parser.add_subparsers(dest="cmd", required=True)

    def add_root(p: argparse.ArgumentParser) -> None:
        p.add_argument("--root", default="./mock-self-coaching-demo", help="project root for .self-coaching artifacts")

    p = sub.add_parser("init"); add_root(p)
    p = sub.add_parser("learn"); add_root(p); p.add_argument("--event", required=True); p.add_argument("--source", default="cli"); p.add_argument("--capability", default="tool_use")
    p = sub.add_parser("self-questioning"); add_root(p); p.add_argument("--capability", default="tool_use"); p.add_argument("--n", type=int, default=3)
    p = sub.add_parser("evaluate"); add_root(p); p.add_argument("--candidate", default="mock-candidate-v1"); p.add_argument("--baseline", default="mock-baseline-v0")
    p = sub.add_parser("train"); add_root(p); p.add_argument("--pipeline", choices=["sft", "grpo"], default="sft"); p.add_argument("--dataset"); p.add_argument("--base-model", default="mock-base")
    p = sub.add_parser("run-all"); add_root(p); p.add_argument("--capability", default="tool_use"); p.add_argument("--pipeline", choices=["sft", "grpo"], default="sft")
    p = sub.add_parser("serve"); add_root(p); p.add_argument("--host", default="127.0.0.1"); p.add_argument("--port", type=int, default=8765)

    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    if args.cmd == "init": result = init(root)
    elif args.cmd == "learn": result = learn(root, args.event, args.source, args.capability)
    elif args.cmd == "self-questioning": result = self_questioning(root, args.capability, args.n)
    elif args.cmd == "evaluate": result = evaluate(root, args.candidate, args.baseline)
    elif args.cmd == "train": result = train(root, args.pipeline, args.dataset, args.base_model)
    elif args.cmd == "run-all": result = run_all(root, args.capability, args.pipeline)
    elif args.cmd == "serve":
        serve(root, args.port, args.host)
        return 0
    else:
        raise SystemExit(f"unknown command {args.cmd}")
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
