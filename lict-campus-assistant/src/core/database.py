"""
db.py — SQLite persistence layer for the Hybrid AI Chatbot.

Schema:
    users          (id, username, display_name, password_hash, created_at)
    conversations  (id, user_id, title, created_at, updated_at)
    messages       (id, conversation_id, role, content, source, score,
                     image_url, blocked, created_at)

Passwords are hashed with bcrypt — never stored or compared in plaintext.
"""

import sqlite3
import bcrypt
import time
from contextlib import contextmanager

import os as _os
DB_PATH = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))), "data", "chatbot.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


@contextmanager
def db_cursor():
    conn = get_connection()
    try:
        cur = conn.cursor()
        yield cur
        conn.commit()
    finally:
        conn.close()


def init_db():
    with db_cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                display_name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                failed_attempts INTEGER NOT NULL DEFAULT 0,
                locked_until REAL,
                created_at REAL NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL DEFAULT 'New chat',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER NOT NULL,
                role TEXT NOT NULL,            -- 'user' or 'assistant'
                content TEXT NOT NULL,
                source TEXT,                   -- 'Knowledge Base' / 'Web Search' / 'Image Search' / 'Blocked' / NULL
                score REAL,
                image_url TEXT,                -- set when source = 'Image Search'
                fetched_url TEXT,               -- set when source = 'Web Fetch'
                blocked INTEGER NOT NULL DEFAULT 0,
                created_at REAL NOT NULL,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS conversation_summaries (
                conversation_id INTEGER PRIMARY KEY,
                summary TEXT NOT NULL,
                message_count_at_summary INTEGER NOT NULL DEFAULT 0,
                updated_at REAL NOT NULL,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            )
            """
        )

        # Lightweight migration for DBs created by an older version of this schema.
        existing_cols = {row["name"] for row in cur.execute("PRAGMA table_info(messages)").fetchall()}
        if "image_url" not in existing_cols:
            cur.execute("ALTER TABLE messages ADD COLUMN image_url TEXT")
        if "fetched_url" not in existing_cols:
            cur.execute("ALTER TABLE messages ADD COLUMN fetched_url TEXT")
        if "blocked" not in existing_cols:
            cur.execute("ALTER TABLE messages ADD COLUMN blocked INTEGER NOT NULL DEFAULT 0")

        existing_user_cols = {row["name"] for row in cur.execute("PRAGMA table_info(users)").fetchall()}
        if "failed_attempts" not in existing_user_cols:
            cur.execute("ALTER TABLE users ADD COLUMN failed_attempts INTEGER NOT NULL DEFAULT 0")
        if "locked_until" not in existing_user_cols:
            cur.execute("ALTER TABLE users ADD COLUMN locked_until REAL")


# ---------------------------------------------------------------------------
# USERS
# ---------------------------------------------------------------------------

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_SECONDS = 5 * 60  # 5 minutes


def create_user(username: str, display_name: str, password: str):
    """Returns (success: bool, message: str)."""
    username = username.strip().lower()
    if not username or not password:
        return False, "Username and password are required."
    if len(password) < 6:
        return False, "Password must be at least 6 characters."
    if username == password.lower():
        return False, "Password cannot be the same as your username."

    pw_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    try:
        with db_cursor() as cur:
            cur.execute(
                "INSERT INTO users (username, display_name, password_hash, created_at) VALUES (?, ?, ?, ?)",
                (username, display_name.strip() or username, pw_hash, time.time()),
            )
        return True, "Account created successfully."
    except sqlite3.IntegrityError:
        return False, "That username is already taken."


def verify_user(username: str, password: str):
    """Returns (user dict | None, message: str).

    Implements a simple brute-force lockout: after MAX_FAILED_ATTEMPTS
    consecutive bad passwords, the account is locked for LOCKOUT_SECONDS.
    """
    username = username.strip().lower()
    with db_cursor() as cur:
        cur.execute("SELECT * FROM users WHERE username = ?", (username,))
        row = cur.fetchone()

    if row is None:
        return None, "Invalid username or password."

    now = time.time()
    if row["locked_until"] and row["locked_until"] > now:
        remaining = int(row["locked_until"] - now)
        return None, f"Account temporarily locked due to repeated failed logins. Try again in {remaining}s."

    if bcrypt.checkpw(password.encode("utf-8"), row["password_hash"].encode("utf-8")):
        with db_cursor() as cur:
            cur.execute(
                "UPDATE users SET failed_attempts = 0, locked_until = NULL WHERE id = ?",
                (row["id"],),
            )
        return dict(row), "OK"

    new_attempts = row["failed_attempts"] + 1
    locked_until = now + LOCKOUT_SECONDS if new_attempts >= MAX_FAILED_ATTEMPTS else None
    with db_cursor() as cur:
        cur.execute(
            "UPDATE users SET failed_attempts = ?, locked_until = ? WHERE id = ?",
            (new_attempts, locked_until, row["id"]),
        )

    if locked_until:
        return None, f"Too many failed attempts. Account locked for {LOCKOUT_SECONDS // 60} minutes."
    return None, "Invalid username or password."


def get_user_by_id(user_id: int):
    with db_cursor() as cur:
        cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = cur.fetchone()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# CONVERSATIONS
# ---------------------------------------------------------------------------

def create_conversation(user_id: int, title: str = "New chat"):
    now = time.time()
    with db_cursor() as cur:
        cur.execute(
            "INSERT INTO conversations (user_id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (user_id, title, now, now),
        )
        return cur.lastrowid


def list_conversations(user_id: int):
    with db_cursor() as cur:
        cur.execute(
            "SELECT * FROM conversations WHERE user_id = ? ORDER BY updated_at DESC",
            (user_id,),
        )
        return [dict(r) for r in cur.fetchall()]


def get_conversation(conversation_id: int):
    with db_cursor() as cur:
        cur.execute("SELECT * FROM conversations WHERE id = ?", (conversation_id,))
        row = cur.fetchone()
    return dict(row) if row else None


def rename_conversation(conversation_id: int, title: str):
    with db_cursor() as cur:
        cur.execute(
            "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
            (title, time.time(), conversation_id),
        )


def touch_conversation(conversation_id: int):
    with db_cursor() as cur:
        cur.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (time.time(), conversation_id),
        )


def delete_conversation(conversation_id: int):
    with db_cursor() as cur:
        cur.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))


# ---------------------------------------------------------------------------
# MESSAGES
# ---------------------------------------------------------------------------

def add_message(conversation_id: int, role: str, content: str, source: str = None,
                 score: float = None, image_url: str = None, fetched_url: str = None,
                 blocked: bool = False):
    with db_cursor() as cur:
        cur.execute(
            """INSERT INTO messages (conversation_id, role, content, source, score,
                                      image_url, fetched_url, blocked, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (conversation_id, role, content, source, score, image_url, fetched_url, int(blocked), time.time()),
        )
    touch_conversation(conversation_id)


