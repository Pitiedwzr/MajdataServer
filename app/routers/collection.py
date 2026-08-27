from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, desc, or_
from sqlalchemy.orm import selectinload
from app.database import get_db
from app.models.collection import Collection, CollectionItem
from app.models.chart import Chart
from app.models.user import User
from app.services.auth import get_current_user, get_current_user_optional
from app.schemas.collection import CollectionCreateRequest, CollectionModifyRequest

router = APIRouter(prefix="/collection", tags=["Collection"])

@router.get("/list")
async def list_collections(
    page: int = Query(0, ge=0),
    pageSize: int = Query(30, ge=1, le=100),
    createdBy: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db)
):
    stmt = (
        select(Collection)
        .options(selectinload(Collection.items), selectinload(Collection.user))
        .join(User, Collection.user_id == User.id)
    )

    # Filter visibility or creator
    if createdBy:
        stmt = stmt.where(User.username == createdBy)
        if not current_user or current_user.username != createdBy:
            stmt = stmt.where(Collection.visibility == 1)
    else:
        # Public or own
        if current_user:
            stmt = stmt.where(or_(Collection.visibility == 1, Collection.user_id == current_user.id))
        else:
            stmt = stmt.where(Collection.visibility == 1)

    if keyword:
        kw = f"%{keyword.strip()}%"
        stmt = stmt.where(or_(Collection.name.ilike(kw), Collection.description.ilike(kw)))

    stmt = stmt.order_by(desc(Collection.created_at)).offset(page * pageSize).limit(pageSize)
    res = await db.execute(stmt)
    collections = res.scalars().all()

    return [
        {
            "id": c.id,
            "name": c.name,
            "createdBy": c.user.username if c.user else "",
            "description": c.description,
            "count": len(c.items),
            "visibility": c.visibility,
        }
        for c in collections
    ]


@router.post("/create")
async def create_collection(
    req: CollectionCreateRequest = Body(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    collection = Collection(
        user_id=current_user.id,
        name=req.name,
        description=req.description or "",
        visibility=req.visibility,
    )
    db.add(collection)
    await db.commit()
    await db.refresh(collection)
    return {
        "id": collection.id,
        "name": collection.name,
        "createdBy": current_user.username,
        "description": collection.description,
        "visibility": collection.visibility,
        "count": 0,
    }


@router.get("/{idStr}/hashlist")
async def get_collection_hash_list(
    idStr: str,
    db: AsyncSession = Depends(get_db)
):
    stmt = select(CollectionItem.chart_hash).where(CollectionItem.collection_id == idStr).order_by(CollectionItem.order_idx)
    res = await db.execute(stmt)
    hashes = list(res.scalars().all())
    return hashes


@router.get("/{idStr}/songlist")
async def get_collection_song_list(
    idStr: str,
    db: AsyncSession = Depends(get_db)
):
    stmt_col = select(Collection).options(selectinload(Collection.user)).where(Collection.id == idStr)
    res_col = await db.execute(stmt_col)
    collection = res_col.scalar_one_or_none()
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")

    stmt_items = (
        select(CollectionItem, Chart)
        .outerjoin(Chart, CollectionItem.chart_hash == Chart.hash)
        .where(CollectionItem.collection_id == idStr)
        .order_by(CollectionItem.order_idx)
    )
    res_items = await db.execute(stmt_items)
    records = res_items.all()

    songs = []
    for item, chart in records:
        if chart:
            songs.append({
                "id": chart.id,
                "title": chart.title,
                "artist": chart.artist,
                "uploader": chart.uploader,
                "designer": chart.designer,
                "levels": chart.levels,
                "hash": chart.hash,
            })

    return {
        "id": collection.id,
        "name": collection.name,
        "createdBy": collection.user.username if collection.user else "",
        "description": collection.description,
        "visibility": collection.visibility,
        "count": len(songs),
        "items": songs,
    }


@router.post("/{idStr}/destroy")
async def delete_collection(
    idStr: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Collection).where(Collection.id == idStr)
    res = await db.execute(stmt)
    col = res.scalar_one_or_none()
    if not col:
        raise HTTPException(status_code=404, detail="Collection not found")
    if col.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Permission denied")

    await db.delete(col)
    await db.commit()
    return {"code": 114514, "message": "Collection destroyed"}


@router.post("/{idStr}/modify")
async def modify_collection(
    idStr: str,
    req: CollectionModifyRequest = Body(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Collection).where(Collection.id == idStr)
    res = await db.execute(stmt)
    col = res.scalar_one_or_none()
    if not col:
        raise HTTPException(status_code=404, detail="Collection not found")
    if col.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Permission denied")

    if req.name is not None:
        col.name = req.name
    if req.description is not None:
        col.description = req.description
    if req.visibility is not None:
        col.visibility = req.visibility

    if req.items is not None:
        # Replace items
        stmt_del = delete(CollectionItem).where(CollectionItem.collection_id == idStr)
        await db.execute(stmt_del)
        for idx, h in enumerate(req.items):
            db.add(CollectionItem(collection_id=idStr, chart_hash=h, order_idx=idx))

    await db.commit()
    return {"code": 114514, "message": "Collection modified"}


@router.post("/{idStr}/diff")
async def get_collection_diff(
    idStr: str,
    db: AsyncSession = Depends(get_db)
):
    return {"diff": []}
