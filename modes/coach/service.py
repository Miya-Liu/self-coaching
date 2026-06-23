# SPDX-License-Identifier: MIT
"""24×7 coach clock service — HTTP POST + WebSocket ingress."""

from __future__ import annotations

import argparse
import json
import logging
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from coach.agent_bridge import MockCoachAgentBridge
from coach.registry import default_registry_path, load_registry
from coach.scheduler import ClockScheduler
from coach.trigger import handle_post_body

LOG = logging.getLogger("coach.service")


def build_coach_bridge() -> Any:
    """Select the coach bridge from env.

    COACH_BRIDGE=mock   (default) → MockCoachAgentBridge (deterministic, CI-safe)
    COACH_BRIDGE=agent            → AgentCoachBridge over an HTTP coach agent

    For COACH_BRIDGE=agent, COACH_AGENT_URL is required. Optional:
      COACH_AGENT_API_KEY, COACH_AGENT_MODEL, COACH_AGENT_TIMEOUT_S.
    """
    import os

    kind = os.environ.get("COACH_BRIDGE", "mock").strip().lower()
    if kind in ("", "mock"):
        return MockCoachAgentBridge()
    if kind == "agent":
        base_url = os.environ.get("COACH_AGENT_URL")
        if not base_url:
            raise SystemExit("COACH_BRIDGE=agent requires COACH_AGENT_URL")
        from coach.agent_bridge_live import AgentCoachBridge, HttpCoachTransport

        transport = HttpCoachTransport(
            base_url,
            api_key=os.environ.get("COACH_AGENT_API_KEY"),
            model=os.environ.get("COACH_AGENT_MODEL"),
            timeout_s=float(os.environ.get("COACH_AGENT_TIMEOUT_S", "60")),
            path=os.environ.get("COACH_AGENT_PATH", "/chat/completions"),
        )
        tools_enabled = os.environ.get("COACH_TOOLS_ENABLED", "").strip().lower() in ("1", "true", "yes")
        return AgentCoachBridge(transport, tools_enabled=tools_enabled)
    raise SystemExit(f"unknown COACH_BRIDGE={kind!r} (expected 'mock' or 'agent')")


class CoachServiceState:
    def __init__(self, registry_path: Path, bridge: Any | None = None):
        self.registry_path = registry_path
        self.bridge = bridge or MockCoachAgentBridge()
        self._ws_clients: list[Any] = []
        self._ws_lock = threading.Lock()

    def handle_post(self, body: dict[str, Any]) -> dict[str, Any]:
        return handle_post_body(body, self.registry_path, self.bridge)

    def register_ws(self, ws: Any) -> None:
        with self._ws_lock:
            self._ws_clients.append(ws)

    def unregister_ws(self, ws: Any) -> None:
        with self._ws_lock:
            if ws in self._ws_clients:
                self._ws_clients.remove(ws)

    async def broadcast(self, message: dict[str, Any]) -> None:
        payload = json.dumps(message, ensure_ascii=False)
        with self._ws_lock:
            clients = list(self._ws_clients)
        dead: list[Any] = []
        for ws in clients:
            try:
                await ws.send(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.unregister_ws(ws)


def _read_json_body(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length", 0))
    raw = handler.rfile.read(length) if length else b"{}"
    data = json.loads(raw.decode("utf-8") or "{}")
    if not isinstance(data, dict):
        raise ValueError("body must be a JSON object")
    return data


def make_handler(state: CoachServiceState):
    class CoachHTTPHandler(BaseHTTPRequestHandler):
        server_state = state

        def log_message(self, fmt: str, *args: Any) -> None:
            LOG.info("%s - %s", self.address_string(), fmt % args)

        def _send_json(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path == "/health":
                agents = load_registry(self.server_state.registry_path)
                self._send_json(
                    200,
                    {
                        "status": "ok",
                        "service": "coach-clock",
                        "agents": [a.id for a in agents],
                        "registry": str(self.server_state.registry_path),
                    },
                )
                return
            self._send_json(404, {"error": "not_found"})

        def do_POST(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path not in ("/coach/post", "/coach/ingest"):
                self._send_json(404, {"error": "not_found", "path": path})
                return
            try:
                body = _read_json_body(self)
                result = self.server_state.handle_post(body)
                self._send_json(200, result)
            except KeyError as exc:
                self._send_json(404, {"error": "agent_not_found", "detail": str(exc)})
            except ValueError as exc:
                self._send_json(400, {"error": "invalid_request", "detail": str(exc)})
            except Exception as exc:
                LOG.exception("coach post failed")
                self._send_json(500, {"error": "internal_error", "detail": str(exc)})

    return CoachHTTPHandler


def run_http_server(state: CoachServiceState, host: str, port: int) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((host, port), make_handler(state))
    thread = threading.Thread(target=server.serve_forever, name="coach-http", daemon=True)
    thread.start()
    LOG.info("coach HTTP listening on http://%s:%s (POST /coach/post)", host, port)
    return server


def run_ws_server(state: CoachServiceState, host: str, port: int) -> Any:
    try:
        from ws_server import run_ws_loop
    except ImportError as exc:
        raise RuntimeError(
            "WebSocket support requires: pip install -e '.[coach]'"
        ) from exc
    thread = threading.Thread(
        target=run_ws_loop,
        args=(state, host, port),
        name="coach-ws",
        daemon=True,
    )
    thread.start()
    LOG.info("coach WebSocket listening on ws://%s:%s/coach/ws", host, port)
    return thread


def cmd_serve(args: argparse.Namespace) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    registry_path = Path(args.registry).resolve()
    if not registry_path.is_file():
        raise SystemExit(f"registry not found: {registry_path}")

    state = CoachServiceState(registry_path, bridge=build_coach_bridge())
    host, port = _parse_bind(args.bind)
    http_server = run_http_server(state, host, port)

    # Start periodic scheduler for all enabled agents
    scheduler: ClockScheduler | None = None
    if not args.once:
        scheduler = ClockScheduler(registry_path, bridge=state.bridge)
        scheduler.start()
        LOG.info("coach scheduler active (%d agents)", len(scheduler.agent_states()))

    if args.ws_port is not None:
        ws_host = args.ws_host or host
        try:
            run_ws_server(state, ws_host, args.ws_port)
        except RuntimeError as exc:
            LOG.warning("%s", exc)

    if args.once:
        http_server.shutdown()
        return 0

    LOG.info("coach clock service running (Ctrl+C to stop)")
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        LOG.info("shutting down")
    if scheduler is not None:
        scheduler.stop()
    http_server.shutdown()
    return 0


def _parse_bind(bind: str) -> tuple[str, int]:
    if ":" not in bind:
        raise ValueError(f"bind must be host:port, got {bind!r}")
    host, port_s = bind.rsplit(":", 1)
    return host, int(port_s)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Coach clock 24×7 service (HTTP + optional WebSocket)")
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="Run coach clock ingress service")
    serve.add_argument(
        "--registry",
        type=Path,
        default=default_registry_path(),
        help="Supervision registry (agents.yaml)",
    )
    serve.add_argument("--bind", default="127.0.0.1:8768", help="HTTP bind host:port")
    serve.add_argument("--ws-port", type=int, default=None, help="WebSocket port (requires [coach] extra)")
    serve.add_argument("--ws-host", default=None, help="WebSocket bind host (default: HTTP host)")
    serve.add_argument("--once", action="store_true", help="Start and exit (smoke / tests)")
    serve.set_defaults(func=cmd_serve)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
