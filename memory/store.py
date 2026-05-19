"""存储层 —— 只管 SQLite 读写，不含业务逻辑

借鉴 hello-agent document_store.py 的两个工程细节：
  1. threading.local() 线程本地连接，解决并发写入问题
  2. 单例模式，同一 db 文件只建一个实例

只建两张表：
  profile  —— 用户画像（慢变量）
  episodes —— 对话记录（快变量）
"""

import json
import os
import sqlite3
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional


class MemoryStore:
    """SQLite 存储，线程安全单例"""

    _instances: Dict[str, "MemoryStore"] = {}

    def __new__(cls, db_path: str = "./buddy_memory.db") -> "MemoryStore":
        abs_path = os.path.abspath(db_path)
        if abs_path not in cls._instances:
            instance = super().__new__(cls)
            cls._instances[abs_path] = instance
        return cls._instances[abs_path]

    def __init__(self, db_path: str = "./buddy_memory.db"):
        if hasattr(self, "_ready"):
            return

        self.db_path = os.path.abspath(db_path)
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._local = threading.local()   # 每个线程独立连接
        self._init_tables()
        self._ready = True
        print(f"[MemoryStore] SQLite 初始化完成: {self.db_path}")

    # ── 连接管理 ──────────────────────────────────────────

    def _conn(self) -> sqlite3.Connection:
        """返回当前线程的连接，不存在则新建"""
        if not hasattr(self._local, "conn"):
            self._local.conn = sqlite3.connect(self.db_path)
            self._local.conn.row_factory = sqlite3.Row
            # WAL 模式：写操作不阻塞读操作，多线程友好
            self._local.conn.execute("PRAGMA journal_mode=WAL")
        return self._local.conn

    def _init_tables(self):
        conn = self._conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS profile (
                user_id       TEXT PRIMARY KEY,
                name          TEXT    DEFAULT 'unknown',
                level         TEXT    DEFAULT 'unknown',
                interests     TEXT    DEFAULT '[]',
                session_count INTEGER DEFAULT 0,
                updated_at    TEXT
            );

            CREATE TABLE IF NOT EXISTS episodes (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    TEXT NOT NULL,
                user_msg   TEXT NOT NULL,
                reply      TEXT NOT NULL,
                persona    TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_episodes_user
                ON episodes (user_id, created_at DESC);
        """)
        conn.commit()

    # ── Profile CRUD ──────────────────────────────────────

    def get_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        row = self._conn().execute(
            "SELECT * FROM profile WHERE user_id = ?", (user_id,)
        ).fetchone()
        if row is None:
            return None
        d = dict(row)
        d["interests"] = json.loads(d["interests"])
        return d

    def upsert_profile(self, user_id: str, data: Dict[str, Any]):
        """插入或更新用户画像"""
        conn = self._conn()
        conn.execute("""
            INSERT INTO profile (user_id, name, level, interests, session_count, updated_at)
            VALUES (:user_id, :name, :level, :interests, :session_count, :updated_at)
            ON CONFLICT(user_id) DO UPDATE SET
                name          = excluded.name,
                level         = excluded.level,
                interests     = excluded.interests,
                session_count = excluded.session_count,
                updated_at    = excluded.updated_at
        """, {
            "user_id":       user_id,
            "name":          data.get("name", "unknown"),
            "level":         data.get("level", "unknown"),
            "interests":     json.dumps(data.get("interests", []), ensure_ascii=False),
            "session_count": data.get("session_count", 0),
            "updated_at":    datetime.now().isoformat(),
        })
        conn.commit()

    # ── Episodes CRUD ─────────────────────────────────────

    def append_episode(
        self,
        user_id: str,
        user_msg: str,
        reply: str,
        persona: str,
    ) -> int:
        """追加一条对话记录，返回自增 id"""
        conn = self._conn()
        cursor = conn.execute("""
            INSERT INTO episodes (user_id, user_msg, reply, persona)
            VALUES (?, ?, ?, ?)
        """, (user_id, user_msg, reply, persona))
        conn.commit()
        return cursor.lastrowid

    def get_recent_episodes(
        self, user_id: str, limit: int = 5
    ) -> List[Dict[str, Any]]:
        """获取最近 N 条对话，按时间升序（方便直接拼 history）"""
        rows = self._conn().execute("""
            SELECT * FROM episodes
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
        """, (user_id, limit)).fetchall()
        # 反转为时间升序
        return [dict(r) for r in reversed(rows)]

    # ── 工具方法 ──────────────────────────────────────────

    def close(self):
        if hasattr(self._local, "conn"):
            self._local.conn.close()
            del self._local.conn
