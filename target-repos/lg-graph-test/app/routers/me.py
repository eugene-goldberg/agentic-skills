from fastapi import APIRouter, Depends

from app.dependencies import get_current_user
from app.models import User
from app.schemas import UserResponse

router = APIRouter()


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)) -> User:
    return current_user
