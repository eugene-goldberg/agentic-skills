import pytest
from fastapi.testclient import TestClient


def _register(client: TestClient, username: str, password: str = "secret123") -> dict:
    r = client.post("/auth/register", json={"username": username, "password": password})
    assert r.status_code == 201
    return r.json()


def _login(client: TestClient, username: str, password: str = "secret123") -> str:
    r = client.post("/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200
    return r.json()["access_token"]


def test_get_my_workspaces_returns_owned_workspaces(client: TestClient) -> None:
    user = _register(client, "meowner")
    token = _login(client, "meowner")

    r = client.post("/workspaces", json={"name": "Owned WS"}, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 201
    ws = r.json()

    r = client.get("/me/workspaces", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    ws_list = r.json()
    assert any(w["id"] == ws["id"] for w in ws_list)


def test_get_my_workspaces_returns_member_workspaces(client: TestClient) -> None:
    owner = _register(client, "memowner")
    member = _register(client, "memmember")
    owner_token = _login(client, "memowner")
    member_token = _login(client, "memmember")

    r = client.post("/workspaces", json={"name": "Member WS"}, headers={"Authorization": f"Bearer {owner_token}"})
    ws = r.json()

    # Invite member
    r = client.post(
        f"/workspaces/{ws['id']}/members",
        json={"id": member["id"], "username": member["username"]},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert r.status_code == 201

    # Member should see the workspace
    r = client.get("/me/workspaces", headers={"Authorization": f"Bearer {member_token}"})
    assert r.status_code == 200
    ws_list = r.json()
    assert any(w["id"] == ws["id"] for w in ws_list)


def test_get_my_workspaces_excludes_unrelated_workspaces(client: TestClient) -> None:
    owner = _register(client, "unrelatedowner")
    stranger = _register(client, "stranger")
    owner_token = _login(client, "unrelatedowner")
    stranger_token = _login(client, "stranger")

    r = client.post("/workspaces", json={"name": "Private WS"}, headers={"Authorization": f"Bearer {owner_token}"})
    ws = r.json()

    # Stranger should not see the workspace
    r = client.get("/me/workspaces", headers={"Authorization": f"Bearer {stranger_token}"})
    assert r.status_code == 200
    ws_list = r.json()
    assert not any(w["id"] == ws["id"] for w in ws_list)


def test_get_my_workspaces_unauthenticated_returns_401(client: TestClient) -> None:
    r = client.get("/me/workspaces")
    assert r.status_code == 401
