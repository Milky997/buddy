"""数据结构定义

只描述数据长什么样，不含任何业务逻辑。
借鉴 hello-agent 的 MemoryItem(pydantic BaseModel)，
但字段精简为 English Buddy 真正需要的。
"""

from pydantic import BaseModel, Field
from datetime import datetime
from typing import List


class UserProfile(BaseModel):
    """用户画像 —— 慢变量，跨 session 持久化"""

    user_id: str
    name: str = "unknown"
    level: str = "unknown"           # beginner / intermediate / advanced / unknown
    interests: List[str] = Field(default_factory=list)
    session_count: int = 0
    updated_at: datetime = Field(default_factory=datetime.now)

    class Config:
        # 允许 datetime 等非基础类型
        arbitrary_types_allowed = True


class Episode(BaseModel):
    """单轮对话记录 —— 快变量，用于短期上下文"""

    id: int = -1                     # 由数据库自增，写入前为 -1
    user_id: str
    user_msg: str
    reply: str
    persona: str                     # cheerful / calm / coach
    created_at: datetime = Field(default_factory=datetime.now)

    class Config:
        arbitrary_types_allowed = True
