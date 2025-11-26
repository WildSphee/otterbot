import os
import sqlite3
import threading
from typing import Dict, List, Optional
import re

DATABASE_FILE = f"{os.getenv('DATABASE_NAME', 'database')}.db"


class DB:
    # Ensure singleton DB
    _instance_lock = threading.Lock()
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super(DB, cls).__new__(cls)
        return cls._instance

    def __init__(self, conn=None):
        # for monkeypatching in test
        self.conn = (
            conn if conn else sqlite3.connect(DATABASE_FILE, check_same_thread=False)
        )
        # dict-like rows
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self):
        cursor = self.conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS games (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT,
                status TEXT DEFAULT 'created',
                store_dir TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_researched_at DATETIME
            )
            """
        )

        # --- NEW: game_sources (files/links associated with a game) ---
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS game_sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id INT NOT NULL,
                source_type TEXT NOT NULL, -- pdf|html|link|video|txt|other
                url TEXT,
                title TEXT,
                local_path TEXT,
                added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (game_id) REFERENCES games(id) ON DELETE CASCADE
            )
            """
        )

        # --- NEW: chat_log (group/user conversations) ---
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INT NOT NULL,
                chat_type TEXT,       -- private|group|supergroup|channel
                user_id INT,
                user_name TEXT,
                message TEXT NOT NULL,
                role TEXT NOT NULL,   -- user|assistant|system
                game_slug TEXT,       -- optional tagged game for inference
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        self.conn.commit()


    def create_game(self, name: str, store_dir: str, status: str = "created", description: Optional[str] = None):
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO games (name, description, status, store_dir)
            VALUES (?, ?, ?, ?, ?)
            """,
            (name, description, status, store_dir),
        )
        self.conn.commit()

    def get_game_by_name(self, name: str) -> Optional[Dict]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM games WHERE lower(name) = lower(?)", (name,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def list_games(self) -> List[Dict]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM games ORDER BY name COLLATE NOCASE ASC")
        return [dict(r) for r in cursor.fetchall()]

    def update_game_status(self, slug: str, status: str):
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE games SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE slug = ?",
            (status, slug),
        )
        self.conn.commit()

    def update_game_timestamps(self, slug: str):
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE games SET last_researched_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE slug = ?",
            (slug,),
        )
        self.conn.commit()

    def add_game_source(self, game_id: int, source_type: str, url: str, title: str, local_path: Optional[str]):
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO game_sources (game_id, source_type, url, title, local_path)
            VALUES (?, ?, ?, ?, ?)
            """,
            (int(game_id), str(source_type), str(url) if url else None, str(title) if title else None, str(local_path) if local_path else None),
        )
        self.conn.commit()

    # ------------------------------
    # NEW: Chat Log Operations
    # ------------------------------
    def add_chat_message(self, chat_id: int, chat_type: str, user_id: Optional[int], user_name: Optional[str],
                         message: str, role: str, game_slug: Optional[str] = None):
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO chat_log (chat_id, chat_type, user_id, user_name, message, role, game_slug)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (int(chat_id), str(chat_type) if chat_type else None,
             int(user_id) if user_id is not None else None,
             str(user_name) if user_name else None,
             str(message), str(role), str(game_slug) if game_slug else None),
        )
        self.conn.commit()

    def get_recent_chat(self, chat_id: int, limit: int = 50) -> List[Dict]:
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT * FROM chat_log WHERE chat_id = ?
            ORDER BY id DESC LIMIT ?
            """,
            (int(chat_id), int(limit)),
        )
        return [dict(r) for r in cursor.fetchall()][::-1]

    def find_recent_game_for_chat(self, chat_id: int) -> Optional[Dict]:
        """
        Finds the most recently referenced/answered game in this chat by scanning logged messages for known game slugs.
        Preference order: explicit game_slug tag -> name match in text
        """
        # First try explicit game_slug tags
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT g.* FROM chat_log c
            JOIN games g ON g.slug = c.game_slug
            WHERE c.chat_id = ? AND c.game_slug IS NOT NULL
            ORDER BY c.id DESC LIMIT 1
            """,
            (int(chat_id),),
        )
        row = cursor.fetchone()
        if row:
            return dict(row)

        # Otherwise heuristics: scan messages for known game names (last 200 msgs)
        msgs = self.get_recent_chat(chat_id, limit=200)
        games = self.list_games()
        names = [(g["name"], g["slug"]) for g in games]
        for m in reversed(msgs):
            text = m["message"]
            for name, slug in sorted(names, key=lambda x: len(x[0]), reverse=True):
                if re.search(r"\b" + re.escape(name) + r"\b", text, flags=sqlite3.re.IGNORECASE):
                    return self.get_game_by_slug(slug)
        return None


    def close(self):
        self.conn.close()
