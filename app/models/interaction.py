from datetime import datetime, timezone
import uuid
from sqlalchemy import Column, String, Integer, Boolean, DateTime, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from app.database import Base

def utcnow():
    return datetime.now(timezone.utc)

class ChartLike(Base):
    __tablename__ = "chart_likes"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    chart_id = Column(String(255), ForeignKey("charts.id"), index=True, nullable=False)
    user_id = Column(String(36), ForeignKey("users.id"), index=True, nullable=False)
    is_dislike = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("chart_id", "user_id", name="uq_chart_user_like"),
    )


class ChartComment(Base):
    __tablename__ = "chart_comments"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    chart_id = Column(String(255), ForeignKey("charts.id"), index=True, nullable=False)
    user_id = Column(String(36), ForeignKey("users.id"), index=True, nullable=False)
    content = Column(Text, nullable=False)
    reply_to = Column(String(36), ForeignKey("chart_comments.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    user = relationship("User", back_populates="comments")
    replies = relationship("ChartComment", cascade="all, delete-orphan")


class ChartPlay(Base):
    __tablename__ = "chart_plays"

    chart_id = Column(String(255), primary_key=True)
    play_count = Column(Integer, default=0, nullable=False)
