# SPDX-License-Identifier: MIT
"""Opt-in stdout step logs for long-running loop / adapter operations."""

from __future__ import annotations

import os


def step_log_enabled() -> bool:
    return os.environ.get("LOOP_STEP_LOG", "1").strip().lower() not in ("0", "false", "no")


def step_log(tag: str, message: str) -> None:
    if step_log_enabled():
        print(f"  [{tag}] {message}", flush=True)


__all__ = ["step_log", "step_log_enabled"]
