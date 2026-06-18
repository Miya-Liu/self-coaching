# SPDX-License-Identifier: MIT
"""SubjectTaskSource — drive a live agent to produce real trajectories (Phase 2).

Replaces the deterministic ``simulate_trajectory`` fixture producer with a real
HTTP call to the supervised subject agent (``coach_clock.subject_chat_url``).

The subject is expected to expose an OpenAI-style ``/chat/completions`` endpoint.
For each task ``tau`` the source:

  1. Sends the task's user_request as a chat message.
  2. Receives the assistant response.
  3. Shapes it into the trajectory ``xi`` the rubric scorer consumes:
       { task_id, messages, tool_trace_summary, final_answer, capability }

Tool usage: if the subject returns OpenAI ``tool_calls``, their function names
become the ``tool_trace_summary``. A subject that answers without invoking tools
yields an empty trace — which the rubric correctly scores as "missing tools" for
tool-requiring tasks. This is faithful: the coach learns from the agent's real
behavior, not a simulation.

Usage:
    source = SubjectTaskSource("http://subject:8000")
    xi = source(tau)                      # callable: tau -> xi
    # inject into the loop:
    run_tasks(root, trajectory_fn=source, ...)
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any


class SubjectSourceError(RuntimeError):
    """Failure driving the subject agent."""


def _user_request(tau: dict[str, Any]) -> str:
    for key in ("user_request", "prompt", "task_text"):
        value = tau.get(key)
        if value:
            return str(value)
    return f"Complete task {tau.get('task_id', 'unknown')}"


def extract_assistant_content(data: Any) -> str:
    """Pull assistant text from an OpenAI-style chat/completions response."""
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
    return ""


def extract_tool_trace(data: Any) -> list[str]:
    """Extract tool/function names from an OpenAI-style response.

    Recognizes:
      - choices[0].message.tool_calls[].function.name (OpenAI tool-calling)
      - top-level "tool_trace_summary" (subjects that report directly)
    """
    if not isinstance(data, dict):
        return []
    # Direct report (a cooperative subject may include this)
    direct = data.get("tool_trace_summary")
    if isinstance(direct, list):
        return [str(entry) for entry in direct]
    choices = data.get("choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        msg = choices[0].get("message")
        if isinstance(msg, dict):
            tool_calls = msg.get("tool_calls")
            if isinstance(tool_calls, list):
                names: list[str] = []
                for call in tool_calls:
                    if not isinstance(call, dict):
                        continue
                    fn = call.get("function")
                    if isinstance(fn, dict) and fn.get("name"):
                        names.append(f"invoke {fn['name']}")
                    elif call.get("name"):
                        names.append(f"invoke {call['name']}")
                return names
    return []


def build_xi(tau: dict[str, Any], *, final_answer: str, tool_trace: list[str]) -> dict[str, Any]:
    """Shape a subject response into the trajectory xi the scorer expects."""
    user_request = _user_request(tau)
    return {
        "task_id": tau.get("task_id"),
        "messages": [
            {"role": "user", "content": user_request},
            {"role": "assistant", "content": final_answer},
        ],
        "tool_trace_summary": tool_trace,
        "final_answer": final_answer,
        "capability": tau.get("capability") or ["tool_use"],
        "_source": "live_subject",
    }


def resolve_endpoint(base_url: str, path: str) -> str:
    """Resolve the chat endpoint URL.

    If ``base_url`` already includes a path component (e.g. ``/chat`` or
    ``/v1/chat/completions``), it is treated as the full endpoint and ``path``
    is ignored. Only when ``base_url`` is bare (no path, or just ``/``) is
    ``path`` appended. This avoids the ``/chat`` + ``/chat/completions`` =
    ``/chat/chat/completions`` footgun and keeps the legacy
    ``agent_chat_url: http://host:8000/chat`` convention working.
    """
    parsed = urllib.parse.urlparse(base_url)
    existing = parsed.path.rstrip("/")
    if existing:  # operator supplied a full endpoint path
        return base_url.rstrip("/")
    suffix = path if path.startswith("/") else "/" + path
    return f"{base_url.rstrip('/')}{suffix}"


class SubjectTaskSource:
    """Callable that turns a task ``tau`` into a real trajectory ``xi``.

    Localhost targets bypass the system proxy (Windows WinINET can 503 on
    127.0.0.1), mirroring the rest of the repo's HTTP clients.

    ``subject_chat_url`` may be either a bare base (``http://host:8000`` →
    ``path`` appended) or a full endpoint (``http://host:8000/chat`` → used
    as-is). See :func:`resolve_endpoint`.
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
        if not base_url:
            raise SubjectSourceError("SubjectTaskSource requires a non-empty base_url")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model or "subject"
        self.timeout_s = timeout_s
        self.endpoint = resolve_endpoint(base_url, path)
        self.system_prompt = system_prompt
        self.temperature = temperature
        self._opener = self._build_opener(self.base_url)

    @staticmethod
    def _build_opener(base_url: str) -> urllib.request.OpenerDirector:
        host = (urllib.parse.urlparse(base_url).hostname or "").lower()
        if host in ("localhost", "127.0.0.1", "::1"):
            return urllib.request.build_opener(urllib.request.ProxyHandler({}))
        return urllib.request.build_opener()

    def _call(self, user_request: str) -> Any:
        url = self.endpoint
        messages: list[dict[str, str]] = []
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})
        messages.append({"role": "user", "content": user_request})
        body = {"model": self.model, "messages": messages, "temperature": self.temperature}
        data = json.dumps(body).encode("utf-8")
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with self._opener.open(req, timeout=self.timeout_s) as resp:
                raw = resp.read().decode("utf-8")
        except Exception as exc:  # noqa: BLE001
            raise SubjectSourceError(f"subject request to {url} failed: {exc}") from exc
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw

    def __call__(self, tau: dict[str, Any]) -> dict[str, Any]:
        user_request = _user_request(tau)
        data = self._call(user_request)
        final_answer = extract_assistant_content(data)
        tool_trace = extract_tool_trace(data)
        return build_xi(tau, final_answer=final_answer, tool_trace=tool_trace)


def build_subject_source(
    subject_chat_url: str | None,
    *,
    api_key: str | None = None,
    model: str | None = None,
    path: str = "/chat/completions",
    timeout_s: float = 60.0,
) -> SubjectTaskSource | None:
    """Return a SubjectTaskSource when a URL is configured, else None (use fixtures)."""
    if not subject_chat_url:
        return None
    return SubjectTaskSource(
        subject_chat_url,
        api_key=api_key,
        model=model,
        path=path,
        timeout_s=timeout_s,
    )


__all__ = [
    "SubjectTaskSource",
    "SubjectSourceError",
    "build_subject_source",
    "build_xi",
    "extract_assistant_content",
    "extract_tool_trace",
    "resolve_endpoint",
]
