"""记忆管理层 —— 业务逻辑，不直接碰数据库

对外提供三个主要方法：
  load(user_id)                                        → UserProfile
  update_async(user_id, msg, reply, persona, profile)  → 后台线程，非阻塞
  get_recent_history(user_id, limit)                   → List[dict] 可直接传 LLM

记忆提取用本地 vLLM（通过 buddy_core_c.vllm_generate），
和 chat() 共享同一个串行队列，永远不会并发冲突。
"""

import json
import logging
import threading
from typing import Any, Dict, List

from .models import Episode, UserProfile
from .store import MemoryStore

logger = logging.getLogger(__name__)


class MemoryManager:
    """English Buddy 记忆管理器"""

    def __init__(self, db_path: str = "./buddy_memory.db"):
        self.store = MemoryStore(db_path)
        self._lock = threading.Lock()

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
        """后台线程更新记忆（非阻塞）"""
        threading.Thread(
            target=self._update_worker,
            args=(user_id, user_msg, reply, persona, profile),
            daemon=True,
            name=f"memory-update-{user_id}",
        ).start()

    def get_recent_history(
        self, user_id: str, limit: int = 5
    ) -> List[Dict[str, str]]:
        """获取最近 N 轮对话，格式可直接作为 LLM messages history"""
        episodes = self.store.get_recent_episodes(user_id, limit)
        history = []
        for ep in episodes:
            history.append({"role": "user",     "content": ep["user_msg"]})
            history.append({"role": "assistant", "content": ep["reply"]})
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

            # 2. vLLM 提取信息
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
                print(f"\n[💾 Memory updated: {user_id}]", end="", flush=True)

        except Exception as e:
            print(f"\n[后台记忆更新失败: {e}]", end="", flush=True)

    def _extract_info(self, user_msg: str, reply: str) -> Dict[str, Any]:
        """用本地 vLLM 提取结构化信息，走 buddy_core_v1 的串行队列"""
        # 延迟 import 避免循环依赖
        from buddy_core_v1 import vllm_generate, get_vllm_model
        from vllm import SamplingParams

        _, tokenizer = get_vllm_model()

        prompt_text = f"""Analyze this English learner exchange and extract structured info.

User said: {user_msg}
Assistant replied: {reply}

Return ONLY valid JSON with no markdown, using these exact keys:
{{
  "detected_level": "beginner|intermediate|advanced|unknown",
  "topics_mentioned": [],
  "user_name": ""
}}

Rules:
- topics_mentioned: ONLY if the user showed clear enthusiasm or asked follow-up questions. Max 1 topic. Must be specific (e.g. "minecraft"), not generic (e.g. "games").
- detected_level: best guess, or "unknown" if unclear
- user_name: extract if mentioned, else empty string
- Output JSON only, no explanation."""

        messages = [{"role": "user", "content": prompt_text}]
        prompt = tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )

        sampling_params = SamplingParams(temperature=0.1, max_tokens=150)

        try:
            raw = vllm_generate(prompt, sampling_params)
            if "```" in raw:
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            return json.loads(raw.strip())
        except Exception as e:
            logger.warning(f"[MemoryManager] 提取解析失败: {e}")
            return {}