# SPDX-License-Identifier: MIT
"""Live coach bridge — delegate the clock-tick decision to a real coach agent.

The coach brain is any agent reachable over HTTP (OpenAI-style /chat/completions
by default). This bridge:

  1. Builds the decision prompt (reuses _SETUP_PROMPT from agent_bridge).
  2. Enriches it with live loop state (generation, Σ, buffer B).
  3. Sends it to the coach agent via a pluggable CoachTransport.
  4. Parses a ClockPlan from the (possibly messy) LLM response.
  5. Writes an audit record (prompt + raw response + parsed plan).

Design choices vs. MockCoachAgentBridge:
  - The scheduler pre-bakes payload.action="full_tick"; this bridge treats that
    as a *hint*, not a directive — the coach brain decides.
  - On transport failure or unparseable output, the live bridge defaults to
    "hold" (fail-safe: don't burn a real evolution cycle on uncertainty), whereas
    the mock defaults to "full_tick" (CI wants the tick to run).
"""

from __future__ import annotations

import json
import logging
import re
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Protocol

from coach.agent_bridge import ClockPlan, _SETUP_PROMPT, _VALID_ACTIONS
from coach.post import CoachPost
from coach.registry import SupervisedAgent

LOG = logging.getLogger("coach.agent_bridge_live")


class CoachTransportError(RuntimeError):
    """Failure talking to the coach agent (network / protocol)."""


class CoachTransport(Protocol):
    """Anything that turns a prompt into the coach agent's text response."""

    def complete(self, prompt: str) -> str: ...


# ---------------------------------------------------------------------------
# Response parsing helpers (pure — unit-testable without a server)
# ---------------------------------------------------------------------------

_JSON_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def parse_chat_response(data: Any) -> str:
    """Extract assistant text from an OpenAI-style chat/completions response."""
    if isinstance(data, str):
        return data
    if isinstance(data, dict):
        choices = data.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0]
            if isinstance(first, dict):
                msg = first.get("message")
                if isinstance(msg, dict) and isinstance(msg.get("content"), str):
                    return msg["content"]
                if isinstance(first.get("text"), str):
                    return first["text"]
        for key in ("content", "response", "output", "text"):
            if isinstance(data.get(key), str):
                return data[key]
    raise CoachTransportError(f"could not parse chat response: {data!r}"[:200])


