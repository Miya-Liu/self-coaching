#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Mock self-learning service — classify events, route artifacts, bump registry versions.

Phase 1 mock platform. Uses AgentRegistry (shared --data-dir) in-process.

CLI:
  python mock_self_learning.py serve --data-dir ./demo-stack --port 8766
  python mock_self_learning.py record --data-dir ./demo-stack --event "..." --agent-id example-agent
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import http.server
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

try:
    from mock_agent_registry import AgentRegistry
except ImportError:  # pragma: no cover
    from .mock_agent_registry import AgentRegistry

VERSION = "0.1.0"
UTC = _dt.timezone.utc

CLASSIFICATIONS = frozenset({
    "memory",
    "skill_patch",
    "eval_case_candidate",
    "training_candidate",
    "error_log",
})

NEXT_ARTIFACT = {
    "memory": "memory",
    "skill_patch": "skill_patch",
    "eval_case_candidate": "self_play_task",
    "training_candidate": "training_manifest",
    "error_log": "none",
}


def _now() -> str:
    return _dt.datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def stable_id(prefix: str, payload: object) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return f"{prefix}-{hashlib.sha1(raw).hexdigest()[:10]}"


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def classify_event(event: str, explicit: str | None = None) -> str:
    if explicit and explicit in CLASSIFICATIONS:
        return explicit
    text = event.lower()
    if any(k in text for k in ("crash", "oom", "parse error", "exception", "failed with")):
        return "error_log"
    if any(k in text for k in ("skill", "patch", "instruction", "pitfall")):
        return "skill_patch"
    if any(k in text for k in ("memory", "preference", "always use", "never ")):
        return "memory"
    if any(k in text for k in ("train", "fine-tune", "model gap", "sft", "grpo")):
        return "training_candidate"
    return "eval_case_candidate"


class MockSelfLearningEngine:
    """Record learning events, route durable artifacts, draft registry versions."""

    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir).resolve()
        self.registry = AgentRegistry(self.data_dir)

    def _paths(self, root: Path) -> dict[str, Path]:
        base = root / ".self-coaching"
        return {
            "events": base / "events" / "learning_events.jsonl",
            "memory": base / "memory" / "facts.jsonl",
            "patches": base / "skills" / "patches",
            "experience": root / "experience",
        }

    def _ensure_layout(self, root: Path) -> None:
        p = self._paths(root)
        p["events"].parent.mkdir(parents=True, exist_ok=True)
        p["memory"].parent.mkdir(parents=True, exist_ok=True)
        p["patches"].mkdir(parents=True, exist_ok=True)
        p["experience"].mkdir(parents=True, exist_ok=True)
        for name, title in [
            ("EXPERIMENT_LOG.md", "# Experiment log (mock self-coaching)\n"),
            ("ERROR.md", "# Error log (mock self-coaching)\n"),
            ("LEARNINGS.md", "# Learnings (mock self-coaching)\n"),
        ]:
            path = p["experience"] / name
            if not path.exists():
                path.write_text(title, encoding="utf-8")

    def record_event(
        self,
        *,
        coaching_root: Path | None = None,
        event: str,
        source: str = "manual",
        capability: str = "tool_use",
        agent_id: str = "example-agent",
        version_id: str | None = None,
        classification: str | None = None,
    ) -> dict[str, Any]:
        root = Path(coaching_root or self.data_dir).resolve()
        self._ensure_layout(root)
        self.registry.ensure_agent(agent_id)
        if version_id is None:
            version_id = str(self.registry.get_agent(agent_id)["active_version_id"])

        kind = classify_event(event, classification)
        record_id = stable_id("learn", {"event": event, "source": source, "capability": capability, "kind": kind})
        record: dict[str, Any] = {
            "id": record_id,
            "timestamp": _now(),
            "source": source,
            "capability": [capability],
            "event": event,
            "classification": kind,
            "agent_id": agent_id,
            "version_id": version_id,
            "privacy_checked": True,
            "durable_artifact": NEXT_ARTIFACT[kind],
            "notes": "Mock self-learning event. No secrets or raw transcript stored.",
        }

        routed: dict[str, Any] = {"classification": kind, "next_artifact": NEXT_ARTIFACT[kind]}
        new_version: dict[str, Any] | None = None

        p = self._paths(root)
        append_jsonl(p["events"], record)

        learn_md = p["experience"] / "LEARNINGS.md"
        with learn_md.open("a", encoding="utf-8") as fh:
            fh.write(f"\n## {record['timestamp']} {record_id}\n")
            fh.write(f"- category: {kind}\n- context: {source}\n- observation: {event}\n")
            fh.write(f"- reusable_lesson: routed to {NEXT_ARTIFACT[kind]}.\n")
            fh.write(f"- next_artifact: {NEXT_ARTIFACT[kind]}\n")

        if kind == "memory":
            fact = {
                "id": stable_id("mem", record_id),
                "timestamp": record["timestamp"],
                "agent_id": agent_id,
                "fact": event[:500],
                "source": record_id,
                "privacy_checked": True,
            }
            append_jsonl(p["memory"], fact)
            routed["memory_fact_id"] = fact["id"]
            mem_ref = f"mem-{hashlib.sha1(agent_id.encode()).hexdigest()[:8]}"
            new_version = self.registry.create_version(
                agent_id,
                parent_version_id=version_id,
                components={"memory_ref": mem_ref},
                artifacts={"memory_path": str(p["memory"])},
                source="self-learning",
            )
            record["memory_ref"] = mem_ref

        elif kind == "skill_patch":
            patch_id = stable_id("patch", record_id)
            patch_path = p["patches"] / f"{patch_id}.md"
            patch_path.write_text(
                f"# Skill patch {patch_id}\n\n- agent_id: {agent_id}\n- source: {record_id}\n\n"
                f"## Observation\n{event}\n\n## Mock patch\n"
                "- Add explicit verification step before claiming success.\n",
                encoding="utf-8",
            )
            skill_ver = f"skills-{patch_id[-8:]}"
            new_version = self.registry.create_version(
                agent_id,
                parent_version_id=version_id,
                components={"skill_bundle_version": skill_ver},
                artifacts={"skill_patches": [str(patch_path)]},
                source="self-learning",
            )
            routed["patch_id"] = patch_id
            routed["skill_bundle_version"] = skill_ver
            record["skill_bundle_version"] = skill_ver

        elif kind == "error_log":
            err_md = p["experience"] / "ERROR.md"
            with err_md.open("a", encoding="utf-8") as fh:
                fh.write(f"\n## {record['timestamp']} {record_id}\n")
                fh.write("- category: logic_bug\n")
                fh.write(f"- symptom: {event}\n")
                fh.write(f"- command/log: source={source}\n")
                fh.write("- root_cause: (mock) undiagnosed\n")
                fh.write("- fix_or_workaround: route to self-play/eval\n")
                fh.write("- verification: pending\n")
                fh.write("- durable_artifact: eval_case\n")

        elif kind == "training_candidate":
            new_version = self.registry.create_version(
                agent_id,
                parent_version_id=version_id,
                components={},
                artifacts={"training_candidate": True, "learning_event_id": record_id},
                source="self-learning",
            )
            routed["training_candidate"] = True

        else:
            record["durable_artifact"] = "self_play_seed"
            routed["self_play_seed"] = True

        if new_version is not None:
            routed["draft_version_id"] = new_version["version_id"]
            record["draft_version_id"] = new_version["version_id"]

        record["routing"] = routed
        return record

    def classify(self, event: str, classification: str | None = None) -> dict[str, Any]:
        kind = classify_event(event, classification)
        return {"classification": kind, "next_artifact": NEXT_ARTIFACT[kind]}


