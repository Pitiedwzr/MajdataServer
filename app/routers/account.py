import os
import uuid
import mimetypes
from datetime import datetime, timedelta, timezone
from typing import Optional, List
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Form, File, UploadFile, Query, Response, Request
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, desc
from sqlalchemy.orm import selectinload
from app.config import settings
from app.database import get_db
from app.models.user import User, UserSession, OTPVerification
from app.models.score import Score
from app.models.chart import Chart
from app.models.collection import Collection, CollectionFavorite
from app.services.auth import (
    hash_password,
    verify_password,
    create_user_session,
    get_current_user,
    get_current_user_optional,
)
from app.schemas.account import (
    UserInfoResponse,
    SessionInfoResponse,
    ApiResponse,
)

router = APIRouter(prefix="/account", tags=["Account"])

# Return code constants matching frontend apiRetCode.ts
CODE_SUCCESS = 114514
CODE_NOT_LOGGED_IN = -1
CODE_INVALID_VALUE = 6
CODE_INVALID_CREDENTIALS = 10
CODE_LOGIN_FAILED_PENDING_VERIFICATION = 11
CODE_LOGIN_FAILED_USER_BANNED = 12
CODE_USERNAME_ALREADY_EXISTS = 4
CODE_EMAIL_ALREADY_EXISTS = 5
CODE_NO_SUCH_ITEM = 13

@router.post("/Register")
@router.post("/register")
async def register_user(
    username: str = Form(...),
    password: str = Form(...),
    email: str = Form(...),
    cf_turnstile_response: Optional[str] = Form(None, alias="cf-turnstile-response"),
    db: AsyncSession = Depends(get_db)
):
    # Check if username or email already exists
    stmt_username = select(User).where(User.username == username)
    result = await db.execute(stmt_username)
    if result.scalar_one_or_none():
        return JSONResponse(status_code=400, content={"code": CODE_USERNAME_ALREADY_EXISTS, "message": "Username already exists"})

    stmt_email = select(User).where(User.email == email)
    result_email = await db.execute(stmt_email)
    if result_email.scalar_one_or_none():
        return JSONResponse(status_code=400, content={"code": CODE_EMAIL_ALREADY_EXISTS, "message": "Email already exists"})

    # Auto activate user or create verification OTP
    is_active = settings.AUTO_ACTIVATE_USERS
    user = User(
        username=username,
        email=email,
        password_hash=hash_password(password),
        is_active=is_active,
        intro="",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    if not is_active:
        otp_code = str(uuid.uuid4())[:8]
        otp = OTPVerification(
            username=username,
            email=email,
            otp=otp_code,
            purpose="register",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24)
        )
        db.add(otp)
        await db.commit()
        # In production, send email here with otp_code

    return {"code": CODE_SUCCESS, "message": "Registered successfully"}


@router.post("/Login")
@router.post("/login")
async def login_user(
    response: Response,
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    rememberMe: Optional[str] = Form("false"),
    db: AsyncSession = Depends(get_db)
):
    is_remember = rememberMe.lower() in ("true", "1", "yes")
    stmt = select(User).where(User.username == username)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user or not verify_password(password, user.password_hash):
        return JSONResponse(status_code=400, content={"code": CODE_INVALID_CREDENTIALS, "message": "Invalid username or password"})

    if user.is_banned:
        return JSONResponse(status_code=400, content={"code": CODE_LOGIN_FAILED_USER_BANNED, "message": "User is banned"})

    if not user.is_active:
        return JSONResponse(status_code=400, content={"code": CODE_LOGIN_FAILED_PENDING_VERIFICATION, "message": "Account pending activation"})

    # Create session
    user_agent = request.headers.get("User-Agent", "")
    client_ip = request.client.host if request.client else ""
    session = await create_user_session(db, user, remember_me=is_remember, user_agent=user_agent, ip_address=client_ip)

    # Set cookies
    max_age = 30 * 86400 if is_remember else None
    response.set_cookie(
        key="session_id",
        value=session.session_id,
        httponly=True,
        samesite="lax",
        max_age=max_age,
        path="/"
    )
    response.set_cookie(
        key="sessionId",
        value=session.session_id,
        httponly=False,
        samesite="lax",
        max_age=max_age,
        path="/"
    )

    return {"code": CODE_SUCCESS, "message": "Login success", "sessionId": session.session_id}


@router.post("/Logout")
@router.post("/logout")
async def logout_user(
    response: Response,
    sessionId: Optional[str] = Query(None),
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db)
):
    if sessionId:
        stmt = delete(UserSession).where(UserSession.session_id == sessionId)
        await db.execute(stmt)
        await db.commit()
    elif current_user:
        stmt = delete(UserSession).where(UserSession.user_id == current_user.id)
        await db.execute(stmt)
        await db.commit()

    response.delete_cookie("session_id", path="/")
    response.delete_cookie("sessionId", path="/")
    return {"code": CODE_SUCCESS, "message": "Logged out"}


