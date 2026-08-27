from typing import Optional, List, Any
from datetime import datetime
from pydantic import BaseModel

class CollectionCreateRequest(BaseModel):
    name: str
    description: Optional[str] = ""
    visibility: int = 0 # 0: Private, 1: Public

class CollectionModifyRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    visibility: Optional[int] = None
    items: Optional[List[str]] = None # List of hashes

class CollectionResponse(BaseModel):
    id: str
    name: str
    createdBy: str
    description: Optional[str] = ""
    count: int = 0
    visibility: int = 0

class CollectionSongListResponse(CollectionResponse):
    items: List[Any] = []
