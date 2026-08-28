import mimetypes
import zipfile
import io
import shutil
import uuid
from pathlib import Path
from typing import Optional, List
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, Form, File, UploadFile, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, func, desc
from app.config import settings
from app.database import get_db
from app.models.chart import Chart
from app.models.user import User
from app.services.auth import get_current_user, get_current_user_optional
from app.services.chart_scanner import (
    chart_id_for_folder,
    parse_maidata,
    compute_maidata_hash,
)
from app.services.file_service import (
    get_chart_folder_path,
    find_first_existing_file,
    create_hashed_file_response,
)
from app.services.image_service import get_thumbnail_bytes

router = APIRouter(prefix="/maichart", tags=["MaiChart"])

# In-memory cache to map generated UUIDs back to original DB string IDs
_uuid_cache = {}

async def get_real_chart_id(chart_uuid: str, db: AsyncSession) -> str:
    """Safely resolves a client UUID back to the original database string ID."""
    if len(chart_uuid) != 36:
        return chart_uuid  # Not a UUID, return as-is

    if chart_uuid in _uuid_cache:
        return _uuid_cache[chart_uuid]

    # Cache miss: load mapping from DB (only happens on server restart if a file is requested before /list)
    res = await db.execute(select(Chart.id))
    for real_id in res.scalars().all():
        hashed = str(uuid.uuid5(uuid.NAMESPACE_OID, str(real_id)))
        _uuid_cache[hashed] = real_id

    return _uuid_cache.get(chart_uuid, chart_uuid)


@router.get("/list")
async def get_chart_list(
        sort: Optional[str] = Query(None),
        search: Optional[str] = Query(None),
        page: int = Query(0, ge=0),
        pageSize: int = Query(100, ge=1, le=1000),
        isRanking: Optional[bool] = Query(False),
        db: AsyncSession = Depends(get_db)
):
    stmt = select(Chart)

    if search:
        search_clean = search.strip()
        if search_clean.startswith("tag:"):
            tag_query = search_clean[4:].strip()
            stmt = stmt.where(
                or_(
                    func.json_extract(Chart.tags_json, '$').like(f"%{tag_query}%"),
                    func.json_extract(Chart.public_tags_json, '$').like(f"%{tag_query}%")
                )
            )
        else:
            pattern = f"%{search_clean}%"
            stmt = stmt.where(
                or_(
                    Chart.title.ilike(pattern),
                    Chart.artist.ilike(pattern),
                    Chart.designer.ilike(pattern),
                    Chart.uploader.ilike(pattern),
                )
            )

    if sort == "latest" or sort == "date":
        stmt = stmt.order_by(desc(Chart.timestamp))
    elif sort == "title":
        stmt = stmt.order_by(Chart.title)
    elif sort == "artist":
        stmt = stmt.order_by(Chart.artist)
    else:
        stmt = stmt.order_by(desc(Chart.timestamp))

    if page > 0 or pageSize != 100:
        stmt = stmt.offset(page * pageSize).limit(pageSize)

    result = await db.execute(stmt)
    charts = result.scalars().all()

    response_list = []
    for c in charts:
        safe_uuid = str(uuid.uuid5(uuid.NAMESPACE_OID, str(c.id)))
        _uuid_cache[safe_uuid] = c.id  # Warm up the cache

        response_list.append({
            "id": safe_uuid,
            "title": c.title,
            "artist": c.artist,
            "designer": c.designer,
            "uploader": c.uploader,
            "description": c.description,
            "levels": c.levels,
            "tags": c.tags,
            "publicTags": c.public_tags,
            "timestamp": c.timestamp.isoformat() if c.timestamp else "",
            "hash": c.hash,
        })

    return response_list


@router.get("/{chartId}/summary")
async def get_chart_summary(
        chartId: str,
        db: AsyncSession = Depends(get_db)
):
    real_id = await get_real_chart_id(chartId, db)
    stmt = select(Chart).where(Chart.id == real_id)
    res = await db.execute(stmt)
    chart = res.scalar_one_or_none()
    if not chart:
        raise HTTPException(status_code=404, detail="Chart not found")

    return {
        "id": chartId,  # Keep as UUID for client
        "title": chart.title,
        "artist": chart.artist,
        "uploader": chart.uploader,
        "designer": chart.designer,
        "description": chart.description,
        "levels": chart.levels,
        "tags": chart.tags,
        "publicTags": chart.public_tags,
        "hash": chart.hash,
        "timestamp": chart.timestamp.isoformat() if chart.timestamp else "",
    }