@router.get("/info")
@router.get("/info/")
async def get_user_info(current_user: User = Depends(get_current_user)):
    return {
        "username": current_user.username,
        "email": current_user.email,
        "intro": current_user.intro,
        "is_active": current_user.is_active,
        "createdAt": current_user.created_at.isoformat() if current_user.created_at else None
    }


@router.get("/session")
async def get_current_session(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    session_id = request.cookies.get("session_id") or request.cookies.get("sessionId")
    stmt = select(UserSession).where(UserSession.session_id == session_id)
    res = await db.execute(stmt)
    session = res.scalar_one_or_none()
    if not session:
        return {"username": current_user.username}
    return {
        "sessionId": session.session_id,
        "username": current_user.username,
        "createdAt": session.created_at.isoformat(),
        "expiresAt": session.expires_at.isoformat(),
        "userAgent": session.user_agent,
        "ipAddress": session.ip_address,
    }


@router.get("/sessions")
async def get_all_sessions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    now = datetime.now(timezone.utc)
    stmt = (
        select(UserSession)
        .where(UserSession.user_id == current_user.id, UserSession.expires_at > now)
        .order_by(desc(UserSession.created_at))
    )
    result = await db.execute(stmt)
    sessions = result.scalars().all()
    return [
        {
            "sessionId": s.session_id,
            "username": current_user.username,
            "createdAt": s.created_at.isoformat(),
            "expiresAt": s.expires_at.isoformat(),
            "userAgent": s.user_agent,
            "ipAddress": s.ip_address,
        }
        for s in sessions
    ]


@router.get("/intro")
async def get_user_intro(
    username: str = Query(""),
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db)
):
    target_username = username.strip() or (current_user.username if current_user else "")
    if not target_username:
        return ""
    
    stmt = select(User).where(User.username == target_username)
    res = await db.execute(stmt)
    user = res.scalar_one_or_none()
    if not user:
        return ""
    return user.intro or ""


