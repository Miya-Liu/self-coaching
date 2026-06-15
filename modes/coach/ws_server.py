# SPDX-License-Identifier: MIT
"""WebSocket ingress for coach clock — same JSON envelope as HTTP POST /coach/post."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

LOG = logging.getLogger("coach.ws")


async def _ws_handler(websocket: Any, state: Any) -> None:
    state.register_ws(websocket)
    try:
        async for message in websocket:
            try:
                body = json.loads(message)
                if not isinstance(body, dict):
                    await websocket.send(json.dumps({"error": "message must be a JSON object"}))
                    continue
                result = state.handle_post(body)
                await websocket.send(json.dumps(result, ensure_ascii=False))
                await state.broadcast({"type": "coach_tick_complete", "result": result})
            except Exception as exc:
                LOG.exception("ws message failed")
                await websocket.send(json.dumps({"error": str(exc)}))
    finally:
        state.unregister_ws(websocket)


def run_ws_loop(state: Any, host: str, port: int) -> None:
    import websockets

    async def _main() -> None:
        async with websockets.serve(
            lambda ws: _ws_handler(ws, state),
            host,
            port,
            ping_interval=30,
            ping_timeout=30,
        ):
            await asyncio.Future()

    asyncio.run(_main())