@router.get("/{chartId}/chart")
async def get_chart_file(chartId: str, db: AsyncSession = Depends(get_db)):
    real_id = await get_real_chart_id(chartId, db)
    folder_path = get_chart_folder_path(real_id)
    maidata_path = folder_path / "maidata.txt"
    if not maidata_path.exists():
        raise HTTPException(status_code=404, detail="maidata.txt not found")

    data = maidata_path.read_bytes()
    return create_hashed_file_response(data, "text/plain; charset=utf-8", "maidata.txt")


@router.get("/{chartId}/track")
async def get_chart_track(chartId: str, db: AsyncSession = Depends(get_db)):
    real_id = await get_real_chart_id(chartId, db)
    folder_path = get_chart_folder_path(real_id)
    track_path = find_first_existing_file(folder_path, ["track.mp3", "track.ogg", "track.wav"])
    if not track_path:
        raise HTTPException(status_code=404, detail="Track audio not found")

    data = track_path.read_bytes()
    mime = "audio/mp3" if track_path.suffix.lower() == ".mp3" else (mimetypes.guess_type(str(track_path))[0] or "audio/mpeg")
    return create_hashed_file_response(data, mime, track_path.name)


@router.get("/{chartId}/image")
async def get_chart_image(
        chartId: str,
        fullImage: bool = Query(False, alias="fullImage"),
        db: AsyncSession = Depends(get_db)
):
    real_id = await get_real_chart_id(chartId, db)
    folder_path = get_chart_folder_path(real_id)
    image_path = find_first_existing_file(folder_path, ["bg.jpg", "bg.png", "bg.jpeg", "cover.jpg", "cover.png"])
    if not image_path:
        raise HTTPException(status_code=404, detail="Cover image not found")

    if fullImage:
        data = image_path.read_bytes()
        mime, _ = mimetypes.guess_type(str(image_path))
        return create_hashed_file_response(data, mime or "image/jpeg", image_path.name)
    else:
        thumb_bytes, mime = get_thumbnail_bytes(image_path)
        return create_hashed_file_response(thumb_bytes, mime, image_path.name)


@router.get("/{chartId}/video")
async def get_chart_video(chartId: str, db: AsyncSession = Depends(get_db)):
    real_id = await get_real_chart_id(chartId, db)
    folder_path = get_chart_folder_path(real_id)
    video_path = find_first_existing_file(folder_path, ["bg.mp4", "pv.mp4", "video.mp4"])
    if not video_path:
        raise HTTPException(status_code=404, detail="Video not found")

    data = video_path.read_bytes()
    return create_hashed_file_response(data, "video/mp4", video_path.name)


@router.get("/hash-status")
async def check_hash_status(
        hash: str = Query(...),
        db: AsyncSession = Depends(get_db)
):
    stmt = select(Chart).where(Chart.hash == hash)
    res = await db.execute(stmt)
    chart = res.scalar_one_or_none()

    chart_id = str(uuid.uuid5(uuid.NAMESPACE_OID, str(chart.id))) if chart else None
    if chart and chart_id:
        _uuid_cache[chart_id] = chart.id

    return {"exists": chart is not None, "chartId": chart_id}