@router.post("/intro")
async def update_user_intro(
    content: str = Form(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    current_user.intro = content
    await db.commit()
    return {"code": CODE_SUCCESS, "message": "Intro updated"}


@router.get("/Icon")
@router.get("/icon")
async def get_user_icon(
    username: str = Query(...),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(User).where(User.username == username)
    res = await db.execute(stmt)
    user = res.scalar_one_or_none()
    
    if user and user.icon_filename:
        icon_path = settings.AVATARS_DIR / user.icon_filename
        if icon_path.exists():
            mime, _ = mimetypes.guess_type(str(icon_path))
            return FileResponse(icon_path, media_type=mime or "image/jpeg")

    # Generate or return fallback SVG avatar
    svg_avatar = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="100" height="100">
        <rect width="100" height="100" fill="#3b82f6"/>
        <text x="50%" y="55%" dominant-baseline="middle" text-anchor="middle" font-size="40" font-family="sans-serif" font-weight="bold" fill="#ffffff">
            {(username[0] if username else '?').upper()}
        </text>
    </svg>"""
    return Response(content=svg_avatar, media_type="image/svg+xml")


@router.post("/Icon")
@router.post("/icon")
async def upload_user_icon(
    pic: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    ext = Path(pic.filename or "avatar.png").suffix or ".png"
    filename = f"{current_user.id}_{int(datetime.now().timestamp())}{ext}"
    filepath = settings.AVATARS_DIR / filename
    
    content = await pic.read()
    filepath.write_bytes(content)

    current_user.icon_filename = filename
    await db.commit()
    return {"code": CODE_SUCCESS, "message": "Icon uploaded successfully"}


@router.get("/Recent")
@router.get("/recent")
async def get_recent_activity(
    username: str = Query(...),
    db: AsyncSession = Depends(get_db)
):
    stmt_user = select(User).where(User.username == username)
    res_user = await db.execute(stmt_user)
    user = res_user.scalar_one_or_none()
    if not user:
        return []

    stmt = (
        select(Score, Chart)
        .outerjoin(Chart, Score.chart_hash == Chart.hash)
        .where(Score.user_id == user.id)
        .order_by(desc(Score.timestamp))
        .limit(20)
    )
    result = await db.execute(stmt)
    records = result.all()

    recent_list = []
    for score, chart in records:
        chart_id = str(uuid.uuid5(uuid.NAMESPACE_OID, str(chart.id))) if chart else "00000000-0000-0000-0000-000000000000"
        title = chart.title if chart else "Unknown"
        artist = chart.artist if chart else ""
        uploader = chart.uploader if chart else ""
        designer = chart.designer if chart else ""
        levels = chart.levels if chart else []
        level_str = levels[score.chart_level] if score.chart_level < len(levels) and levels[score.chart_level] else ""

        recent_list.append({
            "chartId": chart_id,
            "title": title,
            "artist": artist,
            "uploader": uploader,
            "designer": designer,
            "level": level_str,
            "difficulty": f"lv_{score.chart_level + 1}",
            "acc": score.acc_dx,
            "comboState": score.combo_state,
            "timestamp": score.timestamp.isoformat() if score.timestamp else None,
        })
    return recent_list


@router.get("/scores")
async def get_user_scores(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    stmt = (
        select(Score, Chart)
        .outerjoin(Chart, Score.chart_hash == Chart.hash)
        .where(Score.user_id == current_user.id)
        .order_by(desc(Score.timestamp))
    )
    result = await db.execute(stmt)
    records = result.all()

    score_list = []
    for score, chart in records:
        chart_info = {
            "id": str(uuid.uuid5(uuid.NAMESPACE_OID, str(chart.id))) if chart else "00000000-0000-0000-0000-000000000000",
            "title": chart.title if chart else "",
            "artist": chart.artist if chart else "",
            "designer": chart.designer if chart else "",
            "description": chart.description if chart else "",
            "levels": chart.levels if chart else [],
            "uploader": chart.uploader if chart else "",
            "timestamp": chart.timestamp.isoformat() if chart and chart.timestamp else "",
            "hash": score.chart_hash,
            "tags": chart.tags if chart else [],
            "publicTags": chart.public_tags if chart else [],
        }
        score_list.append({
            "acc": {"dx": score.acc_dx, "classic": score.acc_classic},
            "dxScore": score.dx_score,
            "comboState": score.combo_state,
            "chartLevel": score.chart_level,
            "hash": score.chart_hash,
            "chartInfo": chart_info,
            "timestamp": score.timestamp.isoformat() if score.timestamp else "",
        })
    return score_list


@router.get("/verify")
async def verify_otp(
    otp: str = Query(...),
    db: AsyncSession = Depends(get_db)
):
    now = datetime.now(timezone.utc)
    stmt = select(OTPVerification).where(
        OTPVerification.otp == otp,
        OTPVerification.is_used == False,
        OTPVerification.expires_at > now
    )
    res = await db.execute(stmt)
    otp_record = res.scalar_one_or_none()
    if not otp_record:
        raise HTTPException(status_code=400, detail="Invalid or expired OTP")

    otp_record.is_used = True
    stmt_user = select(User).where(User.username == otp_record.username)
    user_res = await db.execute(stmt_user)
    user = user_res.scalar_one_or_none()
    if user:
        user.is_active = True
    await db.commit()
    return {"code": CODE_SUCCESS, "message": "Account verified successfully"}


@router.post("/forget")
async def forget_password_request(
    username: str = Form(...),
    email: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(User).where(User.username == username, User.email == email)
    res = await db.execute(stmt)
    user = res.scalar_one_or_none()
    if not user:
        return JSONResponse(status_code=400, content={"code": CODE_NO_SUCH_ITEM, "message": "User not found"})

    otp_code = str(uuid.uuid4())[:8]
    otp = OTPVerification(
        username=username,
        email=email,
        otp=otp_code,
        purpose="reset_password",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=2)
    )
    db.add(otp)
    await db.commit()
    # In production, send reset email with otp_code
    return {"code": CODE_SUCCESS, "message": "Reset email sent"}


@router.put("/forget")
async def reset_password(
    otp: str = Form(...),
    newpassword: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    now = datetime.now(timezone.utc)
    stmt = select(OTPVerification).where(
        OTPVerification.otp == otp,
        OTPVerification.is_used == False,
        OTPVerification.expires_at > now
    )
    res = await db.execute(stmt)
    otp_record = res.scalar_one_or_none()
    if not otp_record:
        return JSONResponse(status_code=400, content={"code": CODE_INVALID_VALUE, "message": "Invalid or expired OTP"})

    otp_record.is_used = True
    stmt_user = select(User).where(User.username == otp_record.username)
    user_res = await db.execute(stmt_user)
    user = user_res.scalar_one_or_none()
    if user:
        user.password_hash = hash_password(newpassword)
    await db.commit()
    return {"code": CODE_SUCCESS, "message": "Password reset successfully"}


@router.get("/favorite/collection/list")
async def get_favorite_collections(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    stmt = (
        select(Collection)
        .options(selectinload(Collection.items), selectinload(Collection.user))
        .join(CollectionFavorite, Collection.id == CollectionFavorite.collection_id)
        .where(CollectionFavorite.user_id == current_user.id)
    )
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


@router.post("/favorite/collection/diff")
async def get_favorite_collection_diff(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    return {"diff": []}
