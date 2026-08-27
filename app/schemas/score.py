from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel

class AccDetail(BaseModel):
    dx: float = 0.0
    classic: float = 0.0

class ScoreSubmitRequest(BaseModel):
    chartLevel: int = 0
    hash: str
    dxScore: int = 0
    comboState: int = 0
    acc: AccDetail

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
