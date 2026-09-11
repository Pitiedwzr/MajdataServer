import asyncio
import secrets
import string
import time
from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from app.models.user import User
from app.services.auth import get_current_user


router = APIRouter(prefix="/multiplayer", tags=["Multiplayer"])

START_DELAY_MS = 8_000
TICKET_TTL_SEC = 60


class CreateRoomRequest(BaseModel):
    name: str = Field(default="Multiplayer room", max_length=80)


class JoinRoomRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6)


class RoomAction(BaseModel):
    room_id: str


@dataclass
class Member:
    user_id: str
    username: str
    difficulty: int = 0
    ready: bool = False

    def serialize(self) -> dict[str, Any]:
        return {
            "userId": self.user_id,
            "username": self.username,
            "difficulty": self.difficulty,
            "ready": self.ready,
        }


@dataclass
class Room:
    id: str
    code: str
    name: str
    members: dict[str, Member] = field(default_factory=dict)
    song_hash: str | None = None
    revision: int = 0
    phase: str = "lobby"
    start_at_ms: int | None = None

    def serialize(self) -> dict[str, Any]:
        return {
            "roomId": self.id,
            "code": self.code,
            "name": self.name,
            "songHash": self.song_hash,
            "revision": self.revision,
            "phase": self.phase,
            "startAtMs": self.start_at_ms,
            "members": [member.serialize() for member in self.members.values()],
        }


class MultiplayerHub:
    def __init__(self) -> None:
        self.rooms: dict[str, Room] = {}
        self.codes: dict[str, str] = {}
        self.tickets: dict[str, tuple[str, float]] = {}
        self.sockets: dict[str, dict[str, WebSocket]] = {}
        self.lock = asyncio.Lock()

    @staticmethod
    def new_code() -> str:
        alphabet = string.ascii_uppercase + string.digits
        return "".join(secrets.choice(alphabet) for _ in range(6))

    async def create_room(self, user: User, name: str) -> Room:
        async with self.lock:
            code = self.new_code()
            while code in self.codes:
                code = self.new_code()
            room = Room(id=secrets.token_urlsafe(12), code=code, name=name)
            room.members[user.id] = Member(user.id, user.username)
            self.rooms[room.id] = room
            self.codes[code] = room.id
            return room

    async def join_room(self, user: User, code: str) -> Room:
        async with self.lock:
            room_id = self.codes.get(code.upper())
            room = self.rooms.get(room_id) if room_id else None
            if room is None:
                raise HTTPException(status_code=404, detail="Room not found")
            room.members.setdefault(user.id, Member(user.id, user.username))
            return room

    async def get_member_room(self, user: User, room_id: str) -> Room:
        async with self.lock:
            room = self.rooms.get(room_id)
            if room is None or user.id not in room.members:
                raise HTTPException(status_code=404, detail="Room not found")
            return room

    async def issue_ticket(self, user: User, room_id: str) -> str:
        await self.get_member_room(user, room_id)
        ticket = secrets.token_urlsafe(32)
        async with self.lock:
            self.tickets[ticket] = (user.id, time.monotonic() + TICKET_TTL_SEC)
        return ticket

    async def consume_ticket(self, ticket: str) -> str | None:
        async with self.lock:
            item = self.tickets.pop(ticket, None)
            if item is None or item[1] < time.monotonic():
                return None
            return item[0]

    async def connect(self, room_id: str, user_id: str, socket: WebSocket) -> None:
        async with self.lock:
            self.sockets.setdefault(room_id, {})[user_id] = socket

    async def disconnect(self, room_id: str, user_id: str, socket: WebSocket) -> None:
        async with self.lock:
            sockets = self.sockets.get(room_id)
            if sockets and sockets.get(user_id) is socket:
                sockets.pop(user_id, None)

    async def broadcast(self, room: Room, event: str = "room_snapshot") -> None:
        payload = {"type": event, "serverTimeMs": int(time.time() * 1000), "room": room.serialize()}
        async with self.lock:
            sockets = list(self.sockets.get(room.id, {}).values())
        for socket in sockets:
            try:
                await socket.send_json(payload)
            except RuntimeError:
                pass


hub = MultiplayerHub()


@router.post("/rooms")
async def create_room(payload: CreateRoomRequest, user: User = Depends(get_current_user)):
    room = await hub.create_room(user, payload.name.strip() or "Multiplayer room")
    return room.serialize()


@router.post("/rooms/join")
async def join_room(payload: JoinRoomRequest, user: User = Depends(get_current_user)):
    room = await hub.join_room(user, payload.code)
    await hub.broadcast(room)
    return room.serialize()


@router.get("/rooms/{room_id}")
async def get_room(room_id: str, user: User = Depends(get_current_user)):
    return (await hub.get_member_room(user, room_id)).serialize()


@router.post("/rooms/ticket")
async def create_ticket(payload: RoomAction, user: User = Depends(get_current_user)):
    return {"ticket": await hub.issue_ticket(user, payload.room_id), "expiresIn": TICKET_TTL_SEC}


@router.websocket("/ws")
async def multiplayer_socket(websocket: WebSocket, ticket: str, room_id: str):
    user_id = await hub.consume_ticket(ticket)
    if user_id is None:
        await websocket.close(code=1008)
        return
    room = hub.rooms.get(room_id)
    if room is None or user_id not in room.members:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    await hub.connect(room_id, user_id, websocket)
    await hub.broadcast(room)
    try:
        while True:
            message = await websocket.receive_json()
            message_type = message.get("type")
            async with hub.lock:
                if message_type == "select_song":
                    if any(member.ready for member in room.members.values()):
                        continue
                    song_hash = message.get("songHash")
                    if not isinstance(song_hash, str) or not song_hash:
                        continue
                    room.song_hash = song_hash
                    room.revision += 1
                    room.phase = "lobby"
                    room.start_at_ms = None
                    for member in room.members.values():
                        member.ready = False
                elif message_type == "set_difficulty":
                    difficulty = message.get("difficulty")
                    if not isinstance(difficulty, int) or difficulty not in range(7):
                        continue
                    room.members[user_id].difficulty = difficulty
                elif message_type == "set_ready":
                    room.members[user_id].ready = bool(message.get("ready"))
                elif message_type == "request_start":
                    if room.song_hash is None or not room.members or not all(member.ready for member in room.members.values()):
                        continue
                    room.phase = "countdown"
                    room.start_at_ms = int(time.time() * 1000) + START_DELAY_MS
                elif message_type == "clock_ping":
                    await websocket.send_json({"type": "clock_pong", "clientTimeMs": message.get("clientTimeMs"), "serverTimeMs": int(time.time() * 1000)})
                    continue
                else:
                    continue
            await hub.broadcast(room, "start_scheduled" if room.phase == "countdown" else "room_snapshot")
    except WebSocketDisconnect:
        pass
    finally:
        await hub.disconnect(room_id, user_id, websocket)
