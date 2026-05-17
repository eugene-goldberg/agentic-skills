from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import User, Workspace, WorkspaceMembership, Project
from app.schemas import ProjectCreate, ProjectUpdate, ProjectResponse

router = APIRouter(tags=["projects"])


def _check_workspace_membership(workspace_id: int, user_id: int, db: Session) -> None:
    """Raise 404 if user is not a member of the workspace."""
    membership = (
        db.query(WorkspaceMembership)
        .filter(
            WorkspaceMembership.workspace_id == workspace_id,
            WorkspaceMembership.user_id == user_id,
        )
        .first()
    )
    if membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")


@router.post(
    "/workspaces/{workspace_id}/projects",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_project(
    workspace_id: int,
    project_in: ProjectCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Project:
    _check_workspace_membership(workspace_id, current_user.id, db)

    # Check for duplicate project name within workspace
    existing = (
        db.query(Project)
        .filter(
            Project.workspace_id == workspace_id,
            Project.name == project_in.name,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project with this name already exists in the workspace",
        )

    project = Project(name=project_in.name, workspace_id=workspace_id)
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.get(
    "/workspaces/{workspace_id}/projects",
    response_model=list[ProjectResponse],
)
def list_projects(
    workspace_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Project]:
    _check_workspace_membership(workspace_id, current_user.id, db)

    projects = db.query(Project).filter(Project.workspace_id == workspace_id).all()
    return projects


@router.get(
    "/workspaces/{workspace_id}/projects/{project_id}",
    response_model=ProjectResponse,
)
def get_project(
    workspace_id: int,
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Project:
    _check_workspace_membership(workspace_id, current_user.id, db)

    project = (
        db.query(Project)
        .filter(
            Project.id == project_id,
            Project.workspace_id == workspace_id,
        )
        .first()
    )
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


@router.patch(
    "/workspaces/{workspace_id}/projects/{project_id}",
    response_model=ProjectResponse,
)
def update_project(
    workspace_id: int,
    project_id: int,
    project_in: ProjectUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Project:
    _check_workspace_membership(workspace_id, current_user.id, db)

    project = (
        db.query(Project)
        .filter(
            Project.id == project_id,
            Project.workspace_id == workspace_id,
        )
        .first()
    )
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    # Check for duplicate name if changing name
    if project_in.name != project.name:
        existing = (
            db.query(Project)
            .filter(
                Project.workspace_id == workspace_id,
                Project.name == project_in.name,
            )
            .first()
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Project with this name already exists in the workspace",
            )

    project.name = project_in.name
    db.commit()
    db.refresh(project)
    return project


@router.delete(
    "/workspaces/{workspace_id}/projects/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_project(
    workspace_id: int,
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    _check_workspace_membership(workspace_id, current_user.id, db)

    project = (
        db.query(Project)
        .filter(
            Project.id == project_id,
            Project.workspace_id == workspace_id,
        )
        .first()
    )
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    db.delete(project)
    db.commit()
    return None
