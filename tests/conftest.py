# tests/conftest.py
import pytest
import requests

BASE_URL = "http://127.0.0.1:8000"

# -------------------- TEST USER --------------------
TEST_USERNAME = "pytest_test_user"
TEST_PASSWORD = "pytest_test_pass123"


@pytest.fixture(scope="session")
def base_url():
    """Base URL for all API calls"""
    return BASE_URL


@pytest.fixture(scope="session")
def register_test_user():
    """Register test user once for entire test session"""
    res = requests.post(f"{BASE_URL}/register", json={
        "username": TEST_USERNAME,
        "password": TEST_PASSWORD
    })
    # 200 = registered, 400 = already exists — both are fine
    assert res.status_code in [200, 400]
    return TEST_USERNAME


@pytest.fixture(scope="session")
def auth_token(register_test_user):
    """Login and get token once for entire test session"""
    res = requests.post(f"{BASE_URL}/login", json={
        "username": TEST_USERNAME,
        "password": TEST_PASSWORD
    })
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    return data["access_token"]


@pytest.fixture(scope="session")
def auth_headers(auth_token):
    """Auth headers for all API calls"""
    return {"Authorization": f"Bearer {auth_token}"}


@pytest.fixture(scope="session")
def test_session_id(auth_headers):
    """Create one test session for entire test session"""
    res = requests.post(
        f"{BASE_URL}/create_chat",
        headers=auth_headers
    )
    assert res.status_code == 200
    data = res.json()
    assert "session_id" in data
    return data["session_id"]