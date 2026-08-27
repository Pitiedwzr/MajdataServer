from datetime import datetime, timezone
import uuid
from sqlalchemy import Column, String, Boolean, DateTime, Text, JSON, UniqueConstraint
from app.database import Base

def utcnow():
    return datetime.now(timezone.utc)

class Machine(Base):
    __tablename__ = "machines"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(100), nullable=False)
    description = Column(Text, default="", nullable=False)
    registered_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    is_authorized = Column(Boolean, default=True, nullable=False)


class MachineAuthRequest(Base):
    __tablename__ = "machine_auth_requests"

    auth_id = Column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    machine_id = Column(String(36), nullable=True)
    status = Column(String(20), default="pending", nullable=False) # pending, permitted, rejected
    user_id = Column(String(36), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)


class PersistData(Base):
    __tablename__ = "persist_data"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    app_id = Column(String(50), index=True, nullable=False)
    category = Column(String(50), index=True, nullable=False)
    user_id = Column(String(36), index=True, nullable=True)
    data_json = Column(JSON, default=dict, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("app_id", "category", "user_id", name="uq_app_category_user"),
    )
