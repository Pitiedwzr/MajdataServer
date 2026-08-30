import uuid
import pytest
import pytest_asyncio
import httpx
from pathlib import Path
from sqlalchemy import select
from app.main import app
from app.database import init_db, AsyncSessionLocal
from app.models.chart import Chart
from app.models.interaction import ChartLike
from app.services.chart_scanner import (
    parse_maidata,
    compute_maidata_hash,
    compute_sha256_hash,
    chart_id_for_folder,
    folder_for_chart_id,
    scan_and_sync_charts
)

@pytest_asyncio.fixture(autouse=True)
async def setup_test_db():
    await init_db()

@pytest.mark.asyncio
async def test_maidata_parser_and_hashes():
    sample_maidata = (
        b"&title=\xe8\x8a\xb1\xe3\x81\xae\xe5\xa1\x94\n"
        b"&artist=\xe3\x81\x95\xe3\x83\xa6\xe3\x82\x8a\n"
        b"&des=FTOWER\n"
        b"&lv_5=13+\n"
    )
    parsed = parse_maidata(sample_maidata)
    assert parsed["title"] == "花の塔"
    assert parsed["artist"] == "さユり"
    assert parsed["designer"] == "FTOWER"
    assert parsed["levels"][4] == "13+"
    assert parsed["levels"][0] is None

    # Test folder base64 encoding
    folder = "test/song_01"
    encoded_id = chart_id_for_folder(folder)
    assert "=" not in encoded_id
    decoded_folder = folder_for_chart_id(encoded_id)
    assert decoded_folder == folder

    # Test hash calculation
    m_hash = compute_maidata_hash(sample_maidata)
    assert isinstance(m_hash, str) and len(m_hash) > 0
    s_hash = compute_sha256_hash(sample_maidata)
    assert isinstance(s_hash, str) and len(s_hash) > 0


