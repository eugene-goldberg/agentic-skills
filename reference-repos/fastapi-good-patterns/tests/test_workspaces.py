import pytest
from fastapi.testclient import TestClient

from app.models import Workspace, WorkspaceMembership, WorkspaceRole


def _register(client: TestClient, username: str, password: str = "secret123") -> dict:
    r = client.post("/auth/register", json={"username": username, "password": password})
    assert r.status_code == 201
    return r.json()


def _login(client: TestClient, username: str, password: str = "secret123") -> str:
    r = client.post("/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200
    return r.json()["access_token"]


# --- Acceptance 1: Models exist (tested implicitly via endpoints) ---


def test_create_workspace_sets_creator_as_owner(client: TestClient) -> None:
    user = _register(client, "wsowner")
    token = _login(client, "wsowner")

    r = client.post("/workspaces", json={"name": "My Workspace"}, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 201
    data = r.json()
    assert data["name"] == "My Workspace"
    assert "id" in data

    # Verify owner membership in DB
    from tests.conftest import TestSessionLocal
    db = TestSessionLocal()
    ws = db.query(Workspace).filter(Workspace.id == data["id"]).first()
    assert ws is not None
    membership = (
        db.query(WorkspaceMembership)
        .filter(WorkspaceMembership.workspace_id == ws.id, WorkspaceMembership.user_id == user["id"])
        .first()
    )
    assert membership is not None
    assert membership.role == WorkspaceRole.owner
    db.close()


def test_create_workspace_unauthenticated_returns_401(client: TestClient) -> None:
    r = client.post("/workspaces", json={"name": "No Auth Workspace"})
    assert r.status_code == 401


# --- Acceptance 2: WorkspaceMembership links User to Workspace with role ---


def test_workspace_membership_role_is_owner_or_member(client: TestClient) -> None:
    owner = _register(client, "owner1")
    member = _register(client, "member1")
    owner_token = _login(client, "owner1")
    member_token = _login(client, "member1")

    r = client.post("/workspaces", json={"name": "Team Workspace"}, headers={"Authorization": f"Bearer {owner_token}"})
    ws_id = r.json()["id"]

    # Invite member by username
    r = client.post(
        f"/workspaces/{ws_id}/members",
        json={"username": member["username"]},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert r.status_code == 201
    data = r.json()
    assert data["role"] == "member"
    assert data["user_id"] == member["id"]
    assert data["workspace_id"] == ws_id


def test_invite_nonexistent_user_returns_404(client: TestClient) -> None:
    owner = _register(client, "owner2")
    owner_token = _login(client, "owner2")

    r = client.post("/workspaces", json={"name": "Private"}, headers={"Authorization": f"Bearer {owner_token}"})
    ws_id = r.json()["id"]

    r = client.post(
        f"/workspaces/{ws_id}/members",
        json={"username": "ghost"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert r.status_code == 404


def test_invite_duplicate_member_returns_409(client: TestClient) -> None:
    owner = _register(client, "owner3")
    member = _register(client, "member3")
    owner_token = _login(client, "owner3")

    r = client.post("/workspaces", json={"name": "Dup Test"}, headers={"Authorization": f"Bearer {owner_token}"})
    ws_id = r.json()["id"]

    r = client.post(
        f"/workspaces/{ws_id}/members",
        json={"username": member["username"]},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert r.status_code == 201

    r = client.post(
        f"/workspaces/{ws_id}/members",
        json={"username": member["username"]},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert r.status_code == 409


def test_nonowner_invite_returns_403(client: TestClient) -> None:
    owner = _register(client, "owner4")
    member = _register(client, "member4")
    other = _register(client, "other4")
    owner_token = _login(client, "owner4")
    member_token = _login(client, "member4")

    r = client.post("/workspaces", json={"name": "Restrict"}, headers={"Authorization": f"Bearer {owner_token}"})
    ws_id = r.json()["id"]

    # Add member4 as member
    client.post(
        f"/workspaces/{ws_id}/members",
        json={"username": member["username"]},
        headers={"Authorization": f"Bearer {owner_token}"},
    )

    # member4 tries to invite other4
    r = client.post(
        f"/workspaces/{ws_id}/members",
        json={"username": other["username"]},
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert r.status_code == 403


def test_remove_member_by_owner(client: TestClient) -> None:
    owner = _register(client, "owner5")
    member = _register(client, "member5")
    owner_token = _login(client, "owner5")

    r = client.post("/workspaces", json={"name": "Remove Test"}, headers={"Authorization": f"Bearer {owner_token}"})
    ws_id = r.json()["id"]

    client.post(
        f"/workspaces/{ws_id}/members",
        json={"username": member["username"]},
        headers={"Authorization": f"Bearer {owner_token}"},
    )

    r = client.delete(
        f"/workspaces/{ws_id}/members/{member['id']}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert r.status_code == 204


def test_remove_nonmember_returns_404(client: TestClient) -> None:
    owner = _register(client, "owner6")
    owner_token = _login(client, "owner6")

    r = client.post("/workspaces", json={"name": "Remove 404"}, headers={"Authorization": f"Bearer {owner_token}"})
    ws_id = r.json()["id"]

    r = client.delete(
        f"/workspaces/{ws_id}/members/99999",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert r.status_code == 404


def test_nonowner_remove_returns_403(client: TestClient) -> None:
    owner = _register(client, "owner7")
    member = _register(client, "member7")
    owner_token = _login(client, "owner7")
    member_token = _login(client, "member7")

    r = client.post("/workspaces", json={"name": "Remove 403"}, headers={"Authorization": f"Bearer {owner_token}"})
    ws_id = r.json()["id"]

    client.post(
        f"/workspaces/{ws_id}/members",
        json={"username": member["username"]},
        headers={"Authorization": f"Bearer {owner_token}"},
    )

    r = client.delete(
        f"/workspaces/{ws_id}/members/{owner['id']}",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert r.status_code == 403


def test_remove_member_clears_assignee_in_workspace(client: TestClient) -> None:
    from tests.conftest import TestSessionLocal
    from app.models import Project, Task

    owner = _register(client, "owner8")
    member = _register(client, "member8")
    owner_token = _login(client, "owner8")

    r = client.post("/workspaces", json={"name": "Assignee Clear"}, headers={"Authorization": f"Bearer {owner_token}"})
    ws_id = r.json()["id"]

    client.post(
        f"/workspaces/{ws_id}/members",
        json={"username": member["username"]},
        headers={"Authorization": f"Bearer {owner_token}"},
    )

    db = TestSessionLocal()
    project = Project(name="Test Project", workspace_id=ws_id)
    db.add(project)
    db.commit()
    db.refresh(project)

    task = Task(title="Test Task", project_id=project.id, assignee_id=member["id"])
    db.add(task)
    db.commit()
    task_id = task.id
    db.close()

    r = client.delete(
        f"/workspaces/{ws_id}/members/{member['id']}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert r.status_code == 204

    db = TestSessionLocal()
    task_after = db.query(Task).filter(Task.id == task_id).first()
    assert task_after is not None
    assert task_after.assignee_id is None
    db.close()


def test_remove_member_does_not_affect_other_workspaces(client: TestClient) -> None:
    from tests.conftest import TestSessionLocal
    from app.models import Project, Task

    owner = _register(client, "owner9")
    member = _register(client, "member9")
    owner_token = _login(client, "owner9")

    r = client.post("/workspaces", json={"name": "WS1"}, headers={"Authorization": f"Bearer {owner_token}"})
    ws1_id = r.json()["id"]

    r = client.post("/workspaces", json={"name": "WS2"}, headers={"Authorization": f"Bearer {owner_token}"})
    ws2_id = r.json()["id"]

    client.post(
        f"/workspaces/{ws1_id}/members",
        json={"username": member["username"]},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    client.post(
        f"/workspaces/{ws2_id}/members",
        json={"username": member["username"]},
        headers={"Authorization": f"Bearer {owner_token}"},
    )

    db = TestSessionLocal()
    project1 = Project(name="P1", workspace_id=ws1_id)
    project2 = Project(name="P2", workspace_id=ws2_id)
    db.add_all([project1, project2])
    db.commit()
    db.refresh(project1)
    db.refresh(project2)

    task1 = Task(title="T1", project_id=project1.id, assignee_id=member["id"])
    task2 = Task(title="T2", project_id=project2.id, assignee_id=member["id"])
    db.add_all([task1, task2])
    db.commit()
    task1_id = task1.id
    task2_id = task2.id
    db.close()

    # Remove member from ws1 only
    r = client.delete(
        f"/workspaces/{ws1_id}/members/{member['id']}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert r.status_code == 204

    db = TestSessionLocal()
    t1 = db.query(Task).filter(Task.id == task1_id).first()
    t2 = db.query(Task).filter(Task.id == task2_id).first()
    assert t1.assignee_id is None
    assert t2.assignee_id == member["id"]
    db.close()


# --- Acceptance 3: Migration / auto-create mechanism ---


def test_tables_are_created_via_create_all(client: TestClient) -> None:
    from tests.conftest import test_engine
    from sqlalchemy import inspect
    inspector = inspect(test_engine)
    tables = inspector.get_table_names()
    assert "users" in tables
    assert "workspaces" in tables
    assert "workspace_memberships" in tables


# --- Acceptance 4: Database connection configurable via env var ---


def test_database_url_env_var_is_used(monkeypatch) -> None:
    import os
    import importlib
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./test_env.db")
    # Re-import to pick up env var
    from app import database
    importlib.reload(database)
    assert "test_env.db" in database.DATABASE_URL
