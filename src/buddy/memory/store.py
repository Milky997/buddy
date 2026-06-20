"""SQLite 存储层（线程安全，WAL 模式，单例）。"""
import json, os, sqlite3, threading
from datetime import datetime
from typing import Any, Dict, List, Optional

class MemoryStore:
    _instances: Dict[str, "MemoryStore"] = {}
    def __new__(cls, db_path: str = "./buddy_memory.db") -> "MemoryStore":
        ap = os.path.abspath(db_path)
        if ap not in cls._instances:
            cls._instances[ap] = super().__new__(cls)
        return cls._instances[ap]
    def __init__(self, db_path: str = "./buddy_memory.db"):
        if hasattr(self, "_ready"):
            return
        self.db_path = os.path.abspath(db_path)
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._local = threading.local()
        self._init_tables()
        self._ready = True
    def _conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn"):
            self._local.conn = sqlite3.connect(self.db_path)
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
        return self._local.conn
    def _init_tables(self):
        c = self._conn()
        c.executescript("""
            CREATE TABLE IF NOT EXISTS profile (
                user_id TEXT PRIMARY KEY, name TEXT DEFAULT 'unknown',
                level TEXT DEFAULT 'unknown', interests TEXT DEFAULT '[]',
                session_count INTEGER DEFAULT 0, updated_at TEXT);
            CREATE TABLE IF NOT EXISTS episodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL,
                user_msg TEXT NOT NULL, reply TEXT NOT NULL,
                persona TEXT NOT NULL, created_at TEXT DEFAULT (datetime('now')));
            CREATE INDEX IF NOT EXISTS idx_episodes_user ON episodes (user_id, created_at DESC);""")
        c.commit()
    def get_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        row = self._conn().execute("SELECT * FROM profile WHERE user_id = ?", (user_id,)).fetchone()
        if row is None:
            return None
        d = dict(row)
        d["interests"] = json.loads(d["interests"])
        return d
    def upsert_profile(self, user_id: str, data: Dict[str, Any]):
        c = self._conn()
        c.execute("""
            INSERT INTO profile (user_id, name, level, interests, session_count, updated_at)
            VALUES (:user_id, :name, :level, :interests, :session_count, :updated_at)
            ON CONFLICT(user_id) DO UPDATE SET
                name=excluded.name, level=excluded.level, interests=excluded.interests,
                session_count=excluded.session_count, updated_at=excluded.updated_at""",
            {"user_id": user_id, "name": data.get("name", "unknown"),
             "level": data.get("level", "unknown"),
             "interests": json.dumps(data.get("interests", []), ensure_ascii=False),
             "session_count": data.get("session_count", 0),
             "updated_at": datetime.now().isoformat()})
        c.commit()
    def append_episode(self, user_id: str, user_msg: str, reply: str, persona: str) -> int:
        cur = self._conn().execute(
            "INSERT INTO episodes (user_id, user_msg, reply, persona) VALUES (?, ?, ?, ?)",
            (user_id, user_msg, reply, persona))
        self._conn().commit()
        return cur.lastrowid
    def get_recent_episodes(self, user_id: str, limit: int = 5) -> List[Dict[str, Any]]:
        rows = self._conn().execute(
            "SELECT * FROM episodes WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit)).fetchall()
        return [dict(r) for r in reversed(rows)]
    def close(self):
        if hasattr(self._local, "conn"):
            self._local.conn.close()
            del self._local.conn
