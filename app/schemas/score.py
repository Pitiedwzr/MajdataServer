from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field

class AccDetail(BaseModel):
    dx: float = Field(default=0.0, alias="DX")
    classic: float = Field(default=0.0, alias="Classic")

class ScoreSubmitRequest(BaseModel):
    chartLevel: int = Field(default=0, alias="ChartLevel")
    hash: Optional[str] = Field(default=None, alias="Hash")
    dxScore: int = Field(default=0, alias="DXScore")
    comboState: int = Field(default=0, alias="ComboState")
    acc: AccDetail = Field(alias="Acc")

class PlayerInfo(BaseModel):
    username: str

class ChartScoreItem(BaseModel):
    player: PlayerInfo
    acc: float
    comboState: int

class ChartScoresResponse(BaseModel):
    levels: List[Optional[str]]
    scores: List[List[ChartScoreItem]]

class RecentPlayedItem(BaseModel):
    chartId: str
    title: str
    artist: str
    uploader: str
    designer: str
    level: str
    difficulty: str
    acc: float
    comboState: int
    timestamp: str

class ScoreDetailResponse(BaseModel):
    acc: AccDetail
    dxScore: int
    comboState: int
    chartLevel: int
    hash: str
    chartInfo: Dict[str, Any]
    timestamp: str
