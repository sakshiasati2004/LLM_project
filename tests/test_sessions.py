# tests/test_sessions.py
import requests
import pytest

BASE_URL = "http://127.0.0.1:8000"


# ==================== CREATE SESSION TESTS ====================

def test_create_session(auth_headers):
    """Test creating a new chat session"""
    res = requests.post(
        f"{BASE_URL}/create_chat",
        headers=auth_headers
    )
    assert res.status_code == 200
    data = res.json()
    assert "session_id" in data
    assert isinstance(data["session_id"], int)


def test_create_multiple_sessions(auth_headers):
    """Test creating multiple sessions"""
    session_ids = []
    for _ in range(3):
        res = requests.post(
            f"{BASE_URL}/create_chat",
            headers=auth_headers
        )
        assert res.status_code == 200
        session_ids.append(res.json()["session_id"])

    # ✅ All session IDs should be unique
    assert len(set(session_ids)) == 3


def test_create_session_without_token():
    """Test creating session without token — should return 401"""
    res = requests.post(f"{BASE_URL}/create_chat")
    assert res.status_code == 401


# ==================== GET SESSIONS TESTS ====================

def test_get_sessions(auth_headers):
    """Test getting all sessions for a user"""
    res = requests.get(
        f"{BASE_URL}/sessions",
        headers=auth_headers
    )
    assert res.status_code == 200
    data = res.json()
    assert "sessions" in data
    assert isinstance(data["sessions"], list)


def test_get_sessions_returns_correct_format(auth_headers):
    """Test that sessions have correct format"""
    res = requests.get(
        f"{BASE_URL}/sessions",
        headers=auth_headers
    )
    assert res.status_code == 200
    sessions = res.json()["sessions"]

    if sessions:
        session = sessions[0]
        assert "id" in session
        assert "title" in session


def test_get_sessions_without_token():
    """Test getting sessions without token — should return 401"""
    res = requests.get(f"{BASE_URL}/sessions")
    assert res.status_code == 401


# ==================== RENAME SESSION TESTS ====================

def test_rename_session(auth_headers, test_session_id):
    """Test renaming a session"""
    res = requests.put(
        f"{BASE_URL}/rename_session",
        headers=auth_headers,
        json={
            "session_id": test_session_id,
            "title": "Renamed Test Session"
        }
    )
    assert res.status_code == 200
    assert "message" in res.json()


def test_rename_session_verify(auth_headers, test_session_id):
    """Test that rename actually updates the title"""
    new_title = "Updated Title For Verification"

    # ✅ Rename
    requests.put(
        f"{BASE_URL}/rename_session",
        headers=auth_headers,
        json={
            "session_id": test_session_id,
            "title": new_title
        }
    )

    # ✅ Verify
    res = requests.get(
        f"{BASE_URL}/sessions",
        headers=auth_headers
    )
    sessions = res.json()["sessions"]
    titles = [s["title"] for s in sessions]
    assert new_title in titles


def test_rename_session_unauthorized(auth_headers):
    """Test renaming a session that doesn't belong to user"""
    res = requests.put(
        f"{BASE_URL}/rename_session",
        headers=auth_headers,
        json={
            "session_id": 999999,
            "title": "Should Not Work"
        }
    )
    assert res.status_code == 403


def test_rename_session_without_token(test_session_id):
    """Test renaming session without token — should return 401"""
    res = requests.put(
        f"{BASE_URL}/rename_session",
        json={
            "session_id": test_session_id,
            "title": "No Token Title"
        }
    )
    assert res.status_code == 401


# ==================== DELETE SESSION TESTS ====================

def test_delete_session(auth_headers):
    """Test deleting a session"""
    # ✅ Create a new session to delete
    res = requests.post(
        f"{BASE_URL}/create_chat",
        headers=auth_headers
    )
    session_id = res.json()["session_id"]

    # ✅ Delete it
    res = requests.delete(
        f"{BASE_URL}/delete_session/{session_id}",
        headers=auth_headers
    )
    assert res.status_code == 200
    assert "message" in res.json()


def test_delete_session_verify(auth_headers):
    """Test that deleted session no longer appears in sessions list"""
    # ✅ Create a new session
    res = requests.post(
        f"{BASE_URL}/create_chat",
        headers=auth_headers
    )
    session_id = res.json()["session_id"]

    # ✅ Delete it
    requests.delete(
        f"{BASE_URL}/delete_session/{session_id}",
        headers=auth_headers
    )

    # ✅ Verify it's gone
    res = requests.get(
        f"{BASE_URL}/sessions",
        headers=auth_headers
    )
    session_ids = [s["id"] for s in res.json()["sessions"]]
    assert session_id not in session_ids


def test_delete_session_unauthorized(auth_headers):
    """Test deleting a session that doesn't belong to user"""
    res = requests.delete(
        f"{BASE_URL}/delete_session/999999",
        headers=auth_headers
    )
    assert res.status_code == 403


def test_delete_session_without_token(test_session_id):
    """Test deleting session without token — should return 401"""
    res = requests.delete(
        f"{BASE_URL}/delete_session/{test_session_id}"
    )
    assert res.status_code == 401


# ==================== CHAT HISTORY TESTS ====================

def test_get_chat_history(auth_headers, test_session_id):
    """Test getting chat history for a session"""
    res = requests.get(
        f"{BASE_URL}/history/{test_session_id}",
        headers=auth_headers
    )
    assert res.status_code == 200
    data = res.json()
    assert "messages" in data
    assert isinstance(data["messages"], list)


def test_get_chat_history_format(auth_headers, test_session_id):
    """Test that chat history messages have correct format"""
    # ✅ First send a message
    requests.post(
        f"{BASE_URL}/chat",
        headers=auth_headers,
        json={
            "session_id": test_session_id,
            "message": "Hello this is a test message",
            "selected_doc": "All Documents"
        }
    )

    # ✅ Then get history
    res = requests.get(
        f"{BASE_URL}/history/{test_session_id}",
        headers=auth_headers
    )
    messages = res.json()["messages"]

    if messages:
        msg = messages[0]
        assert "role" in msg
        assert "content" in msg
        assert msg["role"] in ["user", "assistant"]


def test_get_chat_history_unauthorized(auth_headers):
    """Test getting history for session that doesn't belong to user"""
    res = requests.get(
        f"{BASE_URL}/history/999999",
        headers=auth_headers
    )
    assert res.status_code == 403


def test_get_chat_history_without_token(test_session_id):
    """Test getting history without token — should return 401"""
    res = requests.get(
        f"{BASE_URL}/history/{test_session_id}"
    )
    assert res.status_code == 401