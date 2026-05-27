from datetime import datetime
from pydantic import BaseModel, EmailStr, ConfigDict


class SignupRequest(BaseModel):
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: EmailStr
    created_at: datetime


class WorkspaceCreate(BaseModel):
    name: str


class WorkspaceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    created_at: datetime


from app.models import WorkspaceRole  # noqa: E402


class InviteMemberRequest(BaseModel):
    email: EmailStr
    role: WorkspaceRole


class MembershipResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: int
    workspace_id: int
    role: WorkspaceRole


from app.models import TaskStatus  # noqa: E402
from typing import Optional  # noqa: E402


class ProjectCreate(BaseModel):
    name: str


class ProjectUpdate(BaseModel):
    name: Optional[str] = None


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    workspace_id: int
    created_at: datetime


class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = None
    status: Optional[TaskStatus] = None
    assignee_email: Optional[EmailStr] = None


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[TaskStatus] = None
    assignee_email: Optional[EmailStr] = None
    clear_assignee: bool = False


class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    description: Optional[str]
    status: TaskStatus
    project_id: int
    assignee_id: Optional[int]
    created_at: datetime


class CommentCreate(BaseModel):
    body: str


class CommentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    body: str
    task_id: int
    author_id: int
    created_at: datetime
