import pytest
from fastapi.testclient import TestClient

from app.auth import create_access_token, decode_access_token


def test_register_creates_user(client: TestClient) -> None:
    response = client.post("/auth/register", json={"username": "alice", "password": "secret123"})
    assert response.status_code == 201
    data = response.json()
    assert data["username"] == "alice"
    assert "id" in data
    assert "password" not in data
    assert "hashed_password" not in data


def test_register_duplicate_username_returns_409(client: TestClient) -> None:
    client.post("/auth/register", json={"username": "bob", "password": "secret123"})
    response = client.post("/auth/register", json={"username": "bob", "password": "different"})
    assert response.status_code == 409


def test_register_response_does_not_include_password_hash(client: TestClient) -> None:
    response = client.post("/auth/register", json={"username": "charlie", "password": "secret123"})
    assert response.status_code == 201
    data = response.json()
    assert "hashed_password" not in data
    assert "password" not in data


def test_password_is_hashed_in_database(client: TestClient) -> None:
    client.post("/auth/register", json={"username": "dave", "password": "plainpassword"})
    from tests.conftest import TestSessionLocal
    from app.models import User
    db = TestSessionLocal()
    user = db.query(User).filter(User.username == "dave").first()
    db.close()
    assert user is not None
    assert user.hashed_password != "plainpassword"
    assert len(user.hashed_password) > 32  # bcrypt hash length


# BL-0003 tests

def test_login_returns_jwt_with_sub(client: TestClient) -> None:
    client.post("/auth/register", json={"username": "loginuser", "password": "secret123"})
    response = client.post("/auth/login", json={"username": "loginuser", "password": "secret123"})
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    payload = decode_access_token(data["access_token"])
    assert payload is not None
    assert payload.get("sub") == "loginuser"


def test_login_invalid_credentials_returns_401(client: TestClient) -> None:
    client.post("/auth/register", json={"username": "wrongpass", "password": "secret123"})
    response = client.post("/auth/login", json={"username": "wrongpass", "password": "badpassword"})
    assert response.status_code == 401


def test_login_nonexistent_user_returns_401(client: TestClient) -> None:
    response = client.post("/auth/login", json={"username": "nouser", "password": "secret123"})
    assert response.status_code == 401


def test_protected_endpoint_rejects_missing_token(client: TestClient) -> None:
    response = client.get("/me")
    assert response.status_code == 401


def test_protected_endpoint_rejects_invalid_token(client: TestClient) -> None:
    response = client.get("/me", headers={"Authorization": "Bearer invalidtoken"})
    assert response.status_code == 401


def test_protected_endpoint_accepts_valid_token(client: TestClient) -> None:
    client.post("/auth/register", json={"username": "tokenuser", "password": "secret123"})
    login_resp = client.post("/auth/login", json={"username": "tokenuser", "password": "secret123"})
    token = login_resp.json()["access_token"]
    response = client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["username"] == "tokenuser"


def test_token_expiration_is_enforced(client: TestClient) -> None:
    from datetime import timedelta
    token = create_access_token(data={"sub": "expuser"}, expires_delta=timedelta(seconds=-1))
    response = client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
