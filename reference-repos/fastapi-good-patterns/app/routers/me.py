from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.dependencies import get_current_user
from app.database import get_db
from app.models import User, WorkspaceMembership
from app.schemas import UserResponse, WorkspaceResponse

router = APIRouter(tags=["me"])


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@router.get("/me/workspaces", response_model=list[WorkspaceResponse])
def get_my_workspaces(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[WorkspaceResponse]:
    memberships = (
        db.query(WorkspaceMembership)
        .filter(WorkspaceMembership.user_id == current_user.id)
        .all()
    )
    return [m.workspace for m in memberships]
