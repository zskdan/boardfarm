import asyncio
import json
import logging
from typing import Set

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

_connections: Set[WebSocket] = set()


async def ws_handler(websocket: WebSocket):
    await websocket.accept()
    _connections.add(websocket)
    try:
        while True:
            # Keep alive - wait for client messages (ping/close)
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        _connections.discard(websocket)


async def broadcast(event: dict):
    """Broadcast a JSON event to all connected WebSocket clients."""
    if not _connections:
        return
    msg = json.dumps(event)
    dead = set()
    for ws in _connections:
        try:
            await ws.send_text(msg)
        except Exception:
            dead.add(ws)
    _connections -= dead
