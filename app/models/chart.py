from datetime import datetime, timezone
import json
from sqlalchemy import Column, String, DateTime, Text, JSON
from app.database import Base

def utcnow():
    return datetime.now(timezone.utc)

class Chart(Base):
    __tablename__ = "charts"

    id = Column(String(255), primary_key=True) # Base64 URL-safe folder path
    folder_path = Column(String(500), unique=True, index=True, nullable=False)
    title = Column(String(255), default="", index=True, nullable=False)
    artist = Column(String(255), default="", index=True, nullable=False)
    designer = Column(String(255), default="", index=True, nullable=False)
    uploader = Column(String(50), default="", index=True, nullable=False)
    description = Column(Text, default="", nullable=False)
    hash = Column(String(64), index=True, nullable=False) # Base64 MD5 of maidata.txt
    levels_json = Column(JSON, default=lambda: [None] * 7, nullable=False)
    tags_json = Column(JSON, default=list, nullable=False)
    public_tags_json = Column(JSON, default=list, nullable=False)
    timestamp = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    @property
    def levels(self):
        return self.levels_json if self.levels_json is not None else [None] * 7

    @property
    def tags(self):
        return self.tags_json if self.tags_json is not None else []

    @property
    def public_tags(self):
        return self.public_tags_json if self.public_tags_json is not None else []
