from pydantic import BaseModel, ConfigDict


class UserCreate(BaseModel):
    username: str
    password: str


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str


# Workspace schemas

class WorkspaceCreate(BaseModel):
    name: str


class WorkspaceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class WorkspaceMembershipResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    workspace_id: int
    role: str


class InviteMemberRequest(BaseModel):
    username: str


# Project schemas

class ProjectCreate(BaseModel):
    name: str


class ProjectUpdate(BaseModel):
    name: str


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    workspace_id: int


class TaskCreate(BaseModel):
    title: str
    description: str | None = None
    status: str | None = None
    assignee_id: int | None = None


class TaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    status: str | None = None
    assignee_id: int | None = None


class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str | None = None
    status: str
    project_id: int
    assignee_id: int | None = None
