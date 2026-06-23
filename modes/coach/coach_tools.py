# SPDX-License-Identifier: MIT
"""Coach tool definitions and executor — gives the coach agent *hands*.

When COACH_TOOLS_ENABLED=1, the AgentCoachBridge sends these tool definitions
alongside the decision prompt. The coach LLM can invoke them via tool_calls in
its response; the bridge executes them server-side before finalizing ClockPlan.

This enables fine-grained actions beyond the 5 action labels:
  - Inspect loop state in detail
  - Write a memory/learning entry
  - Create an eval case
  - Target specific capabilities in self-questioning
  - Read recent failures

The tools operate on the supervised agent's coaching_root (not the coach's own state).

Design:
  - Tools are pure functions that take (coaching_root, **params) → result dict.
  - The schema is OpenAI function-calling compatible (name, description, parameters).
  - Execution is sandboxed to the coaching_root filesystem + loop store reads/writes.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Tool definitions (OpenAI function-calling schema)
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_loop_state",
            "description": "Get the current loop state: generation, support set Σ size, buffer B size, tasks processed.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_recent_failures",
            "description": "Get the N most recent entries from the support set (failures). Returns task_id, score, and event_text for each.",
            "parameters": {
                "type": "object",
                "properties": {
                    "n": {"type": "integer", "description": "Number of recent failures to return", "default": 5},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_buffer_status",
            "description": "Get tuning buffer status: total rows, active (unconsumed) rows, and the beta threshold.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "record_learning",
            "description": "Append a learning entry to the agent's experience/LEARNINGS.md file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Short title for the learning entry"},
                    "category": {
                        "type": "string",
                        "enum": ["optimization", "process", "metric", "stability", "best_practice"],
                        "description": "Category of the learning",
                    },
                    "observation": {"type": "string", "description": "What was observed"},
                    "lesson": {"type": "string", "description": "The reusable lesson"},
                },
                "required": ["title", "observation", "lesson"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "record_error",
            "description": "Append an error entry to the agent's experience/ERROR.md file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Short title for the error entry"},
                    "category": {
                        "type": "string",
                        "enum": ["crash", "oom", "parse_error", "env", "logic_bug", "timeout", "other"],
                        "description": "Error category",
                    },
                    "symptom": {"type": "string", "description": "What went wrong"},
                    "root_cause": {"type": "string", "description": "Why it happened"},
                    "fix": {"type": "string", "description": "How it was resolved"},
                },
                "required": ["title", "symptom"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_eval_case",
            "description": "Append an eval case to .self-coaching/cases/eval_cases.jsonl for future regression testing.",
            "parameters": {
                "type": "object",
                "properties": {
                    "case_id": {"type": "string", "description": "Unique stable identifier for the case"},
                    "capability": {"type": "string", "description": "Target capability (tool_use, safety, reasoning, etc.)"},
                    "prompt": {"type": "string", "description": "The task prompt for the eval case"},
                    "must_contain": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Substrings the answer must contain",
                    },
                    "must_not_contain": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Substrings the answer must NOT contain",
                    },
                },
                "required": ["case_id", "capability", "prompt", "must_contain"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_tick_history",
            "description": "Get the last N tick events from the tick log (action, outcome, duration).",
            "parameters": {
                "type": "object",
                "properties": {
                    "n": {"type": "integer", "description": "Number of recent ticks to return", "default": 10},
                },
                "required": [],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Tool executor
# ---------------------------------------------------------------------------


def execute_tool(
    name: str,
    arguments: dict[str, Any],
    *,
    coaching_root: Path,
    config: Any | None = None,
) -> dict[str, Any]:
    """Execute a coach tool and return its result."""
    try:
        if name == "get_loop_state":
            return _get_loop_state(coaching_root, config)
        if name == "get_recent_failures":
            return _get_recent_failures(coaching_root, arguments.get("n", 5))
        if name == "get_buffer_status":
            return _get_buffer_status(coaching_root, config)
        if name == "record_learning":
            return _record_learning(coaching_root, arguments)
        if name == "record_error":
            return _record_error(coaching_root, arguments)
        if name == "create_eval_case":
            return _create_eval_case(coaching_root, arguments)
        if name == "get_tick_history":
            return _get_tick_history(coaching_root, arguments.get("n", 10))
        return {"error": f"unknown tool: {name}"}
    except Exception as exc:  # noqa: BLE001
        return {"error": f"tool {name} failed: {exc}"}


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


def _get_loop_state(coaching_root: Path, config: Any | None) -> dict[str, Any]:
    try:
        from self_coaching.loop_store import LoopStore, read_jsonl
        from self_coaching.state import LoopStateStore
    except ImportError:
        from loop_store import LoopStore, read_jsonl
        from state import LoopStateStore

    state = LoopStateStore(coaching_root).load()
    store = LoopStore(coaching_root)
    sigma = len(read_jsonl(store.support_path))
    buffer = len(store.active_buffer_rows())
    sigma_min = getattr(config, "sigma_min", 3) if config else 3
    beta = getattr(config, "batch_size", 4) if config else 4
    return {
        "generation": state.generation,
        "tasks_processed": state.tasks_processed,
        "support_set_size": sigma,
        "buffer_size": buffer,
        "sigma_min_threshold": sigma_min,
        "beta_threshold": beta,
        "sigma_ready": sigma >= sigma_min,
        "buffer_ready": buffer >= beta,
    }


def _get_recent_failures(coaching_root: Path, n: int) -> dict[str, Any]:
    try:
        from self_coaching.loop_store import LoopStore, read_jsonl
    except ImportError:
        from loop_store import LoopStore, read_jsonl

    store = LoopStore(coaching_root)
    rows = read_jsonl(store.support_path)
    recent = rows[-n:] if n > 0 else rows
    entries = [
        {"task_id": r.get("task_id"), "score": r.get("score"), "event_text": r.get("event_text")}
        for r in recent
    ]
    return {"total_failures": len(rows), "recent": entries}


def _get_buffer_status(coaching_root: Path, config: Any | None) -> dict[str, Any]:
    try:
        from self_coaching.loop_store import LoopStore, read_jsonl
    except ImportError:
        from loop_store import LoopStore, read_jsonl

    store = LoopStore(coaching_root)
    all_rows = read_jsonl(store.buffer_path)
    active = [r for r in all_rows if not r.get("used_for_train")]
    beta = getattr(config, "batch_size", 4) if config else 4
    return {
        "total_rows": len(all_rows),
        "active_rows": len(active),
        "consumed_rows": len(all_rows) - len(active),
        "beta_threshold": beta,
        "ready_for_tune": len(active) >= beta,
    }


def _record_learning(coaching_root: Path, args: dict[str, Any]) -> dict[str, Any]:
    from datetime import datetime, timezone

    exp_dir = coaching_root / "experience"
    exp_dir.mkdir(parents=True, exist_ok=True)
    path = exp_dir / "LEARNINGS.md"
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    title = args.get("title", "Untitled")
    category = args.get("category", "process")
    observation = args.get("observation", "")
    lesson = args.get("lesson", "")
    entry = (
        f"\n## {date} {title}\n"
        f"- category: {category}\n"
        f"- observation: {observation}\n"
        f"- reusable_lesson: {lesson}\n"
        f"- next_artifact: none\n"
    )
    with path.open("a", encoding="utf-8") as f:
        f.write(entry)
    return {"status": "recorded", "path": str(path), "title": title}


def _record_error(coaching_root: Path, args: dict[str, Any]) -> dict[str, Any]:
    from datetime import datetime, timezone

    exp_dir = coaching_root / "experience"
    exp_dir.mkdir(parents=True, exist_ok=True)
    path = exp_dir / "ERROR.md"
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    title = args.get("title", "Untitled")
    category = args.get("category", "other")
    symptom = args.get("symptom", "")
    root_cause = args.get("root_cause", "unknown")
    fix = args.get("fix", "pending")
    entry = (
        f"\n## {date} {title}\n"
        f"- category: {category}\n"
        f"- symptom: {symptom}\n"
        f"- root_cause: {root_cause}\n"
        f"- fix_or_workaround: {fix}\n"
        f"- durable_artifact: none\n"
    )
    with path.open("a", encoding="utf-8") as f:
        f.write(entry)
    return {"status": "recorded", "path": str(path), "title": title}


def _create_eval_case(coaching_root: Path, args: dict[str, Any]) -> dict[str, Any]:
    cases_dir = coaching_root / ".self-coaching" / "cases"
    cases_dir.mkdir(parents=True, exist_ok=True)
    path = cases_dir / "eval_cases.jsonl"
    case = {
        "case_id": args["case_id"],
        "capability": args["capability"],
        "prompt": args["prompt"],
        "checks": {
            "must_contain": args.get("must_contain", []),
            "must_not_contain": args.get("must_not_contain", []),
            "match_mode": "all_of_must_contain",
        },
        "budget_tokens": 250,
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(case, ensure_ascii=False, sort_keys=True) + "\n")
    return {"status": "created", "case_id": args["case_id"], "path": str(path)}


def _get_tick_history(coaching_root: Path, n: int) -> dict[str, Any]:
    try:
        from self_coaching.loop_store import read_jsonl
    except ImportError:
        from loop_store import read_jsonl

    log_path = coaching_root / ".self-coaching" / "coach" / "ticks" / "tick_log.jsonl"
    rows = read_jsonl(log_path) if log_path.is_file() else []
    recent = rows[-n:] if n > 0 else rows
    return {"total_ticks": len(rows), "recent": recent}


__all__ = ["TOOL_DEFINITIONS", "execute_tool"]
