"""WebSocket connection manager and event helpers."""

from __future__ import annotations

import json
from typing import Any, Dict, Set

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        self.rooms: Dict[str, Set[WebSocket]] = {}
        self.user_sockets: Dict[int, Set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, rooms: list[str], user_id: int | None = None) -> None:
        await websocket.accept()
        for room in rooms:
            self.rooms.setdefault(room, set()).add(websocket)
        if user_id is not None:
            self.user_sockets.setdefault(user_id, set()).add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        for room, room_set in list(self.rooms.items()):
            room_set.discard(websocket)
            if not room_set:
                del self.rooms[room]
        for uid, sock_set in list(self.user_sockets.items()):
            sock_set.discard(websocket)
            if not sock_set:
                del self.user_sockets[uid]

    async def broadcast(self, room: str, event: str, data: dict[str, Any]) -> None:
        payload = json.dumps({"event": event, "data": data})
        dead: list[WebSocket] = []
        for ws in list(self.rooms.get(room, set())):
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    async def send_user(self, user_id: int, event: str, data: dict[str, Any]) -> None:
        payload = json.dumps({"event": event, "data": data})
        for ws in list(self.user_sockets.get(user_id, set())):
            try:
                await ws.send_text(payload)
            except Exception:
                self.disconnect(ws)


manager = ConnectionManager()


def trip_room(trip_id: int) -> str:
    return f"trip:{trip_id}"


def ops_room() -> str:
    return "ops"


def driver_room(trip_id: int) -> str:
    return f"driver:{trip_id}"
