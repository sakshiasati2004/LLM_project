import sqlite3
import os
from contextlib import contextmanager
from backend.auth import hash_password, verify_password

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "chat.db")


@contextmanager
def get_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def create_tables():
    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            title TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            session_id INTEGER,
            role TEXT,
            content TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """)


# -------------------- AUTH --------------------
def register_user(username, password):
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO users (username, password) VALUES (?, ?)",
                (username, hash_password(password))
            )
        return True
    except sqlite3.IntegrityError:
        return False


def login_user(username, password):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username=?", (username,))
        user = cursor.fetchone()

    if not user:
        return "not_found"       # ✅ User doesn't exist
    if not verify_password(password, user[2]):
        return "wrong_password"  # ✅ Wrong password
    return user                  # ✅ Success


# -------------------- SESSION --------------------
def verify_session_ownership(session_id, user_id):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id FROM chat_sessions WHERE id=? AND user_id=?",
            (session_id, user_id)
        )
        result = cursor.fetchone()
    return result is not None


def create_chat_session(user_id, title="New Chat"):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO chat_sessions (user_id, title) VALUES (?, ?)",
            (user_id, title)
        )
        session_id = cursor.lastrowid
    return session_id


def get_user_sessions(user_id):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, title FROM chat_sessions WHERE user_id=? ORDER BY id DESC",
            (user_id,)
        )
        rows = cursor.fetchall()
    return [{"id": r[0], "title": r[1]} for r in rows]


def save_message(user_id, session_id, role, content):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO messages (user_id, session_id, role, content) VALUES (?, ?, ?, ?)",
            (user_id, session_id, role, content)
        )


def get_chat_history(user_id, session_id):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT role, content FROM (
            SELECT role, content, id FROM messages
            WHERE user_id=? AND session_id=?
            ORDER BY id DESC LIMIT 10
        ) ORDER BY id ASC
        """, (user_id, session_id))
        rows = cursor.fetchall()
    return [{"role": r[0], "content": r[1]} for r in rows]


def get_message_count(user_id, session_id):
    """Check if this is the first message in a session"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM messages WHERE user_id=? AND session_id=?",
            (user_id, session_id)
        )
        return cursor.fetchone()[0]


def rename_session(session_id, new_title, user_id):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE chat_sessions SET title=? WHERE id=? AND user_id=?",
            (new_title, session_id, user_id)
        )


def delete_session(session_id):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM messages WHERE session_id=?", (session_id,))
        cursor.execute("DELETE FROM chat_sessions WHERE id=?", (session_id,))