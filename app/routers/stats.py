from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from app.database import get_db
from app.models.chart import Chart
from app.models.score import Score
from app.models.user import User

router = APIRouter(prefix="/stats", tags=["Stats"])

@router.get("/score-sums")
async def get_score_sums(
    uploader: Optional[str] = Query(None),
    page: int = Query(0, ge=0),
    pageSize: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db)
):
    """Get aggregated score statistics by user."""
    stmt = (
        select(
            User.username,
            func.sum(Score.acc_dx).label("dxAccSum"),
            func.count(Score.id).label("scoreCount"),
        )
        .join(User, Score.user_id == User.id)
    )

    if uploader:
        # Filter scores on charts uploaded by specific uploader
        stmt = stmt.join(Chart, Score.chart_hash == Chart.hash).where(Chart.uploader == uploader)

    stmt = (
        stmt.group_by(User.username)
        .order_by(desc("dxAccSum"))
        .offset(page * pageSize)
        .limit(pageSize)
    )
    res = await db.execute(stmt)
    rows = res.all()

    return [
        {
            "username": row.username,
            "dxAccSum": float(row.dxAccSum or 0),
            "scoreCount": row.scoreCount,
        }
        for row in rows
    ]
