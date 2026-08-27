from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel

class ParsedChartResponse(BaseModel):
    id: str
    title: str
    artist: str
    designer: str
    description: str = ""
    timestamp: str
    hash: str
    levels: List[Optional[str]]

class SongSummaryResponse(BaseModel):
    id: str
    title: str
    artist: str
    uploader: str
    designer: str
    levels: List[Optional[str]]
    tags: List[str] = []
    publicTags: List[str] = []
    hash: str
    timestamp: str
    description: Optional[str] = ""

class SongListItemResponse(BaseModel):
    id: str
    title: str
    artist: str
    uploader: str
    designer: str
    levels: List[Optional[str]]
    hash: str
