from datetime import datetime, timezone
import uuid
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from app.database import Base

def utcnow():
    return datetime.now(timezone.utc)

class Collection(Base):
    __tablename__ = "collections"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), index=True, nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text, default="", nullable=True)
    visibility = Column(Integer, default=0, nullable=False) # 0: Private, 1: Public
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    user = relationship("User", back_populates="collections")
    items = relationship("CollectionItem", back_populates="collection", cascade="all, delete-orphan", order_by="CollectionItem.order_idx")
    favorites = relationship("CollectionFavorite", back_populates="collection", cascade="all, delete-orphan")


class CollectionItem(Base):
    __tablename__ = "collection_items"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    collection_id = Column(String(36), ForeignKey("collections.id"), index=True, nullable=False)
    chart_hash = Column(String(64), index=True, nullable=False)
    order_idx = Column(Integer, default=0, nullable=False)

    collection = relationship("Collection", back_populates="items")

    __table_args__ = (
        UniqueConstraint("collection_id", "chart_hash", name="uq_collection_chart_hash"),
    )


class CollectionFavorite(Base):
    __tablename__ = "collection_favorites"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), index=True, nullable=False)
    collection_id = Column(String(36), ForeignKey("collections.id"), index=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    collection = relationship("Collection", back_populates="favorites")

    __table_args__ = (
        UniqueConstraint("user_id", "collection_id", name="uq_user_collection_favorite"),
    )
