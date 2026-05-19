"""
迁移指南：buddy_core_c.py 改动说明
只需改动 4 处，其他逻辑完全不动。
"""

# ══════════════════════════════════════════════════════════
# 第 1 处：替换 import
# ══════════════════════════════════════════════════════════

# 旧代码（删掉）：
# from pathlib import Path
# import json
# MEMORY_FILE = Path("user_memory.md")

# 新代码（加上）：
from buddy_memory import MemoryManager
memory_manager = MemoryManager(db_path="./buddy_memory.db")


# ══════════════════════════════════════════════════════════
# 第 2 处：chat() 函数签名不变，内部改两行
# ══════════════════════════════════════════════════════════

# 旧代码：
# def chat(user_message, history, memory, persona_key=DEFAULT_PERSONA):
#     ...
#     update_memory_async(memory, user_message, reply, history)  # ← 删掉
#     return reply

# 新代码：
# def chat(user_message, history, memory, persona_key=DEFAULT_PERSONA):
#     ...
#     memory_manager.update_async(                               # ← 换成这行
#         user_id=memory.user_id,
#         user_msg=user_message,
#         reply=reply,
#         persona=persona_key,
#         profile=memory,
#     )
#     return reply


# ══════════════════════════════════════════════════════════
# 第 3 处：serve.py — get_session() 里替换 load_memory()
# ══════════════════════════════════════════════════════════

# 旧代码：
# "memory": load_memory(),

# 新代码：
# "memory": memory_manager.load(session_id),


# ══════════════════════════════════════════════════════════
# 第 4 处：serve.py — /chat 路由，history 可选择从数据库恢复
# ══════════════════════════════════════════════════════════

# 可选优化：服务重启后 history 不再丢失
# 在 get_session() 里，histories 初始化改为：
#
# "histories": {
#     key: memory_manager.get_recent_history(session_id, limit=5)
#     for key in PERSONAS
# }
#
# 这样重启服务后，孩子继续说话，Buddy 还记得上次聊了什么。


# ══════════════════════════════════════════════════════════
# 可以删掉的旧函数（buddy_core_c.py 里）
# ══════════════════════════════════════════════════════════
#
# load_memory()           → 由 memory_manager.load() 替代
# save_memory()           → 由 memory_manager.save() 替代（内部自动调用）
# update_memory_async()   → 由 memory_manager.update_async() 替代
