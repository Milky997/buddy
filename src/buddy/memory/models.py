from pydantic import BaseModel, Field
from datetime import datetime
from typing import List

class UserProfile(BaseModel):
    user_id: str
    name: str = "unknown"
    level: str = "unknown"
    interests: List[str] = Field(default_factory=list)
    session_count: int = 0
    updated_at: datetime = Field(default_factory=datetime.now)
    class Config:
        arbitrary_types_allowed = True

class Episode(BaseModel):
    id: int = -1
    user_id: str
    user_msg: str
    reply: str
    persona: str
    created_at: datetime = Field(default_factory=datetime.now)
    class Config:
        arbitrary_types_allowed = True
