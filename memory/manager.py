"""记忆管理层 —— 业务逻辑，不直接碰数据库

对外提供三个主要方法：
  load(user_id)                        → UserProfile
  update_async(user_id, msg, reply, persona)  → 后台线程更新，线程安全
  get_recent_history(user_id, limit)   → List[dict]  可直接传给 LLM

与现有代码的对应关系：
  load_memory()      → manager.load(user_id)
  save_memory()      → 内部自动调用，无需手动
  update_memory_async() → manager.update_async(...)
"""

import json
import logging
import threading
from typing import Any, Dict, List

from openai import OpenAI
import os

from .models import Episode, UserProfile
from .store import MemoryStore

logger = logging.getLogger(__name__)


class MemoryManager:
    """English Buddy 记忆管理器"""

    def __init__(
        self,
        db_path: str = "./buddy_memory.db",
        llm_client: OpenAI = None,
        extract_model: str = "qwen-plus",
    ):
        self.store = MemoryStore(db_path)
        self.client = llm_client or OpenAI(
            api_key=os.environ.get("DASHSCOPE_API_KEY"),
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        )
        self.extract_model = extract_model
        self._lock = threading.Lock()   # 保护 profile 并发写入

    # ── 对外主接口 ────────────────────────────────────────

    def load(self, user_id: str) -> UserProfile:
        """加载用户画像，不存在则返回默认值"""
        data = self.store.get_profile(user_id)
        if data is None:
            return UserProfile(user_id=user_id)
        return UserProfile(**data)

    def save(self, profile: UserProfile):
        """保存用户画像"""
        with self._lock:
            self.store.upsert_profile(profile.user_id, profile.dict())

    def update_async(
        self,
        user_id: str,
        user_msg: str,
        reply: str,
        persona: str,
        profile: UserProfile,
    ):
        """后台线程更新记忆（非阻塞）
        
        1. 持久化本轮对话到 episodes
        2. 用 LLM 提取 level / interests / name 更新 profile
        """
        threading.Thread(
            target=self._update_worker,
            args=(user_id, user_msg, reply, persona, profile),
            daemon=True,
        ).start()

    def get_recent_history(
        self, user_id: str, limit: int = 5
    ) -> List[Dict[str, str]]:
        """获取最近 N 轮对话，格式可直接作为 LLM messages history
        
        返回格式：[{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}, ...]
        """
        episodes = self.store.get_recent_episodes(user_id, limit)
        history = []
        for ep in episodes:
            history.append({"role": "user",      "content": ep["user_msg"]})
            history.append({"role": "assistant",  "content": ep["reply"]})
        return history

    # ── 内部方法 ──────────────────────────────────────────

    def _update_worker(
        self,
        user_id: str,
        user_msg: str,
        reply: str,
        persona: str,
        profile: UserProfile,
    ):
        try:
            # 1. 存对话记录
            self.store.append_episode(user_id, user_msg, reply, persona)

            # 2. LLM 提取信息
            extracted = self._extract_info(user_msg, reply)

            # 3. 合并到 profile
            changed = False

            name = extracted.get("user_name", "")
            if name and profile.name == "unknown":
                profile.name = name
                changed = True

            level = extracted.get("detected_level", "unknown")
            if level != "unknown" and level != profile.level:
                profile.level = level
                changed = True

            for topic in extracted.get("topics_mentioned", []):
                if topic and topic not in profile.interests:
                    profile.interests.append(topic)
                    changed = True

            profile.session_count += 1

            # 4. 写回数据库
            self.save(profile)

            if changed:
                logger.debug(f"[MemoryManager] profile 已更新: {profile.user_id}")

        except Exception as e:
            logger.warning(f"[MemoryManager] 后台更新失败: {e}")

    def _extract_info(self, user_msg: str, reply: str) -> Dict[str, Any]:
        """用 LLM 从对话中提取结构化信息"""
        prompt = f"""Analyze this English learner exchange and extract structured info.

User said: {user_msg}
Assistant replied: {reply}

Return ONLY valid JSON with no markdown, using these exact keys:
{{
  "detected_level": "beginner|intermediate|advanced|unknown",
  "topics_mentioned": [],
  "user_name": ""
}}

- topics_mentioned: ONLY if the user showed clear enthusiasm or asked follow-up questions. Max 1 topic. Must be specific (e.g. "minecraft"), not generic (e.g. "games").
- detected_level: best guess, or "unknown" if unclear
- user_name: extract if mentioned, else empty string"""

        try:
            response = self.client.chat.completions.create(
                model=self.extract_model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200,
            )
            raw = response.choices[0].message.content.strip()
            # 去掉可能的 markdown 代码块
            if "```" in raw:
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            return json.loads(raw.strip())
        except Exception as e:
            logger.warning(f"[MemoryManager] LLM 提取失败: {e}")
            return {}
