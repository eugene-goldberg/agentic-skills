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


def _create_workspace(client: TestClient, token: str, name: str = "Test Workspace") -> dict:
    r = client.post("/workspaces", json={"name": name}, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 201
    return r.json()


def _create_project(client: TestClient, token: str, workspace_id: int, name: str = "Test Project") -> dict:
    r = client.post(
        f"/workspaces/{workspace_id}/projects",
        json={"name": name},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201
    return r.json()


# --- Acceptance 1: POST creates task; missing title -> 422 ---


def test_create_task_in_project(client: TestClient) -> None:
    user = _register(client, "taskowner1")
    token = _login(client, "taskowner1")
    ws = _create_workspace(client, token)
    project = _create_project(client, token, ws["id"])

    r = client.post(
        f"/workspaces/{ws['id']}/projects/{project['id']}/tasks",
        json={"title": "My Task"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201
    data = r.json()
    assert data["title"] == "My Task"
    assert data["status"] == "todo"
    assert data["project_id"] == project["id"]
    assert "id" in data


def test_create_task_missing_title_returns_422(client: TestClient) -> None:
    user = _register(client, "taskowner2")
    token = _login(client, "taskowner2")
    ws = _create_workspace(client, token)
    project = _create_project(client, token, ws["id"])

    r = client.post(
        f"/workspaces/{ws['id']}/projects/{project['id']}/tasks",
        json={"description": "No title"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 422


def test_create_task_unauthenticated_returns_401(client: TestClient) -> None:
    user = _register(client, "taskowner3")
    token = _login(client, "taskowner3")
    ws = _create_workspace(client, token)
    project = _create_project(client, token, ws["id"])

    r = client.post(
        f"/workspaces/{ws['id']}/projects/{project['id']}/tasks",
        json={"title": "No Auth Task"},
    )
    assert r.status_code == 401


def test_create_task_nonmember_returns_404(client: TestClient) -> None:
    owner = _register(client, "taskowner4")
    stranger = _register(client, "stranger4")
    owner_token = _login(client, "taskowner4")
    stranger_token = _login(client, "stranger4")
    ws = _create_workspace(client, owner_token)
    project = _create_project(client, owner_token, ws["id"])

    r = client.post(
        f"/workspaces/{ws['id']}/projects/{project['id']}/tasks",
        json={"title": "Secret Task"},
        headers={"Authorization": f"Bearer {stranger_token}"},
    )
    assert r.status_code == 404


# --- Acceptance 2: GET lists tasks ---


def test_list_tasks_in_project(client: TestClient) -> None:
    user = _register(client, "taskowner5")
    token = _login(client, "taskowner5")
    ws = _create_workspace(client, token)
    project = _create_project(client, token, ws["id"])

    client.post(
        f"/workspaces/{ws['id']}/projects/{project['id']}/tasks",
        json={"title": "Task A"},
        headers={"Authorization": f"Bearer {token}"},
    )
    client.post(
        f"/workspaces/{ws['id']}/projects/{project['id']}/tasks",
        json={"title": "Task B"},
        headers={"Authorization": f"Bearer {token}"},
    )

    r = client.get(
        f"/workspaces/{ws['id']}/projects/{project['id']}/tasks",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 2
    titles = {t["title"] for t in data}
    assert titles == {"Task A", "Task B"}


def test_list_tasks_nonmember_returns_404(client: TestClient) -> None:
    owner = _register(client, "taskowner6")
    stranger = _register(client, "stranger6")
    owner_token = _login(client, "taskowner6")
    stranger_token = _login(client, "stranger6")
    ws = _create_workspace(client, owner_token)
    project = _create_project(client, owner_token, ws["id"])

    r = client.get(
        f"/workspaces/{ws['id']}/projects/{project['id']}/tasks",
        headers={"Authorization": f"Bearer {stranger_token}"},
    )
    assert r.status_code == 404


def test_list_tasks_unauthenticated_returns_401(client: TestClient) -> None:
    user = _register(client, "taskowner7")
    token = _login(client, "taskowner7")
    ws = _create_workspace(client, token)
    project = _create_project(client, token, ws["id"])

    r = client.get(f"/workspaces/{ws['id']}/projects/{project['id']}/tasks")
    assert r.status_code == 401


# --- Acceptance 3: GET single task ---


def test_get_task_returns_task(client: TestClient) -> None:
    user = _register(client, "taskowner8")
    token = _login(client, "taskowner8")
    ws = _create_workspace(client, token)
    project = _create_project(client, token, ws["id"])

    r = client.post(
        f"/workspaces/{ws['id']}/projects/{project['id']}/tasks",
        json={"title": "Single Task"},
        headers={"Authorization": f"Bearer {token}"},
    )
    task = r.json()

    r = client.get(
        f"/workspaces/{ws['id']}/projects/{project['id']}/tasks/{task['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == task["id"]
    assert data["title"] == "Single Task"


def test_get_task_not_found_returns_404(client: TestClient) -> None:
    user = _register(client, "taskowner9")
    token = _login(client, "taskowner9")
    ws = _create_workspace(client, token)
    project = _create_project(client, token, ws["id"])

    r = client.get(
        f"/workspaces/{ws['id']}/projects/{project['id']}/tasks/99999",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 404


def test_get_task_nonmember_returns_404(client: TestClient) -> None:
    owner = _register(client, "taskowner10")
    stranger = _register(client, "stranger10")
    owner_token = _login(client, "taskowner10")
    stranger_token = _login(client, "stranger10")
    ws = _create_workspace(client, owner_token)
    project = _create_project(client, owner_token, ws["id"])

    r = client.post(
        f"/workspaces/{ws['id']}/projects/{project['id']}/tasks",
        json={"title": "Secret Single"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    task = r.json()

    r = client.get(
        f"/workspaces/{ws['id']}/projects/{project['id']}/tasks/{task['id']}",
        headers={"Authorization": f"Bearer {stranger_token}"},
    )
    assert r.status_code == 404


def test_get_task_unauthenticated_returns_401(client: TestClient) -> None:
    user = _register(client, "taskowner11")
    token = _login(client, "taskowner11")
    ws = _create_workspace(client, token)
    project = _create_project(client, token, ws["id"])

    r = client.post(
        f"/workspaces/{ws['id']}/projects/{project['id']}/tasks",
        json={"title": "Auth Test"},
        headers={"Authorization": f"Bearer {token}"},
    )
    task = r.json()

    r = client.get(f"/workspaces/{ws['id']}/projects/{project['id']}/tasks/{task['id']}")
    assert r.status_code == 401


# --- Acceptance 4: PATCH updates task ---


def test_update_task_title(client: TestClient) -> None:
    user = _register(client, "taskowner12")
    token = _login(client, "taskowner12")
    ws = _create_workspace(client, token)
    project = _create_project(client, token, ws["id"])

    r = client.post(
        f"/workspaces/{ws['id']}/projects/{project['id']}/tasks",
        json={"title": "Old Title"},
        headers={"Authorization": f"Bearer {token}"},
    )
    task = r.json()

    r = client.patch(
        f"/workspaces/{ws['id']}/projects/{project['id']}/tasks/{task['id']}",
        json={"title": "New Title"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["title"] == "New Title"
    assert data["id"] == task["id"]


def test_update_task_status(client: TestClient) -> None:
    user = _register(client, "taskowner13")
    token = _login(client, "taskowner13")
    ws = _create_workspace(client, token)
    project = _create_project(client, token, ws["id"])

    r = client.post(
        f"/workspaces/{ws['id']}/projects/{project['id']}/tasks",
        json={"title": "Status Task"},
        headers={"Authorization": f"Bearer {token}"},
    )
    task = r.json()
    assert task["status"] == "todo"

    r = client.patch(
        f"/workspaces/{ws['id']}/projects/{project['id']}/tasks/{task['id']}",
        json={"status": "in_progress"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "in_progress"


def test_update_task_invalid_status_returns_422(client: TestClient) -> None:
    user = _register(client, "taskowner14")
    token = _login(client, "taskowner14")
    ws = _create_workspace(client, token)
    project = _create_project(client, token, ws["id"])

    r = client.post(
        f"/workspaces/{ws['id']}/projects/{project['id']}/tasks",
        json={"title": "Invalid Status Task"},
        headers={"Authorization": f"Bearer {token}"},
    )
    task = r.json()

    r = client.patch(
        f"/workspaces/{ws['id']}/projects/{project['id']}/tasks/{task['id']}",
        json={"status": "invalid_status"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 422


def test_update_task_nonmember_returns_404(client: TestClient) -> None:
    owner = _register(client, "taskowner15")
    stranger = _register(client, "stranger15")
    owner_token = _login(client, "taskowner15")
    stranger_token = _login(client, "stranger15")
    ws = _create_workspace(client, owner_token)
    project = _create_project(client, owner_token, ws["id"])

    r = client.post(
        f"/workspaces/{ws['id']}/projects/{project['id']}/tasks",
        json={"title": "Secret Update"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    task = r.json()

    r = client.patch(
        f"/workspaces/{ws['id']}/projects/{project['id']}/tasks/{task['id']}",
        json={"title": "Hacked"},
        headers={"Authorization": f"Bearer {stranger_token}"},
    )
    assert r.status_code == 404


def test_update_task_unauthenticated_returns_401(client: TestClient) -> None:
    user = _register(client, "taskowner16")
    token = _login(client, "taskowner16")
    ws = _create_workspace(client, token)
    project = _create_project(client, token, ws["id"])

    r = client.post(
        f"/workspaces/{ws['id']}/projects/{project['id']}/tasks",
        json={"title": "Auth Update"},
        headers={"Authorization": f"Bearer {token}"},
    )
    task = r.json()

    r = client.patch(
        f"/workspaces/{ws['id']}/projects/{project['id']}/tasks/{task['id']}",
        json={"title": "Hacked"},
    )
    assert r.status_code == 401


# --- Acceptance 5: DELETE task ---


def test_delete_task(client: TestClient) -> None:
    user = _register(client, "taskowner17")
    token = _login(client, "taskowner17")
    ws = _create_workspace(client, token)
    project = _create_project(client, token, ws["id"])

    r = client.post(
        f"/workspaces/{ws['id']}/projects/{project['id']}/tasks",
        json={"title": "Delete Me"},
        headers={"Authorization": f"Bearer {token}"},
    )
    task = r.json()

    r = client.delete(
        f"/workspaces/{ws['id']}/projects/{project['id']}/tasks/{task['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 204

    r = client.get(
        f"/workspaces/{ws['id']}/projects/{project['id']}/tasks/{task['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 404


def test_delete_task_nonmember_returns_404(client: TestClient) -> None:
    owner = _register(client, "taskowner18")
    stranger = _register(client, "stranger18")
    owner_token = _login(client, "taskowner18")
    stranger_token = _login(client, "stranger18")
    ws = _create_workspace(client, owner_token)
    project = _create_project(client, owner_token, ws["id"])

    r = client.post(
        f"/workspaces/{ws['id']}/projects/{project['id']}/tasks",
        json={"title": "Secret Delete"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    task = r.json()

    r = client.delete(
        f"/workspaces/{ws['id']}/projects/{project['id']}/tasks/{task['id']}",
        headers={"Authorization": f"Bearer {stranger_token}"},
    )
    assert r.status_code == 404


def test_delete_task_unauthenticated_returns_401(client: TestClient) -> None:
    user = _register(client, "taskowner19")
    token = _login(client, "taskowner19")
    ws = _create_workspace(client, token)
    project = _create_project(client, token, ws["id"])

    r = client.post(
        f"/workspaces/{ws['id']}/projects/{project['id']}/tasks",
        json={"title": "Auth Delete"},
        headers={"Authorization": f"Bearer {token}"},
    )
    task = r.json()

    r = client.delete(f"/workspaces/{ws['id']}/projects/{project['id']}/tasks/{task['id']}")
    assert r.status_code == 401


# --- Acceptance 5: Task status defaults and validation ---


def test_create_task_with_status(client: TestClient) -> None:
    user = _register(client, "taskowner20")
    token = _login(client, "taskowner20")
    ws = _create_workspace(client, token)
    project = _create_project(client, token, ws["id"])

    r = client.post(
        f"/workspaces/{ws['id']}/projects/{project['id']}/tasks",
        json={"title": "Status Task", "status": "done"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201
    data = r.json()
    assert data["status"] == "done"


def test_create_task_invalid_status_returns_422(client: TestClient) -> None:
    user = _register(client, "taskowner21")
    token = _login(client, "taskowner21")
    ws = _create_workspace(client, token)
    project = _create_project(client, token, ws["id"])

    r = client.post(
        f"/workspaces/{ws['id']}/projects/{project['id']}/tasks",
        json={"title": "Bad Status", "status": "invalid"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 422


def test_create_task_default_status_is_todo(client: TestClient) -> None:
    user = _register(client, "taskowner22")
    token = _login(client, "taskowner22")
    ws = _create_workspace(client, token)
    project = _create_project(client, token, ws["id"])

    r = client.post(
        f"/workspaces/{ws['id']}/projects/{project['id']}/tasks",
        json={"title": "Default Status"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201
    data = r.json()
    assert data["status"] == "todo"


# --- Member can also CRUD tasks ---


def test_member_can_create_task(client: TestClient) -> None:
    owner = _register(client, "taskowner23")
    member = _register(client, "taskmember23")
    owner_token = _login(client, "taskowner23")
    member_token = _login(client, "taskmember23")
    ws = _create_workspace(client, owner_token)
    project = _create_project(client, owner_token, ws["id"])

    # Invite member
    r = client.post(
        f"/workspaces/{ws['id']}/members",
        json={"username": member["username"]},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert r.status_code == 201

    # Member creates task
    r = client.post(
        f"/workspaces/{ws['id']}/projects/{project['id']}/tasks",
        json={"title": "Member Task"},
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert r.status_code == 201
    data = r.json()
    assert data["title"] == "Member Task"


def test_member_can_update_task(client: TestClient) -> None:
    owner = _register(client, "taskowner24")
    member = _register(client, "taskmember24")
    owner_token = _login(client, "taskowner24")
    member_token = _login(client, "taskmember24")
    ws = _create_workspace(client, owner_token)
    project = _create_project(client, owner_token, ws["id"])

    # Invite member
    r = client.post(
        f"/workspaces/{ws['id']}/members",
        json={"username": member["username"]},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert r.status_code == 201

    # Owner creates task
    r = client.post(
        f"/workspaces/{ws['id']}/projects/{project['id']}/tasks",
        json={"title": "Owner Task"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    task = r.json()

    # Member updates task
    r = client.patch(
        f"/workspaces/{ws['id']}/projects/{project['id']}/tasks/{task['id']}",
        json={"title": "Member Updated"},
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["title"] == "Member Updated"


def test_member_can_delete_task(client: TestClient) -> None:
    owner = _register(client, "taskowner25")
    member = _register(client, "taskmember25")
    owner_token = _login(client, "taskowner25")
    member_token = _login(client, "taskmember25")
    ws = _create_workspace(client, owner_token)
    project = _create_project(client, owner_token, ws["id"])

    # Invite member
    r = client.post(
        f"/workspaces/{ws['id']}/members",
        json={"username": member["username"]},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert r.status_code == 201

    # Owner creates task
    r = client.post(
        f"/workspaces/{ws['id']}/projects/{project['id']}/tasks",
        json={"title": "Owner Task"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    task = r.json()

    # Member deletes task
    r = client.delete(
        f"/workspaces/{ws['id']}/projects/{project['id']}/tasks/{task['id']}",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert r.status_code == 204


# --- BL-0010: Task Assignment ---


def test_create_task_with_assignee(client: TestClient) -> None:
    owner = _register(client, "taskowner26")
    member = _register(client, "taskmember26")
    owner_token = _login(client, "taskowner26")
    member_token = _login(client, "taskmember26")
    ws = _create_workspace(client, owner_token)
    project = _create_project(client, owner_token, ws["id"])

    # Invite member
    r = client.post(
        f"/workspaces/{ws['id']}/members",
        json={"username": member["username"]},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert r.status_code == 201

    # Create task with assignee
    r = client.post(
        f"/workspaces/{ws['id']}/projects/{project['id']}/tasks",
        json={"title": "Assigned Task", "assignee_id": member["id"]},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert r.status_code == 201
    data = r.json()
    assert data["assignee_id"] == member["id"]


def test_create_task_with_non_member_assignee_returns_404(client: TestClient) -> None:
    owner = _register(client, "taskowner27")
    stranger = _register(client, "stranger27")
    owner_token = _login(client, "taskowner27")
    ws = _create_workspace(client, owner_token)
    project = _create_project(client, owner_token, ws["id"])

    # Try to assign to non-member
    r = client.post(
        f"/workspaces/{ws['id']}/projects/{project['id']}/tasks",
        json={"title": "Bad Assignee", "assignee_id": stranger["id"]},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert r.status_code == 404


def test_update_task_assignee(client: TestClient) -> None:
    owner = _register(client, "taskowner28")
    member = _register(client, "taskmember28")
    owner_token = _login(client, "taskowner28")
    member_token = _login(client, "taskmember28")
    ws = _create_workspace(client, owner_token)
    project = _create_project(client, owner_token, ws["id"])

    # Invite member
    r = client.post(
        f"/workspaces/{ws['id']}/members",
        json={"username": member["username"]},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert r.status_code == 201

    # Create task without assignee
    r = client.post(
        f"/workspaces/{ws['id']}/projects/{project['id']}/tasks",
        json={"title": "Unassigned Task"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    task = r.json()
    assert task["assignee_id"] is None

    # Update assignee
    r = client.patch(
        f"/workspaces/{ws['id']}/projects/{project['id']}/tasks/{task['id']}",
        json={"assignee_id": member["id"]},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["assignee_id"] == member["id"]


def test_update_task_clear_assignee(client: TestClient) -> None:
    owner = _register(client, "taskowner29")
    member = _register(client, "taskmember29")
    owner_token = _login(client, "taskowner29")
    member_token = _login(client, "taskmember29")
    ws = _create_workspace(client, owner_token)
    project = _create_project(client, owner_token, ws["id"])

    # Invite member
    r = client.post(
        f"/workspaces/{ws['id']}/members",
        json={"username": member["username"]},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert r.status_code == 201

    # Create task with assignee
    r = client.post(
        f"/workspaces/{ws['id']}/projects/{project['id']}/tasks",
        json={"title": "Assigned Task", "assignee_id": member["id"]},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    task = r.json()
    assert task["assignee_id"] == member["id"]

    # Clear assignee
    r = client.patch(
        f"/workspaces/{ws['id']}/projects/{project['id']}/tasks/{task['id']}",
        json={"assignee_id": None},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["assignee_id"] is None


def test_update_task_with_non_member_assignee_returns_404(client: TestClient) -> None:
    owner = _register(client, "taskowner30")
    stranger = _register(client, "stranger30")
    owner_token = _login(client, "taskowner30")
    ws = _create_workspace(client, owner_token)
    project = _create_project(client, owner_token, ws["id"])

    # Create task
    r = client.post(
        f"/workspaces/{ws['id']}/projects/{project['id']}/tasks",
        json={"title": "Task"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    task = r.json()

    # Try to assign to non-member
    r = client.patch(
        f"/workspaces/{ws['id']}/projects/{project['id']}/tasks/{task['id']}",
        json={"assignee_id": stranger["id"]},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert r.status_code == 404


def test_non_member_task_endpoints_return_404(client: TestClient) -> None:
    owner = _register(client, "taskowner31")
    stranger = _register(client, "stranger31")
    owner_token = _login(client, "taskowner31")
    stranger_token = _login(client, "stranger31")
    ws = _create_workspace(client, owner_token)
    project = _create_project(client, owner_token, ws["id"])

    # Create task
    r = client.post(
        f"/workspaces/{ws['id']}/projects/{project['id']}/tasks",
        json={"title": "Secret Task"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    task = r.json()

    # Non-member on all task endpoints
    r = client.get(
        f"/workspaces/{ws['id']}/projects/{project['id']}/tasks",
        headers={"Authorization": f"Bearer {stranger_token}"},
    )
    assert r.status_code == 404

    r = client.get(
        f"/workspaces/{ws['id']}/projects/{project['id']}/tasks/{task['id']}",
        headers={"Authorization": f"Bearer {stranger_token}"},
    )
    assert r.status_code == 404

    r = client.post(
        f"/workspaces/{ws['id']}/projects/{project['id']}/tasks",
        json={"title": "Hacked"},
        headers={"Authorization": f"Bearer {stranger_token}"},
    )
    assert r.status_code == 404

    r = client.patch(
        f"/workspaces/{ws['id']}/projects/{project['id']}/tasks/{task['id']}",
        json={"title": "Hacked"},
        headers={"Authorization": f"Bearer {stranger_token}"},
    )
    assert r.status_code == 404

    r = client.delete(
        f"/workspaces/{ws['id']}/projects/{project['id']}/tasks/{task['id']}",
        headers={"Authorization": f"Bearer {stranger_token}"},
    )
    assert r.status_code == 404
