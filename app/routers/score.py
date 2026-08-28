import uuid
from typing import List, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from sqlalchemy.exc import IntegrityError
from app.database import get_db
from app.models.chart import Chart
from app.models.score import Score
from app.models.user import User
from app.services.auth import get_current_user
from app.schemas.score import ScoreSubmitRequest, ChartScoresResponse

router = APIRouter(prefix="/maichart", tags=["Score"])

@router.get("/{chartId}/score")
async def get_chart_scores(
        chartId: str,
        db: AsyncSession = Depends(get_db)
):
    """
    Get leaderboard scores for each difficulty level of a chart.
    Matches frontend ChartScoresResponse shape.
    """
    # INTERCEPT CLIENT BUG: If client sends literal "{0}", return empty leaderboard
    # since we don't have the hash in a GET request body to look it up.
    if chartId in ("{0}", "%7B0%7D"):
        return {"levels": [], "scores": []}

    stmt_chart = select(Chart).where(Chart.id == chartId)
    res_chart = await db.execute(stmt_chart)
    chart = res_chart.scalar_one_or_none()

    if not chart:
        return {"levels": [], "scores": []}

    levels = chart.levels
    scores_by_level: List[List[dict]] = [[] for _ in range(len(levels))]

    # Get scores grouped by level
    stmt_scores = (
        select(Score, User.username)
        .join(User, Score.user_id == User.id)
        .where(Score.chart_hash == chart.hash)
        .order_by(Score.chart_level, desc(Score.acc_dx))
    )
    res_scores = await db.execute(stmt_scores)
    all_scores = res_scores.all()

    # Track best score per user per level
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
    # Find the chart using the hash provided in the body
    stmt_chart = select(Chart).where(Chart.hash == req.hash)
    res_chart = await db.execute(stmt_chart)
    chart = res_chart.scalar_one_or_none()

    valid_chart_id = chartId
    if chartId in ("{0}", "%7B0%7D"):
        valid_chart_id = chart.id if chart else str(uuid.uuid4())
    else:
        # Use the actual string ID from the database, not the hashed UUID from the client
        valid_chart_id = chart.id if chart else chartId

    score = Score(
        user_id=current_user.id,
        chart_id=valid_chart_id,  # Will store the original 'T3V0...' format if chart is found
        chart_hash=req.hash,
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