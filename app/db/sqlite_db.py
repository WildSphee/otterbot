import os
import sqlite3
import threading
from typing import Dict

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
        # Setting row_factory so fetch operations return dict-like rows
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self):
        cursor = self.conn.cursor()
        # Create user table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS user (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INT,
                user_name TEXT,
                preferred_name TEXT,
                page TEXT,
                model TEXT,
                tokens INT,
                date_joined DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        # Create generations table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS generations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INT,
                prompt TEXT,
                model TEXT,
                image_path TEXT,
                used_tokens INT,
                time_taken FLOAT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        # Create purchases table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS purchases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INT,
                tokens INT,
                environment TEXT,
                price_id,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self.conn.commit()

    # ------------------------------
    # User Table Operations
    # ------------------------------

    def add_user(
        self,
        user_id: int,
        user_name: str,
        preferred_name: str,
        page: str,
        model: str,
        tokens: int,
    ):
        """
        Inserts a new user into the user table.
        """
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT INTO user (user_id, user_name, preferred_name, page, model, tokens) VALUES (?, ?, ?, ?, ?, ?)",
            (
                int(user_id),
                str(user_name),
                str(preferred_name),
                str(page),
                str(model),
                int(tokens),
            ),
        )
        self.conn.commit()

    def update_user_page(self, user_id: int, new_page: str):
        """
        Updates the 'page' field for a given user_id.
        """
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE user SET page = ? WHERE user_id = ?", (new_page, int(user_id))
        )
        self.conn.commit()

    def update_user_model(self, user_id: int, new_model: str):
        """
        Updates the 'model' field for a given user_id.
        """
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE user SET model = ? WHERE user_id = ?", (new_model, int(user_id))
        )
        self.conn.commit()

    def get_user(self, user_id: int) -> Dict | None:
        """
        Retrieves a user record by user_id.
        Returns a dictionary if found, otherwise None.
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM user WHERE user_id = ?", (int(user_id),))
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None

    def update_user_tokens(self, user_id: int, delta: int):
        """
        Adds (or subtracts if delta is negative) tokens for a given user_id.
        """
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE user SET tokens = tokens + ? WHERE user_id = ?",
            (delta, int(user_id)),
        )
        self.conn.commit()

    # ------------------------------
    # Generations Table Operations
    # ------------------------------

    def add_generation_entry(
        self,
        user_id: int,
        prompt: str,
        model: str,
        image_path: str,
        used_tokens: int,
        time_taken: float,
    ):
        """
        Inserts a new entry into the generations table.
        """
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT INTO generations (user_id, prompt, model, image_path, used_tokens, time_taken) VALUES (?, ?, ?, ?, ?, ?)",
            (
                int(user_id),
                str(prompt),
                str(model),
                str(image_path),
                int(used_tokens),
                float(time_taken),
            ),
        )
        self.conn.commit()

    def get_generations_by_user(self, user_id: int):
        """
        Retrieves all generation entries for a given user_id.
        Returns a list of dictionaries.
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM generations WHERE user_id = ?", (int(user_id),))
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    # ------------------------------
    # Connection Management
    # ------------------------------

    def close(self):
        self.conn.close()
