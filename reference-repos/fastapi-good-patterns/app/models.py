from sqlalchemy import Column, Integer, String, ForeignKey, Enum
from sqlalchemy.orm import relationship
import enum

from app.database import Base


class WorkspaceRole(str, enum.Enum):
    owner = "owner"
    member = "member"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)

    memberships = relationship("WorkspaceMembership", back_populates="user", cascade="all, delete-orphan")


class Workspace(Base):
    __tablename__ = "workspaces"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)

    memberships = relationship("WorkspaceMembership", back_populates="workspace", cascade="all, delete-orphan")
    projects = relationship("Project", back_populates="workspace", cascade="all, delete-orphan")


class WorkspaceMembership(Base):
    __tablename__ = "workspace_memberships"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=False)
    role = Column(Enum(WorkspaceRole), nullable=False, default=WorkspaceRole.member)

    user = relationship("User", back_populates="memberships")
    workspace = relationship("Workspace", back_populates="memberships")


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=False)

    workspace = relationship("Workspace", back_populates="projects")
    tasks = relationship("Task", back_populates="project", cascade="all, delete-orphan")


class TaskStatus(str, enum.Enum):
    todo = "todo"
    in_progress = "in_progress"
    done = "done"


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(String, nullable=True)
    status = Column(Enum(TaskStatus), nullable=False, default=TaskStatus.todo)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    assignee_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    project = relationship("Project", back_populates="tasks")
