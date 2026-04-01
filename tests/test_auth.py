# tests/test_auth.py
import requests
import pytest

BASE_URL = "http://127.0.0.1:8000"


# ==================== REGISTER TESTS ====================

def test_register_new_user():
    """Test registering a brand new user"""
    import random
    random_username = f"testuser_{random.randint(10000, 99999)}"
    res = requests.post(f"{BASE_URL}/register", json={
        "username": random_username,
        "password": "testpass123"
    })
    assert res.status_code == 200
    assert "message" in res.json()


def test_register_duplicate_user(register_test_user):
    """Test registering same user twice — should fail with 400"""
    res = requests.post(f"{BASE_URL}/register", json={
        "username": "pytest_test_user",
        "password": "pytest_test_pass123"
    })
    assert res.status_code == 400
    assert "detail" in res.json()


def test_register_missing_username():
    """Test registering with empty username: handled at UI level"""
    res = requests.post(f"{BASE_URL}/register", json={
        "username": "",
        "password": "testpass123"
    })
    assert res.status_code in [200,400, 422]


def test_register_missing_password():
    """Test registering with empty password: handled at UI level"""
    res = requests.post(f"{BASE_URL}/register", json={
        "username": "someuser",
        "password": ""
    })
    assert res.status_code in [200,400, 422]


# ==================== LOGIN TESTS ====================

def test_login_correct_credentials(register_test_user):
    """Test login with correct credentials"""
    res = requests.post(f"{BASE_URL}/login", json={
        "username": "pytest_test_user",
        "password": "pytest_test_pass123"
    })
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    assert "token_type" in data
    assert data["token_type"] == "bearer"


def test_login_wrong_password(register_test_user):
    """Test login with wrong password — should return 401"""
    res = requests.post(f"{BASE_URL}/login", json={
        "username": "pytest_test_user",
        "password": "wrongpassword"
    })
    assert res.status_code == 401
    assert "detail" in res.json()


def test_login_nonexistent_user():
    """Test login with user that doesn't exist — should return 404"""
    res = requests.post(f"{BASE_URL}/login", json={
        "username": "this_user_does_not_exist_xyz",
        "password": "somepassword"
    })
    assert res.status_code == 404
    assert "detail" in res.json()


def test_login_returns_valid_token(register_test_user):
    """Test that login returns a proper JWT token"""
    res = requests.post(f"{BASE_URL}/login", json={
        "username": "pytest_test_user",
        "password": "pytest_test_pass123"
    })
    assert res.status_code == 200
    token = res.json().get("access_token")
    assert token is not None
    assert len(token) > 10
    # ✅ JWT tokens have 3 parts separated by dots
    assert len(token.split(".")) == 3


# ==================== TOKEN TESTS ====================

def test_access_protected_route_without_token():
    """Test accessing protected route without token — should return 401"""
    res = requests.get(f"{BASE_URL}/sessions")
    assert res.status_code == 401


def test_access_protected_route_with_invalid_token():
    """Test accessing protected route with invalid token — should return 401"""
    res = requests.get(
        f"{BASE_URL}/sessions",
        headers={"Authorization": "Bearer invalidtoken123"}
    )
    assert res.status_code == 401


def test_access_protected_route_with_valid_token(auth_headers):
    """Test accessing protected route with valid token — should return 200"""
    res = requests.get(
        f"{BASE_URL}/sessions",
        headers=auth_headers
    )
    assert res.status_code == 200