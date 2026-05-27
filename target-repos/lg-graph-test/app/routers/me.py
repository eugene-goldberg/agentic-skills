from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import Task, User
from app.schemas import TaskResponse, UserResponse

router = APIRouter(tags=["me"])


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)) -> User:
    return current_user


# BL-0016
@router.get("/me/tasks", response_model=list[TaskResponse])
def my_assigned_tasks(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Task]:
    return db.query(Task).filter(Task.assignee_id == current_user.id).all()
