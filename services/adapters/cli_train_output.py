# SPDX-License-Identifier: MIT
"""Parse training stdout for checkpoint and metrics markers."""

from __future__ import annotations

import json
import re
from typing import Any

_MARKER_PREFIX = "TRAINING_COMPLETE"
_RE_CHECKPOINT = re.compile(r"(?:^|\s)checkpoint=(\S+)")
_RE_MODEL_ID = re.compile(r"(?:^|\s)model_id=(\S+)")
_RE_METRICS = re.compile(r"(?:^|\s)metrics=(\{.*\})\s*$")


def parse_training_marker(stdout: str) -> dict[str, Any]:
    """Extract checkpoint/model_id/metrics from a TRAINING_COMPLETE marker line."""
    if not stdout:
        return {}
    for line in reversed(stdout.splitlines()):
        stripped = line.strip()
        if _MARKER_PREFIX not in stripped:
            continue
        idx = stripped.find(_MARKER_PREFIX)
        tail = stripped[idx + len(_MARKER_PREFIX) :].strip()
        parsed: dict[str, Any] = {}
        checkpoint = _RE_CHECKPOINT.search(tail)
        if checkpoint:
            parsed["checkpoint"] = checkpoint.group(1)
        model_id = _RE_MODEL_ID.search(tail)
        if model_id:
            parsed["model_id"] = model_id.group(1)
        metrics = _RE_METRICS.search(tail)
        if metrics:
            try:
                parsed["metrics"] = json.loads(metrics.group(1))
            except json.JSONDecodeError:
                parsed["metrics_raw"] = metrics.group(1)
        return parsed
    return {}


def resolve_candidate(
    marker: dict[str, Any],
    *,
    run_id: str,
    pipeline: str,
) -> str:
    """Choose candidate_model_id from marker fields or synthesize a fallback."""
    for key in ("model_id", "checkpoint"):
        value = marker.get(key)
        if value:
            return str(value)
    return f"cli-train-{pipeline}-{run_id.removeprefix('cli-train-')}"
