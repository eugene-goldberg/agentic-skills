from pathlib import Path
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.main import app


def main() -> int:
    import uuid

    client = TestClient(app)
    username = f"verify_{uuid.uuid4().hex[:8]}"
    password = "secret123"

    register = client.post("/auth/register", json={"username": username, "password": password})
    assert register.status_code == 201, register.text
    register_data = register.json()
    assert register_data["username"] == username
    assert "password" not in register_data
    assert "hashed_password" not in register_data

    duplicate = client.post("/auth/register", json={"username": username, "password": password})
    assert duplicate.status_code == 409, duplicate.text

    invalid_login = client.post("/auth/login", json={"username": username, "password": "wrongpass"})
    assert invalid_login.status_code == 401, invalid_login.text

    login = client.post("/auth/login", json={"username": username, "password": password})
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]

    unauthenticated = client.get("/me")
    assert unauthenticated.status_code == 401, unauthenticated.text

    me = client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200, me.text
    assert me.json()["username"] == username

    print("BL-0001 verification passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
