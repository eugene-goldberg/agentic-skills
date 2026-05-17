from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import User, Workspace, WorkspaceMembership, WorkspaceRole, Project, Task
from app.schemas import (
    WorkspaceCreate,
    WorkspaceResponse,
    WorkspaceMembershipResponse,
    InviteMemberRequest,
)

router = APIRouter(tags=["workspaces"])


@router.post("/workspaces", response_model=WorkspaceResponse, status_code=status.HTTP_201_CREATED)
def create_workspace(
    workspace_in: WorkspaceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Workspace:
    workspace = Workspace(name=workspace_in.name)
    db.add(workspace)
    db.flush()  # get workspace.id before commit

    membership = WorkspaceMembership(
        user_id=current_user.id,
        workspace_id=workspace.id,
        role=WorkspaceRole.owner,
    )
    db.add(membership)
    db.commit()
    db.refresh(workspace)
    return workspace


@router.post(
    "/workspaces/{workspace_id}/members",
    response_model=WorkspaceMembershipResponse,
    status_code=status.HTTP_201_CREATED,
)
def invite_member(
    workspace_id: int,
    invite_in: InviteMemberRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WorkspaceMembership:
    # Check current user is owner of the workspace
    current_membership = (
        db.query(WorkspaceMembership)
        .filter(
            WorkspaceMembership.workspace_id == workspace_id,
            WorkspaceMembership.user_id == current_user.id,
        )
        .first()
    )
    if current_membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    if current_membership.role != WorkspaceRole.owner:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only owners can invite members")

    # Check target user exists by username
    target_user = db.query(User).filter(User.username == invite_in.username).first()
    if target_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Check if already a member
    existing = (
        db.query(WorkspaceMembership)
        .filter(
            WorkspaceMembership.workspace_id == workspace_id,
            WorkspaceMembership.user_id == target_user.id,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User is already a member")

    membership = WorkspaceMembership(
        user_id=target_user.id,
        workspace_id=workspace_id,
        role=WorkspaceRole.member,
    )
    db.add(membership)
    db.commit()
    db.refresh(membership)
    return membership


@router.delete("/workspaces/{workspace_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(
    workspace_id: int,
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    # Check current user is owner
    current_membership = (
        db.query(WorkspaceMembership)
        .filter(
            WorkspaceMembership.workspace_id == workspace_id,
            WorkspaceMembership.user_id == current_user.id,
        )
        .first()
    )
    if current_membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    if current_membership.role != WorkspaceRole.owner:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only owners can remove members")

    # Check target membership exists
    target_membership = (
        db.query(WorkspaceMembership)
        .filter(
            WorkspaceMembership.workspace_id == workspace_id,
            WorkspaceMembership.user_id == user_id,
        )
        .first()
    )
    if target_membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")

    # Clear assignee on all tasks in this workspace assigned to the removed user
    tasks = (
        db.query(Task)
        .join(Project)
        .filter(
            Project.workspace_id == workspace_id,
            Task.assignee_id == user_id,
        )
        .all()
    )
    for task in tasks:
        task.assignee_id = None

    db.delete(target_membership)
    db.commit()
    return None
