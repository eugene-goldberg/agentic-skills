from fastapi import FastAPI

from app.database import Base, engine
from app.routers import auth, health, me, projects, tasks, workspaces

# Import models so Base.metadata.create_all sees all tables.
import app.models  # noqa: F401

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Project Tracker v1")
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(me.router)
app.include_router(workspaces.router)
app.include_router(projects.router)
app.include_router(tasks.router)
