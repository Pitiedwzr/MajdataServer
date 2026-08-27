from typing import Optional, List
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Form, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func, and_
from app.database import get_db
from app.models.chart import Chart
from app.models.user import User
from app.models.interaction import ChartLike, ChartComment, ChartPlay
from app.services.auth import get_current_user, get_current_user_optional

router = APIRouter(prefix="/maichart", tags=["Interaction"])

@router.get("/{chartId}/interact")
async def get_chart_interactions(
    chartId: str,
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db)
):
    # Likes
    stmt_likes = (
        select(User.username)
        .join(ChartLike, ChartLike.user_id == User.id)
        .where(ChartLike.chart_id == chartId, ChartLike.is_dislike == False)
    )
    res_likes = await db.execute(stmt_likes)
    like_usernames = list(res_likes.scalars().all())

    # Dislikes count
    stmt_dislikes = select(func.count()).select_from(ChartLike).where(ChartLike.chart_id == chartId, ChartLike.is_dislike == True)
    res_dislikes = await db.execute(stmt_dislikes)
    dislike_count = res_dislikes.scalar() or 0

    # Current user like / dislike status
    is_liked = False
    is_disliked = False
    if current_user:
        stmt_user_like = select(ChartLike).where(ChartLike.chart_id == chartId, ChartLike.user_id == current_user.id)
        res_user_like = await db.execute(stmt_user_like)
        user_like = res_user_like.scalar_one_or_none()
        if user_like:
            is_liked = not user_like.is_dislike
            is_disliked = user_like.is_dislike

    # Plays
    stmt_plays = select(ChartPlay).where(ChartPlay.chart_id == chartId)
    res_plays = await db.execute(stmt_plays)
    play_rec = res_plays.scalar_one_or_none()
    plays = play_rec.play_count if play_rec else 0

    # Comments (top level with replies)
    stmt_comments = (
        select(ChartComment, User.username)
        .join(User, ChartComment.user_id == User.id)
        .where(ChartComment.chart_id == chartId)
        .order_by(ChartComment.created_at)
    )
    res_comments = await db.execute(stmt_comments)
    all_comments = res_comments.all()

    # Build tree
    comment_map = {}
    top_level_comments = []

    for comment, username in all_comments:
        c_dict = {
            "id": comment.id,
            "sender": username,
            "content": comment.content,
            "timestamp": comment.created_at.isoformat() if comment.created_at else "",
            "replyTo": comment.reply_to,
            "replies": [],
        }
        comment_map[comment.id] = c_dict

    for comment, username in all_comments:
        c_dict = comment_map[comment.id]
        if comment.reply_to and comment.reply_to in comment_map:
            comment_map[comment.reply_to]["replies"].append(c_dict)
        else:
            top_level_comments.append(c_dict)

    return {
        "likes": like_usernames,
        "isLiked": is_liked,
        "disLikeCount": dislike_count,
        "isDisLiked": is_disliked,
        "plays": plays,
        "comments": top_level_comments,
    }


@router.post("/{chartId}/interact")
async def create_interaction(
    chartId: str,
    type: str = Form(...),
    content: Optional[str] = Form(""),
    replyTo: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if type == "like":
        stmt = select(ChartLike).where(ChartLike.chart_id == chartId, ChartLike.user_id == current_user.id)
        res = await db.execute(stmt)
        existing = res.scalar_one_or_none()
        if existing:
            if existing.is_dislike:
                existing.is_dislike = False
            else:
                await db.delete(existing)
        else:
            db.add(ChartLike(chart_id=chartId, user_id=current_user.id, is_dislike=False))
        await db.commit()
        return {"code": 114514, "message": "Like updated"}

    elif type == "dislike":
        stmt = select(ChartLike).where(ChartLike.chart_id == chartId, ChartLike.user_id == current_user.id)
        res = await db.execute(stmt)
        existing = res.scalar_one_or_none()
        if existing:
            if not existing.is_dislike:
                existing.is_dislike = True
            else:
                await db.delete(existing)
        else:
            db.add(ChartLike(chart_id=chartId, user_id=current_user.id, is_dislike=True))
        await db.commit()
        return {"code": 114514, "message": "Dislike updated"}

    elif type == "comment":
        if not content or not content.strip():
            raise HTTPException(status_code=400, detail="Empty comment")
        comment = ChartComment(
            chart_id=chartId,
            user_id=current_user.id,
            content=content.strip(),
            reply_to=replyTo if replyTo else None,
            created_at=datetime.now(timezone.utc)
        )
        db.add(comment)
        await db.commit()
        return {"code": 114514, "message": "Comment posted"}

    elif type == "play":
        stmt = select(ChartPlay).where(ChartPlay.chart_id == chartId)
        res = await db.execute(stmt)
        play_rec = res.scalar_one_or_none()
        if play_rec:
            play_rec.play_count += 1
        else:
            db.add(ChartPlay(chart_id=chartId, play_count=1))
        await db.commit()
        return {"code": 114514, "message": "Play recorded"}

    raise HTTPException(status_code=400, detail="Unknown interaction type")


@router.delete("/{chartId}/interact")
async def delete_interaction(
    chartId: str,
    type: str = Query(...),
    commentId: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if type == "comment" and commentId:
        stmt = select(ChartComment).where(ChartComment.id == commentId)
        res = await db.execute(stmt)
        comment = res.scalar_one_or_none()
        if not comment:
            raise HTTPException(status_code=404, detail="Comment not found")
        if comment.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Permission denied")
        await db.delete(comment)
        await db.commit()
        return {"code": 114514, "message": "Comment deleted"}

    return {"code": 114514, "message": "Deleted"}


@router.get("/{chartId}/interactsum")
async def get_interaction_summary(
    chartId: str,
    db: AsyncSession = Depends(get_db)
):
    stmt_comments = select(func.count()).select_from(ChartComment).where(ChartComment.chart_id == chartId)
    res_comments = await db.execute(stmt_comments)
    comments_count = res_comments.scalar() or 0

    stmt_likes = select(func.count()).select_from(ChartLike).where(ChartLike.chart_id == chartId, ChartLike.is_dislike == False)
    res_likes = await db.execute(stmt_likes)
    likes_count = res_likes.scalar() or 0

    stmt_plays = select(ChartPlay).where(ChartPlay.chart_id == chartId)
    res_plays = await db.execute(stmt_plays)
    play_rec = res_plays.scalar_one_or_none()
    plays_count = play_rec.play_count if play_rec else 0

    return {
        "comments": comments_count,
        "likes": likes_count,
        "plays": plays_count,
    }
