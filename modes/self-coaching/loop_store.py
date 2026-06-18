# SPDX-License-Identifier: MIT
"""Persistent loop artifacts: support.jsonl, tuning_buffer.jsonl, trajectories."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


@dataclass(frozen=True)
class SupportEntry:
    task_id: str
    trajectory_id: str
    trajectory_ref: str
    score: float
    event_text: str


class LoopStore:
    """Read/write loop store artifacts under {coaching_root}/.self-coaching/loop/."""

    def __init__(self, coaching_root: str | Path):
        self.coaching_root = Path(coaching_root).resolve()
        self.loop_dir = self.coaching_root / ".self-coaching" / "loop"
        self.support_path = self.loop_dir / "support.jsonl"
        self.buffer_path = self.loop_dir / "tuning_buffer.jsonl"
        self.trajectories_dir = self.loop_dir / "trajectories"

    def save_trajectory(
        self,
        task_id: str,
        xi: dict[str, Any],
        *,
        rubric_result: dict[str, Any] | None = None,
    ) -> tuple[str, str]:
        payload = hashlib.sha1(
            json.dumps({"task_id": task_id, "xi": xi}, sort_keys=True).encode("utf-8")
        ).hexdigest()[:10]
        trajectory_id = f"traj-{payload}"
        rel_ref = f".self-coaching/loop/trajectories/{trajectory_id}.json"
        record = {
            "trajectory_id": trajectory_id,
            "task_id": task_id,
            "messages": xi.get("messages") or [],
            "tool_trace_summary": xi.get("tool_trace_summary") or [],
            "final_answer": xi.get("final_answer"),
            "capability": xi.get("capability") or ["tool_use"],
        }
        if xi.get("_source"):
            record["_source"] = xi["_source"]
        if rubric_result is not None:
            record["rubric_result"] = rubric_result
        self.trajectories_dir.mkdir(parents=True, exist_ok=True)
        path = self.trajectories_dir / f"{trajectory_id}.json"
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return trajectory_id, rel_ref

    def append_support(
        self,
        *,
        task_id: str,
        generation: int,
        version_id: str,
        trajectory_id: str,
        trajectory_ref: str,
        score: float,
        event_text: str,
    ) -> None:
        append_jsonl(
            self.support_path,
            {
                "task_id": task_id,
                "generation": generation,
                "version_id": version_id,
                "trajectory_id": trajectory_id,
                "score": score,
                "event_text": event_text,
                "trajectory_ref": trajectory_ref,
            },
        )

    def append_buffer(
        self,
        *,
        task_id: str,
        generation: int,
        version_id: str,
        score: float,
        trajectory_ref: str,
    ) -> None:
        append_jsonl(
            self.buffer_path,
            {
                "task_id": task_id,
                "generation": generation,
                "version_id": version_id,
                "score": score,
                "used_for_train": False,
                "trajectory_ref": trajectory_ref,
            },
        )

    def _rewrite_buffer(self, rows: list[dict[str, Any]]) -> None:
        self.buffer_path.parent.mkdir(parents=True, exist_ok=True)
        content = "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows
        )
        self.buffer_path.write_text(content, encoding="utf-8")

    def active_buffer_rows(self) -> list[dict[str, Any]]:
        return [row for row in read_jsonl(self.buffer_path) if not row.get("used_for_train")]

    def mark_buffer_consumed(self, *, task_ids: set[str] | None = None) -> int:
        rows = read_jsonl(self.buffer_path)
        consumed = 0
        for row in rows:
            if row.get("used_for_train"):
                continue
            if task_ids is not None and row.get("task_id") not in task_ids:
                continue
            row["used_for_train"] = True
            consumed += 1
        self._rewrite_buffer(rows)
        return consumed

    def flush_buffer_stale(self, generation: int) -> int:
        rows = read_jsonl(self.buffer_path)
        kept = [row for row in rows if int(row.get("generation", 0)) > generation]
        removed = len(rows) - len(kept)
        if removed:
            self._rewrite_buffer(kept)
        return removed

    def export_train_dataset(self, rows: list[dict[str, Any]]) -> Path:
        curated = self.coaching_root / ".self-coaching" / "curated"
        curated.mkdir(parents=True, exist_ok=True)
        train_path = curated / "train.jsonl"
        records: list[dict[str, Any]] = []
        for row in rows:
            ref = str(row.get("trajectory_ref") or "")
            traj_path = self.coaching_root / ref
            if not traj_path.is_file():
                continue
            traj = json.loads(traj_path.read_text(encoding="utf-8"))
            records.append(
                {
                    "id": row.get("task_id") or traj.get("trajectory_id") or traj.get("id"),
                    "messages": traj.get("messages") or [],
                    "tool_trace_summary": traj.get("tool_trace_summary") or [],
                    "labels": {"privacy_checked": True, "use_for": ["train"]},
                    "source": "loop_buffer",
                }
            )
        train_path.write_text(
            "".join(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in records),
            encoding="utf-8",
        )
        return train_path

    def append_buffer_from_trajectory(
        self,
        traj: dict[str, Any],
        *,
        generation: int,
        version_id: str,
    ) -> str:
        task_id = str(traj.get("case_id") or traj.get("id") or "self-play")
        score = float((traj.get("critique") or {}).get("score", 0.9))
        _trajectory_id, trajectory_ref = self.save_trajectory(task_id, traj)
        self.append_buffer(
            task_id=task_id,
            generation=generation,
            version_id=version_id,
            score=score,
            trajectory_ref=trajectory_ref,
        )
        return trajectory_ref
