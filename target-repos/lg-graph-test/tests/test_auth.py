from app.security import decode_access_token


def test_register_returns_identity_without_password_fields(client) -> None:
    response = client.post("/auth/register", json={"username": "alice", "password": "secret123"})

    assert response.status_code == 201
    data = response.json()
    assert data["username"] == "alice"
    assert "id" in data
    assert "password" not in data
    assert "hashed_password" not in data


def test_duplicate_username_returns_client_error(client) -> None:
    client.post("/auth/register", json={"username": "bob", "password": "secret123"})

    response = client.post("/auth/register", json={"username": "bob", "password": "anotherpass"})

    assert response.status_code == 409


def test_registration_persists_hashed_password_for_later_authentication(client, db_session) -> None:
    client.post("/auth/register", json={"username": "dave", "password": "plainpassword"})

    from app.models import User

    user = db_session.query(User).filter(User.username == "dave").first()

    assert user is not None
    assert user.hashed_password != "plainpassword"
    assert ":" in user.hashed_password


def test_login_returns_bearer_token(client) -> None:
    client.post("/auth/register", json={"username": "loginuser", "password": "secret123"})

    response = client.post("/auth/login", json={"username": "loginuser", "password": "secret123"})

    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    payload = decode_access_token(data["access_token"])
    assert payload is not None
    assert payload["sub"] == "loginuser"


def test_login_invalid_password_returns_401(client) -> None:
    client.post("/auth/register", json={"username": "carol", "password": "secret123"})

    response = client.post("/auth/login", json={"username": "carol", "password": "wrongpass"})

    assert response.status_code == 401


def test_login_nonexistent_user_returns_401(client) -> None:
    response = client.post("/auth/login", json={"username": "nouser", "password": "secret123"})

    assert response.status_code == 401


def test_protected_endpoint_rejects_missing_token(client) -> None:
    response = client.get("/me")

    assert response.status_code == 401


def test_protected_endpoint_rejects_invalid_token(client) -> None:
    response = client.get("/me", headers={"Authorization": "Bearer invalidtoken"})

    assert response.status_code == 401


def test_protected_endpoint_accepts_valid_token(client) -> None:
    client.post("/auth/register", json={"username": "tokenuser", "password": "secret123"})
    login_resp = client.post("/auth/login", json={"username": "tokenuser", "password": "secret123"})
    token = login_resp.json()["access_token"]

    response = client.get("/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json()["username"] == "tokenuser"
    assert "hashed_password" not in response.json()