@router.post("/upload")
async def upload_chart(
        formfiles: List[UploadFile] = File(None),
        file: Optional[UploadFile] = File(None),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    files = formfiles or ([file] if file else [])
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")

    if len(files) == 1 and files[0].filename and files[0].filename.endswith(".zip"):
        zip_bytes = await files[0].read()
        try:
            with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
                maidata_info = next((i for i in z.infolist() if i.filename.endswith("maidata.txt")), None)
                if not maidata_info:
                    raise HTTPException(status_code=400, detail="maidata.txt not found in ZIP archive")

                maidata_content = z.read(maidata_info)
                parsed = parse_maidata(maidata_content)
                chart_title = parsed["title"] or Path(files[0].filename).stem

                safe_title = "".join(c for c in chart_title if c.isalnum() or c in " -_").strip() or "chart"
                folder_name = f"{safe_title}_{int(datetime.now().timestamp())}"
                target_dir = settings.CHARTS_DIR / folder_name
                target_dir.mkdir(parents=True, exist_ok=True)

                for item in z.infolist():
                    if item.is_dir():
                        continue
                    filename = Path(item.filename).name
                    if filename:
                        (target_dir / filename).write_bytes(z.read(item))

                chart_id = chart_id_for_folder(folder_name)
                chart_hash = compute_maidata_hash(maidata_content)

                chart = Chart(
                    id=chart_id,
                    folder_path=folder_name,
                    title=parsed["title"],
                    artist=parsed["artist"],
                    designer=parsed["designer"],
                    uploader=current_user.username,
                    description="",
                    hash=chart_hash,
                    levels_json=parsed["levels"],
                    tags_json=[],
                    public_tags_json=[],
                    timestamp=datetime.now(timezone.utc),
                )
                db.add(chart)
                await db.commit()

                safe_uuid = str(uuid.uuid5(uuid.NAMESPACE_OID, str(chart_id)))
                _uuid_cache[safe_uuid] = chart_id

                return {"code": 114514, "chartId": safe_uuid, "message": "Uploaded successfully"}
        except zipfile.BadZipFile:
            raise HTTPException(status_code=400, detail="Invalid zip file")

    maidata_file = next((f for f in files if f.filename and f.filename.endswith("maidata.txt")), None)
    if not maidata_file:
        raise HTTPException(status_code=400, detail="maidata.txt must be included in upload")

    maidata_content = await maidata_file.read()
    parsed = parse_maidata(maidata_content)
    chart_title = parsed["title"] or "chart"
    safe_title = "".join(c for c in chart_title if c.isalnum() or c in " -_").strip() or "chart"
    folder_name = f"{safe_title}_{int(datetime.now().timestamp())}"
    target_dir = settings.CHARTS_DIR / folder_name
    target_dir.mkdir(parents=True, exist_ok=True)

    (target_dir / "maidata.txt").write_bytes(maidata_content)

    for f in files:
        if f.filename and not f.filename.endswith("maidata.txt"):
            content = await f.read()
            (target_dir / Path(f.filename).name).write_bytes(content)

    chart_id = chart_id_for_folder(folder_name)
    chart_hash = compute_maidata_hash(maidata_content)

    chart = Chart(
        id=chart_id,
        folder_path=folder_name,
        title=parsed["title"],
        artist=parsed["artist"],
        designer=parsed["designer"],
        uploader=current_user.username,
        description="",
        hash=chart_hash,
        levels_json=parsed["levels"],
        tags_json=[],
        public_tags_json=[],
        timestamp=datetime.now(timezone.utc),
    )
    db.add(chart)
    await db.commit()

    safe_uuid = str(uuid.uuid5(uuid.NAMESPACE_OID, str(chart_id)))
    _uuid_cache[safe_uuid] = chart_id

    return {"code": 114514, "chartId": safe_uuid, "message": "Uploaded successfully"}


@router.post("/delete")
async def delete_chart(
        chartId: str = Query(...),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    real_id = await get_real_chart_id(chartId, db)
    stmt = select(Chart).where(Chart.id == real_id)
    res = await db.execute(stmt)
    chart = res.scalar_one_or_none()
    if not chart:
        raise HTTPException(status_code=404, detail="Chart not found")

    if chart.uploader != current_user.username:
        raise HTTPException(status_code=403, detail="Permission denied")

    try:
        folder_path = settings.CHARTS_DIR / chart.folder_path
        if folder_path.exists():
            shutil.rmtree(folder_path)
    except Exception as e:
        print(f"Error removing folder: {e}")

    await db.delete(chart)
    await db.commit()

    if chartId in _uuid_cache:
        del _uuid_cache[chartId]

    return {"code": 114514, "message": "Deleted successfully"}


@router.get("/{chartId}/tags")
async def get_chart_tags(chartId: str, db: AsyncSession = Depends(get_db)):
    real_id = await get_real_chart_id(chartId, db)
    stmt = select(Chart).where(Chart.id == real_id)
    res = await db.execute(stmt)
    chart = res.scalar_one_or_none()
    return chart.tags if chart else []


@router.post("/{chartId}/tags")
async def update_chart_tags(
        chartId: str,
        tags: List[str] = Form(...),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    real_id = await get_real_chart_id(chartId, db)
    stmt = select(Chart).where(Chart.id == real_id)
    res = await db.execute(stmt)
    chart = res.scalar_one_or_none()
    if not chart:
        raise HTTPException(status_code=404, detail="Chart not found")
    if chart.uploader != current_user.username:
        raise HTTPException(status_code=403, detail="Permission denied")

    chart.tags_json = tags
    await db.commit()
    return {"code": 114514, "message": "Tags updated"}


@router.get("/{chartId}/publictags")
async def get_chart_public_tags(chartId: str, db: AsyncSession = Depends(get_db)):
    real_id = await get_real_chart_id(chartId, db)
    stmt = select(Chart).where(Chart.id == real_id)
    res = await db.execute(stmt)
    chart = res.scalar_one_or_none()
    return chart.public_tags if chart else []


@router.post("/{chartId}/publictags")
async def update_chart_public_tags(
        chartId: str,
        tags: List[str] = Form(...),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    real_id = await get_real_chart_id(chartId, db)
    stmt = select(Chart).where(Chart.id == real_id)
    res = await db.execute(stmt)
    chart = res.scalar_one_or_none()
    if not chart:
        raise HTTPException(status_code=404, detail="Chart not found")

    chart.public_tags_json = tags
    await db.commit()
    return {"code": 114514, "message": "Public tags updated"}