"""buddy_memory - English Buddy 记忆系统

对外暴露的接口：
    MemoryManager  ← 主要使用这个
    UserProfile    ← 数据结构，需要时可直接用
"""

from .manager import MemoryManager
from .models import UserProfile, Episode

__all__ = ["MemoryManager", "UserProfile", "Episode"]
