import uuid

import httpx
import pytest

from app.main import app


async def register_and_login(client: httpx.AsyncClient, suffix: str) -> None:
    username = f"multiplayer_{suffix}"
    response = await client.post(
        "/api/account/register",
        data={"username": username, "password": "password123", "email": f"{username}@example.com"},
    )
    assert response.status_code == 200
    response = await client.post("/api/account/login", data={"username": username, "password": "password123"})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_room_join_and_ticket_flow():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as first_client:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as second_client:
            await register_and_login(first_client, uuid.uuid4().hex[:8])
            await register_and_login(second_client, uuid.uuid4().hex[:8])

            room_response = await first_client.post("/api/multiplayer/rooms", json={"name": "Test room"})
            assert room_response.status_code == 200
            room = room_response.json()
            assert room["songHash"] is None
            assert len(room["members"]) == 1

            join_response = await second_client.post("/api/multiplayer/rooms/join", json={"code": room["code"]})
            assert join_response.status_code == 200
            assert len(join_response.json()["members"]) == 2

            ticket_response = await second_client.post("/api/multiplayer/rooms/ticket", json={"room_id": room["roomId"]})
            assert ticket_response.status_code == 200
            assert ticket_response.json()["expiresIn"] > 0
