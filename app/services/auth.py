import bcrypt
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import Request, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.config import settings
from app.database import get_db
from app.models.user import User, UserSession

def hash_password(password: str) -> str:
    """Hash password with bcrypt."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8")[:72], salt).decode("utf-8")

def verify_password(plain_or_md5_password: str, hashed_password: str) -> bool:
    """
    Verify password. Supports standard plain-text / bcrypt, and frontend MD5 pre-hashed passwords.
    """
    try:
        if bcrypt.checkpw(plain_or_md5_password.encode("utf-8")[:72], hashed_password.encode("utf-8")):
            return True
    except Exception:
        pass

    try:
        md5_input = hashlib.md5(plain_or_md5_password.encode("utf-8")).hexdigest()
        if bcrypt.checkpw(md5_input.encode("utf-8")[:72], hashed_password.encode("utf-8")):
            return True
    except Exception:
        pass

    return False

async def create_user_session(
    db: AsyncSession,
    user: User,
    remember_me: bool = False,
    user_agent: str = "",
    ip_address: str = ""
) -> UserSession:
    """Create a database-backed user session."""
    expire_days = 30 if remember_me else 1
    expires_at = datetime.now(timezone.utc) + timedelta(days=expire_days)
    
    session = UserSession(
        user_id=user.id,
        user_agent=user_agent[:250],
        ip_address=ip_address[:60],
        remember_me=remember_me,
        expires_at=expires_at,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session

async def get_current_user_optional(
    request: Request,
    db: AsyncSession = Depends(get_db)
) -> Optional[User]:
    """Extract session token from cookie, header, or query param and return User."""
    session_id = (
        request.cookies.get("session_id")
        or request.cookies.get("sessionId")
        or request.headers.get("X-Session-ID")
    )
    
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        session_id = auth_header[7:].strip()

    if not session_id:
        return None

    now = datetime.now(timezone.utc)
    stmt = (
        select(UserSession)
        .where(UserSession.session_id == session_id, UserSession.expires_at > now)
    )
    result = await db.execute(stmt)
    user_session = result.scalar_one_or_none()

    if not user_session:
        return None

    stmt_user = select(User).where(User.id == user_session.user_id)
    user_result = await db.execute(stmt_user)
    user = user_result.scalar_one_or_none()

    if not user or not user.is_active or user.is_banned:
        return None

    return user

async def get_current_user(
    user: Optional[User] = Depends(get_current_user_optional)
) -> User:
    """Strict dependency requiring authenticated user."""
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user
