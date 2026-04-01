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

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS sql_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            question TEXT,
            sql_query TEXT,
            summary TEXT,
            result_type TEXT,
            row_count INTEGER,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # -------------------- MIGRATIONS --------------------
        # Add standalone_question to messages table if not exists
        try:
            cursor.execute("ALTER TABLE messages ADD COLUMN standalone_question TEXT")
        except sqlite3.OperationalError:
            pass  # Column already exists

        # Add standalone_question to sql_messages table if not exists
        try:
            cursor.execute("ALTER TABLE sql_messages ADD COLUMN standalone_question TEXT")
        except sqlite3.OperationalError:
            pass  # Column already exists


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
        return "not_found"
    if not verify_password(password, user[2]):
        return "wrong_password"
    return user


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


def save_message(user_id, session_id, role, content, standalone_question=None):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO messages (user_id, session_id, role, content, standalone_question)
            VALUES (?, ?, ?, ?, ?)""",
            (user_id, session_id, role, content, standalone_question)
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


def get_last_standalone_question(user_id, session_id) -> str:
    """
    ✅ NEW: Fetch the most recent standalone_question for a user+session
    from the messages table (user role only).
    Used for chaining context-dependent questions.
    Returns empty string if none found.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """SELECT standalone_question FROM messages
            WHERE user_id=? AND session_id=? AND role='user'
            AND standalone_question IS NOT NULL
            ORDER BY id DESC LIMIT 1""",
            (user_id, session_id)
        )
        row = cursor.fetchone()
    return row[0] if row else ""


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


# -------------------- NL2SQL HISTORY --------------------
def save_sql_message(user_id, question, sql_query, summary, result_type, row_count, standalone_question=None):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO sql_messages
            (user_id, question, sql_query, summary, result_type, row_count, standalone_question)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (user_id, question, sql_query, summary, result_type, row_count, standalone_question)
        )


def get_sql_history(user_id):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """SELECT question, sql_query, summary, result_type, row_count, timestamp, standalone_question
            FROM sql_messages WHERE user_id=?
            ORDER BY id DESC LIMIT 20""",
            (user_id,)
        )
        rows = cursor.fetchall()
    return [
        {
            "question": r[0],
            "sql_query": r[1],
            "summary": r[2],
            "result_type": r[3],
            "row_count": r[4],
            "timestamp": r[5],
            "standalone_question": r[6]
        }
        for r in rows
    ]