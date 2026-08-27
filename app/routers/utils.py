from datetime import datetime, timezone
from fastapi import APIRouter

router = APIRouter(prefix="/utils", tags=["Utils"])

@router.get("/Ping")
@router.get("/ping")
async def ping():
    """Health check endpoint."""
    return {
        "status": "ok",
        "time": datetime.now(timezone.utc).isoformat(),
        "message": "pong"
    }
