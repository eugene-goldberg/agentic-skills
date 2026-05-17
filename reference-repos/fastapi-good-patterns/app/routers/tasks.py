from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import User, Workspace, WorkspaceMembership, Project, Task, TaskStatus
from app.schemas import TaskCreate, TaskUpdate, TaskResponse

router = APIRouter(tags=["tasks"])


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
    "/workspaces/{workspace_id}/projects/{project_id}/tasks",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_task(
    workspace_id: int,
    project_id: int,
    task_in: TaskCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Task:
    _check_workspace_membership(workspace_id, current_user.id, db)

    # Verify project exists and belongs to workspace
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

    # Validate status if provided
    status_value = TaskStatus.todo
    if task_in.status is not None:
        try:
            status_value = TaskStatus(task_in.status)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid status value",
            )

    # Validate assignee if provided
    if task_in.assignee_id is not None:
        assignee_membership = (
            db.query(WorkspaceMembership)
            .filter(
                WorkspaceMembership.workspace_id == workspace_id,
                WorkspaceMembership.user_id == task_in.assignee_id,
            )
            .first()
        )
        if assignee_membership is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Assignee not found",
            )

    task = Task(
        title=task_in.title,
        description=task_in.description,
        status=status_value,
        project_id=project_id,
        assignee_id=task_in.assignee_id,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


@router.get(
    "/workspaces/{workspace_id}/projects/{project_id}/tasks",
    response_model=list[TaskResponse],
)
def list_tasks(
    workspace_id: int,
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Task]:
    _check_workspace_membership(workspace_id, current_user.id, db)

    # Verify project exists and belongs to workspace
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

    tasks = db.query(Task).filter(Task.project_id == project_id).all()
    return tasks


@router.get(
    "/workspaces/{workspace_id}/projects/{project_id}/tasks/{task_id}",
    response_model=TaskResponse,
)
def get_task(
    workspace_id: int,
    project_id: int,
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Task:
    _check_workspace_membership(workspace_id, current_user.id, db)

    task = (
        db.query(Task)
        .join(Project)
        .filter(
            Task.id == task_id,
            Task.project_id == project_id,
            Project.workspace_id == workspace_id,
        )
        .first()
    )
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task


@router.patch(
    "/workspaces/{workspace_id}/projects/{project_id}/tasks/{task_id}",
    response_model=TaskResponse,
)
def update_task(
    workspace_id: int,
    project_id: int,
    task_id: int,
    task_in: TaskUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Task:
    _check_workspace_membership(workspace_id, current_user.id, db)

    task = (
        db.query(Task)
        .join(Project)
        .filter(
            Task.id == task_id,
            Task.project_id == project_id,
            Project.workspace_id == workspace_id,
        )
        .first()
    )
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    # Update title if provided
    if task_in.title is not None:
        task.title = task_in.title

    # Update description if provided
    if task_in.description is not None:
        task.description = task_in.description

    # Update status if provided
    if task_in.status is not None:
        try:
            task.status = TaskStatus(task_in.status)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid status value",
            )

    # Update assignee if provided
    if task_in.assignee_id is not None:
        assignee_membership = (
            db.query(WorkspaceMembership)
            .filter(
                WorkspaceMembership.workspace_id == workspace_id,
                WorkspaceMembership.user_id == task_in.assignee_id,
            )
            .first()
        )
        if assignee_membership is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Assignee not found",
            )
        task.assignee_id = task_in.assignee_id
    elif "assignee_id" in task_in.model_dump(exclude_unset=True):
        # Explicitly set to null
        task.assignee_id = None

    db.commit()
    db.refresh(task)
    return task


@router.delete(
    "/workspaces/{workspace_id}/projects/{project_id}/tasks/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_task(
    workspace_id: int,
    project_id: int,
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    _check_workspace_membership(workspace_id, current_user.id, db)

    task = (
        db.query(Task)
        .join(Project)
        .filter(
            Task.id == task_id,
            Task.project_id == project_id,
            Project.workspace_id == workspace_id,
        )
        .first()
    )
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    db.delete(task)
    db.commit()
    return None
