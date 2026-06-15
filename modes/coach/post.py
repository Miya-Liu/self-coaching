# SPDX-License-Identifier: MIT
"""Inbound coach post envelope — WebSocket or HTTP POST."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

ClockAction = Literal["hold", "learn", "play", "tune", "full_tick"]


@dataclass(frozen=True)
class CoachPost:
    agent_id: str
    event: str
    payload: dict[str, Any] = field(default_factory=dict)
    post_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    received_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "post_id": self.post_id,
            "agent_id": self.agent_id,
            "event": self.event,
            "payload": self.payload,
            "received_at": self.received_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CoachPost:
        agent_id = data.get("agent_id")
        if not agent_id or not isinstance(agent_id, str):
            raise ValueError("post requires non-empty string agent_id")
        event = data.get("event")
        if not event or not isinstance(event, str):
            raise ValueError("post requires non-empty string event")
        payload = data.get("payload") or {}
        if not isinstance(payload, dict):
            raise ValueError("post payload must be a mapping")
        return cls(
            agent_id=agent_id,
            event=event,
            payload=payload,
            post_id=str(data.get("post_id") or uuid.uuid4()),
            received_at=str(data.get("received_at") or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")),
        )


def persist_post(coaching_root: Path, post: CoachPost) -> Path:
    inbox = coaching_root / ".self-coaching" / "coach" / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    path = inbox / f"{post.post_id}.json"
    path.write_text(json.dumps(post.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return path
