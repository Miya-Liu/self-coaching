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
import time
import uuid
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
    "eval_case_candidate": "self_questioning_task",
    "training_candidate": "training_manifest",
    "error_log": "none",
}

_FIXTURE_SESSIONS: list[dict[str, Any]] = [
    {
        "session_id": "sess_smoke_001",
        "title": "Verify config.yaml side effects",
        "last_active": "2026-06-15T10:00:00Z",
        "message_count": 18,
        "platform": "cli",
        "learn_optout": False,
        "review_event": "Agent claimed success without reading back config.yaml",
    },
    {
        "session_id": "sess_smoke_002",
        "title": "Lint and report findings",
        "last_active": "2026-06-15T11:30:00Z",
        "message_count": 24,
        "platform": "cli",
        "learn_optout": False,
        "review_event": "Skill patch: require explicit lint evidence before summarizing",
    },
    {
        "session_id": "sess_smoke_optout",
        "title": "Opted-out session",
        "last_active": "2026-06-15T09:00:00Z",
        "message_count": 6,
        "platform": "cli",
        "learn_optout": True,
        "review_event": "Should not be reviewed",
    },
]


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
        self._jobs: dict[str, dict[str, Any]] = {}
        self._optout: set[str] = {
            str(s["session_id"]) for s in _FIXTURE_SESSIONS if s.get("learn_optout")
        }

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
                fh.write("- fix_or_workaround: route to self-questioning/eval\n")
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
            record["durable_artifact"] = "self_questioning_seed"
            routed["self_questioning_seed"] = True

        if new_version is not None:
            routed["draft_version_id"] = new_version["version_id"]
            record["draft_version_id"] = new_version["version_id"]

        record["routing"] = routed
        return record

    def classify(self, event: str, classification: str | None = None) -> dict[str, Any]:
        kind = classify_event(event, classification)
        return {"classification": kind, "next_artifact": NEXT_ARTIFACT[kind]}

    def _session_index(self) -> dict[str, dict[str, Any]]:
        index = {str(s["session_id"]): dict(s) for s in _FIXTURE_SESSIONS}
        for sid in self._optout:
            if sid in index:
                index[sid]["learn_optout"] = True
        return index

    def list_sessions(
        self,
        *,
        hours: float = 24.0,
        limit: int = 50,
        include_optout: bool = False,
    ) -> dict[str, Any]:
        now = _dt.datetime.now(UTC)
        window_from = now - _dt.timedelta(hours=max(1.0, float(hours)))
        sessions = []
        for session in self._session_index().values():
            if not include_optout and session.get("learn_optout"):
                continue
            sessions.append(
                {
                    "session_id": session["session_id"],
                    "title": session["title"],
                    "last_active": session["last_active"],
                    "message_count": session["message_count"],
                    "platform": session["platform"],
                    "learn_optout": bool(session.get("learn_optout")),
                }
            )
        sessions.sort(key=lambda row: row["last_active"], reverse=True)
        return {
            "window": {
                "hours": hours,
                "from": window_from.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                "to": now.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            },
            "sessions": sessions[: max(1, int(limit))],
        }

    def set_optout(self, session_id: str, optout: bool = True) -> dict[str, Any]:
        if optout:
            self._optout.add(session_id)
        else:
            self._optout.discard(session_id)
        return {
            "session_id": session_id,
            "optout": optout,
            "updated_at": _now(),
        }

    def _review_session(
        self,
        *,
        coaching_root: Path | None,
        session: dict[str, Any],
        agent_id: str,
        evolve_memory: bool,
        evolve_skills: bool,
        dry_run: bool,
    ) -> dict[str, Any]:
        sid = str(session["session_id"])
        if session.get("learn_optout") or sid in self._optout:
            return {
                "session_id": sid,
                "status": "skipped",
                "reason": "session has learn_optout=true",
            }

        event = str(session.get("review_event") or session.get("title") or sid)
        classification = None
        if evolve_skills and not evolve_memory:
            classification = "skill_patch"
        elif evolve_memory and not evolve_skills:
            classification = "memory"

        if dry_run:
            kind = classify_event(event, classification)
            return {
                "session_id": sid,
                "status": "ok",
                "actions": {
                    "memory_writes": 1 if kind == "memory" else 0,
                    "skills_created": 0,
                    "skills_patched": 1 if kind == "skill_patch" else 0,
                    "summary": f"(dry_run) would route to {NEXT_ARTIFACT[kind]}",
                },
                "fork_iterations": 0,
                "tokens": {"input": 0, "output": 0},
            }

        record = self.record_event(
            coaching_root=coaching_root,
            event=event,
            source="mock-evolve",
            capability="tool_use",
            agent_id=agent_id,
            classification=classification,
        )
        kind = str(record.get("classification") or "eval_case_candidate")
        actions = {
            "memory_writes": 1 if kind == "memory" else 0,
            "skills_created": 0,
            "skills_patched": 1 if kind == "skill_patch" else 0,
            "summary": f"Mock review routed to {NEXT_ARTIFACT.get(kind, kind)}",
        }
        return {
            "session_id": sid,
            "status": "ok",
            "actions": actions,
            "fork_iterations": 3,
            "tokens": {"input": 1200, "output": 180},
            "draft_version_id": record.get("draft_version_id"),
        }

    def evolve_sessions(
        self,
        *,
        coaching_root: Path | None = None,
        session_ids: list[str],
        agent_id: str = "example-agent",
        evolve_memory: bool = True,
        evolve_skills: bool = True,
        dry_run: bool = False,
        wait: bool | None = None,
    ) -> dict[str, Any]:
        if not evolve_memory and not evolve_skills:
            raise ValueError("invalid_request: evolve_memory and evolve_skills cannot both be false")
        if not session_ids:
            raise ValueError("invalid_request: session_ids must be non-empty")

        index = self._session_index()
        missing = [sid for sid in session_ids if sid not in index]
        if missing:
            raise KeyError(f"session_not_found: {missing}")

        auto_wait = len(session_ids) <= 5
        block = auto_wait if wait is None else bool(wait)
        started = time.perf_counter()
        results = [
            self._review_session(
                coaching_root=coaching_root,
                session=index[sid],
                agent_id=agent_id,
                evolve_memory=evolve_memory,
                evolve_skills=evolve_skills,
                dry_run=dry_run,
            )
            for sid in session_ids
        ]
        completed = {
            "status": "completed",
            "duration_ms": int((time.perf_counter() - started) * 1000),
            "results": results,
        }
        if block:
            return completed

        job_id = f"learn_{_now().replace(':', '-')}_{uuid.uuid4().hex[:4]}"
        job = {
            **completed,
            "job_id": job_id,
            "started_at": _now(),
            "completed_at": _now(),
        }
        self._jobs[job_id] = job
        return {
            "status": "queued",
            "job_id": job_id,
            "session_count": len(session_ids),
            "poll_url": f"/learning/status/{job_id}",
        }

    def evolve_recent(
        self,
        *,
        coaching_root: Path | None = None,
        hours: float = 24.0,
        max_sessions: int = 10,
        agent_id: str = "example-agent",
        evolve_memory: bool = True,
        evolve_skills: bool = True,
        dry_run: bool = False,
        wait: bool | None = None,
    ) -> dict[str, Any]:
        listing = self.list_sessions(hours=hours, limit=max(1, int(max_sessions) * 2))
        candidates = [s for s in listing["sessions"] if not s.get("learn_optout")]
        selected = candidates[: max(1, int(max_sessions))]
        skipped = [
            {"session_id": s["session_id"], "reason": "max_sessions cap"}
            for s in candidates[max(1, int(max_sessions)) :]
        ]
        skipped.extend(
            {"session_id": s["session_id"], "reason": "learn_optout"}
            for s in listing["sessions"]
            if s.get("learn_optout")
        )
        if not selected:
            return {
                "status": "completed",
                "duration_ms": 0,
                "window": listing["window"],
                "sessions_found": len(listing["sessions"]),
                "sessions_reviewed": 0,
                "sessions_skipped": skipped,
                "results": [],
            }

        result = self.evolve_sessions(
            coaching_root=coaching_root,
            session_ids=[str(s["session_id"]) for s in selected],
            agent_id=agent_id,
            evolve_memory=evolve_memory,
            evolve_skills=evolve_skills,
            dry_run=dry_run,
            wait=wait,
        )
        metadata = {
            "window": listing["window"],
            "sessions_found": len(listing["sessions"]),
            "sessions_reviewed": len(selected),
            "sessions_skipped": skipped,
        }
        result.update(metadata)
        job_id = result.get("job_id")
        if job_id and job_id in self._jobs:
            self._jobs[job_id].update(metadata)
        return result

    def get_job_status(self, job_id: str) -> dict[str, Any]:
        job = self._jobs.get(job_id)
        if job is None:
            raise KeyError(f"job_not_found: {job_id}")
        return job


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
    from proxyutil import urlopen as _urlopen
    with _urlopen(req, timeout=30) as resp:
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
        if path == "/health" or path == "/learning/health":
            self._json(200, {"status": "ok", "version": VERSION, "data_dir": str(self.engine.data_dir)})
            return
        m_status = re.fullmatch(r"/learning/status/([^/]+)", path)
        if m_status:
            try:
                result = self.engine.get_job_status(m_status.group(1))
            except KeyError as exc:
                self._json(404, {"error": str(exc), "code": "job_not_found"})
                return
            self._json(200, result)
            return
        if path == "/learn/sessions":
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            hours = float((query.get("hours") or ["24"])[0])
            limit = int((query.get("limit") or ["50"])[0])
            include_optout = (query.get("include_optout") or ["false"])[0].lower() in {"1", "true", "yes"}
            self._json(
                200,
                self.engine.list_sessions(hours=hours, limit=limit, include_optout=include_optout),
            )
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
        if path == "/learning/evolve":
            coaching_root = data.get("coaching_root")
            root = Path(coaching_root) if coaching_root else None
            session_ids = data.get("session_ids") or []
            if not isinstance(session_ids, list):
                self._json(400, {"error": "session_ids must be a list", "code": "invalid_request"})
                return
            try:
                result = self.engine.evolve_sessions(
                    coaching_root=root,
                    session_ids=[str(sid) for sid in session_ids],
                    agent_id=str(data.get("agent_id", "example-agent")),
                    evolve_memory=bool(data.get("evolve_memory", True)),
                    evolve_skills=bool(data.get("evolve_skills", True)),
                    dry_run=bool(data.get("dry_run", False)),
                    wait=data.get("wait"),
                )
            except ValueError as exc:
                self._json(400, {"error": str(exc), "code": "invalid_request"})
                return
            except KeyError as exc:
                self._json(404, {"error": str(exc), "code": "session_not_found"})
                return
            code = 200 if result.get("status") == "completed" else 202
            self._json(code, result)
            return
        if path == "/learning/evolve/recent":
            coaching_root = data.get("coaching_root")
            root = Path(coaching_root) if coaching_root else None
            try:
                result = self.engine.evolve_recent(
                    coaching_root=root,
                    hours=float(data.get("hours", 24)),
                    max_sessions=int(data.get("max_sessions", 10)),
                    agent_id=str(data.get("agent_id", "example-agent")),
                    evolve_memory=bool(data.get("evolve_memory", True)),
                    evolve_skills=bool(data.get("evolve_skills", True)),
                    dry_run=bool(data.get("dry_run", False)),
                    wait=data.get("wait"),
                )
            except ValueError as exc:
                self._json(400, {"error": str(exc), "code": "invalid_request"})
                return
            code = 200 if result.get("status") == "completed" else 202
            self._json(code, result)
            return
        if path == "/learning/optout":
            session_id = str(data.get("session_id", ""))
            if not session_id:
                self._json(400, {"error": "session_id required", "code": "invalid_request"})
                return
            result = self.engine.set_optout(session_id, optout=bool(data.get("optout", True)))
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

    p_evolve = sub.add_parser("evolve")
    add_data(p_evolve)
    p_evolve.add_argument("--session-id", action="append", dest="session_ids", required=True)
    p_evolve.add_argument("--agent-id", default="example-agent")
    p_evolve.add_argument("--wait", action="store_true", default=True)

    p_recent = sub.add_parser("evolve-recent")
    add_data(p_recent)
    p_recent.add_argument("--hours", type=float, default=24.0)
    p_recent.add_argument("--max-sessions", type=int, default=10)
    p_recent.add_argument("--agent-id", default="example-agent")

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
    if args.cmd == "evolve":
        result = engine.evolve_sessions(
            session_ids=args.session_ids,
            agent_id=args.agent_id,
            wait=args.wait,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if args.cmd == "evolve-recent":
        result = engine.evolve_recent(
            hours=args.hours,
            max_sessions=args.max_sessions,
            agent_id=args.agent_id,
            wait=False,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if args.cmd == "serve":
        serve(Path(args.data_dir), args.port, args.host)
        return 0
    raise SystemExit(f"unknown command {args.cmd}")


if __name__ == "__main__":
    raise SystemExit(main())
