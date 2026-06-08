#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Mock agent registry — version lineage for skills, tools, memory, and model_id.

Persists JSON under {data_dir}/agents/{agent_id}/. Used by mock AgentEvals (Phase 0)
and planned self-learning / self-play / AERL mocks.

CLI:
  python mock_agent_registry.py init --data-dir ./demo-stack --agent-id example-agent
  python mock_agent_registry.py serve --data-dir ./demo-stack --port 8768
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import http.server
import json
import re
import sys
import urllib.parse
from pathlib import Path
from typing import Any

VERSION = "0.1.0"
UTC = _dt.timezone.utc


class RegistryError(ValueError):
    """Invalid registry operation."""


def _now() -> str:
    return _dt.datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _stable_version_id(agent_id: str, parent: str | None, payload: dict[str, Any]) -> str:
    raw = json.dumps({"agent_id": agent_id, "parent": parent, "payload": payload}, sort_keys=True)
    return f"ver-{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:8]}"


class AgentRegistry:
    """File-backed mock agent version store."""

    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir).resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def _agent_dir(self, agent_id: str) -> Path:
        safe = re.sub(r"[^a-zA-Z0-9._-]+", "-", agent_id).strip("-") or "agent"
        return self.data_dir / "agents" / safe

    def _read_json(self, path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    def _write_json(self, path: Path, obj: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def ensure_agent(
        self,
        agent_id: str,
        *,
        model_id: str = "model-base-v1",
        skill_bundle_version: str = "skills-bootstrap",
    ) -> dict[str, Any]:
        """Create agent + bootstrap version if missing."""
        agent_dir = self._agent_dir(agent_id)
        meta_path = agent_dir / "meta.json"
        if meta_path.is_file():
            return self.get_agent(agent_id)

        version_id = "ver-0001"
        version = {
            "version_id": version_id,
            "agent_id": agent_id,
            "parent_version_id": None,
            "active": True,
            "components": {
                "model_id": model_id,
                "skill_bundle_version": skill_bundle_version,
                "tools_ref": "tools-v1",
                "memory_ref": "mem-bootstrap",
            },
            "artifacts": {},
            "source": "bootstrap",
            "created_at": _now(),
        }
        self._write_json(agent_dir / "meta.json", {"agent_id": agent_id, "created_at": _now()})
        self._write_json(agent_dir / "active.json", {"version_id": version_id})
        self._write_json(agent_dir / "versions" / f"{version_id}.json", version)
        return {"agent_id": agent_id, "active_version_id": version_id, "version": version}

    def get_agent(self, agent_id: str) -> dict[str, Any]:
        agent_dir = self._agent_dir(agent_id)
        meta_path = agent_dir / "meta.json"
        if not meta_path.is_file():
            raise RegistryError(f"agent not found: {agent_id}")
        active = self._read_json(agent_dir / "active.json")
        version_id = str(active["version_id"])
        version = self.get_version(agent_id, version_id)
        return {"agent_id": agent_id, "active_version_id": version_id, "version": version}

    def list_versions(self, agent_id: str) -> list[dict[str, Any]]:
        self.ensure_agent(agent_id)
        versions_dir = self._agent_dir(agent_id) / "versions"
        out: list[dict[str, Any]] = []
        for path in sorted(versions_dir.glob("*.json")):
            out.append(self._read_json(path))
        return out

    def get_version(self, agent_id: str, version_id: str) -> dict[str, Any]:
        path = self._agent_dir(agent_id) / "versions" / f"{version_id}.json"
        if not path.is_file():
            raise RegistryError(f"version not found: {agent_id}/{version_id}")
        return self._read_json(path)

    def create_version(
        self,
        agent_id: str,
        *,
        parent_version_id: str | None = None,
        components: dict[str, Any] | None = None,
        artifacts: dict[str, Any] | None = None,
        source: str = "manual",
    ) -> dict[str, Any]:
        self.ensure_agent(agent_id)
        parent_id = parent_version_id
        if parent_id is None:
            parent_id = str(self._read_json(self._agent_dir(agent_id) / "active.json")["version_id"])
        parent = self.get_version(agent_id, parent_id)
        merged_components = dict(parent.get("components") or {})
        if components:
            merged_components.update(components)
        version_id = _stable_version_id(agent_id, parent_id, {"components": merged_components, "source": source})
        version = {
            "version_id": version_id,
            "agent_id": agent_id,
            "parent_version_id": parent_id,
            "active": False,
            "components": merged_components,
            "artifacts": artifacts or {},
            "source": source,
            "created_at": _now(),
        }
        self._write_json(self._agent_dir(agent_id) / "versions" / f"{version_id}.json", version)
        return version

    def activate(self, agent_id: str, version_id: str) -> dict[str, Any]:
        version = self.get_version(agent_id, version_id)
        agent_dir = self._agent_dir(agent_id)
        for path in agent_dir.glob("versions/*.json"):
            doc = self._read_json(path)
            doc["active"] = doc.get("version_id") == version_id
            self._write_json(path, doc)
        self._write_json(agent_dir / "active.json", {"version_id": version_id})
        version["active"] = True
        return version

    def score_multiplier(self, agent_id: str, version_id: str) -> float:
        """Deterministic mock scoring factor from version / model ids."""
        model_id = ""
        try:
            version = self.get_version(agent_id, version_id)
            model_id = str((version.get("components") or {}).get("model_id", ""))
        except RegistryError:
            pass
        text = f"{model_id} {version_id}".lower()
        if "bad" in text or "regress" in text:
            return 0.55
        if "cand" in text or "candidate" in text:
            return 0.92
        return 1.0


class _RegistryHandler(http.server.BaseHTTPRequestHandler):
    server_version = "MockAgentRegistry/" + VERSION

    @property
    def registry(self) -> AgentRegistry:
        return self.server.registry  # type: ignore[attr-defined]

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
            self._json(200, {"status": "ok", "version": VERSION, "data_dir": str(self.registry.data_dir)})
            return
        m = re.match(r"^/api/agents/([^/]+)/versions/([^/]+)$", path)
        if m:
            try:
                self._json(200, self.registry.get_version(m.group(1), m.group(2)))
            except RegistryError as exc:
                self._json(404, {"error": str(exc)})
            return
        m = re.match(r"^/api/agents/([^/]+)/versions$", path)
        if m:
            self._json(200, {"agent_id": m.group(1), "versions": self.registry.list_versions(m.group(1))})
            return
        m = re.match(r"^/api/agents/([^/]+)$", path)
        if m:
            try:
                self._json(200, self.registry.get_agent(m.group(1)))
            except RegistryError as exc:
                self._json(404, {"error": str(exc)})
            return
        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        path = urllib.parse.urlparse(self.path).path
        m = re.match(r"^/api/agents/([^/]+)/versions$", path)
        if m:
            data = self._body()
            version = self.registry.create_version(
                m.group(1),
                parent_version_id=data.get("parent_version_id"),
                components=data.get("components"),
                artifacts=data.get("artifacts"),
                source=str(data.get("source", "http")),
            )
            self._json(201, version)
            return
        m = re.match(r"^/api/agents/([^/]+)/versions/([^/]+)/activate$", path)
        if m:
            try:
                self._json(200, self.registry.activate(m.group(1), m.group(2)))
            except RegistryError as exc:
                self._json(404, {"error": str(exc)})
            return
        self._json(404, {"error": "not found"})

    def log_message(self, fmt: str, *args: object) -> None:
        sys.stderr.write("[mock-agent-registry] " + fmt % args + "\n")


def serve(data_dir: Path, port: int, host: str = "127.0.0.1") -> None:
    registry = AgentRegistry(data_dir)
    server = http.server.ThreadingHTTPServer((host, port), _RegistryHandler)
    server.registry = registry  # type: ignore[attr-defined]
    print(json.dumps({"status": "serving", "url": f"http://{host}:{port}", "data_dir": str(data_dir)}, indent=2))
    server.serve_forever()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Mock agent registry")
    parser.add_argument("--version", action="version", version=VERSION)
    sub = parser.add_subparsers(dest="cmd", required=True)

    def add_data(p: argparse.ArgumentParser) -> None:
        p.add_argument("--data-dir", default="./mock-agent-registry-data", help="registry persistence root")

    p_init = sub.add_parser("init")
    add_data(p_init)
    p_init.add_argument("--agent-id", default="example-agent")
    p_init.add_argument("--model-id", default="model-base-v1")

    p_serve = sub.add_parser("serve")
    add_data(p_serve)
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8768)

    args = parser.parse_args(argv)
    registry = AgentRegistry(args.data_dir)
    if args.cmd == "init":
        result = registry.ensure_agent(args.agent_id, model_id=args.model_id)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if args.cmd == "serve":
        serve(Path(args.data_dir), args.port, args.host)
        return 0
    raise SystemExit(f"unknown command {args.cmd}")


if __name__ == "__main__":
    raise SystemExit(main())
