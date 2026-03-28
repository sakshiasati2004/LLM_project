import sqlite3
import os
from backend.auth import hash_password, verify_password

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "chat.db")


def get_connection():
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def create_tables():
    conn = get_connection()
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

    conn.commit()
    conn.close()


# AUTH
def register_user(username, password):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO users (username, password) VALUES (?, ?)",
            (username, hash_password(password))
        )
        conn.commit()
        return True
    except:
        return False
    finally:
        conn.close()


def login_user(username, password):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM users WHERE username=?", (username,))
    user = cursor.fetchone()
    conn.close()

    if user and verify_password(password, user[2]):
        return user
    return None


# SESSION SECURITY CHECK
def verify_session_ownership(session_id, user_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id FROM chat_sessions WHERE id=? AND user_id=?",
        (session_id, user_id)
    )

    result = cursor.fetchone()
    conn.close()
    return result is not None


def create_chat_session(user_id, title="New Chat"):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO chat_sessions (user_id, title) VALUES (?, ?)",
        (user_id, title)
    )

    conn.commit()
    session_id = cursor.lastrowid
    conn.close()
    return session_id


def get_user_sessions(user_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id, title FROM chat_sessions WHERE user_id=? ORDER BY id DESC",
        (user_id,)
    )

    rows = cursor.fetchall()
    conn.close()
    return [{"id": r[0], "title": r[1]} for r in rows]


def save_message(user_id, session_id, role, content):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO messages (user_id, session_id, role, content) VALUES (?, ?, ?, ?)",
        (user_id, session_id, role, content)
    )

    conn.commit()
    conn.close()


def get_chat_history(user_id, session_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT role, content FROM messages
    WHERE user_id=? AND session_id=?
    ORDER BY id ASC
    """, (user_id, session_id))

    rows = cursor.fetchall()
    conn.close()

    return [{"role": r[0], "content": r[1]} for r in rows[-10:]]  # limit memory


def rename_session(session_id, new_title):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "UPDATE chat_sessions SET title=? WHERE id=?",
        (new_title, session_id)
    )

    conn.commit()
    conn.close()


def delete_session(session_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM messages WHERE session_id=?", (session_id,))
    cursor.execute("DELETE FROM chat_sessions WHERE id=?", (session_id,))

    conn.commit()
    conn.close()