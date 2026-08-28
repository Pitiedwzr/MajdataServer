from typing import List
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from app.database import get_db
from app.models.chart import Chart
from app.models.score import Score
from app.models.user import User
from app.services.auth import get_current_user
from app.schemas.score import ScoreSubmitRequest
from app.routers.maichart import get_real_chart_id  # Import the UUID cache

router = APIRouter(prefix="/maichart", tags=["Score"])

@router.get("/{chartId}/score")
async def get_chart_scores(
        chartId: str,
        db: AsyncSession = Depends(get_db)
):
    """Get leaderboard scores for each difficulty level of a chart."""
    real_id = await get_real_chart_id(chartId, db)

    stmt_chart = select(Chart).where(Chart.id == real_id)
    res_chart = await db.execute(stmt_chart)
    chart = res_chart.scalar_one_or_none()

    if not chart:
        return {"levels": [], "scores": []}

    levels = chart.levels
    scores_by_level: List[List[dict]] = [[] for _ in range(len(levels))]

    stmt_scores = (
        select(Score, User.username)
        .join(User, Score.user_id == User.id)
        .where(Score.chart_hash == chart.hash)
        .order_by(Score.chart_level, desc(Score.acc_dx))
    )
    res_scores = await db.execute(stmt_scores)
    all_scores = res_scores.all()

    user_seen = [set() for _ in range(len(levels))]

    for score, username in all_scores:
        lvl = score.chart_level
        if 0 <= lvl < len(levels):
            if username not in user_seen[lvl]:
                user_seen[lvl].add(username)
                scores_by_level[lvl].append({
                    "player": {"username": username},
                    "acc": score.acc_dx,
                    "comboState": score.combo_state,
                })

    return {
        "levels": levels,
        "scores": scores_by_level
    }


@router.post("/{chartId}/score")
async def submit_chart_score(
        chartId: str,
        req: ScoreSubmitRequest = Body(...),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """Submit a gameplay score for a chart."""
    # 1. Translate the client's UUID back to the original database string ID
    real_id = await get_real_chart_id(chartId, db)

    # 2. Look up the chart using the real ID
    stmt_chart = select(Chart).where(Chart.id == real_id)
    res_chart = await db.execute(stmt_chart)
    chart = res_chart.scalar_one_or_none()

    # 3. Fallback: If not found by ID but the client sent a hash, try finding it by hash
    if not chart and req.hash:
        stmt_chart = select(Chart).where(Chart.hash == req.hash)
        res_chart = await db.execute(stmt_chart)
        chart = res_chart.scalar_one_or_none()

    # Fallback to the real_id if the chart doesn't exist yet, avoiding DB UUID crashes
    final_chart_id = chart.id if chart else real_id
    final_chart_hash = chart.hash if chart else (req.hash or "unknown_hash")

    score = Score(
        user_id=current_user.id,
        chart_id=final_chart_id,
        chart_hash=final_chart_hash,
        chart_level=req.chartLevel,
        dx_score=req.dxScore,
        combo_state=req.comboState,
        acc_dx=req.acc.dx,
        acc_classic=req.acc.classic,
        timestamp=datetime.now(timezone.utc),
    )
    db.add(score)

    try:
        await db.commit()
    except Exception:
        await db.rollback()
        return {"code": 500, "message": "Server error during submission"}

    return {"code": 114514, "message": "Score submitted successfully"}