def learn_via_http(
    base_url: str,
    *,
    coaching_root: Path,
    event: str,
    source: str = "manual",
    capability: str = "tool_use",
    agent_id: str = "example-agent",
    version_id: str | None = None,
    classification: str | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "event": event,
        "source": source,
        "capability": capability,
        "agent_id": agent_id,
        "coaching_root": str(coaching_root),
    }
    if version_id:
        body["version_id"] = version_id
    if classification:
        body["classification"] = classification
    payload = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/learning/events",
        data=payload,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


class _SelfLearningHandler(http.server.BaseHTTPRequestHandler):
    server_version = "MockSelfLearning/" + VERSION

    @property
    def engine(self) -> MockSelfLearningEngine:
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
        if path == "/learning/events":
            coaching_root = data.get("coaching_root")
            root = Path(coaching_root) if coaching_root else None
            result = self.engine.record_event(
                coaching_root=root,
                event=str(data.get("event", "")),
                source=str(data.get("source", "http")),
                capability=str(data.get("capability", "tool_use")),
                agent_id=str(data.get("agent_id", "example-agent")),
                version_id=data.get("version_id"),
                classification=data.get("classification"),
            )
            self._json(200, result)
            return
        if path == "/learning/classify":
            result = self.engine.classify(
                str(data.get("event", "")),
                classification=data.get("classification"),
            )
            self._json(200, result)
            return
        self._json(404, {"error": "not found"})

    def log_message(self, fmt: str, *args: object) -> None:
        sys.stderr.write("[mock-self-learning] " + fmt % args + "\n")


def serve(data_dir: Path, port: int, host: str = "127.0.0.1") -> None:
    engine = MockSelfLearningEngine(data_dir)
    server = http.server.ThreadingHTTPServer((host, port), _SelfLearningHandler)
    server.engine = engine  # type: ignore[attr-defined]
    print(json.dumps({"status": "serving", "url": f"http://{host}:{port}", "data_dir": str(data_dir)}, indent=2))
    server.serve_forever()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Mock self-learning service")
    parser.add_argument("--version", action="version", version=VERSION)
    sub = parser.add_subparsers(dest="cmd", required=True)

    def add_data(p: argparse.ArgumentParser) -> None:
        p.add_argument("--data-dir", default="./mock-self-learning-data")

    p_record = sub.add_parser("record")
    add_data(p_record)
    p_record.add_argument("--event", required=True)
    p_record.add_argument("--source", default="cli")
    p_record.add_argument("--capability", default="tool_use")
    p_record.add_argument("--agent-id", default="example-agent")
    p_record.add_argument("--classification")

    p_serve = sub.add_parser("serve")
    add_data(p_serve)
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8766)

    args = parser.parse_args(argv)
    engine = MockSelfLearningEngine(args.data_dir)
    if args.cmd == "record":
        result = engine.record_event(
            event=args.event,
            source=args.source,
            capability=args.capability,
            agent_id=args.agent_id,
            classification=args.classification,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if args.cmd == "serve":
        serve(Path(args.data_dir), args.port, args.host)
        return 0
    raise SystemExit(f"unknown command {args.cmd}")


if __name__ == "__main__":
    raise SystemExit(main())
