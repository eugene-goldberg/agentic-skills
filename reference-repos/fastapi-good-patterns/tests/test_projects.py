import pytest
from fastapi.testclient import TestClient

from app.models import Project


def _register(client: TestClient, username: str, password: str = "secret123") -> dict:
    r = client.post("/auth/register", json={"username": username, "password": password})
    assert r.status_code == 201
    return r.json()


def _login(client: TestClient, username: str, password: str = "secret123") -> str:
    r = client.post("/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200
    return r.json()["access_token"]


def _create_workspace(client: TestClient, token: str, name: str = "Test Workspace") -> dict:
    r = client.post("/workspaces", json={"name": name}, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 201
    return r.json()


# --- Acceptance 1: POST creates project; duplicate name -> 409 ---


def test_create_project_in_workspace(client: TestClient) -> None:
    user = _register(client, "projowner1")
    token = _login(client, "projowner1")
    ws = _create_workspace(client, token)

    r = client.post(
        f"/workspaces/{ws['id']}/projects",
        json={"name": "My Project"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201
    data = r.json()
    assert data["name"] == "My Project"
    assert data["workspace_id"] == ws["id"]
    assert "id" in data


def test_create_project_duplicate_name_returns_409(client: TestClient) -> None:
    user = _register(client, "projowner2")
    token = _login(client, "projowner2")
    ws = _create_workspace(client, token)

    r = client.post(
        f"/workspaces/{ws['id']}/projects",
        json={"name": "Dup Project"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201

    r = client.post(
        f"/workspaces/{ws['id']}/projects",
        json={"name": "Dup Project"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 409


def test_create_project_unauthenticated_returns_401(client: TestClient) -> None:
    user = _register(client, "projowner3")
    token = _login(client, "projowner3")
    ws = _create_workspace(client, token)

    r = client.post(
        f"/workspaces/{ws['id']}/projects",
        json={"name": "No Auth Project"},
    )
    assert r.status_code == 401


def test_create_project_nonmember_returns_404(client: TestClient) -> None:
    owner = _register(client, "projowner4")
    stranger = _register(client, "stranger4")
    owner_token = _login(client, "projowner4")
    stranger_token = _login(client, "stranger4")
    ws = _create_workspace(client, owner_token)

    r = client.post(
        f"/workspaces/{ws['id']}/projects",
        json={"name": "Secret Project"},
        headers={"Authorization": f"Bearer {stranger_token}"},
    )
    assert r.status_code == 404


# --- Acceptance 2: GET lists projects ---


def test_list_projects_in_workspace(client: TestClient) -> None:
    user = _register(client, "projowner5")
    token = _login(client, "projowner5")
    ws = _create_workspace(client, token)

    client.post(
        f"/workspaces/{ws['id']}/projects",
        json={"name": "Project A"},
        headers={"Authorization": f"Bearer {token}"},
    )
    client.post(
        f"/workspaces/{ws['id']}/projects",
        json={"name": "Project B"},
        headers={"Authorization": f"Bearer {token}"},
    )

    r = client.get(
        f"/workspaces/{ws['id']}/projects",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 2
    names = {p["name"] for p in data}
    assert names == {"Project A", "Project B"}


def test_list_projects_nonmember_returns_404(client: TestClient) -> None:
    owner = _register(client, "projowner6")
    stranger = _register(client, "stranger6")
    owner_token = _login(client, "projowner6")
    stranger_token = _login(client, "stranger6")
    ws = _create_workspace(client, owner_token)

    r = client.get(
        f"/workspaces/{ws['id']}/projects",
        headers={"Authorization": f"Bearer {stranger_token}"},
    )
    assert r.status_code == 404


def test_list_projects_unauthenticated_returns_401(client: TestClient) -> None:
    user = _register(client, "projowner7")
    token = _login(client, "projowner7")
    ws = _create_workspace(client, token)

    r = client.get(f"/workspaces/{ws['id']}/projects")
    assert r.status_code == 401


# --- Acceptance 3: GET single project ---


def test_get_project_returns_project(client: TestClient) -> None:
    user = _register(client, "projowner8")
    token = _login(client, "projowner8")
    ws = _create_workspace(client, token)

    r = client.post(
        f"/workspaces/{ws['id']}/projects",
        json={"name": "Single Project"},
        headers={"Authorization": f"Bearer {token}"},
    )
    project = r.json()

    r = client.get(
        f"/workspaces/{ws['id']}/projects/{project['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == project["id"]
    assert data["name"] == "Single Project"


def test_get_project_not_found_returns_404(client: TestClient) -> None:
    user = _register(client, "projowner9")
    token = _login(client, "projowner9")
    ws = _create_workspace(client, token)

    r = client.get(
        f"/workspaces/{ws['id']}/projects/99999",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 404


def test_get_project_nonmember_returns_404(client: TestClient) -> None:
    owner = _register(client, "projowner10")
    stranger = _register(client, "stranger10")
    owner_token = _login(client, "projowner10")
    stranger_token = _login(client, "stranger10")
    ws = _create_workspace(client, owner_token)

    r = client.post(
        f"/workspaces/{ws['id']}/projects",
        json={"name": "Secret Single"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    project = r.json()

    r = client.get(
        f"/workspaces/{ws['id']}/projects/{project['id']}",
        headers={"Authorization": f"Bearer {stranger_token}"},
    )
    assert r.status_code == 404


def test_get_project_unauthenticated_returns_401(client: TestClient) -> None:
    user = _register(client, "projowner11")
    token = _login(client, "projowner11")
    ws = _create_workspace(client, token)

    r = client.post(
        f"/workspaces/{ws['id']}/projects",
        json={"name": "Auth Test"},
        headers={"Authorization": f"Bearer {token}"},
    )
    project = r.json()

    r = client.get(f"/workspaces/{ws['id']}/projects/{project['id']}")
    assert r.status_code == 401


# --- Acceptance 4: PATCH updates project ---


def test_update_project_name(client: TestClient) -> None:
    user = _register(client, "projowner12")
    token = _login(client, "projowner12")
    ws = _create_workspace(client, token)

    r = client.post(
        f"/workspaces/{ws['id']}/projects",
        json={"name": "Old Name"},
        headers={"Authorization": f"Bearer {token}"},
    )
    project = r.json()

    r = client.patch(
        f"/workspaces/{ws['id']}/projects/{project['id']}",
        json={"name": "New Name"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["name"] == "New Name"
    assert data["id"] == project["id"]


def test_update_project_duplicate_name_returns_409(client: TestClient) -> None:
    user = _register(client, "projowner13")
    token = _login(client, "projowner13")
    ws = _create_workspace(client, token)

    client.post(
        f"/workspaces/{ws['id']}/projects",
        json={"name": "First Project"},
        headers={"Authorization": f"Bearer {token}"},
    )
    r = client.post(
        f"/workspaces/{ws['id']}/projects",
        json={"name": "Second Project"},
        headers={"Authorization": f"Bearer {token}"},
    )
    project2 = r.json()

    r = client.patch(
        f"/workspaces/{ws['id']}/projects/{project2['id']}",
        json={"name": "First Project"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 409


def test_update_project_not_found_returns_404(client: TestClient) -> None:
    user = _register(client, "projowner14")
    token = _login(client, "projowner14")
    ws = _create_workspace(client, token)

    r = client.patch(
        f"/workspaces/{ws['id']}/projects/99999",
        json={"name": "New Name"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 404


def test_update_project_nonmember_returns_404(client: TestClient) -> None:
    owner = _register(client, "projowner15")
    stranger = _register(client, "stranger15")
    owner_token = _login(client, "projowner15")
    stranger_token = _login(client, "stranger15")
    ws = _create_workspace(client, owner_token)

    r = client.post(
        f"/workspaces/{ws['id']}/projects",
        json={"name": "Update Secret"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    project = r.json()

    r = client.patch(
        f"/workspaces/{ws['id']}/projects/{project['id']}",
        json={"name": "Hacked"},
        headers={"Authorization": f"Bearer {stranger_token}"},
    )
    assert r.status_code == 404


def test_update_project_unauthenticated_returns_401(client: TestClient) -> None:
    user = _register(client, "projowner16")
    token = _login(client, "projowner16")
    ws = _create_workspace(client, token)

    r = client.post(
        f"/workspaces/{ws['id']}/projects",
        json={"name": "Auth Patch"},
        headers={"Authorization": f"Bearer {token}"},
    )
    project = r.json()

    r = client.patch(
        f"/workspaces/{ws['id']}/projects/{project['id']}",
        json={"name": "No Auth"},
    )
    assert r.status_code == 401


# --- Acceptance 5: DELETE project ---


def test_delete_project(client: TestClient) -> None:
    user = _register(client, "projowner17")
    token = _login(client, "projowner17")
    ws = _create_workspace(client, token)

    r = client.post(
        f"/workspaces/{ws['id']}/projects",
        json={"name": "To Delete"},
        headers={"Authorization": f"Bearer {token}"},
    )
    project = r.json()

    r = client.delete(
        f"/workspaces/{ws['id']}/projects/{project['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 204

    # Verify deleted
    r = client.get(
        f"/workspaces/{ws['id']}/projects/{project['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 404


def test_delete_project_not_found_returns_404(client: TestClient) -> None:
    user = _register(client, "projowner18")
    token = _login(client, "projowner18")
    ws = _create_workspace(client, token)

    r = client.delete(
        f"/workspaces/{ws['id']}/projects/99999",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 404


def test_delete_project_nonmember_returns_404(client: TestClient) -> None:
    owner = _register(client, "projowner19")
    stranger = _register(client, "stranger19")
    owner_token = _login(client, "projowner19")
    stranger_token = _login(client, "stranger19")
    ws = _create_workspace(client, owner_token)

    r = client.post(
        f"/workspaces/{ws['id']}/projects",
        json={"name": "Delete Secret"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    project = r.json()

    r = client.delete(
        f"/workspaces/{ws['id']}/projects/{project['id']}",
        headers={"Authorization": f"Bearer {stranger_token}"},
    )
    assert r.status_code == 404


def test_delete_project_unauthenticated_returns_401(client: TestClient) -> None:
    user = _register(client, "projowner20")
    token = _login(client, "projowner20")
    ws = _create_workspace(client, token)

    r = client.post(
        f"/workspaces/{ws['id']}/projects",
        json={"name": "Auth Delete"},
        headers={"Authorization": f"Bearer {token}"},
    )
    project = r.json()

    r = client.delete(f"/workspaces/{ws['id']}/projects/{project['id']}")
    assert r.status_code == 401


# --- Member can also CRUD projects ---


def test_member_can_create_project(client: TestClient) -> None:
    owner = _register(client, "projowner21")
    member = _register(client, "member21")
    owner_token = _login(client, "projowner21")
    member_token = _login(client, "member21")
    ws = _create_workspace(client, owner_token)

    # Invite member
    r = client.post(
        f"/workspaces/{ws['id']}/members",
        json={"username": member["username"]},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert r.status_code == 201

    # Member creates project
    r = client.post(
        f"/workspaces/{ws['id']}/projects",
        json={"name": "Member Project"},
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert r.status_code == 201
    assert r.json()["name"] == "Member Project"


def test_member_can_update_and_delete_project(client: TestClient) -> None:
    owner = _register(client, "projowner22")
    member = _register(client, "member22")
    owner_token = _login(client, "projowner22")
    member_token = _login(client, "member22")
    ws = _create_workspace(client, owner_token)

    # Invite member
    client.post(
        f"/workspaces/{ws['id']}/members",
        json={"username": member["username"]},
        headers={"Authorization": f"Bearer {owner_token}"},
    )

    # Owner creates project
    r = client.post(
        f"/workspaces/{ws['id']}/projects",
        json={"name": "Shared Project"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    project = r.json()

    # Member updates
    r = client.patch(
        f"/workspaces/{ws['id']}/projects/{project['id']}",
        json={"name": "Updated by Member"},
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert r.status_code == 200
    assert r.json()["name"] == "Updated by Member"

    # Member deletes
    r = client.delete(
        f"/workspaces/{ws['id']}/projects/{project['id']}",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert r.status_code == 204
