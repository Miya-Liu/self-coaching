#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Mock self-questioning service — generate cases from failures, register AgentEvals suites, curate splits.

Phase 2 mock platform. Shares --data-dir with registry and AgentEvals mocks.

CLI:
  python mock_self_questioning.py serve --data-dir ./demo-stack --port 8767
  python mock_self_questioning.py generate-suite --data-dir ./demo-stack --query "..." --score 0.4
"""
from __future__ import annotations

import argparse
import hashlib
import http.server
import importlib.util
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

try:
    from mock_agentevals import MockAgentEvalsEngine
except ImportError:  # pragma: no cover
    from .mock_agentevals import MockAgentEvalsEngine

VERSION = "0.1.0"


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


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def _load_curate_module():
    repo_root = Path(__file__).resolve().parents[1]
    path = repo_root / "scripts" / "curate_data.py"
    spec = importlib.util.spec_from_file_location("curate_data", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class MockSelfQuestioningEngine:
    """Generate self-questioning cases, register suites in mock AgentEvals, run curation."""

    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir).resolve()
        self.agentevals = MockAgentEvalsEngine(self.data_dir)

    def _paths(self, root: Path) -> dict[str, Path]:
        base = root / ".self-coaching"
        return {
            "candidates": base / "cases" / "self_questioning_candidates.jsonl",
            "eval_cases": base / "cases" / "eval_cases.jsonl",
            "staging": base / "curated" / "staging.jsonl",
            "curated": base / "curated",
            "events": base / "events" / "learning_events.jsonl",
        }

    def _ensure_layout(self, root: Path) -> None:
        p = self._paths(root)
        p["candidates"].parent.mkdir(parents=True, exist_ok=True)
        p["curated"].mkdir(parents=True, exist_ok=True)
        p["staging"].parent.mkdir(parents=True, exist_ok=True)

    def _agentevals_url(self) -> str | None:
        for key in ("MOCK_AGENTEVALS_URL", "AGENTEVALS_BASE_URL"):
            val = os.environ.get(key, "").strip()
            if val:
                return val.rstrip("/")
        return None

    def _register_suite(
        self,
        *,
        name: str,
        cases: list[dict[str, Any]],
        source_run_id: str | None = None,
        kind: str = "customised",
        source_benchmark: str | None = "tool-use-canary",
    ) -> dict[str, Any]:
        tasks = [{"id": c["id"], "name": str(c.get("user_request", c["id"]))[:120]} for c in cases]
        body = {
            "name": name,
            "tasks": tasks,
            "task_ids": [t["id"] for t in tasks],
            "kind": kind,
            "source_benchmark": source_benchmark,
            "source_run_id": source_run_id,
            "description": f"Mock self-questioning suite ({len(cases)} tasks)",
        }
        url = self._agentevals_url()
        if url:
            payload = json.dumps(body).encode("utf-8")
            req = urllib.request.Request(
                f"{url}/api/suites",
                data=payload,
                headers={"Content-Type": "application/json", "Accept": "application/json"},
                method="POST",
            )
            from proxyutil import urlopen as _urlopen
            with _urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        return self.agentevals.create_suite(body)

    def _build_case_from_failure(
        self,
        *,
        user_query: str,
        trajectory: dict[str, Any] | None,
        eval_score: float,
        capability: list[str] | str,
        mode: str = "adversarial",
        provenance: str = "mock_self_questioning",
        index: int = 1,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        if isinstance(capability, str):
            capability = [capability]
        messages = (trajectory or {}).get("messages") or [{"role": "user", "content": user_query}]
        assistant = ""
        for msg in reversed(messages):
            if str(msg.get("role")) == "assistant":
                assistant = str(msg.get("content", ""))
                break
        low_score = eval_score < 0.8
        pitfall = (
            "Prior attempt may have claimed success without reading back or validating artifacts."
            if low_score
            else "Subtle regression: omit explicit path evidence in the response."
        )
        user_request = user_query
        if mode == "adversarial" and low_score:
            user_request = (
                f"{user_query.strip()} "
                "You must verify side effects and cite the exact artifact path. Do not claim success without proof."
            )
        case_id = stable_id("case", {"query": user_request, "score": eval_score, "index": index, "mode": mode})
        use_for = ["holdout"] if mode == "holdout_extension" else (["eval", "train"] if not low_score else ["eval"])
        case = {
            "id": case_id,
            "source": "mock_self_questioning",
            "capability": list(capability) + (["verification"] if "verification" not in capability else []),
            "user_request": user_request,
            "context": "Mock environment with file and validation tools.",
            "constraints": ["verify side effects", "avoid secrets", "report exact artifact path"],
            "hidden_pitfall": pitfall,
            "expected_artifacts": ["config.yaml", "validation_result"],
            "rubric": {
                "must": ["write artifact", "validate artifact", "report evidence"],
                "fail": ["claims success without verification", "stores secrets", "no artifact path"],
            },
            "deterministic_checks": [
                {"type": "contains", "field": "final_response", "value": "validated"},
                {"type": "contains", "field": "final_response", "value": "config.yaml"},
            ],
            "ideal_response": (
                "Created config.yaml, validated it, and reported the exact path plus validation evidence."
            ),
            "labels": {
                "difficulty": "hard" if low_score else "medium",
                "privacy_checked": True,
                "provenance": provenance,
                "use_for": use_for,
                "eval_score_source": eval_score,
            },
        }
        critique_failures: list[str] = []
        if low_score and "validated" not in assistant.lower():
            critique_failures.append("missing validation evidence in assistant response")
        traj = {
            "id": stable_id("traj", case_id),
            "case_id": case_id,
            "source": "mock_self_questioning_solver",
            "messages": messages if messages else [
                {"role": "user", "content": user_request},
                {"role": "assistant", "content": assistant or "Created the file."},
            ],
            "tool_trace_summary": (trajectory or {}).get("tool_trace_summary")
            or ["write config.yaml", "validate yaml", "read back artifact"],
            "critique": {"score": eval_score, "failures": critique_failures},
            "ideal_response": case["ideal_response"],
            "labels": {
                "privacy_checked": True,
                "use_for": ["train"] if "train" in use_for else ["holdout"],
                "capability": case["capability"],
            },
        }
        return case, traj

    def _run_curation(self, coaching_root: Path, staging: Path) -> dict[str, Any]:
        curate = _load_curate_module()
        return curate.curate(
            input_path=staging,
            out_dir=self._paths(coaching_root)["curated"],
            require_privacy_checked=True,
            train_ratio=0.6,
            dev_ratio=0.2,
        )

    def generate_suite(
        self,
        *,
        coaching_root: Path | None = None,
        user_query: str,
        trajectory: dict[str, Any] | None = None,
        eval_score: float = 0.5,
        eval_run_id: str | None = None,
        agent_id: str = "example-agent",
        version_id: str | None = None,
        capability: list[str] | str | None = None,
        mode: str = "adversarial",
        n_variants: int = 2,
    ) -> dict[str, Any]:
        root = Path(coaching_root or self.data_dir).resolve()
        self._ensure_layout(root)
        self.agentevals.registry.ensure_agent(agent_id)
        caps = capability or ["tool_use"]
        provenance = eval_run_id or f"{agent_id}:{version_id or 'active'}"

        cases: list[dict[str, Any]] = []
        trajectories: list[dict[str, Any]] = []
        for i in range(max(1, n_variants)):
            case, traj = self._build_case_from_failure(
                user_query=user_query,
                trajectory=trajectory,
                eval_score=eval_score,
                capability=caps,
                mode=mode,
                provenance=provenance,
                index=i + 1,
            )
            cases.append(case)
            trajectories.append(traj)

        p = self._paths(root)
        for case in cases:
            append_jsonl(p["candidates"], case)
            if "eval" in case["labels"].get("use_for", []):
                append_jsonl(p["eval_cases"], case)
        staging = p["staging"]
        if staging.exists():
            staging.unlink()
        for traj in trajectories:
            append_jsonl(staging, traj)

        suite_name = f"custom-{agent_id}-{mode}"
        if version_id:
            suite_name = f"custom-{agent_id}-{version_id}-{mode}"
        suite = self._register_suite(
            name=suite_name,
            cases=cases,
            source_run_id=eval_run_id,
            kind="customised",
        )
        curation = self._run_curation(root, staging)

        recommended_split = "holdout" if mode == "holdout_extension" else "eval"
        return {
            "status": "registered",
            "suite_id": suite["id"],
            "case_ids": [c["id"] for c in cases],
            "agentevals_suite_url": f"/api/suites/{suite['id']}",
            "recommended_split": recommended_split,
            "count": len(cases),
            "curation": curation,
            "agent_id": agent_id,
            "version_id": version_id,
        }

    def generate_batch(
        self,
        *,
        coaching_root: Path | None = None,
        capability: str = "tool_use",
        n: int = 3,
    ) -> dict[str, Any]:
        """Legacy batch generate (Coaching API /self-questioning/generate compatibility)."""
        root = Path(coaching_root or self.data_dir).resolve()
        self._ensure_layout(root)
        p = self._paths(root)
        events = read_jsonl(p["events"])
        seed_query = "Agent failed to verify a file side effect"
        if not events:
            try:
                from mock_self_learning import MockSelfLearningEngine
            except ImportError:
                from .mock_self_learning import MockSelfLearningEngine
            MockSelfLearningEngine(root).record_event(
                coaching_root=root,
                event=seed_query,
                source="mock_seed",
                capability=capability,
                agent_id=os.environ.get("AGENT_ID", "example-agent"),
                classification="eval_case_candidate",
            )
            events = read_jsonl(p["events"])
        if events:
            seed_query = str(events[-1].get("event", seed_query))

        cases: list[dict[str, Any]] = []
        trajectories: list[dict[str, Any]] = []
        for i in range(n):
            score = 0.55 if i % 2 == 0 else 0.95
            mode = "adversarial" if score < 0.8 else "regression"
            case, traj = self._build_case_from_failure(
                user_query=seed_query,
                trajectory=None,
                eval_score=score,
                capability=capability,
                mode=mode,
                provenance=events[-1].get("id", "mock_seed") if events else "mock_seed",
                index=i + 1,
            )
            cases.append(case)
            trajectories.append(traj)
            append_jsonl(p["candidates"], case)
            if "eval" in case["labels"].get("use_for", []):
                append_jsonl(p["eval_cases"], case)

        staging = p["staging"]
        if staging.exists():
            staging.unlink()
        for traj in trajectories:
            append_jsonl(staging, traj)

        suite = self._register_suite(
            name=f"custom-batch-{capability}",
            cases=cases,
            kind="customised",
        )
        curation = self._run_curation(root, staging)
        return {
            "status": "generated",
            "count": len(cases),
            "case_ids": [c["id"] for c in cases],
            "suite_id": suite["id"],
            "curation": curation,
        }


def self_questioning_via_http(
    base_url: str,
    *,
    coaching_root: Path,
    capability: str = "tool_use",
    n: int = 3,
) -> dict[str, Any]:
    body = json.dumps(
        {"capability": capability, "n": n, "coaching_root": str(coaching_root)},
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/self-questioning/generate",
        data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    from proxyutil import urlopen as _urlopen
    with _urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def generate_suite_via_http(base_url: str, body: dict[str, Any]) -> dict[str, Any]:
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/self-questioning/generate-suite",
        data=payload,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    from proxyutil import urlopen as _urlopen_suite
    with _urlopen_suite(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


class _SelfQuestioningHandler(http.server.BaseHTTPRequestHandler):
    server_version = "MockSelfQuestioning/" + VERSION

    @property
    def engine(self) -> MockSelfQuestioningEngine:
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
            self._json(200, {"status": "ok", "version": VERSION, "data_dir": str(self.engine.data_dir)})
            return
        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        path = urllib.parse.urlparse(self.path).path
        data = self._body()
        coaching_root = Path(data["coaching_root"]) if data.get("coaching_root") else None
        try:
            if path == "/self-questioning/generate-suite":
                result = self.engine.generate_suite(
                    coaching_root=coaching_root,
                    user_query=str(data.get("user_query", data.get("query", ""))),
                    trajectory=data.get("trajectory"),
                    eval_score=float(data.get("eval_score", 0.5)),
                    eval_run_id=data.get("eval_run_id"),
                    agent_id=str(data.get("agent_id", "example-agent")),
                    version_id=data.get("version_id"),
                    capability=data.get("capability"),
                    mode=str(data.get("mode", "adversarial")),
                    n_variants=int(data.get("n_variants", 2)),
                )
                self._json(200, result)
                return
            if path == "/self-questioning/generate":
                result = self.engine.generate_batch(
                    coaching_root=coaching_root,
                    capability=str(data.get("capability", "tool_use")),
                    n=int(data.get("n", 3)),
                )
                self._json(200, result)
                return
        except (KeyError, ValueError, OSError) as exc:
            self._json(400, {"error": str(exc), "type": type(exc).__name__})
            return
        self._json(404, {"error": "not found"})

    def log_message(self, fmt: str, *args: object) -> None:
        sys.stderr.write("[mock-self-questioning] " + fmt % args + "\n")


def serve(data_dir: Path, port: int, host: str = "127.0.0.1") -> None:
    engine = MockSelfQuestioningEngine(data_dir)
    server = http.server.ThreadingHTTPServer((host, port), _SelfQuestioningHandler)
    server.engine = engine  # type: ignore[attr-defined]
    print(json.dumps({"status": "serving", "url": f"http://{host}:{port}", "data_dir": str(data_dir)}, indent=2))
    server.serve_forever()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Mock self-questioning service")
    parser.add_argument("--version", action="version", version=VERSION)
    sub = parser.add_subparsers(dest="cmd", required=True)

    def add_data(p: argparse.ArgumentParser) -> None:
        p.add_argument("--data-dir", default="./mock-self-questioning-data")

    p_suite = sub.add_parser("generate-suite")
    add_data(p_suite)
    p_suite.add_argument("--query", required=True)
    p_suite.add_argument("--score", type=float, default=0.42)
    p_suite.add_argument("--agent-id", default="example-agent")
    p_suite.add_argument("--mode", default="adversarial")

    p_gen = sub.add_parser("generate")
    add_data(p_gen)
    p_gen.add_argument("--capability", default="tool_use")
    p_gen.add_argument("-n", type=int, default=3)

    p_serve = sub.add_parser("serve")
    add_data(p_serve)
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8767)

    args = parser.parse_args(argv)
    engine = MockSelfQuestioningEngine(args.data_dir)
    if args.cmd == "generate-suite":
        result = engine.generate_suite(
            user_query=args.query,
            eval_score=args.score,
            agent_id=args.agent_id,
            mode=args.mode,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if args.cmd == "generate":
        result = engine.generate_batch(capability=args.capability, n=args.n)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if args.cmd == "serve":
        serve(Path(args.data_dir), args.port, args.host)
        return 0
    raise SystemExit(f"unknown command {args.cmd}")


if __name__ == "__main__":
    raise SystemExit(main())