def extract_json(text: str) -> dict[str, Any]:
    """Best-effort: pull the first JSON object out of an LLM response."""
    if not text:
        return {}
    fenced = _JSON_FENCE.search(text)
    if fenced:
        try:
            obj = json.loads(fenced.group(1))
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
    stripped = text.strip()
    try:
        obj = json.loads(stripped)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass
    # Scan for the first balanced {...} object.
    start = stripped.find("{")
    while start != -1:
        depth = 0
        for i in range(start, len(stripped)):
            ch = stripped[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads(stripped[start : i + 1])
                        if isinstance(obj, dict):
                            return obj
                    except json.JSONDecodeError:
                        break
        start = stripped.find("{", start + 1)
    return {}


def _safe_action(raw: Any, *, default: str = "hold") -> str:
    """Validate an action string; fall back to a fail-safe default."""
    if isinstance(raw, str) and raw in _VALID_ACTIONS:
        return raw
    return default


# ---------------------------------------------------------------------------
# HTTP transport (Phase 1 primary)
# ---------------------------------------------------------------------------


class HttpCoachTransport:
    """Direct HTTP transport to a coach agent's OpenAI-style /chat/completions.

    Localhost targets bypass any system proxy (Windows WinINET can 503 on
    127.0.0.1), mirroring the pattern used elsewhere in this repo.
    """

    def __init__(
        self,
        base_url: str,
        *,
        api_key: str | None = None,
        model: str | None = None,
        timeout_s: float = 60.0,
        path: str = "/chat/completions",
        system_prompt: str | None = None,
        temperature: float = 0.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model or "coach"
        self.timeout_s = timeout_s
        # If base_url already carries a path, treat it as the full endpoint;
        # otherwise append `path`. Avoids /chat + /chat/completions doubling.
        parsed = urllib.parse.urlparse(base_url)
        if parsed.path.rstrip("/"):
            self.endpoint = base_url.rstrip("/")
        else:
            suffix = path if path.startswith("/") else "/" + path
            self.endpoint = f"{self.base_url}{suffix}"
        self.path = path
        self.system_prompt = system_prompt or "You are a coach agent. Reply with JSON only."
        self.temperature = temperature
        self._opener = self._build_opener(self.base_url)

    @staticmethod
    def _build_opener(base_url: str) -> urllib.request.OpenerDirector:
        host = (urllib.parse.urlparse(base_url).hostname or "").lower()
        if host in ("localhost", "127.0.0.1", "::1"):
            return urllib.request.build_opener(urllib.request.ProxyHandler({}))
        return urllib.request.build_opener()

    def complete(self, prompt: str) -> str:
        url = self.endpoint
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": prompt},
            ],
            "temperature": self.temperature,
        }
        data = json.dumps(body).encode("utf-8")
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with self._opener.open(req, timeout=self.timeout_s) as resp:
                raw = resp.read().decode("utf-8")
        except Exception as exc:  # noqa: BLE001 — surface as transport error
            raise CoachTransportError(f"coach agent request to {url} failed: {exc}") from exc
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return raw  # plain-text endpoint
        return parse_chat_response(parsed)

    def complete_with_tools(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Send a multi-turn conversation with optional tool definitions.

        Returns the raw parsed response dict (caller handles tool_calls loop).
        """
        url = self.endpoint
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
        }
        if tools:
            body["tools"] = tools
        data = json.dumps(body).encode("utf-8")
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with self._opener.open(req, timeout=self.timeout_s) as resp:
                raw = resp.read().decode("utf-8")
        except Exception as exc:  # noqa: BLE001
            raise CoachTransportError(f"coach agent request to {url} failed: {exc}") from exc
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"choices": [{"message": {"content": raw}}]}


# ---------------------------------------------------------------------------
# The bridge
# ---------------------------------------------------------------------------


class AgentCoachBridge:
    """CoachAgentBridge backed by a live coach agent (any CoachTransport).

    When ``tools_enabled=True``, the bridge sends tool definitions alongside the
    prompt and executes any tool_calls the LLM returns before collecting the final
    ClockPlan. This gives the coach fine-grained actions (inspect state, write
    memories, create eval cases) beyond the 5 action labels.
    """

    def __init__(
        self,
        transport: CoachTransport,
        *,
        audit_dir: Path | None = None,
        tools_enabled: bool = False,
        max_tool_rounds: int = 5,
    ):
        self._transport = transport
        self._audit_dir = audit_dir
        self._tools_enabled = tools_enabled
        self._max_tool_rounds = max_tool_rounds

    # -- helpers --

    def _coaching_root(self, agent: SupervisedAgent) -> Path:
        from coach.trigger import resolve_coaching_root

        return resolve_coaching_root(agent)

    def _audit_path(self, agent: SupervisedAgent) -> Path:
        base = self._audit_dir or (
            self._coaching_root(agent) / ".self-coaching" / "coach" / "audit"
        )
        return base / agent.id

    def _state_context(self, agent: SupervisedAgent) -> str:
        try:
            root = self._coaching_root(agent)
            try:
                from self_coaching.loop_store import LoopStore, read_jsonl
                from self_coaching.state import LoopStateStore
            except ImportError:
                from loop_store import LoopStore, read_jsonl
                from state import LoopStateStore

            state = LoopStateStore(root).load()
            store = LoopStore(root)
            sigma = len(read_jsonl(store.support_path))
            buffer = len(store.active_buffer_rows())
            return (
                "\nLive loop state:\n"
                f"- generation: {state.generation}\n"
                f"- support set Σ: {sigma}\n"
                f"- buffer B: {buffer}\n"
                f"- tasks_processed: {state.tasks_processed}\n"
            )
        except Exception:  # noqa: BLE001 — state is best-effort context
            LOG.debug("state context unavailable for %s", agent.id, exc_info=True)
            return "\nLive loop state: (unavailable)\n"

    # -- protocol --

    def setup_clock(self, agent: SupervisedAgent, post: CoachPost) -> ClockPlan:
        prompt = _SETUP_PROMPT.format(
            agent_id=agent.id,
            post_json=json.dumps(post.to_dict(), indent=2),
        )
        # A3: scheduler may pre-bake a suggested action — hint, not directive.
        hint = post.payload.get("action") or post.payload.get("suggested_action")
        if hint:
            prompt += f"\n(Scheduler hint: suggested action={hint!r}; you may override.)\n"
        prompt += self._state_context(agent)

        raw = ""
        error: str | None = None
        parsed: dict[str, Any] = {}
        tool_results: list[dict[str, Any]] = []

        try:
            if self._tools_enabled and hasattr(self._transport, "complete_with_tools"):
                raw, parsed, tool_results = self._run_with_tools(agent, prompt)
            else:
                raw = self._transport.complete(prompt)
                parsed = extract_json(raw)
        except CoachTransportError as exc:
            error = str(exc)
            LOG.error("coach agent transport failed for %s: %s", agent.id, exc)

        # Fail-safe: hold on error or unparseable output.
        if error is not None or not parsed:
            action = "hold"
        else:
            action = _safe_action(parsed.get("action"), default="hold")

        if parsed.get("reason"):
            reason = str(parsed["reason"])
        elif error is not None:
            reason = f"transport error → hold: {error}"
        elif not parsed:
            reason = "unparseable coach response → hold"
        else:
            reason = f"coach agent decided {action}"

        overrides = parsed.get("scenario_overrides")
        if not isinstance(overrides, dict):
            overrides = {}

        plan = ClockPlan(action=action, reason=reason, scenario_overrides=overrides)
        self._write_audit(agent, post, prompt, raw, plan, error, tool_results=tool_results)
        return plan

    def _run_with_tools(
        self, agent: SupervisedAgent, prompt: str
    ) -> tuple[str, dict[str, Any], list[dict[str, Any]]]:
        """Multi-turn tool-calling loop: send prompt → handle tool_calls → get final answer."""
        from coach.coach_tools import TOOL_DEFINITIONS, execute_tool

        coaching_root = self._coaching_root(agent)
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self._transport.system_prompt},
            {"role": "user", "content": prompt},
        ]
        tool_results: list[dict[str, Any]] = []

        for _round in range(self._max_tool_rounds):
            resp = self._transport.complete_with_tools(messages, tools=TOOL_DEFINITIONS)
            choices = resp.get("choices") or []
            if not choices:
                break
            msg = choices[0].get("message") or {}
            tool_calls = msg.get("tool_calls")

            if not tool_calls:
                # No tool calls → this is the final answer
                content = msg.get("content") or ""
                return content, extract_json(content), tool_results

            # Append assistant message (with tool_calls) to conversation
            messages.append(msg)

            # Execute each tool call and append results
            for call in tool_calls:
                fn = call.get("function") or {}
                tool_name = fn.get("name", "")
                try:
                    tool_args = json.loads(fn.get("arguments", "{}"))
                except json.JSONDecodeError:
                    tool_args = {}
                result = execute_tool(tool_name, tool_args, coaching_root=coaching_root)
                tool_results.append({"tool": tool_name, "args": tool_args, "result": result})
                messages.append({
                    "role": "tool",
                    "tool_call_id": call.get("id", ""),
                    "content": json.dumps(result, ensure_ascii=False),
                })

        # Exhausted rounds — extract whatever we have
        last_content = ""
        for msg in reversed(messages):
            if msg.get("role") == "assistant" and isinstance(msg.get("content"), str):
                last_content = msg["content"]
                break
        return last_content, extract_json(last_content), tool_results

    def format_response(
        self,
        agent: SupervisedAgent,
        post: CoachPost,
        plan: ClockPlan,
        tick_result: dict[str, Any] | None,
    ) -> dict[str, Any]:
        return {
            "agent_id": agent.id,
            "post_id": post.post_id,
            "plan": plan.to_dict(),
            "tick": tick_result,
            "message": (
                f"Coach agent for {agent.id}: {plan.action} — {plan.reason}"
                + (f"; promoted={tick_result.get('t_path_promoted')}" if tick_result else "")
            ),
        }

    # -- audit --

    def _write_audit(
        self,
        agent: SupervisedAgent,
        post: CoachPost,
        prompt: str,
        raw: str,
        plan: ClockPlan,
        error: str | None,
        *,
        tool_results: list[dict[str, Any]] | None = None,
    ) -> None:
        try:
            audit = self._audit_path(agent)
            audit.mkdir(parents=True, exist_ok=True)
            (audit / "last_setup_prompt.txt").write_text(prompt, encoding="utf-8")
            decision_record: dict[str, Any] = {
                "post_id": post.post_id,
                "agent_id": agent.id,
                "raw_response": raw,
                "plan": plan.to_dict(),
                "error": error,
            }
            if tool_results:
                decision_record["tool_calls"] = tool_results
            (audit / "last_decision.json").write_text(
                json.dumps(
                    decision_record,
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        except Exception:  # noqa: BLE001 — audit must never break a tick
            LOG.debug("could not write coach audit for %s", agent.id, exc_info=True)


__all__ = [
    "AgentCoachBridge",
    "CoachTransport",
    "CoachTransportError",
    "HttpCoachTransport",
    "extract_json",
    "parse_chat_response",
]
