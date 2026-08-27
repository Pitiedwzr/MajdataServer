import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.machine_persist import Machine, MachineAuthRequest, PersistData
from app.models.user import User
from app.services.auth import get_current_user, get_current_user_optional

router = APIRouter(tags=["Machine & Persist"])

# ----------------- Machine API -----------------

@router.post("/machine/register")
async def register_machine(
    name: str = Body(..., embed=True),
    description: str = Body("", embed=True),
    db: AsyncSession = Depends(get_db)
):
    machine = Machine(
        name=name,
        description=description,
        registered_at=datetime.now(timezone.utc),
        is_authorized=True,
    )
    db.add(machine)
    await db.commit()
    await db.refresh(machine)
    return {"code": 114514, "machineId": machine.id, "message": "Machine registered"}


@router.get("/machine/Info")
@router.get("/machine/info")
async def get_machine_info(
    machine_id: str = Query(..., alias="machine-id"),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Machine).where(Machine.id == machine_id)
    res = await db.execute(stmt)
    machine = res.scalar_one_or_none()
    if not machine:
        raise HTTPException(status_code=404, detail="Machine not found")
    return {
        "id": machine.id,
        "name": machine.name,
        "description": machine.description,
        "registeredAt": machine.registered_at.isoformat() if machine.registered_at else "",
        "isAuthorized": machine.is_authorized,
    }


@router.get("/machine/auth/info")
async def get_machine_auth_info(
    auth_id: str = Query(..., alias="auth-id"),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(MachineAuthRequest).where(MachineAuthRequest.auth_id == auth_id)
    res = await db.execute(stmt)
    req = res.scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=404, detail="Auth request not found")
    return {
        "authId": req.auth_id,
        "machineId": req.machine_id,
        "status": req.status,
        "userId": req.user_id,
    }


@router.post("/machine/auth/permit")
async def permit_machine_auth(
    auth_id: str = Query(..., alias="auth-id"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(MachineAuthRequest).where(MachineAuthRequest.auth_id == auth_id)
    res = await db.execute(stmt)
    req = res.scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=404, detail="Auth request not found")
    
    req.status = "permitted"
    req.user_id = current_user.id
    await db.commit()
    return {"code": 114514, "message": "Auth permitted"}


# ----------------- Persist API -----------------

@router.get("/persist/app/{appId}/{category}")
async def get_persist_data(
    appId: str,
    category: str,
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db)
):
    user_id = current_user.id if current_user else None
    stmt = select(PersistData).where(
        PersistData.app_id == appId,
        PersistData.category == category,
        PersistData.user_id == user_id
    )
    res = await db.execute(stmt)
    data = res.scalar_one_or_none()
    return data.data_json if data else {}


@router.post("/persist/app/{appId}/settings")
@router.post("/persist/app/{appId}/{category}")
async def save_persist_data(
    appId: str,
    category: str = "settings",
    payload: Dict[str, Any] = Body(...),
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db)
):
    user_id = current_user.id if current_user else None
    stmt = select(PersistData).where(
        PersistData.app_id == appId,
        PersistData.category == category,
        PersistData.user_id == user_id
    )
    res = await db.execute(stmt)
    existing = res.scalar_one_or_none()

    if existing:
        existing.data_json = payload
    else:
        new_data = PersistData(
            app_id=appId,
            category=category,
            user_id=user_id,
            data_json=payload
        )
        db.add(new_data)

    await db.commit()
    return {"code": 114514, "message": "Settings persisted successfully"}
