# SPDX-License-Identifier: MIT
"""Free-time detector F for T-path idle windows (demo step budget)."""

from __future__ import annotations

import os


DEFAULT_IDLE_AFTER = 0


def idle_after_threshold() -> int:
    raw = os.environ.get("LOOP_IDLE_AFTER", str(DEFAULT_IDLE_AFTER))
    return int(raw)


class FreeTimeSimulator:
    """Returns idle between task arrivals once the step budget is met."""

    def __init__(self, idle_after: int | None = None):
        self.idle_after = idle_after_threshold() if idle_after is None else idle_after
        self._tasks_since_reset = 0

    def on_task_completed(self) -> None:
        self._tasks_since_reset += 1

    def idle(self) -> bool:
        return self._tasks_since_reset >= self.idle_after

    def mark_busy(self) -> None:
        self._tasks_since_reset = 0