def get_messages(conversation_id: int):
    with db_cursor() as cur:
        cur.execute(
            "SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at ASC",
            (conversation_id,),
        )
        return [dict(r) for r in cur.fetchall()]


def get_message_count(conversation_id: int) -> int:
    with db_cursor() as cur:
        cur.execute("SELECT COUNT(*) as c FROM messages WHERE conversation_id = ?", (conversation_id,))
        return cur.fetchone()["c"]


# ---------------------------------------------------------------------------
# CONVERSATION SUMMARIES
#
# Long chats get auto-summarized (see app.py's SUMMARY_TRIGGER_EVERY) so that:
#   1. Returning users get a quick "here's what we covered" recap instead of
#      re-reading a huge thread.
#   2. The RAG pipeline can use the summary instead of the full raw history
#      as long-term context, keeping prompts small even in long chats.
# ---------------------------------------------------------------------------

def get_summary(conversation_id: int):
    """Returns {'summary': str, 'message_count_at_summary': int, 'updated_at': float} or None."""
    with db_cursor() as cur:
        cur.execute(
            "SELECT * FROM conversation_summaries WHERE conversation_id = ?",
            (conversation_id,),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def upsert_summary(conversation_id: int, summary: str, message_count_at_summary: int):
    with db_cursor() as cur:
        cur.execute(
            """
            INSERT INTO conversation_summaries (conversation_id, summary, message_count_at_summary, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(conversation_id) DO UPDATE SET
                summary = excluded.summary,
                message_count_at_summary = excluded.message_count_at_summary,
                updated_at = excluded.updated_at
            """,
            (conversation_id, summary, message_count_at_summary, time.time()),
        )


def delete_summary(conversation_id: int):
    with db_cursor() as cur:
        cur.execute("DELETE FROM conversation_summaries WHERE conversation_id = ?", (conversation_id,))