@pytest.mark.asyncio
async def test_full_api_flow():
    uname = f"user_{uuid.uuid4().hex[:8]}"
    uemail = f"{uname}@example.com"
    folder_name = f"test_chart_{uuid.uuid4().hex[:8]}"
    dummy_chart_id = chart_id_for_folder(folder_name)
    dummy_hash = f"hash_{uuid.uuid4().hex[:8]}"

    # Pre-populate a dummy chart in DB
    async with AsyncSessionLocal() as session:
        chart = Chart(
            id=dummy_chart_id,
            folder_path=folder_name,
            title="Test Song",
            artist="Test Artist",
            designer="Test Designer",
            uploader="System",
            description="Test Description",
            hash=dummy_hash,
            levels_json=[None, None, None, None, "13+", None, None],
            tags_json=["pop", "anime"],
            public_tags_json=["featured"],
        )
        session.add(chart)
        await session.commit()

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # 1. Ping
        res = await client.get("/api/utils/Ping")
        assert res.status_code == 200
        assert res.json()["status"] == "ok"

        # 2. Register
        reg_res = await client.post(
            "/api/account/Register",
            data={
                "username": uname,
                "password": "password123",
                "email": uemail,
            }
        )
        assert reg_res.status_code == 200
        assert reg_res.json()["code"] == 114514

        # 3. Login
        login_res = await client.post(
            "/api/account/Login",
            data={
                "username": uname,
                "password": "password123",
                "rememberMe": "true",
            }
        )
        assert login_res.status_code == 200
        assert login_res.json()["code"] == 114514
        client.cookies.update(login_res.cookies)

        # 4. User Info & Intro
        info_res = await client.get("/api/account/info")
        assert info_res.status_code == 200
        assert info_res.json()["username"] == uname

        intro_update = await client.post("/api/account/intro", data={"content": "Hello World"})
        assert intro_update.status_code == 200
        intro_get = await client.get(f"/api/account/intro?username={uname}")
        assert intro_get.text.strip('"') == "Hello World"

        # 5. Chart List & Summary
        list_res = await client.get("/api/maichart/list")
        assert list_res.status_code == 200
        assert isinstance(list_res.json(), list)

        summary_res = await client.get(f"/api/maichart/{dummy_chart_id}/summary")
        assert summary_res.status_code == 200
        assert summary_res.json()["title"] == "Test Song"

        # 6. Interaction (Like & Comment) through the public UUID ID.
        chart_uuid = str(uuid.uuid5(uuid.NAMESPACE_OID, dummy_chart_id))
        like_res = await client.post(f"/api/maichart/{chart_uuid}/interact", data={"type": "like"})
        assert like_res.status_code == 200

        comment_res = await client.post(
            f"/api/maichart/{chart_uuid}/interact",
            data={"type": "comment", "content": "Awesome chart!"}
        )
        assert comment_res.status_code == 200

        interact_get = await client.get(f"/api/maichart/{chart_uuid}/interact")
        assert interact_get.status_code == 200
        data = interact_get.json()
        assert uname in data["likes"]
        assert len(data["comments"]) >= 1

        async with AsyncSessionLocal() as session:
            stored_like = await session.scalar(
                select(ChartLike).where(ChartLike.chart_id == dummy_chart_id)
            )
            assert stored_like is not None

        # 7. Score Submit & Ranking
        score_res = await client.post(
            f"/api/maichart/{dummy_chart_id}/score",
            json={
                "ChartLevel": 4,
                "Hash": dummy_hash,
                "DXScore": 2500,
                "ComboState": 3,
                "Acc": {"DX": 100.5, "Classic": 100.0}
            }
        )
        assert score_res.status_code == 200
        assert score_res.json()["code"] == 114514

        scores_res = await client.get(f"/api/maichart/{dummy_chart_id}/score")
        assert scores_res.status_code == 200
        assert len(scores_res.json()["scores"][4]) >= 1

        # 8. Collection API
        col_res = await client.post(
            "/api/collection/create",
            json={"name": "My Favorites", "description": "Test Collection", "visibility": 1}
        )
        assert col_res.status_code == 200
        col_id = col_res.json()["id"]

        modify_col = await client.post(
            f"/api/collection/{col_id}/modify",
            json={"items": [dummy_hash]}
        )
        assert modify_col.status_code == 200

        songlist_res = await client.get(f"/api/collection/{col_id}/songlist")
        assert songlist_res.status_code == 200
        assert len(songlist_res.json()["items"]) == 1

        # 9. Machine & Persist API
        reg_machine = await client.post(
            "/api/machine/register",
            json={"name": "Arcade Cabinet 01", "description": "Location A"}
        )
        assert reg_machine.status_code == 200
        machine_id = reg_machine.json()["machineId"]

        machine_info = await client.get(f"/api/machine/Info?machine-id={machine_id}")
        assert machine_info.status_code == 200
        assert machine_info.json()["name"] == "Arcade Cabinet 01"

        persist_save = await client.post(
            "/api/persist/app/1096/settings",
            json={"bgmVolume": 80, "noteSpeed": 7.5}
        )
        assert persist_save.status_code == 200
        persist_get = await client.get("/api/persist/app/1096/settings")
        assert persist_get.status_code == 200
        assert persist_get.json()["noteSpeed"] == 7.5

        # 10. Stats API
        stats_res = await client.get("/api/stats/score-sums")
        assert stats_res.status_code == 200
        assert len(stats_res.json()) >= 1

        # 11. Logout
        logout_res = await client.post("/api/account/Logout")
        assert logout_res.status_code == 200


@pytest.mark.asyncio
async def test_guest_persist_data_is_isolated_per_client():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as first_client:
        save = await first_client.post("/api/persist/app/test/settings", json={"noteSpeed": 8})
        assert save.status_code == 200
        assert "persist_guest_id" in first_client.cookies
        assert (await first_client.get("/api/persist/app/test/settings")).json() == {"noteSpeed": 8}

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as second_client:
        response = await second_client.get("/api/persist/app/test/settings")
        assert response.status_code == 200
        assert response.json() == {}
