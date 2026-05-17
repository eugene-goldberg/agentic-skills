from pathlib import Path
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main import app


def main() -> int:
    import uuid

    client = TestClient(app)
    username = f"smokeuser_{uuid.uuid4().hex[:8]}"
    password = "smokepass"

    r = client.get("/health")
    assert r.status_code == 200, f"/health failed: {r.status_code}"
    assert r.json().get("status") == "ok", f"/health unexpected payload: {r.json()}"
    print("PASS: /health")

    r = client.post("/auth/register", json={"username": username, "password": password})
    assert r.status_code == 201, f"/auth/register failed: {r.status_code} {r.text}"
    data = r.json()
    assert data.get("username") == username, f"unexpected username: {data}"
    assert "id" in data, "missing id in response"
    assert "password" not in data, "password leaked in response"
    assert "hashed_password" not in data, "hashed password leaked in response"
    print("PASS: /auth/register")

    r = client.post("/auth/register", json={"username": username, "password": password})
    assert r.status_code == 409, f"duplicate register expected 409, got {r.status_code}"
    print("PASS: duplicate username rejected")

    r = client.post("/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, f"/auth/login failed: {r.status_code} {r.text}"
    token = r.json().get("access_token")
    assert token, "missing access token"
    assert r.json().get("token_type") == "bearer", f"unexpected token type: {r.json()}"
    print("PASS: /auth/login")

    r = client.post("/auth/login", json={"username": username, "password": "wrongpass"})
    assert r.status_code == 401, f"invalid login expected 401, got {r.status_code}"
    print("PASS: invalid credentials rejected")

    r = client.get("/me")
    assert r.status_code == 401, f"/me without token expected 401, got {r.status_code}"
    print("PASS: /me rejects unauthenticated")

    r = client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, f"/me with token failed: {r.status_code} {r.text}"
    assert r.json().get("username") == username, f"unexpected /me payload: {r.json()}"
    print("PASS: /me accepts bearer token")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
