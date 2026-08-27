from datetime import datetime, timezone
import uuid
from sqlalchemy import Column, String, Integer, Float, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from app.database import Base

def utcnow():
    return datetime.now(timezone.utc)

class Score(Base):
    __tablename__ = "scores"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), index=True, nullable=False)
    chart_id = Column(String(255), ForeignKey("charts.id"), index=True, nullable=True)
    chart_hash = Column(String(64), index=True, nullable=False)
    chart_level = Column(Integer, default=0, nullable=False) # 0 to 6 index
    dx_score = Column(Integer, default=0, nullable=False)
    combo_state = Column(Integer, default=0, nullable=False)
    acc_dx = Column(Float, default=0.0, nullable=False)
    acc_classic = Column(Float, default=0.0, nullable=False)
    timestamp = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    user = relationship("User", back_populates="scores")
    chart = relationship("Chart")

    __table_args__ = (
        Index("ix_scores_chart_hash_level", "chart_hash", "chart_level"),
        Index("ix_scores_user_hash_level", "user_id", "chart_hash", "chart_level"),
    )
