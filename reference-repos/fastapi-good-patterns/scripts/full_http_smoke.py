#!/usr/bin/env python3
"""Full HTTP smoke test covering all implemented endpoints."""

import os
import sys

# Ensure repo root is on path so `app` is importable when run directly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient

from app.main import app


def main() -> int:
    import uuid
    client = TestClient(app)
    username = f"smokeuser_{uuid.uuid4().hex[:8]}"

    # BL-0001: Health check
    r = client.get("/health")
    assert r.status_code == 200, f"/health failed: {r.status_code}"
    assert r.json().get("status") == "ok", f"/health unexpected payload: {r.json()}"
    print("PASS: /health")

    # BL-0002: User registration
    r = client.post("/auth/register", json={"username": username, "password": "smokepass"})
    assert r.status_code == 201, f"/auth/register failed: {r.status_code}"
    data = r.json()
    assert data.get("username") == username, f"unexpected username: {data}"
    assert "id" in data, "missing id in response"
    assert "password" not in data, "password leaked in response"
    assert "hashed_password" not in data, "hashed_password leaked in response"
    print("PASS: /auth/register")

    # BL-0002: Duplicate registration returns 409
    r = client.post("/auth/register", json={"username": username, "password": "otherpass"})
    assert r.status_code == 409, f"duplicate register returned {r.status_code}, expected 409"
    print("PASS: /auth/register duplicate 409")

    # BL-0003: Login returns JWT with sub
    r = client.post("/auth/login", json={"username": username, "password": "smokepass"})
    assert r.status_code == 200, f"/auth/login failed: {r.status_code}"
    data = r.json()
    assert "access_token" in data, "missing access_token"
    assert data["token_type"] == "bearer", "unexpected token_type"
    from app.auth import decode_access_token
    payload = decode_access_token(data["access_token"])
    assert payload is not None, "token could not be decoded"
    assert payload.get("sub") == username, f"unexpected sub: {payload.get('sub')}"
    print("PASS: /auth/login")

    # BL-0003: Invalid credentials return 401
    r = client.post("/auth/login", json={"username": username, "password": "wrongpass"})
    assert r.status_code == 401, f"expected 401, got {r.status_code}"
    print("PASS: /auth/login invalid 401")

    # BL-0003: Protected endpoint rejects missing token
    r = client.get("/me")
    assert r.status_code == 401, f"expected 401 for missing token, got {r.status_code}"
    print("PASS: /me missing token 401")

    # BL-0003: Protected endpoint accepts valid token
    token = data["access_token"]
    r = client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, f"expected 200 for valid token, got {r.status_code}"
    user = r.json()
    assert user["username"] == username
    print("PASS: /me valid token 200")

    # BL-0005: Workspace creation (authenticated)
    r = client.post("/workspaces", json={"name": "Smoke Workspace"}, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 201, f"/workspaces create failed: {r.status_code}"
    ws = r.json()
    assert ws["name"] == "Smoke Workspace"
    assert "id" in ws
    print("PASS: /workspaces create (BL-0005)")

    # BL-0005: Unauthenticated workspace creation returns 401
    r = client.post("/workspaces", json={"name": "No Auth Workspace"})
    assert r.status_code == 401, f"expected 401 for unauthenticated workspace create, got {r.status_code}"
    print("PASS: /workspaces create unauthenticated 401 (BL-0005)")

    # BL-0006: /me/workspaces returns the workspace for owner
    r = client.get("/me/workspaces", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, f"/me/workspaces failed: {r.status_code}"
    ws_list = r.json()
    assert any(w["id"] == ws["id"] for w in ws_list), "workspace not in /me/workspaces"
    print("PASS: /me/workspaces owner sees workspace (BL-0006)")

    # BL-0006: /me/workspaces unauthenticated returns 401
    r = client.get("/me/workspaces")
    assert r.status_code == 401, f"expected 401 for unauthenticated /me/workspaces, got {r.status_code}"
    print("PASS: /me/workspaces unauthenticated 401 (BL-0006)")

    # BL-0004: Invite member
    member_name = f"member_{uuid.uuid4().hex[:8]}"
    r = client.post("/auth/register", json={"username": member_name, "password": "smokepass"})
    assert r.status_code == 201
    member = r.json()

    r = client.post(
        f"/workspaces/{ws['id']}/members",
        json={"username": member["username"]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201, f"invite member failed: {r.status_code}"
    mship = r.json()
    assert mship["role"] == "member"
    assert mship["user_id"] == member["id"]
    print("PASS: /workspaces/{id}/members invite")

    # BL-0004: Duplicate invite returns 409
    r = client.post(
        f"/workspaces/{ws['id']}/members",
        json={"username": member["username"]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 409, f"expected 409 for duplicate invite, got {r.status_code}"
    print("PASS: /workspaces/{id}/members duplicate 409")

    # BL-0004: Remove member
    r = client.delete(
        f"/workspaces/{ws['id']}/members/{member['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 204, f"remove member failed: {r.status_code}"
    print("PASS: /workspaces/{id}/members/{user_id} delete")

    # BL-0007: Invite non-existent user returns 404
    r = client.post(
        f"/workspaces/{ws['id']}/members",
        json={"username": "nonexistent_smoke_user"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 404, f"expected 404 for nonexistent user invite, got {r.status_code}"
    print("PASS: /workspaces/{id}/members invite nonexistent 404 (BL-0007)")

    # BL-0007: Remove non-member returns 404
    r = client.delete(
        f"/workspaces/{ws['id']}/members/99999",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 404, f"expected 404 for remove non-member, got {r.status_code}"
    print("PASS: /workspaces/{id}/members/{user_id} remove non-member 404 (BL-0007)")

    # BL-0007: Non-owner invite returns 403
    # Re-invite member so they can try to invite
    r = client.post(
        f"/workspaces/{ws['id']}/members",
        json={"username": member["username"]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201
    member_token = client.post("/auth/login", json={"username": member_name, "password": "smokepass"}).json()["access_token"]

    other_name = f"other_{uuid.uuid4().hex[:8]}"
    r = client.post("/auth/register", json={"username": other_name, "password": "smokepass"})
    assert r.status_code == 201
    other_user = r.json()

    r = client.post(
        f"/workspaces/{ws['id']}/members",
        json={"username": other_name},
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert r.status_code == 403, f"expected 403 for non-owner invite, got {r.status_code}"
    print("PASS: /workspaces/{id}/members non-owner invite 403 (BL-0007)")

    # BL-0007: Non-owner remove returns 403
    r = client.delete(
        f"/workspaces/{ws['id']}/members/{member['id']}",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert r.status_code == 403, f"expected 403 for non-owner remove, got {r.status_code}"
    print("PASS: /workspaces/{id}/members/{user_id} non-owner remove 403 (BL-0007)")

    # BL-0007: Assignee clearing on member removal
    from app.database import SessionLocal
    from app.models import Project, Task

    db = SessionLocal()
    project = Project(name="Smoke Project", workspace_id=ws["id"])
    db.add(project)
    db.commit()
    db.refresh(project)

    task = Task(title="Smoke Task", project_id=project.id, assignee_id=member["id"])
    db.add(task)
    db.commit()
    task_id = task.id
    db.close()

    r = client.delete(
        f"/workspaces/{ws['id']}/members/{member['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 204

    db = SessionLocal()
    task_after = db.query(Task).filter(Task.id == task_id).first()
    assert task_after.assignee_id is None, "assignee should be cleared after member removal"
    db.close()
    print("PASS: assignee cleared on member removal (BL-0007)")

    # BL-0008: Project CRUD within workspace
    # Create a project (use unique name since "Smoke Project" already exists from BL-0007 test)
    r = client.post(
        f"/workspaces/{ws['id']}/projects",
        json={"name": "BL8 Smoke Project"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201, f"create project failed: {r.status_code}"
    project = r.json()
    assert project["name"] == "BL8 Smoke Project"
    assert project["workspace_id"] == ws["id"]
    print("PASS: POST /workspaces/{id}/projects (BL-0008)")

    # Duplicate project name returns 409
    r = client.post(
        f"/workspaces/{ws['id']}/projects",
        json={"name": "BL8 Smoke Project"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 409, f"expected 409 for duplicate project, got {r.status_code}"
    print("PASS: POST /workspaces/{id}/projects duplicate 409 (BL-0008)")

    # List projects
    r = client.get(
        f"/workspaces/{ws['id']}/projects",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, f"list projects failed: {r.status_code}"
    projects = r.json()
    assert any(p["id"] == project["id"] for p in projects), "project not in list"
    print("PASS: GET /workspaces/{id}/projects (BL-0008)")

    # Get single project
    r = client.get(
        f"/workspaces/{ws['id']}/projects/{project['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, f"get project failed: {r.status_code}"
    assert r.json()["name"] == "BL8 Smoke Project"
    print("PASS: GET /workspaces/{id}/projects/{project_id} (BL-0008)")

    # Update project
    r = client.patch(
        f"/workspaces/{ws['id']}/projects/{project['id']}",
        json={"name": "BL8 Smoke Project Updated"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, f"update project failed: {r.status_code}"
    assert r.json()["name"] == "BL8 Smoke Project Updated"
    print("PASS: PATCH /workspaces/{id}/projects/{project_id} (BL-0008)")

    # Non-member gets 404 on project endpoints
    r = client.post(
        f"/workspaces/{ws['id']}/projects",
        json={"name": "Hacked"},
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert r.status_code == 404, f"expected 404 for non-member project create, got {r.status_code}"
    print("PASS: POST /workspaces/{id}/projects non-member 404 (BL-0008)")

    # Unauthenticated gets 401
    r = client.get(f"/workspaces/{ws['id']}/projects")
    assert r.status_code == 401, f"expected 401 for unauthenticated list projects, got {r.status_code}"
    print("PASS: GET /workspaces/{id}/projects unauthenticated 401 (BL-0008)")

    # Delete project
    r = client.delete(
        f"/workspaces/{ws['id']}/projects/{project['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 204, f"delete project failed: {r.status_code}"
    print("PASS: DELETE /workspaces/{id}/projects/{project_id} (BL-0008)")

    # BL-0009: Task CRUD within Project
    # Create a project for task tests
    r = client.post(
        f"/workspaces/{ws['id']}/projects",
        json={"name": "BL9 Task Project"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201, f"create project for tasks failed: {r.status_code}"
    task_project = r.json()

    # Create task
    r = client.post(
        f"/workspaces/{ws['id']}/projects/{task_project['id']}/tasks",
        json={"title": "BL9 Task"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201, f"create task failed: {r.status_code}"
    task = r.json()
    assert task["title"] == "BL9 Task"
    assert task["status"] == "todo"
    assert task["project_id"] == task_project["id"]
    print("PASS: POST /workspaces/{id}/projects/{project_id}/tasks (BL-0009)")

    # Missing title returns 422
    r = client.post(
        f"/workspaces/{ws['id']}/projects/{task_project['id']}/tasks",
        json={"description": "No title"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 422, f"expected 422 for missing title, got {r.status_code}"
    print("PASS: POST /workspaces/{id}/projects/{project_id}/tasks missing title 422 (BL-0009)")

    # List tasks
    r = client.get(
        f"/workspaces/{ws['id']}/projects/{task_project['id']}/tasks",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, f"list tasks failed: {r.status_code}"
    tasks = r.json()
    assert any(t["id"] == task["id"] for t in tasks), "task not in list"
    print("PASS: GET /workspaces/{id}/projects/{project_id}/tasks (BL-0009)")

    # Get single task
    r = client.get(
        f"/workspaces/{ws['id']}/projects/{task_project['id']}/tasks/{task['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, f"get task failed: {r.status_code}"
    assert r.json()["title"] == "BL9 Task"
    print("PASS: GET /workspaces/{id}/projects/{project_id}/tasks/{task_id} (BL-0009)")

    # Update task
    r = client.patch(
        f"/workspaces/{ws['id']}/projects/{task_project['id']}/tasks/{task['id']}",
        json={"title": "BL9 Task Updated", "status": "in_progress"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, f"update task failed: {r.status_code}"
    updated = r.json()
    assert updated["title"] == "BL9 Task Updated"
    assert updated["status"] == "in_progress"
    print("PASS: PATCH /workspaces/{id}/projects/{project_id}/tasks/{task_id} (BL-0009)")

    # Invalid status returns 422
    r = client.patch(
        f"/workspaces/{ws['id']}/projects/{task_project['id']}/tasks/{task['id']}",
        json={"status": "invalid"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 422, f"expected 422 for invalid status, got {r.status_code}"
    print("PASS: PATCH /workspaces/{id}/projects/{project_id}/tasks/{task_id} invalid status 422 (BL-0009)")

    # Non-member gets 404 on task endpoints
    r = client.get(
        f"/workspaces/{ws['id']}/projects/{task_project['id']}/tasks",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert r.status_code == 404, f"expected 404 for non-member list tasks, got {r.status_code}"
    print("PASS: GET /workspaces/{id}/projects/{project_id}/tasks non-member 404 (BL-0009)")

    # Unauthenticated gets 401
    r = client.get(f"/workspaces/{ws['id']}/projects/{task_project['id']}/tasks")
    assert r.status_code == 401, f"expected 401 for unauthenticated list tasks, got {r.status_code}"
    print("PASS: GET /workspaces/{id}/projects/{project_id}/tasks unauthenticated 401 (BL-0009)")

    # Delete task
    r = client.delete(
        f"/workspaces/{ws['id']}/projects/{task_project['id']}/tasks/{task['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 204, f"delete task failed: {r.status_code}"
    print("PASS: DELETE /workspaces/{id}/projects/{project_id}/tasks/{task_id} (BL-0009)")

    # --- BL-0010: Task Assignment ---
    # Re-invite member for assignment tests (they were removed earlier)
    r = client.post(
        f"/workspaces/{ws['id']}/members",
        json={"username": member["username"]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201, f"re-invite member failed: {r.status_code}"

    # Create a fresh task for assignment tests
    r = client.post(
        f"/workspaces/{ws['id']}/projects/{task_project['id']}/tasks",
        json={"title": "BL10 Task"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201, f"create task for assignment failed: {r.status_code}"
    bl10_task = r.json()

    # Create task with assignee
    r = client.post(
        f"/workspaces/{ws['id']}/projects/{task_project['id']}/tasks",
        json={"title": "BL10 Assigned Task", "assignee_id": member["id"]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201, f"create task with assignee failed: {r.status_code}"
    assigned_task = r.json()
    assert assigned_task["assignee_id"] == member["id"], f"unexpected assignee_id: {assigned_task['assignee_id']}"
    print("PASS: POST task with assignee_id (BL-0010)")

    # Update assignee
    r = client.patch(
        f"/workspaces/{ws['id']}/projects/{task_project['id']}/tasks/{assigned_task['id']}",
        json={"assignee_id": user["id"]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, f"update assignee failed: {r.status_code}"
    updated = r.json()
    assert updated["assignee_id"] == user["id"], f"unexpected assignee_id after update: {updated['assignee_id']}"
    print("PASS: PATCH task assignee_id (BL-0010)")

    # Non-member assignee returns 404 on create
    r = client.post(
        f"/workspaces/{ws['id']}/projects/{task_project['id']}/tasks",
        json={"title": "BL10 Bad Assignee", "assignee_id": other_user["id"]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 404, f"expected 404 for non-member assignee on create, got {r.status_code}"
    print("PASS: POST task non-member assignee 404 (BL-0010)")

    # Non-member assignee returns 404 on update
    r = client.patch(
        f"/workspaces/{ws['id']}/projects/{task_project['id']}/tasks/{bl10_task['id']}",
        json={"assignee_id": other_user["id"]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 404, f"expected 404 for non-member assignee on update, got {r.status_code}"
    print("PASS: PATCH task non-member assignee 404 (BL-0010)")

    # Clear assignee by setting null
    r = client.patch(
        f"/workspaces/{ws['id']}/projects/{task_project['id']}/tasks/{assigned_task['id']}",
        json={"assignee_id": None},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, f"clear assignee failed: {r.status_code}"
    cleared = r.json()
    assert cleared["assignee_id"] is None, f"assignee_id should be null: {cleared['assignee_id']}"
    print("PASS: PATCH task assignee_id null clears assignee (BL-0010)")

    print("All smoke tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
