from typing import Optional, List, Any
from datetime import datetime
from pydantic import BaseModel

class CommentResponse(BaseModel):
    id: str
    sender: str
    content: str
    timestamp: str
    replyTo: Optional[str] = None
    replies: Optional[List[Any]] = []

class InteractionDataResponse(BaseModel):
    likes: List[str] = []
    isLiked: bool = False
    disLikeCount: int = 0
    isDisLiked: bool = False
    plays: int = 0
    comments: List[CommentResponse] = []

class InteractSumResponse(BaseModel):
    comments: int = 0
    likes: int = 0
    plays: int = 0
