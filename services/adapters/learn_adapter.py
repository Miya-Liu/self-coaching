# SPDX-License-Identifier: MIT
"""Self-learning adapter: provides learn() backed by the self-learning HTTP service.

Wires into CompositeClient so the orchestrator and loop driver can delegate
learning events to the real (or mock HTTP) self-learning service instead of
the in-process mock.
"""

from __future__ import annotations

from typing import Any

from .self_learning_client import SelfLearningClient, SelfLearningError


class SelfLearningAdapter:
    """Adapter providing the `learn()` interface backed by the self-learning service.

    Used by CompositeClient when ORCHESTRATOR_LEARN_BACKEND=self-learning.
    """

    def __init__(self, client: SelfLearningClient | None = None):
        self._client = client or SelfLearningClient()

    def learn(
        self,
        *,
        event: str,
        source: str = "client",
        capability: str = "tool_use",
        coaching_root: str | None = None,
    ) -> dict[str, Any]:
        """Record a learning event via the HTTP service."""
        return self._client.learn(
            event=event,
            source=source,
            capability=capability,
            coaching_root=coaching_root,
        )

    def evolve(
        self,
        *,
        session_ids: list[str],
        coaching_root: str | None = None,
        capability: str = "tool_use",
        wait: bool = True,
    ) -> dict[str, Any]:
        """Trigger skill evolution from specific sessions."""
        return self._client.evolve(
            session_ids=session_ids,
            coaching_root=coaching_root,
            capability=capability,
            wait=wait,
        )

    def evolve_recent(
        self,
        *,
        coaching_root: str | None = None,
        capability: str = "tool_use",
        limit: int | None = None,
        wait: bool = True,
    ) -> dict[str, Any]:
        """Trigger skill evolution from recent events."""
        return self._client.evolve_recent(
            coaching_root=coaching_root,
            capability=capability,
            limit=limit,
            wait=wait,
        )


__all__ = ["SelfLearningAdapter", "SelfLearningClient", "SelfLearningError"]
